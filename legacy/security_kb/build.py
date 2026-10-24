"""Local, resumable transcription of the two supplied official security PDFs.

Run with the bundled Python. No example code is executed. Sources are read-only.
"""
from __future__ import annotations
import argparse, bisect, collections, hashlib, json, os, re
from pathlib import Path
from urllib.parse import quote, unquote
import pymupdf as pdf
import yaml

ROOT = Path(__file__).resolve().parents[2]
BASE = ROOT / 'SW개발보안_obsidian' / 'Security'
LEGACY = ROOT / 'legacy' / 'security_kb'
DATA = LEGACY / 'data'
CONFIG = [('Python-2023', 'Python*.pdf', 2023, 6, range(1, 5)),
          ('SW-Diagnosis-2021', '소프트*.pdf', 2021, 0, range(3, 7))]
VERSION = 1
CODE_VERSION = 4

def digest(data):
    return hashlib.sha256(data).hexdigest()

def write(path, text):
    path.parent.mkdir(parents=True, exist_ok=True)
    if not path.exists() or path.read_text(encoding='utf-8') != text:
        path.write_text(text, encoding='utf-8', newline='\n')

def norm(s):
    return re.sub(r'[\s\W_]+', '', s).lower()

def slug(s):
    return re.sub(r'\s+', '-', re.sub(r'[<>:"/\\|?*]', '-', s)).strip(' .-')[:110]

def link(src, target, label):
    rel = os.path.relpath(target, src.parent).replace('\\', '/')
    return f'[{label}]({quote(rel, safe="/-._")} )'.replace(' )', ')')

def chars(s):
    return collections.Counter(c for c in s if not c.isspace())

def line_data(page):
    result = []
    for bi, block in enumerate(page.get_text('dict')['blocks']):
        for ln in block.get('lines', []):
            spans = ln['spans']
            result.append(dict(text=''.join(s['text'] for s in spans),
                               bbox=list(ln['bbox']), block=bi,
                               size=max(s['size'] for s in spans),
                               fonts=list({s['font'] for s in spans})))
    return result

