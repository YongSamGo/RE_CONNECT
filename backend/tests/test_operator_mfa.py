"""운영자 부여·회수와 MFA 등록·확인·복구를 실제 SQL과 AES-GCM으로 검증한다 (W07-01, 부적절한 인가 SEC-02·반복된 인증시도 제한 기능 부재 SEC-16).

정상 입력과 공격 입력(일반 회원의 확인 시도, OTP 재사용, 연속 실패, 잠금 중 정답, 회수 뒤 확인, 비밀값 변조)을
함께 둔다. 회원·비밀값·코드는 모두 가상 값이다.
"""

import base64
from datetime import UTC, datetime, timedelta
import secrets
from uuid import uuid4

import pytest
from pydantic import SecretBytes
from sqlalchemy import insert, select, update
from sqlalchemy.orm import sessionmaker

import manage_operators
from app.core.encryption import ContentCipher, EncryptionKeyRing
from app.modules.operators import totp
from app.modules.operators.repository import LOCK_SECONDS, OperatorProcedureError, SqlOperatorMfaRepository
from app.persistence import AuditEvent, DeletionRecord, OperatorMfaCredential, User
from tests.ingestion_helpers import ingestion_database

NOW = datetime(2026, 10, 27, 3, 0, 0, tzinfo=UTC)
SECRET = b"fictional-totp-seed!"  # 20바이트 가상 비밀값
REQUEST = "req_" + "a" * 32


def code(at, secret=SECRET, offset=0):
    return totp.code_at(secret, totp.time_step(at.timestamp()) + offset)


@pytest.fixture(params=["sqlite", "postgresql"])
def setup(request, tmp_path):
    with ingestion_database(request.param, tmp_path) as (engine, _source):
        cipher = ContentCipher(EncryptionKeyRing(keys={"key-v1": SecretBytes(secrets.token_bytes(32))}, active_key_id="key-v1"))
        repository = SqlOperatorMfaRepository(sessionmaker(engine).begin, cipher)
        user_id = uuid4()
        with engine.begin() as db:
            db.execute(insert(User).values(id=user_id, kakao_subject="900001", role="user", status="active"))
        yield engine, repository, user_id


def enrolled(repository, user_id, at=NOW - timedelta(minutes=5)):
    repository.grant(user_id, now=at, request_id=REQUEST)
    return repository.enroll(user_id, SECRET, totp.time_step(at.timestamp()), now=at, request_id=REQUEST)


def user(engine, user_id):
    with engine.connect() as db:
        return db.execute(select(User.role, User.session_generation).where(User.id == user_id)).one()


def actions(engine):
    with engine.connect() as db:
        return [row.action for row in db.execute(select(AuditEvent).order_by(AuditEvent.at, AuditEvent.action))]


def test_grant_enroll_and_verify_bind_result_to_current_credential(setup):
    engine, repository, user_id = setup
    assert repository.credential_id(user_id) is None
    credential_id = enrolled(repository, user_id)
    assert user(engine, user_id).role == "admin" and repository.credential_id(user_id) == credential_id
    result = repository.verify(user_id, code(NOW), NOW, REQUEST)
    assert result.status == "verified" and result.credential_id == credential_id
    with engine.connect() as db:
        stored = db.execute(select(OperatorMfaCredential.ciphertext, OperatorMfaCredential.failed_count)).one()
        events = db.execute(select(AuditEvent.actor_role, AuditEvent.target_id, AuditEvent.request_id)).all()
    # 비밀값 평문은 DB에 없고 감사 기록에도 OTP가 남지 않는다.
    assert SECRET not in stored.ciphertext and stored.failed_count == 0
    assert {event.target_id for event in events} == {user_id} and all(event.request_id == REQUEST for event in events)
    assert sorted(actions(engine)) == ["mfa.enroll", "mfa.verify", "role.grant"]


