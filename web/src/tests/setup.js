import '@testing-library/jest-dom'
import { vi } from 'vitest'

// Mock do axios para todos os testes
vi.mock('axios', () => ({
  default: {
    get: vi.fn(),
    post: vi.fn(),
  },
}))
