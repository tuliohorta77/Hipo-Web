// web/src/tests/Oportunidades.test.jsx
//
// A página do funil: TRÊS visões dos mesmos dados (kanban, tabela e funil),
// com a preferência gravada no banco (não no localStorage), e KPIs que
// aplicam filtro.
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, fireEvent, cleanup, waitFor, within } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';

const mockGet = vi.fn();
const mockPost = vi.fn();
const mockPatch = vi.fn();
const mockPut = vi.fn();

vi.mock('../api', () => ({
  default: {
    get: (...a) => mockGet(...a),
    post: (...a) => mockPost(...a),
    patch: (...a) => mockPatch(...a),
    put: (...a) => mockPut(...a),
  },
}));

import Oportunidades from '../pages/crm/Oportunidades';

const RESUMO = {
  abertas: 3, ticket_aberto: 7500, previsto_no_mes: 2500,
  paradas: 0, ganhas_mes: 2, perdidas_mes: 1,
  por_fase: [
    { fase: 'suspect', rotulo: 'Suspect', quantidade: 2, ticket: 5000 },
    { fase: 'lead', rotulo: 'Lead', quantidade: 0, ticket: 0 },
    { fase: 'qualificacao', rotulo: 'Qualificação', quantidade: 0, ticket: 0 },
    { fase: 'apresentacao', rotulo: 'Apresentação', quantidade: 0, ticket: 0 },
    { fase: 'negociacao', rotulo: 'Negociação', quantidade: 1, ticket: 2500 },
  ],
  perda_por_fase: [],
};

const OPP = {
  id: 'o1', numero: 'OPP-2026-00001', conta_id: 'c1',
  conta_razao_social: 'Metalurgica Alfa', contato_id: null, contato_nome: null,
  fase: 'negociacao', status: 'ativa', fase_desfecho: null, motivo_desfecho: null,
  valor_mensalidade: 2500, temperatura: 70, previsao_fechamento: '2026-09-30',
  proxima_acao_em: null, proxima_acao_tipo: null, origem_nome: null,
  finder_conta_id: null, finder_razao_social: null, envolvidos: [],
  criado_em: '2026-08-01T12:00:00Z', atualizado_em: '2026-08-01T12:00:00Z',
};

const vazia = (fase, rotulo, extra = {}) => ({
  fase, rotulo, quantidade: 0, ticket_total: 0, itens: [],
  somente_leitura: false, ...extra,
});

const COLUNAS = [
  vazia('suspect', 'Suspect'),
  vazia('lead', 'Lead'),
  vazia('qualificacao', 'Qualificação'),
  vazia('apresentacao', 'Apresentação'),
  vazia('negociacao', 'Negociação', {
    quantidade: 1, ticket_total: 2500, itens: [OPP],
  }),
  vazia('finalizado', 'Finalizado', { somente_leitura: true }),
];

function respostas(visaoSalva) {
  return (url) => {
    if (url === '/crm/dominio/preferencias') {
      return Promise.resolve({
        data: visaoSalva ? [{ chave: 'crm_oportunidades_visao', valor: visaoSalva }] : [],
      });
    }
    if (url === '/crm/dominio/usuarios') {
      return Promise.resolve({ data: [{ id: 'u1', nome: 'Ana Vendas', cargo: 'EV' }] });
    }
    if (url === '/crm/oportunidades/resumo') return Promise.resolve({ data: RESUMO });
    if (url === '/crm/oportunidades/kanban') return Promise.resolve({ data: COLUNAS });
    if (url === '/crm/oportunidades') {
      return Promise.resolve({ data: { total: 1, limit: 50, offset: 0, itens: [OPP] } });
    }
    return Promise.resolve({ data: [] });
  };
}

function montar() {
  return render(<MemoryRouter><Oportunidades /></MemoryRouter>);
}

beforeEach(() => {
  mockGet.mockReset();
  mockPost.mockReset();
  mockPatch.mockReset();
  mockPut.mockReset();
  mockGet.mockImplementation(respostas(null));
});

afterEach(cleanup);

