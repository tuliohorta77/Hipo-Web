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
  // A tela lê o usuário logado do localStorage para preencher o responsável
  // padrão de toda tarefa nova. O mock precisa exportar getUser junto com o
  // default, senão o import quebra a tela inteira na montagem.
  getUser: () => ({ id: 'u1', nome: 'Ana EC', cargo: 'EC' }),
}));

// ── Farol e mini-funil ───────────────────────────────────────────────
//
// A cor vem PRONTA do backend. A tela não recalcula nada: recalcular criaria
// uma segunda fonte de verdade que diverge no primeiro ajuste, e a que
// divergisse seria a que o usuário está olhando. Por isso os fixtures abaixo
// trazem a cor, e não os números que a produziriam.

function semana(inicio, fim, cor, extra = {}) {
  return {
    inicio, fim, cor, concluidas: 0, agendadas: 0, corrente: false, ...extra,
  };
}

const FAROL_VERDE = [
  semana('2026-07-20', '2026-07-26', 'vermelho'),
  semana('2026-07-27', '2026-08-02', 'amarelo', { agendadas: 1 }),
  semana('2026-08-03', '2026-08-09', 'vermelho'),
  semana('2026-08-10', '2026-08-16', 'verde', { concluidas: 2, corrente: true }),
];

const FAROL_VERMELHO = [
  semana('2026-07-20', '2026-07-26', 'vermelho'),
  semana('2026-07-27', '2026-08-02', 'vermelho'),
  semana('2026-08-03', '2026-08-09', 'vermelho'),
  semana('2026-08-10', '2026-08-16', 'vermelho', { corrente: true }),
];

/*
  A data da próxima tarefa é RELATIVA ao relógio, e não uma data fixa: a
  linha decide entre "próxima" e "atrasada" comparando com agora, então uma
  constante em 2026 viraria "atrasada" sozinha depois daquele dia e o teste
  quebraria por passagem do tempo. Mesma disciplina dos testes de backend,
  onde `hoje` entra por parâmetro.
*/
const DAQUI_A_DOIS_DIAS = new Date(Date.now() + 2 * 86400_000).toISOString();

function fase(qtd = 0, ticket = 0) {
  return { qtd, ticket };
}

const FUNIL_CHEIO = {
  suspect: fase(2, 3000), lead: fase(0, 0), qualificacao: fase(1, 1500),
  apresentacao: fase(0, 0), negociacao: fase(1, 2500),
};

const FUNIL_VAZIO = {
  suspect: fase(), lead: fase(), qualificacao: fase(),
  apresentacao: fase(), negociacao: fase(),
};

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
  farol: FAROL_VERDE, semanas_sem_contato: 0, sem_contato: false,
  tarefas_abertas: 1, proxima_tarefa_em: DAQUI_A_DOIS_DIAS,
  funil: FUNIL_CHEIO,
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
  farol: FAROL_VERMELHO, semanas_sem_contato: 4, sem_contato: true,
  tarefas_abertas: 0, proxima_tarefa_em: null,
  funil: FUNIL_VAZIO,
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
  sem_contato_semana: 1,
  por_cor_semana: [
    { cor: 'verde', rotulo: 'Contato feito', quantidade: 1 },
    { cor: 'amarelo', rotulo: 'Agendado, não feito', quantidade: 0 },
    { cor: 'vermelho', rotulo: 'Sem contato', quantidade: 1 },
  ],
};

