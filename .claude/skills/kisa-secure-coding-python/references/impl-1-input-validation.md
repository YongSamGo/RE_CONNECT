# 구현단계 보안약점 — 제1절 입력데이터 검증 및 표현 (INP-01 ~ INP-17)

> 출처
> - KISA·행정안전부 「소프트웨어 개발보안 가이드」(2021.12) 제4장 제1절 — 원문 예제는 Java·C·C#
> - KISA 「Python 시큐어코딩 가이드」(2023 개정본) 2장 제1절 — 원문 예제는 Python(Django·Flask 중심)
>
> 항목마다 다음 순서로 정리했다.
> 1. **KISA 소프트웨어 개발보안 가이드(2021) 원문**: 개요, 보안대책, Java·C·C# 예제 요지
> 2. **Python 시큐어코딩 가이드(2023) 원문**: Python 관련 설명, 안전한 코딩기법, 원문 Python 예제(따옴표·들여쓰기·변수명 오타 등 표기 오류만 정리), **검토 메모**(가이드 예제 자체의 약점, 다른 항목과 충돌하는 부분)
> 3. **이 스킬의 점검 기준**: 탐지 패턴, 보충 예제(2021 원문 취지를 옮기거나 실무 기준으로 보강한 코드), 판정 기준
>
> 심각도(높음/중간/낮음)는 두 가이드 모두에 없는 값으로, 우선순위를 정하기 위해 붙인 것이다.

**정의**: 프로그램 입력값의 검증 누락이나 부적절한 검증, 데이터의 잘못된 형식 지정, 일관되지 않은 언어셋 사용 등으로 생기는 보안약점. SQL 삽입, XSS 등의 공격을 유발할 수 있다.

**공통 소스(외부 입력)** — 아래 값이 싱크에 도달하는지 추적한다.
- Flask/Werkzeug: `request.args`, `request.form`, `request.values`, `request.json`, `request.get_json()`, `request.data`, `request.files`, `request.cookies`, `request.headers`, `request.view_args`, URL 변수
- Django: `request.GET`, `request.POST`, `request.body`, `request.FILES`, `request.COOKIES`, `request.META`, `request.headers`, URL kwargs
- FastAPI/Starlette: 경로·쿼리·바디 파라미터, `Request.query_params`, `Request.json()`, `Header()`, `Cookie()`, `Form()`, `UploadFile`
- 그 외: `sys.argv`, `input()`, `os.environ`, 파일·소켓·메시지큐에서 읽은 값, 외부 API 응답, **DB에서 읽은 값**(저장형 공격)

---

### INP-01. SQL 삽입 (SQL Injection)

| 항목 | 내용 |
|---|---|
| 심각도 | 높음 |
| CWE | CWE-89 |
| 연관 설계항목 | SR1-1 |

#### KISA 소프트웨어 개발보안 가이드(2021) 원문

**개요 (2021 원문)**: DB와 연동된 웹 응용프로그램에서 입력 데이터의 유효성을 검증하지 않으면, 공격자가 입력 폼이나 URL에 SQL 문을 삽입해 DB 정보를 열람하거나 조작할 수 있다. 사용자 입력을 필터링 없이 받아 **동적 쿼리**를 만들기 때문에 의도하지 않은 쿼리가 생성된다.

**보안대책 (2021 원문)**: PreparedStatement 같은 객체로 DB에 컴파일된 쿼리문(상수)을 전달한다. 외부 입력값의 특수문자와 쿼리 예약어를 필터링하고, 프레임워크를 쓰면 입력값 검증모듈과 보안모듈을 상황에 맞게 사용한다.

