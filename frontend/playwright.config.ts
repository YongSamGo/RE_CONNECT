import { defineConfig } from '@playwright/test'

export default defineConfig({
  testDir: './browser-tests',
  fullyParallel: false,
  workers: 1,
  reporter: 'list',
  use: { baseURL: 'http://127.0.0.1:5178', browserName: 'chromium', reducedMotion: 'reduce' },
  webServer: { command: 'npm run dev -- --port 5178 --strictPort', url: 'http://127.0.0.1:5178', reuseExistingServer: false, timeout: 30000 },
  expect: { toHaveScreenshot: { animations: 'disabled', maxDiffPixelRatio: 0.005 } },
})
