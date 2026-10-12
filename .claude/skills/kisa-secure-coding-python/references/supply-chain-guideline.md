# SW 공급망 보안 가이드라인 v1.0 (2024.05) — 원문 정리 + Python 저장소 점검 기준

| 항목 | 내용 |
|---|---|
| 문서 | 「SW 공급망 보안 가이드라인 1.0」 (부제: SW 공급망 보안 국제동향 및 SBOM 활용사례) |
| 발행 | 2024.5.13, 국가정보원·과학기술정보통신부·디지털플랫폼정부위원회 (발행처 KISA) |
| 성격 | 정책·관리체계 문서. 코드 단위 보안약점 목록이 아니라 **개발·빌드·배포·운영 전 과정의 공급망 관리 활동**과 **SBOM**을 다룬다 |
| 이용 조건 | CC BY-NC-ND 2.0 KR |
| 쪽 표기 | 이 파일의 `p.` 는 인쇄면 쪽 번호 (PDF 쪽 − 10) |
| 후속 문서 | 「SW 공급망 보안 강화 로드맵」(2026.6)이 이 가이드라인의 2.0 개정을 예고했다 → `supply-chain-roadmap.md` |

## 이 파일의 사용법

- **A부(원문 정리)**: 가이드라인 내용을 표 단위로 정리했다. 보고서 근거 인용용.
- **B부(점검 기준)**: 원문을 Python 저장소에서 확인할 수 있는 항목으로 바꿨다.
  - `SC-01`~`SC-30`: 가이드라인 표24 자가점검 체크리스트 30개 (번호 그대로)
  - `SCP-01`~`SCP-20`: 이 스킬이 정의한 Python 저장소 공급망 점검 항목 (원문 근거를 항목마다 적음)
- 증거 유형 표기
  - **[코드]** 저장소 파일만으로 판정 가능
  - **[CI]** CI/CD 설정 파일로 판정 가능
  - **[도구]** pip-audit·SBOM 도구 등을 실행해야 판정 가능 (도구가 없으면 `확인 필요(도구)`)
  - **[문서]** 저장소 안 문서(SECURITY.md 등)로 일부 확인 가능
  - **[조직]** 저장소 밖 증거(교육 기록, 계약서, 서버 설정)가 필요 → 정적 검사로는 판정하지 않고 `확인 필요(조직)`으로 보고
- 공모전·학생 프로젝트처럼 조직이 없는 경우 [조직] 항목은 `해당없음` 또는 README에 운영 방식만 적도록 권고한다.

---

# A부. 원문 정리

## A1. 추진 배경 (1장, p.1~19)

**환경변화 3가지 (1절)**

| 구분 | 내용 |
|---|---|
| 변화-1 초연결 사회 | 개발-공급(유통)-운영의 연결성으로 공급망 생태계 참여 계층 확장. DX 가속, 외부 SW 활용·ICT 상호 의존성 증가 |
| 변화-2 SW 부품 공급 분업화 | 최종 제품 무결성에 대한 '신뢰' 하락. CI/CD·공용 리포지토리·클라우드 호스팅 등 개발 파이프라인의 공격 표면 증가. SDLC 전체에서 위험관리 필요 |
| 변화-3 공개 SW 사용 확대 | 공개 SW는 관리 주체가 불명확하고 악성코드·취약점 전파가 쉬워 주요 공격 목표 |

- **SW 공급망 정의**: 최종 SW 제품을 생산하는 사람·장치·시스템의 집합. 개발자가 코드를 작성할 때부터 제품으로 생산되어 사용자 시스템에서 실행될 때까지 일어나는 모든 일.
- **타사(3rd Party) SW 구성요소**: 원래 공급사가 아닌 다른 개발사가 계약에 의해 배포·판매하도록 개발한 재사용 가능한 SW 부품.
- 사례(2절): UEFI 루트킷 LoJax(2018), 국산 위장 외산 CCTV 215대의 DNS가 악성 이력 IP로 설정된 채 납품(2020), 외산 계측장비 악성코드(2023).

**표1. 국내외 SW 공급망 침해사고 (p.6)**

| 공격 | 내용 |
|---|---|
| SolarWinds (2020) | SW 개발환경·배포 시스템 해킹, 18,000개 이상 기관 피해 |
| Codecov (2021) | 컨테이너 이미지 취약점으로 배포 환경 인증정보 유출, 약 2만 9천 고객사 영향 |
| Colonial Pipeline (2021) | 랜섬웨어로 송유관 공급 중단 |
| Log4Shell (2021) | Log4j 제로데이 + 공개 PoC로 대량 공격 |
| Kaseya (2022) | 원격관리 솔루션 서버 해킹, 업데이트로 위장한 랜섬웨어 배포, 17개국 1,500여 조직 |
| 3CX (2023) | 악성 X-트레이더 SW → 3CX 앱 연쇄 감염, 60만 고객·1,200만 조직 |
| 이니세이프 (2023) | 금융 보안인증 SW 취약점 악용, 국내 61개 기관 207대 PC |

- Log4j처럼 수천 프로젝트에 통합된 공개 SW는 취약 인스턴스 제거·업데이트에만 10년이 걸린다는 미국 사이버보안 검토 위원회 보고(2022), Log4j 사태 1년 후에도 다운로드의 25%가 취약 버전(Wired, 2022.12).
- OSSRA 2023: 분석 코드베이스의 96%가 공개 SW 포함, 84%가 취약점 1개 이상 포함, 고위험 취약점 구성요소 비율 약 50%.

## A2. SW 공급망 공격 7유형 (표2·표3, p.9~13)

공급망 공격은 공급망 구성요소 중 하나 이상의 약점이 손상되어 최종 제품이 변경되는 것이다. SW 개발·변환(Build)·배포·운영 시스템 전부가 대상이다.

| 유형 | 원문 정의 | Python 프로젝트에서의 예 | 이 스킬의 점검 |
|---|---|---|---|
| 1. 공개 SW 보안취약점 (Vulnerabilities in OSS) | 공개 SW의 취약 코드·유해 구성요소가 그 공개 SW를 쓰는 모든 SW에 전파 | 취약 버전 Django/Werkzeug/Pillow/PyYAML 사용 | SCP-06, SCP-07 |
| 2. 타사 의존성 (3rd Party Dependencies) | 타사 SW(상용 SDK·라이브러리·컴포넌트)에 악성코드를 삽입해 운영 시스템 침해 | 상용 SDK wheel, 벤더 제공 `.so`/`.pyd`, 출처 불명 휠 파일 | SCP-02, SCP-19 |
| 3. 공용 리포지토리 (Public Repositories) | GitHub 등에 정상 패키지와 유사한 이름의 악성코드 업로드 | PyPI 타이포스쿼팅(로드맵 사례: `set-utils`, 2025), 의존성 혼동 | SCP-03, SCP-04, SCP-05 |
| 4. 변환 시스템 (Build Systems) | CI/CD 상의 중요 코드·리포지토리·컨테이너·변환 서버를 침해해 악성코드로 교체 | GitHub Actions 태그 변조, `pull_request_target` 악용, 빌드 이미지 오염 | SCP-10, SCP-11, SCP-13 |
| 5. 업데이트 가로채기 (Hijacking Updates) | 업데이트 과정·서버 관리권한을 가로채 악성코드 삽입 | 앱 자체 업데이트·플러그인 다운로드를 서명 검증 없이 실행 | SCP-15, SCP-12 (구현 항목 SEC-15) |
| 6. 내부 리포지토리 (Private Repositories) | 기업 내부 코드 저장소에 침입해 악성코드 삽입 | 사내 Git/패키지 서버 기본 계정, 커밋된 토큰 | SCP-14, SCP-03 |
| 7. 공급사 및 협력사 (Suppliers and Business Partners) | 외부 서비스를 받을 때 관리되지 않는 타사 위험이 내부로 전이 | 외주 개발 코드, 외부 API·SaaS 의존 | SC-25, SC-26, SCP-18 |

## A3. 주요국 정책 동향 (1장 3절, p.14~19)

| 국가·기구 | 내용 |
|---|---|
| 미국 OMB M-22-18 (2022.9) | 연방정부 납품 SW 공급자에게 NIST SSDF 준수 + 자체증명서(Self-attestation Form) 제출 요구. 자체 증명 항목 예: **안전한 개발환경 구축, 자동화된 소스코드 출처 관리, 지속적 취약성 검사**. 기관은 적합성 증거(SBOM 등)를 별도 요구 가능. 증명 양식 최종본 2024.3 확정(M-23-16) |
| 미국 FDA (2023) | FD&C Act 개정. 승인거부(RTA) 정책에 사이버보안 요구 추가: 취약점·익스플로잇을 적시에 모니터링·식별·해결하는 계획, **공개 SW·상용 SW 구성요소 목록을 포함한 SBOM 제공** (2023.10~) |
| 미국 경과 (표4) | 2021 EO 14028, NIST 중요 SW 정의, NTIA SBOM 최소 구성요소(2021.7), SSDF SP 800-218(2022.2), ESF 개발자·공급자·고객 지침(2022), C-SCRM SP 800-161 개정(2022.5) |
| EU CRA | 디지털 요소가 있는 제품의 적합성 평가·CE 마크에 SBOM을 기술 문서로 요구. 제조사에 보안 업데이트, 공급망 점검, 취약성 정보공유 의무. 2023.12 정치적 합의, 2024.3 의회 승인 (로드맵 기준: 2024.12 공포, 2027.12 시행 예정) |
| 일본 | 경제산업성 SBOM 실증(의료·자동차·SW), SBOM 도입 안내서(2023.7). 표5 3단계 로드맵 |
| Quad | 안전한 SW를 위한 공동 원칙: 안전한 개발 활동(조직 구성, 보안 테스트, 취약점 식별·대응, 무단 접근 방지, 릴리스 보관, 릴리스 구성요소 기록(SBOM 등)), 정부 조달 최소 가이드라인(Self-attestation 또는 타사 인증, VDP 보고 권장), 정부 SW 사용 보안 |
| 시사점 | 개발사-공급(유통)사-운영사 간 SBOM 유통 관리 체계 필요, 국내 기준과 글로벌 기준의 조화(세이프 하버) |

## A4. 공급망 사이버보안 위험관리, C-SCRM (2장 1절 1, p.21~23)

NIST SP 800-161r1 정의

- **공급망 요소**: 연구·설계, 개발, 제조, 구입, 배포, 통합, 운영·유지보수, 폐기에 쓰이는 조직·개체·도구
- **공급망 위험**: 공급자(개발사·공급사), 공급망(개발환경·업데이트 전송로), 제품·서비스에서 발생할 수 있는 피해와 침해 가능성
- **C-SCRM**: 공급망 전체에서 사이버보안 위험 노출을 관리·대응하기 위한 전략·정책·절차 등의 관리체계. SDLC 내에 통합되어야 하고 보안·개발·조달·법무·인사가 함께 참여

다단계 전사적 위험관리 (표7)

| 수준 | 이해관계자 | 주요 활동 |
|---|---|---|
| 레벨1 전사 | 경영진(C-Level) | 전사 C-SCRM 전략·거버넌스·위험 기조 정의, PMO 구성 |
| 레벨2 프로세스 | 비즈니스 프로세스 관리자 | 프로세스별 전략, 정책·절차·지침, 신규 IT 프로젝트 취약점 감축, 위험 허용 범위 설정 |
| 레벨3 운영 | 시스템 관리자(아키텍트·개발자·QA 등) | C-SCRM 계획 개발, 정책·요구사항 구현, 개별 시스템 SDLC에 적용, 레벨2에 보고 |

