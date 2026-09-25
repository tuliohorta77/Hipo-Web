// web/src/tests/RelatoriosConstrutor.test.jsx
//
// O construtor da tabela dinâmica: as operações sobre a configuração
// (mover, inverter, remover) e o editor de filtro, que é o autofiltro do
// Excel — lista de valores vinda do banco, "(em branco)" incluso.
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, fireEvent, cleanup, waitFor } from '@testing-library/react';

const mockPost = vi.fn();
vi.mock('../api', () => ({ default: { post: (...a) => mockPost(...a) } }));

// eslint-disable-next-line import/first
import {
  moverCampo, inverterEixos, removerDaZona, adicionarNaZona,
} from '../components/relatorios/Construtor';
// eslint-disable-next-line import/first
import FiltroCampo, { resumoFiltro, operadoresDoTipo } from '../components/relatorios/FiltroCampo';

const BASE = {
  linhas: [{ campo: 'fase' }, { campo: 'ev' }],
  colunas: [{ campo: 'mes' }],
  valores: [],
  filtros: [],
};

describe('operações do construtor', () => {
  it('move de linhas para colunas no fim', () => {
    const c = moverCampo(BASE, 'linhas', 0, 'colunas');
    expect(c.linhas).toEqual([{ campo: 'ev' }]);
    expect(c.colunas).toEqual([{ campo: 'mes' }, { campo: 'fase' }]);
  });

  it('move para uma posição', () => {
    const c = moverCampo(BASE, 'colunas', 0, 'linhas', 1);
    expect(c.linhas.map((x) => x.campo)).toEqual(['fase', 'mes', 'ev']);
    expect(c.colunas).toEqual([]);
  });

  it('reordena dentro da mesma zona', () => {
    const c = moverCampo(BASE, 'linhas', 1, 'linhas', 0);
    expect(c.linhas.map((x) => x.campo)).toEqual(['ev', 'fase']);
  });

  it('inverte linhas e colunas', () => {
    const c = inverterEixos(BASE);
    expect(c.linhas).toEqual(BASE.colunas);
    expect(c.colunas).toEqual(BASE.linhas);
  });

  it('remove pelo índice', () => {
    expect(removerDaZona(BASE, 'linhas', 0).linhas).toEqual([{ campo: 'ev' }]);
  });

  it('data entra com mês; contagem de registros com "contagem"', () => {
    const fonte = { campos: [{ chave: 'data_criacao', tipo: 'data', agregacoes: ['contagem_distinta'] }] };
    expect(adicionarNaZona(BASE, 'colunas', 'data_criacao', fonte).colunas.at(-1))
      .toEqual({ campo: 'data_criacao', granularidade: 'mes' });
    expect(adicionarNaZona(BASE, 'valores', '*', fonte).valores).toEqual([{ campo: '*', agregacao: 'contagem' }]);
  });
});

describe('resumo e operadores do filtro', () => {
  const FASE = { chave: 'fase', tipo: 'texto', valores: [{ valor: 'lead', rotulo: 'Lead' }] };

  it('lista curta aparece inteira; longa, resumida', () => {
    expect(resumoFiltro({ operador: 'em', valores: ['lead', null] }, FASE)).toBe('Lead, (em branco)');
    expect(resumoFiltro({ operador: 'nao_em', valores: ['a', 'b', 'c', 'd'] }, FASE)).toBe('exceto a, b +2');
  });

  it('faixa de data', () => {
    const data = { chave: 'd', tipo: 'data', valores: [] };
    expect(resumoFiltro({ operador: 'entre', minimo: '2026-09-01', maximo: '2026-09-30' }, data))
      .toBe('01/09/2026 a 30/09/2026');
  });

  it('operadores por tipo', () => {
    expect(operadoresDoTipo('texto')).toEqual(['em', 'nao_em', 'contem']);
    expect(operadoresDoTipo('booleano')).toEqual(['em']);
    expect(operadoresDoTipo('data')[0]).toBe('entre');
  });
});

describe('editor de filtro', () => {
  const CAMPO = { chave: 'origem', rotulo: 'Origem do lead', tipo: 'texto', valores: [], ajuda: '' };
  const BASE_CONSULTA = { fonte: 'oportunidades', periodo: { data_ref: 'x', inicio: '2026-09-01', fim: '2026-09-30' } };

  beforeEach(() => {
    mockPost.mockResolvedValue({
      data: { itens: [{ valor: 'Site', n: 4 }, { valor: null, n: 2 }], truncado: false },
    });
  });
  afterEach(() => { cleanup(); vi.clearAllMocks(); });

  function abrir(props = {}) {
    const onSalvar = vi.fn();
    render(
      <FiltroCampo
        aberto
        campo={CAMPO}
        filtroInicial={null}
        consultaBase={BASE_CONSULTA}
        operadores={{ em: 'é um destes', nao_em: 'não é nenhum destes', contem: 'contém o texto' }}
        granularidades={{ mes: 'Mês' }}
        onSalvar={onSalvar}
        onFechar={() => {}}
        {...props}
      />,
    );
    return onSalvar;
  }

  it('busca os valores do campo no período, com contagem e em branco', async () => {
    abrir();
    expect(await screen.findByText('Site')).toBeInTheDocument();
    expect(screen.getByText('(em branco)')).toBeInTheDocument();
    expect(mockPost).toHaveBeenCalledWith('/crm/relatorios/valores', expect.objectContaining({
      campo: 'origem', fonte: 'oportunidades',
    }));
  });

  it('aplica os marcados, com (em branco) como null', async () => {
    const onSalvar = abrir();
    await screen.findByText('Site');
    fireEvent.click(screen.getByText('Marcar todos'));
    fireEvent.click(screen.getByText('Aplicar filtro'));
    expect(onSalvar).toHaveBeenCalledWith({ campo: 'origem', operador: 'em', valores: ['Site', null] });
  });

  it('não aplica sem valor marcado', async () => {
    const onSalvar = abrir();
    await screen.findByText('Site');
    fireEvent.click(screen.getByText('Aplicar filtro'));
    expect(onSalvar).not.toHaveBeenCalled();
    expect(screen.getByText('Marque pelo menos um valor.')).toBeInTheDocument();
  });

  it('contém texto', async () => {
    const onSalvar = abrir();
    fireEvent.change(screen.getByLabelText('Condição'), { target: { value: 'contem' } });
    fireEvent.change(screen.getByLabelText('Texto do filtro'), { target: { value: ' indica ' } });
    fireEvent.click(screen.getByText('Aplicar filtro'));
    await waitFor(() => expect(onSalvar).toHaveBeenCalledWith({ campo: 'origem', operador: 'contem', texto: 'indica' }));
  });
});
