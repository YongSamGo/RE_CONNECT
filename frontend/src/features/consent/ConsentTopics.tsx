import { useEffect, useRef, useState } from 'react'
import { consentNotices } from './notice-content'

const keyPoints = [
  [
    '입력한 경험을 정리하고, 확정한 프로필을 바탕으로 공고를 찾습니다.',
    'AI가 정리한 내용은 직접 확인하고 수정할 수 있습니다. 신청은 공식 신청처에서 직접 진행합니다.',
    'AI 처리에 동의하지 않아도 공개 공고를 볼 수 있습니다. 동의는 나중에 철회할 수 있습니다.',
  ],
  [
    '경험과 업무, 희망 지역과 활동 유형을 처리합니다. 추가 활동 조건은 선택해 입력할 수 있습니다.',
    '음성은 해당 기능을 선택한 경우에만 처리합니다. 주민등록번호, 연락처, 건강 정보 등 불필요한 개인정보는 입력하지 마세요.',
    '로그인만으로 자료가 저장되지는 않습니다. 회원 저장은 별도로 동의하고 선택해야 합니다.',
  ],
  [
    '저장하지 않은 대화와 체험 자료는 시작 후 최대 2시간 보관합니다. 30분 동안 활동이 없으면 더 일찍 만료됩니다.',
    '별도로 저장한 프로필은 삭제, 저장 동의 철회, 회원 탈퇴 중 먼저 발생할 때까지 보관합니다.',
    '원본 녹음은 음성을 글로 바꾸는 동안만 처리합니다. 브라우저를 닫는 것만으로 체험 자료가 바로 삭제되지는 않습니다.',
  ],
]
const details = [
  [
    '확정한 경험과 희망 활동을 바탕으로 공고를 추천하고 조건을 비교합니다. 정보가 부족하거나 조건이 불명확하면 확인이 필요하다고 안내합니다.',
    '공고에 필요한 서류를 안내하고, 확정한 사실을 바탕으로 지원서 초안 작성을 돕습니다. 결과와 공고 원문을 확인해 주세요.',
    '다시잇다는 채용이나 선발을 결정하지 않으며 신청을 대신 제출하지 않습니다.',
    '대화 정리와 음성 기능에는 AI를 사용합니다. 입력 내용은 AI 모델의 추가 학습이나 광고에 사용하지 않습니다.',
    'AI 처리에 동의하지 않으면 AI 대화, 경험 정리, 음성 기능과 AI 문서 작성은 이용할 수 없습니다. 공개 공고는 볼 수 있습니다.',
  ],
  [
    '대화에 입력한 경험과 업무, 활동 기간, 정리한 역량, 희망 지역과 활동 유형을 처리합니다.',
    '보수 선호, 가능 요일과 시간, 거주 지역, 출생연도, 자격과 교육 이력 등은 선택하여 입력할 수 있습니다.',
    '음성 입력을 선택하면 녹음과 글로 바뀐 내용을 처리합니다. 읽어주기를 선택하면 요청한 내용과 음성을 처리합니다.',
    '이용 과정에서 프로필, 선택한 공고, 추천과 조건 비교 결과, 지원서 초안 및 동의 기록 등이 생성됩니다.',
    '카카오 로그인 시 계정 연결에 필요한 식별값을 사용합니다. 카카오 프로필, 이메일, 전화번호는 요청하지 않습니다.',
    '불필요한 개인정보는 입력하지 마세요. 자동 확인으로 모든 개인정보를 찾아내거나 삭제할 수는 없습니다.',
  ],
  [
    '체험 자료는 시작 후 최대 2시간 보관하며, 30분 동안 활동이 없으면 더 일찍 만료됩니다. 종료하고 삭제를 선택해 삭제할 수도 있습니다.',
    '로그인 후 저장을 이어가기 위한 저장 대기 자료는 최대 10분 보관합니다. 별도로 저장한 프로필은 삭제, 저장 동의 철회, 회원 탈퇴 중 먼저 발생할 때까지 보관합니다.',
    'AI 처리 동의를 철회하면 진행 중인 체험 자료를 삭제합니다. 이미 저장한 프로필은 AI 처리 동의 철회만으로 삭제되지 않습니다.',
    '저장 동의를 철회하면 저장한 프로필과 해당 프로필에서 만든 지원서를 삭제합니다. 회원 탈퇴 시 계정 연결, 동의 기록, 저장 자료와 진행 중인 체험을 삭제합니다.',
    '서비스 운영 기록은 14일, 보안과 운영을 위한 감사 기록은 30일 보관합니다. 삭제 이력은 30일, 회원 저장 자료의 백업은 최대 7일 보관합니다.',
    '직접 복사하거나 제출한 자료와 외부 신청기관이 보관하는 자료는 다시잇다에서 삭제할 수 없습니다.',
  ],
]

/** Shared presentation for preview and server-backed entry; never records consent. */
export function ConsentTopics() {
  const [selected, setSelected] = useState<number | null>(null)
  const dialogRef = useRef<HTMLDialogElement>(null)
  const notice = selected === null ? null : consentNotices[selected]
  useEffect(() => {
    if (selected !== null && dialogRef.current && !dialogRef.current.open) dialogRef.current.showModal()
  }, [selected])
  return <>
    <div className="consent-topics">{consentNotices.map((item, index) => <div className="consent-topic" key={item.title}>
      <span>{item.title}</span><button type="button" className="consent-topic-detail" aria-label={`${item.title} 자세히 보기`} onClick={() => setSelected(index)}>자세히 보기</button>
    </div>)}</div>
    <dialog ref={dialogRef} className="consent-dialog" aria-labelledby="consent-dialog-title" onClose={() => setSelected(null)}>
      {notice && <><header className="consent-dialog-header">
        <h2 id="consent-dialog-title" tabIndex={-1} autoFocus>{notice.title}</h2>
        <button type="button" className="consent-dialog-close" onClick={() => dialogRef.current?.close()}>닫기</button>
      </header><div className="consent-dialog-content" tabIndex={0} role="region" aria-label={`${notice.title} 상세 안내`}>
        <div className="consent-key-points">{keyPoints[selected!].map(point => <p key={point}>{point}</p>)}</div>
        <div className="consent-full-details" aria-label="상세 정보 처리 내용">
          {details[selected!].map(paragraph => <p key={paragraph}>{paragraph}</p>)}
        </div>
      </div></>}
    </dialog>
  </>
}
