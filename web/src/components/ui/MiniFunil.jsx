// web/src/components/ui/MiniFunil.jsx
//
// O funil de UMA linha de tabela: as cinco fases abertas do estoque daquele
// registro, em cinco casas de largura fixa.
//
// ── História ─────────────────────────────────────────────────────────
// A versão anterior deste arquivo era código morto — ninguém a importava e
// ela ainda falava na fase `cadencia`, que deixou de existir na Sprint 0.
// Voltou porque a linha do parceiro precisa responder "o que ele indicou e
// onde isso está" sem abrir o painel: a coluna "Indicações: 7" diz quantas,
// não diz se são sete suspects parados ou duas negociações quentes.
//
// ── Por que largura FIXA ─────────────────────────────────────────────
// Não é um funil proporcional como o da tela de Oportunidades. Ali a largura
// da faixa É o dado, porque é uma faixa por tela. Aqui são cinco casas
// repetidas linha após linha, e casa que muda de largura conforme o conteúdo
// destrói a leitura vertical — o olho compara colunas, não números soltos.
// Por isso as cinco casas aparecem sempre, inclusive as zeradas: o payload
// do backend é um modelo fechado justamente para garantir isso.
//
// ── Por que a cor não diferencia a fase ──────────────────────────────
// Manual de marca: azul é a cor de acento, única. Cinco cores numa célula de
// tabela viram semáforo sem significado. A fase é identificada pela LETRA
// (S/L/Q/A/N) e o peso vem do número; fase vazia fica neutra para não
// competir com as que têm conteúdo.

const FASES = [
  { chave: 'suspect', letra: 'S', rotulo: 'Suspect' },
  { chave: 'lead', letra: 'L', rotulo: 'Lead' },
  { chave: 'qualificacao', letra: 'Q', rotulo: 'Qualificação' },
  { chave: 'apresentacao', letra: 'A', rotulo: 'Apresentação' },
  { chave: 'negociacao', letra: 'N', rotulo: 'Negociação' },
];

/**
 * 'R$ 12,5k'. Compacto porque a célula tem ~34px de largura: o valor cheio
 * quebraria a linha e a tabela ganharia altura em toda linha.
 */
export function moedaCompacta(valor) {
  const n = Number(valor) || 0;
  if (n >= 1_000_000) return `${(n / 1_000_000).toFixed(1).replace('.', ',')}M`;
  if (n >= 1_000) return `${(n / 1_000).toFixed(1).replace('.', ',')}k`;
  return String(Math.round(n));
}

function moedaCheia(valor) {
  return Number(valor || 0).toLocaleString('pt-BR', {
    style: 'currency', currency: 'BRL', maximumFractionDigits: 0,
  });
}

export default function MiniFunil({ dados, vazio = 'Nada em aberto', mostrarTicket = true }) {
  if (!dados) {
    return <span className="text-[11px] text-hipo-muted">—</span>;
  }

  const total = FASES.reduce((soma, f) => soma + (dados[f.chave]?.qtd || 0), 0);

  // Tudo zerado vira uma frase, não cinco caixinhas cinzas. Cinco zeros
  // repetidos por linha inteira é ruído com o formato de dado.
  if (total === 0) {
    return <span className="text-[11px] text-hipo-muted">{vazio}</span>;
  }

  return (
    <div
      className="inline-flex items-center gap-1 whitespace-nowrap"
      role="group"
      aria-label={`Funil em aberto: ${total} oportunidade${total === 1 ? '' : 's'}`}
    >
      {FASES.map((f) => {
        const fase = dados[f.chave] || { qtd: 0, ticket: 0 };
        const qtd = Number(fase.qtd) || 0;
        const ticket = Number(fase.ticket) || 0;
        const vazia = qtd === 0;

        return (
          <span
            key={f.chave}
            title={`${f.rotulo}: ${qtd} em aberto · ${moedaCheia(ticket)}`}
            className={
              'w-9 shrink-0 flex flex-col items-center rounded px-0.5 py-0.5 leading-none ' +
              (vazia
                ? 'bg-hipo-bg text-hipo-muted'
                : 'bg-hipo-blueSoft text-hipo-blue font-semibold')
            }
          >
            <span className="text-[9px] tracking-wider opacity-70">{f.letra}</span>
            <span className="text-[11px] mt-0.5">{qtd}</span>
            {mostrarTicket && (
              <span className="text-[8px] mt-0.5 opacity-80">
                {vazia ? '—' : moedaCompacta(ticket)}
              </span>
            )}
          </span>
        );
      })}
    </div>
  );
}
