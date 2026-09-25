// web/src/tests/relatoriosLogica.test.js
//
// Lógica pura do módulo de Relatórios: período e grade da tabela dinâmica.
//
// A grade NÃO soma nada — os totais vêm do banco. O que estes testes seguram
// é o POSICIONAMENTO: cada número vindo da API aparece na linha e na coluna
// certas, e o clique numa célula manda para o drilldown exatamente as
// dimensões daquela célula.
import { describe, it, expect } from 'vitest';
import {
  datasDoPreset, resolverPeriodo, descreverPeriodo, paraIsoData, PRESETS,
} from '../components/relatorios/periodo';
import {
  montarGrade, formatarDimensao, formatarMedida, comparadorDimensao,
  cabecalhosDeColuna, EM_BRANCO,
} from '../components/relatorios/pivot';

// Quinta, 25/09/2026.
const HOJE = new Date(2026, 8, 25, 15, 30);

describe('período', () => {
  it.each([
    ['hoje', '2026-09-25', '2026-09-25'],
    ['ontem', '2026-09-24', '2026-09-24'],
    ['ultimos_7', '2026-09-19', '2026-09-25'],
    ['ultimos_30', '2026-08-27', '2026-09-25'],
    ['semana_atual', '2026-09-21', '2026-09-27'],
    ['mes_atual', '2026-09-01', '2026-09-30'],
    ['mes_anterior', '2026-08-01', '2026-08-31'],
    ['trimestre_atual', '2026-07-01', '2026-09-30'],
    ['ano_atual', '2026-01-01', '2026-12-31'],
    ['ano_anterior', '2025-01-01', '2025-12-31'],
    ['ultimos_12_meses', '2025-10-01', '2026-09-30'],
  ])('%s', (preset, inicio, fim) => {
    expect(datasDoPreset(preset, HOJE)).toEqual({ inicio, fim });
  });

  it('mês anterior em janeiro volta para dezembro do ano anterior', () => {
    expect(datasDoPreset('mes_anterior', new Date(2027, 0, 10)))
      .toEqual({ inicio: '2026-12-01', fim: '2026-12-31' });
  });

  it('semana começa na segunda mesmo num domingo', () => {
    expect(datasDoPreset('semana_atual', new Date(2026, 8, 27)))
      .toEqual({ inicio: '2026-09-21', fim: '2026-09-27' });
  });

  it('todo preset resolve', () => {
    PRESETS.forEach((p) => expect(datasDoPreset(p.chave, HOJE).inicio).toMatch(/^\d{4}-\d{2}-\d{2}$/));
  });

  it('preset desconhecido é erro, não período vazio', () => {
    expect(() => datasDoPreset('semestre', HOJE)).toThrow();
  });

  it('fixo passa direto; incompleto é null', () => {
    expect(resolverPeriodo({ tipo: 'fixo', inicio: '2026-01-01', fim: '2026-06-30' }))
      .toEqual({ inicio: '2026-01-01', fim: '2026-06-30' });
    expect(resolverPeriodo({ tipo: 'fixo', inicio: '2026-01-01' })).toBeNull();
  });

  it('descrição legível', () => {
    expect(descreverPeriodo({ tipo: 'relativo', preset: 'mes_atual' }, HOJE))
      .toBe('Este mês (01/09/2026 a 30/09/2026)');
    expect(descreverPeriodo({ tipo: 'fixo', inicio: '2026-01-05', fim: '2026-01-05' }))
      .toBe('05/01/2026');
  });

  it('data ISO local não escorrega para UTC à noite', () => {
    expect(paraIsoData(new Date(2026, 8, 25, 23, 59))).toBe('2026-09-25');
  });
});

describe('formatação', () => {
  const FASE = { tipo: 'texto', valores: [{ valor: 'lead', rotulo: 'Lead' }] };

  it('vocabulário usa o rótulo', () => {
    expect(formatarDimensao('lead', FASE)).toBe('Lead');
  });

  it('nulo é (em branco)', () => {
    expect(formatarDimensao(null, FASE)).toBe(EM_BRANCO);
  });

  it('booleano vira Sim/Não', () => {
    expect(formatarDimensao('true', { tipo: 'booleano' })).toBe('Sim');
    expect(formatarDimensao('false', { tipo: 'booleano' })).toBe('Não');
  });

  it.each([
    ['mes', 'set/2026'],
    ['ano', '2026'],
    ['trimestre', '3º tri/2026'],
    ['dia', '01/09/2026'],
    ['semana', 'Sem. de 01/09/2026'],
  ])('data por %s', (granularidade, esperado) => {
    expect(formatarDimensao('2026-09-01', { tipo: 'data', granularidade })).toBe(esperado);
  });

  it('data com hora do drilldown', () => {
    expect(formatarDimensao('2026-09-01T14:05', { tipo: 'data' })).toBe('01/09/2026 14:05');
  });

  it('medidas', () => {
    expect(formatarMedida(1234.5, 'moeda')).toMatch(/1\.234,50/);
    expect(formatarMedida(45.25, 'percentual')).toBe('45,3%');
    expect(formatarMedida(3, 'inteiro')).toBe('3');
    expect(formatarMedida(null, 'moeda')).toBe('—');
  });

  it('ordem do funil, não alfabética; em branco por último', () => {
    const dim = {
      tipo: 'texto',
      valores: [{ valor: 'suspect' }, { valor: 'lead' }, { valor: 'negociacao' }],
    };
    const lista = ['negociacao', null, 'lead', 'suspect'].sort(comparadorDimensao(dim));
    expect(lista).toEqual(['suspect', 'lead', 'negociacao', null]);
  });

  it('número ordena como número', () => {
    expect(['10', '9', '100'].sort(comparadorDimensao({ tipo: 'numero' }))).toEqual(['9', '10', '100']);
  });
});

