// 端到端测试：自动启动后端（全新 SQLite 库 + 演示数据 + worker）和前端开发服务器
import { defineConfig } from '@playwright/test'

export default defineConfig({
  testDir: './e2e',
  timeout: 240_000,
  expect: { timeout: 30_000 },
  workers: 1,
  reporter: [['list']],
  use: {
    baseURL: 'http://localhost:5173',
    viewport: { width: 1440, height: 1000 },
    trace: 'off',
    actionTimeout: 20_000,
    locale: 'zh-CN',
    timezoneId: 'Asia/Shanghai',
  },
  webServer: [
    {
      command: 'bash e2e/start-backend.sh',
      url: 'http://127.0.0.1:8000/api/health',
      reuseExistingServer: !process.env.CI,
      timeout: 180_000,
    },
    {
      command: 'npx vite --port 5173',
      url: 'http://localhost:5173',
      reuseExistingServer: !process.env.CI,
      timeout: 60_000,
    },
  ],
})
