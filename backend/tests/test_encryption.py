"""AEAD 라운드트립·대상/메타데이터 변조·키 회전/복구·비노출을 실제 암호화로 검증한다."""

import base64
from dataclasses import replace
from datetime import UTC, datetime
import json
import secrets
from uuid import uuid4

import pytest
from pydantic import SecretBytes
from sqlalchemy import insert, select

from app.core.config import Settings
from app.core.encryption import ContentCipher, ContentTarget, EncryptedEnvelope, EncryptionKeyRing, EncryptionUnavailable, ProtectedContentError
from app.persistence import ProfileDocument, ProfileVersion, User
from tests.test_member_models import db


def target(**updates):
    return ContentTarget(**{"owner_id": uuid4(), "kind": "profile", "document_id": uuid4(), "version": 1, "schema_version": 1, **updates})


def ring(keys=None, active="key-v1"):
    return EncryptionKeyRing(keys=keys or {"key-v1": SecretBytes(secrets.token_bytes(32))}, active_key_id=active)


def test_unicode_roundtrip_and_fresh_nonces_for_same_target():
    cipher = ContentCipher(ring())
    destination = target()
    plaintext = json.dumps({"description": "가상 경험과 승인 본문"}, ensure_ascii=False).encode()
    first, second = [cipher.encrypt(plaintext, destination) for _ in range(2)]
    assert first.nonce != second.nonce
    assert first.ciphertext != second.ciphertext
    assert cipher.decrypt(first, destination) == cipher.decrypt(second, destination) == plaintext
    assert first.schema_version == 1 and first.algorithm == "AES-256-GCM"


@pytest.mark.parametrize("field", ["ciphertext", "nonce"])
def test_altered_ciphertext_or_nonce_is_rejected(field):
    cipher, destination = ContentCipher(ring()), target()
    envelope = cipher.encrypt(b"fictional-approved-content", destination)
    data = getattr(envelope, field)
    changed = bytes([data[0] ^ 1]) + data[1:]
    with pytest.raises(ProtectedContentError):
        cipher.decrypt(replace(envelope, **{field: changed}), destination)


@pytest.mark.parametrize("updates", [
    {"owner_id": uuid4()}, {"document_id": uuid4()}, {"kind": "application"},
    {"version": 2}, {"schema_version": 2},
])
def test_owner_kind_document_and_versions_are_bound_to_target(updates):
    cipher, destination = ContentCipher(ring()), target()
    envelope = cipher.encrypt(b"fictional-approved-content", destination)
    with pytest.raises(ProtectedContentError):
        cipher.decrypt(envelope, replace(destination, **updates))


def test_key_alias_and_algorithm_metadata_cannot_be_relabelled():
    root = SecretBytes(secrets.token_bytes(32))
    cipher, destination = ContentCipher(ring({"key-v1": root, "key-v2": root})), target()
    envelope = cipher.encrypt(b"fictional-approved-content", destination)
    with pytest.raises(ProtectedContentError):
        cipher.decrypt(replace(envelope, key_id="key-v2"), destination)
    with pytest.raises(ProtectedContentError):
        replace(envelope, algorithm="plaintext")


def test_rotation_and_recovery_keep_old_envelopes_readable_without_rewrite():
    first_key, second_key = SecretBytes(secrets.token_bytes(32)), SecretBytes(secrets.token_bytes(32))
    destination = target()
    old = ContentCipher(ring({"key-v1": first_key})).encrypt(b"fictional-content", destination)
    restored_ring = ring({"key-v1": first_key, "key-v2": second_key}, active="key-v2")
    cipher = ContentCipher(restored_ring)
    assert cipher.decrypt(old, destination) == b"fictional-content"
    assert cipher.encrypt(b"fictional-content", destination).key_id == "key-v2"
    with pytest.raises(EncryptionUnavailable):
        ContentCipher(ring({"key-v2": second_key}, active="key-v2")).decrypt(old, destination)
    with pytest.raises(ProtectedContentError):
        ContentCipher(ring()).decrypt(old, destination)


