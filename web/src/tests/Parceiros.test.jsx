// web/src/tests/Parceiros.test.jsx
//
// A carteira de parceiros tem cinco promessas que os testes precisam segurar:
//   1. as duas taxas aparecem com o denominador certo — e '—' quando não há
//      denominador nenhum (null e 0% são coisas diferentes)
//   2. trocar o EC responsável acontece na LINHA, sem abrir nada
//   3. o KPI 'Sem EC' é um filtro, não um enfeite: ele existe para ser zerado
//   4. o painel abre as indicações e o histórico da carteira
//   5. desmarcar o parceiro fecha o painel — a linha saiu da carteira
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, fireEvent, cleanup, waitFor, within } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';

const mockGet = vi.fn();
const mockPost = vi.fn();
const mockPatch = vi.fn();

vi.mock('../api', () => ({
  default: {
    get: (...a) => mockGet(...a),
    post: (...a) => mockPost(...a),
    patch: (...a) => mockPatch(...a),
  },
}));

import Parceiros from '../pages/crm/Parceiros';

const USUARIOS = [
  { id: 'u1', nome: 'Ana EC', cargo: 'EC' },
  { id: 'u2', nome: 'Bruno EC', cargo: 'EC' },
  { id: 'u3', nome: 'Carla SDR', cargo: 'SDR' },
];

const ALFA = {
  id: 'p1', razao_social: 'Contabilidade Alfa', nome_fantasia: null,
  cnpj: '11111111000191', cnpj_formatado: '11.111.111/0001-91',
  cidade: 'Guarulhos', uf: 'SP', telefone: null, email: null, ativo: true,
  eh_finder: true, ec_responsavel_id: 'u1', ec_responsavel_nome: 'Ana EC',
  indicacoes: 4, convertidas: 1, perdidas: 1, canceladas: 1, em_aberto: 1,
  ticket_indicado: 4000, ticket_convertido: 1000,
  ultima_indicacao_em: '2026-08-01', situacao: 'ativo', situacao_rotulo: 'Ativo',
  taxa_conversao: 0.5, taxa_cancelamento: 0.25,
};

const BETA = {
  ...ALFA,
  id: 'p2', razao_social: 'Escritorio Beta',
  cnpj: '22222222000191', cnpj_formatado: '22.222.222/0001-91',
  ec_responsavel_id: null, ec_responsavel_nome: null,
  indicacoes: 0, convertidas: 0, perdidas: 0, canceladas: 0, em_aberto: 0,
  ticket_indicado: 0, ticket_convertido: 0,
  ultima_indicacao_em: null, situacao: 'sem_indicacao',
  situacao_rotulo: 'Sem indicação',
  taxa_conversao: null, taxa_cancelamento: null,
};

const RESUMO = {
  parceiros: 2, sem_ec: 1, indicacoes: 4, convertidas: 1, canceladas: 1,
  ticket_convertido: 1000, taxa_conversao: 0.5, periodo: 'sempre',
  por_situacao: [
    { situacao: 'sem_indicacao', rotulo: 'Sem indicação', quantidade: 1 },
    { situacao: 'ativo', rotulo: 'Ativo', quantidade: 1 },
    { situacao: 'esfriando', rotulo: 'Esfriando', quantidade: 0 },
    { situacao: 'dormente', rotulo: 'Dormente', quantidade: 3 },
  ],
  por_ec: [{ usuario_id: 'u1', nome: 'Ana EC', parceiros: 1, indicacoes: 4, convertidas: 1 }],
};

const INDICACOES = [{
  id: 'o1', numero: 'OPP-2026-00007', conta_id: 'c1',
  conta_razao_social: 'Metalurgica Gama', fase: 'negociacao', status: 'ativa',
  valor_mensalidade: 2500, criado_em: '2026-08-01T12:00:00Z',
  atualizado_em: '2026-08-01T12:00:00Z',
}];

const DETALHE = {
  ...ALFA,
  eventos: [
    { tipo: 'transferido', de_nome: 'Bruno EC', para_nome: 'Ana EC',
      autor_nome: 'Tulio', criado_em: '2026-08-05T10:00:00Z' },
    { tipo: 'marcado', de_nome: null, para_nome: null,
      autor_nome: 'Tulio', criado_em: '2026-01-02T10:00:00Z' },
  ],
};

function respostas(url) {
  if (url === '/crm/dominio/usuarios') return Promise.resolve({ data: USUARIOS });
  if (url === '/crm/parceiros/resumo') return Promise.resolve({ data: RESUMO });
  if (url === '/crm/parceiros') {
    return Promise.resolve({
      data: { total: 2, limit: 50, offset: 0, periodo: 'sempre', itens: [ALFA, BETA] },
    });
  }
  if (url === '/crm/parceiros/p1/indicacoes') return Promise.resolve({ data: INDICACOES });
  if (url === '/crm/parceiros/p1') return Promise.resolve({ data: DETALHE });
  if (url === '/crm/parceiros/p2') {
    return Promise.resolve({ data: { ...BETA, eventos: [] } });
  }
  if (url === '/crm/parceiros/p2/indicacoes') return Promise.resolve({ data: [] });
  return Promise.resolve({ data: [] });
}

