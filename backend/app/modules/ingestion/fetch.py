"""고정 공공 API의 메모리 수집. URL·본문·인증키를 로그/예외로 전달하지 않는다."""

import asyncio
from dataclasses import dataclass, field
from enum import StrEnum
import ipaddress
import socket
import ssl
from typing import Literal
from urllib.parse import urlencode
# TreeBuilder/Element/ParseError만 사용한다. 외부 입력 파싱은 아래 DefusedXMLParser로 제한한다.
import xml.etree.ElementTree as ET  # nosec B405

from defusedxml.ElementTree import DefusedXMLParser
from defusedxml.common import DefusedXmlException
import httpcore
from pydantic import BaseModel, ConfigDict, Field, SecretStr, model_validator


HOST = "apis.data.go.kr"
ENDPOINTS = {
    "senuri_list": "/B552474/SenuriService/getJobList",
    "senuri_detail": "/B552474/SenuriService/getJobInfo",
    "volunteer_list": "/1741000/volunteerPartcptnService/getVltrAreaList",
    "volunteer_detail": "/1741000/volunteerPartcptnService/getVltrPartcptnItem",
}
MAX_BYTES = 2 * 1024 * 1024
MAX_ELEMENTS = 20000
MAX_DEPTH = 32
MAX_TEXT = 65536
TOTAL_TIMEOUT = 20.0
IO_TIMEOUT = 5.0
# 노인 일자리 API의 약 7초 응답을 허용하되 전체 20초 제한은 유지한다.
SENURI_READ_TIMEOUT = 15.0
# 순서는 영속 수집 커서의 region_index와 대응한다. 변경 시 커서 마이그레이션이 필요하다.
VOLUNTEER_REGIONS = ("6110000", "6410000", "6280000")


class FetchRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    operation: Literal["senuri_list", "senuri_detail", "volunteer_list", "volunteer_detail"]
    page_no: int = Field(default=1, ge=1, le=100000)
    num_rows: int = Field(default=10, ge=1, le=100)
    external_id: str | None = Field(default=None, pattern=r"^[A-Za-z0-9_-]{1,64}$")
    region_code: Literal["6110000", "6410000", "6280000"] | None = None

    @model_validator(mode="after")
    def detail_has_id(self):
        if self.operation.endswith("_detail") != (self.external_id is not None):
            raise ValueError("상세 요청에는 식별자가 필요하고 목록에는 사용할 수 없습니다")
        if (self.operation == "volunteer_list") != (self.region_code is not None):
            raise ValueError("봉사 목록에는 수도권 지역이 필요하고 다른 요청에는 사용할 수 없습니다")
        return self


class FetchStatus(StrEnum):
    OK = "ok"
    CONFIGURATION = "configuration_error"
    BLOCKED_DESTINATION = "blocked_destination"
    REDIRECT = "redirect_rejected"
    HTTP_ERROR = "http_error"
    INVALID_RESPONSE = "invalid_response"
    TOO_LARGE = "response_too_large"
    UNSAFE_XML = "unsafe_xml"
    UPSTREAM_ERROR = "upstream_error"
    TIMEOUT = "timeout"
    UNAVAILABLE = "unavailable"


@dataclass(frozen=True)
class UntrustedDocument:
    """필드 값은 아직 비신뢰 원문이며 저장·화면 출력 전에 #46 정규화가 필요하다."""

    root: ET.Element = field(repr=False)
    item_count: int
    total_count: int


@dataclass(frozen=True)
class FetchResult:
    status: FetchStatus
    document: UntrustedDocument | None = field(default=None, repr=False)
    http_status: int | None = None


class BlockedDestination(Exception):
    pass


class XMLLimit(Exception):
    pass


