// web/src/tests/AbaProposta.test.jsx
//
// A proposta comercial dentro da oportunidade.
//
// O que os testes seguram:
//   1. cliente e executivo vêm do cadastro — não há campo para digitá-los
//   2. mensalidade e investimento são DERIVADOS, e aparecem antes de gerar
//   3. vários CNPJs (042): cada um com vidas e valor; tabela sugere, o
//      vendedor negocia e a tela mostra o desconto; adicionar CNPJ vincula
//      à oportunidade na hora
//   4. gerar cria uma versão nova e mantém as anteriores baixáveis —
//      consolidada ou por CNPJ
//   5. o botão de PDF só existe onde o servidor consegue produzir PDF
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, fireEvent, cleanup, waitFor, within } from '@testing-library/react';

const mockGet = vi.fn();
const mockPost = vi.fn();
const mockPut = vi.fn();
const mockDelete = vi.fn();

vi.mock('../api', () => ({
  default: {
    get: (...a) => mockGet(...a),
    post: (...a) => mockPost(...a),
    put: (...a) => mockPut(...a),
    delete: (...a) => mockDelete(...a),
  },
}));

import AbaProposta, { hojeLocalISO, somarDiasISO } from '../components/crm/AbaProposta';
import {
  valorTabela, descontoPercentual, mensalidadeDaLinha, numero,
} from '../components/crm/propostaCalculo';

const OPP = { id: 'o1', numero: 'OPP-2026-00001' };

const FAIXAS = [
  { vidas_ate: 5, tipo: 'fixo', valor: '180.00' },
  { vidas_ate: 10, tipo: 'fixo', valor: '220.00' },
  { vidas_ate: 15, tipo: 'fixo', valor: '260.00' },
  { vidas_ate: 20, tipo: 'fixo', valor: '300.00' },
  { vidas_ate: null, tipo: 'por_vida', valor: '15.00' },
];

const TABELA = {
  faixas: FAIXAS,
  linhas: [
    'CNPJs até 05 funcionários registrados – R$ 180,00 mensais',
    'CNPJs acima de 20 funcionários registrados – R$ 15,00 por funcionário/mês',
  ],
  excedente_padrao: '15.00',
  padrao: true,
  atualizado_em: null,
  atualizado_por_nome: null,
  pode_editar: false,
};

const MATRIZ = {
  conta_id: 'c1', cnpj: '11222333000181', cnpj_formatado: '11.222.333/0001-81',
  razao_social: 'Metalurgica Alfa LTDA', nome_fantasia: null, principal: true,
  num_funcionarios: null, num_funcionarios_origem: null,
  vinculado_em: null, vinculado_por_nome: null,
};
const FILIAL = {
  conta_id: 'c2', cnpj: '11222333000262', cnpj_formatado: '11.222.333/0002-62',
  razao_social: 'Alfa Filial LTDA', nome_fantasia: null, principal: false,
  num_funcionarios: 23, num_funcionarios_origem: 'declarado',
  vinculado_em: '2026-10-05T12:00:00Z', vinculado_por_nome: 'Bruno',
};

const PADRAO = {
  escopo_padrao: ['PGR - (NR-01)', 'PCMSO - (NR-07)'],
  cidade: 'Guarulhos',
  dias_validade: 10,
  modalidade: 'tabela',
  vidas: null,
  valor_por_vida: null,
  valor_vida_excedente: '15.00',
  ultimos_itens: [],
  cnpjs: [MATRIZ],
  tabela: TABELA,
  executivo_id: 'u1',
  executivo_nome: 'Bruno Gonçalo',
  executivo_email: 'bruno@controllermedseg.com',
  executivo_telefone: '+55 (11) 9 9571-3682',
  cliente_razao_social: 'Metalurgica Alfa LTDA',
  geracao_disponivel: true,
  pdf_disponivel: true,
};

