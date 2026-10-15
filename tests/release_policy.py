#!/usr/bin/env python3
"""Stable promotion decisions and their HTTP failure boundary."""
import contextlib
import http.server
import io
import os
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
import unittest
from unittest.mock import patch
from urllib.error import HTTPError

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import release_policy as policy


def release(tag='v1.9.0', **changes):
    return dict(dict(tag_name=tag, draft=False, prerelease=False,
                     published_at='2026-10-14T00:00:00Z'), **changes)


class PolicyTests(unittest.TestCase):
    def test_numeric_stable_promotion_and_immutable_equal_version(self):
        for version, current, expected in [
            ('1.10.0', release(), True), ('2.0.0', release(), True),
            ('1.8.9', release(), False), ('1.9.0', release(), False),
            ('0.1.0', None, True), ('2.0.0-rc.1', release(), False),
            ('2.0.0-rc.1', None, False), ('1.9.0+build.2', release(), False)]:
            with self.subTest(version=version, current=current):
                self.assertEqual(policy.should_promote(version, current), expected)

    def test_malformed_versions_and_latest_metadata_fail_closed(self):
        for version in ['01.0.0', '1.0', 'v1.0.0', '1.0.0-01', '1.0.0+', 'bad']:
            with self.subTest(version=version), self.assertRaises(ValueError):
                policy.should_promote(version, None)
        for current in [{}, [], release(tag='bad'), release(tag='v2.0.0-rc.1'),
                        release(draft=True), release(prerelease=True),
                        release(published_at=None), release(published_at='not-a-date'), release(draft=None)]:
            with self.subTest(current=current), self.assertRaises(ValueError):
                policy.should_promote('2.0.0', current)

    def test_only_current_stable_can_publish_pages(self):
        self.assertTrue(policy.is_latest_stable('1.9.0', release()))
        self.assertFalse(policy.is_latest_stable('1.8.9', release()))
        self.assertFalse(policy.is_latest_stable('1.9.0', None))
        self.assertFalse(policy.is_latest_stable('2.0.0-rc.1', release()))

    def test_command_outputs_share_one_promotion_decision(self):
        for version, latest, expected in [
            ('1.10.0', release(), 'promote=true\nprerelease=false\n'),
            ('1.8.0', release(), 'promote=false\nprerelease=false\n'),
            ('2.0.0-rc.1', release(), 'promote=false\nprerelease=true\n')]:
            with self.subTest(version=version), tempfile.TemporaryDirectory() as directory:
                output = Path(directory) / 'github-output'
                with patch.object(policy, 'fetch_latest', return_value=latest), \
                        patch.object(sys, 'argv', ['release_policy.py', '--version', version]), \
                        patch.dict(os.environ, {'GITHUB_OUTPUT': str(output)}), \
                        contextlib.redirect_stdout(io.StringIO()):
                    policy.main()
                self.assertEqual(output.read_text(), expected)
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / 'github-output'
            with patch.object(policy, 'fetch_latest', return_value={}), \
                    patch.object(sys, 'argv', ['release_policy.py', '--version', '2.0.0']), \
                    patch.dict(os.environ, {'GITHUB_OUTPUT': str(output)}), self.assertRaises(ValueError):
                policy.main()
            self.assertFalse(output.exists())

    def test_http_status_and_json_boundary(self):
        class Handler(http.server.BaseHTTPRequestHandler):
            def log_message(self, *_): pass
            def do_GET(self):
                code, body = fixtures[self.path]
                self.send_response(code)
                self.end_headers()
                self.wfile.write(body)
        fixtures = {'/ok': (200, json.dumps(release()).encode()),
                    '/missing': (404, b'{}'), '/bad': (200, b'not json'),
                    '/null': (200, b'null'), '/list': (200, b'[]')}
        fixtures.update({f'/{code}': (code, b'{}') for code in [401, 403, 429, 500, 503]})
        server = http.server.ThreadingHTTPServer(('127.0.0.1', 0), Handler)
        thread = threading.Thread(target=server.serve_forever)
        thread.start()
        try:
            base = f'http://127.0.0.1:{server.server_port}'
            self.assertEqual(policy.fetch_json(base + '/ok'), release())
            self.assertIsNone(policy.fetch_json(base + '/missing'))
            for path in ['/bad', '/null', '/list']:
                with self.subTest(path=path), self.assertRaises(ValueError):
                    policy.fetch_json(base + path)
            for code in [401, 403, 429, 500, 503]:
                with self.subTest(code=code), self.assertRaises(HTTPError):
                    policy.fetch_json(base + f'/{code}')
        finally:
            server.shutdown()
            server.server_close()
            thread.join()

    def test_docker_default_consistency_command(self):
        root = Path(__file__).resolve().parents[1]
        with tempfile.TemporaryDirectory() as directory:
            dockerfile = Path(directory) / 'Dockerfile'
            for image, expected in [('juanfontes/curlimp:1.2.3', 0),
                                    ('juanfontes/curlimp:1.2.3@sha256:' + 'a' * 64, 0),
                                    ('juanfontes/curlimp:1.2.2', 1), ('juanfontes/curlimp:latest', 1)]:
                dockerfile.write_text('ARG RUNTIME_IMAGE=' + image + '\nFROM ${RUNTIME_IMAGE}\n')
                result = subprocess.run([sys.executable, str(root / 'scripts/check-distribution.py'),
                                         '--version', '1.2.3', '--dockerfile', str(dockerfile)],
                                        capture_output=True)
                self.assertEqual(result.returncode, expected, result.stderr)


if __name__ == '__main__':
    unittest.main()