def test_other_targets_use_different_derived_keys_even_if_nonce_is_forced_equal(monkeypatch):
    key_ring = ring()
    cipher = ContentCipher(key_ring)
    first, second = target(), target(kind="application")
    monkeypatch.setattr("app.core.encryption.secrets.token_bytes", lambda length: b"n" * length)
    assert key_ring.derive("key-v1", first) != key_ring.derive("key-v1", second)
    one, two = cipher.encrypt(b"same-content", first), cipher.encrypt(b"same-content", second)
    assert one.nonce == two.nonce and one.ciphertext != two.ciphertext
    with pytest.raises(ProtectedContentError):
        cipher.decrypt(one, second)


@pytest.mark.parametrize("payload", [b"", b"a" * 262129, "plaintext"], ids=["empty", "oversized", "nonbytes"])
def test_empty_oversized_and_nonbytes_plaintext_rejected(payload):
    with pytest.raises(ProtectedContentError):
        ContentCipher(ring()).encrypt(payload, target())


@pytest.mark.parametrize("updates", [
    {"version": 0}, {"version": True}, {"schema_version": 0}, {"kind": "arbitrary"},
    {"owner_id": "not-a-server-uuid"},
])
def test_invalid_targets_are_rejected(updates):
    with pytest.raises(ProtectedContentError):
        target(**updates)


def test_settings_load_strict_versioned_keys_without_repr_or_exception_leaks(caplog):
    root = secrets.token_bytes(32)
    encoded = base64.b64encode(root).decode()
    configured = Settings(_env_file=None, data_encryption_keys=json.dumps({"key-v1": encoded}), data_encryption_active_key_id="key-v1")
    key_ring = EncryptionKeyRing.from_settings(configured)
    cipher, destination = ContentCipher(key_ring), target()
    envelope = cipher.encrypt(b"private-fictional-content", destination)
    assert encoded not in repr(configured) + repr(key_ring) + repr(envelope) + caplog.text
    assert "private-fictional-content" not in repr(envelope)
    assert cipher.decrypt(envelope, destination) == b"private-fictional-content"
    for raw in ("invalid-private-input", "[]", '{"key-v1":"bad"}', '{"key-v1":"bad","key-v1":"bad"}'):
        configured = Settings(_env_file=None, data_encryption_keys=raw, data_encryption_active_key_id="key-v1")
        with pytest.raises(EncryptionUnavailable) as caught:
            EncryptionKeyRing.from_settings(configured)
        assert raw not in str(caught.value)


def test_missing_and_short_keys_fail_closed_without_generated_fallback():
    with pytest.raises(EncryptionUnavailable):
        EncryptionKeyRing.from_settings(Settings(_env_file=None))
    with pytest.raises(EncryptionUnavailable):
        ring({"key-v1": SecretBytes(b"short")})


def test_real_envelope_fits_saved_model_and_key_is_not_in_database(db):
    key_ring = ring()
    cipher, destination = ContentCipher(key_ring), target()
    plaintext = b'{"fictional-approved-profile":true}'
    envelope = cipher.encrypt(plaintext, destination)
    now = datetime(2026, 10, 17, tzinfo=UTC)
    db.execute(insert(User), {"id": destination.owner_id, "kakao_subject": "fictional-crypto"})
    db.execute(insert(ProfileDocument), {"id": destination.document_id, "owner_id": destination.owner_id})
    db.execute(insert(ProfileVersion), {
        "owner_id": destination.owner_id, "profile_id": destination.document_id, "version": destination.version,
        "confirmed_at": now, "saved_at": now, "ciphertext": envelope.ciphertext, "nonce": envelope.nonce,
        "algorithm": envelope.algorithm, "key_id": envelope.key_id, "schema_version": envelope.schema_version,
    })
    row = db.execute(select(ProfileVersion.__table__)).mappings().one()
    loaded = EncryptedEnvelope(row["ciphertext"], row["nonce"], row["key_id"], row["algorithm"], row["schema_version"])
    assert cipher.decrypt(loaded, destination) == plaintext
    assert plaintext not in row["ciphertext"]
    assert not {"key", "key_material", "plaintext", "content"} & row.keys()
