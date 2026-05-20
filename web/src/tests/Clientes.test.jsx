import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, waitFor, cleanup, fireEvent } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'

// Mock do api antes do import da página
vi.mock('../api', () => ({
  default: {
    get: vi.fn(),
    post: vi.fn(),
  },
  getUser: () => ({ nome: 'Tulio', cargo: 'ADM' }),
  getModulos: () => ['pex', 'po', 'bd', 'carteira', 'clientes', 'metas'],
  isAuthenticated: () => true,
}))

import api from '../api'
import Clientes from '../pages/Clientes'

const resumoVazio = {
  oportunidades: { total: 0, em_andamento: 0, conquistado: 0, perdido: 0, cancelado: 0 },
  tarefas: { total: 0, atrasada: 0 },
  ultimo_upload_oportunidades: null,
  ultimo_upload_tarefas: null,
}

const resumoCheio = {
  oportunidades: { total: 1500, em_andamento: 300, conquistado: 200, perdido: 800, cancelado: 200 },
  tarefas: { total: 3000, atrasada: 50 },
  ultimo_upload_oportunidades: {
    data_upload: '2026-05-19T10:00:00Z',
    nome_arquivo: 'ops.xlsx',
    total_validos: 1500,
  },
  ultimo_upload_tarefas: null,
}

function renderClientes() {
  return render(
    <MemoryRouter>
      <Clientes />
    </MemoryRouter>
  )
}

beforeEach(() => {
  cleanup()
  vi.clearAllMocks()
})

describe('Clientes — render básico', () => {
  it('renderiza titulo e cabecalho', async () => {
    api.get.mockResolvedValueOnce({ data: resumoVazio })  // /clientes/resumo
    api.get.mockResolvedValueOnce({ data: { total: 0, items: [], page: 1, page_size: 50 } }) // ops

    renderClientes()

    // Titulo: usa H1 pra ser inambíguo
    expect(screen.getByRole('heading', { name: 'Clientes', level: 1 })).toBeInTheDocument()

    // Subtítulo do header (texto exato)
    expect(screen.getByText('Oportunidades comerciais e tarefas dos leads.')).toBeInTheDocument()

    // Espera a página estabilizar
    await waitFor(() => {
      expect(screen.getByText('Nenhuma oportunidade')).toBeInTheDocument()
    })
  })

  it('mostra KPIs quando há dados', async () => {
    api.get.mockResolvedValueOnce({ data: resumoCheio })
    api.get.mockResolvedValueOnce({ data: { total: 0, items: [], page: 1, page_size: 50 } })

    renderClientes()

    await waitFor(() => {
      // Labels únicos dos KpiCards
      expect(screen.getByText('Total de Oportunidades')).toBeInTheDocument()
      expect(screen.getByText('Conquistadas')).toBeInTheDocument()
      expect(screen.getByText('Tarefas Atrasadas')).toBeInTheDocument()
      // Valor formatado
      expect(screen.getByText('1.500')).toBeInTheDocument()
      expect(screen.getByText('300')).toBeInTheDocument()
    })
  })

  it('renderiza tabela de oportunidades', async () => {
    api.get.mockResolvedValueOnce({ data: resumoVazio })
    api.get.mockResolvedValueOnce({
      data: {
        total: 2,
        page: 1,
        page_size: 50,
        items: [
          {
            op_id: 1, cnpj: '00.111.222/0001-33', razao_social: 'ACME LTDA',
            status: 'Em andamento', fase: '02. Cadência',
            cnpj_contador: '99.888.777/0001-66', razao_contador: 'CONT XYZ',
            previsao_valor: 1500, dias_parado: 5,
          },
          {
            op_id: 2, cnpj: '01.222.333/0001-44', razao_social: 'OUTRA',
            status: 'Conquistado', fase: '06. Conquistado',
            cnpj_contador: '99.888.777/0001-66', razao_contador: 'CONT XYZ',
            previsao_valor: 500, dias_parado: 0,
          },
        ],
      }
    })

    renderClientes()

    await waitFor(() => {
      expect(screen.getByText('ACME LTDA')).toBeInTheDocument()
      expect(screen.getByText('OUTRA')).toBeInTheDocument()
    })
  })
})

describe('Clientes — interações', () => {
  it('alterna entre aba Oportunidades e Tarefas', async () => {
    api.get.mockResolvedValueOnce({ data: resumoVazio })
    api.get.mockResolvedValueOnce({ data: { total: 0, items: [], page: 1, page_size: 50 } }) // ops

    renderClientes()

    // Espera carregar
    await waitFor(() => {
      expect(screen.getByText('Nenhuma oportunidade')).toBeInTheDocument()
    })

    // Próxima chamada: troca pra Tarefas
    api.get.mockResolvedValueOnce({ data: { total: 0, items: [], page: 1, page_size: 50 } })

    // Buscar a aba pelo role button - a aba Tarefas é a segunda
    // (há também botões "Tarefas" no UploadButton, mas com role="" porque é <label>)
    const tabs = screen.getAllByRole('button').filter(
      (b) => b.textContent.trim() === 'Tarefas'
    )
    expect(tabs.length).toBeGreaterThan(0)
    fireEvent.click(tabs[0])

    await waitFor(() => {
      expect(screen.getByText('Nenhuma tarefa')).toBeInTheDocument()
    })
  })

  it('faz upload de oportunidades chama endpoint correto', async () => {
    api.get.mockResolvedValueOnce({ data: resumoVazio })
    api.get.mockResolvedValueOnce({ data: { total: 0, items: [], page: 1, page_size: 50 } })

    const { container } = renderClientes()
    await waitFor(() => expect(screen.getByText('Nenhuma oportunidade')).toBeInTheDocument())

    // Mock do post
    api.post.mockResolvedValueOnce({
      data: { upload_id: 'abc', total_linhas: 100, total_validos: 99, erros: [] }
    })
    // Mocks pros recarregamentos que rolam após upload
    api.get.mockResolvedValueOnce({ data: resumoVazio })
    api.get.mockResolvedValueOnce({ data: { total: 99, items: [], page: 1, page_size: 50 } })

    // Pegar os inputs de arquivo (UploadButton renderiza um <input type="file"> escondido)
    const fileInputs = container.querySelectorAll('input[type="file"]')
    expect(fileInputs.length).toBeGreaterThan(0)

    const arquivo = new File(['fake'], 'ops.xlsx', {
      type: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
    })
    fireEvent.change(fileInputs[0], { target: { files: [arquivo] } })

    await waitFor(() => {
      expect(api.post).toHaveBeenCalledWith(
        '/clientes/upload-oportunidades',
        expect.any(FormData),
      )
    })
  })
})
