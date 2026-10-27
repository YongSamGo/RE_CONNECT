import { useEffect } from 'react'
import { required, useRequest } from '../../state/useRequest'
import { useMemoryScope } from '../../state/useMemoryScope'
import { Button } from '../../ui/Button'
import { ApiError } from '../../api/errors'
import { RequestError } from '../../ui/StatusNotice'
import { invalid, record } from '../public-opportunities/catalog'

export function SavedProfileSave({ journeyId, version, baseVersion, disabled, copyText, onUnavailable }: {
  journeyId: string; version: number; baseVersion: number; disabled: boolean; copyText: string; onUnavailable?: () => void
}) {
  const state = useMemoryScope<{ base: number; key: string; savedVersion: number }>(() => ({ base: baseVersion, key: crypto.randomUUID(), savedVersion: 0 }))
  const request = useRequest<{ base: number; key: string; savedVersion: number }>()
  const copy = useRequest<string>()
  const update = state.setValue
  useEffect(() => { update(previous => ({ ...previous, key: crypto.randomUUID(), savedVersion: 0 })) }, [version, update])
  useEffect(() => {
    if (request.state.status === 'error' && ['UNAUTHENTICATED', 'SESSION_EXPIRED', 'NOT_FOUND'].includes(request.state.error.code)) onUnavailable?.()
  }, [request.state, onUnavailable])
  const pending = request.state.status === 'pending' || copy.state.status === 'pending'
  return <section className="panel"><h2>재확정한 프로필 회원 저장</h2>
    <p>수정 중 자동 저장하지 않습니다. 재확정한 뒤 이 버튼을 눌러야 기존 저장본을 새 버전으로 저장합니다. 현재 회원 저장 동의가 있어야 합니다.</p>
    <Button pending={pending} disabled={disabled || state.value.savedVersion === version} onClick={() => void request.run(async (api, signal) => {
      const result = record(required((await api.POST('/profiles/me/versions', { signal, params: { header: { 'Idempotency-Key': state.value.key } }, body: {
        source: { type: 'journey', journey_id: journeyId, version }, base_saved_version: state.value.base,
      } })).data))
      if (typeof result.version !== 'number' || !Number.isSafeInteger(result.version) || result.version < 1) return invalid()
      return { base: result.version, key: crypto.randomUUID(), savedVersion: version }
    }, value => state.setValue(value))}>재확정 프로필 저장 · 실패 시 재시도</Button>
    <Button variant="secondary" disabled={pending} onClick={() => void copy.run(async () => {
      if (!navigator.clipboard?.writeText) throw new ApiError('INVALID_TARGET')
      await navigator.clipboard.writeText(copyText)
      return '프로필 내용을 복사했습니다.'
    })}>프로필 내용 복사</Button>
    {copy.state.status === 'error' && <RequestError error={copy.state.error} />}
    {copy.state.status === 'success' && <p role="status">{copy.state.data}</p>}
    {request.state.status === 'error' && <><RequestError error={request.state.error} /><p>입력 내용은 화면에 남습니다. 복사하거나 같은 내용으로 다시 저장해 주세요. 저장 버전이 충돌하면 저장 자료를 다시 불러와 확인해 주세요.</p></>}
    {state.value.savedVersion === version && <p role="status">프로필 {state.value.base}번을 저장했습니다.</p>}
  </section>
}
