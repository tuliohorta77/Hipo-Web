// web/src/components/crm/propostaCalculo.js
//
// As contas da proposta, do lado da tela. Espelham services/proposta.py —
// servem para o vendedor ver o total ANTES de gerar. O servidor recalcula
// tudo na hora de gravar: estes números são para o olho, não são o que vai
// para o arquivo.

// "1.234,56", "1234,56" e "1234.56" viram 1234.56. Vazio vira NaN — quem
// chama decide se vazio é zero ou "use a tabela".
export function numero(v) {
  if (v === null || v === undefined) return NaN;
  const s = String(v).trim();
  if (!s) return NaN;
  const normal = s.includes(',') ? s.replace(/\./g, '').replace(',', '.') : s;
  const n = Number(normal);
  return Number.isFinite(n) ? n : NaN;
}

function arred(n) {
  return Math.round(n * 100) / 100;
}

// A faixa em que `vidas` cai. A tabela chega do servidor já ordenada, com
// a faixa aberta (vidas_ate = null) por último.
export function faixaDe(vidas, faixas) {
  if (!faixas?.length) return null;
  return faixas.find((f) => f.vidas_ate === null || vidas <= f.vidas_ate)
    || faixas[faixas.length - 1];
}

// Mensalidade sugerida pela tabela para um CNPJ com `vidas` vidas.
export function valorTabela(vidas, faixas) {
  const v = Number(vidas);
  if (!Number.isFinite(v) || v < 1) return null;
  const f = faixaDe(v, faixas);
  if (!f) return null;
  const valor = Number(f.valor);
  return arred(f.tipo === 'por_vida' ? v * valor : valor);
}

// Quanto ficou abaixo da tabela, em %, uma casa. null quando não há tabela
// ou o valor está na tabela (ou acima).
export function descontoPercentual(mensal, tabela) {
  const m = Number(mensal);
  const t = Number(tabela);
  if (!Number.isFinite(m) || !Number.isFinite(t) || t <= 0 || m >= t) return null;
  return Math.round(((t - m) / t) * 1000) / 10;
}

// A mensalidade de uma linha da proposta, como o servidor vai calcular:
//   por_vida — vidas x valor por vida, sempre
//   tabela   — o valor negociado, ou o da tabela quando em branco
export function mensalidadeDaLinha({ modalidade, vidas, valorNegociado, valorPorVida, faixas }) {
  const v = Number(vidas);
  if (!Number.isFinite(v) || v < 1) return null;
  if (modalidade === 'por_vida') {
    const vpv = numero(valorPorVida);
    return Number.isFinite(vpv) ? arred(v * vpv) : null;
  }
  const negociado = numero(valorNegociado);
  return Number.isFinite(negociado) ? arred(negociado) : valorTabela(v, faixas);
}
