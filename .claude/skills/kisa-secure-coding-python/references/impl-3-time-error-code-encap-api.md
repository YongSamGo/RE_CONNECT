# 구현단계 보안약점 — 제3~7절 (TIM · ERR · COD · ENC · API)

> 출처
> - KISA·행정안전부 「소프트웨어 개발보안 가이드」(2021.12) 제4장 제3절~제7절 — 원문 예제는 Java·C·C#
> - KISA 「Python 시큐어코딩 가이드」(2023 개정본) 2장 제3절~제7절 — 원문 예제는 Python(Django·Flask 중심)
>
> 항목마다 다음 순서로 정리했다.
> 1. **KISA 소프트웨어 개발보안 가이드(2021) 원문**: 개요, 보안대책, Java·C·C# 예제 요지
> 2. **Python 시큐어코딩 가이드(2023) 원문**: Python 관련 설명, 안전한 코딩기법, 원문 Python 예제(따옴표·들여쓰기·변수명 오타 등 표기 오류만 정리), **검토 메모**(가이드 예제 자체의 약점, 다른 항목과 충돌하는 부분)
> 3. **이 스킬의 점검 기준**: 탐지 패턴, 보충 예제(2021 원문 취지를 옮기거나 실무 기준으로 보강한 코드), 판정 기준
>
> 심각도(높음/중간/낮음)는 두 가이드 모두에 없는 값으로, 우선순위를 정하기 위해 붙인 것이다.

| 절 | ID | 항목 |
|---|---|---|
| 제3절 시간 및 상태 | TIM-01 | 경쟁조건: 검사시점과 사용시점(TOCTOU) |
| | TIM-02 | 종료되지 않는 반복문 또는 재귀함수 |
| 제4절 에러처리 | ERR-01 | 오류 메시지 정보노출 |
| | ERR-02 | 오류 상황 대응 부재 |
| | ERR-03 | 부적절한 예외 처리 |
| 제5절 코드오류 | COD-01 | Null Pointer 역참조 |
| | COD-02 | 부적절한 자원 해제 |
| | COD-03 | 해제된 자원 사용 |
| | COD-04 | 초기화되지 않은 변수 사용 |
| | COD-05 | 신뢰할 수 없는 데이터의 역직렬화 |
| 제6절 캡슐화 | ENC-01 | 잘못된 세션에 의한 데이터 정보노출 |
| | ENC-02 | 제거되지 않고 남은 디버그 코드 |
| | ENC-03 | Public 메소드로부터 반환된 Private 배열 |
| | ENC-04 | Private 배열에 Public 데이터 할당 |
| 제7절 API 오용 | API-01 | DNS lookup에 의존한 보안결정 |
| | API-02 | 취약한 API 사용 |

---

## 제3절 시간 및 상태

**정의**: 동시 또는 거의 동시 수행을 지원하는 병렬 시스템이나 하나 이상의 프로세스가 동작하는 환경에서 시간과 상태를 부적절하게 관리해 생기는 보안약점.

### TIM-01. 경쟁조건: 검사시점과 사용시점 (TOCTOU)

| 항목 | 내용 |
|---|---|
| 심각도 | 중간 (금전·권한·재고 처리면 높음) |
| CWE | CWE-367, CWE-362 |
| 연관 설계항목 | — |

#### KISA 소프트웨어 개발보안 가이드(2021) 원문

**개요 (2021 원문)**: 병렬 시스템에서는 자원(파일, 소켓 등)을 쓰기 전에 상태를 검사한다. 그런데 검사 시점(Time Of Check)과 사용 시점(Time Of Use)이 달라 그 사이 자원 상태가 바뀔 수 있다. 예: 프로세스 A가 파일 존재를 확인한 뒤 읽으려는 순간 프로세스 B가 삭제. 동기화 오류뿐 아니라 교착상태도 생길 수 있다.

**보안대책 (2021 원문)**: 공유자원을 여러 프로세스가 쓰면 동기화 구문(synchronized, mutex 등)으로 **한 번에 하나만 접근**하게 하고, 성능 영향을 줄이기 위해 **임계 코드 주변만** 동기화한다.