const V1 = {
  id: 'p1', oportunidade_id: 'o1', versao: 1, modalidade: 'tabela',
  vidas: 27, valor_por_vida: null, treinamentos: '0.00', laudos: '0.00',
  mensalidade: '479.00', investimento: '479.00',
  itens: [
    { id: 'i1', ordem: 1, conta_id: 'c1', cnpj: '11222333000181',
      cnpj_formatado: '11.222.333/0001-81', razao_social: 'Metalurgica Alfa LTDA',
      vidas: 4, mensalidade: '180.00', valor_tabela: '180.00', desconto_percentual: null },
    { id: 'i2', ordem: 2, conta_id: 'c2', cnpj: '11222333000262',
      cnpj_formatado: '11.222.333/0002-62', razao_social: 'Alfa Filial LTDA',
      vidas: 23, mensalidade: '299.00', valor_tabela: '345.00', desconto_percentual: '13.3' },
  ],
  tabela_preco: FAIXAS,
  escopo: ['PGR - (NR-01)'], cidade: 'Guarulhos',
  data_proposta: '2026-09-04', validade: '2026-09-25',
  cliente_razao_social: 'Metalurgica Alfa LTDA',
  executivo_id: 'u1', executivo_nome: 'Bruno Gonçalo',
  executivo_email: 'bruno@controllermedseg.com',
  executivo_telefone: '+55 (11) 9 9571-3682',
  criado_por_nome: 'Bruno Gonçalo', criado_em: '2026-09-04T12:00:00Z',
  valor_vida_excedente: '15.00',
  aprovada_em: '2026-09-04T12:05:00Z', aprovada_por_nome: 'Bruno Gonçalo',
};

function respostas(padrao = PADRAO, versoes = []) {
  return (url) => {
    if (url.endsWith('/proposta-padrao')) return Promise.resolve({ data: padrao });
    if (url.endsWith('/propostas')) return Promise.resolve({ data: versoes });
    return Promise.resolve({ data: [] });
  };
}

function montar(props = {}) {
  return render(<AbaProposta oportunidade={OPP} {...props} />);
}

const vidasDe = (nome) => screen.findByLabelText(`Vidas de ${nome}`);

beforeEach(() => {
  mockGet.mockReset();
  mockPost.mockReset();
  mockPut.mockReset();
  mockDelete.mockReset();
  mockGet.mockImplementation(respostas());
  mockPost.mockResolvedValue({ data: { ...V1, versao: 1 } });
  // O download usa URL.createObjectURL, que o jsdom não implementa.
  global.URL.createObjectURL = vi.fn(() => 'blob:fake');
  global.URL.revokeObjectURL = vi.fn();
});

afterEach(cleanup);

// ── Contas puras ─────────────────────────────────────────────────────

describe('propostaCalculo', () => {
  it('valor da tabela por faixa, igual ao servidor', () => {
    expect(valorTabela(4, FAIXAS)).toBe(180);
    expect(valorTabela(5, FAIXAS)).toBe(180);
    expect(valorTabela(6, FAIXAS)).toBe(220);
    expect(valorTabela(20, FAIXAS)).toBe(300);
    expect(valorTabela(21, FAIXAS)).toBe(315);
    expect(valorTabela(23, FAIXAS)).toBe(345);
    expect(valorTabela(0, FAIXAS)).toBeNull();
  });

  it('desconto só quando abaixo da tabela', () => {
    expect(descontoPercentual(299, 345)).toBe(13.3);
    expect(descontoPercentual(345, 345)).toBeNull();
    expect(descontoPercentual(400, 345)).toBeNull();
  });

  it('linha por vida ignora o valor negociado', () => {
    expect(mensalidadeDaLinha({
      modalidade: 'por_vida', vidas: 10, valorNegociado: '1', valorPorVida: '20', faixas: FAIXAS,
    })).toBe(200);
  });

  it('linha da tabela usa o negociado, ou a tabela em branco', () => {
    const base = { modalidade: 'tabela', vidas: 23, valorPorVida: '', faixas: FAIXAS };
    expect(mensalidadeDaLinha({ ...base, valorNegociado: '299' })).toBe(299);
    expect(mensalidadeDaLinha({ ...base, valorNegociado: '' })).toBe(345);
  });

  it('numero aceita vírgula brasileira', () => {
    expect(numero('1.234,56')).toBe(1234.56);
    expect(numero('1234.56')).toBe(1234.56);
    expect(Number.isNaN(numero(''))).toBe(true);
  });
});

// ── Datas sem armadilha de fuso ──────────────────────────────────────