describe('Oportunidades — visão padrão e preferência', () => {
  it('abre no kanban quando não há preferência salva', async () => {
    montar();
    expect(await screen.findByRole('region', { name: 'Fase Suspect' })).toBeInTheDocument();
  });

  it('não recarrega o funil sozinho depois do debounce da busca', async () => {
    /*
      Regressao real: o timer da busca dispara uma vez na montagem, com a
      busca vazia. Ele criava um `filtros` novo por identidade, `params`
      recalculava, `carregar` trocava e a tela buscava tudo de novo — piscando
      o "Carregando funil…" e desmontando o que ja estava renderizado. O
      sintoma era o kanban sumir do DOM entre o findByRole e o assert, so em
      maquina lenta o suficiente para os dois cairem em lados diferentes do
      timer.
    */
    montar();
    await screen.findByRole('region', { name: 'Fase Suspect' });
    await new Promise((r) => setTimeout(r, 700));
    const chamadas = mockGet.mock.calls.filter(
      ([u]) => u === '/crm/oportunidades/kanban'
    );
    expect(chamadas).toHaveLength(1);
  });

  it('a tela tem altura fixa e não rola', async () => {
    /*
      O scroll vive nas colunas do kanban. Se a raiz voltar a crescer, o
      arrasto entre a primeira e a última coluna volta a exigir rolagem.
    */
    const { container } = montar();
    await screen.findByRole('region', { name: 'Fase Suspect' });
    expect(container.firstChild.className).toContain('h-full');
    expect(container.firstChild.className).not.toContain('space-y-6');
  });

  it('respeita a preferência de tabela vinda do banco', async () => {
    mockGet.mockImplementation(respostas('tabela'));
    montar();
    expect(await screen.findByText('OPP-2026-00001')).toBeInTheDocument();
    expect(screen.queryByRole('region', { name: 'Fase Suspect' })).not.toBeInTheDocument();
  });

  it('trocar de visão grava a preferência no banco', async () => {
    /*
      No banco e não no localStorage: o HIPO é a fonte primária, e a escolha
      deve acompanhar a pessoa entre máquinas.
    */
    montar();
    await screen.findByRole('region', { name: 'Fase Suspect' });
    fireEvent.click(screen.getByLabelText('Ver como tabela'));
    await waitFor(() =>
      expect(mockPut).toHaveBeenCalledWith(
        '/crm/dominio/preferencias/crm_oportunidades_visao',
        { valor: 'tabela' }
      )
    );
  });

  it('falha ao gravar a preferência não trava a troca de visão', async () => {
    mockPut.mockRejectedValue(new Error('offline'));
    montar();
    await screen.findByRole('region', { name: 'Fase Suspect' });
    fireEvent.click(screen.getByLabelText('Ver como tabela'));
    expect(await screen.findByText('OPP-2026-00001')).toBeInTheDocument();
  });
});

