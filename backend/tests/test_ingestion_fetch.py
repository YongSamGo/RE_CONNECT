"""고정 대상·DNS 재바인딩·TLS·XXE·크기·수명 경계. 실제 키/공고를 쓰지 않는다."""

import asyncio
import ipaddress
import socket
import ssl

import httpcore
from pydantic import SecretStr, ValidationError
import pytest

from app.modules.ingestion import fetch as collector


VALID = ("<response><header><resultCode>00</resultCode></header><body><items>"
         "<item><jobId>fixture-1</jobId><title>가상 시험 공고</title></item>"
         "</items><totalCount>1</totalCount></body></response>").encode()
EMPTY = b"<response><header><resultCode>0</resultCode></header><body><items/><totalCount>0</totalCount></body></response>"


def wire(body=VALID, status=200, headers=None):
    headers = headers if headers is not None else [("Content-Type", "application/xml"), ("Content-Length", str(len(body)))]
    return [f"HTTP/1.1 {status} fixture\r\n".encode()
            + b"".join(f"{k}: {v}\r\n".encode() for k, v in headers) + b"\r\n", body]


class ObservedStream(httpcore.AsyncMockStream):
    def __init__(self, buffers):
        super().__init__(buffers)
        self.tls_host = None
        self.writes = []
        self.closed = False

    async def start_tls(self, ssl_context, server_hostname=None, timeout=None):
        assert ssl_context.verify_mode == ssl.CERT_REQUIRED
        assert ssl_context.check_hostname is True
        self.tls_host = server_hostname
        return self

    async def write(self, buffer, timeout=None):
        self.writes.append(buffer)

    async def aclose(self):
        self.closed = True


@pytest.fixture
def network(monkeypatch):
    class Backend:
        stream = ObservedStream(wire())
        calls = []

        async def connect_tcp(self, host, port, **kwargs):
            self.calls.append((host, port))
            return self.stream

    backend = Backend()
    monkeypatch.setattr(httpcore, "AnyIOBackend", lambda: backend)
    return backend


def run_fetch(monkeypatch, network, request=None, addresses=("8.8.8.8",)):
    calls = []

    async def main():
        async def resolve(host, port, **kwargs):
            calls.append((host, port))
            return [(socket.AF_INET if ipaddress.ip_address(a).version == 4 else socket.AF_INET6,
                     socket.SOCK_STREAM, 6, "", (a, port)) for a in addresses]
        monkeypatch.setattr(asyncio.get_running_loop(), "getaddrinfo", resolve)
        return await collector.fetch(request or collector.FetchRequest(operation="senuri_list"), SecretStr("fixture"))

    return asyncio.run(main()), calls


def test_success_pins_numeric_ip_but_preserves_tls_and_host(monkeypatch, network):
    monkeypatch.setenv("HTTPS_PROXY", "http://127.0.0.1:1")
    result, dns = run_fetch(monkeypatch, network)
    assert result.status == collector.FetchStatus.OK
    assert result.document.item_count == result.document.total_count == 1
    assert network.calls == [("8.8.8.8", 443)]
    assert dns == [(collector.HOST, 443)]
    assert network.stream.tls_host == collector.HOST
    request = b"".join(network.stream.writes)
    assert b"Host: apis.data.go.kr\r\n" in request
    assert b"/B552474/SenuriService/getJobList?" in request
    assert b"Accept-Encoding: identity" in request
    assert network.stream.closed
    assert "fixture-1" not in repr(result) + repr(result.document)


@pytest.mark.parametrize("operation,identifier,path,param", [
    ("senuri_detail", "K-fixture", b"/B552474/SenuriService/getJobInfo?", b"id=K-fixture"),
    ("volunteer_list", None, b"/1741000/volunteerPartcptnService/getVltrSearchWordList?", b"pageNo=1"),
    ("volunteer_detail", "123", b"/1741000/volunteerPartcptnService/getVltrPartcptnItem?", b"progrmRegistNo=123"),
])
def test_fixed_operations(monkeypatch, network, operation, identifier, path, param):
    result, _ = run_fetch(monkeypatch, network, collector.FetchRequest(operation=operation, external_id=identifier))
    assert result.status == collector.FetchStatus.OK
    written = b"".join(network.stream.writes)
    assert path in written and param in written


