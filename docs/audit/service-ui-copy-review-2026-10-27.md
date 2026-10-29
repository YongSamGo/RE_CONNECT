# 화면 문구 검토 기록

모드: AI 티 제거와 해요체 정리. UI의 배치 변경과 예시 추가는 제품 디자인 작업으로 구분한다. URL과 식별자, API와 저장 조건은 보존한다.

규칙: N-2/N-5 구체 행동, J-1 장식, E-3 불필요한 쉼표, ST-1/ST-7 쉬운 해요체. 아래 표는 정보량 축소 요청 이전의 1차 편집 이력이다. 문장별로 원문과 대조했으며 이후 최종 구조와 문구는 frontend/UI_QUALITY.md 및 실제 소스가 기준이다.

| 파일 | 원문 | 수정 |
|---|---|---|
| App.tsx | 운영 서비스에서는 AWS EC2 안의 자체 AI 모델이 대화·음성 인식·읽어주기를 처리할 예정입니다. 사용자 기기 안에서만 처리되는 방식은 아닙니다. | 운영 서비스에서는 AWS EC2 안의 자체 AI 모델로 대화와 음성 인식, 읽어주기를 처리할 예정이에요. 사용자 기기 안에서만 처리되는 방식은 아니에요. |
| App.tsx | AI가 만든 초안은 직접 고치고 확정합니다. 회원 저장은 별도의 로그인과 저장 동의 후에만 진행합니다. | AI가 만든 초안은 직접 고치고 확정해요. 회원 자료로 저장하려면 별도로 로그인하고 저장에 동의해야 해요. |
| App.tsx | 개인 체험의 AI 처리·서버 보관·회원 저장은 연결되지 않았습니다. 아래에서 입력한 내용은 이 화면의 메모리에서만 사용하며 새로고침하거나 종료하면 사라집니다. 실제 개인정보는 입력하지 마세요. | 현재 미리보기에는 개인 체험의 AI 처리와 서버 보관, 회원 저장이 연결되지 않았어요. 입력한 내용은 이 화면의 메모리에서만 사용해요. 새로고침하거나 종료하면 사라져요. 실제 개인정보는 입력하지 마세요. |
| App.tsx | 안내문 초안 · 운영 주체, 문의처, AWS 리전과 실제 보관·삭제 안내는 확인 후 확정해야 합니다. 이 선택은 운영 서비스의 처리 동의로 기록되지 않습니다. | 안내문 초안이에요. 운영 주체와 문의처, AWS 리전, 실제 보관 및 삭제 안내는 확인 후 확정해야 해요. 아래 선택은 운영 서비스의 처리 동의로 기록되지 않아요. |
| App.tsx | 안내를 확인했고, 가상의 경험으로 화면을 살펴볼게요. | 안내를 확인했어요. 가상의 경험으로 화면을 살펴볼게요. |
| App.tsx | 현재는 직접 적은 경험만 확인할 수 있습니다. 다음 질문과 프로필 추출은 서버 연결 후 제공됩니다. | 지금은 직접 적은 경험만 확인할 수 있어요. 다음 질문과 AI의 경험 정리 기능은 서버 연결 후 제공할 예정이에요. |
| features/profile/ProfilePreview.tsx | 02 · 프로필 확인 미리보기 | 작성 내용 확인 |
| features/profile/ProfilePreview.tsx | 직접 적은 경험과 희망 조건을 확인해 주세요. 아직 서버에서 확정된 프로필은 아닙니다. | 직접 적은 경험을 다시 읽고 희망 활동 조건을 골라 주세요. 이 미리보기는 서버에서 프로필을 확정하거나 저장하지 않아요. |
| features/profile/ProfilePreview.tsx | 거주 자격을 판정하는 주소가 아닌, 활동하고 싶은 지역입니다. 시·도 전체 또는 시·군·구를 합계 10곳까지 고를 수 있어요. | 활동하고 싶은 지역을 합계 10곳까지 골라 주세요. 시도 전체나 시군구를 선택할 수 있어요. 이 선택으로 거주 자격을 판정하지 않아요. |
| features/profile/ProfilePreview.tsx | 목록 조회에는 로그인·AI 처리 동의가 필요하지 않아요. 실패해도 기존 지역을 유지하며, 시·도 전체로 임의 변경하지 않아요. | 지역 목록은 로그인이나 AI 처리 동의 없이 불러올 수 있어요. 조회에 실패해도 기존 선택을 유지해요. 시도 전체로 임의 변경하지 않아요. |
| features/profile/ProfilePreview.tsx | 경험과 희망 조건을 확인했습니다. 화면 미리보기에서만 유지하며 서버 확정·회원 저장은 진행하지 않았습니다. | 경험과 희망 조건을 확인했어요. 이번 미리보기 안에서만 유지돼요. 서버에서 확정하거나 회원 자료로 저장하지 않았어요. |
| features/profile/ProfilePreview.tsx | 서버에서 확정한 경험에 근거해 역할 후보와 추천을 제공할 예정입니다. 이 미리보기 선택만으로 역할·자격·추천 결과를 만들지 않습니다. | 역할 후보와 추천은 서버에서 확정한 경험을 바탕으로 제공할 예정이에요. 이 미리보기의 선택으로 역할이나 자격을 판단하거나 추천 결과를 만들지 않아요. |
| features/profile/ProfilePreview.tsx | 공개 공고 화면 살펴보기 → | 공개 공고 살펴보기 |
| features/profile/ProfilePreview.tsx | 시·군·구 목록 새로 불러오기 | 시군구 목록 새로 불러오기 |
| features/profile/ProfilePreview.tsx | 시·군·구 목록 불러오기 | 시군구 목록 불러오기 |
| features/profile/ProfilePreview.tsx | 시·군·구 목록을 불러와 선택한 지역을 대조해 주세요. 목록에 없는 선택은 직접 변경하거나 제거해 주세요. | 시군구 목록을 불러와 선택한 지역을 확인해 주세요. 목록에 없는 선택은 직접 변경하거나 제거해 주세요. |
| features/profile/ProfilePreview.tsx | 취업·공공일자리 | 취업 및 공공일자리 |
| features/public-opportunities/PublicOpportunities.tsx | 로그인 없이 · 공개 공고 탐색 | 로그인 없이 공고 탐색 |
| features/public-opportunities/PublicOpportunities.tsx | 나의 다음 기회를 찾아봐요 | 일자리와 봉사 공고를 찾아보세요 |
| features/public-opportunities/PublicOpportunities.tsx | 취업·공공일자리와 봉사 공고를 찾아보세요. 검색에는 AI 처리 동의나 프로필이 필요하지 않습니다. | 지역과 활동 유형을 골라 공고를 검색해 보세요. AI 처리 동의나 프로필 없이 이용할 수 있어요. |
| features/public-opportunities/PublicOpportunities.tsx | '취업·일자리' | '일자리' |
| features/public-opportunities/PublicOpportunities.tsx | ' · 원격 활동 가능' | ' / 원격 활동 가능' |
| features/public-opportunities/PublicOpportunities.tsx | ' · 시·군·구는 상세에서 확인' | ' / 시군구는 상세에서 확인' |
| features/public-opportunities/PublicOpportunities.tsx | 공고 상세 화면으로 → | 공고 상세 보기 |
| features/public-opportunities/PublicOpportunities.tsx | 상세에서 최신 모집 상태와 원문 조건을 확인하세요. 지원 자격과 신청 완료를 뜻하지 않습니다. | 상세 화면에서 최신 모집 상태와 원문 조건을 확인해 주세요. 공고가 표시돼도 지원 자격을 충족하거나 신청이 완료된 것은 아니에요. |
| features/public-opportunities/PublicOpportunities.tsx | }건 · {state.result.page}페이지 | }건 / {state.result.page}페이지 |
| features/public-opportunities/PublicOpportunities.tsx | 필터를 직접 바꿔 다시 검색해 보세요. 검색 조건을 자동으로 넓히지 않았습니다. | 검색어나 지역, 활동 유형을 바꿔 다시 검색해 보세요. 선택한 조건을 자동으로 넓히지는 않아요. |
| features/public-opportunities/PublicOpportunities.tsx | 가상 경험으로 화면 미리보기 → | 가상 경험으로 화면 미리보기 |
| features/public-opportunities/PublicOpportunities.tsx | 조회·검수 정책의 실제 동작은 백엔드 연결 후 확인해야 합니다. | 개발 중인 화면이에요. 실제 공고 조회와 검수 정책은 서버 연결 후 확인해야 해요. |
| features/public-opportunities/PublicOpportunities.tsx |  · 목록 대조 필요 |  (목록 확인 필요) |
| features/public-opportunities/PublicOpportunities.tsx | 시·군·구 목록 새로 불러오기 | 시군구 목록 새로 불러오기 |
| features/public-opportunities/PublicOpportunities.tsx | 시·군·구 목록 불러오기 | 시군구 목록 불러오기 |
| features/public-opportunities/PublicOpportunities.tsx | 시·군·구 목록을 다시 불러와 선택을 확인하거나, 활동 범위를 직접 변경해 주세요. | 시군구 목록을 다시 불러와 선택을 확인하거나 활동 범위를 직접 변경해 주세요. |
| features/public-opportunities/PublicOpportunities.tsx | 시·도를 바꾸면 | 시도를 바꾸면 |
| features/public-opportunities/PublicOpportunities.tsx | 시·도를 먼저 선택하세요 | 시도를 먼저 선택해 주세요 |
| features/public-opportunities/PublicOpportunities.tsx | >시·군·구< | >시군구< |
| features/public-opportunities/PublicOpportunities.tsx | 취업·공공일자리 | 취업 및 공공일자리 |
| features/preparation/ManualPreparation.tsx | 03 · 신청 준비 미리보기 | 지원 내용 작성 연습 |
| features/preparation/ManualPreparation.tsx | 공고·프로필 연결 전의 연습 화면이에요 | 가상의 경험으로 작성하는 연습 화면이에요 |
| features/preparation/ManualPreparation.tsx | AI 생성·자격 판정·회원 저장은 연결 준비 중입니다. 실제 개인정보는 적지 마세요. 특정 공고의 지원서나 서버에서 승인한 자료로 처리하지 않습니다. | AI 생성과 자격 판정, 회원 저장은 아직 연결되지 않았어요. 실제 개인정보는 적지 마세요. 작성한 내용은 특정 공고의 지원서나 서버에서 승인한 자료로 처리하지 않아요. |
| features/preparation/ManualPreparation.tsx | 공고를 선택한 뒤 공식 원문에서 모집 상태·지원 조건·필요 서류·접수 방법을 확인해 주세요. 이 화면에서는 공고별 서류를 안내하거나 준비 완료를 판정하지 않습니다. | 공고를 선택한 뒤 공식 원문에서 모집 상태와 지원 조건, 필요 서류, 접수 방법을 확인해 주세요. 이 연습 화면은 공고별 서류를 안내하거나 준비 완료를 판정하지 않아요. |
| features/preparation/ManualPreparation.tsx | 공개 공고에서 공식 안내 확인하기 → | 공개 공고에서 공식 안내 확인하기 |
| features/preparation/ManualPreparation.tsx | 직접 해온 일과 경험을 적어 주세요. 연락처·주민등록번호·상세 병력은 적지 마세요. | 직접 해온 일과 경험을 적어 주세요. 연락처나 주민등록번호, 상세 병력은 적지 마세요. |
| features/preparation/ManualPreparation.tsx | 하고 싶은 활동과 그 이유를 적어 주세요. 확인하지 않은 경력·자격은 추가하지 마세요. | 하고 싶은 활동과 그 이유를 적어 주세요. 확인하지 않은 경력이나 자격은 추가하지 마세요. |
| features/preparation/ManualPreparation.tsx | 작성한 두 항목을 읽고, 내 경험과 맞는 내용인지 확인했어요. | 두 항목을 읽고 내 경험과 맞는지 확인했어요. |
| features/account/AuthResult.tsx | 주소의 결과 표시만으로 로그인이나 저장이 완료되지는 않습니다. | 현재 로그인 상태를 서버에서 확인해 주세요. 로그인 후에도 자료 저장은 따로 확인해야 해요. |
| features/account/AuthResult.tsx | 회원 세션이 확인되었습니다 | 로그인 상태를 확인했어요 |
| features/account/AuthResult.tsx | 로그인만으로 자료를 저장하지 않았습니다. 저장 대기 화면에서 안내문·동의·저장 대상을 직접 확인해 주세요. | 로그인만으로 자료를 저장하지는 않았어요. 저장 대기 화면에서 안내문과 동의 내용, 저장 대상을 직접 확인해 주세요. |
| features/account/AuthResult.tsx | 운영 주체·문의처·보관 및 삭제 정책을 확정 게시하기 전에는 새 로그인·동의를 제공하지 않습니다. | 운영 주체와 문의처, 보관 및 삭제 정책이 확정 게시되기 전에는 새 로그인과 동의를 제공하지 않아요. |
| features/account/PendingSave.tsx | 로그인과 자료 저장은 별개입니다. 저장 버튼을 누르기 전에는 저장하지 않습니다. | 로그인 후에도 저장 대상을 확인해야 해요. 저장 버튼을 누르기 전에는 자료를 저장하지 않아요. |
| features/account/PendingSave.tsx | 서버가 게시한 현재 안내문을 읽고 동의해야 저장할 수 있습니다. 안내문이 미정이면 동의·저장을 제공하지 않습니다. | 서버가 게시한 현재 안내문을 읽고 동의해야 저장할 수 있어요. 안내문이 확정되지 않았다면 동의와 저장을 제공하지 않아요. |
| features/account/PendingSave.tsx | 프로필에 연결해 지원서 저장 · 실패 시 재확인 | 프로필에 연결해 지원서 저장 |