def test_same_otp_and_enrollment_confirmation_code_cannot_be_reused(setup):
    engine, repository, user_id = setup
    enrolled(repository, user_id, at=NOW)
    # 등록 확인에 쓴 코드는 웹 확인에 다시 쓸 수 없다.
    assert repository.verify(user_id, code(NOW), NOW, REQUEST).status == "invalid"
    later = NOW + timedelta(seconds=30)
    assert repository.verify(user_id, code(later), later, REQUEST).status == "verified"
    assert repository.verify(user_id, code(later), later, REQUEST).status == "invalid"
    # 이미 쓴 구간보다 이전 구간(시계 오차 허용 범위)도 받지 않는다.
    assert repository.verify(user_id, code(later, offset=-1), later, REQUEST).status == "invalid"


def test_five_consecutive_failures_lock_account_and_correct_code_is_not_checked_while_locked(setup):
    engine, repository, user_id = setup
    enrolled(repository, user_id)
    wrong = "000000" if code(NOW) != "000000" else "111111"
    assert [repository.verify(user_id, wrong, NOW, REQUEST).status for _ in range(4)] == ["invalid"] * 4
    locked = repository.verify(user_id, wrong, NOW, REQUEST)
    assert locked.status == "locked" and locked.retry_after == LOCK_SECONDS
    soon = NOW + timedelta(minutes=14, seconds=50)
    during = repository.verify(user_id, code(soon), soon, REQUEST)
    assert during.status == "locked" and during.retry_after == 10
    with engine.connect() as db:
        assert db.scalar(select(OperatorMfaCredential.last_step)) == totp.time_step((NOW - timedelta(minutes=5)).timestamp())
    after = NOW + timedelta(minutes=15)
    assert repository.verify(user_id, code(after), after, REQUEST).status == "verified"
    assert actions(engine).count("mfa.fail") == 5 and actions(engine).count("mfa.lock") == 1


def test_success_resets_failure_count(setup):
    engine, repository, user_id = setup
    enrolled(repository, user_id)
    for _ in range(4):
        repository.verify(user_id, "999999" if code(NOW) != "999999" else "888888", NOW, REQUEST)
    assert repository.verify(user_id, code(NOW), NOW, REQUEST).status == "verified"
    with engine.connect() as db:
        assert db.scalar(select(OperatorMfaCredential.failed_count)) == 0


def test_member_without_operator_role_cannot_verify_or_enroll(setup):
    engine, repository, user_id = setup
    assert repository.verify(user_id, code(NOW), NOW, REQUEST).status == "forbidden"
    with pytest.raises(OperatorProcedureError, match="not_operator"):
        repository.enroll(user_id, SECRET, totp.time_step(NOW.timestamp()), now=NOW, request_id=REQUEST)
    assert actions(engine) == []


def test_revoke_removes_secret_expires_sessions_and_blocks_verify(setup):
    engine, repository, user_id = setup
    enrolled(repository, user_id)
    generation = user(engine, user_id).session_generation
    repository.revoke(user_id, now=NOW, request_id=REQUEST)
    assert user(engine, user_id) == ("user", generation + 1)
    assert repository.credential_id(user_id) is None
    assert repository.verify(user_id, code(NOW), NOW, REQUEST).status == "forbidden"
    with engine.connect() as db:
        assert db.execute(select(OperatorMfaCredential)).all() == []
    with pytest.raises(OperatorProcedureError, match="not_operator"):
        repository.revoke(user_id, now=NOW, request_id=REQUEST)


