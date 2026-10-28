"""Real loopback TLS handshakes: 중요정보 평문 전송 / 인증서 검증 경계."""
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
import importlib.util
from pathlib import Path
import socket
import ssl
import struct
import tempfile
import unittest
from unittest.mock import patch

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import NameOID

spec = importlib.util.spec_from_file_location(
    'database_tls', Path(__file__).resolve().parents[1] / 'check_database_tls.py')
probe = importlib.util.module_from_spec(spec)
spec.loader.exec_module(probe)


def certificate(directory, label, hostname):
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, hostname)])
    now = datetime.now(timezone.utc)
    cert = (x509.CertificateBuilder().subject_name(name).issuer_name(name)
            .public_key(key.public_key()).serial_number(x509.random_serial_number())
            .not_valid_before(now - timedelta(minutes=1))
            .not_valid_after(now + timedelta(hours=1))
            .add_extension(x509.SubjectAlternativeName([x509.DNSName(hostname)]), critical=False)
            .add_extension(x509.BasicConstraints(ca=True, path_length=None), critical=True)
            .sign(key, hashes.SHA256()))
    cert_path, key_path = directory / f'{label}.pem', directory / f'{label}.key'
    cert_path.write_bytes(cert.public_bytes(serialization.Encoding.PEM))
    key_path.write_bytes(key.private_bytes(serialization.Encoding.PEM,
                                         serialization.PrivateFormat.PKCS8,
                                         serialization.NoEncryption()))
    return cert_path, key_path


@contextmanager
def postgres_tls(cert, key, accept_tls=True):
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    context.load_cert_chain(cert, key)
    with socket.socket() as listener, ThreadPoolExecutor(max_workers=1) as executor:
        listener.bind(('127.0.0.1', 0))
        listener.listen(1)
        listener.settimeout(5)

        def serve():
            connection, _ = listener.accept()
            with connection:
                connection.settimeout(5)
                data = b''
                while len(data) < 8:
                    part = connection.recv(8 - len(data))
                    if not part:
                        raise AssertionError('incomplete SSLRequest')
                    data += part
                if data != struct.pack('!II', 8, 80877103):
                    raise AssertionError('unexpected PostgreSQL SSLRequest')
                connection.sendall(b'S' if accept_tls else b'N')
                if accept_tls:
                    try:
                        with context.wrap_socket(connection, server_side=True) as secured:
                            # Probe must close without sending database authentication.
                            assert secured.recv(1) == b''
                    except (ssl.SSLError, ConnectionResetError, ConnectionAbortedError, BrokenPipeError):
                        # TLS alerts, reset/abort, or a broken pipe may follow the
                        # probe's immediate close (including TLS 1.3 ticket writes).
                        # Certificate/hostname failures still propagate at the client.
                        pass

        future = executor.submit(serve)
        try:
            yield listener.getsockname()[1]
        finally:
            future.result(timeout=6)


class DatabaseTlsTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.cert, self.key = certificate(Path(self.directory.name), 'server', 'localhost')

    def test_trusted_certificate_and_hostname(self):
        with postgres_tls(self.cert, self.key) as port:
            self.assertIn(probe.verify_tls('localhost', self.cert, port), ('TLSv1.2', 'TLSv1.3'))

    def test_untrusted_ca_rejected(self):
        other, _ = certificate(Path(self.directory.name), 'other', 'localhost')
        with postgres_tls(self.cert, self.key) as port:
            with self.assertRaises(ssl.SSLCertVerificationError):
                probe.verify_tls('localhost', other, port)

    def test_wrong_hostname_rejected(self):
        cert, key = certificate(Path(self.directory.name), 'wrong', 'wrong.example.test')
        with postgres_tls(cert, key) as port:
            with self.assertRaises(ssl.SSLCertVerificationError):
                probe.verify_tls('localhost', cert, port)

    def test_plaintext_server_rejected(self):
        with postgres_tls(self.cert, self.key, accept_tls=False) as port:
            with self.assertRaises(ValueError):
                probe.verify_tls('localhost', self.cert, port)

    def test_ip_and_invalid_host_rejected_before_connection(self):
        with patch.object(probe.socket, 'create_connection') as connect:
            for host in ('127.0.0.1', '::1', '', ' localhost', 'a\n', '/tmp/database'):
                with self.subTest(host=host), self.assertRaises(ValueError):
                    probe.verify_tls(host, self.cert)
            connect.assert_not_called()
