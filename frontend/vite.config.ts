import tailwindcss from '@tailwindcss/vite'
import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

// https://vite.dev/config/
export default defineConfig({
  plugins: [react(), tailwindcss()],
  // Locally the API runs on :8000; on Railway the app calls VITE_API_URL instead
  server: { proxy: { '/api': 'http://localhost:8000' } },
})