def test_reset_changes_credential_and_expires_sessions(setup):
    engine, repository, user_id = setup
    first = enrolled(repository, user_id)
    generation = user(engine, user_id).session_generation
    repository.reset(user_id, now=NOW, request_id=REQUEST)
    assert repository.credential_id(user_id) is None and user(engine, user_id).session_generation == generation + 1
    assert repository.verify(user_id, code(NOW), NOW, REQUEST).status == "invalid"
    with pytest.raises(OperatorProcedureError, match="not_enrolled"):
        repository.reset(user_id, now=NOW, request_id=REQUEST)
    second = repository.enroll(user_id, SECRET, totp.time_step(NOW.timestamp()), now=NOW, request_id=REQUEST)
    assert second != first and repository.credential_id(user_id) == second
    with pytest.raises(OperatorProcedureError, match="already_enrolled"):
        repository.enroll(user_id, SECRET, totp.time_step(NOW.timestamp()), now=NOW, request_id=REQUEST)
    assert "mfa.reset" in actions(engine)


def test_suspended_or_deleting_member_cannot_be_granted_and_loses_operator_access(setup):
    engine, repository, user_id = setup
    enrolled(repository, user_id)
    with engine.begin() as db:
        db.execute(insert(DeletionRecord).values(id=uuid4(), owner_id=user_id, scope="account", target_id=user_id,
                                                status="pending", deleted_at=NOW, expires_at=NOW + timedelta(days=1)))
    assert repository.credential_id(user_id) is None
    assert repository.verify(user_id, code(NOW), NOW, REQUEST).status == "forbidden"
    other = uuid4()
    with engine.begin() as db:
        db.execute(insert(User).values(id=other, kakao_subject="900002", role="user", status="suspended"))
    for target, reason in ((user_id, "pending_deletion"), (other, "not_found"), (uuid4(), "not_found")):
        with pytest.raises(OperatorProcedureError, match=reason):
            repository.grant(target, now=NOW, request_id=REQUEST)


def test_tampered_secret_fails_closed_without_counting_as_success(setup):
    engine, repository, user_id = setup
    enrolled(repository, user_id)
    with engine.begin() as db:
        stored = db.scalar(select(OperatorMfaCredential.ciphertext))
        db.execute(update(OperatorMfaCredential).values(ciphertext=bytes([stored[0] ^ 1]) + stored[1:]))
    from app.core.business_errors import AppError
    with pytest.raises(AppError, match="SERVICE_UNAVAILABLE"):
        repository.verify(user_id, code(NOW), NOW, REQUEST)


def test_cli_enroll_saves_only_after_matching_code_and_never_prints_secret_in_result(setup):
    engine, repository, user_id = setup
    repository.grant(user_id, now=NOW, request_id=REQUEST)
    shown, typed = [], iter(["123", "000000", "999999"])
    result = manage_operators.execute("enroll", user_id, repository, clock=lambda: NOW, prompt=lambda: next(typed), show=shown.append)
    assert result == {"completed": False} and repository.credential_id(user_id) is None
    assert len(shown) == 1 and shown[0].startswith("otpauth://totp/")

    def prompt_with_right_code():
        encoded = shown[-1].split("secret=")[1].split("&")[0]
        secret = base64.b32decode(encoded + "=" * (-len(encoded) % 8))
        return totp.code_at(secret, totp.time_step(NOW.timestamp()))
    assert manage_operators.execute("enroll", user_id, repository, clock=lambda: NOW, prompt=prompt_with_right_code,
                                    show=shown.append) == {"completed": True}
    assert repository.credential_id(user_id) is not None and len(shown) == 2


def test_cli_commands_and_argument_validation(setup):
    engine, repository, user_id = setup
    for command, role in (("grant", "admin"), ("revoke", "user")):
        assert manage_operators.execute(command, user_id, repository, clock=lambda: NOW) == {"completed": True}
        assert user(engine, user_id).role == role
    assert manage_operators.parse_args(["grant", str(user_id)]).user_id == user_id
    for bad in (["grant", "1"], ["grant", user_id.hex], ["promote", str(user_id)], ["grant", str(user_id) + "' OR 1=1"]):
        with pytest.raises(SystemExit):
            manage_operators.parse_args(bad)


def test_cli_enroll_refuses_non_terminal_output(capsys):
    assert manage_operators.main(["enroll", str(uuid4())]) == 1
    assert '"tty_required"' in capsys.readouterr().out
