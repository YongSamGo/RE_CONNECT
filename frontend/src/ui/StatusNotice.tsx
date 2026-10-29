import { useId } from 'react'
import type { ReactNode } from 'react'
import { ApiError } from '../api/errors'

type Props = { title: string; children: ReactNode; kind?: 'info' | 'loading' | 'error'; label?: string; actions?: ReactNode }

export function StatusNotice({ title, children, kind = 'info', label, actions }: Props) {
  const id = useId()
  return <section className={`notice notice-${kind}`} aria-labelledby={id}>
    <div role={kind === 'error' ? 'alert' : kind === 'loading' ? 'status' : undefined} aria-atomic={kind === 'info' ? undefined : true}>
      <span className="badge">{label ?? (kind === 'loading' ? '처리 중' : kind === 'error' ? '확인 필요' : '이용 안내')}</span>
      <h2 id={id}>{title}</h2><p>{children}</p>
    </div>
    {actions && <div className="actions">{actions}</div>}
  </section>
}

export function RequestError({ error, actions }: { error: unknown; actions?: ReactNode }) {
  if (error instanceof ApiError && error.code === 'CANCELLED') return null
  const message = error instanceof ApiError ? error.message : '처리 중 문제가 발생했습니다. 입력을 확인하고 다시 시도해 주세요.'
  return <StatusNotice kind="error" title="요청을 완료하지 못했어요" actions={actions}>{message}</StatusNotice>
}
