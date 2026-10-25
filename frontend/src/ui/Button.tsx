import type { ButtonHTMLAttributes, ReactNode } from 'react'

type Props = ButtonHTMLAttributes<HTMLButtonElement> & {
  variant?: 'primary' | 'secondary' | 'compact'
  pending?: boolean
  pendingLabel?: ReactNode
}

export function Button({ variant = 'primary', pending = false, pendingLabel = '처리 중입니다…', children, disabled, className = '', type = 'button', ...props }: Props) {
  return <button {...props} type={type} className={`button ${variant} ${className}`.trim()} disabled={disabled || pending} aria-busy={pending || undefined}>
    {pending ? pendingLabel : children}
  </button>
}