| public-opportunities/PublicOpportunityDetail.tsx | {label} · {link.host} (새 창) | {label} ({link.host}, 새 창) |
| public-opportunities/PublicOpportunityDetail.tsx | '취업·공공일자리' : '봉사'} · 공고 버전 | '취업 및 공공일자리' : '봉사'} / 공고 버전 |
| public-opportunities/PublicOpportunityDetail.tsx | 중요 변경을 검수하고 있습니다. 확인이 끝나기 전에는 이 공고로 추천·지원서를 만들 수 없습니다. | 중요한 변경 사항을 확인하고 있어요. 확인이 끝나기 전에는 이 공고를 추천하거나 지원서를 만들 수 없어요. |
| public-opportunities/PublicOpportunityDetail.tsx | '지역 확인 필요'} · {item.location_text | '지역 확인 필요'} / {item.location_text |
| public-opportunities/PublicOpportunityDetail.tsx | ` · 주 ${item.hours_per_week}시간` | ` / 주 ${item.hours_per_week}시간` |
| public-opportunities/PublicOpportunityDetail.tsx | '무보수'} · {item.compensation_text | '무보수'} / {item.compensation_text |
| public-opportunities/PublicOpportunityDetail.tsx |  · 조건 해석 확인 필요 |  (조건 해석 확인 필요) |
| public-opportunities/PublicOpportunityDetail.tsx | 신청 방법 · {methods[item.application_method]} | 신청 방법: {methods[item.application_method]} |
| public-opportunities/PublicOpportunityDetail.tsx | 원문 확인: {checkedTime(item.source_checked_at)} · 검수: | 원문 확인: {checkedTime(item.source_checked_at)} / 검수: |
| public-opportunities/PublicOpportunityDetail.tsx | 공식 서류·접수 준비 안내 보기 | 공식 서류와 접수 안내 보기 |
| public-opportunities/PublicOpportunityDetail.tsx | 로그인·AI 동의 없이 조회합니다. 현재 서버는 연결 검증 전이며 응답이 없으면 오류를 안내합니다. | 로그인이나 AI 처리 동의 없이 조회할 수 있어요. 현재 서버 연결은 검증 전이에요. 응답을 받지 못하면 오류를 안내해요. |
| public-opportunities/PublicOpportunityDetail.tsx | 로그인 없이 · 공개 공고 상세 | 공개 공고 상세 |
| public-opportunities/PublicOpportunityDetail.tsx | 공고의 조건을 함께 확인해요 | 공고의 조건을 확인해 주세요 |
| public-opportunities/PublicOpportunityDetail.tsx | 모집 상태·원문 조건·신청 방법을 살펴보세요. | 모집 상태와 원문 조건, 신청 방법을 살펴보세요. |
| preparation/OfficialPreparation.tsx | {label} · {link.host} (새 창) | {label} ({link.host}, 새 창) |
| preparation/OfficialPreparation.tsx | {item.opportunity.version} · 접수 방법: | {item.opportunity.version} / 접수 방법: |
| preparation/OfficialPreparation.tsx | ` · ${new Date(item.deadline_at) | ` / ${new Date(item.deadline_at) |
| preparation/OfficialPreparation.tsx | 체크는 나의 준비 메모예요. 서류 제출·자격 충족·신청 완료를 뜻하지 않아요. 이 화면을 나가거나 새로 조회·새로고침·종료하면 지워져요. | 체크는 나의 준비 메모예요. 체크해도 서류 제출이나 자격 충족, 신청 완료를 뜻하지는 않아요. 이 화면을 나가거나 새로 조회할 때, 새로고침하거나 종료할 때 지워져요. |
| preparation/OfficialPreparation.tsx | 새 창으로 이동해도 신청 완료로 기록하지 않으며, 서류·개인정보를 대신 제출하지 않습니다. | 새 창으로 이동해도 신청 완료로 기록하지 않아요. 서류나 개인정보를 대신 제출하지 않아요. |
| preparation/OfficialPreparation.tsx | 로그인·AI 동의 없이 공개 안내를 조회합니다. 서버 응답이 없으면 오류를 안내하며 서류나 절차를 만들어 채우지 않습니다. | 로그인이나 AI 처리 동의 없이 공개 안내를 조회할 수 있어요. 서버 응답을 받지 못하면 오류를 안내해요. 서류나 절차를 임의로 만들어 보여주지는 않아요. |
| preparation/OfficialPreparation.tsx | 공고에 명시된 정보로 준비해요 | 공식 신청 준비 |
| preparation/OfficialPreparation.tsx | 신청 준비를 차근차근 | 필요한 서류와 접수 방법을 확인해요 |
| preparation/OfficialPreparation.tsx | 공식 서류·절차·접수 방법을 확인해 주세요. | 공고에 명시된 서류와 절차, 접수 방법을 확인해 주세요. |
| preparation/OfficialPreparation.tsx | 공고 화면으로 돌아가기 → | 공고 화면으로 돌아가기 |
| account/AccountPage.tsx | 새 로그인·동의는 서버가 확정 안내문을 게시한 경우에만 제공합니다. 아래 관리 기능은 서버가 확인한 현재 회원 세션에만 적용합니다. | 서버에 확정 안내문이 게시돼야 새 로그인과 동의를 제공해요. 아래 관리 기능은 서버에서 확인한 현재 회원에게만 적용돼요. |
| account/AccountPage.tsx | 'AI 처리'} · 안내문 | 'AI 처리'} / 안내문 |
| account/AccountPage.tsx | 삭제·철회 시 다른 기기를 포함한 기존 임시 체험과 로그인 세션을 종료합니다. | 삭제하거나 동의를 철회하면 다른 기기를 포함한 기존 임시 체험과 로그인 세션을 종료해요. |
| account/AccountPage.tsx | 진행 중인 체험과 임시 자료를 지웁니다. 이미 회원 저장한 프로필·지원서는 유지합니다. | 진행 중인 체험과 임시 자료를 지워요. 이미 회원 자료로 저장한 프로필과 지원서는 유지해요. |
| account/notices.tsx | 로그인만으로 체험 자료를 저장하지 않습니다. 회원 저장 동의와 자료 저장은 별도로 선택합니다. | 로그인만으로 체험 자료를 저장하지 않아요. 회원 저장 동의와 자료 저장은 따로 선택해요. |
| account/notices.tsx | 운영 주체·문의처·리전·보관 및 삭제 정책 확정 후 동의를 제공합니다. | 운영 주체와 문의처, 리전, 보관 및 삭제 정책이 확정된 후 동의를 제공해요. |
| account/SavedProfileSave.tsx | 재확정 프로필 저장 · 실패 시 재시도 | 재확정 프로필 저장 |
| voice/VoicePreview.tsx | 최대 90초·6MiB입니다. | 최대 90초 또는 6MiB까지 녹음할 수 있어요. |
| voice/VoicePreview.tsx | 최대 90초·6MiB이며 화면을 떠나면 녹음이 삭제됩니다. | 최대 90초 또는 6MiB까지 녹음할 수 있어요. 화면을 떠나면 녹음이 삭제돼요. |
| voice/VoicePreview.tsx | 녹음 중 · ${seconds} / 90초 | 녹음 중 ${seconds} / 90초 |
| voice/VoicePreview.tsx | 녹음·입력 취소하고 삭제 | 녹음과 입력 취소하고 삭제 |
| voice/VoicePreview.tsx | 녹음 전사 요청 · 같은 요청 재확인 | 녹음을 글로 바꾸기 |
| voice/VoicePreview.tsx | 글로 작성하는 화면으로 → | 글로 작성하는 화면으로 |
| voice/AudioRecorderControls.tsx | 녹음 중 · ${recorder.seconds} / 90초 | 녹음 중 ${recorder.seconds} / 90초 |
| voice/AudioRecorderControls.tsx | 녹음·입력 취소하고 삭제 | 녹음과 입력 취소하고 삭제 |
| public-opportunities/OpportunityReport.tsx | 일정·장소가 달라요 | 일정이나 장소가 달라요 |
| public-opportunities/OpportunityReport.tsx | 그 밖의 오류는 설명이 필요해요. 이름·연락처·주민등록번호·상세 병력은 적지 마세요. | 그 밖의 오류는 설명이 필요해요. 이름이나 연락처, 주민등록번호, 상세 병력은 적지 마세요. |

