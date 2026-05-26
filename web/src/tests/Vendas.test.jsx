import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, waitFor, fireEvent, within } from '@testing-library/react'

vi.mock('../api', () => ({
  default: {
    get: vi.fn(),
    post: vi.fn(),
  },
  isAuthenticated: () => true,
  getUser: () => ({ nome: 'Tulio Horta', cargo: 'Franqueado' }),
  logout: vi.fn(),
  TOKEN_KEY: 'hipo_token',
  USER_KEY: 'hipo_user',
}))

import api from '../api'
import Vendas from '../pages/Vendas'


// Resposta de /vendas/funil-cromie com 1 conforme e 1 com problema.
function funilCromieMock() {
  return {
    data: {
      itens: [
        {
          op_id: 1,
          cnpj: '00000000000001',
          razao_social: 'Empresa Conforme',
          fase: '01. Suspect',
          responsavel: 'Carla SDR',
          data_atualizacao: '2026-05-20T10:00:00Z',
          classificacao: {
            fase_analisada: true,
            conforme: true,
            problemas: [],
            problemas_rotulos: [],
            regras_aplicaveis: ['tarefa_futura'],
            temperatura_incoerente: false,
          },
        },
        {
          op_id: 2,
          cnpj: '00000000000002',
          razao_social: 'Empresa Com Problema',
          fase: '03. Qualificação',
          responsavel: 'Bruno EV',
          data_atualizacao: '2026-05-21T10:00:00Z',
          classificacao: {
            fase_analisada: true,
            conforme: false,
            problemas: ['temperatura', 'previsao'],
            problemas_rotulos: ['Falta temperatura', 'Falta previsão de fechamento'],
            regras_aplicaveis: ['tarefa_futura', 'temperatura', 'previsao'],
            temperatura_incoerente: false,
          },
        },
      ],
      resumo: {
        total_analisadas: 2,
        conformes: 1,
        nao_conformes: 1,
        pct_conforme: 50.0,
        fora_da_analise: 0,
        temperatura_incoerente: 0,
      },
      por_fase: {},
      filtro_aplicado: {},
    },
  }
}

// Resposta de /vendas/funil — 5 fases com faixas.
const funilMock = {
  data: {
    fases: [
      { fase: '01. Suspect',      total: 81,  faixas: { sem: 49, fria: 32,  morna: 0,  quente: 0 } },
      { fase: '02. Cadência',     total: 141, faixas: { sem: 12, fria: 106, morna: 23, quente: 0 } },
      { fase: '03. Qualificação', total: 10,  faixas: { sem: 1,  fria: 9,   morna: 0,  quente: 0 } },
      { fase: '04. Apresentação', total: 12,  faixas: { sem: 3,  fria: 7,   morna: 2,  quente: 0 } },
      { fase: '05. Negociação',   total: 78,  faixas: { sem: 4,  fria: 1,   morna: 54, quente: 19 } },
    ],
    total_geral: 322,
    temperatura_incoerente: 0,
  },
}

const filtrosMock = {
  data: {
    fases: ['01. Suspect', '03. Qualificação'],
    responsaveis: ['Bruno EV', 'Carla SDR'],
  },
}

function setupApi({ cromie = funilCromieMock(), funil = funilMock } = {}) {
  api.get.mockImplementation((url) => {
    if (url === '/vendas/funil-cromie/filtros') {
      return Promise.resolve(filtrosMock)
    }
    if (url === '/vendas/funil') {
      return Promise.resolve(funil)
    }
    if (url.startsWith('/vendas/funil-cromie')) {
      return Promise.resolve(cromie)
    }
    return Promise.reject(new Error(`URL não mockada: ${url}`))
  })
}


