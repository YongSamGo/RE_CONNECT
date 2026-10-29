# 다시잇다 로고 사용

## 공식 원본

- 바탕화면 심볼 원본: `brand/source/logo-symbol-original.png`
- 이전에 제공된 브랜드 보드: `brand/source/original-reference.png`
- 웹 상단 락업: `brand/logos/original/lockup-with-background.png`
- 심볼: `brand/symbols/original/symbol-with-background.png`

바탕화면 원본 심볼 PNG를 변형 없이 보존합니다. 이전에 제공된 브랜드 보드도 별도 보존합니다. 현재 자산은 실제 벡터가 아닌 PNG 래스터이며 원본의 옅은 블루 배경을 포함합니다.

## 사용 원칙

- 워드마크를 텍스트나 유사 글꼴로 다시 입력하지 않습니다.
- 심볼의 곡선, 겹침, 그라데이션, 하이라이트를 재구성하지 않습니다.
- 배경 제거, 색 변경, 윤곽·비율 변경을 하지 않습니다.
- 비율을 유지해 크기를 조절하고, 자르거나 늘리지 않습니다.
- 밝은 배경 자산을 어두운 배경 위에 직접 사용하지 않습니다.
- PNG를 SVG로 포장하거나 벡터라고 표기하지 않습니다.
- 새 원본의 품질이 확인되기 전까지 투명·다크·모노크롬 로고를 공식 자산으로 만들지 않습니다.

## 웹 사용

React 공통 헤더는 `/brand/symbols/dasieitda-symbol.png` 심볼 PNG와 에스코어 드림으로 렌더링하는 큰 `다시잇다` 텍스트를 조합합니다. 슬로건은 헤더에 표시하지 않습니다. 원본 심볼 이미지의 옅은 배경은 투명화하지 않고 페이지의 밝은 블루 배경과 함께 사용합니다. `logos/original/lockup-with-background.png`는 이전 슬로건이 있는 초기 제공 이미지의 보관본입니다. 탭 아이콘은 별도 래스터 PNG입니다.
