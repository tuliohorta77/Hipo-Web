// web/src/tests/Contratos.test.jsx
//
// Módulo Contratos (043). As promessas da tela:
//   1. o mês mostra os KPIs e a próxima ação que veio do servidor
//   2. linha sem lançamento mostra a SUGESTÃO e o botão Lançar
//   3. lançar grava pela API com o percentual vazio (o servidor decide o
//      primeiro mês) e a prévia K/L/N/O acompanha o que se digita
//   4. "Confirmar sugestões" lança os pendentes de uma vez
//   5. a nota: desconto e número da NF vão para a API
//   6. a aba Contratos lista e gera contratos a partir da oportunidade
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, fireEvent, cleanup, waitFor, within } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';

const mockGet = vi.fn();
const mockPost = vi.fn();
const mockPut = vi.fn();
const mockPatch = vi.fn();
const mockDelete = vi.fn();

vi.mock('../api', () => ({
  default: {
    get: (...a) => mockGet(...a),
    post: (...a) => mockPost(...a),
    put: (...a) => mockPut(...a),
    patch: (...a) => mockPatch(...a),
    delete: (...a) => mockDelete(...a),
  },
}));

import Contratos from '../pages/contratos/Contratos';
import { calcularRepasse, reais, rotuloCompetencia } from '../components/contratos/repasseCalculo';

const CONTRATO_A = {
  id: 'c1', razao_social: 'SERVCON UNIQUE', cnpj: '32390090000160',
  cnpj_formatado: '32.390.090/0001-60', oportunidade_numero: 'OPP-2026-00010',
  grupo: 'GRUPO B', modalidade: 'por_vida', vidas: 142, valor_por_vida: 11.5,
  valor_fixo: null, percentual_repasse: 30, percentual_primeiro_mes: 100,
  imposto_percentual: 14.33, status: 'ativo', data_venda: '2026-02-02',
};
const CONTRATO_B = {
  id: 'c2', razao_social: 'TONBOO ELETRONICOS', cnpj: '62136173000199',
  cnpj_formatado: '62.136.173/0001-99', oportunidade_numero: 'OPP-2026-00011',
  grupo: null, modalidade: 'valor_fixo', vidas: 5, valor_por_vida: null,
  valor_fixo: 180, percentual_repasse: 30, percentual_primeiro_mes: 100,
  imposto_percentual: 14.33, status: 'ativo', data_venda: '2026-09-01',
};

function painel(extra = {}) {
  return {
    competencia: '2026-10', rotulo: 'out/2026', anterior: '2026-09', seguinte: '2026-11',
    lancados: 1, pendentes: 1,
    linhas: [
      {
        contrato: CONTRATO_A,
        lancamento: {
          id: 'l1', competencia: '2026-10', vidas: 142, valor_por_vida: 11.5,
          valor_contrato: 1633, percentual_repasse: 30, valor_repasse: 489.9,
          imposto_percentual: 14.33, valor_imposto: 70.2, valor_liquido: 419.7,
          primeiro_mes: false, pago: true,
        },
        sugestao: null,
      },
      {
        contrato: CONTRATO_B,
        lancamento: null,
        sugestao: {
          vidas: 5, valor_por_vida: null, valor_fixo: 180, primeiro_mes: true,
          valor_contrato: 180, percentual_repasse: 100, valor_repasse: 180,
          imposto_percentual: 14.33, valor_imposto: 25.79, valor_liquido: 154.21,
        },
      },
    ],
    totais: {
      valor_contrato: 1633, valor_repasse: 489.9, valor_imposto: 70.2,
      valor_liquido: 419.7, vidas: 142, liquido_pago: 419.7, descontos: 0, valor_nf: 419.7,
    },
    descontos: [],
    fechamento: { nf_numero: null, nf_emitida_em: null, recebido_em: null, observacoes: null },
    proximo_passo: { acao: 'lancar', texto: 'Lançar vidas e valores de 1 contrato de out/2026.' },
    historico: [
      { competencia: '2026-09', rotulo: 'set/2026', valor_nf: 5923.18 },
      { competencia: '2026-10', rotulo: 'out/2026', valor_nf: 419.7 },
    ],
    ...extra,
  };
}

function renderTela() {
  return render(<MemoryRouter><Contratos /></MemoryRouter>);
}

