// web/src/tests/Relatorios.test.jsx
//
// A tela de Relatórios tem cinco promessas:
//   1. o período vem ANTES de tudo: sem fonte e período, não há consulta
//   2. a montagem vira o corpo certo para a API (e recalcula sozinha)
//   3. todo número leva aos registros que o compõem (drilldown)
//   4. salvar guarda a montagem com nome, no perfil
//   5. relatório de colega é só leitura: dá para duplicar, não para salvar por cima
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import {
  render, screen, fireEvent, cleanup, waitFor, within,
} from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';

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
  getUser: () => ({ id: 'u1', nome: 'Tulio', cargo: 'Franqueado' }),
}));

// eslint-disable-next-line import/first
import Relatorios, { normalizarConfig, corpoDaConsulta, novaConfig } from '../pages/crm/Relatorios';

const FASES = [{ valor: 'lead', rotulo: 'Lead' }, { valor: 'negociacao', rotulo: 'Negociação' }];

function campo(chave, rotulo, tipo, extra = {}) {
  const ags = { moeda: ['soma', 'media', 'minimo', 'maximo', 'contagem_distinta'], texto: ['contagem_distinta'], data: ['contagem_distinta'] };
  return {
    chave, rotulo, tipo, grupo: extra.grupo || 'Oportunidade', ajuda: '', valores: [],
    referencia: false, dimensao: true, agregacoes: ags[tipo] || [], ...extra,
  };
}

const CATALOGO = {
  fontes: [
    {
      chave: 'oportunidades',
      rotulo: 'Oportunidades',
      descricao: 'Cada linha é uma oportunidade.',
      rotulo_registro: 'oportunidades',
      data_padrao: 'data_criacao',
      colunas_registro: ['numero'],
      campos: [
        campo('fase', 'Fase', 'texto', { valores: FASES }),
        campo('ev', 'Executivo de vendas (EV)', 'texto', { grupo: 'Equipe' }),
        campo('mensalidade', 'Mensalidade (R$)', 'moeda', { grupo: 'Valores' }),
        campo('data_criacao', 'Data de criação', 'data', { grupo: 'Datas', referencia: true }),
        campo('data_desfecho', 'Data do desfecho (ganho/perda)', 'data', { grupo: 'Datas', referencia: true }),
      ],
    },
    {
      chave: 'tarefas',
      rotulo: 'Tarefas e atividades',
      descricao: 'Cada linha é uma tarefa.',
      rotulo_registro: 'tarefas',
      data_padrao: 'data_prazo',
      colunas_registro: ['titulo'],
      campos: [
        campo('titulo', 'Título da tarefa', 'texto'),
        campo('data_prazo', 'Prazo (data agendada)', 'data', { referencia: true }),
      ],
    },
  ],
  agregacoes: {
    contagem: 'Quantidade', soma: 'Soma', media: 'Média', minimo: 'Mínimo', maximo: 'Máximo',
    contagem_distinta: 'Qtd. distinta', percentual: '% com Sim',
  },
  granularidades: { dia: 'Dia', semana: 'Semana', mes: 'Mês', trimestre: 'Trimestre', ano: 'Ano' },
  operadores: { em: 'é um destes', nao_em: 'não é nenhum destes', entre: 'está entre', contem: 'contém o texto' },
  presets_periodo: {},
  limites: { linhas: 4, colunas: 2, valores: 6, filtros: 15, dias_periodo: 3700, combinacoes_coluna: 100 },
};

const PERIODO_RES = { data_ref: 'data_criacao', data_ref_rotulo: 'Data de criação', inicio: '2026-09-01', fim: '2026-09-30' };
const VALOR_CONTAGEM = { campo: '*', agregacao: 'contagem', rotulo: 'Quantidade de oportunidades', formato: 'inteiro' };

const RES_TOTAL = {
  fonte: 'oportunidades', periodo: PERIODO_RES, linhas: [], colunas: [],
  valores: [VALOR_CONTAGEM],
  celulas: [{ d: [], g: [], n: 3, v: [3] }],
  total_registros: 3,
};