| frontend\src\features\account\AccountPage.tsx | 계정 연결·동의·저장 자료와 모든 로그인 세션·체험을 지웁니다. 복구 시 삭제 재적용에 필요한 최소 이력만 30일 남습니다. 탈퇴에는 5분 이내 카카오 재인증이 필요합니다. | 계정 연결과 동의, 저장 자료, 모든 로그인 세션과 체험을 지워요. 복구 시 삭제를 다시 적용하는 데 필요한 최소 이력만 30일 남겨요. 탈퇴하려면 5분 이내에 카카오에서 다시 인증해야 해요. |
| frontend\src\features\account\AccountPage.tsx | 시작 화면으로 → | 시작 화면으로 |
| frontend\src\features\account\BeginSave.tsx | 서버의 확정·승인 참조를 확인했습니다. | 서버에서 확정하거나 승인한 자료를 확인했어요. |
| frontend\src\features\account\BeginSave.tsx | 직접 확정·승인한 자료를 확인합니다. 로그인 후 저장 여부를 따로 선택합니다. | 직접 확정하거나 승인한 자료를 확인해요. 로그인 후 저장 여부는 따로 선택해요. |
| frontend\src\features\account\PendingSave.tsx | 응답이 없으면 실제 저장됐을 수도 있습니다. 같은 요청으로 재확인하거나 저장 자료를 조회해 주세요. 만료·충돌이면 현재 자료를 확인한 뒤 새로 시작해 주세요. | 응답을 받지 못해도 실제로는 저장됐을 수 있어요. 같은 요청으로 다시 확인하거나 저장한 자료를 조회해 주세요. 요청이 만료되거나 충돌했다면 현재 자료를 확인한 뒤 새로 시작해 주세요. |
| frontend\src\features\account\SavedDraftEditor.tsx | 재승인한 지원서 저장 · 실패 시 재시도 | 재승인한 지원서 저장 |
| frontend\src\features\account\SavedMaterials.tsx | 내 정보 · 저장 자료 | 저장한 자료 |
| frontend\src\features\account\SavedMaterials.tsx | 조회·삭제는 서버에서 현재 회원의 자료에만 적용합니다. | 조회와 삭제는 서버에서 현재 회원의 자료에만 적용돼요. |
| frontend\src\features\account\SavedMaterials.tsx | 저장 프로필로 새 체험·편집 시작 | 저장 프로필로 새 체험 시작 |
| frontend\src\features\account\SavedMaterials.tsx | {document.title} · 버전 | {document.title} / 버전 |
| frontend\src\features\account\SavedMaterials.tsx | 내용 보기 · {document.title} | 내용 보기: {document.title} |
| frontend\src\features\account\SavedMaterials.tsx | 페이지 · 전체 | 페이지 / 전체 |
| frontend\src\features\account\SavedMaterials.tsx | 내 정보로 → | 내 정보로 |
| frontend\src\features\conversation\JourneyConversation.tsx | 03 · 경험 이야기 | 경험 이야기 |
| frontend\src\features\conversation\JourneyConversation.tsx | 희망 지역·활동 유형과 다른 조건은 프로필 화면에서 직접 선택해 주세요. | 희망 지역과 활동 유형 등 다른 조건은 프로필 화면에서 직접 선택해 주세요. |
| frontend\src\features\conversation\JourneyConversation.tsx | 재확정 전 추천·자격은 이전 확정 프로필 기준입니다. | 다시 확정하기 전의 추천과 자격 대조는 이전 확정 프로필 기준이에요. |
| frontend\src\features\conversation\JourneyConversation.tsx | 연락처·주민등록번호·상세 병력은 적지 마세요. 보내기 전에 내용을 확인해 주세요. | 연락처나 주민등록번호, 상세 병력은 적지 마세요. 보내기 전에 내용을 확인해 주세요. |
| frontend\src\features\conversation\JourneyConversation.tsx | 이 체험의 대화·초안·확정본·역할 선택과 진행 결과를 삭제합니다. | 이 체험의 대화와 초안, 확정본, 역할 선택 및 진행 결과를 삭제해요. |
| frontend\src\features\preparation\JourneyDraftEditor.tsx | 번 · 공고 { | 번 / 공고 { |
| frontend\src\features\preparation\JourneyDraftEditor.tsx | 직접 작성할 임시 초안을 만들었습니다. 아직 승인·회원 저장하지 않았습니다. | 직접 작성할 임시 초안을 만들었어요. 아직 내용을 승인하거나 회원 자료로 저장하지 않았어요. |
| frontend\src\features\preparation\JourneyDraftEditor.tsx | AI 초안은 확정한 사실만 사용합니다. 지원동기는 직접 작성하고, 수정·승인·회원 저장을 따로 선택합니다. | AI 초안은 확정한 사실만 사용해요. 지원동기는 직접 작성해 주세요. 내용 수정과 승인, 회원 저장은 따로 선택해요. |
| frontend\src\features\preparation\JourneyDraftEditor.tsx | AI 초안 생성 · 같은 요청 재확인 | AI 초안 만들기 |
| frontend\src\features\preparation\JourneyDraftEditor.tsx | AI 실패 시 직접 작성을 선택할 수 있습니다. 응답 유실은 같은 생성 요청으로 재확인하고, 수정·승인 결과는 서버 편집본에서 확인해 주세요. 충돌 시 입력을 자동으로 덮어쓰지 않습니다. | AI로 만들지 못하면 직접 작성할 수 있어요. 응답을 받지 못했을 때는 같은 생성 요청으로 다시 확인해 주세요. 수정과 승인 결과는 서버 편집본에서 확인해 주세요. 충돌이 생겨도 입력을 자동으로 덮어쓰지 않아요. |
| frontend\src\features\preparation\JourneyPreparation.tsx | 08 · 체험 신청 준비 | 체험 신청 준비 |
| frontend\src\features\preparation\JourneyPreparation.tsx | 초안 반영·사용자 승인·회원 저장·외부 신청은 각각 다른 단계입니다. | 초안 반영과 내용 승인, 회원 저장, 공식 신청처에서의 신청은 따로 진행해요. |
| frontend\src\features\preparation\JourneyPreparation.tsx | </Link> · <Link | </Link> <Link |
| frontend\src\features\preparation\JourneyPreparation.tsx | 경험·희망 지역·활동 유형을 직접 확인하고 확정하면 이 공고의 지원서를 만들 수 있어요. | 경험과 희망 지역, 활동 유형을 직접 확인하고 확정하면 이 공고의 지원서를 만들 수 있어요. |
| frontend\src\features\preparation\JourneyPreparation.tsx | 번 · 공고 { | 번 / 공고 { |
| frontend\src\features\preparation\JourneyPreparation.tsx | {editor.remote.revision} · 원래 확정 프로필 | {editor.remote.revision} / 원래 확정 프로필 |
| frontend\src\features\preparation\JourneyPreparation.tsx | 직접 확인한 경험만 적고 연락처·주민등록번호·상세 병력은 적지 마세요. | 직접 확인한 경험만 적어 주세요. 연락처나 주민등록번호, 상세 병력은 적지 마세요. |
| frontend\src\features\preparation\JourneyPreparation.tsx | 내용을 복사했습니다. 저장·신청 완료는 아닙니다. | 내용을 복사했어요. 자료 저장이나 신청 접수가 완료된 것은 아니에요. |
| frontend\src\features\preparation\JourneyPreparation.tsx | 복사 전에 서버의 승인 리비전·본문·확정 프로필·공고를 다시 조회합니다. | 복사 전에 서버에서 승인한 버전과 본문, 확정 프로필, 공고를 다시 확인해요. |
| frontend\src\features\preparation\JourneyPreparation.tsx | 대화·프로필·모든 임시 지원서를 삭제합니다. | 대화와 프로필, 모든 임시 지원서를 삭제해요. |
| frontend\src\features\profile\JourneyProfile.tsx | 05 · 체험 프로필 | 체험 프로필 |
| frontend\src\features\profile\JourneyProfile.tsx | 취업·공공일자리 | 취업 및 공공일자리 |
| frontend\src\features\profile\JourneyProfile.tsx | } 시·도< | } 시도< |
| frontend\src\features\profile\JourneyProfile.tsx | } 시·군·구< | } 시군구< |
| frontend\src\features\profile\JourneyProfile.tsx | >시·도 전체< | >시도 전체< |
| frontend\src\features\profile\JourneyProfile.tsx | 시·군·구는 지역 목록을 불러온 뒤 고를 수 있어요. | 시군구는 지역 목록을 불러온 뒤 고를 수 있어요. |
| frontend\src\features\profile\JourneyProfile.tsx | 시·군·구 목록 불러오기 | 시군구 목록 불러오기 |
| frontend\src\features\profile\JourneyProfile.tsx | 프로필을 확정했습니다. 이전 추천·자격 결과는 새 확정본으로 다시 확인해 주세요. | 프로필을 확정했어요. 이전 추천과 자격 대조 결과는 새 확정본으로 다시 확인해 주세요. |
| frontend\src\features\profile\JourneyProfile.tsx | 초안 반영·프로필 확정·회원 저장은 서로 다른 단계입니다. 이 화면은 임시 체험의 프로필을 편집합니다. | 초안 반영과 프로필 확정, 회원 저장은 따로 진행해요. 여기서는 임시 체험의 프로필을 고칠 수 있어요. |
| frontend\src\features\profile\JourneyProfile.tsx | 이 체험의 초안·확정본·역할 선택과 진행 결과가 삭제됩니다. 아직 반영하지 않은 화면 입력도 사라집니다. | 이 체험의 초안과 확정본, 역할 선택 및 진행 결과가 삭제돼요. 아직 반영하지 않은 화면 입력도 사라져요. |
| frontend\src\features\profile\JourneyProfile.tsx | 수정 중입니다. 재확정 전 추천·자격 결과는 이전 확정 프로필 기준입니다. | 수정 중이에요. 다시 확정하기 전의 추천과 자격 대조 결과는 이전 확정 프로필 기준이에요. |
| frontend\src\features\recommendations\JourneyRecommendations.tsx | 06 · 내 경험과 연결된 기회 | 경험을 바탕으로 찾은 공고 |
| frontend\src\features\recommendations\JourneyRecommendations.tsx | 취업·공공일자리 | 취업 및 공공일자리 |
| frontend\src\features\recommendations\JourneyRecommendations.tsx | </Link> · <Link | </Link> <Link |
| frontend\src\features\recommendations\JourneyRecommendations.tsx | 번 · 공고 { | 번 / 공고 { |
| frontend\src\features\recommendations\JourneyRecommendations.tsx | 번 · {checkedTime | 번 / {checkedTime |
| frontend\src\features\recommendations\JourneyRecommendations.tsx | 조건 묶음 {index + 1} · | 조건 묶음 {index + 1}: |
| frontend\src\features\recommendations\JourneyRecommendations.tsx | 프로필 확인·수정·역할 제외 | 프로필 확인과 수정 |
| frontend\src\features\recommendations\JourneyRecommendations.tsx | 프로필에서 경험·희망 지역·활동 유형을 확인하고 확정할 수 있습니다. 대화를 끝낼 필요는 없습니다. | 프로필에서 경험과 희망 지역, 활동 유형을 확인하고 확정할 수 있어요. 대화를 끝낼 필요는 없어요. |
| frontend\src\features\recommendations\JourneyRecommendations.tsx | 연결 근거가 충분한 공고를 찾지 못했습니다. 경험·역량과 선택 필터를 확인하고 프로필을 다시 확정하거나 공개 공고를 살펴보세요. | 추천할 근거가 충분한 공고를 찾지 못했어요. 경험과 역량, 검색 조건을 확인해 프로필을 다시 확정하거나 공개 공고를 살펴보세요. |
| frontend\src\features\recommendations\JourneyRecommendations.tsx | {item.opportunity.organization_name} · | {item.opportunity.organization_name} / |
| frontend\src\features\recommendations\JourneyRecommendations.tsx | ' · 원격 가능' | ' / 원격 가능' |
| frontend\src\features\recommendations\JourneyRecommendations.tsx | } · {deadlineLabel | } / {deadlineLabel |
| frontend\src\features\recommendations\JourneyRecommendations.tsx | ` · 확인할 조건 ${ | ` / 확인할 조건 ${ |
| frontend\src\features\recommendations\JourneyRecommendations.tsx | 최신 상세·공식 원문·오류 신고 확인 | 공고 상세와 공식 원문 보기 |
| frontend\src\features\voice\JourneyTranscription.tsx | 녹음·전사 확인 | 녹음과 전사 확인 |
| frontend\src\features\voice\JourneyTranscription.tsx | 최대 90초·6MiB입니다. 마이크는 녹음 시작을 누를 때만 켜집니다. 연락처·주민등록번호·상세 병력은 말하지 마세요. | 녹음은 90초 이내로 해 주세요. 파일 크기는 6MiB 이하여야 해요. 마이크는 녹음 시작을 누를 때만 켜져요. 연락처나 주민등록번호, 상세 병력은 말하지 마세요. |
| frontend\src\features\voice\JourneyTranscription.tsx | 원본은 전사 성공·실패·취소 뒤 기기에서 정리합니다. | 전사가 성공하거나 실패했을 때, 취소했을 때 원본을 기기에서 정리해요. |
| frontend\src\features\voice\JourneyVoiceInput.tsx | 확인·수정할 전사 문장 | 글로 바꾼 내용 확인과 수정 |
| frontend\src\features\voice\VoicePreview.tsx | 최대 90초 또는 6MiB까지 녹음할 수 있어요. | 녹음은 90초 이내로 해 주세요. 파일 크기는 6MiB 이하여야 해요. |