def code_regions(lines, book):
    # Numbered gutters provide explicit code boundaries, including blank lines.
    numbered = []
    for i, ln in enumerate(lines):
        m = re.match(r'^\s*(\d{1,3}):', ln['text'])
        if m and ln['bbox'][0] < 115:
            numbered.append((i, int(m[1]), ln))
    groups = []
    for item in sorted(numbered, key=lambda x: (x[2]['bbox'][1], x[2]['bbox'][0])):
        if (not groups or item[1] <= groups[-1][-1][1]
            or item[2]['bbox'][1] - groups[-1][-1][2]['bbox'][1] > 40):
            groups.append([])
        groups[-1].append(item)
    regions = []
    for gi,group in enumerate(groups):
        y0 = min(x[2]['bbox'][1] for x in group) - 1.2
        y1 = max(x[2]['bbox'][3] for x in group) + 1.2
        prior_end=max((x[2]['bbox'][3] for x in groups[gi-1]),default=0) if gi else 0
        labels=[ln for ln in lines if ln['bbox'][3]<y0 and ln['bbox'][1]>prior_end
                and y0-ln['bbox'][3]<120 and '코드' in ln['text']
                and ln['text'].startswith(('안전','취약'))]
        label=max(labels,key=lambda l:l['bbox'][1])['text'] if labels else ''
        if len(group)<2 and not labels:continue
        if labels:
            lab=max(labels,key=lambda l:l['bbox'][1]);y0=lab['bbox'][3]+0.1
        # Unnumbered comments and last-line wraps share the source code font.
        tail=sorted([ln for ln in lines if ln['bbox'][1]>y1-1],key=lambda l:l['bbox'][1])
        for ln in tail:
            if ln['size']>=9.5 or ln['bbox'][1]-y1>25 or re.match(r'^\s*\d{1,3}:',ln['text']):break
            if ln['bbox'][1]>y1-1:y1=max(y1,ln['bbox'][3]+1.2)
        indices = [i for i, ln in enumerate(lines)
                   if y0 <= (ln['bbox'][1]+ln['bbox'][3])/2 <= y1
                   and ln['bbox'][0] >= min(x[2]['bbox'][0] for x in group)-1]
        previous = [ln for ln in lines if ln['bbox'][3] <= y0 and y0-ln['bbox'][3] < 45]
        if previous and not label:
            label = max(previous, key=lambda l:l['bbox'][3])['text']
        language = 'text'
        if book == 'Python-2023':
            sample = ''.join(lines[i]['text'] for i in indices)
            language = 'html' if ('<form' in sample or '<script' in sample or '<input' in sample) else 'python'
        else:
            for token, lang in [('MyBatis','xml'),('XML','xml'),('JSP','jsp'),('C#','csharp'),('C++','cpp'),('JAVASCRIPT','javascript'),('JavaScript','javascript'),('JAVA','java'),('Java','java'),('PHP','php'),('Python','python'),('C언어','c')]:
                if token in label:
                    language=lang; break
            if re.search(r'\bC\s*$',label):language='c'
        # Keep original number labels: these are transcription blocks, not runnable code.
        rows=[]
        for idx in sorted(indices,key=lambda i:(lines[i]['bbox'][1],lines[i]['bbox'][0])):
            ln=lines[idx]
            if rows and abs(ln['bbox'][1]-rows[-1][0]) < 2:
                rows[-1][1].append(idx)
            else:
                rows.append([ln['bbox'][1],[idx]])
        text=[]
        for _, ids in rows:
            ids.sort(key=lambda i:lines[i]['bbox'][0])
            # Existing spaces (including NBSP) are retained. Add a delimiter only
            # between independent spans such as a gutter and its code line.
            value=lines[ids[0]]['text']
            for left,right in zip(ids,ids[1:]):
                gap=lines[right]['bbox'][0]-lines[left]['bbox'][2]
                spaces=1 if book=='Python-2023' else max(1,round(gap/(lines[right]['size']*0.26)))
                value+=' '*spaces+lines[right]['text']
            text.append(value)
        result='\n'.join(text)
        assert chars(result)==chars(''.join(lines[i]['text'] for i in indices))
        regions.append(dict(kind='code', indices=indices, text=result, language=language,
                            label=label, bbox=[min(lines[i]['bbox'][0] for i in indices),y0,
                                             max(lines[i]['bbox'][2] for i in indices),y1]))
    # Some source pages contain only unnumbered comments before the example
    # continues on the next page. Preserve those inside a code block as well.
    for lab in lines:
        label=lab['text']
        if not re.match(r'^(?:안전하지 않은|안전한|취약한) 코드(?:의 예| 예시)',label) or len(label)>60:
            continue
        if any(r['label']==label and r['bbox'][1]>lab['bbox'][1] and r['bbox'][1]-lab['bbox'][3]<120 for r in regions):
            continue
        ids=[];end=lab['bbox'][3]
        for i,ln in sorted(enumerate(lines),key=lambda x:x[1]['bbox'][1]):
            if ln['bbox'][1]<=lab['bbox'][3]:continue
            if ln['size']>=9.5 or ln['bbox'][1]-end>25:break
            ids.append(i);end=max(end,ln['bbox'][3])
        if not ids or any(set(ids).intersection(r['indices']) for r in regions):continue
        language='python' if book=='Python-2023' else ('java' if 'JAVA' in label else 'text')
        regions.append(dict(kind='code',indices=ids,text='\n'.join(lines[i]['text'] for i in ids),
                            language=language,label=label,
                            bbox=[min(lines[i]['bbox'][0] for i in ids),lab['bbox'][3]+0.1,
                                  max(lines[i]['bbox'][2] for i in ids),end]))
    return regions

def extract_page(page, book):
    lines=line_data(page)
    regions=code_regions(lines,book)
    occupied={i for r in regions for i in r['indices']}
    tables=[]
    for t in page.find_tables(strategy='lines_strict').tables:
        if t.row_count < 2 or t.col_count < 2:
            continue
        box=t.bbox
        ids=[i for i,ln in enumerate(lines)
             if box[0]-1 <= (ln['bbox'][0]+ln['bbox'][2])/2 <= box[2]+1
             and box[1]-1 <= (ln['bbox'][1]+ln['bbox'][3])/2 <= box[3]+1]
        if not ids or occupied.intersection(ids):
            continue
        cells=t.extract()
        exact=chars(''.join(c or '' for row in cells for c in row))==chars(''.join(lines[i]['text'] for i in ids))
        simple=exact and t.col_count<=5 and all(c is not None for row in cells for c in row)
        table=dict(kind='table',indices=ids,bbox=list(box),cells=cells,simple=simple,exact=exact,
                   text='\n'.join(lines[i]['text'] for i in ids))
        regions.append(table); tables.append(table);occupied.update(ids)
    # Unmodified native text is retained independently for reproducibility.
    native=page.get_text()
    return dict(lines=lines,regions=regions,native=native,
                native_sha256=digest(native.encode()),
                chars=len(native),replacement_characters=native.count('\ufffd'),
                control_characters=sorted({ord(c) for c in native if ord(c)<32 and c not in '\n\r\t'}))