describe('Oportunidades — a terceira visão (funil)', () => {
  it('respeita a preferência de funil vinda do banco', async () => {
    mockGet.mockImplementation(respostas('funil'));
    montar();
    expect(await screen.findByRole('region', { name: 'Funil de vendas' })).toBeInTheDocument();
    expect(screen.queryByRole('region', { name: 'Fase Suspect' })).not.toBeInTheDocument();
  });

  it('preferência com valor desconhecido cai no kanban', async () => {
    /*
      A preferência vem do banco e pode ter sido gravada por uma versão
      anterior da tela. Sem whitelist, um valor órfão renderizava a página
      sem visão nenhuma.
    */
    mockGet.mockImplementation(respostas('carrossel'));
    montar();
    expect(await screen.findByRole('region', { name: 'Fase Suspect' })).toBeInTheDocument();
  });

  it('trocar para funil grava a preferência no banco', async () => {
    montar();
    await screen.findByRole('region', { name: 'Fase Suspect' });
    fireEvent.click(screen.getByLabelText('Ver como funil'));
    await waitFor(() =>
      expect(mockPut).toHaveBeenCalledWith(
        '/crm/dominio/preferencias/crm_oportunidades_visao',
        { valor: 'funil' }
      )
    );
  });

  it('o funil não busca kanban nem a lista — ele vem do resumo', async () => {
    /*
      As faixas são desenhadas com `por_fase` e `perda_por_fase`, que já vêm
      no /resumo. Buscar a lista aqui seria uma varredura inteira da tabela
      para desenhar cinco retângulos.
    */
    mockGet.mockImplementation(respostas('funil'));
    montar();
    await screen.findByRole('region', { name: 'Funil de vendas' });
    expect(mockGet.mock.calls.filter(([u]) => u === '/crm/oportunidades/kanban')).toHaveLength(0);
    expect(mockGet.mock.calls.filter(([u]) => u === '/crm/oportunidades')).toHaveLength(0);
  });

  it('o resumo recebe os mesmos filtros das outras visões', async () => {
    /*
      Sem isso, trocar de visão com um filtro ativo mostrava um funil global
      ao lado de uma lista filtrada — dois números diferentes para a mesma
      pergunta, na mesma tela.
    */
    mockGet.mockImplementation(respostas('funil'));
    montar();
    await screen.findByRole('region', { name: 'Funil de vendas' });
    fireEvent.change(screen.getByLabelText('Envolvido'), { target: { value: 'u1' } });
    await waitFor(() =>
      expect(mockGet).toHaveBeenCalledWith(
        '/crm/oportunidades/resumo',
        { params: { envolvido_id: 'u1' } }
      )
    );
  });

  it('a métrica do funil também é preferência de banco', async () => {
    mockGet.mockImplementation(respostas('funil'));
    montar();
    await screen.findByRole('region', { name: 'Funil de vendas' });
    fireEvent.click(screen.getByRole('button', { name: 'R$' }));
    await waitFor(() =>
      expect(mockPut).toHaveBeenCalledWith(
        '/crm/dominio/preferencias/crm_oportunidades_funil_metrica',
        { valor: 'ticket' }
      )
    );
  });

  it('o filtro de fase não aparece no funil — a fase É a faixa', async () => {
    mockGet.mockImplementation(respostas('funil'));
    montar();
    await screen.findByRole('region', { name: 'Funil de vendas' });
    expect(screen.queryByLabelText('Fase')).not.toBeInTheDocument();
  });

  it('mover pelo painel da fase chama o endpoint e recarrega', async () => {
    mockGet.mockImplementation(respostas('funil'));
    montar();
    await screen.findByRole('region', { name: 'Funil de vendas' });
    fireEvent.click(screen.getByLabelText('Ver oportunidades em Negociação'));
    const seletor = await screen.findByLabelText('Mover OPP-2026-00001 para outra fase');
    fireEvent.change(seletor, { target: { value: 'lead' } });
    await waitFor(() =>
      expect(mockPatch).toHaveBeenCalledWith(
        '/crm/oportunidades/o1/fase', { fase: 'lead' }
      )
    );
  });
});

describe('Oportunidades — KPIs', () => {
  it('mostra os três indicadores', async () => {
    montar();
    expect(await screen.findByText('Em aberto')).toBeInTheDocument();
    expect(screen.getByText('Previsto no mês')).toBeInTheDocument();
    expect(screen.getByText('Ganhas no mês')).toBeInTheDocument();
  });

  it('não existe mais o KPI "Sem próxima ação"', async () => {
    /*
      Saiu do produto: concluir uma tarefa vai obrigar o vendedor a criar a
      próxima, então o indicador nasceria zerado para sempre — e um KPI que
      nunca sai de zero só ocupa a altura que as colunas precisam.
    */
    montar();
    await screen.findByText('Em aberto');
    expect(screen.queryByText('Sem próxima ação')).not.toBeInTheDocument();
  });

  it('clicar em "Em aberto" filtra', async () => {
    montar();
    await screen.findByText('Em aberto');
    const kpi = screen.getByText('Em aberto').closest('button');
    fireEvent.click(kpi);
    await waitFor(() => expect(kpi).toHaveAttribute('aria-pressed', 'true'));
  });

  it('clicar de novo desfaz o filtro', async () => {
    montar();
    await screen.findByText('Em aberto');
    const kpi = screen.getByText('Em aberto').closest('button');
    fireEvent.click(kpi);
    await waitFor(() => expect(kpi).toHaveAttribute('aria-pressed', 'true'));
    fireEvent.click(kpi);
    await waitFor(() => expect(kpi).toHaveAttribute('aria-pressed', 'false'));
  });
});

