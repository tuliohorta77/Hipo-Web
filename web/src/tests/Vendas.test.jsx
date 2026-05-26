import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, waitFor, fireEvent, within } from '@testing-library/react'

// Mock do api antes do import do componente — mesmo padrão dos demais testes.
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
function funilMock() {
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
          },
        },
      ],
      resumo: {
        total_analisadas: 2,
        conformes: 1,
        nao_conformes: 1,
        pct_conforme: 50.0,
        fora_da_analise: 0,
      },
      por_fase: {},
      filtro_aplicado: { fase: null, responsavel: null, so_problema: false },
    },
  }
}

const filtrosMock = {
  data: {
    fases: ['01. Suspect', '03. Qualificação'],
    responsaveis: ['Bruno EV', 'Carla SDR'],
  },
}

function setupApi({ funil = funilMock() } = {}) {
  api.get.mockImplementation((url) => {
    if (url === '/vendas/funil-cromie/filtros') {
      return Promise.resolve(filtrosMock)
    }
    if (url.startsWith('/vendas/funil-cromie')) {
      return Promise.resolve(funil)
    }
    return Promise.reject(new Error(`URL não mockada: ${url}`))
  })
}


describe('Vendas — sub-abas e funil CROmie', () => {
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
    expect(screen.getByText(/tarefa futura em todas as fases/i)).toBeInTheDocument()
  })

  it('mostra a coluna Responsável com o nome calculado por fase', async () => {
    setupApi()
    render(<Vendas />)
    // O nome do responsável aparece tanto no <option> do filtro quanto na
    // <td> da tabela — por isso a busca é restrita às células da tabela.
    await waitFor(() => screen.getByText('Empresa Conforme'))

    const tabela = screen.getByRole('table')
    // Suspect -> responsável é o SDR; Qualificação -> o executivo.
    expect(within(tabela).getByText('Carla SDR')).toBeInTheDocument()
    expect(within(tabela).getByText('Bruno EV')).toBeInTheDocument()
  })

  it('mostra os rótulos de pendência nas oportunidades com problema', async () => {
    setupApi()
    render(<Vendas />)
    await waitFor(() => {
      expect(screen.getByText('Falta temperatura')).toBeInTheDocument()
      expect(screen.getByText('Falta previsão de fechamento')).toBeInTheDocument()
    })
  })

  it('troca para a sub-aba Funil e mostra o placeholder', async () => {
    setupApi()
    render(<Vendas />)
    await waitFor(() => screen.getByText('Empresa Conforme'))

    fireEvent.click(screen.getByText('Funil'))

    // "em breve" aparece no título e na descrição do placeholder —
    // o título é uma âncora única e suficiente.
    await waitFor(() => {
      expect(
        screen.getByText('Funil de Vendas — em breve')
      ).toBeInTheDocument()
    })
  })

  it('chama o endpoint de filtros para popular os dropdowns', async () => {
    setupApi()
    render(<Vendas />)
    await waitFor(() => {
      const urls = api.get.mock.calls.map(([u]) => u)
      expect(urls).toContain('/vendas/funil-cromie/filtros')
    })
  })
})
