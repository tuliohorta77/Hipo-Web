import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, waitFor, fireEvent } from '@testing-library/react'

// Mock do api antes do import do componente
vi.mock('../api', () => ({
  default: {
    get: vi.fn(),
    post: vi.fn(),
  },
  isAuthenticated: () => true,
  getUser: () => ({ nome: 'Beatriz', cargo: 'Hunter' }),
  logout: vi.fn(),
  TOKEN_KEY: 'hipo_token',
  USER_KEY: 'hipo_user',
}))

import api from '../api'
import CarteiraGrupoDrawer from '../components/CarteiraGrupoDrawer'

// Detalhe mock retornado por /carteira/grupos/:id
const detalheMock = {
  id_grupo: 'g-001',
  qtd_cnpj: 2,
  cnpjs: [
    {
      cnpj_contador: '02.895.158/0001-00',
      contabilidade: 'MASETTI AUDITORIA E CONSULTORIA S C LTDA',
      parceria: 'Não Parceiro',
      cidade_uf: 'SAO PAULO/SP',
      colaborador_nome: 'Beatriz Silva',
      apps_ativos: 3,
    },
    {
      cnpj_contador: '22.604.270/0001-44',
      contabilidade: 'PRADA CONTABILIDADE EIRELI',
      parceria: 'Não Parceiro',
      cidade_uf: 'Guarulhos/SP',
      colaborador_nome: 'Beatriz Silva',
      apps_ativos: 1,
    },
  ],
  tarefas: [],
}

const leadsMockCnpj1 = {
  cnpj_contador: '02.895.158/0001-00',
  kpis: { total: 2, em_andamento: 1, conquistado: 1, perdido: 0 },
  leads: [
    {
      op_id: 100, cnpj: 'a', razao_social: 'EMP A',
      fase: '02. Cadência', status: 'Ativo', proposta_nmrr: 1500,
      dias_parado: 3, data_atualizacao: '2026-05-15T10:00:00Z',
    },
    {
      op_id: 101, cnpj: 'b', razao_social: 'EMP B',
      fase: '06. Conquistado', status: 'Conquistado', proposta_nmrr: 2200,
      dias_parado: null, data_atualizacao: '2026-05-10T10:00:00Z',
    },
  ],
}

const leadsMockCnpj2 = {
  cnpj_contador: '22.604.270/0001-44',
  kpis: { total: 1, em_andamento: 1, conquistado: 0, perdido: 0 },
  leads: [
    {
      op_id: 200, cnpj: 'c', razao_social: 'EMP C',
      fase: '03. Qualificação', status: 'Ativo', proposta_nmrr: 800,
      dias_parado: 1, data_atualizacao: '2026-05-18T10:00:00Z',
    },
  ],
}

function setupApi({ detalhe = detalheMock, leadsPorCnpj = {} } = {}) {
  api.get.mockImplementation((url, opts) => {
    if (url.startsWith('/carteira/grupos/')) {
      return Promise.resolve({ data: detalhe })
    }
    if (url === '/clientes/contador-leads') {
      const cnpj = opts?.params?.cnpj
      const data = leadsPorCnpj[cnpj]
      if (data instanceof Error) {
        return Promise.reject(data)
      }
      if (data) {
        return Promise.resolve({ data })
      }
      // CNPJ sem mock configurado → 500 por padrão (não deveria acontecer no teste)
      return Promise.reject({ response: { status: 500 } })
    }
    return Promise.reject(new Error(`URL não mockada: ${url}`))
  })
}

function makeForbiddenError() {
  const err = new Error('Request failed with status code 403')
  err.response = { status: 403, data: { detail: 'forbidden' } }
  return err
}


