#!/usr/bin/env python3
"""Response export contract exercised against a local HTTP fixture."""
import base64
import gzip
import http.server
import json
import os
from pathlib import Path
import re
import subprocess
import tempfile
import threading
import unittest

CLI = os.environ.get('CLI', str(Path(__file__).resolve().parents[1] / 'target/debug/curlimp'))
HTML = '<!doctype html>\n<html><body>Olá ☃<script>const data={"x":"a\\b"};</script></body></html>\n'.encode()
BINARY = b'\x00\xff\x80\x01hello\r\n'


class Handler(http.server.BaseHTTPRequestHandler):
    protocol_version = 'HTTP/1.1'

    def log_message(self, *_):
        pass

    def do_HEAD(self):
        self.do_GET()

    def do_POST(self):
        self.do_GET()

    def do_GET(self):
        path = self.path.split('?')[0]
        body, code, extra = HTML, 200, []
        if path == '/binary': body = BINARY
        if path == '/controls': body = bytes(range(128)) + '☃'.encode()
        if path.startswith('/binary-size/'):
            body = bytes(range(256))[:int(path.rsplit('/', 1)[1])]
        if path == '/header-bytes': extra.append(('X-Latin', '\xff'))
        if path == '/gzip':
            body = gzip.compress(HTML, mtime=0)
            extra.append(('Content-Encoding', 'gzip'))
        if path == '/empty': body, code = b'', 204
        if path == '/error': body, code = b'failed\n', 502
        if path == '/redirect':
            body, code = b'redirect', 302
            extra.append(('Location', '/html'))
        if path == '/echo':
            body = self.rfile.read(int(self.headers.get('Content-Length', '0')))
        if path == '/large': body = b'x' * (64 * 1024 * 1024 + 1)
        if path == '/boundary-text': body = b'a' * 65535 + 'é☃😀'.encode() + b'\nend'
        if path == '/boundary-binary': body = b'a' * 65535 + b'\xff\x80\x00\n'
        if path == '/long-headers':
            extra.extend([('X-Long', 'a' * 40000), ('X-Long', 'b' * 40000), ('X-Opaque', '\xff')])
        self.send_response(code)
        self.send_header('Content-Type', 'text/html; charset=utf-8')
        self.send_header('X-Repeat', 'one')
        self.send_header('X-Repeat', 'two')
        self.send_header('Content-Length', str(len(body)))
        self.send_header('Connection', 'close')
        for key, value in extra: self.send_header(key, value)
        self.end_headers()
        if path == '/partial':
            self.wfile.write(body[:10])
            self.wfile.flush()
            self.close_connection = True
            return
        if self.command != 'HEAD':
            try: self.wfile.write(body)
            except (BrokenPipeError, ConnectionResetError): pass


