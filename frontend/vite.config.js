import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    // All weather traffic is proxied through FastAPI. The browser never calls
    // Open-Meteo directly.
    proxy: { '/api': { target: 'http://localhost:8000', changeOrigin: true } },
  },
  build: {
    rollupOptions: {
      output: {
        // Firebase is intentionally absent: it is dynamically imported in
        // lib/firebase.js so an unconfigured build never loads the SDK.
        manualChunks: {
          charts: ['recharts'],
          map: ['leaflet', 'react-leaflet'],
        },
      },
    },
  },
})
