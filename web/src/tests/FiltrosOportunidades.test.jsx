// web/src/tests/FiltrosOportunidades.test.jsx
//
// As funções puras do painel de filtros do funil: o que vira parâmetro de
// query, o número do selo e os períodos rápidos.
import { describe, it, expect } from 'vitest';
import {
  FILTROS_PADRAO, paramsDosFiltros, contarFiltros, periodoRapido,
} from '../components/crm/FiltrosOportunidades';

describe('paramsDosFiltros', () => {
  it('sem filtro nenhum não manda parâmetro nenhum', () => {
    expect(paramsDosFiltros(FILTROS_PADRAO)).toEqual({});
  });

  it('a data de referência só vai junto de uma data', () => {
    /*
      `data_campo` sozinho não filtra nada, e mandá-lo mudaria os params por
      identidade — refetch à toa.
    */
    expect(paramsDosFiltros({ ...FILTROS_PADRAO, data_campo: 'desfecho' })).toEqual({});
    expect(paramsDosFiltros({ ...FILTROS_PADRAO, data_campo: 'desfecho', data_ate: '2026-09-30' }))
      .toEqual({ data_campo: 'desfecho', data_ate: '2026-09-30' });
  });

  it('números viram número e zero é filtro de verdade', () => {
    expect(paramsDosFiltros({ ...FILTROS_PADRAO, temperatura_min: '0', valor_max: '1500.5' }))
      .toEqual({ temperatura_min: 0, valor_max: 1500.5 });
  });

  it('parceiro vira booleano', () => {
    expect(paramsDosFiltros({ ...FILTROS_PADRAO, veio_de_parceiro: 'nao' }))
      .toEqual({ veio_de_parceiro: false });
  });
});

describe('contarFiltros', () => {
  it('conta grupos, não campos', () => {
    expect(contarFiltros({
      ...FILTROS_PADRAO,
      status: ['perdido', 'cancelado'],
      temperatura_min: '10', temperatura_max: '50',
      envolvido_id: 'u1', papel: 'EV',
    })).toBe(3);
  });
});

describe('periodoRapido', () => {
  const hoje = new Date(2026, 8, 30, 22, 0);   // 30/09/2026, 22h local

  it('este mês vai do dia 1 ao último dia', () => {
    expect(periodoRapido('este_mes', hoje)).toEqual(['2026-09-01', '2026-09-30']);
  });

  it('mês passado atravessa a virada do ano', () => {
    expect(periodoRapido('mes_passado', new Date(2026, 0, 15)))
      .toEqual(['2025-12-01', '2025-12-31']);
  });

  it('últimos 30 dias incluem hoje, na data local', () => {
    expect(periodoRapido('ultimos_30', hoje)).toEqual(['2026-09-01', '2026-09-30']);
  });
});
