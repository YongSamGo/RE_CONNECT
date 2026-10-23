import { spawn, type ChildProcess } from 'node:child_process'
import { once } from 'node:events'
import { createServer as createSocket } from 'node:net'
import { fileURLToPath } from 'node:url'
import { createServer, type ViteDevServer } from 'vite'
import { afterAll, beforeAll, expect, it, vi } from 'vitest'
import { createApiClient } from '../src/api/client'
import { ApiError } from '../src/api/errors'
import { parseRegionCatalog } from '../src/features/regions/catalog'

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

it('an unimplemented public API returns the real normalized error rather than SPA HTML', async () => {
  try {
    await createApiClient().GET('/opportunities')
    expect.fail('Missing endpoint must not become a fake success')
  } catch (error) {
    expect(error).toBeInstanceOf(ApiError)
    expect(error).toMatchObject({ code: 'NOT_FOUND', status: 404 })
  }
  const response = await fetch(`${origin}/api/v1/opportunities`)
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