**2021 원문 예제 요지 (Java·C·C#)**: Java 읽기 스레드와 삭제 스레드가 `f.exists()` 후 각각 읽기·삭제 → `synchronized(SYNC)` 블록. C# `File.Exists` 후 읽기 → `[MethodImpl(Synchronized)]`. C 입금·출금이 lock 없이 `account` 갱신 → `mutex_lock`.

#### Python 시큐어코딩 가이드(2023) 원문 — 2장 3절 1항 (p.120~122)

- **Python 관련 설명**: 파이썬은 멀티스레드 환경에서 공유 자원 동시 접근을 막기 위해 **`threading.Lock`** 객체를 제공한다(`acquire()`로 잠그고 `release()`로 해제).
- **안전한 코딩기법**: 변수·파일 같은 공유 자원을 여러 프로세스가 쓰면 동기화 구문으로 한 번에 하나만 접근하게 하고, 성능을 위해 **임계영역(critical section) 주변만** 동기화한다. `acquire()`/`release()`는 **`with` 문**으로 간단히 쓸 수 있다.
- **원문 예제**

```python
import datetime
import io
import os
import threading


# [가이드 원문] 안전하지 않은 코드 — 검사(isfile)와 사용(open) 사이 경쟁
def write_shared_file(filename, content):
    if os.path.isfile(filename) is True:
        f = open(filename, 'w')
        f.seek(0, io.SEEK_END)
        f.write(content)
        f.close()


def start():
    filename = './temp.txt'
    content = f"start time is {datetime.datetime.now()}"
    my_thread = threading.Thread(target=write_shared_file, args=(filename, content))
    my_thread.start()


# [가이드 원문] 안전한 코드 — with lock으로 검사와 사용을 묶음
lock = threading.Lock()


def write_shared_file(filename, content):
    with lock:
        if os.path.isfile(filename) is True:
            f = open(filename, 'w')
            f.seek(0, io.SEEK_END)
            f.write(content)
            f.close()
```

- **검토 메모**: `threading.Lock`은 **같은 프로세스의 스레드끼리만** 보호한다. 다른 프로세스·외부 사용자가 파일을 지우는 경우(가이드가 든 상황)는 막지 못한다. 멀티 워커 웹 서버, 공용 디렉토리, DB 갱신은 이 스킬 TIM-01 기준(EAFP, `O_EXCL`, 파일 락, DB 원자적 갱신·`select_for_update`)으로 판정한다. 또 예제의 `open(filename, 'w')`는 내용을 지우므로 이어쓰기 의도라면 `'a'`가 맞다.

#### 이 스킬의 점검 기준 (2021 가이드 + 실무 기준)

**탐지 패턴 (Python)**
- 파일: `if os.path.exists(p): open(p)`, `if not os.path.exists(p): open(p, "w")`, `os.access(p, os.W_OK)` 후 `open`, `os.path.isfile` 후 삭제, `tempfile.mktemp()`
- 심볼릭 링크 경쟁: 검사 후 `open`·`chmod`·`chown`(공용 디렉토리 `/tmp`에서 특히)
- DB 읽기-수정-쓰기: `obj = Model.get(); obj.balance -= x; obj.save()` (잠금·원자적 갱신 없음), 재고 확인 후 차감, 쿠폰 사용 여부 확인 후 사용 처리, "1인 1회" 검사 후 생성(유니크 제약 없음)
- 멀티스레드 공유 상태: 모듈 전역 dict/list/카운터를 `threading` 스레드·`ThreadPoolExecutor`에서 lock 없이 갱신
- asyncio: `await` 사이에 공유 상태 검사·갱신 분리
- 캐시: `if key not in cache: cache[key] = compute()` (중복 계산은 대개 무해하지만 인증·결제면 문제)

**보충 예제 — 취약 코드**
```python
import os

# 파일 TOCTOU (원문 Java 예제 대응)
def read_file(path: str) -> str:
    if os.path.exists(path):          # 검사
        with open(path) as f:         # 사용 — 그 사이 삭제·심볼릭 링크 교체 가능
            return f.read()
    return ""


# 잔액 갱신 경쟁 (원문 C deposit/withdraw 예제 대응)
@app.route("/withdraw", methods=["POST"])
@login_required
def withdraw():
    account = Account.query.filter_by(user_id=current_user.id).first()
    amount = int(request.form["amount"])
    if account.balance >= amount:     # 동시 요청 두 건이 모두 통과 가능
        account.balance -= amount
        db.session.commit()
    return "ok"
```

**보충 예제 — 안전 코드 (권장 기준)**
```python
import os
import threading

# 1) 검사 없이 바로 시도하고 예외로 처리 (EAFP) — 검사와 사용 사이 틈을 없앰
def read_file(path: str) -> str:
    try:
        with open(path) as f:
            return f.read()
    except FileNotFoundError:
        return ""


# 새 파일은 원자적으로 생성 (이미 있으면 실패)
fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)

# 2) 프로세스 내 공유 자원은 Lock (원문 synchronized/mutex 대응, 임계구역만)
_file_lock = threading.Lock()


def manage_file(path: str, action: str) -> None:
    with _file_lock:
        if action == "DELETE":
            try:
                os.remove(path)
            except FileNotFoundError:
                pass


# 3) DB는 원자적 갱신 또는 행 잠금
@app.route("/withdraw", methods=["POST"])
@login_required
def withdraw():
    amount = bounded_int(request.form.get("amount", ""), 1, 10_000_000)
    result = db.session.execute(
        update(Account)
        .where(Account.user_id == current_user.id, Account.balance >= amount)
        .values(balance=Account.balance - amount)
    )
    db.session.commit()
    if result.rowcount == 0:
        abort(400, "잔액 부족")
    return "ok"

# Django: Account.objects.filter(pk=pk, balance__gte=amt).update(balance=F("balance") - amt)
#         또는 transaction.atomic() + select_for_update()
# 1회 제한은 DB 유니크 제약으로 보장
```

**판정 기준 / 오탐 주의**
- 단일 프로세스·단일 스레드 CLI 스크립트의 `exists` 후 `open`은 위험도가 낮다. 웹 서버(멀티 워커), 공용 디렉토리, 금전·권한 로직인지 기준으로 판단한다.
- 여러 워커 프로세스(gunicorn 등)에서는 `threading.Lock`이 효과가 없다. DB 잠금·Redis 분산 락·파일 락(`fcntl.flock`)이 필요한지 본다.

---

### TIM-02. 종료되지 않는 반복문 또는 재귀함수

| 항목 | 내용 |
|---|---|
| 심각도 | 중간 |
| CWE | CWE-674, CWE-835 |
| 연관 설계항목 | — |

#### KISA 소프트웨어 개발보안 가이드(2021) 원문

**개요 (2021 원문)**: 재귀 순환 횟수를 제어하지 못해 메모리나 스택 같은 자원을 과다하게 쓰면 위험하다. 귀납 조건(Base Case)이 없는 재귀 함수는 무한 루프에 빠져 자원을 고갈시키고 서비스를 중단시킨다.

**보안대책 (2021 원문)**: 모든 재귀 호출에서 **호출 횟수를 제한**하거나, 초기값(상수)을 설정해 재귀를 제한한다.

**2021 원문 예제 요지 (Java·C·C#)**: C `factorial(i)`에 탈출 조건 없음 → `if (i <= 1) return 1;`.

#### Python 시큐어코딩 가이드(2023) 원문 — 2장 3절 2항 (p.123~125)

- **Python 관련 설명**: 파이썬에는 **재귀 깊이 제한(Recursion Depth Limit)**이 있어 무한 재귀가 무한히 돌지는 않는다(`RecursionError`). 기본값은 **1000**(Anaconda는 2000)이다. `sys.setrecursionlimit()`으로 최대 깊이를 임의로 바꾸면 호출이 과도하게 많아지지 않도록 주의해야 한다.
- **안전한 코딩기법**: 모든 재귀 호출에서 호출 횟수를 제한하거나 종료 조건(Base Case: 재귀 호출 없이 반환하는 경우)을 명확히 정의한다. recursionlimit은 스택 오버플로우를 막기 위한 장치이므로 **과도하게 큰 값으로 설정하지 않는다.**
- **원문 예제**

```python
import sys


# [가이드 원문] 안전하지 않은 코드 — 탈출 조건 없음
def factorial(num):
    return num * factorial(num - 1)


# [가이드 원문] 안전한 코드 — 탈출 조건 명시
def factorial(num):
    if num == 0:
        return 1
    return num * factorial(num - 1)


# [가이드 원문] 재귀 제한을 과도하게 변경하지 않음
sys.setrecursionlimit(1000)
```

- **검토 메모**: 가이드 안전 예제는 음수 입력(`factorial(-1)`)이면 여전히 끝나지 않는다(`RecursionError`). 종료 조건은 `num <= 1`처럼 **입력 범위 전체를 덮도록** 쓰고, 외부 입력이면 범위를 먼저 검사한다. `RecursionError`가 웹 요청에서 처리되지 않으면 500 오류·스택 노출(ERR-01)로 이어진다. 탐지 패턴에 `sys.setrecursionlimit(`을 포함하고 1000을 크게 넘는 값이면 지적한다.

#### 이 스킬의 점검 기준 (2021 가이드 + 실무 기준)

**탐지 패턴 (Python)**
- 탈출 조건이 없거나 외부 입력에 따라 도달 불가능한 재귀 함수
- 외부 입력 구조(JSON 중첩, 트리, 링크 그래프, 디렉토리)를 깊이 제한 없이 재귀 순회
- `while True:` 루프에 `break`/`return`/타임아웃이 없거나, 외부 응답에 의존한 종료 조건(재시도 횟수 제한 없음)
- 페이지네이션 루프에서 `next` 링크가 순환해도 멈추지 않음
- `sys.setrecursionlimit(큰 값)` (스택 오버플로로 프로세스 크래시 가능)
- 정규식 ReDoS: `(a+)+`, `(.*)*`, `(\w+\s?)*$` 등 중첩 수량자에 외부 입력 (반복 폭주라는 점에서 함께 점검)
- 외부 요청에 타임아웃 없음: `requests.get(url)`(기본 무한 대기), `socket.recv()` 무한 대기

**보충 예제 — 취약 코드**
```python
def factorial(i: int) -> int:
    return i * factorial(i - 1)  # 탈출 조건 없음 → RecursionError


def walk(node: dict) -> int:
    # 사용자가 보낸 깊게 중첩된 JSON이면 RecursionError로 500 응답
    return 1 + sum(walk(child) for child in node.get("children", []))


def fetch_all(url: str) -> list:
    items = []
    while url:
        data = requests.get(url).json()  # 타임아웃 없음
        items += data["items"]
        url = data.get("next")           # next가 순환하면 무한 반복
    return items
```

**보충 예제 — 안전 코드 (권장 기준)**
```python
MAX_DEPTH = 50
MAX_PAGES = 100


def factorial(i: int) -> int:
    if i <= 1:  # 원문의 귀납 조건
        return 1
    return i * factorial(i - 1)
# 실무에서는 math.factorial 또는 반복문 사용


def walk(node: dict, depth: int = 0) -> int:
    if depth > MAX_DEPTH:
        raise ValueError("구조가 너무 깊습니다.")
    return 1 + sum(walk(c, depth + 1) for c in node.get("children", []))


def fetch_all(url: str) -> list:
    items, seen = [], set()
    for _ in range(MAX_PAGES):
        if not url or url in seen:
            break
        seen.add(url)
        resp = requests.get(url, timeout=(3, 10))
        resp.raise_for_status()
        data = resp.json()
        items += data["items"]
        url = data.get("next")
    return items
```

**판정 기준 / 오탐 주의**
- 워커·데몬의 메인 루프(`while True`)는 의도된 무한 루프다. 종료 신호 처리와 예외 시 재시작 간격(backoff)이 있는지만 본다.

---

## 제4절 에러처리

**정의**: 에러를 처리하지 않거나 불충분하게 처리해 에러 정보에 중요정보(시스템 내부정보 등)가 포함될 때 생기는 보안약점.

### ERR-01. 오류 메시지 정보노출

| 항목 | 내용 |
|---|---|
| 심각도 | 중간 |
| CWE | CWE-209, CWE-497 |
| 연관 설계항목 | SR3-1 |

#### KISA 소프트웨어 개발보안 가이드(2021) 원문

**개요 (2021 원문)**: 실행환경, 사용자 등 관련 데이터나 시스템 내부 데이터 같은 민감한 정보를 포함하는 오류 메시지를 외부에 제공하면 공격자를 돕게 된다. 예외 이름이나 **스택 트레이스**를 출력하면 프로그램 내부 구조를 쉽게 파악할 수 있다.

**보안대책 (2021 원문)**: 오류 메시지는 정해진 사용자에게 유용한 **최소한의 정보**만 포함한다. 예외는 내부적으로 처리하고, 사용자에게는 민감 정보가 없는 **미리 정의된 메시지**를 제공한다.

**2021 원문 예제 요지 (Java·C·C#)**: Java `e.printStackTrace()`, `System.err.print(e.getMessage())` → `logger.error("ERROR-01: 파일 열기 에러")`처럼 에러 코드와 최소 정보만. C# `Console.WriteLine(e)` → `_log.Debug("ERROR-01 : error information")`.

#### Python 시큐어코딩 가이드(2023) 원문 — 2장 4절 1항 (p.126~129)

- **Python 관련 설명**: 예외 발생 시 예외 이름이나 **traceback**을 출력하면 내부 구조가 드러난다. Django와 Flask는 HTTP 오류 코드별 **사용자 에러 페이지 핸들러**를 제공한다. Django를 `DEBUG=True`로 배포하면 시스템 주요 정보가 노출되고, `DEBUG=False`여도 사용자 에러 페이지를 지정하지 않으면 **Django 기본 에러 페이지**가 출력된다.
- **안전한 코딩기법**: 오류 메시지는 정해진 사용자에게 유용한 최소 정보만 담는다. 예외는 내부에서 처리하고 미리 정의된 메시지를 보여준다. Django는 **`urls.py`에 사용자 정의 에러 페이지 핸들러**를 정의한다.
- **원문 예제**

```python
# [가이드 원문] 안전한 코드 — config/urls.py 사용자 정의 에러 핸들러
handler400 = "blog.views.error400"
handler403 = "blog.views.error403"
handler404 = "blog.views.error404"
handler500 = "blog.views.error500"
# (안전하지 않은 코드: 위 핸들러를 선언하지 않아 Django 기본 에러 페이지 출력)

import logging
import traceback

import requests

logger = logging.getLogger(__name__)


# [가이드 원문] 안전하지 않은 코드 — traceback 출력
def fetch_url(url, useragent, referer=None, retries=1, dimension=False):
    try:
        response = requests.get(url, stream=True, timeout=5,
                                headers={'User-Agent': useragent, 'Referer': referer})
    except IOError:
        traceback.print_exc()


# [가이드 원문] 안전한 코드 — 에러 코드와 최소 정보만 로깅
def fetch_url(url, useragent, referer=None, retries=1, dimension=False):
    try:
        response = requests.get(url, stream=True, timeout=5,
                                headers={'User-Agent': useragent, 'Referer': referer})
    except IOError:
        logger.error('ERROR-01:통신에러')
```

- **검토 메모**: Django `handler400`~`handler500` 미정의도 탐지 대상에 넣는다(`urls.py`에 `handler404`/`handler500` 검색). 서버 측 로그에는 원인 파악을 위해 `logger.exception()`으로 스택을 남겨도 되며, **사용자 응답에만** 내부 정보를 넣지 않으면 된다. `traceback.print_exc()`가 표준출력으로만 가고 사용자에게 전달되지 않는 서버 프로세스라면 위험도를 낮춘다(다만 로그 관리 관점에서 logging 사용 권고).

#### 이 스킬의 점검 기준 (2021 가이드 + 실무 기준)

**탐지 패턴 (Python)**
- 응답에 예외 정보: `return str(e)`, `return {"error": str(e)}`, `jsonify(error=repr(e))`, `traceback.format_exc()`를 응답·템플릿에 넣음, `HTTPException(detail=str(e))`
- 디버그 모드: Django `DEBUG = True`(운영 설정), Flask `app.run(debug=True)`·`FLASK_DEBUG=1`, FastAPI `FastAPI(debug=True)`, Werkzeug 디버거(PIN 우회 시 원격 코드 실행) — ENC-02와 함께 확인
- `traceback.print_exc()`, `print(e)`가 사용자에게 보이는 출력(CGI, CLI 도구의 웹 래퍼)으로 감
- DB 오류 원문 노출: `except IntegrityError as e: return str(e.orig)` (테이블·컬럼·쿼리 노출)
- 응답 헤더로 버전 노출: `Server: Werkzeug/x.y Python/x.y`, `X-Powered-By`
- 로그인 실패 메시지로 계정 존재 여부 노출 (SEC-16 참고)
- 로그에 비밀번호·토큰·개인정보 기록 (로그도 유출 경로)

**보충 예제 — 취약 코드**
```python
@app.route("/file")
def read_file():
    try:
        with open(build_path(request.args["name"])) as f:
            return f.read()
    except Exception as e:
        return f"Error: {e}\n{traceback.format_exc()}", 500  # 경로·스택 노출


# settings.py (운영)
DEBUG = True
```

**보충 예제 — 안전 코드 (권장 기준)**
```python
import logging
import uuid

logger = logging.getLogger(__name__)


@app.route("/file")
def read_file():
    try:
        with open(build_path(request.args["name"])) as f:
            return f.read()
    except FileNotFoundError:
        return {"code": "ERROR-01", "message": "요청한 파일을 찾을 수 없습니다."}, 404
    except OSError:
        logger.exception("ERROR-02: 파일 열기 에러")  # 상세 정보는 서버 로그에만
        return {"code": "ERROR-02", "message": "파일을 처리할 수 없습니다."}, 500


@app.errorhandler(Exception)
def handle_unexpected(e):
    incident = uuid.uuid4().hex[:8]
    logger.exception("unhandled error id=%s", incident)
    return {"code": "ERROR-99", "message": "일시적인 오류입니다.", "id": incident}, 500


# FastAPI
@api.exception_handler(Exception)
async def unhandled(request, exc):
    logger.exception("unhandled")
    return JSONResponse({"message": "일시적인 오류입니다."}, status_code=500)

# Django 운영: DEBUG = False, ALLOWED_HOSTS 지정, handler404/handler500 정의
```

**판정 기준 / 오탐 주의**
- 입력 검증 오류(예: pydantic 422의 필드명·이유)는 사용자에게 필요한 정보라 허용된다. 내부 경로·쿼리·스택·라이브러리 버전이 포함되는지로 판단한다.

---

### ERR-02. 오류 상황 대응 부재

| 항목 | 내용 |
|---|---|
| 심각도 | 중간 (인증·권한 경로면 높음) |
| CWE | CWE-390 |
| 연관 설계항목 | SR3-1 |

#### KISA 소프트웨어 개발보안 가이드(2021) 원문

**개요 (2021 원문)**: 오류가 날 수 있는 부분을 알면서 예외 처리를 하지 않으면, 공격자가 오류 상황을 악용해 프로그램이 의도하지 않은 방향으로 동작하게 할 수 있다.

**보안대책 (2021 원문)**: 오류가 날 수 있는 부분에 제어문으로 **적절한 예외 처리**를 한다(Java try-catch, C/C++ if·switch 등).

**2021 원문 예제 요지 (Java·C·C#)**: Java 로그인에서 `PASSWORD` 파라미터가 없으면 `NullPointerException`이 나는데, catch 블록이 **비어 있어 인증된 것으로 처리**됨 → catch에서 메시지 설정 후 로그인 화면으로 반환. C# 빈 catch → 로깅.

#### Python 시큐어코딩 가이드(2023) 원문 — 2장 4절 2항 (p.130~132)

- **Python 관련 설명**: 예외처리는 코드를 견고하게 하고, 제어 실패로 인한 의도치 않은 중단을 막는다.
- **안전한 코딩기법**: 오류가 날 수 있는 부분은 `try-except`로 적절히 처리한다.
- **원문 예제** (키 선택 실패 시 예외를 무시해 기본 키 `0000000000000000`으로 암호화되는 사례)

```python
import base64
import secrets

from Crypto.Cipher import AES
from Crypto.Util.Padding import pad

static_keys = [
    {'key': b'\xb9J\xfd\xa9\xd2\xefD\x0b\x7f\xb2\xbcy\x9c\xf7\x9c', 'iv': b'\xf1BZ\x06\x03TP\xd1\x8a\xad"\xdc\xc3\x08\x88\xda'},
    {'key': b'Z\x01$.:\xd4u3~\xb6TS(\x08\xcc\xfc', 'iv': b'\xa1a=:\xba\xfczv]\xca\x83\x9485\x14\x17'},
]


# [가이드 원문] 안전하지 않은 코드 — IndexError를 pass → 약한 기본 키로 암호화
def encryption(key_id, plain_text):
    static_key = {'key': b'0000000000000000', 'iv': b'0000000000000000'}
    try:
        static_key = static_keys[key_id]
    except IndexError:
        pass
    cipher_aes = AES.new(static_key['key'], AES.MODE_CBC, static_key['iv'])
    return base64.b64encode(cipher_aes.encrypt(pad(plain_text.encode(), 32))).decode('ASCII')


# [가이드 원문] 안전한 코드 — 예외 시 랜덤 키를 생성
def encryption(key_id, plain_text):
    static_key = {'key': b'0000000000000000', 'iv': b'0000000000000000'}
    try:
        static_key = static_keys[key_id]
    except IndexError:
        static_key = {'key': secrets.token_bytes(16), 'iv': secrets.token_bytes(16)}
        static_keys.append(static_key)
    cipher_aes = AES.new(static_key['key'], AES.MODE_CBC, static_key['iv'])
    return base64.b64encode(cipher_aes.encrypt(pad(plain_text.encode(), 32))).decode('ASCII')
```

- **검토 메모**: 이 예제의 교훈은 "**예외를 무시하면 보안상 더 약한 기본값으로 계속 진행된다**"는 것이다. 다만 가이드 안전 예제도 (1) 키와 IV를 소스코드에 하드코딩하고(SEC-06), (2) 고정 IV를 재사용하며(SEC-04), (3) 잘못된 `key_id`에 오류를 내지 않고 새 키로 암호화를 계속한다. 이 스킬 기준으로는 **잘못된 입력이면 예외를 올려 실패(fail-closed)**하는 것이 정답이며, 가이드 예제를 그대로 따른 코드는 SEC-04·SEC-06도 함께 지적한다.

#### 이 스킬의 점검 기준 (2021 가이드 + 실무 기준)

**탐지 패턴 (Python)**
- `except: pass`, `except Exception: pass`, `except BaseException: pass`, `except ...: ...`, `except ...: continue`, `contextlib.suppress(Exception)`
- 예외를 잡고 아무 표시 없이 성공 경로로 진행: 인증·권한·서명 검증·결제·파일 쓰기 함수에서 `except` 후 `return True` 또는 기본값 반환
- 반환값으로 오류를 알리는 API의 반환값 무시: `subprocess.run(..., check=False)` 후 `returncode` 미확인, `requests.get()` 후 `status_code`/`raise_for_status()` 미확인, `os.system()` 반환값 무시, `cursor.execute` 후 `rowcount` 미확인
- `asyncio.create_task()` 결과를 보관·대기하지 않아 예외가 사라짐
- `finally` 블록 안의 `return`(예외를 삼킴)

**보충 예제 — 취약 코드**
```python
def authenticate(form) -> bool:
    authenticated = True
    try:
        username = form["username"]
        password = form["password"]            # 없으면 KeyError
        if not (username == "webgoat" and check(password)):
            authenticated = False
    except KeyError:
        pass                                    # 오류를 무시 → 인증된 것으로 처리 (원문 대응)
    return authenticated


try:
    audit_log.write(event)
except Exception:
    pass
```

**보충 예제 — 안전 코드 (권장 기준)**
```python
def authenticate(form) -> bool:
    try:
        username = form["username"]
        password = form["password"]
    except KeyError:
        logger.info("login attempt with missing field")
        return False                            # 실패 쪽으로 닫는다 (fail-closed)
    return username == "webgoat" and check(password)


try:
    audit_log.write(event)
except OSError:
    logger.exception("감사 로그 기록 실패")
    raise                                        # 감사 로그 실패는 상위로 전달하거나 대체 경로 사용

result = subprocess.run(["/opt/app/backup.sh"], capture_output=True, text=True, check=False)
if result.returncode != 0:
    logger.error("backup failed rc=%s", result.returncode)
```

**판정 기준 / 오탐 주의**
- 의도적으로 무시해도 되는 예외(예: 정리 단계의 `FileNotFoundError`)는 **구체적 예외 + 주석**이 있으면 허용한다. 원칙은 "보안 판단 경로에서 오류 시 거부(fail-closed)".

---

### ERR-03. 부적절한 예외 처리

| 항목 | 내용 |
|---|---|
| 심각도 | 낮음~중간 |
| CWE | CWE-754, CWE-396 |
| 연관 설계항목 | SR3-1 |

#### KISA 소프트웨어 개발보안 가이드(2021) 원문

**개요 (2021 원문)**: 함수 결과값을 적절히 처리하지 않거나 예외 상황 조건을 적절히 검사하지 않으면 예기치 않은 문제가 생긴다.

**보안대책 (2021 원문)**: 값을 반환하는 **모든 함수의 결과값을 검사**해 의도한 값인지 확인하고, 예외 처리는 **광범위한 예외 대신 구체적인 예외**로 한다.

**2021 원문 예제 요지 (Java·C·C#)**: Java `catch (Exception e)` 하나로 URL·IO·날짜 파싱 오류를 처리 → `MalformedURLException`, `IOException`, `ParseException`으로 세분화. C# 동일.

#### Python 시큐어코딩 가이드(2023) 원문 — 2장 4절 3항 (p.133~134)

- **안전한 코딩기법**: 값을 반환하는 모든 함수의 결과값이 의도한 값인지 검사하고, 광범위한 예외 대신 구체적인 예외를 처리한다.
- **원문 예제**

```python
# [가이드 원문] 안전하지 않은 코드 — bare except
def get_content():
    try:
        f = open('myfile.txt')
        s = f.readline()
        i = int(s.strip())
    except:
        print("Unexpected error ")


# [가이드 원문] 안전한 코드 — 예외 세분화
def get_content():
    try:
        f = open('myfile.txt')
        s = f.readline()
        i = int(s.strip())
    except FileNotFoundError:
        print("file is not found")
    except OSError:
        print("cannot open file")
    except ValueError:
        print("Could not convert data to an integer.")
```

- **검토 메모**: `FileNotFoundError`는 `OSError`의 하위 클래스이므로 가이드처럼 **하위 예외를 먼저** 써야 한다(순서가 바뀌면 하위 처리가 실행되지 않음). 예제는 파일을 닫지 않으므로 COD-02(`with open`)도 함께 본다.

#### 이 스킬의 점검 기준 (2021 가이드 + 실무 기준)

**탐지 패턴 (Python)**
- `except:`(bare except — `KeyboardInterrupt`, `SystemExit`까지 잡음), `except BaseException`, 넓은 `except Exception`이 여러 종류의 작업을 한꺼번에 감쌈
- try 블록이 너무 넓어 어떤 줄의 실패인지 구분 불가
- 반환값 미검사: `re.match()`가 `None`일 수 있는데 바로 `.group()`, `dict.get()` 결과 미검사, `str.find()`가 `-1`인 경우 미처리, ORM `.first()` 결과 미검사 (COD-01과 연결)
- 예외를 잡아 다른 예외로 바꾸면서 원인 소실(`raise NewError()` — `from e` 누락)
- `assert`로 보안 검사 (`python -O`에서 제거됨)

**보충 예제 — 취약 코드**
```python
try:
    with urllib.request.urlopen(url) as resp:
        line = resp.readline().decode()
    date = datetime.strptime(line.strip(), "%m/%d/%y")
except:                      # 모든 예외(시스템 종료 포함)를 한 번에
    print("Exception")

assert current_user.is_admin  # -O 옵션 실행 시 제거됨
```

**보충 예제 — 안전 코드 (권장 기준)**
```python
from urllib.error import HTTPError, URLError

try:
    with urllib.request.urlopen(url, timeout=10) as resp:
        line = resp.readline().decode()
except ValueError:           # 잘못된 URL 형식 (원문 MalformedURLException 대응)
    logger.warning("invalid url")
    raise
except HTTPError as e:       # HTTPError는 URLError의 하위 클래스이므로 먼저 처리
    logger.warning("http error %s", e.code)
    raise
except URLError as e:
    logger.warning("network error: %s", e.reason)
    raise

try:
    date = datetime.strptime(line.strip(), "%m/%d/%y")
except ValueError:           # 원문 ParseException 대응
    logger.warning("date parse error")
    raise

if not current_user.is_admin:
    abort(403)
```

**판정 기준 / 오탐 주의**
- 최상위 경계(요청 핸들러 전역 처리기, 워커 루프)의 `except Exception` + 로깅은 정상 패턴이다. 비즈니스 로직 안쪽의 넓은 예외 처리를 지적한다.

---

## 제5절 코드오류

**정의**: 타입 변환 오류, 자원(메모리 등)의 부적절한 반환처럼 개발자가 범할 수 있는 코딩 오류로 생기는 보안약점.

### COD-01. Null Pointer 역참조 (Python: None 역참조)

| 항목 | 내용 |
|---|---|
| 심각도 | 낮음~중간 |
| CWE | CWE-476 |
| 연관 설계항목 | SR1-9 |

#### KISA 소프트웨어 개발보안 가이드(2021) 원문

**개요 (2021 원문)**: "그 객체는 널이 될 수 없다"는 가정을 위반할 때 생긴다. 공격자가 의도적으로 널 역참조를 일으키면, 그 예외 상황을 이용해 이후 공격을 계획할 수 있다.

**보안대책 (2021 원문)**: 널이 될 수 있는 레퍼런스는 **참조 전에 널인지 검사**하고 안전한 경우에만 쓴다.

**2021 원문 예제 요지 (Java·C·C#)**: Java `obj.equals(elt)`에서 `obj`가 null → `null != obj` 확인 추가. `request.getParameter("url").equals("")` → null 검사 먼저. C# `QueryString["name"].Length` → null 검사. C `*p = count` → `if (p != 0)`.

#### Python 시큐어코딩 가이드(2023) 원문 — 2장 5절 1항 (p.135~137)

- **Python 관련 설명**: 파이썬에는 Null pointer dereference가 **발생하지 않는다.** Null 대신 `None`을 쓰며, `None`은 다른 언어의 null과 같은 기능을 하지 않고 0이나 다른 값을 뜻하지도 않는다. 하지만 데이터 검사를 하지 않으면 **None 값 참조 오류**를 범할 수 있다.
- **안전한 코딩기법**: `None`을 반환하는 함수는 `None`과 다른 값(0, 빈 문자열)이 조건문에서 똑같이 `False`로 평가되어 실수하기 쉽다. `None`이 될 수 있는 데이터는 참조 전에 `None`인지 검사한다.
- **원문 예제**

```python
import os

from xml.sax import make_parser
from xml.sax.handler import feature_namespaces


# [가이드 원문] 안전하지 않은 코드 — filename None 검사 없음
def parse_xml(request):
    filename = request.POST.get('filename')
    if filename.count('.') > 0:          # filename이 None이면 AttributeError
        name, ext = os.path.splitext(filename)
    else:
        ext = ''
    ...


# [가이드 원문] 안전한 코드 — None·빈 문자열 검사
def parse_xml(request):
    filename = request.POST.get('filename')
    if filename is None or filename.strip() == "":
        return render(request, "/error.html", {"error": "파일 이름이 없습니다."})
    if filename.count('.') > 0:
        name, ext = os.path.splitext(filename)
    else:
        ext = ''
    if ext == ".xml":
        parser = make_parser()
        parser.setFeature(feature_namespaces, True)
        handler = Handler()
        parser.setContentHandler(handler)
        parser.parse(filename)
        return render(request, "/success.html", {"result": handler.root})
```

- **검토 메모**: 가이드 예제는 사용자 입력 파일명을 그대로 `parser.parse(filename)`에 넘겨 **경로 조작(INP-03)**과 **XXE(INP-08)** 검토 대상이 된다. None 검사는 `is None`으로 하고, `if not value:`로 대체하면 `0`·빈 문자열과 구분되지 않는 점(가이드 지적)을 판정에 반영한다.

#### 이 스킬의 점검 기준 (2021 가이드 + 실무 기준)

**Python 관점**: `None`의 속성·메서드 접근은 `AttributeError`/`TypeError`를 일으킨다. 웹 요청에서는 500 오류(가용성 저하)와 스택 노출(ERR-01), 그리고 예외 처리 흐름에 따라 인증 우회(ERR-02)로 이어질 수 있다.

**탐지 패턴 (Python)**
- `request.args.get("x").strip()`, `request.json.get("a").lower()` (`get`은 없으면 `None`)
- `request.get_json()`이 `None`(Content-Type 불일치)인데 `["key"]` 접근
- `re.match(...).group()`, `re.search(...).group(1)`
- ORM: `Model.query.filter_by(...).first().attr`, `Model.objects.filter(...).first().attr`, `session.get(Model, id).attr`
- `os.environ.get("X").split()`, `dict.get(k).method()`
- `Optional[...]` 타입 반환 함수 결과를 바로 사용 (mypy `--strict-optional`로 탐지 가능)

**보충 예제 — 취약 코드**
```python
@app.route("/go")
def go():
    url = request.args.get("url")
    if url.startswith("/"):      # url 파라미터가 없으면 AttributeError → 500
        return redirect(url)
    abort(400)


def cardinality(obj, col) -> int:
    if col is None:
        return 0
    # 원문 Java 예제 대응: obj가 None이고 elt가 None이 아니면 obj.__eq__ 호출 문제
    return sum(1 for elt in col if (obj is None and elt is None) or obj.equals(elt))


m = re.match(r"(\d+)-(\d+)", value)
start = int(m.group(1))          # 매치 실패 시 AttributeError
```

**보충 예제 — 안전 코드 (권장 기준)**
```python
@app.route("/go")
def go():
    url = request.args.get("url")
    if url is None or not is_local_url(url):
        abort(400)
    return redirect(url)


def cardinality(obj, col) -> int:
    if col is None:
        return 0
    return sum(1 for elt in col if (obj is None and elt is None) or (obj is not None and obj == elt))


m = re.match(r"(\d+)-(\d+)", value)
if m is None:
    raise ValueError("형식 오류")
start = int(m.group(1))

user = User.query.filter_by(id=user_id).first_or_404()  # 또는 None 검사
data = request.get_json(silent=True) or {}
```

---

### COD-02. 부적절한 자원 해제

| 항목 | 내용 |
|---|---|
| 심각도 | 낮음~중간 |
| CWE | CWE-404, CWE-772, CWE-775 |
| 연관 설계항목 | — |

#### KISA 소프트웨어 개발보안 가이드(2021) 원문

**개요 (2021 원문)**: 파일 디스크립터, 힙 메모리, 소켓 등은 유한한 자원이다. 쓴 뒤 반환해야 하는데, 프로그램 오류나 에러로 반환하지 못하면 자원이 고갈되어 새 입력을 처리할 수 없게 된다.

**보안대책 (2021 원문)**: 자원을 획득해 쓴 다음에는 **반드시 해제**한다. 예외 발생 여부와 상관없이 항상 실행되는 `finally` 블록에서 반환한다.

**2021 원문 예제 요지 (Java·C·C#)**: Java try 안에서 `close()` → 오류 시 실행 안 됨 → `finally`에서 각각 null 검사 후 `close`. C# → `using` 구문. C 오류 분기에서 `fclose` 누락 → 모든 반환 경로에서 `fclose`.

#### Python 시큐어코딩 가이드(2023) 원문 — 2장 5절 2항 (p.138~140)

- **안전한 코딩기법**: 자원을 획득해 쓴 다음에는 반드시 해제·반환한다. 예외 여부와 상관없이 실행되는 **`finally`** 블록에서 반환하거나, **`with` 문**을 써서 블록이 끝날 때 자동 반환되게 한다.
- **원문 예제**

```python
# [가이드 원문] 안전하지 않은 코드 — 예외 시 close()가 실행되지 않음
def get_config():
    lines = None
    try:
        f = open('config.cfg')
        lines = f.readlines()
        raise Exception("Throwing the exception!")
        f.close()
        return lines
    except Exception as e:
        return ''


# [가이드 원문] 안전한 코드 — finally에서 반환
def get_config():
    lines = None
    try:
        f = open('config.cfg')
        lines = f.readlines()
        raise Exception("Throwing the exception!")
    except Exception as e:
        ...
    finally:
        f.close()
    return lines


# [가이드 원문] 안전한 코드 — with 문
with open('config.cfg') as f:
    print(f.read())
```

- **검토 메모**: 가이드 `finally` 예제는 `open()` 자체가 실패하면 `f`가 정의되지 않아 `finally`에서 `NameError`가 난다. 원문은 `finally` 안에 `return`도 두는데, 이는 **예외를 삼키는 패턴**(ERR-02)이라 위에서는 밖으로 옮겼다. `with` 문을 기준으로 판정한다.

#### 이 스킬의 점검 기준 (2021 가이드 + 실무 기준)

**탐지 패턴 (Python)**
- `f = open(...)` 후 `with` 없이 사용, 예외 경로에서 `close()` 누락
- `socket.socket()`, `sqlite3.connect()`, `psycopg2.connect()`, `pymysql.connect()`, DB 커서, `requests.Session()`, `httpx.Client()`, `zipfile.ZipFile()`, `tarfile.open()`, `tempfile.TemporaryFile()`, `subprocess.Popen()`(프로세스·파이프), `multiprocessing.Pool()`, `ThreadPoolExecutor()`, `threading.Lock().acquire()`(release 누락)를 `with` 없이 사용
- `requests.get(..., stream=True)` 후 응답 미종료
- SQLAlchemy `Session()`을 요청마다 만들고 닫지 않음 (`scoped_session.remove()` 누락)
- 무제한 캐시·전역 리스트에 계속 추가 (메모리 고갈)
- 요청 처리 시간·업로드 크기·동시 연결 수 제한 없음 (자원 고갈 DoS)

**보충 예제 — 취약 코드**
```python
def copy_file(src: str, dst: str) -> None:
    fin = open(src, "rb")
    fout = open(dst, "wb")
    fout.write(fin.read())   # 여기서 예외가 나면 두 파일 모두 열린 채로 남음
    fin.close()
    fout.close()


def query(sql, params):
    conn = sqlite3.connect("app.db")
    cur = conn.cursor()
    if not check_something():
        return None          # 원문 C 예제 대응: 이른 반환에서 연결을 닫지 않음
    rows = cur.execute(sql, params).fetchall()
    conn.close()
    return rows
```

**보충 예제 — 안전 코드 (권장 기준)**
```python
import contextlib
import shutil
import sqlite3


def copy_file(src: str, dst: str) -> None:
    with open(src, "rb") as fin, open(dst, "wb") as fout:  # 원문 finally/using 대응
        shutil.copyfileobj(fin, fout)


def query(sql, params):
    # sqlite3 연결의 with는 트랜잭션만 관리하므로 closing으로 연결을 닫는다
    with contextlib.closing(sqlite3.connect("app.db")) as conn:
        if not check_something():
            return None
        return conn.execute(sql, params).fetchall()


with requests.get(url, stream=True, timeout=10) as resp:
    for chunk in resp.iter_content(8192):
        ...
```

---

### COD-03. 해제된 자원 사용

| 항목 | 내용 |
|---|---|
| 심각도 | 높음 (네이티브 코드) / 낮음 (순수 Python) |
| CWE | CWE-416, CWE-415 |
| 연관 설계항목 | — |

#### KISA 소프트웨어 개발보안 가이드(2021) 원문

**개요 (2021 원문)**: C에서 동적 메모리 관리는 보안 취약점의 대표적 원인이다. 해제한 메모리를 참조하면 예상치 못한 값이나 코드가 실행된다. **이중 해제(double free)**도 같은 범주다.

**보안대책 (2021 원문)**: 해제한 메모리를 가리키던 포인터를 참조 추적·형 변환·피연산자 등으로 쓰지 않는다. 해제 후 포인터에 **NULL**을 넣으면 의도하지 않은 실행을 막을 수 있다.

**2021 원문 예제 요지 (Java·C·C#)**: C `free(temp)` 후 `strncpy(temp, ...)` → 사용을 끝낸 뒤 해제. 조건에 따라 `free(data)` 두 번 → 해제 후 `data = NULL`.

#### Python 시큐어코딩 가이드(2023) 원문

**언어 특성상 제외된 항목**이다. 순수 파이썬은 해당이 없으며, 이 스킬에서는 `ctypes`/`cffi`/C 확장이 있을 때만 2021 가이드 기준으로 점검한다.

#### 이 스킬의 점검 기준 (2021 가이드 + 실무 기준)

**Python 관점**: 순수 Python은 참조 카운팅·GC로 메모리를 관리해 이 약점이 생기지 않는다. 해당되는 경우와 유사 패턴:
- `ctypes`/`cffi`로 할당·해제한 메모리를 해제 후 사용 (`ffi.gc`, `libc.free` 후 포인터 사용), C 확장 모듈
- `memoryview`를 해제된 버퍼에 대해 사용, `mmap.close()` 후 접근 (Python은 `ValueError`로 막지만 네이티브 확장은 아닐 수 있음)
- **논리적 유사 패턴**: 닫힌 파일·소켓·DB 커넥션 재사용, 커넥션 풀에 반납한 연결을 계속 사용, 로그아웃·무효화된 세션/토큰을 계속 사용 (서버 측 무효화 미흡 — SR4-1과 연결)

**탐지 패턴 (Python)**
- `ctypes.CDLL("libc.so.6").free(ptr)` 후 `ptr` 사용, `cffi` `ffi.release()` 후 사용
- `.pyx`/`.c` 파일은 C 규칙으로 별도 점검
- `conn.close()` 후 `conn.execute(...)`, `with` 블록 밖에서 파일 객체 사용
- 토큰 폐기 목록 없이 JWT만으로 로그아웃 처리 (만료 전까지 재사용 가능)

**보충 예제 — 취약 코드**
```python
import ctypes

libc = ctypes.CDLL("libc.so.6")
libc.malloc.restype = ctypes.c_void_p
buf = libc.malloc(64)
libc.free(ctypes.c_void_p(buf))
ctypes.memmove(buf, b"data", 4)  # 해제된 메모리에 쓰기 (원문 대응)
```

**보충 예제 — 안전 코드 (권장 기준)**
```python
buf = libc.malloc(64)
try:
    ctypes.memmove(buf, b"data", 4)  # 사용을 모두 끝낸 뒤
finally:
    libc.free(ctypes.c_void_p(buf))
    buf = None                       # 원문 '해제 후 NULL 할당' 대응

# 가능하면 ctypes.create_string_buffer 등 Python이 수명을 관리하는 객체를 사용
```

**판정 기준 / 오탐 주의**
- 네이티브 코드가 없으면 "해당없음"으로 보고하되, 논리적 유사 패턴(무효화된 세션·토큰 재사용)은 SR4-1/SEC-01 관점에서 따로 본다.

---

### COD-04. 초기화되지 않은 변수 사용

| 항목 | 내용 |
|---|---|
| 심각도 | 낮음 |
| CWE | CWE-457, CWE-824 |
| 연관 설계항목 | — |

#### KISA 소프트웨어 개발보안 가이드(2021) 원문

**개요 (2021 원문)**: C의 스택 지역변수는 생성 시 자동으로 초기화되지 않는다. 초기화되지 않은 변수는 이전 함수에서 쓰던 값을 담고 있어, 공격자가 메모리 값을 읽거나 특정 코드를 실행하는 데 쓸 수 있다.

**보안대책 (2021 원문)**: 모든 변수에 사용 전 **올바른 초기값**을 할당한다.

**2021 원문 예제 요지 (Java·C·C#)**: C `switch`의 `default`에서 `x`만 초기화하고 `y`는 초기화 안 함 → 선언 시 `int x=1, y=1;`.

#### Python 시큐어코딩 가이드(2023) 원문

**언어 특성상 제외된 항목**이다. 이 스킬은 파이썬에서 같은 결과를 내는 유사 패턴(분기 일부에서만 할당, 가변 기본 인자, `numpy.empty`)만 낮은 심각도로 점검한다.

#### 이 스킬의 점검 기준 (2021 가이드 + 실무 기준)

**Python 관점**: 할당 전 사용은 `NameError`/`UnboundLocalError`로 막히지만, 다음 패턴이 같은 문제를 만든다.
- 조건 분기 일부에서만 변수를 할당하고 다른 경로에서 사용 → 런타임 오류(500)
- **이전 반복의 값이 남는 변수**: 루프 안에서 조건부로만 갱신되는 변수가 이전 사용자·이전 항목의 값을 유지 (정보노출·권한 혼동)
- 가변 기본 인자 `def f(items=[])`, `def f(ctx={})` — 호출 간 상태 공유 (ENC-01과 유사한 데이터 누출)
- `bytearray(n)`은 0으로 초기화되지만, `numpy.empty()`는 **초기화되지 않은 메모리**를 반환 → 그대로 응답·파일로 내보내면 메모리 내용 노출
- 클래스 속성을 인스턴스 기본값처럼 쓰는 가변 객체(`class A: cache = {}`)

**보충 예제 — 취약 코드**
```python
import numpy as np


def set_cursor(position: int, base: int, i: int):
    if position == 0:
        x, y = base, base
    elif position == 1:
        x, y = base + i, base - i
    else:
        x = 1                     # y 미할당 → UnboundLocalError (원문 C 예제 대응)
    return x, y


def add_item(item, items=[]):     # 모든 호출이 같은 리스트를 공유
    items.append(item)
    return items


def make_buffer(n: int) -> bytes:
    return np.empty(n, dtype=np.uint8).tobytes()  # 초기화되지 않은 메모리 내용 반환
```

**보충 예제 — 안전 코드 (권장 기준)**
```python
import numpy as np


def set_cursor(position: int, base: int, i: int):
    x, y = 1, 1                   # 원문 '선언 시 초기화' 대응
    if position == 0:
        x, y = base, base
    elif position == 1:
        x, y = base + i, base - i
    return x, y


def add_item(item, items=None):
    items = [] if items is None else items
    items.append(item)
    return items


def make_buffer(n: int) -> bytes:
    return np.zeros(n, dtype=np.uint8).tobytes()
```

---

### COD-05. 신뢰할 수 없는 데이터의 역직렬화

| 항목 | 내용 |
|---|---|
| 심각도 | 높음 |
| CWE | CWE-502 |
| 연관 설계항목 | — (SR1-10 무결성과 연결) |

#### KISA 소프트웨어 개발보안 가이드(2021) 원문

**개요 (2021 원문)**: 직렬화는 객체 상태를 바이트 스트림으로 바꿔 파일로 저장하거나 전달하는 작업이고, 역직렬화는 그 반대다. 전송·저장된 스트림을 공격자가 조작할 수 있으면, 신뢰할 수 없는 역직렬화로 **무결성 침해, 원격 코드 실행, 서비스 거부**가 생긴다.

**보안대책 (2021 원문)**: 신뢰할 수 없는 데이터를 **역직렬화하지 않도록** 구성한다. 암호화 통신을 적용하지 못하면 송신 측에서 **서명**을 추가하고 수신 측에서 확인해 무결성을 검증한다. 또는 역직렬화 대상이 **사전에 검증된 클래스만** 포함하는지 확인하거나(화이트리스트), 제한된 실행 권한으로 역직렬화 코드를 실행한다.

> 원문 보안대책 첫 문단에는 "초기화되지 않은 변수" 항목의 문장이 편집 오류로 섞여 있다. 위 내용은 그 뒤 실제 대책 문장을 정리한 것이다.

**2021 원문 예제 요지 (Java·C·C#)**: Java `SealedObject`/`SignedObject`로 서명 검증 후 객체 사용. `ObjectInputStream.readObject()` 무검증 → `resolveClass`를 오버라이드한 `WhitelistedObjectInputStream`으로 허용 클래스(`Student`)만 역직렬화.

#### Python 시큐어코딩 가이드(2023) 원문 — 2장 5절 3항 (p.141~143)

- **Python 관련 설명**: 파이썬은 **`pickle`** 모듈로 직렬화(pickle)·역직렬화(unpickle)한다. pickle은 **데이터 변조 검증 과정이 없어** 임의 코드를 실행하는 악성 pickle 데이터를 만들 수 있다. pickle로 역직렬화하면 **`hmac`으로 데이터에 서명**하거나 **`json` 모듈 사용**을 고려해야 한다.
- **안전한 코딩기법**: 신뢰할 수 없는 데이터를 역직렬화하지 않는다. 암호화 통신을 못 쓰면 최소한 송신측 서명·수신측 서명 확인으로 무결성을 검증한다. 또는 사전에 검증된 클래스만 포함하는지 확인하거나 제한된 실행 권한으로 역직렬화한다. 역직렬화 데이터의 일부만 필요하면 **JSON 같은 텍스트 형식**을 쓴다.
  > 가이드 원문 "나. 안전한 코딩기법" 첫 문단에는 2021 가이드와 똑같이 "초기화되지 않은 변수" 항목의 문장이 잘못 들어가 있다.
- **원문 예제**

```python
import hashlib
import hmac
import pickle


# [가이드 원문] 안전하지 않은 코드 — 사용자 입력을 그대로 역직렬화
def load_user_object(request):
    pickled_userinfo = pickle.dumps(request.POST.get('userinfo', ''))
    user_obj = pickle.loads(pickled_userinfo)
    return render(request, '/load_user_obj.html', {'obj': user_obj})


# [가이드 원문] 안전한 코드 — HMAC 검증 후 역직렬화
def load_user_object(request):
    hashed_pickle = request.POST.get("hashed_pickle", "")
    pickled_userinfo = pickle.dumps(request.POST.get("userinfo", ""))
    m = hmac.new(key="secret_key".encode("utf-8"), digestmod=hashlib.sha512)
    m.update(pickled_userinfo)
    if hmac.compare_digest(str(m.digest()), hashed_pickle):
        user_obj = pickle.loads(pickled_userinfo)
        return render(request, "/load_user_obj.html", {"obj": user_obj})
    return render(request, "/error.html", {"error": "신뢰할 수 없는 데이터입니다."})
```

- **검토 메모**
  - 가이드 예제는 사용자가 보낸 **문자열을 서버가 pickle.dumps 한 뒤 loads** 하므로, 실제 공격 시나리오(공격자가 만든 pickle 바이트를 서버가 loads)와 맞지 않는다. 판정은 "외부에서 들어온 바이트가 `pickle.loads`/`yaml.load` 등에 도달하는가"로 한다.
  - HMAC 키를 `"secret_key"`로 **하드코딩**(SEC-06)하고, `str(m.digest())`(바이트 repr)와 비교해 사실상 정상 동작하지 않는다. 올바른 방식은 `hmac.compare_digest(m.hexdigest(), received_hex)`이며, 키는 환경변수·시크릿에서 읽는다.
  - 이 스킬의 권고 순서는 그대로다: **JSON/`yaml.safe_load` > 서명된 직렬화(`itsdangerous`) > 허용 클래스 Unpickler(내부 신뢰 구간 한정)**.

#### 이 스킬의 점검 기준 (2021 가이드 + 실무 기준)

**탐지 패턴 (Python)**
- **항상 위험(외부 데이터일 때)**: `pickle.load(s)(`, `pickle.Unpickler(`, `cPickle`, `_pickle`, `dill.load(s)`, `cloudpickle.load(s)`, `shelve.open(`, `marshal.load(s)(`, `jsonpickle.decode(`
- PyYAML: `yaml.load(data)`(Loader 미지정, 구버전), `yaml.load(data, Loader=yaml.Loader|yaml.UnsafeLoader|yaml.FullLoader)`, `yaml.unsafe_load(` → `yaml.safe_load` 사용
- ML 모델·데이터: `torch.load(f)`(`weights_only=False` 또는 구버전 기본값), `joblib.load(`, `numpy.load(..., allow_pickle=True)`, `pandas.read_pickle(`, Keras `load_model(..., safe_mode=False)`, Hugging Face `trust_remote_code=True`
- 세션·캐시: 쿠키·Redis·메시지큐 값을 `pickle.loads` (서명 없이), Django `PickleSerializer`(세션), Celery `accept_content=["pickle"]`
- `xmlrpc`·`multiprocessing.connection`(인증키 없이 외부 노출)

**보충 예제 — 취약 코드**
```python
import base64
import pickle

import yaml


@app.route("/restore", methods=["POST"])
def restore():
    # 쿠키·업로드 데이터를 pickle로 복원 → __reduce__로 임의 코드 실행
    state = pickle.loads(base64.b64decode(request.cookies["state"]))
    return jsonify(state)


@app.route("/config", methods=["POST"])
def load_config():
    cfg = yaml.load(request.data, Loader=yaml.Loader)  # !!python/object 태그로 코드 실행
    return jsonify(cfg)


model = torch.load(uploaded_file)  # pickle 기반
```

**보충 예제 — 안전 코드 (권장 기준)**
```python
import hashlib
import hmac
import json

import yaml
from itsdangerous import BadSignature, URLSafeSerializer

# 1) 데이터 전용 형식 사용 (JSON / yaml.safe_load) — 객체 복원 자체를 하지 않음
@app.route("/config", methods=["POST"])
def load_config():
    cfg = yaml.safe_load(request.data)
    return jsonify(cfg)


# 2) 클라이언트로 보낸 상태는 JSON + 서버 서명 (원문 SignedObject 대응)
signer = URLSafeSerializer(app.config["SECRET_KEY"], salt="state")


@app.route("/restore", methods=["POST"])
def restore():
    try:
        state = signer.loads(request.cookies.get("state", ""))
    except BadSignature:
        abort(400)
    return jsonify(state)


# 3) pickle을 꼭 써야 하면 (내부 신뢰 구간 한정) 허용 클래스만 복원 (원문 WhitelistedObjectInputStream 대응)
import io
import pickle


class RestrictedUnpickler(pickle.Unpickler):
    ALLOWED = {("myapp.models", "Student")}

    def find_class(self, module, name):
        if (module, name) not in self.ALLOWED:
            raise pickle.UnpicklingError(f"허용되지 않은 클래스: {module}.{name}")
        return super().find_class(module, name)


def restricted_loads(data: bytes):
    return RestrictedUnpickler(io.BytesIO(data)).load()
# 주의: find_class 제한은 우회 사례가 있어, 외부 입력에는 1)·2)를 우선한다.


# 4) 모델 파일
state_dict = torch.load(path, weights_only=True)  # 텐서만 로드 (PyTorch 1.13+)
# 가능하면 safetensors 형식 사용
```

**판정 기준 / 오탐 주의**
- 역직렬화 대상이 **같은 프로세스가 방금 만든 데이터**이거나, 공격자가 쓸 수 없는 경로(권한 통제된 로컬 캐시)라면 위험도를 낮춘다. 저장소 쓰기 권한과 서명 여부를 확인한다.

---

## 제6절 캡슐화

**정의**: 중요한 데이터나 기능을 불충분하게 캡슐화하거나 잘못 사용해 생기는 보안약점. 정보노출, 권한 문제 등이 생긴다.

### ENC-01. 잘못된 세션에 의한 데이터 정보노출

| 항목 | 내용 |
|---|---|
| 심각도 | 높음 |
| CWE | CWE-488, CWE-543 |
| 연관 설계항목 | SR4-1 |

#### KISA 소프트웨어 개발보안 가이드(2021) 원문

**개요 (2021 원문)**: 다중 스레드 환경에서는 싱글톤 객체 필드에 경쟁조건이 생길 수 있다. Java 서블릿처럼 다중 스레드 환경에서는 정보를 저장하는 **멤버 변수**를 두지 않아, 서로 다른 세션이 데이터를 공유하지 않게 해야 한다.

**보안대책 (2021 원문)**: 싱글톤 패턴을 쓸 때는 변수 범위(Scope)에 주의한다. Java에서는 `HttpServlet` 하위 클래스에 멤버 필드를 선언하지 말고, 필요하면 **지역 변수**를 쓴다.

**2021 원문 예제 요지 (Java·C·C#)**: JSP 선언부 `<%! String username %>`(모든 사용자 공유) → 스크립틀릿 `<% %>`(지역변수). Spring `@Controller`의 `private int currentPage` 멤버 → 메서드 지역변수. C# `IHttpHandler`의 `private String id` 필드 → 지역변수·세션변수.

#### Python 시큐어코딩 가이드(2023) 원문 — 2장 6절 1항 (p.144~146)

- **Python 관련 설명**: 다중 스레드 환경에서는 정보를 저장하는 **전역 변수**가 포함되지 않도록 해야 한다. **파이썬의 클래스 변수는 스레드 간에 공유**되므로, 클래스 변수에 값을 할당하면 서로 다른 세션 간에 데이터가 공유되어 의도하지 않은 데이터가 전달될 수 있다.
- **안전한 코딩기법**: 싱글톤 패턴은 변수 범위(Scope)에 주의한다. 다중 스레드 환경에서 클래스 변수의 값은 하위 메서드와 공유되므로, 필요하면 **인스턴스 변수**로 선언한다.
- **원문 예제**

```python
# [가이드 원문] 안전하지 않은 코드 — 클래스 변수에 요청 데이터 저장
class UserDescription:
    user_name = ''

    def get_user_profile(self):
        return self.get_user_discription(UserDescription.user_name)

    def show_user_profile(self, request):
        UserDescription.user_name = request.POST.get('name', '')
        self.user_profile = self.get_user_profile()
        return render(request, 'profile.html', {'profile': self.user_profile})


# [가이드 원문] 안전한 코드 — 인스턴스 변수 사용 (원문의 인자 오류를 바로잡음)
class UserDescription:
    def get_user_profile(self):
        return self.get_user_discription(self.user_name)

    def show_user_profile(self, request):
        self.user_name = request.POST.get('name', '')
        self.user_profile = self.get_user_profile()
        return render(request, 'profile.html', {'profile': self.user_profile})
```

- **검토 메모**: 인스턴스 변수도 **그 인스턴스가 요청 간에 재사용되면**(모듈 수준에서 한 번 만든 서비스 객체, 싱글톤) 같은 문제가 남는다. 판정은 "요청별 데이터가 요청 간에 공유되는 객체에 저장되는가"로 하며, 지역 변수나 인자 전달을 가장 안전한 기준으로 본다.

#### 이 스킬의 점검 기준 (2021 가이드 + 실무 기준)

**탐지 패턴 (Python)**
- 모듈 전역 변수에 요청·사용자별 값을 저장: `current_user_id = None` 후 핸들러에서 `global current_user_id; current_user_id = ...`
- 클래스 속성(인스턴스가 아닌)에 요청 데이터 저장: `class View: user = None` 후 `View.user = request.user`
- 요청 간 재사용되는 객체의 속성에 요청 데이터 저장: Django 클래스 기반 뷰는 요청마다 새 인스턴스라 비교적 안전하지만, **미들웨어 인스턴스**, DRF `Serializer`를 전역에 하나 만들어 재사용, 모듈 수준 싱글톤 서비스 객체, `functools.lru_cache`/`cache`로 사용자별 결과 캐싱(키에 사용자 미포함)
- 가변 기본 인자(`def handler(ctx={})`) — COD-04와 동일
- 비동기(asyncio)·스레드 워커에서 `threading.local` 대신 전역 변수 사용, `contextvars` 미사용
- 캐시 키에 사용자·권한 정보 누락: `cache.set(f"profile", data)`, `@cache_page`를 로그인 사용자 페이지에 적용(`Vary: Cookie` 없음), CDN 캐시가 개인화 응답 저장

**보충 예제 — 취약 코드**
```python
current_page = 1                  # 모든 요청·스레드가 공유 (원문 Controller 멤버 변수 대응)


@app.route("/trend")
def trend():
    global current_page
    current_page = int(request.args.get("page", 1))
    ...
    return render_page(current_page)  # 다른 요청이 그 사이 값을 바꿀 수 있음


class ProfileService:
    _user = None                  # 클래스 속성 = 싱글톤 공유 상태

    def load(self, req):
        ProfileService._user = req.user
        return self._get_profile()


@functools.lru_cache(maxsize=1024)
def my_orders():                  # 사용자 구분 없이 첫 결과를 모두에게 반환
    return Order.query.filter_by(user_id=current_user.id).all()
```

**보충 예제 — 안전 코드 (권장 기준)**
```python
import contextvars

# 1) 요청 범위 값은 지역 변수로 (원문 대응)
@app.route("/trend")
def trend():
    current_page = bounded_int(request.args.get("page", "1"), 1, 1000)
    return render_page(current_page)


# 2) 요청 컨텍스트가 필요하면 프레임워크 컨텍스트나 contextvars
request_user: contextvars.ContextVar = contextvars.ContextVar("request_user")


class ProfileService:
    def load(self, user):
        return self._get_profile(user)   # 인자로 전달, 상태를 저장하지 않음


# 3) 캐시는 사용자 단위 키
def my_orders(user_id: int):
    key = f"orders:{user_id}"
    data = cache.get(key)
    if data is None:
        data = [o.to_dict() for o in Order.query.filter_by(user_id=user_id)]
        cache.set(key, data, timeout=60)
    return data
```

**판정 기준 / 오탐 주의**
- 설정값·상수·읽기 전용 리소스(커넥션 풀, 컴파일된 정규식)를 전역에 두는 것은 정상이다. **요청·사용자별로 바뀌는 값**을 공유 위치에 쓰는지로 판단한다.

---

### ENC-02. 제거되지 않고 남은 디버그 코드

| 항목 | 내용 |
|---|---|
| 심각도 | 중간 (디버그 모드·디버그 엔드포인트면 높음) |
| CWE | CWE-489, CWE-215 |
| 연관 설계항목 | SR3-1 |

#### KISA 소프트웨어 개발보안 가이드(2021) 원문

**개요 (2021 원문)**: 디버깅용 코드는 개발이 끝나면 제거해야 한다. 디버그 코드는 설정 같은 민감 정보를 담거나 시스템을 제어하게 허용할 수 있다. 남긴 채 배포하면 공격자가 식별 과정을 우회하거나 의도하지 않은 정보·제어 정보가 노출된다.

**보안대책 (2021 원문)**: 배포 전 디버그 코드를 **반드시 확인하고 삭제**한다. Java 웹 애플리케이션에서는 디버그용 `main()` 메서드를 남기는 경우가 많으니 디버깅이 끝나면 삭제한다.

**2021 원문 예제 요지 (Java·C·C#)**: Java 클래스의 `main()` 안 디버그 출력 → `main()` 삭제. C# `Console.WriteLine("sensitive info")` → 삭제. C 디버그 모드에서 `backtrace_symbols` 콜스택 출력 → 삭제.

#### Python 시큐어코딩 가이드(2023) 원문 — 2장 6절 2항 (p.147~150)

- **Python 관련 설명**: Django·Flask는 전역 수준에서 DEBUG 모드를 설정한다. DEBUG 모드에서는 **브라우저에서 임의의 파이썬 코드를 실행할 수도 있고**(Werkzeug 대화형 디버거) 모든 오류가 출력되어 정보 노출 위험이 있다. 배포 전에 반드시 비활성화한다.
- **안전한 코딩기법**: 배포 전 디버그 코드를 확인·삭제한다. Django는 `settings.py`에서 `DEBUG = False`, Flask는 `app.run()` 전에 `debug = False`로 설정한다.
- **원문 예제**

```python
# [가이드 원문] Django settings.py — 안전하지 않은 코드 / 안전한 코드
DEBUG = True    # 취약
DEBUG = False   # 안전


# [가이드 원문] Flask — 안전하지 않은 코드 (디버그 설정 방법 2가지)
from flask import Flask

app = Flask(__name__)
app.debug = True                 # 방법 1

if __name__ == '__main__':
    app.run(debug=True)          # 방법 2


# [가이드 원문] Flask — 안전한 코드
app = Flask(__name__)
app.debug = False

if __name__ == '__main__':
    app.run(debug=False)
```

- **검토 메모**: 탐지 패턴에 `app.debug = True`(속성 방식)를 포함한다. 환경변수 `FLASK_DEBUG=1`, `DJANGO_DEBUG=True` 같은 배포 설정도 확인한다.

#### 이 스킬의 점검 기준 (2021 가이드 + 실무 기준)

**탐지 패턴 (Python)**
- 디버그 모드: Django `DEBUG = True`, Flask `app.run(debug=True)`, `app.debug = True`, `FLASK_DEBUG=1`/`FLASK_ENV=development`(배포 설정·Dockerfile·compose·Procfile), FastAPI/Starlette `debug=True`, `uvicorn --reload` 운영 사용
- 디버그 툴: `django-debug-toolbar`(`INSTALLED_APPS`·`INTERNAL_IPS`), `werkzeug.debug.DebuggedApplication`, `flask_debugtoolbar`, `pdb.set_trace()`, `breakpoint()`, `import ipdb`, `import pydevd`, `debugpy.listen(`
- 디버그 엔드포인트: `/debug`, `/test`, `/_internal`, `/env`, `/config`, `/eval`, `/shell`, 백도어성 로그인(`if password == "debug": login`)
- 운영 코드의 `if __name__ == "__main__":` 블록에 테스트 계정·하드코딩 키·`app.run(host="0.0.0.0", debug=True)`
- `print()`로 토큰·비밀번호·요청 전체 출력, `logging.basicConfig(level=logging.DEBUG)` 운영 적용, `traceback.print_stack()`
- 소스맵·`.git` 디렉토리·`*.bak` 파일이 정적 경로로 배포

**보충 예제 — 취약 코드**
```python
@app.route("/debug/env")
def debug_env():
    return dict(os.environ)       # 비밀키·DB 비밀번호 노출


@app.route("/login", methods=["POST"])
def login():
    print("login:", request.form)  # 비밀번호가 표준출력·로그로
    ...


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)  # Werkzeug 대화형 디버거 노출
```

**보충 예제 — 안전 코드 (권장 기준)**
```python
import os

DEBUG = os.environ.get("APP_DEBUG", "false").lower() == "true"  # 기본값 False

# 디버그 전용 라우트는 개발 환경에서만 등록
if DEBUG:
    from .debug_routes import debug_bp
    app.register_blueprint(debug_bp)


@app.route("/login", methods=["POST"])
def login():
    logger.debug("login attempt user=%s", request.form.get("username"))  # 민감정보 제외
    ...


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5000, debug=DEBUG)
# 운영은 gunicorn/uvicorn으로 실행하고 debug 옵션을 쓰지 않는다.
# 점검 자동화: ruff의 T20(print), T10(debugger) 규칙, bandit B201(flask debug=True)
```

**판정 기준 / 오탐 주의**
- `if __name__ == "__main__":`이 CLI 도구의 정상 진입점이면 제외한다. 웹 애플리케이션 모듈 안의 테스트용 블록인지 확인한다.
- 설정 파일이 환경별로 분리되어 있으면 **운영 설정**을 기준으로 판정한다.

---

### ENC-03. Public 메소드로부터 반환된 Private 배열

| 항목 | 내용 |
|---|---|
| 심각도 | 낮음 |
| CWE | CWE-495 |
| 연관 설계항목 | — |

#### KISA 소프트웨어 개발보안 가이드(2021) 원문

**개요 (2021 원문)**: private 배열을 public 메서드가 반환하면 배열의 레퍼런스가 외부에 공개되어, 외부에서 배열과 객체 속성을 바꿀 수 있다.

**보안대책 (2021 원문)**: private 배열을 public 메서드로 반환하지 않는다. **복사본**을 반환하고, 원소가 가변 객체면 원소도 `clone()`으로 복사한다. 원소가 `String`처럼 불변이면 배열 복사본만 만들어 반환한다.

**2021 원문 예제 요지 (Java·C·C#)**: Java `return colors;` → 새 배열에 원소별 `clone()`해 반환 / `String[]`은 배열만 복사. C# `List<Color>` → 원소 `Clone()` 후 새 리스트 반환.

#### Python 시큐어코딩 가이드(2023) 원문 — 2장 6절 3항 (p.151~152)

- **Python 관련 설명**: 파이썬은 명시적 private 선언이 없다. 관례상 이름 앞 밑줄로 구분한다.

| 구분 | 표시 방법 |
|---|---|
| public | 속성·메서드는 기본적으로 public |
| protected | 이름 앞에 `_`(single underscore). 실제 제약보다는 관례 |
| private | 이름 앞에 `__`(double underscore). 네임 맹글링으로 `_클래스__멤버`로 접근은 가능하지만 바람직하지 않음 |

  public 메서드가 배열을 반환하면 참조가 외부에 공개되어 수정될 수 있으며, 이는 배열뿐 아니라 **변경 가능한(mutable) 모든 객체**에 해당한다.
- **안전한 코딩기법**: private 배열을 public 메서드로 그대로 반환하지 않고 **복사본**을 반환한다. 원소가 가변 객체면 원소도 복사하고, 불변(immutable)이면 배열 복사본만 반환한다.
- **원문 예제**

```python
# [가이드 원문] 안전하지 않은 코드
class UserObj:
    __private_variable = []

    def get_private_member(self):
        return self.__private_variable


# [가이드 원문] 안전한 코드 — [:]로 새 리스트 반환
class UserObj:
    __private_variable = []

    def get_private_member(self):
        return self.__private_variable[:]
```

- **검토 메모**: `[:]`는 **얕은 복사**라 원소가 dict·객체면 원소는 여전히 공유된다. 가이드 본문의 "원소도 복사"에 맞추려면 `copy.deepcopy()`가 필요하다. 또 가이드 예제처럼 `__private_variable = []`를 **클래스 속성**으로 두면 모든 인스턴스가 같은 리스트를 공유한다(ENC-01). `__init__`에서 인스턴스 속성으로 만드는 것을 권고한다.

#### 이 스킬의 점검 기준 (2021 가이드 + 실무 기준)

**Python 관점**: Python에는 접근 제어자가 없고 `_`/`__` 접두사는 관례다. 그래도 **내부 가변 컬렉션(list, dict, set)의 참조를 그대로 반환**하면 호출자가 객체 내부 상태(권한 목록, 허용목록, 설정)를 바꿀 수 있다. 보안 판단에 쓰는 내부 상태일 때 의미가 있다.

**탐지 패턴 (Python)**
- `return self._roles`, `return self._allowed_hosts`, `return self.__permissions` 등 내부 `list`/`dict`/`set`를 그대로 반환하는 메서드·`@property`
- 모듈 전역 허용목록·설정 dict를 함수가 그대로 반환 (`def get_config(): return CONFIG`)
- 캐시에서 꺼낸 가변 객체를 호출자가 수정 (캐시 오염)

**보충 예제 — 취약 코드**
```python
class User:
    def __init__(self, roles: list[str]):
        self._roles = roles

    @property
    def roles(self) -> list[str]:
        return self._roles          # 호출자가 user.roles.append("admin") 가능


ALLOWED_HOSTS = ["api.example.com"]


def get_allowed_hosts():
    return ALLOWED_HOSTS            # 반환값을 수정하면 전역 허용목록이 바뀜
```

**보충 예제 — 안전 코드 (권장 기준)**
```python
import copy
from types import MappingProxyType


class User:
    def __init__(self, roles):
        self._roles = tuple(roles)  # 불변 타입으로 보관

    @property
    def roles(self) -> tuple[str, ...]:
        return self._roles          # 불변이므로 그대로 반환해도 안전 (원문 String 배열 경우)


class Palette:
    def __init__(self, colors: list["Color"]):
        self._colors = colors

    def get_colors(self) -> list["Color"]:
        return copy.deepcopy(self._colors)  # 원소까지 복사 (원문 clone() 대응)


ALLOWED_HOSTS = frozenset({"api.example.com"})
CONFIG = MappingProxyType({"timeout": 10})  # 읽기 전용 dict 뷰
```

---

### ENC-04. Private 배열에 Public 데이터 할당

| 항목 | 내용 |
|---|---|
| 심각도 | 낮음 |
| CWE | CWE-496 |
| 연관 설계항목 | — |

#### KISA 소프트웨어 개발보안 가이드(2021) 원문

**개요 (2021 원문)**: public 메서드의 인자가 private 배열에 그대로 저장되면, 외부에서 그 배열에 접근해 배열과 객체 속성을 바꿀 수 있다.

**보안대책 (2021 원문)**: public 메서드의 인자를 private 배열에 **그대로 저장하지 않는다**. 인자 배열의 복사본을 만들고 원소도 `clone()`으로 복사해 할당한다. 원소가 불변이면 배열 복사본만 만들어 할당한다.

**2021 원문 예제 요지 (Java·C·C#)**: Java `this.userRoles = userRoles;` → 새 배열에 원소별 `clone()` / `String[]`은 배열만 복사. C# 동일.

#### Python 시큐어코딩 가이드(2023) 원문 — 2장 6절 4항 (p.153~154)

- **안전한 코딩기법**: public 메서드의 인자를 private 배열에 그대로 저장하지 않는다. 사용자가 전달한 값으로 클래스 외부에서 private 값을 바꾸면 안 되며, 필요하면 별도 인스턴스 변수로 정의하거나, 의도된 기능이면 **전달된 값의 정상 여부를 검증한 뒤** 적용한다.
- **원문 예제**

```python
# [가이드 원문] 안전하지 않은 코드 — 외부 리스트 참조를 그대로 저장
class UserObj:
    __private_variable = []

    def set_private_member(self, input_list):
        self.__private_variable = input_list


# [가이드 원문] 안전한 코드 — 인스턴스 변수 + [:] 복사본 저장
class UserObj:
    def __init__(self):
        self.__privateVariable = []

    def set_private_member(self, input_list):
        self.__privateVariable = input_list[:]
```

- **검토 메모**: 가이드가 강조한 "**검증 후 적용**"은 이 스킬의 기준(복사 후 검증, 검사 후 변경 방지)과 같다. 원소가 가변이면 `deepcopy`, 가능하면 `tuple`/`frozenset`으로 불변화한다.

#### 이 스킬의 점검 기준 (2021 가이드 + 실무 기준)

**탐지 패턴 (Python)**
- 생성자·setter에서 인자로 받은 `list`/`dict`/`set`을 그대로 `self._x = arg`로 저장하고, 그 값이 보안 판단(권한, 허용목록, 검증된 데이터)에 쓰임
- 검증 후 저장한 가변 객체를 호출자가 나중에 변경 (검증 우회: "검사 후 변경")

**보충 예제 — 취약 코드**
```python
class Account:
    def set_user_roles(self, user_roles: list[str]) -> None:
        validate_roles(user_roles)
        self._user_roles = user_roles  # 호출자가 검증 후 리스트에 "admin"을 추가하면 반영됨


roles = ["viewer"]
acc = Account()
acc.set_user_roles(roles)
roles.append("admin")                  # 검증을 우회해 내부 상태 변경
```

**보충 예제 — 안전 코드 (권장 기준)**
```python
import copy


class Account:
    def set_user_roles(self, user_roles) -> None:
        roles = tuple(user_roles)              # 먼저 복사(불변화)한 뒤
        validate_roles(roles)                  # 복사본을 검증
        self._user_roles = roles


class Team:
    def set_members(self, members: list["Member"]) -> None:
        self._members = copy.deepcopy(members)  # 가변 원소는 깊은 복사 (원문 clone() 대응)
```

**판정 기준 / 오탐 주의 (ENC-03·04 공통)**
- Python에서는 성능·관례상 참조 공유가 흔하다. **보안 판단에 쓰이는 내부 상태**이거나 **검증 후 저장**하는 경우만 지적한다.
- pydantic 모델(`frozen=True`), `dataclass(frozen=True)`, `tuple`/`frozenset` 사용이면 충족이다.

---

## 제7절 API 오용

**정의**: 의도된 사용에 반하는 방법으로 API를 쓰거나, 보안에 취약한 API를 써서 생기는 보안약점.

### API-01. DNS lookup에 의존한 보안결정

| 항목 | 내용 |
|---|---|
| 심각도 | 중간 |
| CWE | CWE-350, CWE-247 |
| 연관 설계항목 | SR2-1 |

#### KISA 소프트웨어 개발보안 가이드(2021) 원문

**개요 (2021 원문)**: 공격자가 DNS 엔트리를 속일 수 있으므로 **도메인명에 의존해 보안결정**(인증, 접근 통제 등)을 하면 안 된다. 로컬 DNS 서버 캐시가 오염되면 사용자와 서버 간 트래픽이 공격자를 거치게 하거나, 공격자가 같은 도메인의 서버인 것처럼 위장할 수 있다.

**보안대책 (2021 원문)**: 보안결정에서 도메인명을 이용한 DNS lookup을 하지 않는다. **IP 주소를 직접 비교**한다.

**2021 원문 예제 요지 (Java·C·C#)**: Java `InetAddress.getByName(ip).getCanonicalHostName().endsWith("trustme.com")` → `ip.equals(trustedAddr)`. C# `Dns.GetHostByAddress` 후 `EndsWith("trust.com")` → IP 직접 비교. C `gethostbyaddr` 결과 호스트명 비교 → IP 비교.

#### Python 시큐어코딩 가이드(2023) 원문 — 2장 7절 1항 (p.155~156)

- **안전한 코딩기법**: 보안결정에서 도메인명을 이용한 DNS lookup을 하지 않는다. 도메인명 비교 대신 **IP 주소를 직접 비교**한다.
- **원문 예제**

```python
import socket


# [가이드 원문] 안전하지 않은 코드 — 도메인명으로 신뢰 판단 (원문 변수명 오류를 바로잡음)
def is_trust(host_domain_name):
    trusted = False
    trusted_host = "trust.example.com"
    if trusted_host == host_domain_name:
        trusted = True
    return trusted


# [가이드 원문] 안전한 코드 — 이름을 IP로 해석해 신뢰 IP와 비교
def is_trust(host_domain_name):
    trusted = False
    trusted_ip = "192.168.10.7"
    dns_resolved_ip = socket.gethostbyname(host_domain_name)
    if trusted_ip == dns_resolved_ip:
        trusted = True
    return trusted
```

- **검토 메모 (중요)**: 가이드 안전 예제는 `socket.gethostbyname()`으로 **정방향 DNS 조회를 한 결과**를 비교하므로, DNS 응답을 조작하면(캐시 오염, 공격자 도메인을 `192.168.10.7`로 응답) 여전히 통과한다. 즉 **DNS에 의존한 보안결정**이 그대로 남아 있다. 판정은 이 스킬 API-01 기준대로 **실제 연결의 원격 IP(`request.remote_addr`, `sock.getpeername()`)를 신뢰 IP·대역과 직접 비교**하고, 가능하면 인증(mTLS 등)을 함께 쓰는 방식을 기준으로 한다.

#### 이 스킬의 점검 기준 (2021 가이드 + 실무 기준)

**탐지 패턴 (Python)**
- `socket.gethostbyaddr(ip)`, `socket.getfqdn(ip)`, `dns.reversename`+`dns.resolver.resolve(..., "PTR")` 결과로 `endswith("trusted.com")` 같은 신뢰 판단
- `request.remote_addr`를 역조회한 호스트명으로 관리자·내부망 판정
- `Host` 헤더·`request.host`로 신뢰 판단 (`if request.host.endswith(".internal")`)
- 호스트명 문자열 부분 일치로 허용 (`"trusted.com" in hostname` → `trusted.com.evil.net` 통과)
- `X-Forwarded-For`를 그대로 신뢰 (INP-15와 연결)

**보충 예제 — 취약 코드**
```python
import socket


@app.route("/internal/report")
def internal_report():
    ip = request.remote_addr
    hostname, _, _ = socket.gethostbyaddr(ip)  # PTR 레코드는 IP 소유자가 마음대로 설정 가능
    if hostname.endswith("trustme.com"):
        return do_something_for_trust_system()
    abort(403)
```

**보충 예제 — 안전 코드 (권장 기준)**
```python
import ipaddress

TRUSTED_NETWORKS = [ipaddress.ip_network("10.0.10.0/24"), ipaddress.ip_network("127.0.0.1/32")]


@app.route("/internal/report")
@login_required                       # IP 제한은 보조 수단, 인증을 함께 적용
def internal_report():
    ip_str = request.remote_addr      # 프록시 뒤라면 ProxyFix 등 신뢰 프록시 설정 후 사용
    if not ip_str:
        abort(403)
    ip = ipaddress.ip_address(ip_str)
    if not any(ip in net for net in TRUSTED_NETWORKS):  # 원문 'IP 직접 비교' 대응
        abort(403)
    return do_something_for_trust_system()
```

**판정 기준 / 오탐 주의**
- 로깅·표시용 역조회는 문제가 아니다. **허용/거부 판단**에 쓰이는지 확인한다.
- IP 기반 통제도 단독으로는 약하다(스푸핑·NAT·프록시). 인증·mTLS와 함께 쓰도록 권고한다.

---

### API-02. 취약한 API 사용

| 항목 | 내용 |
|---|---|
| 심각도 | API별 상이 (아래 표) |
| CWE | CWE-676, CWE-242, CWE-246, CWE-382 |
| 연관 설계항목 | — |

#### KISA 소프트웨어 개발보안 가이드(2021) 원문

**개요 (2021 원문)**: 취약한 API는 보안상 **금지된(banned) 함수**이거나 부주의하게 쓰일 가능성이 높은 API다. 금지 API의 예는 문자열 관련 `gets()`, `strcat()`, `strcpy()`, `strncat()`, `strncpy()`, `sprintf()` 등이다. 보안상 문제가 없는 함수라도 잘못된 방식으로 쓰면 문제가 된다.

**보안대책 (2021 원문)**: 금지된 함수는 안전한 대체 함수(`gets_s()/fgets()`, `strcat_s()`, `strcpy_s()`, `strncat_s()`, `strncpy_s()`, `sprintf_s()` 등)로 바꾼다. `strtol()`을 작은 정수형 변환에 쓰는 것처럼 금지는 아니지만 취약한 사용도 주의한다. 개발 조직이 취약 API 목록을 정했다면 **반드시 준수**한다.

**2021 원문 예제 요지 (Java·C·C#)**: C `gets(str)` → `gets_s(str, sizeof(str))`. Java 서블릿에서 소켓 직접 사용 → 프레임워크의 `URLConnection`. J2EE에서 `System.exit(1)` → 사용 금지. C# `Application.Exit()` → `this.Close()`.

**Python 취약 API 목록 (조직 기준으로 쓸 수 있도록 정리)**

| 분류 | 취약·주의 API | 대체 / 조건 | 관련 항목 |
|---|---|---|---|
| 코드 실행 | `eval`, `exec`, `compile`, `__import__`(외부 입력) | `ast.literal_eval`, 허용목록 디스패치 | INP-02 |
| 명령 실행 | `os.system`, `os.popen`, `subprocess.*(shell=True)`, `commands.*`, `pty.spawn` | `subprocess.run([...], shell=False)` | INP-05 |
| 역직렬화 | `pickle.load(s)`, `marshal.load(s)`, `shelve`, `yaml.load`(unsafe Loader), `jsonpickle.decode`, `torch.load`(weights_only=False) | `json`, `yaml.safe_load`, `safetensors` | COD-05 |
| XML | `xml.etree`·`minidom`·`sax`·`lxml`(외부 입력, 안전 설정 없음) | `defusedxml`, lxml 안전 파서 | INP-08 |
| 임시파일 | `tempfile.mktemp` | `tempfile.mkstemp`, `NamedTemporaryFile` | TIM-01 |
| 난수 | `random.*`(보안 용도) | `secrets`, `os.urandom` | SEC-08 |
| 해시·암호 | `hashlib.md5/sha1`(보안 용도), `Crypto.Cipher.DES/ARC4/Blowfish`, `MODE_ECB`, `pycrypto` 패키지 | `hashlib.sha256+`, `cryptography` AES-GCM | SEC-04 |
| TLS | `ssl._create_unverified_context`, `verify=False`, `CERT_NONE`, `PROTOCOL_SSLv*/TLSv1/TLSv1_1` | `ssl.create_default_context()` | SEC-11 |
| 평문 프로토콜 | `telnetlib`, `ftplib.FTP`, `smtplib.SMTP`(STARTTLS 없음), `http://` | SFTP/FTPS, `SMTP_SSL`/`starttls(context=)`, HTTPS | SEC-05 |
| 입력 | Python 2 `input()`(eval 동작) | Python 3 `input()`, `raw_input` | INP-02 |
| 아카이브 | `tarfile.extractall`(필터 없음), `zipfile.extractall`(외부 아카이브) | 경로 검증, `filter="data"`(3.12+) | INP-03 |
| 프로세스 종료 | 웹 요청 처리 중 `sys.exit()`, `os._exit()`, `quit()`, `exit()` | 예외 발생·HTTP 오류 응답 | 원문 System.exit |
| 저수준 소켓 | 웹 앱에서 `socket` 직접 HTTP 구현 | `requests`/`httpx`(TLS 검증·타임아웃 지원) | 원문 Direct Use of Sockets |
| 검증용 assert | `assert`로 권한·입력 검증 | `if ...: raise`/`abort` | ERR-03 |
| 네이티브 | `ctypes`/`cffi`에서 `strcpy`·`sprintf`·`gets` 등 C 금지 함수 호출 | 길이 지정 함수 | INP-16 |
| 템플릿 | `render_template_string`(외부 입력), `Markup()`/`mark_safe()`(외부 입력) | 파일 템플릿 + 변수 전달 | INP-02, INP-04 |
| 요청 | `requests.*`·`urlopen` 타임아웃 미지정 | `timeout=` 지정 | TIM-02 |

#### Python 시큐어코딩 가이드(2023) 원문 — 2장 7절 2항 (p.157~161) ※ 2021 가이드(금지 함수 중심)와 관점이 다르다: **외부 패키지(공급망) 관리**

- **Python 관련 설명**: 파이썬은 **외부 의존성을 기본으로 하는 생태계**다. 패키지는 다른 개발자가 작성한 코드로 의도적인 악성코드를 포함할 수 있고, 의도하지 않은 오류·약점으로 보안 문제를 일으킬 수 있다. `pip`가 설치하는 **PyPI는 누구나 패키지를 등록**할 수 있다. 안전하지 않다고 알려진 패키지 목록은 PyPI가 따로 관리하지만, 잘 알려지지 않은 패키지의 위험은 남는다.
  - 보안 문제 원인 2가지: ① **사용자 배포 패키지 내 결함**(완화: 취약 패키지·취약 버전을 쓰지 않거나, 함수 실행 전후 보호 루틴 적용) ② **언어 엔진 자체 결함**(기본 제공 패키지. 개선된 버전으로 업데이트해 완화 — 원문에는 "Node.js 버전"으로 잘못 적혀 있으며 파이썬 버전 업데이트를 뜻함)
- **안전한 API 선택 — 패키지 도입 전 검토 항목**
  - **사용 통계**: 다운로드 수, 선호도
  - **이슈 관리**: 버그·이슈 처리 방식
  - **마지막 버전**: 유지관리 상태
  - **발견된 취약점**: 특정 버전의 취약점과 수정 버전 공개 여부 (**개발 완료 시점에 한 번 더 확인**)
  - 취약점 검색: NIST NVD(`https://nvd.nist.gov/vuln/search`), CVEdetails(`https://www.cvedetails.com`). 사용(예정) 버전에 영향이 있으면 패치 버전을 적용하고, 패치가 없으면 아래 사후 관리 절차를 따른다.
- **사후 관리 — SBOM(Software Bill of Materials)**: 오픈소스를 쓰는 제품은 SBOM을 적용한다. NTIA가 제시한 필수 구성요소는 **공급자 이름, 컴포넌트 이름, 컴포넌트 버전, 컴포넌트 해시, 고유 식별자(UID), 의존 관계, 작성자**다.
  - SBOM 기반 취약점 대응 절차: 1) 신규 취약점 인지 → 2) SBOM 목록에서 관련 컴포넌트 탐색 → 3) 존재 시 (1) 사내 정보 공유, (2-1) 보안 솔루션(침입탐지) 정책 반영, (2-2) 소스코드 수정·임시 예외처리(외부 관리면 상황 전파·결과 회신), (3) 패키지 업데이트 → 4) SBOM 목록 최신화

- **정적 점검 반영 방법 (이 스킬의 해석)**
  - 의존성 파일 확인: `requirements*.txt`, `pyproject.toml`, `poetry.lock`, `Pipfile.lock`, `setup.py`/`setup.cfg`
  - 버전 고정 여부: 버전 미지정(`requests`), 범위만 지정(`>=`)이면 재현성·공급망 위험으로 지적. 잠금 파일·해시(`--require-hashes`) 사용 권고(SEC-15와 연결)
  - 알려진 취약 버전: `pip-audit -r requirements.txt` 또는 `safety`로 확인. 도구를 실행할 수 없으면 주요 패키지(Django, Flask, Werkzeug, Jinja2, requests, urllib3, PyYAML, Pillow, cryptography, lxml) 버전을 보고서에 적고 "취약점 DB 확인 필요"로 표시
  - 유지보수 종료 패키지: `pycrypto`(→ `pycryptodome`), Python 2 전용 패키지, 오래 갱신되지 않은 패키지
  - 타이포스쿼팅 의심 이름(예: `reqeusts`, `python-dateutils`), 출처가 불분명한 Git URL·사설 인덱스(`--extra-index-url`) 의존성
  - SBOM 생성 여부: `cyclonedx-py`(CycloneDX), `syft` 등으로 생성한 SBOM 파일이 저장소·CI에 있는지 확인하고, 없으면 생성을 권고
- **검토 메모**: 2021 가이드의 API-02 내용(금지 함수·잘못된 함수 사용)은 이 스킬의 "Python 취약 API 표"로 계속 점검한다. 두 가이드를 합쳐 **① 위험 함수 사용 ② 취약·미관리 의존성** 두 축으로 보고한다.

#### 이 스킬의 점검 기준 (2021 가이드 + 실무 기준)

**보충 예제 — 취약 코드**
```python
import sys
import tempfile


@app.route("/shutdown-on-error")
def handler():
    try:
        do_something()
    except OSError:
        logger.info("ERROR")
        sys.exit(1)               # 원문 System.exit 대응: 워커 프로세스 종료 → 서비스 중단


tmp_name = tempfile.mktemp()      # 이름만 만들고 파일은 나중에 생성 → 경쟁조건
with open(tmp_name, "w") as f:
    f.write(data)
```

**보충 예제 — 안전 코드 (권장 기준)**
```python
import tempfile


@app.route("/shutdown-on-error")
def handler():
    try:
        do_something()
    except OSError:
        logger.exception("ERROR")
        abort(500)                # 요청 단위로 실패 처리, 프로세스는 유지


with tempfile.NamedTemporaryFile("w", delete=False) as f:  # 원자적 생성, 0o600
    f.write(data)
    tmp_name = f.name
```

**판정 기준 / 오탐 주의**
- 표의 API 사용 자체가 아니라 **외부 입력 도달 여부와 용도**로 판정한다. 예: `hashlib.md5`를 캐시 키로 쓰는 것은 정상.
- 자동화 도구 대응: bandit(B102 exec, B301 pickle, B307 eval, B324 md5/sha1, B501 verify=False, B506 yaml.load, B602 shell=True, B608 SQL 문자열 등), semgrep `p/python`, ruff `S` 규칙(flake8-bandit). 정적 검사 결과를 이 표의 항목 ID로 매핑해 보고한다.
