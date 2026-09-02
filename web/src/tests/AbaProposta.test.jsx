// web/src/tests/AbaProposta.test.jsx
//
// A proposta comercial dentro da oportunidade.
//
// O que os testes seguram:
//   1. cliente e executivo vêm do cadastro — não há campo para digitá-los
//   2. mensalidade e investimento são DERIVADOS, e aparecem antes de gerar
//   3. gerar cria uma versão nova e mantém as anteriores baixáveis
//   4. o botão de PDF só existe onde o servidor consegue produzir PDF
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, fireEvent, cleanup, waitFor, within } from '@testing-library/react';

const mockGet = vi.fn();
const mockPost = vi.fn();

vi.mock('../api', () => ({
  default: {
    get: (...a) => mockGet(...a),
    post: (...a) => mockPost(...a),
  },
}));

import AbaProposta, { hojeLocalISO, somarDiasISO } from '../components/crm/AbaProposta';

const OPP = { id: 'o1', numero: 'OPP-2026-00001' };

const PADRAO = {
  escopo_padrao: ['PGR - (NR-01)', 'PCMSO - (NR-07)'],
  cidade: 'Guarulhos',
  dias_validade: 10,
  vidas: null,
  valor_por_vida: null,
  executivo_id: 'u1',
  executivo_nome: 'Bruno Gonçalo',
  executivo_email: 'bruno@controllermedseg.com',
  executivo_telefone: '+55 (11) 9 9571-3682',
  cliente_razao_social: 'Metalurgica Alfa LTDA',
  geracao_disponivel: true,
  pdf_disponivel: true,
};

