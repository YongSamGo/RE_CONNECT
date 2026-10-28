import { defineConfig } from 'vitest/config'

export default defineConfig({ test: { environment: 'node', include: ['contract-tests/**/*.test.ts'] } })