@pytest.mark.parametrize("kwargs", [
    {"operation": "https://attacker.invalid"}, {"url": "http://127.0.0.1"},
    {"operation": "senuri_detail"}, {"external_id": "fixture"},
    {"operation": "senuri_detail", "external_id": "../private"},
    {"operation": "senuri_detail", "external_id": "fixture\n"},
    {"page_no": True}, {"page_no": 0}, {"num_rows": 101},
])
def test_request_cannot_supply_url_or_unbounded_parameters(kwargs):
    with pytest.raises(ValidationError):
        collector.FetchRequest(**({"operation": "senuri_list"} | kwargs))


@pytest.mark.parametrize("address", [
    "127.0.0.1", "10.0.0.1", "169.254.169.254", "192.168.0.1", "0.0.0.0", "224.0.0.1",
    "::1", "fc00::1", "fe80::1", "::ffff:127.0.0.1", "2002:7f00:1::", "64:ff9b::a9fe:a9fe",
])
def test_private_and_transition_dns_answers_never_connect(monkeypatch, network, address):
    result, _ = run_fetch(monkeypatch, network, addresses=(address,))
    assert result.status == collector.FetchStatus.BLOCKED_DESTINATION
    assert network.calls == []


def test_mixed_public_private_dns_is_rejected(monkeypatch, network):
    result, _ = run_fetch(monkeypatch, network, addresses=("8.8.8.8", "127.0.0.1"))
    assert result.status == collector.FetchStatus.BLOCKED_DESTINATION
    assert network.calls == []


def test_public_ipv6_stays_numeric(monkeypatch, network):
    result, _ = run_fetch(monkeypatch, network, addresses=("2606:4700:4700::1111",))
    assert result.status == collector.FetchStatus.OK
    assert network.calls == [("2606:4700:4700::1111", 443)]


def test_direct_wrong_host_or_socket_rejected():
    async def main():
        backend = collector.PublicNetworkBackend()
        for host, port in [("attacker.invalid", 443), (collector.HOST, 80)]:
            with pytest.raises(collector.BlockedDestination):
                await backend.connect_tcp(host, port)
        with pytest.raises(collector.BlockedDestination):
            await backend.connect_unix_socket("/tmp/fixture")
    asyncio.run(main())


@pytest.mark.parametrize("status", [301, 302, 303, 307, 308])
def test_redirect_never_followed_and_key_never_forwarded(monkeypatch, network, status):
    network.stream = ObservedStream(wire(b"", status, [("Location", "http://169.254.169.254/fixture")]))
    result, dns = run_fetch(monkeypatch, network)
    assert result.status == collector.FetchStatus.REDIRECT
    assert len(dns) == len(network.calls) == 1
    assert result.document is None and result.http_status == status


@pytest.mark.parametrize("status", [401, 429, 500])
def test_http_error_has_no_body(monkeypatch, network, status):
    network.stream = ObservedStream(wire(b"fixture-body-must-not-be-exposed", status))
    result, _ = run_fetch(monkeypatch, network)
    assert result.status == collector.FetchStatus.HTTP_ERROR
    assert result.document is None and "fixture-body" not in repr(result)


@pytest.mark.parametrize("headers", [
    [("Content-Type", "text/html")], [("Content-Type", "application/xml"), ("Content-Encoding", "gzip")],
    [("Content-Type", "application/xml"), ("Content-Length", "-1")],
    [("Content-Type", "application/xml"), ("Content-Type", "text/html")],
])
def test_wrong_response_headers_rejected(monkeypatch, network, headers):
    network.stream = ObservedStream(wire(VALID, headers=headers))
    result, _ = run_fetch(monkeypatch, network)
    assert result.status == collector.FetchStatus.INVALID_RESPONSE
    assert network.stream.closed


