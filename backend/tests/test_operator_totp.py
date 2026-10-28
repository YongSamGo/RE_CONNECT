"""TOTP 계산을 RFC 6238 부록 B 시험값으로 확인하고 형식·시간 구간 공격 입력을 거절한다."""

from urllib.parse import parse_qs, urlsplit

import pytest

from app.modules.operators import totp

RFC_SECRET = b"12345678901234567890"


@pytest.mark.parametrize(("unix_time", "expected"), [
    (59, "287082"), (1111111109, "081804"), (1111111111, "050471"),
    (1234567890, "005924"), (2000000000, "279037"), (20000000000, "353130"),
])
def test_rfc6238_sha1_vectors_truncated_to_six_digits(unix_time, expected):
    assert totp.code_at(RFC_SECRET, totp.time_step(unix_time)) == expected
    # 8자리 원값의 뒤 6자리와 같아야 한다(RFC 6238 부록 B).
    assert totp.code_at(RFC_SECRET, totp.time_step(unix_time), digits=8).endswith(expected)


def test_accepts_only_one_step_of_clock_drift_and_returns_matched_step():
    step = totp.time_step(1234567890)
    for offset in (-1, 0, 1):
        assert totp.matching_step(RFC_SECRET, totp.code_at(RFC_SECRET, step + offset), step) == step + offset
    for offset in (-3, -2, 2, 3):
        assert totp.matching_step(RFC_SECRET, totp.code_at(RFC_SECRET, step + offset), step) is None


@pytest.mark.parametrize("otp", ["", "12345", "1234567", "12ab56", " 287082", "287082\n", "２８７０８２", None, 287082])
def test_malformed_codes_never_match(otp):
    assert totp.matching_step(RFC_SECRET, otp, totp.time_step(59)) is None


def test_other_secret_does_not_match_and_step_range_is_checked():
    step = totp.time_step(59)
    assert totp.matching_step(b"x" * 20, totp.code_at(RFC_SECRET, step), step) != step
    with pytest.raises(ValueError):
        totp.code_at(RFC_SECRET, -1)


def test_new_secret_is_random_and_uri_has_no_member_identifiers():
    first, second = totp.new_secret(), totp.new_secret()
    assert len(first) == totp.SECRET_BYTES and first != second
    uri = totp.provisioning_uri(first, "operator-1a2b3c4d")
    parts = urlsplit(uri)
    query = parse_qs(parts.query)
    assert parts.scheme == "otpauth" and parts.netloc == "totp"
    assert query["digits"] == ["6"] and query["period"] == ["30"] and query["algorithm"] == ["SHA1"]
    assert "kakao" not in uri.lower()