class Exports(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = http.server.ThreadingHTTPServer(('127.0.0.1', 0), Handler)
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()
        cls.url = f'http://127.0.0.1:{cls.server.server_port}'

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join()

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)

    def run_cli(self, *args, path='/html'):
        env = {k: v for k, v in os.environ.items() if k not in ['CURL_IMPERSONATE', 'CURL_IMPERSONATE_HEADERS']}
        return subprocess.run([CLI, '-sS', *args, self.url + path], cwd=self.root, env=env,
                              capture_output=True, timeout=20)

    def report(self, *args, path='/html', code=0):
        result = self.run_cli('--json-output', *args, path=path)
        self.assertEqual(result.returncode, code, result.stderr)
        return json.loads(result.stdout), result

    def test_json_html_is_one_unmodified_string(self):
        doc, result = self.report()
        self.assertEqual(doc['schema_version'], 1)
        self.assertEqual(doc['status'], 200)
        self.assertEqual(doc['exit_code'], 0)
        self.assertEqual(doc['body_encoding'], 'utf-8')
        self.assertEqual(doc['body'].encode(), HTML)
        self.assertNotIn('headers', doc)
        self.assertEqual(result.stderr, b'')

    def test_spooled_fields_preserve_utf8_binary_and_long_header_boundaries(self):
        for path, expected in [('/boundary-text', b'a' * 65535 + 'é☃😀'.encode() + b'\nend'),
                               ('/boundary-binary', b'a' * 65535 + b'\xff\x80\x00\n')]:
            doc, _ = self.report(path=path)
            actual = doc['body'].encode() if doc['body_encoding'] == 'utf-8' else base64.b64decode(doc['body'])
            self.assertEqual(actual, expected)
        doc, _ = self.report('-i', path='/long-headers')
        self.assertEqual(doc['headers_encoding'], 'base64')
        headers = [base64.b64decode(value) for value in doc['headers']]
        self.assertIn(b'X-Long: ' + b'a' * 40000 + b'\r\n', headers)
        self.assertIn(b'X-Long: ' + b'b' * 40000 + b'\r\n', headers)
        self.assertIn(b'X-Opaque: \xff\r\n', headers)

    def test_include_and_head_select_fields_and_keep_duplicate_headers(self):
        for flag in ['-i', '-I']:
            doc, _ = self.report(flag)
            self.assertEqual(doc['headers_encoding'], 'utf-8')
            self.assertTrue(doc['headers'][0].startswith('HTTP/1.1 200'))
            self.assertIn('X-Repeat: one\r\n', doc['headers'])
            self.assertIn('X-Repeat: two\r\n', doc['headers'])
            if flag == '-i': self.assertEqual(doc['body'].encode(), HTML)
            else: self.assertNotIn('body', doc)

    def test_head_include_order_selects_json_headers(self):
        for flags, selected in [(["-I"], True), (["-I", "--no-include"], False),
                                (["--no-include", "-I"], True),
                                (["-I", "--no-include", "-i"], True)]:
            with self.subTest(flags=flags):
                doc, _ = self.report(*flags)
                self.assertNotIn("body", doc)
                self.assertEqual("headers" in doc, selected)
                if selected:
                    self.assertTrue(doc["headers"][0].startswith("HTTP/1.1 200"))

    def test_txt_preserves_the_selected_bytes(self):
        for flags, path, expected in [([], '/html', HTML), ([], '/binary', BINARY), ([], '/empty', b'')]:
            result = self.run_cli('--txt', *flags, path=path)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(result.stdout, b'')
            files = list(self.root.glob('*.txt'))
            self.assertEqual(len(files), 1)
            self.assertEqual(files[0].read_bytes(), expected)
            files[0].unlink()
        result = self.run_cli('--txt', '-i')
        self.assertEqual(result.returncode, 0, result.stderr)
        content = next(self.root.glob('*.txt')).read_bytes()
        self.assertTrue(content.startswith(b'HTTP/1.1 200'))
        self.assertTrue(content.endswith(b'\r\n\r\n' + HTML))

    def test_json_file_name_permissions_and_no_clobber(self):
        for _ in range(2):
            result = self.run_cli('--json-file', path='/a/../html?token=secret#fragment')
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(result.stdout, b'')
        files = list(self.root.glob('*.json'))
        self.assertEqual(len(files), 2)
        for file in files:
            self.assertRegex(file.name, r'^\d{4}-\d{2}-\d{2}_\d{2}-\d{2}-\d{2}_127-0-0-1-')
            self.assertNotIn('secret', file.name)
            self.assertNotIn('fragment', file.name)
            self.assertLessEqual(len(file.name), 160)
            self.assertEqual(file.stat().st_mode & 0o077, 0)
            self.assertEqual(json.loads(file.read_text())['body'].encode(), HTML)

    def test_malformed_url_credentials_never_become_filenames(self):
        for separator in ['?', '#', '/']:
            url = f'http://user:secret{separator}value@127.0.0.1:1/path'
            result = subprocess.run([CLI, '-sS', '--json-file', url], cwd=self.root,
                                    capture_output=True, timeout=20)
            self.assertEqual(result.returncode, 3, result.stderr)
            files = list(self.root.glob('*.json'))
            self.assertEqual(len(files), 1)
            self.assertRegex(files[0].name, r'_response\.json$')
            self.assertEqual(json.loads(files[0].read_text())['exit_code'], 3)
            files[0].unlink()
        url = self.url.replace('://', '://user:p%3F%23%2Fsecret@') + '/html?token=secret#fragment'
        result = subprocess.run([CLI, '-sS', '--json-file', url], cwd=self.root,
                                capture_output=True, timeout=20)
        self.assertEqual(result.returncode, 0, result.stderr)
        name = next(self.root.glob('*.json')).name
        self.assertRegex(name, r'_127-0-0-1-html\.json$')
        self.assertNotIn('secret', name)

    def test_binary_is_explicit_base64_not_lossy_text(self):
        doc, _ = self.report(path='/binary')
        self.assertEqual(doc['body_encoding'], 'base64')
        self.assertEqual(base64.b64decode(doc['body'], validate=True), BINARY)

    def test_json_round_trips_controls_and_base64_padding(self):
        doc, _ = self.report(path='/controls')
        self.assertEqual(doc['body'].encode(), bytes(range(128)) + '☃'.encode())
        for size in [129, 130, 131, 255, 256]:
            doc, _ = self.report(path=f'/binary-size/{size}')
            self.assertEqual(doc['body_encoding'], 'base64')
            self.assertEqual(base64.b64decode(doc['body'], validate=True), bytes(range(256))[:size])
        doc, _ = self.report('-i', path='/header-bytes')
        self.assertEqual(doc['headers_encoding'], 'base64')
        self.assertIn(b'X-Latin: \xff\r\n', [base64.b64decode(line, validate=True) for line in doc['headers']])

    def test_network_failure_keeps_partial_response_and_exit_code(self):
        doc, _ = self.report(path='/partial', code=18)
        self.assertEqual(doc['exit_code'], 18)
        self.assertEqual(doc['body'].encode(), HTML[:10])
        result = self.run_cli('--txt', path='/partial')
        self.assertEqual(result.returncode, 18)
        self.assertEqual(next(self.root.glob('*.txt')).read_bytes(), HTML[:10])

    def test_connection_failure_still_produces_json(self):
        result = subprocess.run([CLI, '-sS', '--noproxy', '*', '--json-output',
                                 '--max-time', '2', 'http://127.0.0.1:1/'],
                                cwd=self.root, capture_output=True, timeout=5)
        self.assertEqual(result.returncode, 7, result.stderr)
        doc = json.loads(result.stdout)
        self.assertEqual((doc['status'], doc['exit_code'], doc['body']), (0, 7, ''))

    def test_decompression_and_raw_override(self):
        doc, _ = self.report(path='/gzip')
        self.assertEqual(doc['body'].encode(), HTML)
        doc, _ = self.report('--no-compressed', path='/gzip')
        self.assertEqual(gzip.decompress(base64.b64decode(doc['body'])), HTML)

    def test_redirect_headers_are_ordered_and_body_is_final(self):
        doc, _ = self.report('-i', '-L', path='/redirect')
        lines = doc['headers']
        self.assertTrue(lines[0].startswith('HTTP/1.1 302'))
        self.assertTrue(any(line.startswith('HTTP/1.1 200') for line in lines[1:]))
        self.assertEqual(doc['body'].encode(), HTML)

    def test_http_error_codes_and_empty_body_are_preserved(self):
        doc, _ = self.report('--fail-with-body', path='/error', code=22)
        self.assertEqual((doc['status'], doc['exit_code'], doc['body']), (502, 22, 'failed\n'))
        doc, _ = self.report('-f', path='/error', code=22)
        self.assertEqual(doc['body'], '')
        doc, _ = self.report(path='/empty')
        self.assertEqual((doc['status'], doc['body']), (204, ''))

    def test_request_json_keeps_its_existing_meaning(self):
        payload = '{"message":"hello"}'
        doc, _ = self.report('--json', payload, path='/echo')
        self.assertEqual(doc['body'], payload)

    def test_verbose_stays_outside_json(self):
        doc, result = self.report('-v')
        self.assertEqual(doc['body'].encode(), HTML)
        self.assertIn(b'HTTP', result.stderr)

    def test_conflicting_options_fail_without_creating_files(self):
        for mode in ['--txt', '--json-output', '--json-file']:
            for flag, value in [('-o', 'out'), ('-D', 'headers'), ('-w', '%{http_code}')]:
                result = self.run_cli(mode, flag, value)
                self.assertEqual(result.returncode, 2, result.stderr)
                self.assertEqual(result.stdout, b'')
        for args in [('--txt', '--json-output'), ('--json-output', '--json-file'), ('--txt', '--json-file'), ('--json-file', '-N')]:
            self.assertEqual(self.run_cli(*args).returncode, 2)
        self.assertEqual(list(self.root.iterdir()), [])

    def test_invalid_profile_does_not_create_export(self):
        result = self.run_cli('--txt', '--impersonate', 'not-a-profile')
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(list(self.root.iterdir()), [])

    def test_json_limit_fails_explicitly_without_partial_json(self):
        result = self.run_cli('--json-file', path='/large')
        self.assertEqual(result.returncode, 23, result.stderr)
        self.assertIn(b'64 MiB', result.stderr)
        self.assertEqual(result.stdout, b'')
        self.assertEqual(list(self.root.iterdir()), [])


if __name__ == '__main__':
    unittest.main(verbosity=2)
