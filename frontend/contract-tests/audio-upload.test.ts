import { execFileSync } from 'node:child_process'
import { createHash } from 'node:crypto'
import { fileURLToPath } from 'node:url'
import { afterEach, expect, it, vi } from 'vitest'
import { createApiClient } from '../src/api/client'
import { parseTranscription } from '../src/features/voice/transcription'

afterEach(() => vi.unstubAllGlobals())
it('actual browser client multipart serialization reaches the real bounded audio parser unchanged', async () => {
  const root = new URL('../', import.meta.url)
  const python = process.env.CONTRACT_PYTHON || fileURLToPath(new URL(process.platform === 'win32' ? '../backend/.venv/Scripts/python.exe' : '../backend/.venv/bin/python', root))
  vi.stubGlobal('window', { location: new URL('https://reconnect.test/') })
  vi.stubGlobal('document', { cookie: '__Host-rc_csrf=token' })
  const data = Buffer.alloc(48)
  data.write('RIFF', 0); data.writeUInt32LE(40, 4); data.write('WAVEfmt ', 8); data.writeUInt32LE(16, 16)
  data.writeUInt16LE(1, 20); data.writeUInt16LE(1, 22); data.writeUInt32LE(16000, 24); data.writeUInt32LE(32000, 28)
  data.writeUInt16LE(2, 32); data.writeUInt16LE(16, 34); data.write('data', 36); data.writeUInt32LE(4, 40); data.writeUInt16LE(1, 44); data.writeUInt16LE(2, 46)
  const audio = new Blob([new Uint8Array(data)], { type: 'audio/wav' })
  let captured: Request | undefined
  const client = createApiClient({ fetch: async request => {
    captured = request
    return new Response(JSON.stringify({ transcription_id: '22345678-1234-1234-1234-123456789012', text: '가상 전사', duration_seconds: 0.000125 }), { status: 201, headers: { 'Content-Type': 'application/json' } })
  } })
  const response = await client.POST('/journeys/{journey_id}/transcriptions', {
    params: { path: { journey_id: '12345678-1234-1234-1234-123456789012' }, header: { 'Idempotency-Key': '32345678-1234-1234-1234-123456789012' } },
    body: { audio }, bodySerializer: body => { const form = new FormData(); form.set('audio', body.audio, 'ignored.wav'); return form },
  })
  expect(parseTranscription(response.data).text).toBe('가상 전사')
  expect(captured!.headers.get('X-CSRF-Token')).toBe('token')
  const serialized = Buffer.from(await captured!.clone().arrayBuffer())
  const actual = JSON.parse(execFileSync(python, ['-I', fileURLToPath(new URL('contract-tests/export_audio_upload.py', root))], {
    input: JSON.stringify({ content_type: captured!.headers.get('content-type'), body: serialized.toString('base64') }),
    encoding: 'utf8', timeout: 20000, maxBuffer: 1024 * 1024, windowsHide: true,
  }))
  expect(actual).toEqual({ size: data.length, sha256: createHash('sha256').update(data).digest('hex'), content_type: 'audio/wav' })
})
