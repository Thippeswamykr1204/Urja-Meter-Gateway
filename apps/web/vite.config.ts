import { defineConfig, loadEnv, type ProxyOptions } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, '../../', '')
  const readKey = process.env.API_READ_KEY ?? env.API_READ_KEY ?? 'local-development-read-key'
  const adminKey = process.env.API_ADMIN_KEY ?? env.API_ADMIN_KEY ?? 'local-development-admin-key'
  const target = process.env.API_PROXY_TARGET ?? env.API_PROXY_TARGET ?? 'http://127.0.0.1:8000'
  const withServerKey = (apiKey: string): ProxyOptions => ({
    target,
    changeOrigin: true,
    configure(proxy) {
      proxy.on('proxyReq', (proxyRequest) => {
        proxyRequest.setHeader('X-API-Key', apiKey)
      })
    },
  })
  return {
    envDir: '../../',
    plugins: [react()],
    server: {
      port: 5173,
      host: '127.0.0.1',
      proxy: {
        '/api/v1/refresh': withServerKey(adminKey),
        '/api': withServerKey(readKey),
        '/health': withServerKey(readKey),
        '/ready': withServerKey(readKey),
      },
    },
  }
})
