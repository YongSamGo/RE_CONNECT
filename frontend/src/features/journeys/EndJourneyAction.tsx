import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { ApiError } from '../../api/errors'
import { useRequest } from '../../state/useRequest'
import { Button } from '../../ui/Button'
import { RequestError } from '../../ui/StatusNotice'
import { navigateDiscardingInput } from '../../ui/discardConfirmed'

/**
 * 체험 임시 자료를 서버에서 바로 삭제하는 공통 행동.
 * 204를 확인한 뒤에만 시작 화면으로 이동한다. 서버 자료가 이미 지워졌으므로 이 이동은
 * 작성 중 입력 보호를 통과하고, 체험 화면이 내려가며 진행 요청과 화면 메모리도 정리된다.
 * 실패하면 화면과 입력을 그대로 두고 다시 시도할 수 있다.
 */
export function EndJourneyAction({ journeyId }: { journeyId: string }) {
  const navigate = useNavigate()
  const [confirming, setConfirming] = useState(false)
  const request = useRequest<true>()
  const pending = request.state.status === 'pending'
  function end() {
    void request.run(async (api, signal) => {
      const result = await api.DELETE('/journeys/{journey_id}', { params: { path: { journey_id: journeyId } }, signal })
      if (result.response.status !== 204) throw new ApiError('INVALID_RESPONSE')
      return true
    }, () => navigateDiscardingInput(navigate, '/'))
  }
  return <section className="journey-end" aria-label="체험 종료">
    {!confirming && <Button variant="secondary" onClick={() => setConfirming(true)}>종료하고 삭제</Button>}
    {confirming && <div className="panel" role="group" aria-label="체험 삭제 확인">
      <h2>체험 임시 자료를 삭제할까요?</h2>
      <p>대화와 프로필, 모든 임시 지원서를 서버에서 바로 삭제해요. 삭제한 자료는 되돌릴 수 없어요. 회원으로 저장한 자료는 지우지 않아요.</p>
      {request.state.status === 'error' && <RequestError error={request.state.error} />}
      <div className="actions">
        <Button pending={pending} onClick={end}>{request.state.status === 'error' ? '삭제 다시 시도' : '체험 임시 자료 삭제 확인'}</Button>
        <Button variant="secondary" disabled={pending} onClick={() => { request.clear(); setConfirming(false) }}>계속 이용하기</Button>
      </div>
    </div>}
  </section>
}
