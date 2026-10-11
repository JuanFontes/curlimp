#!/usr/bin/env python3
"""Exercise local engine preparation without fetching any source archives."""
import hashlib
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

SCRIPT = Path(__file__).resolve().parents[1] / 'scripts' / 'prepare-engine.sh'


class VendorEngineTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.source = self.root / 'vendor'
        self.source.mkdir()
        (self.source / 'scripts').mkdir()
        (self.source / 'LICENSE').write_bytes(b'Third-party notice\n')
        helper = self.source / 'scripts' / 'build.sh'
        helper.write_bytes(b'#!/bin/sh\nexit 0\n')
        helper.chmod(0o755)
        self.manifest = self.source / 'SHA256SUMS'
        self.update_manifest()
        self.pin = hashlib.sha256(self.manifest.read_bytes()).hexdigest()
        self.destination = self.root / 'workspace' / 'upstream'

    def update_manifest(self):
        self.manifest.write_text(''.join(
            f'{hashlib.sha256((self.source / name).read_bytes()).hexdigest()}  {name}\n'
            for name in ('LICENSE', 'scripts/build.sh')
        ))

    def prepare(self):
        return subprocess.run(
            ['sh', str(SCRIPT), str(self.source), str(self.destination), self.pin],
            capture_output=True, text=True,
        )

    def test_copy_preserves_bytes_and_executable_mode_and_can_be_reused(self):
        # Unlisted files must not become build inputs.
        (self.source / 'unlisted.cmake').write_text('unexpected input')
        for _ in range(2):
            result = self.prepare()
            self.assertEqual(result.returncode, 0, result.stderr)
        for name in ('LICENSE', 'scripts/build.sh', 'SHA256SUMS'):
            self.assertEqual((self.source / name).read_bytes(), (self.destination / name).read_bytes())
        self.assertTrue(os.access(self.destination / 'scripts/build.sh', os.X_OK))
        self.assertFalse((self.destination / 'unlisted.cmake').exists())

    def test_unlisted_build_input_in_destination_is_rejected(self):
        result = self.prepare()
        self.assertEqual(result.returncode, 0, result.stderr)
        unexpected = self.destination / 'GNUmakefile'
        unexpected.write_text('all:\n\t@echo unpinned input\n')
        self.assertNotEqual(self.prepare().returncode, 0)
        self.assertTrue(unexpected.exists())

    def test_modified_source_is_rejected_before_copy(self):
        (self.source / 'LICENSE').write_text('changed')
        self.assertNotEqual(self.prepare().returncode, 0)
        self.assertFalse(self.destination.exists())

    def test_recomputed_manifest_is_rejected_without_lock_update(self):
        (self.source / 'LICENSE').write_text('changed')
        self.update_manifest()
        self.assertNotEqual(self.prepare().returncode, 0)
        self.assertFalse(self.destination.exists())

    def test_modified_destination_is_rejected_without_overwriting(self):
        result = self.prepare()
        self.assertEqual(result.returncode, 0, result.stderr)
        (self.destination / 'LICENSE').write_text('changed')
        self.assertNotEqual(self.prepare().returncode, 0)
        self.assertEqual((self.destination / 'LICENSE').read_text(), 'changed')


if __name__ == '__main__':
    unittest.main()
