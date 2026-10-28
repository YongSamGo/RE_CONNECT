"""가상 카카오 신원의 계정 연결/역할 보존/정지 검사. 실제 사용자 데이터 없음."""

import pytest
from sqlalchemy import func, select, update
from sqlalchemy.orm import sessionmaker

from app.core.business_errors import AppError
from app.modules.auth.accounts import SqlAccountRepository
from app.modules.auth.service import Identity
from app.adapters.auth import OAuthFailure
from app.persistence import User
from tests.ingestion_helpers import ingestion_database


@pytest.mark.parametrize("backend", ["sqlite", "postgresql"])
def test_verified_subject_is_linked_once_with_user_role_and_existing_role_is_not_overwritten(backend, tmp_path):
    with ingestion_database(backend, tmp_path) as (engine, _source):
        repository = SqlAccountRepository(sessionmaker(engine).begin)
        first = repository.link(Identity("12345"))
        assert first.role == "user" and repository.link(Identity("12345")).id == first.id
        with engine.begin() as db:
            assert db.scalar(select(func.count()).select_from(User)) == 1
            db.execute(update(User).where(User.id == first.id).values(role="admin"))
        assert repository.get(first.id).role == "admin"
        assert repository.link(Identity("12345")).role == "admin"
        with engine.begin() as db:db.execute(update(User).where(User.id == first.id).values(role="user", status="suspended"))
        assert repository.get(first.id) is None
        with pytest.raises(AppError, match="FORBIDDEN"):
            repository.link(Identity("12345"))
        with engine.connect() as db:
            assert db.scalar(select(func.count()).select_from(User)) == 1
            assert db.scalar(select(User.status)) == "suspended"


@pytest.mark.parametrize("subject", ["0", "01", "-1", "123 OR 1=1", "9223372036854775808", "１２３", True])
def test_unverified_subject_never_reaches_database(subject, tmp_path):
    with ingestion_database("sqlite", tmp_path) as (engine, _source):
        repository = SqlAccountRepository(sessionmaker(engine).begin)
        with pytest.raises(OAuthFailure):
            repository.link(Identity(subject))
        with engine.connect() as db:
            assert db.scalar(select(func.count()).select_from(User)) == 0
