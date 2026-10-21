import { spawn, type ChildProcess } from 'node:child_process'
import { once } from 'node:events'
import { createServer as createSocket } from 'node:net'
import { fileURLToPath } from 'node:url'
import { createServer, type ViteDevServer } from 'vite'
import { readFileSync } from 'node:fs'
import { Ajv2020 } from 'ajv/dist/2020'
import { JSON_SCHEMA, load } from 'js-yaml'
import { afterAll, beforeAll, expect, it, vi } from 'vitest'
import { createApiClient } from '../src/api/client'
import { ApiError } from '../src/api/errors'
import { parseRegionCatalog } from '../src/features/regions/catalog'
import { parsePreparation } from '../src/features/preparation/official'

const root = new URL('../', import.meta.url)
const python = process.env.CONTRACT_PYTHON || fileURLToPath(new URL(process.platform === 'win32' ? '../backend/.venv/Scripts/python.exe' : '../backend/.venv/bin/python', root))
let backend: ChildProcess | undefined
let exited: Promise<unknown> | undefined
let frontend: ViteDevServer | undefined
let origin: string

async function freePort() {
  const socket = createSocket()
  socket.listen(0, '127.0.0.1')
  await once(socket, 'listening')
  const address = socket.address()
  if (!address || typeof address === 'string') throw new Error('No test port')
  await new Promise<void>((resolve, reject) => socket.close(error => error ? reject(error) : resolve()))
  return address.port
}

beforeAll(async () => {
  const port = await freePort()
  backend = spawn(python, ['-I', fileURLToPath(new URL('contract-tests/serve_app.py', root)), String(port)], { stdio: 'ignore', windowsHide: true })
  exited = new Promise(resolve => { backend!.once('exit', resolve); backend!.once('error', resolve) })
  let ready = false
  for (let attempt = 0; attempt < 80; attempt++) {
    if (backend.exitCode !== null || backend.pid === undefined) throw new Error('Backend test process did not start')
    try { ready = (await fetch(`http://127.0.0.1:${port}/health/live`, { signal: AbortSignal.timeout(500) })).ok } catch { /* booting */ }
    if (ready) break
    await new Promise(resolve => setTimeout(resolve, 100))
  }
  if (!ready) throw new Error('Backend test readiness timed out')
  frontend = await createServer({
    root: fileURLToPath(root), configFile: fileURLToPath(new URL('vite.config.ts', root)),
    server: { host: '127.0.0.1', port: 0, proxy: { '/api/v1': { target: `http://127.0.0.1:${port}`, changeOrigin: false } } },
  })
  await frontend.listen()
  const address = frontend.httpServer?.address()
  if (!address || typeof address === 'string') throw new Error('No frontend test port')
  origin = `http://127.0.0.1:${address.port}`
  // The existing browser client uses location and cookie only. Requests still
  // use real Node fetch, real HTTP, Vite's proxy and the actual app middleware.
  vi.stubGlobal('window', { location: new URL(origin) })
  vi.stubGlobal('document', { cookie: '' })
}, 20000)

afterAll(async () => {
  vi.unstubAllGlobals()
  await frontend?.close()
  if (backend && backend.exitCode === null) backend.kill()
  await exited
})

it('existing API client reads the real region catalog through the frontend origin', async () => {
  const response = await createApiClient().GET('/regions')
  expect(response.response.url).toBe(`${origin}/api/v1/regions`)
  expect(response.response.headers.get('x-request-id')).toMatch(/^req_/)
  const catalog = parseRegionCatalog(response.data)
  expect(catalog.provinces).toHaveLength(3)
  expect(catalog.provinces.find(item => item.id === 'seoul')?.districts.some(item => item.id === 'seongdong')).toBe(true)
})

it('an absent public opportunity returns the real normalized error rather than SPA HTML', async () => {
  const id = '00000000-0000-0000-0000-000000000004'
  try {
    await createApiClient().GET('/opportunities/{opportunity_id}', { params: { path: { opportunity_id: id } } })
    expect.fail('Missing endpoint must not become a fake success')
  } catch (error) {
    expect(error).toBeInstanceOf(ApiError)
    expect(error).toMatchObject({ code: 'NOT_FOUND', status: 404 })
  }
  const response = await fetch(`${origin}/api/v1/opportunities/${id}`)
  expect(response.status).toBe(404)
  expect(response.headers.get('content-type')).toContain('application/json')
  expect(await response.json()).toMatchObject({ code: 'NOT_FOUND', request_id: expect.stringMatching(/^req_/) })
})

it('screen routes still receive the SPA document instead of being sent to the backend', async () => {
  const response = await fetch(`${origin}/profile`)
  expect(response.status).toBe(200)
  expect(response.headers.get('content-type')).toContain('text/html')
  expect(await response.text()).toContain('id="root"')
})

it.each([
  ['00000000-0000-0000-0000-000000000001', 'online', null],
  ['00000000-0000-0000-0000-000000000002', 'phone', []],
  ['00000000-0000-0000-0000-000000000003', 'mixed', ['공식 신청서']],
] as const)('reads official preparation from the real SQL-backed API through Vite: %s', async (id, method, documents) => {
  const response = await createApiClient().GET('/opportunities/{opportunity_id}/preparation', {
    params: { path: { opportunity_id: id } },
  })
  expect(response.response.status).toBe(200)
  expect(response.response.url).toBe(`${origin}/api/v1/opportunities/${id}/preparation`)
  expect(response.response.headers.get('cache-control')).toBe('no-store')
  const parsed = parsePreparation(response.data, id)
  expect(parsed.application_method).toBe(method)
  expect(parsed.required_documents).toEqual(documents)
  expect(parsed.opportunity).toEqual({ id, version: 1 })
  expect(parsed.application_instructions).toBe('가상 공고의 공식 안내를 확인해 주세요.')

  type Contract = { components: Record<string, unknown> }
  const contract = load(readFileSync(new URL('../docs/api/openapi.yaml', root), 'utf8'), { schema: JSON_SCHEMA }) as Contract
  const ajv = new Ajv2020({ strict: true, allErrors: true }).addKeyword('components')
    .addFormat('uuid', /^[a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12}$/i)
    .addFormat('date', value => {
      const date = new Date(`${value}T00:00:00Z`)
      return /^\d{4}-\d{2}-\d{2}$/.test(value) && Number.isFinite(date.getTime()) && date.toISOString().slice(0, 10) === value
    })
    .addFormat('date-time', value => Number.isFinite(Date.parse(value)) && /(?:Z|[+-]\d{2}:\d{2})$/.test(value))
    .addFormat('uri', value => { try { return Boolean(new URL(value).protocol) } catch { return false } })
  const validate = ajv.compile({ $ref: '#/components/schemas/Preparation', components: contract.components })
  expect(validate(response.data), JSON.stringify(validate.errors)).toBe(true)
  expect(validate({ ...response.data, invented_document: '추정 서류' })).toBe(false)
})
