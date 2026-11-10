#!/usr/bin/env python3
"""Refresh domain-backed IPv4 targets in the managed port-forward.conf."""
import argparse
import fcntl
import ipaddress
import json
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path

CONF = Path('/etc/nftables.d/port-forward.conf')
MAPPING = Path('/etc/nftables.d/domain-targets.json')
LOCK = Path('/run/lock/nft-domain-update.lock')
DNAT = re.compile(r'^([ \t]*)(tcp|udp) dport (\d+) dnat to ([0-9.]+):(\d+)[ \t]*$', re.M)
SNAT = re.compile(r'^([ \t]*)ip daddr ([0-9.]+) (tcp|udp) dport (\d+) ct status dnat snat to \$LOCAL_IP[ \t]*$', re.M)
TABLE = re.compile(r'^table ip port_forward \{[ \t]*$', re.M)


def ipv4(value):
    return str(ipaddress.IPv4Address(value))


def lookup(domain):
    # getent follows the host's configured name service (including /etc/hosts).
    result = subprocess.run(['getent', 'ahostsv4', domain], capture_output=True, text=True, timeout=15, check=True)
    addresses = set()
    for line in result.stdout.splitlines():
        try:
            addresses.add(ipv4(line.split()[0]))
        except (ValueError, IndexError):
            continue
    if not addresses:
        raise ValueError('未查询到 IPv4 地址')
    return addresses


