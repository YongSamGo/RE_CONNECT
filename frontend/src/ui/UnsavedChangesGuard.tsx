import { useCallback, useContext, useEffect, useRef } from 'react'
import { UNSAFE_DataRouterContext, useBeforeUnload, useBlocker } from 'react-router-dom'
import { Button } from './Button'
import { isDiscardConfirmed } from './discardConfirmed'

export function UnsavedChangesGuard({ dirty }: { dirty: boolean }) {
  const router = useContext(UNSAFE_DataRouterContext)
  useBeforeUnload(useCallback((event: BeforeUnloadEvent) => {
    if (dirty) { event.preventDefault(); event.returnValue = '' }
  }, [dirty]))
  // Isolated component previews can use MemoryRouter. The application uses a
  // data router so back/forward, links and programmatic navigation are guarded.
  return router ? <RouteGuard dirty={dirty} /> : null
}

function RouteGuard({ dirty }: { dirty: boolean }) {
  const blocker = useBlocker(useCallback(({ nextLocation }: { nextLocation: { state: unknown } }) => dirty && !isDiscardConfirmed(nextLocation.state), [dirty]))
  const dialog = useRef<HTMLDialogElement>(null)
  const previousFocus = useRef<HTMLElement | null>(null)
  useEffect(() => {
    if (blocker.state === 'blocked' && !dialog.current?.open) {
      previousFocus.current = document.activeElement instanceof HTMLElement ? document.activeElement : null
      dialog.current?.showModal()
    } else if (blocker.state !== 'blocked' && dialog.current?.open) dialog.current.close()
  }, [blocker.state])
  const stay = () => { if (blocker.state === 'blocked') blocker.reset(); previousFocus.current?.focus() }
  return <dialog ref={dialog} className="draft-review-dialog" aria-labelledby="leave-title" onCancel={event => { event.preventDefault(); stay() }}>
    <h2 id="leave-title">작성 중인 내용이 있어요</h2>
    <p>이동하면 아직 반영하지 않은 화면 입력이 사라집니다. 저장된 자료는 유지됩니다.</p>
    <div className="actions"><Button onClick={stay}>계속 작성하기</Button><Button variant="secondary" onClick={() => { if (blocker.state === 'blocked') blocker.proceed() }}>입력을 버리고 이동</Button></div>
  </dialog>
}
