# 개인 승인 본문 암호화·키 관리 (W03-06)

관련 #25. 가상 키로 SQLite·실제 개발 PostgreSQL 저장/복호화를 검증했다. 운영 키 등록·접근권한·분리 백업/복원
증거는 #94에서 확인해야 하므로 이 이슈를 운영 검증 완료로 처리하지 않는다.

## 암호화 봉투와 대상 결합

`app.core.encryption`은 cryptography의 AESGCM(256비트 키, 128비트 태그)을 사용한다.
암호화마다 `secrets.token_bytes(12)`로 새 nonce를 만들고 호출자가 nonce를 지정하지 못하게 한다.
태그는 ciphertext 끝에 포함한다. 저장 값은 ciphertext·nonce·key_id·algorithm·schema_version뿐이다.
평문이나 root key를 DB에 넣는 메서드는 없다. 평문은 bytes 1~262,128바이트까지만 받는다.
신고처럼 더 작은 DB 한도가 있는 대상은 저장 서비스가 별도 크기 제한을 적용한다.

서버가 소유권·승인 상태를 확인한 뒤 `ContentTarget(owner_id, kind, document_id, version,
schema_version)`을 구성한다. kind는 profile/application/report다. 해당 값과 고정 domain,
알고리즘, key_id를 정렬한 canonical JSON AAD로 결합한다. 복호화할 때도 DB의 같은 대상
메타데이터로 재구성하고 요청자가 보낸 소유자나 대상 값으로 대체하지 않는다.

HKDF-SHA256으로 root key에서 종류·소유자·문서·버전·스키마별 256비트 AES 키를 파생한다.
서로 다른 대상은 실제 AES 키가 달라져 같은 root 버전을 사용하더라도 종류 사이의 nonce 공간을
분리한다. 같은 대상에 다시 암호화할 때도 nonce를 새로 만든다. HKDF는 고엔트로피 root key용이며
비밀번호를 root key로 쓰거나 직접 암호 알고리즘을 구현하지 않는다.

암호문/nonce/AAD/키가 바뀌면 InvalidTag를 원문 없는 ProtectedContentError로 바꾼다.
키가 없거나 설정이 잘못되면 EncryptionUnavailable로 실패하며 임의 키 생성·평문 저장·다른 키
추측 복호화로 대체하지 않는다. 서비스는 이 내부 예외를 고정 오류 응답으로 변환해야 한다.
암호화 함수는 API 인증·동의·승인·자격을 검사하거나 자동 저장하지 않는다.

## 설정과 회전

DATA_ENCRYPTION_KEYS는 키 ID를 base64 32바이트 root key에 연결한 JSON이고
DATA_ENCRYPTION_ACTIVE_KEY_ID는 새 암호화에 사용할 ID다. 키 ID는 소문자 영숫자·점·밑줄·하이픈,
1~128자다. 중복 JSON 키·잘못된 base64·짧은 키·없는 활성 ID를 거절한다. 최대 10개 버전을 받는다.
Settings의 SecretStr와 KeyRing의 SecretBytes로 repr 노출을 막는다. 실제 키 값을 예제·로그·
테스트·커밋에 넣지 않는다. 키 생성은 OS의 암호학적 난수를 사용한다.

개발자는 안전한 로컬 터미널에서 `python -c "import base64,secrets; print(base64.b64encode(secrets.token_bytes(32)).decode())"`로
키를 만들 수 있다. 생성 결과를 대화/공유 로그에 붙이지 않고 개인 `.env`에만 등록한다.
운영은 비밀 관리 경로에서 실행 환경으로 제공하고 DB/RDS 스냅샷·소스 패키지와 키 백업을 분리한다.
현재 코드는 환경 설정을 읽는 adapter이며 AWS 비밀 관리·권한·감사·배포는 구성하지 않는다.

회전은 새 ID/키를 추가하고 active ID를 바꾼다. 기존 봉투는 자신의 key_id로 복호화되므로
원문·버전을 덮어쓰지 않아도 된다. 동일 ID의 키 bytes를 바꾸면 과거 자료가 복호화되지 않으므로
ID를 재사용하지 않는다. 보관 중인 암호문과 7일 백업이 참조하는 이전 키를 임의 폐기하지 않는다.
키 침해 후 자료 재암호화/키 폐기는 별도의 승인된 복구 절차와 저장본 불변 정책 검토가 필요하다.

복구는 분리 보관한 키 버전과 DB 백업을 각각 복원한 후 가상/승인 표본의 복호화, 변조 거절,
최신 삭제 이력 재적용을 확인한다. 테스트는 새 KeyRing 인스턴스와 회전 후 active 키로 이 경로를
재현하지만 실제 운영 키의 분리 백업 성공을 증명하지 않는다.

Python 메모리에서 bytes 복사본을 완전히 지우는 것을 보장하지 않는다. 프로세스/디버거/덤프/
환경 접근권한도 운영에서 제한해야 한다. 암호화가 서비스의 읽기 권한 검사를 대체하지 않는다.

## 검증과 근거

Unicode bytes 라운드트립, 같은 대상의 새 nonce, 암호문/nonce·키 ID·알고리즘·소유자·종류·
문서/스키마/버전 변조 거절, 키 회전·분리 인스턴스 복구·키 없음·잘못된 키, 크기/형식·설정
오류 비노출과 실제 ProfileVersion 저장/복호화를 검증한다. 테스트 키는 실행마다 생성한다.

2026-10-17 KST [PostgreSQL/Redis·암호화 통합 CI](https://github.com/YongSamGo/RE_CONNECT/actions/runs/38941711480)에서
113개 시험이 통과했다. 운영 키 백업이나 RDS 배포의 증거로 대신하지 않는다.

Security/INDEX.md → 다음 Python 구현 원문을 적용했다. 모두 저장소 상대경로이며
제2장 제2절 보안기능이다:

- `team-vault/SW개발보안_obsidian/Security/Python-2023/제2장-시큐어코딩-가이드/제2절-보안기능/026-4.-취약한-암호화-알고리즘-사용.md`: 4항, PDF 83~86쪽.
- 같은 디렉터리 `027-5.-암호화되지-않은-중요정보.md`: 5항, PDF 87~90쪽.
- 같은 디렉터리 `028-6.-하드코드된-중요정보.md`: 6항, PDF 91~93쪽.
- 같은 디렉터리 `029-7.-충분하지-않은-키-길이-사용.md`: 7항, PDF 94~96쪽.

진단 관점의 중요정보 저장·접근 경계는 [영구 모델 기록](../data/persistence.md#보안-원문-연결)의
2021 진단가이드 제4장 제2절 5항, PDF 337~349쪽과 구분해 검토했다.
AESGCM/AAD/InvalidTag와 HKDF 사용은 [cryptography AEAD](https://cryptography.io/en/latest/hazmat/primitives/aead/),
[HKDF 공식 문서](https://cryptography.io/en/latest/hazmat/primitives/key-derivation-functions/#hkdf)를 확인했다.
가이드의 예제 코드·과거 알고리즘 권고를 그대로 쓰지 않았다. 대상별 파생·봉투 형식·키 버전/복구
절차·보관기간은 프로젝트 설계이며 공식 가이드가 이 스키마를 정한 것은 아니다.
