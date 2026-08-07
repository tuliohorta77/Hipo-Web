// web/src/tests/Contas.test.jsx
//
// Cobre o que dá identidade à tela: máscara e validação de CNPJ no cliente,
// KPIs que aplicam filtro (dashboard operacional), busca com debounce e o
// tratamento do 409 de CNPJ duplicado — que precisa oferecer abrir a conta
// existente, não só mostrar um erro.
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, fireEvent, cleanup, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';

const mockGet = vi.fn();
const mockPost = vi.fn();
const mockPatch = vi.fn();
const mockDelete = vi.fn();

vi.mock('../api', () => ({
  default: {
    get: (...a) => mockGet(...a),
    post: (...a) => mockPost(...a),
    patch: (...a) => mockPatch(...a),
    delete: (...a) => mockDelete(...a),
  },
}));

import Contas, { mascararCnpj, cnpjValido } from '../pages/crm/Contas';

const RESUMO = {
  total: 3, ativas: 2, inativas: 1, finders: 1,
  sem_oportunidade_ativa: 1, sem_vertical: 2, por_vertical: [],
};

const CONTA = {
  id: 'c1', razao_social: 'Metalurgica Alfa LTDA', nome_fantasia: 'Alfa',
  cnpj: '11222333000181', cnpj_formatado: '11.222.333/0001-81',
  cidade: 'Guarulhos', uf: 'SP', vertical_id: 1, vertical_nome: 'Metalúrgica',
  num_funcionarios: 120, eh_finder: false, ativo: true,
  vendedores: ['Ana Vendas'], qtd_oportunidades_ativas: 2,
  criado_em: '2026-08-01T12:00:00Z',
};

const DETALHE = { ...CONTA, contatos: [], oportunidades: [], observacoes: null };

function respostaPadrao(url) {
  if (url === '/crm/contas') return Promise.resolve({ data: { total: 1, limit: 50, offset: 0, itens: [CONTA] } });
  if (url === '/crm/contas/resumo') return Promise.resolve({ data: RESUMO });
  if (url === '/crm/dominio/verticais') return Promise.resolve({ data: [{ id: 1, nome: 'Metalúrgica', slug: 'metalurgica' }] });
  if (url === '/crm/contas/c1') return Promise.resolve({ data: DETALHE });
  if (url === '/crm/contatos/busca') return Promise.resolve({ data: [] });
  return Promise.resolve({ data: {} });
}

function renderContas() {
  return render(<MemoryRouter><Contas /></MemoryRouter>);
}

beforeEach(() => {
  mockGet.mockReset();
  mockPost.mockReset();
  mockPatch.mockReset();
  mockDelete.mockReset();
  mockGet.mockImplementation((url) => respostaPadrao(url));
});

afterEach(cleanup);


// ── Funções puras ────────────────────────────────────────────────────

describe('mascararCnpj', () => {
  it('formata progressivamente', () => {
    expect(mascararCnpj('11')).toBe('11');
    expect(mascararCnpj('11222')).toBe('11.222');
    expect(mascararCnpj('11222333')).toBe('11.222.333');
    expect(mascararCnpj('112223330001')).toBe('11.222.333/0001');
    expect(mascararCnpj('11222333000181')).toBe('11.222.333/0001-81');
  });

  it('ignora caracteres não numéricos', () => {
    expect(mascararCnpj('a1b1c2')).toBe('11.2');
  });

  it('trunca em 14 dígitos', () => {
    expect(mascararCnpj('1122233300018199999')).toBe('11.222.333/0001-81');
  });

  it('aceita vazio e nulo', () => {
    expect(mascararCnpj('')).toBe('');
    expect(mascararCnpj(null)).toBe('');
  });
});

describe('cnpjValido', () => {
  it('aceita CNPJs reais', () => {
    for (const c of ['11.222.333/0001-81', '34.028.316/0001-03', '47.960.950/0001-21']) {
      expect(cnpjValido(c)).toBe(true);
    }
  });

  it('rejeita dígito verificador errado', () => {
    expect(cnpjValido('11222333000182')).toBe(false);
  });

  it('rejeita dígitos repetidos', () => {
    expect(cnpjValido('00000000000000')).toBe(false);
    expect(cnpjValido('11111111111111')).toBe(false);
  });

  it('rejeita tamanho errado, vazio e nulo', () => {
    expect(cnpjValido('1122233300018')).toBe(false);
    expect(cnpjValido('')).toBe(false);
    expect(cnpjValido(null)).toBe(false);
  });
});


// ── Renderização ─────────────────────────────────────────────────────

