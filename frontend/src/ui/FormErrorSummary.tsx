import { useEffect, useId, useRef } from 'react'

export type FieldError = { fieldId: string; message: string }

export function FormErrorSummary({ errors }: { errors: FieldError[] }) {
  const id = useId()
  const ref = useRef<HTMLElement>(null)
  useEffect(() => { if (errors.length) ref.current?.focus() }, [errors])
  if (!errors.length) return null
  return <section className="error-summary" ref={ref} tabIndex={-1} aria-labelledby={id}>
    <h2 id={id}>입력한 항목을 확인해 주세요</h2><ul>{errors.map(({ fieldId, message }) => <li key={fieldId}>
      <a href={`#${fieldId}`} onClick={(event) => {
        const field = document.getElementById(fieldId)
        if (field) { event.preventDefault(); field.focus() }
      }}>{message}</a>
    </li>)}</ul>
  </section>
}