def load_mapping(path):
    def unique_pairs(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError(f'映射端口重复: {key}')
            result[key] = value
        return result
    data = json.loads(path.read_text(encoding='utf-8'), object_pairs_hook=unique_pairs)
    return validate_mapping(data)


def validate_mapping(data):
    if not isinstance(data, dict):
        raise ValueError('映射文件必须是 JSON 对象')
    clean = {}
    for port, domain in data.items():
        if not isinstance(port, str) or not re.fullmatch(r'[1-9][0-9]{0,4}', port) or int(port) > 65535:
            raise ValueError(f'无效的本机端口: {port}')
        if not isinstance(domain, str) or len(domain) > 253 or not re.fullmatch(r'(?=.{1,253}$)(?:[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?\.)*[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?\.?', domain):
            raise ValueError(f'无效的域名: {domain}')
        clean[port] = domain
    return clean


def transform(config, targets):
    if len(TABLE.findall(config)) != 1:
        raise ValueError('配置不是主脚本生成的 table ip port_forward 格式')
    active_lines = [line for line in config.splitlines() if not line.lstrip().startswith('#')]
    dnat_lines = [line for line in active_lines if re.search(r'\bdnat\s+to\b', line)]
    snat_lines = [line for line in active_lines if re.search(r'\bsnat\s+to\b', line)]
    if len(dnat_lines) != len(list(DNAT.finditer(config))) or len(snat_lines) != len(list(SNAT.finditer(config))):
        raise ValueError('发现无法识别的 DNAT/SNAT 规则，拒绝修改')
    rules = {}
    for match in DNAT.finditer(config):
        indent, proto, port, addr, dport = match.groups()
        addr = ipv4(addr)
        rules.setdefault(port, []).append((proto, addr, dport))
    for port, entries in rules.items():
        if len(entries) != 2 or {e[0] for e in entries} != {'tcp', 'udp'} or len({e[1:] for e in entries}) != 1:
            raise ValueError(f'端口 {port} 的 TCP/UDP 规则不匹配')
    for port in targets:
        if port not in rules:
            raise ValueError(f'找不到本机端口 {port} 的转发规则')
    changes = {p: (entries[0][1], targets[p], entries[0][2]) for p, entries in rules.items() if p in targets and targets[p] != entries[0][1]}
    if not changes:
        return config, changes
    snat_pairs = {(m.group(2), m.group(3), m.group(4)) for m in SNAT.finditer(config)}
    for old, new, dport in changes.values():
        if not all((old, proto, dport) in snat_pairs for proto in ('tcp', 'udp')):
            raise ValueError(f'找不到完整的 SNAT 规则: {old}:{dport}')
    updated = DNAT.sub(lambda m: f'{m.group(1)}{m.group(2)} dport {m.group(3)} dnat to {targets.get(m.group(3), m.group(4))}:{m.group(5)}', config)
    final_pairs = {(targets.get(port, entries[0][1]), entries[0][2]) for port, entries in rules.items()}
    # Keep any original SNAT still used by another forwarding rule. Duplicate
    # new entries are harmless, but avoid creating them in the first place.
    affected = {(old, dport) for old, _, dport in changes.values()}
    retained = {(addr, proto, dport) for addr, proto, dport in snat_pairs
                if (addr, dport) not in affected or (addr, dport) in final_pairs}
    required = {(new, proto, dport) for _, new, dport in changes.values() for proto in ('tcp', 'udp')}
    missing = sorted(required - retained)
    def rewrite_snat(m):
        indent, old, proto, dport = m.groups()
        if (old, dport) in affected and (old, dport) not in final_pairs:
            return ''
        return m.group(0)
    updated = SNAT.sub(rewrite_snat, updated)
    if missing:
        # Insert into the existing postrouting chain, immediately after its hook.
        hook = '        type nat hook postrouting priority 100; policy accept;'
        if updated.count(hook) != 1:
            raise ValueError('无法识别预期的 postrouting 链')
        additions = ''.join(f'\n        ip daddr {addr} {proto} dport {dport} ct status dnat snat to $LOCAL_IP'
                            for addr, proto, dport in missing)
        updated = updated.replace(hook, hook + additions, 1)
    # Comments are descriptive only; update original per-port comments.
    for port, (old, new, dport) in changes.items():
        updated = updated.replace(f'# 转发: 本机:{port} -> {old}:{dport}', f'# 转发: 本机:{port} -> {new}:{dport}')
    return updated, changes


def nft_run(config, check=False):
    # A single nft batch is committed atomically: existing table survives failure.
    batch = 'delete table ip port_forward\n' + config
    return subprocess.run(['nft'] + (['-c'] if check else []) + ['-f', '-'], input=batch, text=True, capture_output=True, check=True)


def update():
    mapping = load_mapping(MAPPING)
    if not mapping:
        print('没有配置域名目标。')
        return 0
    original = CONF.read_text(encoding='utf-8')
    # Validate the entire managed layout before any DNS or firewall operation.
    transform(original, {})
    rules = {m.group(3): m.group(4) for m in DNAT.finditer(original)}
    targets = {}
    failed = False
    for port, domain in mapping.items():
        if port not in rules:
            raise ValueError(f'映射的端口 {port} 不存在；请先使用主脚本添加')
        try:
            addresses = lookup(domain)
            # Keep the existing address when still present to avoid DNS rotation churn.
            targets[port] = rules[port] if rules[port] in addresses else sorted(addresses, key=lambda x: int(ipaddress.IPv4Address(x)))[0]
        except (OSError, subprocess.SubprocessError, ValueError) as exc:
            print(f'{domain}: 查询失败，保留旧地址：{exc}', file=sys.stderr)
            failed = True
    updated, changes = transform(original, targets)
    if not changes:
        print('没有需要更新的地址。')
        return 1 if failed else 0
    # Verify and commit the whole transaction before replacing the boot config.
    nft_run(updated, check=True)
    stat = CONF.stat()
    fd, temp_name = tempfile.mkstemp(prefix='.port-forward.', dir=str(CONF.parent))
    try:
        with os.fdopen(fd, 'w', encoding='utf-8') as f:
            f.write(updated)
            f.flush()
            os.fsync(f.fileno())
        os.chmod(temp_name, stat.st_mode & 0o777)
        os.chown(temp_name, stat.st_uid, stat.st_gid)
        if CONF.read_text(encoding='utf-8') != original:
            raise RuntimeError('配置在更新过程中被修改，已取消；请重试')
        nft_run(updated)
        try:
            os.replace(temp_name, CONF)
        except OSError:
            # Try to restore the active rules if persistence fails.
            nft_run(original)
            raise
    finally:
        if os.path.exists(temp_name):
            os.unlink(temp_name)
    for port, (old, new, dport) in changes.items():
        print(f'{port}: {old}:{dport} -> {new}:{dport} ({mapping[port]})')
    return 1 if failed else 0


def main():
    parser = argparse.ArgumentParser(description='更新nftables 脚本中的域名转发目标')
    parser.parse_args()
    if os.geteuid() != 0:
        sys.exit('请以 root 权限运行')
    try:
        LOCK.parent.mkdir(parents=True, exist_ok=True)
        with LOCK.open('w') as lock:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            return update()
    except (OSError, ValueError, RuntimeError, subprocess.SubprocessError) as exc:
        if isinstance(exc, subprocess.CalledProcessError) and exc.stderr:
            print(exc.stderr.strip(), file=sys.stderr)
        print(f'更新失败: {exc}', file=sys.stderr)
        return 1

if __name__ == '__main__':
    sys.exit(main())