describe('CarteiraGrupoDrawer', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('não renderiza nada quando idGrupo é null', () => {
    const { container } = render(
      <CarteiraGrupoDrawer idGrupo={null} onFechar={() => {}} nomeGrupo="X" />
    )
    expect(container.firstChild).toBeNull()
  })

  it('carrega detalhe do grupo ao montar', async () => {
    setupApi()
    render(
      <CarteiraGrupoDrawer
        idGrupo="g-001"
        onFechar={() => {}}
        nomeGrupo="Beatriz Silva"
      />
    )

    await waitFor(() => {
      expect(
        screen.getByText('MASETTI AUDITORIA E CONSULTORIA S C LTDA')
      ).toBeInTheDocument()
    })

    expect(api.get).toHaveBeenCalledWith('/carteira/grupos/g-001')
  })

  it('aba Leads chama /clientes/contador-leads UMA VEZ por CNPJ (sem loop)', async () => {
    setupApi({
      leadsPorCnpj: {
        '02.895.158/0001-00': leadsMockCnpj1,
        '22.604.270/0001-44': leadsMockCnpj2,
      },
    })
    render(
      <CarteiraGrupoDrawer
        idGrupo="g-001"
        onFechar={() => {}}
        nomeGrupo="Beatriz Silva"
      />
    )

    // Espera o detalhe carregar
    await waitFor(() => {
      expect(
        screen.getByText('MASETTI AUDITORIA E CONSULTORIA S C LTDA')
      ).toBeInTheDocument()
    })

    // Clica na aba Leads
    fireEvent.click(screen.getByText(/^Leads/))

    // Espera os leads renderizarem
    await waitFor(() => {
      expect(screen.getByText('EMP A')).toBeInTheDocument()
    })

    // Garante que cada CNPJ foi chamado EXATAMENTE 1 vez
    const callsContadorLeads = api.get.mock.calls.filter(
      ([url]) => url === '/clientes/contador-leads'
    )
    expect(callsContadorLeads).toHaveLength(2)

    const cnpjsChamados = callsContadorLeads
      .map(([, opts]) => opts.params.cnpj)
      .sort()
    expect(cnpjsChamados).toEqual([
      '02.895.158/0001-00',
      '22.604.270/0001-44',
    ])
  })

  it('NÃO entra em loop quando todas as chamadas retornam 403', async () => {
    setupApi({
      leadsPorCnpj: {
        '02.895.158/0001-00': makeForbiddenError(),
        '22.604.270/0001-44': makeForbiddenError(),
      },
    })

    render(
      <CarteiraGrupoDrawer
        idGrupo="g-001"
        onFechar={() => {}}
        nomeGrupo="Beatriz Silva"
      />
    )
    await waitFor(() => {
      expect(
        screen.getByText('MASETTI AUDITORIA E CONSULTORIA S C LTDA')
      ).toBeInTheDocument()
    })

    fireEvent.click(screen.getByText(/^Leads/))

    // Espera a mensagem de "sem permissão" aparecer
    await waitFor(() => {
      expect(screen.getByTestId('leads-forbidden')).toBeInTheDocument()
    })

    // Espera um tick adicional pra dar chance de loop acontecer (se houver bug)
    await new Promise((r) => setTimeout(r, 100))

    // Cada CNPJ foi tentado UMA vez só, mesmo com 403
    const callsContadorLeads = api.get.mock.calls.filter(
      ([url]) => url === '/clientes/contador-leads'
    )
    expect(callsContadorLeads).toHaveLength(2)
  })

  it('mostra mensagem de sem permissão quando todos 403', async () => {
    setupApi({
      leadsPorCnpj: {
        '02.895.158/0001-00': makeForbiddenError(),
        '22.604.270/0001-44': makeForbiddenError(),
      },
    })
    render(
      <CarteiraGrupoDrawer
        idGrupo="g-001"
        onFechar={() => {}}
        nomeGrupo="Beatriz Silva"
      />
    )
    await waitFor(() => screen.getByText('MASETTI AUDITORIA E CONSULTORIA S C LTDA'))
    fireEvent.click(screen.getByText(/^Leads/))

    await waitFor(() => {
      expect(screen.getByText(/Sem permissão para ver os leads/i)).toBeInTheDocument()
    })
  })

  it('mostra estado vazio quando 200 mas sem leads', async () => {
    setupApi({
      leadsPorCnpj: {
        '02.895.158/0001-00': {
          cnpj_contador: '02.895.158/0001-00',
          kpis: { total: 0, em_andamento: 0, conquistado: 0, perdido: 0 },
          leads: [],
        },
        '22.604.270/0001-44': {
          cnpj_contador: '22.604.270/0001-44',
          kpis: { total: 0, em_andamento: 0, conquistado: 0, perdido: 0 },
          leads: [],
        },
      },
    })
    render(
      <CarteiraGrupoDrawer
        idGrupo="g-001"
        onFechar={() => {}}
        nomeGrupo="Beatriz Silva"
      />
    )
    await waitFor(() => screen.getByText('MASETTI AUDITORIA E CONSULTORIA S C LTDA'))
    fireEvent.click(screen.getByText(/^Leads/))

    await waitFor(() => {
      expect(screen.getByText(/Nenhum lead vinculado/i)).toBeInTheDocument()
    })
  })

  it('agrega KPIs e leads de múltiplos CNPJs corretamente', async () => {
    setupApi({
      leadsPorCnpj: {
        '02.895.158/0001-00': leadsMockCnpj1,
        '22.604.270/0001-44': leadsMockCnpj2,
      },
    })
    render(
      <CarteiraGrupoDrawer
        idGrupo="g-001"
        onFechar={() => {}}
        nomeGrupo="Beatriz Silva"
      />
    )
    await waitFor(() => screen.getByText('MASETTI AUDITORIA E CONSULTORIA S C LTDA'))
    fireEvent.click(screen.getByText(/^Leads/))

    await waitFor(() => {
      expect(screen.getByText('EMP A')).toBeInTheDocument()
      expect(screen.getByText('EMP B')).toBeInTheDocument()
      expect(screen.getByText('EMP C')).toBeInTheDocument()
    })
    // Total = 2 + 1 = 3 (aparece no contador da aba + no KPI Total)
    const trechosTotal = screen.getAllByText('3')
    expect(trechosTotal.length).toBeGreaterThanOrEqual(1)
  })
})