describe('AbaProposta — datas', () => {
  it('hojeLocalISO devolve o dia LOCAL, não o de Greenwich', () => {
    const fim = new Date(2026, 8, 2, 22, 30); // 2 de setembro, 22h30 local
    expect(hojeLocalISO(fim)).toBe('2026-09-02');
  });

  it('somarDiasISO atravessa o mês', () => {
    expect(somarDiasISO('2026-08-26', 10)).toBe('2026-09-05');
    expect(somarDiasISO('2026-12-28', 10)).toBe('2027-01-07');
  });
});

// ── O formulário ─────────────────────────────────────────────────────

describe('AbaProposta — formulário', () => {
  it('não pede cliente nem executivo: vêm do cadastro', async () => {
    montar();
    await vidasDe('Metalurgica Alfa LTDA');
    expect(screen.queryByLabelText(/^cliente/i)).not.toBeInTheDocument();
    expect(screen.queryByLabelText(/executivo/i)).not.toBeInTheDocument();
    expect(screen.queryByLabelText(/e-mail/i)).not.toBeInTheDocument();
  });

  it('abre na modalidade tabela, com o CNPJ principal', async () => {
    montar();
    await vidasDe('Metalurgica Alfa LTDA');
    expect(screen.getByRole('radio', { name: 'Tabela por faixa' }))
      .toHaveAttribute('aria-checked', 'true');
    expect(screen.getByText('Principal')).toBeInTheDocument();
    expect(screen.queryByLabelText('Valor por vida (R$)')).not.toBeInTheDocument();
  });

  it('abre com o escopo padrão do servidor', async () => {
    montar();
    const primeiro = await screen.findByLabelText('Item 1 do escopo');
    expect(primeiro.value).toBe('PGR - (NR-01)');
  });

  it('mudar a data da proposta empurra a validade junto', async () => {
    montar();
    const data = await screen.findByLabelText('Data da proposta');
    fireEvent.change(data, { target: { value: '2026-08-26' } });
    expect(screen.getByLabelText('Válida até').value).toBe('2026-09-05');
  });

  it('itens do escopo podem ser adicionados e removidos', async () => {
    montar();
    await screen.findByLabelText('Item 1 do escopo');
    fireEvent.click(screen.getByText('Item'));
    expect(screen.getByLabelText('Item 3 do escopo')).toBeInTheDocument();
    fireEvent.click(screen.getByLabelText('Remover item 1'));
    expect(screen.getByLabelText('Item 1 do escopo').value).toBe('PCMSO - (NR-07)');
  });

  it('não gera sem vidas', async () => {
    montar();
    await vidasDe('Metalurgica Alfa LTDA');
    expect(screen.getByText('Gerar proposta').closest('button')).toBeDisabled();
  });
});

// ── Vários CNPJs e tabela ────────────────────────────────────────────

