// web/src/components/monitor/monitorComum.js
//
// O vocabulário do Monitor: as carinhas, as cores e como cada número é
// escrito. Num painel de parede o formato é metade da informação — "39,3 K"
// se lê de longe, "R$ 39.312,00" não.
//
// As REGRAS (meta MTD, atingimento, qual carinha) ficam no servidor
// (services/monitor.py): o painel recebe `carinha` e `atingimento` prontos.
// Recalcular aqui daria uma segunda régua, e a que divergisse seria a que
// está na TV — o pior lugar possível para um número errado.

// As cinco carinhas. Emoji e não ícone de biblioteca: é o desenho que a
// operação já usa na planilha, é legível a cinco metros e não depende de
// cor para ser entendido.
export const CARINHAS = {
  muito_feliz: { emoji: '😄', rotulo: 'muito acima da meta', tom: 'success' },
  feliz: { emoji: '🙂', rotulo: 'na meta', tom: 'success' },
  neutro: { emoji: '😐', rotulo: 'perto da meta', tom: 'warning' },
  triste: { emoji: '😟', rotulo: 'abaixo da meta', tom: 'danger' },
  bravo: { emoji: '😠', rotulo: 'muito abaixo da meta', tom: 'danger' },
};

// Sem carinha o quadro não é neutro por estética: é "não há como comparar"
// — falta a meta, ou falta a fonte do dado (o treinamento).
export const SEM_CARINHA = { emoji: '—', rotulo: 'sem meta definida', tom: 'neutro' };

export function carinhaDe(chave) {
  return CARINHAS[chave] || SEM_CARINHA;
}

// Cor da barra e do número, pela carinha. O verde/amarelo/vermelho do
// manual de marca, sem inventar paleta nova.
export const TOM_CLASSE = {
  success: { texto: 'text-hipo-success', barra: 'bg-hipo-success' },
  warning: { texto: 'text-hipo-warning', barra: 'bg-hipo-warning' },
  danger: { texto: 'text-hipo-danger', barra: 'bg-hipo-danger' },
  neutro: { texto: 'text-hipo-slate', barra: 'bg-hipo-border' },
};

/**
 * Dinheiro curto para parede: 39,3 K em vez de R$ 39.312,00.
 *
 * O painel é lido de longe e o que importa nele é a ordem de grandeza. O
 * valor exato continua a um clique de distância, na tela de origem.
 */
export function moedaCurta(valor) {
  const n = Number(valor || 0);
  if (Math.abs(n) >= 1000) {
    return `${(n / 1000).toFixed(1).replace('.', ',')} K`;
  }
  return n.toLocaleString('pt-BR', { maximumFractionDigits: 0 });
}

export function inteiro(valor) {
  return Number(valor || 0).toLocaleString('pt-BR', { maximumFractionDigits: 1 });
}

export function percentual(valor) {
  const n = Number(valor || 0);
  return `${n.toLocaleString('pt-BR', { maximumFractionDigits: 1 })}%`;
}

/**
 * Escreve um valor no formato do indicador.
 *
 * `null` vira travessão, e isso é informação: ticket médio sem contrato
 * nenhum é INDEFINIDO, e "R$ 0" seria uma afirmação sobre o mês.
 */
export function formatar(valor, formato) {
  if (valor === null || valor === undefined) return '—';
  if (formato === 'moeda') return moedaCurta(valor);
  if (formato === 'percentual') return percentual(valor);
  return inteiro(valor);
}

/** Fração (0.25) para largura de barra em % , limitada a 100. */
export function larguraDaBarra(fracao) {
  if (fracao === null || fracao === undefined) return 0;
  return Math.max(0, Math.min(100, Math.round(fracao * 100)));
}

/** Fração para texto curto: 0.253 -> '25%'. */
export function pctCurto(fracao) {
  if (fracao === null || fracao === undefined) return null;
  return `${Math.round(fracao * 100)}%`;
}

/** 'HH:MM:SS' do instante em que o painel foi lido. */
export function horaDaLeitura(iso) {
  if (!iso) return null;
  return new Date(iso).toLocaleTimeString('pt-BR', {
    hour: '2-digit', minute: '2-digit', second: '2-digit',
  });
}

// De quanto em quanto tempo a TV busca o painel de novo. 60s é o ritmo em
// que o dado de fato muda (uma reunião registrada, uma venda fechada) e
// mantém a carga em uma request por minuto por tela aberta.
export const INTERVALO_MS = 60000;
