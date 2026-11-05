import importlib.util
import json
from pathlib import Path
import unittest
from unittest import mock

spec = importlib.util.spec_from_file_location('war3_connection_modes', Path('apps/war3-battle-platform/connection_modes.py'))
modes = importlib.util.module_from_spec(spec); spec.loader.exec_module(modes)

class ConnectionModeTests(unittest.TestCase):
    def test_migration_and_separate_profiles(self):
        legacy={'server_host':'example.test','server_port':47653,'fingerprint':'a'*64,'host_mode':False}
        profiles=modes.load_profiles(legacy)
        self.assertEqual(profiles['direct'],{**legacy,'ipv6_enabled':False})
        self.assertEqual(profiles['zerotier'],modes.PROFILE_DEFAULT)
        stored={'connection_profiles':{'direct':legacy,'zerotier':{'server_host':'10.10.0.2','server_port':1234,'fingerprint':'b'*64,'host_mode':False}}}
        profiles=modes.load_profiles(stored)
        self.assertEqual(profiles['direct']['server_host'],'example.test')
        self.assertEqual(profiles['zerotier']['server_host'],'10.10.0.2')
        profiles['zerotier']['server_host']='10.10.0.3'
        self.assertEqual(profiles['direct']['server_host'],'example.test')

    def test_zerotier_address_validation(self):
        self.assertEqual(modes.normalize_address('zerotier',' 10.147.17.2 '),'10.147.17.2')
        self.assertEqual(modes.normalize_address('direct',' example.test '),'example.test')
        for address in ('','example.test','127.0.0.1','0.0.0.0','169.254.1.1','224.0.0.1','2001:db8::1'):
            with self.assertRaises(ValueError): modes.normalize_address('zerotier',address)

    def test_ipv6_address_support_and_filtering(self):
        self.assertEqual(modes.normalize_address('direct','[2409:8a31:414:d0b4::1000]'),'2409:8a31:414:d0b4::1000')
        output=json.dumps(['2409:8a31:414:d0b4::1000','2409:8a31:414:d0b4::1000','fe80::1','fd00::1','ff02::1','127.0.0.1'])
        self.assertEqual(modes.parse_global_ipv6(output),['2409:8a31:414:d0b4::1000'])
        with mock.patch.object(modes.sys,'platform','win32'), mock.patch.object(modes.subprocess,'run',return_value=mock.Mock(returncode=0,stdout=output)) as run:
            self.assertEqual(modes.global_ipv6_addresses(),['2409:8a31:414:d0b4::1000'])
            self.assertIn('Get-NetIPAddress',run.call_args.args[0][-1])

    def test_read_only_adapter_output(self):
        output=json.dumps(['10.147.17.2','10.147.17.2','169.254.1.2','127.0.0.1',None,'garbage'])
        self.assertEqual(modes.parse_zerotier_ips(output),['10.147.17.2'])
        self.assertEqual(modes.parse_zerotier_ips('[]'),[])
        with self.assertRaises(ValueError): modes.parse_zerotier_ips('{"IPAddress":"10.1.1.1"}')
        completed=mock.Mock(returncode=0, stdout=output)
        with mock.patch.object(modes.sys,'platform','win32'), mock.patch.object(modes.subprocess,'run',return_value=completed) as run:
            self.assertEqual(modes.zerotier_ips(),['10.147.17.2'])
            self.assertIn('Get-NetAdapter',run.call_args.args[0][-1])
            self.assertNotIn('join',run.call_args.args[0][-1].lower())

if __name__=='__main__': unittest.main()
