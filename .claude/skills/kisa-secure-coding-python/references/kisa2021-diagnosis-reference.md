# KISA 소프트웨어 보안약점 진단가이드(2021) — 정적 보안 점검 레퍼런스

> 출처: KISA·행정안전부 「소프트웨어 보안약점 진단가이드」 2021.11 개정판 (설계단계 20개 + 구현단계 49개 항목)
> 용도: Claude Code 정적 보안 점검 시 **항목별 상세 기준**으로 참조. 실행 절차·보고 형식은 스킬의 `SKILL.md`와 `/kisa-review` 명령(`.claude/commands/kisa-review.md`) 참고.
>
> **이 스킬에서의 위치 (패키지 통합 시 추가)**
> - 이 파일은 **진단가이드(2021.11)** 기준의 언어 공통(Java·JSP·C·C#·일부 Python) 판정 기준이다. Python 판정 기준과 Python 가이드(2023) 원문은 `impl-1~3.md`에 있다.
> - 같은 항목을 볼 때: Python 코드 → `impl-*.md`를 먼저 읽고, **진단방법(정탐/오탐 조건) 근거**가 필요하거나 저장소에 Java·JS·C·Mapper XML 등 Python 외 코드가 있으면 이 파일의 해당 섹션을 읽는다.
> - ID 대응: `KISA21-IMPL-1.nn` = `INP-nn`, `2.nn` = `SEC-nn`, `3.nn` = `TIM-nn`, `4.nn` = `ERR-nn`, `5.nn` = `COD-nn`, `6.nn` = `ENC-nn`, `7.nn` = `API-nn` / `KISA21-SRx-y` = `SRx-y`
> - CWE 표기 차이: 6.01은 CWE-488 외에 CWE-543 추가, 7.01은 CWE-247(현재 CWE-350으로 대체된 구 번호), 7.02는 CWE-676 외 242·246·382 추가. 보고서에는 두 번호를 함께 적어도 된다.
> - 통째로 읽지 말고 `grep -n "KISA21-IMPL-1.01" references/kisa2021-diagnosis-reference.md`처럼 항목 위치를 찾아 그 섹션만 읽는다 (약 2,400줄).
> 표기: `(보충)` = 가이드 원문에 없는 내용을 정리자가 보충한 것 / `(가이드 원문 오류)` 등 = 원문의 오타·모순을 표시한 것. 판정 시 원문 기준을 우선하되, 보충 표기는 참고 수준으로 사용.
> ID 규칙: `KISA21-IMPL-{절}.{번호}` (구현단계), `KISA21-SR{x}-{y}` (설계단계). 다른 가이드를 추가할 때도 `{출처코드}-...` 형태를 유지하고 CWE로 교차 매핑한다.

## 목차
- [Part A. 구현단계 보안약점 (49개)](#part-a-구현단계-보안약점-49개)
  - 제1절 입력데이터 검증 및 표현 (1.01–1.17) · 제2절 보안기능 (2.01–2.16) · 제3절 시간 및 상태 (3.01–3.02) · 제4절 에러처리 (4.01–4.03) · 제5절 코드오류 (5.01–5.05) · 제6절 캡슐화 (6.01–6.04) · 제7절 API 오용 (7.01–7.02)
- [Part B. 설계단계 보안설계 기준 (20개)](#part-b-설계단계-보안설계-기준-20개)

---

# Part A. 구현단계 보안약점 (49개)

## 제1절 입력데이터 검증 및 표현

### KISA21-IMPL-1.01 SQL 삽입 (SQL Injection)

- **분류**: 입력데이터 검증 및 표현 · **CWE**: CWE-89 · **대상 언어(가이드 예제 기준)**: Java(JDBC, MyBatis/iBATIS, Hibernate, JDO, JPA/Persistence, Spring JdbcTemplate), JSP, C#
- **정의**: SQL 질의문 생성 시 검증되지 않은 외부 입력값을 문자열 결합(동적쿼리)으로 허용하여, 공격자가 쿼리 구조를 바꿔 DB 정보를 열람·조작할 수 있는 보안약점.

**탐지 대상**
- Source(외부입력): `request.getParameter`, C# `Request["..."]`, 메소드 인자로 전달된 외부값(예: `doPrivilegedAction(String username, ...)`), `props.getProperty(...)`(Properties 파일 `props.load(new FileInputStream(...))`로 읽은 값), JSP에서 받은 값을 DAO 인자(`"where projectid=" + pid`)로 넘기는 경우
- Sink(위험 지점):
  - JDBC: `Statement.executeQuery/execute/executeUpdate(sql)`, 결합된 문자열로 만든 `con.prepareStatement(query)` (PreparedStatement라도 문자열 결합이면 취약)
  - Spring: `JdbcTemplate.query(sql_, ...)` 등에 결합된 SQL 전달
  - MyBatis 3 Mapper XML: `${...}` / iBATIS(mybatis Data Map, sqlMap 2.0) XML: `$name$`
  - Hibernate: `session.createQuery("..." + name + "...")`
  - JDO: `PersistenceManager.newQuery(query).execute()` (SQL/JDOQL 문자열 결합)
  - J2EE Persistence(JPA): `EntityManager.createNativeQuery("..." + id)` → `getResultList()`
  - C#: `new SqlCommand(query, conn)` + `ExecuteReader()` 에 결합 문자열
- 그 밖에 찾아야 할 코드 신호: DAO 메소드가 `where`절 문자열 조각을 인자로 받아 `sql_ += " " + where;` 식으로 붙이는 구조(호출 측까지 추적 필요), 메시지소스/프로퍼티에서 가져온 SQL에 인자 결합, 테이블명 등 식별자를 외부값으로 결합

**취약 패턴**
- `"SELECT ... WHERE col = '" + input + "'"` 후 `Statement`/`prepareStatement(query)`/`createQuery`/`newQuery`/`createNativeQuery`/`SqlCommand` 로 실행
- PreparedStatement를 쓰지만 쿼리를 상수 문자열로 만들지 않고 외부값을 결합 (가이드 정탐 예: `"SELECT * FROM " + tableName + " WHERE Name ='" + name + "'"` → `prepareStatement(query)`)
- MyBatis `like '%${keyword}%'`, iBATIS `NAME = '$name$'`
- grep/정규식 힌트: `\$\{[^}]+\}` 및 `\$[A-Za-z_]+\$` in `*Mapper.xml`/sqlMap XML (ORDER BY 등 상수 치환에도 쓰여 과탐 가능); `(executeQuery|executeUpdate|execute|prepareStatement|createQuery|createNativeQuery|createSQLQuery|newQuery|SqlCommand)\s*\(\s*"[^"]*"\s*\+`; `(SELECT|INSERT|UPDATE|DELETE|WHERE)[^"]*"\s*\+\s*\w+` (문자열 결합 일반, 상수 결합도 걸려 과탐 가능)

**안전 패턴 / 조치 방법**
- 쿼리는 상수 문자열 + 바인딩 변수: JDBC `?` + `pstmt.setString(1, v)`; Hibernate `?` + `query.setString(0, v)` 또는 `:name` + `query.setParameter("name", v)`; MyBatis `#{keyword}` (예: `'%'||#{keyword}||'%'`); iBATIS `#name#`; C# `@ProductID` + `cmd.Parameters.AddWithValue(...)`
- PreparedStatement 사용 시에도 쿼리에 쓰이는 외부 입력값은 특수문자·쿼리 예약어 필터링
- Struts/Spring 등 프레임워크 사용 시 외부입력값 검증모듈·보안모듈을 상황에 맞게 적용

**판정 기준 (가이드 '진단방법' 기반)**
- 진단 절차: ① Statement 객체로 쿼리가 실행되는 부분 확인 → ② 그 객체가 PreparedStatement인지 확인 → ③ 쿼리에 쓰이는 변수가 외부 입력값이면 적절한 필터링 모듈 존재 여부 확인
- 취약(정탐)으로 판정: 외부 입력값이 쿼리 문자열에 결합되어 실행됨(Statement, 결합 문자열로 생성한 PreparedStatement, JdbcTemplate, `${}`/`$name$`, Hibernate/JDO/JPA 결합 쿼리, C# SqlCommand). 입력이 다른 함수(DAO) 인자를 거쳐 결합되는 경우도 추적하여 정탐. Properties 파일에서 읽은 값도 외부입력으로 간주
- 안전/오탐으로 판정: PreparedStatement를 상수 문자열로 생성하고 setString/setParameter 등으로 바인딩한 경우(기본적으로 안전), Hibernate `?`/`:name` 바인딩, 쿼리 생성 관련 외부 입력값에 필터링 모듈이 있거나 프레임워크에서 적절한 조치가 이루어진 경우

**예시**
```java
// 취약
String gubun = request.getParameter("gubun");
String sql = "SELECT * FROM board WHERE b_gubun = '" + gubun + "'";
ResultSet rs = con.createStatement().executeQuery(sql);
// 안전
PreparedStatement pstmt = con.prepareStatement("SELECT * FROM board WHERE b_gubun = ?");
pstmt.setString(1, gubun);
ResultSet rs = pstmt.executeQuery();
```

### KISA21-IMPL-1.02 코드 삽입 (Code Injection)

- **분류**: 입력데이터 검증 및 표현 · **CWE**: CWE-94, CWE-95 · **대상 언어(가이드 예제 기준)**: Java(javax.script), JSP/JavaScript, PHP
- **정의**: 프로세스가 외부 입력값을 코드로 해석·실행할 수 있어 공격자가 임의 코드를 삽입해 권한 탈취·인증 우회·시스템 명령 실행 등을 할 수 있는 보안약점. 프로그래밍 언어 자체 기능에 의해서만 제한된다는 점에서 운영체제 명령어 삽입과 구분된다.

**탐지 대상**
- Source(외부입력): `@RequestParam`, `request.getParameter`, `main(String[] args)`의 `args[]`, PHP `$_GET[...]`
- Sink(위험 지점):
  - Java: `ScriptEngineManager().getEngineByName("javascript")` → `ScriptEngine.eval(src)`
  - JavaScript(JSP 내): `new Function(<%=name%>)()`, `eval(...)`
  - PHP: `eval()`, 외부 입력을 기록한 파일을 `include()` (예: `fwrite`로 사용자 메시지를 파일에 저장 후 `include($MessageFile)`)
- 그 밖에 찾아야 할 코드 신호: eval을 감싼 유틸 함수(예: `ACC.executeScript(name)`)를 컨트롤러가 사용자 입력으로 호출하는 구조 — 호출 경로 추적

**취약 패턴**
- `scriptEngine.eval(src)` / `engine.eval("print('" + name + "')")` 에 외부값
- JSP 스크립틀릿 출력을 `new Function(...)` / `eval(...)`에 삽입
- PHP `eval('$myvar = ' . $_GET['arg'] . ';')` (공격 예: `?arg=1;system("cat /etc/passwd")`)
- PHP: 외부값을 필터링 없이 파일에 쓰고 그 파일을 `include`
- grep/정규식 힌트: `\.eval\s*\(`, `getEngineByName`, `new\s+Function\s*\(`, `\beval\s*\(`, PHP `\b(eval|include|require)(_once)?\s*\(` (상수 인자 사용 시 과탐)

**안전 패턴 / 조치 방법**
- 동적코드 실행 함수를 사용하지 않는다
- 필요 시 화이트리스트 방식: 허용된 값(예: `"UNDER_BAR"`, `"DOLLAR"`)일 때만 해당 메소드 호출, 그 외 예외
- 유효 문자만 허용하는 필터: 예 `if (!src.matches("[\\w]*")) throw new IllegalArgumentException();` (입력 형태에 맞게 정규식 조정)
- PHP: eval 전에 잠재적으로 위험한 기호 제거(`preg_replace`)

**판정 기준 (가이드 '진단방법' 기반)**
- 진단 절차: ① 언어별 동적실행 함수 사용 확인 → ② 동적코드 실행에 쓰이는 데이터가 신뢰할 수 있는 값인지 확인
- 취약(정탐)으로 판정: 실행 데이터가 신뢰할 수 없는 값(사용자 입력, 프로그램 실행 파라미터 args 등)이고 별도 검증절차가 없음. 다른 함수를 거쳐 eval에 도달해도 정탐
- 안전/오탐으로 판정: eval 전에 위험 기호를 제거(PHP `preg_replace`)하거나 검증 함수(예: `Filter.filterScript` — `[\w]*`만 허용)를 거치는 경우; 동적 실행 함수를 쓰지만 외부 입력값을 실행하지 않는 경우(예: 루프 인덱스로만 `eval("obj.test" + i + "=" + i)`)

**예시**
```java
// 취약
@RequestMapping("/execute")
public String execute(@RequestParam("src") String src) throws ScriptException {
    ScriptEngine se = new ScriptEngineManager().getEngineByName("javascript");
    return (String) se.eval(src);
}
// 안전
if (src.matches("[\\w]*") == false) throw new IllegalArgumentException();
String retValue = (String) se.eval(src);
```

### KISA21-IMPL-1.03 경로 조작 및 자원 삽입 (Path Traversal / Resource Injection)

- **분류**: 입력데이터 검증 및 표현 · **CWE**: CWE-22, CWE-99 · **대상 언어(가이드 예제 기준)**: Java(Servlet/Spring/JSP), C#, C
- **정의**: 시스템 자원 접근경로 또는 자원제어 명령어(파일명, 소켓 포트 등)에 검증되지 않은 외부 입력값을 허용하여, 보호된 자원에 무단 접근·수정·삭제, 정보누출, 자원 충돌로 인한 서비스 장애 등을 유발하는 보안약점.

**탐지 대상**
- Source(외부입력): `request.getParameter`, `@RequestParam`, `main`의 `args[0]`, C# `Request.QueryString[...]`, C `getenv("...")`, `props.getProperty(...)`(개별 프로퍼티 파일)
- Sink(위험 지점):
  - Java 파일: `new File(path)`, `new FileInputStream(...)`, `new FileReader(...)`, `FileOutputStream`, `ZipOutputStream` 등 파일 생성/압축 대상 경로
  - Java 자원: `new ServerSocket(port)` 등 소켓 포트
  - C#: `File.Delete(file)` 등 System.IO 파일 API
  - C: `fopen(filename, ...)`
- 그 밖에 찾아야 할 코드 신호: `response.setHeader("Content-Disposition", ...filename...)` 다운로드 로직, 외부값 + `getServletContext().getRealPath("/")` 결합, `replace('\\', FILE_SEPARATOR)`처럼 구분자만 치환하고 `..`은 제거하지 않는 처리, JSP → static 유틸 함수(예: `EgovFileCmprs.cmprsFile(source, target)`)로 넘어가는 경로

**취약 패턴**
- `"C:/datas/" + fileName`, `safeDir + helpFile`, `basePath + filename` 으로 만든 경로를 파일 API에 전달
- `.`, `/`, `\` 를 제거했더라도 `getRealPath("/") + filePath` 로 컨텍스트 루트 하위(WEB-INF 등 웹·서블릿 설정 파일)에 접근 가능 → 정탐
- 프로퍼티 값(`Integer.parseInt(props.getProperty("Service No"))`)으로 소켓 포트 결정
- grep/정규식 힌트: `new\s+(File|FileInputStream|FileOutputStream|FileReader|FileWriter|RandomAccessFile)\s*\([^)]*\+`, `getRealPath\([^)]*\)\s*\+`, `File\.(Delete|Open|ReadAll\w*|WriteAll\w*)\(`, `fopen\s*\(` (상수 경로 결합도 걸려 과탐 가능)

**안전 패턴 / 조치 방법**
- 외부 입력을 자원 식별자로 쓰면 검증하거나 사전 정의된 리스트(매핑표)에서 선택
- 파일명이면 경로순회 문자(`"`, `/`, `\`, `..`, `&` 등) 제거: 예 `replaceAll("\\.", "").replaceAll("/", "").replaceAll("\\\\", "")`, 또는 `helpFile.replaceAll("\\.{2,}[/\\\\]", "")` (null 체크 후)
- C#: `file.IndexOf('\\') > -1 || file.IndexOf('/') > -1` 이면 차단
- C: `regcomp(&regex, ".*\\.\\..*", 0)` + `regexec`로 `..` 탐지 시 오류 처리
- 시스템 경로는 직접 입력 대신 시스템 함수를 호출하여 생성

**판정 기준 (가이드 '진단방법' 기반)**
- 진단 절차(공통): 경로 생성·자원제어 코드에 외부 입력값이 쓰이는지 확인 → 쓰이면 적절한 필터링 또는 리스트 선택 여부 확인 → 시스템 경로를 시스템 함수로 생성하는지 확인
- [경로 조작] ① 파일 객체 사용 확인 → ② 그 파일에 외부에서 직접 접근하는지 확인. 경로순회 문자열 제거 없이 외부값이 경로에 쓰이면 취약
- [자원 삽입] ① 파일명·소켓 포트 등 자원 사용 확인 → ② 외부에서 직접 접근하는지 확인. 매핑표/리스트를 거치면 기본적으로 안전, 그 외는 취약. 식별자를 구성하는 외부 입력값에 검증 프로세스가 없으면 취약
- 취약(정탐)으로 판정: 위 조건 + 필터링 후에도 `getRealPath("/")` 결합으로 컨텍스트 경로 접근 가능; 구분자 치환만 하고 `..` 미제거; 개별(애플리케이션 전용) 프로퍼티에서 온 값 사용
- 안전/오탐으로 판정: `getRealPath()`, `getContextPath()` 등 내부 함수가 소스인 경우; 내부 설정 프로퍼티(`SystemierConfig.getPropertiesBean().getProperty(...)`)와 `FilenameFilter`로 고른 파일 목록에서 경로를 얻는 경우; 프레임워크의 시스템 프로퍼티 등 공용 프로퍼티에서 가져온 값(개별 사용 프로퍼티면 정탐)

**예시**
```java
// 취약
String fileName = request.getParameter("P");
fis = new FileInputStream("C:/datas/" + fileName);
// 안전
fileName = fileName.replaceAll("\\.", "").replaceAll("/", "").replaceAll("\\\\", "");
fis = new FileInputStream("C:/datas/" + fileName);
```

### KISA21-IMPL-1.04 크로스사이트 스크립트 (Cross-Site Scripting, XSS)

- **분류**: 입력데이터 검증 및 표현 · **CWE**: CWE-79 · **대상 언어(가이드 예제 기준)**: Java/JSP(JSTL, Spring), JavaScript, C#, C(CGI)
- **정의**: 사용자 브라우저에 검증되지 않은 외부 입력값을 출력하여 악의적인 스크립트가 열람자 권한으로 실행되게 하는 보안약점. Reflected(URL 파라미터가 응답에 반영), Stored(게시판·프로필 등으로 DB에 저장된 값이 출력), DOM 기반(서버를 거치지 않고 DOM 생성 중 실행) 3종.

**탐지 대상**
- Source(외부입력): `request.getParameter`, `request.getQueryString()`, `@ModelAttribute`로 바인딩된 VO의 getter(예: `apApsCommonCodeVO.getTarget()`), 사용자 입력 폼으로 저장된 DB 값(`rs.getString("title")`, 게시판 제목/내용/사용자 정보), C# `Request.QueryString[...]`, C `cgiFormString/cgiFromString`
- Sink(위험 지점):
  - JSP: `<%= var %>` (HTML 본문, 속성값 `value="<%=...%>"`, HTML 주석 `<!-- <%=param%> -->` 포함), EL `${m.content}` 직접 출력, `<c:out value="..." escapeXml="false"/>`, `out.println`
  - Servlet/Spring: `response.getWriter().print/write`, `PrintWriter.print(target)`
  - DOM: `document.write("..." + <%=name%>)`
  - C#: `Response.Write(str)` (가이드 예제 표기는 `Request.Write`)
  - C CGI: `fprintf(cgiOut, "...%s...", data)`
- 그 밖에 찾아야 할 코드 신호: `<script>`/`</script>` 문자열만 제거하는 블랙리스트 필터, DOM 출력에 HTML 엔티티 치환만 적용한 경우(`;`, `%`, `-` 미처리)

**취약 패턴**
- `검색어 : <%=keyword%>`, `<p>NAME:<%=name%></p>`, `<p>TITLE:<%=title%></p>`(DB값)
- `<c:out value="${param.name}" escapeXml="false" />`
- `param.replaceAll("<script>","")` 같은 불완전 필터 → `<sc<script>ript>`로 우회
- `<input type="hidden" name="nextUrl" value="<%=nextUrl%>" />` (nextUrl = `getRequestURL() + getQueryString()`)
- HTML 주석 안 출력 `<!-- <%=param%> -->` → `--><script>…</script>`로 탈출
- `document.write("name:" + <%=name%>)` — `< > & " ' /` 치환만 해도 `;) alert(document.cookie);<%--` 로 실행 가능 → 정탐
- grep/정규식 힌트: `<%=\s*\w+`, `escapeXml\s*=\s*"false"`, `document\.write\s*\(.*<%=`, `getWriter\(\)\.(print|write|println)\(`, `Response\.Write\(`, `fprintf\s*\(\s*cgiOut` (내부값 출력도 걸려 과탐 많음)

**안전 패턴 / 조치 방법**
- 출력 전 문자 치환: `&`→`&amp;`, `<`→`&lt;`, `>`→`&gt;`, `"`→`&quot;`, `'`→`&#x27;`, `/`→`&#x2F;`, `(`→`&#x28;`, `)`→`&#x29;`
- JSTL `<c:out value="${...}"/>`(escapeXml 기본 true) 또는 `${fn:escapeXml(...)}`
- 검증된 외부 라이브러리를 출력 상황별로 사용: NAVER Lucy-XSS-Filter, OWASP ESAPI, OWASP Java-Encoder(`Encoder.encodeForJS(Encoder.encodeForHTML(keyword))`)
- C#: AntiXss `Sanitizer.GetSafeHtmlFragment(str)`; C: 출력 전 `strchr(p,'<')`, `strchr(p,'>')` 등으로 위험 문자 검사
- HTML 태그를 허용하는 게시판은 허용 태그 화이트리스트
- DOM XSS 방지를 위해 `;`, `%`, `-` 등도 필터링 문자에 추가

**판정 기준 (가이드 '진단방법' 기반)**
- 진단 절차: ① 웹 페이지로 출력하는 변수값 존재 확인 → ② 그 값이 외부 입력값 또는 사용자 입력 폼으로 저장된 DB 값인지 확인 → 적절한 필터를 거치는지 확인
- 취약(정탐)으로 판정: 필터 없이 출력; `escapeXml="false"`; `<script>` 문자열만 제거하는 불완전 필터; HTML 주석 내부 출력; 쿼리스트링으로 만든 URL을 속성값에 출력; DOM(`document.write`) 출력에 `;`/`%`/`-` 미필터; Stored — 게시판 제목·내용·사용자 정보 등 입력 폼으로 저장된 DB 값 출력
- 안전/오탐으로 판정: 적절한 필터 후 출력 또는 프레임워크 자체 검증 기능 존재; `response.sendRedirect(request.getParameter("url"))`나 `location.href('<%=request.getParameter("url")%>')`처럼 URL로 이동만 하는 경우(XSS 관점 — 단 오픈 리다이렉트는 별도 항목); JSTL `<c:out>`(escapeXml 기본) 또는 `fn:escapeXml`; 출력값이 문자형이 아닌 경우(`Integer.parseInt`); `substring`으로 짧은 글자 수 이하로 제한된 경우; 출력값이 프로그램 내부에서 정해진 경우(예: 계산된 `p1.toText()`); 웹페이지가 아닌 `System.out.println` 콘솔 출력; 사용자 입력값이 아닌 경우(예: `request.getRequestURL()`); Stored — 메뉴 이름 등 사용자 입력으로 수정되지 않는 DB 값 출력 (DB 값이 사용자 입력으로 수정되는지는 정적도구로 판단이 어려우므로 데이터 출처를 수동 확인)

**예시**
```jsp
<%-- 취약 --%>
<% String keyword = request.getParameter("keyword"); %>
검색어 : <%=keyword%>
<c:out value="${param.name}" escapeXml="false" />
<%-- 안전 --%>
검색결과 : <c:out value="${m.content}"/>
document.write("keyword:" + <%=Encoder.encodeForJS(Encoder.encodeForHTML(keyword))%>);
```

### KISA21-IMPL-1.05 운영체제 명령어 삽입 (OS Command Injection)

- **분류**: 입력데이터 검증 및 표현 · **CWE**: CWE-78 · **대상 언어(가이드 예제 기준)**: Java, C#, C
- **정의**: 운영체제 명령어를 생성할 때 검증되지 않은 외부 입력값이 명령어의 일부 또는 전부로 사용되어 의도하지 않은 시스템 명령이 실행되고, 권한 변경이나 시스템 운영에 악영향을 줄 수 있는 보안약점.

**탐지 대상**
- Source(외부입력): `main`의 `args[]`(C `argv[]`), `request.getParameter`, `@ModelAttribute` VO 값, C# UI 입력(`PgmTextBox.Text`), `props.getProperty(...)`(개별 프로퍼티 파일), 스트림 입력
- Sink(위험 지점): Java `Runtime.getRuntime().exec(cmd | String[])`; C# `ProcessStartInfo.FileName = ...` + `Process.Start(...)`; C `system(cmd)` (snprintf로 조합), 기타 `exec()` 계열
- 그 밖에 찾아야 할 코드 신호: 명령 문자열을 만드는 유틸 함수(예: `getProcessId(processNm)` 내부 `"tasklist /fo table /nh /fi \"imagename eq " + processNm + "\""`)를 컨트롤러가 외부값으로 호출하는 경로

**취약 패턴**
- `Runtime.getRuntime().exec(args[0])` — 실행 프로그램 제한 없음
- `exec("cmd.exe /c backuplog.bat" + date)`, `exec(cmd + "c:\\prog_cmd\\" + version)` (version = 개별 프로퍼티 값)
- C: `snprintf(cmd, CMD_LENGTH, "cat %s", argv[1]); system(cmd);`
- grep/정규식 힌트: `Runtime\.getRuntime\(\)\.exec\(`, `ProcessBuilder\(`(보충), `Process\.Start\(`, `ProcessStartInfo`, `\bsystem\s*\(`, `\bpopen\s*\(`(보충), `exec[lv]p?e?\s*\(`(보충) (상수 명령도 걸려 과탐 가능)

**안전 패턴 / 조치 방법**
- 웹 인터페이스로 시스템 명령어를 전달하지 않도록 구성; 외부값을 검증 없이 명령어로 사용 금지
- 명령어 생성에 필요한 값을 미리 정의(화이트리스트)하고 외부 입력은 선택에만 사용: 예 `allowedCommands.contains(cmd)` 아니면 거부
- 멀티라인 지원 특수문자(`|`, `;`, `&`, `:`)와 리다이렉트 문자(`>`, `>>`) 제거/거부 (Java `replaceAll`, C 문자 단위 검사 후 `return -1`)
- C#: `Regex.IsMatch(fileName, ...)` 등 정규식/화이트리스트 검증 후 `Process.Start`

**판정 기준 (가이드 '진단방법' 기반)**
- 진단 절차: ① 운영체제 명령 실행 함수(`exec()`, `system()`, `Runtime.getRuntime().exec` 등) 호출 확인 → ② 외부 전달값이 명령어의 일부 또는 전부로 쓰이는지 확인
- 취약(정탐)으로 판정: 외부 입력(직접 또는 유틸 함수 인자 경유)이 명령 문자열 구성에 쓰이고 화이트리스트/검증 없음; 시스템 공용 프로퍼티가 아닌 개별 사용 프로퍼티 값으로 명령 구성
- 안전/오탐으로 판정: 정해진 후보군(White List)에서 선택하거나 적절히 검증한 경우; 프레임워크 시스템 프로퍼티(예: `EgovProperties.getPathProperty(Globals.SERVER_CONF_PATH, "SHELL."+Globals.OS_TYPE+...)`)에서 가져온 명령; 사용자 입력이 명령에 들어가지 않는 경우; 인자가 `srcFile.getName()` 결과처럼 파일 구분자나 `..`가 포함될 수 없는 값인 경우

**예시**
```java
// 취약
String cmd = args[0];
Process ps = Runtime.getRuntime().exec(cmd);
// 안전
List<String> allowedCommands = Arrays.asList("notepad", "calc");
if (!allowedCommands.contains(cmd)) { System.err.println("허용되지 않은 명령어입니다."); return; }
Process ps = Runtime.getRuntime().exec(cmd);
```

### KISA21-IMPL-1.06 위험한 형식 파일 업로드 (Unrestricted Upload of File with Dangerous Type)

- **분류**: 입력데이터 검증 및 표현 · **CWE**: CWE-434 · **대상 언어(가이드 예제 기준)**: Java(COS MultipartRequest, Spring MultipartFile), C#(ASP.NET FileUpload)
- **정의**: 확장자 등 파일 형식 검증 없이 업로드를 허용하여, 서버에서 실행 가능한 스크립트(asp, jsp, php 등)를 올리고 웹으로 직접 실행해 시스템 명령 실행·외부 연결 등 시스템 제어가 가능한 보안약점.

**탐지 대상**
- Source(외부입력): 업로드 파일명 — `MultipartRequest.getFilesystemName(...)`, `MultipartFile.getOriginalFilename()`, `MultipartHttpServletRequest.getFile(...)`, C# `FileUploadCtr.FileName`
- Sink(위험 지점): 업로드 저장 — `new MultipartRequest(request, savePath, ...)`(생성 시 저장), `file.transferTo(new File(path))`, `uploadDir.getAbsolutePath()+"/"+fileName` 로 저장 경로 구성, C# `FileUploadCtr.SaveAs(...)`
- 그 밖에 찾아야 할 코드 신호: 확장자 검사 존재 여부, 대소문자 정규화(`toLowerCase()`) 여부, 마지막 `.` 기준 확장자 추출(`lastIndexOf(".")`) 여부, 저장 파일명 랜덤화 여부, 저장 경로가 web document root(예: `/app/webapp/...`) 안인지, 실행 속성 제거 여부

**취약 패턴**
- 원본 파일명을 검증 없이 저장·사용(`getFilesystemName` → DB 저장 및 `Thumbnail.create(savePath+"/"+fileName, ...)`)
- `getOriginalFilename()`으로 얻은 이름의 확장자를 검사하지 않고 업로드 (확장자를 추출만 하고 검사하지 않는 경우 포함)
- 블랙리스트 + 대소문자 미구분: `!fileName.endsWith(".jsp")` → `JSP`, `Jsp`, `ASP`, `PHP`, `Php` 우회
- C#: `FileUploadCtr.SaveAs(Path.GetFileName(FileUploadCtr.FileName))` 무검증
- grep/정규식 힌트: `getOriginalFilename\(\)`, `getFilesystemName\(`, `transferTo\(`, `new\s+MultipartRequest\(`, `\.SaveAs\(`, `endsWith\("\.(jsp|asp|php)"\)` (검사 로직이 다른 파일/메소드에 있으면 과탐)

**안전 패턴 / 조치 방법**
- 화이트리스트 확장자만 허용, 마지막 `.` 기준 실제 확장자 추출 + 소문자 변환: `fileName.substring(fileName.lastIndexOf(".")+1).toLowerCase()` 후 `gif/jpg/png`만 허용
- 저장 시 파일명·확장자를 외부에서 추측할 수 없는 문자열로 변경(예: 키+타임스탬프 기반 `newName`)
- 저장 경로는 web document root 밖; 가능하면 실행 속성 제거
- C#: `PostedFile.ContentType == "image/jpeg"` 및 `PostedFile.ContentLength < 102400` 등 타입·크기 제한

**판정 기준 (가이드 '진단방법' 기반)**
- 진단 절차: ① 외부 입력값에서 파일명을 얻는 부분 확인 → ② 허용된 확장자만 업로드를 허용하는지 확인
- 취약(정탐)으로 판정: `getOriginalFilename()` 등으로 업로드하면서 확장자 검사 없음(가이드 정탐 예는 저장명을 `KeyStr + 타임스탬프 + fileKey`로 바꾸는데도 확장자 미검사를 이유로 정탐 처리 — 저장명 변경만으로 안전 판정하지 말고 확장자 검사를 우선 확인); 확장자 필터가 대소문자를 구분하지 않아(정규화 없음) 우회 가능
- 안전/오탐으로 판정: 제어문 등으로 허용된 파일만 업로드되는 경우; 업로드 파일명을 외부에서 알 수 없는 형태로 변경하는 경우; 확장자를 소문자화하여 금지 확장자 목록과 비교해 예외를 던지는 경우(가이드는 이 블랙리스트 비교도 안전 예로 듦); `getOriginalFilename()` 반환값을 저장·사용하지 않는 경우(예: 빈 값 여부만 확인하고 `file.getInputStream()` 처리)

**예시**
```java
// 취약
String fileName = file.getOriginalFilename();
String uploadFilePath = uploadDir.getAbsolutePath() + "/" + fileName;
// 안전
String fileExt = fileName.substring(fileName.lastIndexOf(".") + 1).toLowerCase();
if (!"gif".equals(fileExt) && !"jpg".equals(fileExt) && !"png".equals(fileExt)) {
    alertMessage("업로드 불가능한 파일입니다."); return;
}
```

### KISA21-IMPL-1.07 신뢰되지 않는 URL 주소로 자동접속 연결 (URL Redirection to Untrusted Site / Open Redirect)

- **분류**: 입력데이터 검증 및 표현 · **CWE**: CWE-601 · **대상 언어(가이드 예제 기준)**: Java(Servlet/JSP), C#(ASP.NET)
- **정의**: 사용자 입력값을 외부 사이트 주소로 사용해 자동 연결(리다이렉트)하면, 공격자가 요청을 변조해 피해자를 피싱 사이트 등 위험한 URL로 보낼 수 있다. (예: `http://bank.example.com/redirect?url=http://attacker.example.net`)

**탐지 대상**
- Source(외부입력): `request.getParameter(...)`, `request.getQueryString()`, `request.getAttribute(...)`(요청 유래 값), C# `Request["dest"]`
- Sink(위험 지점): Java `response.sendRedirect(url)`(JSP의 리다이렉트 래퍼 포함, 예: `se.sendRedirect(CP + action + ...)`), C# `Response.Redirect(url)`
- 그 밖에 찾아야 할 코드 신호: 리다이렉트 대상 화이트리스트(허용 URL 배열/맵) 존재 여부, 로컬 URL 검증 함수(`Url.IsLocalUrl`, 자체 `IsLocalUrl`) 존재 여부

**취약 패턴**
- 외부 입력을 그대로 또는 문자열 결합으로 리다이렉트 URL에 사용 (`sendRedirect(rd)`, `sendRedirect(CP + action + "?redirectCode=" + code)`)
- CR/LF 제거(`replaceAll("\r","")...`)만 하고 URL 자체 유효성(허용 목록) 검증이 없는 경우도 취약 (가이드 일반 진단 예)
- grep/정규식 힌트: `sendRedirect\s*\(`, `Response\.Redirect\s*\(` → 인자 출처 추적 필요 (상수/contextPath 결합은 과탐)

**안전 패턴 / 조치 방법**
- 자동 연결할 외부 사이트 URL·도메인을 화이트리스트로 관리하고 입력값이 목록에 있는지 확인
- 입력값을 URL이 아닌 인덱스/키로 받아 서버측 허용 목록에서 선택 (`rd = allowedUrl[Integer.parseInt(rd)]`, 예외 시 거부)
- C#: 로컬 URL 여부 검증 후 리다이렉트 — MVC 3 이상은 `System.Web.Mvc`의 `Url.IsLocalUrl` 사용, 또는 `Uri.TryCreate(url, UriKind.Absolute, ...)`로 호스트가 `Request.Url.Host`와 같은지 비교, 상대경로는 `http:`/`https:`로 시작하지 않고 `Uri.IsWellFormedUriString(url, UriKind.Relative)`인지 확인

**판정 기준 (가이드 '진단방법' 기반)**
- 진단 절차: ① 외부 사이트로 리다이렉션하는 함수/메소드(Java `response.sendRedirect`) 존재 확인 → ② 그 인자(url)가 외부 입력값인지 확인 → 외부 입력이면 유효값 검사 및 화이트리스트 관리 여부 확인
- 취약(정탐)으로 판정: 외부 입력값으로 URL을 이동하는 `sendRedirect(String url)` 사용 시(검증·화이트리스트 없음). 요청 attribute/parameter를 결합해 URL을 만드는 경우 포함
- 안전/오탐으로 판정: 인자가 외부 입력 변수가 아닌 경우; 유효값 검사 및 화이트리스트로 관리하는 경우; `response.sendRedirect(request.getContextPath() + "/login.do")`처럼 내장함수 `getContextPath()` + 상수 경로 조합

**예시**
```java
// 취약
String rd = request.getParameter("redirect");
response.sendRedirect(rd);
// 안전
String allowedUrl[] = { "/main.do", "/login.jsp", "list.do" };
try { rd = allowedUrl[Integer.parseInt(request.getParameter("redirect"))]; }
catch (NumberFormatException | ArrayIndexOutOfBoundsException e) { return "잘못된 접근입니다."; }
response.sendRedirect(rd);
```

### KISA21-IMPL-1.08 부적절한 XML 외부개체 참조 (XML External Entity Reference, XXE)

- **분류**: 입력데이터 검증 및 표현 · **CWE**: CWE-611 · **대상 언어(가이드 예제 기준)**: Java(JAXP DOM/SAX/StAX/Schema, JAXB, Spring MultipartFile), PHP
- **정의**: XML 문서의 DTD로 정의한 외부 엔티티를 서버 파서가 처리하도록 설정된 경우, 공격자가 삽입한 엔티티(`<!ENTITY xxe SYSTEM "file:///etc/passwd">`, `<!DOCTYPE foo SYSTEM "file:/dev/tty">`)로 서버 파일 접근, 자원 고갈(DoS), 인증 우회, 정보 노출이 발생한다.

**탐지 대상**
- Source(외부입력): 업로드 파일(`ServletFileUpload.parseRequest(request)`의 `FileItem`, Spring `@RequestParam MultipartFile` → `transferTo`), 수신 XML(`File receivedXml`), 외부에서 온 XML 문자열/스트림
- Sink(위험 지점):
  - `DocumentBuilderFactory.newInstance()` → `newDocumentBuilder().parse(...)`
  - `SAXParserFactory.newInstance()` → `newSAXParser().parse(...)`
  - `XMLInputFactory.newFactory()` → `createXMLEventReader(...)` (StAX)
  - `SchemaFactory.newInstance(...)` → `newSchema(...)`, `Schema.newValidator()` (Validator)
  - JAXB `Unmarshaller.unmarshal(document)` (외부 엔티티가 확장된 Document를 언마샬)
  - PHP `DOMDocument->loadXML($xml)`
- 그 밖에 찾아야 할 코드 신호: 파서 팩토리 생성 후 파싱 전까지 아래 보안 설정 호출이 있는지(없으면 취약)

**취약 패턴**
- 파서 팩토리를 기본 설정 그대로 생성해 신뢰할 수 없는 XML을 파싱
- grep/정규식 힌트: `DocumentBuilderFactory\.newInstance|SAXParserFactory\.newInstance|XMLInputFactory\.new(Factory|Instance)|SchemaFactory\.newInstance|loadXML\(` 후 같은 객체에 `setFeature|setAttribute|setProperty|libxml_disable_entity_loader` 존재 여부 확인 (상수 내부 리소스 파싱은 과탐 가능)

**안전 패턴 / 조치 방법**
- 로컬 정적 DTD를 사용하고, 외부 XML에 포함된 DTD를 완전히 비활성화. 불가하면 파서별 방식으로 외부 엔티티·외부 문서유형 선언 비활성화
- `DocumentBuilderFactory`:
  - `setFeature("http://apache.org/xml/features/disallow-doctype-decl", true)` (가이드 원문은 `featuresdisallow-...`로 오탈자)
  - `setFeature("http://xml.org/sax/features/external-general-entities", false)`
  - `setFeature("http://xml.org/sax/features/external-parameter-entities", false)`
  - `setFeature("http://apache.org/xml/features/nonvalidating/load-external-dtd", false)`
  - `setXIncludeAware(false)`, `setExpandEntityReferences(false)`
  - 또는 `setAttribute(XMLConstants.ACCESS_EXTERNAL_DTD, "")`, `setAttribute(XMLConstants.ACCESS_EXTERNAL_SCHEMA, "")`
- `SAXParser`: `parser.setProperty(XMLConstants.ACCESS_EXTERNAL_DTD, "")`, `setProperty(XMLConstants.ACCESS_EXTERNAL_SCHEMA, "")`
- `SchemaFactory` 또는 `Validator`: `setProperty(XMLConstants.ACCESS_EXTERNAL_DTD, "")`, `setProperty(XMLConstants.ACCESS_EXTERNAL_SCHEMA, "")`
- `XMLInputFactory`: `setProperty(XMLInputFactory.SUPPORT_DTD, false)`, `setProperty(XMLInputFactory.IS_SUPPORTING_EXTERNAL_ENTITIES, false)`
- PHP: `libxml_disable_entity_loader(true)` 후 `loadXML`, 이후 원래 값 복원

**판정 기준 (가이드 '진단방법' 기반)**
- 진단 절차: ① XML 파일을 파싱하는지 확인 → 신뢰할 수 없는 외부 입력 파일에 대해 외부 엔티티를 비활성화하는 코드가 있는지 확인
- 취약(정탐)으로 판정: 업로드 파일 등 사용자 입력 XML을 `DocumentBuilder.parse`/`SAXParser.parse` 등으로 파싱하면서 외부 엔티티 비활성화 설정이 없는 경우
- 안전/오탐으로 판정: 위 파서별 제한 설정(`ACCESS_EXTERNAL_DTD`/`ACCESS_EXTERNAL_SCHEMA`=`""`, `SUPPORT_DTD`=false, `IS_SUPPORTING_EXTERNAL_ENTITIES`=false, feature 설정 등)이 파싱 전에 적용된 경우

**예시**
```java
// 취약
DocumentBuilderFactory dbf = DocumentBuilderFactory.newInstance();
Document document = dbf.newDocumentBuilder().parse(xmlFile);
// 안전
DocumentBuilderFactory df = DocumentBuilderFactory.newInstance();
df.setAttribute(XMLConstants.ACCESS_EXTERNAL_DTD, "");
df.setAttribute(XMLConstants.ACCESS_EXTERNAL_SCHEMA, "");
Document document = df.newDocumentBuilder().parse(new InputSource(xml));
```

### KISA21-IMPL-1.09 XML 삽입 (XQuery / XPath Injection)

- **분류**: 입력데이터 검증 및 표현 · **CWE**: CWE-652 (XQuery Injection), CWE-643 (XPath Injection) · **대상 언어(가이드 예제 기준)**: Java(javax.xml.xquery XQJ, javax.xml.xpath, nux XQuery), C#(Saxon .NET XQuery, System.Xml.XPath)
- **정의**: 검증되지 않은 외부 입력이 XQuery/XPath 쿼리 문자열 생성에 사용되면 공격자가 쿼리 구조를 변경(`something' or '1'='1`, `x' or 'x'='x`)해 허가되지 않은 데이터 열람·인증 우회가 가능하다.

**탐지 대상**
- Source(외부입력): `props.getProperty(...)`, `request.getParameter(...)`, `args[]`(커맨드라인), C# `Request["..."]`, `UserTextBox.Text`/`PwdTextBox.Text`
- Sink(위험 지점):
  - Java XQuery: `XQConnection.prepareExpression(es)` → `XQPreparedExpression.executeQuery()` (`es`가 입력 결합 문자열)
  - Java XPath: `XPath.compile(query)` → `XPathExpression.evaluate(...)`, `XPath.evaluate("..." + input + "...", doc, XPathConstants.NODESET)`
  - C# XQuery(Saxon): `XQueryCompiler.Compile(...)` → `XQueryEvaluator.Run(...)`
  - C# XPath: `XPathNavigator.Evaluate(query)` / `Select(...)` (`StringBuffer.Append(input)`로 만든 쿼리)
- 그 밖에 찾아야 할 코드 신호: 쿼리 문자열의 `+` 결합 / `StringBuffer.append`로 입력 삽입, 필터링 함수 존재 여부

**취약 패턴**
- `"doc('users.xml')/userlist/user[uname='" + name + "']"`를 `prepareExpression`에 전달
- `xpath.compile("//users/user[login/text()='" + nm + "' and password/text()='" + pw + "']/home_dir/text()")`
- grep/정규식 힌트: `(compile|evaluate|prepareExpression|Evaluate|Compile)\s*\(.*\+` 또는 쿼리 변수에 `append(` — 상수만 결합하면 과탐

**안전 패턴 / 조치 방법**
- 특수문자·쿼리 예약어 필터링 + 파라미터화 쿼리 지원 XQuery 사용
- Java XQJ: 쿼리에 외부 변수(`$xname`) 사용 후 `expr.bindString(new QName("xname"), name, null)`
- Java XPath 대체: 외부 `.xq` 파일에 `declare variable $loginID as xs:string external;`로 파라미터화 쿼리 정의 → `new XQueryFactory().createXQuery(new File("login.xq"))`, `vars.put("loginID", nm)` 후 `xquery.execute(doc, null, vars)`
- C# XPath: `"/accounts/account[@acctID=$acctID]/email/text()"`를 `DynamicContext.Compile`로 컴파일하고 `ctx.AddVariable("acctID", ...)`, `expr.SetContext(ctx)`, `nav.Select(expr)`
- 파라미터화 불가 시 문자 제거 필터: `input.replaceAll("[',\\[]", "")` 또는 `name.replaceAll("[()\\-'\\[\\]:,*/]", "")` (C# 안전 예는 `squery.Replace('/','*')` 수준의 문자열 필터링 제시)

**판정 기준 (가이드 '진단방법' 기반)**
- 진단 절차(XQuery): ① XQuery 실행 부분(`executeQuery`) 확인 → ② 쿼리스트링에 쓰이는 변수가 외부 입력인지 확인 → 해당 변수 필터링 모듈 존재 확인
- 진단 절차(XPath): ① XPath 객체로 쿼리 스트링이 컴파일되는 부분(`xpath.compile`) 확인 → ② 쿼리스트링 변수가 외부 입력인지 확인 → 필터링 모듈 존재 확인
- 취약(정탐)으로 판정: 외부 입력이 XQuery/XPath 쿼리 문자열 생성 인자로 그대로 결합되고 필터링이 없는 경우(인증 우회·전체 데이터 출력 가능)
- 안전/오탐으로 판정: 필터링 모듈이 존재하거나 관련 프레임워크에서 적절히 조치(파라미터 바인딩 등)한 경우

**예시**
```java
// 취약
String es = "doc('users.xml')/userlist/user[uname='" + name + "']";
XQPreparedExpression expr = conn.prepareExpression(es);
// 안전
String es = "doc('users.xml')/userlist/user[uname='$xname']";
XQPreparedExpression expr = conn.prepareExpression(es);
expr.bindString(new QName("xname"), name, null);
XQResultSequence result = expr.executeQuery();
```

### KISA21-IMPL-1.10 LDAP 삽입 (LDAP Injection)

- **분류**: 입력데이터 검증 및 표현 · **CWE**: CWE-90 · **대상 언어(가이드 예제 기준)**: Java(JNDI), C#(System.DirectoryServices), C(OpenLDAP API)
- **정의**: 외부 입력을 적절한 처리 없이 LDAP 쿼리문(필터/DN/base)이나 결과의 일부로 사용하면, 공격자가 LDAP 명령문 구성을 바꿔(예: `*` 입력 → `(&(sn=S*)(userPassword=*))` 항상 참) 인증 우회나 정보 노출을 일으킬 수 있다.

**탐지 대상**
- Source(외부입력): `request.getParameter(...)`, `props.getProperty(...)`(외부 properties 파일 로드), 메소드 인자, C `getenv("Filter")`
- Sink(위험 지점):
  - Java JNDI: `DirContext.search(base, filter, sc)` / `ctx.search("ou=...", filter)` (`InitialDirContext`), 필터·base 인자에 입력 사용 (`BasicAttribute(...).getID()`를 인자로 넘기는 경우 포함)
  - C: `ldap_search_ext_s(ld, FIND_DN, LDAP_SCOPE_BASE, filter, ...)`
  - C#: `new DirectoryEntry(path)` (자격증명 없이 생성 = 익명 바인딩 후 `Children` 열거)
- 그 밖에 찾아야 할 코드 신호: 필터 문자열 `"(&(sn=" + x + ")..."`, `"(manager=" + x + ")"` 형태 결합; base(DN) 문자열에 입력 사용; 익명 바인딩

**취약 패턴**
- 외부 입력을 필터 문자열에 결합해 `search`에 전달
- 외부 입력으로 검색 base(루트 디렉터리)를 지정 → 임의 루트 접근, 접근제어 없으면 정보 누출
- C#: 인증하지 않은 익명 바인딩으로 LDAP 쿼리 실행
- grep/정규식 힌트: `\.search\s*\(` 및 `"\(\w+=" *\+`, `ldap_search(_ext)?(_s)?\s*\(`, `new DirectoryEntry\([^,)]*\)` (상수 필터는 과탐)

**안전 패턴 / 조치 방법**
- DN과 필터에 쓰이는 입력에서 특수문자 제거. 특수문자가 필요하면 `= + < > # ; \` 등이 명령이 아닌 일반문자로 인식되도록 처리(이스케이프)
- Java: 화이트리스트 정규식 검증 후 사용 — `if (!userSN.matches("[\\w\\s]*") || !userPassword.matches("[\\w]*")) throw new IllegalArgumentException(...)`
- C: 필터 문자열을 순회하며 `*`, `(`, `)` 등 공격 가능 문자 발견 시 중단, 또는 고정된 LDAP 쿼리 사용
- C#: `new DirectoryEntry(GetStrPath(), userSN, userPW)`로 인증 후 쿼리 (익명 바인딩 금지)

**판정 기준 (가이드 '진단방법' 기반)**
- 진단 절차: ① LDAP 조회 쿼리 실행(`search`) 확인 → ② 조회문 필터에 쓰이는 변수가 외부 입력인지 확인 → ③ 해당 변수 필터링 모듈 존재 확인
- 취약(정탐)으로 판정: 외부 입력(파라미터, 외부 properties 값 등)이 필터 문자열 생성에 여과 없이 사용(`"(name=" + name + ")"` → `*` 입력 시 항상 참); 외부 입력이 검색 base 문자열 생성에 사용되고 접근제어가 없는 경우
- 안전/오탐으로 판정: 필터링 모듈이 존재하거나 관련 프레임워크에서 적절히 조치한 경우

**예시**
```java
// 취약
String filter = "(&(sn=" + userSN + ")(userPassword=" + userPassword + "))";
NamingEnumeration<?> results = dctx.search(base, filter, sc);
// 안전
if (!userSN.matches("[\\w\\s]*") || !userPassword.matches("[\\w]*")) {
    throw new IllegalArgumentException("Invalid input");
}
String filter = "(&(sn=" + userSN + ")(userPassword=" + userPassword + "))";
NamingEnumeration<?> results = dctx.search(base, filter, sc);
```

### KISA21-IMPL-1.11 크로스사이트 요청 위조 (Cross-Site Request Forgery, CSRF)

- **분류**: 입력데이터 검증 및 표현 · **CWE**: CWE-352 · **대상 언어(가이드 예제 기준)**: Java(Servlet/JSP), C#(ASP.NET MVC Razor)
- **정의**: 서버가 요청이 사용자가 의도해 작성·전송한 것인지 확인하지 않으면, 공격자가 인증된 사용자(특히 관리자)의 세션으로 수정·삭제·등록 등 의도한 행위를 요청하게 할 수 있다. 정당성 입증 값이 고정되어 있고 GET으로 전달되면 더 쉽게 악용된다.

**탐지 대상**
- Source(외부입력): 상태 변경 요청 파라미터(`request.getParameter("level"/"group"/"id")` 등)
- Sink(위험 지점): 사용자 권한 변경, 신규 정보 등록, 게시물 삭제 등 주요 기능의 상태 변경 처리(예: `pstmt.executeUpdate()`로 `update member set level=?...`)
- 그 밖에 찾아야 할 코드 신호: CSRF 토큰 생성/세션 저장/hidden 필드/비교 로직 유무, C# `@Html.AntiForgeryToken()`(및 대응 검증) 유무, 상태 변경을 GET으로 처리하는지 여부, 중요 기능의 재인증 유무

**취약 패턴**
- 주요 기능 처리 시 권한확인/요청검증 절차가 없음 ("어떤 형태의 요청이든 기본적으로 CSRF 취약점을 가질 수 있음")
- 권한 확인이 세션쿠키, 사용자 IP, SSL 인증처럼 브라우저가 자동 제출하는 자격증명에만 의존
- grep/정규식 힌트: 상태 변경 핸들러(`executeUpdate`, `doPost`, `@PostMapping` 등)에서 `csrf|token|AntiForgery` 부재 확인 (보충: 프레임워크 전역 CSRF 필터 사용 시 과탐 가능)

**안전 패턴 / 조치 방법**
- 입력 폼은 GET보다 POST 사용, 폼과 처리 프로그램 사이에 토큰 사용, 중요 기능은 세션 검증 + 재인증 유도
- Java: 입력화면 요청 시 `session.setAttribute("SESSION_CSRF_TOKEN", UUID.randomUUID().toString())` → 폼에 `<input type="hidden" name="param_csrf_token" value="${SESSION_CSRF_TOKEN}"/>` → 처리 시 `request.getParameter("param_csrf_token")`와 세션 토큰을 비교, null이거나 불일치하면 거부
- C#: `Html.BeginForm(..., FormMethod.Post, ...)` 내부에 `@Html.AntiForgeryToken()` 사용

**판정 기준 (가이드 '진단방법' 기반)**
- 진단 절차: ① 사용자 권한변경, 신규정보 등록 등 주요 기능 확인 → ② 해당 기능 수행 시 권한확인 절차 존재 여부 확인
- 취약(정탐)으로 판정: 권한확인 절차가 없거나, 확인 방법이 세션쿠키·사용자 IP·SSL 인증 등 자동 제출되는 자격증명에 의존
- 안전/오탐으로 판정: 임의 토큰을 생성해 세션에 저장, hidden 필드로 전달하고 요청 파라미터 토큰과 세션 토큰이 일치할 때만 처리하는 경우

**예시**
```java
// 취약: 토큰 검증 없이 상태 변경
String sql = "update member set level=?, group=? where id=?";
pstmt.executeUpdate();
// 안전
String pToken = request.getParameter("param_csrf_token");
String sToken = (String) session.getAttribute("SESSION_CSRF_TOKEN");
if (pToken != null && pToken.equals(sToken)) { /* 정상 처리 */ } else { /* 오류 */ }
```

### KISA21-IMPL-1.12 서버사이드 요청 위조 (Server-Side Request Forgery, SSRF)

- **분류**: 입력데이터 검증 및 표현 · **CWE**: CWE-918 · **대상 언어(가이드 예제 기준)**: Java, PHP(cURL)
- **정의**: 검증되지 않은 입력을 서버 간 요청(다른 시스템 서비스 호출)에 사용하면, 공격자가 URL/요청을 위조해 접근통제를 우회하고 내부망 데이터 획득, 차단된 admin 페이지 접근, 클라우드 메타데이터(169.254.169.254) 크레덴셜 조회, 로컬 파일 열람(`file://`) 등을 할 수 있다.

**탐지 대상**
- Source(외부입력): `req.getParameter("url"/"host")`, 메소드 인자로 전달된 URL, `Properties.getProperty("connectUrl")`(위변조 가능한 properties 파일), PHP `$_GET['url']`
- Sink(위험 지점):
  - Java: `new URL(x).openConnection()` → `HttpURLConnection`, `new URL(x).openStream()`, URL을 받아 원격 내용을 가져오는 헬퍼(`getImage("http://" + host + "/favicon.ico")`, `getRemoteContent(url)`)
  - PHP: `curl_setopt($ch, CURLOPT_URL, $url)` + `curl_exec($ch)`
- 그 밖에 찾아야 할 코드 신호: 호스트/스킴 검증 유무, 화이트리스트(Map 키 매핑) 또는 내부 IP 블랙리스트 함수(`isPrivateIP`), `CURLOPT_FOLLOWLOCATION` 설정

**취약 패턴**
- 사용자 입력 URL로 직접 접속 (`new URL(req.getParameter("url")).openConnection()`)
- 사용자 입력을 host 부분에 결합 (`"http://" + host + "/favicon.ico"` → `host=192.168.176.1:8080/secrets.txt?`)
- 우회 페이로드 예: `http://site_example.com:x@192.168.0.45/...`(도메인 체크 우회), 단축 URL, 사설IP로 resolve되는 도메인, 10진/16진/8진/오버플로 IP 표기(`http://2852039166/`, `0xA9FEA9FE`, `0251.0376.0251.0376`), IDNA 변환(`ⓖⓞⓞⓖⓛⓔ.com`, `wordpreß.com`), broken parser(`https://evil-host#expected-host`, `https://expected-host@evil-host`), `file:///etc/passwd`, `ldap://localhost:1337/%0astats%0aquit`
- grep/정규식 힌트: `new URL\(.*\)\.(openConnection|openStream)`, `curl_setopt\(.*CURLOPT_URL`, `curl_exec` — 인자 출처 추적 필요

**안전 패턴 / 조치 방법**
- 식별 가능한 범위의 입력은 화이트리스트로 필터링: 사전 정의 URL을 `Map<String, URL>`에 두고 사용자에게는 키만 입력받아 `urlMap.get(key)` 사용
- 임의 URL을 받아야 하면 내부 URL/IP를 블랙리스트로 필터링(loopback `127.`/`0.`, `10.`, `172.16.`~`172.31.`, `192.168.`, `169.254.`, IPv6 `fc`/`fd`/`fe`/`ff`/`::1`), 스킴을 http/https로 제한, 호스트를 `gethostbyname`으로 해석해 메타데이터 IP 차단, 리다이렉트 추적 비활성(`CURLOPT_FOLLOWLOCATION` false)
- 동일 내부망이라도 기기 인증·접근권한 확인 후 요청 처리

**판정 기준 (가이드 '진단방법' 기반)**
- 진단 절차: ① 다른 시스템의 서비스를 호출하는 함수 존재 확인 → ② 호출 시 사용되는 입력값이 신뢰할 수 있는 값인지 확인
- 취약(정탐)으로 판정: 입력값이 신뢰할 수 없고 별도 검증 절차가 없음 — 요청 파라미터 URL/host, 추가 검증 없이 `openStream`에 전달되는 메소드 인자, properties에서 읽은 URL(다른 공격으로 위변조 가능하므로 취약)
- 안전/오탐으로 판정: 화이트리스트(Map 키) 방식; 메타데이터 IP(169.254.169.254) 및 스킴을 검증해 차단하는 경우; 내부 대역 IP 블랙리스트(`isPrivateIP`)로 차단하는 경우 — 단, 블랙리스트는 인코딩·IDNA·parser 우회 등 다양한 우회 공격을 감안해 필터링하는지 검토 후 판정

**예시**
```java
// 취약
URL url = new URL(req.getParameter("url"));
HttpURLConnection conn = (HttpURLConnection) url.openConnection();
// 안전
private Map<String, URL> urlMap;   // 사전 정의된 URL 목록
URL url = urlMap.get(req.getParameter("url"));
HttpURLConnection conn = (HttpURLConnection) url.openConnection();
```

### KISA21-IMPL-1.13 HTTP 응답분할 (HTTP Response Splitting)

- **분류**: 입력데이터 검증 및 표현 · **CWE**: CWE-113 · **대상 언어(가이드 예제 기준)**: Java(Servlet/JSP), C#(ASP.NET)
- **정의**: 요청 파라미터가 HTTP 응답헤더에 포함될 때 CR/LF 개행문자가 있으면 응답이 둘 이상으로 분리되어, 공격자가 두 번째 응답에 악성 코드를 주입해 XSS·캐시 훼손(Cache Poisoning)을 수행할 수 있다.

**탐지 대상**
- Source(외부입력): `request.getParameter(...)`, C# `Request.QueryString[...]`
- Sink(위험 지점):
  - Java: `response.setHeader(name, value)`(예: `Content-Disposition: attachment; filename=` + 입력), `response.addHeader`(보충), `new Cookie(name, value)` + `response.addCookie(c)`(Set-Cookie 헤더), `response.sendRedirect(url)`(Location 헤더에 URL 기록)
  - C#: `Response.AddHeader(name, value)`, 쿠키 설정
- 그 밖에 찾아야 할 코드 신호: `\r`, `\n` 제거 로직 유무

**취약 패턴**
- `res.setHeader("Content-Disposition", "attachment;filename=" + filename)` (filename이 요청 파라미터)
- `new Cookie("LASTLOGIN", lastLogin)` 후 `addCookie` (null/빈값 체크만 있고 개행 제거 없음)
- `Response.AddHeader("foo", "bar" + usrInput)`
- grep/정규식 힌트: `(setHeader|addHeader|AddHeader|sendRedirect)\s*\(.*\+`, `new Cookie\(` — 숫자/상수 값은 과탐

**안전 패턴 / 조치 방법**
- 요청 파라미터를 응답헤더(Set-Cookie 등)에 넣을 때 CR, LF 제거
- Java: `lastLogin = lastLogin.replaceAll("[\\r\\n]", "")` 후 쿠키/헤더 설정 (null 체크 병행)
- C#: `usrInput.Replace("\n", "").Replace("\r", "")` 후 `Response.AddHeader`

**판정 기준 (가이드 '진단방법' 기반)**
- 진단 절차: ① Response 헤더에 변수가 사용되는지 확인 → ② 변수가 외부 입력값인지 확인 → 개행문자(`\r`, `\n`) 제거 필터링/검증 절차 유무 확인
- 취약(정탐)으로 판정: 외부 입력이 `setHeader`, 쿠키 값, `sendRedirect` URL 등 헤더에 필터링 없이 사용
- 안전/오탐으로 판정: 개행문자를 필터링한 후 헤더/쿠키에 설정; `response.sendRedirect(request.getContextPath() + "/login.do")`(내장함수 context path + 상수); `Long`/`Integer` 등 숫자값을 문자열로 변환한 값(예: `response.setHeader("Content-Length", Long.toString(file.length()))`)은 `\r\n`이 포함될 수 없어 안전
- (가이드 일반 진단 예는 `URLEncoder.encode(fileid, "UTF-8")`로 인코딩된 값을 `Content-Disposition`에 사용하는 코드를 진단 대상으로 표시함 — 해당 예제의 판정 결론은 명시되지 않음)

**예시**
```java
// 취약
String lastLogin = request.getParameter("last_login");
Cookie c = new Cookie("LASTLOGIN", lastLogin);
response.addCookie(c);
// 안전
lastLogin = lastLogin.replaceAll("[\\r\\n]", "");
Cookie c = new Cookie("LASTLOGIN", lastLogin);
response.addCookie(c);
```

### KISA21-IMPL-1.14 정수형 오버플로우 (Integer Overflow)

- **분류**: 입력데이터 검증 및 표현 · **CWE**: CWE-190 · **대상 언어(가이드 예제 기준)**: Java, C#, C
- **정의**: 정수값이 허용 최대값을 넘어 아주 작은 수나 음수가 되는 현상으로, 반복문 제어·메모리 할당·메모리 복사 조건에 사용자 입력값을 쓰는 과정에서 발생하면 보안 문제를 유발한다(음수 배열 크기, 범위 밖 인덱스 접근 등).

**탐지 대상**
- Source(외부입력): `request.getParameter(...)` → `Integer.parseInt`, C# `Int32.Parse(args[0])`, C `atoi(argv[1])`, 메소드 인자로 전달된 크기 값
- Sink(위험 지점): 배열 크기 동적 결정(`new String[n]`, `new byte[n]`), 배열 인덱스 접근(`array[usrNum]`, `num_array[usr_num]`), 반복문 경계, 동적 메모리 할당/복사 크기
- 그 밖에 찾아야 할 코드 신호: 음수/상한 범위 체크 유무, C# `checked` 구문 및 `System.OverflowException` 처리 유무

**취약 패턴**
- `int param_ct = Integer.parseInt(tmp); String[] strArr = new String[param_ct];` (검증 없음)
- `string num = array[Int32.Parse(args[0])];`, `num = num_array[atoi(argv[1])];`
- 외부에서 전달된 크기 인자(`int parLine`)로 `new String[parLine]` 생성 후 반복문 사용
- grep/정규식 힌트: `new \w+\[\s*\w+\s*\]` 중 크기 변수가 `parseInt|Parse|atoi` 유래인지 추적 (상수/내부값은 과탐)

**안전 패턴 / 조치 방법**
- 언어·플랫폼별 정수 타입 범위를 확인해 사용, 정수 연산 시 결과 범위를 체크하는 모듈 사용
- 외부 입력을 동적 메모리 할당에 쓰면 적절한 범위인지 확인 — Java: `if (param_ct < 0) throw ...` 후 할당 (`NumberFormatException` 등 예외 처리)
- C#: `checked(Int32.Parse(args[0]))` + `catch (System.OverflowException)`, 인덱스 상한 검사(`if (usrNum < 3)`)
- C: `if (usr_num >= 0 && usr_num < 4)` 범위 확인 후 인덱싱

**판정 기준 (가이드 '진단방법' 기반)**
- 진단 절차: ① 변수로 배열 크기를 동적으로 결정하는지 확인 → ② 그 변수가 외부 입력인지 확인 → 의도한 범위 내인지 확인하는 절차 유무 확인
- 취약(정탐)으로 판정: 외부 입력값에 대한 범위 검증 없이 배열 크기/인덱스에 사용; 정수 값이 증가해 한계를 넘는 상황(아주 작은 값/음수)에 대한 검사 없이 진행
- 안전/오탐으로 판정: `InputStream.available()`처럼 int를 반환하는 API 결과로 크기 결정(정수 한계를 벗어난 값 불가); `request.getHeader("Referer")` 등 HTTP 헤더는 길이 한계가 있어 정수 한계 초과 불가; `args.length` 등 인자 개수가 정수 한계 이상일 가능성은 희박; 사용자 입력 등 외부 값이 아닌 경우

**예시**
```java
// 취약
int param_ct = Integer.parseInt(request.getParameter("slf_msg_param_num"));
String[] strArr = new String[param_ct];
// 안전
int param_ct = Integer.parseInt(tmp);
if (param_ct < 0) { throw new Exception(); }
String[] strArr = new String[param_ct];
```

### KISA21-IMPL-1.15 보안기능 결정에 사용되는 부적절한 입력값 (Reliance on Untrusted Inputs in a Security Decision)

- **분류**: 입력데이터 검증 및 표현 · **CWE**: CWE-807 · **대상 언어(가이드 예제 기준)**: Java(JSP/Servlet), C#(ASP.NET), C
- **정의**: 쿠키, 환경변수, 히든필드 등 조작 가능한 외부 입력을 신뢰해 인증·인가 등 보안 결정(보호 메커니즘)을 내리면, 공격자가 값을 조작해 보안을 우회할 수 있다. 충분한 암호화·무결성 체크가 없으면 외부 입력을 신뢰하면 안 된다.

**탐지 대상**
- Source(외부입력): `request.getCookies()`/`Cookie.getValue()`, hidden 필드 값(`request.getParameter("price")`), C# 쿠키(`HttpCookie`), C `getenv("server_addr")`
- Sink(위험 지점): 인증 여부 플래그 설정(`authenticated = true`), 가격·수량 등 중요 계산(`total = quantity * price`), 라이선스/인증 서버 연결 주소(`connect(sockfd, ...)`)
- 그 밖에 찾아야 할 코드 신호: 인증정보/인증여부를 평문 쿠키로 발급(`new Cookie("authenticated","1")`, `new HttpCookie("Authentificated","1")` + `Response.Cookies.Add`), `<input type="hidden" name="price">`

**취약 패턴**
- `if (c.getName().equals("authenticated") && Boolean.TRUE.equals(c.getValue())) authenticated = true;`
- 로그인 성공 후 `response.addCookie(new Cookie("user", username))`, `new Cookie("authenticated","1")` 평문 저장
- 서버가 보유한 단가를 클라이언트 hidden 필드로 받아 계산 (`Float.parseFloat(request.getParameter("price"))`)
- C: 환경 변수에서 인증 서버 주소를 읽어 연결 → 사용자가 주소를 바꿔 라이선스 검증 우회
- grep/정규식 힌트: `getCookies\(\)` 근처 `auth|admin|role|level`, `new (Http)?Cookie\(\s*"auth`, `getParameter\("price"\)`, `getenv\(` + `connect\(`

**안전 패턴 / 조치 방법**
- 상태정보·민감 데이터(특히 세션정보)는 서버에 저장하고 보안 확인도 서버에서 수행
- 보안 결정 값은 사용자 입력이 아닌 서버 내부 값 사용 — 가격은 `productService.getPrice(item)`처럼 서버 보유 정보로 계산, 사용자에게는 품목·수량만 입력받음
- 인증정보는 세션에 저장(C# `Session["Authentificated"] = "1"`), 쿠키에 저장해야 하면 암호화
- C: 인증 서버 주소를 환경 변수가 아닌 고정 정보로 설정(`inet_addr("127.0.0.1")`, 고정 포트)
- 신뢰할 수 없는 입력 진입점과 보안결정 입력값을 식별해 입력에 의존하지 않는 구조로 변경 검토

**판정 기준 (가이드 '진단방법' 기반)**
- 진단 절차: ① 인증 여부 확인에 쓰는 변수 확인 → ② 그 변수가 세션정보 등 서버 내부에서 검증된 값인지 확인
- 취약(정탐)으로 판정: 인증 결정 기준으로 외부 입력값(쿠키 등)을 그대로 사용; 평문으로 인증정보 및 "authenticated" 값을 쿠키에 저장
- 안전/오탐으로 판정: hidden 필드로 전송된 값을 사용하지 않고 서버에서 정해진 값(예: `price = 1000`)을 사용하는 경우; 세션 등 서버 내부 검증 값을 사용하는 경우

**예시**
```java
// 취약
price = request.getParameter("price");   // hidden 필드
total = Integer.parseInt(quantity) * Float.parseFloat(price);
// 안전
item = request.getParameter("item");
price = productService.getPrice(item);   // 서버 보유 가격
total = Integer.parseInt(quantity) * price;
```

### KISA21-IMPL-1.16 메모리 버퍼 오버플로우 (Improper Restriction of Operations within the Bounds of a Memory Buffer)

- **분류**: 입력데이터 검증 및 표현 · **CWE**: CWE-119 · **대상 언어(가이드 예제 기준)**: C
- **정의**: 연속된 메모리 공간에서 할당된 범위를 넘어선 위치를 읽거나 쓰면(스택/힙 버퍼 오버플로우) 프로그램 오동작이나 복귀주소 덮어쓰기를 통한 악성 코드 실행·권한 획득이 가능해진다.

**탐지 대상**
- Source(외부입력): 함수 매개변수 문자열, 사용자 제공 주소(`user_supplied_addr`)로 조회한 결과(`hp->h_name`), 표준입력(`gets`), 외부에서 결정되는 길이 값
- Sink(위험 지점): `gets()`(크기 무관 저장), `strcpy(buf, src)`, `memcpy(dst, src, n)`(잘못 계산된 n, 예: `sizeof(struct)`를 필드 복사에 사용), 인덱스/반복문을 통한 버퍼 직접 접근
- 그 밖에 찾아야 할 코드 신호: 복사 전 길이 비교 유무, 인덱스 음수 검사 유무, 상수 인덱스 접근, 문자열 끝 널 종료 여부

**취약 패턴**
- `char message[40]; gets(message);`
- `char buf[16]; strcpy(buf, string);` (입력 크기 검사 없음)
- `char hostname[64]; strcpy(hostname, hp->h_name);` (외부 입력 기반 호스트명은 64바이트 미만 보장 불가)
- `memcpy(cv_struct.x, SRC_STR, sizeof(cv_struct));` (필드 크기가 아닌 구조체 크기 → 인접 포인터 y 덮어쓰기) + 널 종료 미삽입
- 반복문 안에서 인덱스를 감소시키며 0 미만 검사 없음: `while (isspace(message[len])) { message[len] = '\0'; len--; }`
- grep/정규식 힌트: `\bgets\s*\(`, `\bstrcpy\s*\(`, `\bmemcpy\s*\(.*sizeof\(` (sizeof 대상이 목적지 버퍼와 일치하는지 확인), 루프 내 `--` 인덱스

**안전 패턴 / 조치 방법**
- 버퍼 크기를 적절히 설정하고 설정 범위 내에서만 읽고 쓰도록 통제
- 복사 크기는 대상 버퍼 기준: `memcpy(cv_struct.x, SRC_STR, sizeof(cv_struct.x));`
- 문자열은 버퍼 범위 내에 널 문자 삽입: `cv_struct.x[(sizeof(cv_struct.x)/sizeof(char))-1] = '\0';`
- 인덱스는 크기 비교뿐 아니라 0 이상인지 확인, 상수 인덱스 대신 버퍼 범위를 고려한 접근, 반복문 접근 시 경계값 확인

**판정 기준 (가이드 '진단방법' 기반)**
- 진단 절차: 버퍼에 값을 기록할 때 값의 크기가 대상 버퍼보다 작은지 확인 → 버퍼/데이터 크기가 외부 입력으로 결정되면 입력 크기가 대상 데이터를 충분히 포함할 수 있는지 확인 → 비교·인덱싱 시 음수 포함 여부(0보다 큰지) 확인 → 상수 인덱스 접근 시 상수값 확인 → 반복문 접근 시 경계값 확인 → 문자열 버퍼의 널 종료 확인
- 취약(정탐)으로 판정: 입력 크기 검사 없이 고정 크기 버퍼에 복사(`strcpy(buf, string)`); 외부 입력 유래 문자열을 고정 크기 버퍼에 복사; 루프에서 인덱스가 0 미만이 될 수 있는데 검사 없음(버퍼 범위 밖 참조)
- 안전/오탐으로 판정: 복사 크기가 대상 버퍼 크기로 제한되고, 인덱스 하한/상한이 모두 검사되며, 문자열이 버퍼 내에서 널 종료되는 경우

**예시**
```c
// 취약
void foo(char* string) { char buf[16]; strcpy(buf, string); }
memcpy(cv_struct.x, SRC_STR, sizeof(cv_struct));
// 안전
memcpy(cv_struct.x, SRC_STR, sizeof(cv_struct.x));
cv_struct.x[(sizeof(cv_struct.x)/sizeof(char))-1] = '\0';
```

### KISA21-IMPL-1.17 포맷 스트링 삽입 (Uncontrolled Format String)

- **분류**: 입력데이터 검증 및 표현 · **CWE**: CWE-134 · **대상 언어(가이드 예제 기준)**: Java, C
- **정의**: 외부 입력을 검증 없이 입·출력 함수의 포맷 문자열로 사용(또는 포맷 문자열 생성에 포함)하면, 공격자가 메모리를 읽거나 쓰고(특히 `%n`, `%hn`) 프로세스 권한으로 임의 코드를 실행할 수 있다. C에 국한되지 않으며 Java에서도 `%1$tY` 등으로 내부 정보가 노출된다.

**탐지 대상**
- Source(외부입력): `args[]`, 함수 인자(사용자 이름 등), 사용자 입력이 포함된 조합 문자열(`snprintf`로 만든 `msg`)
- Sink(위험 지점): C `printf`, `fprintf(stderr, msg)`, `snprintf`, `sprintf` 등 포맷 문자열 함수의 포맷 인자; Java `System.out.printf(args[0] + "...", c)`, (보충) `String.format`, `PrintStream.format`
- 그 밖에 찾아야 할 코드 신호: 포맷 인자가 리터럴인지, 포맷 지정자 개수와 실제 인자 개수 일치 여부, 출력 데이터 길이 한정 여부

**취약 패턴**
- 사용자 입력을 포맷 문자열에 결합: `System.out.printf(args[0] + " did not match! HINT: It was issued on %1$terd of some month", validDate);` → `%1$tY-%1$tm-%1$te` 입력 시 유효기간 노출
- 사용자 입력이 포함된 버퍼를 포맷 인자로 전달: `fprintf(stderr, msg);`
- grep/정규식 힌트: `\b(f|s|sn|v)?printf\s*\(\s*(stderr\s*,\s*)?[a-zA-Z_]\w*\s*[,)]` (포맷 위치에 리터럴이 아닌 변수), Java `printf\s*\(\s*[^"]`, `printf\(.*\+` — 상수 포맷 변수는 과탐

**안전 패턴 / 조치 방법**
- 사용자 입력을 포맷 문자열로 직접 쓰거나 포맷 문자열 생성에 포함하지 않음
- 가능하면 `%s` 포맷을 지정하고 사용자 입력은 2번째 이후 파라미터로 전달: `System.out.printf("%s did not match! HINT: It was issued on %2$terd of some month", args[0], validDate);`
- `%n`, `%hn`은 포맷 스트링 매개변수로 사용하지 않음
- 포맷 처리가 필요 없으면 비포맷 출력 함수 사용: `fprintf(stderr, msg)` → `fputs(msg, stderr)`
- 포맷에 출력할 데이터의 길이를 한정

**판정 기준 (가이드 '진단방법' 기반)**
- 진단 절차: 포맷 스트링 함수 사용 시 인자로 포맷 스트링이 포함되어 있는지 확인 → 외부 입력이 포맷 스트링 생성에 사용되는지 확인 → 포맷 지정자 개수와 매개변수 개수 일치 확인 → 출력 데이터 길이 한정 확인
- 취약(정탐)으로 판정: 위 안전 조건 외 모두 취약 — 포맷 스트링이 인자로 있더라도 사용자 입력이 포맷 스트링 생성에 사용되는 경우(`printf(args[0] + "...%1$terd...", c)`) 등
- 안전/오탐으로 판정: 포맷 스트링이 함수 인자로 포함되어 있고, 외부 입력이 포맷 스트링 생성에 사용되지 않으며, 포맷의 인자 개수와 매개변수 개수가 일치하는 경우 (출력 데이터 길이도 한정할 것)

**예시**
```c
// 취약
int ret = snprintf(msg, len, msg_format, user);
fprintf(stderr, msg);
// 안전
int ret = snprintf(msg, len, msg_format, user);
if (fputs(msg, stderr) == EOF) { /* 오류 처리 */ }
```


## 제2절 보안기능

### KISA21-IMPL-2.01 적절한 인증 없는 중요기능 허용 (Missing Authentication for Critical Function)

- **분류**: 보안기능 · **CWE**: CWE-306 · **대상 언어(가이드 예제 기준)**: Java(Spring MVC), C#(ASP.NET WebForms), JavaScript/JSP(클라이언트측 검사)
- **정의**: 적절한 인증 과정 없이 중요정보(금융정보, 개인정보, 인증정보 등)를 열람·변경할 수 있게 하는 보안약점. 클라이언트측 검사만 있으면 우회 가능.

**탐지 대상**
- Source(외부입력): `request.getParameter(...)`, `@ModelAttribute`/`@RequestParam`으로 바인딩된 요청 객체(예: `memberModel.getUserId()`), 폼 컨트롤 값(`UserName.Text`, `Password.Text`)
- Sink(위험 지점):
  - Java: 중요정보 변경/삭제 서비스·DAO 호출 — `service.modifyMember(...)`, `boardDao.delete(...)`, 계좌이체 `AccountManager.send(account)` 등
  - C#: `FormsAuthentication.RedirectFromLoginPage(...)` (자격인증 없이 호출 시)
  - JS/JSP: `<script>` 안에서 `if (${command.allowedIp} == false) { alert(...); history.back(-1); }` 같은 클라이언트측 권한 검사
- 그 밖에 찾아야 할 코드 신호: 중요정보 대상 정의(비밀번호, 주민등록번호·여권번호·외국인 식별번호, 카드번호·계좌정보, 게시글 수정·삭제 등), 세션 사용자(`session.getAttribute("userId")`)와 요청 대상 사용자의 일치 비교 누락, 계좌이체 등 고위험 기능의 재인증 누락

**취약 패턴**
- 세션의 로그인 사용자 ID와 요청 객체의 대상 사용자 ID를 비교하지 않고 회원정보 수정/삭제 수행
- `Membership.ValidateUser` 등 자격 검증 없이 `FormsAuthentication.RedirectFromLoginPage` 호출
- 재인증 없이 계좌이체 등 중요 기능 실행
- 인증/권한 검사를 JavaScript 등 클라이언트측에서만 수행
- grep/정규식 힌트: `RedirectFromLoginPage\(` (주변에 `ValidateUser` 없음 확인), `history\.back|alert\(.*권한` in *.jsp/*.html, `@RequestMapping` 핸들러 중 `modify|update|delete|transfer|send` 계열 (과탐 많음 — 반드시 수동 확인)

**안전 패턴 / 조치 방법**
- 클라이언트 보안검사를 우회해 서버에 접근하지 못하도록 서버측에서 인증 검사
- 중요정보 페이지(계좌이체 등)는 재인증 적용
- 로그인 사용자와 요청 사용자 일치 여부 확인 후에만 수정: `if (userId != null && requestUser != null && !userId.equals(requestUser)) { 에러 반환 }`
- C#: `if (Membership.ValidateUser(UserName.Text, Password.Text)) { FormsAuthentication.RedirectFromLoginPage(...); }`
- 검증된 라이브러리/프레임워크(OpenSSL, ESAPI 보안기능 등) 사용

**판정 기준 (가이드 '진단방법' 기반)**
- 진단 절차: ① 접근·사용이 제한되어야 하는 중요정보·기능(비밀번호, 개인정보, 금융정보, 게시글 수정·삭제 등)을 정의했는지와 그 사용 지점을 확인 → ② 중요정보 접근·변경 시 적절한 인증 여부를 확인하는 기능이 구현되어 있는지 확인. 정적도구로 판단이 어려워 진단원이 코드를 보며 중요정보 여부를 직접 판단.
- 취약(정탐)으로 판정: 중요정보 접근/변경 전 인증 여부 확인이 없음; 재인증 없이 계좌이체 수행; 클라이언트측(JavaScript)에서 인증 수행하여 우회 가능
- 안전/오탐으로 판정: 중요 기능 호출 전에 서버측에서 인증 여부를 확인함(예: `if(request.getSession().getAttribute("isLogin") == "logined") { boardDao.delete(...) }`)

**예시**
```java
// 취약
String userId = (String) session.getAttribute("userId");
if (service.modifyMember(memberModel)) { ... }   // 요청자-로그인 사용자 일치 확인 없음
// 안전
String requestUser = memberModel.getUserId();
if (userId != null && requestUser != null && !userId.equals(requestUser)) { mav.addObject("errCode", 1); return mav; }
if (service.modifyMember(memberModel)) { ... }
```

### KISA21-IMPL-2.02 부적절한 인가 (Improper Authorization)

- **분류**: 보안기능 · **CWE**: CWE-285 · **대상 언어(가이드 예제 기준)**: Java(Servlet, JNDI/LDAP), C#(ASP.NET MVC), C(OpenLDAP API)
- **정의**: 모든 가능한 실행경로에 대해 접근제어를 검사하지 않거나 불완전하게 검사하여, 비인가자가 중요자원에 접근할 수 있는 보안약점.

**탐지 대상**
- Source(외부입력): `request.getParameter("action")`, `request.getParameter("contentId")`, 함수 인자로 들어온 사용자명(`char *username`), LDAP 접속 파라미터(`sServiceProvider`, `sUid`, `sPwd`)
- Sink(위험 지점):
  - Java: 권한 확인 없는 `boardDao.delete(contentId)` 등 변경 작업; JNDI `env.put(Context.SECURITY_AUTHENTICATION, "none")` (익명 LDAP 바인딩)
  - C#: `[Authorize(...)]` 어트리뷰트 없는 관리용 `Controller` 클래스/액션 (예: `AdministrationController : Controller`)
  - C: 인증(`ldap_simple_bind_s`)·로그인 사용자 일치 확인 없이 `ldap_search_ext_s(...)` 호출
- 그 밖에 찾아야 할 코드 신호: 중요정보를 저장하는 외부시스템(웹서버, DB서버, LDAP 등) 식별, 역할별 권한(ACL) 정의 여부, JavaScript 등 클라이언트측 접근제어

**취약 패턴**
- `if (action.equals("delete")) boardDao.delete(...)` — 사용자 권한(ACL) 확인 없음
- 관리자 컨트롤러에 `[Authorize(Roles = "Administrator")]` 누락
- LDAP: `Context.SECURITY_AUTHENTICATION`를 `"none"`으로 설정(anonymous binding 허용), 또는 바인드 없이 검색
- grep/정규식 힌트: `SECURITY_AUTHENTICATION\s*,\s*"none"`, `class\s+\w*Admin\w*Controller\s*:\s*Controller` (위에 `[Authorize` 없는지 확인), `ldap_search(_ext)?_s\(` (같은 함수/흐름에 `ldap_(simple_)?bind` 없는지), `\.delete\(|\.remove\(` 근처 권한 체크 유무 (과탐 많음)

**안전 패턴 / 조치 방법**
- 정보·기능을 역할에 따라 배분해 공격노출면(Attack Surface) 최소화, 사용자 권한별 ACL 관리
- JAAS Authorization Framework, OWASP ESAPI Access Control 등 프레임워크 사용
- 세션 사용자 정보로 권한 확인 후 수행: `User user = (User)session.getAttribute("user"); if (... && checkAccessControlList(user, action)) { ... }`
- C#: `[Authorize(Roles = "Administrator")]`를 컨트롤러에 적용
- C: `ldap_simple_bind_s(ld, username, password) != LDAP_SUCCESS`면 실패 처리, `strcmp(username, getLoginName()) != 0`이면 실패 처리 후 검색

**판정 기준 (가이드 '진단방법' 기반)**
- 진단 절차: 중요정보를 저장할 수 있는 외부시스템 존재 여부 식별 → 해당 시스템 접근(열람)·변경(생성·삭제·수정) 권한이 사전 정의되었는지 확인 → ① 해당 정보/기능을 호출하는 함수에서 사전 정의 권한 소유 여부를 검사하는지 확인 → 접근제어가 서버측이 아닌 JavaScript 등 클라이언트측에서 이루어져 우회 가능한지 확인. 정적도구로 판단이 어려움.
- 취약(정탐)으로 판정: 권한 검사 없이 중요정보/기능 실행; LDAP 익명 인증(`"none"`) 사용으로 외부에서 임의 사용자 정보 접근 가능; 클라이언트측 접근제어만 존재
- 안전/오탐으로 판정: 세션 사용자 정보로 `checkAccessControlList(user, action)` 등 권한 확인 후에만 작업 수행

**예시**
```java
// 취약
env.put(Context.SECURITY_AUTHENTICATION, "none");   // 익명 LDAP 바인딩
if (action != null && action.equals("delete")) { boardDao.delete(contentId); }
// 안전
User user = (User) session.getAttribute("user");
if (action != null && action.equals("delete") && checkAccessControlList(user, action)) { boardDao.delete(contentId); }
```

### KISA21-IMPL-2.03 중요한 자원에 대한 잘못된 권한 설정 (Incorrect Permission Assignment for Critical Resource)

- **분류**: 보안기능 · **CWE**: CWE-732 · **대상 언어(가이드 예제 기준)**: Java, C#, C
- **정의**: 설정파일·실행파일·라이브러리 등 중요 자원에 의도치 않게 읽기/쓰기/실행 권한을 과다 부여하여 비인가 사용자가 자원을 사용·수정할 수 있는 보안약점.

**탐지 대상**
- Source(외부입력): 해당 없음(권한 설정 코드 자체가 점검 대상). 대상 자원 경로(예: `"/home/setup/system.ini"`, 업로드 파일, 설정파일)
- Sink(위험 지점):
  - Java: `File.setExecutable(true, false)`, `setReadable(true, false)`, `setWritable(true, false)` — 두 번째 인자 `false`(ownerOnly=false)면 모든 사용자에게 권한 부여; `Runtime.getRuntime().exec("umask 0")`
  - C#: `DirectorySecurity.AddAccessRule(new FileSystemAccessRule("everyone", FileSystemRights.FullControl, ..., AccessControlType.Allow))` + `SetAccessControl`
  - C: `umask(0)` 후 `fopen(..., "w")` 등 파일 생성
- 그 밖에 찾아야 할 코드 신호: 설정파일·문서파일에 실행 권한 부여 여부, 사용자 업로드 파일의 권한 정의 여부

**취약 패턴**
- `setXxx(true, false)` 형태로 전체 사용자 권한 부여
- `"everyone"` + `FullControl` 접근 규칙 추가
- `umask(0)` / `"umask 0"` (파일 rw-rw-rw-, 디렉토리 rwxrwxrwx)
- grep/정규식 힌트: `set(Executable|Readable|Writable)\(\s*true\s*,\s*false\s*\)`, `FileSystemAccessRule\(\s*"everyone"`, `umask\s*\(?\s*0+\s*\)?["\s;]` (umask 0/000만; 과탐 적음), (보충) `chmod.*777`

**안전 패턴 / 조치 방법**
- 설정파일·실행파일·라이브러리는 SW 관리자만 읽고 쓰도록 최소권한 설정
- Java: 단일 인자 `setExecutable(false)`, `setReadable(true)`, `setWritable(false)` 처럼 소유자 권한만 설정
- C#: 특정 계정(`Account`)·필요 권한(`Rights`)·`ControlType`만 지정한 `FileSystemAccessRule` 사용
- C: `umask(077)` — 소유자 외 권한 없음
- 중요 자원 사용 시 비인가 사용자 접근 가능 여부 검사

**판정 기준 (가이드 '진단방법' 기반)**
- 진단 절차: SW가 생성하는 중요자원(파일 등) 식별 → 사용자 업로드 파일·설정파일 등 중요자원에 대한 읽기/쓰기/실행 권한이 사전 정의되었는지 확인 → 정의대로 권한을 허용하는지 확인 → 설정파일·문서파일에 실행 권한이 설정되지 않았는지 확인. 중요자원 판단은 진단원이 직접 수행.
- 취약(정탐)으로 판정: 중요자원에 모든 사용자 권한(읽기/쓰기/실행) 부여, `umask 0`, 설정·문서 파일에 실행권한
- 안전/오탐으로 판정: 실행·쓰기 권한은 제외하고 읽기 권한만 소유자에게 부여(`setExecutable(false); setReadable(true); setWritable(false);`)

**예시**
```java
// 취약
File file = new File("/home/setup/system.ini");
file.setExecutable(true, false); file.setReadable(true, false); file.setWritable(true, false);
// 안전
file.setExecutable(false); file.setReadable(true); file.setWritable(false);
```

### KISA21-IMPL-2.04 취약한 암호화 알고리즘 사용 (Use of a Broken or Risky Cryptographic Algorithm)

- **분류**: 보안기능 · **CWE**: CWE-327 · **대상 언어(가이드 예제 기준)**: Java(JCA), C#(.NET Cryptography), C(OpenSSL EVP)
- **정의**: 취약하거나 표준화되지 않은(자체 구현) 암호 알고리즘, 또는 base64 같은 단순 인코딩으로 중요정보를 보호하려 해 기밀성을 보장할 수 없는 보안약점.

**알고리즘 기준(가이드 명시)**
- 취약: RC2, RC4, RC5, RC6, MD4, MD5, SHA1, DES (+ 자체 구현 알고리즘, 암호화 목적의 Base64)
- 안전(진단방법): SHA-256, AES, SEED, ARIA 등. 보안대책 본문은 DES·RC5 대체로 3DES, AES, SEED 언급. 업무·개인정보는 검증필 암호모듈 사용.
- [참고 표: 안전한 암호알고리즘 및 키 길이 — 암호알고리즘 검증기준 Ver 2.0(2012.3)] 최소 안전성 수준 112비트
  - 블록암호: ARIA(128/192/256), SEED(128)
  - 운영모드: 기밀성 ECB(원문 "ECD"), CBC, CFB, OFB, CTR / 기밀성·인증 CCM, GCM
  - 해시: SHA-224/256/384/512
  - MAC: HMAC(해시 기반), CMAC, GMAC(블록 기반)
  - 난수발생기: HASH_DRBG, HMAC_DRBG, CTR_DRBG
  - 공개키 암호: RSAES (공개키 2048, 3072), RSA-OAEP 해시 SHA-224/256
  - 전자서명: RSA-PSS, KCDSA, ECDSA, EC-KCDSA / 키 설정: DH, ECDH
  - 파라미터: RSA-PSS 2048, 3072; KCDSA·DH (공개키, 개인키) (2048,224), (2048,256); ECDSA·EC-KCDSA·ECDH: B-233, B-283, K-233, K-283, P-224, P-256

**탐지 대상**
- Source(외부입력): 설정파일 값(`prop.getProperty("password")` 등, Base64 정탐 케이스)
- Sink(위험 지점):
  - Java: `Cipher.getInstance("DES")` 등 취약 알고리즘 문자열, `MessageDigest.getInstance("SHA1")`, `MessageDigest.getInstance("MD5")`, `Base64.decode(...)`로 비밀번호 "복호화"
  - C#: `new DESCryptoServiceProvider()` (보충: RC2CryptoServiceProvider, MD5/SHA1 클래스도 동일 계열)
  - C(OpenSSL): `EVP_EncryptInit(&ctx, EVP_des_ecb(), ...)` 등 `EVP_des_*`
- 그 밖에 찾아야 할 코드 신호: 자체 구현 암호 함수(XOR, 치환 등), 설정파일에 Base64로 저장된 비밀번호

**취약 패턴**
- 취약 알고리즘명을 암호 API에 전달
- 암호화 목적으로 Base64 인코딩 사용
- 자체 구현 암호 알고리즘
- grep/정규식 힌트: `getInstance\(\s*"(DES|DESede?/ECB|RC2|RC4|ARCFOUR|RC5|RC6|MD4|MD5|SHA-?1)[/"]` (Java, 대소문자 무시), `DESCryptoServiceProvider|RC2CryptoServiceProvider|MD5CryptoServiceProvider|SHA1Managed`, `EVP_(des|rc2|rc4|rc5|md4|md5|sha1)\w*\(`, `Base64\.(decode|encode).*(pass|pwd)` (과탐 주의: MD5를 체크섬/UUID 용도로 쓰는 경우도 가이드는 정탐으로 봄)

**안전 패턴 / 조치 방법**
- 자체 알고리즘 개발 금지, 학계·업계 검증 표준 알고리즘 사용
- Java: `Cipher.getInstance("AES/CBC/PKCS5Padding")`, 해시는 `SHA-256` 이상
- C#: `new AesCryptoServiceProvider()`
- C: `EVP_EncryptInit(&ctx, EVP_aes_128_cbc(), key, iv)`
- 업무·개인정보에는 IT보안인증사무국 검증필 암호모듈 사용

**판정 기준 (가이드 '진단방법' 기반)**
- 진단 절차: 자체 구현 암호 알고리즘 사용 여부 확인(사용 시 취약, 단 암호전문가가 적절성을 보증하면 가능) → 언어 제공 암호 함수 호출 식별 후 알고리즘이 취약 목록(RC2, RC4, RC5, RC6, MD4, MD5, SHA1, DES 등)인지 확인
- 취약(정탐)으로 판정: 취약 알고리즘 사용(예: `MessageDigest.getInstance("SHA1")`, UUID 생성에 `"MD5"` 사용도 정탐); 자체 구현 알고리즘; 개발자가 **암호화 목적으로** Base64를 사용(예: 설정파일 비밀번호를 `Base64.decode` 후 DB 접속)
- 안전/오탐으로 판정: SHA-256, AES, SEED, ARIA 등 사용; Base64를 암호화가 아닌 가시성·보관성 목적으로 사용한 경우는 취약 암호화 알고리즘으로 보기 어려움

**예시**
```java
// 취약
Cipher c = Cipher.getInstance("DES");
MessageDigest md = MessageDigest.getInstance("SHA1");
// 안전
Cipher c = Cipher.getInstance("AES/CBC/PKCS5Padding");
MessageDigest md = MessageDigest.getInstance("SHA-256");
```

### KISA21-IMPL-2.05 암호화되지 않은 중요정보 (Cleartext Storage/Transmission of Sensitive Information)

- **분류**: 보안기능 · **CWE**: CWE-312(평문저장), CWE-319(평문전송) · **대상 언어(가이드 예제 기준)**: Java, C#(ASP.NET), C, 설정파일(web.config)
- **정의**: 개인정보·인증정보·금융정보 등 중요정보를 평문으로 저장하거나 송·수신하여 비인가자에게 노출될 수 있는 보안약점.

**탐지 대상**
- Source(외부입력): `request.getParameter("pwd")`, `getPassword()`, `MembershipUser.GetPassword()`, 소켓 `read(sock, buffer, ...)`, 설정파일 `fgets(passwd, ..., fp)`
- Sink(위험 지점):
  - 평문저장 — Java: `PreparedStatement.setString(..., pwd)` + `executeUpdate()` (해시/암호화 없이 DB 저장); C: `write(passFileD, password_buffer, n)`; 설정파일: `<connectionStrings>`에 `uid=...; pwd=...` 평문; 쿠키에 중요정보 저장
  - 평문 출력 — C#: `Response.Write(password)`
  - 평문전송 — Java: `new Socket(...)` 후 `PrintWriter.write(password)`; `new URL("http://...")` + `HttpURLConnection` 으로 중요정보 송신; C#: `MailMessage.Body`에 비밀번호 포함 후 `SmtpMail.Send`; C: 파일에서 읽은 비밀번호를 그대로 `SQLConnect(...)`에 사용
- 그 밖에 찾아야 할 코드 신호: 쿠키 `setSecure(true)` 누락, 중요정보 임시 변수/버퍼 사용 후 초기화 누락, URL에 민감정보 포함

**취약 패턴**
- 비밀번호/주민번호/카드번호 등을 해시·암호화 없이 DB·파일·쿠키에 저장
- 중요정보를 HTTP·평문 소켓·이메일로 전송
- grep/정규식 힌트: `new URL\(\s*"http://`, `connectionString=.*(pwd|password)=`, `new Socket\(` 근처 `write\(.*pass`, `Response\.Write\(.*[Pp]assword`, `new Cookie\(` 후 `setSecure` 부재 (과탐 가능, 데이터가 중요정보인지 수동 확인)

**안전 패턴 / 조치 방법**
- 중요정보 저장·전송 시 반드시 암호화; 비밀번호는 솔트 포함 SHA-256 해시로 저장 (`md.update(salt); md.digest(pwd.getBytes())`)
- 전송 전 AES 등 안전한 알고리즘으로 암호화(`Cipher.getInstance("AES/CBC/PKCS5Padding")`), 또는 SSL/HTTPS 보안 채널 사용
- 쿠키에 중요정보 저장 시 암호화 + `setSecure(true)`
- 비밀번호는 출력하지 않음(C#)
- 중요정보 읽기/쓰기 시 권한인증으로 적합 사용자만 접근
- 사용 완료된 임시변수/버퍼 값 초기화, 불필요한 참조 제거

**판정 기준 (가이드 '진단방법' 기반)**
- 평문저장 절차: 중요정보는 설계에서 결정되므로 일반 검사 기법은 없음. 로그인·암호 사용 등 특정 메소드의 인자값을 추적해 평문 여부 판단 → 임시 변수 저장 시 암호화 여부, 사용 후 초기화 여부 확인 → 쿠키에는 중요정보 미저장 또는 암호화 저장 확인
- 평문전송 절차: 민감정보 취급 여부 확인 → 네트워크 전송 시 암호화·보안채널 사용 여부 확인 → 민감정보 포함 URL 전송 시 암호화 확인 → 쿠키 전송 시 암호화 및 `setSecure(true)` 확인
- 취약(정탐)으로 판정: 소켓으로 받은 암호값을 암호화 없이 파일에 기록; 설정파일(`connectionStrings`)에 DB ID/비밀번호 평문; 비밀번호를 암호화 없이 소켓 전송; 중요정보 URL을 `http://` 일반 채널로 연결; 위 절차가 생략된 경우
- 안전/오탐으로 판정: 암호화/솔트 해시 후 저장, 암호화 후 전송 또는 보안채널 사용

**예시**
```java
// 취약
stmt.setString(2, pwd);           // 평문 비밀번호 DB 저장
URL u = new URL("http://www.secret.example.org/");
// 안전
MessageDigest md = MessageDigest.getInstance("SHA-256"); md.reset(); md.update(salt);
byte[] hashInBytes = md.digest(pwd.getBytes());   // 해시값을 저장
```

### KISA21-IMPL-2.06 하드코드된 중요정보 (Use of Hard-coded Password / Cryptographic Key)

- **분류**: 보안기능 · **CWE**: CWE-259(하드코드된 비밀번호), CWE-321(하드코드된 암호화 키) · **대상 언어(가이드 예제 기준)**: Java, C#, C
- **정의**: 비밀번호·암호화 키를 소스코드에 상수로 직접 코딩하여 소스 유출 시 중요정보가 노출되고 주기적 변경이 어려운 보안약점.

**탐지 대상**
- Source(외부입력): 해당 없음(소스 내 상수 문자열/바이트 배열이 점검 대상)
- Sink(위험 지점):
  - Java: `DriverManager.getConnection(URL, USER, PASS)`의 PASS가 상수(`private static final String PASS = "..."`), `new SecretKeySpec(key.getBytes(), "AES")`의 key가 상수 문자열, `byte[] privateKey = {...}` 상수로 `SecretKeySpec` 생성
  - C#: `new NetworkCredential(UserName, Password)`의 Password 상수, `TripleDESCryptoServiceProvider().CreateEncryptor(key, iv)`의 key/iv가 `new byte[] {0x43, ...}` 상수
  - C: `SQLConnect(..., password, ...)`의 `char *password = "password"`, `crypt(passwd, "salt")` 상수 솔트 + `strcmp(cpasswd, "68af...")` 하드코드된 해시 비교
- 그 밖에 찾아야 할 코드 신호: 로그인(식별·인증) 모듈의 사용자·관리자 비밀번호 상수, 내·외부 서버(업무서버, DB) 접속 모듈의 비밀번호 상수, 소스 내 "암호화된" 비밀번호 상수

**취약 패턴**
- 비밀번호/키/IV/솔트를 리터럴로 선언해 인증·암호화에 사용
- 암호화된 비밀번호라도 소스에 상수로 저장
- grep/정규식 힌트: `(?i)(pass(word)?|pwd|passwd|secret|key|iv|salt)\w*\s*=\s*"[^"]+"`, `SecretKeySpec\(\s*"`, `new byte\[\]\s*\{\s*0x`, `getConnection\([^)]*"[^"]*"\s*\)` (과탐: 알고리즘명 문자열·빈 문자열·테스트 코드)

**안전 패턴 / 조치 방법**
- 비밀번호는 암호화하여 별도 파일에 저장, 사용 시 복호화 (`props.getProperty("EncryptedPswd")` → `cipher.doFinal(...)`)
- 암호화 키는 외부 공간(파일)에 암호화하여 보관 후 복호화 사용 (`getPassword("./password.ini")` → `decrypt(key)`)
- C#: `SecureString`으로 Credential 생성, `GetKey/GetIV` 후 `Decrypt(...)`
- C: `getenv("password")`, `getenv("salt")` 등 외부에서 로드하여 비교

**판정 기준 (가이드 '진단방법' 기반)**
- 하드코드된 비밀번호 절차: 사용자·관리자 로그인 모듈에서 비밀번호가 소스에 직접 코딩되었는지 확인 → 내·외부 서버 접속 모듈에서 접속 비밀번호가 직접 코딩되었는지 확인. 별도 파일에 저장하지 않고 하드코딩되면 취약.
- 하드코드된 암호화 키 절차: ① DB 접속 등 비밀번호 사용 로직 확인 → ② 사용된 비밀번호의 암호화 여부 확인 → ③ 암호화된 비밀번호가 소스 내에 존재하는지 확인. 소스에 암호화된 비밀번호를 저장해도 취약.
- 취약(정탐)으로 판정: 상수 비밀번호로 `getConnection`; 암호화 키를 상수 배열로 정의해 `SecretKeySpec` 생성
- 안전/오탐으로 판정: 암호화 키가 아닌 **알고리즘명**만 상수로 지정한 경우(예: `new SecretKeySpec(key, "DESede")`)

**예시**
```java
// 취약
private static final String PASS = "SCOTT";
con = DriverManager.getConnection(URL, USER, PASS);
String key = "22df3023sf~2;asn!@#/>as"; new SecretKeySpec(key.getBytes(), "AES");
// 안전
String PASS = props.getProperty("EncryptedPswd");
PASS = new String(cipher.doFinal(PASS.getBytes()));
```

### KISA21-IMPL-2.07 충분하지 않은 키 길이 사용 (Inadequate Encryption Strength)

- **분류**: 보안기능 · **CWE**: CWE-326 · **대상 언어(가이드 예제 기준)**: Java, C#, C(OpenSSL)
- **정의**: 검증된 알고리즘이라도 키 길이가 짧으면 짧은 시간에 키를 찾아 암호문·비밀번호를 복호화할 수 있는 보안약점.

**키 길이 기준(가이드 명시)**
- 보안대책: RSA 2,048비트 이상, 대칭키 128비트 이상
- 진단방법: 대칭키(AES, ARIA, SEED 등) 128bit 이상, 해시(SHA 등) 128bit 이상, 공개키(RSA, DSA 등) 2,048bit 이상, ECC 256 이상
- 취약 예: RSA 1024, RSA 512

**탐지 대상**
- Source(외부입력): 해당 없음
- Sink(위험 지점):
  - Java: `KeyPairGenerator.getInstance("RSA")` + `keyGen.initialize(1024)` / `initialize(512)`
  - C#: `new RSACryptoServiceProvider(1024)`
  - C: `RSA_generate_key(512, 35, NULL, NULL)`
- 그 밖에 찾아야 할 코드 신호: (보충) `KeyGenerator.init(n)` 대칭키 길이, 키 크기 상수 정의

**취약 패턴**
- 공개키 2048 미만, 대칭키 128 미만, ECC 256 미만으로 키 생성
- grep/정규식 힌트: `\.initialize\(\s*(512|768|1024)\s*[,)]`, `RSACryptoServiceProvider\(\s*(512|768|1024)\s*\)`, `RSA_generate_key\(\s*(512|768|1024)\s*,` (키 크기가 변수/상수면 정의부 추적)

**안전 패턴 / 조치 방법**
- RSA 등 공개키: `keyGen.initialize(2048)`, `new RSACryptoServiceProvider(2048)`, `RSA_generate_key(2048, ...)` 이상
- 대칭키 128비트 이상

**판정 기준 (가이드 '진단방법' 기반)**
- 진단 절차: 사용 알고리즘 종류 확인 → 대칭키 ≥128bit, 해시 ≥128bit, 공개키 ≥2048bit(ECC ≥256)인지 확인
- 취약(정탐)으로 판정: 위 기준 미만 키 길이 사용(예: RSA `initialize(512)`)
- 안전/오탐으로 판정: 기준 이상 키 길이 사용

**예시**
```java
// 취약
KeyPairGenerator keyGen = KeyPairGenerator.getInstance("RSA");
keyGen.initialize(1024);
// 안전
keyGen.initialize(2048);
```

### KISA21-IMPL-2.08 적절하지 않은 난수 값 사용 (Use of Insufficiently Random Values)

- **분류**: 보안기능 · **CWE**: CWE-330 · **대상 언어(가이드 예제 기준)**: Java, C#, C, JavaScript
- **정의**: 예측 가능한 난수(고정 시드, 비암호학적 PRNG)를 세션ID·암호화키·인증키 등 보안결정에 사용하여 공격자가 다음 값을 예측할 수 있는 보안약점.

**탐지 대상**
- Source(외부입력): 해당 없음
- Sink(위험 지점):
  - Java: `Math.random()`, `new java.util.Random(100)`(고정 시드), 보안결정용 `new Random()`/`random.nextInt()`
  - C#: 보안결정용 `new Random()` / `rng.Next(...)`
  - C: 시드 없는 `rand()`
  - JavaScript: `Set_Cookie('SessionID', Math.random())`
- 그 밖에 찾아야 할 코드 신호: 생성된 난수의 용도 — 세션ID, 암호화 키, 인증키(authKey) 등 보안결정에 쓰이는지

**취약 패턴**
- `Math.random()` 사용
- 고정 시드 `new Random(상수)`
- 보안결정 값 생성에 `java.util.Random` / `System.Random` 사용
- C에서 `srand` 없이 `rand()` 사용
- grep/정규식 힌트: `Math\.random\(\)`, `new Random\(\s*\d+\s*\)`, `\brand\(\)` (C, `srand` 유무 확인), `new Random\(\)` 결과가 `session|token|key|auth` 변수로 흐르는지 (과탐 가능)

**안전 패턴 / 조치 방법**
- 보안결정(세션ID, 암호화키 등)에는 `java.security.SecureRandom` 사용 (예: `SecureRandom.getInstance("SHA1PRNG")`, `setSeed(secureRandom.generateSeed(128))`)
- C#: `System.Security.Cryptography.RNGCryptoServiceProvider().GetBytes(b)`
- 일반 용도 `java.util.Random`은 고정 시드 금지(기본 생성자 = 현재시간 기반, 또는 매번 변경되는 `setSeed`)
- C: `srandom(time(NULL))` 후 `random()` 사용(가이드 안전 예), `rand()` 사용 시 `srand()`로 매번 변경되는 시드 설정

**판정 기준 (가이드 '진단방법' 기반)**
- 진단 절차: ① `Math.random()` 사용 여부 확인 → 사용 시 취약 → ② 난수값을 세션ID 등 보안결정에 사용하는지 확인 → 보안결정에 `java.security.SecureRandom`을 사용하면 안전
- 취약(정탐)으로 판정: `Math.random()`으로 난수 생성(예: `(int)(Math.random() * scope)`); 세션ID에 `Math.random()` 사용
- 안전/오탐으로 판정: `java.util.Random`·`java.security.SecureRandom` 사용 시 복잡도가 상대적으로 높아 취약하지 않다고 봄(진단방법 기준); Date 요소 등으로 자체 랜덤 키 생성해 보완한 경우(`(r.nextLong()>>>1) % (endDate.getTimeInMillis() - beginDate.getTimeInMillis() + 1) + beginDate.getTimeInMillis()`) 안전. 단 코드예제 기준으로 고정 시드 `Random` 및 보안결정용 `Random`은 취약.

**예시**
```java
// 취약
Random random = new Random(100);                       // 고정 시드
String authKey = Integer.toString(new Random().nextInt()); // 보안결정에 Random
// 안전
SecureRandom secureRandom = SecureRandom.getInstance("SHA1PRNG");
secureRandom.setSeed(secureRandom.generateSeed(128));
```

### KISA21-IMPL-2.09 취약한 비밀번호 허용 (Weak Password Requirements)

- **분류**: 보안기능 · **CWE**: CWE-521 · **대상 언어(가이드 예제 기준)**: Java, JSP, C#, C
- **정의**: 비밀번호 생성·변경 시 강한 조합규칙(영문·숫자·특수문자, 길이 등)을 요구하지 않거나 빈 비밀번호를 허용하면 계정이 추측·무차별 대입에 취약해진다. KISA 「암호이용안내서」의 비밀번호 설정규칙을 적용해야 한다.

**탐지 대상**
- Source(외부입력): `request.getParameter("pass"/"passwd"/"password")` 등 회원가입·비밀번호 변경 폼 입력, 함수 인자로 전달되는 `char* pwd`
- Sink(위험 지점):
  - Java/JSP: 비밀번호를 담은 VO/엔티티를 저장하는 호출 — `registerDAO.register(userVO)`, `registDAO.regist(userVO)` 등 사용자 등록/비밀번호 변경 DAO·Service 메소드
  - C#: `new NetworkCredential(UserName, "")` (빈 비밀번호 리터럴)
  - C: 검증 없이 비밀번호를 그대로 쓰는 `mysql_real_connect(conn, host, id, pwd, ...)`
- 그 밖에 찾아야 할 코드 신호: 가입/비밀번호 변경 핸들러(`doPost`, `/join`, `/register`, `/changePassword` 등)에서 비밀번호 복잡도 검사 모듈(정규식 `Pattern.compile`, `checkValidationPwd()` 등)이 호출되는지 여부; 널(Null) 체크 존재 여부

**취약 패턴**
- 비밀번호 파라미터를 받아 Null 체크·자릿수·특수문자 포함 여부 검사 없이 바로 VO 생성 → 등록 DAO 호출
- 복잡도 검사가 있으나 조건이 약함(예: 길이만 4자 이상, 숫자만 허용 등)
- 빈 문자열 비밀번호 허용 (`NetworkCredential(user, "")`, `password == ""` 통과)
- grep/정규식 힌트: `NetworkCredential\([^,]+,\s*""\)`; 가입 컨트롤러에서 `getParameter\("pass` 이후 `Pattern|matches|valid` 부재 확인 (과탐 많음 — 로그인 로직과 구분 필수)

**안전 패턴 / 조치 방법**
- 비밀번호 생성·변경 시 강한 조건 검증 수행 후에만 저장/가입 승인. 숫자·영문자·특수문자 혼합, 주기적 변경 유도
- 가이드 제시 안전한 비밀번호 조합규칙(진단방법 ※참고):
  - 영문자(대·소 구별), 숫자, 특수문자를 조합
  - 비밀번호 길이는 8자리~10자리 이상
  - 특정 패턴 및 사용자 ID 등을 비밀번호로 사용 금지 등
- Java 예: `Pattern.compile("((?=.*[a-zA-Z])(?=.*[0-9@#$%]).{9,})")` + `matcher.matches()` 실패 시 "비밀번호 조합규칙 오류" 반환 (가이드 원문 정규식은 `. {9, }`로 공백 오타 있음 — 그대로 쓰면 동작 안 함)
- C: `checkValidationId(id) && checkValidationPwd(pwd)` 통과 시에만 `mysql_real_connect`
- C#: 빈 문자열 대신 검증된 `Password` 사용

**판정 기준 (가이드 '진단방법' 기반)**
- 진단 절차: 비밀번호 생성 또는 변경 시 입력값을 위 조합규칙으로 검사하는 모듈이 존재하는지 확인
- 취약(정탐)으로 판정: 사용자 계정 등록 등 비밀번호를 요구하는 정보 입력에서 Null 체크, 자릿수, 특수문자 포함 등 요구 조건이 **없거나 약한** 경우; 가입자 비밀번호 복잡도 검증 없이 가입 승인 처리
- 안전/오탐으로 판정: 로그인 시 입력 비밀번호를 받아 확인하는 코드(저장 목적이 아님); 설정파일(`props.getProperty("password")`)에서 읽어 `authenticate()`에 넘기는 등 저장이 아닌 **확인 목적** 사용

**예시**
```java
// 취약
String pass = request.getParameter("pass");
UserVo userVO = new UserVo(id, pass);
String result = registerDAO.register(userVO);   // 복잡도 검사 없음
// 안전
Pattern pattern = Pattern.compile("((?=.*[a-zA-Z])(?=.*[0-9@#$%]).{9,})");
if (!pattern.matcher(pass).matches()) return "비밀번호 조합규칙 오류";
String result = registerDAO.register(new UserVo(id, pass));
```

### KISA21-IMPL-2.10 부적절한 전자서명 확인 (Improper Verification of Cryptographic Signature)

- **분류**: 보안기능 · **CWE**: CWE-347 · **대상 언어(가이드 예제 기준)**: Java (Servlet, Spring MVC)
- **정의**: 프로그램·라이브러리·코드의 전자서명을 검증하지 않거나 검증 절차가 부적절하면 위변조된 파일(악성코드)이 실행될 수 있다.

**탐지 대상**
- Source(외부입력): 신뢰할 수 없는 곳에서 다운로드한 파일 경로(`downloadedFilePath`), 업로드 파일 — Commons FileUpload `uploader.parseRequest(request)` / `FileItem.write(file)`, Spring `@RequestParam MultipartFile` → `multipartFile.transferTo(f)`
- Sink(위험 지점): `new JarFile(f)` (서명 검증 플래그 없는 생성자), `new JarFile(f, true)` 후 `JarEntry.getCodeSigners()` 미검사, 생성된 JarFile을 사용하는 코드(`useDriver(driver)`, 클래스 로드 등)
- 그 밖에 찾아야 할 코드 신호: `jf.entries()` 순회 및 `getCodeSigners()` 결과의 null/길이·서명 주체 신뢰성 확인 존재 여부, 파일 출처 확인

**취약 패턴**
- `new JarFile(file)` — 1-인자 생성자(서명 검증 안 함)
- `new JarFile(file, true)`를 사용했지만 `JarEntry.getCodeSigners()`로 서명 주체를 검증하지 않음
- `getCodeSigners()`를 호출만 하고 null/빈 배열 여부 및 신뢰 주체 여부를 확인하지 않음
- grep/정규식 힌트: `new\s+JarFile\([^,()]+\)` (1-인자), `new JarFile\(.*,\s*true\)` 이후 `getCodeSigners` 부재 확인

**안전 패턴 / 조치 방법**
- 전자서명을 포함하는 파일은 항상 서명을 확인하고, 파일 출처를 확인하여 신뢰할 수 없는 곳에서 생성된 파일은 사용하지 않음
- `new JarFile(f, true)`로 서명 검증 활성화 → `jf.entries()` 순회 → 각 엔트리 내용을 끝까지 읽은 뒤(`readAll(jf.getInputStream(en), ...)`) `en.getCodeSigners()`로 서명 주체를 얻어 `signers != null && signers.length != 0` 및 신뢰할 수 있는 주체인지 확인

**판정 기준 (가이드 '진단방법' 기반)**
- 진단 절차: ① JarFile 생성 시 서명 여부를 확인하는 boolean 파라미터 생성자를 사용하는지 확인 ② `JarEntry.getCodeSigners()`로 전자서명 주체를 검증하는지 확인
- 취약(정탐)으로 판정: 업로드/다운로드 파일로 `new JarFile(file)` 생성 후 사용; `new JarFile(f, true)`를 쓰더라도 서명 주체 검증 코드가 없는 경우
- 안전/오탐으로 판정: `new JarFile(f, true)` + 엔트리별 `getCodeSigners()` 결과 검증(null/길이 체크 및 주체 확인)이 모두 있는 경우

**예시**
```java
// 취약
JarFile jf = new JarFile(f, true);   // 서명 주체 검증 없음
// 안전
JarFile jf = new JarFile(f, true);
for (Enumeration<JarEntry> e = jf.entries(); e.hasMoreElements();) {
    JarEntry en = e.nextElement();
    byte[] data = readAll(jf.getInputStream(en), en.getSize());
    CodeSigner[] signers = en.getCodeSigners();
    if (signers != null && signers.length != 0) { /* 신뢰 주체 확인 */ }
}
```

### KISA21-IMPL-2.11 부적절한 인증서 유효성 검증 (Improper Certificate Validation)

- **분류**: 보안기능 · **CWE**: CWE-295 · **대상 언어(가이드 예제 기준)**: C (OpenSSL), Java
- **정의**: 인증서를 확인하지 않거나 확인 절차가 부적절하면 악의적인 호스트에 연결되거나 신뢰할 수 없는 호스트의 데이터를 수신(중간자 공격)하게 된다.

**탐지 대상**
- Source(외부입력): 피어(서버/클라이언트) 인증서 — `SSL_get_peer_certificate(ssl)`, Java `X509Certificate`
- Sink(위험 지점):
  - C/OpenSSL: `SSL_get_verify_result(ssl)` 결과 처리, `X509_V_ERR_SELF_SIGNED_CERT_IN_CHAIN` 허용, `SSL_set1_host`/`SSL_set_hostflags` 누락, `SSL_set_verify(ssl, SSL_VERIFY_PEER, ...)` 누락
  - Java: `X509Certificate`의 `getIssuerDN()`/`getSubjectDN()` 비교, `verify(publicKey)`, `checkValidity()` 누락
- 그 밖에 찾아야 할 코드 신호: CRL/OCSP를 통한 해지 여부 확인, 안전한 암호 알고리즘 사용 여부 확인

**취약 패턴**
- `if (cert) { ... }` — 인증서 존재만 확인하고 검증 결과를 보지 않음
- `X509_V_OK` 이외의 값(예: `X509_V_ERR_SELF_SIGNED_CERT_IN_CHAIN`)을 허용 → 자체 서명 인증서 수용
- `SSL_get_verify_result(ssl)==X509_V_OK`만 확인하고 Common Name(호스트명) 일치 확인 없음 → 공격자가 CN을 자기 도메인으로 한 정상 인증서로 MITM 가능
- 신뢰되지 않은 발급기관 인증서 또는 유효기간 만료 인증서 허용
- grep/정규식 힌트: `X509_V_ERR_SELF_SIGNED_CERT_IN_CHAIN`, `SSL_get_peer_certificate` 근방에 `SSL_get_verify_result`/`SSL_set1_host` 부재

**안전 패턴 / 조치 방법**
- 인증서 사용 전 유효성 확인: CN과 실제 호스트 일치, 신뢰된 발급기관(CA, RootCA) 서명 여부, 유효기간, 해지 여부, 안전한 암호화 알고리즘 사용 여부
- C/OpenSSL: `SSL_get_verify_result(ssl)==X509_V_OK`만 허용 + `SSL_set_hostflags(ssl, X509_CHECK_FLAG_NO_PARTIAL_WILDCARDS)` + `SSL_set1_host(ssl, "기대호스트")` 실패 시 에러 + `SSL_set_verify(ssl, SSL_VERIFY_PEER, NULL)`
- Java: `toVerify.getIssuerDN().equals(signingCert.getSubjectDN())`, `toVerify.verify(signingCert.getPublicKey())`, `toVerify.checkValidity()`; 실패 시 `GeneralSecurityException` 처리하여 거부
- 해지 여부: CRL(인증기관에서 다운로드한 해지목록) 또는 OCSP 실시간 상태 확인

**판정 기준 (가이드 '진단방법' 기반)**
- 진단 절차: ① 인증서를 확인(획득)하는 코드 찾기 ② 검증 결과가 `X509_V_OK` 이외 값을 허용하는지 확인 ③ 인증서의 Common Name 확인 여부 확인
- 취약(정탐)으로 판정: 유효성 확인 없이 인증서 사용; 신뢰되지 않은 발급기관·만료 인증서 허용; `X509_V_OK` 외 값 허용; CN 미확인
- 안전/오탐으로 판정: `X509_V_OK`만 허용하고 `SSL_set1_host` 등으로 CN 확인, 피어 검증 활성화(가이드 '일반적인 진단의 예' 형태)

**예시**
```c
// 취약
cert = SSL_get_peer_certificate(ssl);
if (cert) { /* 인증서 검증 없이 작업 수행 */ }
// 안전
if (cert && SSL_get_verify_result(ssl) == X509_V_OK) {
    SSL_set_hostflags(ssl, X509_CHECK_FLAG_NO_PARTIAL_WILDCARDS);
    if (!SSL_set1_host(ssl, "www.securecoding_example.com")) return -1;
    SSL_set_verify(ssl, SSL_VERIFY_PEER, NULL);
}
```

### KISA21-IMPL-2.12 사용자 하드디스크에 저장되는 쿠키를 통한 정보 노출 (Information Exposure Through Persistent Cookies)

- **분류**: 보안기능 · **CWE**: CWE-539 · **대상 언어(가이드 예제 기준)**: Java (Servlet), C# (ASP.NET)
- **정의**: 만료시간이 긴 영속적 쿠키(Persistent Cookie)는 사용자 하드디스크에 저장되어 다음 브라우저 세션까지 남으므로, 여기에 세션ID·권한정보·개인/인증정보가 담기면 탈취 기회가 커진다.

**탐지 대상**
- Source(외부입력): 쿠키에 담기는 값 — 사용자 id, 세션ID, 권한등급, rememberme 플래그 등
- Sink(위험 지점):
  - Java: `new Cookie(name, value)` + `cookie.setMaxAge(긴 값)` + `response.addCookie(cookie)`
  - C#: `HttpCookie` + `cookie.Expires = DateTime.Now.AddMinutes(긴 값)` (또는 AddDays/AddYears 등) + `Response.Cookies.Add(cookie)`
- 그 밖에 찾아야 할 코드 신호: 쿠키 이름/값에 `id`, 세션ID, 권한, 비밀번호 등 중요정보 포함 여부

**취약 패턴**
- `setMaxAge(60*60*24*365)`, `setMaxAge(60*60*24*30*12)`, `setMaxAge(60*60*24*365*10)` 등 과도하게 긴 만료시간(가이드 예: 1년, 10년)
- C# `cookie.Expires = DateTime.Now.AddMinutes(60.0*24.0*365.0)` (1년)
- 영속 쿠키에 `new Cookie("id", "test123")`처럼 사용자 식별/중요정보 저장
- grep/정규식 힌트: `setMaxAge\(` 값 계산 결과가 큰 경우, `\.Expires\s*=\s*DateTime\.Now\.Add`; 상수식은 직접 계산해 기간 판단

**안전 패턴 / 조치 방법**
- 쿠키 만료시간은 세션 지속 시간을 고려해 기능에 맞춰 최소로 설정 (가이드 안전 예: Java `setMaxAge(60*60*24)` = 1일, C# `AddMinutes(10d)` = 10분)
- 영속 쿠키에는 사용자 권한 등급, 세션ID 등 중요정보를 포함하지 않음

**판정 기준 (가이드 '진단방법' 기반)**
- 진단 절차: ① 사용자 브라우저로 쿠키를 전송하는지(`addCookie`/`Cookies.Add`) 확인 ② 쿠키 유효기간 확인 ③ 쿠키 값에 id 등 중요정보 포함 여부 확인
- 취약(정탐)으로 판정: 만료시간이 과도하게 긴 경우(가이드 예: 1년) — 하드디스크에 저장되어 도용 가능; 영속 쿠키에 중요정보 포함
- 안전/오탐으로 판정: 만료시간을 기능에 맞춰 최소로 설정한 경우(가이드 오탐 예: rememberme 쿠키 `setMaxAge(60*60*24)`)
- (보충) 가이드는 구체적 허용 상한을 명시하지 않음 — 1일 이하는 오탐 예, 1년 이상은 정탐 예로 제시됨. 중간 값은 쿠키 용도·내용 기준으로 판단

**예시**
```java
// 취약
Cookie loginCookie = new Cookie("rememberme", "YES");
loginCookie.setMaxAge(60*60*24*365);
response.addCookie(loginCookie);
// 안전
loginCookie.setMaxAge(60*60*24);
```

### KISA21-IMPL-2.13 주석문 안에 포함된 시스템 주요정보 (Information Exposure Through Comments)

- **분류**: 보안기능 · **CWE**: CWE-615 · **대상 언어(가이드 예제 기준)**: Java, C#, C
- **정의**: 개발 편의로 주석에 ID·비밀번호 등 인증정보/시스템 주요정보를 적어두면, 소스코드 노출 시 주요정보도 함께 노출되어 쉽게 침입당한다.

**탐지 대상**
- Source(외부입력): 해당 없음 (소스코드 자체)
- Sink(위험 지점): DB 접속·관리자 로그인 등이 구현된 코드 주변 주석 — `DriverManager.getConnection(...)`, `customGetConnection(USER, PASS)`, `InitialContext.lookup()`/`DataSource.getConnection()`, 인증 비교 함수(`strncmp(ipasswd, ...)`) 등
- 그 밖에 찾아야 할 코드 신호: 주석 내 `password`, `passwd`, `pwd`, `비밀번호`, `root / ...`, `admin`, 암호화 전/후 값 쌍, DB sample 값 등

**취약 패턴**
- `// DB연결 root / a1q2w3r3f2!@` 처럼 계정/비밀번호를 주석에 기재
- `/* password is "admin" */`, `* Password for administrator is "tiger."`
- 암호화 전·후 값(평문 비밀번호와 해시/암호문)을 주석에 남김: `// 암호화 전, 후 : 1365ADMIN_01, aa84c4...`
- grep/정규식 힌트: `(//|/\*|\*|#|<!--).*(password|passwd|pwd|비밀번호|암호|root\s*/)` (대소문자 무시) — 단순 단어 매칭은 과탐 많음, 실제 값 포함 여부 확인 필요

**안전 패턴 / 조치 방법**
- 주석에 ID, 비밀번호 등 보안 관련 내용을 기입하지 않음
- 개발 중 남긴 계정·비밀번호 주석은 개발 완료 시 확실히 삭제; 불필요한 주석 삭제

**판정 기준 (가이드 '진단방법' 기반)**
- 진단 절차: ① DB 접속, 관리자 로그인 등이 구현된 코드 확인 ② 주석을 확인하여 암호(비밀번호) 포함 여부 확인
- 취약(정탐)으로 판정: 주석에 실제 비밀번호(또는 평문/암호문 쌍 등 인증정보)를 적어놓은 경우
- 안전/오탐으로 판정: 주석에 "password", "passwd", "비밀번호", "암호화" 등의 텍스트가 있으나 실제 내용이 비밀번호가 아닌 경우(예: `// 암호화` 설명 주석)

**예시**
```java
// 취약
// DB연결 root / a1q2w3r3f2!@
con = DriverManager.getConnection(URL, USER, PASS);
// 안전
// ID, 비밀번호 등의 중요 정보는 주석에 포함하지 않는다.
con = DriverManager.getConnection(URL, USER, PASS);
```

### KISA21-IMPL-2.14 솔트 없이 일방향 해쉬 함수 사용 (Use of a One-Way Hash without a Salt)

- **분류**: 보안기능 · **CWE**: CWE-759 · **대상 언어(가이드 예제 기준)**: Java, C#, C
- **정의**: 비밀번호 등을 솔트 없이 해시하여 저장하면 공격자가 레인보우 테이블 등 미리 계산된 해시값으로 원문을 복원할 수 있다.

**탐지 대상**
- Source(외부입력): 저장 대상 비밀번호/중요정보 (`password.getBytes()` 등)
- Sink(위험 지점):
  - Java: `MessageDigest.getInstance("SHA-256"/"SHA-512"...)` → `update(password.getBytes())` → `digest()` / `digest(password.getBytes("UTF-8"))` (솔트 `update` 없음)
  - C#: `SHA256CryptoServiceProvider().ComputeHash(source)` (솔트 미결합)
  - C: `MD5HashAlgorithm(data, hashedData, NULL)` 처럼 솔트 인자에 NULL 전달
- 그 밖에 찾아야 할 코드 신호: 해시 함수 시그니처에 salt 파라미터 존재 여부, 솔트 생성(암호학적 난수) 여부

**취약 패턴**
- `md.update(password.getBytes()); md.digest();` — 솔트 없는 단일 입력
- `digest.reset(); return digest.digest(password.getBytes("UTF-8"));`
- 해시 API의 salt 인자에 `NULL`/빈 값 전달
- grep/정규식 힌트: `MessageDigest\.getInstance` 사용 메소드 내 `update\(.*salt` 부재; `ComputeHash\(`; `Hash\w*\([^)]*NULL\s*\)`

**안전 패턴 / 조치 방법**
- 비밀번호와 솔트를 함께 해시함수에 입력하여 얻은 해시값을 저장
- Java: `md.update(password.getBytes()); md.update(salt); md.digest();`
- C#: `GenerateRandomCryptographicBytes(saltLength)`로 솔트 생성 후 원문에 결합하여 `ComputeHash` (가이드 C# 예제는 `AddRange(sourceWithSaltBytes)`로 솔트 대신 자기 자신을 추가하는 오류가 있음 — 실제로는 `AddRange(saltBytes)`)
- C: 솔트 값을 인자로 넘김 `MD5HashAlgorithm(data, hashedData, salt)`
- (보충) 안전한 해시 알고리즘을 인자로 사용(진단방법 ①) — MD5 등 취약 알고리즘은 KISA21-IMPL-2.04 참조

**판정 기준 (가이드 '진단방법' 기반)**
- 진단 절차: ① `getInstance`로 안전한 해시 알고리즘을 인자로 하여 `MessageDigest` 객체를 생성하는지 확인 ② 해시 값을 반환하기 전에 `update`로 솔트를 사용하여 해시하는지 확인
- 취약(정탐)으로 판정: `MessageDigest` 생성 후 솔트 없이 해시 값을 반환하는 경우
- 안전/오탐으로 판정: 해시 반환 전 솔트가 `update`(또는 입력 결합)로 함께 적용된 경우

**예시**
```java
// 취약
MessageDigest digest = MessageDigest.getInstance("SHA-512");
digest.reset();
return digest.digest(password.getBytes("UTF-8"));
// 안전
MessageDigest md = MessageDigest.getInstance("SHA-256");
md.update(password.getBytes());
md.update(salt);
byte[] byteData = md.digest();
```

### KISA21-IMPL-2.15 무결성 검사 없는 코드 다운로드 (Download of Code Without Integrity Check)

- **분류**: 보안기능 · **CWE**: CWE-494 · **대상 언어(가이드 예제 기준)**: Java, C#, C (WinINet)
- **정의**: 원격에서 소스코드·실행파일을 무결성 검사 없이 다운로드해 실행하면 호스트 서버 변조, DNS 스푸핑, 전송 중 코드 변조로 공격자의 악성 코드가 실행될 수 있다.

**탐지 대상**
- Source(외부입력): 원격 URL/파일 — `new URL(...)`, `URLConnection.getInputStream()`, C# `WebRequest.Create(url)`, `WebClient.DownloadData(url)`, C `InternetReadFile(m_hURL, ...)`
- Sink(위험 지점):
  - Java: `new URLClassLoader(classURLs)` + `Class.forName(name, true, loader)` (로드 전 체크섬/서명 검증 없음)
  - C#: `WebClient.DownloadData` 결과를 `FileStream.Write`로 저장 (무결성 검사 없음)
  - C: `InternetReadFile` 리턴값 확인 없이 `WriteFile(hFile, lpBuffer, ...)`
- 그 밖에 찾아야 할 코드 신호: 체크섬/해시 비교(`CheckIntegrity`), 공개키 서명 검증, 다운로드 코드 실행 권한 최소화

**취약 패턴**
- `URLClassLoader`로 원격/외부 경로 클래스를 로드하면서 체크섬·서명 비교 없음
- 다운로드 바이트를 검증 없이 파일로 저장/실행
- `InternetReadFile` 반환값 미확인 후 `WriteFile`
- grep/정규식 힌트: `new URLClassLoader\(`, `Class\.forName\([^)]*,\s*true,`, `DownloadData\(|DownloadFile\(`, `InternetReadFile\(` — 이후 해시/서명 검증 호출 부재 확인

**안전 패턴 / 조치 방법**
- DNS 스푸핑을 방어할 수 있는 DNS lookup 수행, 코드 전송 시 신뢰할 수 있는 암호 기법으로 코드를 암호화(서명), 다운로드 코드는 필요한 최소 권한으로 실행
- Java: 클래스 로드 전 체크섬을 실행·비교하여 변조 여부 확인; 가이드 예는 서버에서 Private Key로 암호화(서명)하고 클라이언트에서 Public Key로 복호화 후 `URLClassLoader`로 로드
- C#: 다운로드 후 저장 전에 해시 값 등으로 무결성 검사(`CheckIntegrity(fileData)`)
- C: `InternetReadFile` 리턴값을 확인(`if (result == true)`)한 뒤 `WriteFile` (가이드 예제 수준; (보충) 실제 무결성은 해시/서명 검증 필요)
- (참고) CERT SEC06-J: `URLClassLoader`/`java.util.jar`의 기본 자동 서명 검증에 의존하지 말 것

**판정 기준 (가이드 '진단방법' 기반)**
- 진단 절차: ① 클래스를 로드하기 위한 코드(`URLClassLoader`, `Class.forName(..., loader)`) 확인 ② 로드 전에 체크섬을 실행·비교하여 변조되지 않았음을 확인하는지 점검
- 취약(정탐)으로 판정: 로드하려는 클래스/다운로드 코드의 체크섬(또는 서명) 비교로 무결성을 확인하지 않는 경우
- 안전/오탐으로 판정: 로드·저장·실행 전 해시/체크섬 비교 또는 공개키 기반 서명 검증을 수행하는 경우

**예시**
```java
// 취약
URL[] classURLs = new URL[] { new URL("file:subdir/") };
URLClassLoader loader = new URLClassLoader(classURLs);
Class loadedClass = Class.forName("LoadMe", true, loader);
// 안전 (C#)
fileData = client.DownloadData(url);
CheckIntegrity(fileData);   // 해시 등으로 무결성 검사 후 저장
fs.Write(fileData, 0, fileData.Length);
```

### KISA21-IMPL-2.16 반복된 인증시도 제한 기능 부재 (Improper Restriction of Excessive Authentication Attempts)

- **분류**: 보안기능 · **CWE**: CWE-307 · **대상 언어(가이드 예제 기준)**: Java, C# (ASP.NET Login 컨트롤), C
- **정의**: 일정 시간 내 반복 인증 시도에 대해 계정잠금·추가 인증 등 조치가 없으면, 사전(Dictionary)·무차별 대입(brute force)으로 로그인 및 권한 획득이 가능하다.

**탐지 대상**
- Source(외부입력): 로그인 ID/비밀번호 입력 — 소켓 메시지(`getNextMsg`/`getNextMessage(socket, ...)`), 로그인 폼
- Sink(위험 지점):
  - Java: `while (result == FAIL) { ... result = verifyUser(username, password); }` (횟수 제한 없음)
  - C#: `OnLoginError(EventArgs e)` 오버라이드가 비어 있음(`//do nothing`)
  - C: `while (isValidUser == 0) { ... AuthenticateUser(nm, pw); }`
- 그 밖에 찾아야 할 코드 신호: 실패 카운터(`MAX_ATTEMPTS`, `count`, `LoginErrors`), 계정 잠금, 추가 인증(비밀번호 복구/CAPTCHA 등) 리다이렉트

**취약 패턴**
- 인증 함수(`verifyUser`, `AuthenticateUser`, `authenticate` 등)를 실패 시 무제한 반복 호출하는 루프
- 로그인 실패 이벤트 핸들러에서 아무 조치도 하지 않음
- grep/정규식 힌트: `while\s*\(\s*(result\s*==\s*FAIL|isValidUser\s*==\s*0)\s*\)`, `OnLoginError` 본문이 비어 있음; 웹 로그인 핸들러에서 실패 횟수 저장/조회 로직 부재

**안전 패턴 / 조치 방법**
- 인증 시도 횟수를 적절한 횟수로 제한하고, 설정된 실패 횟수 초과 시 계정 잠금 또는 추가 인증 과정을 거치게 함
- Java/C: `MAX_ATTEMPTS = 5` 정의, `while (result == FAIL && count < MAX_ATTEMPTS) { ...; count++; }`, 초과 시 FAIL 반환
- C#: `ViewState["LoginErrors"]`로 실패 횟수 누적, `ErrorCount > 3`이면 `Response.Redirect(Login1.PasswordRecoveryUrl)` 등 추가 절차
- (보충) ViewState 등 클라이언트 측 카운터는 우회 가능하므로 서버 측(계정/IP 단위) 카운터 권장

**판정 기준 (가이드 '진단방법' 기반)**
- 진단 절차: 인증 함수를 호출하는 경우, 해당 함수의 호출 횟수를 확인하고 호출을 제한하는 코드가 존재하는지 확인
- 취약(정탐)으로 판정: 인증 시도 횟수 검사 루틴 없이 반복문 안에서 계속 인증을 시도하는 경우 등, 호출 제한 코드가 없는 경우
- 안전/오탐으로 판정: 시도 횟수 카운터와 상한(및 초과 시 잠금/추가 인증)이 구현된 경우

**예시**
```c
// 취약
while (isValidUser == 0) {
    if (getNextMsg(socket, nm, NAME_SIZE) > 0 && getNextMsg(socket, pw, PSWD_SIZE) > 0)
        isValidUser = AuthenticateUser(nm, pw);
}
// 안전
int count = 0;
while ((isValidUser == 0) && (count < MAX_ATTEMPTS)) { /* ... */ count++; }
return isValidUser ? SUCCESS : FAIL;
```


## 제3절 시간 및 상태

### KISA21-IMPL-3.01 경쟁조건: 검사 시점과 사용 시점 (TOCTOU) (Time-of-check Time-of-use Race Condition)

- **분류**: 시간 및 상태 · **CWE**: CWE-367 · **대상 언어(가이드 예제 기준)**: Java, C#, C
- **정의**: 멀티프로세스/멀티스레드 환경에서 공유자원(파일, 소켓 등)의 상태를 검사하는 시점(TOC)과 사용하는 시점(TOU)이 달라, 그 사이 다른 프로세스가 자원 상태를 바꾸면 동기화 오류·교착상태 등이 발생하는 보안약점.

**탐지 대상**
- Source(외부입력): 해당 없음 (외부입력보다 공유자원에 대한 동시 접근이 핵심)
- Sink(위험 지점):
  - Java: `File.exists()` 검사 후 `new FileReader(f)` / `new FileOutputStream(...)` / `f.delete()` 등 사용, `Thread` 상속·`run()` 내부에서 같은 파일을 읽기/삭제하는 스레드를 동시에 `start()`
  - C#: `File.Exists(f)` 검사 후 `File.ReadAllLines(f)` 등 사용
  - C: `access(file, W_OK)` 검사 후 `fopen(file, "w+")`; lock 없이 공유 전역변수 갱신(`account += amount`, `account -= amount`, `static volatile` 변수 포함)
- 그 밖에 찾아야 할 코드 신호: 공유자원(파일/폴더, 소켓, 드라이버 등)을 여러 스레드/프로세스가 접근하는 구조, `synchronized`·mutex·`[MethodImpl(MethodImplOptions.Synchronized)]` 등 동기화 구문의 부재

**취약 패턴**
- 같은 파일명을 대상으로 한 스레드는 `exists()` 후 읽기, 다른 스레드는 `exists()` 후 `delete()`를 동기화 없이 수행
- C의 `access()` → `fopen()` 순서 (검사와 사용 사이 race window)
- 공유 변수에 대한 read-modify-write를 lock 없이 수행 (`volatile`만으로는 원자성 보장 안 됨)
- grep/정규식 힌트: `\.exists\(\)|File\.Exists\(|\baccess\s*\(` 이후 근접 라인의 open/delete 호출 (단일 스레드 코드에서 과탐 많음 → 동시 접근 가능성 확인 필요)

**안전 패턴 / 조치 방법**
- 공유자원 접근 구간을 동기화 구문으로 감싸 한 번에 하나의 프로세스/스레드만 접근하도록 함: Java `synchronized(LOCK) { ... }`, C# `[MethodImpl(MethodImplOptions.Synchronized)]`, C `mutex_lock(&lock)` / `mutex_unlock(&lock)`
- 성능 영향을 줄이기 위해 임계코드 주변만 동기화
- 공유자원 접근을 관리하는 pool 형태의 자체 모듈 사용

**판정 기준 (가이드 '진단방법' 기반)**
- 진단 절차: ① 공유자원(파일/폴더, 소켓, 드라이버 등)을 여러 프로세스(스레드)가 사용하는지 확인 → ② 하나의 공유자원에 동시 접근할 가능성이 있는지(예: 읽기 스레드와 삭제 스레드가 동시에 start) 확인
- 취약(정탐)으로 판정: 하나의 공유자원을 동시에 접근할 가능성이 존재하고 동기화가 없음. C에서 `access()` 검사 후 `fopen()`으로 여는 패턴
- 안전/오탐으로 판정: 동기화 구문 사용 / 공유자원 억세스를 관리하는 pool 형태의 자체 모듈 사용 / 실제로 경쟁 조건이 이루어지지 않는 경우(예: `file.listFiles()`로 목록을 읽어 단순 정보 조회만 하는 코드) / Java에서 `!f.exists()` 후 `new FileOutputStream()` 생성은 스트림 생성 시 `IOException`이 발생하므로 예외를 적절히 처리하면 문제 아님

**예시**
```java
// 취약: 읽기 스레드와 삭제 스레드가 동시에 같은 파일에 접근
public void run() {
    File f = new File("Test_367.txt");
    if (f.exists()) { f.delete(); }
}
// 안전: 공유 lock 객체로 임계구역 동기화
private static final String SYNC = "SYNC";
public void run() {
    synchronized (SYNC) { File f = new File("Test_367.txt"); if (f.exists()) { f.delete(); } }
}
```

### KISA21-IMPL-3.02 종료되지 않는 반복문 또는 재귀 함수 (Uncontrolled Recursion / Infinite Loop)

- **분류**: 시간 및 상태 · **CWE**: CWE-674, CWE-835 · **대상 언어(가이드 예제 기준)**: C, Java
- **정의**: 종료조건(귀납 조건, Base Case) 없는 재귀함수나 반복문이 무한히 반복되어 메모리·프로그램 스택 등 자원을 고갈시키고 정상 서비스를 불가능하게 하는 보안약점.

**탐지 대상**
- Source(외부입력): 해당 없음
- Sink(위험 지점): 자기 자신을 호출하는 함수/메소드(C `int factorial(int i) { return i * factorial(i - 1); }`, Java 메소드), 탈출 조건 없는 반복문
- 그 밖에 찾아야 할 코드 신호: 재귀 호출 경로 이전에 `return`하는 제어문(if 등)의 존재 여부, 재귀 깊이/호출 횟수 제한 여부

**취약 패턴**
- 함수 본문이 무조건 자기 자신을 재호출 (`return n * factorial(n - 1);`만 존재)
- 오버로드된 메소드 내부에서 같은 시그니처(함수명·파라미터 개수·자료형 일치)로 자기 자신을 호출: `public void func(String a) { func(a); }`
- grep/정규식 힌트: 함수 정의 내부에서 동일 함수명 호출 검색 (오버로딩된 다른 시그니처 호출은 과탐이므로 인자 타입 확인 필요)

**안전 패턴 / 조치 방법**
- 모든 재귀 함수에 귀납조건(Base case) 구현: `if (i <= 1) return 1;`
- 재귀 호출 횟수를 제한하거나 초기값(상수)을 설정하여 재귀 호출을 제한

**판정 기준 (가이드 '진단방법' 기반)**
- 진단 절차: ① 자신을 호출하는 재귀함수/메소드가 존재하는지 식별 → ② 해당 함수 내에 제어문으로 함수에서 리턴될 수 있는지(재귀를 빠져나올 수 있는지) 확인
- 취약(정탐)으로 판정: 함수명·파라미터 개수·파라미터 자료형이 일치하는 자기 호출이 있고, 제어문으로 빠져나올 경로가 없음
- 안전/오탐으로 판정: 같은 이름이지만 파라미터가 다른 오버로드 함수 호출(예: `func(String a)`에서 `func(Integer.parseInt(a))` → `func(int)` 호출)은 재귀가 아님 / 제어조건이 존재하는 재귀(예: `if (CollectionUtils.isEmpty(childMenuList)) return ...;` 후 재귀 호출)

**예시**
```c
// 취약: 탈출 조건 없음
int factorial(int i) { return i * factorial(i - 1); }
// 안전: Base case 구현
int factorial(int i) {
    if (i <= 1) { return 1; }
    return i * factorial(i - 1);
}
```

## 제4절 에러처리

### KISA21-IMPL-4.01 오류 메시지 정보노출 (Information Exposure Through an Error Message)

- **분류**: 에러처리 · **CWE**: CWE-209 · **대상 언어(가이드 예제 기준)**: Java, JSP, C#
- **정의**: 오류 메시지나 스택정보에 실행환경·사용자·관련 데이터 등 시스템 내부 정보(민감정보, 디버깅 정보)가 포함되어 외부에 제공되면 공격자가 내부구조를 파악해 추가 공격에 활용할 수 있는 보안약점.

**탐지 대상**
- Source(외부입력): 예외 객체 및 그 정보 (`e`, `e.getMessage()`, 스택트레이스)
- Sink(위험 지점):
  - Java/JSP: `e.printStackTrace()`, `System.err.print(e.getMessage())`, `System.err.println(...)`/`System.out.println(...)`으로 예외 정보 출력, JSP 스크립틀릿 내 `catch(Exception e) { e.printStackTrace(); }`
  - C#: `Console.WriteLine(e)` (예외 객체 전체 출력)
- 그 밖에 찾아야 할 코드 신호: catch 블록에서 예외 이름/메시지/스택트레이스를 화면·응답·표준출력으로 내보내는 출력함수

**취약 패턴**
- catch 블록 내 `e.printStackTrace()` (특히 JSP/서블릿에서 응답으로 노출 가능)
- 예외 메시지·예외 객체를 그대로 콘솔/화면 출력 (`System.err.print(e.getMessage())`, `Console.WriteLine(e)`)
- grep/정규식 힌트: `printStackTrace\(\)|getMessage\(\)|Console\.WriteLine\(\s*e\s*\)` (로거로 서버 내부에만 기록하는 경우 과탐 가능)

**안전 패턴 / 조치 방법**
- 오류 메시지는 정해진 사용자에게 유용한 최소한의 정보만 포함
- 예외상황은 내부적으로 처리하고, 사용자에게는 미리 정의된 메시지 제공
- 에러 코드와 정보를 별도로 정의하고 최소 정보만 로깅: Java `logger.error("ERROR-01: 파일 열기 에러");`, C# `_log.Debug("ERROR-01 : error information");`

**판정 기준 (가이드 '진단방법' 기반)**
- 진단 절차: ① 오류메시지를 출력하는 지점(출력함수 등) 식별 → ② 외부로 출력되는 값에 시스템 환경, 유저정보, 데이터 등 민감한 정보가 포함되어 있는지 진단원이 판단 (정적도구가 민감정보 기준을 판단하기 어려우므로 수동 판단 필요)
- 취약(정탐)으로 판정: 오류 메시지로 환경, 사용자, 관련 데이터 등 내부 정보가 유출되는 경우 (예: JSP에서 `request.getParameter` 처리 중 `catch(Exception e) { e.printStackTrace(); }`)
- 안전/오탐으로 판정: 로거를 통해 내부 로그로만 기록하는 경우(예: `logger.error(e, e);` — 가이드 오탐 예) / 미리 정의된 최소 메시지만 출력

**예시**
```java
// 취약
} catch (IOException e) {
    e.printStackTrace();
}
// 안전
} catch (IOException e) {
    logger.error("ERROR-01: 파일 열기 에러");
}
```

### KISA21-IMPL-4.02 오류상황 대응 부재 (Detection of Error Condition Without Action)

- **분류**: 에러처리 · **CWE**: CWE-390 · **대상 언어(가이드 예제 기준)**: Java, C#
- **정의**: 오류가 발생할 수 있는 부분을 확인(catch)했으나 아무 조치를 하지 않아, 프로그램이 의도하지 않은 방향(예: 인증 우회)으로 계속 동작하거나 실행정지 등이 발생할 수 있는 보안약점.

**탐지 대상**
- Source(외부입력): 오류를 유발할 수 있는 외부 입력 (예: `s.getParser().getRawParameter(PASSWORD)` 결과가 null)
- Sink(위험 지점): 비어 있는 예외 처리 블록 — Java `catch (NullPointerException e) { }`, `catch (SQLException e) { }`, `catch (NamingException e) { }`, C# `catch (CustomException e) { }`; C/C++에서 오류 반환값을 if/switch로 처리하지 않는 경우
- 그 밖에 찾아야 할 코드 신호: 주석만 있는 catch 블록(`// TODO`), 오류 발생 후에도 정상 흐름으로 이어지는 인증/권한 로직, 예외 후 초기화되지 않은 객체 반환(`return conn;`)

**취약 패턴**
- 인증 로직의 try에서 NPE를 잡고 아무 처리 없이 진행 → 인증된 것으로 처리
- DB 연결 실패(`SQLException`, `NamingException`)를 무시하고 null 커넥션 반환
- grep/정규식 힌트: `catch\s*\([^)]*\)\s*\{\s*(//[^\n]*\s*)*\}` (멀티라인; 의도적 무시 케이스 과탐 가능)

**안전 패턴 / 조치 방법**
- 오류가 발생할 수 있는 부분에 제어문으로 적절한 예외 처리 수행 (C/C++: if, switch / Java: try-catch)
- catch 후 각 예외에 대해 적절한 조치 수행: 예) `s.setMessage(e.getMessage()); return (makeLogin(s));` (로그인 화면으로 되돌림), C# `logger.Debug("log message");`

**판정 기준 (가이드 '진단방법' 기반)**
- 진단 절차: ① 오류가 발생할 수 있는 부분에 예외처리를 수행했는지 확인 → ② 제어문으로 예외 처리하는 루틴(catch 블록 등)이 비어있는지 확인
- 취약(정탐)으로 판정: 오류를 포착(catch)하고도 아무 조치가 없는 빈 예외 처리 루틴
- 안전/오탐으로 판정: 각 예외에 대해 로깅·사용자 안내·흐름 중단 등 적절한 조치가 있는 경우

**예시**
```java
// 취약: catch 블록이 비어있음
} catch (SQLException e) {
} catch (NamingException e) {
}
return conn;
// 안전: 예외에 대한 조치 수행
} catch (NullPointerException e) {
    s.setMessage(e.getMessage());
    return (makeLogin(s));
}
```

### KISA21-IMPL-4.03 부적절한 예외 처리 (Improper Check for Unusual or Exceptional Conditions)

- **분류**: 에러처리 · **CWE**: CWE-754 · **대상 언어(가이드 예제 기준)**: Java, C#
- **정의**: 함수의 결과값에 대한 처리나 예외상황 조건 검사를 부적절하게(광범위한 예외 처리 등) 수행하여 의도하지 않은 상황이 발생할 수 있는 보안약점.

**탐지 대상**
- Source(외부입력): 예외를 발생시키거나 값을 반환하는 함수/메소드 호출 (`url.openStream()`, `reader.readLine()`, `format.parse(line)`, `new FileReader(myFile)`, `InvokeMtd()` 등)
- Sink(위험 지점): 광범위한 예외 클래스로 일괄 처리 — Java `catch (Exception e)`, `catch(Exception ex){…}`, C# `catch (Exception e)`
- 그 밖에 찾아야 할 코드 신호: 반환값을 검사하지 않고 사용하는 함수 호출, try 블록 안에 서로 다른 예외(MalformedURLException, IOException, ParseException 등)를 던지는 호출이 여러 개 있는데 하나의 catch로 처리

**취약 패턴**
- 여러 종류의 예외가 발생할 수 있는 try 블록을 `catch (Exception e)` 하나로 처리
- 반환값을 검사하지 않음 (보충: 가이드 보안대책 기준)
- grep/정규식 힌트: `catch\s*\(\s*(Exception|Throwable)\s+\w+\s*\)` (최상위 진입점의 최종 방어용 catch는 과탐 가능)

**안전 패턴 / 조치 방법**
- 값을 반환하는 모든 함수의 결과값을 검사하여 의도한 값인지 확인
- 발생 가능한 예외를 세분화하고, 발생 가능한 순서에 맞춰 구체적인 예외로 처리: Java `catch (MalformedURLException e)` → `catch (IOException e)` → `catch (ParseException e)`, C# `catch (IOException e)` → `catch (SQLException e)`

**판정 기준 (가이드 '진단방법' 기반)**
- 진단 절차: ① 함수/메소드에 대해 반환값을 검사하고 예외를 발생시키는 지점에서 구체적인 예외처리를 수행하는지 확인
- 취약(정탐)으로 판정: 구체적 예외 처리가 가능한데도 `Exception` 등 광범위한 예외 클래스로 처리 (예: `new FileReader(myFile)` 후 `catch(Exception ex)`)
- 안전/오탐으로 판정: 발생 가능한 예외별로 구체적인 catch 절을 두어 처리하는 경우

**예시**
```java
// 취약
try {
    reader = new BufferedReader(new InputStreamReader(url.openStream()));
    Date date = format.parse(reader.readLine());
} catch (Exception e) { System.err.println("Exception : " + e.getMessage()); }
// 안전
} catch (MalformedURLException e) { ...
} catch (IOException e) { ...
} catch (ParseException e) { ... }
```

## 제5절 코드오류

### KISA21-IMPL-5.01 Null Pointer 역참조 (NULL Pointer Dereference)

- **분류**: 코드오류 · **CWE**: CWE-476 · **대상 언어(가이드 예제 기준)**: Java, JSP, C#, C
- **정의**: '그 객체가 널이 될 수 없다'는 가정을 위반하여 주소 값이 Null인 객체를 참조하는 보안약점. 공격자가 의도적으로 발생시킨 예외 상황을 후속 공격에 이용할 수 있다.

**탐지 대상**
- Source(외부입력/Null 원천):
  - Java: `request.getParameter("url")`, `System.getProperty("cmd")`, `null`로 초기화된 변수(`VMResultSet vmrs = null;`, `PreparedStatement statement = null;`), null을 반환할 수 있는 사용자 함수(예: `UTIL.enter2br()`가 입력 null 시 `return null`)
  - C#: `Request.QueryString["name"]` (파라미터 없으면 null)
  - C: null(0)을 반환할 수 있는 함수 반환값(`int *p = IntegerAddressReturn();`)
- Sink(위험 지점): null 가능 참조에 대한 메소드 호출/필드 접근 — `obj.equals(elt)`, `url.equals("")`, `cmd.trim()`, `vmrs.setMessage(...)`, `strContent.equals("")`, `username.Length`, `*p = count`, finally 블록의 `rs.close()` / `statement.close()`
- 그 밖에 찾아야 할 코드 신호: 분기에 따라 null 초기화 변수가 대입되지 않는 경로, 예외 발생 시 대입이 건너뛰어진 채 finally로 진입하는 경로, 널 체크 순서 오류

**취약 패턴**
- 외부입력/설정값을 null 체크 없이 메소드 호출 (`String cmd = System.getProperty("cmd"); cmd = cmd.trim();`)
- `null`로 초기화 후 if/else 중 한 분기에서만 대입하고 다른 분기에서 참조 (`else { vmrs.setMessage(...); }`)
- DB `Connection`/`Statement`/`ResultSet`을 null로 초기화 → try 내 예외로 대입 실패 → finally에서 null 체크 없이 `close()`
- 널 체크를 했으나 순서가 잘못됨: `if (str.length() == 0 || str == null)`
- `(null == obj && null == elt) || obj.equals(elt)` 처럼 obj가 null인 경로에서 역참조
- grep/정규식 힌트: `=\s*null;` 선언 변수의 이후 `\.\w+\(` 사용, `getParameter\(|QueryString\[|getProperty\(` 결과의 즉시 역참조 (데이터 흐름 확인 필수)

**안전 패턴 / 조치 방법**
- 널이 될 수 있는 레퍼런스는 참조 전에 널 검사 후 안전한 경우에만 사용: `(null != obj && obj.equals(elt))`, C `if (p != 0) *p = count;`, C# `username != null && username.Length > 20`
- 널 체크를 단락평가 앞쪽에 배치: `if (a == null || a.length() == 0)`
- finally에서 자원 해제 시 `if (con != null) con.close();`처럼 null 확인
- (참고) 가이드의 Java 안전 예 `if ( url != null || url.equals("") )`와 C# 안전 예 `username > 20`은 원문 오기로 보임 → 실제로는 `url != null && ...`, `username.Length > 20` (보충)

**판정 기준 (가이드 '진단방법' 기반)**
- 진단 절차: ① 표현된 객체가 널 값이 될 수 있는지 확인 → 널 가능성 체크/예외처리 여부 확인
  - 널 가능성 기준: 초기값이 null로 할당된 값 / 선언 후 객체가 생성되지 않은 값 / null 객체로의 필드 접근·메소드 호출 결과 / 문자열 등 Nullable 객체의 연산 결과
- 취약(정탐)으로 판정: 널이 될 수 있는 객체를 널 체크 없이 참조 (분기로 인해 null 초기화 변수가 대입되지 않는 경우, 예외로 대입 실패 후 finally에서 참조, null 반환 가능한 함수 결과 참조, 널 체크보다 역참조를 먼저 비교하는 조건문)
- 안전/오탐으로 판정:
  - 설계상 null을 반환하지 않는 함수/인터페이스(Iteration, `StringTokenizer.nextToken()` 등)의 반환값 참조 — Javadoc의 반환값 명세로 확인
  - try~catch에서 catch 절이 `throw`(또는 `return`)하여 이후 코드가 실행되지 않는 경우
  - 이미 앞선 문장에서 null 역참조로 예외가 발생해 이후 동일 참조 문장이 실행되지 않는 경우(뒤 문장은 오탐)
  - `if (a == null || a.length() == 0)`처럼 앞의 널 체크가 참이면 뒤 조건이 평가되지 않는 경우
  - JSP 내장 객체 참조(예: `${pageContext.request.contextPath}`)
  - `Integer.parseInt(stringValue)` 같은 static 함수 호출 (클래스 자체는 null 참조 아님)
  - Data Flow 상이 아닌 단일 함수에서 파라미터가 null일 수 있는 경우 (호출하는 쪽에서 널 체크하도록 함)
  - JRE 기본 패키지 클래스의 생성자(`new ArrayList()`, `new HashMap()` 등)는 null 반환이 명시되지 않는 한 null로 판단하지 않음

**예시**
```java
// 취약
String cmd = System.getProperty("cmd");
cmd = cmd.trim();
// 안전
String cmd = System.getProperty("cmd");
if (cmd != null) { cmd = cmd.trim(); }
```

### KISA21-IMPL-5.02 부적절한 자원 해제 (Improper Resource Shutdown or Release)

- **분류**: 코드오류 · **CWE**: CWE-404 · **대상 언어(가이드 예제 기준)**: Java, C#, C
- **정의**: 파일디스크립터, 힙 메모리, 소켓, DB 연결 등 유한한 자원을 사용 후 프로그램 오류·에러로 반환하지 못해 자원이 고갈되고 새로운 입력을 처리할 수 없게 되는 보안약점.

**탐지 대상**
- Source(외부입력): 해당 없음 (자원 할당 지점이 기준)
- Sink(위험 지점 = 자원 할당):
  - Java: `new FileInputStream`, `new FileOutputStream`, `new BufferedReader`, `DriverManager.getConnection`, `conn.prepareStatement`, `pstmt.executeQuery()`(ResultSet), 소켓
  - C#: `new FileStream(...)` (using 없이 사용)
  - C: `fopen()` 후 `fclose()` 누락, `malloc()` 후 `free()` 누락 (보충: 힙 메모리는 개요 기준)
- 그 밖에 찾아야 할 코드 신호: try 블록 안에서만 `close()` 호출, finally 부재, 조기 `return` 경로에서 해제 누락, finally 안의 여러 `close()`를 하나의 try로 묶음

**취약 패턴**
- try 내부에서 `in.close(); out.close();` 호출 → 그 전에 예외 발생 시 미해제
- C에서 오류 분기 `if(!checkSomething()) { ...; return; }`로 `fclose(f)` 없이 반환
- C# `FileStream`을 `using`/`Dispose` 없이 사용
- finally에서 `try { rs.close(); pstmt.close(); pstmt1.close(); conn.close(); } catch(Exception e) {}` — `rs.close()` 예외 시 이후 자원 미해제
- grep/정규식 힌트: `new (FileInputStream|FileOutputStream|FileStream)\(|getConnection\(|prepareStatement\(|fopen\(` 후 같은 함수 내 finally/using/fclose 존재 여부 확인

**안전 패턴 / 조치 방법**
- 자원을 획득·사용한 후 반드시 해제
- Java: 예외 여부와 관계없이 실행되는 `finally`에서 각 자원별로 null 검사 후 개별 try-catch로 `close()`
- C#: `using(FileStream fs = new FileStream(...)) { ... }` 구문으로 자동 해제
- C: 오류로 조기 반환하는 모든 분기에서도 `fclose(f)` 수행

**판정 기준 (가이드 '진단방법' 기반)**
- 진단 절차: ① 자원(파일기술자, 힙메모리, 소켓)이 선언·할당되는지 확인 → ② 제어문·예외처리문 등의 분기에 따른 모든 control flow에서 해제되는지 확인
- 취약(정탐)으로 판정: 자원이 해제되지 않는 분기가 하나라도 존재 (finally에서 여러 자원 해제를 하나의 try로 묶어, 앞선 `close()` 예외 시 뒤 자원이 해제되지 않는 경우 포함)
- 안전/오탐으로 판정: 모든 흐름에서 할당 자원이 해제됨 (finally에서 자원별 개별 try-catch로 close) / 함수의 역할이 자원을 리턴하는 경우(예: `DBUtil.getConnection()`이 `return conn;`) — 해제는 호출한 쪽 책임이므로 취약하지 않음

**예시**
```java
// 취약: 하나의 try로 묶여 rs.close() 예외 시 나머지 미해제
} finally {
    try { rs.close(); pstmt.close(); conn.close(); } catch (Exception e) { }
}
// 안전: 자원별 null 검사 + 개별 try-catch
} finally {
    if (in != null) { try { in.close(); } catch (IOException e) { logger.error(e); } }
    if (out != null) { try { out.close(); } catch (IOException e) { logger.error(e); } }
}
```

### KISA21-IMPL-5.03 해제된 자원 사용 (Use After Free)

- **분류**: 코드오류 · **CWE**: CWE-416 · **대상 언어(가이드 예제 기준)**: C
- **정의**: 이미 해제된 동적 메모리 등 자원을 다시 참조(또는 이중 해제)하여 예상치 못한 값·코드가 실행되는 등 의도하지 않은 결과가 발생하는 보안약점.

**탐지 대상**
- Source(외부입력): 해당 없음 (외부입력 `argv[1]` 등이 해제된 버퍼에 복사되는 경우 위험 증가)
- Sink(위험 지점): `free(ptr)` 이후의 `ptr` 사용 — `strncpy(temp, ...)`(원문 표기 `stmcpy`), `logError(..., messageBody)` 등 함수 인자 전달, 역참조, 형 변환, 수식의 피연산자; 동일 포인터에 대한 두 번째 `free()` (이중 해제)
- 그 밖에 찾아야 할 코드 신호: `free()` 후 포인터에 `NULL` 미대입, 조건 분기 안에서만 해제 후 분기 밖에서 사용, 포인터 연산·재대입(`messageBody = &message[1][0];`)

**취약 패턴**
- `free(temp);` 다음 줄에서 `temp` 사용
- `if (data_type==val_1) { free(data); } ... if (data_type==val_2) { free(data); }` → 두 조건이 동시에 참이면 이중 해제
- 오류 분기에서 `free(messageBody)` 후, 이후 `if (result == ERROR) logError(..., messageBody);`로 재접근
- grep/정규식 힌트: `free\(\s*(\w+)\s*\)` 이후 동일 식별자 사용 및 `\1\s*=\s*NULL` 부재 확인 (재할당 후 사용은 과탐)

**안전 패턴 / 조치 방법**
- 할당 메모리를 최종적으로 사용한 뒤 해제 (사용 → `free` 순서)
- 해제 후 포인터를 참조 추적·형 변환·수식 피연산자 등으로 사용하지 않음
- 해제 직후 포인터에 `NULL`(또는 적절한 값) 대입: `free(data); data = NULL;` → 이중 해제도 무시됨

**판정 기준 (가이드 '진단방법' 기반)**
- 진단 절차: ① 메모리·파일 등 자원을 사용하는 코드 확인 → ② 사용 코드 앞에서 자원 해제가 발생하는지, 해제 후 제어 흐름이 사용 코드로 도달하는지 확인 → ③ 포인터 변수에 연산을 수행하는 경우 올바른 값을 참조하는지 정밀 검사, 사용 완료된 포인터 변수의 초기화(NULL) 여부 확인
- 취약(정탐)으로 판정: 자원 사용 코드 앞에서 해제가 발생하는 경로가 존재 (예: 조건부 `free` 후 다른 조건에서 같은 변수 접근)
- 안전/오탐으로 판정: 해제 후 모든 경우의 제어 흐름이 해당 자원 사용 코드에 도달하지 않음

**예시**
```c
// 취약
temp = (char *)malloc(BUFFER_SIZE);
free(temp);
strncpy(temp, argv[1], BUFFER_SIZE-1);
// 안전
temp = (char *)malloc(BUFFER_SIZE);
strncpy(temp, argv[1], BUFFER_SIZE-1);
free(temp);
temp = NULL;
```

### KISA21-IMPL-5.04 초기화되지 않은 변수 사용 (Use of Uninitialized Variable)

- **분류**: 코드오류 · **CWE**: CWE-457 · **대상 언어(가이드 예제 기준)**: C, C++
- **정의**: C의 스택 지역변수는 자동 초기화되지 않으며 이전 함수의 내용을 담고 있으므로, 초기화하지 않고 사용하면 예기치 않은 동작·메모리 값 노출·특정 코드 실행·서비스 거부가 가능한 보안약점.

**탐지 대상**
- Source(외부입력): 해당 없음 (공격자가 사전에 스택에 남겨 둔 값)
- Sink(위험 지점): 선언 시 초기화되지 않은 지역변수의 사용 (`int x, y;` 후 `setCursorPosition(x, y)`), C++ 생성자에서 초기화되지 않은 멤버 필드 접근 (`Foo() {}` + `get_a()`가 `a_` 반환)
- 그 밖에 찾아야 할 코드 신호: switch/if 분기 중 일부(예: `default`)에서만 일부 변수를 초기화, 모든 생성자가 멤버를 초기화하는지 여부

**취약 패턴**
- `int x, y; switch(position) { ... default: x=1; break; }` → default 경로에서 y 미초기화 상태로 사용
- C++ 디폴트 생성자가 필드를 초기화하지 않고, 해당 객체의 필드를 읽음
- grep/정규식 힌트: `^\s*(int|char|long|short|float|double|unsigned)\s+\w+(\s*,\s*\w+)*\s*;` (초기화자 없는 선언; 이후 모든 경로에서 대입되면 과탐)

**안전 패턴 / 조치 방법**
- 모든 변수는 사용 전에 올바른 초기값 할당 — 선언과 동시에 초기화: `int x=1, y=1;`
- 분기 내부 초기화에 의존하지 말고 초기화 구문을 분기 밖으로 이동
- C++ 객체 필드는 모든 생성자(디폴트 생성자 포함)에서 초기화 (보충: 예) `Foo() : a_(0) {}`)

**판정 기준 (가이드 '진단방법' 기반)**
- 진단 절차: ① 변수의 선언과 동시에 초기화가 이루어지는지 확인 → ② C++처럼 객체 필드가 초기값을 갖지 않는 경우 생성자로 필드 초기화가 이루어지는지 확인
- 취약(정탐)으로 판정: 위 초기화가 이루어지지 않으면 기본적으로 취약 (예: 디폴트 생성자로 생성한 객체의 미초기화 필드 접근)
- 안전/오탐으로 판정: 선언 시 초기화되었거나, 생성자에서 필드가 초기화된 경우

**예시**
```c
// 취약
int x, y;
switch(position) { case 0: x = base_position; y = base_position; break; default: x = 1; break; }
setCursorPosition(x, y);
// 안전
int x = 1, y = 1;
switch(position) { case 0: x = base_position; y = base_position; break; default: x = 1; break; }
setCursorPosition(x, y);
```

### KISA21-IMPL-5.05 신뢰할 수 없는 데이터의 역직렬화 (Deserialization of Untrusted Data)

- **분류**: 코드오류 · **CWE**: CWE-502 (추정; 가이드 참고자료에는 CWE-918 SSRF가 잘못 기재되어 있음) · **대상 언어(가이드 예제 기준)**: Java, Python
- **정의**: 악의적인 코드가 삽입·수정된 직렬화 데이터(바이트 스트림/파일)를 적절한 검증 없이 역직렬화하여 무결성 침해, 원격 코드 실행, 서비스 거부 등이 발생하는 보안약점.

**탐지 대상**
- Source(외부입력): `HttpServletRequest.getInputStream()`, `MultipartFile.getInputStream()`(업로드 파일), 외부에서 전달된 `byte[] buffer`, 사용자 제공 XML 문자열, 소켓 수신 데이터(`conn.recv(1024)`), 파일(`new FileInputStream("data")`)
- Sink(위험 지점):
  - Java: `java.io.ObjectInputStream.readObject()` (`new ObjectInputStream(req.getInputStream())`, `new ObjectInputStream(new ByteArrayInputStream(buffer))`), `java.beans.XMLDecoder.readObject()`
  - Python: `pickle.loads(data)`
- 그 밖에 찾아야 할 코드 신호: `resolveClass` 오버라이드(화이트리스트) 부재, 서명(`SignedObject.verify`)·HMAC 무결성 검증 부재

**취약 패턴**
- 서블릿에서 `ois = new ObjectInputStream(req.getInputStream()); ois.readObject();`
- 바이트 배열 입력을 검증 없이 `ObjectInputStream.readObject()`
- `new XMLDecoder(new ByteArrayInputStream(xml.getBytes())).readObject()`로 사용자 제공 XML 역직렬화
- 소켓 수신 데이터를 바로 `pickle.loads(data)`
- grep/정규식 힌트: `ObjectInputStream|readObject\(|XMLDecoder|pickle\.loads?\(` (신뢰 출처 고정 파일·화이트리스트/HMAC 적용 시 과탐)

**안전 패턴 / 조치 방법**
- 신뢰할 수 없는 데이터를 역직렬화하지 않도록 응용프로그램 구성
- 암호화 통신을 적용하지 못하면 송신 측에서 서명 추가, 수신 측에서 서명 확인으로 무결성 검증 (Java `SignedObject.verify(publicKey, sig)` 실패 시 예외; Python `hmac.new(key, pickled_data, hashlib.sha1).hexdigest()` 비교 후 일치할 때만 `pickle.loads`)
- 역직렬화 대상이 사전에 검증된 클래스만 포함하는지 검증: `ObjectInputStream`을 상속한 `WhitelistedObjectInputStream`에서 `resolveClass()`를 오버라이드해 화이트리스트에 없는 클래스면 `InvalidClassException` 발생
- 제한된 실행 권한으로 역직렬화 코드 실행

**판정 기준 (가이드 '진단방법' 기반)**
- 진단 절차: ① `java.io.ObjectInputStream.readObject()` 등 각 언어의 역직렬화 함수 확인 → ② 해당 함수가 사용하는 데이터가 신뢰할 수 있는 값인지 확인
- 취약(정탐)으로 판정: 사용자 입력 값, 소켓 입력 값 등 출처를 신뢰할 수 없는 데이터를 검증 절차 없이 역직렬화 (`req.getInputStream()` → `readObject()`, 사용자 XML → `XMLDecoder.readObject()`, 소켓 수신 → `pickle.loads`)
- 안전/오탐으로 판정: HMAC/서명 등으로 데이터 무결성을 검증한 후 역직렬화 / 화이트리스트 기반 `resolveClass` 검증 적용

**예시**
```python
# 취약
conn, addr = self.receiver_socket.accept()
data = conn.recv(1024)
return pickle.loads(data)
# 안전: HMAC 무결성 검증 후 역직렬화
recvd_digest, pickled_data = data.split(' ')
new_digest = hmac.new('shared-key', pickled_data, hashlib.sha1).hexdigest()
if recvd_digest == new_digest:
    unpickled_data = pickle.loads(pickled_data)
```


## 제6절 캡슐화

### KISA21-IMPL-6.01 잘못된 세션에 의한 데이터 정보 노출 (Exposure of Data Element to Wrong Session)

- **분류**: 캡슐화 · **CWE**: CWE-488, CWE-543 · **대상 언어(가이드 예제 기준)**: Java(Servlet, JSP, Spring Controller), C#(IHttpHandler)
- **정의**: 다중 스레드 환경에서 싱글톤으로 동작하는 객체(Servlet, JSP, Controller, IHttpHandler 등)의 멤버 필드에 요청/사용자별 정보를 저장하면 경쟁조건이 발생해 다른 세션의 데이터가 노출·덮어쓰기될 수 있다.

**탐지 대상**
- Source(외부입력): `request.getParameter(...)`, `ctx.Request.QueryString[...]` 등 요청 데이터가 멤버 필드에 대입되는 지점
- Sink(위험 지점):
  - Java: `HttpServlet` 하위클래스의 non-final 인스턴스 필드
  - JSP: 선언부 `<%! ... %>` 안의 변수 선언 (모든 사용자에게 공유됨)
  - Spring: `@Controller`(싱글톤) 클래스의 상태 저장용 멤버 변수 (예: `private int currentPage`)
  - C#: `IHttpHandler` 구현 클래스의 정보 저장 필드 (예: `private String id;`)
- 그 밖에 찾아야 할 코드 신호: 요청 처리 메소드(`doGet/doPost/ProcessRequest/@RequestMapping` 핸들러) 안에서 `this.필드 = ...` 형태로 멤버 필드에 값을 쓰는 코드

**취약 패턴**
- `class X extends HttpServlet { private String name; ... doPost(...) { name = request.getParameter("name"); } }`
- JSP `<%! String commonPath = "/"; String imagePath = ...; %>` (상수로 쓰지 않는 선언부 변수)
- `@Controller` 클래스에 `private int currentPage = 1;` 후 핸들러에서 대입
- grep/정규식 힌트: JSP `<%!` 블록 탐색; `extends HttpServlet` / `@Controller` / `: IHttpHandler` 클래스에서 `final`/`static final` 아닌 필드 선언 (DI 필드 등 과탐 많음 → 오탐 기준으로 걸러낼 것)

**안전 패턴 / 조치 방법**
- 싱글톤 객체에서는 변수 범위(Scope)에 주의: 멤버 필드를 선언하지 말고 메소드 안의 지역 변수로 사용
- JSP는 선언부 `<%! %>` 대신 스크립틀릿 `<% %>`에 선언 (`_jspService`의 지역변수가 되므로 공유되지 않음)
- C#은 지역 변수 또는 세션 변수(`ctx.Session["id"] = ...`) 사용

**판정 기준 (가이드 '진단방법' 기반)**
- 진단 절차: HttpServlet 하위클래스(JSP 포함)/Controller/IHttpHandler에 멤버 필드가 있는지 확인 → final(상수)인지 확인 → 요청 처리 중 값이 쓰이는지 확인
- 취약(정탐)으로 판정: HttpServlet 하위클래스에 final이 아닌 멤버 필드가 선언됨; 서블릿(JSP 포함)에서 상수로 사용하지 않는 멤버 변수(JSP `<%! %>` 선언 변수 포함)를 사용
- 안전/오탐으로 판정:
  - JSP/서블릿 내부에 선언된 내부 클래스(`<%! private class CacheEntity { String name; ... } %>`)의 필드 — 멤버필드가 아님
  - `final` 필드 (클래스 내부 상수)
  - Spring/eGov 프레임워크 IoC로 주입되는 필드 (`@Resource(name="fileMngService") private FileMngService fileService;`) — 프레임워크가 인스턴스 관리

**예시**
```java
// 취약
@Controller
public class TrendForecastController {
  private int currentPage = 1;
  public void doSomething(HttpServletRequest request) {
    currentPage = Integer.parseInt(request.getParameter("page"));
  }
}
// 안전
public void doSomething(HttpServletRequest request) {
  int currentPage = Integer.parseInt(request.getParameter("page"));
}
```

### KISA21-IMPL-6.02 제거되지 않고 남은 디버그 코드 (Leftover Debug Code)

- **분류**: 캡슐화 · **CWE**: CWE-489 · **대상 언어(가이드 예제 기준)**: Java(J2EE), C#, C
- **정의**: 디버깅용 코드가 배포 후에도 남아 있으면 설정 등 민감정보 노출, 인증(식별) 우회, 시스템 제어가 가능해질 수 있다.

**탐지 대상**
- Source(외부입력): 해당 없음 (코드 존재 자체가 문제)
- Sink(위험 지점):
  - Java(J2EE): 웹 애플리케이션 클래스(`HttpServlet` 하위클래스 등) 안의 `public static void main(String[] args)`; 그 안의 `System.out/err.print*` 디버그 출력
  - C#: `Console.WriteLine(...)` 등 디버그용 출력 (민감정보 출력)
  - C: `backtrace()`, `backtrace_symbols()` 결과(콜 스택)를 `printf`로 출력하는 코드 → 프로그램 구조 유추 가능
- 그 밖에 찾아야 할 코드 신호: `if (debug) { ... }` 블록, 테스트용 진입점, 디버깅용 로그 출력문

**취약 패턴**
- J2EE 클래스에 `main()` 존재 (J2EE Standard는 main 작성을 금함; 개발자가 디버그 코드를 main에 작성하는 경우가 일반적)
- `if(debug) { for(...) printf("%s\n", strings[i]); }` 형태의 콜스택 출력
- grep/정규식 힌트: `public\s+static\s+void\s+main\s*\(` in 웹 애플리케이션 소스; `Console\.WriteLine`, `backtrace_symbols`, `if\s*\(\s*debug` (일반 로깅/콘솔 앱은 과탐 가능)

**안전 패턴 / 조치 방법**
- 배포 전 디버그 코드를 반드시 확인·삭제
- J2EE 등 웹 애플리케이션에서는 디버깅용 `main()` 메소드 삭제
- 릴리즈 빌드에서 디버그 출력/콜스택 출력 코드 삭제, 동작 코드만 남김

**판정 기준 (가이드 '진단방법' 기반)**
- 진단 절차: ① 개발 중 테스트 목적으로 남은 디버그 코드 존재 여부 확인. J2EE 환경에서 main 메소드가 있으면 디버그 코드인지 확인
- 취약(정탐)으로 판정: J2EE 응용프로그램(서블릿 등)에 디버깅용 `main()`이나 디버깅용 로그 출력문(`System.err.printf("Print debug code")` 등)이 남아 있음
- 안전/오탐으로 판정: 가이드에 명시된 오탐 사례 없음. 단 가이드는 "J2EE를 제외하고는 정적도구만으로 디버그 코드 판단이 쉽지 않다"고 명시 → J2EE 외에는 문맥(디버그 플래그, 민감정보 출력 여부)을 보고 판단

**예시**
```java
// 취약
public class U489 extends HttpServlet {
  protected void doGet(...) { ... }
  public static void main(String args[]) {
    System.err.printf("Print debug code");
  }
}
// 안전: main() 메소드 삭제
public class U489 extends HttpServlet {
  protected void doGet(...) { ... }
}
```

### KISA21-IMPL-6.03 Public 메소드부터 반환된 Private 배열 (Private Array-Typed Field Returned From A Public Method)

- **분류**: 캡슐화 · **CWE**: CWE-495 · **대상 언어(가이드 예제 기준)**: Java, C#
- **정의**: private 배열(컬렉션)을 public 메소드가 그대로 반환하면 참조가 외부에 공개되어 외부에서 배열 및 원소 객체 속성을 수정할 수 있다.

**탐지 대상**
- Source(외부입력): 해당 없음 (public 메소드 호출자)
- Sink(위험 지점):
  - Java: `private T[] field;` 를 `public` 메소드에서 `return field;` / `return this.field;`
  - C#: `private List<T> field;` 등 private 컬렉션을 public 메소드에서 그대로 반환
- 그 밖에 찾아야 할 코드 신호: 새 배열을 만들어 for문으로 복사했지만 원소가 일반(가변) 객체인데 `clone()` 없이 참조만 대입 (`ret[i] = this.arr[i]`)

**취약 패턴**
- `private String[] colors; public String[] getColors() { return colors; }`
- 얕은 복사: `Color[] ret = new Color[n]; for(...) ret[i] = this.myColors[i]; return ret;` (원소가 일반 객체면 주소만 복사 → 취약)
- grep/정규식 힌트: `private\s+[\w<>]+\s*\[\]\s*(\w+)` 수집 후 `return\s+(this\.)?\1\s*;` 가 public 메소드 안에 있는지 (getter 자동생성 Lombok `@Getter` 등은 별도 확인 필요 — (보충))

**안전 패턴 / 조치 방법**
- private 배열을 public 메소드로 직접 반환하지 않음 (메소드를 private으로 하거나, 복제본 반환, 수정용 public 메소드 별도 제공)
- 원소가 일반 객체: 새 배열 생성 + 각 원소 `clone()` 복사 (`colors[i] = this.colors[i].clone();`)
- 원소가 String 등 불변: 배열 복사본만 생성하여 반환
- C#: 새 컬렉션 생성 후 각 원소 `Clone()`(ICloneable)으로 복사하여 반환

**판정 기준 (가이드 '진단방법' 기반)**
- 진단 절차: ① private 배열 선언 확인 → ② 해당 배열이 public 메소드에서 반환되는지 확인. 원소가 일반 객체이면 원소별로 객체를 생성하고 내부 값을 복사하는지 확인
- 취약(정탐)으로 판정: public 메소드가 private 배열 필드를 그대로 반환 (예: `public String[] getChkb() { return this.checkb; }`); 새 배열로 복사했더라도 일반 객체 원소의 참조만 복사
- 안전/오탐으로 판정: private이 아닌 `public static final` 상수 배열 (예: `public static final String[] XML_TAG = {...}`); 불변 원소 배열의 복사본 반환; 가변 원소를 clone으로 깊은 복사 후 반환

**예시**
```java
// 취약
private String[] colors;
public String[] getColors() { return colors; }
// 안전
public String[] getColors() {
  String[] ret = null;
  if (this.colors != null) {
    ret = new String[colors.length];
    for (int i = 0; i < colors.length; i++) { ret[i] = this.colors[i]; }
  }
  return ret;
}
```

### KISA21-IMPL-6.04 Private 배열에 Public 데이터 할당 (Public Data Assigned to Private Array-Typed Field)

- **분류**: 캡슐화 · **CWE**: CWE-496 · **대상 언어(가이드 예제 기준)**: Java, C#
- **정의**: public 메소드의 인자(배열)를 private 배열 필드에 그대로 저장하면, 호출자가 가진 참조로 private 배열과 원소 객체 속성을 외부에서 수정할 수 있어 사실상 public 필드가 된다.

**탐지 대상**
- Source(외부입력): public 메소드(setter 등)의 배열 타입 인자
- Sink(위험 지점):
  - Java: `public void setX(T[] arg) { this.field = arg; }` (field는 private 배열)
  - C#: `public void SetUserRoles(String[] userRoles) { this.userRoles = userRoles; }`
- 그 밖에 찾아야 할 코드 신호: 새 배열을 생성해 for문으로 복사했지만 원소가 일반 객체인데 `clone()` 없이 참조만 대입

**취약 패턴**
- `private UserRole[] userRoles; public void setUserRoles(UserRole[] userRoles) { this.userRoles = userRoles; }`
- 얕은 복사: `this.userRoles = new UserRole[n]; for(...) this.userRoles[i] = userRoles[i];` (일반 객체 → 주소값만 복사되어 취약)
- grep/정규식 힌트: public 메소드 안의 `this\.(\w+)\s*=\s*(\w+)\s*;` 중 좌변이 private 배열 필드이고 우변이 배열 파라미터인 경우

**안전 패턴 / 조치 방법**
- public 메소드 인자를 private 배열에 직접 저장하지 않음
- 원소가 일반 객체: 새 배열 생성 + 원소별 `clone()` 후 할당 (`this.userRoles[i] = userRoles[i].clone();`)
- 원소가 String 등 불변: 인자 배열의 복사본을 생성하여 할당 (C#도 동일하게 새 배열 생성 후 원소 복사)

**판정 기준 (가이드 '진단방법' 기반)**
- 진단 절차: ① private 배열 선언 확인 → ② public 메소드 인자로 받은 배열을 private 배열 필드에 직접 할당하는지 확인. 원소가 일반 객체이면 원소별로 객체를 생성해 내부 값을 복사하는지 확인
- 취약(정탐)으로 판정: 인자 배열을 private 필드에 직접 대입; 새 배열을 만들었어도 일반 객체 원소를 참조 복사
- 안전/오탐으로 판정: 불변 원소(String 등) 배열을 새 배열로 복사해 할당; 가변 원소를 clone으로 깊은 복사해 할당 (가이드에 별도 오탐 사례 없음)

**예시**
```java
// 취약
private UserRole[] userRoles;
public void setUserRoles(UserRole[] userRoles) { this.userRoles = userRoles; }
// 안전
public void setUserRoles(UserRole[] userRoles) {
  this.userRoles = new UserRole[userRoles.length];
  for (int i = 0; i < userRoles.length; ++i)
    this.userRoles[i] = userRoles[i].clone();
}
```

## 제7절 API 오용

### KISA21-IMPL-7.01 DNS lookup에 의존한 보안결정 (Reliance on DNS Lookups in a Security Decision)

- **분류**: API 오용 · **CWE**: CWE-247 · **대상 언어(가이드 예제 기준)**: Java, C#, C
- **정의**: DNS 엔트리는 공격자가 속일 수 있으므로(DNS 캐시 오염, 동일 도메인 위장 등) 도메인명/호스트명에 의존해 인증·접근통제 같은 보안결정을 하면 우회된다.

**탐지 대상**
- Source(외부입력): 요청 원격 주소 (`req.getRemoteAddr()`, `Request.ServerVariables["REMOTE_HOST"]`, `ip_addr_string`)
- Sink(위험 지점) — DNS lookup 결과(호스트명)로 신뢰 여부 판정:
  - Java: `InetAddress.getByName(ip)` → `addr.getCanonicalHostName()` (또는 호스트명) `.endsWith("trustme.com")` 등 비교
  - C#: `Dns.GetHostByAddress(...)` → `hostInfo.HostName.EndsWith("trust.com")`
  - C: `gethostbyaddr(...)` → `hp->h_name`을 `strncmp`/`strcmp`로 신뢰 도메인과 비교
- 그 밖에 찾아야 할 코드 신호: 호스트명 비교 결과가 `trusted = true`, 권한 부여, 신뢰 시스템 기능 호출로 이어지는지

**취약 패턴**
- `if (addr.getCanonicalHostName().endsWith("trustme.com")) { trusted = true; }`
- grep/정규식 힌트: `getCanonicalHostName|getHostName|GetHostByAddress|GetHostEntry|gethostbyaddr|h_name` 뒤 `endsWith|EndsWith|equals|strcmp|strncmp` 와 if 분기 (단순 로깅용 lookup은 과탐)

**안전 패턴 / 조치 방법**
- 보안결정에서 도메인명 DNS lookup을 사용하지 않음
- 신뢰할 서버의 실제 IP 주소와 요청 IP를 직접 비교 (`ip.equals(trustedAddr)`, `remoteIpAddress.Equals(trustedAddr)`), null/빈값 체크 포함

**판정 기준 (가이드 '진단방법' 기반)**
- 진단 절차: ① DNS lookup 모듈 존재 확인 → ② 그 결과로 보안결정(신뢰 판단)을 하는 부분이 있는지 확인
- 취약(정탐)으로 판정: DNS 이름(호스트명)으로 요청의 신뢰 여부를 판정
- 안전/오탐으로 판정: IP 주소를 직접 비교하는 경우; DNS lookup이 있어도 보안결정에 쓰이지 않는 경우 (가이드에 별도 오탐 사례 없음)

**예시**
```java
// 취약
InetAddress addr = InetAddress.getByName(req.getRemoteAddr());
if (addr.getCanonicalHostName().endsWith("trustme.com")) { trusted = true; }
// 안전
String ip = req.getRemoteAddr();
if (ip == null || "".equals(ip)) return;
if (ip.equals("127.0.0.1")) { do_something_for_Trust_System(); }
```

### KISA21-IMPL-7.02 취약한 API 사용 (Use of Potentially/Inherently Dangerous Function)

- **분류**: API 오용 · **CWE**: CWE-676, CWE-242, CWE-246, CWE-382 · **대상 언어(가이드 예제 기준)**: C, Java(J2EE), C#
- **정의**: 보안상 금지된(banned) 함수나 부주의하게 사용되기 쉬운 API를 검증 없이 쓰거나, 문제없는 API라도 잘못된 방식으로 쓰면 버퍼 오버플로우, 서비스 종료 등 보안 문제가 발생한다.

**탐지 대상**
- Source(외부입력): 함수 매개변수, 사용자 입력 등 크기가 제한되지 않은 데이터 (C 문자열 함수의 경우)
- Sink(위험 지점) — 가이드가 명시한 취약 API 전체:
  - C (금지 함수 → 대체 함수):
    - `strcat()` → `strcat_s()`
    - `strcpy()` → `strcpy_s()`
    - `strncat()` → `strncat_s()`
    - `strncpy()` → `strncpy_s()`
    - `sprintf()` → `sprintf_s()`
    - `gets()` → `gets_s()` 또는 `fgets()` (입력 크기 제한 불가 → 버퍼 오버플로우)
    - `strtol()` (금지 API는 아니나 취약): `int`, `short`, `char` 등 작은 부호 있는 정수형 변환에 쓰면 범위 제한 없이 평가됨
  - Java (J2EE):
    - `new Socket(...)` 직접 사용 (CWE-246) → 프레임워크 보안기능을 못 받음. `URL.openConnection()`(`URLConnection`) 등 프레임워크 메소드 사용
    - `System.exit()` (CWE-382) → 웹 애플리케이션 컨테이너 종료 가능. 사용 금지
  - C#:
    - `Application.Exit()` → 즉시 종료되어 `Form.Closed`/`Form.Closing` 이벤트 미처리. `this.Close()` 사용
- 그 밖에 찾아야 할 코드 신호: 개발 조직이 별도로 명시한 취약 API 목록이 있으면 그 목록도 적용 (가이드: "반드시 준수")

**취약 패턴**
- `char buf[24]; strcpy(buf, string);` (매개변수 길이가 버퍼보다 크면 문제)
- `char str[100]; gets(str);`
- 서블릿 안의 `socket = new Socket("kisa.or.kr", 8080);`
- 서블릿 catch 블록의 `System.exit(1);`
- grep/정규식 힌트: `\b(strcat|strcpy|strncat|strncpy|sprintf|gets|strtol)\s*\(` (`_s` 버전 제외), `new\s+Socket\s*\(` / `System\.exit\s*\(` in J2EE 소스, `Application\.Exit\s*\(` in C#

**안전 패턴 / 조치 방법**
- 금지 함수는 안전한 대체 함수(`*_s`, `fgets`)로 교체하고 크기 인자 지정 (`gets_s(str, sizeof(str))`)
- J2EE에서는 소켓 직접 사용 대신 `URL`/`URLConnection` 등 프레임워크 메소드 사용, `System.exit()` 미사용
- C#은 `Application.Exit()` 대신 `this.Close()` 사용
- 대체 API가 없으면 해당 API의 인자와 반환 값을 검사

**판정 기준 (가이드 '진단방법' 기반)**
- 진단 절차: 취약 API 리스트 작성 → 대상 프로그램에서 해당 API 사용 여부 확인 → 대체 API가 없는 경우 인자·반환 값 검사 여부 확인
- 취약(정탐)으로 판정: 취약 API를 사용하는 경우 (예: 매개변수를 고정 크기 버퍼에 `strcpy`로 복사, J2EE 서블릿에서 `System.exit()` 호출)
- 안전/오탐으로 판정: 대체 API가 없는 취약 API이면서 인자와 반환 값에 대한 검사가 이루어지는 경우 (가이드에 별도 오탐 코드 예 없음)

**예시**
```c
// 취약
void manipulate_string(char *string) {
  char buf[24];
  strcpy(buf, string);
}
// 안전 (가이드 gets 예제)
char str[100];
gets_s(str, sizeof(str));   /* gets(str) 대신 */
```


---

# Part B. 설계단계 보안설계 기준 (20개)


> 출처: KISA 「소프트웨어 보안약점 진단가이드(2021)」 제3장 제3절, 제5장 부록 제1절. 연관 구현단계 항목은 가이드의 「구현단계 기준과의 관계」 표와 각 항목의 "라. 연관된 구현단계 보안약점 항목"을 따름.

## 1. 입력데이터 검증 및 표현

### KISA21-SR1-1 DBMS 조회 및 결과 검증
- **설명**: DBMS 조회 시 SQL 질의문 내 입력값과 조회결과의 유효성 검증방법(필터링 등)과 유효하지 않은 값의 처리방법을 설계한다.
- **요구사항**:
  - ① 애플리케이션의 DB 연결은 최소권한 계정을 사용한다.
  - ② 외부입력값이 삽입되는 SQL을 동적으로 생성·실행하지 않는다.
  - ③ 동적 SQL이 불가피하면 입력값 검증 후 사용한다.
- **코드/설정에서 확인할 것**:
  - DB 접속 계정(datasource 설정 등)이 해당 애플리케이션이 쓰는 테이블·뷰·프로시저에 대한 읽기/쓰기/삭제/수정 권한만 갖는지 (root/sa/DBA 계정 사용 여부)
  - 문자열 연결로 SQL을 만드는 코드 부재; PreparedStatement/파라미터 바인딩, ORM(Hibernate, JPA, MyBatis) 사용
  - MyBatis 쿼리맵에서 외부입력 바인딩은 `#{}` 사용 (`${}` 사용 금지)
  - 동적 SQL 사용 시 Filter/Interceptor/공통 Validator 컴포넌트에서 SQL 삽입 문자열 필터링이 일괄 적용되는지 (클라이언트·서버 양측 검증)
- **연관 구현단계 항목**: IMPL-1.01 SQL 삽입

### KISA21-SR1-2 XML조회 및 결과 검증
- **설명**: XML 조회 시 질의문(XPath, XQuery 등) 내 입력값과 조회결과의 유효성 검증방법 및 유효하지 않은 값의 처리방법을 설계한다.
- **요구사항**:
  - ① XML 조회 기능의 질의 파라미터는 질의를 조작할 수 없도록 필터링하거나, 미리 작성된 질의문에 자료형에 따라 바인딩해서 사용한다.
- **코드/설정에서 확인할 것**:
  - XPath/XQuery 문자열에 외부입력을 직접 연결하는 코드 부재; 변수 바인딩 가능한 API(예: Java XQuery API) 사용
  - 외부입력에서 XML 삽입 문자 `"`, `[`, `]`, `/`, `=`, `@` 등을 제거·치환하는 Filter/Validator 적용 여부
  - (보충) XML 파서의 외부 엔티티(DTD/External Entity) 처리 비활성화 여부 — 연관 항목 XXE 점검용
- **연관 구현단계 항목**: IMPL-1.09 XML 삽입, IMPL-1.08 부적절한 XML 외부개체 참조(XXE)

### KISA21-SR1-3 디렉토리 서비스 조회 및 결과 검증
- **설명**: LDAP 등 디렉토리 서비스 조회 시 입력값과 조회결과의 유효성 검증방법 및 유효하지 않은 값의 처리방법을 설계한다.
- **요구사항**:
  - ① LDAP 인증서버로 인증을 구현할 때 인증요청에 쓰이는 외부입력값은 LDAP 삽입이 불가능하도록 필터링해서 사용한다.
- **코드/설정에서 확인할 것**:
  - LDAP 검색 필터 문자열 생성 시 외부입력값에서 필터 특수문자(`=`, `+`, `<`, `>`, `#`, `;`, `\` 등)를 제거/이스케이프하는지
  - 외부입력이 DN·검색필터에 그대로 연결되는 코드 부재
- **연관 구현단계 항목**: IMPL-1.10 LDAP 삽입

### KISA21-SR1-4 시스템 자원 접근 및 명령어 수행 입력값 검증
- **설명**: 시스템 자원 접근 및 명령어 수행 시 입력값의 유효성 검증방법 및 유효하지 않은 값의 처리방법을 설계한다.
- **요구사항**:
  - ① 외부입력값으로 시스템 자원(IP, PORT, 프로세스, 메모리, 파일 등)을 식별할 때 허가되지 않은 자원이 사용되지 않게 한다.
  - ② 서버 프로그램에서 셸을 생성해 명령어를 실행할 경우 외부입력값으로 악의적 명령이 실행되지 않게 한다.
- **코드/설정에서 확인할 것**:
  - 외부입력이 리소스(파일 경로, URL/호스트, 포트 등)를 직접 결정하지 않고, 프로퍼티/XML로 정의된 허용 목록에서 인덱스(선택자)로 선택하는지
  - 디렉토리 내 임의 파일 접근이 필요한 경우 경로조작 문자(`..`, `/`, `\`) 제거 후 지정 경로 내로 제한하는지
  - `Runtime.exec`, `ProcessBuilder`, `system()`, `os.system`, `subprocess(shell=True)`, `eval` 등에 외부입력이 직접 들어가는지; 셸 실행 구조 자체를 피했는지
  - 명령어 인자가 허용목록 값으로만 조립되는지
- **연관 구현단계 항목**: IMPL-1.02 코드 삽입, IMPL-1.03 경로 조작 및 자원 삽입, IMPL-1.12 서버사이드 요청 위조(SSRF), IMPL-1.05 운영체제 명령어 삽입

### KISA21-SR1-5 웹 서비스 요청 및 결과 검증
- **설명**: 웹 서비스(게시판 등) 요청과 응답결과(스크립트를 포함한 웹 페이지)의 유효성 검증방법 및 유효하지 않은 값의 처리방법을 설계한다.
- **요구사항**:
  - ① 사용자 입력값을 동적 응답페이지에 사용할 때 XSS 필터링 후 사용한다.
  - ② DB 조회결과를 동적 응답페이지에 사용할 때 HTML 인코딩 또는 XSS 필터링 후 사용한다.
- **코드/설정에서 확인할 것**:
  - 웹 컨테이너 Filter, MVC Interceptor, 공통 Validator로 XSS 필터/HTML 인코딩이 일괄 적용되는지
  - View(템플릿)에서 출력값 인코딩 여부 (이스케이프 해제 출력 — 예: JSP 스크립틀릿 `<%= %>`, `innerHTML`, `|safe`, `dangerouslySetInnerHTML` 등 — 존재 여부는 보충 점검)
  - DB에서 읽은 데이터도 외부입력으로 간주해 출력 전 검증하는지(저장형 XSS)
  - XSS 방어 라이브러리 사용: Lucy XSS Filter, OWASP ESAPI, HTML Sanitizer, HTML Purifier, MS AntiXSS 등
- **연관 구현단계 항목**: IMPL-1.04 크로스사이트 스크립트(XSS)

### KISA21-SR1-6 웹 기반 중요 기능 수행 요청 유효성 검증
- **설명**: 비밀번호 변경, 결제 등 권한 확인이 필요한 중요기능 수행 시 웹 요청의 유효성 검증방법 및 처리방법을 설계한다.
- **요구사항**:
  - ① 시스템으로 전송되는 모든 요청에 대해 정상 사용자의 유효한 요청인지 판별할 수 있어야 한다.
- **코드/설정에서 확인할 것**:
  - 세션별 CSRF 토큰 생성·세션 저장 → hidden 필드로 전달 → 데이터 처리 요청 시 세션 토큰과 비교하는 로직이 Interceptor/필터로 자동 적용되는지
  - 프레임워크 CSRF 방어 기능 활성화 여부(Spring Security 3.2+ CSRF, Django CSRF, OWASP CSRFGuard, CSRF Protector 등); CSRF 보호 비활성화 설정(예: `csrf().disable()`, `@csrf_exempt`) 여부
  - 중요기능에 CAPTCHA 등 사용자 상호작용 또는 재인증 요구 여부
- **연관 구현단계 항목**: IMPL-1.11 크로스사이트 요청 위조(CSRF)

### KISA21-SR1-7 HTTP 프로토콜 유효성 검증
- **설명**: 비정상 HTTP 헤더, 자동연결 URL 링크 등 원하지 않는 결과를 생성하는 HTTP 헤더·응답결과의 유효성 검증방법 및 처리방법을 설계한다.
- **요구사항**:
  - ① 외부입력값을 쿠키·HTTP 헤더에 사용할 때 HTTP 응답분할이 없도록 필터링한다.
  - ② 외부입력값이 리다이렉트/포워드 URL로 쓰일 때 허용된 URL 목록의 선택자로만 사용한다.
- **코드/설정에서 확인할 것**:
  - Cookie 설정, 응답 헤더 설정, Location(리다이렉트) 헤더에 들어가는 외부입력에서 `\r\n` 제거 여부
  - `sendRedirect`, `redirect:`, `Location` 등에 외부입력 URL이 그대로 들어가는지; 허용 URL 목록(소스 하드코딩 또는 XML/properties 설정)으로 제한되는지
- **연관 구현단계 항목**: IMPL-1.13 HTTP 응답분할, IMPL-1.07 신뢰되지 않는 URL 주소로 자동접속 연결

### KISA21-SR1-8 허용된 범위내 메모리 접근
- **설명**: 프로세스에 허용된 범위의 메모리 버퍼에만 읽기/쓰기하도록 검증방법 및 범위 초과 시 처리방법을 설계한다.
- **요구사항**:
  - ① C/C++ 등 프로그래머가 메모리를 관리하는 플랫폼에서는 버퍼 경계를 넘어 읽기/쓰기하지 않도록 경계설정·검사를 반드시 수행한다.
  - ② 버퍼오버플로우를 유발할 수 있는 취약한 API를 사용하지 않도록 통제한다.
- **코드/설정에서 확인할 것**:
  - 버퍼 접근 전 경계값 검사 여부
  - 취약 함수(보충 예: `strcpy`, `strcat`, `sprintf`, `gets`, `scanf("%s")`) 대신 길이 제한 안전 함수 사용
  - 빌드/실행 환경의 메모리 보호 정책: Non-executable Stack, ASLR(랜덤스택), StackGuard (컴파일 옵션 등)
  - (연관) printf 계열 포맷 문자열에 외부입력 직접 사용 여부
- **연관 구현단계 항목**: IMPL-1.16 메모리 버퍼 오버플로우, IMPL-1.17 포맷 스트링 삽입

### KISA21-SR1-9 보안기능 입력값 검증
- **설명**: 보안기능(인증, 권한부여 등) 입력값과 함수의 외부입력값·수행결과의 유효성 검증방법 및 처리방법을 설계한다.
- **요구사항**:
  - ① 사용자의 역할·권한을 결정하는 정보는 서버에서 관리한다.
  - ② 쿠키, 환경변수, 파라미터 등 외부입력값이 보안기능 함수 인자로 쓰일 때 검증 후 제한적으로 사용한다.
  - ③ 중요 상태정보·인증·권한결정 정보는 쿠키로 전송하지 않으며, 불가피하면 암호화해 전송한다.
- **코드/설정에서 확인할 것**:
  - 권한/역할/인증상태 판단이 서버 측 세션·DB 값이 아닌 쿠키·hidden 필드·파라미터(예: `role=admin`, `isAdmin=true`, `auth=Y`)에 의존하는지
  - 클라이언트 측 검증과 서버 측 검증이 동일하게 구현되었는지(클라이언트 검증만 존재하지 않는지)
  - 외부입력값 사용 전 NULL 체크 여부
  - 중요정보 포함 쿠키의 암호화 또는 HMAC 등 메시지인증코드로 서버 측 무결성 검증 여부
  - (연관) 외부입력 숫자값을 크기·반복·메모리 할당에 쓸 때 범위 검사(정수형 오버플로우)
- **연관 구현단계 항목**: IMPL-1.15 보안기능 결정에 사용되는 부적절한 입력값, IMPL-1.14 정수형 오버플로우, IMPL-5.01 Null Pointer 역참조

### KISA21-SR1-10 업로드·다운로드 파일 검증
- **설명**: 업로드·다운로드 파일의 무결성, 실행권한 등의 유효성 검증방법 및 부적합 파일 처리방법을 설계한다.
- **요구사항**:
  - ① 업로드 저장 파일의 타입, 크기, 개수, 실행권한을 제한한다.
  - ② 업로드 저장 파일은 외부에서 식별되지 않아야 한다.
  - ③ 파일 다운로드 요청 시 요청 파일명을 검증한다.
  - ④ 다운로드 받은 소스코드·실행파일은 무결성 검사를 수행한다.
- **코드/설정에서 확인할 것**:
  - 업로드 크기 제한 설정(예: Spring `MultipartResolver`의 `maxUploadSize`(가이드 예시 20971520=20MB), `maxInMemorySize`(1048576=1MB)); 파일 개수 제한
  - 확장자와 MIME-Type을 동시에 검사하는 공통 필터 모듈 적용, 서버·클라이언트 동일 정책
  - 업로드 디렉터리가 웹 루트 밖(URL로 직접 접근 불가)인지, 업로드 경로 파일에 실행권한이 없고 서버 설정으로 실행되지 않는지
  - 저장 파일명을 랜덤 생성하고 원본명↔저장명 매핑을 DB에 저장하는지
  - 다운로드 컨트롤러에서 파일명의 `..`, `/`, `\` 필터링, 허가된 사용자·허가된 파일인지 확인, 허용 파일 화이트리스트 적용
  - (설계 권고) 다운로드 파일 악성코드/바이러스 검사
  - 원격 다운로드 파일 사용·실행 전 체크섬(해시 등)·전자서명 검증 여부
- **연관 구현단계 항목**: IMPL-1.06 위험한 형식 파일 업로드, IMPL-2.10 부적절한 전자서명 확인, IMPL-2.15 무결성 검사 없는 코드 다운로드

## 2. 보안기능

### KISA21-SR2-1 인증 대상 및 방식
- **설명**: 중요정보·기능의 특성에 따라 인증방식을 정의하고 정의된 인증방식을 우회하지 못하게 설계한다.
- **요구사항**:
  - ① 중요기능·리소스에는 "인증 후 사용" 정책을 적용한다.
  - ② 안전한 인증방식을 사용해 인증우회·권한상승이 발생하지 않게 한다.
  - ③ 중요기능에 2단계(2-factor) 인증을 고려한다.
- **코드/설정에서 확인할 것**:
  - 중요기능 URL/메소드에 중앙집중식 인증(필터, Spring Security, 인터셉터 등)이 일괄 적용되는지; 인증 예외(permitAll 등)에 중요기능이 포함되지 않는지
  - 인증정보가 서버 측에 저장되고 서버에서 인증 여부를 확인하는지(클라이언트 값 신뢰 금지)
  - OTP 적용 시: 시간 제한(금융영역 30~60초), 6자리 이상 숫자·문자, 중복·유추 불가
  - 2단계 인증: Type1(지식), Type2(소유), Type3(생체) 중 2개 이상
  - (연관) 인증서 유효성 검증 비활성화(모든 인증서 신뢰하는 TrustManager/HostnameVerifier, `verify=False` 등) 여부, DNS lookup(호스트명) 기반 보안결정 여부, 서버 측 요청 URL에 외부입력 사용(SSRF)
- **연관 구현단계 항목**: IMPL-1.12 서버사이드 요청 위조, IMPL-2.01 적절한 인증 없는 중요기능 허용, IMPL-2.11 부적절한 인증서 유효성 검증, IMPL-7.01 DNS lookup에 의존한 보안결정

### KISA21-SR2-2 인증 수행 제한
- **설명**: 반복된 인증 시도를 제한하고 인증 실패 이력을 추적하도록 설계한다.
- **요구사항**:
  - ① 로그인 시 인증시도 횟수를 제한하고 초과 시 인증제한 정책을 적용한다.
  - ② 실패한 인증시도 정보를 로깅해 추적 가능하게 한다.
- **코드/설정에서 확인할 것**:
  - 로그인 실패 횟수 3~5회 이내 제한, 초과 시 계정 잠금 또는 추가 정보 요구
  - 사용자 테이블에 로그인 실패 횟수, 계정 잠금 여부, 마지막 성공·실패 로그인 시간, 로그아웃 시간 컬럼 존재 및 갱신 로직
  - 사용자ID별·세션ID별 실패 횟수 추적
  - 자동입력방지(CAPTCHA: reCAPTCHA 등) 적용 여부
  - 로그인 실패 시 로깅 코드 존재
- **연관 구현단계 항목**: IMPL-2.16 반복된 인증시도 제한 기능 부재

### KISA21-SR2-3 비밀번호 관리
- **설명**: 생성규칙, 저장방법, 변경주기 등 비밀번호 관리정책별 안전한 적용방법을 설계한다.
- **요구사항**:
  - ① 비밀번호 설정 시 KISA 안내서의 안전한 비밀번호 생성규칙을 적용한다.
  - ② 네트워크 전송 시 비밀번호를 암호화하거나 암호화된 통신채널을 이용한다.
  - ③ 저장 시 솔트를 적용한 안전한 해시함수를 사용하고 해시는 서버에서 수행한다.
  - ④ 비밀번호 재설정/변경 시 안전한 규칙을 정의·적용한다.
  - ⑤ 비밀번호 관리 규칙을 정의·적용한다.
- **코드/설정에서 확인할 것**:
  - 비밀번호 정책 검증 로직: 2종류 이상 문자 조합 시 8자리 이상, 또는 10자리 이상 (문자 종류: 영대문자·영소문자·특수문자·숫자); 동일문자 반복('123123'), 키보드 연속('qwerty'), 숫자가 맨 앞/뒤, 개인정보(이름·생일·전화번호), 이용자ID 포함, 사전 단어, 초기/예제 비밀번호 등 거부
  - 로그인/비밀번호 전송 경로에 TLS 적용; TLS 1.2 안전 암호군 예: `TLS_ECDHE_ECDSA_WITH_AES_128_GCM_SHA256`, `TLS_ECDHE_ECDSA_WITH_AES_256_GCM_SHA384`, `TLS_ECDHE_RSA_WITH_AES_128_GCM_SHA256`, `TLS_ECDHE_RSA_WITH_AES_128_CBC_SHA256`, `TLS_RSA_WITH_AES_256_GCM_SHA384` 등(표 3-15)
  - 비밀번호를 평문·가역 암호화·단순 해시(솔트 없는 SHA-256 등)로 저장하지 않는지; 사용자별 고유 솔트, 솔트 길이 32바이트 이상; 해시를 클라이언트가 아닌 서버에서 수행
  - 변경 시 이전 비밀번호 재사용 금지/연관성 없음 검사
  - 재설정: 본인확인(I-PIN, 휴대전화, 질의답변 등) 후 등록 이메일로 재설정 링크 발송 (비밀번호 자체를 응답/메일로 노출하지 않음)
  - 변경주기 3개월(또는 6개월), 만료 시 로그인 시 변경 요구, 마지막 성공 로그인 시간 저장·사용자 통지
  - 소스·설정에 하드코드된 비밀번호, 초기 비밀번호 사용 여부
- **연관 구현단계 항목**: IMPL-2.06 하드코드된 중요정보, IMPL-2.09 취약한 비밀번호 허용

### KISA21-SR2-4 중요자원 접근통제
- **설명**: 중요자원(프로그램 설정, 민감한 사용자 데이터 등)을 정의하고 신뢰할 수 있는 접근통제 방법(권한관리 포함) 및 접근통제 실패 시 처리방법을 설계한다.
- **요구사항**:
  - ① 중요자원에 대한 접근통제 정책을 수립·적용한다.
  - ② 중요기능에 대한 접근통제 정책을 수립·적용한다.
  - ③ 관리자 페이지에 대한 접근통제 정책을 수립·적용한다.
- **코드/설정에서 확인할 것**:
  - RBAC/ACL 기반 인가가 적용되는지(Spring Security ACL, .NET, PHP-RBAC 등); 최소권한·권한분리 원칙
  - 메소드 호출 전·후(반환 객체 포함) 사용자 권한 검증, 사용자별·그룹별 접근 체크 (객체 소유자 확인 등)
  - 익명·일반·특권사용자·관리자 영역 구분
  - 파라미터 변조 여부 확인 절차(예: 사용자 ID·객체 ID를 파라미터로 받아 권한 확인 없이 처리하지 않는지)
  - 상위권한 사용 시 가능한 마지막에 상승하고 종료 즉시 원복
  - 파일/디렉터리 생성 시 과도한 권한(예: world-writable) 설정 여부 (보충 예: `chmod 777`, `umask 0`)
  - 관리자 페이지: 추측 어려운 URL, TLS 사용, 접속 허용 IP 제한, 80번이 아닌 별도 포트, 추가인증
- **연관 구현단계 항목**: IMPL-2.02 부적절한 인가, IMPL-2.03 중요한 자원에 대한 잘못된 권한 설정

### KISA21-SR2-5 암호키 관리
- **설명**: 암호키 생성, 분배, 접근, 파기 등 생명주기별 암호키 관리방법을 안전하게 설계한다.
- **요구사항**:
  - ① DB 데이터 암호화용 암호키는 KISA 「암호이용안내서」(본문: 「암호 키 관리 안내서」)의 관리 방법을 적용한다.
  - ② 설정파일(xml, properties) 내 중요정보 암호화용 암호키는 암호화해서 별도 디렉터리에 보관한다.
- **코드/설정에서 확인할 것**:
  - 암호키가 소스코드·설정파일·주석에 하드코드되지 않았는지
  - DB 암호화 키가 DB와 물리적으로 분리된 장소에 보관되는지
  - 비밀번호·암호키를 메모리에 장기 보관하지 않고, 불가피 시 사용 후 0으로 초기화하는지 (예: `String` 대신 `char[]`/`byte[]` 후 덮어쓰기 — 보충)
  - 키 생성·변경 시 백업 기능, 키 종류별 유효기한 설정(NIST: 대칭 비밀키 송신자 최대 2년/수신자 송신자기간+3년 이하, 암호화 공개키·복호화 개인키 최대 2년, 검증용 공개키 1~3년), 기한 경과 시 신규 키 생성 권고
  - 설정파일 내 중요정보 암호화 키는 마스터키로 암호화해 별도 디렉터리에 보관
  - (설계) 키 생명주기(생성·사용·폐기)·키 복구 절차, FIPS 140-2 레벨 선택
- **연관 구현단계 항목**: IMPL-2.06 하드코드된 중요정보, IMPL-2.13 주석문 안에 포함된 시스템 주요정보

### KISA21-SR2-6 암호연산
- **설명**: 국제표준 또는 검증필 암호모듈 등재 안전 알고리즘을 선정하고 충분한 키 길이, 솔트, 충분한 난수를 적용한 암호연산 방법을 설계한다.
- **요구사항**:
  - ① 대칭/비대칭 암·복호화 시 KISA 「암호 알고리즘 및 키 길이 이용 안내서」의 알고리즘과 안전한 키 길이를 사용한다.
  - ② 복호화되지 않는 암호화(해시) 시 안전한 해시 알고리즘과 솔트를 적용한다.
  - ③ 난수 생성 시 안전한 난수 생성 알고리즘을 사용한다.
- **코드/설정에서 확인할 것**:
  - 권고 대칭키: SEED, ARIA-128/192/256, AES-128/192/256 (그 외 표 3-20: Camellia, Blowfish, MISTY1, KASUMI 등); 권고 비대칭: RSA, RSAES-OAEP, KCDSA, ECC, ECKCDSA, ElGamal
  - 키 길이(2011~2030년 이후 사용 기준 보안강도 112비트 이상): 대칭 3TDEA/AES-128 이상, RSA·이산대수 2048비트 이상(128비트 강도는 3072), ECC 224비트 이상(128비트 강도는 256). 80비트 강도(2TDEA, RSA 1024, ECC 160)는 ~2010년까지만 (표 3-19)
  - DES, 2TDEA, RC4, MD5 등 취약 알고리즘 사용 여부 (보충: 가이드 표에 없는 MD5/RC4/DES는 구현단계 항목 기준), base64 등 단순 인코딩을 암호화로 사용하는지
  - 해시: 보안강도 112비트 이상이면 SHA-224/256/384/512 (SHA-1은 단순해시/전자서명 용도로 112비트 이상에서 제외); 비밀번호 등 해시 시 솔트 적용
  - 난수: 보안 목적 난수에 FIPS 140-2 인증 암호모듈의 난수생성기, 256비트 이상 시드 사용 (예: `java.util.Random`, `Math.random()`, `rand()` 대신 `SecureRandom` 등 — 보충)
  - (연관) 인증서 유효성 검증 생략 여부
- **연관 구현단계 항목**: IMPL-2.04 취약한 암호화 알고리즘 사용, IMPL-2.07 충분하지 않은 키 길이 사용, IMPL-2.08 적절하지 않은 난수 값 사용, IMPL-2.11 부적절한 인증서 유효성 검증, IMPL-2.14 솔트 없이 일방향 해쉬 함수 사용

### KISA21-SR2-7 중요정보 저장
- **설명**: 중요정보(비밀번호, 개인정보 등)를 저장·보관하는 방법이 안전하도록 설계한다.
- **요구사항**:
  - ① 중요정보·개인정보는 암호화해서 저장한다.
  - ② 불필요하거나 사용하지 않는 중요정보가 메모리에 남지 않게 한다.
- **코드/설정에서 확인할 것**:
  - 서버 DB·파일에 저장되는 중요정보가 SR2-6 기준 알고리즘·키로 암호화되는지
  - 쿠키, HTML5 로컬저장소(localStorage/sessionStorage) 등 클라이언트 측에 중요정보를 저장하지 않는지; 불가피 시 암호화
  - 중요 로직·주석은 클라이언트(HTML/JS)가 아닌 서버 측 코드에서만 처리
  - 사용 끝난 개인정보·금융정보 메모리 초기화
  - 민감 정보 포함 페이지의 사용자 측 캐싱 비활성화(캐시 제어 헤더 — 보충 예: `Cache-Control: no-store`), 캐싱 시 암호화
  - 인증정보 입력 폼의 자동완성 비활성화(`autocomplete="off"` — 보충)
  - 영속 쿠키(만료시간 설정)에 중요정보 저장 여부
- **연관 구현단계 항목**: IMPL-2.05 암호화되지 않은 중요정보, IMPL-2.12 사용자 하드디스크에 저장되는 쿠키를 통한 정보 노출

### KISA21-SR2-8 중요정보 전송
- **설명**: 중요정보(비밀번호, 개인정보, 쿠키 등)를 전송하는 방법이 안전하도록 설계한다.
- **요구사항**:
  - ① 인증정보 등 민감정보 전송 시 안전하게 암호화해서 전송한다.
  - ② 쿠키에 포함되는 중요정보는 암호화해서 전송한다.
- **코드/설정에서 확인할 것**:
  - 중요정보 전송 구간의 TLS/VPN 등 안전한 통신채널 적용(HTTP 평문 엔드포인트, 평문 소켓 전송 여부), 또는 SR2-6 기준 암호모듈로 암호화 후 전송
  - hidden 필드, Ajax 변수, 쿠키, 헤더, HTTP 응답헤더로 불필요하게 많은 데이터를 주고받지 않는지
  - 중요정보 포함 쿠키는 세션쿠키(만료시간 미설정)로 설정되고 값이 암호화되는지
- **연관 구현단계 항목**: IMPL-2.05 암호화되지 않은 중요정보

## 3. 에러처리

### KISA21-SR3-1 예외처리
- **설명**: 오류메시지에 중요정보(개인정보, 시스템 정보, 민감정보 등)가 노출되거나 부적절한 에러·오류 처리로 의도치 않은 상황이 발생하지 않도록 설계한다.
- **요구사항**:
  - ① 명시적 예외는 예외처리 블록으로 예외 발생 시 수행할 기능을 구현한다.
  - ② 런타임 예외는 입력값 범위를 체크해 정상 동작 가능한 값만 사용되도록 보장한다.
  - ③ 에러 발생 시 상세 에러 정보가 사용자에게 노출되지 않게 한다.
- **코드/설정에서 확인할 것**:
  - 예외를 catch 후 적절히 처리·로깅하는지 (Logger API 사용, `printStackTrace()`·`System.out` 출력 대신)
  - 입력값에 따라 예외가 날 수 있는 지점(인덱스, 형변환, 0 나눗셈 등)에서 범위 검사
  - 에러 발생 시 지정된 에러 페이지로 응답: 예) `web.xml`의 `<error-page>`로 404, 500, `java.lang.Throwable`을 공통 에러 JSP에 매핑
  - 사용자 응답 오류 메시지에 스택트레이스, 예외 메시지, SQL·경로·서버 버전 등 시스템정보·개인정보 미포함 (디버그/상세 에러 출력 설정 비활성화 여부)
- **연관 구현단계 항목**: IMPL-4.01 오류 메시지 정보노출 (보충: 4.02 오류상황 대응 부재, 4.03 부적절한 예외처리도 ①② 점검과 관련)

## 4. 세션통제

### KISA21-SR4-1 세션통제
- **설명**: 다른 세션 간 데이터 공유금지, 세션ID 노출금지, (재)로그인 시 기존 세션ID 재사용금지 등 안전한 세션 관리방안을 설계한다.
- **요구사항**:
  - ① 세션 간 데이터가 공유되지 않도록 설계한다.
  - ② 세션이 안전하게 관리되도록 한다.
  - ③ 세션ID가 안전하게 관리되도록 한다.
- **코드/설정에서 확인할 것**:
  - 컨트롤러·싱글톤 서비스 컴포넌트(Servlet, Spring Bean 등)에 읽기/쓰기 가능한 클래스 멤버 변수·static 변수로 사용자/요청별 데이터를 저장하지 않는지
  - 모든 페이지에서 로그아웃 가능, 로그아웃 시 세션 완전 제거(Java `session.invalidate()`)
  - 세션 타임아웃: 중요기능 2~5분, 위험도 낮은 애플리케이션 15~30분 (예: `web.xml` `<session-timeout>`, `server.servlet.session.timeout` — 설정 키는 보충); 미사용 세션 서버 측 강제 삭제
  - 이전 세션 미종료 상태에서 새 세션 생성 방지; 중복 로그인 불허 시 기존 세션 종료 또는 신규 연결 차단 정책
  - 세션ID 쿠키에 HttpOnly 속성 설정
  - 비밀번호 변경 시 현재 활성 세션 삭제 후 재할당
  - 세션ID는 서버에서 생성, 최소 128비트, 안전한 난수 알고리즘으로 예측 불가
  - URL Rewrite(URL에 세션ID 포함, 예: `;jsessionid=`) 미사용
  - 로그인 성공 시 기존 세션ID 파기 후 재발급(세션 고정 대응); 장기 접속 시 주기적 세션ID 재할당
- **연관 구현단계 항목**: IMPL-6.01 잘못된 세션에 의한 데이터 정보 노출
