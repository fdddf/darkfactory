import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'

export default defineConfig({
  plugins: [react(), tailwindcss()],
  server: {
    port: 5173,
    // The platform API is the Python service; in production both are served
    // from the same origin on the Nebius VM.
    proxy: {
      '/api': { target: 'http://127.0.0.1:8800', changeOrigin: true, ws: false },
    },
  },
  build: { outDir: 'dist', sourcemap: false },
})