describe('Contas — carga inicial', () => {
  it('mostra os KPIs vindos do resumo', async () => {
    renderContas();
    expect(await screen.findByText('Contas ativas')).toBeInTheDocument();
    expect(screen.getByText('Sem oportunidade aberta')).toBeInTheDocument();
    expect(screen.getByText('Parceiros indicadores')).toBeInTheDocument();
  });

  it('lista a conta com CNPJ formatado e vendedor derivado', async () => {
    renderContas();
    expect(await screen.findByText('Metalurgica Alfa LTDA')).toBeInTheDocument();
    expect(screen.getByText('11.222.333/0001-81')).toBeInTheDocument();
    expect(screen.getByText('Ana Vendas')).toBeInTheDocument();
  });

  it('mostra estado vazio quando não há contas', async () => {
    mockGet.mockImplementation((url) =>
      url === '/crm/contas'
        ? Promise.resolve({ data: { total: 0, limit: 50, offset: 0, itens: [] } })
        : respostaPadrao(url)
    );
    renderContas();
    expect(await screen.findByText('Nenhuma conta cadastrada')).toBeInTheDocument();
  });

  it('mostra erro quando a API falha', async () => {
    mockGet.mockRejectedValue({ response: { data: { detail: 'Boom' } } });
    renderContas();
    expect(await screen.findByText('Boom')).toBeInTheDocument();
  });
});


// ── Dashboard operacional: KPI aplica filtro ─────────────────────────

describe('Contas — drilldown pelos KPIs', () => {
  it('clicar em "Sem oportunidade aberta" filtra a listagem', async () => {
    renderContas();
    await screen.findByText('Metalurgica Alfa LTDA');
    mockGet.mockClear();

    fireEvent.click(screen.getByText('Sem oportunidade aberta').closest('button'));

    await waitFor(() => {
      const chamada = mockGet.mock.calls.find(([url]) => url === '/crm/contas');
      expect(chamada[1].params.sem_oportunidade_ativa).toBe(true);
    });
  });

  it('clicar em "Parceiros indicadores" filtra por eh_finder', async () => {
    renderContas();
    await screen.findByText('Metalurgica Alfa LTDA');
    mockGet.mockClear();

    fireEvent.click(screen.getByText('Parceiros indicadores').closest('button'));

    await waitFor(() => {
      const chamada = mockGet.mock.calls.find(([url]) => url === '/crm/contas');
      expect(chamada[1].params.eh_finder).toBe('true');
    });
  });

  it('mostra o botão de limpar quando há filtro ativo', async () => {
    renderContas();
    await screen.findByText('Metalurgica Alfa LTDA');
    fireEvent.click(screen.getByText('Parceiros indicadores').closest('button'));
    expect(await screen.findByText('Limpar filtros')).toBeInTheDocument();
  });

  it('clicar duas vezes no mesmo KPI desfaz o filtro', async () => {
    renderContas();
    await screen.findByText('Metalurgica Alfa LTDA');
    const kpi = screen.getByText('Parceiros indicadores').closest('button');

    fireEvent.click(kpi);
    await waitFor(() => expect(kpi).toHaveAttribute('aria-pressed', 'true'));

    mockGet.mockClear();
    fireEvent.click(kpi);
    await waitFor(() => expect(kpi).toHaveAttribute('aria-pressed', 'false'));
    await waitFor(() => {
      const chamada = mockGet.mock.calls.find(([url]) => url === '/crm/contas');
      expect(chamada[1].params.eh_finder).toBeUndefined();
    });
  });

  it('só um KPI fica ativo por vez', async () => {
    renderContas();
    await screen.findByText('Metalurgica Alfa LTDA');
    const finders = screen.getByText('Parceiros indicadores').closest('button');
    const semOp = screen.getByText('Sem oportunidade aberta').closest('button');

    fireEvent.click(finders);
    await waitFor(() => expect(finders).toHaveAttribute('aria-pressed', 'true'));

    fireEvent.click(semOp);
    await waitFor(() => expect(semOp).toHaveAttribute('aria-pressed', 'true'));
    expect(finders).toHaveAttribute('aria-pressed', 'false');
  });

  it('clicar em "Sem vertical" filtra por sem_vertical', async () => {
    renderContas();
    await screen.findByText('Metalurgica Alfa LTDA');
    mockGet.mockClear();

    fireEvent.click(screen.getByText('Sem vertical').closest('button'));

    await waitFor(() => {
      const chamada = mockGet.mock.calls.find(([url]) => url === '/crm/contas');
      expect(chamada[1].params.sem_vertical).toBe(true);
    });
  });
});


// ── Formulário ───────────────────────────────────────────────────────

