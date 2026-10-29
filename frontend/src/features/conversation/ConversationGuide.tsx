import { useEffect, useRef, useState } from 'react'
import { Button } from '../../ui/Button'

const steps = [
  { target: 'conversation-question', title: '화면에 표시된 질문에 편하게 답해주세요' },
  { target: 'question-audio-actions', title: '질문은 다시 들을 수 있어요' },
  { target: 'question-volume', title: '소리를 키우거나 줄일 수 있어요' },
  { target: 'conversation-speak', title: '말하기를 눌러 답변을 녹음할 수 있어요', description: '직접 글로 쓰는 것도 가능합니다.' },
]

export function ConversationGuide({ onClose }: { onClose: () => void }) {
  const [step, setStep] = useState(0)
  const [rect, setRect] = useState<DOMRect | null>(null)
  const dialog = useRef<HTMLDialogElement>(null)
  useEffect(() => { dialog.current?.showModal() }, [])
  useEffect(() => {
    const update = () => setRect(document.getElementById(steps[step].target)?.getBoundingClientRect() ?? null)
    document.getElementById(steps[step].target)?.scrollIntoView({ block: 'center', behavior: 'instant' })
    update()
    window.addEventListener('resize', update)
    window.addEventListener('scroll', update, true)
    return () => { window.removeEventListener('resize', update); window.removeEventListener('scroll', update, true) }
  }, [step])
  return <dialog ref={dialog} className="conversation-guide" aria-labelledby="conversation-guide-title" onCancel={event => { event.preventDefault(); onClose() }}>
    {rect && <div className="conversation-guide-highlight" aria-hidden="true" style={{ top: rect.top - 8, left: rect.left - 8, width: rect.width + 16, height: rect.height + 16 }} />}
    <div className="conversation-guide-card"><p>{step + 1} / {steps.length}</p><h2 id="conversation-guide-title">{steps[step].title}</h2>{steps[step].description && <p>{steps[step].description}</p>}
      <div className="actions"><Button onClick={() => step === steps.length - 1 ? onClose() : setStep(step + 1)}>{step === steps.length - 1 ? '대화 시작하기' : '다음'}</Button><Button variant="secondary" onClick={onClose}>안내 건너뛰기</Button></div></div>
  </dialog>
}
