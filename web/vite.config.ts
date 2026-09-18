import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react-swc'
import tailwindcss from '@tailwindcss/vite'

// Static build: every number is precomputed by the Python pipeline and
// imported as JSON, so the deployed site does no computation at all.
export default defineConfig({
  base: './',
  plugins: [react(), tailwindcss()],
  // In development the upload page talks to the local API (uvicorn api.main:app).
  server: { proxy: { '/api': 'http://localhost:8000' } },
  preview: { proxy: { '/api': 'http://localhost:8000' } },
  build: {
    target: 'es2022',
    rollupOptions: {
      output: {
        // React changes far less often than the data; a separate chunk
        // stays cached across re-deploys of new analysis results.
        manualChunks: (id) => (id.includes('node_modules') ? 'vendor' : undefined),
      },
    },
  },
})