describe('Oportunidades — tabela', () => {
  beforeEach(() => { mockGet.mockImplementation(respostas('tabela')); });

  it('lista com número, empresa e valor', async () => {
    montar();
    expect(await screen.findByText('OPP-2026-00001')).toBeInTheDocument();
    expect(screen.getByText('Metalurgica Alfa')).toBeInTheDocument();
  });

  it('mostra o filtro de fase só na tabela', async () => {
    montar();
    await screen.findByText('OPP-2026-00001');
    expect(screen.getByLabelText('Fase')).toBeInTheDocument();
  });

  it('as seis fases aparecem no filtro', async () => {
    montar();
    await screen.findByText('OPP-2026-00001');
    const opcoes = [...screen.getByLabelText('Fase').querySelectorAll('option')]
      .map((o) => o.value)
      .filter(Boolean);
    expect(opcoes).toEqual([
      'suspect', 'lead', 'qualificacao', 'apresentacao', 'negociacao', 'finalizado',
    ]);
  });

  it('estado vazio quando não há oportunidades', async () => {
    mockGet.mockImplementation((url) => {
      if (url === '/crm/oportunidades') {
        return Promise.resolve({ data: { total: 0, limit: 50, offset: 0, itens: [] } });
      }
      return respostas('tabela')(url);
    });
    montar();
    expect(await screen.findByText('Nenhuma oportunidade')).toBeInTheDocument();
  });
});

describe('Oportunidades — kanban', () => {
  it('mover cartão chama o endpoint de fase', async () => {
    montar();
    await screen.findByRole('region', { name: 'Fase Suspect' });
    const seletor = screen.getByLabelText('Mover OPP-2026-00001 para outra fase');
    fireEvent.change(seletor, { target: { value: 'lead' } });
    await waitFor(() =>
      expect(mockPatch).toHaveBeenCalledWith(
        '/crm/oportunidades/o1/fase', { fase: 'lead' }
      )
    );
  });

  it('erro ao mover é exibido', async () => {
    mockPatch.mockRejectedValue({ response: { data: { detail: 'Reabra antes.' } } });
    montar();
    await screen.findByRole('region', { name: 'Fase Suspect' });
    fireEvent.change(
      screen.getByLabelText('Mover OPP-2026-00001 para outra fase'),
      { target: { value: 'lead' } }
    );
    expect(await screen.findByText('Reabra antes.')).toBeInTheDocument();
  });

  it('botão Finalizar do cartão abre o modal de desfecho', async () => {
    montar();
    await screen.findByRole('region', { name: 'Fase Suspect' });
    fireEvent.click(screen.getByLabelText('Finalizar OPP-2026-00001'));
    expect(await screen.findByText('Finalizar oportunidade')).toBeInTheDocument();
  });
});

