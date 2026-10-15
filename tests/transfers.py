#!/usr/bin/env python3
"""Multiple-transfer contracts against a local HTTP fixture."""
import http.server
import base64
import json
import resource
import signal
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
import time
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
        if self.path == '/partial': body = b'partial-data'
        if self.path.startswith('/large/'):
            body = b'x' * int(self.path.rsplit('/', 1)[1])
        if self.path == '/redirect':
            body, status, headers = b'', 302, [('Location', '/one')]
        if self.path == '/set-cookie': headers = [('Set-Cookie', 'session=first; Path=/')]
        if self.path == '/cookie': body = self.headers.get('Cookie', '').encode()
        if self.path == '/echo': body = self.rfile.read(int(self.headers.get('Content-Length', '0')))
        if self.path.startswith('/wait/'):
            with self.server.condition:
                self.server.active += 1
                self.server.peak = max(self.server.peak, self.server.active)
                self.server.condition.notify_all()
            self.server.release.wait(10)
        if self.path == '/release': self.server.release.set()
        self.send_response(status)
        self.send_header('Content-Length', str(len(body)))
        for name, value in headers: self.send_header(name, value)
        self.end_headers()
        if self.path == '/partial':
            self.wfile.write(body[:3])
            self.wfile.flush()
            self.close_connection = True
            return
        if self.command != 'HEAD':
            try: self.wfile.write(body)
            except (BrokenPipeError, ConnectionResetError): pass
        if self.path.startswith('/wait/'):
            with self.server.condition:
                self.server.active -= 1
                self.server.condition.notify_all()


