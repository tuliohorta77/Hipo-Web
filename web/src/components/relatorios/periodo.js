// web/src/components/relatorios/periodo.js
//
// Período dos relatórios: presets relativos ("Este mês") viram datas aqui,
// na tela, no fuso de quem abre. A API só recebe datas.
//
// Por que relativo é o padrão de um relatório salvo: "Funil deste mês" salvo
// em setembro tem que mostrar outubro quando aberto em outubro. Período fixo
// existe para fechamento que não muda ("1º semestre de 2026").
//
// `hoje` entra por parâmetro — mesma disciplina do backend (hoje: date |
// None): teste determinístico sem mockar o relógio.
//
// A lista de chaves tem que bater com PRESETS_PERIODO em
// api/services/relatorios.py. A API recusa relatório salvo com preset que
// ela não conhece.

export const PRESETS = [
  { chave: 'hoje', rotulo: 'Hoje' },
  { chave: 'ontem', rotulo: 'Ontem' },
  { chave: 'ultimos_7', rotulo: 'Últimos 7 dias' },
  { chave: 'ultimos_30', rotulo: 'Últimos 30 dias' },
  { chave: 'ultimos_90', rotulo: 'Últimos 90 dias' },
  { chave: 'semana_atual', rotulo: 'Esta semana' },
  { chave: 'mes_atual', rotulo: 'Este mês' },
  { chave: 'mes_anterior', rotulo: 'Mês passado' },
  { chave: 'trimestre_atual', rotulo: 'Este trimestre' },
  { chave: 'ano_atual', rotulo: 'Este ano' },
  { chave: 'ano_anterior', rotulo: 'Ano passado' },
  { chave: 'ultimos_12_meses', rotulo: 'Últimos 12 meses' },
];

export const PRESET_PADRAO = 'mes_atual';

function dia(ano, mes, d) {
  return new Date(ano, mes, d);
}

function somarDias(data, n) {
  return dia(data.getFullYear(), data.getMonth(), data.getDate() + n);
}

/** Date local -> 'AAAA-MM-DD' (sem passar por UTC, que muda o dia à noite). */
export function paraIsoData(data) {
  const a = data.getFullYear();
  const m = String(data.getMonth() + 1).padStart(2, '0');
  const d = String(data.getDate()).padStart(2, '0');
  return `${a}-${m}-${d}`;
}

/** 'AAAA-MM-DD' -> Date local à meia-noite. */
export function deIsoData(iso) {
  const [a, m, d] = String(iso).split('-').map(Number);
  return dia(a, m - 1, d);
}

/**
 * Datas de um preset.
 * @returns {{inicio: string, fim: string}} em 'AAAA-MM-DD'
 */
export function datasDoPreset(chave, hoje = new Date()) {
  const h = dia(hoje.getFullYear(), hoje.getMonth(), hoje.getDate());
  const a = h.getFullYear();
  const m = h.getMonth();
  let inicio;
  let fim = h;
  switch (chave) {
    case 'hoje':
      inicio = h;
      break;
    case 'ontem':
      inicio = somarDias(h, -1);
      fim = inicio;
      break;
    case 'ultimos_7':
      inicio = somarDias(h, -6);
      break;
    case 'ultimos_30':
      inicio = somarDias(h, -29);
      break;
    case 'ultimos_90':
      inicio = somarDias(h, -89);
      break;
    case 'semana_atual': {
      // Semana começa na segunda (getDay: 0 = domingo).
      const desloc = (h.getDay() + 6) % 7;
      inicio = somarDias(h, -desloc);
      fim = somarDias(inicio, 6);
      break;
    }
    case 'mes_atual':
      inicio = dia(a, m, 1);
      fim = dia(a, m + 1, 0);
      break;
    case 'mes_anterior':
      inicio = dia(a, m - 1, 1);
      fim = dia(a, m, 0);
      break;
    case 'trimestre_atual': {
      const t = Math.floor(m / 3) * 3;
      inicio = dia(a, t, 1);
      fim = dia(a, t + 3, 0);
      break;
    }
    case 'ano_atual':
      inicio = dia(a, 0, 1);
      fim = dia(a, 11, 31);
      break;
    case 'ano_anterior':
      inicio = dia(a - 1, 0, 1);
      fim = dia(a - 1, 11, 31);
      break;
    case 'ultimos_12_meses':
      inicio = dia(a, m - 11, 1);
      fim = dia(a, m + 1, 0);
      break;
    default:
      throw new Error(`Período desconhecido: ${chave}`);
  }
  return { inicio: paraIsoData(inicio), fim: paraIsoData(fim) };
}

/**
 * Período da configuração -> datas para a API.
 * @param {{tipo: 'relativo'|'fixo', preset?: string, inicio?: string, fim?: string}} periodo
 */
export function resolverPeriodo(periodo, hoje = new Date()) {
  if (!periodo) return null;
  if (periodo.tipo === 'relativo') return datasDoPreset(periodo.preset, hoje);
  if (periodo.tipo === 'fixo' && periodo.inicio && periodo.fim) {
    return { inicio: periodo.inicio, fim: periodo.fim };
  }
  return null;
}

export function rotuloPreset(chave) {
  return PRESETS.find((p) => p.chave === chave)?.rotulo || chave;
}

/** '2026-09-01' -> '01/09/2026' */
export function dataBr(iso) {
  if (!iso) return '';
  const [a, m, d] = String(iso).slice(0, 10).split('-');
  return `${d}/${m}/${a}`;
}

/** Texto curto do período, para cabeçalho e lista de salvos. */
export function descreverPeriodo(periodo, hoje = new Date()) {
  const datas = resolverPeriodo(periodo, hoje);
  if (!datas) return 'Período não definido';
  const faixa = datas.inicio === datas.fim
    ? dataBr(datas.inicio)
    : `${dataBr(datas.inicio)} a ${dataBr(datas.fim)}`;
  return periodo.tipo === 'relativo' ? `${rotuloPreset(periodo.preset)} (${faixa})` : faixa;
}
