import { defineConfig } from 'vitest/config'
import react from '@vitejs/plugin-react'

const backend = process.env.BACKEND_URL ?? 'http://127.0.0.1:8000'

export default defineConfig({
  plugins: [react()],
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
