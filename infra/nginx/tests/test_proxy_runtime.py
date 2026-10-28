"""Opt-in real Nginx smoke test: set NGINX_TEST_BINARY to a reviewed binary."""
from datetime import datetime, timedelta, timezone
from contextlib import ExitStack
import http.client
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import socket
import ssl
import subprocess
import tempfile
from threading import Event, Thread
import time
import unittest

from test_render_config import renderer


@unittest.skipUnless(os.environ.get('NGINX_TEST_BINARY'), 'Nginx binary not configured')
class ProxyRuntimeTests(unittest.TestCase):
    def test_real_https_routes_headers_and_body_limit(self):
        from cryptography import x509
        from cryptography.hazmat.primitives import hashes, serialization
        from cryptography.hazmat.primitives.asymmetric import rsa
        from cryptography.x509.oid import NameOID

        received = []
        upload_started = Event()

        class Backend(BaseHTTPRequestHandler):
            def do_POST(self):
                upload_started.set()
                self.rfile.read(int(self.headers['Content-Length']))
                self.do_GET()

            def do_GET(self):
                received.append((self.path, dict(self.headers)))
                self.send_response(200)
                self.send_header('Content-Type', 'audio/wav' if self.path.endswith('/audio') else 'application/json')
                self.send_header('Cache-Control', 'public, max-age=3600')
                self.end_headers()
                self.wfile.write(b'fixture')

            def log_message(self, *args):
                pass

        binary = str(Path(os.environ['NGINX_TEST_BINARY']).resolve())
        with tempfile.TemporaryDirectory(prefix='nginx-smoke-') as temporary:
            root = Path(temporary)
            (root / 'html').mkdir()
            (root / 'html' / 'index.html').write_text('SPA fixture', encoding='utf-8')
            (root / 'html' / 'assets').mkdir()
            (root / 'html' / 'assets' / 'index-f1a2b3c4.js').write_text('fixture', encoding='utf-8')
            (root / 'body').mkdir()
            (root / 'logs').mkdir()
            (root / 'mime.types').write_text('types { text/html html; }', encoding='utf-8')
            key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
            name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, 'app.example.test')])
            now = datetime.now(timezone.utc)
            cert = (x509.CertificateBuilder().subject_name(name).issuer_name(name)
                    .public_key(key.public_key()).serial_number(x509.random_serial_number())
                    .not_valid_before(now - timedelta(minutes=1)).not_valid_after(now + timedelta(hours=1))
                    .add_extension(x509.SubjectAlternativeName([x509.DNSName('app.example.test')]), False)
                    .add_extension(x509.BasicConstraints(ca=True, path_length=None), True)
                    .sign(key, hashes.SHA256()))
            (root / 'cert.pem').write_bytes(cert.public_bytes(serialization.Encoding.PEM))
            (root / 'key.pem').write_bytes(key.private_bytes(serialization.Encoding.PEM,
                                            serialization.PrivateFormat.PKCS8, serialization.NoEncryption()))
            context = ssl.create_default_context(cafile=str(root / 'cert.pem'))
            context.minimum_version = ssl.TLSVersion.TLSv1_2
            with ExitStack() as stack:
                backend = stack.enter_context(ThreadingHTTPServer(('127.0.0.1', 0), Backend))
                thread = Thread(target=backend.serve_forever, daemon=True)
                thread.start()
                stack.callback(backend.shutdown)
                with socket.socket() as allocation:
                    allocation.bind(('127.0.0.1', 0))
                    port = allocation.getsockname()[1]
                config = renderer.render('app.example.test')
                replacements = {
                    'worker_processes auto;': 'worker_processes 1;',
                    'listen 443 ssl': f'listen 127.0.0.1:{port} ssl',
                    '/run/nginx/nginx.pid': (root / 'nginx.pid').as_posix(),
                    '/run/nginx/client-body': (root / 'body').as_posix(),
                    '/run/nginx': root.as_posix(),
                    '/etc/nginx/mime.types': (root / 'mime.types').as_posix(),
                    '/usr/share/nginx/html': (root / 'html').as_posix(),
                    '/run/secrets/tls-fullchain.pem': (root / 'cert.pem').as_posix(),
                    '/run/secrets/tls-key.pem': (root / 'key.pem').as_posix(),
                    '/dev/null': (root / 'error.log').as_posix(),
                    '/dev/stdout': (root / 'access.log').as_posix(),
                    'backend:8000': f'127.0.0.1:{backend.server_port}',
                }
                for source, target in replacements.items():
                    config = config.replace(source, target)
                config_path = root / 'nginx.conf'
                config_path.write_text(config, encoding='utf-8')
                flags = subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0
                command = [binary, '-p', root.as_posix() + '/', '-c', config_path.as_posix()]
                syntax = subprocess.run(command + ['-t'], capture_output=True, creationflags=flags)
                self.assertEqual(syntax.returncode, 0, syntax.stderr.decode(errors='replace'))
                with (root / 'process.log').open('wb') as log:
                    process = subprocess.Popen(command + ['-g', 'daemon off;'], stdout=log,
                                               stderr=log, creationflags=flags)
                    try:
                        deadline = time.monotonic() + 5
                        while True:
                            try:
                                with socket.create_connection(('127.0.0.1', port), timeout=.2):
                                    break
                            except OSError:
                                if process.poll() is not None or time.monotonic() > deadline:
                                    self.fail('Nginx did not start')
                                time.sleep(.05)

                        def request(path, host='app.example.test', method='GET', headers=None, body=None):
                            connection = http.client.HTTPConnection('127.0.0.1', port, timeout=5)
                            connection.sock = context.wrap_socket(
                                socket.create_connection(('127.0.0.1', port), timeout=5),
                                server_hostname='app.example.test')
                            try:
                                connection.request(method, path, body=body, headers={'Host': host, **(headers or {})})
                                response = connection.getresponse()
                                return response.status, dict(response.getheaders()), response.read()
                            finally:
                                connection.close()

                        status, headers, body = request('/profile/edit')
                        self.assertEqual((status, body), (200, b'SPA fixture'))
                        self.assertEqual(headers['Cache-Control'], 'no-store')

                        def assert_security_headers(headers):
                            self.assertEqual(headers['Strict-Transport-Security'], 'max-age=31536000')
                            self.assertEqual(headers['X-Content-Type-Options'], 'nosniff')
                            self.assertEqual(headers['Referrer-Policy'], 'no-referrer')
                            self.assertEqual(headers['X-Frame-Options'], 'DENY')
                            self.assertIn("script-src 'self'", headers['Content-Security-Policy-Report-Only'])

                        assert_security_headers(headers)
                        status, headers, body = request('/assets/index-f1a2b3c4.js')
                        self.assertEqual((status, body), (200, b'fixture'))
                        self.assertEqual(headers['Cache-Control'], 'public, max-age=31536000, immutable')
                        assert_security_headers(headers)
                        status, headers, body = request('/assets/missing.js')
                        self.assertEqual(status, 404)
                        self.assertEqual(headers['Cache-Control'], 'no-store')
                        assert_security_headers(headers)
                        path = '/api/v1/auth/kakao/callback?code=synthetic&state=synthetic'
                        status, headers, body = request(path, headers={
                            'X-Forwarded-For': 'spoofed', 'Forwarded': 'spoofed', 'X-Request-ID': 'spoofed',
                            'Cookie': 'session=synthetic', 'Authorization': 'Bearer synthetic'})
                        self.assertEqual((status, body), (200, b'fixture'))
                        self.assertEqual(headers['Cache-Control'], 'no-store')
                        self.assertEqual(received[-1][0], path)
                        forwarded = {key.lower(): value for key, value in received[-1][1].items()}
                        self.assertEqual(forwarded['x-forwarded-for'], '127.0.0.1')
                        self.assertEqual(forwarded['x-forwarded-proto'], 'https')
                        self.assertNotIn('forwarded', forwarded)
                        self.assertNotIn('x-request-id', forwarded)
                        self.assertEqual(request('/api/v1/audio')[1]['Content-Type'], 'audio/wav')
                        self.assertEqual(request('/api/preserve?value=synthetic')[0], 200)
                        self.assertEqual(received[-1][0], '/api/preserve?value=synthetic')
                        self.assertEqual(request('/api/v1/messages', method='POST', body=b'x' * (64 * 1024))[0], 200)
                        upload_started.clear()
                        self.assertEqual(request('/.env')[0], 404)
                        upload_path = '/api/v1/journeys/00000000-0000-4000-8000-000000000001/transcriptions'
                        before = len(received)
                        # JSON and lookalike paths must not inherit the recording limit.
                        for route in ('/api/v1/messages', upload_path + '/other'):
                            self.assertEqual(request(route, method='POST', headers={
                                'Content-Length': str(64 * 1024 + 1), 'Expect': '100-continue'})[0], 413)
                        self.assertEqual(request(upload_path, method='POST', headers={
                            'Content-Length': str(7 * 1024 * 1024 + 1), 'Expect': '100-continue'})[0], 413)
                        self.assertEqual(len(received), before)
                        # Slow client: no backend request until the entire >1 MiB body is buffered.
                        with context.wrap_socket(socket.create_connection(('127.0.0.1', port), timeout=5),
                                                 server_hostname='app.example.test') as slow:
                            payload = b'x' * (7 * 1024 * 1024)
                            slow.sendall((f'POST {upload_path} HTTP/1.1\r\nHost: app.example.test\r\n'
                                          f'Content-Length: {len(payload)}\r\nConnection: close\r\n\r\n').encode())
                            slow.sendall(payload[:1024])
                            self.assertFalse(upload_started.wait(.3), 'Incomplete upload reached backend')
                            slow.sendall(payload[1024:])
                            response = http.client.HTTPResponse(slow)
                            response.begin()
                            self.assertEqual((response.status, response.read()), (200, b'fixture'))
                        self.assertTrue(upload_started.is_set())
                        self.assertEqual(received[-1][0], upload_path)
                        upload_headers = {key.lower(): value for key, value in received[-1][1].items()}
                        self.assertEqual(upload_headers['x-forwarded-proto'], 'https')
                        self.assertEqual(upload_headers['host'], 'app.example.test')
                        self.assertEqual(upload_headers['x-forwarded-for'], '127.0.0.1')
                        modern = ssl.create_default_context(cafile=str(root / 'cert.pem'))
                        modern.minimum_version = ssl.TLSVersion.TLSv1_2
                        modern.maximum_version = ssl.TLSVersion.TLSv1_2
                        modern.set_ciphers('ECDHE-RSA-AES128-GCM-SHA256')
                        with modern.wrap_socket(socket.create_connection(('127.0.0.1', port), timeout=5),
                                                server_hostname='app.example.test') as connection:
                            self.assertEqual(connection.cipher()[0], 'ECDHE-RSA-AES128-GCM-SHA256')
                        # SEC-04: TLS 1.2 with RSA key exchange/CBC must not negotiate.
                        legacy = ssl.create_default_context(cafile=str(root / 'cert.pem'))
                        legacy.minimum_version = ssl.TLSVersion.TLSv1_2
                        legacy.maximum_version = ssl.TLSVersion.TLSv1_2
                        legacy.set_ciphers('AES128-SHA')
                        with socket.create_connection(('127.0.0.1', port), timeout=5) as raw:
                            with self.assertRaises(ssl.SSLError):
                                legacy.wrap_socket(raw, server_hostname='app.example.test')
                        before = len(received)
                        try:
                            rejected = request('/api/v1/host-check', host='wrong.example.test')
                        except http.client.RemoteDisconnected:
                            pass  # Nginx 444 closes the connection without an HTTP response.
                        else:
                            self.assertEqual(rejected[0], 421)
                        self.assertEqual(len(received), before)
                        with socket.create_connection(('127.0.0.1', port), timeout=5) as raw:
                            with self.assertRaises(ssl.SSLError):
                                context.wrap_socket(raw, server_hostname='wrong.example.test')
                    finally:
                        subprocess.run(command + ['-s', 'quit'], capture_output=True, creationflags=flags)
                        try:
                            process.wait(timeout=10)
                        except subprocess.TimeoutExpired:
                            if os.name == 'nt':
                                subprocess.run(['taskkill', '/PID', str(process.pid), '/T', '/F'],
                                               capture_output=True, creationflags=flags)
                            else:
                                process.kill()
                            process.wait(timeout=5)
                self.assertNotIn('synthetic', (root / 'error.log').read_text(encoding='utf-8'))
                access = (root / 'access.log').read_text(encoding='utf-8')
                for private in ('synthetic', 'spoofed', '127.0.0.1', upload_path, '/profile/edit', 'callback'):
                    self.assertNotIn(private, access)
                records = [json.loads(line) for line in access.splitlines()]
                self.assertTrue({200, 404, 413, 444} <= {record['status'] for record in records})
                self.assertTrue(all(set(record) == {'route', 'status', 'bytes', 'duration'} for record in records))
                self.assertTrue(all(record['route'] in {'page', 'api', 'asset'} for record in records))
                # The callback is the only successful backend request omitted from access logs.
                self.assertEqual(sum(record['route'] == 'api' and record['status'] == 200 for record in records),
                                 len(received) - 1)
