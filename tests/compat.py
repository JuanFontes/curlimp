#!/usr/bin/env python3
"""Real HTTP/TLS compatibility checks; no public services required."""
import base64
import gzip
import http.server
import json
import os
from pathlib import Path
import ssl
import shutil
import socket
import subprocess
import tempfile
import threading
import time
import unittest
from urllib.parse import urlsplit
import zlib

CLI = os.environ.get("CLI", str(Path(__file__).resolve().parents[1] / "target/debug/curlimp"))
CURL = os.environ.get("REFERENCE_CURL", "curl")
BINARY = b"\x00\xffhello\r\n\x80world\n"


class Handler(http.server.BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"
    server_version = "fixture"
    sys_version = ""

    def log_message(self, *_):
        pass

    def handle(self):
        # A client rejecting the test certificate may close after TLS setup.
        try:
            super().handle()
        except ConnectionResetError:
            pass

    def date_time_string(self, *_):
        return "Thu, 01 Jan 1970 00:00:00 GMT"

    def do_HEAD(self):
        self.respond()

    def do_GET(self):
        self.respond()

    def do_POST(self):
        self.respond()

    def do_PATCH(self):
        self.respond()

    def respond(self):
        body = self.rfile.read(int(self.headers.get("Content-Length", "0")))
        code, headers = 200, []
        if self.path == "/bytes":
            payload = BINARY
        elif self.path == "/not-modified":
            code, payload = 304, b""
        elif self.path == "/opaque":
            headers.append(("Content-Type", 'text/plain; description="caf\xe9"'))
            payload = b"ok"
        elif self.path == "/empty":
            code, payload = 204, b""
        elif self.path == "/gzip":
            payload = gzip.compress(BINARY, mtime=0)
            headers.append(("Content-Encoding", "gzip"))
        elif self.path == "/deflate":
            payload = zlib.compress(BINARY)
            headers.append(("Content-Encoding", "deflate"))
        elif self.path == "/profile-headers":
            payload = json.dumps(list(self.headers.items())).encode()
        elif self.path == "/redirect":
            code, payload = 302, b"redirect body"
            headers.append(("Location", "/bytes"))
        elif self.path == "/redirect-post":
            code, payload = 302, b"redirect body"
            headers.append(("Location", "/echo"))
        elif self.path == "/redirect-host":
            code, payload = 302, b"redirect body"
            headers.append(("Location", f"http://localhost:{self.server.server_port}/echo"))
        elif self.path == "/missing":
            code, payload = 404, b"missing resource\n"
        elif self.path.endswith("/slow-credentials"):
            payload = json.dumps({"user": self.headers.get("Authorization"),
                                  "proxy": self.headers.get("Proxy-Authorization")}).encode()
            self.server.credentials_seen.set()
            self.server.credentials_release.wait(3)
        elif self.path == "/slow":
            time.sleep(0.2)
            payload = b"late"
        elif self.path == "/set-cookie":
            headers.append(("Set-Cookie", "session=hello; Path=/"))
            payload = b"cookie saved"
        elif self.path == "/profile":
            payload = json.dumps({name.lower(): value for name, value in self.headers.items()}, sort_keys=True).encode()
        else:
            names = ["Content-Type", "Accept", "X-Test", "Cookie", "Authorization", "Referer"]
            payload = json.dumps({"method": self.command, "path": self.path,
                                  "body": base64.b64encode(body).decode(),
                                  "headers": {n.lower(): self.headers.get_all(n, []) for n in names}}, sort_keys=True).encode()
        self.send_response(code)
        for name, value in headers:
            self.send_header(name, value)
        self.send_header("Content-Length", str(len(payload)))
        self.send_header("Connection", "close")
        self.end_headers()
        if self.command != "HEAD":
            try:
                self.wfile.write(payload)
            except (BrokenPipeError, ConnectionResetError, ssl.SSLError):
                pass


class Compatibility(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory()
        cls.root = Path(cls.temp.name)
        cls.server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        cls.server.daemon_threads = True
        cls.server.credentials_seen = threading.Event()
        cls.server.credentials_release = threading.Event()
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()
        cls.url = f"http://127.0.0.1:{cls.server.server_port}"
        cls.cert = cls.root / "cert.pem"
        key = cls.root / "key.pem"
        subprocess.run(["openssl", "req", "-x509", "-newkey", "rsa:2048", "-nodes", "-days", "1",
                        "-keyout", str(key), "-out", str(cls.cert), "-subj", "/CN=localhost",
                        "-addext", "subjectAltName=DNS:localhost,IP:127.0.0.1"], check=True, capture_output=True)
        cls.tls = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        ctx.load_cert_chain(cls.cert, key)
        cls.tls.socket = ctx.wrap_socket(cls.tls.socket, server_side=True)
        threading.Thread(target=cls.tls.serve_forever, daemon=True).start()
        cls.tls_url = f"https://127.0.0.1:{cls.tls.server_port}"

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.tls.shutdown()
        cls.tls.server_close()
        cls.temp.cleanup()

    def run_cli(self, args, *, engine=CLI, data=None, environment=None):
        env = {k: v for k, v in os.environ.items() if k.lower() not in
               {"http_proxy", "https_proxy", "all_proxy", "no_proxy", "curl_impersonate", "curl_impersonate_headers", "curl_ca_bundle", "ssl_cert_file", "ssl_cert_dir"}}
        env.update(environment or {})
        return subprocess.run([engine, "-q", "-sS", *args], input=data, capture_output=True, env=env, cwd=getattr(self, "root", None), timeout=10)

    def compare(self, args, *, data=None):
        # Compare curl's generic defaults explicitly; browser defaults have
        # their own request/header and HTTP2 assertions below.
        actual = self.run_cli(["--no-impersonate", *args], data=data)
        expected = self.run_cli(args, engine=CURL, data=data)
        self.assertEqual(actual.returncode, expected.returncode, actual.stderr)
        self.assertEqual(actual.stdout, expected.stdout, actual.stderr)
        return actual

    def test_audit_not_modified_preserves_output(self):
        for flags in ([], ["-i"], ["-I"], ["-I", "--no-include"]):
            for exists in (False, True):
                outcomes = []
                for engine in (CLI, CURL):
                    output = self.root / "not-modified.bin"
                    output.unlink(missing_ok=True)
                    if exists:
                        output.write_bytes(b"KEEP")
                    result = self.run_cli([*flags, "-o", str(output), self.url + "/not-modified"], engine=engine)
                    self.assertEqual(result.returncode, 0, result.stderr)
                    outcomes.append(output.read_bytes() if output.exists() else None)
                self.assertEqual(*outcomes, (flags, exists))

    def test_audit_head_include_order(self):
        for flags in (["-I", "--no-include"], ["--no-include", "-I"], ["-I", "--no-include", "-i"]):
            with self.subTest(flags=flags):
                self.compare([*flags, self.url + "/bytes"])
        headers = self.root / "head-dump.headers"
        result = self.compare(["-I", "--no-include", "-D", str(headers), self.url + "/bytes"])
        self.assertEqual(result.stdout, b"")
        self.assertTrue(headers.read_bytes().startswith(b"HTTP/1.1 200"))

    def test_audit_empty_data_separators(self):
        for flags in (["-d", "", "-d", "a=1"], ["-d", "a=1", "-d", ""],
                      ["-d", "", "-d", "", "-d", "a=1"],
                      ["--data-binary", "", "--data-binary", "a=1"]):
            with self.subTest(flags=flags):
                self.compare([*flags, self.url + "/echo"])
        for url in ("/echo", "/echo?old=1", "/echo?", "/echo?old=?"):
            self.compare(["-G", "-d", "", self.url + url])
            self.compare(["-G", self.url + url])

    def test_audit_stdin_readers_follow_argument_order(self):
        pairs = [("-w", "@-"), ("-d", "@-"), ("-H", "@-"), ("--data-binary", "@-")]
        for left, right in ((pairs[0], pairs[1]), (pairs[1], pairs[0]),
                            (pairs[2], pairs[3]), (pairs[3], pairs[2])):
            with self.subTest(left=left, right=right):
                self.compare([*left, *right, self.url + "/echo"], data=b"X-Test: hello\n")
        # Superseded write-out options still consume their input in curl.
        self.compare(["-w", "@-", "-w", "done", "-d", "@-", self.url + "/echo"], data=b"consumed")

    def test_audit_superseded_writeout_formats_do_not_fail(self):
        source = self.root / "discarded-format.txt"
        source.write_bytes(b"%{discarded}\n")
        for discarded in ("%{discarded}", "%{unfinished", "@" + str(source)):
            with self.subTest(discarded=discarded):
                result = self.compare(["-o", os.devnull, "-w", discarded, "-w", "FINAL", self.url])
                self.assertEqual(result.stdout, b"FINAL")
        # Invalid superseded stdin is still consumed before the body reader.
        self.compare(["-w", "@-", "-w", "FINAL", "-d", "@-", self.url + "/echo"],
                     data=b"%{discarded}")

    def test_audit_writeout_file_and_escapes(self):
        source = self.root / "format.txt"
        source.write_bytes(b"first\r\n%{http_code}\x00last\n" + rb"\n")
        self.compare(["-o", os.devnull, "-w", "@" + str(source), self.url])
        self.compare(["-o", os.devnull, "-w", "@-", self.url], data=source.read_bytes())
        for value in (r"a\\b", r"a\\n", r"a\q", "trailing\\"):
            self.compare(["-o", os.devnull, "-w", value, self.url])

    def test_audit_writeout_preserves_opaque_metadata(self):
        result = self.compare(["-o", os.devnull, "-w", "%{content_type}", self.url + "/opaque"])
        self.assertEqual(result.stdout, b'text/plain; description="caf\xe9"')

    def test_audit_invalid_profile_preserves_header_file(self):
        for profile in ("not-a-profile", "okhttp4_android", "okhttp4", "OKHTTP4:no"):
            for environment in (False, True):
                with self.subTest(profile=profile, environment=environment):
                    output = self.root / "keep.headers"
                    output.write_bytes(b"KEEP")
                    flags = [] if environment else ["--impersonate", profile]
                    env = {"CURL_IMPERSONATE": profile} if environment else {}
                    result = self.run_cli([*flags, "-D", str(output), self.url], environment=env)
                    self.assertNotEqual(result.returncode, 0, (profile, environment))
                    self.assertEqual(output.read_bytes(), b"KEEP")
        # Native aliases must continue to work.
        self.assertEqual(self.run_cli(["--impersonate", "safari26_0_1", self.url]).returncode, 0)

    def test_audit_json_cookie_stdout_conflict(self):
        result = self.run_cli(["--json-output", "-c", "-", self.url])
        self.assertEqual(result.returncode, 2)
        self.assertEqual(result.stdout, b"")
        for mode in ("--txt", "--json-file"):
            # These combinations do not share JSON stdout.
            result = self.run_cli([mode, "-c", "-", self.url])
            self.assertEqual(result.returncode, 0, result.stderr)

    def test_audit_ca_bundle_suppresses_env_directory(self):
        other = self.root / "untrusted.pem"
        subprocess.run(["openssl", "req", "-x509", "-newkey", "rsa:2048", "-nodes", "-days", "1",
                        "-keyout", str(self.root / "untrusted.key"), "-out", str(other),
                        "-subj", "/CN=untrusted"], check=True, capture_output=True)
        directory = self.root / "ca-directory"
        directory.mkdir(exist_ok=True)
        hashed = subprocess.check_output(["openssl", "x509", "-noout", "-hash", "-in", str(self.cert)], text=True).strip()
        (directory / (hashed + ".0")).write_bytes(self.cert.read_bytes())
        for flags, extra in ((["--cacert", str(other)], {}), ([], {"CURL_CA_BUNDLE": str(other)})):
            env = {"SSL_CERT_DIR": str(directory), **extra}
            result = self.run_cli([*flags, self.tls_url], environment=env)
            self.assertEqual(result.returncode, 60, result.stderr)
        for env in ({"SSL_CERT_DIR": str(directory)}, {"SSL_CERT_FILE": str(self.cert)}):
            result = self.run_cli([self.tls_url], environment=env)
            self.assertEqual(result.returncode, 0, result.stderr)

    @unittest.skipIf(CLI.endswith("chroot_cli.py"), "wrapper argv belongs to Python; direct bundle tests cover masking")
    @unittest.skipUnless(os.uname().sysname in ("Linux", "Darwin"), "shipped Unix targets")
    def test_audit_credentials_hidden_in_process_arguments(self):
        for flags in (["--user", "dummy:DUMMY_USER", "--proxy-user", "dummy:DUMMY_PROXY"],
                      ["--user=dummy:DUMMY_USER", "--proxy-user=dummy:DUMMY_PROXY"],
                      ["-udummy:DUMMY_USER", "-Udummy:DUMMY_PROXY"],
                      ["-su", "dummy:DUMMY_USER", "-sUdummy:DUMMY_PROXY"]):
            with self.subTest(flags=flags):
                self.server.credentials_seen.clear()
                self.server.credentials_release.clear()
                process = subprocess.Popen([CLI, "--noproxy", "", "--proxy", self.url, *flags,
                                            "http://credential.invalid/slow-credentials"],
                                           stdout=subprocess.PIPE, stderr=subprocess.PIPE)
                try:
                    self.assertTrue(self.server.credentials_seen.wait(3), "request did not reach delayed fixture")
                    self.assertIsNone(process.poll())
                    observed = subprocess.check_output(["ps", "-p", str(process.pid), "-o", "command="])
                    self.assertNotIn(b"DUMMY_USER", observed)
                    self.assertNotIn(b"DUMMY_PROXY", observed)
                finally:
                    self.server.credentials_release.set()
                    stdout, stderr = process.communicate(timeout=5)
                self.assertEqual(process.returncode, 0, stderr)
                credentials = json.loads(stdout)
                self.assertEqual(base64.b64decode(credentials["user"].split()[1]), b"dummy:DUMMY_USER")
                self.assertEqual(base64.b64decode(credentials["proxy"].split()[1]), b"dummy:DUMMY_PROXY")

    def test_get_binary_and_headers(self):
        self.compare([self.url + "/bytes"])
        self.compare(["-i", self.url + "/bytes"])
        self.compare(["-I", self.url + "/bytes"])
        self.compare(["-H", "X-Test: one", "-H", "X-Test: two", "-e", "https://httpbin.org/status/200", self.url + "/echo"])

    def test_referer_auto_redirects(self):
        for referer in (";auto", "https://httpbin.org/status/200;auto"):
            with self.subTest(referer=referer):
                result = self.compare(["-L", "-e", referer, self.url + "/redirect-post"])
                self.assertEqual(json.loads(result.stdout)["headers"]["referer"],
                                 [self.url + "/redirect-post"])
        # No redirect: strip the modifier, preserve an explicit initial URL.
        for referer, expected in (("", []), (";auto", []), ("https://httpbin.org/status/200;auto", ["https://httpbin.org/status/200"])):
            result = self.compare(["-e", referer, self.url + "/echo"])
            self.assertEqual(json.loads(result.stdout)["headers"]["referer"], expected)
        # Modern curl recognizes only the suffix; older system curl versions
        # also treat substrings such as ';automatic' as the modifier.
        literal = "https://httpbin.org/status/200;automatic"
        result = self.run_cli(["-e", literal, self.url + "/echo"])
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout)["headers"]["referer"], [literal])
        # Last value wins, including disabling a previously enabled auto mode.
        self.compare(["-L", "-e", ";auto", "-e", "https://httpbin.org/status/201", self.url + "/redirect-post"])
        # libcurl must remove credentials and fragments from generated Referer.
        credential_url = self.url.replace("http://", "http://audit:dummy@") + "/redirect-post#fragment"
        result = self.compare(["-L", "-e", ";auto", credential_url])
        self.assertEqual(json.loads(result.stdout)["headers"]["referer"], [self.url + "/redirect-post"])

    def test_request_data_and_method(self):
        self.compare(["-d", "a=1", "-d", "b=two", self.url + "/echo"])
        self.compare(["--data-raw", "@literal", "-XPATCH", self.url + "/echo"])
        self.compare(["-d", "", self.url + "/echo"])
        self.compare(["-G", "-d", "a=1", self.url + "/echo?x=2"])
        self.compare(["-G", "-d", "a=1", self.url + "/echo?"])
        self.compare(["--json", '{"x":1}', self.url + "/echo"])
        self.compare(["--json", '{}', "-H", "Content-Type: custom/test", "-H", "Accept: text/plain", self.url + "/echo"])

    def test_stdin_and_file_bodies_preserve_binary(self):
        self.compare(["--data-binary", "@-", self.url + "/echo"], data=BINARY)
        source = self.root / "body.bin"
        source.write_bytes(BINARY)
        self.compare(["--data-binary", "@" + str(source), self.url + "/echo"])
        # curl 7.88 (bookworm) handles embedded NULs differently from modern
        # curl. Assert the current documented --data behavior independently:
        # https://curl.se/docs/manpage.html#-d (strip CR, LF, and NUL from files).
        result = self.run_cli(["--data", "@" + str(source), self.url + "/echo"])
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(base64.b64decode(json.loads(result.stdout)["body"]), b"\xffhello\x80world")
        source.write_bytes(b"a=hello\r\n&b=world\n")
        self.compare(["--data", "@" + str(source), self.url + "/echo"])
        missing = self.run_cli(["--data-binary", "@" + str(self.root / "absent"), self.url + "/echo"])
        self.assertEqual(missing.returncode, 26)
        self.assertEqual(missing.stdout, b"")

    def test_redirects_and_credentials(self):
        self.compare(["-L", self.url + "/redirect"])
        self.compare(["-L", "-d", "value=1", self.url + "/redirect-post"])
        result = self.compare(["-L", "-u", "alice:secret", self.url + "/redirect-host"])
        self.assertEqual(json.loads(result.stdout)["headers"]["authorization"], [])
        self.compare(["-L", "--max-redirs", "0", self.url + "/redirect"])

    def test_http_errors_and_writeout(self):
        self.compare([self.url + "/missing"])
        self.compare(["-f", self.url + "/missing"])
        self.compare(["--fail-with-body", self.url + "/missing"])
        self.compare(["-L", "-w", r"\n%{http_code}|%{num_redirects}|%%\n", self.url + "/redirect"])
        self.compare(["-f", "-w", "%{http_code}|%{exitcode}", self.url + "/missing"])
        result = self.run_cli(["-s", "--no-show-error", "-f", self.url + "/missing"])
        self.assertEqual(result.returncode, 22)
        self.assertEqual(result.stderr, b"")

    def test_output_and_header_files(self):
        outputs = []
        for name, engine in [("ours", CLI), ("reference", CURL)]:
            body, headers = self.root / (name + ".bin"), self.root / (name + ".headers")
            result = self.run_cli(["-o", str(body), "-D", str(headers), "-w", "%{http_code}", self.url + "/bytes"], engine=engine)
            self.assertEqual(result.returncode, 0, result.stderr)
            outputs.append((body.read_bytes(), headers.read_bytes(), result.stdout))
        self.assertEqual(outputs[0], outputs[1])
        self.assertEqual(outputs[0][0], BINARY)

    def test_compression_timeout_and_proxy(self):
        self.assertEqual(self.compare(["--compressed", self.url + "/gzip"]).stdout, BINARY)
        self.compare(["--max-time", "0.025", self.url + "/slow"])
        result = self.compare(["--proxy", self.url, "--noproxy", "", "http://unresolved.invalid/proxy-check"])
        self.assertEqual(json.loads(result.stdout)["path"], "http://unresolved.invalid/proxy-check")

    def test_output_file_survives_errors_without_response_body(self):
        # A bound, unlistening socket cannot serve a response. macOS may report
        # a connection timeout instead of Linux's immediate refusal.
        with socket.socket() as closed:
            closed.bind(("127.0.0.1", 0))
            unreachable = f"http://127.0.0.1:{closed.getsockname()[1]}/"
            for args, codes in [(["--connect-timeout", "0.05", unreachable], (7, 28)), (["-f", self.url + "/missing"], (22,))]:
                for engine in (CLI, CURL):
                    output = self.root / "keep.bin"
                    output.write_bytes(b"KEEP")
                    result = self.run_cli(["-o", str(output), *args], engine=engine)
                    self.assertIn(result.returncode, codes, result.stderr)
                    self.assertEqual(output.read_bytes(), b"KEEP", (engine, args))
            output = self.root / "keep.bin"
            output.write_bytes(b"KEEP")
            result = self.run_cli(["-o", str(output), "--impersonate", "invalid-profile", self.url + "/bytes"])
            self.assertNotEqual(result.returncode, 0)
            self.assertEqual(output.read_bytes(), b"KEEP")
        for engine in (CLI, CURL):
            output = self.root / "empty.bin"
            output.write_bytes(b"REPLACE")
            result = self.run_cli(["-o", str(output), self.url + "/empty"], engine=engine)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(output.read_bytes(), b"")
        for endpoint in ("/bytes", "/empty"):
            result = self.compare(["-o", str(self.root / "missing-directory" / "out.bin"),
                                   "-w", "%{exitcode}", self.url + endpoint])
            self.assertEqual(result.returncode, 23, result.stderr)

    def test_cookies(self):
        self.compare(["-b", "a=1", "-b", "b=2", self.url + "/echo"])
        jar = self.root / "cookies.txt"
        result = self.run_cli(["-c", str(jar), self.url + "/set-cookie"])
        self.assertEqual(result.returncode, 0, result.stderr)
        result = self.compare(["-b", str(jar), self.url + "/echo"])
        self.assertIn("session=hello", json.loads(result.stdout)["headers"]["cookie"][0])

    def test_tls_verification_is_on_by_default(self):
        self.assertEqual(self.run_cli([self.tls_url + "/bytes"]).returncode, 60)
        self.assertEqual(self.run_cli(["--cacert", str(self.cert), self.tls_url + "/bytes"]).stdout, BINARY)
        self.assertEqual(self.run_cli(["-k", self.tls_url + "/bytes"]).stdout, BINARY)

    def test_profile_selection_and_header_override(self):
        result = self.run_cli(["--impersonate", "chrome150", "-H", "Accept: application/json", self.url + "/echo"])
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout)["headers"]["accept"], ["application/json"])
        invalid = self.run_cli(["--impersonate", "not-a-browser", self.url + "/bytes"])
        self.assertNotEqual(invalid.returncode, 0)
        self.assertEqual(invalid.stdout, b"")

    def profile_headers(self, args=(), environment=None):
        result = self.run_cli([*args, self.url + "/profile"], environment=environment)
        self.assertEqual(result.returncode, 0, result.stderr)
        return json.loads(result.stdout)

    def test_default_profile_is_chrome_and_preserves_response_bytes(self):
        headers = self.profile_headers()
        self.assertIn("Chrome/150.0.0.0", headers.get("user-agent", ""))
        self.assertIn('"Chromium";v="150"', headers.get("sec-ch-ua", ""))
        self.assertEqual(self.run_cli([self.url + "/bytes"]).stdout, BINARY)
        headers = self.profile_headers(["-H", "Accept: application/json", "-A", "custom-agent"])
        self.assertEqual(headers["accept"], "application/json")
        self.assertEqual(headers["user-agent"], "custom-agent")

    def test_positional_profile_applies_the_same_engine_settings(self):
        explicit = self.profile_headers(["--impersonate", "firefox147", "-H", "Accept: application/json"])
        for args in (["firefox147", "-sS", "-H", "Accept: application/json"],
                     ["-sS", "firefox147", "-H", "Accept: application/json"]):
            with self.subTest(args=args):
                self.assertEqual(self.profile_headers(args), explicit)
        self.assertIn("Firefox/147.0", explicit["user-agent"])
        headers = self.profile_headers(["firefox147", "--impersonate", "chrome150"])
        self.assertIn("Chrome/150.0.0.0", headers["user-agent"])

    def test_profile_decompression_defaults_and_overrides(self):
        cases = [
            ([], {}, True),
            (["--impersonate", "firefox147"], {}, True),
            (["--impersonate", "safari2601"], {}, True),
            ([], {"CURL_IMPERSONATE": "firefox147"}, True),
            ([], {"CURL_IMPERSONATE_HEADERS": "no"}, True),
            (["--impersonate", "chrome150:no"], {}, True),
            (["--no-compressed"], {}, False),
            (["--compressed"], {}, True),
            (["--compressed", "--no-compressed"], {}, False),
            (["--no-compressed", "--compressed"], {}, True),
            (["--no-impersonate"], {}, False),
            (["--no-impersonate", "--compressed"], {}, True),
            (["--compressed", "--no-impersonate"], {}, True),
            (["--no-impersonate", "--impersonate", "chrome150"], {}, True),
            (["--impersonate", "firefox147", "--no-impersonate"], {}, False),
            (["--no-compressed", "--impersonate", "firefox147"], {}, False),
            (["--no-impersonate"], {"CURL_IMPERSONATE": "invalid-profile"}, False),
        ]
        for encoding, decompress in [("gzip", gzip.decompress), ("deflate", zlib.decompress)]:
            for flags, environment, decoded in cases:
                with self.subTest(encoding=encoding, flags=flags, environment=environment):
                    result = self.run_cli([*flags, self.url + "/" + encoding], environment=environment)
                    self.assertEqual(result.returncode, 0, result.stderr)
                    self.assertEqual(result.stdout if decoded else decompress(result.stdout), BINARY)

    def test_decompression_preserves_profile_and_custom_encoding_headers(self):
        for profile in ("chrome150", "firefox147", "safari2601"):
            for custom in ([], ["-H", "Accept-Encoding: gzip"], ["-H", "Accept-Encoding:"]):
                with self.subTest(profile=profile, custom=custom):
                    flags = ["--impersonate", profile, *custom]
                    raw = self.run_cli([*flags, "--no-compressed", self.url + "/profile-headers"])
                    decoded = self.run_cli([*flags, self.url + "/profile-headers"])
                    self.assertEqual(raw.returncode, 0, raw.stderr)
                    self.assertEqual(decoded.returncode, 0, decoded.stderr)
                    self.assertEqual(json.loads(decoded.stdout), json.loads(raw.stdout))
        result = self.run_cli(["-H", "Accept-Encoding: gzip", self.url + "/gzip"])
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout, BINARY)

    def test_default_decompression_writes_binary_body_and_original_headers(self):
        output = self.root / "decoded.bin"
        headers = self.root / "encoded-headers.txt"
        result = self.run_cli(["-o", str(output), "-D", str(headers),
                               "-w", "%{http_code}", self.url + "/gzip"])
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout, b"200")
        self.assertEqual(output.read_bytes(), BINARY)
        self.assertIn("Content-Encoding: gzip", headers.read_text())
        plain = self.run_cli([self.url + "/bytes"])
        self.assertEqual(plain.returncode, 0, plain.stderr)
        self.assertEqual(plain.stdout, BINARY)

    def test_profile_flags_override_environment_and_last_selection_wins(self):
        for environment in [{"CURL_IMPERSONATE": "firefox147"}, {"CURL_IMPERSONATE": "invalid-profile"}]:
            with self.subTest(environment=environment):
                headers = self.profile_headers(["--impersonate", "chrome150"], environment)
                self.assertIn("Chrome/150.0.0.0", headers.get("user-agent", ""))
                headers = self.profile_headers(["--impersonate", "chrome150", "--no-impersonate"], environment)
                self.assertTrue(headers.get("user-agent", "").startswith("curl/"))
                self.assertEqual(headers.get("accept"), "*/*")
                self.assertNotIn("sec-ch-ua", headers)
        headers = self.profile_headers(["--no-impersonate", "--impersonate", "firefox147"])
        self.assertIn("Firefox/147.0", headers.get("user-agent", ""))
        self.assertNotIn("sec-ch-ua", headers)

    def test_environment_profile_and_header_selection(self):
        headers = self.profile_headers(environment={"CURL_IMPERSONATE": "firefox147"})
        self.assertIn("Firefox/147.0", headers.get("user-agent", ""))
        for environment in [{"CURL_IMPERSONATE_HEADERS": "no"},
                            {"CURL_IMPERSONATE": "chrome150", "CURL_IMPERSONATE_HEADERS": "no"}]:
            with self.subTest(environment=environment):
                headers = self.profile_headers(environment=environment)
                self.assertNotIn("sec-ch-ua", headers)
                self.assertNotIn("user-agent", headers)
                headers = self.profile_headers(["--impersonate", "chrome150:yes"], environment)
                self.assertIn("Chrome/150.0.0.0", headers.get("user-agent", ""))
        headers = self.profile_headers(["--impersonate", "chrome150:no"])
        self.assertNotIn("sec-ch-ua", headers)

    def test_invalid_selected_profile_fails_without_a_request(self):
        for environment in [{"CURL_IMPERSONATE": "invalid-profile"}, {"CURL_IMPERSONATE": ""}]:
            with self.subTest(environment=environment):
                result = self.run_cli([self.url + "/profile"], environment=environment)
                self.assertNotEqual(result.returncode, 0)
                self.assertEqual(result.stdout, b"")
        result = self.run_cli(["--impersonate", "invalid-profile", self.url + "/profile"],
                              environment={"CURL_IMPERSONATE": "chrome150"})
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(result.stdout, b"")

    def test_profile_listing_ignores_request_environment(self):
        result = self.run_cli(["--list-profiles"], environment={"CURL_IMPERSONATE": "invalid-profile"})
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn(b"chrome150\n", result.stdout)

    def test_catalog_matches_the_native_engine(self):
        result = self.run_cli(["--list-profiles"])
        self.assertEqual(result.returncode, 0, result.stderr)
        profiles = result.stdout.decode().splitlines()
        self.assertIn("chrome150", profiles)
        self.assertIn("firefox147", profiles)
        self.assertIn("safari2601", profiles)
        self.assertEqual(len(profiles), len(set(profiles)))

    def test_http2_profile_on_local_tls_server(self):
        server = shutil.which("nghttpd")
        if not server:
            if os.environ.get("REQUIRE_HTTP2") == "1":
                self.fail("nghttpd is required for the Docker validation target")
            self.skipTest("nghttpd is not installed on this host; mandatory in Docker")
        (self.root / "resource.bin").write_bytes(BINARY)
        with socket.socket() as probe:
            probe.bind(("127.0.0.1", 0))
            port = probe.getsockname()[1]
        with tempfile.TemporaryFile() as log:
            process = subprocess.Popen([server, "-v", "--echo-upload", "-a", "127.0.0.1", "-d", str(self.root), str(port), str(self.root / "key.pem"), str(self.cert)], stdout=log, stderr=log)
            try:
                deadline = time.monotonic() + 5
                while True:
                    self.assertIsNone(process.poll(), "nghttpd exited before listening")
                    try:
                        with socket.create_connection(("127.0.0.1", port), timeout=0.1):
                            break
                    except OSError:
                        if time.monotonic() >= deadline:
                            self.fail("nghttpd did not start")
                        time.sleep(0.02)
                catalog = self.run_cli(["--list-profiles"])
                self.assertEqual(catalog.returncode, 0, catalog.stderr)
                # A native engine update must keep every profile functional
                # through TLS and HTTP/2, including sending request bodies.
                # This is not a comparison against real-browser fingerprints.
                for profile in catalog.stdout.decode().splitlines():
                    for upload in (False, True):
                        with self.subTest(profile=profile, upload=upload):
                            args = ["--impersonate", profile, "--cacert", str(self.cert), "--http2", "-w", "%{http_version}"]
                            if upload:
                                args += ["--data-binary", "@-"]
                            result = self.run_cli([*args, f"https://127.0.0.1:{port}/resource.bin"], data=BINARY if upload else None)
                            self.assertEqual(result.returncode, 0, result.stderr)
                            self.assertEqual(result.stdout, BINARY + b"2")
            finally:
                process.terminate()
                process.wait(timeout=5)
            log.seek(0)
            observed = log.read().decode(errors="replace")
            self.assertIn("Chrome/150.0.0.0", observed)

    def test_unsupported_options_and_formats_are_explicit(self):
        for args in [["--retry", "2"], ["--next"], ["-w", "%{not_supported}"], ["-w", "%{http_code"], ["--config", "missing"], ["-I", "-d", "body"]]:
            result = self.run_cli([*args, self.url + "/bytes"])
            self.assertEqual(result.returncode, 2, (args, result.stderr))
            self.assertEqual(result.stdout, b"")