describe('Oportunidades — o drill da oportunidade', () => {
  const DETALHE = {
    ...OPP,
    descricao: null, observacoes: null, origem_id: null,
    concorrentes: [], tarefas_abertas: 0,
  };

  // A aba Proposta é um componente que carrega do servidor. Sem estes dois
  // mocks ela quebraria ao mapear um escopo indefinido — e o teste falharia
  // por montagem, não pelo que ele quer medir.
  const PADRAO_PROPOSTA = {
    escopo_padrao: ['PGR - (NR-01)'],
    cidade: 'Guarulhos', dias_validade: 10,
    vidas: null, valor_por_vida: null,
    executivo_id: 'u1', executivo_nome: 'Ana Vendas',
    executivo_email: 'ana@exemplo.com', executivo_telefone: '11 90000-0000',
    cliente_razao_social: 'Metalurgica Alfa',
    geracao_disponivel: true, pdf_disponivel: true,
  };

  function respostasComDetalhe(url) {
    if (url === '/crm/oportunidades/o1') return Promise.resolve({ data: DETALHE });
    if (url.endsWith('/proposta-padrao')) return Promise.resolve({ data: PADRAO_PROPOSTA });
    if (url.endsWith('/propostas')) return Promise.resolve({ data: [] });
    if (url === '/crm/contatos') {
      return Promise.resolve({ data: { total: 0, limit: 100, offset: 0, itens: [] } });
    }
    if (url === '/crm/tarefas') {
      return Promise.resolve({ data: { total: 0, abertas: 0, atrasadas: 0, itens: [] } });
    }
    if (url.startsWith('/crm/dominio/')) return Promise.resolve({ data: [] });
    return respostas(null)(url);
  }

  async function abrir() {
    mockGet.mockImplementation(respostasComDetalhe);
    montar();
    await screen.findByRole('region', { name: 'Fase Suspect' });
    fireEvent.click(screen.getByText('Metalurgica Alfa'));
    await screen.findByTestId('tab-dados');
  }

  it('o subtítulo do modal é o status, não a fase', async () => {
    /*
      A fase já está no seletor do trilho. O que muda a leitura da tela é
      saber se está ativa, suspensa ou finalizada.
    */
    await abrir();
    // O número também aparece no cartão do kanban atrás do modal — pega o
    // <h2> do cabeçalho, que é único.
    const cabecalho = screen.getByRole('heading', { name: /OPP-2026-00001/ })
      .closest('div').parentElement;
    expect(cabecalho).toHaveTextContent('ativa');
    expect(cabecalho).not.toHaveTextContent('Negociação');
  });

  it('as quatro ações ficam na mesma barra de baixo', async () => {
    /*
      Suspender e Finalizar são saídas desta tela, igual a Fechar e Salvar.
      Espalhá-las em cantos diferentes obrigava o olho a procurar.
    */
    await abrir();
    // Escopado na barra: 'Fechar' também é o rótulo do botão de desfecho no
    // cartão do kanban, e 'Finalizar' aparece no X do modal.
    const barra = within(screen.getByLabelText('Ações da oportunidade'));
    for (const acao of ['Suspender', 'Finalizar', 'Fechar', 'Salvar']) {
      expect(barra.getByText(acao)).toBeInTheDocument();
    }
  });

  it('fase e temperatura ficam no trilho, com o rótulo na mesma linha', async () => {
    await abrir();
    expect(screen.getByLabelText('Fase')).toBeInTheDocument();
    expect(screen.getByLabelText('Temperatura')).toBeInTheDocument();
  });

  it('mensalidade saiu do trilho e foi para a aba Proposta', async () => {
    /* É resultado de proposta, não atributo solto da oportunidade. */
    await abrir();
    expect(screen.queryByLabelText('Mensalidade (R$)')).not.toBeInTheDocument();
    fireEvent.click(screen.getByTestId('tab-proposta'));
    expect(await screen.findByLabelText('Mensalidade (R$)')).toBeInTheDocument();
  });

  it('a aba Proposta traz o formulário da proposta comercial', async () => {
    /*
      Substitui o teste do placeholder "ainda não implementadas": a aba
      passou a gerar o .pptx de verdade. Aqui só se confere que ela monta e
      pede os dados certos — o comportamento da proposta tem arquivo
      próprio, em AbaProposta.test.jsx.
    */
    await abrir();
    fireEvent.click(screen.getByTestId('tab-proposta'));
    expect(await screen.findByLabelText('Qtde. de vidas')).toBeInTheDocument();
    expect(screen.getByLabelText('Válida até')).toBeInTheDocument();
    expect(screen.getByText('Gerar proposta')).toBeInTheDocument();
  });

  it('a mensalidade continua editável para negociação sem proposta', async () => {
    /* Negociação que começou no telefone tem valor antes de ter documento. */
    await abrir();
    fireEvent.click(screen.getByTestId('tab-proposta'));
    expect(await screen.findByLabelText('Mensalidade (R$)')).toBeInTheDocument();
  });
});

