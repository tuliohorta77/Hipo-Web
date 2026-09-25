// web/src/components/relatorios/pivot.js
//
// Monta a GRADE da tabela dinâmica a partir das células que a API devolve.
// Funções puras: nada de React, nada de rede.
//
// ── O que a API entrega ──────────────────────────────────────────────
// Uma lista de células vinda de um GROUPING SETS. Cada célula tem:
//   d: valores das dimensões (linhas primeiro, depois colunas), em TEXTO
//   g: para cada dimensão, true quando ela foi "somada" (subtotal/total)
//   n: quantos registros compõem a célula
//   v: os valores das medidas, na ordem pedida
//
// Os totais e subtotais JÁ VÊM CALCULADOS do banco. Esta camada não soma
// nada: somar aqui daria subtotal errado para média e contagem distinta
// (média de médias não é média). Ela só posiciona.
//
// ── A grade ──────────────────────────────────────────────────────────
// Formato "tabular" do Excel: uma coluna de rótulo por campo de linha, o
// rótulo repetido suprimido, e uma linha "Total de X" depois de cada grupo
// quando há mais de um nível. Colunas: uma por combinação dos campos de
// coluna × medida, mais o bloco "Total" no fim.

export const EM_BRANCO = '(em branco)';

const MESES = ['jan', 'fev', 'mar', 'abr', 'mai', 'jun', 'jul', 'ago', 'set', 'out', 'nov', 'dez'];