class Transfers(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = Server(('127.0.0.1', 0), Handler)
        cls.server.daemon_threads = True
        cls.server.lock = threading.Lock()
        cls.server.requests = []
        cls.server.condition = threading.Condition()
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
        self.server.release = threading.Event()
        self.server.active = self.server.peak = 0

    def run_cli(self, *args, data=None, env=None, child_setup=None):
        environment = {k: v for k, v in os.environ.items()
                       if k not in ('CURL_IMPERSONATE', 'CURL_IMPERSONATE_HEADERS')}
        environment.update(env or {})
        return subprocess.run([CLI, '-sS', '--noproxy', '*', *args], cwd=self.root,
                              env=environment, input=data, capture_output=True, timeout=30,
                              preexec_fn=child_setup)

    def tearDown(self):
        self.server.release.set()
        with self.server.condition:
            self.assertTrue(self.server.condition.wait_for(lambda: self.server.active == 0, 3))

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

    def test_invalid_shared_get_data_preserves_outputs_before_setup(self):
        for options in ([], ['--parallel']):
            for data in (b'\xff', b'key=bad\x00value'):
                with self.subTest(options=options, data=data):
                    for name in ('headers', 'body', 'cookies'):
                        (self.root / name).write_bytes(b'keep-existing')
                    result = self.run_cli(*options, '-G', '--data-binary', '@-',
                                          '-D', 'headers', '-o', 'body', '-c', 'cookies',
                                          *self.urls('/one', '/two'), data=data)
                    self.assertEqual(result.returncode, 2, result.stderr)
                    for name in ('headers', 'body', 'cookies'):
                        self.assertEqual((self.root / name).read_bytes(), b'keep-existing', name)
                    self.assertEqual(self.server.requests, [])

    def test_invalid_common_settings_preserve_outputs(self):
        (self.root / 'first').write_bytes(b'keep')
        result = self.run_cli('--impersonate', 'invalid', *self.urls('/one', '/two'),
                              '-o', 'first', '-D', 'headers')
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual((self.root / 'first').read_bytes(), b'keep')
        self.assertFalse((self.root / 'headers').exists())
        self.assertEqual(self.server.requests, [])

    def test_parallel_admission_and_disabled_parallel(self):
        for flags, limit in [(['-Z', '--parallel-max', '2'], 2),
                             (['-Z', '--parallel-max', '1'], 1),
                             (['-Z', '--no-parallel'], 1),
                             (['--parallel-max', '2'], 1)]:
            with self.subTest(flags=flags):
                self.server.release.clear()
                self.server.active = self.server.peak = 0
                args = [CLI, '-sS', '--noproxy', '*', *flags,
                        *self.urls('/wait/1', '/wait/2', '/wait/3', '/wait/4')]
                with subprocess.Popen(args, cwd=self.root, stdout=subprocess.PIPE,
                                      stderr=subprocess.PIPE) as process:
                    try:
                        with self.server.condition:
                            ready = self.server.condition.wait_for(lambda: self.server.active >= limit, 4)
                            self.assertTrue(ready, f'expected {limit} admitted transfers')
                            self.assertEqual(self.server.active, limit)
                        self.server.release.set()
                        stdout, stderr = process.communicate(timeout=10)
                        self.assertEqual(process.returncode, 0, stderr)
                        self.assertLessEqual(self.server.peak, limit)
                        for number in range(1, 5): self.assertIn(f'/wait/{number}'.encode(), stdout)
                    finally:
                        self.server.release.set()
                        if process.poll() is None: process.kill()

    def test_parallel_files_and_writeout_are_independent(self):
        result = self.run_cli('-Z', *self.urls('/wait/1', '/release'), '-o', 'a', '-o', 'b',
                              '-w', '%{http_code}\n')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual((self.root / 'a').read_bytes(), b'/wait/1')
        self.assertEqual((self.root / 'b').read_bytes(), b'/release')
        self.assertEqual(result.stdout, b'200\n200\n')

    def test_parallel_failure_frees_slot_and_is_not_masked(self):
        result = self.run_cli('-Z', '--parallel-max', '1', '-f', *self.urls('/error', '/one', '/two'))
        self.assertEqual(result.returncode, 22, result.stderr)
        self.assertEqual(result.stdout, b'/one/two')
        self.assertEqual(result.stderr.count(b'(22)'), 1)

    def test_parallel_timeout_does_not_block_other_results(self):
        result = self.run_cli('-Z', '-m', '0.2', *self.urls('/wait/1', '/two'),
                              '-o', 'a', '-o', 'b')
        self.server.release.set()
        self.assertEqual(result.returncode, 28, result.stderr)
        self.assertEqual((self.root / 'b').read_bytes(), b'/two')
        self.assertFalse((self.root / 'a').exists())

    def test_parallel_partial_body_preserves_other_output(self):
        result = self.run_cli('-Z', *self.urls('/partial', '/one'), '-o', 'a', '-o', 'b')
        self.assertEqual(result.returncode, 18, result.stderr)
        self.assertEqual((self.root / 'a').read_bytes(), b'par')
        self.assertEqual((self.root / 'b').read_bytes(), b'/one')

    def test_parallel_broken_stdout_returns_write_error(self):
        with subprocess.Popen([CLI, '-sS', '-Z', '--noproxy', '*', *self.urls('/one', '/two')],
                              cwd=self.root, stdout=subprocess.PIPE, stderr=subprocess.PIPE) as process:
            process.stdout.close()
            process.wait(timeout=10)
            self.assertEqual(process.returncode, 23, process.stderr.read())

    def test_repeated_output_path_does_not_append(self):
        result = self.run_cli(*self.urls('/one', '/two'), '-o', 'same', '-o', 'same')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual((self.root / 'same').read_bytes(), b'/two')

    def test_parallel_header_sink_cookies_and_profile(self):
        result = self.run_cli('firefox147', '-Z', '--parallel-max', '1', '-c', 'jar',
                              *self.urls('/set-cookie', '/cookie'), '-D', 'headers')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue(result.stdout.endswith(b'session=first'))
        self.assertEqual((self.root / 'headers').read_bytes().count(b'HTTP/1.1 200'), 2)
        self.assertTrue(all('Firefox/147' in r[2].get('User-Agent', '') for r in self.server.requests))

    def test_multi_json_is_one_ordered_array_with_transfer_identity(self):
        result = self.run_cli('-Z', '--json-output', '-i', *self.urls('/wait/1', '/release', '/binary'))
        self.assertEqual(result.returncode, 0, result.stderr)
        values = json.loads(result.stdout)
        self.assertEqual([v['transfer_index'] for v in values], [0, 1, 2])
        self.assertEqual([v['url'] for v in values], self.urls('/wait/1', '/release', '/binary'))
        self.assertEqual(values[0]['body'], '/wait/1')
        self.assertEqual(values[1]['body'], '/release')
        self.assertEqual(base64.b64decode(values[2]['body']), b'\x00\xff\x80\r\n')
        self.assertTrue(all(v['headers'][0].startswith('HTTP/1.1 200') for v in values))

    def test_multi_json_head_and_network_failure_keep_individual_results(self):
        result = self.run_cli('-Z', '--json-output', *self.urls('/partial', '/one'))
        self.assertEqual(result.returncode, 18, result.stderr)
        values = json.loads(result.stdout)
        self.assertEqual([v['exit_code'] for v in values], [18, 0])
        self.assertEqual([v['body'] for v in values], ['par', '/one'])
        result = self.run_cli('--json-output', '-I', *self.urls('/one', '/empty'))
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue(all('body' not in v for v in json.loads(result.stdout)))

    def test_multi_file_exports_do_not_overwrite_repeated_urls(self):
        for mode, extension in [('--txt', 'txt'), ('--json-file', 'json')]:
            result = self.run_cli('-Z', mode, *self.urls('/one', '/one', '/binary'))
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(result.stdout, b'')
            files = list(self.root.glob('*.' + extension))
            self.assertEqual(len(files), 3)
            self.assertTrue(all(p.stat().st_mode & 0o077 == 0 for p in files))
            if extension == 'json':
                values = sorted((json.loads(p.read_text()) for p in files), key=lambda v: v['transfer_index'])
                self.assertEqual([v['transfer_index'] for v in values], [0, 1, 2])
                self.assertEqual(values[0]['body'], values[1]['body'])

    def test_multi_json_identity_never_contains_url_credentials(self):
        private = self.url.replace('http://', 'http://alice:secret@') + '/one#private'
        result = self.run_cli('--json-output', private, *self.urls('/two'))
        self.assertEqual(result.returncode, 0, result.stderr)
        values = json.loads(result.stdout)
        self.assertEqual(values[0]['url'], self.url + '/one')
        self.assertNotIn(b'secret', result.stdout)
        self.assertNotIn(b'#private', result.stdout)

    def test_json_temp_failure_has_no_misleading_aggregate(self):
        result = self.run_cli('--json-output', *self.urls('/one', '/two'),
                              env={'TMPDIR': str(self.root / 'missing')})
        self.assertEqual(result.returncode, 23, result.stderr)
        self.assertEqual(result.stdout, b'')

    def test_json_spools_leave_no_named_files(self):
        temporary = self.root / 'temporary'
        temporary.mkdir()
        result = self.run_cli('-Z', '--json-output', *self.urls('/one', '/binary'),
                              env={'TMPDIR': str(temporary)})
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(len(json.loads(result.stdout)), 2)
        self.assertEqual(list(temporary.iterdir()), [])

    def test_json_size_limit_suppresses_entire_aggregate(self):
        result = self.run_cli('-Z', '--json-output', *self.urls('/one', '/large/67108865'))
        self.assertEqual(result.returncode, 23, result.stderr)
        self.assertEqual(result.stdout, b'')

    def test_json_storage_write_failure_returns_23_without_report(self):
        def limit_files():
            signal.signal(signal.SIGXFSZ, signal.SIG_IGN)
            resource.setrlimit(resource.RLIMIT_FSIZE, (4096, 4096))
        result = self.run_cli('--json-output', *self.urls('/large/8192', '/one'), child_setup=limit_files)
        self.assertEqual(result.returncode, 23, result.stderr)
        self.assertEqual(result.stdout, b'')

    def test_completed_json_results_do_not_keep_one_descriptor_each(self):
        def limit_descriptors():
            resource.setrlimit(resource.RLIMIT_NOFILE, (64, 64))
        result = self.run_cli('-Z', '--parallel-max', '2', '--json-output',
                              *self.urls(*(['/one'] * 100)), child_setup=limit_descriptors)
        self.assertEqual(result.returncode, 0, result.stderr)
        values = json.loads(result.stdout)
        self.assertEqual([v['transfer_index'] for v in values], list(range(100)))
        self.assertTrue(all(v['body'] == '/one' for v in values))

    def test_aggregate_memory_does_not_grow_with_total_body_size(self):
        # wait4 reports the child CLI's peak RSS, independently of fixture memory.
        with (self.root / 'aggregate.json').open('wb') as output, (self.root / 'stderr').open('wb') as errors:
            process = subprocess.Popen([CLI, '-sS', '--noproxy', '*', '-Z', '--parallel-max', '16',
                                        '--json-output', *self.urls(*(['/large/8388608'] * 16))],
                                       cwd=self.root, stdout=output, stderr=errors)
            deadline = time.monotonic() + 30
            while True:
                waited, status, usage = os.wait4(process.pid, os.WNOHANG)
                if waited: break
                if time.monotonic() >= deadline:
                    process.kill()
                    process.wait()
                    self.fail('large aggregate did not finish within 30 seconds')
                time.sleep(0.01)
            process.returncode = os.waitstatus_to_exitcode(status)
        self.assertEqual(process.returncode, 0, (self.root / 'stderr').read_bytes())
        peak = usage.ru_maxrss if sys.platform == 'darwin' else usage.ru_maxrss * 1024
        self.assertLess(peak, 96 * 1024 * 1024, f'peak RSS was {peak} bytes for 128 MiB of response bodies')
        self.assertGreater((self.root / 'aggregate.json').stat().st_size, 128 * 1024 * 1024)

    def test_json_accepts_exactly_64_mib_selected_bytes(self):
        with (self.root / 'exact.json').open('wb') as output:
            result = subprocess.run([CLI, '-sS', '--noproxy', '*', '--json-output',
                                     *self.urls('/large/67108864')], cwd=self.root,
                                    stdout=output, stderr=subprocess.PIPE, timeout=30)
        self.assertEqual(result.returncode, 0, result.stderr)
        with (self.root / 'exact.json').open() as output:
            value = json.load(output)
        self.assertEqual(len(value['body']), 64 * 1024 * 1024)
        self.assertEqual(value['body_encoding'], 'utf-8')


if __name__ == '__main__':
    unittest.main()
