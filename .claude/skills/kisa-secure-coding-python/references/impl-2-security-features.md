# 구현단계 보안약점 — 제2절 보안기능 (SEC-01 ~ SEC-16)

> 출처
> - KISA·행정안전부 「소프트웨어 개발보안 가이드」(2021.12) 제4장 제2절 — 원문 예제는 Java·C·C#
> - KISA 「Python 시큐어코딩 가이드」(2023 개정본) 2장 제2절 — 원문 예제는 Python(Django·Flask 중심)
>
> 항목마다 다음 순서로 정리했다.
> 1. **KISA 소프트웨어 개발보안 가이드(2021) 원문**: 개요, 보안대책, Java·C·C# 예제 요지
> 2. **Python 시큐어코딩 가이드(2023) 원문**: Python 관련 설명, 안전한 코딩기법, 원문 Python 예제(따옴표·들여쓰기·변수명 오타 등 표기 오류만 정리), **검토 메모**(가이드 예제 자체의 약점, 다른 항목과 충돌하는 부분)
> 3. **이 스킬의 점검 기준**: 탐지 패턴, 보충 예제(2021 원문 취지를 옮기거나 실무 기준으로 보강한 코드), 판정 기준
>
> 심각도(높음/중간/낮음)는 두 가이드 모두에 없는 값으로, 우선순위를 정하기 위해 붙인 것이다.

**정의**: 보안기능(인증, 접근제어, 기밀성, 암호화, 권한관리 등)을 부적절하게 구현할 때 생기는 보안약점. 적절한 인증 없는 중요기능 허용, 부적절한 인가 등이 포함된다.

---

### SEC-01. 적절한 인증 없는 중요기능 허용

| 항목 | 내용 |
|---|---|
| 심각도 | 높음 |
| CWE | CWE-306 |
| 연관 설계항목 | SR2-1 |

#### KISA 소프트웨어 개발보안 가이드(2021) 원문

**개요 (2021 원문)**: 적절한 인증 없이 중요정보(계좌이체 정보, 개인정보 등)를 열람하거나 변경할 수 있는 보안약점이다.

**보안대책 (2021 원문)**: 클라이언트의 보안검사를 우회해 서버에 접근하지 못하도록 설계하고, 중요한 정보가 있는 페이지는 **재인증**을 적용한다(은행 계좌이체 등). 안전하다고 검증된 라이브러리나 프레임워크(OpenSSL, ESAPI 보안기능 등)를 쓴다.

