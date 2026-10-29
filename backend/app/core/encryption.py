"""AES-256-GCM 승인 본문 암호화 (W03-06).

키는 DB와 분리한 비밀 설정에서 받고 저장 대상·소유자·버전을 AAD로 결합한다.
동의/승인/소유권 검사를 대신하지 않으며 평문·키·암호문을 로그로 출력하지 않는다.
"""

import base64
import binascii
from dataclasses import dataclass, field
import json
import re
import secrets
from typing import Literal
from uuid import UUID

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.hkdf import HKDF
from pydantic import SecretBytes

from app.core.config import Settings

ALGORITHM = "AES-256-GCM"
MAX_CIPHERTEXT_BYTES = 262144
_KEY_ID = re.compile(r"[a-z0-9._-]{1,128}")
ContentKind = Literal["profile", "application", "report", "operator_mfa"]


class EncryptionUnavailable(Exception):
    """키 설정 누락/오류. 원문이나 키 ID를 메시지에 넣지 않는다."""


class ProtectedContentError(Exception):
    """변조·대상 불일치·잘못된 봉투. 사용자에게 내부 구분을 노출하지 않는다."""


@dataclass(frozen=True)
class ContentTarget:
    owner_id: UUID
    kind: ContentKind
    document_id: UUID
    version: int
    schema_version: int

    def __post_init__(self):
        if (
            not isinstance(self.owner_id, UUID) or not isinstance(self.document_id, UUID)
            or self.kind not in ("profile", "application", "report", "operator_mfa")
            or type(self.version) is not int or not 1 <= self.version <= 2**31 - 1
            or type(self.schema_version) is not int or not 1 <= self.schema_version <= 2**31 - 1
        ):
            raise ProtectedContentError("저장 대상을 확인할 수 없습니다")

    def fields(self):
        return {
            "owner_id": str(self.owner_id), "kind": self.kind, "document_id": str(self.document_id),
            "version": self.version, "schema_version": self.schema_version,
        }


@dataclass(frozen=True)
class EncryptedEnvelope:
    ciphertext: bytes = field(repr=False)
    nonce: bytes = field(repr=False)
    key_id: str
    algorithm: str
    schema_version: int

    def __post_init__(self):
        if (
            type(self.ciphertext) is not bytes or not 17 <= len(self.ciphertext) <= MAX_CIPHERTEXT_BYTES
            or type(self.nonce) is not bytes or len(self.nonce) != 12
            or not isinstance(self.key_id, str) or not _KEY_ID.fullmatch(self.key_id)
            or self.algorithm != ALGORITHM
            or type(self.schema_version) is not int or not 1 <= self.schema_version <= 2**31 - 1
        ):
            raise ProtectedContentError("저장 자료를 확인할 수 없습니다")


def _unique_object(pairs):
    result = {}
    for name, value in pairs:
        if name in result:
            raise ValueError("중복 키")
        result[name] = value
    return result


class EncryptionKeyRing:
    """버전별 256비트 master key. 공개 직렬화/DB 저장 메서드를 제공하지 않는다."""

    def __init__(self, *, keys: dict[str, SecretBytes], active_key_id: str):
        if (
            not isinstance(active_key_id, str) or not _KEY_ID.fullmatch(active_key_id)
            or not 1 <= len(keys) <= 10 or active_key_id not in keys
            or any(
                not isinstance(name, str) or not _KEY_ID.fullmatch(name)
                or not isinstance(key, SecretBytes) or len(key.get_secret_value()) != 32
                for name, key in keys.items()
            )
        ):
            raise EncryptionUnavailable("암호화 키 설정을 확인해 주세요")
        self._keys = dict(keys)
        self.active_key_id = active_key_id

    def __repr__(self):
        return "EncryptionKeyRing([redacted])"

    @classmethod
    def from_settings(cls, settings: Settings) -> "EncryptionKeyRing":
        if settings.data_encryption_keys is None or settings.data_encryption_active_key_id is None:
            raise EncryptionUnavailable("암호화 키 설정이 필요합니다")
        try:
            raw = settings.data_encryption_keys.get_secret_value()
            if len(raw) > 4096:
                raise ValueError
            encoded = json.loads(raw, object_pairs_hook=_unique_object)
            if not isinstance(encoded, dict):
                raise ValueError
            keys = {name: SecretBytes(base64.b64decode(value, validate=True)) for name, value in encoded.items()}
            return cls(keys=keys, active_key_id=settings.data_encryption_active_key_id)
        except (ValueError, TypeError, binascii.Error):
            raise EncryptionUnavailable("암호화 키 설정을 확인해 주세요") from None

    def derive(self, key_id: str, target: ContentTarget) -> bytes:
        root = self._keys.get(key_id)
        if root is None:
            raise EncryptionUnavailable("필요한 복호화 키를 사용할 수 없습니다")
        # 종류·소유자·문서·버전별로 실제 AES 키를 분리한다. 같은 master ID라도 다른 대상은 다른 키다.
        info = _canonical({"domain": "reconnect/content-key/v1", **target.fields()})
        return HKDF(algorithm=hashes.SHA256(), length=32, salt=None, info=info).derive(root.get_secret_value())


def _canonical(value) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("ascii")


def _aad(target: ContentTarget, key_id: str) -> bytes:
    return _canonical({"domain": "reconnect/content-aad/v1", "algorithm": ALGORITHM, "key_id": key_id, **target.fields()})


class ContentCipher:
    def __init__(self, key_ring: EncryptionKeyRing):
        self._key_ring = key_ring

    def encrypt(self, plaintext: bytes, target: ContentTarget) -> EncryptedEnvelope:
        if type(plaintext) is not bytes or not 1 <= len(plaintext) <= MAX_CIPHERTEXT_BYTES - 16:
            raise ProtectedContentError("저장 본문의 형식이나 크기를 확인해 주세요")
        key_id = self._key_ring.active_key_id
        nonce = secrets.token_bytes(12)
        ciphertext = AESGCM(self._key_ring.derive(key_id, target)).encrypt(nonce, plaintext, _aad(target, key_id))
        return EncryptedEnvelope(ciphertext, nonce, key_id, ALGORITHM, target.schema_version)

    def decrypt(self, envelope: EncryptedEnvelope, target: ContentTarget) -> bytes:
        if envelope.schema_version != target.schema_version:
            raise ProtectedContentError("저장 자료를 확인할 수 없습니다")
        try:
            return AESGCM(self._key_ring.derive(envelope.key_id, target)).decrypt(
                envelope.nonce, envelope.ciphertext, _aad(target, envelope.key_id),
            )
        except InvalidTag:
            raise ProtectedContentError("저장 자료를 확인할 수 없습니다") from None