const TAREFAS_DO_PARCEIRO = {
  total: 1, abertas: 1, atrasadas: 0,
  itens: [{
    id: 't1', alvo: 'parceiro', alvo_rotulo: 'Parceiro',
    oportunidade_id: null, oportunidade_numero: null, status_oportunidade: null,
    conta_id: 'p1', conta_razao_social: 'Contabilidade Alfa',
    tipo: 'ligacao', tipo_rotulo: 'Ligação', titulo: 'Ligar para o contador',
    descricao: null, responsavel_id: 'u1', responsavel_nome: 'Ana EC',
    prazo: '2026-08-14T12:00:00Z', situacao: 'futura',
    concluida_em: null, resultado: null, cancelada_em: null,
    motivo_cancelamento: null, tarefa_anterior_id: null,
    criado_em: '2026-08-10T12:00:00Z',
  }],
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
  if (url === '/crm/tarefas') return Promise.resolve({ data: TAREFAS_DO_PARCEIRO });
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

/**
 * O drilldown do parceiro. Modal `full`, trilho com abas verticais e barra
 * no rodapé — a MESMA casca do OportunidadeDetalhe.
 *
 * O seletor virou `role=dialog`: quando o drilldown deixou de ser um aside
 * próprio e passou a usar o modal compartilhado, o rótulo passou a ser o
 * título do modal.
 */
async function abrirParceiro(nome = 'Contabilidade Alfa') {
  fireEvent.click(await screen.findByText(nome));
  return screen.findByRole('dialog');
}

describe('Parceiros — o drilldown', () => {
  it('clicar na linha abre o mesmo modal da oportunidade', async () => {
    montar();
    const dialogo = await abrirParceiro();
    expect(within(dialogo).getByText('Contabilidade Alfa')).toBeInTheDocument();
    expect(within(dialogo).getByText('11.111.111/0001-91')).toBeInTheDocument();
  });

  it('as abas do parceiro sao Dados, Tarefas, Indicacoes e Carteira', async () => {
    /*
      O que vai divergir da venda com o tempo é SÓ este conjunto. A casca, o
      trilho e o mecanismo de tarefa são os mesmos.
    */
    montar();
    const dialogo = await abrirParceiro();
    ['dados', 'tarefas', 'indicacoes', 'carteira'].forEach((k) => {
      expect(within(dialogo).getByTestId(`tab-${k}`)).toBeInTheDocument();
    });
  });

  it('abre na aba Dados, com as duas taxas separadas', async () => {
    montar();
    const dialogo = await abrirParceiro();
    expect(within(dialogo).getByText('Conversão')).toBeInTheDocument();
    expect(within(dialogo).getByText('Cancelamento')).toBeInTheDocument();
  });

  it('a aba Dados traz o farol e o mini-funil lado a lado', async () => {
    montar();
    const dialogo = await abrirParceiro();
    expect(within(dialogo).getByText('Contato feito esta semana')).toBeInTheDocument();
    expect(
      within(dialogo).getByLabelText('Funil em aberto: 4 oportunidades')
    ).toBeInTheDocument();
  });

  it('trocar o EC pelo trilho chama o endpoint na hora, sem Salvar', async () => {
    /*
      Mesmo papel que a Fase tem na oportunidade: estado que muda por AÇÃO e
      grava evento, não campo de formulário. Por isso não há botão Salvar.
    */
    montar();
    const dialogo = await abrirParceiro();
    fireEvent.change(within(dialogo).getByLabelText('EC responsável'), {
      target: { value: 'u2' },
    });
    await waitFor(() =>
      expect(mockPatch).toHaveBeenCalledWith(
        '/crm/parceiros/p1', { ec_responsavel_id: 'u2' }, expect.anything()
      )
    );
    expect(within(dialogo).queryByText('Salvar')).not.toBeInTheDocument();
  });

  it('a aba Indicacoes lista o que o parceiro indicou', async () => {
    montar();
    const dialogo = await abrirParceiro();
    fireEvent.click(within(dialogo).getByTestId('tab-indicacoes'));
    expect(await within(dialogo).findByText('OPP-2026-00007')).toBeInTheDocument();
    expect(within(dialogo).getByText('Metalurgica Gama')).toBeInTheDocument();
  });

  it('a indicacao tem atalho para o funil', async () => {
    /* É o caminho mais curto entre "quem indicou" e "o que virou". */
    montar();
    const dialogo = await abrirParceiro();
    fireEvent.click(within(dialogo).getByTestId('tab-indicacoes'));
    expect(
      await within(dialogo).findByLabelText('Abrir OPP-2026-00007 no funil')
    ).toBeInTheDocument();
  });

  it('falha ao buscar indicacoes nao derruba o drilldown', async () => {
    mockGet.mockImplementation((url, cfg) => {
      if (url === '/crm/parceiros/p1/indicacoes') return Promise.reject(new Error('offline'));
      return respostas(url, cfg);
    });
    montar();
    const dialogo = await abrirParceiro();
    fireEvent.click(within(dialogo).getByTestId('tab-indicacoes'));
    expect(
      await within(dialogo).findByText('Não foi possível carregar as indicações.')
    ).toBeInTheDocument();
    expect(screen.getByRole('dialog')).toBeInTheDocument();
  });

  it('a aba Carteira mostra de quem era antes', async () => {
    montar();
    const dialogo = await abrirParceiro();
    fireEvent.click(within(dialogo).getByTestId('tab-carteira'));
    expect(within(dialogo).getByText('Transferido')).toBeInTheDocument();
    expect(within(dialogo).getByText(/era de Bruno EC/)).toBeInTheDocument();
  });

  it('remover da carteira desmarca o parceiro', async () => {
    mockPatch.mockResolvedValue({ data: { ...DETALHE, eh_finder: false } });
    montar();
    const dialogo = await abrirParceiro();
    fireEvent.click(within(dialogo).getByText('Remover da carteira'));
    await waitFor(() =>
      expect(mockPatch).toHaveBeenCalledWith(
        '/crm/parceiros/p1', { eh_finder: false }, expect.anything()
      )
    );
  });

  it('desmarcado fecha o drilldown — a linha saiu da carteira', async () => {
    mockPatch.mockResolvedValue({ data: { ...DETALHE, eh_finder: false } });
    montar();
    const dialogo = await abrirParceiro();
    fireEvent.click(within(dialogo).getByText('Remover da carteira'));
    await waitFor(() => expect(screen.queryByRole('dialog')).not.toBeInTheDocument());
  });

  it('Fechar fecha o drilldown', async () => {
    montar();
    const dialogo = await abrirParceiro();
    fireEvent.click(within(dialogo).getByText('Fechar'));
    await waitFor(() => expect(screen.queryByRole('dialog')).not.toBeInTheDocument());
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

// ── Farol, mini-funil e tarefas (006) ────────────────────────────────
//
// As duas colunas novas respondem perguntas opostas, e é por isso que existem
// as duas: o farol mede o que NÓS fizemos pelo parceiro, o mini-funil mede o
// que ELE nos deu. Parceiro sem indicação com quatro semanas verdes é
// problema de mercado; com quatro vermelhas é abandono.

describe('Parceiros — o farol semanal na linha', () => {
  it('cada parceiro tem a trilha das quatro semanas', async () => {
    montar();
    const linha = (await screen.findByText('Contabilidade Alfa')).closest('tr');
    expect(
      within(linha).getByRole('button', { name: /Contato feito esta semana/ })
    ).toBeInTheDocument();
  });

  it('quem está parado mostra há quantas semanas', async () => {
    montar();
    const linha = (await screen.findByText('Escritorio Beta')).closest('tr');
    expect(
      within(linha).getByRole('button', { name: /Sem contato há 4\+ semanas/ })
    ).toBeInTheDocument();
  });

  it('mostra quando é a próxima tarefa', async () => {
    /*
      Embrião da "próxima tarefa" da Etapa 5: a linha já diz QUANDO é o
      próximo toque, sem ainda decidir por ninguém qual fazer primeiro.
    */
    montar();
    const linha = (await screen.findByText('Contabilidade Alfa')).closest('tr');
    expect(within(linha).getByText(/^próxima /)).toBeInTheDocument();
  });

  it('prazo vencido não é chamado de "próxima"', async () => {
    /*
      Tarefa em aberto com prazo passado é dívida, não futuro. Chamá-la de
      próxima faria a linha anunciar "próxima 22/07" num dia 13/08.
    */
    mockGet.mockImplementation((url, cfg) => {
      if (url === '/crm/parceiros') {
        return Promise.resolve({
          data: {
            total: 1, limit: 50, offset: 0, periodo: 'sempre',
            itens: [{ ...ALFA, proxima_tarefa_em: '2020-01-15T12:00:00Z' }],
          },
        });
      }
      return respostas(url, cfg);
    });
    montar();
    const linha = (await screen.findByText('Contabilidade Alfa')).closest('tr');
    expect(within(linha).getByText(/^atrasada /)).toBeInTheDocument();
    expect(within(linha).queryByText(/^próxima /)).not.toBeInTheDocument();
  });

  it('sem tarefa marcada a linha diz isso, em vez de ficar em branco', async () => {
    montar();
    const linha = (await screen.findByText('Escritorio Beta')).closest('tr');
    expect(within(linha).getByText('nada agendado')).toBeInTheDocument();
  });

  it('clicar no farol abre o drilldown daquele parceiro', async () => {
    /*
      Diretriz pétrea 2. Um farol vermelho que não leva a lugar nenhum é
      relatório; daqui o EC chega às tarefas em um clique.
    */
    montar();
    const linha = (await screen.findByText('Contabilidade Alfa')).closest('tr');
    fireEvent.click(
      within(linha).getByRole('button', { name: /Contato feito esta semana/ })
    );
    expect(
      await screen.findByRole('dialog')
    ).toBeInTheDocument();
  });
});

describe('Parceiros — o mini-funil na linha', () => {
  it('mostra o estoque aberto por fase', async () => {
    montar();
    const linha = (await screen.findByText('Contabilidade Alfa')).closest('tr');
    expect(
      within(linha).getByLabelText('Funil em aberto: 4 oportunidades')
    ).toBeInTheDocument();
  });

  it('parceiro sem nada em aberto mostra a frase, não cinco zeros', async () => {
    montar();
    const linha = (await screen.findByText('Escritorio Beta')).closest('tr');
    expect(within(linha).getByText('Nada em aberto')).toBeInTheDocument();
  });
});

/**
 * O KPI, e não o farol da linha.
 *
 * Os dois começam com "Sem contato": o KPI se chama "Sem contato 1" (rótulo
 * + valor) e o farol de um parceiro parado se chama "Sem contato há 4+
 * semanas". Sem a âncora no dígito, o seletor pega os dois e o teste falha
 * com "found multiple elements" — que é um erro de teste, não de tela.
 */
function kpiSemContato() {
  return screen.getByRole('button', { name: /^Sem contato \d/ });
}

describe('Parceiros — o KPI "Sem contato"', () => {
  it('mostra quantos estão vermelhos nesta semana', async () => {
    montar();
    await screen.findByText('Contabilidade Alfa');
    const kpi = kpiSemContato();
    expect(kpi).toHaveTextContent('1');
  });

  it('clicar filtra a carteira pelos vermelhos', async () => {
    /*
      É o KPI que existe para ser zerado toda sexta. Sem o filtro ele seria
      um número que ninguém sabe o que fazer com.
    */
    montar();
    await screen.findByText('Contabilidade Alfa');
    fireEvent.click(kpiSemContato());
    await waitFor(() =>
      expect(mockGet).toHaveBeenCalledWith(
        '/crm/parceiros',
        expect.objectContaining({
          params: expect.objectContaining({ sem_contato: true }),
        })
      )
    );
  });

  it('clicar de novo desfaz o filtro', async () => {
    montar();
    await screen.findByText('Contabilidade Alfa');
    const kpi = kpiSemContato();
    fireEvent.click(kpi);
    await waitFor(() => expect(kpi).toHaveAttribute('aria-pressed', 'true'));
    fireEvent.click(kpi);
    await waitFor(() => expect(kpi).toHaveAttribute('aria-pressed', 'false'));
    const ultima = mockGet.mock.calls
      .filter(([url]) => url === '/crm/parceiros')
      .pop();
    expect(ultima[1].params).not.toHaveProperty('sem_contato');
  });

  it('só um KPI fica ativo por vez', async () => {
    montar();
    await screen.findByText('Contabilidade Alfa');
    fireEvent.click(kpiSemContato());
    fireEvent.click(screen.getByRole('button', { name: /Dormentes/ }));
    await waitFor(() =>
      expect(kpiSemContato())
        .toHaveAttribute('aria-pressed', 'false')
    );
  });
});

describe('Parceiros — a aba de Tarefas e a mesma da venda', () => {
  it('a aba carrega as tarefas DAQUELE parceiro', async () => {
    montar();
    const dialogo = await abrirParceiro();
    fireEvent.click(within(dialogo).getByTestId('tab-tarefas'));
    expect(await within(dialogo).findByText('Ligar para o contador')).toBeInTheDocument();
    expect(mockGet).toHaveBeenCalledWith('/crm/tarefas', {
      params: { conta_id: 'p1', ordenar: 'cronologico' },
    });
  });

  it('usa a linha do tempo, igual a da oportunidade', async () => {
    /*
      Mesmo componente, não um parecido. Se alguém recriar uma lista própria
      para o parceiro, este teste cai.
    */
    montar();
    const dialogo = await abrirParceiro();
    fireEvent.click(within(dialogo).getByTestId('tab-tarefas'));
    expect(
      await within(dialogo).findByLabelText('Linha do tempo das tarefas')
    ).toBeInTheDocument();
  });

  it('concluir exige agendar a proxima, igual a oportunidade', async () => {
    /*
      Parceria não tem estado final que dispense a próxima — e é por isso que
      ela exige. Sem próximo contato marcado, a relação some da agenda de
      todo mundo e só reaparece meses depois, como parceiro dormente.
    */
    montar();
    const dialogo = await abrirParceiro();
    fireEvent.click(within(dialogo).getByTestId('tab-tarefas'));
    fireEvent.click(await within(dialogo).findByText('Ligar para o contador'));
    fireEvent.click(await within(dialogo).findByLabelText(/^Concluir Ligar/));

    expect(within(dialogo).getByLabelText(/Próxima: Título/)).toBeInTheDocument();
    expect(
      within(dialogo).getByText('Concluir tarefa').closest('button')
    ).toBeDisabled();
  });

  it('o aviso da proxima nao manda "finalizar a oportunidade"', async () => {
    /*
      Não existe "finalizar parceria", e a tela do parceiro não tem esse
      botão. Mandar o usuário fazer uma ação que a tela não oferece é pior
      do que não explicar. Espelha a mensagem do backend.
    */
    montar();
    const dialogo = await abrirParceiro();
    fireEvent.click(within(dialogo).getByTestId('tab-tarefas'));
    fireEvent.click(await within(dialogo).findByText('Ligar para o contador'));
    fireEvent.click(await within(dialogo).findByLabelText(/^Concluir Ligar/));

    expect(within(dialogo).queryByText(/finalize a oportunidade/)).not.toBeInTheDocument();
    expect(within(dialogo).getByText(/tire o parceiro da carteira/)).toBeInTheDocument();
  });

  it('concluir com a proxima preenchida recarrega a linha e o drilldown', async () => {
    /*
      O farol e a contagem de abertas são da LINHA. Sem o recarregamento, o
      quadradinho da semana continuaria vermelho depois de a tarefa ser
      concluída — a tela mentindo sobre o que o usuário acabou de fazer.
    */
    mockPost.mockResolvedValue({ data: {} });
    montar();
    const dialogo = await abrirParceiro();
    fireEvent.click(within(dialogo).getByTestId('tab-tarefas'));
    fireEvent.click(await within(dialogo).findByText('Ligar para o contador'));
    fireEvent.click(await within(dialogo).findByLabelText(/^Concluir Ligar/));

    const antes = mockGet.mock.calls.filter(([u]) => u === '/crm/parceiros').length;
    fireEvent.change(within(dialogo).getByLabelText(/Próxima: Título/), {
      target: { value: 'Retomar em duas semanas' },
    });
    fireEvent.click(within(dialogo).getByText('Concluir tarefa'));

    await waitFor(() =>
      expect(
        mockGet.mock.calls.filter(([u]) => u === '/crm/parceiros').length
      ).toBeGreaterThan(antes)
    );
    expect(mockGet).toHaveBeenCalledWith('/crm/parceiros/p1', expect.anything());
  });

  it('o detalhe da tarefa tem textarea, nao input de uma linha', async () => {
    /*
      Campo apertado ensina a escrever pouco. O detalhe é textarea; o título
      segue em uma linha, porque rótulo que vira parágrafo quebra a lista.
    */
    montar();
    const dialogo = await abrirParceiro();
    fireEvent.click(within(dialogo).getByTestId('tab-tarefas'));
    fireEvent.click(await within(dialogo).findByText('Nova tarefa'));

    const detalhe = within(dialogo).getByLabelText(/Detalhe \(opcional\)/);
    expect(detalhe.tagName).toBe('TEXTAREA');
    expect(Number(detalhe.getAttribute('rows'))).toBeGreaterThanOrEqual(3);
    expect(within(dialogo).getByLabelText(/^Título/).tagName).toBe('INPUT');
  });
});
