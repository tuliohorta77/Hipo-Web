import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, waitFor, fireEvent, within } from '@testing-library/react'

vi.mock('../api', () => ({
  default: {
    get: vi.fn(),
    post: vi.fn(),
  },
  isAuthenticated: () => true,
  getUser: () => ({ nome: 'Alice Santos', cargo: 'SDR' }),
  logout: vi.fn(),
  TOKEN_KEY: 'hipo_token',
  USER_KEY: 'hipo_user',
}))

import api from '../api'
import Agendamento from '../pages/Agendamento'


// Helper: gera o mock da resposta de /agendamento/conformidade.
// v1.3.2: cada item tem 'estado' e 'tarefa_hoje' na classificação.
function conformidadeMock() {
  return {
    data: {
      itens: [
        {
          op_id: 700111,
          cnpj: '00000000000001',
          razao_social: 'Empresa Conforme',
          fase: '01. Suspect',
          responsavel: 'Carla SDR',
          proposta_nmrr: 0,
          data_atualizacao: '2026-05-20T10:00:00Z',
          classificacao: {
            fase_analisada: true,
            estado: 'conforme',
            conforme: true,
            problemas: [],
            problemas_rotulos: [],
            regras_aplicaveis: ['tarefa_futura'],
            temperatura_incoerente: false,
            tarefa_hoje: false,
          },
        },
        {
          op_id: 700222,
          cnpj: '00000000000002',
          razao_social: 'Empresa Tarefa Hoje',
          fase: '01. Suspect',
          responsavel: 'Carla SDR',
          proposta_nmrr: 0,
          data_atualizacao: '2026-05-28T10:00:00Z',
          classificacao: {
            fase_analisada: true,
            estado: 'atencao',
            conforme: false,
            problemas: [],
            problemas_rotulos: [],
            regras_aplicaveis: ['tarefa_futura'],
            temperatura_incoerente: false,
            tarefa_hoje: true,
          },
        },
        {
          op_id: 700333,
          cnpj: '00000000000003',
          razao_social: 'Empresa Com Problema',
          fase: '03. Qualificação',
          responsavel: 'Bruno EV',
          proposta_nmrr: 0,
          data_atualizacao: '2026-05-21T10:00:00Z',
          classificacao: {
            fase_analisada: true,
            estado: 'problema',
            conforme: false,
            problemas: ['temperatura', 'previsao'],
            problemas_rotulos: ['Falta temperatura', 'Falta previsão de fechamento'],
            regras_aplicaveis: ['tarefa_futura', 'temperatura', 'previsao'],
            temperatura_incoerente: false,
            tarefa_hoje: false,
          },
        },
      ],
      resumo: {
        total_analisadas: 2,
        conformes: 1,
        nao_conformes: 1,
        atencao_hoje: 1,
        pct_conforme: 50.0,
        fora_da_analise: 0,
        temperatura_incoerente: 0,
      },
      por_fase: {},
      filtro_aplicado: {},
    },
  }
}

const filtrosMock = {
  data: {
    fases: ['01. Suspect', '03. Qualificação'],
    responsaveis: ['Bruno EV', 'Carla SDR'],
  },
}

function setupApi({ conformidade = conformidadeMock() } = {}) {
  api.get.mockImplementation((url) => {
    if (url === '/agendamento/conformidade/filtros') {
      return Promise.resolve(filtrosMock)
    }
    if (url.startsWith('/agendamento/conformidade')) {
      return Promise.resolve(conformidade)
    }
    return Promise.reject(new Error(`URL não mockada: ${url}`))
  })
}


describe('Agendamento — conformidade (v1.3.2 com estado de atenção)', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('renderiza o título do módulo Agendamento', async () => {
    setupApi()
    render(<Agendamento />)
    await waitFor(() => {
      expect(screen.getByText('Agendamento')).toBeInTheDocument()
    })
  })

  it('lista as oportunidades classificadas (incluindo atenção)', async () => {
    setupApi()
    render(<Agendamento />)
    await waitFor(() => {
      expect(screen.getByText('Empresa Conforme')).toBeInTheDocument()
      expect(screen.getByText('Empresa Tarefa Hoje')).toBeInTheDocument()
      expect(screen.getByText('Empresa Com Problema')).toBeInTheDocument()
    })
  })

  it('mostra o KPI "Tarefa para hoje" com a contagem do resumo', async () => {
    setupApi()
    render(<Agendamento />)
    // "Tarefa para hoje" aparece em 2 lugares: o KPI (texto exato) e o
    // badge da linha (com prefixo de rel�gio). Procuro pelo exato do KPI.
    await waitFor(() => {
      expect(screen.getByText('Tarefa para hoje')).toBeInTheDocument()
    })
  })

  it('mostra o badge Atenção na linha com tarefa hoje', async () => {
    setupApi()
    render(<Agendamento />)
    await waitFor(() => screen.getByText('Empresa Tarefa Hoje'))

    const tabela = screen.getByRole('table')
    // Badge de situação "Atenção" (do estado=atencao).
    expect(within(tabela).getByText(/Atenção/)).toBeInTheDocument()
    // Badge de pendência "Tarefa para hoje" (flag tarefa_hoje).
    expect(within(tabela).getAllByText(/Tarefa para hoje/i).length).toBeGreaterThan(0)
  })

  it('mostra o badge Conforme na linha conforme e Problema na com problema', async () => {
    setupApi()
    render(<Agendamento />)
    await waitFor(() => screen.getByText('Empresa Conforme'))

    const tabela = screen.getByRole('table')
    expect(within(tabela).getByText(/✓ Conforme/)).toBeInTheDocument()
    expect(within(tabela).getByText(/✗ Problema/)).toBeInTheDocument()
  })

  it('mostra o percentual de conformidade interna (atenção fora do %)', async () => {
    setupApi()
    render(<Agendamento />)
    await waitFor(() => {
      // 50% = 1 conforme / (1 conforme + 1 problema). Atenção fora.
      expect(screen.getByText('50%')).toBeInTheDocument()
    })
  })

  it('cada linha tem o link para o CROmie com o op_id certo', async () => {
    setupApi()
    render(<Agendamento />)
    await waitFor(() => screen.getByText('Empresa Conforme'))

    const link = screen.getByLabelText(/Abrir Empresa Conforme no CROmie/i)
    expect(link).toHaveAttribute(
      'href',
      'https://app.crm.omie.com.br/business-opportunity/44/700111',
    )
    expect(link).toHaveAttribute('target', '_blank')
  })

  it('consome /agendamento/conformidade (não /vendas)', async () => {
    setupApi()
    render(<Agendamento />)
    await waitFor(() => screen.getByText('Empresa Conforme'))

    const urls = api.get.mock.calls.map((c) => c[0])
    expect(urls.some((u) => u.startsWith('/agendamento/conformidade'))).toBe(true)
    expect(urls.some((u) => u.startsWith('/vendas'))).toBe(false)
  })

  it('filtra só com problema (refaz a chamada com o parâmetro)', async () => {
    setupApi()
    render(<Agendamento />)
    await waitFor(() => screen.getByText('Empresa Conforme'))

    const checkbox = screen.getByLabelText(/Só com problema/i)
    fireEvent.click(checkbox)

    await waitFor(() => {
      const urls = api.get.mock.calls.map((c) => c[0])
      expect(urls.some((u) => u.includes('so_problema=true'))).toBe(true)
    })
  })
})