const RES_POR_FASE = {
  ...RES_TOTAL,
  linhas: [{ campo: 'fase', granularidade: null, rotulo: 'Fase', tipo: 'texto', valores: FASES }],
  celulas: [
    { d: ['lead'], g: [false], n: 2, v: [2] },
    { d: ['negociacao'], g: [false], n: 1, v: [1] },
    { d: [null], g: [true], n: 3, v: [3] },
  ],
};

const SALVO_MEU = {
  id: 'r1', nome: 'Funil por fase', descricao: null, fonte: 'oportunidades', fonte_rotulo: 'Oportunidades',
  compartilhado: false, dono_id: 'u1', dono_nome: 'Tulio', eh_meu: true,
  criado_em: '2026-09-01T10:00:00Z', atualizado_em: '2026-09-01T10:00:00Z',
  config: {
    fonte: 'oportunidades',
    periodo: { tipo: 'relativo', preset: 'mes_atual', data_ref: 'data_criacao' },
    linhas: [{ campo: 'fase', granularidade: null }], colunas: [],
    valores: [{ campo: '*', agregacao: 'contagem' }], filtros: [],
    ordenacao: { por: 'rotulo', direcao: 'asc' }, destacar: true,
  },
};

const SALVO_DO_COLEGA = {
  ...SALVO_MEU, id: 'r2', nome: 'Ranking de EVs', eh_meu: false, compartilhado: true,
  dono_id: 'u2', dono_nome: 'Ana',
};

let salvos;

function configurarApi() {
  mockGet.mockImplementation((url) => {
    if (url === '/crm/relatorios/catalogo') return Promise.resolve({ data: CATALOGO });
    if (url === '/crm/relatorios/salvos') return Promise.resolve({ data: salvos });
    return Promise.reject(new Error(`GET inesperado ${url}`));
  });
  mockPost.mockImplementation((url, corpo) => {
    if (url === '/crm/relatorios/consulta') {
      return Promise.resolve({ data: corpo.linhas.length ? RES_POR_FASE : RES_TOTAL });
    }
    if (url === '/crm/relatorios/registros') {
      return Promise.resolve({
        data: {
          colunas: [{ campo: 'numero', rotulo: 'Número da oportunidade', tipo: 'texto', valores: [] }],
          total: 2,
          itens: [
            { valores: ['OPP-2026-00001'], abrir: { tipo: 'oportunidade', id: 'o1' } },
            { valores: ['OPP-2026-00003'], abrir: { tipo: 'oportunidade', id: 'o3' } },
          ],
        },
      });
    }
    if (url === '/crm/relatorios/salvos') {
      return Promise.resolve({ data: { ...SALVO_MEU, id: 'novo', nome: corpo.nome, config: corpo.config } });
    }
    if (url.endsWith('/duplicar')) {
      return Promise.resolve({ data: { ...SALVO_DO_COLEGA, id: 'copia', nome: 'Ranking de EVs (cópia)', eh_meu: true, compartilhado: false } });
    }
    return Promise.reject(new Error(`POST inesperado ${url}`));
  });
}

function renderTela(rota = '/crm/relatorios') {
  return render(
    <MemoryRouter initialEntries={[rota]}>
      <Relatorios />
    </MemoryRouter>,
  );
}

async function montarBasico() {
  renderTela();
  fireEvent.click(await screen.findByRole('button', { name: /Montar relatório/ }));
  await screen.findByTestId('tabela-dinamica');
}

beforeEach(() => {
  vi.clearAllMocks();
  salvos = [];
  configurarApi();
});

afterEach(cleanup);

describe('Relatórios — início', () => {
  it('pede fonte e período antes de qualquer consulta', async () => {
    renderTela();
    expect(await screen.findByText('1. O que você quer analisar?')).toBeInTheDocument();
    expect(screen.getByRole('radio', { name: /Oportunidades/ })).toHaveAttribute('aria-checked', 'true');
    expect(screen.getByLabelText('Período pela data de')).toHaveValue('data_criacao');
    expect(mockPost).not.toHaveBeenCalled();
  });

  it('trocar a fonte troca a data de referência para a padrão dela', async () => {
    renderTela();
    fireEvent.click(await screen.findByRole('radio', { name: /Tarefas/ }));
    expect(screen.getByLabelText('Período pela data de')).toHaveValue('data_prazo');
  });

  it('período personalizado invertido bloqueia o botão', async () => {
    renderTela();
    await screen.findByText('1. O que você quer analisar?');
    fireEvent.change(screen.getByLabelText('Período'), { target: { value: 'personalizado' } });
    fireEvent.change(screen.getByLabelText('Data inicial'), { target: { value: '2026-09-30' } });
    fireEvent.change(screen.getByLabelText('Data final'), { target: { value: '2026-09-01' } });
    expect(screen.getByRole('button', { name: /Montar relatório/ })).toBeDisabled();
  });
});

