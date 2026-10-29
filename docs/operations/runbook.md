# 운영 절차: 장애·키·권한·비용 (#97 W12-08)

서버 명령은 모두 운영 EC2의 root 셸(Session Manager)에서, 릴리스 태그 체크아웃(`/opt/reconnect`)을 기준으로 실행한다.
관리 명령은 backend 이미지에서 실행한다([deploy README](../../infra/deploy/README.md) 4절의 `manage_*.py` 실행 형식).
출력은 터미널에서만 보고 저장소·이슈·채팅에 붙이지 않는다.

## 1. 상태 확인

backend의 `/health/ready`는 구성요소별 `ok`/`fail`과 전체 상태를 준다.

| 전체 상태 | 뜻 | 이용자에게 보이는 것 |
| --- | --- | --- |
| `ready` | db·redis·llm·speech 모두 `ok` | 전체 기능 |
| `degraded` | 필수 구성요소는 정상, AI·음성 중 일부 `fail` (HTTP 200) | 공개 공고 조회·직접 작성은 되고 AI·음성 기능은 쓸 수 없다 |
| `unavailable` | DB나 Redis 같은 필수 구성요소 `fail` | 서비스 전체 503 |

`degraded`도 HTTP 200이므로 상태 코드만 보고 정상으로 판단하지 않는다.
수집 상태는 운영자 화면의 `GET /admin/operations`, 주기 작업은 `systemctl list-timers 'reconnect-*'`로 본다([scheduler](../../infra/scheduler/README.md)).

## 2. 장애별 첫 조치