beforeEach(() => {
  mockGet.mockReset();
  mockPost.mockReset();
  mockPut.mockReset();
  mockPatch.mockReset();
  mockDelete.mockReset();
  mockGet.mockImplementation((url) => {
    if (url === '/repasses/painel') return Promise.resolve({ data: painel() });
    if (url === '/repasses/contratos') return Promise.resolve({ data: [CONTRATO_A, CONTRATO_B] });
    if (url === '/repasses/oportunidades') {
      return Promise.resolve({
        data: [{
          id: 'o1', numero: 'OPP-2026-00099', razao_social: 'ONIX SEGUROS',
          data_conquista: '2026-08-31',
          cnpjs_sem_contrato: [{ cnpj: '07251199000170', cnpj_formatado: '07.251.199/0001-70',
            razao_social: 'ONIX SEGUROS', vidas: 21, mensalidade: 273 }],
        }],
      });
    }
    return Promise.reject(new Error(`GET inesperado ${url}`));
  });
  mockPut.mockResolvedValue({ data: {} });
  mockPost.mockResolvedValue({ data: {} });
});

afterEach(cleanup);

describe('repasseCalculo', () => {
  it('confere com a planilha (181 vidas a 11,50, 30%, 14,33%)', () => {
    const c = calcularRepasse({ vidas: 181, valorPorVida: '11,50', percentual: 30, imposto: 14.33 });
    expect(c).toEqual({
      valorContrato: 2081.5, valorRepasse: 624.45, valorImposto: 89.48, valorLiquido: 534.97,
    });
  });

  it('valor fixo no primeiro mês a 100%', () => {
    const c = calcularRepasse({ vidas: 1, valorFixo: '130', percentual: 100, imposto: '14.33' });
    expect(c.valorLiquido).toBe(111.37);
  });

  it('sem valor não calcula', () => {
    expect(calcularRepasse({ vidas: 1, percentual: 30, imposto: 10 })).toBeNull();
  });

  it('formata reais e competência', () => {
    expect(reais(5923.18).replace(/\s/g, ' ')).toBe('R$ 5.923,18');
    expect(rotuloCompetencia('2026-02')).toBe('fev/2026');
  });
});

describe('Contratos — aba Mês', () => {
  it('mostra o mês, os KPIs, a próxima ação e a sugestão do pendente', async () => {
    renderTela();
    expect(await screen.findByTestId('competencia')).toHaveTextContent('out/2026');
    expect(screen.getByTestId('proximo-passo')).toHaveTextContent('Lançar vidas e valores de 1 contrato');
    expect(screen.getByTestId('valor-nf')).toHaveTextContent('419,70');
    // Somas do cabeçalho contam lançado + sugestão (1.633 + 180).
    expect(screen.getByText((_, el) => el?.tagName === 'SPAN' && /1\.813,00/.test(el.textContent))).toBeInTheDocument();
    expect(screen.getByText('147')).toBeInTheDocument();

    const pendente = screen.getByTestId('linha-c2');
    expect(within(pendente).getByText('1º mês')).toBeInTheDocument();
    expect(within(pendente).getByRole('button', { name: 'Lançar' })).toBeInTheDocument();
    const lancado = screen.getByTestId('linha-c1');
    expect(within(lancado).getByText('pago')).toBeInTheDocument();
    expect(within(lancado).getByRole('button', { name: 'Editar' })).toBeInTheDocument();
  });

  it('lançar grava sem percentual (regra do servidor) e mostra a prévia', async () => {
    renderTela();
    const pendente = await screen.findByTestId('linha-c2');
    fireEvent.click(within(pendente).getByRole('button', { name: 'Lançar' }));

    const previa = await screen.findByTestId('previa');
    expect(previa).toHaveTextContent('154,21');
    fireEvent.change(screen.getByLabelText('Vidas cobradas'), { target: { value: '6' } });
    fireEvent.change(screen.getByLabelText('Valor do mês'), { target: { value: '220' } });
    expect(screen.getByTestId('previa')).toHaveTextContent('188,47');

    fireEvent.click(screen.getByTestId('gravar-lancamento'));
    await waitFor(() => expect(mockPut).toHaveBeenCalled());
    const [url, corpo] = mockPut.mock.calls[0];
    expect(url).toBe('/repasses/contratos/c2/lancamentos/2026-10');
    expect(corpo).toMatchObject({ vidas: 6, valor_fixo: 220, valor_por_vida: null, percentual_repasse: null });
  });

  it('editar lançamento existente mantém o percentual gravado', async () => {
    renderTela();
    const lancado = await screen.findByTestId('linha-c1');
    fireEvent.click(within(lancado).getByRole('button', { name: 'Editar' }));
    fireEvent.click(await screen.findByTestId('gravar-lancamento'));
    await waitFor(() => expect(mockPut).toHaveBeenCalled());
    expect(mockPut.mock.calls[0][1]).toMatchObject({
      vidas: 142, valor_por_vida: 11.5, percentual_repasse: 30, pago: true,
    });
  });

  it('confirmar sugestões lança os pendentes', async () => {
    renderTela();
    fireEvent.click(await screen.findByRole('button', { name: /Confirmar sugestões/ }));
    await waitFor(() => expect(mockPost).toHaveBeenCalledWith(
      '/repasses/competencias/2026-10/lancar-sugestoes', {},
    ));
  });

  it('desconto e nota vão para a API', async () => {
    renderTela();
    await screen.findByTestId('valor-nf');
    fireEvent.change(screen.getByLabelText('Descrição do desconto'), { target: { value: 'Pagamento indevido' } });
    fireEvent.change(screen.getByLabelText('Valor do desconto'), { target: { value: '19,70' } });
    fireEvent.click(screen.getByRole('button', { name: 'Desconto' }));
    await waitFor(() => expect(mockPost).toHaveBeenCalledWith(
      '/repasses/competencias/2026-10/descontos', { descricao: 'Pagamento indevido', valor: 19.7 },
    ));

    fireEvent.change(screen.getByLabelText('Número da NF'), { target: { value: '1234' } });
    fireEvent.click(screen.getByRole('button', { name: 'Gravar nota' }));
    await waitFor(() => expect(mockPut).toHaveBeenCalledWith(
      '/repasses/competencias/2026-10',
      expect.objectContaining({ nf_numero: '1234' }),
    ));
  });

  it('navega para o mês anterior', async () => {
    renderTela();
    fireEvent.click(await screen.findByLabelText('Mês anterior'));
    await waitFor(() => expect(mockGet).toHaveBeenCalledWith(
      '/repasses/painel', { params: { competencia: '2026-09' } },
    ));
  });

  it('erro da API aparece', async () => {
    mockGet.mockImplementation(() => Promise.reject({ response: { data: { detail: 'falhou' } } }));
    renderTela();
    expect(await screen.findByText('falhou')).toBeInTheDocument();
  });
});

