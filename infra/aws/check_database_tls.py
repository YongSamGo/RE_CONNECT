"""Verify the PostgreSQL TLS handshake before sending any authentication data.

No database credentials are accepted. TLS negotiation alone does not prove SQL
authentication, grants, migration success, or denial of plaintext connections.
"""
import argparse
import ipaddress
from pathlib import Path
import socket
import ssl
import struct


def verify_tls(host: str, ca_file: Path, port: int = 5432) -> str:
    if not host or host != host.strip() or any(c in host for c in '/\\\x00\r\n'):
        raise ValueError('a DNS hostname is required')
    try:
        ipaddress.ip_address(host)
    except ValueError:
        pass
    else:
        raise ValueError('use the DNS endpoint, not an IP address')
    if not 1 <= port <= 65535:
        raise ValueError('invalid port')
    # Use only the supplied CA bundle, not additional platform trust stores.
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    context.minimum_version = ssl.TLSVersion.TLSv1_2
    context.load_verify_locations(cafile=str(ca_file))
    with socket.create_connection((host, port), timeout=5) as connection:
        connection.sendall(struct.pack('!II', 8, 80877103))
        if connection.recv(1) != b'S':
            raise ValueError('server refused PostgreSQL TLS negotiation')
        with context.wrap_socket(connection, server_hostname=host) as secured:
            version = secured.version()
            if version not in ('TLSv1.2', 'TLSv1.3'):
                raise ValueError('unexpected TLS version')
            return version


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--host', required=True)
    parser.add_argument('--ca-file', type=Path, required=True)
    parser.add_argument('--port', type=int, default=5432)
    args = parser.parse_args()
    try:
        version = verify_tls(args.host, args.ca_file, args.port)
    except (OSError, ValueError):
        # Avoid disclosing connection targets, certificate details or local paths.
        print('PostgreSQL TLS verification failed.')
        return 1
    print(f'PostgreSQL TLS verified ({version}); authentication not tested.')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
