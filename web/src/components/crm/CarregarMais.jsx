// web/src/components/crm/CarregarMais.jsx
//
// Rodapé das colunas do kanban (oportunidades e tarefas) e do painel da fase
// do funil: puxa os próximos cartões, de 100 em 100.
//
// ── Por que existe ───────────────────────────────────────────────────
// As colunas mostravam os primeiros N cartões e um "+1074 não exibidas" sem
// caminho nenhum até eles. Cartão que existe e não pode ser alcançado é dado
// perdido para quem opera a tela — o suspect 1.051 simplesmente não existia
// para o SDR. Agora toda coluna chega ao último cartão.
//
// O texto "+N não exibidas" continua visível ao lado do botão: é ele que diz
// quanto falta, e o número bate com o contador do cabeçalho da coluna.

import { ChevronsDown, Loader2 } from 'lucide-react';

export const PAGINA_KANBAN = 100;

/**
 * Junta a página nova à lista atual sem repetir cartão.
 *
 * Repetição acontece de verdade: se alguém move um cartão entre a primeira
 * página e o "carregar mais", o offset desloca uma posição e o último cartão
 * da página anterior volta na seguinte. Chave duplicada no React embaralha a
 * reconciliação — o cartão aberto passa a ser outro.
 */
export function mesclarItens(atuais, novos) {
  const vistos = new Set(atuais.map((i) => i.id));
  return [...atuais, ...novos.filter((i) => !vistos.has(i.id))];
}

/**
 * Recarregar a tela (depois de mover, concluir, filtrar...) devolve só a
 * primeira página de cada coluna. Quem tinha puxado 300 cartões voltaria
 * para 100 a cada ação — e perderia o lugar onde estava rolando.
 *
 * `alvo` é quantos cartões a coluna tinha antes da recarga. Esta função busca
 * o que falta para chegar lá (em blocos de até 500, o teto do backend) e
 * devolve a coluna completa. Para quando a coluna acaba ou a página vem vazia.
 */
export async function completarColuna(coluna, alvo, buscar) {
  const meta = Math.min(alvo || 0, coluna.quantidade);
  let atual = coluna;
  while (atual.itens.length < meta) {
    const offset = atual.itens.length;
    const limit = Math.min(500, meta - offset);
    // eslint-disable-next-line no-await-in-loop
    const pagina = await buscar(offset, limit);
    if (!pagina?.itens?.length) break;
    atual = {
      ...atual,
      quantidade: pagina.quantidade ?? atual.quantidade,
      itens: mesclarItens(atual.itens, pagina.itens),
    };
    if (atual.itens.length === offset) break;   // só repetidos: não há mais o que puxar
  }
  return atual;
}

export default function CarregarMais({ exibidos, total, onCarregar, carregando = false }) {
  const faltam = total - exibidos;
  if (faltam <= 0) return null;

  const proxima = Math.min(PAGINA_KANBAN, faltam);

  return (
    <div className="shrink-0 pt-1.5 flex flex-col items-center gap-0.5">
      {onCarregar && (
        <button
          type="button"
          onClick={onCarregar}
          disabled={carregando}
          className={
            'w-full h-8 inline-flex items-center justify-center gap-1.5 rounded-lg ' +
            'border border-hipo-border bg-hipo-card text-xs font-medium text-hipo-blue ' +
            'hover:bg-hipo-blueSoft/40 transition-colors ' +
            'disabled:cursor-wait disabled:opacity-60 ' +
            'focus:outline-none focus-visible:ring-2 focus-visible:ring-hipo-blue'
          }
        >
          {carregando
            ? <Loader2 size={13} className="animate-spin" aria-hidden="true" />
            : <ChevronsDown size={13} aria-hidden="true" />}
          {carregando ? 'Carregando…' : `Carregar mais ${proxima}`}
        </button>
      )}
      <span className="text-[11px] text-hipo-muted">+{faltam} não exibidas</span>
    </div>
  );
}
