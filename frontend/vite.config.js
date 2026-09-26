import { execFileSync } from 'node:child_process'
import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

function gitOutput(args) {
  try {
    return execFileSync('git', args, {
      cwd: new URL('..', import.meta.url),
      encoding: 'utf8',
      timeout: 2000,
      stdio: ['ignore', 'pipe', 'ignore'],
    }).trim()
  } catch {
    return null
  }
}

const commit = gitOutput(['rev-parse', '--short=12', 'HEAD'])
const dirty = commit ? Boolean(gitOutput(['status', '--porcelain', '--untracked-files=no'])) : false

export default defineConfig(({ command }) => ({
  plugins: [react()],
  define: {
    'import.meta.env.VITE_BUILD_INFO': JSON.stringify({
      commit,
      dirty,
      generatedAt: new Date().toISOString(),
      command,
    }),
  },
  build: {
    rollupOptions: {
      output: {
        manualChunks: {
          react: ['react', 'react-dom', 'react-router-dom'],
          recharts: ['recharts'],
        },
      },
    },
  },
  server: {
    port: 5173,
    proxy: {
      '/api': {
        target: 'http://127.0.0.1:8000',
        changeOrigin: true,
      },
    },
  },
}))