describe('AbaProposta — vários CNPJs', () => {
  const COM_FILIAL = { ...PADRAO, cnpjs: [MATRIZ, FILIAL] };

  it('tabela sugere o valor e a soma aparece antes de gerar', async () => {
    mockGet.mockImplementation(respostas(COM_FILIAL));
    montar();
    fireEvent.change(await vidasDe('Metalurgica Alfa LTDA'), { target: { value: '4' } });
    // A filial já veio com as vidas DECLARADAS no cadastro (23).
    expect(screen.getByLabelText('Vidas de Alfa Filial LTDA').value).toBe('23');
    expect(screen.getByTestId('mensal-c1').textContent).toContain('180,00');
    expect(screen.getByTestId('mensal-c2').textContent).toContain('345,00');
    expect(screen.getByTestId('calc-mensalidade').textContent).toContain('525,00');
  });

  it('valor negociado abaixo da tabela mostra o desconto', async () => {
    mockGet.mockImplementation(respostas(COM_FILIAL));
    montar();
    fireEvent.change(await screen.findByLabelText('Mensalidade de Alfa Filial LTDA'),
      { target: { value: '299' } });
    const linha = screen.getByTestId('linha-c2');
    expect(within(linha).getByText('−13,3%')).toBeInTheDocument();
  });

  it('desmarcar um CNPJ tira da soma', async () => {
    mockGet.mockImplementation(respostas(COM_FILIAL));
    montar();
    fireEvent.change(await vidasDe('Metalurgica Alfa LTDA'), { target: { value: '4' } });
    fireEvent.click(screen.getByLabelText('Incluir Alfa Filial LTDA na proposta'));
    expect(screen.getByTestId('calc-mensalidade').textContent).toContain('180,00');
  });

  it('valor por vida: campo único e linhas derivadas', async () => {
    mockGet.mockImplementation(respostas(COM_FILIAL));
    montar();
    await vidasDe('Metalurgica Alfa LTDA');
    fireEvent.click(screen.getByRole('radio', { name: 'Valor por vida' }));
    fireEvent.change(screen.getByLabelText('Vidas de Metalurgica Alfa LTDA'),
      { target: { value: '10' } });
    fireEvent.change(screen.getByLabelText('Valor por vida (R$)'), { target: { value: '20' } });
    expect(screen.queryByLabelText('Mensalidade de Alfa Filial LTDA')).not.toBeInTheDocument();
    expect(screen.getByTestId('calc-mensalidade').textContent).toContain('660,00'); // 33 x 20
  });

  it('a última proposta volta com os CNPJs e o valor negociado', async () => {
    mockGet.mockImplementation(respostas({
      ...COM_FILIAL, ultimos_itens: V1.itens,
    }));
    montar();
    expect((await vidasDe('Metalurgica Alfa LTDA')).value).toBe('4');
    expect(screen.getByLabelText('Mensalidade de Alfa Filial LTDA').value).toBe('299.00');
  });

  it('adicionar CNPJ vincula à oportunidade na hora', async () => {
    mockGet.mockImplementation((url, cfg) => {
      if (url === '/crm/contas/busca') {
        return Promise.resolve({ data: [{
          id: 'c2', razao_social: 'Alfa Filial LTDA', cnpj_formatado: '11.222.333/0002-62',
          ativo: true, nao_prospectar: false,
        }] });
      }
      return respostas()(url, cfg);
    });
    mockPost.mockImplementation((url) => {
      if (url === '/crm/oportunidades/o1/cnpjs') {
        return Promise.resolve({ data: [MATRIZ, FILIAL] });
      }
      return Promise.resolve({ data: V1 });
    });
    const onCnpjsMudaram = vi.fn();
    montar({ onCnpjsMudaram });
    await vidasDe('Metalurgica Alfa LTDA');

    fireEvent.click(screen.getByText('Buscar por razão social ou CNPJ…'));
    fireEvent.change(screen.getByPlaceholderText(/buscar/i), { target: { value: 'Alfa' } });
    fireEvent.click(await screen.findByText('Alfa Filial LTDA'));

    await waitFor(() => expect(mockPost).toHaveBeenCalledWith(
      '/crm/oportunidades/o1/cnpjs', { conta_id: 'c2' },
    ));
    expect(await vidasDe('Alfa Filial LTDA')).toBeInTheDocument();
    expect(onCnpjsMudaram).toHaveBeenCalled();
  });

  it('CNPJ em outra negociação: o motivo do servidor aparece', async () => {
    mockGet.mockImplementation((url, cfg) => {
      if (url === '/crm/contas/busca') {
        return Promise.resolve({ data: [{
          id: 'c9', razao_social: 'Outra LTDA', cnpj_formatado: '1', ativo: true,
          nao_prospectar: false,
        }] });
      }
      return respostas()(url, cfg);
    });
    mockPost.mockRejectedValue({ response: { data: { detail: {
      erro: 'conta_vinculada_a_oportunidade',
      mensagem: 'Outra LTDA já está na oportunidade OPP-9 (Grupo X) como CNPJ adicional.',
    } } } });
    montar();
    await vidasDe('Metalurgica Alfa LTDA');
    fireEvent.click(screen.getByText('Buscar por razão social ou CNPJ…'));
    fireEvent.change(screen.getByPlaceholderText(/buscar/i), { target: { value: 'Outra' } });
    fireEvent.click(await screen.findByText('Outra LTDA'));
    expect(await screen.findByText(/já está na oportunidade OPP-9/)).toBeInTheDocument();
  });

  it('tirar um CNPJ desvincula', async () => {
    mockGet.mockImplementation(respostas(COM_FILIAL));
    mockDelete.mockResolvedValue({ data: [MATRIZ] });
    montar();
    fireEvent.click(await screen.findByLabelText('Tirar Alfa Filial LTDA da oportunidade'));
    await waitFor(() => expect(mockDelete).toHaveBeenCalledWith(
      '/crm/oportunidades/o1/cnpjs/c2',
    ));
    await waitFor(() =>
      expect(screen.queryByLabelText('Vidas de Alfa Filial LTDA')).not.toBeInTheDocument());
  });

  it('o principal não tem botão de tirar', async () => {
    montar();
    await vidasDe('Metalurgica Alfa LTDA');
    expect(screen.queryByLabelText('Tirar Metalurgica Alfa LTDA da oportunidade'))
      .not.toBeInTheDocument();
  });
});

