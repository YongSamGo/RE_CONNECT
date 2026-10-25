"""Opt-in real Nginx smoke test: set NGINX_TEST_BINARY to a reviewed binary."""
from datetime import datetime, timedelta, timezone
from contextlib import ExitStack
import http.client
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import os
from pathlib import Path
import socket
import ssl
import subprocess
import tempfile
from threading import Thread
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

        class Backend(BaseHTTPRequestHandler):
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

                        def request(path, host='app.example.test', method='GET', headers=None):
                            connection = http.client.HTTPConnection('127.0.0.1', port, timeout=5)
                            connection.sock = context.wrap_socket(
                                socket.create_connection(('127.0.0.1', port), timeout=5),
                                server_hostname='app.example.test')
                            try:
                                connection.request(method, path, headers={'Host': host, **(headers or {})})
                                response = connection.getresponse()
                                return response.status, dict(response.getheaders()), response.read()
                            finally:
                                connection.close()

                        status, headers, body = request('/profile/edit')
                        self.assertEqual((status, body), (200, b'SPA fixture'))
                        self.assertEqual(headers['Cache-Control'], 'no-store')
                        path = '/api/v1/auth/kakao/callback?code=synthetic&state=synthetic'
                        status, headers, body = request(path, headers={
                            'X-Forwarded-For': 'spoofed', 'Forwarded': 'spoofed', 'X-Request-ID': 'spoofed'})
                        self.assertEqual((status, body), (200, b'fixture'))
                        self.assertEqual(headers['Cache-Control'], 'no-store')
                        self.assertEqual(received[-1][0], path)
                        forwarded = {key.lower(): value for key, value in received[-1][1].items()}
                        self.assertEqual(forwarded['x-forwarded-for'], '127.0.0.1')
                        self.assertEqual(forwarded['x-forwarded-proto'], 'https')
                        self.assertNotIn('forwarded', forwarded)
                        self.assertNotIn('x-request-id', forwarded)
                        self.assertEqual(request('/api/v1/audio')[1]['Content-Type'], 'audio/wav')
                        self.assertEqual(request('/assets/missing.js')[0], 404)
                        self.assertEqual(request('/.env')[0], 404)
                        self.assertEqual(request('/api/v1/upload', method='POST', headers={
                            'Content-Length': str(8 * 1024 * 1024), 'Expect': '100-continue'})[0], 413)
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
                self.assertFalse((root / 'logs' / 'access.log').exists())
