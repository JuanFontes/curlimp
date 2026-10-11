#!/usr/bin/env python3
"""Reject release bundles that do not belong to the tested revision."""
import hashlib
import io
import json
from pathlib import Path
import subprocess
import sys
import tarfile
import tempfile
import unittest

SCRIPT = Path(__file__).resolve().parents[1] / 'scripts/release_artifacts.py'
VERSION = subprocess.check_output([sys.executable, str(SCRIPT.with_name('release_version.py'))], text=True).strip()
sys.path.insert(0, str(SCRIPT.parent))
import release_artifacts as release


class ReleaseSourceTests(unittest.TestCase):
    def test_rejects_a_successful_old_run_after_main_moves(self):
        self.assertTrue(hasattr(release, 'validate_run'), 'Current-main validation is missing')
        run = dict(status='completed', conclusion='success', path='.github/workflows/ci.yml',
                   head_sha='a' * 40, head_branch='main', event='push',
                   head_repository={'full_name': 'JuanFontes/curlimp'})
        release.validate_run(run, 'a' * 40, 'a' * 40, 'JuanFontes/curlimp')
        with self.assertRaisesRegex(ValueError, 'main has moved'):
            release.validate_run(run, 'a' * 40, 'b' * 40, 'JuanFontes/curlimp')
        for key, value in [('conclusion', 'failure'), ('head_sha', 'b' * 40), ('event', 'pull_request')]:
            with self.subTest(key=key), self.assertRaises(ValueError):
                release.validate_run(dict(run, **{key: value}), 'a' * 40, 'a' * 40, 'JuanFontes/curlimp')


class ReleaseArtifactTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.artifacts = self.root / 'artifacts'
        self.output = self.root / 'release'
        self.paths = []
        for system, arch in [('linux', 'amd64'), ('linux', 'arm64'), ('macos', 'arm64')]:
            directory = self.artifacts / f'{system}-{arch}'
            directory.mkdir(parents=True)
            archive = directory / f'curlimp-{VERSION}-{system}-{arch}.tar.gz'
            self.write_bundle(archive, system, arch)
            self.paths.append(archive)

    def write_bundle(self, archive, system, arch, **overrides):
        metadata = dict(version=VERSION, system=system, architecture=arch, source_revision='a' * 40)
        metadata.update(overrides)
        data = json.dumps(metadata).encode()
        with tarfile.open(archive, 'w:gz') as bundle:
            member = tarfile.TarInfo(archive.name.removesuffix('.tar.gz') + '/release.json')
            member.size = len(data)
            bundle.addfile(member, io.BytesIO(data))

    def run_check(self):
        return subprocess.run([sys.executable, str(SCRIPT), '--artifacts', str(self.artifacts),
                               '--revision', 'a' * 40, '--output', str(self.output)],
                              capture_output=True, text=True)

    def test_preserves_tested_bytes_and_generates_checksums(self):
        result = self.run_check()
        self.assertEqual(result.returncode, 0, result.stderr)
        for path in self.paths:
            self.assertEqual(path.read_bytes(), (self.output / path.name).read_bytes())
            self.assertIn(hashlib.sha256(path.read_bytes()).hexdigest() + '  ' + path.name,
                          (self.output / 'SHA256SUMS').read_text())

    def test_rejects_wrong_revision_version_and_architecture(self):
        for key, value in [('source_revision', 'b' * 40), ('version', '0.2.0'), ('architecture', 'amd64')]:
            with self.subTest(key=key):
                self.write_bundle(self.paths[2], 'macos', 'arm64', **{key: value})
                result = self.run_check()
                self.assertNotEqual(result.returncode, 0)
                self.assertIn(key, result.stderr)
                self.assertFalse(self.output.exists())

    def test_rejects_missing_platform(self):
        self.paths[1].unlink()
        result = self.run_check()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('linux-arm64', result.stderr)

    def test_refuses_to_overwrite_previous_output(self):
        self.output.mkdir()
        existing = self.output / 'SHA256SUMS'
        existing.write_text('existing publication')
        result = self.run_check()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('already exists', result.stderr)
        self.assertEqual(existing.read_text(), 'existing publication')

    def test_rejects_link_in_place_of_release_metadata(self):
        with tarfile.open(self.paths[0], 'w:gz') as bundle:
            member = tarfile.TarInfo(self.paths[0].name.removesuffix('.tar.gz') + '/release.json')
            member.type = tarfile.SYMTYPE
            member.linkname = '/tmp/untrusted.json'
            bundle.addfile(member)
        result = self.run_check()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('regular', result.stderr)


if __name__ == '__main__':
    unittest.main()
