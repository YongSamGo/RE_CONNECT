# 저장소 관리 도구

## 다음 작업 후보 조회

`project_status.py`는 Python 3.12 표준 라이브러리와 로그인된 GitHub CLI(`gh`)를 사용한다. GitHub 읽기 권한이 필요하다. 이슈·PR을 페이지 끝까지 읽고 표준 출력에 Markdown을 쓴다. 이슈·댓글·브랜치·PR·작업 상태는 변경하지 않는다.

저장소 루트에서 실행한다.

```powershell
python -X utf8 tools/project_status.py
```

스냅샷을 갱신하려면 PowerShell 7에서 다음과 같이 UTF-8로 저장한다. GitHub 조회가 실패하면 기존 파일을 덮어쓰지 않는다.

```powershell
$taskSnapshot = python -X utf8 tools/project_status.py
if ($LASTEXITCODE -eq 0) {
  [System.IO.File]::WriteAllText(
    (Join-Path (Get-Location) 'docs/progress/next-tasks.md'),
    (($taskSnapshot -join "`n") + "`n"),
    [System.Text.UTF8Encoding]::new($false)
  )
}
```

판정 범위와 한계:

- `## 먼저 완료할 작업` 절에서 `- #번호` 형식만 읽는다. 다른 문장·댓글·쉘 명령은 실행하지 않는다.
- 선행 이슈가 열려 있거나 조회에 없으면 `선행 종료 대기`다. 선행 절이 없으면 `선행 정보 확인`이다.
- 선행 이슈가 닫혔으면 `착수 후보·증거 확인`이다. 실제 검증 통과를 뜻하지 않는다.
- PR의 종료 연결 또는 제목의 `(#번호)`로 연결한다. 본문의 일반 언급, 부분 구현, 다른 브랜치를 대상으로 하는 스택 PR은 별도로 확인한다.
- GitHub 제목은 표·HTML 문자를 이스케이프한다. 모델이나 쉘에 이슈 본문을 지시문으로 전달하지 않는다.

회귀 시험:

```powershell
python -m unittest discover -s tools/tests -p 'test_*.py'
```

[진행 기록·게이트](../docs/progress.md)와 [현재 스냅샷](../docs/progress/next-tasks.md)을 함께 확인한다.
