from pathlib import Path
import re, json, html, hashlib, unicodedata
from PIL import ImageFont

ROOT = Path(__file__).resolve().parents[2]
OUT = Path(__file__).resolve().parent
files = [ROOT/'Plan'/n for n in ['Implementation_Plan.md','01_UX_Flow.md','02_Data_Design.md','03_Architecture_and_Dependencies.md','04_Functional_Specification.md','05_Engineering_Constraints.md']]
sources = {p.name:p.read_text(encoding='utf-8-sig') for p in files}
font = ImageFont.truetype('C:/Windows/Fonts/malgun.ttf',22)
records=[]
for p in files:
    lines=sources[p.name].splitlines(); starts=[]; fenced=False
    for i,line in enumerate(lines):
        if line.startswith('```'): fenced=not fenced
        if not fenced and re.match(r'^#{1,4} ',line): starts.append(i)
    for j,i in enumerate(starts):
        end=starts[j+1] if j+1<len(starts) else len(lines)
        title=re.sub(r'^#+ ','',lines[i]); raw='\n'.join(lines[i:end])
        task=re.match(r'(W\d{2}-\d{2}) · (.*)',title)
        group=re.match(r'(W\d{2}) · (.*)',title)
        rid=task[1] if task else f'd{files.index(p)}s{j}'
        dep=re.search(r'\*\*먼저 완료:\*\* ([^\n]+)',raw)
        records.append(dict(id=rid,title=title,raw=raw,source='Plan/'+p.name,line=i+1,end=end,
            kind='task' if task else 'group' if group else 'section',group=task[1][:3] if task else group[1] if group else None,
            deps=list(dict.fromkeys(re.findall(r'W\d{2}-\d{2}',dep[1]))) if dep else []))
tasks=[r for r in records if r['kind']=='task']; groups=[r for r in records if r['kind']=='group']
assert len(tasks)==106 and len(groups)==14
ids={r['id'] for r in records}; assert all(d in ids for r in tasks for d in r['deps'])

def clean(raw):
    raw=re.sub(r'```mermaid\n.*?```','[도식 원문은 상세 패널에 보존 · 작업 선행관계는 선택 시 지도에 표시]',raw,flags=re.S)
    raw=re.sub(r'\[([^\]]+)\]\([^\n]*?\)',r'\1',raw)
    result=[]
    for line in raw.splitlines()[1:]:
        if line.startswith('```') or re.match(r'^\s*[|\- :]+$',line) or '전체 구현 지도로 돌아가기' in line: continue
        line=line.replace('**','').replace('`','').lstrip('> ').strip()
        if line: result.append(line)
    return result

def wrap(line,width,size=22):
    f=font if size==22 else ImageFont.truetype('C:/Windows/Fonts/malgun.ttf',size)
    result=[]; current=''
    for c in line:
        if current and f.getlength(current+c)>width:
            result.append(current); current=c
        else: current+=c
    if current:result.append(current)
    return result

W=8400; parts=[]
def text(x,y,s,size=22,color='#233247',weight=400,cls=''):
    parts.append(f'<text class="{cls}" x="{x}" y="{y}" font-size="{size}" font-weight="{weight}" fill="{color}">{html.escape(str(s))}</text>')