function montar() {
  return render(<MemoryRouter><Parceiros /></MemoryRouter>);
}

beforeEach(() => {
  mockGet.mockReset();
  mockPost.mockReset();
  mockPatch.mockReset();
  mockGet.mockImplementation(respostas);
  mockPatch.mockResolvedValue({ data: DETALHE });
});

afterEach(cleanup);

describe('Parceiros — a carteira na tela', () => {
  it('lista os parceiros com razão social e CNPJ', async () => {
    montar();
    expect(await screen.findByText('Contabilidade Alfa')).toBeInTheDocument();
    expect(screen.getByText('11.111.111/0001-91')).toBeInTheDocument();
  });

  it('mostra a conversão como percentual', async () => {
    montar();
    await screen.findByText('Contabilidade Alfa');
    expect(screen.getAllByText('50%').length).toBeGreaterThan(0);
  });

  it('parceiro sem nada fechado mostra travessão, não 0%', async () => {
    /*
      null e 0 são coisas diferentes: o primeiro é "nada fechou ainda", o
      segundo é "fechou e não converteu". Mostrar 0% para quem acabou de
      entrar na carteira seria cobrar alguém que não deve nada.
    */
    montar();
    const linha = (await screen.findByText('Escritorio Beta')).closest('tr');
    // Conversao e ultima indicacao: dois travessoes na mesma linha.
    expect(within(linha).getAllByText('—').length).toBeGreaterThan(0);
  });

  it('mostra a situação como badge', async () => {
    montar();
    // Escopado na linha: 'Ativo' e 'Sem indicacao' tambem sao opcoes do
    // filtro de situacao na barra.
    const alfa = (await screen.findByText('Contabilidade Alfa')).closest('tr');
    const beta = screen.getByText('Escritorio Beta').closest('tr');
    expect(within(alfa).getByText('Ativo')).toBeInTheDocument();
    expect(within(beta).getByText('Sem indicação')).toBeInTheDocument();
  });

  it('destaca as canceladas ao lado da conversão', async () => {
    montar();
    const linha = (await screen.findByText('Contabilidade Alfa')).closest('tr');
    expect(within(linha).getByText('1 cancelada')).toBeInTheDocument();
  });

  it('a tela tem altura fixa e não rola', async () => {
    const { container } = montar();
    await screen.findByText('Contabilidade Alfa');
    expect(container.firstChild.className).toContain('h-full');
  });

  it('estado vazio quando não há parceiro', async () => {
    mockGet.mockImplementation((url) => {
      if (url === '/crm/parceiros') {
        return Promise.resolve({
          data: { total: 0, limit: 50, offset: 0, periodo: 'sempre', itens: [] },
        });
      }
      return respostas(url);
    });
    montar();
    expect(await screen.findByText('Nenhum parceiro ainda')).toBeInTheDocument();
  });

  it('erro de carga aparece na tela', async () => {
    mockGet.mockImplementation((url) => {
      if (url === '/crm/parceiros/resumo') {
        return Promise.reject({ response: { data: { detail: 'Boom' } } });
      }
      return respostas(url);
    });
    montar();
    expect(await screen.findByText('Boom')).toBeInTheDocument();
  });
});

describe('Parceiros — KPIs', () => {
  it('mostra os quatro indicadores', async () => {
    montar();
    expect(await screen.findByText('Parceiros')).toBeInTheDocument();
    expect(screen.getByText('Sem EC')).toBeInTheDocument();
    expect(screen.getByText('Dormentes')).toBeInTheDocument();
    // 'Conversao' tambem e cabecalho de coluna: pega o KPI pelo title.
    expect(screen.getByTitle(/Das indicações que chegaram ao fim/))
      .toBeInTheDocument();
  });

  it('o KPI Sem EC filtra a fila', async () => {
    /* Este KPI existe para ser zerado: parceiro sem responsável é relação
       que ninguém está cultivando. */
    montar();
    await screen.findByText('Contabilidade Alfa');
    const kpi = screen.getByText('Sem EC').closest('button');
    fireEvent.click(kpi);
    await waitFor(() => expect(kpi).toHaveAttribute('aria-pressed', 'true'));
    await waitFor(() =>
      expect(mockGet).toHaveBeenCalledWith(
        '/crm/parceiros',
        { params: expect.objectContaining({ sem_ec: true }) }
      )
    );
  });

  it('clicar de novo desfaz o filtro', async () => {
    montar();
    await screen.findByText('Contabilidade Alfa');
    const kpi = screen.getByText('Sem EC').closest('button');
    fireEvent.click(kpi);
    await waitFor(() => expect(kpi).toHaveAttribute('aria-pressed', 'true'));
    fireEvent.click(kpi);
    await waitFor(() => expect(kpi).toHaveAttribute('aria-pressed', 'false'));
  });

  it('o KPI Dormentes filtra por situação', async () => {
    montar();
    await screen.findByText('Contabilidade Alfa');
    fireEvent.click(screen.getByText('Dormentes').closest('button'));
    await waitFor(() =>
      expect(mockGet).toHaveBeenCalledWith(
        '/crm/parceiros',
        { params: expect.objectContaining({ situacao: 'dormente' }) }
      )
    );
  });
});

