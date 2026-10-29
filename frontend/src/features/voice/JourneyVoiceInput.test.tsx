import { act, render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import { Blob as NodeBlob, File as NodeFile } from 'node:buffer'
import { JourneyVoiceInput } from './JourneyVoiceInput'
import { parseTranscription } from './transcription'

vi.mock('./VoicePreview', () => ({ VoicePreview: ({ transcription }: { transcription: { onRequest: (blob: Blob) => void; onReset: () => void } }) => <><button onClick={() => transcription.onRequest(new Blob(['fixture-audio'], { type: 'audio/webm' }))}>시험 녹음 전사</button><button onClick={transcription.onReset}>시험 녹음 취소</button></> }))
const id = '12345678-1234-1234-1234-123456789012'
const result = { transcription_id: id, text: '가상 원래 전사', duration_seconds: 2.5 }
beforeEach(async () => {
  // Match Node's Request body implementation instead of mixing jsdom File
  // objects with undici serialization, which would erase their byte content.
  const native = await new Response('fixture=1', { headers: { 'Content-Type': 'application/x-www-form-urlencoded' } }).formData()
  vi.stubGlobal('FormData', native.constructor)
  vi.stubGlobal('Blob', NodeBlob)
  vi.stubGlobal('File', NodeFile)
})
const json = (value: unknown) => new Response(JSON.stringify(value), { headers: { 'Content-Type': 'application/json' } })
function mount(options: { consent?: boolean; loseFirst?: boolean; replace?: boolean } = {}) {
  let posts = 0
  const fetch = vi.fn(async (request: Request) => {
    if (request.method === 'GET') return json({ authenticated: false, user: null, pending_save_intent: null, consents: options.consent === false ? [] : [{ purpose: 'ai_processing', notice_version: 'fixture-ai', granted_at: '2026-10-18T00:00:00Z' }] })
    posts++
    if (options.loseFirst && posts === 1) throw new TypeError('fixture lost response')
    return json(result)
  })
  vi.stubGlobal('fetch', fetch)
  document.cookie = '__Host-rc_csrf=token; Secure; Path=/'
  const onUseText = vi.fn()
  render(<JourneyVoiceInput journeyId={id} replaceRequired={options.replace ?? false} onUseText={onUseText} />)
  return { user: userEvent.setup(), fetch, onUseText }
}
afterEach(() => { vi.restoreAllMocks(); vi.unstubAllGlobals(); document.cookie = '__Host-rc_csrf=; Max-Age=0; Secure; Path=/' })

it('uploads only explicit audio as multipart and imports a validated transcript without sending a conversation answer',async()=>{
  const {user,fetch,onUseText}=mount();expect(fetch).not.toHaveBeenCalled()
  await user.click(screen.getByRole('button',{name:'시험 녹음 전사'}))
  expect(onUseText).toHaveBeenCalledWith(result.text,result.transcription_id)
  const request=fetch.mock.calls.find(([request])=>request.method==='POST')![0]
  expect(request.headers.get('content-type')).toMatch(/^multipart\/form-data; boundary=/)
  expect(request.headers.get('X-CSRF-Token')).toBe('token')
  const data=await request.clone().formData();expect([...data.keys()]).toEqual(['audio'])
  expect((data.get('audio') as File).size).toBeGreaterThan(0)
  expect(fetch.mock.calls.some(([request])=>request.url.endsWith('/messages'))).toBe(false)
})
it('does not upload without current AI consent',async()=>{
  const {user,fetch,onUseText}=mount({consent:false});await user.click(screen.getByRole('button',{name:'시험 녹음 전사'}))
  expect(await screen.findByRole('alert')).toBeVisible();expect(fetch.mock.calls.every(([request])=>request.method==='GET')).toBe(true)
  expect(onUseText).not.toHaveBeenCalled()
})
it('reuses the same key and original audio after response loss',async()=>{
  const {user,fetch,onUseText}=mount({loseFirst:true});await user.click(screen.getByRole('button',{name:'시험 녹음 전사'}))
  await screen.findByRole('alert');await user.click(screen.getByRole('button',{name:'시험 녹음 전사'}))
  expect(onUseText).toHaveBeenCalledOnce()
  const posts=fetch.mock.calls.map(([request])=>request).filter(request=>request.method==='POST')
  expect(posts).toHaveLength(2);expect(posts[0].headers.get('Idempotency-Key')).toBe(posts[1].headers.get('Idempotency-Key'))
  const bodies=await Promise.all(posts.map(request=>request.clone().formData()))
  expect(await (bodies[0].get('audio') as File).text()).toBe(await (bodies[1].get('audio') as File).text())
})
it.each(['cancel','pagehide'])('never imports a late transcript after %s',async kind=>{
  let finish!:(response:Response)=>void
  const onUseText=vi.fn();const fetch=vi.fn(async(request:Request):Promise<Response>=>request.method==='GET'?json({authenticated:false,user:null,pending_save_intent:null,consents:[{purpose:'ai_processing',notice_version:'fixture-ai',granted_at:'2026-10-18T00:00:00Z'}]}):new Promise(resolve=>{finish=resolve}))
  vi.stubGlobal('fetch',fetch);document.cookie='__Host-rc_csrf=token; Secure; Path=/'
  render(<JourneyVoiceInput journeyId={id} onUseText={onUseText}/>);await userEvent.click(screen.getByRole('button',{name:'시험 녹음 전사'}))
  if(kind==='cancel')await userEvent.click(screen.getByRole('button',{name:'시험 녹음 취소'}));else act(()=>window.dispatchEvent(new Event('pagehide')))
  await act(async()=>finish(json(result)));expect(onUseText).not.toHaveBeenCalled()
  expect(fetch.mock.calls.find(([request])=>request.method==='POST')![0].signal.aborted).toBe(true)
})
it('rejects invalid transcript references, durations, and oversized text',()=>{
  for(const change of [{transcription_id:'forged'},{duration_seconds:91},{duration_seconds:true},{text:'x'.repeat(2001)}])expect(()=>parseTranscription({...result,...change})).toThrow()
})
