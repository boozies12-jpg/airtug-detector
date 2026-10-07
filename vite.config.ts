import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'

// https://vite.dev/config/
export default defineConfig({
  plugins: [
    react(),
    tailwindcss()
  ],
  server: {
    host: '0.0.0.0',
    port: 41732,
    proxy: {
      '/api': {
        target: 'http://127.0.0.1:41730',
        changeOrigin: true
      },
      '/ws': {
        target: 'ws://127.0.0.1:41730',
        ws: true
      }
    }
  }
})