describe('Parceiros — filtros', () => {
  it('o período vai para o resumo e para a lista', async () => {
    montar();
    await screen.findByText('Contabilidade Alfa');
    fireEvent.change(screen.getByLabelText('Período'), { target: { value: '90d' } });
    await waitFor(() =>
      expect(mockGet).toHaveBeenCalledWith(
        '/crm/parceiros/resumo', { params: { periodo: '90d' } }
      )
    );
  });

  it('o seletor de EC só oferece quem trabalha carteira', async () => {
    /*
      Carla é SDR. Se ela aparecesse aqui, a tela deixaria pendurar a
      carteira em quem não a trabalha — e a API responderia 422 depois do
      clique, que é tarde demais.
    */
    montar();
    await screen.findByText('Contabilidade Alfa');
    const nomes = [...screen.getByLabelText('EC responsável').querySelectorAll('option')]
      .map((o) => o.textContent);
    expect(nomes).toEqual(['Todo EC', 'Ana EC', 'Bruno EC']);
  });

  it('filtrar por situação chama a API', async () => {
    montar();
    await screen.findByText('Contabilidade Alfa');
    fireEvent.change(screen.getByLabelText('Situação'), { target: { value: 'esfriando' } });
    await waitFor(() =>
      expect(mockGet).toHaveBeenCalledWith(
        '/crm/parceiros',
        { params: expect.objectContaining({ situacao: 'esfriando' }) }
      )
    );
  });

  it('não recarrega sozinha depois do debounce da busca', async () => {
    /* Mesma regressão das outras telas: o timer dispara uma vez na montagem
       com a busca vazia e trocava a identidade de `filtros`. */
    montar();
    await screen.findByText('Contabilidade Alfa');
    await new Promise((r) => setTimeout(r, 700));
    const chamadas = mockGet.mock.calls.filter(([u]) => u === '/crm/parceiros');
    expect(chamadas).toHaveLength(1);
  });
});

describe('Parceiros — trocar o EC na linha', () => {
  it('o select da linha salva sem abrir o painel', async () => {
    /* Trocar o dono é a ação mais frequente da tela. Exigir abrir o painel
       somaria dois cliques a cada troca. */
    montar();
    await screen.findByText('Contabilidade Alfa');
    const seletor = screen.getByLabelText('EC responsável por Contabilidade Alfa');
    fireEvent.change(seletor, { target: { value: 'u2' } });
    await waitFor(() =>
      expect(mockPatch).toHaveBeenCalledWith(
        '/crm/parceiros/p1',
        { ec_responsavel_id: 'u2' },
        { params: { periodo: 'sempre' } }
      )
    );
    expect(screen.queryByLabelText('Parceiro Contabilidade Alfa')).not.toBeInTheDocument();
  });

  it('escolher "sem responsável" manda null, não string vazia', async () => {
    montar();
    await screen.findByText('Contabilidade Alfa');
    fireEvent.change(
      screen.getByLabelText('EC responsável por Contabilidade Alfa'),
      { target: { value: '' } }
    );
    await waitFor(() =>
      expect(mockPatch).toHaveBeenCalledWith(
        '/crm/parceiros/p1',
        { ec_responsavel_id: null },
        expect.anything()
      )
    );
  });

  it('erro ao salvar aparece na tela', async () => {
    mockPatch.mockRejectedValue({ response: { data: { detail: 'Cargo não trabalha carteira.' } } });
    montar();
    await screen.findByText('Contabilidade Alfa');
    fireEvent.change(
      screen.getByLabelText('EC responsável por Contabilidade Alfa'),
      { target: { value: 'u2' } }
    );
    expect(await screen.findByText('Cargo não trabalha carteira.')).toBeInTheDocument();
  });
});

