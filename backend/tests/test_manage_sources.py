"""수집 출처 등록 관리 명령: 고정 허용 목록, 멱등 등록, 변조 행 거절."""

import json

import pytest
from sqlalchemy import create_engine, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.pool import StaticPool

import manage_sources
from app.modules.ingestion.runs import BASE_URLS, DAILY_LIMITS
from app.persistence.base import Base
from app.persistence.operations import Source


@pytest.fixture
def engine():
    engine = create_engine("sqlite://", poolclass=StaticPool, connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    yield engine
    engine.dispose()


def run(engine, *argv, capsys):
    code = manage_sources.main(list(argv), engine=engine)
    return code, json.loads(capsys.readouterr().out)


def rows(engine):
    with engine.connect() as db:
        return {row.code: row for row in db.execute(select(Source.code, Source.base_url, Source.enabled))}


def test_allow_list_matches_collector():
    assert set(manage_sources.OFFICIAL) == set(DAILY_LIMITS)
    for code, source in manage_sources.OFFICIAL.items():
        assert source["base_url"] == BASE_URLS[code]
        assert source["base_url"].startswith("https://apis.data.go.kr/")
        assert source["terms_url"].startswith("https://www.data.go.kr/data/")


def test_register_is_disabled_and_idempotent(engine, capsys):
    assert run(engine, "register", capsys=capsys) == (0, {"completed": True, "created": ["senuri", "volunteer"]})
    assert {code: row.enabled for code, row in rows(engine).items()} == {"senuri": False, "volunteer": False}
    assert run(engine, "register", capsys=capsys) == (0, {"completed": True, "created": []})
    assert len(rows(engine)) == 2


def test_enable_disable_and_list(engine, capsys):
    run(engine, "register", capsys=capsys)
    assert run(engine, "enable", "senuri", capsys=capsys)[0] == 0
    code, output = run(engine, "list", capsys=capsys)
    assert code == 0
    assert {s["code"]: (s["registered"], s["official"], s["enabled"]) for s in output["sources"]} == {
        "senuri": (True, True, True), "volunteer": (True, True, False)}
    assert run(engine, "disable", "senuri", capsys=capsys)[0] == 0
    assert rows(engine)["senuri"].enabled is False


def test_enable_before_register_fails(engine, capsys):
    assert run(engine, "enable", "volunteer", capsys=capsys) == (1, {"completed": False, "code": "SOURCE_NOT_REGISTERED"})


def test_database_rejects_plain_http_source(engine, capsys):
    run(engine, "register", capsys=capsys)
    with pytest.raises(IntegrityError), engine.begin() as db:
        db.execute(update(Source).where(Source.code == "senuri").values(base_url="http://apis.data.go.kr/B552474/SenuriService"))
    assert rows(engine)["senuri"].base_url == BASE_URLS["senuri"]


@pytest.mark.parametrize("tampered", [
    "https://evil.example/B552474/SenuriService",
    "https://apis.data.go.kr/B552474/SenuriService/../other",
])
def test_tampered_row_is_not_enabled_or_overwritten(engine, capsys, tampered):
    run(engine, "register", capsys=capsys)
    with engine.begin() as db:
        db.execute(update(Source).where(Source.code == "senuri").values(base_url=tampered))
    assert run(engine, "enable", "senuri", capsys=capsys) == (1, {"completed": False, "code": "SOURCE_MISMATCH"})
    assert run(engine, "register", capsys=capsys) == (1, {"completed": False, "code": "SOURCE_MISMATCH"})
    row = rows(engine)["senuri"]
    assert (row.base_url, row.enabled) == (tampered, False)
    listed = {s["code"]: s for s in run(engine, "list", capsys=capsys)[1]["sources"]}
    assert listed["senuri"]["official"] is False


@pytest.mark.parametrize("field,value", [
    ("base_url", "https://evil.example/B552474/SenuriService"),
    ("name", "오래된 이름"),
    ("terms_url", "https://www.data.go.kr/data/00000000/openapi.do"),
])
def test_enabled_mismatched_row_can_still_be_disabled(engine, capsys, field, value):
    run(engine, "register", capsys=capsys)
    run(engine, "enable", "senuri", capsys=capsys)
    with engine.begin() as db:
        db.execute(update(Source).where(Source.code == "senuri").values(**{field: value}))
    assert run(engine, "disable", "senuri", capsys=capsys) == (0, {"completed": True, "code": "senuri", "enabled": False})
    with engine.connect() as db:
        row = db.execute(select(Source.enabled, getattr(Source, field)).where(Source.code == "senuri")).one()
    # 끄기만 하고 달라진 값은 고치지 않는다 (운영자가 원인을 확인할 수 있게)
    assert row.enabled is False and row[1] == value
    assert run(engine, "enable", "senuri", capsys=capsys) == (1, {"completed": False, "code": "SOURCE_MISMATCH"})


@pytest.mark.parametrize("argv", [
    ["enable", "manual_seoul"],
    ["enable", "https://evil.example"],
    ["register", "--base-url", "https://evil.example"],
    ["enable"],
])
def test_unknown_codes_and_url_arguments_are_rejected(engine, argv):
    with pytest.raises(SystemExit):
        manage_sources.main(argv, engine=engine)
    assert rows(engine) == {}


def test_output_has_no_urls(engine, capsys):
    run(engine, "register", capsys=capsys)
    text = json.dumps(run(engine, "list", capsys=capsys)[1])
    assert "http" not in text


def test_missing_database_url_fails_closed(monkeypatch, capsys):
    class Settings:
        database_url = None
    monkeypatch.setattr(manage_sources, "get_settings", lambda: Settings())
    assert manage_sources.main(["list"]) == 1
    assert json.loads(capsys.readouterr().out) == {"completed": False, "code": "SERVICE_UNAVAILABLE"}