def outline(doc, config, pages):
    book,_,year,offset,toc_pages=config
    nodes=[]; chapter=None; section=None; group=None; known=set()
    for p in toc_pages:
        for line in doc[p].get_text().splitlines():
            cm=re.search(r'제\s*(\d+)\s*장\s*(.+)',line)
            if cm and '·' not in line:
                num=int(cm[1])
                if num not in known:
                    chapter=dict(title=f'제{num}장 {cm[2].strip()}',kind='chapter',num=num,
                                 chapter=num,section=0,group=None)
                    nodes.append(chapter);known.add(num)
                    section=None;group=None
                else:
                    chapter=next(n for n in nodes if n['kind']=='chapter' and n['num']==num)
                continue
            m=re.match(r'^\s*(.*?)\s*·{2,}\s*(\d+)\s*$',line)
            if not m or not chapter:
                continue
            title=m[1].strip();printed=int(m[2]);pidx=printed+offset-1
            sm=re.match(r'제\s*(\d+)\s*절\s*(.*)',title)
            if sm:
                section=int(sm[1]);group=None;kind='section';num=section
                title=f'제{section}절 {sm[2]}'
            else:
                im=re.match(r'(\d+(?:\.\d+)?)\.?(?:\s+)(.+)',title)
                if not im: raise ValueError(f'Unparsed TOC: {title}')
                num=im[1];kind='item'
                if book=='SW-Diagnosis-2021' and chapter['num']==3 and section==3 and '.' not in num:
                    group=im[2];kind='category'
            nodes.append(dict(title=title,kind=kind,num=num,chapter=chapter['num'],
                              section=section,group=group,printed=printed,page=pidx))
    for n in nodes:
        if n['kind']=='chapter':
            first=next(x for x in nodes if x['chapter']==n['chapter'] and 'page' in x)
            # Chapter divider pages are included as separate structural units.
            n['page']=first['page']-(2 if book=='Python-2023' and n['chapter']==3 else 1)
            n['printed']=n['page']+1-offset
    # The 91-page appendix has meaningful original subitems absent from the TOC.
    if book=='SW-Diagnosis-2021':
        for pi in range(515,606):
            for ln in pages[pi]['lines']:
                m=re.match(r'^([1-4])-([1-9]\d?)\.\s*(.+)',ln['text'])
                if m and ln['size']>=10 and len(m[3])>3:
                    nodes.append(dict(title=ln['text'].strip(),kind='appendix-item',num=f'{m[1]}-{m[2]}',
                                      chapter=5,section=3,group=None,printed=pi+1,page=pi))
    # Locate starts on the actual page, rather than trusting TOC numbers alone.
    missing=[]
    for n in nodes:
        n['toc_printed']=n.get('printed')
        target=norm(n['title'])
        candidates=[]
        for i,ln in enumerate(pages[n['page']]['lines']):
            t=norm(ln['text'])
            if t==target or (n['kind']=='chapter' and target in t):
                candidates.append((ln['bbox'][1],i))
        if not candidates:
            # Section title can be split across two native lines.
            for i,ln in enumerate(pages[n['page']]['lines']):
                following=pages[n['page']]['lines'][i:i+3]
                if target in norm(''.join(x['text'] for x in following)):
                    candidates.append((ln['bbox'][1],i))
        if not candidates and n['kind']!='chapter':
            # The supplied diagnosis PDF has incorrect TOC start numbers for
            # several topics. Resolve them from nearby actual heading text.
            for pi in sorted(range(max(0,n['page']-5),min(len(pages),n['page']+6)),key=lambda p:abs(p-n['page'])):
                found=[]
                for i,ln in enumerate(pages[pi]['lines']):
                    combined=norm(''.join(x['text'] for x in pages[pi]['lines'][i:i+3]))
                    if norm(ln['text'])==target or (target in combined and ln['size']>=10):
                        found.append((ln['bbox'][1],i))
                if found:
                    n['page']=pi;n['printed']=pi+1-offset;candidates=found;break
        n['y']=min(candidates)[0] if candidates else 0
        n['matched']=bool(candidates)
        if not candidates and n['kind']!='chapter':missing.append(n['title'])
    nodes.sort(key=lambda n:(n['page'],n['y'], {'chapter':0,'section':1,'category':2,'item':3,'appendix-item':3}[n['kind']]))
    front=dict(title='표지·목차·앞부분',kind='front',chapter=0,section=0,group=None,page=0,y=-1,printed=None,matched=True)
    nodes.insert(0,front)
    # Colophon/back cover have no printed page number.
    end_page=174 if book=='Python-2023' else 610
    nodes.append(dict(title='발행정보·뒷표지',kind='back',chapter=99,section=0,group=None,page=end_page,y=0,printed=None,matched=True))
    chapter_names={n['chapter']:slug(n['title']) for n in nodes if n['kind']=='chapter'}
    section_names={(n['chapter'],n['section']):slug(n['title']) for n in nodes if n['kind']=='section'}
    for idx,n in enumerate(nodes):
        parts=[book]
        if n['chapter'] in chapter_names:parts.append(chapter_names[n['chapter']])
        if n['kind'] not in ['chapter','front','back']:
            parts.append(section_names[(n['chapter'],n['section'])])
        if n['group']:parts.append(slug(n['group']))
        n['path']='/'.join(parts+[f'{idx:03d}-{slug(n["title"])}.md'])
        n['id']=idx;n['pages']=[];n['segments']=[]
        n['weakness']=(n['kind']=='item' and ((book=='Python-2023' and n['chapter']==2) or (book=='SW-Diagnosis-2021' and n['chapter']==4)))
    return nodes,missing

