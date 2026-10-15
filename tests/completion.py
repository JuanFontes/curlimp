#!/usr/bin/env python3
"""Exercise completion through the real CLI without any network service."""
import os
from pathlib import Path
import subprocess
import unittest

CLI = os.environ.get('CLI', str(Path(__file__).resolve().parents[1] / 'target/debug/curlimp'))
CHROME_1 = ['chrome100', 'chrome101', 'chrome104', 'chrome107', 'chrome110',
            'chrome116', 'chrome119', 'chrome120', 'chrome123', 'chrome124',
            'chrome131', 'chrome131_android', 'chrome133a', 'chrome136',
            'chrome142', 'chrome145', 'chrome146', 'chrome150']


class CompletionTests(unittest.TestCase):
    def candidates(self, *words):
        result = subprocess.run([CLI, '--complete-profiles', *words],
                                capture_output=True, text=True, timeout=5,
                                env={**os.environ, 'CURL_IMPERSONATE': 'invalid-profile',
                                     'https_proxy': 'http://127.0.0.1:1'})
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stderr, '')
        return result.stdout.splitlines()

    def test_any_length_prefix_filters_the_whole_catalog(self):
        chromes = CHROME_1 + ['chrome99', 'chrome99_android']
        for prefix in ['c', 'ch', 'chr', 'chro', 'chrom', 'chrome']:
            with self.subTest(prefix=prefix):
                self.assertEqual(self.candidates(prefix), chromes)
        for prefix, expected in [
            ('chrome1', CHROME_1), ('chrome15', ['chrome150']),
            ('chrome150', ['chrome150']), ('chrome131_', ['chrome131_android']),
            ('firefox14', ['firefox144', 'firefox147']), ('firefox147', ['firefox147']),
            ('safari26', ['safari260', 'safari2601', 'safari260_ios']),
            ('ed', ['edge101', 'edge99']), ('okhttp4_', []),
            ('t', ['tor145']), ('does-not-exist', []), ('Chrome', []),
            ('chrome*', []), ('chrome150-extra', []),
        ]:
            with self.subTest(prefix=prefix):
                self.assertEqual(self.candidates(prefix), expected)

    def test_empty_prefix_lists_each_available_profile_once(self):
        names = self.candidates('')
        self.assertEqual(len(names), 38)
        self.assertEqual(len(set(names)), 38)
        self.assertIn('chrome150', names)
        self.assertIn('firefox147', names)
        self.assertIn('safari2601', names)
        self.assertIn('edge99', names)
        self.assertNotIn('okhttp4_android', names)
        self.assertIn('tor145', names)

    def test_flags_and_profile_options_preserve_completion_context(self):
        for words in [('-sSI', 'firefox14'), ('-o', 'file', 'firefox14'),
                      ('-sofile', 'firefox14'), ('--output=file', 'firefox14'),
                      ('--impersonate', 'firefox14'), ('--impersonate=firefox14',),
                      ('chrome150', '--impersonate', 'firefox14')]:
            with self.subTest(words=words):
                self.assertEqual(self.candidates(*words), ['firefox144', 'firefox147'])

    def test_no_profiles_for_option_values_urls_or_completed_selection(self):
        for words in [('-o', 'fi'), ('-sofi',), ('--output=fi',),
                      ('--json', 'fi'), ('-H', 'fi'), ('--url', 'fi'),
                      ('--url=fi',), ('--', 'fi'), ('chrome150', 'fi'),
                      ('--impersonate', 'chrome150', 'fi'),
                      ('https://httpbin.org/status/200', 'fi'),
                      ('--url', 'firefox147', 'fi'), ('--unknown', 'fi'), ('--j',)]:
            with self.subTest(words=words):
                self.assertEqual(self.candidates(*words), [])

    def test_prints_loadable_zsh_script_without_url(self):
        result = subprocess.run([CLI, '--completions', 'zsh'], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        script = result.stdout
        self.assertTrue(script.startswith('#compdef curlimp\n'))
        checked = subprocess.run(['zsh', '-n'], input=script, text=True, capture_output=True)
        self.assertEqual(checked.returncode, 0, checked.stderr)
        unsupported = subprocess.run([CLI, '--completions', 'fish'], capture_output=True)
        self.assertEqual(unsupported.returncode, 2)


if __name__ == '__main__':
    unittest.main(verbosity=2)