def rect(x,y,w,h,fill='#ffffff',stroke='#d7e0e9',radius=16):
    parts.append(f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="{radius}" fill="{fill}" stroke="{stroke}"/>')
def edge(x1,y1,x2,y2,color='#6b8199'):
    parts.append(f'<path d="M{x1},{y1} L{x2},{y2}" fill="none" stroke="{color}" stroke-width="7" marker-end="url(#arrow)"/>')
def card(r,x,y,w=1100):
    body=[]
    for line in clean(r['raw']): body.extend(wrap(line,w-64))
    titlelines=wrap(r['title'],w-64,32)
    h=85+len(titlelines)*42+len(body)*33
    r.update(x=x,y=y,w=w,h=h)
    parts.append(f'<g class="node" data-id="{r["id"]}">')
    rect(x,y,w,h, '#f8fbff' if r['kind']=='task' else '#ffffff')
    yy=y+46
    for line in titlelines:text(x+32,yy,line,32,'#153d59',500,'node-title'); yy+=42
    text(x+32,yy,f'{r["source"]} : {r["line"]}',17,'#64748b',cls='detail'); yy+=35
    if r['kind']=='task': text(x+w-210,y+46+len(titlelines)*42,'계획 · 미착수',18,'#64748b')
    for line in body:text(x+32,yy,line,22,cls='detail'); yy+=33
    parts.append('</g>')
    return h

rect(0,0,W,2300,'#eef5fa',radius=0)
text(100,180,'다시잇다',140,'#17354b',500)
text(880,172,'개발 전체 지도',94,'#17354b',500)
text(100,272,'Plan v1.1 · 2026-10-13 기준 · 14개 영역 / 106개 작업 · 구현 상태는 문서 기준 전부 미착수',43,'#556b7e')
text(100,380,'경험 → 확정 → 실제 공고 → 신청 준비',82,'#17354b',500)
text(100,467,'비회원 전체 이용  ·  승인 프로필·지원서만 선택 저장  ·  공식 신청 안내 이동',42,'#556b7e')
text(100,595,'01  사용자 여정',50,'#17354b',500)
steps=['시작·동의','대화·전사 확인','프로필 확정','역할·추천','공고·자격 대조','지원서·공식 안내','선택 저장·삭제']
for i,s in enumerate(steps):
    x=100+i*1180
    rect(x,640,1080,145,'#ffffff')
    text(x+34,726,s,52,'#153d59',500)
    if i<6:edge(x+1095,710,x+1160,710)
text(100,900,'02  시스템과 신뢰 경계',50,'#17354b',500)
arch=[('브라우저','React · TypeScript · Vite'),('Nginx / HTTPS','화면 / API 경로 유지'),('FastAPI','API → 서비스 → Adapter'),('EC2 내부 추론','Ollama Qwen3 / STT / TTS'),('Redis','임시 체험 · 세션 · 한도'),('별도 RDS','PostgreSQL · 승인 본문 암호화'),('외부 연동','카카오 / 승인 공고 출처')]
for i,(a,b) in enumerate(arch):
    x=100+i*1180; rect(x,950,1080,185,'#ffffff');text(x+32,1016,a,45,'#153d59',500);text(x+32,1080,b,30)
for a,b in [(0,1),(1,2),(2,3)]:edge(100+a*1180+1085,1040,100+b*1180-20,1040)
text(100,1210,'모델·Redis·RDS 비공개 / RDS TLS 검증 / AI·음성은 EC2 자체 처리 / 사용자 기기 내 처리로 안내하지 않음',38,'#556b7e')
text(100,1360,'03  개발 경로 · 묶음 선택으로 상세 이동',50,'#17354b',500)
for i,g in enumerate(groups):
    x=100+(i%7)*1180;y=1410+(i//7)*275
    rect(x,y,1080,235,'#ffffff'); parts.append(f'<g class="jump" data-id="{g["id"]}">')
    text(x+30,y+65,g['group'],55,'#153d59',500)
    for j,line in enumerate(wrap(g['title'].split(' · ',1)[1],1020,42)):text(x+30,y+126+j*50,line,42,'#233247',500)
    text(x+30,y+205,f'{sum(t["group"]==g["group"] for t in tasks)}개 작업 · 세부 선행 ID 기준',28,'#64748b');parts.append(f'<rect x="{x}" y="{y}" width="1080" height="235" fill="transparent"/></g>')
text(100,2120,'계약·기반 → 모델 + 공고 + 화면 → 확정·자격·추천 → 저장·삭제 → 통합·복구·제출',46,'#17354b',500)
text(100,2220,'목표: G1 10/15 · G2 10/18 · G3 10/23 · G4 10/26 · G5 10/29 · G6 10/30 18:00 KST',40,'#556b7e')

archstart=2400
architecture_parts_start=len(parts)
text(100,archstart+100,'04  시스템 아키텍처  /  서비스 · 데이터 · 신뢰 경계',86,'#17354b',500)
text(100,archstart+185,'설계 명세를 도식화 · 컴포넌트 클릭 시 근거 원문 · 운영 준비/성능 검증 완료를 의미하지 않음',36,'#556b7e')
ay=archstart+240
rect(1300,ay+100,5550,1930,'#e6f0f7','#a7bdcf',26)
text(1360,ay+190,'AWS EC2 · Docker Compose · 내부 네트워크',48,'#17354b',500)
text(1360,ay+1950,'외부 공개: Nginx HTTPS / Ollama·음성·Redis 포트 비공개 / 모델 적재는 사용자 요청 전에 수행',34,'#556b7e')

def archref(title):
    return next(r['id'] for r in records if r['source']=='Plan/03_Architecture_and_Dependencies.md' and r['title']==title)

def component(x,y,w,h,title,lines,ref,fill='#ffffff'):
    parts.append(f'<g class="arch-node" data-id="{ref}">')
    rect(x,y,w,h,fill)
    yy=y+62
    for s in wrap(title,w-64,44):text(x+32,yy,s,44,'#153d59',500,'node-title');yy+=54
    yy+=14
    for line in lines:
        for s in wrap(line,w-64,30):text(x+32,yy,s,30);yy+=42
    parts.append('</g>')

def route(points,label,lx,ly):
    path='M'+' L'.join(f'{x},{y}' for x,y in points)
    parts.append(f'<path class="arch-route" d="{path}" fill="none" stroke="#6b8199" stroke-width="7" marker-end="url(#arrow)"/>')
    if label:text(lx,ly,label,28,'#516b80')

systemref=archref('1. 시스템 구성');netref=archref('1.1 Nginx·네트워크·RDS 경계');modelref=archref('1.2 텍스트·음성 로컬 추론 계약');modref=archref('2. 모듈 책임과 의존성');apiref=archref('3. API 계약');storeref=archref('3.2 로그인 왕복의 일회성 저장');reqref=archref('4. 공통 요청·오류·처리')
# 연결선을 먼저 그려 컴포넌트 본문을 가리지 않는다.
route([(1150,ay+500),(1430,ay+500)],'HTTPS',1170,ay+460)
route([(2460,ay+500),(2750,ay+500)],'/api/v1',2480,ay+460)
route([(1940,ay+740),(1940,ay+880)],'정적 화면 · /',1970,ay+820)
route([(5330,ay+430),(5530,ay+430),(5530,ay+510),(5600,ay+510)],'LLM Adapter',5360,ay+365)
route([(5330,ay+800),(5500,ay+800),(5500,ay+990),(5600,ay+990)],'Speech Adapter',5340,ay+750)
route([(5330,ay+1230),(5480,ay+1230),(5480,ay+1450),(5600,ay+1450)],'임시 저장·원자 제한',5335,ay+1190)
route([(4100,ay+1430),(4100,ay+1740),(6970,ay+1740),(6970,ay+1260),(7100,ay+1260)],'SQLAlchemy 저장소 · VPC 비공개 TLS / CA·호스트 검증',4150,ay+1680)
route([(5000,ay+330),(5000,ay+240),(7650,ay+240),(7650,ay+330)],'인증 코드 교환 · state 검증 / 내부 세션 교체',5410,ay+215)
route([(2460,ay+1390),(2610,ay+1390),(2610,ay+1810),(7010,ay+1810),(7010,ay+1390),(7100,ay+1390)],'검수 대기 공고 저장 · 운영자 승인 후 공개',3120,ay+1870)
route([(1430,ay+1390),(1150,ay+1390)],'고정 대상',1160,ay+1340)
component(100,ay+330,1050,500,'사용자·운영자 브라우저',['React · TypeScript','Android Chrome / iPhone Safari','PC Chrome · 녹음·전사 확인','확정·승인 / 선택 저장'],systemref)
component(1430,ay+330,1030,410,'Nginx · HTTPS',['프론트엔드 컨테이너','/api/* → FastAPI · 접두사 유지','요청 크기 / 콜백 로그 제어'],netref)
component(1430,ay+880,1030,310,'React 정적 빌드',['Vite 빌드 파일 · 화면 라우트','운영 Vite 서버 공개 없음'],systemref)
component(2750,ay+330,2580,1100,'FastAPI · Python 3.12',['Pydantic / OpenAPI / SQLAlchemy · API → 서비스 → 저장소/Adapter','공통: 동의 · 소유권 · CSRF · 리비전 · 요청 ID · 호출 한도'],apiref,'#f7fbff')
modules=[('Auth / Consent','카카오·세션·MFA / 목적별 동의'),('Journey / Profile','초안·확정·불변 버전·TTL'),('AI / Speech','내부 호출·스키마·근거·슬롯'),('Opportunity / Ingestion','정규화·중복·변경·공개본'),('Eligibility','원문 조건·AND/OR·3상태'),('Recommendation','자격 필터·경험 근거·정렬'),('Application','직접/생성·편집·승인·저장'),('Administration','검수·신고·운영 상태·감사'),('Security / Operations','암호화·키·삭제·복구·로그')]
for i,(title,desc) in enumerate(modules):
    component(2790+(i%3)*830,ay+585+(i//3)*255,780,230,title,[desc],modref,'#eef5fa')
component(5600,ay+330,1100,355,'Ollama + Qwen3',['후보: qwen3:4b','내부 /api/chat · JSON Schema','검증 후 digest 고정 / Cloud OFF'],modelref)
component(5600,ay+800,1100,420,'로컬 음성 서비스',['STT: faster-whisper · 다국어 small','TTS: Qwen3-TTS 0.6B · Sohee','음성 메모리/tmpfs · 영구 저장 없음','LLM/STT/TTS 공유 슬롯 초기 1개'],modelref)
component(5600,ay+1340,1100,310,'Redis · 임시 데이터',['체험·세션·저장 대기·멱등키·한도','RDB / AOF 개인정보 영속화 없음'],reqref)
component(1430,ay+1280,1030,365,'공고 수집 실행 명령',['6시간 주기 · 출처 제한 우선','안전한 파싱 · 실패≠모집 종료','사용자 개인정보 접근 없음'],systemref)
component(100,ay+1280,1050,400,'승인 출처·공식 자료',['취업·공공일자리 / 봉사','출처별 고정 API·공식 URL','승인 지연 시 공식 자료 수동 검수','SSRF·XXE·응답 크기 방어'],systemref)
component(7100,ay+330,1190,330,'카카오 로그인',['EC2 밖 외부 인증 경계','state · 허용 콜백 · 세션 교체','로그인 성공만으로 저장 안 함'],storeref)
component(7100,ay+850,1190,870,'Amazon RDS PostgreSQL',['EC2 밖 · 동일 VPC 비공개 접근','EC2 보안 그룹에서만 DB 연결','Alembic · 최소권한 DB 계정','User / Consent / ProfileVersion','ApplicationDraft / RoleDefinition','Source / IngestionRun / OpportunityVersion','Report / AuditEvent / DeletionRecord','승인 개인 본문 AES-256-GCM','키 분리 · 백업 7일 · 삭제 재적용'],netref)
text(100,ay+2150,'추론 경로: 녹음 → 로컬 STT → 전사 확인 → Qwen3 → 초안 → 사용자 확정 / 표시 내용 참조 → 로컬 TTS → 재생',40,'#17354b',500)
text(100,ay+2250,'저장 경로: 확정/승인 → 선택 로그인·저장 동의 → 소유권·버전 재검사 → 암호화 RDS / 삭제·만료 뒤 늦은 결과 폐기',40,'#17354b',500)
archheight=2600
architecture_fragment=''.join(parts[architecture_parts_start:])

text(100,archstart+archheight+150,'05  실행 작업  /  담당 · 선행 · 3단계 · 완료 조건',86,'#17354b',500)
taskstart=archstart+archheight+250; rowstart=taskstart
for row in range(2):
    bottoms=[]
    for col in range(7):
        g=groups[row*7+col]; x=100+col*1180;y=rowstart
        h=card(g,x,y,1100);y+=h+30
        for t in [t for t in tasks if t['group']==g['group']]:y+=card(t,x,y,1100)+30
        bottoms.append(y)
    rowstart=max(bottoms)+150

specstart=rowstart+80
text(100,specstart,'06  설계·계약·검증 원문  /  6개 문서의 모든 절',86,'#17354b',500)
labels=['실행 계획 보충','사용자 여정','데이터 계약','아키텍처·API','기능 F01~F11','제약·보안·검증']
columnw=1300; bottoms=[specstart+250]*6
for col,label in enumerate(labels):
    text(100+col*1370,specstart+165,label,48,'#153d59',500)
queues=[[r for r in records if r['source']=='Plan/'+p.name and r['kind']=='section'] for p in files]
while any(queues):
    for queue in queues:
        if not queue:continue
        r=queue.pop(0);col=min(range(6),key=lambda c:bottoms[c]);x=100+col*1370;y=bottoms[col]
        bottoms[col]+=card(r,x,y,columnw)+30
H=max(bottoms)+200
text(100,H-80,'출처: Plan 폴더 6개 Markdown · 도식화한 개요는 탐색용 · 상세 패널에 절별 원문 보존 · 일정은 목표 / 통과 증거는 별도',31,'#64748b')
defs='<defs><marker id="arrow" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="4" markerHeight="4" orient="auto"><path d="M0,0 L10,5 L0,10 z" fill="#6b8199"/></marker></defs>'
svg=f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" viewBox="0 0 {W} {H}" font-family="Malgun Gothic, Noto Sans KR, sans-serif"><title>다시잇다 개발 전체 지도</title><desc>14개 작업 영역, 106개 작업, 6개 계획 문서의 모든 절을 연결한 개발 지도. 확대하여 상세 내용을 확인합니다.</desc>{defs}<rect width="{W}" height="{H}" fill="#edf2f7"/><g id="selection-edges"/>'+''.join(parts)+'</svg>'
(OUT/'development-map.svg').write_text(svg,encoding='utf-8')
(OUT/'system-architecture.svg').write_text(f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{archheight}" viewBox="0 {archstart} {W} {archheight}" font-family="Malgun Gothic, sans-serif"><title>다시잇다 시스템 아키텍처</title>{defs}<rect y="{archstart}" width="{W}" height="{archheight}" fill="#edf2f7"/>{architecture_fragment}</svg>',encoding='utf-8')
payload=dict(records=records,sources=sources,width=W,height=H,overview=[0,0,W,2300],architecture=[0,archstart,W,archheight],tasks=[0,taskstart-150,W,specstart-taskstart+150],specs=[0,specstart-130,W,H-specstart+130])
(OUT/'map-data.json').write_text(json.dumps(payload,ensure_ascii=False,indent=2),encoding='utf-8')
template=(OUT/'viewer-template.html').read_text(encoding='utf-8')
encoded=json.dumps(payload,ensure_ascii=False).replace('<','\\u003c').replace('>','\\u003e').replace('&','\\u0026')
(OUT/'development-map.html').write_text(template.replace('<!--MAP-->',svg).replace('/*DATA*/',encoded),encoding='utf-8')
manifest={'sources':[{ 'path':'Plan/'+p.name,'sha256':hashlib.sha256(p.read_bytes()).hexdigest(),'sections':sum(r['source']=='Plan/'+p.name for r in records)} for p in files],'tasks':len(tasks),'groups':len(groups),'records':len(records),'dependency_edges':sum(len(t['deps']) for t in tasks),'svg_dimensions':[W,H]}
(OUT/'manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps(manifest,ensure_ascii=False))
