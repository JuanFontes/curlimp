#!/usr/bin/env python3
"""Multiple-transfer contracts against a local HTTP fixture."""
import http.server
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
import unittest

CLI = os.environ.get('CLI', str(Path(__file__).resolve().parents[1] / 'target/debug/curlimp'))


class Server(http.server.ThreadingHTTPServer):
    def handle_error(self, request, client_address):
        if not isinstance(sys.exception(), (BrokenPipeError, ConnectionResetError)):
            super().handle_error(request, client_address)


class Handler(http.server.BaseHTTPRequestHandler):
    protocol_version = 'HTTP/1.1'

    def log_message(self, *_):
        pass

    def do_HEAD(self):
        self.do_GET()

    def do_POST(self):
        self.do_GET()

    def do_GET(self):
        with self.server.lock:
            self.server.requests.append((self.path, self.client_address, dict(self.headers)))
        body, status, headers = self.path.encode(), 200, []
        if self.path == '/binary': body = b'\x00\xff\x80\r\n'
        if self.path == '/empty': body, status = b'', 204
        if self.path == '/unchanged': body, status = b'', 304
        if self.path == '/error': body, status = b'failure', 502
        if self.path == '/redirect':
            body, status, headers = b'', 302, [('Location', '/one')]
        if self.path == '/set-cookie': headers = [('Set-Cookie', 'session=first; Path=/')]
        if self.path == '/cookie': body = self.headers.get('Cookie', '').encode()
        if self.path == '/echo': body = self.rfile.read(int(self.headers.get('Content-Length', '0')))
        self.send_response(status)
        self.send_header('Content-Length', str(len(body)))
        for name, value in headers: self.send_header(name, value)
        self.end_headers()
        if self.command != 'HEAD':
            try: self.wfile.write(body)
            except (BrokenPipeError, ConnectionResetError): pass


