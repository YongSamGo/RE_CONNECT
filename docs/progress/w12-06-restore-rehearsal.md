# W12-06 복원 후 삭제 재적용 진행 기록

[진행 상태 기록 양식](../progress.md#기록-방법)을 따른다. 절차는 [복원 체크리스트](../security/backup-restore.md#복원-체크리스트)에 있다.
이 기록은 **로컬 리허설**이다. 운영 RDS 스냅샷·S3 버킷에서 실행한 증거가 아니므로 이슈를 통과로 옮기지 않는다.

```text
작업: #95 / W12-06
담당·협력: C(SeungwonKwon) · 협력 없음
상태·확인 시각(KST)·확인자: 진행 · 2026-10-29 · SeungwonKwon
코드 작성 / 계약 예제 연결 / 실제 연동 / 배포 검증: 공개 전 확인 도구·1회성 서비스·로컬 리허설 완료 / 해당 없음 / 미검증 / 미검증
commit·PR·CI: 기준 develop dfcba3e. PR·CI는 이 기록을 추가한 PR에서 확인
환경: 로컬 Windows의 Linux 컨테이너(Python 3.12), PostgreSQL 16·Redis 7(infra/compose.dev.yaml),
  잠금 S3 에뮬레이터 LocalStack 4.4.0(버전 관리·Object Lock GOVERNANCE 30일), pg_dump/psql 17. 가상 회원 1명
사례 ID / 기대 / 실제 / 판정:
  S3 이력 저장소: 같은 이력 재전송 / 성공 / 성공 / 통과
  S3 이력 저장소: 조건부 덮어쓰기 / 거절 / PreconditionFailed / 통과
  S3 이력 저장소: 잠긴 버전 삭제 / 거절 / AccessDenied / 통과
  test_restore_rehearsal: pg_dump 스냅숏 뒤 지원서 삭제·탈퇴 → 새 DB에 복원
    복원 DB의 회원 자료 표 / 남아 있음 / 8개 표 / 통과
    옛 스키마(head-1)에서 확인 / 재적용 없이 닫힘 / schema_not_current 1 / 통과
    migrate 뒤 재적용 전 확인 / 공개 불가 / 기록 없음 2·대상 남음 2·세션 세대 낮음 2 / 통과
    재적용 뒤 확인 / 공개 가능 / 재적용 2·대기 처리 0·문제 0 / 통과
    읽기 전용 재확인 / 공개 가능 / 공개 가능 / 통과
    회원 흔적(회원 ID·카카오 식별자, 최소 이력 표 제외) / 0 / 0 / 통과
  test_restore_check (SQLite·PostgreSQL 각 9): 삭제 동작 5종 각각 복원 전 막힘·재적용 뒤 열림,
    스냅숏 시점 진행 중 삭제의 대기 처리, 옛 스키마 거절, 종료 코드·한도 / 통과 / 18 통과 / 통과
  같은 시험 + 지원서 삭제 대상 검사 제거 / 실패 / 2 실패 / 시험이 결함을 잡음
  같은 시험 + 세션 세대 검사 제거 / 실패 / 10 실패 / 시험이 결함을 잡음
  manage_restore.py CLI(개발 설정) / 정상 0·옛 스키마 1·이력 저장소 없음 2 / 0·1·2 / 통과
  백엔드 전체 시험(2회) / 통과 / 매회 2167 통과·1 실패·5 건너뜀 / 실패는 회차마다 다른 기존 test_deletions 사례.
    단독 재실행 3회 모두 통과. 이 변경을 뺀 develop 기준 전체 실행도 다른 기존 시험 4건이 간헐 실패해
    로컬 Docker 환경의 기존 간헐 실패로 본다. CI 결과는 PR에서 확인
완료 증거: 위 결과. 건수만 담은 증거 JSON은 security-reports/에 두고 커밋하지 않는다
미구현·미검증·후속 담당:
  실제 RDS 스냅샷 격리 복원·키 분리 복구·운영 S3 버킷에서 restore-check 실행 · #93·#94 운영 증거 뒤 · C
  복원 인스턴스 생성 비용 승인(aws-launch 기록의 현재 승인 범위 밖) · 사용자
차단 원인 / 영향 / 해제 조건 / 해결 담당: 운영 S3 버킷·릴리스 이미지 미게시 / 실제 복구 증거 없음 / #93·#94 운영 검증 / C
다음 확인 시각(KST) / 확인할 대상: 미정 — 담당자 확인 필요 / 운영 버킷 생성 뒤 격리 복원 실행
실제 시작 / 종료 / 제외 시간 / 작업 분 / 작성자: 미기록
기존 목표 / 변경 제안 / 결정자·결정일: G4 10/26 / 없음 / -
재시험 결과: 미실행
```

## 리허설 재현

MinIO 공개 이미지를 받을 수 없어 Object Lock·조건부 쓰기를 지원하는 LocalStack을 썼다.
접근 키는 에뮬레이터용 가짜 값이고 운영 자격증명을 쓰지 않는다. 개발 DB·Redis는 [개발 환경](../development.md)대로 띄운다.

```bash
docker run -d --name rc-s3 --network reconnect-dev_local --network-alias s3 -e SERVICES=s3 localstack/localstack:4.4.0
```

같은 네트워크의 Linux 컨테이너(`pg_dump`·`psql` 설치)에서 백엔드 의존성을 설치하고 실행한다.

```bash
export PERSISTENCE_TEST_DATABASE_URL=postgresql+psycopg://<개발 DB>
export PERSISTENCE_TEST_REDIS_URL=redis://<개발 Redis>
export RESTORE_REHEARSAL_S3_ENDPOINT=http://s3:4566 AWS_ACCESS_KEY_ID=test AWS_SECRET_ACCESS_KEY=test
export RESTORE_REHEARSAL_EVIDENCE=../security-reports/w12-06-rehearsal.json
python -m pytest tests/test_restore_rehearsal.py tests/test_restore_check.py -q
```