class CookiePolicy(unittest.TestCase):
    def test_public_suffix_cookies_are_rejected_and_valid_domains_work(self):
        class Proxy(http.server.BaseHTTPRequestHandler):
            protocol_version = "HTTP/1.1"

            def log_message(self, *_):
                pass

            def do_GET(self):
                initial = urlsplit(self.path).path == "/start"
                payload = json.dumps({"cookie": self.headers.get("Cookie")}).encode()
                self.send_response(302 if initial else 200)
                if initial:
                    self.send_header("Set-Cookie", f"audit=dummy; Domain={self.server.cookie_domain}; Path=/")
                    self.send_header("Location", f"http://{self.server.target}/end")
                self.send_header("Content-Length", str(len(payload)))
                self.send_header("Connection", "close")
                self.end_headers()
                self.wfile.write(payload)

        server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Proxy)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        self.addCleanup(server.server_close)
        self.addCleanup(server.shutdown)
        # All named hosts are handled by this local proxy, never resolved or contacted.
        cases = [
            ("shop.example.co.uk", "api.other.co.uk", "co.uk", None),
            ("alice.github.io", "bob.github.io", "github.io", None),
            ("a.example.xn--55qx5d.cn", "b.other.xn--55qx5d.cn", "xn--55qx5d.cn", None),
            ("a.example.co.uk", "b.example.co.uk", "example.co.uk", "audit=dummy"),
            ("a.city.kawasaki.jp", "b.city.kawasaki.jp", "city.kawasaki.jp", "audit=dummy"),
        ]
        for profile in (["--no-impersonate"], ["--impersonate", "chrome150"]):
            for source, target, domain, expected in cases:
                with self.subTest(profile=profile, domain=domain):
                    server.cookie_domain, server.target = domain, target
                    result = Compatibility.run_cli(self, [*profile, "-b", "", "-L", "--noproxy", "",
                        "--proxy", f"http://127.0.0.1:{server.server_port}", "--max-time", "3",
                        f"http://{source}/start"])
                    self.assertEqual(result.returncode, 0, result.stderr)
                    self.assertEqual(json.loads(result.stdout)["cookie"], expected)


if __name__ == "__main__":
    unittest.main(verbosity=2)