// ── Gerar ────────────────────────────────────────────────────────────

describe('AbaProposta — gerar', () => {
  async function preencher(props = {}) {
    mockGet.mockImplementation(respostas({ ...PADRAO, cnpjs: [MATRIZ, FILIAL] }));
    montar({ onGerada: vi.fn(), ...props });
    fireEvent.change(await vidasDe('Metalurgica Alfa LTDA'), { target: { value: '4' } });
    fireEvent.change(screen.getByLabelText('Mensalidade de Alfa Filial LTDA'),
      { target: { value: '299' } });
  }

  it('envia modalidade, CNPJs, escopo e datas — nunca os totais', async () => {
    await preencher();
    fireEvent.click(screen.getByText('Gerar proposta'));

    await waitFor(() => expect(mockPost).toHaveBeenCalled());
    const [url, corpo] = mockPost.mock.calls[0];
    expect(url).toBe('/crm/oportunidades/o1/propostas');
    expect(corpo.modalidade).toBe('tabela');
    expect(corpo.itens).toEqual([
      { conta_id: 'c1', vidas: 4 },                       // em branco = tabela
      { conta_id: 'c2', vidas: 23, mensalidade: 299 },
    ]);
    expect(corpo).not.toHaveProperty('valor_por_vida');
    expect(corpo.escopo).toEqual(['PGR - (NR-01)', 'PCMSO - (NR-07)']);
    expect(corpo).not.toHaveProperty('mensalidade');
    expect(corpo).not.toHaveProperty('investimento');
  });

  it('por vida manda o valor por vida', async () => {
    await preencher();
    fireEvent.click(screen.getByRole('radio', { name: 'Valor por vida' }));
    fireEvent.change(screen.getByLabelText('Valor por vida (R$)'), { target: { value: '20' } });
    fireEvent.click(screen.getByText('Gerar proposta'));
    await waitFor(() => expect(mockPost).toHaveBeenCalled());
    const [, corpo] = mockPost.mock.calls[0];
    expect(corpo.modalidade).toBe('por_vida');
    expect(corpo.valor_por_vida).toBe(20);
    expect(corpo.itens[1]).toEqual({ conta_id: 'c2', vidas: 23 });
  });

  it('a versão nova entra no topo da lista e avisa o pai', async () => {
    const onGerada = vi.fn();
    await preencher({ onGerada });
    fireEvent.click(screen.getByText('Gerar proposta'));
    await waitFor(() =>
      expect(within(screen.getByLabelText('Versões da proposta'))
        .getByText('v1')).toBeInTheDocument()
    );
    expect(onGerada.mock.calls[0][0].mensalidade).toBe('479.00');
  });

  it('erro do servidor aparece na tela', async () => {
    mockPost.mockRejectedValue({
      response: { data: { detail: 'Escopo e CNPJs somam 40 linhas e não cabem no slide.' } },
    });
    await preencher();
    fireEvent.click(screen.getByText('Gerar proposta'));
    expect(await screen.findByText(/não cabem no slide/)).toBeInTheDocument();
  });
});

// ── Versões ──────────────────────────────────────────────────────────

