import { act, fireEvent, render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, expect, it, vi } from 'vitest'
import { AccountHeaderActions } from './AccountHeaderActions'
import { anonymousSession } from '../../api/fixtures'

const member = { ...anonymousSession, authenticated: true, user: { id: '12345678-1234-4234-9234-123456789012', roles: ['user'], mfa_verified: false, reauth_until: null } }
const json = (data: unknown) => new Response(JSON.stringify(data), { headers: { 'Content-Type': 'application/json' } })
const mount = () => render(<MemoryRouter><AccountHeaderActions /></MemoryRouter>)
afterEach(() => { vi.unstubAllGlobals(); document.cookie = '__Host-rc_csrf=; Max-Age=0; Path=/; Secure' })

it('keeps failed session verification distinct from anonymous access and offers a retry', async () => {
  const fetch = vi.fn().mockRejectedValueOnce(new Error('private-network')).mockResolvedValueOnce(json(anonymousSession))
  vi.stubGlobal('fetch', fetch)
  mount()
  expect(await screen.findByText('로그인 상태를 확인하지 못했습니다.')).toHaveAttribute('role', 'status')
  expect(screen.queryByRole('link', { name: '로그인' })).not.toBeInTheDocument()
  expect(document.body).not.toHaveTextContent('private')
  await userEvent.click(screen.getByRole('button', { name: '로그인 상태 다시 확인' }))
  expect(await screen.findByRole('link', { name: '로그인' })).toBeVisible()
})

it('clears the cached member controls on page departure and requires fresh verification', async () => {
  const fetch = vi.fn().mockResolvedValueOnce(json(member)).mockResolvedValueOnce(json(anonymousSession))
  vi.stubGlobal('fetch', fetch)
  mount()
  await screen.findByRole('button', { name: '로그아웃' })
  act(() => window.dispatchEvent(new Event('pagehide')))
  expect(screen.queryByRole('button', { name: '로그아웃' })).not.toBeInTheDocument()
  await userEvent.click(screen.getByRole('button', { name: '로그인 상태 다시 확인' }))
  expect(await screen.findByRole('link', { name: '로그인' })).toBeVisible()
})

it('does not replay logout after response loss and verifies the state with a read', async () => {
  const fetch = vi.fn().mockResolvedValueOnce(json(member)).mockRejectedValueOnce(new Error('lost-post')).mockResolvedValueOnce(json(anonymousSession))
  vi.stubGlobal('fetch', fetch)
  document.cookie = '__Host-rc_csrf=token; Path=/; Secure'
  mount()
  const logout = await screen.findByRole('button', { name: '로그아웃' })
  fireEvent.click(logout); fireEvent.click(logout)
  expect(await screen.findByRole('alert')).toHaveTextContent('로그아웃 결과를 확인하지 못했습니다.')
  await userEvent.click(screen.getByRole('button', { name: '로그인 상태 다시 확인' }))
  expect(await screen.findByRole('link', { name: '로그인' })).toBeVisible()
  expect(fetch.mock.calls.map(([request]) => (request as Request).method)).toEqual(['GET', 'POST', 'GET'])
})

it('cancels an in-flight logout when the header unmounts and skips its follow-up read', async () => {
  let finish!: (response: Response) => void
  const fetch = vi.fn().mockResolvedValueOnce(json(member)).mockImplementationOnce(() => new Promise<Response>(resolve => { finish = resolve }))
  vi.stubGlobal('fetch', fetch)
  document.cookie = '__Host-rc_csrf=token; Path=/; Secure'
  const view = mount()
  await userEvent.click(await screen.findByRole('button', { name: '로그아웃' }))
  view.unmount()
  await act(async () => finish(new Response(null, { status: 204 })))
  expect(fetch).toHaveBeenCalledTimes(2)
  expect((fetch.mock.calls[1][0] as Request).signal.aborted).toBe(true)
})