describe('Relatórios — montagem e consulta', () => {
  it('consulta com o período resolvido e a contagem padrão', async () => {
    await montarBasico();
    const [url, corpo] = mockPost.mock.calls.find(([u]) => u === '/crm/relatorios/consulta');
    expect(url).toBe('/crm/relatorios/consulta');
    expect(corpo.fonte).toBe('oportunidades');
    expect(corpo.periodo.data_ref).toBe('data_criacao');
    expect(corpo.periodo.inicio).toMatch(/^\d{4}-\d{2}-01$/);
    expect(corpo.valores).toEqual([{ campo: '*', agregacao: 'contagem' }]);
    expect(screen.getByRole('button', { name: /^Quantidade de oportunidades/ })).toHaveTextContent('3');
  });

  it('adicionar Fase nas linhas recalcula e desenha uma linha por fase', async () => {
    await montarBasico();
    fireEvent.click(screen.getByRole('button', { name: 'Adicionar em Linhas' }));
    fireEvent.click(await screen.findByRole('button', { name: /^Fase$/ }));
    await waitFor(() => {
      const ult = mockPost.mock.calls.filter(([u]) => u === '/crm/relatorios/consulta').at(-1);
      expect(ult[1].linhas).toEqual([{ campo: 'fase', granularidade: null }]);
    });
    const tabela = await screen.findByTestId('tabela-dinamica');
    await within(tabela).findByText('Lead');
    expect(within(tabela).getByText('Negociação')).toBeInTheDocument();
    expect(within(tabela).getByText('Total geral')).toBeInTheDocument();
  });

  it('campo de data entra agrupado por mês', async () => {
    await montarBasico();
    fireEvent.click(screen.getByRole('button', { name: 'Adicionar em Colunas' }));
    fireEvent.click(await screen.findByRole('button', { name: /Data de criação/ }));
    await waitFor(() => {
      const ult = mockPost.mock.calls.filter(([u]) => u === '/crm/relatorios/consulta').at(-1);
      expect(ult[1].colunas).toEqual([{ campo: 'data_criacao', granularidade: 'mes' }]);
    });
    expect(screen.getByLabelText('Agrupar Data de criação por')).toHaveValue('mes');
  });

  it('mover de linhas para colunas pelo botão', async () => {
    await montarBasico();
    fireEvent.click(screen.getByRole('button', { name: 'Adicionar em Linhas' }));
    fireEvent.click(await screen.findByRole('button', { name: /^Fase$/ }));
    fireEvent.click(await screen.findByRole('button', { name: 'Mover Fase para Colunas' }));
    await waitFor(() => {
      const ult = mockPost.mock.calls.filter(([u]) => u === '/crm/relatorios/consulta').at(-1);
      expect(ult[1].linhas).toEqual([]);
      expect(ult[1].colunas).toEqual([{ campo: 'fase', granularidade: null }]);
    });
  });

  it('valor de soma usa a primeira agregação do campo', async () => {
    await montarBasico();
    fireEvent.click(screen.getByRole('button', { name: 'Adicionar em Valores' }));
    fireEvent.click(await screen.findByRole('button', { name: /Mensalidade/ }));
    await waitFor(() => {
      const ult = mockPost.mock.calls.filter(([u]) => u === '/crm/relatorios/consulta').at(-1);
      expect(ult[1].valores).toEqual([
        { campo: '*', agregacao: 'contagem' },
        { campo: 'mensalidade', agregacao: 'soma' },
      ]);
    });
  });

  it('erro da API aparece em português', async () => {
    mockPost.mockImplementation((url) => (url === '/crm/relatorios/consulta'
      ? Promise.reject({ response: { data: { detail: 'A tabela teria 140 colunas.' } } })
      : Promise.resolve({ data: {} })));
    renderTela();
    fireEvent.click(await screen.findByRole('button', { name: /Montar relatório/ }));
    expect(await screen.findByText('A tabela teria 140 colunas.')).toBeInTheDocument();
  });
});