describe('AbaProposta — versões', () => {
  it('lista as geradas com valor, vidas, CNPJs e validade', async () => {
    mockGet.mockImplementation(respostas(PADRAO, [V1]));
    montar();
    const lista = within(await screen.findByLabelText('Versões da proposta'));
    expect(lista.getByText('v1')).toBeInTheDocument();
    expect(lista.getByText(/479,00/)).toBeInTheDocument();
    expect(lista.getByText(/27 vidas/)).toBeInTheDocument();
    expect(lista.getByText(/2 CNPJs/)).toBeInTheDocument();
    expect(lista.getByText(/25\/09\/2026/)).toBeInTheDocument();
  });

  it('sem versões, explica o que vai aparecer ali', async () => {
    montar();
    expect(await screen.findByText('Nenhuma proposta gerada')).toBeInTheDocument();
  });

  it('esconde o PDF onde o servidor não tem LibreOffice', async () => {
    mockGet.mockImplementation(respostas({ ...PADRAO, pdf_disponivel: false }, [V1]));
    montar();
    const lista = within(await screen.findByLabelText('Versões da proposta'));
    expect(lista.getByText('PPTX')).toBeInTheDocument();
    expect(lista.queryByText('PDF')).not.toBeInTheDocument();
    expect(screen.getByText(/exporte pelo PowerPoint/)).toBeInTheDocument();
  });

  // 050: a versão vai por e-mail, da caixa do vendedor, em PDF.
  it('E-mail na versão chama o pai com a proposta (e o CNPJ, se for um só)', async () => {
    mockGet.mockImplementation(respostas(PADRAO, [V1]));
    const onEnviar = vi.fn();
    montar({ onEnviarPorEmail: onEnviar });
    await screen.findByLabelText('Versões da proposta');
    fireEvent.click(screen.getAllByRole('button', { name: 'Enviar por e-mail' })[0]);
    expect(onEnviar).toHaveBeenCalledWith(expect.objectContaining({ id: 'p1' }));
    fireEvent.click(screen.getByText('Proposta por CNPJ'));
    const porCnpj = within(screen.getByLabelText('CNPJs da versão 1'));
    fireEvent.click(porCnpj.getAllByRole('button', { name: 'Enviar por e-mail' })[1]);
    expect(onEnviar).toHaveBeenLastCalledWith(
      expect.objectContaining({ id: 'p1' }), expect.objectContaining({ id: 'i2' }),
    );
  });

  it('sem PDF no servidor, não oferece o e-mail', async () => {
    mockGet.mockImplementation(respostas({ ...PADRAO, pdf_disponivel: false }, [V1]));
    montar({ onEnviarPorEmail: vi.fn() });
    await screen.findByLabelText('Versões da proposta');
    expect(screen.queryByRole('button', { name: 'Enviar por e-mail' })).not.toBeInTheDocument();
  });

  it('sem o handler do pai, não há botão de e-mail', async () => {
    mockGet.mockImplementation(respostas(PADRAO, [V1]));
    montar();
    await screen.findByLabelText('Versões da proposta');
    expect(screen.queryByRole('button', { name: 'Enviar por e-mail' })).not.toBeInTheDocument();
  });

  function comDownload() {
    mockGet.mockImplementation((url, cfg) => {
      if (url === '/crm/propostas/p1/arquivo') {
        return Promise.resolve({
          data: new Blob(['x']),
          headers: { 'content-disposition': 'attachment; filename="OPP-2026-00001_v1.pptx"' },
        });
      }
      return respostas(PADRAO, [V1])(url, cfg);
    });
  }

  it('baixar a consolidada pede o arquivo como blob, sem item', async () => {
    comDownload();
    montar();
    const lista = within(await screen.findByLabelText('Versões da proposta'));
    fireEvent.click(lista.getAllByText('PPTX')[0]);
    await waitFor(() => {
      const chamada = mockGet.mock.calls.find(([u]) => u === '/crm/propostas/p1/arquivo');
      expect(chamada[1].responseType).toBe('blob');
      expect(chamada[1].params).toEqual({ formato: 'pptx' });
    });
  });

  it('baixar a proposta de UM CNPJ manda o item', async () => {
    comDownload();
    montar();
    await screen.findByLabelText('Versões da proposta');
    fireEvent.click(screen.getByText('Proposta por CNPJ'));
    const porCnpj = within(screen.getByLabelText('CNPJs da versão 1'));
    expect(porCnpj.getByText(/−13,3%/)).toBeInTheDocument();
    fireEvent.click(porCnpj.getAllByText('PDF')[1]);
    await waitFor(() => {
      const chamada = mockGet.mock.calls.find(([u]) => u === '/crm/propostas/p1/arquivo');
      expect(chamada[1].params).toEqual({ formato: 'pdf', item: 'i2' });
    });
  });
});

// ── Tabela de preços ─────────────────────────────────────────────────

