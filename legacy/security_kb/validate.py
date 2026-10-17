"""Validate actual Markdown against cached source lines and source PDF text."""
import collections, hashlib, html, json, re
from pathlib import Path
from urllib.parse import unquote
import pymupdf as pdf
import yaml
from build import ROOT, BASE, LEGACY, DATA, CONFIG, canonical, chars, digest, link, write

def recover_text(md):
    out=[];fence=None;rows=md.splitlines();i=0
    while i<len(rows):
        line=rows[i]
        m=re.match(r'^(`{3,})(\w*)$',line)
        if m:
            if fence is None:fence=m[1]
            elif line==fence:fence=None
            i+=1;continue
        if fence:
            out.append(line);i+=1;continue
        if line.startswith('| ') and i+1<len(rows) and re.match(r'^\| (?:--- \| ?)+$',rows[i+1]):
            while i<len(rows) and rows[i].startswith('| '):
                if not re.match(r'^\| (?:--- \| ?)+$',rows[i]):
                    cells=re.split(r'(?<!\\)\|',rows[i])[1:-1]
                    out.append(''.join(c.replace('\\|','|').replace('<br>','\n') for c in cells))
                i+=1
            continue
        out.append(html.unescape(re.sub(r'^#### ', '',line)))
        i+=1
    assert fence is None,'Unclosed source code fence'
    return '\n'.join(out)