def fenced(text,lang):
    fence='`'*max(3,max((len(x) for x in re.findall(r'`+',text)),default=0)+1)
    return f'{fence}{lang}\n{text}\n{fence}'

def format_segment(data, ids, book):
    lines=data['lines'];selected=set(ids); consumed=set();elements=[]
    for r in data['regions']:
        if not set(r['indices'])<=selected:continue
        consumed.update(r['indices'])
        if r['kind']=='code':
            text=fenced(r['text'],r['language'])
        elif r['simple']:
            rows=[[ (c or '').replace('|','\\|').replace('\n','<br>') for c in row] for row in r['cells']]
            has_header=any(c in ['번호','구분','보안약점','진단방법','항목','유형','언어','설명'] for c in rows[0])
            header=rows[0] if has_header else ['']*len(rows[0])
            rest=rows[1:] if has_header else rows
            text='\n'.join(['| '+' | '.join(header)+' |','| '+' | '.join(['---']*len(rows[0]))+' |']+['| '+' | '.join(row)+' |' for row in rest])
        else:
            text=fenced(r['text'],'text')
        elements.append((min(r['indices']),text,r['kind']))
    # Preserve native block order for prose and columns; numbered gutters were
    # already regrouped above using their coordinates.
    buf=[];last_block=None;start=None;previous=None
    def flush():
        nonlocal buf,start
        if buf:elements.append((start,'\n'.join(buf),'prose'))
        buf=[];start=None
    for i in ids:
        if i in consumed:flush();last_block=None;continue
        ln=lines[i];s=ln['text']
        if previous is not None:
            gap=ln['bbox'][1]-previous['bbox'][3]
            new_indent=ln['bbox'][0]-previous['bbox'][0]
            if (gap>max(ln['size'],previous['size'])*1.4 or gap < -2
                or abs(new_indent)>50 or (new_indent>6 and gap>2)):
                flush()
        if re.match(r'^(?:[가-하]\.\s|[가-하]\)\s|[1-9]\d?\.\s|제\d+[장절]\s)',s) and len(s)<100:
            flush();elements.append((i,'#### '+s,'heading'))
        elif s.startswith(('안전하지 않은 코드','안전한 코드','취약한 코드')):
            flush();elements.append((i,'#### '+s,'heading'))
        else:
            if start is None:start=i
            # Prevent HTML/XML samples from disappearing in Markdown rendering.
            s=s.replace('&','&amp;').replace('<','&lt;').replace('>','&gt;')
            buf.append(s)
        last_block=ln['block']
        previous=ln
    flush()
    elements.sort()
    return '\n\n'.join(x[1] for x in elements)