**2021 원문 예제 요지 (Java·C·C#)**: JDBC `"... WHERE b_gubun = '" + gubun + "'"` → `?` 바인딩. MyBatis `${keyword}` → `#{keyword}`. Hibernate 문자열 연결 HQL → `?` 또는 `:name` 바인딩. C# 문자열 연결 → `@ProductID` 파라미터.

#### Python 시큐어코딩 가이드(2023) 원문 — 2장 1절 1항 (p.8~13)

- **Python 관련 설명**: 파이썬은 DB 모듈 간 일관성을 위해 DB-API를 정의하며, Django·SQLAlchemy·Storm 같은 ORM으로도 DB에 접근한다. ORM은 기본적으로 인자화된 쿼리를 쓰므로 안전하지만, 복잡한 조건·성능 문제로 **원시 SQL**을 직접 실행할 때 외부 입력을 검증 없이 쓰면 SQL 삽입이 생긴다.
- **안전한 코딩기법**: DB-API는 인자화된 쿼리로 외부 입력을 바인딩한다. ORM 안에서 원시 SQL을 쓸 때도 외부 입력은 바인딩 변수로만 쓴다. SQLite는 `?` 또는 `:name` 플레이스홀더를 쓴다.
- **원문 예제** (따옴표·들여쓰기 등 표기 오류만 정리)

```python
# [가이드 원문] 안전하지 않은 코드 — DB-API (Django connection)
def update_board(request):
    dbconn = connection
    with dbconn.cursor() as curs:
        name = request.POST.get('name', '')
        content_id = request.POST.get('content_id', '')
        # 검증되지 않은 입력값으로 동적 쿼리문 생성
        sql_query = "update board set name='" + name + "' where content_id='" + content_id + "'"
        curs.execute(sql_query)
        dbconn.commit()
        return render(request, '/success.html')


# [가이드 원문] 안전한 코드 — 인자화된 쿼리 + execute() 두 번째 인자로 바인딩
def update_board(request):
    dbconn = connection
    with dbconn.cursor() as curs:
        name = request.POST.get('name', '')
        content_id = request.POST.get('content_id', '')
        sql_query = 'update board set name=%s where content_id=%s'
        curs.execute(sql_query, (name, content_id))
        dbconn.commit()
        return render(request, '/success.html')


# [가이드 원문] 안전하지 않은 코드 — Django Manager.raw()
def member_search(request):
    name = request.POST.get('name', '')
    query = "select * from member where name='" + name + "'"
    data = Member.objects.raw(query)
    return render(request, '/member_list.html', {'member_list': data})


# [가이드 원문] 안전한 코드 — raw()의 params 인자로 바인딩 (list는 %s, dict는 %(key)s)
def member_search(request):
    name = request.POST.get('name', '')
    query = 'select * from member where name=%s'
    data = Member.objects.raw(query, [name])
    return render(request, '/member_list.html', {'member_list': data})
```

- **검토 메모**: 가이드 예시 `content_id = 'a' or 'a'='a` 입력 시 board 테이블 전체의 name이 변경된다. 판정 기준은 이 스킬과 같다.

#### 이 스킬의 점검 기준 (2021 가이드 + 실무 기준)

**탐지 패턴 (Python)**
- 싱크: `cursor.execute(`, `cursor.executemany(`, `cursor.executescript(`, `connection.execute(`, `engine.execute(`, `session.execute(`, `text(`, `Model.objects.raw(`, `.extra(`, `RawSQL(`, `connection.cursor().execute(`, `pd.read_sql(`, `pd.read_sql_query(`
- 위험 신호: 싱크의 첫 번째 인자가 다음 중 하나
  - f-string: `execute(f"... {x} ...")`
  - `%` 포맷: `execute("... %s ..." % x)` ← **인자 튜플을 두 번째 인자로 넘기는 바인딩과 구분할 것**
  - `.format()`: `execute("... {} ...".format(x))`
  - 문자열 연결: `execute("..." + x)`, 또는 앞에서 연결해 만든 변수
- SQLAlchemy `text()` 안의 f-string, `order_by(text(입력값))`, `literal_column(입력값)`
- Django `.extra(where=[f"..."])`, `.raw(f"...")`, `RawSQL(f"...")`
- 동적 식별자(테이블·컬럼·정렬방향)를 입력에서 받아 그대로 넣는 경우 — 바인딩이 불가능한 위치이므로 허용목록 필요

**보충 예제 — 취약 코드**
```python
# Flask + sqlite3 — 원문 JDBC 예제 대응
@app.route("/board")
def board():
    gubun = request.args.get("gubun", "")
    sql = "SELECT * FROM board WHERE b_gubun = '" + gubun + "'"
    rows = db.execute(sql).fetchall()  # gubun = a' or 'a'='a 이면 전체 조회
    return render_template("board.html", rows=rows)


# SQLAlchemy — 원문 Hibernate 예제 대응
name = request.args["name"]
result = session.execute(text(f"SELECT * FROM student WHERE student_name = '{name}'"))
```

**보충 예제 — 안전 코드 (권장 기준)**
```python
@app.route("/board")
def board():
    gubun = request.args.get("gubun", "")
    # DB-API 파라미터 바인딩 (sqlite3는 ?, psycopg/pymysql은 %s)
    rows = db.execute("SELECT * FROM board WHERE b_gubun = ?", (gubun,)).fetchall()
    return render_template("board.html", rows=rows)


# SQLAlchemy 명명 파라미터
result = session.execute(
    text("SELECT * FROM student WHERE student_name = :name"), {"name": name}
)

# ORM 사용
students = session.scalars(select(Student).where(Student.student_name == name)).all()
students = Student.objects.filter(student_name=name)  # Django

# LIKE 검색 — 원문 MyBatis '%'||#{keyword}||'%' 대응
rows = db.execute(
    "SELECT * FROM tbl_board WHERE title LIKE ? ORDER BY pos ASC", (f"%{keyword}%",)
).fetchall()

# 바인딩할 수 없는 식별자는 허용목록으로 선택
ALLOWED_SORT = {"date": "created_at", "title": "title"}
column = ALLOWED_SORT.get(request.args.get("sort"), "created_at")
rows = db.execute(f"SELECT * FROM board ORDER BY {column}").fetchall()
```

**판정 기준 / 오탐 주의**
- `execute("... %s", (x,))` 처럼 SQL 문자열과 값이 **별도 인자**로 넘어가면 안전(바인딩)이다.
- f-string에 들어간 값이 코드 상수나 허용목록 결과뿐이면 오탐이다. 값의 출처를 역추적해서 판단한다.
- `LIKE` 검색값에서 `%`, `_` 와일드카드 이스케이프가 필요한지도 함께 본다(정보노출·DoS 측면).
- DB 계정 권한(SR1-1 ①)도 함께 점검한다.

---

### INP-02. 코드 삽입 (Code Injection)

| 항목 | 내용 |
|---|---|
| 심각도 | 높음 |
| CWE | CWE-94, CWE-95 |
| 연관 설계항목 | SR1-4 |

#### KISA 소프트웨어 개발보안 가이드(2021) 원문

**개요 (2021 원문)**: 공격자가 임의 코드를 삽입해 소프트웨어가 비정상적으로 동작하게 하는 보안약점이다. 프로그래밍 언어 자체의 기능으로만 제한된다는 점에서 운영체제 명령어 삽입과 다르다. 사용자 입력에 코드가 포함되도록 허용하면 권한 탈취, 인증 우회, 시스템 명령어 실행 등이 가능해진다.

**보안대책 (2021 원문)**: 동적 코드를 실행하는 함수를 쓰지 않는다. 필요하면 실행 가능한 동적 코드를 입력으로 받지 않도록 **화이트리스트** 방식으로 구현하거나, 유효한 문자만 포함하도록 입력값을 필터링한다.

**2021 원문 예제 요지 (Java·C·C#)**: Java `ScriptEngine.eval(src)`, JSP의 `new Function(<%=name%>)` → 정규식 `[\w]*` 검사, 또는 입력값을 허용된 키워드(`UNDER_BAR`, `DOLLAR`)로만 받아 해당 메소드 호출.

#### Python 시큐어코딩 가이드(2023) 원문 — 2장 1절 2항 (p.14~17)

- **Python 관련 설명**: 파이썬에서 코드 삽입을 유발하는 함수는 `eval()`, `exec()` 등이다. 예: `"compile('for x in range(1):\n import time\n time.sleep(20)','a','single')"` 입력으로 20초간 sleep 상태가 된다. `__import__('platform').system()` 입력으로 시스템 정보가 노출된다.
- **안전한 코딩기법**: 동적 코드 실행 함수를 쓰지 않는다. 필요하면 화이트리스트로 검증하거나, 유효한 문자만 포함하도록 필터링한다. 검증용 문자열 메서드 `str.isalpha()`, `str.isdecimal()`, `str.isdigit()`(위 첨자 숫자도 True), `str.isalnum()`과 `re` 정규식(예: 이메일 형식)을 쓴다.
- **원문 예제**

```python
# [가이드 원문] 안전하지 않은 코드 — eval()
def route(request):
    message = request.POST.get('message', '')
    ret = eval(message)
    return render(request, '/success.html', {'data': ret})


# [가이드 원문] 안전한 코드 — 영문·숫자만 허용한 뒤 eval()
def route(request):
    message = request.POST.get('message', '')
    if message.isalnum():
        ret = eval(message)
        return render(request, '/success.html', {'data': ret})
    return render(request, '/error.html')


# [가이드 원문] 안전하지 않은 코드 — exec()로 사용자 지정 함수 호출
def request_rest_api(request):
    function_name = request.POST.get('function_name', '')
    exec('{}()'.format(function_name))
    return render(request, '/success.html')


# [가이드 원문] 안전한 코드 — 화이트리스트 함수만 실행
WHITE_LIST = ['get_friends_list', 'get_address', 'get_phone_number']


def request_rest_api(request):
    function_name = request.POST.get('function_name', '')
    if function_name in WHITE_LIST:
        exec('{}()'.format(function_name))
        return render(request, '/success.html')
    return render(request, '/error.html', {'error': '허용되지 않은 함수입니다.'})
```

- **검토 메모**: 가이드의 `isalnum()` 후 `eval()`은 괄호·점이 막혀 공격면이 크게 줄지만, 영숫자 식별자만으로도 전역 변수 값(예: `SECRET_KEY`)을 읽을 수 있다. 판정 시 **eval을 쓰지 않는 구조(허용목록 dict 디스패치, `ast.literal_eval`)를 우선 권고**하고, isalnum 검증만 있으면 "부분충족"으로 본다. exec 화이트리스트 예제도 `exec` 대신 `{이름: 함수}` dict로 호출하는 편이 안전하다.

#### 이 스킬의 점검 기준 (2021 가이드 + 실무 기준)

**탐지 패턴 (Python)**
- 싱크: `eval(`, `exec(`, `compile(`, `execfile(`, `__import__(`, `importlib.import_module(`, `getattr(obj, 입력값)`, `setattr(`, `globals()[입력값]`, `locals()[입력값]`
- 템플릿 엔진을 통한 코드 실행(SSTI): `render_template_string(입력값)`, `jinja2.Template(입력값).render()`, `Environment().from_string(입력값)`, Django `Template(입력값)`, Mako `Template(입력값)`
- 역직렬화 계열은 COD-05에서 다룬다 (`pickle`, `yaml.load`)
- `numexpr.evaluate`, `pandas.eval`, `DataFrame.query`에 외부 입력
- 브라우저 측: 템플릿에서 `<script>`에 서버 값을 넣고 `eval`/`new Function`/`setTimeout(문자열)` 실행

**보충 예제 — 취약 코드**
```python
@app.route("/execute")
def execute():
    src = request.args.get("src", "")
    return str(eval(src))  # src="__import__('os').system('id')" 로 명령 실행


@app.route("/hello")
def hello():
    name = request.args.get("name", "")
    # SSTI: name="{{ config.items() }}" 등으로 서버 정보 노출·코드 실행
    return render_template_string("<h1>Hello " + name + "</h1>")
```

**보충 예제 — 안전 코드 (권장 기준)**
```python
import ast
import operator

# 1) 화이트리스트: 입력은 '어떤 기능을 쓸지' 선택자로만 사용 (원문 UNDER_BAR/DOLLAR 예제 대응)
ACTIONS = {"UNDER_BAR": handle_underbar, "DOLLAR": handle_dollar}


@app.route("/execute")
def execute():
    action = ACTIONS.get(request.args.get("src", ""))
    if action is None:
        abort(400)
    return action()


# 2) 값 파싱이 목적이면 eval 대신 ast.literal_eval / json.loads
value = ast.literal_eval(request.args["value"])  # 리터럴(숫자·문자열·리스트 등)만 허용

# 3) 계산기가 필요하면 허용 연산자만 가진 AST 평가기를 직접 구현
_OPS = {ast.Add: operator.add, ast.Sub: operator.sub,
        ast.Mult: operator.mul, ast.Div: operator.truediv}


def safe_calc(expr: str) -> float:
    def _eval(node):
        if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)):
            return node.value
        if isinstance(node, ast.BinOp) and type(node.op) in _OPS:
            return _OPS[type(node.op)](_eval(node.left), _eval(node.right))
        raise ValueError("허용되지 않은 식")
    return _eval(ast.parse(expr, mode="eval").body)


# 4) 템플릿은 고정 문자열, 사용자 값은 변수로 전달
@app.route("/hello")
def hello():
    return render_template_string("<h1>Hello {{ name }}</h1>",
                                  name=request.args.get("name", ""))
```

**판정 기준 / 오탐 주의**
- `eval`/`exec`의 인자가 코드 상수뿐이면 위험도는 낮지만, 유지보수 리스크로 "주의"를 남긴다.
- `getattr(obj, name)`은 `name`이 허용목록으로 제한되면 안전하다. `__class__`, `__globals__`, `__subclasses__` 같은 dunder 접근이 가능한지 본다.
- 원문의 "정규식으로 특수문자 차단"은 Python `eval`에는 충분하지 않다(괄호·점 없이도 공격 가능한 경우가 있음). 허용목록이나 `literal_eval`을 우선한다.

---

### INP-03. 경로 조작 및 자원 삽입 (Path Traversal / Resource Injection)

| 항목 | 내용 |
|---|---|
| 심각도 | 높음 |
| CWE | CWE-22, CWE-99 |
| 연관 설계항목 | SR1-4, SR1-10 |

#### KISA 소프트웨어 개발보안 가이드(2021) 원문

**개요 (2021 원문)**: 검증되지 않은 외부 입력값으로 파일이나 서버 등 시스템 자원에 접근하거나 식별하게 허용하면, 입력값 조작으로 보호 자원에 임의 접근할 수 있다. 자원 수정·삭제, 시스템 정보 누출, 자원 충돌로 인한 서비스 장애를 일으키고, 허용되지 않은 권한으로 설정 파일을 바꾸거나 실행할 수 있다.

**보안대책 (2021 원문)**: 외부 입력을 자원(파일, 소켓 포트 등)의 식별자로 쓸 때는 적절히 검증하거나 **사전에 정의된 리스트에서 선택**하게 한다. 입력이 파일명이면 경로순회 위험 문자(`"`, `/`, `\`, `..` 등)를 제거하는 필터를 쓴다.

**2021 원문 예제 요지 (Java·C·C#)**: Java `new FileInputStream("C:/datas/" + fileName)` → `..`, `/`, `\` 제거. 도움말 파일 `safeDir + args[0]` → null 확인 후 `\.{2,}[/\\]` 제거. C# `File.Delete(Request.QueryString["path"])` → `\`, `/` 포함 시 거부. C `fopen(getenv("reportfile"))` → `..` 정규식 탐지.

#### Python 시큐어코딩 가이드(2023) 원문 — 2장 1절 3항 (p.18~21)

- **Python 관련 설명**: `subprocess.Popen()`처럼 프로세스를 여는 함수, `os.pipe()`처럼 파이프를 여는 함수, `socket` 연결 등에 외부 입력을 검증 없이 쓰면 경로 조작·자원 삽입이 생긴다.
- **안전한 코딩기법**: 자원 식별자로 쓰는 외부 입력은 검증하거나 사전 정의 목록에서만 선택한다. 파일명이면 `/`, `\`, `..` 등을 필터로 제거한다(`replace` 외에 `re.sub`, `filter`도 가능).
- **원문 예제**

```python
# [가이드 원문] 안전하지 않은 코드 — 확장자만 확인하고 경로를 그대로 open
def get_info(request):
    request_file = request.POST.get('request_file')
    (filename, file_ext) = os.path.splitext(request_file)
    file_ext = file_ext.lower()
    if file_ext not in ['.txt', '.csv']:
        return render(request, '/error.html', {'error': '파일을 열 수 없습니다.'})
    with open(request_file) as f:   # ../../../../etc/passwd 등
        data = f.read()
    return render(request, '/success.html', {'data': data})


# [가이드 원문] 안전한 코드 — 파일명에서 경로 조작 문자 제거
def get_info(request):
    request_file = request.POST.get('request_file')
    (filename, file_ext) = os.path.splitext(request_file)
    file_ext = file_ext.lower()
    if file_ext not in ['.txt', '.csv']:
        return render(request, '/error.html', {'error': '파일을 열수 없습니다.'})
    filename = filename.replace('.', '')
    filename = filename.replace('/', '')
    filename = filename.replace('\\', '')
    try:
        with open(filename + file_ext) as f:
            data = f.read()
    except:
        return render(request, '/error.html', {'error': '파일이 존재하지 않거나 열 수 없는 파일입니다.'})
    return render(request, '/success.html', {'data': data})


# [가이드 원문] 안전하지 않은 코드 — 자원 삽입: 외부 입력을 소켓 포트로 사용
def get_info(request):
    port = int(request.POST.get('port'))
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(('127.0.0.1', port))
        return render(request, '/success.html')


# [가이드 원문] 안전한 코드 — 허용 포트 목록
ALLOW_PORT = [4000, 6000, 9000]


def get_info(request):
    port = int(request.POST.get('port'))
    if port not in ALLOW_PORT:
        return render(request, '/error.html', {'error': '소켓연결 실패'})
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(('127.0.0.1', port))
        return render(request, '/success.html')
```

- **검토 메모**: 가이드 안전 예제는 기준 디렉토리 없이 **현재 작업 디렉토리** 기준으로 파일을 열고, bare `except`(ERR-03)를 쓴다. 판정은 이 스킬의 `resolve()` + 기준 디렉토리 포함 확인 방식을 기준으로 하되, 문자 제거 필터가 있으면 "부분충족"으로 본다. 참고자료로 Django File Uploads, Werkzeug `secure_filename` 문서를 제시한다.

#### 이 스킬의 점검 기준 (2021 가이드 + 실무 기준)

**탐지 패턴 (Python)**
- 싱크: `open(`, `io.open(`, `os.open(`, `pathlib.Path(...).open/read_text/read_bytes/write_*`, `os.remove(`, `os.unlink(`, `os.rename(`, `os.replace(`, `shutil.copy*(`, `shutil.move(`, `shutil.rmtree(`, `os.listdir(`, `os.makedirs(`, `os.chmod(`, `tarfile.extractall(`, `zipfile.ZipFile.extractall(`, `zipfile.ZipFile.extract(`, `send_file(`, `send_from_directory(` (안전 처리 내장이지만 인자 확인), `FileResponse(`, `django.views.static.serve`
- 자원 삽입: `socket.bind((host, 입력값))`, `socket.connect((입력값, port))`, 입력값으로 DB명·큐 이름·로거 파일 경로를 정하는 코드
- `os.path.join(BASE, 입력값)` — **입력값이 절대경로면 BASE가 무시된다**는 점이 Python 특유의 함정
- 압축 해제(Zip Slip): 멤버 이름 검증 없이 `extractall`

**보충 예제 — 취약 코드**
```python
BASE_DIR = "/srv/app/datas"


@app.route("/download")
def download():
    file_name = request.args.get("P", "")
    # P=../../../etc/passwd 또는 P=/etc/passwd (os.path.join은 절대경로면 앞부분을 버림)
    path = os.path.join(BASE_DIR, file_name)
    return send_file(path, as_attachment=True)


@app.route("/delete", methods=["POST"])
def delete():
    os.remove(request.form["path"])  # 원문 C# File.Delete 예제 대응
    return "ok"
```

**보충 예제 — 안전 코드 (권장 기준)**
```python
from pathlib import Path

BASE_DIR = Path("/srv/app/datas").resolve()


def safe_path(user_name: str) -> Path:
    if not user_name:
        abort(400)
    candidate = (BASE_DIR / user_name).resolve()
    # 심볼릭 링크·..·절대경로를 모두 해석한 뒤 기준 디렉토리 아래인지 확인
    if not candidate.is_relative_to(BASE_DIR):  # Python 3.9+
        abort(400)
    return candidate


@app.route("/download")
def download():
    path = safe_path(request.args.get("P", ""))
    return send_file(path, as_attachment=True)


# Flask 내장: 디렉토리 밖 접근을 막아 준다 (werkzeug.security.safe_join 사용)
@app.route("/files/<path:name>")
def files(name):
    return send_from_directory(BASE_DIR, name)


# 가장 안전한 방식: 파일 ID → 경로 매핑 (원문 '사전에 정의된 리스트에서 선택')
@app.route("/doc/<int:doc_id>")
def doc(doc_id):
    record = Document.query.filter_by(id=doc_id, owner_id=current_user.id).first_or_404()
    return send_file(BASE_DIR / record.stored_name)


# Zip Slip 방지
def safe_extract(zf: zipfile.ZipFile, dest: Path) -> None:
    dest = dest.resolve()
    for member in zf.namelist():
        target = (dest / member).resolve()
        if not target.is_relative_to(dest):
            raise ValueError(f"잘못된 압축 경로: {member}")
    zf.extractall(dest)
# tarfile은 Python 3.12+ 에서 extractall(filter="data") 사용
```

**판정 기준 / 오탐 주의**
- 원문처럼 `..`, `/`, `\`를 **문자열 치환으로 제거**하는 방식은 `....//` 같은 우회가 가능하다. `resolve()` 후 기준 경로 포함 여부 확인을 기준으로 판정한다.
- `werkzeug.utils.secure_filename()`은 파일명 정규화이고, 결과가 빈 문자열일 수 있으니 확인한다.
- `send_from_directory`, Django `FileSystemStorage`는 기본적으로 경로 이탈을 막는다. 대신 접근 권한(인가) 누락이 있는지 SEC-02로 넘겨 본다.

---

### INP-04. 크로스사이트 스크립트 (XSS)

| 항목 | 내용 |
|---|---|
| 심각도 | 높음 |
| CWE | CWE-79 |
| 연관 설계항목 | SR1-5 |

#### KISA 소프트웨어 개발보안 가이드(2021) 원문

**개요 (2021 원문)**: 웹 페이지에 악의적인 스크립트를 넣어 사용자 측에서 실행되게 한다. 검증되지 않은 외부 입력이 동적 웹페이지 생성에 쓰이면, 그 페이지를 여는 접속자 권한으로 스크립트가 실행되어 정보유출 등이 생긴다.
- **Reflected XSS**: 검색 결과·에러 메시지 등으로 URL 파라미터의 악성 스크립트가 응답에 반사된다.
- **Stored XSS**: 게시판·코멘트·프로필 등으로 DB에 저장된 스크립트가 조회 시 실행된다.
- **DOM 기반 XSS**: URL 파라미터의 스크립트가 서버를 거치지 않고 DOM 생성 과정에서 실행된다.

**보안대책 (2021 원문)**: 입력값이나 출력값에 스크립트가 삽입되지 못하도록 `& < > " ' / ( )`를 `&amp; &lt; &gt; &quot; &#x27; &#x2F; &#x28; &#x29;`로 치환하거나, JSTL 또는 잘 알려진 XSS 방지 라이브러리를 쓴다. HTML 태그를 허용하는 게시판은 **허용 태그 화이트리스트**만 지원한다. 동작 상황별로 같은 조치가 맞지 않을 수 있으므로 검증된 외부 라이브러리를 상황에 맞게 쓰도록 권장한다.

**2021 원문 예제 요지 (Java·C·C#)**: JSP `<%=keyword%>`, `${m.content}`, `document.write(... <%=keyword%>)` → 문자 치환 / JSTL `<c:out>` / `Encoder.encodeForJS(Encoder.encodeForHTML(...))`. C# AntiXss `Sanitizer.GetSafeHtmlFragment`. C CGI `<`, `>` 검사.

#### Python 시큐어코딩 가이드(2023) 원문 — 2장 1절 4항 (p.22~28)

- **Python 관련 설명**: XSS 유형은 Reflective(Non-persistent), Persistent(Stored), DOM(Client-Side) 3가지다. Django 템플릿과 Flask의 Jinja2 템플릿은 위험한 HTML 문자를 HTML 엔티티로 치환하므로 위협이 줄어들지만, 보호가 완전하지 않거나 **개발자 실수로 무효화**될 수 있다.
- **안전한 코딩기법**: `& < > " ' / ( )`를 `&amp; &lt; &gt; &quot; &#x27; &#x2F; &#x28; &#x29;`로 치환하거나 `html` 라이브러리의 `escape()`를 쓴다(`quote=True`면 `"`와 `'`도 변환). HTML 태그를 허용하는 게시판은 허용 태그 화이트리스트를 쓴다.
- **주의 사항(가이드 명시)**: `django.utils.safestring.mark_safe`는 Django의 escape 정책을 따르지 않는다. `{% autoescape off %}`와 `|safe` 필터는 XSS에 노출된다. **autoescape off 설정은 그 템플릿을 include/extends하는 템플릿까지 영향이 확장**되므로 공통 템플릿에 쓰면 위험하다.
- **원문 예제**

```python
# [가이드 원문] 안전하지 않은 코드 — Django mark_safe 오용
from django.utils.safestring import mark_safe


def profile_link(request):
    profile_url = request.POST.get('profile_url')
    profile_name = request.POST.get('profile_name')
    object_link = '<a href="{}">{}</a>'.format(profile_url, profile_name)
    object_link = mark_safe(object_link)   # escape 정책 무시
    return render(request, 'my_profile.html', {'object_link': object_link})


# [가이드 원문] 안전한 코드 — 신뢰할 수 없는 데이터에 mark_safe를 쓰지 않음
def profile_link(request):
    profile_url = request.POST.get('profile_url')
    profile_name = request.POST.get('profile_name')
    object_link = '<a href="{}">{}</a>'.format(profile_url, profile_name)
    return render(request, 'my_profile.html', {'object_link': object_link})


# [가이드 원문] Flask — 안전하지 않은 코드 / 안전한 코드(html.escape)
@app.route('/search', methods=['POST'])
def search():
    search_keyword = request.form.get('search_keyword')
    return render_template('search.html', search_keyword=search_keyword)


@app.route('/search', methods=['POST'])
def search():
    search_keyword = request.form.get('search_keyword')
    escape_keyword = html.escape(search_keyword)
    return render_template('search.html', search_keyword=escape_keyword)
```

```html
<!-- [가이드 원문] 안전하지 않은 Django 템플릿 -->
{% autoescape off %} {{ content }} {% endautoescape %}
{{ content | safe }}

<!-- [가이드 원문] 안전한 Django 템플릿 -->
{% autoescape on %} {{ content }} {% endautoescape %}
{{ content }}
```

- **검토 메모**
  - Flask `render_template`(.html)은 기본 자동 이스케이프가 켜져 있어, 가이드의 Flask "안전하지 않은 코드"는 템플릿에서 `|safe`를 쓰지 않는 한 실제로는 이스케이프된다. 반대로 자동 이스케이프가 켜진 상태에서 `html.escape()`를 또 하면 **이중 이스케이프**(`&amp;lt;`)가 된다. 판정은 템플릿 설정과 `|safe` 사용 여부를 기준으로 한다.
  - Django 안전 예제는 `href`에 `javascript:` 스킴이 들어갈 수 있다. URL 속성에는 스킴 허용목록(`http`, `https`) 검사를 함께 권고한다.

#### 이 스킬의 점검 기준 (2021 가이드 + 실무 기준)

**탐지 패턴 (Python)**
- 자동 이스케이프 우회: Jinja2 `|safe`, `{% autoescape false %}`, `Markup(입력값)`, `markupsafe.Markup(f"...")`, Django `|safe`, `{% autoescape off %}`, `mark_safe(입력값)`, `format_html`에 미리 조합한 문자열 전달, `SafeString`
- 이스케이프 꺼진 환경: `jinja2.Environment(...)`에 `autoescape` 미지정(기본 False) 또는 `False`, `select_autoescape`에 확장자 누락
- 직접 HTML 조합: `return "<p>" + 입력값 + "</p>"`, `HttpResponse(f"...{입력값}...")`, `make_response(f"...")`, `HTMLResponse(f"...")`
- `render_template_string(f"...{입력값}...")` (SSTI와 XSS 동시)
- 템플릿 안 스크립트 문맥: `<script>var x = "{{ value }}";</script>` → HTML 이스케이프만으로는 부족, `|tojson` 사용 여부 확인
- 속성 문맥: `href="{{ url }}"` 에 `javascript:` 스킴 허용 여부
- JSON API의 `Content-Type`이 `text/html`로 내려가는지
- 프론트엔드: `innerHTML`, `outerHTML`, `document.write`, `insertAdjacentHTML`, `v-html`, `dangerouslySetInnerHTML`, jQuery `.html(`

**보충 예제 — 취약 코드**
```python
@app.route("/search")
def search():
    keyword = request.args.get("keyword", "")
    # Reflected XSS
    return f"<p>검색어 : {keyword}</p>"


# templates/result.html  (Stored XSS)
#   검색결과 : {{ post.content | safe }}
#   <script>document.write("keyword:" + "{{ keyword }}");</script>   ← DOM/스크립트 문맥


env = jinja2.Environment(loader=jinja2.FileSystemLoader("templates"))  # autoescape 기본 False
```

**보충 예제 — 안전 코드 (권장 기준)**
```python
from markupsafe import escape
import nh3  # 또는 bleach (유지보수 중단 예정이므로 nh3 권장)


@app.route("/search")
def search():
    keyword = request.args.get("keyword", "")
    # 방법1: 문자 치환 (원문 방법1 대응). escape는 & < > " ' 를 치환
    return f"<p>검색어 : {escape(keyword)}</p>"


# 방법2: 템플릿 자동 이스케이프 (원문 JSTL c:out 대응) — Flask는 .html 템플릿에서 기본 활성
#   검색결과 : {{ post.content }}
# 스크립트 문맥은 tojson 필터 사용 (원문 Encoder.encodeForJS 대응)
#   <script>const keyword = {{ keyword | tojson }};</script>

env = jinja2.Environment(
    loader=jinja2.FileSystemLoader("templates"),
    autoescape=jinja2.select_autoescape(["html", "htm", "xml"]),
)

# 방법3: HTML 허용 게시판은 허용목록 sanitizer (원문 '허용 태그 화이트리스트')
ALLOWED_TAGS = {"b", "i", "u", "p", "br", "ul", "ol", "li", "a"}
clean_html = nh3.clean(user_html, tags=ALLOWED_TAGS,
                       attributes={"a": {"href"}}, url_schemes={"http", "https"})
```

**판정 기준 / 오탐 주의**
- Flask `render_template`(.html), Django 템플릿은 기본 자동 이스케이프다. 이 경우 **우회 구문(`|safe` 등)이 있는 곳만** 지적한다.
- `|safe` 대상이 서버에서 sanitizer를 거친 값이면 sanitizer 설정(허용 태그·속성·스킴)을 검토한다.
- API가 JSON만 반환하고 `Content-Type: application/json`이면 서버 측 XSS는 낮다. 소비하는 프론트엔드 코드를 함께 확인한다.
- 방어 심층화: `Content-Security-Policy`, 세션 쿠키 `HttpOnly` 설정 여부도 보고에 덧붙인다.

---

### INP-05. 운영체제 명령어 삽입 (OS Command Injection)

| 항목 | 내용 |
|---|---|
| 심각도 | 높음 |
| CWE | CWE-78 |
| 연관 설계항목 | SR1-4 |

#### KISA 소프트웨어 개발보안 가이드(2021) 원문

**개요 (2021 원문)**: 검증되지 않은 사용자 입력이 운영체제 명령어의 일부나 전부로 실행되면, 의도하지 않은 시스템 명령이 실행되어 권한이 부적절하게 바뀌거나 시스템 동작에 악영향을 준다.

**보안대책 (2021 원문)**: 웹 인터페이스로 서버 내부에 시스템 명령어를 전달하지 않도록 구성하고, 외부 값을 검증 없이 내부 명령어로 쓰지 않는다. 외부 입력에 따라 명령을 만들거나 골라야 하면 **필요한 값을 미리 지정해 두고 입력에 따라 선택**한다. 멀티라인 특수문자(`| ; & :`)와 리다이렉트 문자(`> >>`)를 제거한다.

**2021 원문 예제 요지 (Java·C·C#)**: Java `Runtime.exec(args[0])` → 허용 명령 목록(`notepad`, `calc`) 확인. `exec("cmd.exe /c backuplog.bat" + date)` → `| ; & : >` 제거. C# `Process.Start(사용자입력)` → 정규식 검증. C `system("cat " + argv[1])` → 특수문자 검사.

#### Python 시큐어코딩 가이드(2023) 원문 — 2장 1절 5항 (p.29~32)

- **Python 관련 설명**: `eval()`과 `exec()`를 함께 쓰면 여러 변수에 동적으로 값을 할당할 수 있어 명령어 삽입 공격에 취약하다.
- **안전한 코딩기법**: 외부 입력에 시스템 명령이 포함되면 `|`, `;`, `&`, `:`, `>`, `<`, `` ` ``, `\`, `!` 같은 멀티라인·리다이렉트 문자를 필터링하고, 실행할 파일명과 옵션을 제한해 **인자로만** 쓰이게 한다. 명령을 생성·선택해야 하면 필요한 값을 미리 지정해 둔다. `shlex` 모듈로 구문 분석·이스케이프할 수 있다. `subprocess`의 `shell=True`는 중간 쉘이 파일명·와일드카드(`*`)·환경변수 확장을 검증 없이 실행하므로 **shell 옵션을 제거**한다(기본값 False).
- **원문 예제**

```python
# [가이드 원문] 안전하지 않은 코드 — os.system에 입력 그대로
def execute_command(request):
    app_name_string = request.POST.get('app_name', '')
    os.system(app_name_string)
    return render(request, '/success.html')


# [가이드 원문] 안전한 코드 — 허용 프로그램 목록
ALLOW_PROGRAM = ['notepad', 'calc']


def execute_command(request):
    app_name_string = request.POST.get('app_name', '')
    if app_name_string not in ALLOW_PROGRAM:
        return render(request, '/error.html', {'error': '허용되지 않은 프로그램입니다.'})
    os.system(app_name_string)
    return render(request, '/success.html')


# [가이드 원문] 안전하지 않은 코드 — subprocess + shell=True
def execute_command(request):
    date = request.POST.get('date', '')
    cmd_str = "cmd /c backuplog.bat " + date
    subprocess.run(cmd_str, shell=True)
    return render(request, '/success.html')


# [가이드 원문] 안전한 코드 — 특수문자 제거 + shell 옵션 제거 + 리스트 인자
def execute_command(request):
    date = request.POST.get('date', '')
    for word in ['|', ';', '&', ':', '>', '<', '`', '\\', '!']:
        date = date.replace(word, "")
        # date = re.sub('[|;&:><`\\\\!]', '', date) 도 가능
    subprocess.run(["cmd", "/c", "backuplog.bat", date])
    return render(request, '/success.html')
```

- **검토 메모**: 가이드는 2021 가이드보다 필터 문자(`<`, `` ` ``, `\`, `!`)가 늘었고 `shell=False` 리스트 인자를 명시한다. 다만 Windows `cmd /c`는 리스트 인자여도 `cmd.exe`가 다시 해석하므로 `%`, `^`, `"` 등이 남는다. 이 스킬 기준대로 **형식 허용목록(`re.fullmatch`) + 리스트 인자**를 우선한다.

#### 이 스킬의 점검 기준 (2021 가이드 + 실무 기준)

**탐지 패턴 (Python)**
- 항상 위험: `os.system(`, `os.popen(`, `subprocess.getoutput(`, `subprocess.getstatusoutput(`, `commands.getoutput(`, `pty.spawn(`
- 조건부 위험: `subprocess.run/call/check_call/check_output/Popen(...)`에서
  - `shell=True` 이면서 명령 문자열에 외부 입력 포함
  - 리스트 인자여도 **실행 파일 자체(첫 요소)**가 외부 입력인 경우
  - 인자에 외부 입력이 `-`로 시작할 수 있는데 `--` 구분이 없는 경우 (옵션 삽입. 예: `git`, `tar`, `curl`)
- `os.exec*`, `os.spawn*` 에 외부 입력
- `asyncio.create_subprocess_shell(`
- `paramiko` `exec_command(입력값)`, `fabric` `run(입력값)` — 원격 명령 실행

**보충 예제 — 취약 코드**
```python
@app.route("/backup")
def backup():
    date = request.args.get("date", "")
    # date="20240101; rm -rf /" → 두 번째 명령 실행
    os.system("backuplog.sh " + date)
    return "ok"


@app.route("/run")
def run():
    cmd = request.args.get("cmd", "")
    subprocess.run(cmd, shell=True)  # 원문 Runtime.exec(args[0]) 대응
    return "ok"
```

**보충 예제 — 안전 코드 (권장 기준)**
```python
import re
import shlex
import subprocess

# 1) 허용 명령 목록에서 선택 (원문 allowedCommands 대응)
ALLOWED_COMMANDS = {
    "disk": ["df", "-h"],
    "uptime": ["uptime"],
}


@app.route("/run")
def run():
    argv = ALLOWED_COMMANDS.get(request.args.get("cmd", ""))
    if argv is None:
        abort(400, "허용되지 않은 명령어입니다.")
    out = subprocess.run(argv, capture_output=True, text=True, timeout=10, check=False)
    return out.stdout


# 2) 인자는 형식 검증 후 리스트로 전달, shell=False(기본값)
DATE_RE = re.compile(r"^\d{8}$")


@app.route("/backup")
def backup():
    date = request.args.get("date", "")
    if not DATE_RE.fullmatch(date):
        abort(400)
    subprocess.run(["/opt/app/backuplog.sh", "--", date], check=True, timeout=60)
    return "ok"


# 3) 불가피하게 셸 문자열이 필요하면 shlex.quote (최후의 수단)
subprocess.run(f"grep -- {shlex.quote(pattern)} /var/log/app.log", shell=True, check=False)
```

**판정 기준 / 오탐 주의**
- 원문의 "특수문자 제거" 방식은 Python에서도 우회 여지가 있다(`$()`, 백틱, 개행 등). **`shell=False` + 리스트 인자 + 허용목록/정규식 `fullmatch`** 를 기준으로 판정한다.
- 명령어 실행 자체가 라이브러리로 대체 가능한지(예: `ping` 대신 소켓, `cp` 대신 `shutil`) 함께 제안한다.

---

### INP-06. 위험한 형식 파일 업로드 (Unrestricted File Upload)

| 항목 | 내용 |
|---|---|
| 심각도 | 높음 |
| CWE | CWE-434 |
| 연관 설계항목 | SR1-10 |

#### KISA 소프트웨어 개발보안 가이드(2021) 원문

**개요 (2021 원문)**: 서버에서 실행될 수 있는 스크립트 파일(asp, jsp, php 등)을 업로드할 수 있고, 공격자가 웹으로 그 파일을 직접 실행할 수 있으면 내부 명령 실행이나 외부 연결로 시스템을 제어할 수 있다.

**보안대책 (2021 원문)**: **화이트리스트** 방식으로 허용된 확장자만 업로드를 허용한다. 저장 시 파일명과 확장자를 외부에서 추측할 수 없는 문자열로 바꾸고, 저장 경로는 **web document root 밖**에 두어 웹 직접 접근을 막는다. 파일 실행 여부를 설정할 수 있으면 실행 속성을 제거한다.

**2021 원문 예제 요지 (Java·C·C#)**: Java `MultipartRequest`로 받은 파일명을 검증 없이 저장 → 마지막 `.` 기준 확장자를 소문자로 추출해 `gif/jpg/png`만 허용. C# `SaveAs(파일명)` → `ContentType == image/jpeg` 및 크기 `< 100KB` 검사.

#### Python 시큐어코딩 가이드(2023) 원문 — 2장 1절 6항 (p.33~35)

- **Python 관련 설명**: 서버에서 실행 가능한 스크립트(asp, jsp, php, **sh** 등)를 업로드해 웹으로 실행할 수 있으면 위험하다. 업로드된 파일이 `eval()`/`exec()`와 결합되면 웹쉘 공격에 취약하다.
- **안전한 코딩기법**: 화이트리스트로 파일 유형을 제한하되 **확장자와 Content-Type을 함께** 확인한다. **파일 크기와 개수**를 제한해 자원 고갈(DoS)을 막는다. 업로드 파일은 **웹 루트 밖**에 저장하고, 가능하면 **추측할 수 없는 무작위 이름**으로 바꿔 저장한다. 저장 파일은 **최소 권한**만 주고 실행 권한을 삭제한다.
- **원문 예제**

```python
# [가이드 원문] 안전하지 않은 코드 — 검증 없이 저장
def file_upload(request):
    if request.FILES['upload_file']:
        upload_file = request.FILES['upload_file']
        fs = FileSystemStorage(location='media/screenshot', base_url='media/screenshot')
        filename = fs.save(upload_file.name, upload_file)
        return render(request, '/success.html', {'filename': filename})
    return render(request, '/error.html', {'error': '파일 업로드 실패'})


# [가이드 원문] 안전한 코드 — 개수·크기·타입·확장자 검사
FILE_COUNT_LIMIT = 5
FILE_SIZE_LIMIT = 5242880          # 5MB
WHITE_LIST_EXT = ['.jpg', '.jpeg']


def file_upload(request):
    if len(request.FILES) == 0 or len(request.FILES) > FILE_COUNT_LIMIT:
        return render(request, '/error.html', {'error': '파일 개수 초과'})
    for filename, upload_file in request.FILES.items():
        if upload_file.content_type != 'image/jpeg':
            return render(request, '/error.html', {'error': '파일 타입 오류'})
        if upload_file.size > FILE_SIZE_LIMIT:
            return render(request, '/error.html', {'error': '파일사이즈 오류'})
        file_name, file_ext = os.path.splitext(upload_file.name)
        if file_ext.lower() not in WHITE_LIST_EXT:
            return render(request, '/error.html', {'error': '파일 타입 오류'})
    filename_list = []
    fs = FileSystemStorage(location='media/screenshot', base_url='media/screenshot')
    for upload_file in request.FILES.values():
        filename = fs.save(upload_file.name, upload_file)
        filename_list.append(filename)
    return render(request, '/success.html', {'filename_list': filename_list})
```

- **검토 메모**
  - 가이드 본문은 "파일 자체의 시그니처 확인"을 말하지만, 예제의 `upload_file.content_type`은 **클라이언트가 보낸 값**이라 위조 가능하다. 실제 내용 검사(`python-magic`, 이미지면 Pillow로 열어 검증)가 있어야 "충족"으로 본다.
  - 예제는 **원본 파일명으로 `media/` 아래 저장**하는데, 이는 가이드 본문(무작위 이름, 웹 루트 밖)과 어긋난다. Django `MEDIA_URL`로 직접 서빙되면 지적한다.
  - 원문 예제에는 `filename_list` 초기화가 빠져 있어 위 코드에서 보충했다.

#### 이 스킬의 점검 기준 (2021 가이드 + 실무 기준)

**탐지 패턴 (Python)**
- 업로드 처리: `request.files[...]`, `FileStorage.save(`, `request.FILES`, `UploadedFile`, `default_storage.save(`, FastAPI `UploadFile`, `shutil.copyfileobj(upload.file, ...)`
- 위험 신호
  - 원본 파일명(`file.filename`, `uploaded.name`)을 그대로 저장 경로에 사용
  - 확장자 검사가 없음, 또는 **블랙리스트**(`.php`, `.jsp`만 차단) 방식
  - `filename.split(".")[1]` 처럼 첫 번째 점 기준 추출 (`a.jpg.php` 우회)
  - 대소문자 미정규화 (`.PHP`)
  - `content_type`(클라이언트가 보낸 값)만 신뢰
  - 저장 경로가 `static/`, `public/`, `MEDIA_ROOT`인데 웹서버가 직접 서빙
  - 크기 제한(`MAX_CONTENT_LENGTH`, `DATA_UPLOAD_MAX_MEMORY_SIZE`) 없음
  - 이미지 처리 시 `PIL.Image.open` 결과 검증 없음 (decompression bomb: `Image.MAX_IMAGE_PIXELS`)

**보충 예제 — 취약 코드**
```python
UPLOAD_DIR = "static/uploads"


@app.route("/upload", methods=["POST"])
def upload():
    f = request.files["filename"]
    # 원본 파일명 그대로, 확장자 검사 없음, 웹 루트(static) 아래 저장
    f.save(os.path.join(UPLOAD_DIR, f.filename))
    db.execute("INSERT INTO board(filename) VALUES (?)", (f.filename,))
    return "ok"
```

**보충 예제 — 안전 코드 (권장 기준)**
```python
import secrets
from pathlib import Path

import magic  # python-magic: 실제 파일 내용 기반 MIME 판별

app.config["MAX_CONTENT_LENGTH"] = 10 * 1024 * 1024  # 크기 제한 (초과 시 413)
UPLOAD_DIR = Path("/srv/app/uploads")  # 웹 document root 밖
ALLOWED = {"gif": "image/gif", "jpg": "image/jpeg", "jpeg": "image/jpeg", "png": "image/png"}


@app.route("/upload", methods=["POST"])
@login_required
def upload():
    f = request.files.get("filename")
    if f is None or not f.filename:
        abort(400)
    # 1. 마지막 '.' 기준, 소문자로 확장자 추출 (원문 대응)
    ext = f.filename.rsplit(".", 1)[-1].lower() if "." in f.filename else ""
    if ext not in ALLOWED:
        abort(400, "업로드 불가능한 파일입니다.")
    # 2. 확장자와 실제 내용(MIME)을 함께 검사
    head = f.stream.read(2048)
    f.stream.seek(0)
    if magic.from_buffer(head, mime=True) != ALLOWED[ext]:
        abort(400)
    # 3. 추측 불가능한 저장명, 원본명은 DB에만 보관
    stored_name = f"{secrets.token_hex(16)}.{ext}"
    dest = UPLOAD_DIR / stored_name
    f.save(dest)
    os.chmod(dest, 0o640)  # 실행권한 없음
    db.execute(
        "INSERT INTO board(orig_filename, stored_filename, owner_id) VALUES (?, ?, ?)",
        (f.filename, stored_name, current_user.id),
    )
    return "ok"
```

**판정 기준 / 오탐 주의**
- 확장자 허용목록 + 저장명 랜덤화 + 웹 루트 밖 저장 + 크기 제한이 모두 있어야 "충족"으로 본다. 일부만 있으면 "부분충족"으로 보고 빠진 항목을 적는다.
- 업로드 파일 개수 제한(SR1-10 ①)도 확인한다 (예: `request.files.getlist` 길이).
- 다운로드 측은 INP-03, SEC-02와 연결해서 본다.

---

### INP-07. 신뢰되지 않는 URL 주소로 자동접속 연결 (Open Redirect)

| 항목 | 내용 |
|---|---|
| 심각도 | 중간 |
| CWE | CWE-601 |
| 연관 설계항목 | SR1-7 |

#### KISA 소프트웨어 개발보안 가이드(2021) 원문

**개요 (2021 원문)**: 사용자 입력을 외부 사이트 주소로 써서 자동으로 연결하는 서버 프로그램은 피싱 공격에 노출된다. 클라이언트가 보낸 URL이라 안전하다고 생각하기 쉽지만, 공격자가 요청을 변조해 위험한 URL로 접속하게 할 수 있다. (예: `http://bank.example.com/redirect?url=http://attacker.example.net`)

**보안대책 (2021 원문)**: 자동 연결할 외부 사이트의 URL과 도메인은 **화이트리스트**로 관리하고, 사용자 입력을 연결 주소로 쓸 때는 입력값이 화이트리스트에 있는지 확인한다.

**2021 원문 예제 요지 (Java·C·C#)**: Java `response.sendRedirect(request.getParameter("redirect"))` → `allowedUrl[Integer.parseInt(rd)]` 인덱스 선택. C# `Response.Redirect(Request["dest"])` → `IsLocalUrl` 확인(호스트 동일 여부, 상대경로 여부).

#### Python 시큐어코딩 가이드(2023) 원문 — 2장 1절 7항 (p.36~38)

- **Python 관련 설명**: 프레임워크의 redirect 함수도 **해당 버전의 알려진 취약점**을 확인해야 한다. 예: Flask-Security-Too의 `get_post_logout_redirect`, `get_post_login_redirect`는 **4.1.0 이전 버전**에서 URL 검증을 우회해 임의 URL로 리다이렉트할 수 있다.
- **안전한 코딩기법**: 리다이렉트를 허용하는 모든 URL을 **서버 측 화이트리스트**로 관리하고 입력값이 목록에 있는지 검증한다. 화이트리스트가 불가능하면 프로토콜·host가 없는 **상대 URL**만 사용·검증하거나, 절대 URL이면 서비스 중인 URL(예: `https://myhompage.com/`)로 시작하는지 확인한다.
- **원문 예제**

```python
# [가이드 원문] 안전하지 않은 코드
def redirect_url(request):
    url_string = request.POST.get('url', '')
    return redirect(url_string)


# [가이드 원문] 안전한 코드 — 허용 URL 목록
ALLOW_URL_LIST = [
    '127.0.0.1',
    '192.168.0.1',
    '192.168.0.100',
    'https://login.myservice.com',
    '/notice',
]


def redirect_url(request):
    url_string = request.POST.get('url', '')
    if url_string not in ALLOW_URL_LIST:
        return render(request, '/error.html', {'error': '허용되지 않는 주소입니다.'})
    return redirect(url_string)
```

- **검토 메모**: "서비스 URL로 시작하는지 확인" 방식은 `https://myhompage.com.evil.net`이나 `https://myhompage.com@evil.net`으로 우회될 수 있다(끝의 `/`까지 포함해 비교하면 일부 완화). 이 스킬의 `urlparse` 후 hostname 정확 일치, Django `url_has_allowed_host_and_scheme()`를 기준으로 판정한다. 의존성에 `Flask-Security-Too<4.1.0`이 있으면 함께 지적한다.

#### 이 스킬의 점검 기준 (2021 가이드 + 실무 기준)

**탐지 패턴 (Python)**
- 싱크: Flask `redirect(`, Django `redirect(`, `HttpResponseRedirect(`, `HttpResponsePermanentRedirect(`, FastAPI/Starlette `RedirectResponse(`, `response.headers["Location"] = `, HTML `<meta http-equiv="refresh" content="0;url={{ next }}">`, JS `location.href = "{{ next }}"`
- 흔한 파라미터명: `next`, `url`, `redirect`, `redirect_uri`, `return`, `returnUrl`, `continue`, `dest`, `goto`
- 잘못된 검증: `url.startswith("/")` 만 확인 (`//evil.com`, `/\evil.com` 우회), `"example.com" in url` (`example.com.evil.net` 우회), `url.startswith("https://example.com")` (`https://example.com@evil.net`, `https://example.com.evil.net` 우회)

**보충 예제 — 취약 코드**
```python
@app.route("/login", methods=["POST"])
def login():
    ...
    return redirect(request.args.get("next", "/"))  # next=https://attacker.example.net
```

**보충 예제 — 안전 코드 (권장 기준)**
```python
from urllib.parse import urlparse

# 1) 인덱스 선택 방식 (원문 allowedUrl 대응)
ALLOWED_URLS = ["/main", "/login", "/list"]


@app.route("/go")
def go():
    try:
        target = ALLOWED_URLS[int(request.args.get("redirect", ""))]
    except (ValueError, IndexError):
        abort(400, "잘못된 접근입니다.")
    return redirect(target)


# 2) 내부 경로만 허용 (원문 IsLocalUrl 대응)
def is_local_url(url: str) -> bool:
    if not url or url.startswith(("//", "/\\")) or "\\" in url:
        return False
    parsed = urlparse(url)
    return parsed.scheme == "" and parsed.netloc == "" and url.startswith("/")


@app.route("/login", methods=["POST"])
def login():
    ...
    nxt = request.args.get("next", "/")
    return redirect(nxt if is_local_url(nxt) else "/")


# 3) Django 내장 함수
from django.utils.http import url_has_allowed_host_and_scheme

if not url_has_allowed_host_and_scheme(nxt, allowed_hosts={request.get_host()},
                                       require_https=request.is_secure()):
    nxt = "/"

# 4) 외부 도메인 허용이 필요하면 호스트 정확히 일치 비교
ALLOWED_HOSTS = {"partner.example.com"}
p = urlparse(url)
ok = p.scheme == "https" and p.hostname in ALLOWED_HOSTS
```

**판정 기준 / 오탐 주의**
- 리다이렉트 대상이 `url_for(...)` 결과나 상수면 안전하다.
- OAuth `redirect_uri`는 사전 등록값과 **정확히 일치**하는지 본다(부분 일치 금지).

---

### INP-08. 부적절한 XML 외부개체 참조 (XXE)

| 항목 | 내용 |
|---|---|
| 심각도 | 높음 |
| CWE | CWE-611 |
| 연관 설계항목 | SR1-2 |

#### KISA 소프트웨어 개발보안 가이드(2021) 원문

**개요 (2021 원문)**: XML 문서의 DTD는 엔티티를 정의할 수 있다. 서버가 XML 외부 엔티티를 처리하도록 설정되어 있으면, 취약한 파서가 외부 값을 참조하는 XML을 처리할 때 공격 구문이 동작해 서버 파일 접근, 자원 낭비, 인증 우회, 정보 노출이 생긴다.
- 예: `<!ENTITY xxe SYSTEM "file:///etc/passwd">` 로 서버 파일 읽기, `<!DOCTYPE foo SYSTEM "file:/dev/tty">` 로 서비스 거부.

**보안대책 (2021 원문)**: 로컬 정적 DTD를 쓰도록 설정하고, 외부에서 받은 XML 문서의 DTD를 **완전히 비활성화**한다. 비활성화할 수 없으면 외부 엔티티와 외부 문서 유형 선언을 파서별 고유 방식으로 비활성화한다.

**2021 원문 예제 요지 (Java·C·C#)**: Java `DocumentBuilderFactory`, `SAXParserFactory` 기본 설정 → `disallow-doctype-decl=true`, `external-general-entities=false`, `external-parameter-entities=false`, `load-external-dtd=false`, `setXIncludeAware(false)`, `setExpandEntityReferences(false)`. PHP `libxml_disable_entity_loader(true)`.

#### Python 시큐어코딩 가이드(2023) 원문 — 2장 1절 8항 (p.39~41)

- **Python 관련 설명**: 파이썬 기본 XML 파서는 **외부 엔티티를 지원하지 않지만 다른 유형의 XML 공격에 취약**할 수 있다. 더 많은 기능이 필요해 쓰는 **lxml은 기본적으로 외부 엔티티 구문 분석이 활성화**되어 있다.
- **안전한 코딩기법**: 로컬 정적 DTD를 쓰고 외부 XML의 DTD를 완전히 비활성화한다. 외부 라이브러리는 외부 엔티티 구문 분석 기능 제공 여부와 비활성화 방법을 확인한다. lxml은 **`resolve_entities` 옵션을 비활성화**하고, 외부 문서 조회 시 네트워크 접근을 막는 **`no_network`가 True**인지 확인한다. `xml.sax`는 **`feature_external_ges`를 False**로 설정한다.
- **원문 예제** (공격 XML: `<!ENTITY xxe1 SYSTEM "file:///etc/passwd">`, `<!ENTITY xxe2 SYSTEM "http://attacker.com/text.txt">`)

```python
from xml.dom.pulldom import START_ELEMENT, parseString
from xml.sax import make_parser
from xml.sax.handler import feature_external_ges


# [가이드 원문] 안전하지 않은 코드 — 외부 일반 엔티티 허용
def get_xml(request):
    if request.method == "POST":
        parser = make_parser()
        parser.setFeature(feature_external_ges, True)
        doc = parseString(request.body.decode('utf-8'), parser=parser)
        for event, node in doc:
            if event == START_ELEMENT and node.tagName == "foo":
                doc.expandNode(node)
                text = node.toxml()
                comments.objects.filter(id=1).update(comment=text)
        return render(request, '/xml_view.html')


# [가이드 원문] 안전한 코드 — feature_external_ges = False
def get_xml(request):
    if request.method == "POST":
        parser = make_parser()
        parser.setFeature(feature_external_ges, False)
        doc = parseString(request.body.decode('utf-8'), parser=parser)
        for event, node in doc:
            if event == START_ELEMENT and node.tagName == "foo":
                doc.expandNode(node)
                text = node.toxml()
                comments.objects.filter(id=1).update(comment=text)
        return render(request, '/xml_view.html')
```

- **검토 메모**: 탐지 패턴에 `setFeature(feature_external_ges, True)`를 추가로 본다. 엔티티 확장 폭탄(Billion Laughs) 같은 "다른 유형의 공격"까지 막으려면 `defusedxml`을 권고한다(가이드 참고자료의 Python 공식 XML vulnerabilities 문서와 같은 입장).

#### 이 스킬의 점검 기준 (2021 가이드 + 실무 기준)

**탐지 패턴 (Python)**
- 싱크: `lxml.etree.parse(`, `lxml.etree.fromstring(`, `lxml.etree.XML(`, `lxml.etree.XMLParser(`, `xml.dom.minidom.parse/parseString(`, `xml.dom.pulldom.parse(`, `xml.sax.parse/parseString(`, `xml.sax.make_parser(`, `xml.etree.ElementTree.parse/fromstring/XML/iterparse(`, `xmltodict.parse(`, `xmlrpc.server`, SOAP 라이브러리(`zeep`, `suds`)
- 위험 신호
  - `lxml.etree.XMLParser(resolve_entities=True)`(구버전 기본값), `load_dtd=True`, `no_network=False`, `huge_tree=True`
  - `xml.sax` 파서에 `feature_external_ges=True` 설정
  - `defusedxml` 미사용 상태에서 외부(요청 본문, 업로드 파일, 외부 API) XML 파싱
- 참고: 표준 `xml.etree`/`minidom`/`sax`는 최신 Python에서 외부 엔티티를 기본으로 가져오지 않지만, 엔티티 확장 폭탄(Billion Laughs) 같은 DoS에는 여전히 노출될 수 있다. 공식 문서도 신뢰할 수 없는 XML에는 `defusedxml`을 권한다.

**보충 예제 — 취약 코드**
```python
from lxml import etree


@app.route("/import", methods=["POST"])
def import_xml():
    parser = etree.XMLParser(resolve_entities=True, load_dtd=True, no_network=False)
    root = etree.fromstring(request.data, parser)  # file:///etc/passwd 참조 가능
    return root.findtext("name")
```

**보충 예제 — 안전 코드 (권장 기준)**
```python
import defusedxml.ElementTree as SafeET
from lxml import etree

# 1) defusedxml 사용 (DTD·외부 엔티티·엔티티 확장 차단)
@app.route("/import", methods=["POST"])
def import_xml():
    root = SafeET.fromstring(request.data)  # 위험 구문이면 예외 발생
    return root.findtext("name")


# 2) lxml을 써야 하면 파서 옵션을 명시적으로 잠금 (원문 setFeature 대응)
SAFE_PARSER = etree.XMLParser(
    resolve_entities=False,  # 엔티티 확장 금지
    load_dtd=False,          # 외부 DTD 로드 금지
    no_network=True,         # 네트워크 접근 금지
    dtd_validation=False,
    huge_tree=False,
)
root = etree.fromstring(request.data, SAFE_PARSER)
```

**판정 기준 / 오탐 주의**
- 파싱 대상이 저장소 안의 고정 설정 파일이면 위험도가 낮다. 외부에서 들어오는 XML(요청, 업로드, 서드파티 응답)인지 확인한다.
- SVG·DOCX·XLSX도 XML이다. 업로드 처리에서 이 파일을 직접 파싱하는지 본다.

---

### INP-09. XML 삽입 (XQuery / XPath Injection)

| 항목 | 내용 |
|---|---|
| 심각도 | 중간 |
| CWE | CWE-643, CWE-652 |
| 연관 설계항목 | SR1-2 |

#### KISA 소프트웨어 개발보안 가이드(2021) 원문

**개요 (2021 원문)**: 검증되지 않은 외부 입력이 XQuery·XPath 쿼리 문자열에 쓰이면, 공격자가 쿼리 구조를 바꿔 허가되지 않은 데이터를 열람하거나 인증을 우회할 수 있다.
- 예: `name = something' or '1'='1` → `doc('users.xml')/userlist/user[uname='something' or '1'='1']` 로 전체 조회.
- 예: `pw = x' or 'x'='x` → `//users/user[login/text()='tester' and password/text()='x' or 'x'='x']` 로 인증 우회.

**보안대책 (2021 원문)**: XQuery·XPath 쿼리에 쓰이는 외부 입력의 특수문자와 쿼리 예약어를 필터링하고, **파라미터화된 쿼리**를 지원하는 XQuery를 쓴다. 파라미터화가 불가능하면 XPath 삽입을 일으키는 문자를 입력에서 제거한 뒤 구문을 만든다.

**2021 원문 예제 요지 (Java·C·C#)**: XQuery `bindString(new QName("xname"), name)`, 외부 `.xq` 파일에 `declare variable $loginID external`. 필터는 `[',\[]` 제거, `[()\-'\[\]:,*/]` 제거. C# `XPathExpression` + `DynamicContext.AddVariable`.

#### Python 시큐어코딩 가이드(2023) 원문 — 2장 1절 9항 (p.42~43)

- **Python 관련 설명**: 기본 모듈 `xml.etree.ElementTree`는 **제한적인 XPath만 지원하고 XPath 표현식을 인자화하는 방법을 제공하지 않는다.** 따라서 외부 입력이 들어가는 XPath는 `lxml`을 쓰고 인자화한다.
- **안전한 코딩기법**: XQuery·XPath에 쓰이는 외부 입력의 특수문자·쿼리 예약어를 필터링하고, 인자화된 쿼리를 쓴다.
- **원문 예제**

```python
from lxml import etree


# [가이드 원문] 안전하지 않은 코드 — 문자열 연결 XPath
def parse_xml(request):
    user_name = request.POST.get('user_name', '')
    parser = etree.XMLParser(resolve_entities=False)
    tree = etree.parse('user.xml', parser)
    root = tree.getroot()
    query = "/collection/users/user[@name='" + user_name + "']/home/text()"
    elmts = root.xpath(query)
    return render(request, 'parse_xml.html', {'xml_element': elmts})


# [가이드 원문] 안전한 코드 — XPath 변수($paramname) 바인딩
def parse_xml(request):
    user_name = request.POST.get('user_name', '')
    parser = etree.XMLParser(resolve_entities=False)
    tree = etree.parse('user.xml', parser)
    root = tree.getroot()
    query = '/collection/users/user[@name = $paramname]/home/text()'
    elmts = root.xpath(query, paramname=user_name)
    return render(request, 'parse_xml.html', {'xml_element': elmts})
```

- **검토 메모**: 가이드에 "파이썬 3.3 이후 보안상의 이유로 금지된 `xml.etree.ElementTree` 모듈"이라는 문장이 있으나, `ElementTree`는 금지되지 않았다(3.3에서 폐기된 것은 `xml.etree.cElementTree`). 판정에는 영향을 주지 않으며, 이 항목의 핵심은 "XPath는 lxml 변수 바인딩"이다. 가이드 예제가 파서에 `resolve_entities=False`를 함께 쓰는 점(INP-08)도 좋은 기준이다.

#### 이 스킬의 점검 기준 (2021 가이드 + 실무 기준)

**탐지 패턴 (Python)**
- 싱크: `lxml.etree.XPath(`, `element.xpath(`, `tree.xpath(`, `ElementTree.find/findall/findtext/iterfind(` (경로식), `elementpath.select(`, `saxonche` XQuery 실행
- 위험 신호: XPath 문자열을 f-string·`+`·`%`·`.format()`으로 만들고 외부 입력을 넣음

**보충 예제 — 취약 코드**
```python
from lxml import etree

doc = etree.parse("users.xml")


def login(nm: str, pw: str) -> bool:
    expr = f"//users/user[login/text()='{nm}' and password/text()='{pw}']/home_dir/text()"
    return bool(doc.xpath(expr))  # pw = "x' or 'x'='x" 로 인증 우회
```

**보충 예제 — 안전 코드 (권장 기준)**
```python
import re

from lxml import etree

doc = etree.parse("users.xml")

# 1) lxml XPath 변수 바인딩 (원문 bindString / DynamicContext.AddVariable 대응)
FIND_USER = etree.XPath("//users/user[login/text()=$nm and password/text()=$pw]/home_dir/text()")


def login(nm: str, pw: str) -> bool:
    return bool(FIND_USER(doc, nm=nm, pw=pw))


# 2) 바인딩을 쓸 수 없는 라이브러리라면 허용 문자만 통과 (원문 필터 대응, 차선책)
SAFE_TOKEN = re.compile(r"^[\w\s.@-]{1,64}$")


def food_price(name: str):
    if not SAFE_TOKEN.fullmatch(name):
        raise ValueError("Invalid input")
    return doc.findall(f".//food[name='{name}']/price")
```

**판정 기준 / 오탐 주의**
- XML 파일에 비밀번호를 평문으로 두는 구조 자체도 SEC-05로 함께 지적한다.
- XML 파서 설정(XXE)은 INP-08로 별도 확인한다.

---

### INP-10. LDAP 삽입 (LDAP Injection)

| 항목 | 내용 |
|---|---|
| 심각도 | 중간 |
| CWE | CWE-90 |
| 연관 설계항목 | SR1-3 |

#### KISA 소프트웨어 개발보안 가이드(2021) 원문

**개요 (2021 원문)**: 외부 입력으로 의도하지 않은 LDAP 명령이 실행될 수 있다. 사용자 입력을 올바르게 처리하지 못하면 공격자가 LDAP 명령문 구성을 바꿀 수 있고, 프로세스는 명령을 실행한 컴포넌트와 같은 권한으로 동작한다.
- 예: `userSN`, `userPassword`에 `*`를 넣으면 `(&(sn=S*)(userPassword=*))` 가 항상 참.

**보안대책 (2021 원문)**: DN과 필터에 쓰이는 사용자 입력에서 특수문자를 제거한다. 특수문자를 써야 하면 `= + < > # ; \` 등이 실행 명령이 아닌 **일반 문자로 인식되도록** 처리한다. (C# 예제에서는 **익명 바인딩을 쓰지 말고 인증 후 조회**할 것을 함께 제시)

**2021 원문 예제 요지 (Java·C·C#)**: Java `"(&(sn=" + userSN + ")(userPassword=" + userPassword + "))"` → `[\w\s]*`, `[\w]*` 정규식 검증. C `ldap_search_ext_s(..., getenv("Filter"), ...)` → `*`, `(`, `)` 검사.

#### Python 시큐어코딩 가이드(2023) 원문 — 2장 1절 10항 (p.44~47)

- **Python 관련 설명**: 파이썬 LDAP 라이브러리는 `python-ldap`과 `ldap3`가 있다. `ldap3`가 더 현대적이고 파이썬 2.6~3 전 버전과 호환되며, 가이드는 **파이썬 3에서는 `ldap3` 사용을 권장**한다.
- **안전한 코딩기법**
  - 올바른 인코딩 함수로 모든 변수를 이스케이프 처리
  - 화이트리스트 방식의 입력값 유효성 검사
  - 사용자 패스워드 같은 민감한 정보가 포함된 필드 인덱싱
  - **LDAP 바인딩 계정에 할당된 권한 최소화**
- **원문 예제**

```python
from ldap3 import ALL, Connection, Server
from ldap3.utils.conv import escape_filter_chars

config = {
    "bind_dn": "cn=read-only-admin,dc=example,dc=com",
    "password": "password",
}


# [가이드 원문] 안전하지 않은 코드
def ldap_query(request):
    search_keyword = request.POST.get('search_keyword', '')
    server = Server('ldap.badSoruce.com', get_info=ALL)
    conn = Connection(server, user=config['bind_dn'], password=config['password'], auto_bind=True)
    search_str = '(&(objectclass=%s))' % search_keyword
    conn.search('dc=company,dc=com', search_str,
                attributes=['sn', 'cn', 'address', 'mail', 'mobile', 'uid'])
    return render(request, '/ldap_query_response.html', {'ldap': conn.entries})


# [가이드 원문] 안전한 코드 — escape_filter_chars
def ldap_query(request):
    search_keyword = request.POST.get('search_keyword', '')
    server = Server('ldap.goodsource.com', get_info=ALL)
    conn = Connection(server, config['bind_dn'], config['password'], auto_bind=True)
    escape_keyword = escape_filter_chars(search_keyword)
    search_str = '(&(objectclass=%s))' % escape_keyword
    conn.search('dc=company,dc=com', search_str,
                attributes=['sn', 'cn', 'address', 'mail', 'mobile', 'uid'])
    return render(request, '/ldap_query_response.html', {'ldap': conn.entries})
```

- **검토 메모**: 가이드 예제는 바인드 비밀번호를 코드에 하드코딩(`"password": "password"`)하고 있다. 이 부분은 SEC-06으로 별도 지적 대상이다. 예제의 LDAP 연결도 평문 `ldap://`이므로 `ldaps://` 또는 StartTLS를 권고한다(SEC-05).

#### 이 스킬의 점검 기준 (2021 가이드 + 실무 기준)

**탐지 패턴 (Python)**
- 싱크: `ldap3.Connection.search(search_base, search_filter, ...)`, `Connection.modify(dn, ...)`, `Connection.delete(dn)`, python-ldap `search_s(`, `search_ext_s(`, `simple_bind_s(dn, ...)`, `modify_s(`
- 위험 신호: 필터·DN 문자열에 외부 입력을 이스케이프 없이 연결
- 익명 바인드: `ldap3.Connection(server)`(user 없이), `auto_bind=True`인데 자격증명 없음, `simple_bind_s("", "")`
- 빈 비밀번호 바인드 허용(`password=""`이면 일부 서버가 익명 바인드로 성공 처리) — 로그인 구현 시 특히 확인

**보충 예제 — 취약 코드**
```python
from ldap3 import Connection, Server

server = Server("ldap://ldap.example.com")


def search_record(user_sn: str, user_password: str):
    conn = Connection(server, auto_bind=True)  # 익명 바인딩
    flt = f"(&(sn={user_sn})(userPassword={user_password}))"  # '*' 입력 시 항상 참
    conn.search("dc=example,dc=com", flt, attributes=["cn", "mail"])
    return conn.entries
```

**보충 예제 — 안전 코드 (권장 기준)**
```python
from ldap3 import Connection, Server
from ldap3.utils.conv import escape_filter_chars
from ldap3.utils.dn import escape_rdn

server = Server("ldaps://ldap.example.com", use_ssl=True)


def search_record(user_sn: str):
    if not user_sn:
        raise ValueError("Invalid input")
    # 인증된 서비스 계정으로 바인딩 (익명 바인딩 금지), 자격증명은 환경변수/시크릿에서
    conn = Connection(server, user=os.environ["LDAP_BIND_DN"],
                      password=os.environ["LDAP_BIND_PW"], auto_bind=True)
    flt = f"(sn={escape_filter_chars(user_sn)})"  # * ( ) \ NUL 이스케이프
    conn.search("dc=example,dc=com", flt, attributes=["cn", "mail"])
    return conn.entries


def authenticate(uid: str, password: str) -> bool:
    if not uid or not password:  # 빈 비밀번호 바인드 = 익명 바인드 성공 방지
        return False
    user_dn = f"uid={escape_rdn(uid)},ou=people,dc=example,dc=com"
    return Connection(server, user=user_dn, password=password).bind()
```

**판정 기준 / 오탐 주의**
- 비밀번호를 LDAP 필터에 넣어 비교하는 방식(원문 예제) 자체가 좋지 않다. 바인드 인증으로 바꾸도록 함께 제안한다.

---

### INP-11. 크로스사이트 요청 위조 (CSRF)

| 항목 | 내용 |
|---|---|
| 심각도 | 중간 (관리자·결제 기능이면 높음) |
| CWE | CWE-352 |
| 연관 설계항목 | SR1-6 |

#### KISA 소프트웨어 개발보안 가이드(2021) 원문

**개요 (2021 원문)**: 사용자가 모르는 사이에 사용자의 의도와 무관하게 공격자가 의도한 행위(수정, 삭제, 등록 등)를 요청하게 하는 공격이다. 요청이 사용자가 의도해 작성·전송한 것인지 확인하지 않으면 생기고, 사용자가 관리자면 권한관리·게시물 삭제·사용자 등록 같은 관리자 기능이 실행될 수 있다. 인증 세션이 유지되어 정상·비정상 요청을 구분하지 못하는 점을 악용한다. 요청의 적법성을 입증하는 값이 **고정되어 있고 GET으로 전달**되면 공격자가 쉽게 알아낸다.

**보안대책 (2021 원문)**: 입력 폼은 GET보다 **POST**를 쓰고, 입력 폼과 처리 프로그램 사이에 **토큰**을 사용해 공격자의 직접적인 URL 사용이 동작하지 않게 한다. 중요 기능은 세션 검증과 더불어 **재인증**을 유도한다.

**2021 원문 예제 요지 (Java·C·C#)**: 입력 화면 요청 시 `UUID.randomUUID()` 토큰을 세션에 저장 → hidden 필드로 전달 → 처리 시 요청 파라미터와 세션 토큰 비교. C# `@Html.AntiForgeryToken()`.

#### Python 시큐어코딩 가이드(2023) 원문 — 2장 1절 11항 (p.48~54)

- **Python 관련 설명**: Django는 **1.2 버전부터** CSRF 방지 기능을 기본 제공하며 `{% csrf_token %}` 태그를 쓴다. Flask는 **Flask-WTF 확장**의 `CSRFProtect`와 `{{ form.csrf_token }}`(FlaskForm 사용 시) 또는 hidden input `{{ csrf_token() }}`(FlaskForm 미사용 시)을 쓴다.
- **안전한 코딩기법**: 세션별 CSRF 토큰을 만들어 세션에 저장하고, 작업 페이지 요청 시 hidden 값으로 전달한 뒤, 처리 요청 시 토큰을 검사한다. 프레임워크 기능을 쓰려면 **form 태그 안에 csrf_token을 반드시 명시**해야 한다.
- **취약 패턴 (가이드 명시)**
  1. `settings.py`의 `MIDDLEWARE`에서 `'django.middleware.csrf.CsrfViewMiddleware'`를 삭제·주석 처리 → 전역적으로 CSRF 검증 제거
  2. 뷰에 `@csrf_exempt` 데코레이터 → 해당 요청 검증 해제. 부득이하면 미들웨어는 켜 두고 **필요한 요청에만** 쓰되 위험에 주의
  3. 미들웨어가 켜져 있어도 **템플릿 form에 `{% csrf_token %}`이 없으면** 검증이 동작하지 않음
  4. Flask에서 `CSRFProtect` 미설정, 또는 템플릿에 토큰 누락
- **원문 예제**

```python
# [가이드 원문] Django — 안전하지 않은 코드: 결제 뷰에서 CSRF 해제
from django.views.decorators.csrf import csrf_exempt


@csrf_exempt
def pay_to_point(request):
    user_id = request.POST.get('user_id', '')
    pay = request.POST.get('pay', '')
    product_info = request.POST.get('product_info', '')
    ret = handle_pay(user_id, pay, product_info)
    return render(request, '/view_wallet.html', {'wallet': ret})
# 안전한 코드: @csrf_exempt를 삭제하고 MIDDLEWARE에 CsrfViewMiddleware를 유지


# [가이드 원문] Flask — 안전한 코드 (순서 오류를 바로잡음: app 생성 후 init_app)
import os

from flask import Flask
from flask_wtf.csrf import CSRFProtect

csrf = CSRFProtect()
app = Flask(__name__)
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY')
csrf.init_app(app)
```

```html
<!-- [가이드 원문] Django 템플릿 -->
<form action="" method="POST">
  {% csrf_token %}
  <table>{{ form.as_table }}</table>
  <input type="submit"/>
</form>

<!-- [가이드 원문] Flask 템플릿 (FlaskForm 미사용 시) -->
<form action="" method="POST">
  <input type="hidden" name="csrf_token" value="{{ csrf_token() }}" />
  <input type="submit"/>
</form>
```

- **검토 메모**
  - 가이드 Flask 예제는 `csrf = CSRFProtect(app)`을 `app = Flask(__name__)`보다 먼저 호출해 그대로는 실행되지 않는다. 위 코드처럼 바로잡았다.
  - 가이드 결제 예제는 `user_id`를 요청 본문에서 받는다. 이는 INP-15/SEC-01(클라이언트가 보낸 식별자 신뢰) 관점에서도 지적 대상이다.
  - 탐지 패턴에 `MIDDLEWARE`에서 `CsrfViewMiddleware`가 **주석 처리**된 경우(`# 'django.middleware.csrf.CsrfViewMiddleware'`)와 템플릿 POST 폼의 `{% csrf_token %}` 누락을 포함한다.

#### 이 스킬의 점검 기준 (2021 가이드 + 실무 기준)

**탐지 패턴 (Python)**
- Django: `MIDDLEWARE`에 `django.middleware.csrf.CsrfViewMiddleware` 누락, `@csrf_exempt`, 템플릿 POST 폼에 `{% csrf_token %}` 누락, `CSRF_COOKIE_HTTPONLY`/`CSRF_TRUSTED_ORIGINS` 과도한 허용(`*`)
- Flask: `flask_wtf.csrf.CSRFProtect` 미적용, `WTF_CSRF_ENABLED = False`, `@csrf.exempt`, FlaskForm을 쓰지 않는 수동 폼
- FastAPI/Starlette: 쿠키 기반 인증인데 CSRF 방어(토큰, `SameSite`, Origin 검증) 없음
- DRF: `SessionAuthentication` 사용 시 CSRF가 적용되지만, 커스텀 인증 클래스에서 `enforce_csrf`를 비워 둔 경우
- 공통: GET 핸들러에서 상태 변경(삭제·수정·결제), 세션 쿠키 `SameSite=None`

**보충 예제 — 취약 코드**
```python
# Flask — CSRF 보호 없음, GET으로 상태 변경
@app.route("/member/delete")
@login_required
def delete_member():
    Member.query.filter_by(id=request.args["id"]).delete()
    db.session.commit()
    return redirect("/admin/members")


# Django
@csrf_exempt
def transfer(request):
    ...
```

**보충 예제 — 안전 코드 (권장 기준)**
```python
# Flask — Flask-WTF로 전역 CSRF 보호, 상태 변경은 POST
from flask_wtf.csrf import CSRFProtect

csrf = CSRFProtect(app)
app.config.update(SESSION_COOKIE_SAMESITE="Lax", SESSION_COOKIE_SECURE=True)


@app.route("/member/delete", methods=["POST"])
@login_required
@admin_required
def delete_member():
    Member.query.filter_by(id=request.form["id"]).delete()
    db.session.commit()
    return redirect("/admin/members")
# 템플릿: <input type="hidden" name="csrf_token" value="{{ csrf_token() }}">


# 수동 구현 (원문 Java 예제 그대로 옮김)
import hmac
import secrets


@app.route("/apply", methods=["GET"])
def apply_form():
    session["csrf_token"] = secrets.token_urlsafe(32)
    return render_template("apply.html", csrf_token=session["csrf_token"])


@app.route("/apply", methods=["POST"])
def apply_submit():
    p_token = request.form.get("param_csrf_token", "")
    s_token = session.get("csrf_token", "")
    if not s_token or not hmac.compare_digest(p_token, s_token):
        abort(403)
    ...


# Django — 기본 미들웨어 유지, 템플릿 폼에 {% csrf_token %}
# 중요기능 재인증: 비밀번호 재확인 후 처리
```

**판정 기준 / 오탐 주의**
- 순수 토큰 인증(Authorization 헤더 Bearer) API는 브라우저가 자동으로 자격증명을 붙이지 않으므로 CSRF 위험이 낮다. 쿠키로 인증하는지부터 확인한다.
- `SameSite=Lax`만으로는 GET 상태 변경을 막지 못한다.

---

### INP-12. 서버사이드 요청 위조 (SSRF)

| 항목 | 내용 |
|---|---|
| 심각도 | 높음 |
| CWE | CWE-918 |
| 연관 설계항목 | SR1-4, SR2-1 |

#### KISA 소프트웨어 개발보안 가이드(2021) 원문

**개요 (2021 원문)**: 검증되지 않은 사용자 입력을 서버 간 요청에 쓰면 악의적인 행위가 생길 수 있다. 외부에 노출된 웹 서버의 취약한 애플리케이션을 통해 URL·요청문을 위조해 접근통제를 우회하고, 신뢰된 내부 네트워크의 데이터를 얻을 수 있다.

원문의 공격 예:

| 목적 | 삽입 예 |
|---|---|
| 내부망 중요정보 획득 | `?url=http://192.168.0.45/member/list.json` |
| 외부 접근이 차단된 admin 접근 | `?url=http://192.168.0.45/admin` |
| 도메인 체크 우회 | `?url=http://site_example.com:x@192.168.0.45/member/list.json` |
| 단축 URL로 필터 우회 | `?url=http://bit.ly/sdjk3kjhkl3` |
| 도메인을 사설 IP로 설정 | `?url=http://internal.site.com/member/list.json` |
| 서버 내 파일 열람 | `?url=http://attack/fileview.html` |

**보안대책 (2021 원문)**: 식별 가능한 범위의 사용자 입력을 다른 시스템 호출에 쓸 때는 **화이트리스트**로 필터링한다. 임의 URL을 받아야 하면 내부 URL을 **블랙리스트**로 지정해 필터링한다. 같은 내부 네트워크라도 기기 인증과 접근권한을 확인한 뒤 요청한다.

**2021 원문 예제 요지 (Java·C·C#)**: Java `new URL(req.getParameter("url")).openConnection()` → `Map<String, URL>`에서 키로 조회.

#### Python 시큐어코딩 가이드(2023) 원문 — 2장 1절 12항 (p.55~57)

- **안전한 코딩기법**: 2021 가이드와 같다(화이트리스트 필터링, 불가피하면 내부 URL 블랙리스트, 같은 내부망이어도 기기 인증·접근권한 확인).
- **삽입 예 (가이드 표)**: 2021 가이드 표와 같고, "서버 내 파일 열람" 예가 **`?url=file:///etc/passwd`**로 바뀌었다.
- **원문 예제**

```python
import requests


# [가이드 원문] 안전하지 않은 코드
def call_third_party_api(request):
    addr = request.POST.get('address', '')
    result = requests.get(addr).text
    return render(request, '/result.html', {'result': result})


# [가이드 원문] 안전한 코드 — 허용 서버 목록 (도메인 대신 IP로 정의)
# 허용 도메인을 화이트리스트로 정의하면 DNS rebinding 공격에 노출될 위험이 있어
# 신뢰할 수 있는 자원의 IP로 검증하는 것이 조금 더 안전하다.
ALLOW_SERVER_LIST = [
    'https://127.0.0.1/latest/',
    'https://192.168.0.1/user_data',
    'https://192.168.0.100/v1/public',
]


def call_third_party_api(request):
    addr = request.POST.get('address', '')
    if addr not in ALLOW_SERVER_LIST:
        return render(request, '/error.html', {'error': '허용되지 않은 서버입니다.'})
    result = requests.get(addr).text
    return render(request, '/result.html', {'result': result})
```

- **검토 메모**: 가이드는 **DNS rebinding 위험 때문에 도메인보다 IP 기반 허용목록**을 권한다. 다만 `requests.get()`은 기본적으로 **리다이렉트를 따라가므로**, 허용된 서버가 다른 곳으로 리다이렉트하면 우회된다. `allow_redirects=False`와 `timeout`을 함께 권고한다. `requests`는 `file://`을 지원하지 않지만 `urllib.request.urlopen`은 지원하므로, urllib을 쓰는 코드는 스킴 검사를 특히 확인한다.

#### 이 스킬의 점검 기준 (2021 가이드 + 실무 기준)

**탐지 패턴 (Python)**
- 싱크: `requests.get/post/put/delete/head/request(`, `httpx.get/...(`, `httpx.Client().get(`, `aiohttp.ClientSession().get(`, `urllib.request.urlopen(`, `urllib.request.Request(`, `urllib3.PoolManager().request(`, `http.client.HTTPConnection(host)`, `pycurl`, `socket.create_connection((host, port))`, `ftplib.FTP(host)`, `smtplib.SMTP(host)`
- 간접 싱크: `PIL.Image.open(urlopen(url))`, `pandas.read_csv(url)`/`read_html(url)`/`read_json(url)`, `lxml.etree.parse(url)`, 웹훅·이미지 프록시·URL 미리보기·PDF 생성기(`weasyprint`, `pdfkit`)에 사용자 URL 전달
- 위험 신호: URL 전체나 호스트를 외부 입력에서 받음, `urllib.urlopen`으로 `file://` 스킴 허용, 리다이렉트 자동 추종(`allow_redirects=True`, 기본값)으로 검증 우회

**보충 예제 — 취약 코드**
```python
import requests


@app.route("/connect")
def connect():
    url = request.args.get("url", "")
    resp = requests.get(url, timeout=5)  # http://169.254.169.254/ (클라우드 메타데이터) 등 접근
    return resp.text
```

**보충 예제 — 안전 코드 (권장 기준)**
```python
import ipaddress
import socket
from urllib.parse import urlparse

import requests

# 1) 키 → URL 매핑 (원문 urlMap 대응) — 가장 안전
URL_MAP = {
    "weather": "https://api.weather.example.com/v1/today",
    "news": "https://api.news.example.com/v1/top",
}


@app.route("/connect")
def connect():
    url = URL_MAP.get(request.args.get("url", ""))
    if url is None:
        abort(400)
    return requests.get(url, timeout=5, allow_redirects=False).text


# 2) 임의 URL을 받아야 하는 경우: 스킴·호스트 검증 + 내부 대역 차단 (원문 '내부 URL 블랙리스트')
def is_safe_public_url(url: str) -> bool:
    p = urlparse(url)
    if p.scheme not in {"http", "https"} or not p.hostname or p.username or p.password:
        return False
    try:
        infos = socket.getaddrinfo(p.hostname, p.port or (443 if p.scheme == "https" else 80))
    except socket.gaierror:
        return False
    for info in infos:
        ip = ipaddress.ip_address(info[4][0])
        if (ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved
                or ip.is_multicast or ip.is_unspecified):
            return False
    return True


@app.route("/preview")
def preview():
    url = request.args.get("url", "")
    if not is_safe_public_url(url):
        abort(400)
    # 리다이렉트를 따라가지 않음 (따라가야 하면 매 hop마다 재검증)
    return requests.get(url, timeout=5, allow_redirects=False).text[:1000]
```

**판정 기준 / 오탐 주의**
- 2)의 방식은 검증 시점과 요청 시점의 DNS 결과가 다른 **DNS 리바인딩**에 취약할 수 있다. 확인된 IP로 직접 연결하거나 egress 프록시·방화벽으로 내부 대역을 차단하는 방식을 함께 제안한다.
- 호스트가 코드 상수이고 경로·쿼리만 사용자 입력이면 SSRF보다는 경로 조작·파라미터 삽입 관점으로 본다.

---

### INP-13. HTTP 응답분할 (HTTP Response Splitting)

| 항목 | 내용 |
|---|---|
| 심각도 | 중간 |
| CWE | CWE-113 |
| 연관 설계항목 | SR1-7 |

#### KISA 소프트웨어 개발보안 가이드(2021) 원문

**개요 (2021 원문)**: HTTP 요청 파라미터가 응답 헤더에 포함되어 돌아갈 때, 입력값에 CR·LF 개행문자가 있으면 응답이 2개 이상으로 나뉠 수 있다. 공격자는 첫 응답을 끝내고 두 번째 응답에 악성 코드를 넣어 XSS나 캐시 훼손(Cache Poisoning)을 수행한다.
- 예: `lastLogin = "Wiley Hacker\r\nHTTP/1.1 200 OK\r\n"` 을 쿠키 값으로 설정.

**보안대책 (2021 원문)**: 요청 파라미터 값을 HTTP 응답 헤더(예: `Set-Cookie`)에 넣을 때 CR, LF 같은 개행문자를 제거한다. null 여부도 확인한다.

**2021 원문 예제 요지 (Java·C·C#)**: Java `new Cookie("LASTLOGIN", lastLogin)` → `replaceAll("[\\r\\n]", "")`. C# `Response.AddHeader("foo", "bar" + usrInput)` → `\n`, `\r` 제거.

#### Python 시큐어코딩 가이드(2023) 원문 — 2장 1절 13항 (p.58~60)

- **Python 관련 설명**: **파이썬 3.9.5+ 버전의 URLValidator 관련 HTTP 응답분할 취약점**이 보고되었고, 이를 쓰는 **Django 버전에도 영향**이 있었다(2021년 5월 Django 보안 릴리스). 최신 버전의 라이브러리·프레임워크를 쓰고 외부 입력을 철저히 검증해야 한다.
- **안전한 코딩기법**: 요청 파라미터를 응답 헤더(`Set-Cookie` 등)에 넣을 때 CR(`\r`)·LF(`\n`)를 제거한다. 외부 입력이 **헤더, 쿠키, 로그** 등에 쓰이면 항상 개행문자를 검증하고, 가능하면 헤더에 쓰이는 값을 **화이트리스트로 제한**한다.
- **원문 예제**

```python
from django.http import HttpResponse


# [가이드 원문] 안전하지 않은 코드 — 외부 입력을 Content-Type 헤더로
def route(request):
    content_type = request.POST.get('content-type')
    res = HttpResponse()
    res['Content-Type'] = content_type
    return res


# [가이드 원문] 안전한 코드 — 개행 문자 제거
def route(request):
    content_type = request.POST.get('content-type')
    content_type = content_type.replace('\r', '')
    content_type = content_type.replace('\n', '')
    res = HttpResponse()
    res['Content-Type'] = content_type
    return res
```

- **검토 메모**: 가이드가 권하는 "헤더 값 화이트리스트"가 이 예제에 더 맞다(예: `{'json': 'application/json', 'csv': 'text/csv'}`에서 선택). 외부 입력으로 Content-Type 자체를 정하게 하면 `text/html`로 바꿔 XSS를 유도할 수 있다. 로그에 쓰이는 값의 개행 제거(로그 위조 방지)도 이 항목 범위로 본다. 의존성 점검 시 Django 2.2.22 / 3.1.10 / 3.2.2 미만이면 해당 보안 릴리스 미적용으로 지적한다.

#### 이 스킬의 점검 기준 (2021 가이드 + 실무 기준)

**탐지 패턴 (Python)**
- 싱크: `response.headers[...] = `, `response.headers.add(`, `make_response(body, status, {헤더: 입력값})`, `response.set_cookie(key, value)`, Django `response[헤더] = `, `HttpResponse(..., headers=)`, Starlette `Response(headers=)`, `redirect(입력값)`의 `Location`, `Content-Disposition`의 `filename=`
- Python 특이사항: 최신 Werkzeug·Django·Starlette는 헤더 값의 개행을 거부하거나 예외를 발생시키는 경우가 많다. 하지만 **저수준 서버(`http.server`, `wsgiref`, 직접 만든 WSGI `start_response`), 구버전 프레임워크, 소켓으로 직접 응답 작성**에서는 여전히 위험하다.

**보충 예제 — 취약 코드**
```python
@app.route("/remember")
def remember():
    last_login = request.args.get("last_login")
    if not last_login:
        return "", 400
    resp = make_response("ok")
    resp.headers["X-Last-Login"] = last_login  # CR/LF 포함 시 응답 분할 (프레임워크 버전에 따라)
    return resp


# 저수준 WSGI
def application(environ, start_response):
    lang = parse_qs(environ["QUERY_STRING"]).get("lang", ["ko"])[0]
    start_response("200 OK", [("Content-Language", lang)])
    return [b"ok"]
```

**보충 예제 — 안전 코드 (권장 기준)**
```python
import re

CRLF = re.compile(r"[\r\n]")


@app.route("/remember")
def remember():
    last_login = request.args.get("last_login")
    if not last_login:
        return "", 400
    last_login = CRLF.sub("", last_login)  # 원문 replaceAll("[\\r\\n]", "") 대응
    resp = make_response("ok")
    resp.set_cookie("LASTLOGIN", last_login, max_age=1000, secure=True,
                    httponly=True, samesite="Lax")
    return resp


# 다운로드 파일명은 RFC 5987 인코딩 (헤더 삽입 방지)
from urllib.parse import quote

resp.headers["Content-Disposition"] = f"attachment; filename*=UTF-8''{quote(filename)}"
```

**판정 기준 / 오탐 주의**
- 사용 중인 프레임워크 버전이 헤더 개행을 막는지 확인하되, 방어 심층화 차원에서 입력 정규화가 있는지 본다. 막혀 있으면 심각도를 "낮음"으로 조정한다.

---

### INP-14. 정수형 오버플로우 (Integer Overflow)

| 항목 | 내용 |
|---|---|
| 심각도 | 낮음 (순수 Python) / 높음 (C 확장·NumPy·ctypes·외부 시스템 연동) |
| CWE | CWE-190 |
| 연관 설계항목 | SR1-9 |

#### KISA 소프트웨어 개발보안 가이드(2021) 원문

**개요 (2021 원문)**: 정수형 크기가 고정되어 있는데 범위를 넘는 값을 저장하면 아주 작은 수나 음수가 되어 프로그램이 예기치 않게 동작한다. 반복문 제어, 메모리 할당, 메모리 복사의 조건으로 사용자 입력을 쓰다 오버플로우가 나면 보안 문제가 된다.

**보안대책 (2021 원문)**: 언어·플랫폼별 정수 타입 범위를 확인해 쓴다. 정수 연산에는 결과값 범위를 확인하는 모듈을 쓴다. 특히 외부 입력을 동적 메모리 할당에 쓰면 값이 적절한 범위인지 확인한다.

**2021 원문 예제 요지 (Java·C·C#)**: Java `new String[Integer.parseInt(tmp)]` → 음수 검사. C# `array[Int32.Parse(args[0])]` → `checked`와 범위 검사. C `num_array[atoi(argv[1])]` → `0 <= n < 4` 검사.

#### Python 시큐어코딩 가이드(2023) 원문 — 2장 1절 14항 (p.61~63)

- **Python 관련 설명**: 파이썬 2.x는 int가 범위를 넘으면 자동으로 long으로 바뀐다. 파이썬 3.x는 long을 없애고 int에 **임의 정밀도(Arbitrary-precision)** 방식을 써서 오버플로우가 발생하지 않는다. 하지만 **pydata stack(numpy 등) 패키지는 C와 같은 방식으로 정수를 처리**하므로 오버플로우에 유의해야 한다.
- **안전한 코딩기법**: 패키지 데이터 타입을 쓸 때는 **표현 방식과 최대 크기를 반드시 확인**한다. numpy는 기본 64비트 정수를 쓰고, 표현할 수 없는 큰 수는 object(문자열 형식)로 변환하는 기능을 제공하지만 64비트를 넘는 수는 제대로 처리하지 못한다. 값을 할당하기 전에 최소·최대값을 확인하고 범위를 넘는 값을 할당하지 않는지 테스트한다. 계산이 필요하면 **파이썬 기본 자료형으로 먼저 계산해 범위를 검사**한 뒤 numpy 타입에 넣는다.
- **원문 예제**

```python
import numpy as np


# [가이드 원문] 안전하지 않은 코드 — 64비트를 넘으면 결과가 0 등 잘못된 값
def handle_data(number, pow):
    res = np.power(number, pow, dtype=np.int64)
    return res


# [가이드 원문] 안전한 코드 — 파이썬 int로 먼저 계산해 범위 검사
MAX_NUMBER = np.iinfo(np.int64).max
MIN_NUMBER = np.iinfo(np.int64).min


def handle_data(number, pow):
    calculated = number ** pow
    if calculated > MAX_NUMBER or calculated < MIN_NUMBER:
        return -1          # 오버플로우 탐지 시 비정상 종료를 나타내는 -1 반환
    res = np.power(number, pow, dtype=np.int64)
    return res
```

- **검토 메모**: 가이드 안전 예제의 `number ** pow`는 외부 입력이 크면 **매우 큰 정수를 실제로 계산해 CPU·메모리를 고갈**시킬 수 있다(예: `10 ** 10_000_000`). 외부 입력이면 `number`, `pow`의 범위부터 제한하도록 권고한다. 이 스킬의 INP-14 판정 기준(인덱스·크기·반복 횟수·금액 범위 검사)과 함께 적용한다.

#### 이 스킬의 점검 기준 (2021 가이드 + 실무 기준)

**Python 관점**
- Python `int`는 임의 정밀도라 언어 수준 오버플로우는 없다. 대신 다음이 이 항목에 해당한다.
  - **NumPy/pandas 고정폭 정수**(`int32`, `uint8` 등)의 랩어라운드
  - `ctypes.c_int`, `struct.pack("i", ...)`, `array.array("i")` 범위 초과
  - DB 컬럼(INT, BIGINT)·외부 API·바이너리 프로토콜로 넘길 때 범위 초과
  - **음수 인덱스**: `items[int(user_input)]` 에 `-1`이 들어가면 마지막 요소에 접근(의도치 않은 데이터 노출)
  - **자원 고갈**: `[0] * n`, `range(n)`, `"x" * n`, `bytearray(n)`, 페이지 크기 `limit=n` 에 큰 값 → 메모리·CPU 고갈(DoS)
  - 매우 긴 숫자 문자열의 `int()` 변환 비용 (Python 3.11+는 기본 4300자리 제한)
  - 금액 계산에서 `float` 사용 → 정밀도 오류(무결성 문제, `decimal.Decimal` 사용 권장)

**탐지 패턴 (Python)**
- `int(request...)`, `float(request...)` 결과를 범위 검사 없이 인덱스·크기·반복 횟수·`limit`/`offset`·수량·금액에 사용
- `np.array(..., dtype=np.int32)` 등 고정폭 타입에 외부 값을 넣고 산술
- `struct.pack`/`ctypes`에 외부 값

**보충 예제 — 취약 코드**
```python
@app.route("/msg")
def msg():
    param_ct = int(request.args.get("slf_msg_param_num", "0"))
    str_arr = [""] * param_ct  # 음수면 빈 리스트(로직 오류), 매우 크면 메모리 고갈
    names = ["one", "two", "three", "four"]
    return names[int(request.args["idx"])]  # -1 → 마지막 요소, 10 → IndexError(500)


import numpy as np

qty = np.int32(request.args["qty"])
total = qty * np.int32(1_000_000)  # 랩어라운드로 음수 금액 가능
```

**보충 예제 — 안전 코드 (권장 기준)**
```python
from decimal import Decimal

MAX_PARAMS = 100
NAMES = ["one", "two", "three", "four"]


def bounded_int(raw: str, lo: int, hi: int) -> int:
    try:
        value = int(raw)
    except (TypeError, ValueError):
        abort(400, "잘못된 입력(접근) 입니다.")
    if not lo <= value <= hi:
        abort(400, "잘못된 입력(접근) 입니다.")
    return value


@app.route("/msg")
def msg():
    param_ct = bounded_int(request.args.get("slf_msg_param_num", "0"), 0, MAX_PARAMS)
    str_arr = [""] * param_ct
    idx = bounded_int(request.args.get("idx", ""), 0, len(NAMES) - 1)
    return NAMES[idx]


# 금액·수량은 범위 검사 + Decimal, NumPy는 int64 및 범위 검사
qty = bounded_int(request.args.get("qty", ""), 1, 1000)
total = Decimal(qty) * get_price_from_db(item_id)
```

**판정 기준 / 오탐 주의**
- pydantic `conint(ge=0, le=100)`/`Field(ge=, le=)`, Django `MinValueValidator`/`MaxValueValidator`, DRF `max_value`로 검증되면 충족이다.

---

### INP-15. 보안기능 결정에 사용되는 부적절한 입력값

| 항목 | 내용 |
|---|---|
| 심각도 | 높음 |
| CWE | CWE-807 |
| 연관 설계항목 | SR1-9 |

#### KISA 소프트웨어 개발보안 가이드(2021) 원문

**개요 (2021 원문)**: 외부 입력을 신뢰한다는 전제로 보호 메커니즘을 쓰면, 입력을 조작할 수 있는 공격자는 보호 메커니즘을 우회한다. 개발자는 쿠키, 환경변수, 파라미터(**히든필드 포함**)가 조작될 수 없다고 가정하지만 공격자는 여러 방법으로 바꿀 수 있고, 조작은 탐지되지 않을 수 있다. 인증·인가 같은 보안결정이 이런 값에 기반하면 보안이 우회된다.

**보안대책 (2021 원문)**: 상태정보나 민감 데이터, 특히 **세션정보 같은 중요 정보는 서버에 저장**하고 보안 확인 절차도 서버에서 실행한다. 신뢰할 수 없는 입력이 들어오는 지점과 보안결정에 쓰이는 입력을 식별하고, 입력에 의존하지 않는 구조로 바꿀 수 있는지 검토한다.

**2021 원문 예제 요지 (Java·C·C#)**
- 클라이언트가 보낸 `memberID`로 토큰B 발급 → 인증서버가 발급한 **토큰A의 서명·만료를 서버에서 검증**하고 거기서 추출한 ID로 발급, 실패 시 401.
- hidden 필드 `price`로 총액 계산 → `item`만 받고 **서버가 보유한 가격**으로 계산.
- C# 쿠키 `Authentificated=1` 평문 저장 → 서버 세션에 저장.
- C 환경변수 `server_addr`로 라이선스 서버 연결 → 고정된 서버 주소 사용.

#### Python 시큐어코딩 가이드(2023) 원문 — 2장 1절 15항 (p.64~67)

- **Python 관련 설명**: Django는 **서버 측 세션** 기능을 제공해 클라이언트에는 세션 ID만 전달하고, 사용자 정보와 권한 등 보안 결정에 필요한 정보는 서버에서 저장·관리할 수 있다. **DRF(Django REST Framework)의 토큰·세션 인증**이나 **djangorestframework-simplejwt** 같은 JWT 라이브러리를 쓰면 서명 검증을 거친 인증 정보로 보안 결정을 할 수 있다.
- **안전한 코딩기법**: 인증·인가 웹 요청·응답 절차를 식별한 뒤, 인증·인가를 결정하는 값을 쿠키·파라미터(히든필드 포함)처럼 **클라이언트가 조작할 수 있는 위치로 보내거나 받아서 쓰지 않는다.** 보안 기능 입력값이 **인증 성공 여부나 회원 식별자**면 위변조에 취약하므로, 반환받은 **토큰**을 입력으로 쓴다.
- **원문 예제** (인증 서버가 발급한 Token A로 서비스 B의 Token B를 발급하는 다단계 인증)

```python
from jwt import InvalidTokenError
from rest_framework import status
from rest_framework.decorators import api_view
from rest_framework.response import Response


# [가이드 원문] 안전하지 않은 코드 — 클라이언트가 보낸 memberID 신뢰
@api_view(['POST'])
def authenticate_b(request):
    member_id = request.data.get('memberID')
    token_b = token_service.generate_token_b(member_id)
    return Response({'tokenB': token_b}, status=status.HTTP_200_OK)


# [가이드 원문] 안전한 코드 — Token A 서명·만료 검증 후 추출한 ID 사용
@api_view(['POST'])
def authenticate_b(request):
    token_a = request.data.get('tokenA')
    if not token_a:
        return Response({'error': 'Token A is required.'}, status=status.HTTP_401_UNAUTHORIZED)
    try:
        verified_member_id = token_service.verify_and_extract_from_token_a(token_a)
    except InvalidTokenError:
        return Response({'error': 'Invalid or expired Token A.'},
                        status=status.HTTP_401_UNAUTHORIZED)
    token_b = token_service.generate_token_b(verified_member_id)
    return Response({'tokenB': token_b}, status=status.HTTP_200_OK)
```

- **검토 메모**: `verify_and_extract_from_token_a` 내부에서 `jwt.decode(..., algorithms=[...])`로 서명·만료·`aud`·`iss`를 검증하는지 확인한다(SEC-10). 판정 기준은 이 스킬과 같다.

#### 이 스킬의 점검 기준 (2021 가이드 + 실무 기준)

**탐지 패턴 (Python)**
- 권한·인증 판단에 클라이언트 값 사용: `request.cookies.get("role"|"is_admin"|"auth"|"user_id"|"level")`, `request.form["price"|"amount"|"discount"|"is_paid"]`, `request.headers.get("X-User-Id"|"X-Role")` (게이트웨이가 주입·덮어쓰는 구조가 아니라면), `request.args.get("admin")`
- 서명 검증 생략: `jwt.decode(token, options={"verify_signature": False})`, `algorithms` 미지정, `algorithms=["none"]`, 검증 없이 `base64` 디코드만 해서 페이로드 사용
- 외부 인증 결과를 클라이언트가 전달: 소셜 로그인 후 클라이언트가 보낸 `email`/`sub`을 그대로 신뢰 (ID 토큰 서버 검증 없음)
- `X-Forwarded-For`/`X-Real-IP`를 신뢰해 IP 기반 접근통제 (프록시 신뢰 설정 없이)
- 환경변수로 보안 동작 전환: `if os.environ.get("SKIP_AUTH")`, 라이선스·인증 서버 주소를 사용자 제어 가능한 설정에서 읽음
- Flask 기본 세션은 **서명된 클라이언트 쿠키**다(암호화 아님). 내용은 누구나 읽을 수 있으므로 민감정보를 넣지 않는다.

**보충 예제 — 취약 코드**
```python
@app.route("/admin")
def admin():
    if request.cookies.get("role") == "admin":  # 쿠키 변조로 권한 상승
        return render_template("admin.html")
    abort(403)


@app.route("/order", methods=["POST"])
def order():
    price = float(request.form["price"])  # hidden 필드 가격을 신뢰
    quantity = int(request.form["quantity"])
    total = price * quantity
    ...


@app.route("/token-b", methods=["POST"])
def token_b():
    member_id = request.json["memberID"]  # 클라이언트가 보낸 식별자를 신뢰
    return {"tokenB": issue_token_b(member_id)}


payload = jwt.decode(token, options={"verify_signature": False})
```

**보충 예제 — 안전 코드 (권장 기준)**
```python
import jwt  # PyJWT


@app.route("/admin")
@login_required
def admin():
    if not current_user.has_role("admin"):  # 서버 DB/세션의 권한 정보
        abort(403)
    return render_template("admin.html")


@app.route("/order", methods=["POST"])
@login_required
def order():
    item_id = request.form["item"]
    quantity = bounded_int(request.form.get("quantity", ""), 1, 100)
    product = Product.query.get_or_404(item_id)
    total = product.price * quantity  # 서버가 보유한 가격 사용
    ...


@app.route("/token-b", methods=["POST"])
def token_b():
    token_a = request.json.get("tokenA", "")
    try:
        claims = jwt.decode(
            token_a,
            key=AUTH_SERVER_PUBLIC_KEY,
            algorithms=["RS256"],          # 허용 알고리즘 명시
            audience="web-server",
            issuer="https://auth.example.com",
            options={"require": ["exp", "sub"]},
        )
    except jwt.PyJWTError:
        return {"error": "Invalid or expired Token A."}, 401
    return {"tokenB": issue_token_b(claims["sub"])}


# 신뢰 프록시 뒤에서만 X-Forwarded-* 사용
from werkzeug.middleware.proxy_fix import ProxyFix

app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1)
```

**판정 기준 / 오탐 주의**
- API 게이트웨이가 인증 후 `X-User-Id` 헤더를 **덮어쓰고**, 서비스가 게이트웨이 외 경로로 접근 불가하면 허용 가능하다. 네트워크 구성을 확인할 수 없으면 "의심"으로 보고한다.
- 쿠키 값이 서버 서명(`itsdangerous`, Django `signing`)으로 무결성 검증되면 변조 위험은 낮다. 기밀성은 별도로 SEC-05/SEC-12로 본다.

---

### INP-16. 메모리 버퍼 오버플로우 (Buffer Overflow)

| 항목 | 내용 |
|---|---|
| 심각도 | 높음 (해당 코드가 있을 때) |
| CWE | CWE-119, CWE-120 |
| 연관 설계항목 | SR1-8 |

#### KISA 소프트웨어 개발보안 가이드(2021) 원문

**개요 (2021 원문)**: 연속된 메모리 공간을 쓰는 프로그램에서 할당 범위를 넘는 위치에 읽거나 쓸 때 생긴다. 프로그램 오동작이나 악성 코드 실행으로 이어진다. 스택 버퍼 오버플로우와 힙 버퍼 오버플로우가 있다. (예: `gets(message)`로 복귀 주소를 덮어써 공격 코드 실행)

**보안대책 (2021 원문)**: 버퍼를 쓸 때 적절한 크기를 설정하고, 설정된 범위 안에서만 읽고 쓰도록 통제한다. 문자열은 버퍼 범위 안에 **널(Null) 문자를 넣어 종료**한다.

**2021 원문 예제 요지 (Java·C·C#)**: C `memcpy(cv_struct.x, SRC_STR, sizeof(cv_struct))` (구조체 전체 크기로 복사해 포인터 y 덮어씀) → `sizeof(cv_struct.x)` 사용 + 마지막 인덱스에 `'\0'`.

#### Python 시큐어코딩 가이드(2023) 원문

**언어 특성상 제외된 항목**이다(49개 중 46개만 수록, 제외: 메모리 버퍼 오버플로우, 해제된 자원 사용, 초기화되지 않은 변수 사용). 이 스킬에서는 `ctypes`/`cffi`/C 확장 등 네이티브 코드가 있을 때만 2021 가이드 기준으로 점검한다.

#### 이 스킬의 점검 기준 (2021 가이드 + 실무 기준)

**Python 관점**
- 순수 Python 객체(`str`, `bytes`, `list`)는 경계 검사가 있어 이 약점이 생기지 않는다.
- 해당되는 경우: `ctypes`, `cffi`, Cython(`cdef char buf[...]`), C/C++ 확장 모듈, `mmap`, `memoryview`를 통한 외부 버퍼 쓰기, `numpy` 저수준 버퍼(`np.frombuffer` + `ctypes` 포인터), 네이티브 라이브러리 바인딩에 길이 인자를 사용자 입력으로 전달.

**탐지 패턴 (Python)**
- `ctypes.memmove(`, `ctypes.memset(`, `ctypes.create_string_buffer(`, `ctypes.string_at(`, `ctypes.cast(`, `ctypes.addressof(`, `(c_char * n).from_buffer(`
- `cffi.FFI().new("char[]", n)` 후 `ffi.memmove`, `ffi.buffer`
- `.pyx`, `.c`, `.cpp` 파일 — C 규칙(`strcpy`, `strcat`, `sprintf`, `gets`, `scanf("%s")`, `memcpy` 길이)으로 별도 점검
- `struct.pack_into(fmt, buf, offset, ...)`의 offset이 외부 입력

**보충 예제 — 취약 코드**
```python
import ctypes

buf = ctypes.create_string_buffer(16)


def copy_name(data: bytes) -> None:
    ctypes.memmove(buf, data, len(data))  # data가 16바이트를 넘으면 인접 메모리 덮어씀
```

**보충 예제 — 안전 코드 (권장 기준)**
```python
import ctypes

BUF_SIZE = 16
buf = ctypes.create_string_buffer(BUF_SIZE)


def copy_name(data: bytes) -> None:
    n = min(len(data), BUF_SIZE - 1)  # 목적지 크기 기준, 널 종료 공간 확보
    ctypes.memmove(buf, data, n)
    buf[n] = b"\x00"                   # 원문의 널 문자 패딩 대응


# 가능하면 ctypes 대신 bytes/bytearray 슬라이싱 사용 (경계 검사 자동)
```

**판정 기준 / 오탐 주의**
- 프로젝트에 네이티브 코드가 전혀 없으면 "해당없음"으로 보고한다.

---

### INP-17. 포맷 스트링 삽입 (Format String Injection)

| 항목 | 내용 |
|---|---|
| 심각도 | 중간 |
| CWE | CWE-134 |
| 연관 설계항목 | SR1-8 |

#### KISA 소프트웨어 개발보안 가이드(2021) 원문

**개요 (2021 원문)**: 외부 입력을 검증 없이 입·출력 함수의 **포맷 문자열로** 그대로 쓰면, 공격자가 포맷 문자열로 프로세스를 공격하거나 메모리를 읽고 쓸 수 있고, 임의 코드 실행까지 이어질 수 있다. 원문은 이 약점이 **C에만 국한되지 않는다**고 명시한다 (Java에서 `%1$tY-%1$tm-%1$te` 입력으로 내부 날짜 정보 노출).

**보안대책 (2021 원문)**: `printf()`, `snprintf()` 등에서 사용자 입력을 직접 포맷 문자열로 쓰거나 포맷 문자열 생성에 포함하지 않는다. 사용자가 포맷 문자열을 바꿀 수 있는 구조로 쓰지 않는다. `%n`, `%hn`은 쓰지 않는다. 가능하면 `%s`를 지정하고 사용자 입력은 두 번째 이후 인자로 넘긴다.

**2021 원문 예제 요지 (Java·C·C#)**: Java `printf(args[0] + " did not match! ...", validDate)` → `printf("%s did not match! ...", args[0], validDate)`. C `fprintf(stderr, msg)` → `fputs(msg, stderr)`.

#### Python 시큐어코딩 가이드(2023) 원문 — 2장 1절 16항 (p.68~69) ※ Python 가이드에서는 버퍼 오버플로우 항목이 빠져 **16번**이다.

- **Python 관련 설명**: 파이썬의 문자열 포맷팅 방식은 `%` formatting, `str.format`, f-string(3.6+) 세 가지다. 공격자는 포맷 문자열로 **내부 정보를 문자열로 만들 수 있고**, 이를 그대로 쓰면 중요 정보 유출로 이어진다. 예: `{user.__init__.__globals__[AUTHENTICATE_KEY]}` 입력으로 전역 변수 `AUTHENTICATE_KEY` 값을 탈취한다.
- **안전한 코딩기법**: 사용자 입력을 직접 포맷 문자열로 쓰거나 포맷 문자열 생성에 포함하지 않는다. 사용자 데이터를 포맷 문자열로 써야 하면 **서식 지정자를 포함하지 않거나, 파이썬 내장함수·내장변수 등이 포함되지 않도록** 한다.
- **원문 예제**

```python
AUTHENTICATE_KEY = 'Passw0rd'


# [가이드 원문] 안전하지 않은 코드 — 사용자 입력을 포맷 문자열로
def make_user_message(request):
    user_info = get_user_info(request.POST.get('user_id', ''))
    format_string = request.POST.get('msg_format', '')
    message = format_string.format(user=user_info)
    return render(request, '/user_page.html', {'message': message})


# [가이드 원문] 안전한 코드 — 포맷 문자열은 상수, 입력은 바인딩
def make_user_message(request):
    user_info = get_user_info(request.POST.get('user_id', ''))
    message = 'user name is {}'.format(user_info.name)
    return render(request, '/user_page.html', {'message': message})
```

- **검토 메모**: f-string은 소스 코드에 쓰인 리터럴이라 그 자체로는 외부 입력이 포맷 문자열이 될 수 없다. 탐지 대상은 `입력값.format(...)`, `입력값 % ...`, `format_map`이다. 판정 기준은 이 스킬과 같다.

#### 이 스킬의 점검 기준 (2021 가이드 + 실무 기준)

**Python 관점**
- `str.format()`에 **사용자가 만든 포맷 문자열**을 쓰면 `{0.__class__.__init__.__globals__[SECRET_KEY]}` 같은 속성 탐색으로 내부 정보가 노출된다.
- `%` 포맷은 속성 탐색은 안 되지만 `%(name)s`로 딕셔너리 키를 열람할 수 있다.
- `logging`은 메시지와 인자를 분리해야 한다(`logger.info(user_msg)`는 `%` 문자가 있으면 오류·로그 위조 소지).
- `string.Template`은 속성 탐색이 없어 상대적으로 안전하지만, `safe_substitute` 사용을 권한다.

**탐지 패턴 (Python)**
- `입력값.format(`, `입력값.format_map(`, `입력값 % (`, `str.format(입력값, ...)`
- 사용자 정의 메시지 템플릿·알림 템플릿·이메일 템플릿 기능에서 `.format(**context)` 사용
- `logger.*(f"...{입력값}...")`, `logger.*(입력값)` (첫 인자에 외부 입력)

**보충 예제 — 취약 코드**
```python
class Config:
    SECRET_KEY = "s3cr3t"


config = Config()


@app.route("/greet")
def greet():
    template = request.args.get("tpl", "Hello {user.name}")
    # tpl = "{config.__class__.__init__.__globals__}" 등으로 내부 정보 노출
    return template.format(user=current_user, config=config)


logger.info(request.args.get("msg", ""))  # 사용자 입력이 포맷 문자열로 해석됨
```

**보충 예제 — 안전 코드 (권장 기준)**
```python
from string import Template


@app.route("/greet")
def greet():
    # 포맷 문자열은 코드 상수, 사용자 입력은 값으로만 (원문 "%s 지정 + 2번째 인자" 대응)
    return "Hello {}".format(request.args.get("name", ""))


# 사용자 정의 템플릿이 꼭 필요하면 속성 접근이 없는 Template + 허용 키만 제공
def render_user_template(tpl: str, values: dict) -> str:
    allowed = {k: str(v) for k, v in values.items() if k in {"name", "date"}}
    return Template(tpl).safe_substitute(allowed)


# logging은 포맷과 인자를 분리
logger.info("user message: %s", request.args.get("msg", ""))
```

**판정 기준 / 오탐 주의**
- 포맷 문자열이 코드 상수이고 사용자 입력이 **인자**로만 들어가면 안전하다.
- 사용자 템플릿 기능은 SSTI(INP-02)와 함께 본다.
