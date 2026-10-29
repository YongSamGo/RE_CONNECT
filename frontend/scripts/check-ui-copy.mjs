import { readdir, readFile } from 'node:fs/promises'
import path from 'node:path'
import { fileURLToPath } from 'node:url'
import ts from 'typescript'

// This checks authored source text only. It does not read runtime user data,
// change copy, or certify visual quality or accessibility.
const root = fileURLToPath(new URL('../', import.meta.url))
const sourceRoot = path.join(root, 'src')
const reportOnly = process.argv.includes('--report')
const forbidden = /[\u00b7\u318d\u30fb]/u
const findings = []

async function visitDirectory(directory) {
  const entries = await readdir(directory, { withFileTypes: true })
  for (const entry of entries.sort((a, b) => a.name.localeCompare(b.name))) {
    const absolute = path.join(directory, entry.name)
    if (entry.isDirectory()) {
      if (entry.name !== 'test') await visitDirectory(absolute)
      continue
    }
    if (!/\.(?:ts|tsx)$/.test(entry.name) || /(?:\.test\.|\.d\.ts$|^test-fixtures\.)/.test(entry.name)) continue
    const contents = await readFile(absolute, 'utf8')
    const source = ts.createSourceFile(absolute, contents, ts.ScriptTarget.Latest, true)
    function walk(node) {
      if (ts.isJsxText(node) || ts.isStringLiteralLike(node)
        || ts.isTemplateHead(node) || ts.isTemplateMiddle(node) || ts.isTemplateTail(node)) {
        if (forbidden.test(node.text)) {
          const { line } = source.getLineAndCharacterOfPosition(node.getStart(source))
          findings.push({ file: path.relative(root, absolute).split(path.sep).join('/'), line: line + 1,
            text: node.text.trim().replace(/\s+/g, ' ').slice(0, 160) })
        }
      }
      ts.forEachChild(node, walk)
    }
    walk(source)
  }
}

await visitDirectory(sourceRoot)
for (const item of findings) process.stdout.write(`${item.file}:${item.line} ${item.text}\n`)
process.stdout.write(`UI copy: ${findings.length} candidate(s). Review authored text; preserve official source content.\n`)
if (findings.length && !reportOnly) process.exitCode = 1
