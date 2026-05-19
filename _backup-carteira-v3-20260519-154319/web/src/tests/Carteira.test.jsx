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
  getUser: () => ({ nome: 'Tester', email: 'tester@hipo.com', cargo: 'ADM' }),
  logout: vi.fn(),
  TOKEN_KEY: 'hipo_token',
  USER_KEY: 'hipo_user',
}))

import api from '../api'
import Carteira from '../pages/Carteira'

// ── Mocks de dados ───────────────────────────────────────────────

const mockResumo = {
  hunter:  { total_grupos: 18, meta_atingida: 15, compliance_pct: 83.3,
             com_tarefa_atrasada: 5, sem_tarefa_futura: 3, leads_no_mes: 7 },
  farmer:  { total_grupos: 21, meta_atingida: 16, compliance_pct: 76.2,
             com_tarefa_atrasada: 8, sem_tarefa_futura: 4, leads_no_mes: 23 },
  outros:  { total_grupos: 2, meta_atingida: 0, compliance_pct: 0,
             com_tarefa_atrasada: 0, sem_tarefa_futura: 2, leads_no_mes: 0 },
  totais: { grupos_total: 41, cnpjs_total: 50, tarefas_total: 200, colaboradores: 5 },
  ultima_carteira: '2026-05-18T10:00:00Z',
  ultima_tarefas:  '2026-05-18T11:00:00Z',
}

const mockHunter = {
  total: 2,
  linhas: [
    {
      colaborador_id: 'patrick-uuid',
      nome: 'Patrick',
      total_grupos: 10,
      meta_atingida: 9,
      tarefas_atrasadas: 1,
      sem_tarefa_futura: 1,
      leads_no_mes: 4,
      compliance_pct: 90.0,
    },
    {
      colaborador_id: 'caio-uuid',
      nome: 'Caio',
      total_grupos: 8,
      meta_atingida: 6,
      tarefas_atrasadas: 3,
      sem_tarefa_futura: 2,
      leads_no_mes: 3,
      compliance_pct: 75.0,
    },
  ],
}

const mockFarmer = {
  total: 1,
  linhas: [
    {
      colaborador_id: 'aline-uuid',
      nome: 'Aline',
      total_contadores: 10,
      semanas: [
        { key: '2026-W18', label: 'S1', com_reuniao: 5, sem_reuniao: 5, pendente: 0 },
        { key: '2026-W19', label: 'S2', com_reuniao: 10, sem_reuniao: 0, pendente: 0 },
        { key: '2026-W20', label: 'S3', com_reuniao: 9, sem_reuniao: 1, pendente: 0 },
        { key: '2026-W21', label: 'S4', com_reuniao: 3, sem_reuniao: 0, pendente: 7 },
      ],
      tarefas_atrasadas: 5,
      tarefas_futuras: 2,
      leads_no_mes: 12,
    },
  ],
}

const mockGruposPatrick = {
  colaborador: { id: 'patrick-uuid', nome: 'Patrick', funcao: 'EC_HUNTER' },
  total: 2,
  grupos: [
    {
      id_grupo: 'G1', nome_grupo: 'CONTAB ALFA',
      contabilidade_principal: 'CONTAB ALFA', cidade_uf: 'SP/SP',
      parceria: 'Parceiro', qtd_cnpj: 1,
      meta_atingida: true, tarefas_atrasadas: 0, tarefas_futuras: 1,
      leads_no_mes: 0,
    },
    {
      id_grupo: 'G2', nome_grupo: 'BETA ASSESSORIA',
      contabilidade_principal: 'BETA ASSESSORIA', cidade_uf: 'Guarulhos/SP',
      parceria: 'Não Parceiro', qtd_cnpj: 2,
      meta_atingida: false, tarefas_atrasadas: 2, tarefas_futuras: 0,
      leads_no_mes: 0,
    },
  ],
}

function renderCarteira() {
  return render(<MemoryRouter><Carteira /></MemoryRouter>)
}

// ── Setup ────────────────────────────────────────────────────────

beforeEach(() => {
  vi.clearAllMocks()
  api.get.mockImplementation((url) => {
    if (url === '/carteira/resumo')             return Promise.resolve({ data: mockResumo })
    if (url === '/carteira/dashboard/hunter')   return Promise.resolve({ data: mockHunter })
    if (url === '/carteira/dashboard/farmer')   return Promise.resolve({ data: mockFarmer })
    if (url.startsWith('/carteira/grupos?funcao=OUTROS')) {
      return Promise.resolve({ data: { total: 0, grupos: [] } })
    }
    if (url === '/carteira/colaboradores/patrick-uuid/grupos') {
      return Promise.resolve({ data: mockGruposPatrick })
    }
    if (url === '/carteira/historico')          return Promise.resolve({ data: [] })
    return Promise.resolve({ data: null })
  })
})


