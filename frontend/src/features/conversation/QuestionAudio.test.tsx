import { fireEvent, render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, expect, it, vi } from 'vitest'
import { QuestionAudio } from './QuestionAudio'

afterEach(() => vi.unstubAllGlobals())

it('reads the fixed opening question slowly with the selected volume', async () => {
  const speak = vi.fn(), cancel = vi.fn()
  vi.stubGlobal('speechSynthesis', { speak, cancel })
  vi.stubGlobal('SpeechSynthesisUtterance', class { text: string; lang = ''; rate = 1; volume = 1; onerror = null; constructor(text: string) { this.text = text } })
  render(<QuestionAudio question="첫 질문입니다." journeyId="12345678-1234-1234-1234-123456789012" messageId={null} />)
  const user = userEvent.setup()
  fireEvent.change(screen.getByLabelText('소리 조절'), { target: { value: '0.5' } })
  await user.click(screen.getByRole('button', { name: '천천히 듣기' }))
  expect(speak).toHaveBeenCalledOnce()
  expect(speak.mock.calls[0][0]).toMatchObject({ text: '첫 질문입니다.', lang: 'ko-KR', rate: 0.75, volume: 0.5 })
})
