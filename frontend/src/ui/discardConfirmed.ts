import type { NavigateFunction, To } from 'react-router-dom'

/**
 * 체험 삭제(204 확인)처럼 입력을 버리는 것이 이미 확정된 이동 한 번에만 쓰는 일회용 표시.
 * 이동 요청 순간에만 유효하다. data router는 이동 차단 여부를 navigate 호출 안에서 바로
 * 판단하므로, 호출이 끝나면 폐기해 이후 뒤로/앞으로 이동에서는 보호가 다시 동작한다.
 */
const KEY = 'reconnectDiscardToken'
let pending: string | null = null
let sequence = 0

export function navigateDiscardingInput(navigate: NavigateFunction, to: To) {
  sequence += 1
  const token = `${Date.now()}-${sequence}`
  pending = token
  try {
    void navigate(to, { replace: true, state: { [KEY]: token } })
  } finally {
    pending = null
  }
}

export function isDiscardConfirmed(state: unknown) {
  return pending !== null && typeof state === 'object' && state !== null
    && (state as Record<string, unknown>)[KEY] === pending
}