def build_book(config, sample=False):
    book,glob,year,offset,_=config
    source=next((ROOT/'보안_가이드라인').glob(glob));doc=pdf.open(source)
    source_hash=digest(source.read_bytes())
    cache=DATA/book/'extracted'
    images=BASE/'assets'/book/'pages'
    image_stamp=images/'source-sha256.txt'
    image_source_changed=image_stamp.exists() and image_stamp.read_text(encoding='utf-8').strip()!=source_hash
    pages=[]
    for pi,page in enumerate(doc):
        cp=cache/f'p{pi+1:04d}.json';image=images/f'p{pi+1:04d}.png'
        if cp.exists():data=json.loads(cp.read_text(encoding='utf-8'))
        else:data=None
        if not data or data.get('source_sha256')!=source_hash or data.get('version')!=VERSION:
            data=extract_page(page,book);data.update(source_sha256=source_hash,version=VERSION)
            data['code_version']=CODE_VERSION
            write(cp,json.dumps(data,ensure_ascii=False,indent=1))
        elif data.get('code_version')!=CODE_VERSION:
            codes=code_regions(data['lines'],book)
            used={i for r in codes for i in r['indices']}
            tables=[r for r in data['regions'] if r['kind']=='table' and not used.intersection(r['indices'])]
            data['regions']=codes+tables;data['code_version']=CODE_VERSION
            write(cp,json.dumps(data,ensure_ascii=False,indent=1))
        pages.append(data)
        write(cache/f'p{pi+1:04d}.txt',data['native'])
        if not sample and (image_source_changed or not image.exists()):
            images.mkdir(parents=True,exist_ok=True)
            page.get_pixmap(matrix=pdf.Matrix(2,2),alpha=False).save(image)
        if (pi+1)%100==0:print(f'{book}: {pi+1}/{len(doc)} extracted',flush=True)
    nodes,missing=outline(doc,config,pages)
    if not sample:write(image_stamp,source_hash+'\n')
    write(DATA/book/'outline.json',json.dumps(nodes,ensure_ascii=False,indent=2))
    if sample:
        print(json.dumps(dict(book=book,pages=len(doc),nodes=len(nodes),weaknesses=sum(n['weakness'] for n in nodes),missing=missing),ensure_ascii=False));return
    starts=[(n['page'],n['y']) for n in nodes]
    ledger=[]
    for pi,data in enumerate(pages):
        allocations=collections.defaultdict(list)
        for li,ln in enumerate(data['lines']):
            # Header/footer stay with the earliest unit on their page; this avoids
            # assigning a next-topic header to a previous weakness.
            idx=bisect.bisect_right(starts,(pi,ln['bbox'][1]+0.1))-1
            if ln['bbox'][1]<65:
                candidates=[j for j,n in enumerate(nodes) if n['page']==pi]
                if candidates:idx=candidates[0]
            allocations[max(idx,0)].append(li)
        if not allocations:
            allocations[max(bisect.bisect_right(starts,(pi,0))-1,0)]=[]
        for ni,ids in allocations.items():
            nodes[ni]['pages'].append(pi+1)
            nodes[ni]['segments'].append(dict(page=pi+1,line_ids=ids))
            ledger.append(dict(page=pi+1,path=nodes[ni]['path'],line_ids=ids,
                               chars=sum(len(data['lines'][i]['text']) for i in ids)))
    for n in nodes:
        path=BASE/n['path']
        ps=n['pages'] or [n['page']+1]
        meta=dict(title=n['title'],source=source.name,
                  publishers=['과학기술정보통신부','한국인터넷진흥원'] if year==2023 else ['행정안전부','한국인터넷진흥원'],
                  source_sha256=source_hash,edition=year,original_chapter=chapter_title(nodes,n['chapter']),
                  original_section=section_title(nodes,n),category=n['group'] or section_title(nodes,n),
                  pdf_pages=f'{min(ps)}-{max(ps)}',pdf_page_list=ps,
                  printed_pages=f'{min(ps)-offset}-{max(ps)-offset}' if n['kind'] not in ['front','back'] else None,
                  toc_printed_start=n.get('toc_printed'),actual_printed_start=n.get('printed'),
                  tags=['security','official-source','python' if year==2023 else 'diagnosis'],
                  transcription='자동 추출; 페이지 이미지와 함께 참조',unit_kind=n['kind'])
        manual=json.loads((LEGACY/'manual-transcriptions.json').read_text(encoding='utf-8')).get(book,{})
        meta['manual_image_transcription_pages']=[p for p in ps if str(p) in manual]
        body=['---',yaml.safe_dump(meta,allow_unicode=True,sort_keys=False).rstrip(),'---','',f'# {n["title"]}','',
              '> 변환 안내(원문 외): 아래 본문은 PDF 텍스트를 추출한 전사입니다. 코드 줄번호·특수 공백·원문 오류를 유지했습니다. 실행용 코드가 아닙니다. 표·그림·들여쓰기는 연결된 페이지 이미지와 대조하세요. 페이지 경계의 줄바꿈을 보존하며, 동일 페이지가 여러 항목에 나뉘면 각 항목의 본문은 해당 구간만 포함합니다.','']
        for seg in n['segments']:
            pi=seg['page']-1;img=images/f'p{pi+1:04d}.png'
            body += [f'### PDF {pi+1}페이지'+(f' / 인쇄 {pi+1-offset}페이지' if pi+1>offset and n['kind'] not in ['front','back'] else ''),'',
                     f'<!-- source-page:{book}:{pi+1}; source-lines:{",".join(map(str,seg["line_ids"]))} -->','',
                     format_segment(pages[pi],seg['line_ids'],book),'',
                     '<details><summary>원본 페이지 이미지 (변환 외 보존 자료)</summary>','',
                     '!'+link(path,img,f'{source.name} PDF {pi+1}페이지'),'', '</details>','']
            if str(pi+1) in manual:
                body += ['#### 이미지 내 원문 전사 (수동 대조)','',
                         '> 변환 안내(원문 외): 이 페이지는 텍스트 레이어가 없어 원본 렌더를 직접 읽어 전사했습니다. 자동 추출 본문과 별도로 표시합니다.','',
                         fenced(manual[str(pi+1)]['text'],'text'),'']
        body+=['---','','## 탐색 링크 (원문 외)','',link(path,BASE/'INDEX.md','통합 인덱스'),'','']
        write(path,'\n'.join(body))
    manifest=dict(book=book,source=str(source.relative_to(ROOT)),source_sha256=source_hash,page_count=len(doc),
                  offset=offset,nodes=nodes,ledger=ledger,missing_headings=missing)
    write(DATA/book/'manifest.json',json.dumps(manifest,ensure_ascii=False,indent=2))
    return manifest,pages