## A5. 참여자별 권장 활동, ESF (2장 1절 2-가, p.24~28)

| 참여자 | 역할 요약 |
|---|---|
| 개발사 | 설계·구현·검증 단계 보안 활동으로 취약점 최소화 + 포함 라이브러리, 빌드·배포 체계의 보안성 확보 |
| 공급사 | 보안 요구사항 충족 확인, 타사 SW 검증, 실행 파일 테스트, 취약점 발견 시 고객사에 알리고 대응 |
| 운영사 | 보안·SCRM 요구사항 정의, 인수테스트, 적용·생명주기 관리 대책 구현 |

**표8. 개발사 권장 활동 (p.26)** — 개발사는 각 단계에서 개발자가 할 보안 활동을 문서로 작성하고 실제로 준수되게 해야 한다.

| 구분 | 세부 내용 | 이 스킬의 점검 |
|---|---|---|
| 안전한 제품 기준 및 관리 | 개발 보안 정책·절차를 문서로 정의. 경영진이 예산·일정 내에서 지원 | SCP-18 |
| 안전한 코드의 개발 | 내부자에 의한 소스코드 수정·공격 차단 | SCP-14 |
| | 안전한 공개 SW 관리 관행 마련 | SCP-01~05 |
| | 안전한 개발자 환경 및 빌드 설정 사용 | SCP-10, SCP-16, SCP-20 |
| | 코드 통합 시 보안성 검증 | SCP-11 |
| | 신고된 결함·취약점에 대한 체계적 대응 | SCP-17, SCP-18 |
| | 외부 개발팀이 기능 확장 시 보안성 확보 | SC-26 |
| 타사 구성요소 검증 | 타사 바이너리 취약점 점검 | SCP-19, SCP-06 |
| | 타사 구성요소 선택·통합 시 보안 위험 평가 | SCP-04, SCP-07 |
| | 신뢰할 수 있는 공급사로부터 컴포넌트 확보 | SCP-03 |
| | 통합 구성요소 유지관리(공급사 활동 모니터링, 계약) | SCP-07 |
| | SBOM을 이용한 검증 | SCP-08 |
| 빌드 환경 보안 강화 | 빌드 체인 공격 대응(소스 저장소·빌드 시스템) | SCP-10, SCP-13 |
| | 서명 서버 해킹 대응 | SCP-12 |
| | 최종 패키지 검증 | SCP-12 |
| 코드 배포 시 보안 강화 | 배포 시스템의 패키지·업데이트 보호 배포, 시스템 보호 | SCP-12, SCP-15 |

**표9. 공급사 권장 활동 (p.27)** — 개발사가 공급사를 겸하면 개발사 활동에 포함해 수행.

| 구분 | 세부 내용 |
|---|---|
| 조직 준비 | SW 보안 점검 기준 정의 및 수행 조직 준비 |
| SW 보호 | 모든 형태의 코드를 비인가 접근으로부터 보호 / 출시(Release) 무결성 검증 메커니즘 제공 / 출시 버전 보관·보호 |
| 보안성이 높은 SW 제작 | 보안 요구사항을 충족하는 설계 / 타사 SW의 보안 요구사항 충족 검증 / 컴파일·빌드 프로세스 보안 구성 / 사람이 읽을 수 있는 코드 검토·분석 / 실행 파일 테스트로 취약점 식별 / 기본 보안 설정이 안전하도록 구성 |
| 보안취약점 대응 | 지속적인 취약점 식별·분석·보완 |

공급사가 갖출 사항: 제공 SW 무결성 유지, 패키지·업데이트 유효성 검사, 알려진 취약점 관리, 고객사 신고 접수 후 개발사 통보.

**표10. 운영사 권장 활동 (p.27~28)**

| 구분 | 세부 내용 |
|---|---|
| 조달 및 인수 | 보안 요구사항 정의 / 제품 평가(평가 대상 제품의 **SBOM 요구**) / 구매 계약에 공급망 보안 요구사항 추가 / 인수 시 공급사 배포 인프라 보안 검증, 제품·구성요소 무결성 검증, **인수 제품과 SBOM 비교·확인** |
| 적용(배포) | 기능 테스트(설치·설정·결과 보고, 테스트 환경 보관) / 충분한 기간 테스트로 숨겨진 악성 기능 확인, 계약 보안 명세 검증 / 구성 제어 위원회(CCB) 검토 / 위험 검토 후 진행·중단 결정 / 운영환경 통합 시 보안 통제 배포·지속 모니터링 / 초기 배포 성공 검증 / 암호화 세션 등 지속 모니터링 |
| 제품 업그레이드 | 통합·보안·상호운영·회귀 테스트 / 다운로드 인프라 무결성 검증, **공급사 SBOM·자체 증명서 확인** / 업그레이드 후 이상 동작 모니터링 |
| 제품 단종 | 제품 관련 계정·권한 비활성화, 보안 인프라의 관련 규칙·역할·그룹 제거 |
| 교육/지원 | 교육·훈련 SW와 환경 보호 |
| SW 운영 | ① 사용자: 오류·이상 현상 보고, 문제 제품 격리, 공급사 통보·추적 절차 ② 업데이트: **승인된 채널·출처에서만 업데이트**, 개발·공급사는 상세 업데이트 노트·전자서명 등 무결성 검증 방법 제공, 운영사는 SBOM·업데이트 무결성 자동 확인, 업데이트 전후 동작 비교, 문제 시 배포 중단 |
| 보안 및 공급망 위험관리 운영 | 기능 변경·보안 이벤트 모니터링, 정기 보안 테스트, 감사, SCRM 평가, 보안 에이전트 무결성 보호, 위협 헌팅, 위협 모델링, 정부·업계 협업 |

※ 원문 주의: ESF 가이드를 국내 적용할 때 개발사·공급사 역할이 미국 환경과 다를 수 있다.

## A6. 안전한 SW 개발체계, NIST SSDF (2장 1절 2-나, p.29~31)

SSDF의 목표: 인력·프로세스·기술 준비 / 모든 구성요소를 변조·비인가 접근으로부터 보호 / 출시 시 취약점 최소화 / 출시 후 남은 취약점 대응·재발 방지. SDLC 모델·언어·플랫폼에 무관하게 적용 가능.

**표11. SDLC 단계 정의**: 설계(기능·제약 정의) → 개발(프로그래밍) → 시험(요구사항 충족·결과 검사) → 배포(최종 고객까지 전달·운영) → 운영(오류 수정, 설계 수정, 새 요구사항, 환경변화 교정).

**표12. SSDF 구현 권장 활동 (p.30~31)**

| 영역 | 관행 | Python 저장소 증거 예 |
|---|---|---|
| 조직 준비(PO) | PO.1 SW 개발 보안 요구사항 정의 | `docs/security-requirements.md`, 이슈 템플릿 |
| | PO.2 역할 및 책임 구현 | CODEOWNERS, SECURITY.md 담당자 |
| | PO.3 지원 도구(Tool chain) 구현 | pre-commit, CI의 bandit/semgrep/pip-audit |
| | PO.4 SW 보안 점검 기준 정의 및 사용 | 이 스킬의 기준표, CI 실패 조건(예: CVSS ≥ 7.0) |
| | PO.5 개발을 위한 보안 환경 구현·유지 | devcontainer, 최소 권한 CI 토큰 |
| SW 보호(PS) | PS.1 모든 형태의 코드를 비인가 접근·변조로부터 보호 | 브랜치 보호, 서명 커밋, 잠금 파일 |
| | PS.2 출시 SW 무결성 검증 메커니즘 제공 | SHA256SUMS, Sigstore 서명, 빌드 출처(provenance) |
| | PS.3 출시 SW 보관 및 보호 | 릴리스 아티팩트·SBOM 보관 |
| 보안성 높은 SW 제작(PW) | PW.1 보안 요구사항을 충족하고 위험을 완화하도록 설계 | `design-SR.md` 설계 점검 |
| | PW.2 설계 검토로 요구사항·위험 준수 검증 | 설계 리뷰 기록 |
| | PW.3 타사 SW 보안 요구사항 준수 검증 (PW.4에 통합) | — |
| | PW.4 가능하면 기능 복제 대신 보안이 잘된 기존 SW 재사용 | 직접 구현한 암호·인증 코드 여부 (SEC-04 등) |
| | PW.5 보안 코딩 관행 준수 | 구현 49개 항목 점검 |
| | PW.6 실행파일 보안을 개선하도록 컴파일·인터프리터·빌드 구성 | SCP-16 |
| | PW.7 사람이 읽을 수 있는 코드 검토·분석 | 정적 분석, 코드 리뷰 |
| | PW.8 실행 코드 테스트로 취약점 식별 | 보안 테스트, DAST |
| | PW.9 기본 설정으로 보안을 갖추도록 구성 | `DEBUG=False` 기본값, 안전한 기본 설정 (ENC-02) |
| 보안취약점 대응(RV) | RV.1 지속적 취약점 식별·확인 | 정기 pip-audit, Dependabot |
| | RV.2 취약점 평가·우선순위·해결 | CVSS·KEV 기반 처리 기록 |
| | RV.3 근본 원인 분석 | 사후 분석 문서 |

참고: 국내 기업 공개 DevSecOps 도구 'NShiftKey'(GitHub Marketplace, 2023.6) — 코드 반영 때마다 취약점 확인.

## A7. SBOM과 최소 요건 (2장 2절 1~3, p.32~37)

- **정의**: NTIA — "SW 구축에 사용되는 다양한 구성요소의 세부 사항과 공급망 관계를 포함하는 공식적인 기록". 가이드라인은 'SW 구성요소 명세서'로 통칭. 기업 목적에 맞게 항목 추가·수정 가능.
- SBOM은 기본적으로 구성요소 종속성을 연결하는 **트리 구조**이며, 이를 통해 Log4j처럼 여러 시스템에 쓰인 구성요소를 빠르게 식별한다.
- 역할별 이점: 개발자(구성요소 최신 여부 식별, 신규 취약점 대응), 구매자(취약점·라이선스 분석으로 위험 평가), 운영자(신규 취약점 노출 여부 빠른 확인).
- NTIA 효과성 분석: SBOM 없이는 취약점 조치까지 수개월~수년, SBOM이 있으면 공급망 각 참여자가 동시에 식별·완화.

**NTIA 최소요건 = ① 데이터 필드 ② 자동화 지원 ③ 관행 및 프로세스**

표14. 데이터 필드 기본항목 7개 (p.35)

| 항목 | 설명 |
|---|---|
| 공급자명 (Supplier Name) | 구성요소를 생성·정의·식별한 주체 |
| 타임스탬프 (Timestamp) | SBOM 데이터로 변환(Assembly)한 날짜·시간 |
| 저작권자 (Author Name) | 구성요소에 대한 SBOM 데이터를 생성하는 주체 |
| 구성요소명 (Component Name) | 최초 공급자가 SW 단위에 할당한 명칭 |
| 버전 (Version String) | 이전 버전으로부터의 변경을 지정하는 식별자 |
| 고유 식별자 (Unique Identifier) | 구성요소 식별 또는 관련 DB 조회 키(Look-up Key) |
| 종속성 관계 (Relationship) | 상위(Upstream) 구성요소 X가 SW Y에 포함된다는 관계 |