describe('AbaProposta — tabela de preços', () => {
  it('mostra a tabela; operacional não vê o Editar', async () => {
    montar();
    const tabela = within(await screen.findByLabelText('Tabela de preços'));
    expect(tabela.getByText(/até 05 funcionários/)).toBeInTheDocument();
    expect(tabela.queryByText('Editar')).not.toBeInTheDocument();
  });

  it('gestão edita e salva a tabela inteira', async () => {
    mockGet.mockImplementation(respostas({ ...PADRAO, tabela: { ...TABELA, pode_editar: true } }));
    mockPut.mockResolvedValue({ data: { ...TABELA, pode_editar: true, padrao: false,
      linhas: ['CNPJs até 05 funcionários registrados – R$ 190,00 mensais'] } });
    montar();
    const tabela = within(await screen.findByLabelText('Tabela de preços'));
    fireEvent.click(tabela.getByText('Editar'));
    fireEvent.change(screen.getByLabelText('Valor da faixa 1'), { target: { value: '190' } });
    fireEvent.click(screen.getByText('Salvar tabela'));
    await waitFor(() => expect(mockPut).toHaveBeenCalled());
    const [url, corpo] = mockPut.mock.calls[0];
    expect(url).toBe('/crm/tabela-precos');
    expect(corpo.faixas[0]).toEqual({ vidas_ate: 5, tipo: 'fixo', valor: 190 });
    expect(corpo.faixas[4]).toEqual({ vidas_ate: null, tipo: 'por_vida', valor: 15 });
    expect(await screen.findByText(/R\$ 190,00 mensais/)).toBeInTheDocument();
  });

  it('some na modalidade por vida', async () => {
    montar();
    await screen.findByLabelText('Tabela de preços');
    fireEvent.click(screen.getByRole('radio', { name: 'Valor por vida' }));
    expect(screen.queryByLabelText('Tabela de preços')).not.toBeInTheDocument();
  });
});

// ── Capacidade do servidor ───────────────────────────────────────────

describe('AbaProposta — servidor sem python-pptx', () => {
  it('avisa e trava o botão em vez de gravar versão que não baixa', async () => {
    mockGet.mockImplementation(respostas({ ...PADRAO, geracao_disponivel: false }));
    montar();
    fireEvent.change(await vidasDe('Metalurgica Alfa LTDA'), { target: { value: '4' } });
    expect(screen.getByText(/sem a biblioteca/)).toBeInTheDocument();
    expect(screen.getByText('Gerar proposta').closest('button')).toBeDisabled();
  });
});

// ── Telefone ─────────────────────────────────────────────────────────

describe('AbaProposta — telefone do executivo', () => {
  it('avisa quando o cadastro está sem telefone', async () => {
    mockGet.mockImplementation(respostas({ ...PADRAO, executivo_telefone: null }));
    montar();
    expect(await screen.findByText(/telefone não está no cadastro/)).toBeInTheDocument();
  });

  it('não avisa quando o telefone existe', async () => {
    montar();
    await vidasDe('Metalurgica Alfa LTDA');
    expect(screen.queryByText(/telefone não está no cadastro/)).not.toBeInTheDocument();
  });
});

// ── 051: excedente, visualizador e aprovação ─────────────────────────

const PENDENTE = { ...V1, id: 'p2', versao: 2, aprovada_em: null, aprovada_por_nome: null };

function comPdf(versoes = [PENDENTE], padrao = PADRAO) {
  mockGet.mockImplementation((url, cfg) => {
    if (url.startsWith('/crm/propostas/') && url.endsWith('/arquivo')) {
      return Promise.resolve({ data: new Blob(['%PDF'], { type: 'application/pdf' }), headers: {} });
    }
    return respostas(padrao, versoes)(url, cfg);
  });
}