// ── Drilldown da conta ───────────────────────────────────────────────
//
// A pergunta "quem é essa empresa" nasce dentro da negociação. Antes ela
// custava fechar o modal, trocar de tela e buscar a razão social de novo.
// A visão 360 da conta abre EM CIMA da oportunidade, editável, e some sem
// levar junto o que estava aberto atrás.

describe('Oportunidades — drilldown da conta', () => {
  const DETALHE = {
    ...OPP,
    descricao: null, observacoes: null, origem_id: null,
    concorrentes: [], tarefas_abertas: 0,
  };

  const CONTA = {
    id: 'c1',
    razao_social: 'Metalurgica Alfa LTDA',
    nome_fantasia: 'Alfa',
    cnpj: '11222333000181',
    cnpj_formatado: '11.222.333/0001-81',
    vertical_id: 1, vertical_nome: 'Metalúrgica', num_funcionarios: 120,
    cep: '07020020', logradouro: 'Rua A', numero: '100', complemento: null,
    bairro: 'Centro', cidade: 'Guarulhos', uf: 'SP',
    telefone: '1130001000', telefone_2: null, email: 'contato@alfa.com',
    observacoes: null, eh_finder: false, ativo: true,
    vendedores: ['Ana Vendas'], qtd_oportunidades_ativas: 1,
    criado_em: '2026-08-01T12:00:00Z', atualizado_em: '2026-08-01T12:00:00Z',
    contatos: [],
    oportunidades: [
      { id: 'o1', numero: 'OPP-2026-00001', fase: 'negociacao', status: 'ativa',
        valor_mensalidade: 2500, temperatura: 70, previsao_fechamento: '2026-09-30' },
    ],
  };

  function respostasComConta(url) {
    if (url === '/crm/oportunidades/o1') return Promise.resolve({ data: DETALHE });
    if (url === '/crm/contas/c1') return Promise.resolve({ data: CONTA });
    if (url === '/crm/dominio/verticais') {
      return Promise.resolve({ data: [{ id: 1, nome: 'Metalúrgica', slug: 'metalurgica' }] });
    }
    if (url === '/crm/contatos') {
      return Promise.resolve({ data: { total: 0, limit: 100, offset: 0, itens: [] } });
    }
    if (url === '/crm/tarefas') {
      return Promise.resolve({ data: { total: 0, abertas: 0, atrasadas: 0, itens: [] } });
    }
    if (url.startsWith('/crm/dominio/')) return Promise.resolve({ data: [] });
    return respostas(null)(url);
  }

  async function abrirOportunidade() {
    mockGet.mockImplementation(respostasComConta);
    montar();
    await screen.findByRole('region', { name: 'Fase Suspect' });
    fireEvent.click(screen.getByText('Metalurgica Alfa'));
    await screen.findByTestId('tab-dados');
  }

  const botaoDaConta = () => screen.getByLabelText('Abrir a conta Metalurgica Alfa');

  async function abrirConta() {
    await abrirOportunidade();
    fireEvent.click(botaoDaConta());
    return screen.findByLabelText('Razão social');
  }

  it('o trilho tem a empresa como botão', async () => {
    await abrirOportunidade();
    expect(botaoDaConta()).toBeInTheDocument();
  });

  it('clicar abre a visão 360 da conta, editável', async () => {
    /* Editável é o ponto: o drilldown é a MESMA tela de Contas, não uma
       cópia só-leitura que envelheceria em paralelo. */
    const razao = await abrirConta();
    expect(razao.value).toBe('Metalurgica Alfa LTDA');
    expect(razao).not.toBeDisabled();
    expect(mockGet.mock.calls.some(([u]) => u === '/crm/contas/c1')).toBe(true);
  });

  it('a oportunidade continua aberta atrás', async () => {
    /* Empilhar em vez de navegar é o que preserva o que já estava aqui. */
    await abrirConta();
    expect(screen.getByTestId('tab-dados')).toBeInTheDocument();
  });

  it('fechar o drilldown devolve a oportunidade intacta', async () => {
    await abrirConta();
    fireEvent.click(screen.getByText('Voltar à oportunidade'));
    await waitFor(() =>
      expect(screen.queryByLabelText('Razão social')).not.toBeInTheDocument()
    );
    expect(screen.getByTestId('tab-dados')).toBeInTheDocument();
    expect(screen.getByLabelText('Fase')).toBeInTheDocument();
  });

  it('a edição da oportunidade sobrevive ao drilldown', async () => {
    /*
      O motivo de empilhar em vez de navegar. Com rota nova, o modal
      desmontaria e o que estava digitado ia junto — sem aviso nenhum.
    */
    await abrirOportunidade();
    fireEvent.change(screen.getByLabelText('Descrição'), {
      target: { value: 'Renovacao anual' },
    });

    fireEvent.click(botaoDaConta());
    await screen.findByLabelText('Razão social');
    fireEvent.click(screen.getByText('Voltar à oportunidade'));

    await waitFor(() =>
      expect(screen.getByLabelText('Descrição').value).toBe('Renovacao anual')
    );
  });

  it('as verticais são buscadas só quando o drilldown abre', async () => {
    /* O funil não usa vertical para nada: buscar na montagem seria custo
       fixo para um caminho que nem todo mundo percorre. */
    await abrirOportunidade();
    const antes = mockGet.mock.calls.filter(([u]) => u === '/crm/dominio/verticais');
    expect(antes).toHaveLength(0);

    fireEvent.click(botaoDaConta());
    await screen.findByLabelText('Razão social');
    expect(mockGet.mock.calls.some(([u]) => u === '/crm/dominio/verticais')).toBe(true);
  });

  it('salvar a conta recarrega o funil e a oportunidade', async () => {
    /*
      A razão social aparece no cartão do funil e no título do modal da
      oportunidade. Sem recarregar as duas, renomear a empresa mostra o nome
      antigo ao fechar — e parece que não salvou.
    */
    await abrirConta();
    mockPatch.mockResolvedValue({ data: { ...CONTA, razao_social: 'Alfa Metais LTDA' } });

    fireEvent.change(screen.getByLabelText('Razão social'), {
      target: { value: 'Alfa Metais LTDA' },
    });
    // Escopado: com os dois modais no DOM há dois botões "Salvar".
    const barraDaConta = within(screen.getByLabelText('Ações da conta'));
    fireEvent.click(barraDaConta.getByText('Salvar'));

    await waitFor(() => expect(mockPatch).toHaveBeenCalled());
    expect(mockPatch.mock.calls[0][0]).toBe('/crm/contas/c1');
    await waitFor(() => {
      const kanban = mockGet.mock.calls.filter(([u]) => u === '/crm/oportunidades/kanban');
      expect(kanban.length).toBeGreaterThan(1);
    });
    expect(mockGet.mock.calls.filter(([u]) => u === '/crm/oportunidades/o1').length)
      .toBeGreaterThan(1);
  });

  it('erro ao abrir a conta aparece e não derruba a oportunidade', async () => {
    await abrirOportunidade();
    mockGet.mockImplementation((url) => {
      if (url === '/crm/contas/c1') {
        return Promise.reject({ response: { data: { detail: 'Conta sumiu' } } });
      }
      return respostasComConta(url);
    });

    fireEvent.click(botaoDaConta());
    expect(await screen.findByText('Conta sumiu')).toBeInTheDocument();
    expect(screen.getByTestId('tab-dados')).toBeInTheDocument();
  });
});

describe('Oportunidades — erro de carga', () => {
  it('mostra a mensagem da API', async () => {
    mockGet.mockImplementation((url) => {
      if (url === '/crm/oportunidades/resumo') {
        return Promise.reject({ response: { data: { detail: 'Boom' } } });
      }
      return respostas(null)(url);
    });
    montar();
    expect(await screen.findByText('Boom')).toBeInTheDocument();
  });
});
