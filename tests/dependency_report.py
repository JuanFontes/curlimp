#!/usr/bin/env python3
"""Focused offline policy and failure tests for maintenance reporting."""
import importlib.util
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import urllib.error

SCRIPT = Path(__file__).resolve().parents[1] / 'scripts/dependency_report.py'
spec = importlib.util.spec_from_file_location('dependency_report', SCRIPT)
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)


def advisory(identifier='GHSA-test', vulnerable='<= 1.22.0', package='ngtcp2'):
    return {'ghsa_id': identifier, 'withdrawn_at': None,
            'html_url': 'https://github.com/ngtcp2/ngtcp2/security/advisories/' + identifier,
            'severity': 'high', 'summary': 'Upstream advisory',
            'vulnerabilities': [{'package': {'name': package, 'ecosystem': 'other'},
                                 'vulnerable_version_range': vulnerable,
                                 'patched_versions': '1.22.1'}]}


def feeds(curl=None, **github):
    def fetch(url, token):
        if url == 'https://curl.se/docs/vuln.json':
            return curl or [{'id': 'CVE-test', 'affected': [{'versions': ['0.0.1']}]}]
        for name, repo in m.REPOS.items():
            if url == f'https://api.github.com/repos/{repo}/security-advisories?per_page=100&page=1':
                return github.get(name, [])
            if url in (f'https://api.github.com/repos/{repo}/releases/latest',
                       f'https://api.github.com/repos/{repo}/commits/HEAD'):
                return {'tag_name': 'v99.0.0', 'sha': 'a' * 40}
        raise AssertionError('Unexpected advisory source: ' + url)
    return fetch


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

    def test_upstream_exact_v_prefix_and_inclusive_hyphen_ranges(self):
        self.assertTrue(m.in_range('1.9.0', 'v1.9.0'))
        self.assertFalse(m.in_range('1.20.0', 'v1.9.0'))
        self.assertTrue(m.in_range('1.34.5', '1.32.3 - 1.34.5'))
        self.assertFalse(m.in_range('1.34.8', '1.32.3 - 1.34.5'))
        for expression in ('', '*', '>= 1.0 || < 2.0', '1.2 - invalid'):
            with self.assertRaises(ValueError):
                m.in_range('1.2.3', expression)

    def test_partial_or_reversed_ranges_fail_closed_instead_of_excluding_versions(self):
        for expression in ('1.20.0 - 1.22', '1.32.3 - 1.34', '<= 1.34',
                           '1.34', '>= 1.2.3.4', '1.34.8 - 1.32.3'):
            with self.subTest(expression=expression), self.assertRaises(ValueError):
                m.in_range('1.34.8', expression)
        with self.assertRaises(ValueError):
            m.in_range('1.34', '<= 1.34.8')

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
            with patch.object(m, 'fetch_json', side_effect=feeds(curl=bad)):
                data = m.inventory()
                findings, errors = m.advisories(data, '')
                self.assertEqual(data['curl']['security_status'], 'unknown')
                self.assertTrue(any('curl advisories:' in error for error in errors))

    def test_advisory_report_checks_every_range_and_records_backport(self):
        curl = [{'id': 'CVE-test', 'affected': [{'versions': ['8.22.0']}]}]
        nghttp2 = [{'ghsa_id': m.BACKPORT_ID,
                    'html_url': 'https://github.com/nghttp2/nghttp2/security/advisories/' + m.BACKPORT_ID,
                    'vulnerabilities': [{'vulnerable_version_range': '<= 1.68.0'}]}]
        with patch.object(m, 'fetch_json', side_effect=feeds(curl=curl, nghttp2=nghttp2)):
            data = m.inventory()
            findings, errors = m.advisories(data, '')
            self.assertEqual(errors, [])
            self.assertEqual(findings[0]['status'], 'backported')
            self.assertEqual(findings[0]['backport_commit'], m.BACKPORT_COMMIT)
            self.assertEqual(data['curl']['advisory_count'], 1)
        nghttp2[0]['vulnerabilities'].append({'vulnerable_version_range': 'future-schema'})
        with patch.object(m, 'fetch_json', side_effect=feeds(curl=curl, nghttp2=nghttp2)):
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
            self.assertTrue(any('curl advisories' in error for error in result['errors']))
            self.assertTrue(any('ngtcp2 advisories' in error for error in result['errors']))
            self.assertIn('result is incomplete, not clean', (Path(temp) / 'report.md').read_text())

    def test_quic_advisory_is_detected_and_empty_feeds_do_not_claim_safety(self):
        with patch.object(m, 'fetch_json', side_effect=feeds(ngtcp2=[advisory()])):
            data = m.inventory()
            findings, errors = m.advisories(data, '')
        self.assertEqual(errors, [])
        self.assertEqual([(item['dependency'], item['status']) for item in findings],
                         [('ngtcp2', 'needs-triage')])
        self.assertEqual(findings[0]['severity'], 'high')
        self.assertIn('no-published-advisories', data['zlib']['security_status'])
        self.assertIn('manual-review', data['libidn2']['security_status'])
        self.assertIn('manual-review', data['boringssl']['security_status'])

    def test_withdrawn_advisory_does_not_block(self):
        item = advisory()
        item['withdrawn_at'] = '2026-01-01T00:00:00Z'
        item['vulnerabilities'] = []
        with patch.object(m, 'fetch_json', side_effect=feeds(ngtcp2=[item])):
            findings, errors = m.advisories(m.inventory(), '')
        self.assertEqual(errors, [])
        self.assertEqual(findings[0]['status'], 'withdrawn')

    def test_unrecognized_packages_ranges_and_git_pins_remain_unknown(self):
        cases = [('ngtcp2', advisory(package='unrelated-library')),
                 ('ngtcp2', advisory(vulnerable='future-schema')),
                 ('boringssl', advisory(package='boringssl'))]
        for name, item in cases:
            with self.subTest(name=name, item=item), \
                    patch.object(m, 'fetch_json', side_effect=feeds(**{name: [item]})):
                data = m.inventory()
                findings, errors = m.advisories(data, '')
                self.assertTrue(errors)
                self.assertEqual(data[name]['security_status'], 'unknown')
                self.assertEqual(findings[0]['status'], 'unknown')

    def test_conflicting_fixed_version_is_not_silently_treated_as_safe(self):
        item = advisory(vulnerable='> 1.32.3', package='c-ares')
        item['vulnerabilities'][0]['patched_versions'] = '1.34.7'
        with patch.object(m, 'fetch_json', side_effect=feeds(cares=[item])):
            findings, errors = m.advisories(m.inventory(), '')
        self.assertEqual(errors, [])
        self.assertEqual(findings[0]['status'], 'needs-triage')
        self.assertEqual(findings[0]['patched_versions'], ['1.34.7'])

    def test_pagination_retains_advisories_beyond_first_page(self):
        base = 'https://api.github.com/repos/ngtcp2/ngtcp2/security-advisories?per_page=100&page='
        pages = {base + '1': [advisory(identifier=f'GHSA-old-{i}', vulnerable='< 1.0.0')
                             for i in range(100)], base + '2': [advisory()]}
        with patch.object(m, 'fetch_json', side_effect=lambda url, token: pages[url]):
            entry = m.inventory()['ngtcp2']
            findings, errors = m.github_advisories('ngtcp2', entry, '')
        self.assertEqual(errors, [])
        self.assertEqual(len(findings), 101)
        self.assertEqual(findings[-1]['status'], 'needs-triage')

    def test_unknown_advisory_does_not_hide_subsequent_findings(self):
        items = [advisory(vulnerable='future-schema'), advisory(identifier='GHSA-next')]
        with patch.object(m, 'fetch_json', side_effect=feeds(ngtcp2=items)):
            findings, errors = m.advisories(m.inventory(), '')
        self.assertTrue(errors)
        self.assertEqual([item['status'] for item in findings], ['unknown', 'needs-triage'])

    def test_new_findings_fail_process_without_losing_json_or_summary(self):
        with tempfile.TemporaryDirectory() as temp, \
                patch.object(m, 'fetch', return_value='libidn2-99.0.0.tar.gz'), \
                patch.object(m, 'fetch_json', side_effect=feeds(ngtcp2=[advisory()])), \
                patch('sys.argv', ['dependency_report.py', '--output', temp]), \
                patch('sys.stdout', new_callable=io.StringIO):
            self.assertEqual(m.main(), 2)
            result = json.loads((Path(temp) / 'report.json').read_text())
            self.assertEqual(result['triage_required'], 1)
            self.assertIn('needs-triage', (Path(temp) / 'report.md').read_text())

    def test_backported_only_report_passes_without_claiming_full_coverage(self):
        item = advisory(identifier=m.BACKPORT_ID, vulnerable='<= 1.68.0', package='nghttp2')
        with tempfile.TemporaryDirectory() as temp, \
                patch.object(m, 'fetch', return_value='libidn2-99.0.0.tar.gz'), \
                patch.object(m, 'fetch_json', side_effect=feeds(nghttp2=[item])), \
                patch('sys.argv', ['dependency_report.py', '--output', temp]), \
                patch('sys.stdout', new_callable=io.StringIO):
            self.assertEqual(m.main(), 0)
            result = json.loads((Path(temp) / 'report.json').read_text())
            self.assertEqual(result['triage_required'], 0)
            self.assertEqual(result['advisories'][0]['status'], 'backported')
            self.assertIn('not a security certification', (Path(temp) / 'report.md').read_text())

    def reviewed_advisory(self, name):
        if name == 'ngtcp2':
            return advisory(identifier='GHSA-f523-465f-8c8f')
        item = advisory(identifier='GHSA-6wfj-rwm7-3542', vulnerable='> 1.32.3', package='c-ares')
        item['vulnerabilities'][0]['patched_versions'] = '1.34.7'
        return item

    def report_one(self, name, item, entry=None):
        with patch.object(m, 'fetch_json', return_value=[item]):
            findings, errors = m.github_advisories(name, entry or m.inventory()[name], '')
        self.assertEqual(errors, [])
        return findings[0]

    def test_reviewed_native_advisories_retain_sources_and_resolution(self):
        for name, status in [('ngtcp2', 'backported'), ('cares', 'fixed-in-pinned-source')]:
            with self.subTest(name=name):
                result = self.report_one(name, self.reviewed_advisory(name))
                self.assertEqual(result['status'], status)
                self.assertTrue(result['review_sources'])
                self.assertTrue(result['review_note'])
                self.assertTrue(result['ranges'])
                if name == 'ngtcp2':
                    self.assertEqual(result['backport_commit'], '708a7640c1f48fb8ffb540c4b8ea5b4c1dfb8ee5')

    def test_review_does_not_cover_changed_pin_source_hash_or_unrelated_id(self):
        for name in ('ngtcp2', 'cares'):
            for field, value in [('pin', '1.19.0' if name == 'ngtcp2' else '1.34.6'),
                                 ('source_sha256', '0' * 64)]:
                with self.subTest(name=name, field=field):
                    entry = m.inventory()[name]
                    entry[field] = value
                    self.assertEqual(self.report_one(name, self.reviewed_advisory(name), entry)['status'],
                                     'needs-triage')
            item = self.reviewed_advisory(name)
            item['ghsa_id'] = 'GHSA-new-advisory'
            self.assertEqual(self.report_one(name, item)['status'], 'needs-triage')

    def test_review_reopens_for_changed_or_additional_upstream_metadata(self):
        import copy
        for name in ('ngtcp2', 'cares'):
            item = self.reviewed_advisory(name)
            for field, value in [('vulnerable_version_range', '>= 1.0.0'),
                                 ('patched_versions', '2.0.0'), ('patched_versions', None)]:
                changed = copy.deepcopy(item)
                changed['vulnerabilities'][0][field] = value
                with self.subTest(name=name, field=field, value=value):
                    self.assertEqual(self.report_one(name, changed)['status'], 'needs-triage')
            item['vulnerabilities'].append(copy.deepcopy(item['vulnerabilities'][0]))
            self.assertEqual(self.report_one(name, item)['status'], 'needs-triage')

    def test_review_requires_the_reviewed_build_recipe_and_patch_bytes(self):
        import shutil
        for name, changed in [('ngtcp2', 'patches/ngtcp2.patch'),
                              ('ngtcp2', 'CMakeLists.txt'), ('cares', 'CMakeLists.txt')]:
            for missing in (False, True):
                with self.subTest(name=name, missing=missing), tempfile.TemporaryDirectory() as temp:
                    root = Path(temp)
                    target = root / 'vendor/engine' / changed
                    shutil.copytree(m.ROOT / 'vendor/engine', root / 'vendor/engine')
                    if missing:
                        target.unlink()
                    else:
                        target.write_bytes(target.read_bytes() + b'\nchanged\n')
                    entry = m.inventory()[name]
                    with patch.object(m, 'ROOT', root):
                        self.assertEqual(self.report_one(name, self.reviewed_advisory(name), entry)['status'],
                                         'needs-triage')

    def test_reviewed_findings_pass_and_remain_visible_in_both_reports(self):
        with tempfile.TemporaryDirectory() as temp, \
                patch.object(m, 'fetch', return_value='libidn2-99.0.0.tar.gz'), \
                patch.object(m, 'fetch_json', side_effect=feeds(
                    ngtcp2=[self.reviewed_advisory('ngtcp2')], cares=[self.reviewed_advisory('cares')])), \
                patch('sys.argv', ['dependency_report.py', '--output', temp]), \
                patch('sys.stdout', new_callable=io.StringIO):
            self.assertEqual(m.main(), 0)
            report = json.loads((Path(temp) / 'report.json').read_text())
            self.assertEqual(report['triage_required'], 0)
            self.assertEqual(len(report['advisories']), 2)
            summary = (Path(temp) / 'report.md').read_text()
            for finding in report['advisories']:
                self.assertIn(finding['id'], summary)
                self.assertIn(finding['review_note'], summary)
                for source in finding['review_sources']:
                    self.assertIn(source, summary)

    def test_inventory_reads_exact_native_pins(self):
        inventory = m.inventory()
        self.assertEqual(inventory['zlib']['pin'], '1.3.2')
        self.assertEqual(inventory['nghttp2']['pin'], '1.63.0')
        self.assertEqual(inventory['curl']['pin'], '8.23.0')
        self.assertEqual(len(inventory), 11)


if __name__ == '__main__':
    unittest.main()
