# 공공 API 수집과 정규화

`fetch.py`는 고정 대상·DNS/IP·TLS·본문/XML 상한을 검사한다. [수집 경계](../../../../docs/data/safe-fetch.md)를 따른다.

`normalize.py`는 안전 파싱한 목록/상세 item을 `OpportunityContent` 검수 대기 후보로 바꾼다. [정규화 계약](../../../../docs/data/normalization.md)을 따른다. 중복 필드를 덮어쓰거나 원문을 로그에 넣지 않는다.

`runner.py`/`runs.py`는 실행/중복 제어/예산과 SQL 저장을 연결한다. `python -m app.collect`와 [실행 안내](../../../../docs/data/ingestion-runs.md)를 따른다. 후보 생성과 공개 승인을 구분하며 실제 키·개인정보 원문을 로그에 넣지 않는다.
