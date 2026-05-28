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
            conforme: true,
            problemas: [],
            problemas_rotulos: [],
            regras_aplicaveis: ['tarefa_futura'],
            temperatura_incoerente: false,
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


describe('Agendamento — conformidade (v1 replica Vendas)', () => {
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

  it('lista as oportunidades classificadas', async () => {
    setupApi()
    render(<Agendamento />)
    await waitFor(() => {
      expect(screen.getByText('Empresa Conforme')).toBeInTheDocument()
      expect(screen.getByText('Empresa Com Problema')).toBeInTheDocument()
    })
  })

  it('mostra o percentual de conformidade interna', async () => {
    setupApi()
    render(<Agendamento />)
    await waitFor(() => {
      expect(screen.getByText('50%')).toBeInTheDocument()
    })
  })

  it('mostra a coluna Responsável', async () => {
    setupApi()
    render(<Agendamento />)
    await waitFor(() => screen.getByText('Empresa Conforme'))
    const tabela = screen.getByRole('table')
    expect(within(tabela).getByText('Carla SDR')).toBeInTheDocument()
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

  it('mostra o badge de temperatura incoerente quando há caso', async () => {
    const conformidade = conformidadeMock()
    conformidade.data.resumo.temperatura_incoerente = 1
    conformidade.data.itens[1].classificacao.temperatura_incoerente = true
    setupApi({ conformidade })
    render(<Agendamento />)
    await waitFor(() => {
      expect(screen.getByText(/Revisar temperatura/i)).toBeInTheDocument()
    })
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
