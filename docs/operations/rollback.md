# 롤백 (#97 W12-08)

문제가 생긴 릴리스를 이전 릴리스로 되돌리는 절차다. 배포 절차는 [infra/deploy/README.md](../../infra/deploy/README.md) 6절을 그대로 쓰고,
여기서는 **되돌려도 되는지 판단하는 기준**과 **판정별 절차**만 정한다.

## 1. 원칙: 운영 DB는 downgrade하지 않는다

운영에서는 `alembic downgrade`를 실행하지 않는다. 마이그레이션의 downgrade는 개발·CI 재현용이다([개발 DB](../data/development-db.md)).
지금 있는 downgrade 대부분이 표나 열을 지운다. 예를 들면 다음과 같다.

| 마이그레이션 | downgrade가 지우는 것 | 운영에서 생기는 일 |
| --- | --- | --- |
| `0006_deletion_generations` | 삭제 기록의 세대·종류, 회원 세션 세대 | 탈퇴·삭제 보장과 이전 세션 차단이 깨진다 |
| `0010_operator_mfa` | 운영자 MFA 비밀값, MFA 감사 기록 | 운영자 MFA가 풀리고 30일 감사 기록이 사라진다 |
| `0011`·`0012`·`0013` | 운영자 쓰기 기록, 검수 기록, 신고 처리 결과 | 운영 이력이 사라진다 |

그래서 이전 릴리스로 돌아갈 때 DB는 그대로 두고 **이미지만** 되돌린다.
이미지만 되돌릴 수 없으면 배포 직전 스냅샷에서 복원하고 최신 삭제 이력을 다시 적용한다(4절).

## 2. 판정: `rollback-check`

운영 중인 릴리스의 태그 체크아웃(`/opt/reconnect`)에서 실행한다. 이 체크아웃의 마이그레이션 폴더로 두 릴리스 사이의 경로를 계산한다.

```bash
cd /opt/reconnect   # 지금 운영 중인 vA.B.C 태그 체크아웃
install -d -m 700 /run/reconnect/rollback
cp /run/reconnect/release-manifest.json /run/reconnect/rollback/current.json
curl -fsSL --proto '=https' -o /run/reconnect/rollback/target.json \
  https://github.com/YongSamGo/RE_CONNECT/releases/download/vX.Y.Z/release-manifest.json
python3 -I infra/release/release_manifest.py rollback-check \
  --current /run/reconnect/rollback/current.json --target /run/reconnect/rollback/target.json
```

먼저 DB가 실제로 current 릴리스의 head에 있는지 본다. 배포 중 migrate가 실패했다면 manifest와 DB가 다를 수 있다.

```bash
docker compose --env-file /run/reconnect/images.env -f infra/compose.prod.yaml run --rm \
  --entrypoint /opt/venv/bin/python migrate -B -m alembic current
```

이 명령에는 migrate env 파일(`/run/reconnect/migrate.env`)이 필요하다. 확인 뒤 지운다.
출력 revision이 current manifest의 `migrations.heads`와 다르면 판정을 믿지 않는다. 공개를 막고 원인부터 확인한다.

| 종료 코드 | `verdict` | 뜻 | 다음 |
| --- | --- | --- | --- |
| 0 | `images_only` | 두 릴리스의 스키마가 같다 | 3절 |
| 0 | `schema_compatible` | target 이후 마이그레이션이 모두 `rollback_safe = True`다 | 3절. DB는 새 스키마 그대로 둔다 |
| 2 | `restore_required` | 이전 앱이 동작한다고 확인하지 않은 마이그레이션이 있다(`not_rollback_safe`) | 4절 |
| 1 | — | 판정 불가: manifest 변조·형식 오류, 체크아웃이 current 태그가 아님, target이 더 새 릴리스이거나 다른 갈래 | 되돌리지 않는다. 원인 확인 |

출력의 `models_changed`·`compose_changed`·`prompts_changed`는 두 릴리스에서 해시나 버전이 다른 항목이다. 3절에서 쓴다.

## 3. 이미지 되돌리기 (`images_only`, `schema_compatible`)

1. **공개 차단 여부:** 개인정보가 잘못 보이거나 저장되는 문제면 먼저 Nginx에서 API를 닫는다([runbook](runbook.md) 2절). 기능 오류만이면 열어 둔 채 진행해도 된다.
2. **체크아웃 전환:** `/opt/reconnect`를 target 태그로 바꾼다. 타이머도 이 경로의 Compose 파일을 쓴다([scheduler](../../infra/scheduler/README.md)).
   `compose_changed`가 비어 있지 않으면 이 단계가 필수다.