describe('Relatórios — drilldown', () => {
  it('clicar no número abre os registros daquela célula', async () => {
    const abrir = vi.spyOn(window, 'open').mockImplementation(() => null);
    await montarBasico();
    fireEvent.click(screen.getByRole('button', { name: 'Adicionar em Linhas' }));
    fireEvent.click(await screen.findByRole('button', { name: /^Fase$/ }));
    const tabela = await screen.findByTestId('tabela-dinamica');
    await within(tabela).findByText('Lead');
    fireEvent.click(within(tabela).getAllByTitle(/clique para ver/)[0]);

    await waitFor(() => {
      const chamada = mockPost.mock.calls.find(([u]) => u === '/crm/relatorios/registros');
      expect(chamada[1].celula).toEqual([{ campo: 'fase', granularidade: null, valor: 'lead' }]);
    });
    expect(await screen.findByText('OPP-2026-00001')).toBeInTheDocument();
    expect(screen.getByText(/Registros — Fase: Lead/)).toBeInTheDocument();

    fireEvent.click(screen.getByText('OPP-2026-00003'));
    expect(abrir).toHaveBeenCalledWith('/crm/oportunidades?abrir=o3', '_blank', 'noopener');
    abrir.mockRestore();
  });
});

describe('Relatórios — salvos', () => {
  it('salvar pede nome e manda a montagem', async () => {
    await montarBasico();
    fireEvent.click(screen.getByRole('button', { name: /^Salvar$/ }));
    fireEvent.change(await screen.findByLabelText('Nome do relatório'), { target: { value: 'Meu funil' } });
    fireEvent.click(screen.getByLabelText(/Compartilhar com a equipe/));
    expect(screen.getByText(/Período salvo como "Este mês"/)).toBeInTheDocument();
    fireEvent.click(within(screen.getByRole('dialog')).getByRole('button', { name: 'Salvar' }));

    await waitFor(() => {
      const chamada = mockPost.mock.calls.find(([u]) => u === '/crm/relatorios/salvos');
      expect(chamada[1].nome).toBe('Meu funil');
      expect(chamada[1].compartilhado).toBe(true);
      expect(chamada[1].config.periodo).toEqual({ tipo: 'relativo', preset: 'mes_atual', data_ref: 'data_criacao' });
    });
    expect(await screen.findByRole('heading', { name: 'Meu funil' })).toBeInTheDocument();
  });

  it('abre o relatório salvo pela lista e recalcula', async () => {
    salvos = [SALVO_MEU];
    renderTela();
    fireEvent.click(await screen.findByRole('button', { name: /Funil por fase/ }));
    expect(await screen.findByRole('heading', { name: 'Funil por fase' })).toBeInTheDocument();
    await waitFor(() => {
      const ult = mockPost.mock.calls.filter(([u]) => u === '/crm/relatorios/consulta').at(-1);
      expect(ult[1].linhas).toEqual([{ campo: 'fase', granularidade: null }]);
    });
    // Sem alteração, Salvar fica desabilitado; mexer marca como não salvo.
    expect(screen.getByRole('button', { name: /^Salvar$/ })).toBeDisabled();
    fireEvent.click(screen.getByRole('button', { name: 'Remover Fase de Linhas' }));
    expect(await screen.findByText('Alterações não salvas')).toBeInTheDocument();
  });

  it('salvar relatório próprio grava por cima (PUT)', async () => {
    salvos = [SALVO_MEU];
    mockPut.mockResolvedValue({ data: { ...SALVO_MEU, config: { ...SALVO_MEU.config, linhas: [] } } });
    renderTela('/crm/relatorios?r=r1');
    expect(await screen.findByRole('heading', { name: 'Funil por fase' })).toBeInTheDocument();
    fireEvent.click(await screen.findByRole('button', { name: 'Remover Fase de Linhas' }));
    fireEvent.click(screen.getByRole('button', { name: /^Salvar$/ }));
    await waitFor(() => expect(mockPut).toHaveBeenCalled());
    const [url, corpo] = mockPut.mock.calls[0];
    expect(url).toBe('/crm/relatorios/salvos/r1');
    expect(corpo.nome).toBe('Funil por fase');
    expect(corpo.config.linhas).toEqual([]);
  });

  it('relatório de colega é só leitura e pode ser duplicado', async () => {
    salvos = [SALVO_MEU, SALVO_DO_COLEGA];
    renderTela('/crm/relatorios?r=r2');
    expect(await screen.findByRole('heading', { name: 'Ranking de EVs' })).toBeInTheDocument();
    expect(screen.getByText(/De Ana — só leitura/)).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Excluir relatório' })).not.toBeInTheDocument();
    expect(screen.getByRole('button', { name: /Salvar uma cópia/ })).toBeInTheDocument();

    salvos = [SALVO_MEU, SALVO_DO_COLEGA, { ...SALVO_DO_COLEGA, id: 'copia', nome: 'Ranking de EVs (cópia)', eh_meu: true, compartilhado: false }];
    fireEvent.click(screen.getByRole('button', { name: /Duplicar para mim/ }));
    await waitFor(() => expect(mockPost).toHaveBeenCalledWith('/crm/relatorios/salvos/r2/duplicar', {}));
    expect(await screen.findByRole('heading', { name: 'Ranking de EVs (cópia)' })).toBeInTheDocument();
  });

  it('lista separa os meus dos compartilhados', async () => {
    salvos = [SALVO_MEU, SALVO_DO_COLEGA];
    renderTela();
    const nav = await screen.findByRole('navigation', { name: 'Relatórios salvos' });
    await within(nav).findByText('Funil por fase');
    expect(within(nav).getByText('Compartilhados pela equipe')).toBeInTheDocument();
    expect(within(nav).getByText('por Ana')).toBeInTheDocument();
  });

  it('excluir pede confirmação', async () => {
    salvos = [SALVO_MEU];
    mockDelete.mockResolvedValue({});
    renderTela('/crm/relatorios?r=r1');
    await screen.findByRole('heading', { name: 'Funil por fase' });
    fireEvent.click(screen.getByRole('button', { name: 'Excluir relatório' }));
    fireEvent.click(within(screen.getByRole('dialog')).getByRole('button', { name: 'Excluir' }));
    await waitFor(() => expect(mockDelete).toHaveBeenCalledWith('/crm/relatorios/salvos/r1'));
  });
});

