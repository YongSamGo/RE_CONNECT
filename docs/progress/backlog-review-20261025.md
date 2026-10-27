# PR·이슈 정리 검토안 (2026-10-25)

이 문서는 로컬 검토 결과다. PR·이슈 종료·본문 수정·새 push는 아직 실행하지 않았다.

기준: PR #228 head `f7cdf96d1d31184e74250e2085b35b164ef04830`, CI 40113788700·CodeQL 40113788701 성공. 원격 상태는 조회 시점 스냅샷이다.

## PR 처리안

| 분류 | 번호/수 | 제안 |
| --- | --- | --- |
| 통합본에 보존된 본인 개발 PR | #209, #208, #207, #206, #205, #204, #203, #202, #201, #200, #199, #198, #197, #196, #195, #194, #193, #192, #191, #190, #189, #188, #187, #186, #185, #184, #183, #182, #181, #180, #179, #178, #177, #176, #175, #174, #173, #172, #171, #170, #169, #168, #167, #166, #165, #164, #163, #161, #160, #154, #153, #152, #151, #150, #149, #148, #147, #146, #145, #144, #143, #142, #141 (63개) | 승인 후 #228로 검토 경로를 연결하고 종료. 원본 브랜치·이슈 유지 |
| 정상 업그레이드 후보 | #215·#216·#218·#219·#220·#222·#226 | 로컬 수정·검증 후 승인받아 해당 PR 갱신. 원격 CI는 갱신 후 별도 확인 |
| 중복 보안 업그레이드 | #225·#227 | #224·#228에 포함된 범위와 대조 후 종료 제안 |
| 지원 범위 밖 메이저 업그레이드 | #217·#221 | Node 24 타입·TypeScript 5 정책 유지. 보류 또는 종료 결정 필요 |
| 다른 작성자의 작업 | #155·#156·#158·#211·#213·#214·#224 | 내용·검수 조건 유지. #158·#211·#213·#214는 별도 로컬 브랜치에서 최신 기반 통합·백엔드 시험 통과, #213 역할 사전 검사 통과. 원격 수정은 승인 대기 |
| 별도 목적 | #140·#159·#228 | 릴리스(사람), 아카이브 보존, 통합 검토로 유지 |

63개 및 중복 2개를 닫으면 84→19개, 지원 범위 밖 2개도 닫으면 17개다. 병합이나 브랜치 삭제는 포함하지 않는다.

## 이슈 정합성

- 열린 이슈 104개, 계획 작업 106개(계획 이슈 종료 5개). 종료 상태만으로 인수 통과를 판정하지 않는다.
- #6과 #157은 상위·하위 작업이다. #157 제목을 W01-03.a로 구분하고 상위 계획 결정 후 콘솔 작업을 실행하도록 선행 조건을 명확히 하는 본문 수정안을 준비했다.
- 명시된 선행 그래프에서 순환·없는 이슈 참조는 없다. #5·#12는 선행 #4가 열린 채 종료되어 있어 증거 확인이 필요하다. 임의로 재개하지 않는다.
- #210의 담당 변경 요청은 협의 자료로 취급한다. 담당자 변경·멘션·리뷰 요청은 수행하지 않는다.
- #125는 팀 공용 권한 정책과 새 세션 검증, CODEOWNERS 판단이 남아 있다. PR #156 존재만으로 완료 처리하지 않는다.

## 역할별 남은 일

| 역할 | 계획 작업 | 단계 추정 | 우선 남은 확인 |
| --- | --- | --- | --- |
| A 기획·프론트엔드 | 23 | 약 51% | 운영 주체·문의처·보관/삭제 정책, 동의 확정, 실제 기기·접근성·사용자 검증 |
| B AI·데이터 | 23 | 약 62% | 실제 승인 공고 20건(현재 확인 0/20), 한국어 품질·추천 평가, 실제 GPU·음성 실측 |
| C 백엔드·보안 | 60 | 약 61% | AWS/GPU·도메인 준비, 카카오 정상 로그인, 관리자 API/MFA, 배포·복구·동시성 운영 검증 |

추정은 2026-10-24의 0/25/50/75/100 단계 검토 기준이며 ±10%p다. 시간 소모율·테스트 통과율·운영 완성도가 아니다.

