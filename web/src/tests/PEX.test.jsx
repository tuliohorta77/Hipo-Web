import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import axios from 'axios'
import PEXDashboard from '../pages/PEX'

const mockPainel = {
  total_geral_pts: 36.5,
  total_resultado_pts: 18.0,
  total_gestao_pts: 11.5,
  total_engajamento_pts: 14.0,
  risco_classificacao: 'AMARELO',
  nmrr_pct: 38.6,
  nmrr_pts: 0,
  nmrr_realizado: 15861,
  nmrr_meta: 41044,
  reunioes_ec_du_realizado: 3.91,
  reunioes_ec_du_pts: 1.5,
  contadores_trabalhados_pct: 66.47,
  contadores_trabalhados_pts: 0,
  contadores_indicando_pct: 16.57,
  contadores_indicando_pts: 0,
  conversao_total_pct: 39.51,
  conversao_total_pts: 4.0,
  demo_du_realizado: 1.2,
  demo_du_pts: 0,
  early_churn_pct: 11.2,
  early_churn_pts: 0,
  crescimento_40_pct: 28.39,
  crescimento_40_pts: 0,
  created_at: '2026-04-23T10:00:00Z',
}

function renderPEX() {
  return render(
    <MemoryRouter>
      <PEXDashboard />
    </MemoryRouter>
  )
}

describe('PEXDashboard', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('exibe estado vazio quando não há dados', async () => {
    axios.get.mockRejectedValue({ response: { status: 404 } })
    renderPEX()
    await waitFor(() => {
      expect(screen.getByText(/Nenhum dado carregado/i)).toBeInTheDocument()
    })
  })

  it('exibe a pontuação do PEX quando há dados', async () => {
    axios.get.mockImplementation((url) => {
      if (url.includes('painel'))    return Promise.resolve({ data: mockPainel })
      if (url.includes('compliance'))return Promise.resolve({ data: [] })
      if (url.includes('historico')) return Promise.resolve({ data: [] })
      return Promise.resolve({ data: null })
    })
    renderPEX()
    await waitFor(() => {
      expect(screen.getByText(/36\.5/)).toBeInTheDocument()
    })
  })

  it('exibe classificação correta para 36.5 pts', async () => {
    axios.get.mockImplementation((url) => {
      if (url.includes('painel')) return Promise.resolve({ data: mockPainel })
      return Promise.resolve({ data: [] })
    })
    renderPEX()
    await waitFor(() => {
      expect(screen.getByText(/Franquia em Desenvolvimento/i)).toBeInTheDocument()
    })
  })

  it('exibe alerta de risco de descredenciamento abaixo de 36', async () => {
    axios.get.mockImplementation((url) => {
      if (url.includes('painel')) return Promise.resolve({ data: { ...mockPainel, total_geral_pts: 35.9, risco_classificacao: 'VERMELHO' } })
      return Promise.resolve({ data: [] })
    })
    renderPEX()
    await waitFor(() => {
      expect(screen.getByText(/Risco de descredenciamento/i)).toBeInTheDocument()
    })
  })

  it('botão de upload está presente e habilitado', async () => {
    axios.get.mockRejectedValue({})
    renderPEX()
    await waitFor(() => {
      expect(screen.getByText(/Upload CROmie/i)).toBeInTheDocument()
    })
  })

  it('navega para aba de compliance ao clicar', async () => {
    axios.get.mockImplementation((url) => {
      if (url.includes('painel'))     return Promise.resolve({ data: mockPainel })
      if (url.includes('compliance')) return Promise.resolve({ data: [
        { usuario_responsavel: 'vendedor@omie.com.vc', leads_sem_tarefa_futura: 5,
          leads_sem_temperatura: 2, leads_sem_previsao: 3, leads_sem_ticket: 1,
          contadores_sem_tarefa_mes: 8, pontos_em_risco: 1.5 }
      ]})
      return Promise.resolve({ data: [] })
    })
    renderPEX()
    await waitFor(() => screen.getByText(/COMPLIANCE/i))
    fireEvent.click(screen.getByText(/COMPLIANCE/i))
    await waitFor(() => {
      expect(screen.getByText('vendedor@omie.com.vc')).toBeInTheDocument()
    })
  })

  it('exibe mensagem de sucesso após upload', async () => {
    axios.get.mockRejectedValue({})
    axios.post.mockResolvedValue({
      data: {
        schema_alterado: false,
        totais: { total_cliente_final: 150, total_contador: 120 },
        pex: { total_geral_pts: 42.0, risco: 'AMARELO' },
        erros: [],
      }
    })
    renderPEX()
    await waitFor(() => screen.getByText(/Upload CROmie/i))
    const input = document.querySelector('input[type="file"]')
    const file = new File(['conteudo'], 'BD_CROMIE.xlsx', { type: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet' })
    fireEvent.change(input, { target: { files: [file] } })
    await waitFor(() => {
      expect(screen.getByText(/CROmie processado/i)).toBeInTheDocument()
    })
  })

  it('exibe aviso quando schema foi alterado', async () => {
    axios.get.mockRejectedValue({})
    axios.post.mockResolvedValue({
      data: {
        schema_alterado: true,
        colunas_novas: ['cliente_final:Nova Coluna 2027'],
        colunas_removidas: [],
        totais: { total_cliente_final: 100 },
        pex: { total_geral_pts: 40.0, risco: 'AMARELO' },
        erros: [],
      }
    })
    renderPEX()
    await waitFor(() => screen.getByText(/Upload CROmie/i))
    const input = document.querySelector('input[type="file"]')
    const file = new File(['x'], 'BD_CROMIE.xlsx', { type: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet' })
    fireEvent.change(input, { target: { files: [file] } })
    await waitFor(() => {
      expect(screen.getByText(/Schema alterado/i)).toBeInTheDocument()
    })
  })
})
