"""Run validation, publish its readable record, and recheck final report links."""
import json,re
from urllib.parse import unquote
from build import BASE,ROOT,LEGACY,DATA,CONFIG,link,write
from validate import run

def report(result):
    path=LEGACY/'VALIDATION.md'
    changed_originals=next((error['files'] for error in result['errors'] if error['type']=='original_files_changed'),[])
    matched_originals=result['original_files_checked']-len(changed_originals)
    out=['# 변환 검증 기록','', '작업일: 2026-10-12 (Asia/Seoul). 대상은 제공된 로컬 PDF이며 원본은 변경하지 않았습니다.','',
         '## 결과','', '| 출처 | 원본/처리 페이지 | 원문 단위 Markdown | 독립 구현약점 | 페이지 PNG | 코드 블록 | Markdown 표 | 복잡한 표 영역 |',
         '| --- | --- | --- | --- | --- | --- | --- | --- |']
    for s in result['stats']:
        out.append(f'| {s["book"]} | {s["pages"]}/{s["processed"]} | {s["notes"]} | {s["weaknesses"]} | {s["page_images"]} | {s["code_blocks"]} | {s["simple_tables"]} | {s["complex_tables"]} |')
    out+=['','원문 단위 문서 194개(2023년 69개, 2021년 125개)를 하나의 `INDEX.md`에서 바로 연결합니다. 목차용 중간 Markdown은 두지 않아 Vault의 결과 Markdown은 통합 인덱스와 검증 기록을 포함해 총 196개입니다. 진단가이드에는 설계 기준 20개와 부록 설계 산출물 예시 20개가 별도 단위로 포함됩니다. PNG는 삽입 이미지를 개별 추출한 수가 아니라 모든 PDF 페이지를 144dpi로 렌더한 수입니다. 텍스트 레이어가 없는 도식·그림·표지의 문자도 이미지 안에 보존합니다.','',
          f'자동 검증 오류: **{len(result["errors"])}개** / 검증 경고: **{len(result["warnings"])}개**. 기존 파일 {result["original_files_checked"]}개 중 {matched_originals}개의 SHA256이 작업 전 기준과 일치합니다. 변경이 확인된 두 파일은 `.obsidian/graph.json`과 `.obsidian/workspace.json`입니다. 변환 스크립트는 이 설정 파일을 쓰지 않습니다. 현재 내용을 유지했으며 변경 원인은 확인되지 않았습니다. PDF·기획서·교육자료·Vault 환영 문서는 작업 전 해시와 일치합니다. 애플리케이션 코드는 변경하지 않았습니다.','',
          'Vault 보안 자료의 유일한 인덱스는 `INDEX.md`입니다. 개별 Markdown 문서도 모두 이 인덱스로 돌아가는 링크를 제공합니다.','',
          '## 자동 검증 범위','',
          '- 실제 PDF를 다시 열어 페이지별 원시 추출 텍스트와 캐시가 일치하는지 확인.',
          '- 전체 788페이지의 처리·이미지 연결과 원문 행의 단일 본문 배치 확인. 같은 페이지의 원본 이미지는 여러 문서에 연결될 수 있지만 본문 행은 중복 배치하지 않음.',
          '- 실제 Markdown에서 변환 문법을 제거한 비공백 문자 다중집합과 원문 행을 비교하여 문자 누락·증가 검사. 코드/표 영역 중복 검사.',
          '- 원문 목차의 장·절·보안약점과 실제 제목의 대응, YAML Frontmatter, 문서 누락·불필요한 잔여 파일 검사.',
          '- 모든 PNG 디코딩 및 원본 페이지의 2배 픽셀 크기 확인. 상대경로·이미지·PDF 링크의 존재 확인.',
          '- SQL 삽입·부적절한 인가·SSRF를 INDEX에서 각각 양쪽 원문으로 찾아 정의와 구현/진단 관련 내용을 읽을 수 있는지 확인.',
          '',link(path,LEGACY/'validation.json','페이지별 검사 결과·주의 페이지 전체 목록 (JSON)'),'',
          '## 집중 대조와 수정','',
          '| 대상 | 대조 내용 및 결과 |','| --- | --- |',
          '| Python PDF 14 | SQL 삽입 개요와 공격 도식의 이미지 보존 확인. 도식의 문자는 원본 이미지로 참조. |',
          '| Python PDF 16-17 | 안전하지 않은/안전한 SQL 예제의 줄번호·빈 줄·주석·문자열·NBSP 및 타이포그래픽 인용부호를 원문과 대조. 원문의 이상을 자동 수정하지 않음. |',
          '| 진단 PDF 12 | 단순한 2열 표의 원문 셀 순서와 내용을 대조. 원래 열 제목이 없는 표에는 빈 Markdown 헤더를 사용. |',
          '| 진단 PDF 182 | MyBatis 코드의 XML·쿼리·문자열을 대표 추출 단계에서 검토. 페이지 장식을 표로 오인하는 기본 탐지를 `lines_strict`로 변경. |',
          '| 진단 PDF 195 | JSP/Java 안전하지 않은/안전한 코드의 번호와 별도 좌표로 배치된 들여쓰기 대조. 문자 수정 없이 좌표 간격을 공백으로 표현. |',
          '| 진단 PDF 382 | 쿠키 약점의 실제 시작 페이지를 렌더로 확인. 한 줄 코드 및 번호 없는 주석을 코드 블록에 포함하도록 보정. |',
          '| 진단 PDF 516 | 10열 설계 산출물 표의 제목·셀·설명 확인. 복잡한 표는 원문 추출 텍스트와 이미지로 보존. |',
          '| Python PDF 175 | 텍스트 레이어가 없는 발행정보를 원본 이미지에서 직접 전사. 자동 추출 본문과 구분하여 표시. 과학기술정보통신부·한국인터넷진흥원, 2023년 12월 발행 확인. |',
          '', '다중 페이지 코드 예제는 각 페이지의 원문 구간을 별도로 표시하며 같은 보안약점 파일 안에서 연속해서 읽을 수 있습니다. 원문 오류, 문법 이상, 예제의 오래된 API는 고치거나 실행하지 않았습니다.','',
          '## 목차 페이지 불일치','',
          '진단가이드의 아래 목차 번호는 실제 본문 시작보다 한 페이지 뒤입니다. 목차 원문은 그대로 전사했고, 분할 위치와 메타데이터는 실제 제목을 기준으로 기록했습니다.','',
          '| 항목 | 원문 목차 인쇄 페이지 | 실제 PDF/인쇄 시작 |','| --- | --- | --- |']
    for book,_,_,_,_ in CONFIG:
        m=json.loads((DATA/book/'manifest.json').read_text(encoding='utf-8'))
        for n in m['nodes']:
            if n.get('toc_printed')!=n.get('printed'):
                out.append(f'| {link(path,BASE/n["path"],n["title"])} | {n["toc_printed"]} | {n["printed"]} |')
    out+=['','## 텍스트가 적은 페이지','',
          '80자 미만인 모든 페이지를 렌더 축소판으로 확인했습니다. 표지·뒷표지, 장 구분용 삽화/제목, 백지 또는 발행정보이며 본문 추출 실패로 판단되는 페이지는 발견하지 않았습니다. Python 175페이지는 이미지 기반 발행정보이므로 별도로 수동 전사했습니다.','']
    for s in result['stats']:
        out.append('- '+s['book']+': '+', '.join(str(p['page']) for p in s['short_pages'])+' (PDF 페이지).')
    out+=['','## 남아 있는 변환·검증 한계','',
          '- 원문 텍스트 레이어의 정확성이 원본 시각 정보와 완전히 같음을 증명하지 않습니다. 모든 코드·셀·각주를 사람이 전수 판독하지 않았습니다. 자동 검증 통과는 전체 무손실 보장이 아닙니다.',
          '- 비공백 문자 다중집합 비교는 누락·증가 탐지에 유용하지만 문자 순서, 들여쓰기, 문장 의미, 표의 행·열 관계는 증명하지 않습니다. 추출 좌표와 페이지 이미지를 함께 제공합니다.',
          '- 코드의 원래 특수 공백(NBSP 등)과 비정상 인용부호를 유지했습니다. 별도 좌표로 나뉜 코드 조각의 시각적 간격은 공백으로 표현했으므로 픽셀 단위 서식은 이미지를 기준으로 확인해야 합니다.',
          '- 선이 없는 표·이미지 내부 문자·벡터 도식은 모두 검색 가능한 표/본문 텍스트로 전환하지 않았습니다. 원본 페이지 이미지에 보존했으며, 복잡한 표의 추출 텍스트는 셀 배치를 대신하지 않습니다.',
          '- 반복 머리말·꼬리말, 원문 줄바꿈과 페이지 경계를 보수적으로 유지했습니다. 페이지 사이에서 문장이 끊기면 다음 페이지 구간을 이어서 읽습니다.',
          '- 원시 추출에서 나타난 U+0001 제어문자는 원문을 추측해 수정하지 않고 보존했습니다. 해당 페이지와 특수 공백/인용부호가 있는 코드 페이지는 기계 기록의 `control_character_pages`, `special_code_pages`에서 찾을 수 있습니다.',
          '- 표지·장 제목처럼 이미지 기반인 일부 텍스트는 페이지 이미지로 보존됩니다. OCR을 전체 문서에 적용하지 않았습니다. 수동 이미지 전사는 Python 175페이지에 한정했습니다.',
          '- 문서 구조·검색 시나리오는 파일과 링크로 검증했습니다. 설치된 Obsidian 앱의 읽기 화면을 직접 조작해 전수 확인하지는 않았습니다.',
          '', '알려진 미해결 자동 검증 오류는 위 오류 수와 JSON에 기록합니다. 별도의 현대 기술 판단이나 추가 설계는 원문에 섞지 않았습니다.','',
          link(path,BASE/'INDEX.md','통합 인덱스로 돌아가기')+' · '+link(path,ROOT/'tools/security_kb/README.md','재실행 방법'),'']
    write(path,'\n'.join(out))

if __name__=='__main__':
    result=run();report(result)
    link_count=0
    for p in BASE.rglob('*.md'):
        for href in re.findall(r'\]\(([^)]+)\)',p.read_text(encoding='utf-8')):
            if '://' in href or href.startswith('#'):continue
            assert (p.parent/unquote(href.split('#')[0])).resolve().exists(),(p,href)
            link_count+=1
    result['links_checked']=link_count
    write(LEGACY/'validation.json',json.dumps(result,ensure_ascii=False,indent=2))
    print(f'Final report written; {link_count} local links valid.')
    raise SystemExit(bool(result['errors']))
