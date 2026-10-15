#!/usr/bin/env python3
"""Exercise real TLS with each supported trust override through the launcher."""
import os
from pathlib import Path
import shutil
import subprocess
import unittest

import compat


class BundleTrust(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.fixture = compat.Compatibility
        cls.fixture.setUpClass()
        cls.addClassCleanup(cls.fixture.tearDownClass)

    def test_certificate_environment(self):
        fixture = self.fixture
        certs = fixture.root / 'custom CA directory'
        certs.mkdir()
        shutil.copyfile(fixture.cert, certs / 'test.crt')
        subprocess.run(['openssl', 'rehash', str(certs)], check=True, capture_output=True)
        env = {key: value for key, value in os.environ.items() if key.lower() not in {
            'http_proxy', 'https_proxy', 'all_proxy', 'no_proxy', 'curl_impersonate',
            'curl_impersonate_headers', 'curl_ca_bundle', 'ssl_cert_file', 'ssl_cert_dir'}}
        if os.environ.get('REQUIRE_NO_SYSTEM_CA') == '1':
            self.assertFalse(Path('/etc/ssl/certs/ca-certificates.crt').exists())
        other = fixture.root / 'untrusted.pem'
        subprocess.run(['openssl', 'req', '-x509', '-newkey', 'rsa:2048', '-nodes', '-days', '1',
                        '-keyout', str(fixture.root / 'untrusted.key'), '-out', str(other),
                        '-subj', '/CN=untrusted'], check=True, capture_output=True)
        for flags, custom, code in [
                ([], {'SSL_CERT_DIR': str(certs)}, 0),
                ([], {'SSL_CERT_FILE': str(fixture.cert)}, 0),
                ([], {'CURL_CA_BUNDLE': str(fixture.cert)}, 0),
                ([], {'SSL_CERT_DIR': str(certs), 'SSL_CERT_FILE': str(fixture.cert)}, 0),
                ([], {'SSL_CERT_DIR': str(certs), 'SSL_CERT_FILE': str(other)}, 0),
                ([], {'CURL_CA_BUNDLE': '', 'SSL_CERT_FILE': '', 'SSL_CERT_DIR': str(certs)}, 0),
                ([], {'SSL_CERT_DIR': str(certs), 'CURL_CA_BUNDLE': str(other)}, 60),
                (['--cacert', str(other)], {'SSL_CERT_DIR': str(certs)}, 60),
                (['--cacert', str(fixture.cert)], {'CURL_CA_BUNDLE': str(other)}, 0)]:
            with self.subTest(flags=flags, custom=custom):
                result = subprocess.run([compat.CLI, '-q', '-sS', *flags, fixture.tls_url + '/bytes'],
                                        env=env | custom, capture_output=True, timeout=10)
                self.assertEqual(result.returncode, code, result.stderr)
                self.assertEqual(result.stdout, compat.BINARY if code == 0 else b'')


if __name__ == '__main__':
    unittest.main(verbosity=2)