class PublicNetworkBackend(httpcore.AsyncNetworkBackend):
    """DNS를 한 번 확인한 뒤 숫자 IP로 연결. TLS SNI/인증은 원래 HOST를 유지한다."""

    def __init__(self):
        self._backend = httpcore.AnyIOBackend()

    async def connect_tcp(self, host, port, timeout=None, local_address=None, socket_options=None):
        if host != HOST or port != 443 or local_address is not None:
            raise BlockedDestination
        records = await asyncio.wait_for(
            asyncio.get_running_loop().getaddrinfo(host, port, type=socket.SOCK_STREAM), IO_TIMEOUT
        )
        addresses = []
        for family, _, _, _, address in records:
            if family not in (socket.AF_INET, socket.AF_INET6):
                raise BlockedDestination
            text = address[0]
            ip = ipaddress.ip_address(text)
            # 사설/루프백/link-local 및 IPv6 전환 주소를 통한 내부 IPv4 우회를 거절한다.
            if not ip.is_global or ip.is_multicast or ip.is_reserved or "%" in text or (ip.version == 6 and (
                ip.ipv4_mapped is not None or ip.sixtofour is not None or ip.teredo is not None
                or ip in ipaddress.ip_network("64:ff9b::/96")
                or ip in ipaddress.ip_network("64:ff9b:1::/48")
            )):
                raise BlockedDestination
            addresses.append(str(ip))
        if not addresses:
            raise BlockedDestination
        # 두 번째 호스트 DNS 조회가 일어나지 않도록 검증한 숫자 IP만 넘긴다.
        return await self._backend.connect_tcp(addresses[0], port, timeout=timeout,
                                               socket_options=socket_options)

    async def connect_unix_socket(self, *args, **kwargs):
        raise BlockedDestination

    async def sleep(self, seconds):
        await asyncio.sleep(seconds)


class LimitedTreeBuilder(ET.TreeBuilder):
    def __init__(self):
        super().__init__()
        self.depth = 0
        self.count = 0
        self.text_sizes = []

    def start(self, tag, attrs):
        self.depth += 1
        self.count += 1
        if self.depth > MAX_DEPTH or self.count > MAX_ELEMENTS or len(attrs) > 32 or len(tag) > 256:
            raise XMLLimit
        self.text_sizes.append(0)
        return super().start(tag, attrs)

    def end(self, tag):
        self.depth -= 1
        self.text_sizes.pop()
        return super().end(tag)

    def data(self, data):
        if self.text_sizes:
            self.text_sizes[-1] += len(data)
            if self.text_sizes[-1] > MAX_TEXT:
                raise XMLLimit
        return super().data(data)


def parse_xml(body: bytes) -> FetchResult:
    if len(body) > MAX_BYTES:
        return FetchResult(FetchStatus.TOO_LARGE)
    try:
        parser = DefusedXMLParser(target=LimitedTreeBuilder(), forbid_dtd=True,
                                 forbid_entities=True, forbid_external=True)
        parser.feed(body)
        root = parser.close()
    except (DefusedXmlException, XMLLimit):
        return FetchResult(FetchStatus.UNSAFE_XML)
    except (ET.ParseError, ValueError, LookupError):
        return FetchResult(FetchStatus.INVALID_RESPONSE)
    # data.go.kr는 HTTP 200에도 키/한도 오류를 담는다. 공고 0개로 성공 처리하지 않는다.
    if root.tag != "response" or len(root.findall("header")) != 1:
        return FetchResult(FetchStatus.UPSTREAM_ERROR)
    codes = root.findall("header/resultCode")
    if len(codes) != 1 or (codes[0].text or "").strip() not in ("00", "0"):
        return FetchResult(FetchStatus.UPSTREAM_ERROR)
    bodies = root.findall("body")
    counts = root.findall("body/totalCount")
    if len(bodies) != 1 or len(counts) != 1:
        return FetchResult(FetchStatus.INVALID_RESPONSE)
    count_text = (counts[0].text or "").strip()
    if not count_text.isascii() or not count_text.isdecimal() or len(count_text) > 10:
        return FetchResult(FetchStatus.INVALID_RESPONSE)
    items = root.findall("body/items")
    item_count = len(root.findall("body/items/item"))
    total = int(count_text)
    if len(items) > 1 or total < item_count or (total > 0 and not items):
        return FetchResult(FetchStatus.INVALID_RESPONSE)
    return FetchResult(FetchStatus.OK, UntrustedDocument(root, item_count, total))


