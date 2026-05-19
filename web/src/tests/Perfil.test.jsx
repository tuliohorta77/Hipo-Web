import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'

vi.mock('../api', () => ({
  default: {
    get: vi.fn(),
    post: vi.fn(),
    put: vi.fn(),
  },
  isAuthenticated: () => true,
  getUser: () => ({
    nome: 'Aline Martins',
    email: 'aline.martins@omie.com.vc',
    cargo: 'Farmer',
    modulos: ['carteira'],
  }),
  logout: vi.fn(),
  TOKEN_KEY: 'hipo_token',
  USER_KEY: 'hipo_user',
}))

import api from '../api'
import Perfil from '../pages/Perfil'

function renderPerfil() {
  return render(<MemoryRouter><Perfil /></MemoryRouter>)
}

beforeEach(() => {
  vi.clearAllMocks()
})

describe('Página Perfil', () => {
  it('exibe nome, email e cargo do usuário', () => {
    renderPerfil()
    expect(screen.getByText('Aline Martins')).toBeInTheDocument()
    expect(screen.getByText('aline.martins@omie.com.vc')).toBeInTheDocument()
    expect(screen.getByText('Farmer')).toBeInTheDocument()
  })

  it('exibe módulos acessíveis (Carteira pra Farmer)', () => {
    renderPerfil()
    expect(screen.getByText('Carteira')).toBeInTheDocument()
    // PEX, POs etc. NÃO devem aparecer
    expect(screen.queryByText('PEX')).not.toBeInTheDocument()
    expect(screen.queryByText('POs')).not.toBeInTheDocument()
  })

  it('valida nova senha e confirmação batem', async () => {
    renderPerfil()
    fireEvent.change(screen.getByLabelText(/Senha atual/i), { target: { value: '123456' } })
    fireEvent.change(screen.getByLabelText(/Nova senha/i),  { target: { value: 'novanova' } })
    fireEvent.change(screen.getByLabelText(/Confirmar/i),    { target: { value: 'diferente' } })
    fireEvent.click(screen.getByRole('button', { name: /Alterar senha/i }))

    await waitFor(() => {
      expect(screen.getByText(/confirmação não bate/i)).toBeInTheDocument()
    })
    // Não chamou API porque validação local falhou
    expect(api.put).not.toHaveBeenCalled()
  })

  it('valida que nova senha tem pelo menos 6 caracteres', async () => {
    renderPerfil()
    fireEvent.change(screen.getByLabelText(/Senha atual/i), { target: { value: '123456' } })
    fireEvent.change(screen.getByLabelText(/Nova senha/i),  { target: { value: 'abc' } })
    fireEvent.change(screen.getByLabelText(/Confirmar/i),    { target: { value: 'abc' } })
    fireEvent.click(screen.getByRole('button', { name: /Alterar senha/i }))

    await waitFor(() => {
      expect(screen.getByText(/pelo menos 6 caracteres/i)).toBeInTheDocument()
    })
  })

  it('troca senha com sucesso e mostra mensagem', async () => {
    api.put.mockResolvedValue({ data: { message: 'Senha alterada com sucesso.' } })

    renderPerfil()
    fireEvent.change(screen.getByLabelText(/Senha atual/i), { target: { value: '123456' } })
    fireEvent.change(screen.getByLabelText(/Nova senha/i),  { target: { value: 'novanova' } })
    fireEvent.change(screen.getByLabelText(/Confirmar/i),    { target: { value: 'novanova' } })
    fireEvent.click(screen.getByRole('button', { name: /Alterar senha/i }))

    await waitFor(() => {
      expect(api.put).toHaveBeenCalledWith('/auth/senha', {
        senha_atual: '123456',
        nova_senha: 'novanova',
      })
      expect(screen.getByText(/Senha alterada com sucesso/i)).toBeInTheDocument()
    })
  })

  it('mostra erro do backend quando troca falha (senha atual incorreta)', async () => {
    api.put.mockRejectedValue({
      response: { data: { detail: 'Senha atual incorreta.' } },
      message: 'Request failed',
    })

    renderPerfil()
    fireEvent.change(screen.getByLabelText(/Senha atual/i), { target: { value: 'errada' } })
    fireEvent.change(screen.getByLabelText(/Nova senha/i),  { target: { value: 'novanova' } })
    fireEvent.change(screen.getByLabelText(/Confirmar/i),    { target: { value: 'novanova' } })
    fireEvent.click(screen.getByRole('button', { name: /Alterar senha/i }))

    await waitFor(() => {
      expect(screen.getByText(/Senha atual incorreta/i)).toBeInTheDocument()
    })
  })
})
