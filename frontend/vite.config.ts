import { defineConfig } from 'vitest/config'
import react from '@vitejs/plugin-react'

const backend = process.env.BACKEND_URL ?? 'http://127.0.0.1:8000'

export default defineConfig({
  plugins: [react()],
  // 电路图：netlistsvg 依赖的 elkjs 默认入口会去找 Node 专用的 webworker-threads，浏览器里改用它自带的浏览器版
  resolve: { alias: { elkjs: 'elkjs/lib/elk.bundled.js' } },
  server: {
    port: Number(process.env.FRONTEND_PORT ?? 5173),
    strictPort: true,
    proxy: { '/api': { target: backend, changeOrigin: false } },
  },
  preview: {
    port: Number(process.env.FRONTEND_PORT ?? 4173),
    strictPort: true,
    proxy: { '/api': { target: backend, changeOrigin: false } },
  },
  build: { chunkSizeWarningLimit: 4000 },
  test: {
    environment: 'jsdom',
    globals: true,
    setupFiles: ['./src/test/setup.ts'],
    include: ['src/**/*.test.{ts,tsx}'],
    css: false,
  },
})
