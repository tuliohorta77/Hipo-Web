// web/src/tests/Oportunidades.test.jsx
//
// A página do funil: duas visões da mesma lista, com a preferência gravada no
// banco (não no localStorage), e KPIs que aplicam filtro.
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
  por_fase: [], perda_por_fase: [],
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

  function respostasComDetalhe(url) {
    if (url === '/crm/oportunidades/o1') return Promise.resolve({ data: DETALHE });
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

  it('a aba Proposta avisa que as versões ainda não existem', async () => {
    await abrir();
    fireEvent.click(screen.getByTestId('tab-proposta'));
    expect(await screen.findByText(/Versões da proposta ainda não implementadas/))
      .toBeInTheDocument();
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