def chapter_title(nodes,num):
    return next((n['title'] for n in nodes if n['kind']=='chapter' and n['chapter']==num),'앞부분·발행정보')

def section_title(nodes,n):
    return next((x['title'] for x in nodes if x['kind']=='section' and x['chapter']==n['chapter'] and x['section']==n['section']),'')

def canonical(title):
    s=re.sub(r'^\d+\.\s*','',title)
    s=re.sub(r'\([^)]*\)','',s)
    s=s.replace('패스워드','비밀번호').replace('해쉬','해시').replace('신뢰되지 않은','신뢰되지 않는').replace('메소드로부터','메소드부터')
    return norm(s)

KEYWORDS={
 'SQL 삽입':'SQLi, query, ORM, SQLAlchemy, DB-API, PostgreSQL, 바인딩',
 '크로스사이트 스크립트':'XSS, HTML, 출력, 공고, 이스케이프',
 '크로스사이트 요청 위조':'CSRF, 쿠키, 브라우저, 요청',
 '서버사이드 요청 위조':'SSRF, URL, 외부 API, 공고 수집, allowlist',
 '부적절한 인가':'인가, authorization, 소유권, 사용자, 기관, 관리자, RBAC, FastAPI',
 '적절한 인증 없는 중요 기능 허용':'인증, authentication, 세션, FastAPI',
 '암호화되지 않은 중요정보':'개인정보, 시니어 프로필, 대화, 초안, 전송, 저장, TLS',
 '하드코드된 중요정보':'API key, secrets, 환경변수, 비밀키',
 '취약한 암호화 알고리즘 사용':'암호화, AES, 지원서 초안, 암호 저장소',
 '솔트 없이 일방향 해시 함수 사용':'비밀번호, password, salt, Argon2id',
 '반복된 인증시도 제한 기능 부재':'Redis, rate limit, 로그인, 남용, 요청 제한',
 '오류 메시지 정보노출':'로그, 예외, 개인정보, 대화, traceback',
 '부적절한 예외 처리':'exception, FastAPI, 에러, 예외',
 '신뢰할 수 없는 데이터의 역직렬화':'pickle, deserialize, 비신뢰 입력, 객체',
 '경로 조작 및 자원 삽입':'path traversal, 파일, 경로, 시스템 자원',
 '잘못된 세션에 의한 데이터 정보 노출':'session, 세션, 사용자 데이터, 기관 계정',
}

