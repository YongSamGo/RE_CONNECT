import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { expect, it } from 'vitest'
import { roleNames } from './roles'

it('matches the role catalog document names', () => {
  const catalog = JSON.parse(readFileSync(resolve(process.cwd(), '../docs/data/role-catalog.json'), 'utf8')) as { id: string; name: string }[]
  expect(roleNames).toEqual(Object.fromEntries(catalog.map(({ id, name }) => [id, name])))
})