## 통합 PR과 기존 이슈의 연결

아래는 명시된 PR 제목/종료 참조의 연결이다. 구현의 인수 완료나 이슈 종료를 뜻하지 않는다. 일반 본문 언급은 자동 연결하지 않았다.

| 이슈 | 기존 PR(코드 보존 확인) | 통합 검토 |
| --- | --- | --- |
| [#11](https://github.com/YongSamGo/RE_CONNECT/issues/11) | #161, #163 | [#228](https://github.com/YongSamGo/RE_CONNECT/pull/228), 인수 조건 별도 확인 |
| [#16](https://github.com/YongSamGo/RE_CONNECT/issues/16) | #145 | [#228](https://github.com/YongSamGo/RE_CONNECT/pull/228), 인수 조건 별도 확인 |
| [#17](https://github.com/YongSamGo/RE_CONNECT/issues/17) | #146 | [#228](https://github.com/YongSamGo/RE_CONNECT/pull/228), 인수 조건 별도 확인 |
| [#18](https://github.com/YongSamGo/RE_CONNECT/issues/18) | #147 | [#228](https://github.com/YongSamGo/RE_CONNECT/pull/228), 인수 조건 별도 확인 |
| [#20](https://github.com/YongSamGo/RE_CONNECT/issues/20) | #149 | [#228](https://github.com/YongSamGo/RE_CONNECT/pull/228), 인수 조건 별도 확인 |
| [#21](https://github.com/YongSamGo/RE_CONNECT/issues/21) | #164 | [#228](https://github.com/YongSamGo/RE_CONNECT/pull/228), 인수 조건 별도 확인 |
| [#22](https://github.com/YongSamGo/RE_CONNECT/issues/22) | #150 | [#228](https://github.com/YongSamGo/RE_CONNECT/pull/228), 인수 조건 별도 확인 |
| [#23](https://github.com/YongSamGo/RE_CONNECT/issues/23) | #152 | [#228](https://github.com/YongSamGo/RE_CONNECT/pull/228), 인수 조건 별도 확인 |
| [#24](https://github.com/YongSamGo/RE_CONNECT/issues/24) | #151 | [#228](https://github.com/YongSamGo/RE_CONNECT/pull/228), 인수 조건 별도 확인 |
| [#25](https://github.com/YongSamGo/RE_CONNECT/issues/25) | #148 | [#228](https://github.com/YongSamGo/RE_CONNECT/pull/228), 인수 조건 별도 확인 |
| [#26](https://github.com/YongSamGo/RE_CONNECT/issues/26) | #143 | [#228](https://github.com/YongSamGo/RE_CONNECT/pull/228), 인수 조건 별도 확인 |
| [#27](https://github.com/YongSamGo/RE_CONNECT/issues/27) | #165 | [#228](https://github.com/YongSamGo/RE_CONNECT/pull/228), 인수 조건 별도 확인 |
| [#28](https://github.com/YongSamGo/RE_CONNECT/issues/28) | #191, #195 | [#228](https://github.com/YongSamGo/RE_CONNECT/pull/228), 인수 조건 별도 확인 |
| [#30](https://github.com/YongSamGo/RE_CONNECT/issues/30) | #166 | [#228](https://github.com/YongSamGo/RE_CONNECT/pull/228), 인수 조건 별도 확인 |
| [#31](https://github.com/YongSamGo/RE_CONNECT/issues/31) | #192 | [#228](https://github.com/YongSamGo/RE_CONNECT/pull/228), 인수 조건 별도 확인 |
| [#32](https://github.com/YongSamGo/RE_CONNECT/issues/32) | #189, #193 | [#228](https://github.com/YongSamGo/RE_CONNECT/pull/228), 인수 조건 별도 확인 |
| [#33](https://github.com/YongSamGo/RE_CONNECT/issues/33) | #186, #194 | [#228](https://github.com/YongSamGo/RE_CONNECT/pull/228), 인수 조건 별도 확인 |
| [#35](https://github.com/YongSamGo/RE_CONNECT/issues/35) | #190 | [#228](https://github.com/YongSamGo/RE_CONNECT/pull/228), 인수 조건 별도 확인 |
| [#36](https://github.com/YongSamGo/RE_CONNECT/issues/36) | #168 | [#228](https://github.com/YongSamGo/RE_CONNECT/pull/228), 인수 조건 별도 확인 |
| [#37](https://github.com/YongSamGo/RE_CONNECT/issues/37) | #179 | [#228](https://github.com/YongSamGo/RE_CONNECT/pull/228), 인수 조건 별도 확인 |
| [#38](https://github.com/YongSamGo/RE_CONNECT/issues/38) | #187 | [#228](https://github.com/YongSamGo/RE_CONNECT/pull/228), 인수 조건 별도 확인 |
| [#39](https://github.com/YongSamGo/RE_CONNECT/issues/39) | #169 | [#228](https://github.com/YongSamGo/RE_CONNECT/pull/228), 인수 조건 별도 확인 |
| [#40](https://github.com/YongSamGo/RE_CONNECT/issues/40) | #170 | [#228](https://github.com/YongSamGo/RE_CONNECT/pull/228), 인수 조건 별도 확인 |
| [#41](https://github.com/YongSamGo/RE_CONNECT/issues/41) | #176 | [#228](https://github.com/YongSamGo/RE_CONNECT/pull/228), 인수 조건 별도 확인 |
| [#42](https://github.com/YongSamGo/RE_CONNECT/issues/42) | #205 | [#228](https://github.com/YongSamGo/RE_CONNECT/pull/228), 인수 조건 별도 확인 |
| [#43](https://github.com/YongSamGo/RE_CONNECT/issues/43) | #178 | [#228](https://github.com/YongSamGo/RE_CONNECT/pull/228), 인수 조건 별도 확인 |
| [#45](https://github.com/YongSamGo/RE_CONNECT/issues/45) | #196 | [#228](https://github.com/YongSamGo/RE_CONNECT/pull/228), 인수 조건 별도 확인 |
| [#46](https://github.com/YongSamGo/RE_CONNECT/issues/46) | #197 | [#228](https://github.com/YongSamGo/RE_CONNECT/pull/228), 인수 조건 별도 확인 |
| [#47](https://github.com/YongSamGo/RE_CONNECT/issues/47) | #154 | [#228](https://github.com/YongSamGo/RE_CONNECT/pull/228), 인수 조건 별도 확인 |
| [#48](https://github.com/YongSamGo/RE_CONNECT/issues/48) | #144 | [#228](https://github.com/YongSamGo/RE_CONNECT/pull/228), 인수 조건 별도 확인 |
| [#49](https://github.com/YongSamGo/RE_CONNECT/issues/49) | #198 | [#228](https://github.com/YongSamGo/RE_CONNECT/pull/228), 인수 조건 별도 확인 |
| [#50](https://github.com/YongSamGo/RE_CONNECT/issues/50) | #153 | [#228](https://github.com/YongSamGo/RE_CONNECT/pull/228), 인수 조건 별도 확인 |
| [#58](https://github.com/YongSamGo/RE_CONNECT/issues/58) | #141 | [#228](https://github.com/YongSamGo/RE_CONNECT/pull/228), 인수 조건 별도 확인 |
| [#59](https://github.com/YongSamGo/RE_CONNECT/issues/59) | #142 | [#228](https://github.com/YongSamGo/RE_CONNECT/pull/228), 인수 조건 별도 확인 |
| [#60](https://github.com/YongSamGo/RE_CONNECT/issues/60) | #171 | [#228](https://github.com/YongSamGo/RE_CONNECT/pull/228), 인수 조건 별도 확인 |
| [#61](https://github.com/YongSamGo/RE_CONNECT/issues/61) | #172 | [#228](https://github.com/YongSamGo/RE_CONNECT/pull/228), 인수 조건 별도 확인 |
| [#62](https://github.com/YongSamGo/RE_CONNECT/issues/62) | #173 | [#228](https://github.com/YongSamGo/RE_CONNECT/pull/228), 인수 조건 별도 확인 |
| [#63](https://github.com/YongSamGo/RE_CONNECT/issues/63) | #174 | [#228](https://github.com/YongSamGo/RE_CONNECT/pull/228), 인수 조건 별도 확인 |
| [#64](https://github.com/YongSamGo/RE_CONNECT/issues/64) | #175 | [#228](https://github.com/YongSamGo/RE_CONNECT/pull/228), 인수 조건 별도 확인 |
| [#66](https://github.com/YongSamGo/RE_CONNECT/issues/66) | #167 | [#228](https://github.com/YongSamGo/RE_CONNECT/pull/228), 인수 조건 별도 확인 |
| [#67](https://github.com/YongSamGo/RE_CONNECT/issues/67) | #182 | [#228](https://github.com/YongSamGo/RE_CONNECT/pull/228), 인수 조건 별도 확인 |
| [#68](https://github.com/YongSamGo/RE_CONNECT/issues/68) | #183 | [#228](https://github.com/YongSamGo/RE_CONNECT/pull/228), 인수 조건 별도 확인 |
| [#69](https://github.com/YongSamGo/RE_CONNECT/issues/69) | #184 | [#228](https://github.com/YongSamGo/RE_CONNECT/pull/228), 인수 조건 별도 확인 |
| [#73](https://github.com/YongSamGo/RE_CONNECT/issues/73) | #201 | [#228](https://github.com/YongSamGo/RE_CONNECT/pull/228), 인수 조건 별도 확인 |
| [#74](https://github.com/YongSamGo/RE_CONNECT/issues/74) | #202 | [#228](https://github.com/YongSamGo/RE_CONNECT/pull/228), 인수 조건 별도 확인 |
| [#75](https://github.com/YongSamGo/RE_CONNECT/issues/75) | #203 | [#228](https://github.com/YongSamGo/RE_CONNECT/pull/228), 인수 조건 별도 확인 |
| [#76](https://github.com/YongSamGo/RE_CONNECT/issues/76) | #204 | [#228](https://github.com/YongSamGo/RE_CONNECT/pull/228), 인수 조건 별도 확인 |
| [#77](https://github.com/YongSamGo/RE_CONNECT/issues/77) | #206 | [#228](https://github.com/YongSamGo/RE_CONNECT/pull/228), 인수 조건 별도 확인 |
| [#78](https://github.com/YongSamGo/RE_CONNECT/issues/78) | #207 | [#228](https://github.com/YongSamGo/RE_CONNECT/pull/228), 인수 조건 별도 확인 |
| [#79](https://github.com/YongSamGo/RE_CONNECT/issues/79) | #208 | [#228](https://github.com/YongSamGo/RE_CONNECT/pull/228), 인수 조건 별도 확인 |
| [#82](https://github.com/YongSamGo/RE_CONNECT/issues/82) | #180 | [#228](https://github.com/YongSamGo/RE_CONNECT/pull/228), 인수 조건 별도 확인 |
| [#83](https://github.com/YongSamGo/RE_CONNECT/issues/83) | #188 | [#228](https://github.com/YongSamGo/RE_CONNECT/pull/228), 인수 조건 별도 확인 |
| [#84](https://github.com/YongSamGo/RE_CONNECT/issues/84) | #177 | [#228](https://github.com/YongSamGo/RE_CONNECT/pull/228), 인수 조건 별도 확인 |
| [#85](https://github.com/YongSamGo/RE_CONNECT/issues/85) | #181 | [#228](https://github.com/YongSamGo/RE_CONNECT/pull/228), 인수 조건 별도 확인 |
| [#86](https://github.com/YongSamGo/RE_CONNECT/issues/86) | #185 | [#228](https://github.com/YongSamGo/RE_CONNECT/pull/228), 인수 조건 별도 확인 |
| [#87](https://github.com/YongSamGo/RE_CONNECT/issues/87) | #209 | [#228](https://github.com/YongSamGo/RE_CONNECT/pull/228), 인수 조건 별도 확인 |

## 미검증 조건

실제 동의는 운영 정보 미정으로 비활성 상태를 유지한다. 실제 카카오 정상 로그인, 승인 공고 20건, EC2/GPU 품질·부하, 실기기 접근성, 운영 백업·복구는 아직 통과로 기록하지 않는다.