def _url(request: FetchRequest, key: SecretStr) -> str:
    params = {"serviceKey": key.get_secret_value(), "pageNo": str(request.page_no),
              "numOfRows": str(request.num_rows)}
    if request.external_id is not None:
        params["id" if request.operation == "senuri_detail" else "progrmRegistNo"] = request.external_id
    if request.region_code is not None:
        params["schSido"] = request.region_code
    return "https://" + HOST + ENDPOINTS[request.operation] + "?" + urlencode(params)


def _header(headers, name: bytes) -> str | None:
    values = [v.decode("ascii") for k, v in headers if k.lower() == name]
    if len(values) > 1:
        raise ValueError("중복 응답 헤더")
    return values[0] if values else None


async def fetch(request: FetchRequest, key: SecretStr) -> FetchResult:
    """운영자/스케줄러가 호출한다. 자동 재시도·파일 저장·로깅은 하지 않는다."""
    value = key.get_secret_value()
    if not value.strip() or len(value) > 512 or any(ord(c) < 32 or ord(c) == 127 for c in value):
        return FetchResult(FetchStatus.CONFIGURATION)
    read_timeout = SENURI_READ_TIMEOUT if request.operation in ("senuri_list", "senuri_detail") else IO_TIMEOUT
    try:
        async with asyncio.timeout(TOTAL_TIMEOUT):
            async with httpcore.AsyncConnectionPool(network_backend=PublicNetworkBackend(),
                    ssl_context=ssl.create_default_context(), max_connections=1,
                    max_keepalive_connections=0, retries=0) as pool:
                async with pool.stream("GET", _url(request, key),
                        headers=[(b"Accept", b"application/xml"), (b"Accept-Encoding", b"identity")],
                        extensions={"timeout": {"connect": IO_TIMEOUT, "read": read_timeout,
                                                "write": IO_TIMEOUT, "pool": IO_TIMEOUT}}) as response:
                    if 300 <= response.status < 400:
                        return FetchResult(FetchStatus.REDIRECT, http_status=response.status)
                    if response.status != 200:
                        return FetchResult(FetchStatus.HTTP_ERROR, http_status=response.status)
                    content_type = (_header(response.headers, b"content-type") or "").split(";")[0].strip().lower()
                    encoding = (_header(response.headers, b"content-encoding") or "identity").lower()
                    if content_type not in ("application/xml", "text/xml") or encoding != "identity":
                        return FetchResult(FetchStatus.INVALID_RESPONSE)
                    length = _header(response.headers, b"content-length")
                    if length is not None and (not length.isascii() or not length.isdecimal()):
                        return FetchResult(FetchStatus.INVALID_RESPONSE)
                    if length is not None and int(length) > MAX_BYTES:
                        return FetchResult(FetchStatus.TOO_LARGE)
                    body = bytearray()
                    async for chunk in response.aiter_stream():
                        if len(body) + len(chunk) > MAX_BYTES:
                            return FetchResult(FetchStatus.TOO_LARGE)
                        body.extend(chunk)
                    if length is not None and len(body) != int(length):
                        return FetchResult(FetchStatus.INVALID_RESPONSE)
                    return parse_xml(bytes(body))
    except BlockedDestination:
        return FetchResult(FetchStatus.BLOCKED_DESTINATION)
    except (TimeoutError, httpcore.TimeoutException):
        return FetchResult(FetchStatus.TIMEOUT)
    except (ValueError, UnicodeError, httpcore.RemoteProtocolError):
        return FetchResult(FetchStatus.INVALID_RESPONSE)
    except (OSError, httpcore.NetworkError, httpcore.ProtocolError):
        return FetchResult(FetchStatus.UNAVAILABLE)