describe('Vendas — sub-aba Conformidade', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('abre na sub-aba Conformidade e lista as oportunidades', async () => {
    setupApi()
    render(<Vendas />)
    await waitFor(() => {
      expect(screen.getByText('Empresa Conforme')).toBeInTheDocument()
      expect(screen.getByText('Empresa Com Problema')).toBeInTheDocument()
    })
  })

  it('mostra o percentual de conformidade interna no KPI', async () => {
    setupApi()
    render(<Vendas />)
    await waitFor(() => {
      expect(screen.getByText('50%')).toBeInTheDocument()
    })
  })

  it('exibe o aviso de que é régua interna, não o PEX oficial', async () => {
    setupApi()
    render(<Vendas />)
    await waitFor(() => screen.getByText('Empresa Conforme'))
    expect(screen.getByText(/régua interna/i)).toBeInTheDocument()
  })

  it('mostra a coluna Responsável com o nome calculado por fase', async () => {
    setupApi()
    render(<Vendas />)
    await waitFor(() => screen.getByText('Empresa Conforme'))
    const tabela = screen.getByRole('table')
    expect(within(tabela).getByText('Carla SDR')).toBeInTheDocument()
    expect(within(tabela).getByText('Bruno EV')).toBeInTheDocument()
  })

  it('não mostra o KPI de temperatura a revisar quando não há caso', async () => {
    setupApi()
    render(<Vendas />)
    await waitFor(() => screen.getByText('Empresa Conforme'))
    expect(screen.queryByText(/a revisar/i)).not.toBeInTheDocument()
  })

  it('mostra o aviso e o badge de temperatura incoerente quando há caso', async () => {
    const cromie = funilCromieMock()
    cromie.data.resumo.temperatura_incoerente = 1
    cromie.data.itens[1].classificacao.temperatura_incoerente = true
    setupApi({ cromie })
    render(<Vendas />)
    await waitFor(() => {
      expect(screen.getByText(/Revisar temperatura/i)).toBeInTheDocument()
    })
  })
})


describe('Vendas — sub-aba Funil', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('troca para a aba Funil e renderiza as 5 fases', async () => {
    setupApi()
    render(<Vendas />)
    await waitFor(() => screen.getByText('Empresa Conforme'))

    fireEvent.click(screen.getByText('Funil'))

    await waitFor(() => {
      expect(screen.getByText('01. Suspect')).toBeInTheDocument()
      expect(screen.getByText('05. Negociação')).toBeInTheDocument()
    })
  })

  it('mostra o total de oportunidades no funil', async () => {
    setupApi()
    render(<Vendas />)
    await waitFor(() => screen.getByText('Empresa Conforme'))

    fireEvent.click(screen.getByText('Funil'))

    await waitFor(() => {
      expect(screen.getByText('322')).toBeInTheDocument()
    })
  })

  it('exibe a legenda de faixas de temperatura', async () => {
    setupApi()
    render(<Vendas />)
    await waitFor(() => screen.getByText('Empresa Conforme'))

    fireEvent.click(screen.getByText('Funil'))

    await waitFor(() => {
      expect(screen.getByText(/Fria/i)).toBeInTheDocument()
      expect(screen.getByText(/Quente/i)).toBeInTheDocument()
    })
  })

  it('mostra o aviso de temperatura incoerente no funil quando há caso', async () => {
    const funil = { data: { ...funilMock.data, temperatura_incoerente: 2 } }
    setupApi({ funil })
    render(<Vendas />)
    await waitFor(() => screen.getByText('Empresa Conforme'))

    fireEvent.click(screen.getByText('Funil'))

    await waitFor(() => {
      expect(screen.getByText(/não entra/i)).toBeInTheDocument()
    })
  })

  it('mostra estado vazio quando o funil não tem oportunidades', async () => {
    const funil = {
      data: {
        fases: [
          { fase: '01. Suspect', total: 0, faixas: { sem: 0, fria: 0, morna: 0, quente: 0 } },
        ],
        total_geral: 0,
        temperatura_incoerente: 0,
      },
    }
    setupApi({ funil })
    render(<Vendas />)
    await waitFor(() => screen.getByText('Empresa Conforme'))

    fireEvent.click(screen.getByText('Funil'))

    await waitFor(() => {
      expect(screen.getByText(/Sem oportunidades no funil/i)).toBeInTheDocument()
    })
  })
})