describe('Contratos — aba Contratos', () => {
  it('lista e gera contratos da oportunidade', async () => {
    renderTela();
    await screen.findByTestId('competencia');
    fireEvent.click(screen.getByTestId('tab-contratos'));
    expect(await screen.findByTestId('contrato-c1')).toHaveTextContent('SERVCON UNIQUE');
    expect(screen.getByTestId('contrato-c2')).toHaveTextContent('180,00');

    fireEvent.click(screen.getByRole('button', { name: 'Da oportunidade' }));
    fireEvent.click(await screen.findByRole('button', { name: /Gerar 1 contrato/ }));
    await waitFor(() => expect(mockPost).toHaveBeenCalledWith(
      '/repasses/contratos/da-oportunidade', { oportunidade_id: 'o1' },
    ));
  });

  it('novo contrato vai para a API com os percentuais padrão', async () => {
    renderTela();
    await screen.findByTestId('competencia');
    fireEvent.click(screen.getByTestId('tab-contratos'));
    fireEvent.click(await screen.findByRole('button', { name: 'Novo contrato' }));
    fireEvent.change(screen.getByLabelText('Razão social'), { target: { value: 'VALLEY SISTEMAS' } });
    fireEvent.change(screen.getByLabelText('Data da venda'), { target: { value: '2026-06-20' } });
    fireEvent.change(screen.getByLabelText('Cobrança'), { target: { value: 'valor_fixo' } });
    fireEvent.change(screen.getByLabelText('Valor fixo do contrato'), { target: { value: '130' } });
    fireEvent.click(screen.getByTestId('gravar-contrato'));
    await waitFor(() => expect(mockPost).toHaveBeenCalled());
    const [url, corpo] = mockPost.mock.calls[0];
    expect(url).toBe('/repasses/contratos');
    expect(corpo).toMatchObject({
      razao_social: 'VALLEY SISTEMAS', cnpj: null, modalidade: 'valor_fixo', valor_fixo: 130,
      percentual_repasse: 30, percentual_primeiro_mes: 100, imposto_percentual: 14.33,
    });
  });
});
