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


function funilCromieMock() {
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
          },
        },
      ],
      resumo: {
        total_analisadas: 2,
        conformes: 1,
        nao_conformes: 1,
        atencao_hoje: 0,
        pct_conforme: 50.0,
        fora_da_analise: 0,
        temperatura_incoerente: 0,
      },
      por_fase: {},
      filtro_aplicado: {},
    },
  }
}

// Drawer — três OPs, dois responsáveis. Bruno tem duas (1500 + 200 =
// 1700), Diego uma (600). Somas distintas dos valores de linha.
const drawerMock = {
  data: {
    itens: [
      {
        op_id: 1250930,
        cnpj: '00000000000009',
        razao_social: 'Empresa do Bruno A',
        fase: '05. Negociação',
        responsavel: 'Bruno EV',
        proposta_nmrr: 1500,
        classificacao: {
          fase_analisada: true, estado: 'conforme', conforme: true, problemas: [],
          problemas_rotulos: [], regras_aplicaveis: [],
          temperatura_incoerente: false, tarefa_hoje: false,
        },
      },
      {
        op_id: 1250931,
        cnpj: '00000000000011',
        razao_social: 'Empresa do Bruno B',
        fase: '05. Negociação',
        responsavel: 'Bruno EV',
        proposta_nmrr: 200,
        classificacao: {
          fase_analisada: true, estado: 'conforme', conforme: true, problemas: [],
          problemas_rotulos: [], regras_aplicaveis: [],
          temperatura_incoerente: false, tarefa_hoje: false,
        },
      },
      {
        op_id: 1250932,
        cnpj: '00000000000010',
        razao_social: 'Empresa do Diego',
        fase: '05. Negociação',
        responsavel: 'Diego EV',
        proposta_nmrr: 600,
        classificacao: {
          fase_analisada: true, estado: 'conforme', conforme: true, problemas: [],
          problemas_rotulos: [], regras_aplicaveis: [],
          temperatura_incoerente: false, tarefa_hoje: false,
        },
      },
    ],
    resumo: {},
    por_fase: {},
    filtro_aplicado: {},
  },
}

function novaFaixa(t = 0, v = 0) {
  return { total: t, valor: v }
}

const funilMock = {
  data: {
    fases: [
      { fase: '01. Suspect', total: 81, valor: 0, faixas: {
        sem: novaFaixa(49), fria: novaFaixa(32), morna: novaFaixa(),
        quente: novaFaixa(), fechando: novaFaixa() } },
      { fase: '02. Cadência', total: 141, valor: 0, faixas: {
        sem: novaFaixa(12), fria: novaFaixa(106), morna: novaFaixa(23),
        quente: novaFaixa(), fechando: novaFaixa() } },
      { fase: '03. Qualificação', total: 10, valor: 0, faixas: {
        sem: novaFaixa(1), fria: novaFaixa(9), morna: novaFaixa(),
        quente: novaFaixa(), fechando: novaFaixa() } },
      { fase: '04. Apresentação', total: 12, valor: 28400, faixas: {
        sem: novaFaixa(3), fria: novaFaixa(7), morna: novaFaixa(2),
        quente: novaFaixa(), fechando: novaFaixa() } },
      { fase: '05. Negociação', total: 78, valor: 96957, faixas: {
        sem: novaFaixa(4), fria: novaFaixa(1), morna: novaFaixa(54),
        quente: novaFaixa(14, 60000), fechando: novaFaixa(5, 36957) } },
    ],
    total_geral: 322,
    valor_geral: 125357,
    temperatura_incoerente: 0,
  },
}

const filtrosMock = {
  data: {
    fases: ['01. Suspect', '03. Qualificação'],
    responsaveis: ['Bruno EV', 'Carla SDR'],
  },
}

function setupApi({ cromie = funilCromieMock(), funil = funilMock,
                    drawer = drawerMock } = {}) {
  api.get.mockImplementation((url) => {
    if (url === '/vendas/funil-cromie/filtros') {
      return Promise.resolve(filtrosMock)
    }
    if (url === '/vendas/funil') {
      return Promise.resolve(funil)
    }
    if (url.startsWith('/vendas/funil-cromie') && url.includes('temperatura=')) {
      return Promise.resolve(drawer)
    }
    if (url.startsWith('/vendas/funil-cromie')) {
      return Promise.resolve(cromie)
    }
    return Promise.reject(new Error(`URL não mockada: ${url}`))
  })
}


// ── Aba Funil (abre por padrão) ──────────────────────────────────