def run():
    errors=[];warnings=[];stats=[];all_manifests=[]
    index_files=list(BASE.rglob('*INDEX*.md'))
    if len(index_files)!=1 or index_files[0]!=BASE/'INDEX.md':
        errors.append({'type':'single_index_entry_point','paths':[str(x.relative_to(BASE)) for x in index_files]})
    source_diff=[]
    baseline=json.loads((LEGACY/'original-files.json').read_text(encoding='utf-8'))
    for name,expected in baseline.items():
        path=ROOT/name
        if not path.exists() or digest(path.read_bytes())!=expected:source_diff.append(name)
    if source_diff:errors.append({'type':'original_files_changed','files':source_diff})
    for book,_,_,_,_ in CONFIG:
        m=json.loads((DATA/book/'manifest.json').read_text(encoding='utf-8'))
        all_manifests.append(m);doc=pdf.open(ROOT/m['source'])
        if digest((ROOT/m['source']).read_bytes())!=m['source_sha256']:errors.append({'book':book,'type':'pdf_hash'})
        page_data=[];short=[];controls=[];code_pages=[];table_pages=[];uncertain_code=[]
        total_codes=total_simple=total_complex=0
        for pi,page in enumerate(doc):
            data=json.loads((DATA/book/'extracted'/f'p{pi+1:04d}.json').read_text(encoding='utf-8'))
            page_data.append(data)
            source=page.get_text()
            if source!=data['native']:errors.append({'book':book,'page':pi+1,'type':'native_text_mismatch'})
            if chars(source)!=chars(''.join(l['text'] for l in data['lines'])):
                errors.append({'book':book,'page':pi+1,'type':'native_vs_spans_mismatch'})
            if len(source.strip())<80:short.append({'page':pi+1,'chars':len(source.strip())})
            if data['control_characters']:controls.append({'page':pi+1,'codes':data['control_characters']})
            if data['replacement_characters']:warnings.append({'book':book,'page':pi+1,'type':'replacement_glyph','count':data['replacement_characters']})
            codes=[r for r in data['regions'] if r['kind']=='code']
            tables=[r for r in data['regions'] if r['kind']=='table']
            memberships=collections.Counter(i for r in data['regions'] for i in r['indices'])
            if any(count>1 for count in memberships.values()):errors.append({'book':book,'page':pi+1,'type':'overlapping_regions'})
            for ln in data['lines']:
                if re.match(r'^(?:안전하지 않은|안전한|취약한) 코드(?:의 예| 예시)',ln['text']) and len(ln['text'])<=60:
                    if not any(r['label']==ln['text'] for r in codes):warnings.append({'book':book,'page':pi+1,'type':'unfenced_code_label','label':ln['text']})
            total_codes+=len(codes);total_simple+=sum(r['simple'] for r in tables);total_complex+=sum(not r['simple'] for r in tables)
            if codes:
                code_pages.append(pi+1)
                if any('\xa0' in r['text'] or re.search('[“”‘’]',r['text']) for r in codes):uncertain_code.append(pi+1)
            if tables:table_pages.append(pi+1)
            # Page image is checked for file integrity and original dimensions.
            image=BASE/'assets'/book/'pages'/f'p{pi+1:04d}.png'
            if not image.exists():errors.append({'book':book,'page':pi+1,'type':'missing_page_image'})
            else:
                pix=pdf.Pixmap(str(image))
                if abs(pix.width-page.rect.width*2)>2 or abs(pix.height-page.rect.height*2)>2:
                    errors.append({'book':book,'page':pi+1,'type':'image_dimensions'})
        line_owners=collections.defaultdict(list)
        pages_seen=set();segment_count=0;empty_units=[]
        for n in m['nodes']:
            path=BASE/n['path']
            if not path.exists():errors.append({'type':'missing_note','path':n['path']});continue
            text=path.read_text(encoding='utf-8')
            fm=yaml.safe_load(text.split('---',2)[1])
            if not isinstance(fm,dict) or fm['title']!=n['title'] or fm['pdf_page_list']!=(n['pages'] or [n['page']+1]):
                errors.append({'type':'frontmatter','path':n['path']})
            actual=list(re.finditer(r'<!-- source-page:([^:]+):(\d+); source-lines:([^>]*) -->\n\n(.*?)\n\n<details>',text,re.S))
            if len(actual)!=len(n['segments']):errors.append({'type':'segment_count','path':n['path']})
            for a,expected in zip(actual,n['segments']):
                p=int(a[2]);ids=[int(x) for x in a[3].split(',') if x]
                if a[1]!=book or p!=expected['page'] or ids!=expected['line_ids']:
                    errors.append({'type':'source_locator','path':n['path'],'page':p})
                recovered=recover_text(a[4])
                source=''.join(page_data[p-1]['lines'][i]['text'] for i in ids)
                if chars(recovered)!=chars(source):
                    diff=chars(source)-chars(recovered);extra=chars(recovered)-chars(source)
                    errors.append({'type':'markdown_content_difference','path':n['path'],'page':p,'missing':dict(diff),'extra':dict(extra)})
                for i in ids:line_owners[(p,i)].append(n['path'])
                pages_seen.add(p);segment_count+=1
            if not any(s['line_ids'] for s in n['segments']):empty_units.append(n['path'])
        for pi,d in enumerate(page_data):
            for li in range(len(d['lines'])):
                owners=line_owners[(pi+1,li)]
                if len(owners)!=1:errors.append({'type':'line_coverage','book':book,'page':pi+1,'line':li,'owners':owners})
        if pages_seen!=set(range(1,len(doc)+1)):errors.append({'type':'page_coverage','book':book,'missing':sorted(set(range(1,len(doc)+1))-pages_seen)})
        if m['missing_headings']:errors.append({'type':'missing_outline_headings','book':book,'headings':m['missing_headings']})
        expected_notes={str((BASE/n['path']).resolve()) for n in m['nodes']}
        unexpected=[str(p.relative_to(BASE)) for p in (BASE/book).rglob('*.md') if p.name!='00-INDEX.md' and str(p.resolve()) not in expected_notes]
        if unexpected:errors.append({'book':book,'type':'unexpected_notes','paths':unexpected})
        stats.append(dict(book=book,pages=len(doc),processed=len(pages_seen),notes=len(m['nodes']),
                          weaknesses=sum(n['weakness'] for n in m['nodes']),page_images=len(doc),code_blocks=total_codes,
                          simple_tables=total_simple,complex_tables=total_complex,short_pages=short,
                          control_character_pages=controls,code_pages=code_pages,table_pages=table_pages,
                          special_code_pages=uncertain_code,empty_units=empty_units,source_segments=segment_count))
    links_count=0
    for path in BASE.rglob('*.md'):
        text=path.read_text(encoding='utf-8')
        for href in re.findall(r'\]\(([^)]+)\)',text):
            if '://' in href or href.startswith('#'):continue
            target=(path.parent/unquote(href.split('#')[0])).resolve()
            if not target.exists():errors.append({'type':'broken_link','path':str(path.relative_to(BASE)),'href':href})
            links_count+=1
    # Scenario traversal: both source documents must be directly linked in INDEX.
    index=(BASE/'INDEX.md').read_text(encoding='utf-8');scenarios=[]
    for title in ['SQL 삽입','부적절한 인가','서버사이드 요청 위조']:
        found=[]
        for m in all_manifests:
            matches=[n for n in m['nodes'] if n['weakness'] and canonical(n['title'])==canonical(title)]
            for n in matches:
                target=BASE/n['path']
                indexed=link(BASE/'INDEX.md',target,'원문') in index
                content=target.read_text(encoding='utf-8')
                has_overview=bool(re.search(r'(개요|보안약점)',content))
                has_criteria=bool(re.search(r'(안전한|진단|대응방안)',content))
                ok=indexed and has_overview and has_criteria
                found.append({'book':m['book'],'path':n['path'],'passed':ok})
                if not ok:errors.append({'type':'scenario','title':title,'path':n['path']})
        if len(found)!=2:errors.append({'type':'scenario_missing_pair','title':title})
        scenarios.append({'title':title,'sources':found})
    result=dict(errors=errors,warnings=warnings,stats=stats,links_checked=links_count,original_files_checked=len(baseline),
                scenarios=scenarios,checks='페이지·원문문자·행의 단일 소유·목차 제목·Frontmatter·이미지 디코딩/크기·상대 링크·원본 SHA256·탐색 시나리오')
    write(LEGACY/'validation.json',json.dumps(result,ensure_ascii=False,indent=2))
    print(json.dumps(dict(errors=len(errors),warnings=len(warnings),links=links_count,stats=[{k:s[k] for k in ['book','pages','notes','weaknesses','code_blocks','simple_tables','complex_tables']} for s in stats],first_errors=errors[:8]),ensure_ascii=False))
    return result

if __name__=='__main__':
    result=run()
    raise SystemExit(bool(result['errors']))
