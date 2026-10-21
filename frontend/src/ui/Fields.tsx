import { useId } from 'react'
import type { InputHTMLAttributes, TextareaHTMLAttributes } from 'react'

type TextAreaProps = Omit<TextareaHTMLAttributes<HTMLTextAreaElement>, 'value' | 'children'> & {
  label: string
  hint?: string
  error?: string
  value: string
}

export function TextAreaField({ id, label, hint, error, value, maxLength, required, 'aria-describedby': describedBy, 'aria-invalid': invalid, ...props }: TextAreaProps) {
  const generatedId = useId()
  const fieldId = id ?? generatedId
  const description = [describedBy, hint && `${fieldId}-help`, maxLength !== undefined && `${fieldId}-length`, error && `${fieldId}-error`].filter(Boolean).join(' ') || undefined
  return <div className="form-field">
    <label htmlFor={fieldId}>{label}{required && <span className="field-required"> (필수)</span>}</label>
    <textarea {...props} id={fieldId} value={value} maxLength={maxLength} required={required} aria-invalid={error ? true : invalid} aria-describedby={description} />
    <div className="input-meta">{hint && <p id={`${fieldId}-help`}>{hint}</p>}{maxLength !== undefined && <p id={`${fieldId}-length`}>{value.length.toLocaleString('ko-KR')} / {maxLength.toLocaleString('ko-KR')}자</p>}</div>
    {error && <p className="field-error" id={`${fieldId}-error`}>오류: {error}</p>}
  </div>
}

type CheckboxProps = Omit<InputHTMLAttributes<HTMLInputElement>, 'type' | 'children'> & {
  label: string
  hint?: string
  error?: string
}

export function CheckboxField({ id, label, hint, error, required, 'aria-describedby': describedBy, 'aria-invalid': invalid, ...props }: CheckboxProps) {
  const generatedId = useId()
  const fieldId = id ?? generatedId
  const description = [describedBy, hint && `${fieldId}-help`, error && `${fieldId}-error`].filter(Boolean).join(' ') || undefined
  return <div className="form-field">
    <label className="checkbox-label" htmlFor={fieldId}><input {...props} type="checkbox" id={fieldId} required={required} aria-invalid={error ? true : invalid} aria-describedby={description} />{label}{required && <span className="field-required"> (필수)</span>}</label>
    {hint && <p className="field-hint" id={`${fieldId}-help`}>{hint}</p>}
    {error && <p className="field-error" id={`${fieldId}-error`}>오류: {error}</p>}
  </div>
}