describe('Vendas — sub-aba Funil (padrão)', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('abre na aba Funil por padrão e renderiza as 5 fases', async () => {
    setupApi()
    render(<Vendas />)
    await waitFor(() => {
      expect(screen.getByText('01. Suspect')).toBeInTheDocument()
      expect(screen.getByText('05. Negociação')).toBeInTheDocument()
    })
  })

  it('exibe a legenda com Quente e Fechando separados', async () => {
    setupApi()
    render(<Vendas />)
    await waitFor(() => {
      expect(screen.getByText(/Quente \(80\)/i)).toBeInTheDocument()
      expect(screen.getByText(/Fechando \(90\)/i)).toBeInTheDocument()
    })
  })

  it('clicar numa faixa abre o drawer com a lista do recorte', async () => {
    setupApi()
    render(<Vendas />)
    await waitFor(() => screen.getByText('05. Negociação'))

    fireEvent.click(screen.getByLabelText(/05\. Negociação, Fechando/i))

    await waitFor(() => {
      expect(screen.getByText('Empresa do Bruno A')).toBeInTheDocument()
      expect(screen.getByText('Empresa do Diego')).toBeInTheDocument()
    })
  })

  it('o drawer tem o link para abrir a OP no CROmie com o op_id certo', async () => {
    setupApi()
    render(<Vendas />)
    await waitFor(() => screen.getByText('05. Negociação'))

    fireEvent.click(screen.getByLabelText(/05\. Negociação, Fechando/i))
    await waitFor(() => screen.getByText('Empresa do Bruno A'))

    const link = screen.getByLabelText(/Abrir Empresa do Bruno A no CROmie/i)
    expect(link).toHaveAttribute(
      'href',
      'https://app.crm.omie.com.br/business-opportunity/44/1250930',
    )
    expect(link).toHaveAttribute('target', '_blank')
  })

  it('filtra o drawer por responsável e recalcula a soma de valor', async () => {
    setupApi()
    render(<Vendas />)
    await waitFor(() => screen.getByText('05. Negociação'))

    fireEvent.click(screen.getByLabelText(/05\. Negociação, Fechando/i))
    await waitFor(() => screen.getByText('Empresa do Bruno A'))

    // Sem filtro: soma 1500 + 200 + 600 = 2300.
    expect(screen.getByText('R$ 2.300')).toBeInTheDocument()

    const selects = screen.getAllByRole('combobox')
    const selectDrawer = selects[selects.length - 1]
    fireEvent.change(selectDrawer, { target: { value: 'Bruno EV' } })

    await waitFor(() => {
      expect(screen.queryByText('Empresa do Diego')).not.toBeInTheDocument()
      // Soma recalcula para 1500 + 200 = 1700.
      expect(screen.getByText('R$ 1.700')).toBeInTheDocument()
    })
    expect(screen.getByText('Empresa do Bruno A')).toBeInTheDocument()
    expect(screen.getByText('Empresa do Bruno B')).toBeInTheDocument()
  })

  it('o drawer fecha ao clicar no botão fechar', async () => {
    setupApi()
    render(<Vendas />)
    await waitFor(() => screen.getByText('05. Negociação'))

    fireEvent.click(screen.getByLabelText(/05\. Negociação, Fechando/i))
    await waitFor(() => screen.getByText('Empresa do Bruno A'))

    fireEvent.click(screen.getByLabelText('Fechar'))
    await waitFor(() => {
      expect(screen.queryByText('Empresa do Bruno A')).not.toBeInTheDocument()
    })
  })

  it('mostra estado vazio quando o funil não tem oportunidades', async () => {
    const funil = {
      data: {
        fases: [
          { fase: '01. Suspect', total: 0, valor: 0, faixas: {
            sem: novaFaixa(), fria: novaFaixa(), morna: novaFaixa(),
            quente: novaFaixa(), fechando: novaFaixa() } },
        ],
        total_geral: 0,
        valor_geral: 0,
        temperatura_incoerente: 0,
      },
    }
    setupApi({ funil })
    render(<Vendas />)
    await waitFor(() => {
      expect(screen.getByText(/Sem oportunidades no funil/i)).toBeInTheDocument()
    })
  })
})


// ── Aba Conformidade (acessada por clique) ───────────────────────

describe('Vendas — sub-aba Conformidade', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('mostra a lista de oportunidades ao clicar na aba Conformidade', async () => {
    setupApi()
    render(<Vendas />)
    // Aguarda o funil aparecer (tela inicial).
    await waitFor(() => screen.getByText('05. Negociação'))

    fireEvent.click(screen.getByText('Conformidade'))

    await waitFor(() => {
      expect(screen.getByText('Empresa Conforme')).toBeInTheDocument()
      expect(screen.getByText('Empresa Com Problema')).toBeInTheDocument()
    })
  })

  it('mostra o percentual de conformidade interna', async () => {
    setupApi()
    render(<Vendas />)
    await waitFor(() => screen.getByText('05. Negociação'))
    fireEvent.click(screen.getByText('Conformidade'))
    await waitFor(() => {
      expect(screen.getByText('50%')).toBeInTheDocument()
    })
  })

  it('mostra a coluna Responsável', async () => {
    setupApi()
    render(<Vendas />)
    await waitFor(() => screen.getByText('05. Negociação'))
    fireEvent.click(screen.getByText('Conformidade'))
    await waitFor(() => screen.getByText('Empresa Conforme'))

    const tabela = screen.getByRole('table')
    expect(within(tabela).getByText('Carla SDR')).toBeInTheDocument()
  })

  it('cada linha da Conformidade tem o link para o CROmie com o op_id certo', async () => {
    setupApi()
    render(<Vendas />)
    await waitFor(() => screen.getByText('05. Negociação'))
    fireEvent.click(screen.getByText('Conformidade'))
    await waitFor(() => screen.getByText('Empresa Conforme'))

    const link = screen.getByLabelText(/Abrir Empresa Conforme no CROmie/i)
    expect(link).toHaveAttribute(
      'href',
      'https://app.crm.omie.com.br/business-opportunity/44/700111',
    )
    expect(link).toHaveAttribute('target', '_blank')
  })

  it('mostra o badge de temperatura incoerente quando há caso', async () => {
    const cromie = funilCromieMock()
    cromie.data.resumo.temperatura_incoerente = 1
    cromie.data.itens[1].classificacao.temperatura_incoerente = true
    setupApi({ cromie })
    render(<Vendas />)
    await waitFor(() => screen.getByText('05. Negociação'))
    fireEvent.click(screen.getByText('Conformidade'))
    await waitFor(() => {
      expect(screen.getByText(/Revisar temperatura/i)).toBeInTheDocument()
    })
  })
})
