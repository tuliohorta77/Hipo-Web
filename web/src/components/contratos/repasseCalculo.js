// web/src/components/contratos/repasseCalculo.js
//
// Espelho, só para a PRÉVIA do formulário, da conta que o servidor faz em
// api/services/repasse.py. O valor que vale é o que a API devolve depois de
// gravar — esta função existe para a pessoa ver o resultado enquanto digita.
//
//   K = vidas x valor por vida   (ou o valor fixo do mês)
//   L = K x percentual           (100% no primeiro mês, 30% depois)
//   N = L x imposto
//   O = L - N                    <- entra na Spectre
//
// Centavos inteiros para não herdar o erro do ponto flutuante; meio para
// cima, como o Decimal ROUND_HALF_UP do backend.

function centavos(valor) {
  if (valor === null || valor === undefined || valor === '') return null;
  const n = Number(String(valor).replace(',', '.'));
  if (!Number.isFinite(n)) return null;
  return Math.round(Number((n * 100).toFixed(6)));
}

// toFixed(6) tira o ruído do ponto flutuante (8948.499999 -> 8948.5) antes
// de arredondar o meio para cima.
function arredondar(valorEmCentavosFracionado) {
  return Math.floor(Number(valorEmCentavosFracionado.toFixed(6)) + 0.5);
}

export function numero(valor) {
  if (valor === null || valor === undefined || valor === '') return null;
  const n = Number(String(valor).replace(',', '.'));
  return Number.isFinite(n) ? n : null;
}

export function calcularRepasse({ vidas, valorPorVida, valorFixo, percentual, imposto }) {
  const v = Number.parseInt(vidas, 10);
  const vpv = centavos(valorPorVida);
  const fixo = centavos(valorFixo);
  const pct = numero(percentual);
  const imp = numero(imposto);
  if (pct === null || imp === null) return null;

  let k;
  if (vpv !== null) {
    if (!Number.isFinite(v) || v < 0) return null;
    k = v * vpv;
  } else if (fixo !== null) {
    k = fixo;
  } else {
    return null;
  }
  const l = arredondar((k * pct) / 100);
  const n = arredondar((l * imp) / 100);
  return {
    valorContrato: k / 100,
    valorRepasse: l / 100,
    valorImposto: n / 100,
    valorLiquido: (l - n) / 100,
  };
}

const BRL = new Intl.NumberFormat('pt-BR', { style: 'currency', currency: 'BRL' });

export function reais(valor) {
  const n = numero(valor);
  return n === null ? '—' : BRL.format(n);
}

export function pct(valor) {
  const n = numero(valor);
  if (n === null) return '—';
  return `${n.toLocaleString('pt-BR', { maximumFractionDigits: 2 })}%`;
}

const MESES = ['jan', 'fev', 'mar', 'abr', 'mai', 'jun', 'jul', 'ago', 'set', 'out', 'nov', 'dez'];

export function rotuloCompetencia(aaaaMm) {
  if (!aaaaMm) return '—';
  const [a, m] = aaaaMm.split('-').map(Number);
  return `${MESES[m - 1]}/${a}`;
}

export function dataBr(iso) {
  if (!iso) return '—';
  const [a, m, d] = String(iso).slice(0, 10).split('-');
  return `${d}/${m}/${a}`;
}