※ Python 가이드(2023) API-02는 NTIA 필수 구성요소에 **컴포넌트 해시**를 포함해 적고 있다. 표15 비교표에도 해시 행이 있다.

표15. 형식별 속성 대응 (p.36) — 자동화 지원: SPDX, CycloneDX, SWID 3종

| 데이터 필드 | SPDX | CycloneDX | SWID |
|---|---|---|---|
| 공급자명 | PackageSupplier | Supplier publisher | `<Entity> @role(softwareCreator/publisher), @name` |
| 컴포넌트명 | PackageName | name | `<softwareIdentity> @name` |
| 고유 식별자 | SPDX Document Namespace, SPDXID | serialNumber, bom-ref | `<softwareIdentity> @tagID` |
| 버전 | PackageVersion | version | `<softwareIdentity> @version` |
| 컴포넌트 해시 | PackageChecksum, PackageVerificationCode | hash "alg" | `<Payload>/../<File> @[hash-algorithm]:hash` |
| 종속성 관계 | Relationship: DESCRIBES, CONTAINS | 중첩 어셈블리·종속성 그래프에 내장 | `<Link> @rel, @href` |
| 저작권자 | Creator | metadata/authors/author | `<Entity> @role(tagCreator), @name` |

(원문 표의 오탈자 `seriaNunber`, `soffwareCretor`는 바로잡음)

관행 및 프로세스 6가지 (p.37)

| 요구 | 내용 | 점검 |
|---|---|---|
| Frequency | 새 빌드·릴리스마다 새 SBOM 생성 | CI에서 릴리스마다 생성하는가 |
| Depth | 최상위부터 하위까지 모든 종속성(전이 의존성 포함) 표시 | 직접 의존성만 있는 SBOM은 미흡 |
| Known Unknowns | 종속성이 표시되지 않았을 때 ① 추가 종속성이 없는 것인지 ② 알 수 없는 불완전 상태인지 기록 | CycloneDX `compositions` 등 |
| Distribution and Delivery | 적절한 접근권한·방식으로 제공 | 릴리스 첨부 또는 요청 시 제공 |
| Access Control | 공개 범위에 따른 접근제어 | 취약점 포함 SBOM의 공개 범위 |
| Accommodation of Mistakes | SBOM은 초기 단계이므로 수요자는 의도치 않은 오류·누락을 용인 | — |

CISA가 2023.9 최소요건 개정 중임을 밝힘 → 가이드라인 개정 시 반영 예정.

## A8. 알려진 취약점 관리 (2장 2절 4-가, p.38~40)

SCA(Software Composition Analysis) 도구로 구성요소 분석·SBOM 생성 후 알려진 취약점과 매칭.

1. **SBOM의 취약점 정보 확인**: SBOM `vulnerabilities` 항목 등에서 CVE·KEV 확인 (CycloneDX 예시)
   - CVE: 공개적으로 알려진 보안 결함 목록. KEV(Known Exploited Vulnerability): 악용 사례가 알려져 보완이 시급한 취약점
2. **영향범위 분석**: NVD `https://nvd.nist.gov/vuln/detail/{CVE_ID}`에서 정보 확인
3. **위험 수준 평가·우선순위**: CVSS(0.0~10.0) 기본 점수·심각도 사용 (NVD는 V2.0·V3.0 제공)
4. **조치계획 수립·정보공유**: NVD 조치방안 확인, 우선순위에 따라 계획 수립 후 개발·운영기업에 해당 컴포넌트 정보 공유
   - **CVSS 7.0 이상은 보안 담당자 등과 즉각 완화조치를 수행하거나 조치 방안·시기를 협의해야 한다.**
   - CVSS 외에 CISA KEV 등 추가 지표 활용 가능
   - 실증(p.58): CVSS 외에도 기업 내부 상황, 고객 운영 현황 등을 종합 고려

## A9. 공개 SW 라이선스 관리 (2장 2절 4-나, p.41~44)

라이선스 관리에서 확인할 사항

- 준수 불가능한 조건이 있으면 컴포넌트 교체 등 조치
- 서비스 중단, 3rd 협력자 라이선스 만료, 폐기된 컴포넌트 확인
- 공개·상용·타사 SW 모든 라이선스의 저작 권리·사용 허가 제공 여부 추적

라이선스 분류

| 계열 | 요구 |
|---|---|
| Permissive | 저작권·라이선스 고지 정도만 요구 (예: MIT, BSD, Apache-2.0) |
| Weak copyleft | 수정 부분을 포함한 소스코드 공개 요구 (예: LGPL, MPL) |
| (Strong) copyleft | 결합된 모든 코드의 소스코드 공개 요구 (예: GPL, AGPL) |

(괄호 안 라이선스 예는 이 스킬이 보충한 것)

표16. 라이선스 관리 범위 예 (p.42)

| 구분 | 내용 |
|---|---|
| 형태 | ① 수정 없이 그대로 복제 ② 수정 및 결합 |
| 이슈 | 수정·결합 저작물에서 이슈가 많음 |
| 의무 | 소스코드 공개, 무상 특허 권리 허용, 사용·변경 사용 고지 |
| 고지 방법 | 저작권(“copyright” + 연도 + 저작권자)과 라이선스 사본 고지 |
| 라이선스 | 사용한 공개 SW 라이선스 명시 + 사본 첨부 |

- **서체 라이선스 위반 사례 (p.43)**: SBOM(SPDX) `License` 항목에 `Non-Commercial-Use-Only-Font-License` 서체 발견 → 영리 제품 사용 시 위반. 조치: 상업 사용 가능 서체로 교체하거나 구매.
- **오소리(OSORI)**: 국내 3사가 공개 SW 라이선스 정보 6만여 건과 API 무료 공개(2023). `osori-db.github.io`, 공개 SW 라이선스 종합정보시스템 `olis.or.kr`.
- 국내 기업은 저작권 소송 대응용이던 SBOM을 최근 취약점 관리에도 활용.

## A10. SBOM 기반 공급망 보안 강화 방안 (2장 3절, p.45~49)

- SW 개발 생명주기 각 단계마다 SBOM 생성·배포 체계 구축, 보안 위험이 해소된 SW를 공급
- 모든 구성요소의 SBOM이 어렵다면 **타사 라이브러리·공개 SW 중심으로 작성자 등 출처 정보와 종속성 관계를 우선 관리**
- 개발사 필수 설비: SBOM 도구, SW 구성요소 저장소, SBOM DB, 자체 취약점 DB + NVD 연계
- 공급사·운영사: 기업 지식재산 보호를 위해 **선별·최소화된 SBOM**을 제공받아 활용
- 산업별 SW 공급망 거점 → SW 공급망 관리센터 (계획 수립, 정보 교류, 교육·홍보). 보안 권고(Security Advisory)를 체계화·자동 대응, VEX(Vulnerability and Exploitability Exchange) 인텔리전스로 발전
- 관리 우선순위: 자체 개발하지 않은 상용 SDK 같은 외부 SW부터 SBOM 관리
- IMDRF(국제의료기기규제당국자포럼) 「의료기기 사이버보안을 위한 SBOM 원칙과 사례」(2023.4)

## A11. SBOM 생성·활용 실증 (3장 1절, p.51~58)

실증: 의료·보안 분야 국산 SW 3종, 소스코드·바이너리 분석, SBOM 도구 4종(유료 2, 무료 2).

**SBOM 유효성 검증이 필요한 이유 (p.52)**

1. 개발자의 의도적·비의도적 변경으로 구성요소 누락·오기 (예: `OPENSSL` → `OPENSL`, `SSL`로 이름 변경)
2. 소스코드/바이너리 중 무엇을 분석하느냐, 개발언어에 따라 결과가 다름 → SBOM 도구 도입 시 필수 고려사항
3. 개발·구축 환경 요인으로 개발자도 모르는 구성요소가 발견될 수 있음

자동 도구로 생성하면 항목 일부가 **누락·중복**된다 (표18: `commons-io`의 공급자·라이선스 누락, 같은 버전 중복 → 표19에서 공급자 `apache`, `Apache-2.0`으로 보완하고 중복 삭제).

**SBOM 유효성 검증 요령 (p.53)**

- ❶ **개발자 확인**: 제품 정보(기업명, 서비스명, 개발언어, 패키지 형태, 개발 프레임워크, 공개 SW, 상용 SW, 빌드 시스템, 형상관리 시스템)와 추출 SBOM을 개발자와 비교해 오탐·과탐 검토
- ❷ **완전성 확인**: CycloneDX·SPDX 등 표준의 기본항목 누락 여부, 항목 내용이 표준 요구와 일치하는지 확인

**컴포넌트 관리 (p.54~56)**

- 실증 기업들은 구성요소의 출처·사용이력을 체계적으로 관리하지 못했고, **개발자가 인지하지 못한 공개 SW**, 설치 후 연결되는 라이브러리 내 공개 SW가 추가 발견됨
- 표20 (기업 A 컴포넌트 수): 소스코드 분석 A 1,862 / B 1,747 / C 1,834 (도구 간 차이 작음), 바이너리 분석 A 141 / B 924 / D 453 / E 186 (차이 큼)
- 결론: **2개 이상 도구로 교차 검증** 권장
- 컴포넌트 관리 요령
  - ❶ 개발·공급 과정에서 변경되는 제품의 SBOM을 지속 공유해야 누락 없는 관리 가능
  - ❷ 개발자가 인지하지 못한 공개 SW와 설치 후 생성되는 공개 SW 컴포넌트를 추가 관리
  - ❸ 소스코드·바이너리·의존성을 종합 분석한 SBOM을 관리

**SBOM 기반 공급망 보안 관리 요령 (p.58)**

- ❶ 개발언어 호환성, 분석 알고리즘, 공급망 특성을 확인해 적합한 SBOM 도구 선정
- ❷ 소스/바이너리 방식은 환경에 맞게 선택하되 2개 이상 도구를 상호 보완 (무료 도구 가능)
- ❸ 설계-개발-공급-도입·운영-유지보수 각 단계별 SBOM 생성·공급 체계 구축
- ❹ SBOM DB 구축, NVD 연동
- ❺ 취약점 탐지 시 개발자에게 신속 전파·조치계획 수립, 고객(운영)사도 조치할 수 있는 체계

SBOM의 버전·명칭 오류는 취약점 매칭 오류로 이어진다 → 유효성 검증이 효과적 취약점 관리의 전제.

## A12. 공급망 보안 관리체계 점검 실증 (3장 2절, p.59~60)

5개 분야 54개 세부항목 (표21 예시)

| 분야 | 항목 수 | 점검 항목 예 |
|---|---|---|
| 안전한 제품 관리 | 12 | 정기 SW 보안 교육, 모의해킹·취약점 진단 등 보안 활동 |
| 보안코드 개발 | 13 | 빌드 관리 및 보안성 검토, 빌드 단계 보안요구사항 확인 |
| 타사 구성요소 확인 | 7 | 공개·상용 SW 보안요구사항 확인, 취약성·라이선스 만료 확인 |
| 개발환경 보안 | 16 | 빌드 환경 공격 표면 조사·위협 모델링, 개발환경 접근제어·인터넷 차단 |
| 보안코드 전달 | 6 | 패키지 바이너리 전자서명 생성, 계약 시 SBOM 전달 |