describe('Contas — formulário', () => {
  async function abrirForm() {
    renderContas();
    await screen.findByText('Metalurgica Alfa LTDA');
    fireEvent.click(screen.getByText('Nova conta'));
    return screen.findByLabelText('CNPJ *');
  }

  it('aplica máscara enquanto digita o CNPJ', async () => {
    const campo = await abrirForm();
    fireEvent.change(campo, { target: { value: '11222333000181' } });
    expect(campo.value).toBe('11.222.333/0001-81');
  });

  it('acusa CNPJ inválido sem chamar a API', async () => {
    const campo = await abrirForm();
    fireEvent.change(screen.getByLabelText('Razão social *'), { target: { value: 'Teste SA' } });
    fireEvent.change(campo, { target: { value: '11222333000182' } });
    fireEvent.click(screen.getByText('Criar conta'));

    expect(await screen.findByText('CNPJ inválido.')).toBeInTheDocument();
    expect(mockPost).not.toHaveBeenCalled();
  });

  it('exige razão social', async () => {
    const campo = await abrirForm();
    fireEvent.change(campo, { target: { value: '11222333000181' } });
    fireEvent.click(screen.getByText('Criar conta'));

    expect(await screen.findByText('Informe a razão social.')).toBeInTheDocument();
    expect(mockPost).not.toHaveBeenCalled();
  });

  it('envia o CNPJ só com dígitos', async () => {
    mockPost.mockResolvedValue({ data: CONTA });
    const campo = await abrirForm();
    fireEvent.change(screen.getByLabelText('Razão social *'), { target: { value: 'Teste SA' } });
    fireEvent.change(campo, { target: { value: '11222333000181' } });
    fireEvent.click(screen.getByText('Criar conta'));

    await waitFor(() => expect(mockPost).toHaveBeenCalled());
    const [url, corpo] = mockPost.mock.calls[0];
    expect(url).toBe('/crm/contas');
    expect(corpo.cnpj).toBe('11222333000181');
  });

  it('oferece abrir a conta existente no 409 de CNPJ duplicado', async () => {
    mockPost.mockRejectedValue({
      response: {
        status: 409,
        data: {
          detail: {
            erro: 'cnpj_duplicado',
            mensagem: 'O CNPJ 11.222.333/0001-81 já está cadastrado.',
            conta_id: 'c1',
            razao_social: 'Metalurgica Alfa LTDA',
            ativo: true,
          },
        },
      },
    });
    const campo = await abrirForm();
    fireEvent.change(screen.getByLabelText('Razão social *'), { target: { value: 'Outro Nome' } });
    fireEvent.change(campo, { target: { value: '11222333000181' } });
    fireEvent.click(screen.getByText('Criar conta'));

    expect(await screen.findByText('Abrir a conta existente')).toBeInTheDocument();
    expect(screen.getByText(/já está cadastrado/)).toBeInTheDocument();
  });

  it('cria vertical pelo próprio formulário', async () => {
    mockPost.mockResolvedValue({ data: { id: 9, nome: 'Saúde', slug: 'saude' } });
    await abrirForm();
    fireEvent.change(screen.getByLabelText('Criar nova'), { target: { value: 'Saúde' } });
    fireEvent.click(screen.getByText('Adicionar'));

    await waitFor(() => {
      expect(mockPost).toHaveBeenCalledWith('/crm/dominio/verticais', { nome: 'Saúde' });
    });
  });

  it('bloqueia edição do CNPJ ao abrir uma conta existente', async () => {
    renderContas();
    fireEvent.click(await screen.findByText('Metalurgica Alfa LTDA'));
    const campo = await screen.findByLabelText('CNPJ *');
    expect(campo).toBeDisabled();
  });

  it('busca o detalhe da conta ao abrir, não usa o resumo da lista', async () => {
    renderContas();
    fireEvent.click(await screen.findByText('Metalurgica Alfa LTDA'));
    await waitFor(() =>
      expect(mockGet.mock.calls.some(([url]) => url === '/crm/contas/c1')).toBe(true)
    );
  });

  it('mostra a seção de contatos só na edição', async () => {
    renderContas();
    await screen.findByText('Metalurgica Alfa LTDA');

    fireEvent.click(screen.getByText('Nova conta'));
    await screen.findByLabelText('CNPJ *');
    expect(screen.queryByText('Contatos')).not.toBeInTheDocument();

    fireEvent.click(screen.getByText('Cancelar'));
    fireEvent.click(screen.getByText('Metalurgica Alfa LTDA'));
    expect(await screen.findByText('Contatos')).toBeInTheDocument();
  });
});
