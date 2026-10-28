# 공공 API 수집과 정규화

`fetch.py`는 고정 대상·DNS/IP·TLS·본문/XML 상한을 검사한다. [수집 경계](../../../../docs/data/safe-fetch.md)를 따른다.

`normalize.py`는 안전 파싱한 목록/상세 item을 `OpportunityContent` 검수 대기 후보로 바꾼다. [정규화 계약](../../../../docs/data/normalization.md)을 따른다. 중복 필드를 덮어쓰거나 원문을 로그에 넣지 않는다.

`runner.py`/`runs.py`는 실행/중복 제어/예산과 SQL 저장을 연결한다. `python -m app.collect`와 [실행 안내](../../../../docs/data/ingestion-runs.md)를 따른다. 후보 생성과 공개 승인을 구분하며 실제 키·개인정보 원문을 로그에 넣지 않는다.

`manual.py`는 공식 자료 수동 입력의 필수 근거·상세 주소·시각을 검사하고 pending 버전과 최소 근거를 함께 저장한다. `python -m app.manual_intake`와 [수동 입력 안내](../../../../docs/data/manual-intake.md)를 따른다. 20건 목표 집계는 후보·검수 승인을 구분하며 실제로 확보하지 못한 자료를 만들지 않는다.
