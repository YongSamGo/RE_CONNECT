import { createHash } from 'node:crypto'
import { readFile, writeFile, mkdir } from 'node:fs/promises'
import openapiTS, { astToString } from 'openapi-typescript'
import ts from 'typescript'

const root = new URL('../', import.meta.url)
const pin = JSON.parse(await readFile(new URL('api-contract.json', root), 'utf8'))
const canonical = new URL('../docs/api/openapi.yaml', root)
const output = new URL('src/api/schema.d.ts', root)
// Deliberately constant: local configuration must not put file data into any
// part of an outbound URL, even for an otherwise trusted download host.
const draftUrl = 'https://raw.githubusercontent.com/YongSamGo/RE_CONNECT/bc8cb82e74ad9ba361776f9c8cfe6927ae09a9ee/docs/api/openapi.yaml'
let source
try {
  source = await readFile(canonical, 'utf8')
  console.info('API types: checking repository docs/api/openapi.yaml')
} catch (error) {
  if (error.code !== 'ENOENT') throw error
  // Temporary until #117 lands. Never follow a moving branch or silently use a
  // stale generated file when the canonical contract changes.
  if (pin.repository !== 'YongSamGo/RE_CONNECT' || pin.commit !== 'bc8cb82e74ad9ba361776f9c8cfe6927ae09a9ee'
    || pin.path !== 'docs/api/openapi.yaml') throw new Error('Draft contract source does not match the fixed download target')
  const response = await fetch(draftUrl, { redirect: 'error', signal: AbortSignal.timeout(15000) })
  if (!response.ok) throw new Error('Pinned draft contract could not be loaded')
  source = await response.text()
  const digest = createHash('sha256').update(source).digest('hex')
  if (digest !== pin.sha256) throw new Error('Pinned draft contract hash does not match')
  console.info(`API types: using unmerged draft #117 at ${pin.commit}`)
}
// Normalize only text line endings for reproducible output on Windows/Linux.
const generated = '/** Generated from docs/api/openapi.yaml. Run npm run api:generate; do not edit. */\n'
  + astToString(await openapiTS(source.replace(/\r\n/g, '\n'), {
    alphabetize: true,
    transform(schema) {
      if (schema.type === 'string' && (schema.format === 'binary'
        || ['audio/wav', 'application/octet-stream'].includes(schema.contentMediaType))) {
        return ts.factory.createTypeReferenceNode('Blob')
      }
    },
  }))
if (process.argv.includes('--check')) {
  const current = await readFile(output, 'utf8')
  if (current.replace(/\r\n/g, '\n') !== generated) {
    console.error('API types differ from the contract. Run npm run api:generate and review the diff.')
    process.exitCode = 1
  }
} else {
  await mkdir(new URL('src/api/', root), { recursive: true })
  await writeFile(output, generated)
}
