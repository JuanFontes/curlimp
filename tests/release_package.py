#!/usr/bin/env python3
"""Focused archive and launcher contract tests; no engine build required."""
import hashlib
import json
import os
from pathlib import Path
import platform
import subprocess
import sys
import tarfile
import tempfile
import unittest

REPO = Path(__file__).resolve().parents[1]
VERSION = '0.0.1-rc.1'
REVISION = 'a' * 40
LOADERS = {'amd64': 'lib64/ld-linux-x86-64.so.2', 'arm64': 'lib/ld-linux-aarch64.so.1'}


class ReleasePackage(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix='release test ')
        self.addCleanup(self.tmp.cleanup)
        self.base = Path(self.tmp.name)
        self.root = self.base / 'rootfs'
        self.output = self.base / 'out'
        self.arch = 'arm64' if platform.machine() in ('arm64', 'aarch64') else 'amd64'
        header = b'\x7fELF\x02\x01\x01' + b'\0' * 11 + (183 if self.arch == 'arm64' else 62).to_bytes(2, 'little')
        for name in ['usr/local/bin/curlimp', LOADERS[self.arch],
                     'opt/native/lib/libcurl-impersonate.so.4',
                     f'lib/{"aarch64" if self.arch == "arm64" else "x86_64"}-linux-gnu/libc.so.6']:
            self.put(name, header, 0o755)
        for name in ['etc/ssl/certs/ca-certificates.crt', 'usr/share/ca-certificates/test.crt',
                     'usr/share/licenses/curlimp/LICENSE',
                     'usr/share/licenses/curlimp/NOTICE',
                     'usr/share/licenses/curlimp/native/LICENSE.txt',
                     'usr/share/doc/libc6/copyright', 'opt/native/engine-build.txt',
                     'opt/native/runtime-packages.txt']:
            self.put(name, b'fixture\n')
        libdir = f'lib/{"aarch64" if self.arch == "arm64" else "x86_64"}-linux-gnu'
        self.put(f'{libdir}/libgcc_s.so.1', header, 0o755)
        self.put('opt/native/runtime-libraries.txt',
                 f'libgcc_s.so.1 => /{libdir}/libgcc_s.so.1 (0x1234)\n'.encode())
        (self.root / 'etc/ssl/certs/test.pem').symlink_to('/usr/share/ca-certificates/test.crt')
        (self.root / 'opt/native/lib/libcurl-impersonate.so').symlink_to('libcurl-impersonate.so.4')

    def put(self, name, data, mode=0o644):
        path = self.root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        path.chmod(mode)
        return path

    def package(self, *extra, ok=True):
        result = subprocess.run([sys.executable, str(REPO / 'scripts/package-release.py'),
                                 '--rootfs', str(self.root), '--arch', self.arch,
                                 '--version', VERSION, '--revision', REVISION,
                                 '--output', str(self.output), *extra], capture_output=True)
        if ok:
            self.assertEqual(result.returncode, 0, result.stderr.decode())
            return next(self.output.glob('*.tar.gz'))
        self.assertNotEqual(result.returncode, 0)
        self.assertFalse(list(self.output.glob('*.tar.gz')))
        return result

    def extract(self, archive):
        destination = self.base / 'moved package'
        with tarfile.open(archive) as tar:
            # These archives are generated from this test's controlled fixtures.
            if hasattr(tarfile, 'data_filter'):
                tar.extractall(destination, filter='data')
            else:
                tar.extractall(destination)
        return next(destination.iterdir())

    def test_archive_is_relocatable_and_complete(self):
        archive = self.package()
        self.assertEqual(archive.name, f'curlimp-{VERSION}-linux-{self.arch}.tar.gz')
        bundle = self.extract(archive)
        manifest = json.loads((bundle / 'release.json').read_text())
        self.assertEqual(manifest['source_revision'], REVISION)
        self.assertEqual(manifest['architecture'], self.arch)
        self.assertEqual(manifest['version'], VERSION)
        self.assertTrue(os.access(bundle / 'curlimp', os.X_OK))
        link = bundle / 'runtime/etc/ssl/certs/test.pem'
        self.assertFalse(link.readlink().is_absolute())
        self.assertEqual(link.read_bytes(), b'fixture\n')
        self.assertTrue((bundle / 'runtime/usr/share/licenses/curlimp/NOTICE').is_file())
        self.assertIn('--impersonate', (bundle / 'README.md').read_text())
        self.assertEqual((bundle / 'completions/zsh/_curlimp').read_bytes(),
                         (REPO / 'completions/_curlimp').read_bytes())

    def test_default_version_matches_cargo_manifest(self):
        import tomllib
        with (REPO / 'Cargo.toml').open('rb') as source:
            version = tomllib.load(source)['package']['version']
        result = subprocess.run([sys.executable, str(REPO / 'scripts/package-release.py'),
                                 '--rootfs', str(self.root), '--arch', self.arch,
                                 '--revision', REVISION, '--output', str(self.output)],
                                capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        archive = next(self.output.glob('*.tar.gz'))
        with tarfile.open(archive) as tar:
            root = tar.getnames()[0]
            metadata = json.load(tar.extractfile(root + '/release.json'))
            self.assertEqual(metadata['version'], version)
            self.assertIn(f'curlimp {version}',
                          tar.extractfile(root + '/README.md').read().decode())

    def test_rejects_wrong_architecture(self):
        result = self.package('--arch', 'amd64' if self.arch == 'arm64' else 'arm64', ok=False)
        self.assertIn(b'architecture', result.stderr.lower())

    def test_rejects_missing_runtime_file(self):
        (self.root / 'etc/ssl/certs/ca-certificates.crt').unlink()
        self.assertIn(b'ca-certificates', self.package(ok=False).stderr)

    def test_rejects_missing_recorded_dependency(self):
        for path in self.root.rglob('libgcc_s.so.1'):
            path.unlink()
        self.assertIn(b'libgcc_s', self.package(ok=False).stderr)

    def test_rejects_escaping_link(self):
        (self.root / 'escape').symlink_to('../outside')
        (self.base / 'outside').write_text('private')
        self.assertIn(b'link', self.package(ok=False).stderr.lower())

    def test_rejects_dangling_link(self):
        (self.root / 'broken').symlink_to('/missing')
        self.assertIn(b'link', self.package(ok=False).stderr.lower())

    def test_rejects_unsafe_version(self):
        self.package('--version', '../../escape', ok=False)

    def test_same_inputs_produce_same_archive(self):
        archive = self.package()
        digest = hashlib.sha256(archive.read_bytes()).digest()
        archive.unlink()
        os.utime(self.root / 'etc/ssl/certs/ca-certificates.crt', (10, 20))
        self.assertEqual(hashlib.sha256(self.package().read_bytes()).digest(), digest)

    def test_does_not_overwrite_archive(self):
        archive = self.package()
        original = archive.read_bytes()
        result = subprocess.run([sys.executable, str(REPO / 'scripts/package-release.py'),
                                 '--rootfs', str(self.root), '--arch', self.arch,
                                 '--version', VERSION, '--revision', REVISION,
                                 '--output', str(self.output)], capture_output=True)
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(archive.read_bytes(), original)

    @unittest.skipUnless(platform.system() == 'Linux', 'Linux launcher contract')
    def test_launcher_preserves_arguments_cwd_streams_and_ca_overrides(self):
        bundle = self.extract(self.package())
        # Replace the loader after extraction to observe exactly what exec receives.
        loader = bundle / 'runtime' / LOADERS[self.arch]
        loader.write_text('#!/usr/bin/env python3\nimport json, os, sys\n'
                          'sys.stderr.write(json.dumps({"args":sys.argv[1:],"cwd":os.getcwd(),'
                          '"ca":os.environ.get("CURL_CA_BUNDLE"),"cert":os.environ.get("SSL_CERT_FILE"),'
                          '"dir":os.environ.get("SSL_CERT_DIR")}))\n'
                          'sys.stdout.buffer.write(sys.stdin.buffer.read())\nsys.exit(23)\n')
        link = self.base / 'my-cli'
        link.symlink_to(bundle / 'curlimp')
        env = {key: value for key, value in os.environ.items()
               if key not in ('CURL_CA_BUNDLE', 'SSL_CERT_FILE', 'SSL_CERT_DIR')}
        env['PATH'] = str(self.base) + ':' + env['PATH']
        for custom in ({}, {'CURL_CA_BUNDLE': '/custom CA'}, {'SSL_CERT_FILE': '/other CA'},
                       {'SSL_CERT_DIR': '/cert dir'},
                       {'CURL_CA_BUNDLE': '', 'SSL_CERT_FILE': '', 'SSL_CERT_DIR': '/cert dir'},
                       {'CURL_CA_BUNDLE': '/custom CA', 'SSL_CERT_FILE': '/other CA', 'SSL_CERT_DIR': '/cert dir'}):
            result = subprocess.run(['my-cli', '-H', 'Name: two words', '--data-binary', '@-'],
                                    input=b'\0\xff\r\n', capture_output=True, cwd=self.base, env=env | custom)
            self.assertEqual(result.returncode, 23, result.stderr)
            self.assertEqual(result.stdout, b'\0\xff\r\n')
            observed = json.loads(result.stderr)
            self.assertEqual(observed['args'][-4:], ['-H', 'Name: two words', '--data-binary', '@-'])
            self.assertEqual(observed['cwd'], str(self.base))
            self.assertEqual(observed['ca'], custom.get('CURL_CA_BUNDLE'))
            expected_cert = custom.get('SSL_CERT_FILE') if custom.get('CURL_CA_BUNDLE') or custom.get('SSL_CERT_FILE') else \
                str(bundle / 'runtime/etc/ssl/certs/ca-certificates.crt')
            self.assertEqual(observed['cert'], expected_cert)
            self.assertEqual(observed['dir'], custom.get('SSL_CERT_DIR'))
        for separator in (':', ';'):
            moved = bundle.with_name('unsupported' + separator + 'path')
            bundle.rename(moved)
            result = subprocess.run([str(moved / 'curlimp'), '--version'], capture_output=True)
            self.assertEqual(result.returncode, 2, result.stderr)
            self.assertIn(b'package path', result.stderr)
            moved.rename(bundle)


if __name__ == '__main__':
    unittest.main(verbosity=2)