| 상황 | 먼저 할 일 | 하지 않을 일 |
| --- | --- | --- |
| 개인정보가 잘못 보이거나 저장되는 의심 | Nginx에서 API를 닫는다. 운영 책임자·개인정보 보호책임자에게 알린다([handover](handover.md)). 증거는 건수·시각·릴리스만 남긴다 | 원문·식별자를 이슈나 채팅에 붙이지 않는다 |
| 새 릴리스 직후 오류 | [rollback.md](rollback.md)의 `rollback-check`로 판정 | `alembic downgrade` |
| DB 접속 실패(`unavailable`) | RDS 상태(중지·재시작·저장 공간)와 보안 그룹, `verify-full` 인증서 경로를 확인한다 | 인증서 검사를 끄거나 runtime 계정에 권한을 더하지 않는다 |
| Redis 실패 | `docker compose ... ps`로 redis 재시작 여부를 본다. Redis는 비영속이라 다시 켜지면 세션·체험·요청 한도가 비워진다. 이용자는 다시 로그인한다 | 요청 한도·동의 검사를 우회하는 설정 변경 |
| 모델·음성 실패(`degraded`) | 공개 조회가 유지되는지 확인하고 모델 서비스 로그와 GPU 상태를 본다. 다시 띄운 뒤 `ready`를 확인한다 | 외부 AI로 바꿔 보내지 않는다 |
| 추론 슬롯이 계속 차 있음 | 모든 LLM/STT/TTS 런타임이 멈췄는지 확인한 뒤 `manage_inference.py status`, 같은 lease일 때만 `release`([추론 제한](../security/inference-admission.md)) | `redis-cli`로 키를 직접 지우지 않는다 |
| 수집 실패 | 마지막 성공 공개본이 유지되는지 확인한다. 실패 출처·코드를 보고 출처 키·요청 한도를 확인한다 | 실패를 이유로 공고를 수동 종료하지 않는다 |
| 보관 정리 실패(`failed`, `incomplete`) | `journalctl -u reconnect-retention.service`로 어느 단계인지 보고 `systemctl start`로 다시 실행한다. `incomplete`는 다음 실행에서 이어진다 | 정리 대상을 DB에서 직접 지우지 않는다 |
| EC2 재부팅 | `/run/reconnect`가 비어 있다. deploy README 6절대로 env 파일을 다시 만들고 `up -d --wait`, 그 뒤 두 타이머 서비스를 한 번 실행한다 | env 파일을 디스크에 영구 저장하지 않는다 |
| 복원이 필요함 | [백업·복원 체크리스트](../security/backup-restore.md#복원-체크리스트)대로 공개 차단 → 격리 복원 → 키 연결 → 삭제 재적용 | 삭제 재적용 전에 공개하지 않는다 |

## 3. 키·비밀값 교체

모든 값은 SSM `SecureString`에서 바꾸고, env 파일을 다시 렌더링한 뒤 `up -d --wait`로 반영한다([deploy README](../../infra/deploy/README.md) 5·6절).
교체한 시각과 이름만 기록하고 값은 남기지 않는다.

| 비밀값 | 교체 방법 | 주의 |
| --- | --- | --- |
| `DATA_ENCRYPTION_KEYS`·`_ACTIVE_KEY_ID` | 새 ID의 키를 **추가**하고 active ID를 바꾼다([암호화](../security/encryption.md#설정과-회전)). 분리 보관 사본도 같이 갱신한다 | 이전 키를 지우지 않는다. 7일 자동 백업과 29일 이내 스냅샷이 참조한다. ID를 다시 쓰지 않는다 |
| `REQUEST_LIMIT_KEY`·`INFERENCE_CONTROL_EPOCH` | 런타임을 멈추고 Redis 제어 레코드를 새 값에 맞춰 다시 준비한다([추론 제한](../security/inference-admission.md#설정과-제어-레코드-준비)) | 제어 레코드와 다르면 사적 한도·추론이 503이 된다 |
| `REDIS_PASSWORD` | redis·app 두 env 파일을 함께 다시 만들고 둘 다 재시작한다 | Redis가 다시 켜지며 세션이 비워진다 |
| DB 비밀번호(runtime·migrator) | RDS에서 바꾼 뒤 SSM의 `DATABASE_URL`을 갱신한다. migrator는 배포 때만 쓴다 | runtime과 migrator 계정을 섞지 않는다 |
| 카카오 client secret | 카카오 개발자 콘솔에서 재발급 → SSM 갱신 → 재시작 → 로그인 왕복 확인 | redirect URI는 `PUBLIC_ORIGIN`과 같아야 한다 |
| `DATA_GO_KR_SERVICE_KEY` | 공공데이터포털 재발급 → SSM 갱신. 다음 수집에서 성공 여부 확인 | — |

키가 노출됐다고 의심되면 교체 전에 API를 닫는다. 노출된 암호화 키로 만든 자료의 재암호화·폐기는 별도로 승인받아 진행한다(암호화 문서).

## 4. 권한

- **운영자:** 부여·회수·MFA 복구는 `manage_operators.py`(`grant`·`enroll`·`reset-mfa`·`revoke`)로만 한다([운영자 MFA](../security/operator-mfa.md)).
  회수하면 그 사람의 모든 세션이 바로 끊긴다. `mfa.lock` 감사가 생기면 본인 시도인지 확인하고, 아니면 `revoke`한다.
- **팀원이 빠질 때:** AWS IAM 사용자·Session Manager 접근, SSM 읽기 권한, GitHub 저장소 권한과 `release` 환경 승인자 목록,
  카카오·공공데이터포털 콘솔 권한을 회수한다. 그 사람이 본 적 있는 비밀값은 3절로 교체한다.
- 운영자 회수는 `role.revoke` 감사 기록(30일 보관)이 남는다. 회수한 계정으로 관리 API를 다시 호출하면 401인지 확인한다.

## 5. 비용과 자원 종료

AWS Budgets는 알림만 보낸다. 지출을 막지 않는다. 종료는 담당자가 직접 확인한다([AWS 준비](../infra/aws.md)).

- 시험이 끝나면 EC2(GPU 포함)를 중지하고 실제로 `stopped`인지 확인한다.
- **RDS는 중지해도 7일 뒤 자동으로 다시 켜진다.** 2026-10-29 조회 기준 다음 자동 재시작은 **2026-11-04 23:54 KST**다.
  그 전에 계속 둘지, 다시 중지할지, 최종 스냅샷을 남기고 지울지 정한다(담당은 [handover](handover.md) 표).
- 중지해도 EBS·스냅샷·고정 IP(EIP)·ECR·S3·로그 보관 비용은 남는다. 종료할 때 각각 확인한다.
- 자원을 지울 때는 대상·보존 필요(백업 29일 규칙, 삭제 이력 30일 잠금)를 확인한 뒤 지운다. 삭제 이력 버킷은 잠금 기간 동안 지울 수 없다.
- GPU 시험의 승인 범위와 비용은 [AWS 실행 전 점검표](../progress/aws-launch-20261029.md)를 따른다.
