import { useId } from 'react'
import type { ReactNode } from 'react'
import { ApiError } from '../api/errors'

type Props = { title: string; children?: ReactNode; kind?: 'info' | 'loading' | 'error'; label?: string; actions?: ReactNode }

export function StatusNotice({ title, children, kind = 'info', label, actions }: Props) {
  const id = useId()
  return <section className={`notice notice-${kind}`} aria-labelledby={id}>
    <div role={kind === 'error' ? 'alert' : kind === 'loading' ? 'status' : undefined} aria-atomic={kind === 'info' ? undefined : true}>
      {label && <span className="badge">{label}</span>}
      <h2 id={id}>{title}</h2>{children && <p>{children}</p>}
    </div>
    {actions && <div className="actions">{actions}</div>}
  </section>
}

export function RequestError({ error, actions }: { error: unknown; actions?: ReactNode }) {
  if (error instanceof ApiError && error.code === 'CANCELLED') return null
  const message = error instanceof ApiError ? error.message : '처리 중 문제가 발생했습니다. 입력을 확인하고 다시 시도해 주세요.'
  const code = error instanceof ApiError ? error.code : ''
  const next = code === 'UNAUTHENTICATED' ? <a className="button primary" href="/login">로그인하기</a>
    : ['SESSION_EXPIRED', 'NOT_FOUND'].includes(code) ? <a className="button primary" href="/start">새로 시작하기</a>
      : code === 'SAVE_INTENT_NOT_FOUND' ? <a className="button secondary" href="/me">저장한 자료 확인</a>
        : code === 'OPPORTUNITY_NOT_AVAILABLE' ? <a className="button secondary" href="/opportunities?browse=all">다른 공고 살펴보기</a> : null
  const wait = error instanceof ApiError && error.retryAfterSeconds !== undefined
    && Number.isInteger(error.retryAfterSeconds) && error.retryAfterSeconds > 0 && error.retryAfterSeconds <= 86400
    ? ` ${error.retryAfterSeconds}초 후 다시 시도해 주세요.` : ''
  return <StatusNotice kind="error" title={code === 'SESSION_EXPIRED' ? '이용 시간이 지났어요' : '요청을 완료하지 못했어요'} actions={next ?? actions}>{message + wait}</StatusNotice>
}
