import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig({
  plugins: [react()],
  test: {
    environment: 'jsdom',
    globals: true,
    setupFiles: './src/tests/setup.js',

    // Os limites padrão do vitest (5s por teste) e do testing-library (1s nas
    // queries findBy*) são folgados numa máquina ociosa e apertados numa
    // máquina carregada. Numa rodada fria aqui, `environment` sozinho levou
    // 117s e seis testes caíram por timeout — sem nenhuma mudança de código.
    // Não é o teste que está lento: é o ambiente. Runner do CI tem o mesmo
    // perfil.
    testTimeout: 20000,
    hookTimeout: 20000,

    coverage: {
      provider: 'v8',
      reporter: ['text', 'lcov'],
      include: ['src/**/*.{js,jsx}'],
      exclude: ['src/tests/**', 'src/main.jsx'],
    },
  },
})