const moeda = new Intl.NumberFormat('pt-BR', { style: 'currency', currency: 'BRL' });
const inteiro = new Intl.NumberFormat('pt-BR', { maximumFractionDigits: 0 });
const decimal = new Intl.NumberFormat('pt-BR', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
const numero = new Intl.NumberFormat('pt-BR', { maximumFractionDigits: 2 });
const percentual = new Intl.NumberFormat('pt-BR', { minimumFractionDigits: 1, maximumFractionDigits: 1 });

function dataBr(iso) {
  const [a, m, d] = String(iso).slice(0, 10).split('-');
  return `${d}/${m}/${a}`;
}

/**
 * Valor de dimensão (texto da API) -> rótulo para a tela.
 * @param {string|null} valor
 * @param {{tipo: string, granularidade?: string, valores?: {valor, rotulo}[]}} dim
 */
export function formatarDimensao(valor, dim) {
  if (valor === null || valor === undefined || valor === '') return EM_BRANCO;
  const enumerado = (dim.valores || []).find((x) => x.valor === valor);
  if (enumerado) return enumerado.rotulo;
  switch (dim.tipo) {
    case 'booleano':
      return valor === 'true' ? 'Sim' : valor === 'false' ? 'Não' : valor;
    case 'moeda':
      return moeda.format(Number(valor));
    case 'numero':
      return numero.format(Number(valor));
    case 'data': {
      const s = String(valor);
      if (s.length > 10) {
        // Data com hora (drilldown): 'AAAA-MM-DDTHH:MM'
        return `${dataBr(s)} ${s.slice(11, 16)}`;
      }
      const [a, m] = s.split('-');
      switch (dim.granularidade) {
        case 'ano':
          return a;
        case 'trimestre':
          return `${Math.floor((Number(m) - 1) / 3) + 1}º tri/${a}`;
        case 'mes':
          return `${MESES[Number(m) - 1]}/${a}`;
        case 'semana':
          return `Sem. de ${dataBr(s)}`;
        default:
          return dataBr(s);
      }
    }
    default:
      return valor;
  }
}

/** Número de uma medida -> texto, conforme o formato que a API declarou. */
export function formatarMedida(valor, formato) {
  if (valor === null || valor === undefined) return '—';
  const n = Number(valor);
  switch (formato) {
    case 'moeda':
      return moeda.format(n);
    case 'inteiro':
      return inteiro.format(n);
    case 'decimal':
      return decimal.format(n);
    case 'percentual':
      return `${percentual.format(n)}%`;
    default:
      return numero.format(n);
  }
}

/**
 * Comparador de valores de uma dimensão: ordem do vocabulário (a do funil,
 * não a alfabética), número como número, data ISO como texto, texto em
 * pt-BR. "(em branco)" sempre por último.
 */
export function comparadorDimensao(dim) {
  const ordem = new Map((dim.valores || []).map((x, i) => [x.valor, i]));
  return (a, b) => {
    const na = a === null || a === undefined;
    const nb = b === null || b === undefined;
    if (na || nb) return na === nb ? 0 : na ? 1 : -1;
    if (ordem.size && ordem.has(a) && ordem.has(b)) return ordem.get(a) - ordem.get(b);
    if (dim.tipo === 'numero' || dim.tipo === 'moeda') return Number(a) - Number(b);
    if (dim.tipo === 'booleano') return a === b ? 0 : a === 'true' ? -1 : 1;
    return String(a).localeCompare(String(b), 'pt-BR', { sensitivity: 'base' });
  };
}

function chave(nivel, linha, coluna) {
  return JSON.stringify([nivel, linha, coluna]);
}

const TOTAL = '__total__';

/**
 * Grade pronta para desenhar.
 *
 * @param {object} res      resposta de POST /crm/relatorios/consulta
 * @param {{por: 'rotulo'|'valor', direcao: 'asc'|'desc'}} ordenacao
 * @returns {{
 *   colunas: {chave: (string|null)[]}[],                  // combinações de coluna
 *   linhas: {tipo: 'detalhe'|'subtotal'|'total', nivel: number, chave: (string|null)[],
 *            mostrar?: boolean[], celulas: object[], total: object}[],
 *   maximos: number[],   // maior valor de detalhe por medida (para o destaque)
 * }}
 * Cada item de `celulas`/`total` é {v, n, celula} — `celula` é a lista de
 * {campo, granularidade, valor} que o drilldown manda para a API.
 */
export function montarGrade(res, ordenacao = { por: 'rotulo', direcao: 'asc' }) {
  const L = res.linhas.length;
  const C = res.colunas.length;
  const M = res.valores.length;
  const dims = [...res.linhas, ...res.colunas];

  const mapa = new Map();
  const colunasVistas = [];
  const nos = Array.from({ length: L + 1 }, () => []);

  for (const cel of res.celulas) {
    const gL = cel.g.slice(0, L);
    const gC = cel.g.slice(L);
    // Nível da linha = quantos campos de linha, a partir do primeiro, NÃO
    // foram somados. GROUPING SETS só gera prefixos, então isso basta.
    const nivel = gL.findIndex((g) => g);
    const nivelLinha = nivel === -1 ? L : nivel;
    const chaveLinha = cel.d.slice(0, nivelLinha);
    const colunasSomadas = C > 0 && gC.every(Boolean);
    const chaveColuna = C === 0 || colunasSomadas ? TOTAL : cel.d.slice(L);

    mapa.set(chave(nivelLinha, chaveLinha, chaveColuna), cel);

    if (chaveColuna === TOTAL) {
      nos[nivelLinha].push({ chave: chaveLinha, cel });
    } else if (nivelLinha === 0) {
      colunasVistas.push(chaveColuna);
    }
  }

  // Combinações de coluna, ordenadas campo a campo.
  const compsColuna = res.colunas.map((d) => comparadorDimensao(d));
  colunasVistas.sort((a, b) => {
    for (let i = 0; i < C; i += 1) {
      const r = compsColuna[i](a[i], b[i]);
      if (r) return r;
    }
    return 0;
  });
  const colunas = C === 0 ? [] : colunasVistas.map((k) => ({ chave: k }));

  function celulaDrill(chaveLinha, chaveColuna) {
    const lista = [];
    chaveLinha.forEach((valor, i) => {
      lista.push({ campo: dims[i].campo, granularidade: dims[i].granularidade || null, valor });
    });
    if (chaveColuna !== TOTAL) {
      chaveColuna.forEach((valor, j) => {
        const d = dims[L + j];
        lista.push({ campo: d.campo, granularidade: d.granularidade || null, valor });
      });
    }
    return lista;
  }

  function valoresDa(nivel, chaveLinha) {
    const celulas = colunas.map((col) => {
      const cel = mapa.get(chave(nivel, chaveLinha, col.chave));
      return {
        v: cel ? cel.v : Array(M).fill(null),
        n: cel ? cel.n : 0,
        celula: celulaDrill(chaveLinha, col.chave),
      };
    });
    const t = mapa.get(chave(nivel, chaveLinha, TOTAL));
    const total = {
      v: t ? t.v : Array(M).fill(null),
      n: t ? t.n : 0,
      celula: celulaDrill(chaveLinha, TOTAL),
    };
    return { celulas, total };
  }

  // Árvore das linhas: filhos de cada prefixo, ordenados.
  const filhos = new Map();
  for (let k = 1; k <= L; k += 1) {
    for (const no of nos[k]) {
      const pai = JSON.stringify(no.chave.slice(0, k - 1));
      if (!filhos.has(pai)) filhos.set(pai, []);
      filhos.get(pai).push(no);
    }
  }
  const sinal = ordenacao?.direcao === 'desc' ? -1 : 1;
  for (const [, lista] of filhos) {
    if (!lista.length) continue;
    const k = lista[0].chave.length - 1;
    const comp = comparadorDimensao(res.linhas[k]);
    lista.sort((a, b) => {
      if (ordenacao?.por === 'valor') {
        const va = a.cel.v[0] ?? -Infinity;
        const vb = b.cel.v[0] ?? -Infinity;
        if (va !== vb) return (va - vb) * sinal;
      }
      return comp(a.chave[k], b.chave[k]) * (ordenacao?.por === 'valor' ? 1 : sinal);
    });
  }

  const linhas = [];
  function visitar(prefixo) {
    const lista = filhos.get(JSON.stringify(prefixo)) || [];
    lista.forEach((no) => {
      const k = no.chave.length;
      if (k === L) {
        // Detalhe: o rótulo de cada nível só aparece quando muda.
        linhas.push({
          tipo: 'detalhe', nivel: k, chave: no.chave,
          mostrar: rotulosVisiveis(no.chave, linhas, L),
          ...valoresDa(k, no.chave),
        });
      } else {
        visitar(no.chave);
        linhas.push({ tipo: 'subtotal', nivel: k, chave: no.chave, ...valoresDa(k, no.chave) });
      }
    });
  }
  visitar([]);
  linhas.push({ tipo: 'total', nivel: 0, chave: [], ...valoresDa(0, []) });

  // Maior valor de DETALHE por medida: base do destaque de intensidade.
  const maximos = Array(M).fill(0);
  for (const l of linhas) {
    if (l.tipo !== 'detalhe') continue;
    const fontes = C ? l.celulas : [l.total];
    for (const c of fontes) {
      c.v.forEach((v, j) => {
        if (typeof v === 'number' && Math.abs(v) > maximos[j]) maximos[j] = Math.abs(v);
      });
    }
  }

  return { colunas, linhas, maximos };
}

/**
 * Quais rótulos de linha aparecem: o de um nível só é mostrado quando ele
 * (ou um nível acima dele) muda em relação à linha de detalhe anterior.
 */
function rotulosVisiveis(chaveAtual, linhasAteAgora, L) {
  let anterior = null;
  for (let i = linhasAteAgora.length - 1; i >= 0; i -= 1) {
    const l = linhasAteAgora[i];
    if (l.tipo === 'detalhe') { anterior = l.chave; break; }
  }
  const mostrar = [];
  let mudou = anterior === null;
  for (let j = 0; j < L; j += 1) {
    if (!mudou && anterior[j] !== chaveAtual[j]) mudou = true;
    mostrar.push(mudou);
  }
  return mostrar;
}

/** Cabeçalhos agrupados das colunas: uma fileira por campo de coluna. */
export function cabecalhosDeColuna(colunas, nCampos) {
  const fileiras = [];
  for (let j = 0; j < nCampos; j += 1) {
    const fileira = [];
    colunas.forEach((col) => {
      const ultimo = fileira[fileira.length - 1];
      const prefixo = JSON.stringify(col.chave.slice(0, j + 1));
      if (ultimo && ultimo.prefixo === prefixo) {
        ultimo.span += 1;
      } else {
        fileira.push({ prefixo, valor: col.chave[j], span: 1 });
      }
    });
    fileiras.push(fileira);
  }
  return fileiras;
}