표22 기업 A 결과: 54개 중 양호 24, 부분양호 16, 취약 12, N/A 2. 보안코드 개발(취약 4)과 개발환경 보안(취약 4)에 취약 항목이 많음.

표23 미흡 사례 — 그대로 점검 항목으로 쓴다

| 분야 | 미흡 사례 | 이 스킬의 점검 |
|---|---|---|
| 안전한 제품 관리 | 웹 취약점 점검만 수행, 모의침투·소스코드 진단 필요 | SCP-11 |
| 보안 코드 개발 | 보안성 검토 없이 서비스 위주 개발 | SCP-11, SCP-18 |
| 타사 구성요소 확인 | 관리자 허가 없이 출처 불분명 공개 SW 무단 사용 | SCP-04, SCP-19 |
| | 서비스 계약이 종료된 SW 제품 사용(보안 업데이트 미수행) | SCP-07 |
| 개발환경 보안 | 외부에서 개발한 단말기에 접속해 개발(빌드) | SCP-20 |
| | 악성코드 감염 USB를 백신 검사 없이 개발 단말에 사용 | SCP-20 |
| 보안 코드 전달 | 안전이 확인되지 않은 업데이트 파일 배포 | SCP-12, SCP-15 |
| | SW 제품 무결성 검증 미수행 | SCP-12 |

일부 기업은 DevSecOps를 검토 중이나 취약점보다 라이선스 관리 중심인 경우가 대부분이었다.

## A13. 자가 점검용 공급망 단계별 체크리스트 (표24, p.61~63)

NIST SP 800-161, SP 800-218 참조. 개발사(개발자 업무 지시, 개발환경 자체 점검), 공급사(개발사 준비도 점검, 고객사에 입증 근거), 고객사(도입 전 확인, 도입 후 관리)가 역할에 따라 선택 활용.

| 단계 | 번호 | 점검 항목 | 세부 설명 |
|---|---|---|---|
| 설계 | 1 | 안전한 개발과 관련하여 조직 내 역할 및 책임을 명시하는가? | 사내 공지 및 발령 내용에 역할 및 책임 명시 |
| | 2 | SW 제품, 서비스 개발자 및 관련자에게 보안 교육을 하는가? | 교육 자료에 보안교육(공급망 보안, 시큐어 코딩 등) 확인 |
| | 3 | 개발단계에서 공급망 보안을 고려하였는가? | 형상관리 시스템, SBOM 생성 및 관리 |
| | 4 | 개발환경의 보안상태를 관리하는가? | 개발환경, 엔드포인트의 운영체제, 백신 업데이트 현황 |
| | 5 | 제품의 주요 보안항목을 식별하고 문서로 보관하는가? | 주요 보안항목(데이터 보호 수준, 암호화, 인증, 인가, 접근 통제 등) 명세 확인 |
| 개발 | 6 | SW의 보안취약점 최소화를 위해서 시큐어코딩을 준수하는가? | 소스코드 개발 또는 빌드 시 시큐어코딩 확인 |
| | 7 | 배포 전 기본 설정을 검토하였는가? | 개발도구가 보안 설정 기능을 제공하면 배포 전 기본 설정 검토, 보안 기능 옵션 활성화. 예) 클라이언트-서버 간 모든 네트워크 통신에 SSL 사용, 접근 권한 설정, 리포지터리 암호화 설정 |
| | 8 | 외부 라이브러리를 도입할 때, 보안성을 확인하는가? | 외부 라이브러리 검사(유해성, 무결성 등) |
| | 9 | 내부 저장소에는 인가된 사용자만 접근하는가? | 내부 저장소(소스코드 형상관리 시스템 등)에 접근통제 확인 |
| | 10 | 내부 저장소에 저장된 공개 SW 및 내부 개발 소스코드의 보안취약점을 지속적으로 점검하는가? | SW의 보안취약점 확인(로그 등) |
| | 11 | 빌드 과정에서 자동화된 보안 테스트를 수행하는가? | 빌드 환경에 자동화 보안 테스트 포함 여부 확인 |
| | 12 | 컴파일러, 인터프리터의 사용 시 보안 옵션을 사용하는가? | 빌드 옵션에 보안 기능 활성화 여부 확인. 예) 권한설정, 암호화 설정, 내부 정책 반영 여부 |
| | 13 | 빌드 후 결과물을 보관하는가? | 빌드 관련 결과물(실행파일, 컴파일 로그, SBOM, 보안 테스트 결과물 등) 검토 |
| | 14 | SBOM에 적시된 컴포넌트의 보안취약점을 확인하는가? | SBOM 결과 점검 시 컴포넌트의 보안취약점 식별 |
| | 15 | SBOM을 통해 식별된 심각한 보안취약점에 대한 검증과정이 있는가? | CVSS 7.0 이상 높은 등급의 보안취약점을 가진 컴포넌트에 대한 경로 확인 등 유효성 검증 |
| | 16 | SBOM 작성 이력은 일정 기간 보관하는가? | SBOM 생성 이력 검토 |
| 공급(유통) | 17 | SW의 무결성을 확인할 수 있는 데이터를 전달하는가? | 코드서명, 해시값 등 전달 여부 |
| | 18 | 배포 SW 생성에 사용된 소스코드, 라이브러리, 공개 SW 정보를 안전하게 보관하는가? | 소스코드, 라이브러리 등 안전하게 보관 |
| | 19 | 필요시, 공급(유통)사는 고객(운영)사에 SBOM, 보안취약점, 라이선스, 제재 정보 등을 제공하는가? | SBOM 활용 |
| 도입 및 운영 | 20 | SW 제품 도입에 대한 공급망 보안 요구사항 및 관리에 대한 매뉴얼이 있는가? | 매뉴얼에 SBOM 제공, 보안취약점 제거 및 완화 및 업데이트 제공, 외주업체 보안 요구사항 등 검토 |
| | 21 | 도입 계약 체결 시, 보안 요구사항 이행을 확인하는가? | 보안 요구사항 이행 여부 확인 |
| | 22 | 제품 도입 시, SW의 코드서명 또는 해시값으로 무결성을 확인하는가? | 코드서명 및 해시값 검증 |
| | 23 | CVE 등 주요 보안취약점 공개 시 해당 보안취약점 포함한 SW가 있는지 모니터링하는가? | 알려진 보안취약점에 대한 확인 |
| | 24 | 심각한 보안취약점 발견 시, 공급(유통)사 또는 개발사에 보안취약점 처리 요구를 하는가? | 보안취약점 조치를 위한 절차 점검 여부 확인 |
| | 25 | 외부 개발사를 통해 도입된 SW인 경우, SBOM을 제공 받는가? | SBOM 검토 |
| | 26 | 외부 개발사를 통해 도입된 SW인 경우, 소스코드에 대해 취약요인을 점검하는가? | 외부 개발 소스코드에 대한 보안취약점 점검 |
| 유지보수 | 27 | 운영 SW에 대한 보안취약점 점검을 지속적으로 실시하는가? | 보안취약점 점검결과 검토 |
| | 28 | 보안취약점 식별 시, 보안취약점 평가 및 대응 방안을 가지고 있는가? | 보안취약점 평가 및 대응 방안 검토 |
| | 29 | 신속한 보안취약점 패치를 위한 효율적인 절차를 수행하였는가? | 패치 적용 절차 확인 |
| | 30 | 배포/업데이트 서버 운영 시 서버에 대한 보안관리를 수행하는가? | 배포/업데이트 서버에 적용된 보안정책(인증, 인가, 접근통제 등) 검토 |

## A14. 점검 지원 테스트베드 (4장 1절, p.65~76)

| 시설 | 내용 |
|---|---|
| 기업지원허브(판교, 2015.10~) | IoT 보안 테스트베드. 위협 시연 6종, 소스코드·펌웨어·프로토콜 취약점 점검, 2024년부터 소스코드·바이너리 방식 SBOM 생성·분석 도구 도입(표25: SPDX·CycloneDX 생성, 2,700여 개 라이선스 검출). 신청: KISA 누리집, `iottestbed@kisa.or.kr` |
| 디지털헬스케어 보안리빙랩(원주, 2020.12~) | 의료기기 위협 시연, 네트워크·소스코드 점검, 2024 상반기부터 SBOM 도구. 조치 확인서는 식약처 인허가 사이버보안 시험항목을 갈음. `cslivinglab@kisa.or.kr` |
| 국가사이버안보협력센터 기술공유실(판교, 2022.11~) | 국정원 공급망 보안 테스트베드: SBOM 생성 자동화·관리·취약점 추적. 상용 SCA 도구 3종(표28: 3종 모두 Python 소스코드 분석 지원). 결과는 PDF·한글·엑셀·JSON 출력 |

**신뢰성 높은 SBOM 생성 도구의 조건 (p.72)**

- ❶ 소스코드 및 바이너리 데이터 분석 가능
- ❷ 분석 결과에 대한 유효성 검증 가능 (컴포넌트 해시, 경로 등 제공)
- ❸ 보안취약점 정보와 연동
- ❹ 대용량 리포지토리 및 빠른 검색결과 제공

도구별 식별 방식(표29): 문자열·함수명 지문(fingerprint) 비교, 실행파일 컴포넌트 해시 비교, 소스 파일·헤더 비교, 폴더·파일·소스 일부 단위 해시 비교(일부 복사한 코드도 식별).

테스트베드 실증 (p.74~75): 4개 분야 10개 제품 중 7개에서 CVSS 9.0 이상 취약점 발견, 13개 중대 취약점(RCE, 명령어 삽입, SQL 삽입, 버퍼 오버플로우) 개발사 통보·패치. 펌웨어가 암호화된 CCTV는 SBOM 출력 불가. 표31 예: ImageMagick 6.8.2, XStream 1.4.15, libtiff 4.0.3, Qt 5.3.2, OpenSSL 1.0.2k, busybox 1.21.1, MyBatis 3.2.1, OpenLDAP 2.4, spring-framework 3.2.8, h2 1.4.192, jackson-databind, Log4j 1.2, thymeleaf 3.0.12 (모두 9.1~9.8).

표32 공급망 보안 통합관리 시나리오: 개발사·공급사·운영사가 각자 SBOM을 통합관리 시스템에 등록 → 신규 취약점 공개 시 자동 진단 → 위기 전파·조치 지원, 취약점 관리기관은 전 세계 취약점 실시간 수집·보안권고 자동 전파.

## A15. SBOM 표준 (4장 2절, p.77~84)

표33 국내외 표준

| 형식 | 개발기구 | 국제표준 | 국내표준 |
|---|---|---|---|
| SPDX | 리눅스재단 (라이선스·패키지 정보 공유 중심) | ISO/IEC 5962 (2021) | 단체표준 TTAK.KO-11.0182 (2015, SPDX v2.0 일부 참조) |
| CycloneDX | OWASP (공급망 위험 감소, 취약점 정보 공유 확장성) | — | — |
| SWID | ISO/IEC (IT 자산 관리) | ISO/IEC 19770-2 (2009 제정, 2015 개정) | 국가표준 KS X ISO/IEC 19770-2 (2021). 취약점 관리에는 널리 쓰이지 않음 |

