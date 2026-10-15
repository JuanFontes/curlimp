#!/usr/bin/env python3
"""Check PR routing without GitHub credentials or native compilation."""
import importlib.util
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / 'scripts/pr_checks.py'


class PullRequestChecks(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not SCRIPT.is_file():
            return
        spec = importlib.util.spec_from_file_location('pr_checks', SCRIPT)
        cls.policy = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(cls.policy)

    def select(self, *paths):
        self.assertTrue(SCRIPT.is_file(), 'PR routing is not implemented')
        return self.policy.select_checks(paths)

    def test_site_and_public_examples_do_not_compile_native_engine(self):
        for path in ['website/package-lock.json', 'website/src/pages/index.astro',
                     'README.md', 'docker/README.md', '.github/workflows/pages.yml',
                     '.github/workflows/site-build.yml']:
            with self.subTest(path=path):
                self.assertEqual(self.select(path), {'runtime': False, 'site': True})

    def test_security_and_tooling_only_changes_do_not_compile_native_engine(self):
        for path in ['SECURITY.md', 'CONTRIBUTING.md', '.github/dependabot.yml',
                     '.github/workflows/dependency-review.yml',
                     'scripts/dependency_report.py', 'tests/dependency_report.py',
                     '.prettierrc.json', 'ruff.toml', '.github/requirements.txt']:
            with self.subTest(path=path):
                self.assertEqual(self.select(path)['runtime'], False)

    def test_native_and_unknown_changes_preserve_runtime_validation(self):
        for path in ['src/cli.rs', 'native/bridge.c', 'engine.lock', 'Dockerfile',
                     'docker/Dockerfile.build', 'vendor/engine/patches/curl.patch',
                     'scripts/build-engine.sh', 'new-build-input', 'tests/new_test.py']:
            with self.subTest(path=path):
                self.assertEqual(self.select(path)['runtime'], True)

    def test_shared_inputs_and_orchestration_validate_both_consumers(self):
        for path in ['Cargo.toml', 'src/help.txt', 'src/profiles.txt',
                     '.github/workflows/ci.yml', '.github/workflows/pull-request.yml',
                     'scripts/pr_checks.py', 'tests/pr_checks.py',
                     'scripts/release_policy.py']:
            with self.subTest(path=path):
                self.assertEqual(self.select(path), {'runtime': True, 'site': True})

    def test_mixed_changes_keep_all_required_checks(self):
        self.assertEqual(self.select('website/package-lock.json', 'src/cli.rs'),
                         {'runtime': True, 'site': True})
        self.assertEqual(self.select(), {'runtime': False, 'site': False})

    def test_git_changes_include_deleted_and_renamed_inputs(self):
        self.assertTrue(SCRIPT.is_file(), 'PR routing is not implemented')
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            def git(*args):
                return subprocess.check_output(['git', '-C', str(root), *args],
                                               stderr=subprocess.DEVNULL, text=True).strip()
            git('init', '-q')
            git('config', 'user.name', 'Test')
            git('config', 'user.email', 'test@localhost')
            native = root / 'native/bridge.c'
            native.parent.mkdir()
            native.write_text('native input\n')
            git('add', '.')
            git('commit', '-qm', 'Fixture')
            base = git('rev-parse', 'HEAD')
            docs = root / 'website/deleted native\ninput.md'
            docs.parent.mkdir()
            native.rename(docs)
            git('add', '-A')
            git('commit', '-qm', 'Move fixture')
            result = subprocess.run([sys.executable, str(SCRIPT), '--base', base],
                                    cwd=root, capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(result.stdout, 'runtime=true\nsite=true\n')

    def test_missing_base_fails_instead_of_skipping_checks(self):
        self.assertTrue(SCRIPT.is_file(), 'PR routing is not implemented')
        result = subprocess.run([sys.executable, str(SCRIPT), '--base', 'invalid-revision'],
                                cwd=ROOT, capture_output=True, text=True)
        self.assertNotEqual(result.returncode, 0)
        self.assertNotIn('runtime=false', result.stdout)


if __name__ == '__main__':
    unittest.main()