describe('Página Carteira (v2 — dashboard por colaborador)', () => {
  it('renderiza o título e botões de upload', async () => {
    renderCarteira()
    expect(screen.getByRole('heading', { level: 1, name: 'Carteira' })).toBeInTheDocument()
    await waitFor(() => expect(api.get).toHaveBeenCalledWith('/carteira/dashboard/hunter'))
  })

  it('exibe abas Hunter / Farmer / Outros com contadores', async () => {
    renderCarteira()
    await waitFor(() => {
      // contadores nos chips das abas
      const chips = Array.from(document.querySelectorAll('button .rounded-full'))
        .map((n) => n.textContent.trim())
      expect(chips).toEqual(expect.arrayContaining(['2', '1', '0']))
    })
  })

  it('lista colaboradores Hunter por padrão', async () => {
    renderCarteira()
    await waitFor(() => {
      expect(screen.getByText('Patrick')).toBeInTheDocument()
      expect(screen.getByText('Caio')).toBeInTheDocument()
    })
  })

  it('mostra KPIs do topo da aba Hunter', async () => {
    renderCarteira()
    await waitFor(() => {
      // 18 grupos totais, 15 com meta atingida
      expect(screen.getByText('18')).toBeInTheDocument()
      expect(screen.getByText(/83\.3% de compliance/i)).toBeInTheDocument()
    })
  })

  it('clica no colaborador Patrick e mostra drilldown dos grupos', async () => {
    renderCarteira()
    await waitFor(() => screen.getByText('Patrick'))

    fireEvent.click(screen.getByText('Patrick'))

    await waitFor(() => {
      expect(api.get).toHaveBeenCalledWith(
        '/carteira/colaboradores/patrick-uuid/grupos'
      )
      expect(screen.getByText('CONTAB ALFA')).toBeInTheDocument()
      expect(screen.getByText('BETA ASSESSORIA')).toBeInTheDocument()
    })
  })

  it('clica novamente no Patrick e o drilldown fecha', async () => {
    renderCarteira()
    await waitFor(() => screen.getByText('Patrick'))

    fireEvent.click(screen.getByText('Patrick'))
    await waitFor(() => expect(screen.getByText('CONTAB ALFA')).toBeInTheDocument())

    fireEvent.click(screen.getByText('Patrick'))
    await waitFor(() => {
      expect(screen.queryByText('CONTAB ALFA')).not.toBeInTheDocument()
    })
  })

  it('troca para aba Farmer e mostra Aline com semanas', async () => {
    renderCarteira()
    await waitFor(() => screen.getByText('Patrick'))

    fireEvent.click(screen.getByRole('button', { name: /Farmer/i }))

    await waitFor(() => {
      expect(screen.getByText('Aline')).toBeInTheDocument()
      expect(screen.getByText(/10 contadores/i)).toBeInTheDocument()
      // Labels das semanas (S1 a S4) aparecem em quaisquer das bolinhas
      expect(screen.getAllByText('S1').length).toBeGreaterThan(0)
      expect(screen.getAllByText('S4').length).toBeGreaterThan(0)
    })
  })

  it('aplica filtro de busca por colaborador', async () => {
    renderCarteira()
    await waitFor(() => screen.getByText('Patrick'))

    const busca = screen.getByPlaceholderText(/Buscar colaborador/i)
    fireEvent.change(busca, { target: { value: 'caio' } })

    await waitFor(() => {
      expect(screen.queryByText('Patrick')).not.toBeInTheDocument()
      expect(screen.getByText('Caio')).toBeInTheDocument()
    })
  })

  it('faz upload de carteira e mostra mensagem de sucesso', async () => {
    api.post.mockResolvedValue({
      data: { message: 'Carteira atualizada: 633 CNPJs CNAE Contábil.' }
    })

    renderCarteira()
    await waitFor(() => expect(api.get).toHaveBeenCalled())

    const inputs = document.querySelectorAll('input[type="file"]')
    expect(inputs.length).toBeGreaterThanOrEqual(2)
    // O botão "Carteira" é o penúltimo input file
    const inputCarteira = inputs[inputs.length - 2]
    const file = new File(['x'], 'carteira.xlsx', {
      type: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
    })
    fireEvent.change(inputCarteira, { target: { files: [file] } })

    await waitFor(() => {
      expect(api.post).toHaveBeenCalledWith(
        '/carteira/upload-carteira',
        expect.any(FormData),
        expect.any(Object)
      )
      expect(screen.getByText(/633 CNPJs/)).toBeInTheDocument()
    })
  })

  it('mostra mensagem amigável quando aba Outros está vazia', async () => {
    renderCarteira()
    await waitFor(() => screen.getByText('Patrick'))

    fireEvent.click(screen.getByRole('button', { name: /Outros/i }))
    await waitFor(() => {
      expect(screen.getByText(/Nenhum grupo nessa aba/i)).toBeInTheDocument()
    })
  })
})