describe('Parceiros — o painel', () => {
  it('clicar na linha abre o painel do parceiro', async () => {
    montar();
    fireEvent.click(await screen.findByText('Contabilidade Alfa'));
    expect(await screen.findByLabelText('Parceiro Contabilidade Alfa')).toBeInTheDocument();
  });

  it('o painel lista as indicações', async () => {
    montar();
    fireEvent.click(await screen.findByText('Contabilidade Alfa'));
    expect(await screen.findByText('OPP-2026-00007')).toBeInTheDocument();
    expect(screen.getByText('Metalurgica Gama')).toBeInTheDocument();
  });

  it('o painel mostra o histórico da carteira', async () => {
    /* A pergunta "de quem era isso antes" aparece exatamente quando alguém
       abre o parceiro para entender por que ninguém falou com ele. */
    montar();
    fireEvent.click(await screen.findByText('Contabilidade Alfa'));
    const painel = within(await screen.findByLabelText('Parceiro Contabilidade Alfa'));
    expect(painel.getByText('Transferido')).toBeInTheDocument();
    expect(painel.getByText(/era de Bruno EC/)).toBeInTheDocument();
  });

  it('o painel mostra as duas taxas separadas', async () => {
    montar();
    fireEvent.click(await screen.findByText('Contabilidade Alfa'));
    const painel = within(await screen.findByLabelText('Parceiro Contabilidade Alfa'));
    expect(painel.getByText('Conversão')).toBeInTheDocument();
    expect(painel.getByText('Cancelamento')).toBeInTheDocument();
  });

  it('remover da carteira desmarca o parceiro', async () => {
    mockPatch.mockResolvedValue({ data: { ...DETALHE, eh_finder: false } });
    montar();
    fireEvent.click(await screen.findByText('Contabilidade Alfa'));
    fireEvent.click(await screen.findByText('Remover da carteira'));
    await waitFor(() =>
      expect(mockPatch).toHaveBeenCalledWith(
        '/crm/parceiros/p1', { eh_finder: false }, expect.anything()
      )
    );
  });

  it('desmarcado fecha o painel — a linha saiu da carteira', async () => {
    mockPatch.mockResolvedValue({ data: { ...DETALHE, eh_finder: false } });
    montar();
    fireEvent.click(await screen.findByText('Contabilidade Alfa'));
    fireEvent.click(await screen.findByText('Remover da carteira'));
    await waitFor(() =>
      expect(screen.queryByLabelText('Parceiro Contabilidade Alfa')).not.toBeInTheDocument()
    );
  });

  it('o X fecha o painel', async () => {
    montar();
    fireEvent.click(await screen.findByText('Contabilidade Alfa'));
    await screen.findByLabelText('Parceiro Contabilidade Alfa');
    fireEvent.click(screen.getByLabelText('Fechar painel do parceiro'));
    expect(screen.queryByLabelText('Parceiro Contabilidade Alfa')).not.toBeInTheDocument();
  });

  it('a indicação tem atalho para o funil', async () => {
    /* É o caminho mais curto entre "quem indicou" e "o que virou". */
    montar();
    fireEvent.click(await screen.findByText('Contabilidade Alfa'));
    expect(
      await screen.findByLabelText('Abrir OPP-2026-00007 no funil')
    ).toBeInTheDocument();
  });

  it('falha ao buscar indicações não derruba o painel', async () => {
    mockGet.mockImplementation((url) => {
      if (url === '/crm/parceiros/p1/indicacoes') return Promise.reject(new Error('offline'));
      return respostas(url);
    });
    montar();
    fireEvent.click(await screen.findByText('Contabilidade Alfa'));
    expect(
      await screen.findByText('Não foi possível carregar as indicações.')
    ).toBeInTheDocument();
    expect(screen.getByLabelText('Parceiro Contabilidade Alfa')).toBeInTheDocument();
  });
});

describe('Parceiros — transferência de carteira', () => {
  it('o botão da barra abre o modal', async () => {
    montar();
    await screen.findByText('Contabilidade Alfa');
    fireEvent.click(screen.getByText('Transferir carteira'));
    expect(await screen.findByText('Move todos os parceiros de uma vez')).toBeInTheDocument();
  });

  it('transferir recarrega a carteira', async () => {
    mockPost.mockResolvedValue({ data: { transferidos: 1, conta_ids: ['p2'] } });
    montar();
    await screen.findByText('Contabilidade Alfa');
    fireEvent.click(screen.getByText('Transferir carteira'));
    await screen.findByText('Move todos os parceiros de uma vez');
    fireEvent.change(screen.getByLabelText('Para'), { target: { value: 'u1' } });
    fireEvent.click(screen.getByRole('button', { name: /Transferir 1/ }));
    await waitFor(() =>
      expect(mockPost).toHaveBeenCalledWith(
        '/crm/parceiros/carteira/transferir',
        { de_usuario_id: null, para_usuario_id: 'u1' }
      )
    );
  });
});