const V1 = {
  id: 'p1', oportunidade_id: 'o1', versao: 1,
  vidas: 50, valor_por_vida: '20.00', treinamentos: '2000.00', laudos: '1000.00',
  mensalidade: '1000.00', investimento: '4000.00',
  escopo: ['PGR - (NR-01)'], cidade: 'Guarulhos',
  data_proposta: '2026-08-26', validade: '2026-09-05',
  cliente_razao_social: 'Metalurgica Alfa LTDA',
  executivo_id: 'u1', executivo_nome: 'Bruno Gonçalo',
  executivo_email: 'bruno@controllermedseg.com',
  executivo_telefone: '+55 (11) 9 9571-3682',
  criado_por_nome: 'Bruno Gonçalo', criado_em: '2026-08-26T12:00:00Z',
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

beforeEach(() => {
  mockGet.mockReset();
  mockPost.mockReset();
  mockGet.mockImplementation(respostas());
  mockPost.mockResolvedValue({ data: { ...V1, versao: 1 } });
  // O download usa URL.createObjectURL, que o jsdom não implementa.
  global.URL.createObjectURL = vi.fn(() => 'blob:fake');
  global.URL.revokeObjectURL = vi.fn();
});

afterEach(cleanup);

// ── Datas sem armadilha de fuso ──────────────────────────────────────

describe('AbaProposta — datas', () => {
  it('hojeLocalISO devolve o dia LOCAL, não o de Greenwich', () => {
    /*
      `toISOString()` converte para UTC: das 21h à meia-noite em Brasília
      ele devolve o dia SEGUINTE, e a proposta sairia datada de amanhã para
      quem gera no fim do expediente. Mesma armadilha que já derrubou 9
      testes do backend.
    */
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
    await screen.findByLabelText('Qtde. de vidas');
    expect(screen.queryByLabelText(/cliente/i)).not.toBeInTheDocument();
    expect(screen.queryByLabelText(/executivo/i)).not.toBeInTheDocument();
    expect(screen.queryByLabelText(/e-mail/i)).not.toBeInTheDocument();
  });

  it('abre com o escopo padrão do servidor', async () => {
    montar();
    const primeiro = await screen.findByLabelText('Item 1 do escopo');
    expect(primeiro.value).toBe('PGR - (NR-01)');
    expect(screen.getByLabelText('Item 2 do escopo').value).toBe('PCMSO - (NR-07)');
  });

  it('a validade nasce com o prazo padrão a partir de hoje', async () => {
    montar();
    const data = await screen.findByLabelText('Data da proposta');
    const validade = screen.getByLabelText('Válida até');
    expect(validade.value).toBe(somarDiasISO(data.value, 10));
  });

  it('mudar a data da proposta empurra a validade junto', async () => {
    /* Manter o vencimento antigo produziria proposta que nasce vencida. */
    montar();
    const data = await screen.findByLabelText('Data da proposta');
    fireEvent.change(data, { target: { value: '2026-08-26' } });
    expect(screen.getByLabelText('Válida até').value).toBe('2026-09-05');
  });

  it('a validade continua editável — é argumento de negociação', async () => {
    montar();
    await screen.findByLabelText('Válida até');
    fireEvent.change(screen.getByLabelText('Válida até'), {
      target: { value: '2026-10-30' },
    });
    expect(screen.getByLabelText('Válida até').value).toBe('2026-10-30');
  });

  it('calcula mensalidade e investimento antes de gerar', async () => {
    /*
      O vendedor precisa ver o total ANTES de mandar. Os campos abertos são
      as parcelas; os totais são texto, não input — input com valor
      calculado convida a digitar por cima.
    */
    montar();
    fireEvent.change(await screen.findByLabelText('Qtde. de vidas'), {
      target: { value: '50' },
    });
    fireEvent.change(screen.getByLabelText('Valor por vida (R$)'), {
      target: { value: '20' },
    });
    fireEvent.change(screen.getByLabelText('Treinamentos (R$)'), {
      target: { value: '2000' },
    });
    fireEvent.change(screen.getByLabelText('Laudos / outros (R$)'), {
      target: { value: '1000' },
    });

    expect(screen.getByTestId('calc-mensalidade').textContent).toContain('1.000,00');
    expect(screen.getByTestId('calc-investimento').textContent).toContain('4.000,00');
  });

  it('itens do escopo podem ser adicionados e removidos', async () => {
    montar();
    await screen.findByLabelText('Item 1 do escopo');
    fireEvent.click(screen.getByText('Item'));
    expect(screen.getByLabelText('Item 3 do escopo')).toBeInTheDocument();

    fireEvent.click(screen.getByLabelText('Remover item 1'));
    expect(screen.queryByLabelText('Item 3 do escopo')).not.toBeInTheDocument();
    expect(screen.getByLabelText('Item 1 do escopo').value).toBe('PCMSO - (NR-07)');
  });

  it('não gera sem vidas e valor', async () => {
    montar();
    await screen.findByLabelText('Qtde. de vidas');
    expect(screen.getByText('Gerar proposta').closest('button')).toBeDisabled();
  });
});

// ── Gerar ────────────────────────────────────────────────────────────

describe('AbaProposta — gerar', () => {
  async function preencher() {
    montar({ onGerada: vi.fn() });
    fireEvent.change(await screen.findByLabelText('Qtde. de vidas'), {
      target: { value: '50' },
    });
    fireEvent.change(screen.getByLabelText('Valor por vida (R$)'), {
      target: { value: '20' },
    });
  }

  it('envia as parcelas, o escopo e as datas', async () => {
    await preencher();
    fireEvent.click(screen.getByText('Gerar proposta'));

    await waitFor(() => expect(mockPost).toHaveBeenCalled());
    const [url, corpo] = mockPost.mock.calls[0];
    expect(url).toBe('/crm/oportunidades/o1/propostas');
    expect(corpo.vidas).toBe(50);
    expect(corpo.valor_por_vida).toBe(20);
    expect(corpo.escopo).toEqual(['PGR - (NR-01)', 'PCMSO - (NR-07)']);
    expect(corpo.cidade).toBe('Guarulhos');
    // Mensalidade e investimento NÃO vão no corpo: quem calcula é o
    // servidor. Mandá-los abriria espaço para a tela e o banco divergirem.
    expect(corpo).not.toHaveProperty('mensalidade');
    expect(corpo).not.toHaveProperty('investimento');
  });

  it('a versão nova entra no topo da lista', async () => {
    await preencher();
    fireEvent.click(screen.getByText('Gerar proposta'));
    await waitFor(() =>
      expect(within(screen.getByLabelText('Versões da proposta'))
        .getByText('v1')).toBeInTheDocument()
    );
  });

  it('avisa o pai para a mensalidade do funil acompanhar', async () => {
    const onGerada = vi.fn();
    montar({ onGerada });
    fireEvent.change(await screen.findByLabelText('Qtde. de vidas'), {
      target: { value: '50' },
    });
    fireEvent.change(screen.getByLabelText('Valor por vida (R$)'), {
      target: { value: '20' },
    });
    fireEvent.click(screen.getByText('Gerar proposta'));
    await waitFor(() => expect(onGerada).toHaveBeenCalled());
    expect(onGerada.mock.calls[0][0].mensalidade).toBe('1000.00');
  });

  it('erro do servidor aparece na tela', async () => {
    mockPost.mockRejectedValue({
      response: { data: { detail: 'A validade não pode ser anterior à data da proposta.' } },
    });
    await preencher();
    fireEvent.click(screen.getByText('Gerar proposta'));
    expect(await screen.findByText(/validade não pode ser anterior/)).toBeInTheDocument();
  });
});

// ── Versões ──────────────────────────────────────────────────────────

describe('AbaProposta — versões', () => {
  it('lista as geradas com valor, vidas e validade', async () => {
    mockGet.mockImplementation(respostas(PADRAO, [V1]));
    montar();
    const lista = within(await screen.findByLabelText('Versões da proposta'));
    expect(lista.getByText('v1')).toBeInTheDocument();
    expect(lista.getByText(/4\.000,00/)).toBeInTheDocument();
    expect(lista.getByText(/50 vidas/)).toBeInTheDocument();
    expect(lista.getByText(/05\/09\/2026/)).toBeInTheDocument();
  });

  it('sem versões, explica o que vai aparecer ali', async () => {
    montar();
    expect(await screen.findByText('Nenhuma proposta gerada')).toBeInTheDocument();
  });

  it('oferece PPTX e PDF quando o servidor converte', async () => {
    mockGet.mockImplementation(respostas(PADRAO, [V1]));
    montar();
    const lista = within(await screen.findByLabelText('Versões da proposta'));
    expect(lista.getByText('PPTX')).toBeInTheDocument();
    expect(lista.getByText('PDF')).toBeInTheDocument();
  });

  it('esconde o PDF onde o servidor não tem LibreOffice', async () => {
    /*
      Oferecer o download e falhar depois do clique é pior do que não
      oferecer: o vendedor descobre no meio do envio ao cliente.
    */
    mockGet.mockImplementation(
      respostas({ ...PADRAO, pdf_disponivel: false }, [V1])
    );
    montar();
    const lista = within(await screen.findByLabelText('Versões da proposta'));
    expect(lista.getByText('PPTX')).toBeInTheDocument();
    expect(lista.queryByText('PDF')).not.toBeInTheDocument();
    expect(screen.getByText(/exporte pelo PowerPoint/)).toBeInTheDocument();
  });

  it('baixar pede o arquivo como blob', async () => {
    mockGet.mockImplementation((url, cfg) => {
      if (url === '/crm/propostas/p1/arquivo') {
        return Promise.resolve({
          data: new Blob(['x']),
          headers: { 'content-disposition': 'attachment; filename="OPP-2026-00001_v1.pptx"' },
        });
      }
      return respostas(PADRAO, [V1])(url, cfg);
    });
    montar();
    const lista = within(await screen.findByLabelText('Versões da proposta'));
    fireEvent.click(lista.getByText('PPTX'));

    await waitFor(() => {
      const chamada = mockGet.mock.calls.find(([u]) => u === '/crm/propostas/p1/arquivo');
      expect(chamada[1].responseType).toBe('blob');
      expect(chamada[1].params.formato).toBe('pptx');
    });
  });
});

// ── Capacidade do servidor ───────────────────────────────────────────

describe('AbaProposta — servidor sem python-pptx', () => {
  it('avisa e trava o botão em vez de gravar versão que não baixa', async () => {
    /*
      Sem a biblioteca, gerar gravaria a versão no banco e falharia no
      download — versão fantasma que ninguém consegue baixar.
    */
    mockGet.mockImplementation(respostas({ ...PADRAO, geracao_disponivel: false }));
    montar();
    await screen.findByLabelText('Qtde. de vidas');
    fireEvent.change(screen.getByLabelText('Qtde. de vidas'), { target: { value: '50' } });
    fireEvent.change(screen.getByLabelText('Valor por vida (R$)'), { target: { value: '20' } });

    expect(screen.getByText(/sem a biblioteca/)).toBeInTheDocument();
    expect(screen.getByText('Gerar proposta').closest('button')).toBeDisabled();
  });
});

// ── Telefone ─────────────────────────────────────────────────────────

describe('AbaProposta — telefone do executivo', () => {
  it('avisa quando o cadastro está sem telefone', async () => {
    /* O slide sai com travessão, e o vendedor precisa saber antes. */
    mockGet.mockImplementation(respostas({ ...PADRAO, executivo_telefone: null }));
    montar();
    expect(await screen.findByText(/telefone não está no cadastro/)).toBeInTheDocument();
  });

  it('não avisa quando o telefone existe', async () => {
    montar();
    await screen.findByLabelText('Qtde. de vidas');
    expect(screen.queryByText(/telefone não está no cadastro/)).not.toBeInTheDocument();
  });
});