describe('Relatórios — funções puras da página', () => {
  const fonte = CATALOGO.fontes[0];

  it('campo que saiu do catálogo é retirado e avisado', () => {
    const { config, removidos } = normalizarConfig({
      ...SALVO_MEU.config,
      linhas: [{ campo: 'fase' }, { campo: 'sumiu' }],
      filtros: [{ campo: 'tambem_sumiu', operador: 'em', valores: ['x'] }],
    }, fonte);
    expect(config.linhas).toEqual([{ campo: 'fase' }]);
    expect(config.filtros).toEqual([]);
    expect(removidos).toEqual(['sumiu', 'tambem_sumiu']);
  });

  it('data de referência inválida volta para a padrão da fonte', () => {
    const { config } = normalizarConfig({ ...SALVO_MEU.config, periodo: { tipo: 'relativo', preset: 'hoje', data_ref: 'fase' } }, fonte);
    expect(config.periodo.data_ref).toBe('data_criacao');
  });

  it('período fixo invertido não vira consulta', () => {
    const cfg = novaConfig(fonte, { tipo: 'fixo', inicio: '2026-09-30', fim: '2026-09-01' });
    expect(corpoDaConsulta(cfg)).toBeNull();
  });

  it('corpo da consulta leva as datas resolvidas', () => {
    const cfg = novaConfig(fonte, { tipo: 'relativo', preset: 'ontem' });
    const corpo = corpoDaConsulta(cfg, new Date(2026, 8, 25));
    expect(corpo.periodo).toEqual({ data_ref: 'data_criacao', inicio: '2026-09-24', fim: '2026-09-24' });
  });
});
