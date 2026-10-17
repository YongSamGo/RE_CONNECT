# 공식 보안 PDF → Obsidian 전사 파이프라인

대상 Vault: `SW개발보안_obsidian` (기존 Vault). 결과: `Security/`. `Security/INDEX.md` 하나가 진입점이며, 인덱스에서 2023 가이드 또는 2021 가이드를 선택하고 전체 장·절 목차 링크로 개별 자료에 접근한다. Obsidian에서 쓰는 페이지 이미지는 `Security/assets/`에 남긴다. 스크립트·캐시·원시 추출물·검증 기록은 `legacy/security_kb/`에 둔다.

## 실행

Python 3.10 이상, PyMuPDF 1.28.2, PyYAML이 필요하다. 이 작업에서는 Codex 번들 Python에 PyMuPDF만 추가 설치했으며 PyYAML은 기존 번들에 있었다.

```powershell
$env:PYTHONIOENCODING='utf-8'
& 'C:\Users\seong\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe' legacy/security_kb/build.py
& 'C:\Users\seong\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe' legacy/security_kb/validate.py
# 최종 검증 및 읽기용 기록 갱신 (validate.py를 별도로 실행할 필요 없음)
& 'C:\Users\seong\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe' legacy/security_kb/report.py
```

`--sample`은 이미지·최종 문서 생성 없이 텍스트·표·코드 구조 캐시와 목차를 점검한다. 대표 페이지 파일과 원본 렌더를 대조한 뒤 전체 생성에 사용했다.

`legacy/security_kb/build.py`는 `legacy/security_kb/data/`의 페이지 추출 캐시와 Vault의 PNG를 재사용하며 동일 파일 내용이면 다시 쓰지 않는다. 중단 후 재실행할 수 있다. 원본 PDF 해시가 바뀌면 캐시 텍스트와 페이지 이미지를 갱신한다. 이 파이프라인은 원본 교체 시 이전 의미 단위 파일을 자동 삭제하지 않는다. 갱신은 파일 목록 비교 후 별도로 검토한다.

## 보존 방식

- 본문은 PDF 텍스트 전사이며 요약·재작성·원문 오류 수정은 하지 않는다.
- 원문 목차와 실제 본문 제목을 대조하여 장·절·개별 보안약점을 분할한다. 진단가이드 부록의 20개 설계 산출물 예시도 원문 소제목을 기준으로 분리한다.
- YAML에 출처·해시·장·절·페이지·분류·태그를 넣는다. 목차의 잘못된 페이지 번호는 `toc_printed_start`와 `actual_printed_start`로 구분한다.
- 코드 블록은 번호가 붙은 줄의 좌표로 재배치한다. 원문 줄번호, 문자열, 연산자, 특수 공백을 보존한다. 원문에 비정상 들여쓰기나 문법 오류가 있어도 고치지 않는다. 코드 블록은 실행용이 아니다.
- 표 장식 오탐을 피하기 위해 `lines_strict`로 검출한다. 병합 셀 없이 5열 이하이며 원문 문자 보존 검사를 통과한 표만 Markdown 표로 표시한다. 복잡한 표는 추출 텍스트 블록과 원본 페이지 이미지를 제공한다. 선이 없는 표·그림은 페이지 이미지로 보존한다.
- 전체 페이지를 144dpi PNG로 렌더하여 텍스트 레이어에 없는 그림·벡터 도식·코드 강조·서식도 보존한다. 페이지 이미지는 각 문서의 접힌 영역에 연결된다. 이미지 수는 원본 삽입 이미지 개수가 아닌 페이지 렌더 수다.
- `legacy/security_kb/data/<book>/extracted/pNNNN.txt`는 수정 없는 페이지별 원시 추출 텍스트다. `.json`에는 좌표·폰트·표·코드 영역이 있다.
- `legacy/security_kb/data/<book>/manifest.json`의 페이지/행/문서 대응표는 원본 행이 정확히 한 문서의 본문에 포함되었는지 검증하기 위한 자료다. 같은 페이지 이미지가 여러 항목에 연결될 수 있지만 본문 행은 중복 배치하지 않는다.
- 원문에 U+0001 등 제어문자가 포함된 곳은 캐시·본문에 그대로 보존하고 검증 기록에 표시한다. 별도 OCR은 적용하지 않았다.
- Python PDF 175페이지의 발행정보는 텍스트 레이어가 없어 `legacy/security_kb/manual-transcriptions.json`에 원본 이미지 직접 대조 전사를 저장했다. 본문에서 자동 추출과 구분하여 표시한다.

## 검증과 한계

검증기는 원본 PDF를 다시 열어 캐시와 비교하고, 실제 생성 Markdown에서 코드·표·헤딩 문법을 제거한 뒤 원본 행의 비공백 문자와 비교한다. 문자 다중집합 검사는 누락·증가 탐지용이며 순서·의미·시각적 충실성을 증명하지 않는다. 별도로 원문 행의 단일 소유, 목차 제목, YAML, 모든 이미지의 디코딩/크기, 링크, 원본 해시와 SQL 삽입·인가·SSRF 탐색 시나리오를 검사한다.

대표 코드·표·다이어그램과 의심 구간은 원본 렌더와 대조한다. 모든 코드의 문법·들여쓰기 또는 모든 셀을 사람이 전수 판독했다고 주장하지 않는다. 상세 결과는 `legacy/security_kb/VALIDATION.md`와 `legacy/security_kb/validation.json`에 있다.

`legacy/security_kb/original-files.json`은 작업 시작 시 기존 11개 파일(PDF, 환영 문서, Vault 설정)의 SHA256 기준값이다. 유지보수 시 기존 파일을 정당하게 바꾼 경우에도 검증기는 차이를 보고하므로 기준값 변경은 별도로 검토한다.