**TTAK.KO-11.0309 「공개 SW 공급망 관리를 위한 SW 목록 구성(SBOM) 속성 규격」 (2022.12) — 15개 구성요소 (표34)**

| # | 구분 | 속성 |
|---|---|---|
| 1 | SBOM 검증 도구 (SBOM Validation Tool Name) | 예) Fosology (원문 표기 Folosology) |
| 2 | 공급자 (Supplier Name) | ComponentSupplier |
| 3 | 저작권자 (Author Name) | ComponentAuthor |
| 4 | 컴포넌트 (Component Name) | ComponentName |
| 5 | 버전 (Version String) | ComponentVersion |
| 6 | 고유식별자 (Unique Identifier) | FormatID |
| 7 | 컴포넌트 해시 (Component Hash) | FileChecksum |
| 8 | 라이선스 명 (License Name) | Component License |
| 9 | 라이선스 결합 형태 (License Usage) | Dynamic/Static Linking |
| 10 | 보안취약점 DB (Vulnerability DB) | VulnerabilityDB, NVD |
| 11 | 관계성 (Relationship) | IncludeComponent, ImportComponent |
| 12 | 릴리즈 날짜 (Release Date) | ReleaseDate |
| 13 | CVE ID | CVE-Year-Serial Number |
| 14 | CVSS Base Score | Base, Impact, Exploitability |
| 15 | CVSS Severity | High, Medium, Low, None |

추가: TTAK.KO-11.0322 「공개 SW SBOM 거버넌스 관리 지침」(2023.12) — SBOM 환경분석, 관리포맷 정의, 자동화 생성 관리정책, R&R, 관리 프로세스.

**NIS-SBOM 기본항목 v1.0 (국가정보원 제안, 표35, p.80~82)**

목표: ❶ 기본항목 간소화 ❷ 취약점 정보 연동 ❸ 위험관리 효율 향상. NTIA 권고안·국내외 표준 분석 + 자체 선정 7개(*) = 20개. 취약점은 CVE·KEV·CVSS 연동, 관리는 제품별, 식별은 제품 내 구성요소 단위. PDF·한글·엑셀 등 표 형태 출력 지원.

| # | 항목 | 내용 |
|---|---|---|
| 1 | SBOM Standard* | SBOM 표준 종류 (예: NIS 1.0, CycloneDX 1.6) |
| 2 | SBOM Type* | 생성 단계: Design, Source, Build, Analyzed, Deployed, Runtime 등 |
| 3 | CycloneDX No. | CycloneDX 사용 시 번호 (serialNumber) |
| 4 | SPDX Doc. ID | SPDX 사용 시 문서번호 |
| 5 | SBOM ID* | SBOM 문서 고유 식별자: **기업명-생성년월일-일련번호(6자리)** |
| 6 | Product Name* | 대상 제품 이름 |
| 7 | Product Version* | 대상 제품 버전 |
| 8 | Component Name | 컴포넌트 이름 (CycloneDX는 Component, SPDX는 Package) |
| 9 | Component Alias* | 이름이 중복될 때 구분용 별칭 |
| 10 | Component Version | 취약점 식별의 최소 단위인 컴포넌트 버전 |
| 11 | Component Supplier Name | 컴포넌트 개발자 이름 |
| 12 | Component Hash | 식별 정확성 검증용, **SHA-256 이상** |
| 13 | Component Path* | 컴포넌트 실제 위치 (식별 정확성 검증용) |
| 14 | SBOM Author Name | SBOM 작성자 |
| 15 | Unique Identifier | 버전 외에 조회 가능한 고유 식별자 (**CPE, PURL** 등) |
| 16 | Dependency Relationship | 상위 컴포넌트와의 종속 관계 |
| 17 | Timestamp | SBOM 생성일시 |
| 18 | License Name·Version | 라이선스 이름·버전 |
| 19 | Vul. DB | NVD(CVE), CISA(KEV) 등 취약점 DB |
| 20 | Vul. Info | CVE 식별자 + CVSS 등급: 0.0 없음 / 0.1~3.9 낮음 / 4.0~6.9 중간 / **7.0~8.9 높음** / 9.0~10.0 심각 |

※ 원문은 7.0~8.9 구간을 "확인"으로 적었으나 CVSS v3 등급 체계상 "높음(High)"의 오기로 보고 바로잡았다.
※ (*) 자체 선정 항목: 1, 2, 5, 6, 7, 9, 13. 원문은 "7개 자체 선정"이라고 한다.

## A16. 발전 제언 (4장 3절, p.85~86)

| 제언 | 요지 |
|---|---|
| 가. 개발기업 SW 투명성 확보 지원 | 지원센터를 통한 취약점 관리·컨설팅, SBOM 관리체계 공통모델 연구 |
| 나. SBOM·공급망 보안 투자 | 미국 FDA·연방 자체증명·EU CRA는 무역장벽 → 선제 투자가 경쟁력 |
| 다. 공급자-수요자 연계 관리 | 수요 기관도 IT 자산·SW·구성요소를 함께 관리하고 취약점 모니터링 |
| 라. 안전한 개발환경·사이버 복원력 | 보안적합성·IoT 보안 라벨링 등 제도화, 개발자 커뮤니티·SDL·DevSecOps 교육, C-Level 인식 제고 |
| 마. SBOM 안전 활용·기밀성 보장 공유 | 무제한 공유는 공격·지재권 탈취에 악용 가능 → 기밀 컴퓨팅 환경 등 안전한 공유 기술 연구 |

---

# B부. 이 스킬의 점검 기준

## B1. 체크리스트 30항목(SC-01~SC-30)의 Python 저장소 판정 방법

`SC-nn` 번호는 표24 번호와 같다. "저장소에서 확인"이 비어 있지 않은 항목만 정적 검사로 판정하고, 나머지는 `확인 필요(조직)`으로 보고한다.

| ID | 단계 | 요지 | 증거 | Python 저장소에서 확인 | 연결 |
|---|---|---|---|---|---|
| SC-01 | 설계 | 역할·책임 명시 | 조직, 문서 | `CODEOWNERS`, `SECURITY.md`의 담당자·연락처 | SCP-18 |
| SC-02 | 설계 | 보안 교육 | 조직 | (없음) 교육 기록 | — |
| SC-03 | 설계 | 개발단계 공급망 보안 고려 | 코드, CI | 형상관리(Git) 사용 + SBOM 생성 설정 | SCP-08 |
| SC-04 | 설계 | 개발환경 보안상태 관리 | 조직 | devcontainer·Dockerfile 기반 이미지 최신성 정도만 | SCP-13, SCP-20 |
| SC-05 | 설계 | 주요 보안항목 문서화 | 문서 | 데이터 보호·암호화·인증·인가·접근통제 명세 문서 존재 | SCP-18, design-SR |
| SC-06 | 개발 | 시큐어코딩 준수 | 코드 | 구현 49개 항목 점검 결과 | impl-1~3 |
| SC-07 | 개발 | 배포 전 기본 설정 검토 | 코드 | `DEBUG`, `ALLOWED_HOSTS`, `SECURE_*`, TLS 강제, 파일 권한, 비밀값 기본값 | SCP-16, ENC-02, SEC-05 |
| SC-08 | 개발 | 외부 라이브러리 도입 시 보안성 확인 | 코드, 도구 | 버전 고정·해시·인덱스·이름 검증 | SCP-01~05 |
| SC-09 | 개발 | 저장소 접근통제 | 조직, 코드 | 커밋된 자격증명·기본 계정 부재, CODEOWNERS, (가능하면) 브랜치 보호 | SCP-14 |
| SC-10 | 개발 | 공개 SW·내부 코드 취약점 지속 점검 | CI | 정기 실행 워크플로(`schedule:`) + SCA/SAST | SCP-06, SCP-17 |
| SC-11 | 개발 | 빌드 시 자동 보안 테스트 | CI | 워크플로·pre-commit의 bandit/semgrep/pip-audit/비밀 스캔 | SCP-11 |
| SC-12 | 개발 | 컴파일러·인터프리터 보안 옵션 | 코드 | Python 해석 기준 (SCP-16): `-O` 사용 시 assert 의존 보안 검사 소실, Cython `boundscheck=False`, C 확장 빌드 플래그 | SCP-16, ERR-03 |
| SC-13 | 개발 | 빌드 결과물 보관 | CI | 아티팩트 업로드(SBOM·보안 테스트 결과 포함)와 보관 기간 | SCP-12 |
| SC-14 | 개발 | SBOM 컴포넌트 취약점 확인 | 도구 | SBOM 기반 취약점 스캔(grype/osv-scanner/pip-audit) | SCP-06, SCP-08 |
| SC-15 | 개발 | CVSS ≥ 7.0 취약점 검증 | 도구, 코드 | 해당 컴포넌트의 실제 사용 경로 확인(import·호출 위치) | SCP-06 |
| SC-16 | 개발 | SBOM 이력 보관 | CI | 릴리스마다 SBOM 첨부·보관 | SCP-08 |
| SC-17 | 공급 | 무결성 데이터(서명·해시) 전달 | CI | 체크섬 파일, Sigstore/GPG 서명, 빌드 출처 증명 | SCP-12 |
| SC-18 | 공급 | 배포 생성 소스·라이브러리 정보 보관 | 코드, CI | 태그된 릴리스, 잠금 파일, 빌드 재현 정보 | SCP-01, SCP-12 |
| SC-19 | 공급 | 고객에게 SBOM·취약점·라이선스·제재 정보 제공 | CI, 문서 | 릴리스에 SBOM·라이선스 고지 첨부 | SCP-08, SCP-09 |
| SC-20 | 도입·운영 | 도입 시 공급망 요구사항 매뉴얼 | 조직, 문서 | 외주·외부 SW 도입 기준 문서 | SCP-18 |
| SC-21 | 도입·운영 | 계약 시 보안 요구사항 이행 확인 | 조직 | (없음) | — |
| SC-22 | 도입·운영 | 도입 시 서명·해시로 무결성 확인 | 코드, CI | `--require-hashes`, 다운로드 파일 해시·서명 검증 코드 | SCP-02, SCP-15 |
| SC-23 | 도입·운영 | 주요 CVE 공개 시 해당 SW 모니터링 | CI | Dependabot/Renovate, 정기 SCA | SCP-17 |
| SC-24 | 도입·운영 | 심각 취약점 처리 요구 절차 | 문서 | SECURITY.md·이슈 템플릿의 처리 절차 | SCP-18 |
| SC-25 | 도입·운영 | 외부 개발 SW의 SBOM 수령 | 조직, 코드 | 벤더 제공 바이너리·SDK의 SBOM 존재 | SCP-19 |
| SC-26 | 도입·운영 | 외부 개발 소스코드 취약점 점검 | 코드 | 외주·벤더링 코드도 점검 범위에 포함했는가 | SCP-19, impl-1~3 |
| SC-27 | 유지보수 | 운영 SW 취약점 지속 점검 | CI | 배포 브랜치 대상 정기 스캔 | SCP-17 |
| SC-28 | 유지보수 | 취약점 평가·대응 방안 | 문서 | 심각도 기준·대응 기한이 적힌 정책 | SCP-18 |
| SC-29 | 유지보수 | 신속 패치 절차 | 문서, CI | 패치 릴리스 절차, 자동 PR 병합 기준 | SCP-17, SCP-18 |
| SC-30 | 유지보수 | 배포·업데이트 서버 보안관리 | 조직, CI | 배포 자격증명 관리(OIDC Trusted Publishing, 최소 권한 토큰) | SCP-10, SCP-12 |

