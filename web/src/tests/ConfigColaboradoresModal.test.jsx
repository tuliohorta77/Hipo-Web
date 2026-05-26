import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, waitFor, fireEvent } from '@testing-library/react'

// Mock do api antes do import do componente — mesmo padrão dos demais testes.
vi.mock('../api', () => ({
  default: {
    get: vi.fn(),
    post: vi.fn(),
    put: vi.fn(),
  },
  isAuthenticated: () => true,
  getUser: () => ({ nome: 'Tulio Horta', cargo: 'Franqueado' }),
  logout: vi.fn(),
  TOKEN_KEY: 'hipo_token',
  USER_KEY: 'hipo_user',
}))

import api from '../api'
import ConfigColaboradoresModal from '../components/ConfigColaboradoresModal'


// /carteira/colaboradores — 2 colaboradores; 1 vinculado, 1 sem vínculo.
const colaboradoresMock = [
  {
    id: 'colab-1',
    nome: 'Beatriz Silva',
    funcao: 'EC_HUNTER',
    funcao_origem: 'Executivo de Contas - HU',
    ativo: true,
    usuario_id: 'user-bea',
    usuario_email: 'beatriz@omie.com.vc',
    usuario_nome: 'Beatriz Silva',
  },
  {
    id: 'colab-2',
    nome: 'Marcos Silva',
    funcao: 'OUTROS',
    funcao_origem: null,
    ativo: true,
    usuario_id: null,
    usuario_email: null,
    usuario_nome: null,
  },
]

// /carteira/usuarios-ativos — 2 usuários ativos.
const usuariosMock = [
  { id: 'user-bea', nome: 'Beatriz Silva', email: 'beatriz@omie.com.vc' },
  { id: 'user-carlos', nome: 'Carlos Lima', email: 'carlos@omie.com.vc' },
]

function setupApi({ colaboradores = colaboradoresMock, usuarios = usuariosMock } = {}) {
  api.get.mockImplementation((url) => {
    if (url === '/carteira/colaboradores') {
      return Promise.resolve({ data: colaboradores })
    }
    if (url === '/carteira/usuarios-ativos') {
      return Promise.resolve({ data: usuarios })
    }
    return Promise.reject(new Error(`URL não mockada: ${url}`))
  })
  api.put.mockResolvedValue({ data: {} })
}


describe('ConfigColaboradoresModal (v1.3.0 etapa 3)', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('não renderiza nada quando aberto é false', () => {
    const { container } = render(
      <ConfigColaboradoresModal aberto={false} onFechar={() => {}} onSalvo={() => {}} />
    )
    expect(container.firstChild).toBeNull()
  })

  it('carrega colaboradores e usuários ativos ao abrir', async () => {
    setupApi()
    render(
      <ConfigColaboradoresModal aberto={true} onFechar={() => {}} onSalvo={() => {}} />
    )
    await waitFor(() => {
      expect(screen.getByText('Beatriz Silva')).toBeInTheDocument()
    })
    const urls = api.get.mock.calls.map(([u]) => u)
    expect(urls).toContain('/carteira/colaboradores')
    expect(urls).toContain('/carteira/usuarios-ativos')
  })

  it('colaborador sem vínculo mostra o aviso "sem usuário"', async () => {
    setupApi()
    render(
      <ConfigColaboradoresModal aberto={true} onFechar={() => {}} onSalvo={() => {}} />
    )
    await waitFor(() => {
      expect(screen.getByText('Marcos Silva')).toBeInTheDocument()
    })
    // Marcos não tem usuario_id -> aviso visível.
    expect(
      screen.getByText(/não aparece para nenhum hunter\/farmer/i)
    ).toBeInTheDocument()
  })

  it('PUT envia funcao + usuario_id quando o vínculo é alterado', async () => {
    setupApi()
    render(
      <ConfigColaboradoresModal aberto={true} onFechar={() => {}} onSalvo={() => {}} />
    )
    await waitFor(() => screen.getByText('Marcos Silva'))

    // O 2º select é o do Marcos (1º é o da Beatriz).
    const selects = screen.getAllByRole('combobox')
    // Vincula o Marcos ao Carlos.
    fireEvent.change(selects[1], { target: { value: 'user-carlos' } })

    fireEvent.click(screen.getByText('Salvar'))

    await waitFor(() => {
      expect(api.put).toHaveBeenCalledWith(
        '/carteira/colaboradores/colab-2',
        expect.objectContaining({ usuario_id: 'user-carlos' })
      )
    })
  })

  it('exibe a mensagem de erro 409 quando o usuário já está vinculado', async () => {
    setupApi()
    const erro409 = new Error('conflict')
    erro409.response = {
      status: 409,
      data: { detail: "Este usuário já está vinculado ao colaborador 'Beatriz Silva'." },
    }
    api.put.mockRejectedValueOnce(erro409)

    render(
      <ConfigColaboradoresModal aberto={true} onFechar={() => {}} onSalvo={() => {}} />
    )
    await waitFor(() => screen.getByText('Marcos Silva'))

    const selects = screen.getAllByRole('combobox')
    fireEvent.change(selects[1], { target: { value: 'user-bea' } })
    fireEvent.click(screen.getByText('Salvar'))

    await waitFor(() => {
      expect(screen.getByText(/já está vinculado ao colaborador/i)).toBeInTheDocument()
    })
  })
})
