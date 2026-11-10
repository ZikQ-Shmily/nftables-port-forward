#!/usr/bin/env python3
"""Manage domain bindings using the same validation as the DNS updater."""
import argparse
import importlib.util
import ipaddress
import json
import os
import sys
import tempfile
from pathlib import Path

spec = importlib.util.spec_from_file_location('updater', Path(__file__).with_name('nft-domain-update.py'))
updater = importlib.util.module_from_spec(spec)
spec.loader.exec_module(updater)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--file', required=True)
    parser.add_argument('action', choices=['get', 'set', 'delete', 'clear', 'resolve'])
    parser.add_argument('port', nargs='?')
    parser.add_argument('domain', nargs='?')
    args = parser.parse_args()
    path = Path(args.file)
    if args.action == 'resolve':
        # Reuse validation without persisting a temporary mapping.
        domain = args.port
        updater.validate_mapping({'1': domain})
        addresses = updater.lookup(domain)
        print(sorted(addresses, key=lambda x: int(ipaddress.IPv4Address(x)))[0])
        return
    data = updater.load_mapping(path) if path.exists() else {}
    if args.action == 'get':
        print(data.get(args.port, ''))
        return
    if args.action == 'set':
        updater.validate_mapping({args.port: args.domain})
        data[args.port] = args.domain
    elif args.action == 'delete':
        data.pop(args.port, None)
    elif args.action == 'clear':
        data = {}
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, name = tempfile.mkstemp(prefix='.domain-targets-', dir=str(path.parent))
    try:
        with os.fdopen(fd, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=True, indent=2, sort_keys=True)
            f.write('\n')
            f.flush()
            os.fsync(f.fileno())
        os.chmod(name, 0o600)
        os.replace(name, path)
    finally:
        if os.path.exists(name):
            os.unlink(name)


if __name__ == '__main__':
    try:
        main()
    except Exception as exc:
        print(f'域名配置错误: {exc}', file=sys.stderr)
        sys.exit(1)