판정값: `충족 / 부분충족 / 미충족 / 확인 필요(조직) / 해당없음`.

## B2. Python 저장소 공급망 점검 항목 (SCP-01 ~ SCP-20)

공통 변수 (아래 명령에서 사용)

```bash
REQ=(-g 'requirements*.txt' -g 'requirements/*.txt' -g 'constraints*.txt')
WF=(-g '.github/workflows/*.yml' -g '.github/workflows/*.yaml' -g 'action.yml' -g 'action.yaml' -g '.gitlab-ci.yml' -g 'Jenkinsfile' -g 'azure-pipelines.yml' -g 'bitbucket-pipelines.yml')
DF=(-g 'Dockerfile*' -g '*.Dockerfile' -g 'Containerfile*')
```

### SCP-01. 의존성 버전 고정 및 잠금 파일 [코드] — 심각도 중간

- 근거: 표24 #8·#18, 표8 '안전한 공개 SW 관리 관행', SSDF PS.1·PS.3, 공격 유형 1·3. Python 가이드(2023) API-02의 버전 고정 권고와 같은 내용.
- 탐지

```bash
# 버전이 '=='로 고정되지 않은 요구사항 줄 (주석·옵션·해시 줄 제외)
rg -n -v -e '^\s*(#|-|$)' -e '==\s*[\w.]+' -e '@\s*[0-9a-f]{40}' "${REQ[@]}"
# 잠금 파일 존재 여부
rg --files -g poetry.lock -g uv.lock -g Pipfile.lock -g pdm.lock -g 'requirements*.lock' -g 'requirements*.txt'
```

- 판정
  - **애플리케이션**(웹 서비스, 배포 대상): 직접 의존성이 `==` 고정이고 전이 의존성까지 담긴 잠금 파일(`poetry.lock`, `uv.lock`, `Pipfile.lock`, `pdm.lock`, `pip-compile` 결과)이 있으면 충족. 범위(`>=`, `~=`, `^`)만 있고 잠금 파일이 없으면 미충족.
  - **라이브러리**(PyPI 배포 패키지): `pyproject.toml`의 범위 지정은 정상이다. 대신 CI·개발용 잠금 파일이 있는지만 본다.
  - 잠금 파일이 있는데 CI·Dockerfile이 잠금 파일을 쓰지 않고 `pip install <이름>`으로 설치하면 부분충족.
- 수정 예

```bash
pip-compile --generate-hashes -o requirements.txt requirements.in    # pip-tools
uv pip compile --generate-hashes requirements.in -o requirements.txt  # uv
poetry lock                                                         # poetry
```

### SCP-02. 설치 시 해시 검증 [코드·CI] — 심각도 중간

- 근거: 표24 #8 '무결성' 검사, #22 해시 검증, SSDF PS.2, 구현 항목 SEC-15(무결성 검사 없는 코드 다운로드).
- 탐지

```bash
rg -c -e '--hash=sha(256|384|512):' "${REQ[@]}"                 # 해시가 붙은 줄 수
rg -n -e 'require-hashes' -e 'PIP_REQUIRE_HASHES' "${WF[@]}" "${DF[@]}" -g Makefile -g tox.ini -g noxfile.py -g '*.sh' --hidden
```

- 판정: 해시가 모든 요구사항에 있고 설치 명령이 `--require-hashes`(또는 해시 포함 잠금 파일을 쓰는 poetry/uv/pipenv)를 쓰면 충족. 일부에만 해시가 있으면 pip는 `--require-hashes` 모드에서 설치를 거부하므로 실제 설치 방식을 함께 본다.
- 오탐 주의: poetry·uv·pipenv 잠금 파일에는 해시가 기본 포함된다.

### SCP-03. 패키지 인덱스 출처와 의존성 혼동 [코드·CI] — 심각도 높음

- 근거: 표8 '신뢰할 수 있는 공급사로부터 컴포넌트 확보', 공격 유형 3(공용 리포지토리)·6(내부 리포지토리).
- 위험: `--extra-index-url`로 사내 인덱스와 PyPI를 함께 쓰면 pip는 두 인덱스를 동등하게 보고 **더 높은 버전**을 고른다. 공격자가 사내 패키지와 같은 이름을 PyPI에 높은 버전으로 올리면 악성 패키지가 설치된다(의존성 혼동). `http://` 인덱스와 `--trusted-host`는 전송 구간 변조를 허용한다.
- 탐지

```bash
rg -n -i --hidden -e '(extra-index-url|--index-url\s+http://|index-url\s*=\s*http://|trusted-host)' \
   "${REQ[@]}" -g pip.conf -g pip.ini -g pyproject.toml -g setup.cfg -g tox.ini -g Pipfile -g uv.toml "${DF[@]}" "${WF[@]}"
```

- 판정: 사내 패키지가 있는데 `--extra-index-url`을 쓰면 높음. `http://` 인덱스 또는 `trusted-host`는 높음. 단일 프록시 인덱스(`--index-url`, Artifactory·Nexus 등이 PyPI를 프록시)만 쓰면 충족.
- 수정: 단일 인덱스 사용, uv는 `index-strategy = "first-index"`(기본)와 `[[tool.uv.index]]`에 `explicit = true`로 사내 패키지 인덱스를 고정, 사내 패키지 이름을 PyPI에 선점 등록.

### SCP-04. 타이포스쿼팅·출처 불명 패키지 [코드 + 수동] — 심각도 높음(확인 시)

- 근거: 공격 유형 3, 표23 '관리자 허가 없이 출처가 불분명한 공개 SW 무단 사용', 로드맵 사례 `set-utils`(2025, PyPI, 암호화폐 지갑 개인키 탈취)·XZ Utils(2024, 관리자 권한 장악 후 백도어).
- 탐지: 스킬의 `scripts/typo_check.py`로 유명 패키지와 이름이 비슷한 패키지를 찾는다. 결과는 **의심**이며 확인 절차를 거친다.

```bash
python3 -I .claude/skills/kisa-secure-coding-python/scripts/typo_check.py backend/requirements.txt [pyproject.toml ...]
```

  스크립트 본문은 `scripts/typo_check.py`에만 둔다 (문서에 사본을 두면 내용이 어긋난다). 유명 패키지 목록(`POPULAR`)에는 다시잇다 스택 패키지(psycopg, pgvector, python-multipart 등)도 들어 있어 정상 패키지 오탐을 줄인다.

  테스트 결과 예: `reqeusts ~ ['requests']`, `set-utils ~ ['utils']`, `pycrypto ~ ['pycryptodome']`(pycrypto는 실제 패키지지만 유지보수 종료 → SCP-07).

- 확인 절차 (의심 패키지마다): PyPI 프로젝트 페이지의 최초 등록일·릴리스 수·관리자, 소스 저장소 링크와 실제 저장소 일치 여부, 다운로드 규모, `setup.py`·빌드 훅의 네트워크 접근·난독화 코드. 저장소 README·코드에서 실제로 import하는 이름과 설치 이름이 같은지 확인.
- 판정: 이름이 유사하고 등록이 최근이거나 출처 저장소가 없으면 높음. 정상 패키지로 확인되면 기록만 남긴다.

### SCP-05. VCS·URL 직접 의존성 [코드] — 심각도 중간

- 근거: 공격 유형 3·6, SSDF PS.1.
- 탐지

```bash
rg -n --pcre2 -e '(git\+|hg\+|svn\+|@\s*https?://)(?!.*@[0-9a-f]{40}\b)' "${REQ[@]}" -g pyproject.toml -g Pipfile -g setup.cfg -g setup.py
```

- 판정: 브랜치·태그(`@main`, `@v1.2`)로 지정한 Git 의존성은 원격에서 내용이 바뀔 수 있어 미충족. 40자리 커밋 해시 고정이면 충족. 아카이브 URL은 `#sha256=` 해시가 있어야 충족.

### SCP-06. 알려진 취약점 (SCA) [도구] — 심각도: CVSS 기준

- 근거: A8 취약점 관리 4단계, 표24 #10·#14·#15·#23·#27, SSDF RV.1·RV.2, 공격 유형 1.
- 실행 (있는 도구만, 설치는 사용자 동의 후)

```bash
pip-audit -r requirements.txt --desc -f json -o pip-audit.json   # PyPI/OSV 취약점 DB
pip-audit -r requirements.txt --require-hashes                   # 해시까지 강제할 때
osv-scanner scan source -r .                                     # OSV (v1은 osv-scanner -r .)
grype sbom:sbom.cdx.json                                         # SBOM 기반 스캔
```

- 판정 (가이드라인 기준 + 이 스킬의 심각도)

| 조건 | 보고 심각도 | 근거 |
|---|---|---|
| CISA KEV 등재 또는 공개 익스플로잇 확인 | 높음 (즉시) | A8: KEV는 보완이 시급 |
| CVSS ≥ 9.0 | 높음 | NIS-SBOM 등급 '심각' |
| 7.0 ≤ CVSS < 9.0 | 높음 | A8: 7.0 이상 즉각 완화 또는 조치 시기 협의 |
| 4.0 ≤ CVSS < 7.0 | 중간 | NIS-SBOM 등급 '중간' |
| CVSS < 4.0 | 낮음 | — |

