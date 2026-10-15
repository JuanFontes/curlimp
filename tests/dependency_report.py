#!/usr/bin/env python3
"""Focused offline policy and failure tests for maintenance reporting."""
import importlib.util
from pathlib import Path
import unittest
from unittest.mock import patch
import urllib.error

SCRIPT = Path(__file__).resolve().parents[1] / 'scripts/dependency_report.py'
spec = importlib.util.spec_from_file_location('dependency_report', SCRIPT)
m = importlib.util.module_from_spec(spec)
# RED: implementation is absent before this test is first run.
spec.loader.exec_module(m)


class DependencyReportTests(unittest.TestCase):
    def test_exact_curl_versions_and_multiple_intervals(self):
        advisory = {'id': 'CVE-test', 'affected': [{'versions': ['8.0.0', '8.2.0'],
            'ranges': [{'type': 'SEMVER', 'events': [{'introduced': '0'},
                {'fixed': '8.1.0'}, {'introduced': '8.2.0'}, {'fixed': '8.3.0'}]}]}]}
        self.assertTrue(m.curl_affected(advisory, '8.2.0'))
        self.assertFalse(m.curl_affected(advisory, '8.1.0'))
        self.assertFalse(m.curl_affected(advisory, '8.23.0'))

    def test_missing_versions_is_unknown_instead_of_clean(self):
        for affected in ([], [{'ranges': []}], [{'versions': []}]):
            with self.assertRaises(ValueError):
                m.curl_affected({'id': 'test', 'affected': affected}, '8.23.0')

    def test_nghttp2_inclusive_and_exclusive_ranges(self):
        self.assertTrue(m.in_range('1.63.0', '>= 1.0.0, < 1.68.1'))
        self.assertTrue(m.in_range('1.63.0', '<= 1.63.0'))
        self.assertFalse(m.in_range('1.68.1', '>= 1.0.0, < 1.68.1'))
        with self.assertRaises(ValueError):
            m.in_range('1.63.0', 'unknown future schema')

    def test_patch_status_requires_exact_digest_and_known_id(self):
        with patch.object(m, 'backport_present', return_value=True):
            self.assertEqual(m.nghttp2_status('GHSA-6933-cjhr-5qg6', True), 'backported')
            self.assertEqual(m.nghttp2_status('GHSA-other', True), 'needs-triage')
        with patch.object(m, 'backport_present', return_value=False):
            self.assertEqual(m.nghttp2_status('GHSA-6933-cjhr-5qg6', True), 'needs-triage')
        self.assertEqual(m.nghttp2_status('GHSA-other', False), 'not-affected-by-range')

    def test_token_is_only_attached_to_github_api_and_stripped_on_redirect(self):
        for url, authenticated in [('https://curl.se/docs/vuln.json', False),
                                   ('https://api.github.com/repos/nghttp2/nghttp2/releases/latest', True)]:
            request = m.request(url, 'secret')
            self.assertEqual(request.has_header('Authorization'), authenticated)
        original = m.request('https://api.github.com/example', 'secret')
        redirected = m.SafeRedirect().redirect_request(original, None, 302, '', {},
                                                       'https://curl.se/example')
        self.assertFalse(redirected.has_header('Authorization'))

    def test_http_network_and_parse_failures_remain_errors(self):
        failures = [urllib.error.HTTPError('https://example.test', 403, 'Forbidden', {}, None),
                    urllib.error.URLError('offline')]
        for failure, marker in zip(failures, ['HTTP 403', 'network']):
            with patch.object(m, 'OPENER') as opener:
                opener.open.side_effect = failure
                with self.assertRaisesRegex(m.SourceError, marker):
                    m.fetch_json('https://curl.se/docs/vuln.json', '')
        with patch.object(m, 'OPENER') as opener:
            opener.open.return_value.__enter__.return_value.read.return_value = b'not JSON'
            with self.assertRaisesRegex(m.SourceError, 'parse'):
                m.fetch_json('https://curl.se/docs/vuln.json', '')

    def test_feed_schema_failure_is_unknown_and_reportable(self):
        for bad in (["invalid OSV object"], [{'id': 'CVE-bad', 'affected': [None]}]):
            with patch.object(m, 'fetch_json', side_effect=[bad, []]):
                data = m.inventory()
                findings, errors = m.advisories(data, '')
                self.assertEqual(data['curl']['security_status'], 'unknown')
                self.assertTrue(any('curl advisories:' in error for error in errors))

    def test_advisory_report_checks_every_range_and_records_backport(self):
        curl = [{'id': 'CVE-test', 'affected': [{'versions': ['8.22.0']}]}]
        nghttp2 = [{'ghsa_id': m.BACKPORT_ID,
                    'html_url': 'https://github.com/nghttp2/nghttp2/security/advisories/' + m.BACKPORT_ID,
                    'vulnerabilities': [{'vulnerable_version_range': '<= 1.68.0'}]}]
        with patch.object(m, 'fetch_json', side_effect=[curl, nghttp2]):
            data = m.inventory()
            findings, errors = m.advisories(data, '')
            self.assertEqual(errors, [])
            self.assertEqual(findings[0]['status'], 'backported')
            self.assertEqual(findings[0]['backport_commit'], m.BACKPORT_COMMIT)
            self.assertEqual(data['curl']['advisory_count'], 1)
        nghttp2[0]['vulnerabilities'].append({'vulnerable_version_range': 'future-schema'})
        with patch.object(m, 'fetch_json', side_effect=[curl, nghttp2]):
            data = m.inventory()
            findings, errors = m.advisories(data, '')
            self.assertEqual(data['nghttp2']['security_status'], 'unknown')
            self.assertTrue(errors)

    def test_failed_sources_make_process_nonzero_and_keep_evidence(self):
        import tempfile
        import json
        import io
        with tempfile.TemporaryDirectory() as temp, \
                patch.object(m, 'fetch_json', side_effect=m.SourceError('HTTP 403')), \
                patch.object(m, 'fetch', side_effect=m.SourceError('network failure')), \
                patch('sys.argv', ['dependency_report.py', '--output', temp]), \
                patch('sys.stdout', new_callable=io.StringIO):
            self.assertEqual(m.main(), 1)
            result = json.loads((Path(temp) / 'report.json').read_text())
            self.assertEqual(len(result['errors']), 13)
            self.assertIn('result is incomplete, not clean', (Path(temp) / 'report.md').read_text())

    def test_inventory_reads_exact_native_pins(self):
        inventory = m.inventory()
        self.assertEqual(inventory['zlib']['pin'], '1.3.2')
        self.assertEqual(inventory['nghttp2']['pin'], '1.63.0')
        self.assertEqual(inventory['curl']['pin'], '8.23.0')
        self.assertEqual(len(inventory), 11)


if __name__ == '__main__':
    unittest.main()
