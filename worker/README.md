# worker — 공고 출처 조사 도구

`tools/`에는 W01-05에서 만든 출처 조사용 일회성 도구가 있다. 표준 라이브러리만 쓴다.

```bash
python worker/tools/fetch_source_samples.py senuri --operation getJobList
```

키는 루트 `.env`에서 읽고, 받은 원본은 커밋하지 않는 `worker/samples/`에 저장한다 ([출처 조사](../docs/data/sources.md)).

운영 공고 수집기는 이 폴더가 아니라 [backend](../backend/README.md) 안의 모듈로 만든다 ([#44](https://github.com/YongSamGo/RE_CONNECT/issues/44)~[#47](https://github.com/YongSamGo/RE_CONNECT/issues/47)). API와 같은 공통 타입을 쓰기 위해서다.
