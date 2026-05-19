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

const mockResumo = {
  hunter:  { total_grupos: 84, meta_atingida: 68, compliance_pct: 81.0,
             com_tarefa_atrasada: 23, sem_tarefa_futura: 71, leads_no_mes: 23 },
  farmer:  { total_grupos: 441, meta_atingida: 200, compliance_pct: 45.3,
             com_tarefa_atrasada: 62, sem_tarefa_futura: 232, leads_no_mes: 100 },
  outros:  { total_grupos: 8, meta_atingida: 0, compliance_pct: 0.0,
             com_tarefa_atrasada: 0, sem_tarefa_futura: 7, leads_no_mes: 0 },
  totais: { grupos_total: 533, cnpjs_total: 633, tarefas_total: 9330, colaboradores: 11 },
  ultima_carteira: '2026-05-18T10:00:00Z',
  ultima_tarefas:  '2026-05-18T11:00:00Z',
}

const grupoHunter = {
  id_grupo: 'g1', nome_grupo: 'Não', qtd_cnpj: 2,
  parceria: 'Parceiro',
  contabilidade_principal: 'CONTAB ABC', cidade_uf: 'SP/SP',
  colaborador_nome: 'Patrick', colaboradores_multiplos: false,
  funcao: 'EC_HUNTER', leads_no_mes: 0,
  tarefas_mes_total: 1, tarefas_atrasadas: 0, tarefas_futuras: 1,
  reunioes_mes: 0,
  timeline: [{ key: '2026-05', label: 'Mai/26', status: 'ok', count: 1 }],
  meta_atingida: true, score: null,
}

const grupoFarmer = {
  id_grupo: 'g2', nome_grupo: 'Sim', qtd_cnpj: 1,
  parceria: 'Parceiro',
  contabilidade_principal: 'CONTAB DEF', cidade_uf: 'SP/SP',
  colaborador_nome: 'Beatriz', colaboradores_multiplos: false,
  funcao: 'EC_FARMER', leads_no_mes: 5,
  tarefas_mes_total: 3, tarefas_atrasadas: 2, tarefas_futuras: 0,
  reunioes_mes: 2,
  timeline: [
    { key: '2026-W18', label: 'S1', status: 'ok',   count: 1 },
    { key: '2026-W19', label: 'S2', status: 'miss', count: 0 },
    { key: '2026-W20', label: 'S3', status: 'ok',   count: 1 },
    { key: '2026-W21', label: 'S4', status: 'now',  count: 0 },
  ],
  meta_atingida: false, score: null,
}

function renderCarteira() {
  return render(<MemoryRouter><Carteira /></MemoryRouter>)
}


describe('Página Carteira', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    api.get.mockImplementation((url) => {
      if (url === '/carteira/resumo') return Promise.resolve({ data: mockResumo })
      if (url.startsWith('/carteira/grupos?')) {
        const u = new URL('http://test' + url)
        const f = u.searchParams.get('funcao')
        const grupos = f === 'EC_HUNTER' ? [grupoHunter]
                     : f === 'EC_FARMER' ? [grupoFarmer]
                     : []
        return Promise.resolve({ data: { total: grupos.length, grupos } })
      }
      if (url === '/carteira/historico') return Promise.resolve({ data: [] })
      return Promise.resolve({ data: null })
    })
  })

  it('renderiza header e botões de upload', async () => {
    renderCarteira()
    // Header h1
    expect(screen.getByRole('heading', { level: 1, name: 'Carteira' })).toBeInTheDocument()
    // Aguarda primeiro fetch
    await waitFor(() => expect(api.get).toHaveBeenCalled())
  })

  it('mostra contador de grupos em cada aba', async () => {
    renderCarteira()
    // Tema novo: contadores ficam em <span class="... rounded-full ..."> dentro
    // dos botões de aba (linha de Tabs no Carteira.jsx).
    await waitFor(() => {
      const counters = Array.from(document.querySelectorAll('button .rounded-full'))
        .map((n) => n.textContent.trim())
      expect(counters).toEqual(expect.arrayContaining(['84', '441', '8']))
    })
  })

  it('lista um grupo Hunter na aba padrão', async () => {
    renderCarteira()
    await waitFor(() => {
      expect(screen.getByText('CONTAB ABC · SP/SP', { exact: false }))
        .toBeInTheDocument()
      expect(screen.getByText('Patrick')).toBeInTheDocument()
    })
  })

  it('troca para aba Farmer e mostra coluna Leads/mês', async () => {
    renderCarteira()
    await waitFor(() =>
      expect(screen.getByText('CONTAB ABC · SP/SP', { exact: false })).toBeInTheDocument()
    )

    fireEvent.click(screen.getByRole('button', { name: /Farmer/i }))
    await waitFor(() => {
      expect(screen.getByText('CONTAB DEF · SP/SP', { exact: false })).toBeInTheDocument()
      // Coluna "Leads/mês" no header da tabela quando aba Farmer
      expect(screen.getByText(/Leads\/mês/i)).toBeInTheDocument()
    })
  })

  it('aplica filtro tarefa atrasada (dispara nova chamada)', async () => {
    renderCarteira()
    await waitFor(() => expect(api.get).toHaveBeenCalledWith(expect.stringContaining('/carteira/grupos?')))

    const checkbox = screen.getByLabelText(/Tarefa atrasada/i)
    fireEvent.click(checkbox)

    await waitFor(() => {
      const chamadas = api.get.mock.calls.map((c) => c[0])
      expect(chamadas.some((u) => u.includes('tarefa_atrasada=true'))).toBe(true)
    })
  })

  it('faz upload de tarefas e mostra mensagem de sucesso', async () => {
    api.post.mockResolvedValue({
      data: { message: 'Tarefas atualizadas: 9330 registros.' }
    })

    renderCarteira()
    await waitFor(() => expect(api.get).toHaveBeenCalled())

    // Pega o input file do botão "Tarefas" (o último input file da tela)
    const inputs = document.querySelectorAll('input[type="file"]')
    expect(inputs.length).toBeGreaterThanOrEqual(2)
    const inputTarefas = inputs[inputs.length - 1]
    const file = new File(['x'], 'tarefas.xlsx', {
      type: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
    })

    fireEvent.change(inputTarefas, { target: { files: [file] } })

    await waitFor(() => {
      expect(api.post).toHaveBeenCalledWith(
        '/carteira/upload-tarefas',
        expect.any(FormData),
        expect.any(Object)
      )
      expect(screen.getByText(/9330 registros/)).toBeInTheDocument()
    })
  })

  it('mostra mensagem amigável quando aba Outros está vazia', async () => {
    renderCarteira()
    await waitFor(() =>
      expect(screen.getByText('CONTAB ABC · SP/SP', { exact: false })).toBeInTheDocument()
    )

    fireEvent.click(screen.getByRole('button', { name: /Outros/i }))
    await waitFor(() => {
      expect(screen.getByText(/Nenhum grupo nessa aba/)).toBeInTheDocument()
    })
  })
})
