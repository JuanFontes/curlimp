#!/usr/bin/env python3
"""Test macOS packaging with real tiny Mach-O binaries, without building curl."""
import hashlib
import json
from pathlib import Path
import platform
import subprocess
import sys
import tarfile
import tempfile
import unittest

REPO = Path(__file__).resolve().parents[1]
VERSION = '0.0.1-rc.2'
REVISION = 'b' * 40
LIBRARY = 'libcurl-impersonate.4.dylib'


@unittest.skipUnless(platform.system() == 'Darwin' and platform.machine() == 'arm64',
                     'Requires native macOS arm64 and Apple command-line tools')
class MacPackage(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='macos package ')
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.prefix = self.root / 'native'
        self.libdir = self.prefix / 'lib'
        self.libdir.mkdir(parents=True)
        self.binary = self.root / 'cli'
        self.output = self.root / 'out'
        self.library = self.libdir / LIBRARY
        (self.root / 'lib.c').write_text('int fixture(void) { return 42; }\n')
        (self.root / 'main.c').write_text('#include <stdio.h>\nint fixture(void);\nint main(void) { printf("%d\\n", fixture()); }\n')
        self.run_command('clang', '-arch', 'arm64', '-dynamiclib', str(self.root / 'lib.c'),
                         '-Wl,-install_name,@rpath/' + LIBRARY, '-o', str(self.library))
        self.run_command('clang', '-arch', 'arm64', str(self.root / 'main.c'), str(self.library),
                         '-Wl,-rpath,' + str(self.libdir), '-o', str(self.binary))
        for name in ['LICENSE', 'LICENSE_CURL', 'LICENSE_BORINGSSL', 'LICENSE_BROTLI',
                     'LICENSE_CARES', 'LICENSE_NGHTTP2', 'LICENSE_NGHTTP3', 'LICENSE_NGTCP2',
                     'LICENSE_ZLIB', 'LICENSE_ZSTD', 'engine-origin.md', 'engine-inputs.sha256']:
            (self.prefix / name).write_text('fixture notice\n')
        (self.prefix / 'engine-build.txt').write_text('build_kind=source\nplatform=macos\narchitecture=arm64\nmacos_deployment_target=13.0\n')

    def run_command(self, *args):
        return subprocess.run(args, check=True, capture_output=True, text=True)

    def package(self, *extra, ok=True):
        result = subprocess.run([sys.executable, str(REPO / 'scripts/package-macos.py'),
                                 '--binary', str(self.binary), '--native-prefix', str(self.prefix),
                                 '--version', VERSION, '--revision', REVISION,
                                 '--output', str(self.output), *extra], capture_output=True, text=True)
        if ok:
            self.assertEqual(result.returncode, 0, result.stderr)
            return next(self.output.glob('*.tar.gz'))
        self.assertNotEqual(result.returncode, 0)
        return result

    def test_relocated_bundle_runs_without_original_library(self):
        originals = [hashlib.sha256(p.read_bytes()).digest() for p in (self.binary, self.library)]
        archive = self.package()
        self.assertEqual(archive.name, f'curlimp-{VERSION}-macos-arm64.tar.gz')
        destination = self.root / 'relocated folder'
        with tarfile.open(archive) as tar:
            self.assertEqual(tar.getnames()[0], f'curlimp-{VERSION}-macos-arm64')
            tar.extractall(destination, filter='data')
        bundle = next(destination.iterdir())
        self.assertEqual([hashlib.sha256(p.read_bytes()).digest() for p in (self.binary, self.library)], originals)
        self.prefix.rename(self.root / 'hidden native prefix')
        result = subprocess.run([str(bundle / 'curlimp')], capture_output=True, text=True,
                                env={'PATH': '/usr/bin:/bin:/usr/sbin:/sbin'}, cwd='/')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout, '42\n')
        self.run_command('codesign', '--verify', '--strict', str(bundle / 'curlimp'))
        self.run_command('codesign', '--verify', '--strict', str(bundle / 'lib' / LIBRARY))
        metadata = json.loads((bundle / 'release.json').read_text())
        self.assertEqual(metadata['source_revision'], REVISION)
        self.assertEqual(metadata['version'], VERSION)
        self.assertEqual(metadata['architecture'], 'arm64')
        self.assertEqual(metadata['system'], 'macos')
        self.assertFalse(metadata['notarized'])
        self.assertTrue((bundle / 'NOTICE').is_file())
        self.assertEqual((bundle / 'licenses/native/LICENSE_CURL').read_text(), 'fixture notice\n')
        self.assertIn('not notarized', (bundle / 'README.md').read_text())
        self.assertEqual((bundle / 'completions/zsh/_curlimp').read_bytes(),
                         (REPO / 'completions/_curlimp').read_bytes())

    def test_default_version_matches_cargo_manifest(self):
        import tomllib
        with (REPO / 'Cargo.toml').open('rb') as source:
            version = tomllib.load(source)['package']['version']
        result = subprocess.run([sys.executable, str(REPO / 'scripts/package-macos.py'),
                                 '--binary', str(self.binary), '--native-prefix', str(self.prefix),
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

    def test_rejects_intel_library(self):
        self.run_command('clang', '-arch', 'x86_64', '-dynamiclib', str(self.root / 'lib.c'),
                         '-Wl,-install_name,@rpath/' + LIBRARY, '-o', str(self.library))
        self.assertIn('arm64', self.package(ok=False).stderr)

    def test_rejects_external_runtime_dependency(self):
        self.run_command('install_name_tool', '-change', '/usr/lib/libSystem.B.dylib',
                         '/opt/homebrew/lib/unbundled.dylib', str(self.library))
        self.assertIn('dependency', self.package(ok=False).stderr.lower())

    def test_rejects_missing_library_and_leaves_no_archive(self):
        self.library.unlink()
        self.package(ok=False)
        self.assertFalse(list(self.output.glob('*.tar.gz')))

    def test_rejects_missing_notices(self):
        (self.prefix / 'LICENSE').unlink()
        self.assertIn('LICENSE', self.package(ok=False).stderr)

    def test_rejects_missing_dependency_notice(self):
        (self.prefix / 'LICENSE_BORINGSSL').unlink()
        self.assertIn('LICENSE_BORINGSSL', self.package(ok=False).stderr)

    def test_rejects_unsafe_version(self):
        self.assertIn('version', self.package('--version', '../../bad', ok=False).stderr.lower())

    def test_refuses_to_overwrite(self):
        archive = self.package()
        before = archive.read_bytes()
        self.assertIn('overwrite', self.package(ok=False).stderr)
        self.assertEqual(archive.read_bytes(), before)


if __name__ == '__main__':
    unittest.main(verbosity=2)