**2021 원문 예제 요지 (Java·C·C#)**: 회원정보 수정(`/modify.do`) 시 수정 요청 사용자와 로그인 사용자의 일치 여부를 확인하지 않음 → 세션의 `userId`와 요청 `userId` 비교 후 일치할 때만 수정. C# `FormsAuthentication.RedirectFromLoginPage`를 자격 검증 없이 호출 → `Membership.ValidateUser` 후 호출.

#### Python 시큐어코딩 가이드(2023) 원문 — 2장 2절 1항 (p.70~72)

- **Python 관련 설명**: Django는 `django.contrib.auth` 앱으로 기본 로그인·로그아웃 인증을 제공하고, DRF는 토큰·세션 인증을 제공한다.
- **안전한 코딩기법**: 클라이언트 보안 검사를 우회해 서버에 접근하지 못하게 설계하고, 중요 정보 페이지는 **재인증**을 적용한다. 검증된 라이브러리·프레임워크(**Django authentication system, Flask-Login** 등)를 쓴다.
- **원문 예제** (비밀번호 변경 시 현재 비밀번호 확인·재확인 절차 누락)

```python
import hashlib
from re import escape

from django.contrib.auth.decorators import login_required


# [가이드 원문] 안전하지 않은 코드 — 현재 비밀번호 확인 없이 변경
def change_password(request):
    new_pwd = request.POST.get('new_password', '')
    user = '%s' % escape(request.session['userid'])
    sha = hashlib.sha256(new_pwd.encode())
    update_password_from_db(user, sha.hexdigest())
    return render(request, '/success.html')


# [가이드 원문] 안전한 코드 — @login_required + 현재 비밀번호 재인증
@login_required
def change_password(request):
    new_pwd = request.POST.get('new_password', '')
    crnt_pwd = request.POST.get('current_password', '')
    user = '%s' % escape(request.session['userid'])
    h_pwd = hashlib.sha256(crnt_pwd.encode()).hexdigest()
    old_pwd = get_password_from_db(user)
    if old_pwd == h_pwd:
        new_h = hashlib.sha256(new_pwd.encode())
        update_password_from_db(user, new_h.hexdigest())
        return render(request, '/success.html')
    return render(request, 'failed.html', {'error': '패스워드가 일치하지 않습니다'})
```

- **검토 메모**: 가이드 안전 예제는 인증·재인증 구조는 맞지만, **비밀번호를 솔트 없는 SHA-256으로 저장**하고(SEC-14 위반), `==`로 비교한다(타이밍). 또 `re.escape`는 정규식용 이스케이프라 여기서 의미가 없다. 이 예제를 그대로 따른 코드는 SEC-01은 충족, **SEC-14는 미충족**으로 판정한다. Django라면 `request.user.check_password()`, `set_password()`, `update_session_auth_hash()`를 쓰도록 권고한다.

#### 이 스킬의 점검 기준 (2021 가이드 + 실무 기준)

**탐지 패턴 (Python)**
- 인증 데코레이터·의존성이 빠진 중요 엔드포인트
  - Flask: `@login_required`(Flask-Login), 커스텀 `@auth_required` 누락. `before_request` 전역 검사 유무 확인
  - Django: `@login_required`, `LoginRequiredMixin`, `@permission_required` 누락. Django 5.1+ `LoginRequiredMiddleware` 사용 여부
  - DRF: `permission_classes = [AllowAny]`, `authentication_classes = []`, 전역 `DEFAULT_PERMISSION_CLASSES`가 `AllowAny`
  - FastAPI: `Depends(get_current_user)` 누락, 라우터 단위 `dependencies` 미설정
- 요청 본문·쿼리의 `user_id`로 대상 사용자를 정하고 세션 사용자와 비교하지 않음 (원문 예제 핵심)
- 자격 검증 없이 로그인 처리: `login_user(User.query.filter_by(username=...).first())` 앞에 비밀번호 검증이 없음
- 비밀번호 변경·이메일 변경·탈퇴·결제·송금에 현재 비밀번호 재확인이 없음
- 디버그·관리용 라우트(`/debug`, `/admin/reset`, `/internal/*`)가 인증 없이 노출

**보충 예제 — 취약 코드**
```python
@app.route("/member/modify", methods=["POST"])
@login_required
def member_modify():
    user_id = request.form["user_id"]  # 요청에서 대상 사용자 지정
    member = Member.query.filter_by(user_id=user_id).first_or_404()
    member.name = request.form["name"]
    member.email = request.form["email"]
    db.session.commit()  # 다른 사람 정보도 수정 가능
    return redirect("/board/list")


@app.route("/login", methods=["POST"])
def login():
    user = User.query.filter_by(username=request.form["username"]).first()
    login_user(user)  # 비밀번호 확인 없음 (원문 C# 예제 대응)
    return redirect("/")
```

**보충 예제 — 안전 코드 (권장 기준)**
```python
@app.route("/member/modify", methods=["POST"])
@login_required
def member_modify():
    # 1. 로그인 사용자를 서버 세션에서 가져온다
    member = current_user
    # 2. 요청 대상이 로그인 사용자와 같은지 확인한다 (원문 대응)
    requested = request.form.get("user_id")
    if requested is not None and requested != member.user_id:
        abort(403)
    # 3. 중요정보 변경은 현재 비밀번호로 재인증
    if not check_password_hash(member.password_hash, request.form.get("old_user_pw", "")):
        abort(403)
    member.name = request.form["name"]
    member.email = request.form["email"]
    db.session.commit()
    return redirect("/board/list")


@app.route("/login", methods=["POST"])
def login():
    user = User.query.filter_by(username=request.form.get("username", "")).first()
    if user is None or not check_password_hash(user.password_hash, request.form.get("password", "")):
        abort(401)
    login_user(user)
    return redirect("/")


# Django REST framework — 기본 차단
REST_FRAMEWORK = {
    "DEFAULT_PERMISSION_CLASSES": ["rest_framework.permissions.IsAuthenticated"],
}

# FastAPI — 라우터 전체에 인증 의존성
router = APIRouter(prefix="/account", dependencies=[Depends(get_current_user)])
```

**판정 기준 / 오탐 주의**
- 공개 의도가 명확한 엔드포인트(로그인, 회원가입, 공지 조회, 헬스체크)는 제외한다.
- 인가(권한·소유자) 누락은 SEC-02로 분리해 보고한다. 이 항목은 "인증 자체가 없거나, 인증 대상 사용자를 요청값으로 바꿀 수 있는 경우"에 집중한다.

---

### SEC-02. 부적절한 인가 (Improper Authorization)

| 항목 | 내용 |
|---|---|
| 심각도 | 높음 |
| CWE | CWE-285 (관련: CWE-639 IDOR, CWE-862) |
| 연관 설계항목 | SR2-4 |

#### KISA 소프트웨어 개발보안 가이드(2021) 원문

**개요 (2021 원문)**: 프로그램이 모든 가능한 실행경로에 대해 접근제어를 검사하지 않거나 불완전하게 검사하면, 공격자는 접근 가능한 실행경로로 정보를 유출할 수 있다.

**보안대책 (2021 원문)**: 정보와 기능을 **역할에 따라 배분**해 공격 노출면(Attack Surface)을 최소화하고, 사용자 권한에 따른 **ACL**을 관리한다. 프레임워크(JAAS Authorization Framework, OWASP ESAPI Access Control 등)를 활용할 수 있다.

**2021 원문 예제 요지 (Java·C·C#)**: `action=delete`이면 권한 확인 없이 `boardDao.delete(contentId)` → 세션 사용자로 `checkAccessControlList(user, action)` 확인 후 삭제. C# 관리자 컨트롤러에 권한 검사 없음 → `[Authorize(Roles = "Administrator")]`. C LDAP 검색 전 사용자 인증·로그인 정보 일치 확인.

#### Python 시큐어코딩 가이드(2023) 원문 — 2장 2절 2항 (p.73~75)

- **안전한 코딩기법**: 정보와 기능을 **역할에 맞게 분리 개발**해 공격 노출면(Attack Surface: 공격자가 진입하거나 영향을 줄 수 있는 시스템 경계·요소·환경)을 최소화하고, 사용자 권한에 따른 ACL을 관리한다.
- **원문 예제**

```python
from django.contrib.auth.decorators import login_required, permission_required


# [가이드 원문] 안전하지 않은 코드 — 권한 확인 없이 삭제
def delete_content(request):
    action = request.POST.get('action', '')
    content_id = request.POST.get('content_id', '')
    if action is not None and action == "delete":
        Content.objects.filter(id=content_id).delete()
        return render(request, '/success.html')
    return render(request, '/error.html', {'error': '접근 권한이 없습니다.'})


# [가이드 원문] 안전한 코드 — 로그인 + 권한 확인 데코레이터
@login_required
@permission_required('content.delete', raise_exception=True)
def delete_content(request):
    action = request.POST.get('action', '')
    content_id = request.POST.get('content_id', '')
    if action is not None and action == "delete":
        Content.objects.filter(id=content_id).delete()
        return render(request, '/success.html')
    return render(request, '/error.html', {'error': '삭제 실패'})
```

- **검토 메모**: `@permission_required`는 **기능 단위 권한**만 확인한다. 삭제 권한이 있는 일반 사용자가 남의 글을 지우는 문제(객체 단위 인가, IDOR)는 여전히 남으므로, 작성자 확인(`filter(id=..., author=request.user)`)이나 객체 권한을 함께 확인한다. Django 권한 코드명은 보통 `'앱라벨.delete_모델명'` 형식이므로 실제 존재하는 권한인지도 확인한다.

#### 이 스킬의 점검 기준 (2021 가이드 + 실무 기준)

**탐지 패턴 (Python)**
- **IDOR**: `Model.query.get(id)`, `get_object_or_404(Model, pk=pk)`, `Model.objects.get(id=...)`, `session.get(Model, id)` 결과를 소유자·권한 확인 없이 반환·수정·삭제
- 쿼리에 소유자 조건이 없음: `.filter(owner=request.user)`, `.filter_by(user_id=current_user.id)` 누락
- DRF: `get_queryset()`이 전체 반환, `has_object_permission` 미구현, `ModelViewSet`에 `permission_classes` 누락
- 역할 검사 누락: 관리자 기능 라우트에 `@admin_required`/`is_staff`/`has_perm` 검사가 없음
- 화면에서만 버튼 숨김(템플릿 `{% if user.is_admin %}`)하고 서버 핸들러는 검사하지 않음
- 대량 할당(Mass Assignment): `Model(**request.json)`, `obj.__dict__.update(request.json)`, `for k, v in data.items(): setattr(obj, k, v)` 로 `is_admin`, `role`, `owner_id` 같은 필드까지 변경 가능
- Django admin `has_*_permission` 오버라이드가 `True` 반환

**보충 예제 — 취약 코드**
```python
@app.route("/board/delete", methods=["POST"])
@login_required
def board_delete():
    if request.form.get("action") == "delete":
        Board.query.filter_by(id=request.form["content_id"]).delete()  # 작성자·권한 확인 없음
        db.session.commit()
    return redirect("/board")


@app.route("/api/orders/<int:order_id>")
@login_required
def order_detail(order_id):
    return jsonify(Order.query.get_or_404(order_id).to_dict())  # 남의 주문도 조회 (IDOR)


@app.route("/api/profile", methods=["PATCH"])
@login_required
def profile_update():
    for k, v in request.json.items():
        setattr(current_user, k, v)  # {"is_admin": true} 로 권한 상승
    db.session.commit()
    return "ok"
```

**보충 예제 — 안전 코드 (권장 기준)**
```python
@app.route("/board/delete", methods=["POST"])
@login_required
def board_delete():
    post = Board.query.get_or_404(request.form["content_id"])
    # 세션 사용자 정보로 권한(ACL) 확인 후 수행 (원문 checkAccessControlList 대응)
    if not (post.author_id == current_user.id or current_user.has_permission("board.delete")):
        abort(403)
    db.session.delete(post)
    db.session.commit()
    return redirect("/board")


@app.route("/api/orders/<int:order_id>")
@login_required
def order_detail(order_id):
    order = Order.query.filter_by(id=order_id, user_id=current_user.id).first_or_404()
    return jsonify(order.to_dict())


EDITABLE_FIELDS = {"nickname", "bio"}


@app.route("/api/profile", methods=["PATCH"])
@login_required
def profile_update():
    for k, v in request.json.items():
        if k in EDITABLE_FIELDS:  # 허용 필드만 변경
            setattr(current_user, k, v)
    db.session.commit()
    return "ok"


# DRF — 객체 수준 권한 + 쿼리셋 범위 제한
class IsOwner(permissions.BasePermission):
    def has_object_permission(self, request, view, obj):
        return obj.owner_id == request.user.id


class OrderViewSet(viewsets.ModelViewSet):
    serializer_class = OrderSerializer
    permission_classes = [permissions.IsAuthenticated, IsOwner]

    def get_queryset(self):
        return Order.objects.filter(owner=self.request.user)
```

**판정 기준 / 오탐 주의**
- 목록 API와 상세 API를 모두 확인한다. 목록은 필터링되는데 상세·수정·삭제가 빠지는 경우가 많다.
- 순차 정수 ID 자체는 취약점이 아니다. 인가 검사가 있으면 충족이다(UUID 사용은 보조 수단으로 제안).

---

### SEC-03. 중요한 자원에 대한 잘못된 권한 설정

| 항목 | 내용 |
|---|---|
| 심각도 | 중간 |
| CWE | CWE-732 |
| 연관 설계항목 | SR2-4 |

#### KISA 소프트웨어 개발보안 가이드(2021) 원문

**개요 (2021 원문)**: SW가 중요한 보안 관련 자원에 읽기·수정 권한을 의도하지 않게 허가하면, 권한이 없는 사용자가 그 자원을 쓰게 된다.

**보안대책 (2021 원문)**: 설정파일, 실행파일, 라이브러리 등은 **SW 관리자만** 읽고 쓸 수 있게 설정하고, 중요한 자원을 쓸 때 허가받지 않은 사용자가 접근할 수 있는지 검사한다.

**2021 원문 예제 요지 (Java·C·C#)**: Java `setExecutable(true,false)`, `setReadable(true,false)`, `setWritable(true,false)`(모든 사용자) → 소유자만 읽기. C# `everyone`에 `FullControl` → 특정 계정·권한만. C `umask(0)` → `umask(077)`.

#### Python 시큐어코딩 가이드(2023) 원문 — 2장 2절 3항 (p.76~77)

- **Python 관련 설명**: 파이썬에서는 `os.fchmod`, `os.chmod` 등으로 파일 생성·수정·읽기 권한을 설정한다.
- **안전한 코딩기법**: 설정 파일·실행 파일·라이브러리는 관리자만 읽고 쓰게 하고, 중요 자원 사용 시 허가받지 않은 사용자가 접근할 수 있는지 검사한다. **파일 소유자라도 기본적으로 읽기 권한만** 주고, 쓰기 권한은 부득이할 때만 제한적으로 준다.
- **원문 예제**

```python
import os


# [가이드 원문] 안전하지 않은 코드 — 모든 사용자 rwx
def write_file():
    os.chmod('/root/system_config', 0o777)
    with open("/root/system_config", 'w') as f:
        f.write("your config is broken")


# [가이드 원문] 안전한 코드 — 소유자 외 권한 없음
def write_file():
    os.chmod('/root/system_config', 0o700)
    with open("/root/system_config", 'w') as f:
        f.write("your config is broken")
```

- **검토 메모**: 가이드 본문은 "소유자도 기본 읽기만"이라고 하지만 예제는 `0o700`(소유자 rwx)이다. 설정 파일이면 `0o600`(쓰기 필요 시) 또는 `0o400`을 기준으로 권고한다. 탐지 패턴에 `os.fchmod`도 포함한다.

#### 이 스킬의 점검 기준 (2021 가이드 + 실무 기준)

**탐지 패턴 (Python)**
- `os.chmod(path, 0o777|0o666|0o775|0o766|...)` — 기타 사용자(other) 쓰기·읽기 비트
- `os.umask(0)`, `os.umask(0o000)`, `os.umask(0o002)`
- `os.makedirs(path, mode=0o777)`, `os.mkdir(path, 0o777)`, `Path.mkdir(mode=0o777)`, `Path.touch(mode=0o666)`, `os.open(path, flags, 0o666)`
- `stat.S_IRWXO`, `stat.S_IWOTH`, `stat.S_IROTH` 사용
- `tempfile.mktemp()`(경쟁조건, 권한) — `mkstemp`/`NamedTemporaryFile` 권장
- 비밀 파일(키, `.env`, 인증서 개인키, SQLite DB, 로그)을 기본 권한으로 생성
- Dockerfile에서 `chmod -R 777`, 컨테이너를 root로 실행, 클라우드 스토리지 공개 ACL(`ACL="public-read"`, `blob public access`)

**보충 예제 — 취약 코드**
```python
import os

CONFIG = "/home/setup/system.ini"

os.umask(0)  # 이후 생성 파일이 모든 사용자 읽기/쓰기
with open(CONFIG, "w") as f:
    f.write(config_text)
os.chmod(CONFIG, 0o777)  # 모든 사용자 rwx (원문 setExecutable/Readable/Writable(true,false) 대응)

s3.put_object(Bucket="app-private", Key="backup.sql", Body=data, ACL="public-read")
```

**보충 예제 — 안전 코드 (권장 기준)**
```python
import os
import stat
import tempfile

CONFIG = "/home/setup/system.ini"

os.umask(0o077)  # 소유자 외 권한 없음 (원문 umask(077) 대응)

# 생성 시점부터 0o600으로 열기 (생성 후 chmod 사이의 경쟁 구간 제거)
fd = os.open(CONFIG, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
with os.fdopen(fd, "w") as f:
    f.write(config_text)
os.chmod(CONFIG, stat.S_IRUSR)  # 소유자 읽기 전용 (원문: 실행X, 읽기O, 쓰기X)

# 임시 파일은 안전한 API
with tempfile.NamedTemporaryFile("w", delete=True) as tmp:  # 기본 0o600
    tmp.write("...")

s3.put_object(Bucket="app-private", Key="backup.sql", Body=data)  # 기본 private
```

**판정 기준 / 오탐 주의**
- 공개 정적 파일(`static/`)의 `0o644`는 정상이다. **비밀·설정·업로드·DB 파일**인지 기준으로 판단한다.
- 디렉토리의 실행 비트(`0o755`)는 탐색 권한이므로, 쓰기 비트(other `w`)를 우선 확인한다.

---

### SEC-04. 취약한 암호화 알고리즘 사용

| 항목 | 내용 |
|---|---|
| 심각도 | 높음 |
| CWE | CWE-327, CWE-328 |
| 연관 설계항목 | SR2-6 |

#### KISA 소프트웨어 개발보안 가이드(2021) 원문

**개요 (2021 원문)**: 개발자가 설정파일의 패스워드를 감추려고 간단한 인코딩 함수를 쓰기도 하지만, **base64** 같은 인코딩으로는 패스워드를 보호할 수 없다. 취약하거나 위험한 암호 알고리즘을 쓰면 안 되며, 표준화되지 않은 알고리즘은 분석·무력화될 가능성이 높다. 오래된 알고리즘은 컴퓨터 성능 향상으로 며칠·몇 시간 만에 해독되기도 한다. **RC2, RC4, RC5, RC6, MD4, MD5, SHA1, DES** 가 여기에 해당한다.

**보안대책 (2021 원문)**: 자체 암호 알고리즘을 개발하지 말고 검증된 표준 알고리즘을 쓴다. DES, RC5 등 대신 **3DES, AES, SEED** 등 안전한 알고리즘으로 대체한다. 업무 관련 내용·개인정보에는 IT보안인증사무국이 안전성을 확인한 **검증필 암호모듈**을 써야 한다.

**원문 참고표: 안전한 암호알고리즘 및 키 길이**

| 분류 | | 보호함수 목록 |
|---|---|---|
| 최소 안전성 수준 | | 112비트 |
| 블록암호 | | ARIA(키 길이 128/192/256), SEED(키 길이 128) |
| 블록암호 운영모드 | 기밀성 | ECB(원문 표기 "ECD"), CBC, CFB, OFB, CTR |
| | 기밀성/인증 | CCM, GCM |
| 해쉬함수 | | SHA-224/256/384/512 |
| 메시지 인증코드 | 해쉬함수 기반 | HMAC |
| | 블록 기반 | CMAC, GMAC |
| 난수발생기 | 해쉬함수/HMAC 기반 | HASH_DRBG, HMAC_DRBG |
| | 블록 기반 | CTR_DRBG |
| 공개키 암호 | | RSAES (공개키 길이 2048, 3072 / RSA-OAEP 해쉬함수 SHA-224/256) |
| 전자서명 | | RSA-PSS, KCDSA, ECDSA, EC-KCDSA |
| 키 설정 방식 | | DH, ECDH |
| 시스템 파라미터 | RSA-PSS | 공개키 길이 2048, 3072 |
| | KCDSA, DH | (공개키 길이, 개인키 길이) = (2048, 224), (2048, 256) |
| | ECDSA, EC-KCDSA, ECDH | (FIPS) B-233, B-283 / K-233, K-283 / P-224, P-256 |

> 표는 검증필 암호모듈(KCMVP) 기준 목록이라 블록암호에 AES가 없다. 본문은 AES를 안전한 알고리즘으로 명시한다. ECB 모드는 목록에 있으나, 같은 평문 블록이 같은 암호문이 되어 패턴이 드러나므로 실무에서는 GCM(인증 암호) 또는 CBC+HMAC을 쓴다.

**2021 원문 예제 요지 (Java·C·C#)**: Java `Cipher.getInstance("DES")` → `"AES/CBC/PKCS5Padding"`. C# `DESCryptoServiceProvider` → `AesCryptoServiceProvider`. C `EVP_des_ecb()` → `EVP_aes_128_cbc()`.

#### Python 시큐어코딩 가이드(2023) 원문 — 2장 2절 4항 (p.78~81)

- **Python 관련 설명**: 취약 알고리즘은 RC2(**ARC2**), RC4(**ARC4**), RC5, RC6, MD4, MD5, SHA1, DES이며, 예제 설명에서 **2TDEA, Blowfish**도 사용 금지로 든다. 파이썬 2.x에서 쓰던 **PyCrypto는 3.x에서 동작하지 않는 경우가 있고 더 이상 유지되지 않으므로(deprecated) 개선판인 `pycryptodome`을 써야** 한다. 대안 라이브러리로 `pyca/cryptography`도 참고자료에 있다.
- **안전한 코딩기법**: 자체 암호 알고리즘을 만들지 말고, DES·RC5 대신 **3TDEA, AES, SEED** 등 안전한 알고리즘을 쓴다. **ECB 모드**는 한 블록이 해독되면 나머지도 해독되는 단점이 있고, **CBC 모드**는 이전 암호문과 XOR하므로 같은 평문도 다른 암호문이 되어 더 안전하다.
- **암호알고리즘 검증기준 ver3.0 (암호모듈시험기관)** — 2021 가이드 표보다 세분화

| 분류 | 알고리즘 | 조건 |
|---|---|---|
| 최소 안전성 수준 | — | 112비트 |
| 블록암호 | ARIA, SEED, LEA | 기밀성(ECB, CBC, CFB, OFB, CTR), 기밀성/인증(CCM, GCM) |
| | HIGHT | 기밀성(ECB, CBC, CFB, OFB, CTR) |
| 해시함수 | SHA-2 | SHA-224/256/384/512 |
| | LSH | LSH-224/256/384/512/512-224/512-256 |
| | SHA-3 | SHA-3-224/256/384/512 |
| 메시지 인증 | 해시함수 기반 / 블록암호 기반 | HMAC / CMAC, GMAC |
| 난수발생기 | 해시함수 기반 / 블록암호 기반 | Hash_DRBG, HMAC_DRBG / CTR_DRBG |
| 공개키 암호 | RSAES | 공개키 2048, 3072 / 해시 SHA-224, SHA-256 |
| 전자서명 | RSA-PSS | 공개키 2048, 3072 / 해시 SHA-224, SHA-256 |
| | KCDSA | (공개키, 개인키) = (2048, 224), (2048, 256) / 해시 SHA-224, SHA-256 |
| | EC-KCDSA, ECDSA | P-224, P-256, B-233, B-283, K-233, K-283 / 해시 SHA-224, SHA-256 |
| 키 설정 | DH | (공개키, 개인키) = (2048, 224), (2048, 256) |
| | ECDH | P-224, P-256, B-233, B-283, K-233, K-283 |
| 키 유도 | KBKDF | HMAC, CMAC |
| | PBKDF | HMAC |

- **원문 예제**

```python
import base64
import hashlib

from Crypto.Cipher import AES, DES
from Crypto.Util.Padding import pad


# [가이드 원문] 안전하지 않은 코드 — DES/ECB (원문의 변수명 오타 cipher_aes를 바로잡음)
def get_enc_text(plain_text, key):
    cipher_des = DES.new(key, DES.MODE_ECB)
    encrypted_data = base64.b64encode(cipher_des.encrypt(pad(plain_text, 32)))
    return encrypted_data.decode('ASCII')


# [가이드 원문] 안전한 코드 — AES/CBC (pycryptodome)
def get_enc_text(plain_text, key, iv):
    cipher_aes = AES.new(key, AES.MODE_CBC, iv)
    encrypted_data = base64.b64encode(cipher_aes.encrypt(pad(plain_text, 32)))
    return encrypted_data.decode('ASCII')


# [가이드 원문] 안전하지 않은 코드 / 안전한 코드 — 해시
def make_md5(plain_text):
    return hashlib.md5(plain_text.encode('utf-8')).hexdigest()


def make_sha256(plain_text):
    return hashlib.sha256(plain_text.encode('utf-8')).hexdigest()
```

- **검토 메모**
  - AES-CBC 예제는 **무결성(인증)이 없어** 패딩 오라클·변조 공격에 노출될 수 있고, IV를 호출자가 넘기므로 **IV 재사용** 여부를 확인해야 한다. 이 스킬은 AES-GCM 또는 CBC+HMAC(Fernet)을 권고 기준으로 둔다. 표에서도 기밀성/인증 모드로 CCM·GCM을 별도로 둔다.
  - `make_sha256` 예제는 일반 해시 용도다. **비밀번호 저장에 쓰면 SEC-14 위반**이다.
  - 탐지 패턴: `from Crypto` 사용 시 의존성이 `pycrypto`인지 `pycryptodome`인지 확인한다.

#### 이 스킬의 점검 기준 (2021 가이드 + 실무 기준)

**탐지 패턴 (Python)**
- 해시: `hashlib.md5(`, `hashlib.sha1(`, `hashlib.new("md5"|"sha1"|"md4")`, `Crypto.Hash.MD5`, `Crypto.Hash.SHA1`, `cryptography.hazmat.primitives.hashes.MD5()`/`SHA1()` — **보안 용도(비밀번호, 서명, 무결성, 토큰)일 때**
- 대칭키: `Crypto.Cipher.DES`, `DES3`(신규 사용), `ARC2`, `ARC4`, `Blowfish`, `algorithms.TripleDES`, `algorithms.Blowfish`, `algorithms.ARC4`, `algorithms.CAST5`, `algorithms.IDEA`
- 모드: `AES.MODE_ECB`, `modes.ECB()`
- 인코딩·난독화를 암호화로 오용: `base64.b64encode(password)`, `codecs.encode(s, "rot13")`, XOR 직접 구현
- 자체 구현 암호(직접 만든 치환·XOR·시프트 함수)
- 구식 라이브러리: `pycrypto`(`from Crypto` + requirements에 `pycrypto`) — 유지보수 종료
- TLS: `ssl.PROTOCOL_SSLv2/3`, `PROTOCOL_TLSv1`, `PROTOCOL_TLSv1_1`, `set_ciphers("...RC4...|...DES...|NULL|EXPORT")`
- JWT: `HS256` 키가 짧음, `algorithms=["none"]`
- 비밀번호 해시: Django `PASSWORD_HASHERS`에 `MD5PasswordHasher`, `SHA1PasswordHasher`, `UnsaltedMD5PasswordHasher`

**보충 예제 — 취약 코드**
```python
import base64
import hashlib

from Crypto.Cipher import DES

# 설정 파일 비밀번호를 base64로 '암호화'
stored = base64.b64encode(db_password.encode()).decode()

# DES/ECB 암호화 (원문 Cipher.getInstance("DES") 대응)
cipher = DES.new(key8, DES.MODE_ECB)
enc = cipher.encrypt(pad(msg, 8))

# 무결성 확인에 MD5
digest = hashlib.md5(file_bytes).hexdigest()
```

**보충 예제 — 안전 코드 (권장 기준)**
```python
import hashlib
import os

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

# AES-256-GCM (기밀성 + 무결성). nonce는 키마다 절대 재사용 금지
key = AESGCM.generate_key(bit_length=256)  # 키는 KMS/시크릿 매니저에 보관
aesgcm = AESGCM(key)
nonce = os.urandom(12)
ciphertext = aesgcm.encrypt(nonce, msg, associated_data=None)
plaintext = aesgcm.decrypt(nonce, ciphertext, associated_data=None)

# 간단히 쓰려면 Fernet (AES-128-CBC + HMAC-SHA256)
from cryptography.fernet import Fernet

f = Fernet(Fernet.generate_key())
token = f.encrypt(b"secret")

# 무결성 확인은 SHA-256 이상
digest = hashlib.sha256(file_bytes).hexdigest()

# 국내 검증필 알고리즘이 요구되면 SEED/ARIA 지원 모듈 사용
# (예: cryptography는 SEED-CBC 지원, ARIA는 OpenSSL 1.1.1+ 바인딩 필요) — 공공 사업은 KCMVP 검증필 모듈 확인
```

**판정 기준 / 오탐 주의**
- MD5/SHA1을 **비보안 용도**(캐시 키, ETag, 중복 검사 식별자)로 쓰면 위험도가 낮다. Python 3.9+ `hashlib.md5(data, usedforsecurity=False)`로 의도를 명시했는지 본다.
- 레거시 데이터 복호화를 위한 읽기 전용 경로라면 "마이그레이션 필요"로 보고한다.

---

### SEC-05. 암호화되지 않은 중요정보

| 항목 | 내용 |
|---|---|
| 심각도 | 높음 |
| CWE | CWE-312 (평문 저장), CWE-319 (평문 전송) |
| 연관 설계항목 | SR2-7, SR2-8 |

#### KISA 소프트웨어 개발보안 가이드(2021) 원문

**개요 (2021 원문)**: 사용자나 시스템의 중요정보가 포함된 데이터를 평문으로 송·수신하거나 저장하면 인가되지 않은 사용자에게 노출될 수 있다.

**보안대책 (2021 원문)**: 개인정보(주민등록번호, 여권번호 등), 금융정보(카드번호, 계좌번호 등), 패스워드 등 중요정보는 전송·저장 시 반드시 암호화한다. 필요하면 SSL·HTTPS 같은 암호채널을 쓰고, HTTPS 같은 보안 채널로 브라우저 쿠키에 중요 데이터를 저장할 때는 쿠키 객체에 **보안속성(Secure)**을 반드시 설정한다. 중요정보를 읽거나 쓸 때는 권한인증 등으로 적합한 사용자만 접근하게 한다.

**2021 원문 예제 요지 (Java·C·C#)**
- 평문 저장: 패스워드를 그대로 `INSERT` → 솔트 + SHA-256 해쉬로 저장. C# 저장된 패스워드를 `GetPassword()`로 꺼내 화면 출력 → 출력 금지.
- 평문 전송: `Socket`으로 패스워드 그대로 전송 → AES로 암호화 후 전송. C# 패스워드를 이메일로 발송 → 해시 처리(원문). C 설정파일 비밀번호를 그대로 DB 연결에 사용 → 환경변수의 키로 AES-CBC 처리.

#### Python 시큐어코딩 가이드(2023) 원문 — 2장 2절 5항 (p.82~85)

- **안전한 코딩기법**: 개인정보(주민등록번호, 여권번호 등)·금융정보(카드번호, 계좌번호 등)·패스워드는 저장·전송 시 반드시 암호화하고, 읽기·쓰기 시 권한인증으로 적합한 사용자만 접근하게 한다. 가능하면 SSL/HTTPS 같은 보안 채널을 쓴다. 보안 채널 없이 쿠키에 중요 데이터를 저장하면 **쿠키 보안속성(`secure=True`)**을 설정한다.
- **원문 예제**

```python
import base64
import hashlib
import os
import socket

from Crypto import Random
from Crypto.Cipher import AES
from Crypto.Hash import SHA256


# [가이드 원문] 안전하지 않은 코드 — 평문 비밀번호 저장
def update_pass(dbconn, password, user_id):
    curs = dbconn.cursor()
    curs.execute('UPDATE USERS SET PASSWORD=%s WHERE USER_ID=%s', (password, user_id))
    dbconn.commit()


# [가이드 원문] 안전한 코드 — SHA-256 + salt 단방향 해시
def update_pass(dbconn, password, user_id, salt):
    hash_obj = SHA256.new()
    hash_obj.update(bytes(password + salt, 'utf-8'))
    hash_pwd = hash_obj.hexdigest()
    curs = dbconn.cursor()
    curs.execute('UPDATE USERS SET PASSWORD=%s WHERE USER_ID=%s', (hash_pwd, user_id))
    dbconn.commit()


HOST = '127.0.0.1'
PORT = 65434


# [가이드 원문] 안전하지 않은 코드 — 평문 전송
def send_password(password):
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.connect((HOST, PORT))
        s.sendall(password.encode('utf-8'))


# [가이드 원문] 안전한 코드 — 환경변수의 키로 AES-CBC 암호화 후 전송
class AEScipher:
    BS = AES.block_size

    def __init__(self, s_key):
        self.s_key = hashlib.sha256(s_key.encode("utf-8")).digest()

    def pad(self, m):
        return m + bytes([self.BS - len(m) % self.BS] * (self.BS - len(m) % self.BS))

    def encrypt(self, plain):
        plain = self.pad(plain.encode())
        iv = Random.new().read(AES.block_size)
        cipher = AES.new(self.s_key, AES.MODE_CBC, iv)
        return base64.b64encode(iv + cipher.encrypt(plain)).decode("utf-8")


def send_password(password):
    block_key = os.environ.get('BLOCK_KEY')
    aes = AEScipher(block_key)
    enc_password = aes.encrypt(password)
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.connect((HOST, PORT))
        s.sendall(enc_password.encode('utf-8'))
```

- **검토 메모**
  - 평문 저장 안전 예제는 2021 가이드와 같은 **솔트 + SHA-256(빠른 해시)** 방식이다. KISA 기준 "충족"이지만 이 스킬은 Argon2/bcrypt/PBKDF2(충분한 반복)를 권고 기준으로 두고 "부분충족 + 업그레이드 권고"로 보고한다(SEC-14 동일).
  - 평문 전송 안전 예제는 직접 만든 AES-CBC 암호화(무결성 없음, 키를 SHA-256으로 유도)를 쓴다. 실무 권고는 **TLS(`ssl.create_default_context().wrap_socket`) 사용**이다. 자체 프로토콜 암호화는 SEC-04 관점에서 추가 검토한다.
  - 가이드 원문 안전하지 않은 예제의 `execute(sql, password, user_id)`는 인자 전달 방식이 잘못되어 있어 위에서 튜플로 바로잡았다.

#### 이 스킬의 점검 기준 (2021 가이드 + 실무 기준)

**탐지 패턴 (Python)**
- 평문 저장
  - 비밀번호 컬럼에 원문 저장: `User(password=request.form["password"])`, `password = db.Column(db.String)` + 해시 함수 미호출
  - 주민등록번호·카드번호·계좌번호 등 컬럼이 평문 `CharField`/`String`
  - 로그에 민감정보: `logger.info(f"login {username} {password}")`, `print(request.form)`, `logger.debug(request.json)`
  - 파일·캐시(Redis)·세션에 평문 저장, `pickle`로 디스크 저장
  - 비밀번호를 복호화 가능한 형태로 저장하거나, 이메일로 원래 비밀번호 발송
- 평문 전송
  - `http://` URL로 외부 API·내부 서비스 호출에 토큰·개인정보 전송
  - `smtplib.SMTP(...)` 후 `starttls()` 없이 `login()`, `ftplib.FTP`, `telnetlib`, 평문 `socket.send(password)`
  - DB 연결 `sslmode=disable`, Redis/Mongo TLS 미사용 (외부망 연결 시)
  - Django `SECURE_SSL_REDIRECT=False`, `SESSION_COOKIE_SECURE=False`, `CSRF_COOKIE_SECURE=False`, `SECURE_HSTS_SECONDS=0`
  - `set_cookie(...)`에 `secure=True` 누락

**보충 예제 — 취약 코드**
```python
@app.route("/join", methods=["POST"])
def join():
    db.execute(
        "INSERT INTO customer(id, pwd, name, ssn) VALUES (?, ?, ?, ?)",
        (request.form["id"], request.form["pwd"], request.form["name"], request.form["ssn"]),
    )  # 비밀번호·주민번호 평문 저장
    logger.info("join: %s", request.form.to_dict())  # 로그에 평문 기록


import smtplib

with smtplib.SMTP("mail.example.com", 25) as s:
    s.login(user, password)  # 평문 전송
    s.sendmail(sender, [to], f"Your password is: {user_password}")  # 비밀번호 메일 발송

requests.post("http://api.partner.example.com/v1/users", json={"ssn": ssn})
```

**보충 예제 — 안전 코드 (권장 기준)**
```python
from argon2 import PasswordHasher
from cryptography.fernet import Fernet

ph = PasswordHasher()  # Argon2id, 솔트 자동 생성·포함
field_cipher = Fernet(os.environ["FIELD_ENC_KEY"])  # 키는 시크릿 매니저에서 주입


@app.route("/join", methods=["POST"])
def join():
    db.execute(
        "INSERT INTO customer(id, pwd, name, ssn_enc) VALUES (?, ?, ?, ?)",
        (
            request.form["id"],
            ph.hash(request.form["pwd"]),                          # 비밀번호: 일방향 해시
            request.form["name"],
            field_cipher.encrypt(request.form["ssn"].encode()),   # 주민번호: 양방향 암호화
        ),
    )
    logger.info("join: id=%s", request.form["id"])  # 민감정보 제외


import smtplib
import ssl

ctx = ssl.create_default_context()
with smtplib.SMTP("mail.example.com", 587) as s:
    s.starttls(context=ctx)
    s.login(user, password)
    # 비밀번호 대신 1회용 재설정 링크 발송
    s.sendmail(sender, [to], f"Reset link: https://example.com/reset/{reset_token}")

requests.post("https://api.partner.example.com/v1/users", json={"ssn": ssn}, timeout=10)

# Django 운영 설정
SECURE_SSL_REDIRECT = True
SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True
SECURE_HSTS_SECONDS = 31536000
```

**판정 기준 / 오탐 주의**
- 원문 C# 안전 예제는 해시값을 메일로 보내는데, 이는 사용자에게 의미가 없다. Python 판정에서는 **비밀번호를 메일로 보내지 않고 재설정 링크를 보내는 방식**을 기준으로 삼는다.
- 내부 네트워크 통신이라도 개인정보·인증정보가 오가면 암호화를 권고한다 (원문 SR2-8).
- 비밀번호 해시 상세는 SEC-14, 키 관리는 SEC-06과 연결한다.

---

### SEC-06. 하드코드된 중요정보

| 항목 | 내용 |
|---|---|
| 심각도 | 높음 |
| CWE | CWE-259 (비밀번호), CWE-321 (암호화 키), CWE-798 |
| 연관 설계항목 | SR2-3, SR2-5 |

#### KISA 소프트웨어 개발보안 가이드(2021) 원문

**개요 (2021 원문)**: 코드 내부에 하드코드된 패스워드나 암호화 키로 내부 인증이나 암호화를 수행하면 중요정보(관리자 정보, 암호화된 정보 등)가 유출될 수 있다.

**보안대책 (2021 원문)**: 패스워드는 암호화해 **별도 파일에 저장**해서 쓴다. 중요정보를 암호화할 때는 상수가 아닌 암호화 키를 쓰고, 소스코드 내부에 상수 형태의 암호화 키를 저장하지 않는다.

**2021 원문 예제 요지 (Java·C·C#)**
- 하드코드된 비밀번호: Java `private static final String PASS = "SCOTT"` → 프로퍼티의 암호화된 패스워드를 복호화해 사용. C# `NetworkCredential(UserName, "password")` → `SecureString`. C `char *password = "password"` → `getenv("password")`.
- 하드코드된 암호화 키: Java `String key = "22df3023sf~2;asn!@#/>as"` → 외부 파일에 암호화 보관 후 복호화. C# `byte[] key = {0x43, ...}` → 외부 파일. C `crypt(passwd, "salt")` 후 하드코드된 해시와 비교 → 환경변수의 해시·솔트 사용.

#### Python 시큐어코딩 가이드(2023) 원문 — 2장 2절 6항 (p.86~88)

- **Python 관련 설명**: 하드코드된 패스워드로 내부 인증·외부 통신을 하면 관리자 정보가 노출된다. 하드코드된 암호화 키는 암호화된 정보 유출 가능성을 높인다. **암호키의 해시를 계산해 저장하더라도 역계산이 가능해 무차별 대입 공격에는 취약할 수 있다.**
- **안전한 코딩기법**: 패스워드는 암호화 후 별도 파일에 저장해 쓴다. 상수가 아닌 암호화 키를 쓰고, 암호화가 잘 되었더라도 **소스코드에 상수 형태의 암호화 키를 주석으로 달거나 저장하지 않는다.**
- **원문 예제**

```python
import json

import pymysql


# [가이드 원문] 안전하지 않은 코드 — DB 계정 하드코딩
def query_execute(query):
    dbconn = pymysql.connect(host='127.0.0.1', port=1234, user='root', passwd='1234',
                             db='mydb', charset='utf8')
    curs = dbconn.cursor()
    curs.execute(query)
    dbconn.commit()
    dbconn.close()


# [가이드 원문] 안전한 코드 — 설정 파일의 암호화된 값을 복호화해 사용
def query_execute(query, config_path):
    with open(config_path, 'r') as config:
        dbconf = json.load(fp=config)
        block_key = get_decrypt_key(dbconf['blockKey'])   # 암호화된 블록키를 복호화하는 사용자 정의 함수
        db_user = decrypt(block_key, dbconf['user'])
        db_passwd = decrypt(block_key, dbconf['passwd'])
    dbconn = pymysql.connect(host=dbconf['host'], port=dbconf['port'], user=db_user,
                             passwd=db_passwd, db=dbconf['db_name'], charset='utf8')
    curs = dbconn.cursor()
    curs.execute(query)
    dbconn.commit()
    dbconn.close()
```

- **검토 메모**: 가이드 방식에서도 `get_decrypt_key`가 쓰는 **마스터키의 위치**가 핵심이다. 마스터키가 코드에 있으면 여전히 취약으로 판정한다. 환경변수·시크릿 매니저 주입 방식도 충족으로 본다(INP-05 안전 예제에서 가이드도 `os.environ.get('BLOCK_KEY')` 사용). 설정 파일은 `.gitignore`에 포함되었는지 확인한다.

#### 이 스킬의 점검 기준 (2021 가이드 + 실무 기준)

**탐지 패턴 (Python)**
- 이름 기반: `(password|passwd|pwd|secret|secret_key|api_key|apikey|access_key|private_key|token|auth|credential|conn_str|dsn)\s*=\s*["'][^"']+["']`
- 설정: Django `SECRET_KEY = "..."`(특히 `django-insecure-` 접두사), Flask `app.secret_key = "..."`, `app.config["SECRET_KEY"] = "..."`, `JWT_SECRET_KEY = "..."`
- 연결 문자열: `"postgresql://user:pass@host/db"`, `"mysql+pymysql://root:1234@..."`, `mongodb://user:pass@`, `redis://:pass@`
- 함수 인자: `pymysql.connect(password="...")`, `psycopg2.connect(..., password="...")`, `create_engine("...:pass@...")`, `boto3.client(aws_access_key_id="AKIA...", aws_secret_access_key="...")`, `jwt.encode(payload, "secret")`, `Fernet(b"...")`, `AES.new(b"0123456789abcdef", ...)`, `hmac.new(b"key", ...)`
- 알려진 키 형식: `AKIA[0-9A-Z]{16}`, `-----BEGIN (RSA |EC |OPENSSH )?PRIVATE KEY-----`, `ghp_[A-Za-z0-9]{36}`, `xox[baprs]-`, `sk_live_`, `AIza[0-9A-Za-z_-]{35}`
- 고정 IV/nonce/salt: `iv = b"\x00" * 16`, `salt = b"salt"`
- 저장소에 포함된 비밀 파일: `.env`, `config.ini`, `settings_local.py`, `credentials.json`, `*.pem`, `*.key`, `id_rsa` (`.gitignore` 확인)
- 테스트 코드·예제·Docker/CI 파일(`docker-compose.yml`의 `environment:`, `.github/workflows/*.yml`)도 확인

**보충 예제 — 취약 코드**
```python
# settings.py
SECRET_KEY = "django-insecure-3k@x!9z..."
DATABASES = {"default": {"ENGINE": "django.db.backends.mysql", "USER": "scott", "PASSWORD": "tiger"}}

# 암호화 키 하드코딩 (원문 key = "22df3023sf~2;asn!@#/>as" 대응)
KEY = b"22df3023sf~2;asn"
cipher = AES.new(KEY, AES.MODE_GCM)

engine = create_engine("postgresql://admin:P@ssw0rd@10.0.0.5/app")
```

**보충 예제 — 안전 코드 (권장 기준)**
```python
import os

# 환경변수/시크릿 매니저에서 주입 (원문 getenv / 외부 파일 대응). 없으면 즉시 실패
SECRET_KEY = os.environ["DJANGO_SECRET_KEY"]
DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.mysql",
        "USER": os.environ["DB_USER"],
        "PASSWORD": os.environ["DB_PASSWORD"],
    }
}

# 시크릿 매니저 예 (AWS)
import json

import boto3


def get_secret(name: str) -> dict:
    client = boto3.client("secretsmanager")  # 자격증명은 IAM 역할로
    return json.loads(client.get_secret_value(SecretId=name)["SecretString"])


db = get_secret("prod/app/db")
engine = create_engine(
    f"postgresql+psycopg://{db['user']}:{db['password']}@{db['host']}/{db['name']}"
)

# 로컬 개발은 .env + python-dotenv, .env는 .gitignore에 추가
# 저장소 점검 도구: gitleaks, detect-secrets, trufflehog (pre-commit 훅)
```

**판정 기준 / 오탐 주의**
- 테스트 픽스처의 더미 값(`"test"`, `"changeme"`), 예제 문서 값은 "낮음"으로 보되, 실제 운영 값과 같은지 확인할 수 없으면 "의심"으로 남긴다.
- 원문의 "암호화된 패스워드를 파일에 두고 복호화" 방식은 복호화 키를 또 어디에 두는지가 핵심이다. 키가 코드에 있으면 여전히 취약으로 판정한다.
- 이미 커밋된 비밀은 코드에서 지워도 Git 이력에 남는다. **키 폐기·교체**를 권고한다.

---

### SEC-07. 충분하지 않은 키 길이 사용

| 항목 | 내용 |
|---|---|
| 심각도 | 높음 |
| CWE | CWE-326 |
| 연관 설계항목 | SR2-6 |

#### KISA 소프트웨어 개발보안 가이드(2021) 원문

**개요 (2021 원문)**: 짧은 키는 암호화 알고리즘을 취약하게 만든다. 검증된 알고리즘이라도 키 길이가 충분하지 않으면 짧은 시간 안에 키를 찾아 데이터나 패스워드를 복호화할 수 있다.

**보안대책 (2021 원문)**: **RSA는 최소 2,048비트 이상**, **대칭 암호는 최소 128비트 이상**의 키를 쓴다.

**2021 원문 예제 요지 (Java·C·C#)**: Java `keyGen.initialize(1024)` → `2048`. C# `new RSACryptoServiceProvider(1024)` → `2048`. C `RSA_generate_key(512, ...)` → `2048`.

#### Python 시큐어코딩 가이드(2023) 원문 — 2장 2절 7항 (p.89~91)

- **Python 관련 설명**: 암호 알고리즘과 키 길이는 **안전성 유지기간과 보안강도별 키 길이 비교표**로 선택한다.
- **보안강도별 암호 알고리즘 비교표 (가이드 표)**

| 보안강도 | 대칭키 | 해시함수(보안강도) | RSA(인수분해) | 이산대수 공개키 | 이산대수 개인키 | 타원곡선 | 안전성 유지기간 |
|---|---|---|---|---|---|---|---|
| 112비트 | 112 | 112 | 2048 | 2048 | 224 | 224 | 2011~2030년 |
| 128비트 | 128 | 128 | 3072 | 3072 | 256 | 256 | 2030년 이후 |
| 192비트 | 192 | 192 | 7680 | 7680 | 384 | 384 | 2030년 이후 |
| 256비트 | 256 | 256 | 15360 | 15360 | 512 | 512 | 2030년 이후 |

- **안전한 코딩기법**: RSA는 최소 2,048비트, 대칭키는 최소 128비트(암호 강도 112비트 이상). **RSA·DSA는 2048비트 이상, ECC는 224비트 이상**.
- **원문 예제**

```python
import secrets

from Crypto.PublicKey import RSA
from tinyec import registry


# [가이드 원문] 안전하지 않은 코드
def make_rsa_key_pair():
    private_key = RSA.generate(1024)            # 2048 미만
    public_key = private_key.publickey()


def make_ecc():
    ecc_curve = registry.get_curve('secp192r1')  # 224비트 미만
    private_key = secrets.randbelow(ecc_curve.field.n)
    public_key = private_key * ecc_curve.g


# [가이드 원문] 안전한 코드
def make_rsa_key_pair():
    private_key = RSA.generate(2048)
    public_key = private_key.publickey()


def make_ecc():
    ecc_curve = registry.get_curve('secp224r1')
    private_key = secrets.randbelow(ecc_curve.field.n)
    public_key = private_key * ecc_curve.g
```

- **검토 메모**: 가이드는 `tinyec`로 ECC 키를 만드는 예를 들지만, `tinyec`는 학습용 순수 파이썬 구현이라 운영에는 `cryptography`(`ec.generate_private_key(ec.SECP256R1())`)나 `pycryptodome`(`ECC.generate(curve='P-256')`)를 권고한다. 탐지 패턴에 `RSA.generate(1024)`, `DSA.generate(1024)`, `get_curve('secp192r1')`, `secp160*` 를 포함한다.

#### 이 스킬의 점검 기준 (2021 가이드 + 실무 기준)

**탐지 패턴 (Python)**
- RSA/DSA/DH: `rsa.generate_private_key(public_exponent=65537, key_size=1024)`, `RSA.generate(1024)`, `DSA.generate(1024)`, `dh.generate_parameters(generator=2, key_size=1024)`, `ssh-keygen -b 1024` 호출
- 타원곡선: `ec.SECP192R1()`, `ec.SECT163K1()` 등 224비트 미만 곡선
- 대칭키: `AES.new(key, ...)`에서 `len(key) < 16`, `os.urandom(8)` 키, 비밀번호 문자열을 키로 직접 사용(`key = password.encode().ljust(16)`) — 키 유도 함수(KDF) 미사용
- HMAC/JWT 비밀키: 짧은 문자열(`"secret"`, 32바이트 미만)
- 키 유도: `PBKDF2HMAC(iterations=1000)` 처럼 반복 횟수가 낮음, `length=8`

**보충 예제 — 취약 코드**
```python
from cryptography.hazmat.primitives.asymmetric import rsa

private_key = rsa.generate_private_key(public_exponent=65537, key_size=1024)

key = "mypassword".encode().ljust(16, b"\0")  # 비밀번호를 그대로 키로 사용
```

**보충 예제 — 안전 코드 (권장 기준)**
```python
import os

from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import ec, rsa
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC

private_key = rsa.generate_private_key(public_exponent=65537, key_size=3072)  # 최소 2048
ec_key = ec.generate_private_key(ec.SECP256R1())

aes_key = os.urandom(32)  # AES-256 (최소 16바이트 = 128비트)

# 비밀번호에서 키가 필요하면 KDF 사용
salt = os.urandom(16)
kdf = PBKDF2HMAC(algorithm=hashes.SHA256(), length=32, salt=salt, iterations=600_000)
derived_key = kdf.derive(password.encode())
```

**판정 기준 / 오탐 주의**
- 2030년 이후까지 쓰일 데이터라면 RSA 3072 이상을 권고한다 (설계 SR2-6 표 참고).

---

### SEC-08. 적절하지 않은 난수값 사용

| 항목 | 내용 |
|---|---|
| 심각도 | 높음 (보안 용도일 때) |
| CWE | CWE-330, CWE-338 |
| 연관 설계항목 | SR2-6 |

#### KISA 소프트웨어 개발보안 가이드(2021) 원문

**개요 (2021 원문)**: 예측 가능한 난수를 쓰면 보안약점이 생긴다. 예측 불가능한 숫자가 필요한 곳에 예측 가능한 난수를 쓰면, 공격자가 다음 숫자를 예상해 공격할 수 있다.

**보안대책 (2021 원문)**: 난수발생기는 시드가 고정되면 매번 같은 값을 낸다. 일반 용도는 매번 바뀌는 시드(현재시간 등)를 쓴다. 그러나 **세션ID, 암호화키 등 보안결정을 위한 값**은 `Random()`/`Math.random()` 대신 **암호학적으로 안전한** `java.security.SecureRandom`을 써야 한다.

**2021 원문 예제 요지 (Java·C·C#)**: Java `new Random(100)`(고정 시드), `new Random().nextInt()`로 인증키 생성 → `SecureRandom`. C# `new Random().Next(10)` → `RNGCryptoServiceProvider`. C `rand()` → `srandom(time(NULL))` + `random()`.

> 원문 C 안전 예제(`srandom(time(NULL))`)는 암호학적으로 안전하지 않다(시간 기반 시드는 추측 가능). Python에서는 보안 용도에 반드시 `secrets`를 쓴다.

#### Python 시큐어코딩 가이드(2023) 원문 — 2장 2절 8항 (p.92~94)

- **Python 관련 설명**: `random` 모듈은 **게임, 퀴즈, 시뮬레이션** 용도로 설계되었다. 세션 ID, 암호화 키 등 보안 기능에는 **`secrets` 모듈(파이썬 3.6+)**을 써야 하며, 3.6 미만에서는 `os.urandom()`, `random.SystemRandom`이 안전하다.
- **안전한 코딩기법**: 시드를 쓰는 경우 고정값이 아닌 예측하기 어려운 값을 쓴다. 그래도 `random`으로 만든 난수는 강도가 낮아 보안 기능에는 안전하지 않다.
- **원문 예제**

```python
import random
import secrets
import string


# [가이드 원문] 안전하지 않은 코드 — OTP를 random으로
def get_otp_number():
    random_str = ''
    for i in range(6):
        random_str += str(random.randrange(10))
    return random_str


# [가이드 원문] 안전한 코드 — secrets.randbelow
def get_otp_number():
    random_str = ''
    for i in range(6):
        random_str += str(secrets.randbelow(10))
    return random_str


# [가이드 원문] 안전하지 않은 코드 / 안전한 코드 — 세션 키
def generate_session_key():
    chars = string.ascii_letters + string.digits
    return "".join(random.choice(chars) for i in range(32))


def generate_session_key():
    chars = string.ascii_letters + string.digits
    return "".join(secrets.choice(chars) for i in range(32))
```

- **검토 메모**: 판정 기준은 이 스킬과 같다. 세션 키처럼 단순 토큰이면 `secrets.token_urlsafe(32)`가 더 간단하다.

#### 이 스킬의 점검 기준 (2021 가이드 + 실무 기준)

**탐지 패턴 (Python)**
- `random.random(`, `random.randint(`, `random.choice(`, `random.choices(`, `random.sample(`, `random.getrandbits(`, `random.shuffle(`, `random.seed(`, `numpy.random.*`, `uuid.uuid1()`(시간·MAC 기반)
- 위 결과를 다음 용도에 쓰는 경우: 세션ID, 토큰(API 키, CSRF, 비밀번호 재설정, 이메일 인증), OTP·인증번호, 임시 비밀번호, 솔트, IV/nonce, 암호화 키, 파일명(추측 방지 목적), 쿠폰 코드
- `random.seed(고정값)` 또는 `random.seed(time.time())`
- `str(time.time())`, `hash(...)`, 증가 카운터로 토큰 생성

**보충 예제 — 취약 코드**
```python
import random
import string


def make_auth_code() -> str:
    return "".join(random.choices(string.digits, k=6))  # 인증번호를 예측 가능한 PRNG로


def make_reset_token() -> str:
    random.seed(time.time())  # 시간 기반 시드
    return str(random.getrandbits(64))
```

**보충 예제 — 안전 코드 (권장 기준)**
```python
import secrets
import string


def make_auth_code() -> str:
    return "".join(secrets.choice(string.digits) for _ in range(6))


def make_reset_token() -> str:
    return secrets.token_urlsafe(32)  # 256비트


salt = secrets.token_bytes(16)
api_key = secrets.token_hex(32)
session_id = secrets.token_urlsafe(32)  # 최소 128비트 (SR4-1)

# 보안과 무관한 용도(게임, 샘플링, 테스트 데이터)는 random 사용 가능
```

**판정 기준 / 오탐 주의**
- `random` 사용 자체가 아니라 **값의 용도**로 판정한다. 시뮬레이션·셔플·지터 등은 정상이다.
- `uuid.uuid4()`는 `os.urandom` 기반이라 식별자로 괜찮지만, 비밀 토큰은 `secrets`를 권장한다.

---

### SEC-09. 취약한 비밀번호 허용

| 항목 | 내용 |
|---|---|
| 심각도 | 중간 |
| CWE | CWE-521 |
| 연관 설계항목 | SR2-3 |

#### KISA 소프트웨어 개발보안 가이드(2021) 원문

**개요 (2021 원문)**: 사용자에게 강한 비밀번호 조합규칙을 요구하지 않으면 계정이 취약해진다. KISA 「패스워드 선택 및 이용 안내서」의 안전한 패스워드 설정규칙을 적용해야 한다.

**보안대책 (2021 원문)**: 비밀번호 생성 시 강한 조건 검증을 한다. 숫자·영문자·특수문자 등을 섞어 정해진 자릿수 이상으로 만들게 하고, 주기적으로 변경하게 한다.

**2021 원문 예제 요지 (Java·C·C#)**: Java 가입 시 복잡도 검사 없음 → 정규식 `((?=.*[a-zA-Z])(?=.*[0-9@#$%]).{9,})` 검사 실패 시 "비밀번호 조합규칙 오류". C# 빈 비밀번호 `NetworkCredential(UserName, "")` 허용 → 금지. C DB 연결 전 ID·비밀번호 검증 함수 호출.

**기준 (설계 SR2-3 표 3-12 요약)**: 2종류 이상 조합 8자리 이상 또는 10자리 이상, 동일 문자 반복·키보드 연속·ID 포함·사전 단어·개인정보 포함 금지.

#### Python 시큐어코딩 가이드(2023) 원문 — 2장 2절 9항 (p.95~98) ※ Python 가이드 명칭은 "취약한 **패스워드** 허용"

- **안전한 코딩기법**: 패스워드 생성 시 강한 조건 검증을 하고, 숫자·영문자·특수문자를 혼합해 쓰며 주기적으로 변경하게 한다. 특수문자 집합(`!@#$%^&*`)은 기업 내부 정책에 맞게 바꾼다. **숫자로만 10자리**를 구성하면 취약할 수 있으니 안전한 패스워드로 바꾸도록 안내한다.
- **Django `AUTH_PASSWORD_VALIDATORS` 기본 검증 (가이드 명시)**
  - `UserAttributeSimilarityValidator`: 다른 속성(이름, 성, 이메일)과의 유사도
  - `MinimumLengthValidator`: 최소 길이(기본 8)
  - `CommonPasswordValidator`: 가장 많이 쓰이는 패스워드 20,000개 해당 여부
  - `NumericPasswordValidator`: 숫자로만 구성되었는지
  - 추가 기준은 사용자 정의 Validator(통과 시 `None`, 실패 시 `ValidationError`)를 만들어 등록한다.
- **원문 예제** (Flask 회원가입)

```python
import re

from django.core.exceptions import ValidationError
from django.utils.translation import gettext as _


# [가이드 원문] 안전하지 않은 코드 — 복잡도 검증 없이 가입
@app.route('/register', methods=['POST'])
def register():
    userid = request.form.get('userid')
    password = request.form.get('password')
    confirm_password = request.form.get('confirm_password')
    if password != confirm_password:
        return make_response("패스워드가 일치하지 않습니다", 400)
    usertable = User()
    usertable.userid = userid
    usertable.password = password
    db.session.add(usertable)
    db.session.commit()
    return make_response("회원가입 성공", 200)


# [가이드 원문] 안전한 코드 — 2종 이상 조합 8자리 이상 또는 10자리 이상
def check_password(password):
    PT1 = re.compile(r'^(?=.*[A-Z])(?=.*[a-z])[A-Za-z\d!@#$%^&*]{8,}$')
    PT2 = re.compile(r'^(?=.*[A-Z])(?=.*\d)[A-Za-z\d!@#$%^&*]{8,}$')
    PT3 = re.compile(r'^(?=.*[A-Z])(?=.*[!@#$%^&*])[A-Za-z\d!@#$%^&*]{8,}$')
    PT4 = re.compile(r'^(?=.*[a-z])(?=.*\d)[A-Za-z\d!@#$%^&*]{8,}$')
    PT5 = re.compile(r'^(?=.*[a-z])(?=.*[!@#$%^&*])[A-Za-z\d!@#$%^&*]{8,}$')
    PT6 = re.compile(r'^(?=.*\d)(?=.*[!@#$%^&*])[A-Za-z\d!@#$%^&*]{8,}$')
    PT7 = re.compile(r'^[A-Za-z\d!@#$%^&*]{10,}$')     # 문자 구성 상관없이 10자리 이상
    for pattern in [PT1, PT2, PT3, PT4, PT5, PT6, PT7]:
        if pattern.match(password):
            return True
    return False


# [가이드 원문] Django 사용자 정의 Validator (raise 위치 오류를 바로잡음)
class CustomValidator:
    PATTERNS = []   # 위 PT1~PT7과 동일

    def validate(self, password, user=None):
        for pattern in self.PATTERNS:
            if pattern.match(password):
                return None
        raise ValidationError(_("패스워드 조합규칙에 적합하지 않습니다."), code='improper_password')

    def get_help_text(self):
        return _("패스워드는 영문 대문자, 소문자, 숫자, 특수문자 조합 중 2가지 이상 8자리이거나 "
                 "문자 구성 상관없이 10자리 이상이어야 합니다.")
```

- **검토 메모**
  - 가이드 안전 예제는 복잡도는 검사하지만 **`usertable.password = password`로 평문 저장**한다. 이 패턴은 SEC-09 충족, **SEC-05·SEC-14 미충족**으로 판정한다.
  - 가이드 코드 주석은 "3종 이상"이지만 정규식과 도움말은 **2종 이상 8자리 또는 10자리 이상**이다(KISA 「패스워드 선택 및 이용 안내서」 기준과 일치). 판정은 2종/8자리, 10자리 기준으로 한다.
  - 가이드 Django Validator 원문은 `raise`가 for 루프 안에 있어 첫 패턴이 불일치하면 바로 실패한다. 위에서 바로잡았다. `ugettext`는 Django 4.0에서 제거되어 `gettext`로 바꿨다.
  - 숫자 10자리(`PT7`이 허용) 문제는 Django `NumericPasswordValidator`를 함께 쓰면 막을 수 있다.

#### 이 스킬의 점검 기준 (2021 가이드 + 실무 기준)

**탐지 패턴 (Python)**
- 회원가입·비밀번호 변경·재설정 핸들러에서 서버 측 비밀번호 검증 함수 호출이 없음
- Django `AUTH_PASSWORD_VALIDATORS = []` 또는 일부만 설정, `MinimumLengthValidator`의 `min_length` < 8
- `User.objects.create_user(..., password=...)` 앞에 `validate_password()` 미호출 (DRF 회원가입 시리얼라이저에서 자주 누락)
- pydantic 스키마 `password: str` 에 길이·패턴 제약 없음
- 빈 비밀번호 허용: `if password:` 검사 없이 저장, `set_unusable_password` 오용
- 클라이언트(JS) 검증만 있고 서버 검증 없음

**보충 예제 — 취약 코드**
```python
@app.route("/register", methods=["POST"])
def register():
    user = User(username=request.form["id"])
    user.set_password(request.form["pass"])  # 복잡도 검사 없음
    db.session.add(user)
    db.session.commit()
    return "ok"
```

**보충 예제 — 안전 코드 (권장 기준)**
```python
import re

KEYBOARD_SEQS = ("qwerty", "asdf", "zxcv", "1234", "abcd")
CLASSES = [r"[a-z]", r"[A-Z]", r"\d", r"[^\w\s]"]


def validate_password(pw: str, user_id: str) -> None:
    if not pw:
        raise ValueError("비밀번호를 입력하세요.")
    kinds = sum(bool(re.search(c, pw)) for c in CLASSES)
    # KISA 기준: 2종류 이상 조합 8자 이상 또는 10자 이상
    if not ((kinds >= 2 and len(pw) >= 8) or len(pw) >= 10):
        raise ValueError("비밀번호 조합규칙 오류")
    if kinds == 1 and pw.isdigit():
        raise ValueError("숫자로만 구성할 수 없습니다.")
    low = pw.lower()
    if user_id and user_id.lower() in low:
        raise ValueError("아이디를 포함할 수 없습니다.")
    if re.search(r"(.)\1\1", pw) or any(s in low for s in KEYBOARD_SEQS):
        raise ValueError("반복·연속 문자를 사용할 수 없습니다.")


@app.route("/register", methods=["POST"])
def register():
    try:
        validate_password(request.form.get("pass", ""), request.form.get("id", ""))
    except ValueError as e:
        return str(e), 400
    ...


# Django
AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator",
     "OPTIONS": {"min_length": 10}},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]
# DRF 시리얼라이저: django.contrib.auth.password_validation.validate_password(value, user)
```

**판정 기준 / 오탐 주의**
- 원문의 주기적 변경 요구는 KISA 기준이다. 최신 NIST SP 800-63B는 강제 주기 변경을 권장하지 않으므로, 공모전·공공 사업 기준이면 KISA를 따르고 그 외에는 두 기준의 차이를 함께 적는다.

---

### SEC-10. 부적절한 전자서명 확인

| 항목 | 내용 |
|---|---|
| 심각도 | 높음 |
| CWE | CWE-347 |
| 연관 설계항목 | SR1-10 |

#### KISA 소프트웨어 개발보안 가이드(2021) 원문

**개요 (2021 원문)**: 전자서명은 서명자의 신원을 확인하고 파일의 무결성을 보장하는 디지털 정보다. 전자서명을 검증하지 않거나 검증 절차가 부적절하면 위·변조된 파일로 악성코드에 감염될 수 있다.

**보안대책 (2021 원문)**: 전자서명이 포함된 파일을 쓸 때는 **항상 전자서명을 확인**한다. 전자서명 파일의 출처를 확인해 신뢰할 수 없는 곳에서 만든 파일을 쓰지 않는다.

**2021 원문 예제 요지 (Java·C·C#)**: Java `new JarFile(f)`(서명 미검증) → `new JarFile(f, true)` + `JarEntry.getCodeSigners()`로 서명 주체 신뢰 여부 확인.

#### Python 시큐어코딩 가이드(2023) 원문 — 2장 2절 10항 (p.99~102)

- **Python 관련 설명**: 클라이언트·서버 간 주요 데이터 전송이나 파일 다운로드에서 생긴다. 전자서명은 원문 데이터의 **암호화된 해시 값**이라 수신측이 변조 여부를 확인할 수 있다. **해시만으로 검증하면 해시 자체를 바꿔 악성코드를 전달할 수 있지만, 전자서명은 해시 자체도 보호**한다.
- **안전한 코딩기법**: 주요 데이터 전송·다운로드 시 전자서명을 함께 보내고, 수신측은 서명을 검증해 변조 여부를 확인한다. 송수신측 언어가 다르면 암호 라이브러리에 따라 인코딩 방식이 다르므로, **배포 전에 서명 검증 과정이 정상 동작하는지 반드시 검증**한다.
- **원문 예제** (pycryptodome, RSA PKCS#1 v1.5 서명)

```python
import base64

from Crypto.Hash import SHA256
from Crypto.PublicKey import RSA
from Crypto.Signature import PKCS1_v1_5 as SIGNATURE_PKCS1_v1_5


# [가이드 원문] 안전하지 않은 코드 — 서명 없이 받은 코드를 복호화해 실행
def verify_data(request):
    encrypted_code = request.POST.get("encrypted_msg", "")
    with open(f"{PATH}/keys/secret_key.out", "rb") as f:
        secret_key = f.read()
    origin_python_code = decrypt_with_symmetric_key(secret_key, encrypted_code)
    eval(origin_python_code)
    return render(request, "/verify_success.html", {"result": "파이썬 코드를 실행했습니다."})


# [가이드 원문] 안전한 코드 — 공개키로 서명 검증 후에만 실행 (미정의 변수명을 바로잡음)
def verify_digit_signature(origin_data: bytes, origin_signature: bytes, client_pub_key: str) -> bool:
    hashed_data = SHA256.new(origin_data)
    signer = SIGNATURE_PKCS1_v1_5.new(RSA.importKey(client_pub_key))
    return signer.verify(hashed_data, base64.b64decode(origin_signature))


def verify_data(request):
    encrypted_code = request.POST.get("encrypted_msg", "")
    encrypted_sig = request.POST.get("encrypted_sig", "")
    with open("/keys/secret_key.out", "rb") as f:
        secret_key = f.read()
    with open("/keys/public_key.out", "rb") as f:
        client_pub_key = f.read()
    origin_python_code = decrypt_with_symmetric_key(secret_key, encrypted_code)
    origin_signature = decrypt_with_symmetric_key(secret_key, encrypted_sig)
    if verify_digit_signature(origin_python_code, origin_signature, client_pub_key):
        eval(origin_python_code)
        return render(request, "/verify_success.html",
                      {"result": "전자서명 검증 통과 및 파이썬 코드를 실행했습니다."})
    return render(request, "/verify_failed.html", {"result": "전자서명 또는 파이썬 코드가 위/변조되었습니다."})
```

- **검토 메모**
  - 서명 검증을 통과해도 **원격에서 받은 코드를 `eval()`로 실행하는 구조 자체**는 INP-02·SEC-15 관점의 위험으로 남는다(서명키 유출 시 원격 코드 실행). 가능하면 코드가 아닌 **데이터**를 주고받도록 권고한다.
  - 공개키를 어디서 받는지(사전 공유·고정)가 핵심이다. 요청과 함께 받은 공개키로 검증하면 무의미하다.
  - `PKCS1_v1_5` 서명도 쓸 수 있지만, KISA 검증기준표의 RSA 전자서명은 **RSA-PSS**이므로 `Crypto.Signature.pss` 사용을 권고한다(SEC-04 표).

#### 이 스킬의 점검 기준 (2021 가이드 + 실무 기준)

**탐지 패턴 (Python)**
- JWT/JWS: `jwt.decode(..., options={"verify_signature": False})`, `algorithms` 미지정, `jwt.get_unverified_header()`/`get_unverified_claims()` 결과로 인가 판단, python-jose `jwt.decode(token, key, options={"verify_signature": False})`
- 웹훅: 결제·GitHub·Slack 웹훅 서명 헤더(`Stripe-Signature`, `X-Hub-Signature-256`, `X-Slack-Signature`) 검증 없음, 또는 `==`로 비교(타이밍 공격 — `hmac.compare_digest` 사용)
- 서명 검증 예외를 삼킴: `try: public_key.verify(...) except InvalidSignature: pass`
- 업데이트·플러그인: 다운로드한 패키지·스크립트를 서명(GPG, Sigstore) 확인 없이 실행
- SAML/OIDC: ID 토큰 서명·`aud`·`iss` 검증 생략
- `pip install --trusted-host`, `--no-verify` 류 옵션

**보충 예제 — 취약 코드**
```python
@app.route("/webhook/payment", methods=["POST"])
def payment_webhook():
    event = request.get_json()  # 서명 검증 없이 결제 완료 처리
    mark_paid(event["order_id"])
    return "ok"


claims = jwt.decode(token, options={"verify_signature": False})
```

**보충 예제 — 안전 코드 (권장 기준)**
```python
import hashlib
import hmac

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import padding

WEBHOOK_SECRET = os.environ["WEBHOOK_SECRET"].encode()


@app.route("/webhook/payment", methods=["POST"])
def payment_webhook():
    sig = request.headers.get("X-Signature-256", "")
    expected = "sha256=" + hmac.new(WEBHOOK_SECRET, request.get_data(), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(sig, expected):
        abort(401)
    event = request.get_json()
    mark_paid(event["order_id"])
    return "ok"


claims = jwt.decode(token, PUBLIC_KEY, algorithms=["RS256"], audience="my-app")


# 파일 서명 검증 (원문 JarFile(f, true) + getCodeSigners 대응)
def verify_file_signature(data: bytes, signature: bytes, trusted_public_key) -> bool:
    try:
        trusted_public_key.verify(
            signature, data,
            padding.PSS(mgf=padding.MGF1(hashes.SHA256()), salt_length=padding.PSS.MAX_LENGTH),
            hashes.SHA256(),
        )
        return True
    except InvalidSignature:
        return False
```

**판정 기준 / 오탐 주의**
- 단위 테스트에서만 `verify_signature=False`를 쓰는 경우는 제외하되, 운영 코드 경로에서 호출되는지 확인한다.

---

### SEC-11. 부적절한 인증서 유효성 검증

| 항목 | 내용 |
|---|---|
| 심각도 | 높음 |
| CWE | CWE-295 |
| 연관 설계항목 | SR2-1, SR2-6 |

#### KISA 소프트웨어 개발보안 가이드(2021) 원문

**개요 (2021 원문)**: 인증서를 확인하지 않거나 확인 절차가 부적절하면, 악의적인 호스트에 연결되거나 신뢰할 수 없는 호스트의 데이터를 받게 된다.

**보안대책 (2021 원문)**: 인증서를 쓰기 전에 유효성을 확인한다. **Common Name과 실제 호스트 일치 여부**, **신뢰된 발급기관(CA, RootCA)의 서명 여부**, **유효기간**, **해지 여부**(CRL 또는 OCSP), **안전한 암호 알고리즘 사용 여부**를 검증한다.

**2021 원문 예제 요지 (Java·C·C#)**: C `SSL_get_verify_result`가 `X509_V_ERR_SELF_SIGNED_CERT_IN_CHAIN`이어도 통과 → 자체 서명 인증서 허용. `X509_V_OK`여도 CN 확인 안 함 → 중간자 공격 탐지 불가. Java 안전 예제: 발급자 DN과 CA 주체 DN 일치 확인, CA 공개키로 서명 검증(`verify`), 유효기간 확인(`checkValidity`), CRL/OCSP로 해지 확인.

#### Python 시큐어코딩 가이드(2023) 원문 — 2장 2절 11항 (p.103~106)

- **Python 관련 설명**: 인증서가 유효하지 않거나 악성이면 공격자가 통신 구간을 가로채 신뢰하는 엔티티로 위장한다.
- **안전한 코딩기법**: 인증서를 쓰는 통신에서는 송신측 인증서가 유효한지 검증한 뒤 데이터를 송수신한다. 기본 검증 함수가 없거나 일반적이지 않은 방식으로 만든 인증서면 암호화 패키지로 **별도 검증 코드**를 작성한다.
- **Python 핵심**: `ssl.SSLContext()` 생성자를 직접 호출하면 **`verify_mode`의 기본값이 `CERT_NONE`**이다. `ssl.PROTOCOL_TLS_CLIENT`로 만들면 `verify_mode=CERT_REQUIRED`, `check_hostname=True`가 설정된다.
- **원문 예제**

```python
import os
import socket
import ssl

HOST, PORT = "127.0.0.1", 7917


# [가이드 원문] 안전하지 않은 코드 — 서버 인증서를 검증하지 않음
def connect_with_server():
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM, 0) as sock:
        context = ssl.SSLContext()
        context.verify_mode = ssl.CERT_NONE
        with context.wrap_socket(sock) as ssock:
            ssock.connect((HOST, PORT))
            ssock.send("Hello I'm a vulnerable client :)".encode("utf-8"))
            data = ssock.recv(1024).decode("utf-8")


# [가이드 원문] 안전한 코드 — PROTOCOL_TLS_CLIENT + CA 로드 + 호스트명 확인
HOST_NAME = "test-server"
SERVER_CA_PEM = f"{os.getcwd()}/rsa_server/CA.pem"


def connect_with_server():
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM, 0) as sock:
        context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)   # CERT_REQUIRED, check_hostname=True
        context.load_verify_locations(SERVER_CA_PEM)
        # server_hostname이 서버 인증서에 등록된 호스트명과 일치해야 통신 가능
        with context.wrap_socket(sock, server_hostname=HOST_NAME) as ssock:
            ssock.connect((HOST, PORT))
            ssock.send("Hello I'm a patched client :)".encode("utf-8"))
            data = ssock.recv(1024).decode("utf-8")
```

- **검토 메모**: 탐지 패턴에 **인자 없는 `ssl.SSLContext()`**(기본 CERT_NONE)를 추가한다. 이 스킬의 기준인 `ssl.create_default_context()`도 같은 효과(검증·호스트명 확인)를 낸다. 최소 프로토콜(`minimum_version = TLSv1_2`) 설정을 함께 권고한다.

#### 이 스킬의 점검 기준 (2021 가이드 + 실무 기준)

**탐지 패턴 (Python)**
- `requests.*(..., verify=False)`, `session.verify = False`, `httpx.Client(verify=False)`, `aiohttp ... ssl=False`, `urllib3.disable_warnings(InsecureRequestWarning)` (검증 끄고 경고 숨김)
- `ssl._create_unverified_context()`, `ssl._create_default_https_context = ssl._create_unverified_context`
- `ctx.check_hostname = False`, `ctx.verify_mode = ssl.CERT_NONE` 또는 `CERT_OPTIONAL`
- `urllib3.PoolManager(cert_reqs="CERT_NONE")`
- `paramiko.SSHClient().set_missing_host_key_policy(paramiko.AutoAddPolicy())`(호스트키 미검증)
- `smtplib.SMTP.starttls()`에 `context` 미지정(구버전 기본은 검증 안 함), `ftplib.FTP_TLS` 동일
- 환경변수 `PYTHONHTTPSVERIFY=0`, `CURL_CA_BUNDLE=""`, `REQUESTS_CA_BUNDLE=""`
- 직접 인증서 검증 구현 시 유효기간·호스트명·체인 검사 누락

**보충 예제 — 취약 코드**
```python
import ssl

import requests
import urllib3

urllib3.disable_warnings()
resp = requests.get("https://api.partner.example.com/data", verify=False)

ctx = ssl.create_default_context()
ctx.check_hostname = False
ctx.verify_mode = ssl.CERT_NONE
```

**보충 예제 — 안전 코드 (권장 기준)**
```python
import ssl

import requests

# 기본값(verify=True)으로 시스템/certifi CA 사용
resp = requests.get("https://api.partner.example.com/data", timeout=10)

# 사설 CA를 써야 하면 CA 번들을 지정 (검증을 끄지 않는다)
resp = requests.get("https://internal.example.local/api", verify="/etc/ssl/certs/internal-ca.pem",
                    timeout=10)

# 표준 ssl: 호스트명 검증 + 체인 검증 + 구버전 프로토콜 차단
ctx = ssl.create_default_context(cafile="/etc/ssl/certs/internal-ca.pem")
ctx.minimum_version = ssl.TLSVersion.TLSv1_2

# 인증서 고정(pinning)이 필요하면 지문 비교를 추가 (검증 대체가 아니라 추가)

# SSH 호스트키 검증
client = paramiko.SSHClient()
client.load_system_host_keys()
client.set_missing_host_key_policy(paramiko.RejectPolicy())
```

**판정 기준 / 오탐 주의**
- 로컬 개발·테스트 환경 분기에서만 `verify=False`면 "낮음"으로 보되, 환경 분기 조건이 운영에서 확실히 꺼지는지 확인한다.

---

### SEC-12. 사용자 하드디스크에 저장되는 쿠키를 통한 정보노출

| 항목 | 내용 |
|---|---|
| 심각도 | 중간 |
| CWE | CWE-539 |
| 연관 설계항목 | SR2-7 |

#### KISA 소프트웨어 개발보안 가이드(2021) 원문

**개요 (2021 원문)**: 대부분의 쿠키는 메모리에 있다가 브라우저가 종료되면 사라진다. 프로그래머가 원하면 브라우저 세션과 무관하게 디스크에 저장되게 할 수 있다. 개인정보·인증정보가 이런 **영속적인 쿠키(Persistent Cookie)**에 저장되면 공격자가 쿠키에 접근할 기회가 많아진다.

**보안대책 (2021 원문)**: 쿠키 만료시간은 세션 지속시간을 고려해 **최소한으로** 설정하고, 영속 쿠키에는 **사용자 권한 등급, 세션ID 등 중요정보를 넣지 않는다**.

**2021 원문 예제 요지 (Java·C·C#)**: Java `setMaxAge(60*60*24*365)`(1년) → `60*60*24`(1일). C# `Expires = Now.AddMinutes(60*24*365)` → `AddMinutes(10)`.

#### Python 시큐어코딩 가이드(2023) 원문 — 2장 2절 12항 (p.107~109)

- **안전한 코딩기법**: 쿠키 만료시간은 세션 지속 시간을 고려해 최소로 설정하고, 영속 쿠키에는 권한 등급·세션 ID 등 중요 정보를 넣지 않는다. 쿠키를 HTTPS로만 전송하도록 **`secure=True`**(기본 False), JavaScript 접근을 막으려면 **`httponly=True`**(기본 False)를 설정한다.
- **원문 예제** (Django)

```python
from django.http import HttpResponse


# [가이드 원문] 안전하지 않은 코드 — 1년짜리 영속 쿠키
def remind_user_state(request):
    res = HttpResponse()
    res.set_cookie('rememberme', 1, max_age=60 * 60 * 24 * 365)
    return res


# [가이드 원문] 안전한 코드 — 1시간 + secure + httponly
def remind_user_state(request):
    res = HttpResponse()
    res.set_cookie('rememberme', 1, max_age=60 * 60, secure=True, httponly=True)
    return res


# [가이드 원문] settings.py 전역 설정 (가이드 예시값)
SESSION_COOKIE_AGE = 60 * 60 * 24 * 14
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SECURE = True
```

- **검토 메모**: 가이드의 전역 설정 예제는 `django.conf.global_settings`에서 값을 import하는데, 이는 **프로젝트 설정이 아니라 Django 기본값**이다. 또 `secure=SESSION_COOKIE_HTTPONLY`로 잘못 넘기고 있다. 프로젝트 값을 쓰려면 `from django.conf import settings` 후 `settings.SESSION_COOKIE_SECURE`를 쓴다. 판정 시 이런 혼동 코드가 있으면 실제 적용 값을 확인한다. 가이드 예시값 `SESSION_COOKIE_AGE`(14일)는 Django 기본값과 같으며, 설계 기준 SR4-1(중요기능 2~5분, 일반 15~30분)과는 차이가 있으므로 기능 위험도에 맞게 줄이도록 권고한다.

#### 이 스킬의 점검 기준 (2021 가이드 + 실무 기준)

**탐지 패턴 (Python)**
- `set_cookie(..., max_age=큰 값)`, `set_cookie(..., expires=먼 미래)`, `max_age=60*60*24*365`
- Django `SESSION_EXPIRE_AT_BROWSER_CLOSE = False` + 긴 `SESSION_COOKIE_AGE`(기본 2주), `request.session.set_expiry(큰 값)`
- Flask `session.permanent = True` + 긴 `PERMANENT_SESSION_LIFETIME`(기본 31일), Flask-Login `REMEMBER_COOKIE_DURATION`(기본 365일)
- 쿠키 값에 `role`, `level`, `user_id`, `email`, `phone`, 세션ID, JWT(장기) 저장
- `httponly=False`(기본값 확인), `secure=False`, `samesite=None`
- 프론트엔드 `localStorage`에 액세스 토큰·개인정보 저장 (SR2-7)

**보충 예제 — 취약 코드**
```python
resp = make_response(redirect("/"))
resp.set_cookie("rememberme", "YES", max_age=60 * 60 * 24 * 365)  # 1년
resp.set_cookie("user_level", "admin", max_age=60 * 60 * 24 * 365)  # 권한정보를 영속 쿠키에

app.config["REMEMBER_COOKIE_DURATION"] = timedelta(days=365)
```

**보충 예제 — 안전 코드 (권장 기준)**
```python
from datetime import timedelta

resp = make_response(redirect("/"))
# 기능에 맞는 최소 기간, 중요정보 미포함, 보안 속성 설정
resp.set_cookie("rememberme", "YES", max_age=60 * 60 * 24, secure=True,
                httponly=True, samesite="Lax")
# 권한 등급은 쿠키가 아니라 서버 세션/DB에서 관리

app.config.update(
    PERMANENT_SESSION_LIFETIME=timedelta(minutes=30),
    REMEMBER_COOKIE_DURATION=timedelta(days=1),
    REMEMBER_COOKIE_SECURE=True,
    REMEMBER_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SECURE=True,
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE="Lax",
)

# Django
SESSION_EXPIRE_AT_BROWSER_CLOSE = True
SESSION_COOKIE_AGE = 60 * 30
```

**판정 기준 / 오탐 주의**
- "로그인 유지" 기능이 요구사항이면, 장기 쿠키에 세션ID 대신 **별도의 회전되는 remember 토큰**(서버 저장, 1회용)을 쓰는지 확인한다.

---

### SEC-13. 주석문 안에 포함된 시스템 주요정보

| 항목 | 내용 |
|---|---|
| 심각도 | 중간 |
| CWE | CWE-615 |
| 연관 설계항목 | SR2-5 |

#### KISA 소프트웨어 개발보안 가이드(2021) 원문

**개요 (2021 원문)**: 패스워드를 주석에 넣어두면 시스템 보안이 훼손될 수 있다. 편의를 위해 주석에 적어둔 패스워드는 완성 후 제거하기 매우 어렵고, 공격자가 소스코드에 접근하면 쉽게 침입할 수 있다.

**보안대책 (2021 원문)**: 주석에는 ID, 패스워드 등 보안 관련 내용을 쓰지 않는다. 개발 완료 시 주석의 계정·패스워드 정보를 확실히 삭제한다.

**2021 원문 예제 요지 (Java·C·C#)**: `// DB연결 root / a1q2w3r3f2!@` 주석 → 삭제. C `/* password is "admin" */` → 삭제.

#### Python 시큐어코딩 가이드(2023) 원문 — 2장 2절 13항 (p.110~111)

- **안전한 코딩기법**: 주석에는 아이디, 패스워드 등 보안 관련 내용을 쓰지 않는다. 개발 완료 후 주석의 계정·패스워드 정보를 확실히 삭제한다.
- **원문 예제**

```python
# [가이드 원문] 안전하지 않은 코드
def user_login(id, passwd):
    # 주석문에 포함된 중요 시스템의 인증 정보
    # id = admin
    # passwd = passw0rd
    result = login(id, passwd)
    return result


# [가이드 원문] 안전한 코드
def user_login(id, passwd):
    # 주석문에 포함된 민감한 정보는 삭제
    result = login(id, passwd)
    return result
```

- **검토 메모**: 가이드 예시처럼 `# passwd = passw0rd` 형태(주석 속 `키 = 값`)도 탐지 패턴에 포함한다: `rg -n -i '#\s*(id|user|passwd|password|pwd|secret|key)\s*[=:]\s*\S{3,}'`.

#### 이 스킬의 점검 기준 (2021 가이드 + 실무 기준)

**탐지 패턴 (Python)**
- `#` 주석, docstring(`"""..."""`), 템플릿 주석(`{# #}`, `<!-- -->`), 주석 처리된 코드에서:
  - `(?i)#.*(password|passwd|pwd|비밀번호|패스워드|secret|token|api[_-]?key|접속정보|계정)\s*[:=/]`
  - `(?i)#.*\b\w+\s*/\s*\S{4,}` (`root / pass` 형식)
  - 내부 IP·호스트·포트(`10.`, `192.168.`, `172.16-31.`), 관리자 URL, 서버 경로
  - 주석 처리된 연결 코드: `# conn = pymysql.connect(host="...", password="...")`
  - `TODO: remove`, `FIXME: hardcoded`, `임시 계정`
- **HTML 템플릿 주석(`<!-- -->`)은 브라우저에 그대로 전달**되므로 특히 위험 (SR2-7: 중요 로직·주석은 서버 측에서만)
- Jupyter 노트북(`.ipynb`)의 셀 출력·주석

**보충 예제 — 취약 코드**
```python
# DB연결 root / a1q2w3r3f2!@
conn = pymysql.connect(host=DB_HOST, user=DB_USER, password=DB_PASS)

# templates/login.html
#   <!-- 테스트 계정: admin / admin1234, 관리자 페이지 /mgr_9f3a -->
```

**보충 예제 — 안전 코드 (권장 기준)**
```python
# DB 접속 정보는 환경변수(DB_HOST, DB_USER, DB_PASS)로 주입한다.
conn = pymysql.connect(host=DB_HOST, user=DB_USER, password=DB_PASS)

# templates/login.html — 서버 측 주석 사용 (클라이언트에 전달되지 않음)
#   {# 로그인 폼 #}
```

**판정 기준 / 오탐 주의**
- 플레이스홀더 설명(`# password: 환경변수 DB_PASS에서 읽음`)은 오탐이다. **실제 값처럼 보이는 문자열**이 있는지로 판단한다.
- 주석에서 지워도 Git 이력에 남는다. 실제 비밀이면 교체를 권고한다 (SEC-06 동일).

---

### SEC-14. 솔트 없이 일방향 해쉬함수 사용

| 항목 | 내용 |
|---|---|
| 심각도 | 높음 |
| CWE | CWE-759, CWE-916 |
| 연관 설계항목 | SR2-6, SR2-3 |

#### KISA 소프트웨어 개발보안 가이드(2021) 원문

**개요 (2021 원문)**: 패스워드를 저장할 때 일방향 해쉬함수의 성질을 이용해 해쉬값을 저장한다. 솔트 없이 해쉬하면 공격자가 **레인보우 테이블**처럼 미리 계산한 해쉬값으로 패스워드를 찾을 수 있다.

**보안대책 (2021 원문)**: 패스워드와 **솔트**를 함께 해쉬함수에 넣어 얻은 값을 저장한다.

**2021 원문 예제 요지 (Java·C·C#)**: Java `MessageDigest("SHA-256").update(password)` → `update(password); update(salt)`. C# `SHA256.ComputeHash(source)` → 암호학적 난수 솔트를 붙여 해시. C `MD5HashAlgorithm(data, out, NULL)` → 솔트 인자 전달.

> 설계 SR2-3 [참고 4]에서 원문도 지적하듯, SHA-256은 **빠른 해시**라 솔트를 붙여도 무차별 대입에 약하다. Python에서는 **비밀번호 전용 느린 해시(Argon2id, bcrypt, scrypt, PBKDF2)**를 기준으로 판정한다. 솔트는 사용자별로 고유해야 하며(원문: 32바이트 이상이면 추측 어려움), 고정 솔트는 솔트가 없는 것과 비슷하다.

#### Python 시큐어코딩 가이드(2023) 원문 — 2장 2절 14항 (p.112~113)

- **안전한 코딩기법**: 중요 정보는 일방향 해시로 저장한다. **솔트는 사용자별로 유일하게 생성**하고 사용자별 솔트를 별도로 저장한다. 파이썬에서는 `hashlib`으로 해시를 만들고, 솔트는 **`os.urandom()` 등 안전한 난수 생성 라이브러리**로 만든다.
- **원문 예제**

```python
import hashlib
import secrets


# [가이드 원문] 안전하지 않은 코드 — 솔트 없음
def get_hash_from_pwd(pw):
    h = hashlib.sha256(pw.encode())
    return h.digest()


# [가이드 원문] 안전한 코드 — 사용자별 랜덤 솔트(secrets.token_hex(32)), 솔트도 DB에 저장
def get_hash_from_pwd(pw):
    salt = secrets.token_hex(32)
    h = hashlib.sha256(salt.encode() + pw.encode())
    return h.digest(), salt
```

- **검토 메모**: 가이드 기준은 **사용자별 랜덤 솔트 + SHA-256**이다. KISA 기준 판정은 "충족"이나, 이 스킬은 빠른 해시의 무차별 대입 취약성(2021 가이드 3장 [참고 4]에서도 지적)을 이유로 Argon2id·bcrypt·scrypt·PBKDF2(충분한 반복)를 권고하고 "부분충족 + 업그레이드 권고"로 보고한다. 같은 가이드 안의 SEC-01, SEC-16 예제는 **솔트 없는 SHA-256**을 쓰고 있어 이 항목과 모순되므로, 그 예제를 따른 코드는 SEC-14 미충족이다.

#### 이 스킬의 점검 기준 (2021 가이드 + 실무 기준)

**탐지 패턴 (Python)**
- 비밀번호에 직접 해시: `hashlib.sha256(password.encode()).hexdigest()`, `hashlib.md5(pw)`, `hashlib.sha512(pw)`
- 고정·전역 솔트: `SALT = "..."`, `hashlib.sha256((SALT + password).encode())`, `salt = b"salt"`
- 사용자 ID·이메일을 솔트로 사용 (예측 가능)
- 반복 횟수 부족: `hashlib.pbkdf2_hmac("sha256", pw, salt, 1000)` (OWASP 권장: PBKDF2-HMAC-SHA256 600,000회)
- 비교에 `==` 사용 (타이밍) — `hmac.compare_digest` 또는 라이브러리 `verify` 사용
- Django `PASSWORD_HASHERS`에 `UnsaltedSHA1PasswordHasher`, `UnsaltedMD5PasswordHasher`

**보충 예제 — 취약 코드**
```python
import hashlib


def get_password_hash(password: str) -> str:
    return hashlib.sha256(password.encode()).hexdigest()  # 솔트 없음


SALT = "myapp"


def get_password_hash2(password: str) -> str:
    return hashlib.sha256((SALT + password).encode()).hexdigest()  # 모든 사용자 동일 솔트
```

**보충 예제 — 안전 코드 (권장 기준)**
```python
import hashlib
import hmac
import os

# 1) 권장: Argon2id (argon2-cffi) — 솔트 생성·저장·비교를 라이브러리가 처리
from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError

ph = PasswordHasher()
stored = ph.hash(password)


def verify(stored_hash: str, password: str) -> bool:
    try:
        return ph.verify(stored_hash, password)
    except VerifyMismatchError:
        return False


# 2) 표준 라이브러리만 써야 할 때: 사용자별 랜덤 솔트 + PBKDF2 (원문 '솔트 사용' 대응)
ITERATIONS = 600_000


def get_password_hash(password: str) -> str:
    salt = os.urandom(32)
    dk = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, ITERATIONS)
    return f"pbkdf2_sha256${ITERATIONS}${salt.hex()}${dk.hex()}"


def check_password(stored_value: str, password: str) -> bool:
    _, iters, salt_hex, dk_hex = stored_value.split("$")
    dk = hashlib.pbkdf2_hmac("sha256", password.encode(), bytes.fromhex(salt_hex), int(iters))
    return hmac.compare_digest(dk.hex(), dk_hex)


# 3) 프레임워크 내장: Django make_password/check_password, Werkzeug generate_password_hash
```

**판정 기준 / 오탐 주의**
- 원문 기준(솔트 + SHA-256)만 충족하고 느린 해시가 아니면 "부분충족"으로 보고, 업그레이드를 권고한다.

---

### SEC-15. 무결성 검사 없는 코드 다운로드

| 항목 | 내용 |
|---|---|
| 심각도 | 높음 |
| CWE | CWE-494 |
| 연관 설계항목 | SR1-10 |

#### KISA 소프트웨어 개발보안 가이드(2021) 원문

**개요 (2021 원문)**: 원격에서 소스코드나 실행파일을 무결성 검사 없이 내려받아 실행하는 제품이 있다. 호스트 서버 변조, **DNS 스푸핑**, 전송 중 코드 변조로 공격자가 악성 코드를 실행할 수 있다.

**보안대책 (2021 원문)**: DNS 스푸핑을 방어할 수 있는 DNS lookup을 수행하고, 코드 전송 시 신뢰할 수 있는 암호 기법으로 코드를 보호한다. 다운로드한 코드는 작업에 필요한 **최소 권한**으로 실행한다.

**2021 원문 예제 요지 (Java·C·C#)**: Java `URLClassLoader`로 원격 클래스를 검증 없이 로드 → 공개키 방식 서명으로 변조 여부 확인 후 로드. C# `WebClient.DownloadData` 후 바로 저장 → 해시로 무결성 검사. C `InternetReadFile` 반환값 미확인 → 반환값 확인 후 쓰기.

#### Python 시큐어코딩 가이드(2023) 원문 — 2장 2절 15항 (p.114~116)

- **Python 관련 설명**: 파일(및 소프트웨어) 무결성 확인의 두 가지 주요 방법은 **암호화 해시와 디지털 서명**이다. 해시로 무결성을 보장하고, 가능하면 **코드 서명 인증서**를 사용·확인하는 것이 더 안전하다.
- **안전한 코딩기법**: DNS 스푸핑을 막을 수 있는 DNS lookup을 하고, 코드 전송 시 신뢰할 수 있는 암호 기법을 쓴다. 다운로드한 코드는 최소 권한으로 실행한다. **신뢰할 수 있는 사이트에서만 다운로드**하고 인증서·해시값으로 변조 여부를 확인한다.
- **원문 예제**

```python
import configparser
import hashlib

import requests


# [가이드 원문] 안전하지 않은 코드 — 다운로드 후 무결성 검사 없이 저장
def execute_remote_code():
    url = "https://www.somewhere.com/storage/code.py"
    file = requests.get(url)
    with open('save.py', 'wb') as f:
        f.write(file.content)


# [가이드 원문] 안전한 코드 — 설정 파일의 기대 해시와 비교
def execute_remote_code():
    config = configparser.RawConfigParser()
    config.read('sample_config.cfg')
    url = "https://www.somewhere.com/storage/code.py"
    remote_code_hash = config.get('HASH', 'file_hash')
    file = requests.get(url)
    sha = hashlib.sha256()
    sha.update(file.content)
    if sha.hexdigest() != remote_code_hash:
        raise Exception('파일이 손상되었습니다.')
    with open('save.py', 'wb') as f:
        f.write(file.content)
```

- **검토 메모**: 기대 해시를 **별도 설정 파일**에서 읽는 구조로, 판정 기준은 이 스킬과 같다("기대값의 출처가 다운로드 서버와 분리되어 있는가"). `requests.get()`에 `timeout`과 `raise_for_status()`가 없는 점은 TIM-02·ERR-02 관점에서 보완을 권고한다.

#### 이 스킬의 점검 기준 (2021 가이드 + 실무 기준)

**탐지 패턴 (Python)**
- 원격 코드 실행: `exec(requests.get(url).text)`, `exec(urlopen(url).read())`, `importlib`로 다운로드한 모듈 로드, `subprocess.run(["bash", "-c", downloaded])`, `curl ... | sh`/`| python` 패턴(Dockerfile·셸 스크립트·`os.system`)
- 다운로드 후 해시·서명 검증 없이 `chmod +x`·실행·`pip install 파일`·`tarfile.extractall` 후 import
- 모델·데이터 파일: `torch.load(url에서 받은 파일)`(pickle 기반), `joblib.load`, `pickle.load` — 원격 파일이면 코드 실행 위험 (COD-05와 연결)
- 의존성 관리: `requirements.txt`에 버전 고정·해시 없음(`--require-hashes` 미사용), `--index-url http://`, `--trusted-host`, `--extra-index-url`(의존성 혼동 공격), Git URL 의존성에 커밋 해시 미지정
- 다운로드 함수 반환값·HTTP 상태 확인 누락: `requests.get(url)` 후 `raise_for_status()` 없이 저장 (원문 C 예제 대응)

**보충 예제 — 취약 코드**
```python
import requests

# 원격 플러그인을 그대로 실행
code = requests.get("http://plugins.example.com/latest.py").text
exec(code)

# 바이너리를 받아 바로 실행
data = requests.get("https://downloads.example.com/agent").content
with open("/opt/agent", "wb") as f:
    f.write(data)
os.chmod("/opt/agent", 0o755)
subprocess.run(["/opt/agent"])
```

**보충 예제 — 안전 코드 (권장 기준)**
```python
import hashlib
import hmac

import requests

# 신뢰할 수 있는 채널에서 별도로 받은(또는 코드에 고정한) 기대 해시
EXPECTED_SHA256 = "3f2a...e9"  # 릴리스 노트/서명된 매니페스트의 값


def download_verified(url: str, expected_sha256: str, dest: str) -> None:
    resp = requests.get(url, timeout=30)  # HTTPS + 인증서 검증(기본값)
    resp.raise_for_status()               # 원문 C '반환값 확인' 대응
    digest = hashlib.sha256(resp.content).hexdigest()
    if not hmac.compare_digest(digest, expected_sha256):
        raise ValueError("무결성 검증 실패")
    with open(dest, "wb") as f:
        f.write(resp.content)
    os.chmod(dest, 0o700)


download_verified("https://downloads.example.com/agent", EXPECTED_SHA256, "/opt/agent")
# 가능하면 해시뿐 아니라 서명(SEC-10)까지 검증하고, 실행은 최소 권한 사용자로

# 의존성: pip install --require-hashes -r requirements.txt (pip-compile --generate-hashes)
```

**판정 기준 / 오탐 주의**
- 해시를 **같은 서버에서 같은 채널로** 받으면 서버가 변조되면 같이 변조된다. 기대값의 출처를 확인한다.

---

### SEC-16. 반복된 인증시도 제한 기능 부재

| 항목 | 내용 |
|---|---|
| 심각도 | 중간 |
| CWE | CWE-307 |
| 연관 설계항목 | SR2-2 |

#### KISA 소프트웨어 개발보안 가이드(2021) 원문

**개요 (2021 원문)**: 일정 시간 안에 여러 번 인증을 시도해도 계정잠금이나 추가 인증 같은 조치가 없으면, 공격자는 가능성 높은 ID·비밀번호 사전을 만들어 무차별 대입(brute-force)으로 로그인하고 권한을 얻는다.

**보안대책 (2021 원문)**: 인증시도 횟수를 **적절한 횟수로 제한**하고, 초과하면 **계정을 잠그거나 추가 인증**을 거치게 한다. (설계 SR2-2: 3~5회 이내, 실패 이력 로깅)

**2021 원문 예제 요지 (Java·C·C#)**: Java `while (result == FAIL)` 무제한 재시도 → `MAX_ATTEMPTS = 5` 카운터. C 동일. C# `OnLoginError`에서 아무것도 안 함 → `ViewState` 카운터로 3회 초과 시 비밀번호 복구 페이지로.

> 원문 C# 예제는 실패 횟수를 클라이언트 측 ViewState에 둔다. 이는 INP-15 관점에서 우회 가능하므로, Python에서는 **서버(DB/캐시)에 카운터를 저장**하는 것을 기준으로 한다.

#### Python 시큐어코딩 가이드(2023) 원문 — 2장 2절 16항 (p.117~119)

- **Python 관련 설명**: **Django는 사용자 인증 요청 횟수를 제어하지 않는다.** 무차별 대입을 막으려면 Django 플러그인 **`django-defender`** 또는 웹 서버 모듈로 요청을 제한한다.
- **안전한 코딩기법**: 최대 인증시도 횟수를 제한하고 초과 시 계정 잠금 또는 추가 인증을 거치게 한다. 코드상 횟수 제한 외에 **CAPTCHA나 Two-Factor 인증도 설계 시부터 고려**한다.
- **원문 예제**

```python
import hashlib

from .models import LoginFail

LOGIN_TRY_LIMIT = 5


# [가이드 원문] 안전하지 않은 코드 — 시도 제한 없음
def login(request):
    user_id = request.POST.get('user_id', '')
    user_pw = request.POST.get('user_pw', '')
    sha = hashlib.sha256()
    sha.update(user_pw.encode('utf-8'))
    hashed_passwd = get_user_pw(user_id)
    if sha.hexdigest() == hashed_passwd:
        return render(request, '/index.html', {'state': 'login_success'})
    return render(request, '/login.html', {'state': 'login_failed'})


# [가이드 원문] 안전한 코드 — 실패 횟수를 DB(LoginFail)에 기록, 5회 이상이면 잠금
def login(request):
    user_id = request.POST.get('user_id', '')
    user_pw = request.POST.get('user_pw', '')
    sha = hashlib.sha256()
    sha.update(user_pw.encode('utf-8'))
    hashed_passwd = get_user_pw(user_id)

    if sha.hexdigest() == hashed_passwd:
        LoginFail.objects.filter(user_id=user_id).delete()
        return render(request, '/index.html', {'state': 'login_success'})

    if LoginFail.objects.filter(user_id=user_id).exists():
        count = LoginFail.objects.get(user_id=user_id).count
    else:
        count = 0
    if count >= LOGIN_TRY_LIMIT:
        return render(request, "/account_lock.html", {"state": "account_lock"})
    LoginFail.objects.update_or_create(user_id=user_id, defaults={"count": count + 1})
    return render(request, "/login.html", {"state": "login_failed"})
```

- **검토 메모 (중요)**
  - 가이드 안전 예제는 **비밀번호 일치 여부를 잠금 확인보다 먼저** 검사한다. 그래서 잠긴 계정도 올바른 비밀번호를 맞히면 로그인되고 실패 기록이 지워진다. 즉, 잠금 이후에도 계속 대입할 수 있고 정답을 맞히는 순간 성공한다. **잠금 여부를 먼저 확인**하고, 잠금 해제 시간(쿨다운)을 두는 구조로 판정한다(이 스킬 SEC-16 안전 코드 참고).
  - 실패 카운트 갱신이 읽기-수정-쓰기라 동시 요청 시 카운트가 덜 올라갈 수 있다(TIM-01). `F('count') + 1` 원자적 갱신을 권고한다.
  - 비밀번호 비교에 솔트 없는 SHA-256을 쓴다(SEC-14 미충족).
  - Django 프로젝트면 `django-defender`(가이드 언급)나 `django-axes` 적용 여부를 확인한다.

#### 이 스킬의 점검 기준 (2021 가이드 + 실무 기준)

**탐지 패턴 (Python)**
- 로그인·OTP/2FA 검증·비밀번호 재설정·인증번호 확인·API 키 검증 엔드포인트에 실패 횟수 카운트, 계정 잠금, rate limit, CAPTCHA가 하나도 없음
- 카운터를 세션·쿠키(클라이언트)에만 저장 → 쿠키 삭제로 초기화
- 실패 횟수가 IP 단위로만 집계(분산 공격) 또는 계정 단위로만 집계(계정 잠금 DoS) — 둘을 조합했는지
- 로그인 실패 응답이 "아이디 없음"/"비밀번호 틀림"을 구분 (계정 열거)
- 실패 로그 미기록 (SR2-2 ②)

**보충 예제 — 취약 코드**
```python
@app.route("/login", methods=["POST"])
def login():
    user = User.query.filter_by(username=request.form["username"]).first()
    if user is None:
        return "존재하지 않는 아이디", 401           # 계정 열거
    if not user.check_password(request.form["password"]):
        return "비밀번호가 틀렸습니다", 401           # 시도 제한 없음
    login_user(user)
    return redirect("/")
```

**보충 예제 — 안전 코드 (권장 기준)**
```python
from datetime import datetime, timedelta, timezone

from flask_limiter import Limiter
from flask_limiter.util import get_remote_address

limiter = Limiter(get_remote_address, app=app, storage_uri=os.environ["REDIS_URL"])
MAX_ATTEMPTS = 5
LOCK_TIME = timedelta(minutes=15)


@app.route("/login", methods=["POST"])
@limiter.limit("10 per minute")  # IP 단위 제한
def login():
    username = request.form.get("username", "")
    user = User.query.filter_by(username=username).first()
    now = datetime.now(timezone.utc)

    if user and user.locked_until and user.locked_until > now:
        security_log.warning("locked login attempt user=%s ip=%s", username, request.remote_addr)
        return "로그인할 수 없습니다. 잠시 후 다시 시도하세요.", 429

    if user is None or not user.check_password(request.form.get("password", "")):
        if user:
            user.failed_count += 1                      # 계정 단위 카운터 (서버 DB)
            if user.failed_count >= MAX_ATTEMPTS:
                user.locked_until = now + LOCK_TIME     # 계정 잠금 (또는 CAPTCHA 요구)
            db.session.commit()
        security_log.warning("login failed user=%s ip=%s", username, request.remote_addr)
        return "아이디 또는 비밀번호가 올바르지 않습니다.", 401  # 동일 메시지

    user.failed_count = 0
    user.last_login_at = now
    db.session.commit()
    login_user(user)
    return redirect("/")
# Django: django-axes (AXES_FAILURE_LIMIT=5, AXES_COOLOFF_TIME=...)
```

**판정 기준 / 오탐 주의**
- 앞단 WAF·API 게이트웨이에서 rate limit을 하는 구조면 설정 근거를 확인한다. 코드만으로 확인할 수 없으면 "확인 필요"로 보고한다.
