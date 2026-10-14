#!/usr/bin/env python3
"""An installed engine cache is reusable only for identical inputs and intact files."""
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import native_cache as cache


class NativeCacheTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.repo = self.root / 'repo'
        self.repo.mkdir()
        (self.repo / 'engine.lock').write_text('engine=v1\n')
        (self.repo / 'vendor/engine').mkdir(parents=True)
        (self.repo / 'vendor/engine/input').write_bytes(b'engine source')
        self.prefix = self.root / 'native'
        for name in ['bin/curl-impersonate', 'include/curl/curl.h', 'lib/libcurl-impersonate.4.dylib',
                     'LICENSE', 'engine-build.txt', 'engine-origin.md', 'engine-inputs.sha256']:
            path = self.prefix / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text('fixture ' + name)
        (self.prefix / 'lib/libcurl-impersonate.dylib').symlink_to('libcurl-impersonate.4.dylib')
        self.inputs = ['engine.lock', 'vendor/engine']

    def key(self, identity='macOS arm64 clang 1 SDK 1'):
        return cache.fingerprint(self.repo, self.inputs, identity)

    def test_same_inputs_reuse_but_source_toolchain_and_paths_invalidate(self):
        original = self.key()
        self.assertEqual(original, self.key())
        self.assertNotEqual(original, self.key('macOS arm64 clang 2 SDK 1'))
        (self.repo / 'vendor/engine/input').write_bytes(b'changed engine')
        self.assertNotEqual(original, self.key())
        (self.repo / 'vendor/engine/input').write_bytes(b'engine source')
        (self.repo / 'vendor/engine/input').rename(self.repo / 'vendor/engine/renamed')
        self.assertNotEqual(original, self.key())

    def test_accepts_complete_sealed_installation_only_for_its_key(self):
        cache.seal(self.prefix, self.key())
        cache.verify(self.prefix, self.key())
        with self.assertRaises(ValueError):
            cache.verify(self.prefix, 'different-key')

    def test_rejects_corruption_missing_files_added_files_and_changed_modes(self):
        for mutation in ['corrupt', 'missing', 'extra', 'mode']:
            with self.subTest(mutation=mutation):
                library = self.prefix / 'lib/libcurl-impersonate.4.dylib'
                original = library.read_bytes()
                mode = library.stat().st_mode & 0o777
                cache.seal(self.prefix, self.key())
                if mutation == 'corrupt':
                    library.write_bytes(b'corrupted')
                elif mutation == 'missing':
                    library.unlink()
                elif mutation == 'extra':
                    (self.prefix / 'unexpected').write_text('extra')
                else:
                    library.chmod(0o700)
                with self.assertRaises(ValueError):
                    cache.verify(self.prefix, self.key())
                library.write_bytes(original)
                library.chmod(mode)
                (self.prefix / 'unexpected').unlink(missing_ok=True)

    def test_rejects_missing_manifest_and_incomplete_prefix(self):
        with self.assertRaises(ValueError):
            cache.verify(self.prefix, self.key())
        (self.prefix / 'include/curl/curl.h').unlink()
        with self.assertRaises(ValueError):
            cache.seal(self.prefix, self.key())

    def test_rejects_symlinks_outside_prefix(self):
        (self.root / 'external').write_text('outside')
        (self.prefix / 'escape').symlink_to('../external')
        with self.assertRaises(ValueError):
            cache.seal(self.prefix, self.key())

    def test_requires_native_executable_for_uncached_feature_checks(self):
        (self.prefix / 'bin/curl-impersonate').unlink()
        with self.assertRaises(ValueError):
            cache.seal(self.prefix, self.key())


if __name__ == '__main__':
    unittest.main()
