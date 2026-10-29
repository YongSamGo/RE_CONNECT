/** 체험 삭제(204 확인)처럼 입력을 버리는 것이 이미 확정된 이동에만 붙이는 표시. */
export const DISCARD_CONFIRMED = 'reconnectDiscardConfirmed'

export function isDiscardConfirmed(state: unknown) {
  return typeof state === 'object' && state !== null && (state as Record<string, unknown>)[DISCARD_CONFIRMED] === true
}
