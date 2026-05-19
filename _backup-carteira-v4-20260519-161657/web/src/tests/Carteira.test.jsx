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
  outros:  { total_grupos: 0, meta_atingida: 0, compliance_pct: 0,
             com_tarefa_atrasada: 0, sem_tarefa_futura: 0, leads_no_mes: 0 },
  totais: { grupos_total: 39, cnpjs_total: 50, tarefas_total: 200, colaboradores: 3 },
  ultima_carteira: '2026-05-18T10:00:00Z',
  ultima_tarefas:  '2026-05-18T11:00:00Z',
}

const grupoPatrickA = {
  id_grupo: 'P_G1',
  nome_grupo: 'CONTAB ALFA',
  qtd_cnpj: 1,
  parceria: 'Parceiro',
  contabilidade_principal: 'CONTAB ALFA',
  cidade_uf: 'SP/SP',
  colaborador_nome: 'Patrick',
  colaboradores_multiplos: false,
  funcao: 'EC_HUNTER',
  leads_no_mes: 2,
  tarefas_mes_total: 1,
  tarefas_atrasadas: 0,
  tarefas_futuras: 1,
  reunioes_mes: 0,
  timeline: [{ key: '2026-05', label: 'Mai/26', status: 'ok', count: 1 }],
  meta_atingida: true,
  score: null,
}

const grupoPatrickB = {
  id_grupo: 'P_G2',
  nome_grupo: 'BETA ASSESSORIA',
  qtd_cnpj: 2,
  parceria: 'Não Parceiro',
  contabilidade_principal: 'BETA ASSESSORIA',
  cidade_uf: 'Guarulhos/SP',
  colaborador_nome: 'Patrick',
  colaboradores_multiplos: false,
  funcao: 'EC_HUNTER',
  leads_no_mes: 0,
  tarefas_mes_total: 0,
  tarefas_atrasadas: 2,
  tarefas_futuras: 0,
  reunioes_mes: 0,
  timeline: [{ key: '2026-05', label: 'Mai/26', status: 'miss', count: 0 }],
  meta_atingida: false,
  score: null,
}

const mockHunter = {
  total: 2,
  linhas: [
    {
      colaborador_id: 'patrick-uuid',
      nome: 'Patrick',
      total_grupos: 2,
      meta_atingida: 1,
      tarefas_atrasadas: 1,
      sem_tarefa_futura: 1,
      leads_no_mes: 2,
      compliance_pct: 50.0,
      grupos: [grupoPatrickB, grupoPatrickA], // não-meta primeiro
    },
    {
      colaborador_id: 'caio-uuid',
      nome: 'Caio',
      total_grupos: 1,
      meta_atingida: 0,
      tarefas_atrasadas: 0,
      sem_tarefa_futura: 1,
      leads_no_mes: 1,
      compliance_pct: 0.0,
      grupos: [],
    },
  ],
}

const grupoAlineA = {
  id_grupo: 'A_G1',
  nome_grupo: 'GAMMA',
  qtd_cnpj: 1,
  parceria: 'Parceiro',
  contabilidade_principal: 'GAMMA',
  cidade_uf: 'SP/SP',
  colaborador_nome: 'Aline',
  colaboradores_multiplos: false,
  funcao: 'EC_FARMER',
  leads_no_mes: 5,
  tarefas_mes_total: 3,
  tarefas_atrasadas: 0,
  tarefas_futuras: 2,
  reunioes_mes: 3,
  timeline: [
    { key: '2026-W18', label: 'S1', status: 'ok',   count: 1 },
    { key: '2026-W19', label: 'S2', status: 'ok',   count: 1 },
    { key: '2026-W20', label: 'S3', status: 'ok',   count: 1 },
    { key: '2026-W21', label: 'S4', status: 'now',  count: 0 },
  ],
  meta_atingida: false,
  score: null,
}

const mockFarmer = {
  total: 1,
  linhas: [
    {
      colaborador_id: 'aline-uuid',
      nome: 'Aline',
      total_contadores: 10,
      total_grupos: 1,
      semanas: [
        { key: '2026-W18', label: 'S1', com_reuniao: 0, sem_reuniao: 10, pendente: 0 },
        { key: '2026-W19', label: 'S2', com_reuniao: 8, sem_reuniao: 2, pendente: 0 },
        { key: '2026-W20', label: 'S3', com_reuniao: 9, sem_reuniao: 1, pendente: 0 },
        { key: '2026-W21', label: 'S4', com_reuniao: 3, sem_reuniao: 0, pendente: 7 },
      ],
      tarefas_atrasadas: 0,
      tarefas_futuras: 1,
      leads_no_mes: 5,
      grupos: [grupoAlineA],
    },
  ],
}

function renderCarteira() {
  return render(<MemoryRouter><Carteira /></MemoryRouter>)
}

beforeEach(() => {
  vi.clearAllMocks()
  api.get.mockImplementation((url) => {
    if (url === '/carteira/resumo')             return Promise.resolve({ data: mockResumo })
    if (url === '/carteira/dashboard/hunter')   return Promise.resolve({ data: mockHunter })
    if (url === '/carteira/dashboard/farmer')   return Promise.resolve({ data: mockFarmer })
    if (url.startsWith('/carteira/grupos?funcao=OUTROS')) {
      return Promise.resolve({ data: { total: 0, grupos: [] } })
    }
    if (url === '/carteira/historico')          return Promise.resolve({ data: [] })
    return Promise.resolve({ data: null })
  })
})