def test_announced_oversize_rejected_before_body(monkeypatch, network):
    network.stream = ObservedStream(wire(b"", headers=[("Content-Type", "application/xml"),
        ("Content-Length", str(collector.MAX_BYTES + 1))]))
    result, _ = run_fetch(monkeypatch, network)
    assert result.status == collector.FetchStatus.TOO_LARGE


def test_stream_oversize_without_length_rejected(monkeypatch, network):
    monkeypatch.setattr(collector, "MAX_BYTES", 100)
    network.stream = ObservedStream(wire(b"x" * 101, headers=[("Content-Type", "application/xml"), ("Connection", "close")]))
    result, _ = run_fetch(monkeypatch, network)
    assert result.status == collector.FetchStatus.TOO_LARGE
    assert network.stream.closed


def test_missing_key_does_not_connect(monkeypatch, network):
    result = asyncio.run(collector.fetch(collector.FetchRequest(operation="senuri_list"), SecretStr("")))
    assert result.status == collector.FetchStatus.CONFIGURATION
    assert network.calls == []


def test_total_deadline_covers_dns(monkeypatch, network):
    monkeypatch.setattr(collector, "TOTAL_TIMEOUT", .01)
    async def main():
        async def slow(*args, **kwargs):
            await asyncio.sleep(5)
        monkeypatch.setattr(asyncio.get_running_loop(), "getaddrinfo", slow)
        return await collector.fetch(collector.FetchRequest(operation="senuri_list"), SecretStr("fixture"))
    assert asyncio.run(main()).status == collector.FetchStatus.TIMEOUT
    assert network.calls == []


def test_total_deadline_closes_slow_response_stream(monkeypatch, network):
    class SlowStream(ObservedStream):
        reads = 0

        async def read(self, max_bytes, timeout=None):
            self.reads += 1
            if self.reads > 1:
                await asyncio.sleep(5)
            return await super().read(max_bytes, timeout)

    monkeypatch.setattr(collector, "TOTAL_TIMEOUT", .05)
    network.stream = SlowStream(wire())
    result, _ = run_fetch(monkeypatch, network)
    assert result.status == collector.FetchStatus.TIMEOUT
    assert network.stream.closed


def test_caller_cancellation_is_preserved_and_closes_stream(monkeypatch, network):
    async def main():
        started = asyncio.Event()

        class WaitingStream(ObservedStream):
            reads = 0

            async def read(self, max_bytes, timeout=None):
                self.reads += 1
                if self.reads > 1:
                    started.set()
                    await asyncio.sleep(5)
                return await super().read(max_bytes, timeout)

        async def resolve(*args, **kwargs):
            return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("8.8.8.8", 443))]

        monkeypatch.setattr(asyncio.get_running_loop(), "getaddrinfo", resolve)
        network.stream = WaitingStream(wire())
        task = asyncio.create_task(collector.fetch(collector.FetchRequest(operation="senuri_list"), SecretStr("fixture")))
        await asyncio.wait_for(started.wait(), 1)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        assert network.stream.closed

    asyncio.run(main())


def test_truncated_http_body_not_success(monkeypatch, network):
    network.stream = ObservedStream(wire(VALID[:-10], headers=[("Content-Type", "application/xml"),
                                                                           ("Content-Length", str(len(VALID)))]))
    result, _ = run_fetch(monkeypatch, network)
    assert result.status == collector.FetchStatus.INVALID_RESPONSE
    assert result.document is None


def test_network_exception_is_not_exposed(monkeypatch, network, caplog):
    async def fail(*args, **kwargs):
        raise httpcore.ConnectError("fixture-sensitive-url-query")
    network.connect_tcp = fail
    result, _ = run_fetch(monkeypatch, network)
    assert result.status == collector.FetchStatus.UNAVAILABLE
    assert "sensitive" not in repr(result) + caplog.text


