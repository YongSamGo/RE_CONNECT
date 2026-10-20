import { readFile, writeFile, mkdir } from 'node:fs/promises'
import openapiTS, { astToString } from 'openapi-typescript'
import ts from 'typescript'

const root = new URL('../', import.meta.url)
const canonical = new URL('../docs/api/openapi.yaml', root)
const output = new URL('src/api/schema.d.ts', root)
const source = await readFile(canonical, 'utf8')
console.info('API types: checking repository docs/api/openapi.yaml')
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