- **경로 확인(#15)**: CVSS ≥ 7.0이면 취약 함수·모듈을 실제로 쓰는지 확인해 보고서에 적는다. 예: `rg -n --type py -e '^\s*(import|from)\s+yaml\b' -e 'yaml\.load\('`. 사용하지 않아도 업그레이드 권고는 유지하고 "도달 경로 없음(완화 근거)"으로 적는다. VEX가 있으면 그 상태(`not_affected` 등)를 인용한다.
- 도구가 없으면: 주요 패키지 버전 목록을 보고서에 적고 `확인 필요(도구)`. 추측으로 CVE 번호를 쓰지 않는다.

### SCP-07. 유지보수 종료·폐기 구성요소와 런타임 [코드 + 수동] — 심각도 중간

- 근거: 표8 '통합된 구성요소 유지관리', 표21 '취약성·라이선스 만료 확인', 표23 '서비스 계약이 종료된 SW 사용', 구현 항목 API-02.
- 탐지

```bash
rg -n -i -e '^\s*pycrypto\b' "${REQ[@]}" -g pyproject.toml -g setup.cfg -g setup.py   # 대표 예. 다른 패키지는 PyPI 최종 릴리스일·저장소 보관(archived) 여부로 확인
rg -n -e 'python_requires' -e 'requires-python' -g setup.py -g setup.cfg -g pyproject.toml
rg -n -e '^\s*FROM\s+python:' "${DF[@]}"
rg -n --hidden -e 'python-version' "${WF[@]}" ; rg --files --hidden -g .python-version -g runtime.txt
```

- 판정: 지원이 끝난 Python 버전(python.org 버전 상태 페이지 기준)이나 유지보수 종료 패키지(`pycrypto` → `pycryptodome`/`cryptography`)를 쓰면 미충족. 오래 릴리스가 없는 패키지는 `의심`으로 적고 대체재 검토를 권고.
- 기준일을 보고서에 적는다 (EOL 판단은 날짜에 따라 바뀜).

### SCP-08. SBOM 생성·검증·이력 [CI·도구] — 심각도 중간

- 근거: A7 NTIA 최소요건, A11 유효성 검증, A15 NIS-SBOM, 표24 #3·#13·#14·#16·#19, 표8 'SBOM을 이용한 검증'.
- 탐지

```bash
rg --files --hidden -g '!.git' -g '*sbom*' -g '*bom.json' -g '*bom.xml' -g '*.cdx.json' -g '*.spdx*'
rg -n --hidden -e 'cyclonedx|syft|spdx|sbom|anchore/sbom-action' "${WF[@]}" -g Makefile -g noxfile.py -g tox.ini
```

- 생성 명령 (교차 검증을 위해 2개 이상 권장 — A11)

```bash
cyclonedx-py requirements requirements.txt -o sbom.cdx.json   # 요구사항 파일 기준
cyclonedx-py environment -o sbom.env.cdx.json                 # 설치된 환경 기준(전이 의존성 포함)
syft dir:. -o cyclonedx-json=sbom.syft.cdx.json               # 디렉터리 스캔(벤더링 코드 등도 탐지)
syft <image>:<tag> -o spdx-json=sbom.image.spdx.json          # 배포 컨테이너 이미지 기준
```

- 판정
  - **Frequency**: 릴리스·빌드마다 생성 → CI에 생성 단계가 있으면 충족, 저장소에 수동 생성 파일 하나만 있으면 부분충족(오래된 SBOM)
  - **Depth**: 전이 의존성 포함 여부 (`requirements.txt`만 기준이면 잠금 파일이 없을 때 전이 의존성 누락)
  - **필드 완전성**: 아래 B3 스크립트로 NTIA 7개 + NIS-SBOM 항목 누락 확인
  - **이력**: 릴리스 첨부 또는 아티팩트 보관 기간 설정 (#16)
  - **교차 검증**: 두 도구의 컴포넌트 수·목록 차이를 비교해 큰 차이는 원인 확인 (A11 표20)
  - **접근통제**: 취약점 정보를 포함한 SBOM을 공개 저장소에 그대로 두는지 (A7 Access Control, A16-마)

### SCP-09. 라이선스 [도구 + 코드] — 심각도 중간(상업 배포 시 높음)

- 근거: A9, 표16, 서체 사례, 표24 #19.
- 탐지

```bash
pip-licenses --format=markdown --with-urls --order=license        # 설치 환경 기준
rg --files --hidden -g '!.git' -g 'LICENSE*' -g 'COPYING*' -g 'NOTICE*' -g 'THIRD_PARTY*'
rg --files -g '*.ttf' -g '*.otf' -g '*.woff' -g '*.woff2'          # 서체: 라이선스 별도 확인 (A9 사례)
```

- 판정
  - 프로젝트 자체 LICENSE 부재: 부분충족(공개 저장소면 사용 조건 불명)
  - strong copyleft(GPL·AGPL) 구성요소를 비공개 소스로 배포·서비스: 의무 검토 필요 → `확인 필요` + 높음 후보 (AGPL은 네트워크 서비스 제공도 공개 의무 대상)
  - 비상업 전용(Non-Commercial) 서체·데이터·모델 가중치를 상업·공모전 수상 후 사업화 예정 제품에 사용: 미충족
  - 고지 의무: 배포물에 저작권·라이선스 사본(THIRD_PARTY_NOTICES 등)이 있는가

### SCP-10. CI/CD 파이프라인 무결성 [CI] — 심각도 높음

- 근거: 공격 유형 4(SolarWinds·Codecov·3CX), 표8 '빌드 체인 공격 대응', 표24 #30, SSDF PO.5·PS.1.
- 탐지

```bash
# 커밋 해시가 아닌 태그·브랜치로 참조한 외부 Action (로컬 ./ 와 docker:// 제외)
rg -n --hidden --pcre2 "${WF[@]}" -e 'uses:\s*["\x27]?(?!\./|docker://)[\w.-]+/[\w./-]+@(?![0-9a-f]{40}\b)'
# 위험 트리거·과도 권한·스크립트 삽입(이벤트 값이 run 셸에 직접 들어감)
rg -n --hidden "${WF[@]}" -e 'pull_request_target' -e 'workflow_run' -e 'permissions:\s*write-all' -e 'run:.*\$\{\{\s*github\.(event|head_ref)'
# 원격 스크립트를 검증 없이 셸로 실행
rg -n --hidden -e '(curl|wget)\b[^|\n]*\|\s*(sudo\s+)?(ba|z|da)?sh\b' -g '!*.md'
# 비밀값 출력·자체 호스팅 러너
rg -n --hidden "${WF[@]}" -e 'echo\s+.*\$\{\{\s*secrets\.' -e 'runs-on:.*self-hosted'
```

- 판정
  - 외부 Action 태그 참조: 중간 (태그는 이동 가능 — 커밋 SHA 고정 권고)
  - `pull_request_target`/`workflow_run`에서 PR 코드를 체크아웃해 실행: 높음
  - `${{ github.event.* }}`를 `run:`에 직접 삽입: 높음 (CI 명령 삽입, INP-05와 같은 구조) — `env:`로 넘긴 뒤 `"$VAR"`로 사용
  - 워크플로 `permissions` 미지정 또는 `write-all`: 중간 — 최상위에 `permissions: contents: read`
  - `curl | sh`: 중간 (해시 검증 후 실행으로 대체)
  - 공개 저장소의 self-hosted 러너: 높음

### SCP-11. 빌드 단계 자동 보안 테스트 [CI] — 심각도 중간

- 근거: 표24 #6·#10·#11, 표9 '사람이 읽을 수 있는 코드 검토·분석', SSDF PO.3·PW.7·PW.8, NShiftKey(DevSecOps) 사례, 표23 '보안성 검토 미수행'.
- 탐지

```bash
rg -n --hidden "${WF[@]}" -g .pre-commit-config.yaml -g tox.ini -g noxfile.py -g Makefile \
   -e 'bandit|semgrep|ruff.*\bS\b|pip-audit|safety|osv-scanner|trivy|grype|gitleaks|trufflehog|detect-secrets|codeql'
rg -n --hidden -g .pre-commit-config.yaml -e 'rev:\s*["\x27]?(main|master|HEAD|latest|stable)\b'   # 고정되지 않은 훅
```

- 판정: SAST(bandit/semgrep/CodeQL) + SCA(pip-audit 등) + 비밀 스캔이 PR·푸시에서 실행되고 실패 시 병합을 막으면 충족. 일부만 있으면 부분충족. `continue-on-error: true`로 결과를 무시하면 부분충족. pre-commit 훅이 브랜치 참조면 SCP-10과 같은 이유로 중간.

### SCP-12. 산출물 무결성·서명·보관 [CI] — 심각도 중간

- 근거: 표24 #13·#17·#22, 표8 '서명 서버 해킹 대응·최종 패키지 검증', 표9 '출시 무결성 검증 메커니즘·출시 버전 보관', SSDF PS.2·PS.3, 표21 '패키지 바이너리 전자서명 생성'.
- 탐지

```bash
rg -n --hidden "${WF[@]}" -e 'sigstore|cosign|attest-build-provenance|slsa-github-generator|gpg\s+--(detach-)?sign|sha256sum|shasum -a 256' \
   -e 'pypa/gh-action-pypi-publish' -e 'id-token:\s*write' -e 'upload-artifact' -e 'retention-days'
rg -n --hidden "${WF[@]}" -e 'PYPI_(API_)?TOKEN|TWINE_PASSWORD'    # 장기 토큰 사용 (Trusted Publishing 권고)
```

- 판정
  - 릴리스 산출물(휠, 이미지, 실행파일)에 체크섬 또는 서명이 함께 배포되면 충족, 없으면 미충족
  - PyPI 배포가 장기 API 토큰이면 부분충족 → OIDC Trusted Publishing(`id-token: write` + `pypa/gh-action-pypi-publish`) 권고
  - 빌드 결과물·SBOM·보안 테스트 결과를 아티팩트로 보관하지 않으면 #13 미충족
- 배포 대상이 없는 프로젝트(공모전 제출용 소스만)는 `해당없음`이되, 제출 압축 파일의 SHA-256 기록을 권고.

### SCP-13. 컨테이너 이미지 구성 [코드] — 심각도 중간

- 근거: 공격 유형 2·4(Codecov: 컨테이너 이미지 취약점), 표24 #4·#7, 표8 '안전한 개발자 환경 및 빌드 설정'.
- 탐지

```bash
rg -n -i --pcre2 "${DF[@]}" -e '^\s*FROM\s+(--platform=\S+\s+)?(?!scratch\b)[^\s@]+(\s|$)'   # 다이제스트(@sha256) 미고정
rg -n -i "${DF[@]}" -e '^\s*FROM\s+\S+:latest\b' -e '^\s*ADD\s+https?://' -e '^\s*USER\s+(root|0)\b'
rg --files-without-match -i '^\s*USER\s' "${DF[@]}"                                           # USER 지정 없음 → root 실행
rg -n -i "${DF[@]}" -e '^\s*(ARG|ENV)\s+\w*(TOKEN|PASSWORD|SECRET|API_?KEY)\w*'               # 이미지 레이어에 남는 비밀
rg -n -i "${DF[@]}" -e 'pip3?\s+install(?!.*(-r|--require-hashes))' --pcre2                    # 해시·잠금 없이 개별 설치
```

- 판정: `latest`·태그만 있는 FROM은 중간(다이제스트 고정 권고), USER 미지정은 중간, `ADD <URL>`은 무결성 검증이 없어 중간, ARG/ENV 비밀은 높음(SEC-06과 연결).

### SCP-14. 저장소 접근통제와 비밀정보 [코드 + 조직] — 심각도 높음

- 근거: 표24 #9, 표8 '내부자에 의한 소스코드 수정 또는 공격 차단', 공격 유형 6(닛산: Git 서버 기본 계정, PHP 자체 Git 서버 침해), 구현 항목 SEC-06·SEC-13.
- 탐지

```bash
rg --files --hidden -g '!.git' -g '.env' -g '.env.*' -g '!.env.example' -g '*.pem' -g '*.key' -g '*.p12' -g 'id_rsa*' -g 'credentials*.json' -g '.pypirc' -g '.netrc'
rg --files --hidden -g CODEOWNERS -g .github/CODEOWNERS -g docs/CODEOWNERS
rg -n --hidden -e '://[^:/\s"\x27]+:[^@/\s"\x27]+@' -g '!.git'                  # URL에 박힌 계정 (git remote, 인덱스 URL 포함)
git log --all --diff-filter=D --name-only --format= -- '*.env' '*.pem' '*.key' 2>/dev/null | sort -u   # 과거에 커밋됐다 지운 비밀 파일
```

- 판정: 비밀 파일·자격증명 URL이 저장소나 이력에 있으면 높음(이력에만 있어도 폐기·교체 필요). CODEOWNERS·브랜치 보호는 [조직] — `gh api repos/{owner}/{repo}/branches/{branch}/protection`을 실행할 수 있으면 확인, 아니면 `확인 필요(조직)`.

### SCP-15. 런타임 코드 다운로드·동적 설치·업데이트 [코드] — 심각도 높음

- 근거: 공격 유형 5(ASUS, 국내 ERP 업데이트 서버), 표10 '승인된 채널과 출처에서만 업데이트', 표24 #22·#30, 구현 항목 SEC-15·INP-02.
- 탐지

```bash
rg -n --type py -e 'pip\._internal' -e '["\x27]-m["\x27]\s*,\s*["\x27]pip["\x27]' -e '(system|run|call|check_call|check_output|Popen)\(.*pip3?\s+install' \
   -e 'urlretrieve\(' -e 'import_module\(\s*request' -e 'exec\(\s*(requests|urllib|httpx)' -e '__import__\('
```

- 판정: 실행 중에 패키지를 설치하거나, 내려받은 코드·플러그인·모델 파일을 해시·서명 검증 없이 실행·로드하면 높음. 자체 업데이트 기능은 HTTPS + 서명 검증(공개키 고정) + 롤백 방지(버전 단조 증가) 여부를 본다. 모델 파일은 `torch.load`·pickle 로드 시 COD-05와 함께 판정.

### SCP-16. 개발도구·인터프리터 보안 옵션과 기본 설정 [코드] — 심각도 중간

- 근거: 표24 #7(배포 전 기본 설정 검토)·#12(컴파일러·인터프리터 보안 옵션), 표9 '컴파일·빌드 프로세스 보안 구성'·'기본 보안 설정이 안전하도록', SSDF PW.6·PW.9.
- Python 해석 (원문은 언어 중립 → 이 스킬의 해석임을 보고서에 밝힌다)
  - `python -O`/`PYTHONOPTIMIZE`: `assert`가 제거되므로 assert로 권한·입력 검사를 하면 운영 환경에서 검사가 사라진다 (ERR-03).
  - Cython `boundscheck=False`·`wraparound=False`: 경계 검사 해제 → 입력 검증 필요 (INP-16).
  - TLS 검증 해제 환경변수: `PYTHONHTTPSVERIFY=0`, `CURL_CA_BUNDLE=""`, `REQUESTS_CA_BUNDLE=""` (SEC-11).
  - 배포 설정 기본값: `DEBUG=True`, `ALLOWED_HOSTS=['*']`, `SESSION_COOKIE_SECURE=False` 등 (ENC-02, SEC-05).
- 탐지

```bash
rg -n -e '["\x27]-O{1,2}["\x27]' -e 'python3?\s+-O' -e 'PYTHONOPTIMIZE' -e 'boundscheck\s*[=(]\s*False' -e 'wraparound\s*[=(]\s*False' \
   -e 'PYTHONHTTPSVERIFY\s*=?\s*["\x27]?0' -e '(CURL_CA_BUNDLE|REQUESTS_CA_BUNDLE)\s*=\s*["\x27]{2}' \
   "${DF[@]}" -g '*.py' -g '*.pyx' -g '*.sh' -g '*.toml' -g '*.cfg' -g '*.ini' -g '*.env*' -g 'docker-compose*.y*ml' --hidden
```

### SCP-17. 지속 점검과 자동 갱신 [CI] — 심각도 낮음~중간

- 근거: 표24 #10·#23·#27·#29, SSDF RV.1, A11 관리 요령 ❺.
- 탐지

```bash
rg --files --hidden -g .github/dependabot.yml -g .github/dependabot.yaml -g renovate.json -g renovate.json5 -g .renovaterc -g .github/renovate.json
rg -n --hidden "${WF[@]}" -e 'schedule:' -e 'cron:'
```

- 판정: 의존성 자동 갱신 설정(pip/uv/poetry 생태계 + github-actions 생태계 모두)과 정기 SCA 실행이 있으면 충족. 하나만 있으면 부분충족. 자동 갱신 PR을 검토 없이 자동 병합하면 SCP-04 위험이 생기므로 병합 조건을 확인.

### SCP-18. 보안 정책·요구사항 문서 [문서] — 심각도 낮음

- 근거: 표24 #1·#5·#20·#24·#28·#29, 표8 '안전한 제품 기준 및 관리', SSDF PO.1·PO.2·PO.4, Quad 원칙(VDP), 로드맵의 CVD·EoS 공지 (→ `supply-chain-roadmap.md` RM-07·RM-08).
- 탐지

```bash
rg --files --hidden -g SECURITY.md -g .github/SECURITY.md -g docs/SECURITY.md -g 'docs/*security*' -g 'docs/*threat*' -g '.github/ISSUE_TEMPLATE/*'
rg -n -i -e 'security|보안|취약점|vulnerab' -g 'README*' | head
```

- 판정: SECURITY.md에 ① 취약점 신고 방법·연락처 ② 지원 버전·지원 기간 ③ 처리 기한·심각도 기준이 있으면 충족. 보안 요구사항(데이터 보호 수준·암호화·인증·인가·접근통제) 문서는 SC-05 근거로 쓴다.

### SCP-19. 벤더링·바이너리·미신고 구성요소 [코드] — 심각도 중간

- 근거: A11 '개발자가 인지하지 못한 공개 SW 컴포넌트', 컴포넌트 관리 요령 ❷❸, 표8 '타사 바이너리의 보안취약점 점검', 표24 #25·#26, 공격 유형 2.
- 탐지

```bash
rg --files --hidden -g '!.git' -g '*.whl' -g '*.so' -g '*.pyd' -g '*.dll' -g '*.dylib' -g '*.exe' -g '*.jar' -g '*.egg' \
   -g '*.min.js' -g '**/vendor/**' -g '**/vendored/**' -g '**/third_party/**' -g '**/_vendor/**' -g '**/site-packages/**' -g '**/node_modules/**'
rg -n -i -e 'copied from|vendored|originally from|forked from|출처:' --type py | head -50   # 복사해 넣은 코드 단서
```

- 판정: 벤더링 코드·바이너리가 SBOM과 라이선스 고지에 없으면 미충족(SBOM 누락). 출처·버전을 알 수 없는 바이너리는 높음 후보로 `의심`. 복사한 코드 조각은 원 프로젝트 라이선스와 취약점 이력을 확인.

### SCP-20. 개발환경 보안 [조직 + 일부 코드] — 심각도: 조직 판정

- 근거: 표21 개발환경 보안 16개 항목(빌드 환경 공격 표면·위협 모델링, 접근제어, 인터넷 차단), 표23(외부 단말에서 빌드, 무검사 USB), 표24 #4.
- 저장소에서 볼 수 있는 것: devcontainer·Dockerfile의 기반 이미지(SCP-13), CI 러너 종류(SCP-10), 빌드 스크립트의 외부 네트워크 접근.
- 나머지(단말 백신·OS 업데이트, 빌드 서버 망분리, USB 통제)는 `확인 필요(조직)`.

## B3. SBOM 필드 점검 스크립트 (CycloneDX JSON)

NTIA 7개 필드 + NIS-SBOM 20개 중 CycloneDX로 표현 가능한 항목과 중복(표18 사례)을 확인한다. 스킬의 `scripts/sbom_check.py`로 점검한다. SPDX는 `spdx-tools`의 검증기(`pyspdxtools -i sbom.spdx.json`)로 형식을 확인하고 같은 항목을 수동 대조한다.

```bash
python3 -I .claude/skills/kisa-secure-coding-python/scripts/sbom_check.py security-reports/sbom.cdx.json
```

스크립트 본문은 `scripts/sbom_check.py`에만 둔다. 출력은 `## 문서 수준`(SBOM 표준·일련번호·생성 시각·작성자·도구·제품명·버전·유형), `## 컴포넌트 수준`(중복, 공급자·버전·PURL/CPE·해시·SHA-256 이상 해시·라이선스·종속성 누락 수), `## 취약점`(CVSS 7.0 이상 표시) 세 부분이다.

해석 메모

- `cyclonedx-py requirements`로 만든 SBOM은 설치 전 정보라 해시·공급자·라이선스가 비는 경우가 많다. `cyclonedx-py environment`(설치 환경 기준)나 syft 결과와 비교한다 (A11 교차 검증).
- PyPI 패키지는 PURL(`pkg:pypi/name@version`)이 고유 식별자 역할을 한다.
- NIS-SBOM의 SBOM ID(⑤, `기업명-생성년월일-일련번호6자리`), Component Alias(⑨), Component Path(⑬)는 CycloneDX 기본 출력에 없다. 공공 납품 대상이면 `properties`나 `evidence.occurrences[].location`(1.5+)에 추가하도록 권고한다.
- 공급자(Supplier)가 비는 것은 도구 한계인 경우가 많다 → `누락`으로 적되 심각도는 낮음.

## B4. 보고서에 추가할 섹션

전체 점검이거나 사용자가 공급망 점검을 요청하면 기존 보고 형식에 다음을 덧붙인다.

```markdown
## 공급망 보안 점검 (SW 공급망 보안 가이드라인 v1.0, 2024.05)
- 점검 기준일: YYYY-MM-DD   - 사용 도구: pip-audit x.y / cyclonedx-py x.y / 수동
- 의존성: 직접 n개, 잠금 파일 <있음/없음>, 해시 <전체/일부/없음>, 인덱스 <단일/혼합>

### 취약 의존성 (SCP-06)
| 패키지 | 설치 버전 | 취약점 | CVSS | KEV | 고정 버전 | 사용 경로 |
|---|---|---|---|---|---|---|

### SCP 판정
| ID | 항목 | 판정 | 근거(파일:행) |
|---|---|---|---|
| SCP-01 | 버전 고정·잠금 파일 | 미충족 | requirements.txt:6 `requests>=2.0` |

### 자가점검 체크리스트 (표24)
| SC | 단계 | 판정 | 근거 |
|---|---|---|---|
| SC-11 | 개발 | 부분충족 | ci.yml에 bandit만 있음, SCA·비밀 스캔 없음 |
| SC-21 | 도입·운영 | 확인 필요(조직) | 계약 문서는 저장소 밖 |

### SBOM 필드 점검 (NTIA 7 / NIS-SBOM 20)
<B3 스크립트 출력 요약>
```

## B5. 구현 49개 항목과의 연결

| 공급망 항목 | 구현 항목 | 관계 |
|---|---|---|
| SCP-02, SCP-15 | SEC-15 무결성 검사 없는 코드 다운로드 | 같은 원리 (다운로드 대상이 패키지·업데이트·플러그인) |
| SCP-06, SCP-07, SCP-08 | API-02 취약한 API 사용 (Python 가이드 2023: 외부 패키지 관리·SBOM) | API-02는 코드 관점, SCP는 저장소·CI 관점 |
| SCP-10 | INP-05 명령 삽입 | CI `run:`에 이벤트 값 삽입은 셸 명령 삽입 |
| SCP-13, SCP-14 | SEC-06 하드코드된 중요정보, SEC-13 주석 속 중요정보 | 이미지 레이어·저장소 이력의 비밀 |
| SCP-15 | COD-05 역직렬화, INP-02 코드 삽입 | 내려받은 모델·플러그인 로드 |
| SCP-16 | ERR-03(assert), ENC-02(디버그), SEC-11(인증서 검증), INP-16(경계 검사) | 인터프리터·빌드 옵션 |
| SC-05, SCP-18 | 설계 SR 20개 (`design-SR.md`) | 보안 요구사항 문서화 |