class Transfers(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = Server(('127.0.0.1', 0), Handler)
        cls.server.daemon_threads = True
        cls.server.lock = threading.Lock()
        cls.server.requests = []
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
        with self.server.lock: self.server.requests.clear()

    def run_cli(self, *args, data=None, env=None):
        environment = {k: v for k, v in os.environ.items()
                       if k not in ('CURL_IMPERSONATE', 'CURL_IMPERSONATE_HEADERS')}
        environment.update(env or {})
        return subprocess.run([CLI, '-sS', '--noproxy', '*', *args], cwd=self.root,
                              env=environment, input=data, capture_output=True, timeout=15)

    def urls(self, *paths):
        return [self.url + path for path in paths]

    def test_sequential_stdout_follows_input_order(self):
        result = self.run_cli(*self.urls('/one', '/two', '/binary'))
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout, b'/one/two\x00\xff\x80\r\n')
        self.assertEqual([r[0] for r in self.server.requests], ['/one', '/two', '/binary'])

    def test_output_pairing_is_ordinal_not_proximity(self):
        for args in [self.urls('/one', '/two') + ['-o', 'first', '-osecond'],
                     ['--output=first', *self.urls('/one'), '-o', 'second', *self.urls('/two')]]:
            result = self.run_cli(*args)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(result.stdout, b'')
            self.assertEqual((self.root / 'first').read_bytes(), b'/one')
            self.assertEqual((self.root / 'second').read_bytes(), b'/two')

    def test_only_second_response_saved(self):
        result = self.run_cli(*self.urls('/one', '/two'), '-o', '-', '-o', 'second')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout, b'/one')
        self.assertEqual((self.root / 'second').read_bytes(), b'/two')

    def test_sequential_requests_reuse_connection(self):
        result = self.run_cli(*self.urls('/one', '/two'))
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(len(self.server.requests), 2)
        self.assertEqual(self.server.requests[0][1], self.server.requests[1][1])

    def test_output_and_status_match_reference_curl(self):
        arguments = ['-sS', '--noproxy', '*', '-f', *self.urls('/error', '/one'),
                     '-o', 'first', '-o', '-', '-w', '|%{http_code}|']
        expected = subprocess.run([os.environ.get('REFERENCE_CURL', 'curl'), *arguments],
                                  cwd=self.root, capture_output=True, timeout=10)
        actual = self.run_cli('--no-impersonate', *arguments)
        self.assertEqual(actual.returncode, expected.returncode)
        self.assertEqual(actual.stdout, expected.stdout)

    def test_missing_destination_defaults_to_stdout_and_surplus_is_not_created(self):
        result = self.run_cli(*self.urls('/one', '/two'), '-o', 'first')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout, b'/two')
        result = self.run_cli(*self.urls('/one'), '-o', 'first', '-o', 'unused')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual((self.root / 'first').read_bytes(), b'/one')
        self.assertFalse((self.root / 'unused').exists())

    def test_empty_and_not_modified_output_semantics(self):
        (self.root / 'keep').write_bytes(b'existing')
        result = self.run_cli(*self.urls('/unchanged', '/empty'), '-o', 'keep', '-o', 'empty')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual((self.root / 'keep').read_bytes(), b'existing')
        self.assertEqual((self.root / 'empty').read_bytes(), b'')

    def test_shared_header_file_and_writeout_per_transfer(self):
        result = self.run_cli(*self.urls('/empty', '/error'), '-D', 'headers',
                              '-o', os.devnull, '-o', os.devnull, '-w', '%{http_code}\n')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout, b'204\n502\n')
        headers = (self.root / 'headers').read_bytes()
        self.assertIn(b'HTTP/1.1 204', headers)
        self.assertIn(b'HTTP/1.1 502', headers)

    def test_head_and_include_apply_to_every_transfer(self):
        result = self.run_cli('-I', *self.urls('/one', '/two'))
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.count(b'HTTP/1.1 200'), 2)
        self.assertNotIn(b'/one', result.stdout)
        result = self.run_cli('-i', *self.urls('/one', '/two'))
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.count(b'HTTP/1.1 200'), 2)
        self.assertTrue(result.stdout.endswith(b'/two'))

    def test_stdin_body_is_prepared_once_for_every_url(self):
        result = self.run_cli('--data-binary', '@-', *self.urls('/echo', '/echo'), data=b'payload\x00')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout, b'payload\x00payload\x00')

    def test_headers_query_and_redirects_apply_to_every_url(self):
        (self.root / 'headers.in').write_text('X-Input: shared\n')
        result = self.run_cli('-H', '@headers.in', '-G', '-d', 'key=value', *self.urls('/one', '/two'))
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout, b'/one?key=value/two?key=value')
        self.assertTrue(all(r[2].get('X-Input') == 'shared' for r in self.server.requests))
        result = self.run_cli('-L', *self.urls('/redirect', '/redirect'))
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout, b'/one/one')

    def test_cookie_engine_shares_received_cookies_and_final_jar(self):
        result = self.run_cli('-b', '', '-c', 'cookies', *self.urls('/set-cookie', '/cookie'))
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue(result.stdout.endswith(b'session=first'), result.stdout)
        self.assertIn('\tsession\tfirst', (self.root / 'cookies').read_text())
        result = self.run_cli('-c', '-', *self.urls('/set-cookie', '/cookie'))
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.count(b'# Netscape HTTP Cookie File'), 1)

    def test_sequential_failure_continues_and_last_result_controls_exit(self):
        result = self.run_cli('-f', *self.urls('/error', '/one'))
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout, b'/one')
        self.assertEqual(result.stderr.count(b'(22)'), 1)
        result = self.run_cli('--fail-with-body', *self.urls('/one', '/error'))
        self.assertEqual(result.returncode, 22, result.stderr)
        self.assertEqual(result.stdout, b'/onefailure')
        self.assertEqual(result.stderr.count(b'(22)'), 1)

    def test_invalid_common_settings_preserve_outputs(self):
        (self.root / 'first').write_bytes(b'keep')
        result = self.run_cli('--impersonate', 'invalid', *self.urls('/one', '/two'),
                              '-o', 'first', '-D', 'headers')
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual((self.root / 'first').read_bytes(), b'keep')
        self.assertFalse((self.root / 'headers').exists())
        self.assertEqual(self.server.requests, [])


if __name__ == '__main__':
    unittest.main()