def test_tls_failure_never_sends_credentials(monkeypatch, network):
    class BadCertificate(ObservedStream):
        async def start_tls(self, ssl_context, server_hostname=None, timeout=None):
            raise httpcore.ConnectError("fixture-certificate-verification-failed")

    network.stream = BadCertificate(wire())
    result, _ = run_fetch(monkeypatch, network)
    assert result.status == collector.FetchStatus.UNAVAILABLE
    assert network.stream.writes == []


def test_xinclude_remains_untrusted_element_without_fetch():
    document = VALID.replace(b"</item>", b'<xi:include xmlns:xi="http://www.w3.org/2001/XInclude" href="file:///private-fixture"/></item>')
    result = collector.parse_xml(document)
    assert result.status == collector.FetchStatus.OK
    include = result.document.root.find(".//{http://www.w3.org/2001/XInclude}include")
    assert include is not None and include.attrib["href"] == "file:///private-fixture"


@pytest.mark.parametrize("encoding", ["utf-8", "utf-16", "utf-16-be"])
@pytest.mark.parametrize("doctype", [
    '<!DOCTYPE response SYSTEM "file:///etc/passwd">',
    '<!DOCTYPE response [<!ENTITY x SYSTEM "http://127.0.0.1/fixture">]>',
    '<!DOCTYPE response [<!ENTITY x "expansion"><!ENTITY y "&x;&x;">]>',
])
def test_dtd_entity_and_external_reference_rejected_in_all_encodings(encoding, doctype):
    declaration = "utf-16" if encoding == "utf-16-be" else encoding
    body = ('<?xml version="1.0" encoding="' + declaration + '"?>' + doctype + '<response/>').encode(encoding)
    assert collector.parse_xml(body).status == collector.FetchStatus.UNSAFE_XML


def test_literal_doctype_in_cdata_is_data():
    document = VALID.replace(b"<title>", b"<title><![CDATA[<!DOCTYPE literal>]]>")
    assert collector.parse_xml(document).status == collector.FetchStatus.OK


@pytest.mark.parametrize("body", [
    b"<response>", b"{}", b"<html/>",
    b"<OpenAPI_ServiceResponse><returnReasonCode>30</returnReasonCode></OpenAPI_ServiceResponse>",
    VALID.replace(b"<resultCode>00</resultCode>", b"<resultCode>99</resultCode>"),
])
def test_malformed_or_upstream_error_not_success(body):
    result = collector.parse_xml(body)
    assert result.status != collector.FetchStatus.OK and result.document is None


def test_real_empty_success_distinct_from_failure():
    result = collector.parse_xml(EMPTY)
    assert result.status == collector.FetchStatus.OK
    assert result.document.item_count == result.document.total_count == 0


@pytest.mark.parametrize("body", [
    VALID.replace(b"<totalCount>1</totalCount>", b"<totalCount>-1</totalCount>"),
    VALID.replace(b"<totalCount>1</totalCount>", b"<totalCount>0</totalCount>"),
    VALID.replace(b"<totalCount>1</totalCount>", b""),
    VALID.replace(b"<resultCode>00</resultCode>", b"<resultCode>00</resultCode><resultCode>99</resultCode>"),
])
def test_ambiguous_envelope_rejected(body):
    assert collector.parse_xml(body).status != collector.FetchStatus.OK


@pytest.mark.parametrize("body", [
    ("<a>" * 33 + "</a>" * 33).encode(),
    b"<a>" + b"<b/>" * 20000 + b"</a>",
    b"<a>" + b"x" * 65537 + b"</a>",
], ids=["depth", "count", "text"])
def test_xml_depth_count_and_text_limits(body):
    assert collector.parse_xml(body).status == collector.FetchStatus.UNSAFE_XML
