import importlib.util
import unittest
import tempfile
from unittest.mock import patch
from pathlib import Path

spec = importlib.util.spec_from_file_location('updater', Path(__file__).with_name('nft-domain-update.py'))
u = importlib.util.module_from_spec(spec)
spec.loader.exec_module(u)


def config(rules):
    s = '#!/usr/sbin/nft -f\ndefine LOCAL_IP = 10.0.0.1\ntable ip port_forward {\n    chain prerouting {\n        type nat hook prerouting priority -100; policy accept;\n'
    for port, ip, dest in rules:
        for proto in ('tcp', 'udp'):
            s += f'        {proto} dport {port} dnat to {ip}:{dest}\n'
    s += '    }\n    chain postrouting {\n        type nat hook postrouting priority 100; policy accept;\n'
    for port, ip, dest in rules:
        for proto in ('tcp', 'udp'):
            s += f'        ip daddr {ip} {proto} dport {dest} ct status dnat snat to $LOCAL_IP\n'
    return s + '    }\n}\n'


class Tests(unittest.TestCase):
    def test_single_and_noop(self):
        original = config([('1000', '1.1.1.1', '443')])
        self.assertEqual(u.transform(original, {'1000': '1.1.1.1'})[0], original)
        updated, changes = u.transform(original, {'1000': '2.2.2.2'})
        self.assertEqual(len(changes), 1)
        self.assertEqual({m.group(4) for m in u.DNAT.finditer(updated)}, {'2.2.2.2'})
        self.assertEqual({m.group(2) for m in u.SNAT.finditer(updated)}, {'2.2.2.2'})

    def test_shared_target_retained(self):
        original = config([('1000', '1.1.1.1', '443'), ('1001', '1.1.1.1', '443')])
        updated, _ = u.transform(original, {'1000': '2.2.2.2'})
        self.assertEqual({m.group(2) for m in u.SNAT.finditer(updated)}, {'1.1.1.1', '2.2.2.2'})

    def test_swap(self):
        original = config([('1000', '1.1.1.1', '443'), ('1001', '2.2.2.2', '443')])
        updated, _ = u.transform(original, {'1000': '2.2.2.2', '1001': '1.1.1.1'})
        self.assertEqual({m.group(2) for m in u.SNAT.finditer(updated)}, {'1.1.1.1', '2.2.2.2'})

    def test_missing_snat_and_rule_rejected(self):
        original = config([('1000', '1.1.1.1', '443')])
        with self.assertRaises(ValueError): u.transform(original, {'1001': '2.2.2.2'})
        with self.assertRaises(ValueError): u.transform(original.replace('ip daddr 1.1.1.1 udp', 'ip daddr 1.1.1.2 udp'), {'1000': '2.2.2.2'})

    def test_dns_failure_keeps_original(self):
        original = config([('1000', '1.1.1.1', '443')])
        with tempfile.TemporaryDirectory() as tmp:
            conf = Path(tmp) / 'port-forward.conf'
            mapping = Path(tmp) / 'domains.json'
            conf.write_text(original)
            mapping.write_text('{"1000": "example.com"}')
            with patch.object(u, 'CONF', conf), patch.object(u, 'MAPPING', mapping), \
                 patch.object(u, 'lookup', side_effect=ValueError('DNS error')), \
                 patch.object(u, 'nft_run') as nft:
                self.assertEqual(u.update(), 1)
                nft.assert_not_called()
                self.assertEqual(conf.read_text(), original)

if __name__ == '__main__': unittest.main()