def indexes(results):
    path=BASE/'INDEX.md'
    out=['# 공식 개발보안 지식 베이스','',
         '두 공식 PDF의 원문을 장·절과 보안약점 단위로 탐색합니다. 이 인덱스의 키워드·대응표·프로젝트 연결은 탐색용 메타데이터이며 공식 원문이 아닙니다.','',
         '진입 순서: 통합 인덱스 → 2023 Python 가이드 또는 2021 진단가이드 → 장·절·개별 원문. 아래 목차에서 원문으로 바로 이동할 수 있습니다.','',
         '## 원문별 빠른 진입','',
         '- [Python 시큐어코딩 가이드 (2023)](#python-2023)',
         '- [소프트웨어 보안약점 진단가이드 (2021)](#sw-diagnosis-2021)',
         '', '원본의 출처: Python 가이드는 과학기술정보통신부·한국인터넷진흥원, 진단가이드는 행정안전부·한국인터넷진흥원. PDF 원본은 프로젝트의 보안_가이드라인 폴더에 보존합니다. Python은 PDF 페이지 = 인쇄 페이지 + 6이며 진단가이드 본문은 두 번호가 일치합니다. 표지·발행정보·뒷표지는 별도로 식별합니다.','',
         '## 보안약점 통합 대응표','',
         '두 문서의 명칭 차이(띄어쓰기, XSS/CSRF 병기, 패스워드/비밀번호, 해쉬/해시 등)를 탐색용으로 연결했습니다. 원문 제목과 본문은 각 문서에서 유지합니다. `—`는 해당 가이드의 독립 항목이 없음을 뜻합니다.','',
         '| 보안약점 / 키워드 | Python 구현 가이드 | 구현단계 진단가이드 |','| --- | --- | --- |']
    grouped={}
    for m,_ in results:
        for n in m['nodes']:
            if n['weakness']:grouped.setdefault(canonical(n['title']),{})[m['book']]=n
    for k,pair in grouped.items():
        n=pair.get('Python-2023') or pair['SW-Diagnosis-2021']
        title=re.sub(r'^\d+\.\s*','',n['title'])
        kw=next((v for t,v in KEYWORDS.items() if canonical(t)==k),'')
        columns=[link(path,BASE/pair[b]['path'],'원문') if b in pair else '—' for b in ['Python-2023','SW-Diagnosis-2021']]
        out.append(f'| {title}'+(f'<br>{kw}' if kw else '')+' | '+' | '.join(columns)+' |')
    out += ['', '## 원문별 전체 목차', '']
    for m,_ in results:
        book=m['book'];label=('Python 시큐어코딩 가이드 (2023)' if book=='Python-2023' else '소프트웨어 보안약점 진단가이드 (2021)')
        anchor='python-2023' if book=='Python-2023' else 'sw-diagnosis-2021'
        weakness_count=sum(1 for n in m['nodes'] if n['weakness'])
        out += [f'<a id="{anchor}"></a>', f'### {label}',
                f'원문 {m["page_count"]}페이지 · 개별 Markdown {len(m["nodes"])}개 · 구현약점 {weakness_count}개','',
                '| 장·절·항목 | PDF 페이지 | 종류 |','| --- | --- | --- |']
        for n in m['nodes']:
            ps=n['pages'] or [n['page']+1]
            out.append(f'| {link(path,BASE/n["path"],n["title"])} | {min(ps)}-{max(ps)} | {n["kind"]} |')
        out.append('')
    out+=['','## 분석·설계 및 부록 탐색','',
          '분석·설계 기준과 설계 산출물 적용 예도 위 진단가이드 전체 목차에서 확인할 수 있습니다.','']
    for m,_ in results:
        if m['book']=='SW-Diagnosis-2021':
            for n in m['nodes']:
                if (n['chapter']==3 and n['kind']=='item' and '.' in str(n['num'])) or n['kind']=='appendix-item':
                    out.append('- '+link(path,BASE/n['path'],f'{chapter_title(m["nodes"],n["chapter"])} / {n["title"]}'))
    def refs(names):
        parts=[]
        for title in names:
            pair=grouped.get(canonical(title),{})
            for b,n in pair.items():parts.append(link(path,BASE/n['path'],title+(' (Python)' if b=='Python-2023' else ' (진단)')))
        return ' · '.join(parts)
    out+=['','## 다시잇다 기능별 탐색 (추가 탐색 정보)','',
          link(path,ROOT/'용삼고_개발기획서.pdf','개발기획서')+' PDF 8-12페이지의 스택·보안 계획을 기준으로 연결했습니다. 애플리케이션 코드는 변경하지 않습니다.','',
          '| 기능·영역 | 관련 공식 원문 |','| --- | --- |']
    mappings=[('FastAPI 인증·세션, 사용자/기관/관리자 권한, 프로필 소유권',['적절한 인증 없는 중요 기능 허용','부적절한 인가','잘못된 세션에 의한 데이터 정보 노출']),
              ('SQLAlchemy·PostgreSQL, 사용자 데이터 접근',['SQL 삽입','부적절한 인가']),
              ('외부 공고·비신뢰 입력, 화면 출력',['크로스사이트 스크립트','크로스사이트 요청 위조','신뢰할 수 없는 데이터의 역직렬화']),
              ('외부 URL·API·배치 수집',['서버사이드 요청 위조','신뢰되지 않은 URL주소로 자동접속 연결','부적절한 인증서 유효성 검증']),
              ('시니어 프로필·대화, LLM API 최소 정보 전달',['암호화되지 않은 중요정보','오류 메시지 정보노출','하드코드된 중요정보']),
              ('지원서 초안 AES-256-GCM, 비밀키·비밀번호',['취약한 암호화 알고리즘 사용','충분하지 않은 키 길이 사용','솔트 없이 일방향 해시 함수 사용','하드코드된 중요정보']),
              ('Redis 요청 제한·LLM 호출 상한·로그인 제한',['반복된 인증시도 제한 기능 부재','종료되지 않는 반복문 또는 재귀 함수']),
              ('로그·오류·예외 메시지',['오류 메시지 정보노출','오류상황 대응 부재','부적절한 예외 처리']),
              ('파일·시스템 자원·인프라 권한',['경로 조작 및 자원 삽입','중요한 자원에 대한 잘못된 권한 설정','운영체제 명령어 삽입']),
              ('삭제·보관·동의 철회',['암호화되지 않은 중요정보','부적절한 인가'])]
    for label,names in mappings:out.append(f'| {label} | {refs(names)} |')
    out+=['','LLM 프롬프트 인젝션·호출 비용 상한、사용자 동의·보관기간·삭제 정책의 구체적 기준은 두 가이드의 독립 항목에서 직접 다루지 않습니다. 위 연결은 관련 원칙을 찾기 위한 탐색 보조이며 현대 기술의 검증이나 법률·제품 정책 판단을 대신하지 않습니다.','',
          '## 변환과 검증','',link(path,LEGACY/'VALIDATION.md','검증 결과·한계·원본 대조 기록'),' · '+link(path,ROOT/'tools/security_kb/README.md','재실행·검증 방법'),'']
    write(path,'\n'.join(out))
    # Consolidate the two generated per-source indices into the single entry point.
    for book in ['Python-2023','SW-Diagnosis-2021']:
        obsolete=BASE/book/'00-INDEX.md'
        if obsolete.exists():
            if not obsolete.resolve().is_relative_to(BASE.resolve()):
                raise ValueError(f'Unexpected index path: {obsolete}')
            obsolete.unlink()

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--sample',action='store_true');args=parser.parse_args()
    results=[]
    for config in CONFIG:
        result=build_book(config,args.sample)
        if result:results.append(result)
    if not args.sample:indexes(results)

if __name__=='__main__':main()
