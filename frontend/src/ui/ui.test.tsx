import { useState } from 'react'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'
import { Button } from './Button'
import { CheckboxField, TextAreaField } from './Fields'
import { FormErrorSummary } from './FormErrorSummary'
import { RequestError, StatusNotice } from './StatusNotice'
import { ApiError } from '../api/errors'

function ExampleForm({ submit }: { submit: () => void }) {
  const [text, setText] = useState('')
  const [invalid, setInvalid] = useState(false)
  const [pending, setPending] = useState(false)
  const message = '경험을 한 가지 적어 주세요.'
  return <form onSubmit={(event) => {
    event.preventDefault()
    setInvalid(!text.trim())
    if (text.trim()) { setPending(true); submit() }
  }}>
    <FormErrorSummary errors={invalid ? [{ fieldId: 'example-experience', message }] : []} />
    <TextAreaField id="example-experience" label="경험" value={text} onChange={(event) => setText(event.target.value)} hint="가상 정보로 작성하세요." error={invalid ? message : undefined} maxLength={20} />
    <Button type="submit" pending={pending} pendingLabel="확인하고 있어요">확인하기</Button>
  </form>
}

describe('accessible shared controls', () => {
  it('preserves caller-provided invalid state and external error descriptions', () => {
    render(<><p id="external-error">입력을 확인해 주세요.</p><TextAreaField label="외부 검증 입력" value="" onChange={() => {}} aria-invalid="true" aria-describedby="external-error" /><CheckboxField label="외부 검증 선택" aria-invalid="true" aria-describedby="external-error" /></>)
    for (const field of [screen.getByRole('textbox'), screen.getByRole('checkbox')]) {
      expect(field).toHaveAttribute('aria-invalid', 'true')
      expect(field).toHaveAccessibleDescription('입력을 확인해 주세요.')
    }
  })
  it('marks a visible component error invalid even if the caller passes false', () => {
    render(<><TextAreaField label="경험 오류" value="" onChange={() => {}} aria-invalid="false" error="경험을 확인해 주세요." /><CheckboxField label="선택 오류" aria-invalid="false" error="선택을 확인해 주세요." /></>)
    expect(screen.getByRole('textbox')).toHaveAttribute('aria-invalid', 'true')
    expect(screen.getByRole('checkbox')).toHaveAttribute('aria-invalid', 'true')
  })
  it('focuses an error summary and lets a keyboard user jump to the invalid input', async () => {
    const user = userEvent.setup()
    render(<ExampleForm submit={vi.fn()} />)
    await user.click(screen.getByRole('button', { name: '확인하기' }))
    expect(screen.getByRole('region', { name: '입력한 항목을 확인해 주세요' })).toHaveFocus()
    expect(screen.getByRole('textbox', { name: '경험' })).toHaveAttribute('aria-invalid', 'true')
    expect(screen.getByRole('textbox')).toHaveAccessibleDescription(/가상 정보로 작성하세요.*오류: 경험을 한 가지 적어 주세요/)
    await user.tab()
    expect(screen.getByRole('link', { name: '경험을 한 가지 적어 주세요.' })).toHaveFocus()
    await user.keyboard('{Enter}')
    expect(screen.getByRole('textbox')).toHaveFocus()
  })
  it('keeps valid input while processing, announces the pending label and blocks duplicate submit', async () => {
    const user = userEvent.setup()
    const submit = vi.fn()
    render(<ExampleForm submit={submit} />)
    await user.type(screen.getByRole('textbox'), '책 정리 경험')
    await user.click(screen.getByRole('button', { name: '확인하기' }))
    const button = screen.getByRole('button', { name: '확인하고 있어요' })
    expect(button).toBeDisabled()
    expect(button).toHaveAttribute('aria-busy', 'true')
    await user.click(button)
    expect(submit).toHaveBeenCalledTimes(1)
    expect(screen.getByRole('textbox')).toHaveValue('책 정리 경험')
  })
  it('does not implicitly submit a form for ordinary action buttons', async () => {
    const submit = vi.fn((event) => event.preventDefault())
    render(<form onSubmit={submit}><Button>다른 행동</Button></form>)
    await userEvent.click(screen.getByRole('button'))
    expect(submit).not.toHaveBeenCalled()
  })
  it('associates a checkbox with its label, hint and error using generated IDs', async () => {
    render(<CheckboxField label="내용 확인" hint="가상 안내입니다." error="선택을 확인해 주세요." />)
    const checkbox = screen.getByRole('checkbox', { name: '내용 확인' })
    expect(checkbox).toHaveAccessibleDescription('가상 안내입니다. 오류: 선택을 확인해 주세요.')
    await userEvent.click(screen.getByText('내용 확인'))
    expect(checkbox).toBeChecked()
  })
  it('creates separate label/description IDs for repeated text fields', () => {
    render(<><TextAreaField label="첫 경험" value="" hint="첫 안내" onChange={() => {}} /><TextAreaField label="둘째 경험" value="" hint="둘째 안내" onChange={() => {}} /></>)
    const first = screen.getByRole('textbox', { name: '첫 경험' })
    const second = screen.getByRole('textbox', { name: '둘째 경험' })
    expect(first.id).not.toBe(second.id)
    expect(first).toHaveAccessibleDescription('첫 안내')
    expect(second).toHaveAccessibleDescription('둘째 안내')
  })
  it('keeps HTML-looking text inert in shared error and status output', () => {
    const attack = '<img src=x onerror=alert(1)>'
    const { container } = render(<StatusNotice kind="error" title="요청을 확인해 주세요">{attack}</StatusNotice>)
    expect(screen.getByRole('alert')).toHaveTextContent(attack)
    expect(container.querySelector('img, script')).toBeNull()
  })
  it('uses a polite processing status and leaves recovery controls operable outside it', async () => {
    const cancel = vi.fn()
    render(<StatusNotice kind="loading" title="처리하고 있어요" actions={<Button onClick={cancel}>취소하기</Button>}>잠시 기다려 주세요.</StatusNotice>)
    expect(screen.getByRole('status')).toHaveTextContent('처리하고 있어요')
    expect(screen.queryByRole('alert')).not.toBeInTheDocument()
    await userEvent.click(screen.getByRole('button', { name: '취소하기' }))
    expect(cancel).toHaveBeenCalledOnce()
  })
  it('renders unknown request failures with a fixed message and no internal details', () => {
    render(<RequestError error={new Error('private-input-server-path')} />)
    expect(screen.getByRole('alert')).toHaveTextContent('처리 중 문제가 발생했습니다.')
    expect(screen.getByRole('alert')).not.toHaveTextContent('private-input-server-path')
  })
  it('uses the safe quota message while leaving recovery actions to the screen', () => {
    render(<RequestError error={new ApiError('DAILY_QUOTA_EXCEEDED', 429)} />)
    expect(screen.getByRole('alert')).toHaveTextContent('다음 날 다시 이용해 주세요.')
    expect(screen.queryByRole('button')).not.toBeInTheDocument()
  })
  it('does not announce an intentional cancellation as a request failure', () => {
    render(<RequestError error={new ApiError('CANCELLED')} />)
    expect(screen.queryByRole('alert')).not.toBeInTheDocument()
  })
})
