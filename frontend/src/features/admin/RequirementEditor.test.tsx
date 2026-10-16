import { act, fireEvent, render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { useState } from 'react'
import { describe, expect, it, vi } from 'vitest'
import type { components } from '../../api/schema'
import { RequirementEditor, RequirementSummary } from './RequirementEditor'

type Requirement = components['schemas']['Requirement']
const condition: Requirement = { id: '12345678-1234-1234-1234-123456789010', field: 'age', operator: 'gte', value: 60, source_evidence: '만 60세 이상', clarity: 'clear', group_id: null, group_operator: null, reference_date: '2026-10-15' }
function setup(items = [condition]) {
  const changed = vi.fn(), editing = vi.fn()
  function Harness() { const [values, setValues] = useState(items); return <RequirementEditor items={values} disabled={false} onEditingChange={editing} onChange={(next) => { changed(next); setValues(next) }} /> }
  render(<Harness />)
  return { changed, editing, user: userEvent.setup() }
}
const change = (label: string, value: string) => fireEvent.change(screen.getByLabelText(label), { target: { value } })
describe('explicit condition editing', () => {
  it('preserves identity and date, resets source review, and cancels without applying', async () => {
    const { changed, editing, user } = setup()
    await user.click(screen.getByRole('button', { name: '조건 1 편집' }))
    change('조건 값 (한 줄에 하나)', '65')
    await user.click(screen.getByRole('button', { name: '조건 편집 적용' }))
    expect(changed).toHaveBeenLastCalledWith([{ ...condition, value: 65, clarity: 'needs_review' }])
    expect(editing).toHaveBeenLastCalledWith(false)
    await user.click(screen.getByRole('button', { name: '조건 1 편집' }))
    change('조건 원문 (필수)', '보내지 않을 입력')
    await user.click(screen.getByRole('button', { name: '조건 편집 취소' }))
    expect(changed).toHaveBeenCalledTimes(1)
    expect(screen.queryByText('보내지 않을 입력')).not.toBeInTheDocument()
  })
  it('rejects reversed ranges with focusable errors, then allows explicitly reviewed rules', async () => {
    const { changed, user } = setup()
    await user.click(screen.getByRole('button', { name: '조건 1 편집' }))
    await user.selectOptions(screen.getByLabelText('조건 비교 방법'), 'between')
    change('조건 값 (한 줄에 하나)', '70\n60')
    await user.click(screen.getByRole('button', { name: '조건 편집 적용' }))
    expect(changed).not.toHaveBeenCalled()
    await user.click(screen.getByRole('link', { name: /조건 원문·값·기준일/ }))
    expect(screen.getByLabelText('조건 값 (한 줄에 하나)')).toHaveFocus()
    change('조건 값 (한 줄에 하나)', '60\n70')
    await user.click(screen.getByRole('checkbox'))
    change('조건 판정 기준일 (미확인은 비워두기)', '2026-10-16')
    expect(screen.getByRole('checkbox')).not.toBeChecked()
    await user.click(screen.getByRole('checkbox'))
    await user.click(screen.getByRole('button', { name: '조건 편집 적용' }))
    expect(changed).toHaveBeenLastCalledWith([{ ...condition, operator: 'between', value: [60, 70], reference_date: '2026-10-16' }])
  })
  it('applies a group operator consistently and invalidates peer review', async () => {
    const grouped = { ...condition, group_id: condition.id, group_operator: 'and' as const }
    const peer = { ...grouped, id: '12345678-1234-1234-1234-123456789011' }
    const { changed, user } = setup([grouped, peer])
    await user.click(screen.getByRole('button', { name: '조건 1 편집' }))
    await user.selectOptions(screen.getByLabelText('묶음 충족 방법'), 'or')
    await user.click(screen.getByRole('button', { name: '조건 편집 적용' }))
    expect(changed).toHaveBeenLastCalledWith([{ ...grouped, group_operator: 'or', clarity: 'needs_review' }, { ...peer, group_operator: 'or', clarity: 'needs_review' }])
  })
  it('keeps unknown conditions unresolved and requires explicit deletion', async () => {
    const { changed, user } = setup([])
    await user.click(screen.getByRole('button', { name: '조건 하나 추가' }))
    change('조건 원문 (필수)', '<img src=x onerror=alert(1)>')
    expect(screen.queryByRole('checkbox')).not.toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: '조건 편집 적용' }))
    expect(changed).toHaveBeenLastCalledWith([expect.objectContaining({ field: 'other', value: null, operator: null, clarity: 'needs_review' })])
    expect(document.querySelector('img')).toBeNull()
    await user.click(screen.getByRole('button', { name: '조건 1 삭제 검토' }))
    expect(changed).toHaveBeenCalledTimes(1)
    await user.click(screen.getByRole('button', { name: '원문 대조 후 조건 삭제' }))
    expect(changed).toHaveBeenLastCalledWith([])
  })
  it('preserves district detail and clears local staged edits on page exit', async () => {
    const regional: Requirement = { ...condition, field: 'residence_region', operator: 'in', value: [{ province: 'seoul', district: 'seongdong' }] }
    const { changed, user } = setup([regional])
    await user.click(screen.getByRole('button', { name: '조건 1 편집' }))
    await user.click(screen.getByRole('button', { name: '조건 편집 적용' }))
    expect(changed).toHaveBeenLastCalledWith([{ ...regional, clarity: 'needs_review' }])
    await user.click(screen.getByRole('button', { name: '조건 1 편집' }))
    change('조건 원문 (필수)', '임시 편집 원문')
    act(() => window.dispatchEvent(new Event('pagehide')))
    expect(screen.queryByLabelText('조건 원문 (필수)')).not.toBeInTheDocument()
    expect(document.body).not.toHaveTextContent('임시 편집 원문')
  })
  it('shows full rule and group information in a review summary', () => {
    render(<RequirementSummary items={[{ ...condition, group_id: condition.id, group_operator: 'or' }]} />)
    expect(screen.getByText(/만 나이 · 이상 · 60 · 기준일 2026-10-15/)).toBeVisible()
    expect(screen.getByText('묶음 1 · 하나 이상 충족')).toBeVisible()
  })
  it('preserves exact multiline qualification values unless the value itself changes', async () => {
    const qualified: Requirement = { ...condition, field: 'certification', operator: 'has_any', value: [' 자격\n명 ', '별도 자격'] }
    const { changed, user } = setup([qualified])
    await user.click(screen.getByRole('button', { name: '조건 1 편집' }))
    change('조건 원문 (필수)', '원문 근거 보완')
    await user.click(screen.getByRole('button', { name: '조건 편집 적용' }))
    expect(changed).toHaveBeenLastCalledWith([{ ...qualified, source_evidence: '원문 근거 보완', clarity: 'needs_review' }])
  })
})
