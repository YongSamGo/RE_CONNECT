# 주기 수집·보관 정리 타이머 (W12-07 · #96)

EC2 호스트의 systemd timer가 운영 Compose의 FastAPI 이미지로 일회성 작업 컨테이너를 띄운다. 앱 프로세스 안에 스케줄러를 두지 않는다. API 재시작·배포와 작업 수명을 분리하고, 같은 이미지·설정·비밀 주입(#93)을 그대로 쓰기 위해서다.

| 타이머 | 주기 | 실행 명령 | 하는 일 |
| --- | --- | --- | --- |
| `reconnect-collect.timer` | 15분마다 | `python -m app.collect --all-due` | 활성 출처 전체를 차례로 `--due` 실행. 실제 수집 여부는 DB가 정한다(성공 후 6시간, 실패 후 15분) |
| `reconnect-retention.timer` | 매일 03:30 KST | `python manage_retention.py run` | 삭제 이력·종결 신고 설명·감사 기록의 30일 정리 |

일반 운영 로그 14일은 이 타이머가 아니라 CloudWatch 로그 그룹 보관 설정이 맡는다([infra/logging](../logging/)).

## 동작 기준

- **출처 한도 우선:** 15분은 "확인" 주기다. 출처 일일 한도·실행당 요청 상한·같은 출처 잠금은 명령 안에서 지키며 타이머가 우회하지 못한다([수집 실행 안내](../../docs/data/ingestion-runs.md)).
- **실패 시 마지막 성공 유지:** 실패·중단은 출처의 `last_success_at`과 기존 공개본을 바꾸지 않는다. 한 출처가 실패해도 다음 출처는 계속 실행하고, 하나라도 실패하면 종료 코드 1로 서비스가 `failed`가 된다.
- **마감 갱신:** 공고 마감은 조회·추천 시점에 `assess_lifecycle`이 판정한다. 마감일이 지나면 별도 배치 없이 즉시 종료로 보이고, 정상 확인이 48시간을 넘으면 추천을 보류한다. 수집 실패·누락만으로 공고를 종료로 바꾸지 않는다. 그래서 마감용 배치를 따로 두지 않는다.
- **보관 정리:** 각 정리 명령을 별도 프로세스로 차례로 실행한다. 한 단계가 실패해도 다음 단계는 계속하고, `failed`·`missing`·`incomplete`가 하나라도 있으면 종료 코드 1이다. 100건 단위 명령은 한 실행에서 최대 20번 반복하고, 남으면 `incomplete`로 알리고 다음 날 이어서 지운다.
- **재시작:** `Persistent=true`라서 재부팅이나 중지 동안 놓친 실행을 부팅 뒤 한 번 실행한다. 수집이 중간에 끊겨도 저장된 지역·페이지에서 재개하고, 끊긴 실행은 다음 잠금 소유자가 `cancelled`로 마무리한다.
- **출력:** 상태·실행 UUID·고정 코드·처리 건수만 출력한다. 하위 명령의 stderr·예외 원문·연결 정보는 옮기지 않는다. 출력은 journald와 Docker 로그 드라이버를 거쳐 운영 로그 그룹(14일)으로 간다.

## 설치 (EC2, 운영 Compose 배포 후)

운영 Compose 파일·서비스 이름·비밀 주입은 #93에서 정한다. 아래 예시는 저장소를 `/opt/re-connect`에 두는 경우다.

```bash
sudo install -d -m 0750 /etc/re-connect
sudo install -m 0600 infra/scheduler/scheduler.env.example /etc/re-connect/scheduler.env
sudo install -m 0644 infra/scheduler/reconnect-*.service infra/scheduler/reconnect-*.timer /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now reconnect-collect.timer reconnect-retention.timer
```

`scheduler.env`에는 경로·Compose 파일·서비스 이름만 둔다. 서비스 키·DB 비밀번호는 넣지 않는다.

## 운영 확인

```bash
systemctl list-timers 'reconnect-*'
systemctl status reconnect-collect.service reconnect-retention.service
journalctl -u reconnect-collect.service -n 20 --no-pager
sudo systemctl start reconnect-retention.service
```

수집 장애는 운영자 화면의 `GET /admin/operations`(출처별 마지막 성공·연속 실패·신선도, #55)에서도 확인한다. 정리 작업의 실패는 서비스 `failed` 상태와 로그로 확인한다.

## 검증 범위

- 단위 시험(`backend/tests/test_scheduled_jobs.py`): 활성 출처만 코드 순서로 실행, 한 출처 예외 뒤에도 계속 실행·원문 비노출, 정리 단계 반복·실패 격리·누락 명령 보고, 하위 명령 JSON 신뢰 조건, 타이머가 실제 명령을 부르는지 확인한다.
- 로컬 실측(2026-10-28, 개발 Compose PostgreSQL·Redis + Linux `python:3.12-slim` 컨테이너):
  - 출처 2개에 `--all-due`를 시험용 키로 실행하면 두 출처 모두 `source_unavailable` 실패, 종료 1, `last_success_at`은 그대로였다. 곧바로 다시 실행하면 두 출처 모두 `skipped`, 종료 0으로 15분 재시도 간격을 지켰다.
  - `manage_retention.py run`은 만료된 삭제 이력 1건만 지우고 유효한 1건을 남겼다. 다시 실행하면 0건이었다. 감사 기록 정리(`manage_audit.py`, #271)가 아직 없어 `missing`, 종료 1로 보고했다.
- **미검증:** EC2에서의 systemd 타이머 실행, 재부팅 뒤 놓친 실행, 운영 Compose의 `docker compose run`. 운영 Compose(#93)와 EC2가 준비된 뒤 위 "운영 확인" 명령으로 확인한다.