// ── Grade ────────────────────────────────────────────────────────────
//
// Fase (linha) × EV (coluna), soma da mensalidade. Células exatamente no
// formato do GROUPING SETS: detalhe, total da linha, total da coluna, geral.
function cel(d, g, v, n = 1) {
  return { d, g, v: [v], n };
}

const RES_LXC = {
  linhas: [{ campo: 'fase', tipo: 'texto', valores: [{ valor: 'lead' }, { valor: 'negociacao' }] }],
  colunas: [{ campo: 'ev', tipo: 'texto', valores: [] }],
  valores: [{ campo: 'mensalidade', agregacao: 'soma', formato: 'moeda' }],
  celulas: [
    cel(['negociacao', 'Ana'], [false, false], 300),
    cel(['lead', 'Ana'], [false, false], 100),
    cel(['lead', 'Beto'], [false, false], 200),
    cel(['lead', null], [false, true], 300, 2),
    cel(['negociacao', null], [false, true], 300),
    cel([null, 'Ana'], [true, false], 400, 2),
    cel([null, 'Beto'], [true, false], 200),
    cel([null, null], [true, true], 600, 3),
  ],
};

describe('grade da tabela dinâmica', () => {
  it('linhas na ordem do funil, colunas em ordem alfabética', () => {
    const g = montarGrade(RES_LXC);
    expect(g.colunas.map((c) => c.chave)).toEqual([['Ana'], ['Beto']]);
    expect(g.linhas.map((l) => l.tipo)).toEqual(['detalhe', 'detalhe', 'total']);
    expect(g.linhas[0].chave).toEqual(['lead']);
  });

  it('cada número na sua célula; célula vazia fica null', () => {
    const g = montarGrade(RES_LXC);
    const [lead, neg, total] = g.linhas;
    expect(lead.celulas.map((c) => c.v[0])).toEqual([100, 200]);
    expect(lead.total.v).toEqual([300]);
    expect(neg.celulas.map((c) => c.v[0])).toEqual([300, null]);
    expect(total.celulas.map((c) => c.v[0])).toEqual([400, 200]);
    expect(total.total.v).toEqual([600]);
  });

  it('o clique leva as dimensões da célula para o drilldown', () => {
    const g = montarGrade(RES_LXC);
    expect(g.linhas[0].celulas[1].celula).toEqual([
      { campo: 'fase', granularidade: null, valor: 'lead' },
      { campo: 'ev', granularidade: null, valor: 'Beto' },
    ]);
    expect(g.linhas[2].total.celula).toEqual([]);
    expect(g.linhas[2].celulas[0].celula).toEqual([{ campo: 'ev', granularidade: null, valor: 'Ana' }]);
  });

  it('ordenar por valor, decrescente', () => {
    const res = {
      ...RES_LXC,
      celulas: RES_LXC.celulas.map((c) => (c.d[0] === 'negociacao' && c.g[1] ? { ...c, v: [900] } : c)),
    };
    const g = montarGrade(res, { por: 'valor', direcao: 'desc' });
    expect(g.linhas[0].chave).toEqual(['negociacao']);
  });

  it('máximo por medida só olha detalhe', () => {
    expect(montarGrade(RES_LXC).maximos).toEqual([300]);
  });

  it('dois níveis de linha geram subtotal depois do grupo e suprimem rótulo repetido', () => {
    const res = {
      linhas: [
        { campo: 'fase', tipo: 'texto', valores: [] },
        { campo: 'ev', tipo: 'texto', valores: [] },
      ],
      colunas: [],
      valores: [{ campo: '*', agregacao: 'contagem', formato: 'inteiro' }],
      celulas: [
        cel([null, null], [true, true], 3, 3),
        cel(['lead', null], [false, true], 2, 2),
        cel(['lead', 'Ana'], [false, false], 1),
        cel(['lead', 'Beto'], [false, false], 1),
        cel(['neg', null], [false, true], 1),
        cel(['neg', 'Ana'], [false, false], 1),
      ],
    };
    const g = montarGrade(res);
    expect(g.linhas.map((l) => [l.tipo, l.chave.join('/')])).toEqual([
      ['detalhe', 'lead/Ana'],
      ['detalhe', 'lead/Beto'],
      ['subtotal', 'lead'],
      ['detalhe', 'neg/Ana'],
      ['subtotal', 'neg'],
      ['total', ''],
    ]);
    expect(g.linhas[0].mostrar).toEqual([true, true]);
    expect(g.linhas[1].mostrar).toEqual([false, true]);
    expect(g.linhas[3].mostrar).toEqual([true, true]);
    expect(g.linhas[2].total.v).toEqual([2]);
    expect(g.colunas).toEqual([]);
  });

  it('sem campo nenhum: só a linha de total', () => {
    const g = montarGrade({
      linhas: [], colunas: [], valores: [{ formato: 'inteiro' }],
      celulas: [{ d: [], g: [], n: 5, v: [5] }],
    });
    expect(g.linhas).toHaveLength(1);
    expect(g.linhas[0].total.v).toEqual([5]);
  });

  it('cabeçalhos agrupados por prefixo', () => {
    const cols = [{ chave: ['2026', 'Ana'] }, { chave: ['2026', 'Beto'] }, { chave: ['2027', 'Ana'] }];
    const f = cabecalhosDeColuna(cols, 2);
    expect(f[0].map((x) => [x.valor, x.span])).toEqual([['2026', 2], ['2027', 1]]);
    expect(f[1].map((x) => x.span)).toEqual([1, 1, 1]);
  });
});
