import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import axios from 'axios'
import POsDashboard from '../pages/POs'

const mockReconciliacao = [
  { tipo: 'COMISSAO', tem_enabler: false, status_reconciliacao: 'CONFORME',   quantidade: 20, valor_total: 38000, divergencia_total: 0 },
  { tipo: 'COMISSAO', tem_enabler: true,  status_reconciliacao: 'CONFORME',   quantidade: 15, valor_total: 14250, divergencia_total: 0 },
  { tipo: 'COMISSAO', tem_enabler: false, status_reconciliacao: 'AUSENTE',    quantidade: 3,  valor_total: 5700,  divergencia_total: 0 },
  { tipo: 'REPASSE',  tem_enabler: false, status_reconciliacao: 'DIVERGENTE', quantidade: 1,  valor_total: 375,   divergencia_total: -125 },
]

const mockAusentes = [
  { referencia_aplicativo: 'APP123', razao_social: 'Empresa Sumida Ltda', tipo: 'COMISSAO',
    valor_esperado: 1900, situacao: 'ACTIVE', saude_paciente: 'Bom', contador_nome: 'Silva Contabilidade' },
]

const mockDivergentes = [
  { referencia_aplicativo: 'APP456', razao_social: 'Empresa Divergente SA',
    tipo: 'REPASSE', valor_esperado: 500, valor_recebido: 375,
    divergencia_valor: -125, semana_ref: '2026-04-20' },
]

function renderPOs() {
  return render(<MemoryRouter><POsDashboard /></MemoryRouter>)
}

describe('POsDashboard', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    axios.get.mockImplementation((url) => {
      if (url.includes('reconciliacao/ultima'))    return Promise.resolve({ data: mockReconciliacao })
      if (url.includes('reconciliacao/ausentes'))  return Promise.resolve({ data: mockAusentes })
      if (url.includes('reconciliacao/divergentes'))return Promise.resolve({ data: mockDivergentes })
      if (url.includes('historico'))               return Promise.resolve({ data: [] })
      if (url.includes('resumo/financeiro'))       return Promise.resolve({ data: [] })
      return Promise.resolve({ data: [] })
    })
  })

  it('renderiza o painel de POs', async () => {
    renderPOs()
    await waitFor(() => {
      expect(screen.getByText(/Módulo POs/i)).toBeInTheDocument()
    })
  })

  it('exibe KPI de valor recebido', async () => {
    renderPOs()
    await waitFor(() => {
      // R$ 38k + R$ 14.25k de conformes
      expect(screen.getByText(/Recebido/i)).toBeInTheDocument()
    })
  })

  it('exibe badge de ausentes na aba', async () => {
    renderPOs()
    await waitFor(() => {
      // Badge com contagem de ausentes
      expect(screen.getByText('1')).toBeInTheDocument()
    })
  })

  it('mostra lista de ausentes ao clicar na aba', async () => {
    renderPOs()
    await waitFor(() => screen.getByTestId('tab-ausentes'))
    fireEvent.click(screen.getByTestId('tab-ausentes'))
    await waitFor(() => {
      expect(screen.getByText('Empresa Sumida Ltda')).toBeInTheDocument()
      expect(screen.getByText('Silva Contabilidade')).toBeInTheDocument()
    })
  })

  it('mostra lista de divergentes ao clicar na aba', async () => {
    renderPOs()
    await waitFor(() => screen.getByTestId('tab-divergentes'))
    fireEvent.click(screen.getByTestId('tab-divergentes'))
    await waitFor(() => {
      expect(screen.getByText('Empresa Divergente SA')).toBeInTheDocument()
    })
  })

  it('exibe mensagem de sucesso após upload', async () => {
    axios.post.mockResolvedValue({
      data: {
        tipo: 'COMISSAO', tem_enabler: false,
        total_linhas: 25, semana_ref: '2026-04-20',
        message: 'PO processada com sucesso.',
      }
    })
    renderPOs()
    await waitFor(() => screen.getByText(/Upload PO/i))
    const input = document.querySelector('input[type="file"]')
    const file = new File(['x'], 'Omie_Apuracao_ComissaoV6_2026_4_Abril.xlsx', {
      type: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
    })
    fireEvent.change(input, { target: { files: [file] } })
    await waitFor(() => {
      expect(screen.getByText(/PO processada/i)).toBeInTheDocument()
    })
  })

  it('exibe erro quando upload falha', async () => {
    axios.post.mockRejectedValue({
      response: { data: { detail: 'Tipo de PO não reconhecido' } }
    })
    renderPOs()
    await waitFor(() => screen.getByText(/Upload PO/i))
    const input = document.querySelector('input[type="file"]')
    const file = new File(['x'], 'arquivo_invalido.xlsx', { type: 'application/vnd.ms-excel' })
    fireEvent.change(input, { target: { files: [file] } })
    await waitFor(() => {
      expect(screen.getByText(/Tipo de PO não reconhecido/i)).toBeInTheDocument()
    })
  })

  it('botão de upload fica desabilitado durante o processamento', async () => {
    let resolve
    axios.post.mockImplementation(() => new Promise(r => { resolve = r }))
    renderPOs()
    await waitFor(() => screen.getByText(/Upload PO/i))
    const input = document.querySelector('input[type="file"]')
    const file = new File(['x'], 'Omie_Apuracao_Incentivo_2026_4_Abril.xlsx', {
      type: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
    })
    fireEvent.change(input, { target: { files: [file] } })
    await waitFor(() => {
      expect(screen.getByText(/Processando/i)).toBeInTheDocument()
    })
    resolve({ data: { tipo: 'INCENTIVO', tem_enabler: false, total_linhas: 5, semana_ref: null } })
  })
})