# 다시잇다 브랜드 자산

이 폴더는 사용자가 선택한 로고 이미지를 보존하고 서비스에서 재사용하기 위한 자료입니다. 현재 상단 심볼의 원본은 사용자의 바탕화면 `logo/logo-symbol-original.png`이며 `source/logo-symbol-original.png`에 바이트 그대로 보존했습니다. 대화에서 먼저 제공된 1536×1024 브랜드 보드도 `source/original-reference.png`에 변형 없이 보존합니다.

## 현재 자산

- `logos/original/lockup-with-background.png`: 처음 제공된 이미지에서 자른 기존 락업 보관본. 이전 슬로건과 밝은 배경을 포함합니다.
- `symbols/original/symbol-with-background.png`: 바탕화면 원본 `logo-symbol-original.png` 그대로인 335×333 PNG. 밝은 원본 배경을 포함합니다.
- `icons/app/app-icon-256.png`: 심볼 크롭을 256×256으로 축소한 앱 아이콘.
- `icons/favicon/favicon-64.png`, `favicon-32.png`, `favicon-16.png`: 심볼 크롭에서 원본 해상도 이하로 축소한 파비콘 크기별 PNG.
- `tokens/`: 초기 브랜드 팔레트와 UI 색상 역할.
- `docs/`: 사용 규칙과 작업 경계.
- `previews/asset-gallery.html`: 로컬 자산 미리보기.

웹 앱은 `frontend/public/brand/symbols/dasieitda-symbol.png`에서 바탕화면 원본 심볼 PNG를 표시합니다. 상단 워드마크는 에스코어 드림 UI 글꼴로 표시하고 슬로건은 노출하지 않습니다. 원본·마스터 자산은 이 폴더를 기준으로 보관합니다.

## 원본과의 차이 및 한계

상단에서 사용하는 심볼은 바탕화면 원본 파일을 그대로 복사한 래스터 PNG입니다. 재구성·크롭·색 변경·투명화를 하지 않았으며, 외곽에 원본의 옅은 블루 배경이 남아 있습니다. 벡터 자산이 아닙니다.

첨부 이미지는 앱 아이콘 예시도 포함하지만, 별도의 무배경 원본이 제공되지 않아 심볼 크롭을 앱/파비콘의 보수적인 대체 자산으로 사용합니다. 어두운 배경용·투명·단색 로고는 제작하지 않았습니다. 배경 제거가 원본 픽셀을 훼손할 수 있기 때문입니다.

원본 PNG를 교체하거나 크롭을 다시 만들 때는 승인된 새 원본을 먼저 보존하고, 기존 파일을 덮어쓰기 전에 백업합니다.
