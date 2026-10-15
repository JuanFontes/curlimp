#!/usr/bin/env python3
"""Check PR routing without GitHub credentials or native compilation."""
import importlib.util
from pathlib import Path
import re
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
                     '.github/workflows/pull-request.yml',
                     'scripts/pr_checks.py', 'tests/pr_checks.py',
                     'scripts/release_policy.py']:
            with self.subTest(path=path):
                self.assertEqual(self.select(path), {'runtime': True, 'site': True})

    def test_runtime_workflow_does_not_build_independent_website(self):
        self.assertEqual(self.select('.github/workflows/ci.yml'),
                         {'runtime': True, 'site': False})

    def route_workflow_change(self, before, after, other_files=None):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)

            def git(*args):
                return subprocess.check_output(['git', '-C', str(root), *args],
                                               stderr=subprocess.DEVNULL, text=True).strip()

            git('init', '-q')
            git('config', 'user.name', 'Test')
            git('config', 'user.email', 'test@localhost')
            workflow = root / '.github/workflows/pull-request.yml'
            workflow.parent.mkdir(parents=True)
            workflow.write_text(before)
            git('add', '.')
            git('commit', '-qm', 'Base fixture')
            base = git('rev-parse', 'HEAD')
            if after is None:
                workflow.unlink()
            else:
                workflow.write_text(after)
            for path, content in (other_files or {}).items():
                file = root / path
                file.parent.mkdir(parents=True, exist_ok=True)
                file.write_text(content)
            git('add', '-A')
            git('commit', '-qm', 'Changed fixture')
            result = subprocess.run([sys.executable, str(SCRIPT), '--base', base],
                                    cwd=root, capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            return result.stdout

    def test_quality_action_pin_updates_only_need_existing_gate(self):
        workflow = (ROOT / '.github/workflows/pull-request.yml').read_text()
        for action in ['setup-python', 'setup-node', 'checkout']:
            with self.subTest(action=action):
                changed = re.sub(r'(actions/' + action + r'@)[0-9a-f]{40}[^\n]*',
                                 r'\g<1>' + 'a' * 40 + ' # v99.0.0', workflow)
                self.assertEqual(self.route_workflow_change(workflow, changed),
                                 'runtime=false\nsite=false\n')

    def test_quality_pin_update_keeps_mixed_native_and_site_checks(self):
        workflow = (ROOT / '.github/workflows/pull-request.yml').read_text()
        changed = re.sub(r'(actions/setup-python@)[0-9a-f]{40}',
                         r'\g<1>' + 'b' * 40, workflow)
        for other_files, expected in [
            ({'src/cli.rs': 'native input'}, 'runtime=true\nsite=false\n'),
            ({'website/src/page.astro': 'site input'}, 'runtime=false\nsite=true\n'),
        ]:
            with self.subTest(files=other_files):
                self.assertEqual(self.route_workflow_change(workflow, changed, other_files),
                                 expected)

    def test_other_orchestration_changes_keep_full_validation(self):
        workflow = (ROOT / '.github/workflows/pull-request.yml').read_text()
        pin_update = re.sub(r'(actions/setup-python@)[0-9a-f]{40}',
                            r'\g<1>' + 'c' * 40, workflow)
        cases = [
            pin_update.replace("python-version: '3.12'", "python-version: '3.13'"),
            pin_update.replace('contents: read', 'contents: write'),
            pin_update.replace('needs: quality', 'needs: []'),
            workflow.replace('actions/setup-python@', 'another/setup-python@'),
            re.sub(r'(actions/setup-python@)[0-9a-f]{40}', r'\g<1>v7', workflow),
            None,
            '',
        ]
        for after in cases:
            with self.subTest(after=after):
                self.assertEqual(self.route_workflow_change(workflow, after),
                                 'runtime=true\nsite=true\n')

    def test_action_pin_outside_quality_job_keeps_full_validation(self):
        workflow = (ROOT / '.github/workflows/pull-request.yml').read_text()
        workflow += '\n  other:\n    steps:\n      - uses: actions/setup-python@' + 'a' * 40 + '\n'
        changed = workflow.replace('a' * 40, 'b' * 40)
        self.assertEqual(self.route_workflow_change(workflow, changed),
                         'runtime=true\nsite=true\n')

    def test_added_or_renamed_quality_workflow_keeps_full_validation(self):
        workflow = (ROOT / '.github/workflows/pull-request.yml').read_text()
        self.assertEqual(self.route_workflow_change('', workflow),
                         'runtime=true\nsite=true\n')
        self.assertEqual(self.route_workflow_change(
            workflow, None, {'website/old-workflow.yml': workflow}),
            'runtime=true\nsite=true\n')

    def test_multiple_quality_pins_can_change_together(self):
        workflow = (ROOT / '.github/workflows/pull-request.yml').read_text()
        changed = re.sub(r'(actions/(?:setup-python|setup-node|checkout)@)[0-9a-f]{40}',
                         r'\g<1>' + 'd' * 40, workflow)
        self.assertEqual(self.route_workflow_change(workflow, changed),
                         'runtime=false\nsite=false\n')

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