describe('AbaProposta — valor por vida excedente (051)', () => {
  it('vem preenchido e vai no corpo da modalidade tabela', async () => {
    mockGet.mockImplementation(respostas());
    montar();
    fireEvent.change(await vidasDe('Metalurgica Alfa LTDA'), { target: { value: '4' } });
    const campo = screen.getByLabelText('Valor por vida excedente (R$)');
    expect(campo.value).toBe('15.00');
    fireEvent.change(campo, { target: { value: '12.5' } });
    fireEvent.click(screen.getByText('Gerar proposta'));
    await waitFor(() => expect(mockPost).toHaveBeenCalled());
    expect(mockPost.mock.calls[0][1].valor_vida_excedente).toBe(12.5);
  });

  it('sem excedente não gera na modalidade tabela', async () => {
    montar();
    fireEvent.change(await vidasDe('Metalurgica Alfa LTDA'), { target: { value: '4' } });
    fireEvent.change(screen.getByLabelText('Valor por vida excedente (R$)'), { target: { value: '' } });
    expect(screen.getByText('Gerar proposta').closest('button')).toBeDisabled();
  });

  it('na modalidade por vida o campo some', async () => {
    montar();
    await vidasDe('Metalurgica Alfa LTDA');
    fireEvent.click(screen.getByRole('radio', { name: 'Valor por vida' }));
    expect(screen.queryByLabelText('Valor por vida excedente (R$)')).not.toBeInTheDocument();
  });
});

describe('AbaProposta — ver e aprovar (051)', () => {
  it('gerar abre o visualizador com o PDF, em vez de baixar', async () => {
    comPdf([]);
    mockPost.mockResolvedValue({ data: PENDENTE });
    montar();
    fireEvent.change(await vidasDe('Metalurgica Alfa LTDA'), { target: { value: '4' } });
    fireEvent.click(screen.getByText('Gerar proposta'));
    expect(await screen.findByTitle('Visualização da proposta')).toBeInTheDocument();
    const pdf = mockGet.mock.calls.find(([u]) => u === '/crm/propostas/p2/arquivo');
    expect(pdf[1].params).toEqual({ formato: 'pdf' });
    expect(mockGet.mock.calls.some(([, c]) => c?.params?.formato === 'pptx')).toBe(false);
    expect(screen.getByRole('button', { name: /Aprovar para envio/ })).toBeInTheDocument();
  });

  it('versão pendente: badge, "Ver e aprovar" e nada de e-mail', async () => {
    comPdf();
    montar({ onEnviarPorEmail: vi.fn() });
    const lista = within(await screen.findByLabelText('Versões da proposta'));
    expect(lista.getByText('Aguardando aprovação')).toBeInTheDocument();
    expect(lista.getByRole('button', { name: 'Ver e aprovar' })).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Enviar por e-mail' })).not.toBeInTheDocument();
  });

  it('aprovar no visualizador libera o e-mail da versão', async () => {
    comPdf();
    mockPost.mockImplementation((url) => {
      if (url === '/crm/propostas/p2/aprovar') {
        return Promise.resolve({ data: {
          ...PENDENTE, aprovada_em: '2026-10-07T15:00:00Z', aprovada_por_nome: 'Bruno Gonçalo',
        } });
      }
      return Promise.reject(new Error(`POST inesperado: ${url}`));
    });
    montar({ onEnviarPorEmail: vi.fn() });
    fireEvent.click(await screen.findByRole('button', { name: 'Ver e aprovar' }));
    fireEvent.click(await screen.findByRole('button', { name: /Aprovar para envio/ }));
    await waitFor(() => expect(mockPost).toHaveBeenCalledWith('/crm/propostas/p2/aprovar', {}));
    expect(await screen.findAllByText(/Aprovada por Bruno Gonçalo/)).not.toHaveLength(0);
    expect(screen.getAllByRole('button', { name: 'Enviar por e-mail' }).length).toBeGreaterThan(0);
  });

  it('com vários CNPJs, troca entre a consolidada e a de um CNPJ', async () => {
    comPdf([V1]);
    montar();
    fireEvent.click(await screen.findByRole('button', { name: 'Ver' }));
    await screen.findByTitle('Visualização da proposta');
    fireEvent.change(screen.getByLabelText('Qual arquivo ver'), { target: { value: 'i2' } });
    await waitFor(() => {
      const ultima = mockGet.mock.calls.filter(([u]) => u === '/crm/propostas/p1/arquivo').at(-1);
      expect(ultima[1].params).toEqual({ formato: 'pdf', item: 'i2' });
    });
  });

  it('servidor sem PDF: avisa e oferece o PPTX', async () => {
    comPdf([PENDENTE], { ...PADRAO, pdf_disponivel: false });
    montar();
    fireEvent.click(await screen.findByRole('button', { name: 'Ver e aprovar' }));
    expect(await screen.findByText(/não gera PDF/)).toBeInTheDocument();
    expect(screen.queryByTitle('Visualização da proposta')).not.toBeInTheDocument();
  });
});