describe('Página Carteira (v3 — drilldown com tabela completa)', () => {
  it('renderiza header e botões de upload', async () => {
    renderCarteira()
    expect(screen.getByRole('heading', { level: 1, name: 'Carteira' })).toBeInTheDocument()
    await waitFor(() => expect(api.get).toHaveBeenCalledWith('/carteira/dashboard/hunter'))
  })

  it('lista colaboradores Hunter na aba padrão', async () => {
    renderCarteira()
    await waitFor(() => {
      expect(screen.getByText('Patrick')).toBeInTheDocument()
      expect(screen.getByText('Caio')).toBeInTheDocument()
    })
  })

  it('clica no Patrick e expande inline a TABELA COMPLETA (sem refetch)', async () => {
    renderCarteira()
    await waitFor(() => screen.getByText('Patrick'))

    // Snapshot do nº de chamadas antes do click
    const callsAntes = api.get.mock.calls.length

    fireEvent.click(screen.getByText('Patrick'))

    await waitFor(() => {
      // Os 2 grupos do Patrick aparecem
      expect(screen.getByText('CONTAB ALFA')).toBeInTheDocument()
      expect(screen.getByText('BETA ASSESSORIA')).toBeInTheDocument()
    })

    // Nenhum request novo foi feito (drilldown vem do estado local)
    const callsDepois = api.get.mock.calls.length
    expect(callsDepois).toBe(callsAntes)
  })

  it('clica de novo no Patrick e o drilldown fecha', async () => {
    renderCarteira()
    await waitFor(() => screen.getByText('Patrick'))

    fireEvent.click(screen.getByText('Patrick'))
    await waitFor(() => expect(screen.getByText('CONTAB ALFA')).toBeInTheDocument())

    fireEvent.click(screen.getByText('Patrick'))
    await waitFor(() => {
      expect(screen.queryByText('CONTAB ALFA')).not.toBeInTheDocument()
    })
  })

  it('drilldown do Hunter mostra colunas atrasadas/futuras por grupo', async () => {
    renderCarteira()
    await waitFor(() => screen.getByText('Patrick'))

    fireEvent.click(screen.getByText('Patrick'))
    await waitFor(() => screen.getByText('BETA ASSESSORIA'))

    // Cabeçalhos do drilldown (formato antigo)
    expect(screen.getByText('Execução')).toBeInTheDocument()
    expect(screen.getByText(/Atrasadas/)).toBeInTheDocument()
    expect(screen.getByText(/Futuras/)).toBeInTheDocument()
  })

  it('filtro "tarefa atrasada" no drilldown filtra os grupos do Patrick', async () => {
    renderCarteira()
    await waitFor(() => screen.getByText('Patrick'))

    fireEvent.click(screen.getByText('Patrick'))
    await waitFor(() => expect(screen.getByText('CONTAB ALFA')).toBeInTheDocument())

    // Marca filtro de tarefa atrasada
    const checkbox = screen.getByLabelText(/Tarefa atrasada/i)
    fireEvent.click(checkbox)

    await waitFor(() => {
      // ALFA não tem atrasada (sai); BETA tem (fica)
      expect(screen.queryByText('CONTAB ALFA')).not.toBeInTheDocument()
      expect(screen.getByText('BETA ASSESSORIA')).toBeInTheDocument()
    })
  })

  it('clica num grupo do drilldown e abre o drawer lateral', async () => {
    api.get.mockImplementation((url) => {
      if (url === '/carteira/resumo')             return Promise.resolve({ data: mockResumo })
      if (url === '/carteira/dashboard/hunter')   return Promise.resolve({ data: mockHunter })
      if (url === '/carteira/dashboard/farmer')   return Promise.resolve({ data: mockFarmer })
      if (url.startsWith('/carteira/grupos?funcao=OUTROS')) {
        return Promise.resolve({ data: { total: 0, grupos: [] } })
      }
      if (url === '/carteira/historico')          return Promise.resolve({ data: [] })
      if (url.startsWith('/carteira/grupos/')) {
        return Promise.resolve({ data: { id_grupo: 'P_G1', qtd_cnpj: 1, cnpjs: [], tarefas: [] } })
      }
      return Promise.resolve({ data: null })
    })

    renderCarteira()
    await waitFor(() => screen.getByText('Patrick'))

    fireEvent.click(screen.getByText('Patrick'))
    await waitFor(() => screen.getByText('CONTAB ALFA'))

    fireEvent.click(screen.getByText('CONTAB ALFA'))

    await waitFor(() => {
      // Drawer foi disparado — pediu detalhes do grupo
      expect(api.get).toHaveBeenCalledWith(expect.stringContaining('/carteira/grupos/P_G1'))
    })
  })

  it('aba Farmer mostra Aline com bolinhas semanais e drilldown com grupos', async () => {
    renderCarteira()
    await waitFor(() => screen.getByText('Patrick'))

    fireEvent.click(screen.getByRole('button', { name: /Farmer/i }))

    await waitFor(() => {
      expect(screen.getByText('Aline')).toBeInTheDocument()
      // Subtítulo "10 contadores · 1 grupos" (singular/plural simples)
      expect(screen.getByText(/10 contadores/)).toBeInTheDocument()
    })

    fireEvent.click(screen.getByText('Aline'))
    await waitFor(() => {
      expect(screen.getByText('GAMMA')).toBeInTheDocument()
    })
  })

  it('busca de colaborador filtra na aba', async () => {
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

  it('aba Outros vazia mostra mensagem amigável', async () => {
    renderCarteira()
    await waitFor(() => screen.getByText('Patrick'))

    fireEvent.click(screen.getByRole('button', { name: /Outros/i }))
    await waitFor(() => {
      expect(screen.getByText(/Nenhum grupo nessa aba/i)).toBeInTheDocument()
    })
  })
})
