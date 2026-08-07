import '@testing-library/jest-dom'
import { configure } from '@testing-library/react'

// O padrão é 1000ms. Toda query `findBy*` espera dois ciclos de promise da
// API mockada mais o re-render; em máquina carregada isso passa de 1s e o
// teste falha por tempo, não por comportamento. 8s dá margem sem esconder
// travamento de verdade — teste que trava bate no testTimeout de 20s do
// vitest.config.js e falha do mesmo jeito.
configure({ asyncUtilTimeout: 8000 })