3. **이미지·env:** deploy README 6절대로 target manifest로 `images.env`를 다시 만들고 세 이미지의 빌드 출처 증명을 확인한다.
   target 릴리스의 `render_env.py`로 SSM env 파일을 다시 렌더링한다. 받는 설정 이름이 릴리스마다 다를 수 있다.
4. **migrate는 실행하지 않는다.** grant도 다시 하지 않는다.
5. **모델 재준비:** `models_changed`가 있으면 target 릴리스의 모델 manifest로 가중치를 다시 검증하고 미리 적재한다.
   운영 모델 구성은 #92(PR #311)가 병합된 뒤 그 절차를 여기에 연결한다. 그 전에는 모델이 바뀐 롤백을 하지 않는다.
6. `docker compose --env-file /run/reconnect/images.env -f infra/compose.prod.yaml up -d --wait`
7. **확인:** `/health/ready`가 `status=ready`이고 db·redis·llm·speech가 각각 `ok`인지 본다. `degraded`도 HTTP 200이므로 본문을 확인한다.
   그 뒤 공개 공고 조회와 대표 업무 요청 하나를 실제로 실행한다. `systemctl list-timers 'reconnect-*'`로 타이머가 남아 있는지 본다.
8. **기록:** current·target 태그, verdict, 실행 시각, 확인 결과를 [handover.md](handover.md) 형식으로 남긴다.
   `prompts_changed`가 있으면 그 사이에 만든 생성 결과의 프롬프트 버전이 다르다는 것도 적는다.

## 4. 스냅샷 복원이 필요한 경우 (`restore_required`)

이전 앱을 새 스키마에 붙이지 않는다. 다음 중 하나를 고른다.

- **고쳐서 앞으로 배포(우선):** 문제를 고친 새 릴리스(vA.B.C+1)를 정상 절차로 만든다. 데이터가 사라지지 않는다.
  그동안 문제가 개인정보에 닿으면 API를 닫아 둔다.
- **스냅샷 복원:** 문제 릴리스의 migrate 직전에 만든 수동 스냅샷을 [백업·복원 체크리스트](../security/backup-restore.md#복원-체크리스트)대로
  격리 복원하고 최신 삭제 이력을 다시 적용한다. 그 뒤 복원 DB에 target 릴리스 이미지를 3절 절차로 붙인다.
  **스냅샷 이후에 생긴 회원 저장분은 사라진다.** 삭제·철회는 삭제 이력으로 다시 적용되지만, 새로 저장한 프로필·지원서는 돌아오지 않는다.
  이 손실을 감수할지는 운영 책임자가 정하고 이용자 안내 여부도 함께 정한다([handover.md](handover.md)).

어느 쪽이든 복원 DB를 운영에 연결하기 전에 `manage_deletions.py recover`가 `completed: true`인지 확인한다.

## 5. 마이그레이션 작성 규칙 (expand → contract)

이미지 되돌리기가 가능하려면 마이그레이션을 "추가 먼저, 삭제는 다음 릴리스"로 나눈다.
새 마이그레이션 템플릿(`backend/migrations/script.py.mako`)은 `rollback_safe = False`를 넣는다.
리뷰에서 아래 조건을 확인한 경우에만 `True`로 바꾼다.

**`rollback_safe = True`로 둘 수 있는 변경** — 바로 앞 릴리스의 앱이 그대로 읽고 쓴다.

- 새 표·새 인덱스 추가
- NULL 허용이거나 서버 기본값이 있는 열 추가
- 이전 앱이 읽어도 의미가 같은 데이터 보정(예: 시드 별칭 추가)

**`False`로 두는 변경** — 이전 앱이 실패하거나, 삭제·권한 보장이 약해진다.

- 열·표 삭제나 이름 변경, 형식 축소
- NOT NULL·CHECK·고유 제약·트리거 추가처럼 이전 앱의 쓰기를 막는 변경
- 이전 앱이 모르는 값을 쓰고 이전 앱이 그 값을 잘못 해석하는 변경(삭제·철회 상태, 역할·권한 값 등)

열 삭제는 다음과 같이 두 릴리스로 나눈다. 1) 새 열을 추가하고 앱이 새 열을 쓰게 바꾼다(`True`). 2) 다음 릴리스에서 옛 열을 지운다(`False`).
2번은 직전 릴리스로만 되돌릴 수 있고, 그 직전 릴리스는 이미 옛 열을 쓰지 않는다. 그래도 판정이 `restore_required`이면 4절을 따른다.

`0001`~`0014`에는 표시가 없다. 모두 첫 운영 릴리스보다 앞서므로 되돌리기 판정에 영향이 없다. 첫 릴리스가 기준점이 된다.
