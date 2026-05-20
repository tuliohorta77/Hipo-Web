// web/src/components/ui/MiniFunil.jsx
//
// Mini-funil horizontal: mostra QTD e R$ de cada uma das 5 etapas ativas
// (Suspect, Cadência, Qualificação, Apresentação, Negociação).
//
// Manual §2: "Azul como cor de acento, ÚNICA. Poucas cores auxiliares".
// Manual §6: "badges suaves, sem saturação excessiva".
//
// Por isso TODAS as etapas usam a paleta azul do manual. A diferenciação
// entre etapas vem da LETRA (S/C/Q/A/N) e do número, não da cor.
// Etapas sem leads ficam em estado "muted" (neutro) pra não poluir a tabela.
//
// Props:
//   - dados: { suspect: {qtd, ticket}, cadencia: {qtd, ticket}, ... }
//   - vazio: string opcional pra exibir quando todas as etapas tem qtd=0

const ETAPAS = [
  { chave: 'suspect',      label: 'S' },
  { chave: 'cadencia',     label: 'C' },
  { chave: 'qualificacao', label: 'Q' },
  { chave: 'apresentacao', label: 'A' },
  { chave: 'negociacao',   label: 'N' },
];

const LABELS_COMPLETOS = {
  suspect:      'Suspect',
  cadencia:     'Cadência',
  qualificacao: 'Qualificação',
  apresentacao: 'Apresentação',
  negociacao:   'Negociação',
};

function fmtMoedaCompacta(v) {
  if (!v) return 'R$0';
  const n = Number(v);
  if (n >= 1_000_000) return `R$${(n / 1_000_000).toFixed(1)}M`;
  if (n >= 1_000)     return `R$${(n / 1_000).toFixed(1)}k`;
  return `R$${n.toFixed(0)}`;
}

export default function MiniFunil({ dados, vazio = '—', loading = false }) {
  if (loading) {
    return <span className="text-xs text-hipo-muted italic">carregando…</span>;
  }
  if (!dados) {
    return <span className="text-xs text-hipo-muted">{vazio}</span>;
  }
  // Se todas as etapas tem qtd=0, mostra mensagem de vazio
  const totalQtd = ETAPAS.reduce(
    (acc, e) => acc + (dados[e.chave]?.qtd || 0),
    0
  );
  if (totalQtd === 0) {
    return <span className="text-xs text-hipo-muted">{vazio}</span>;
  }

  return (
    <div className="inline-flex items-center gap-1.5 text-[11px] leading-tight whitespace-nowrap">
      {ETAPAS.map((e) => {
        const v = dados[e.chave] || { qtd: 0, ticket: 0 };
        const qtd = v.qtd || 0;
        const ticket = v.ticket || 0;
        const desativado = qtd === 0;
        const labelTitulo = LABELS_COMPLETOS[e.chave];

        // Estado "com leads": fundo blueSoft + texto blue (acento azul do manual).
        // Estado "sem leads": neutro discreto pra não poluir.
        const classes = desativado
          ? 'bg-hipo-bg text-hipo-muted'
          : 'bg-hipo-blueSoft text-hipo-blue font-semibold';

        return (
          <div
            key={e.chave}
            title={`${labelTitulo}: ${qtd} leads · R$ ${ticket.toLocaleString('pt-BR', { maximumFractionDigits: 0 })}`}
            className={`flex flex-col items-center px-1.5 py-0.5 rounded ${classes}`}
          >
            <span className="text-[10px] tracking-wide opacity-70">{e.label}</span>
            <span className="text-xs">{qtd}</span>
            <span className="text-[9px] opacity-80">{fmtMoedaCompacta(ticket)}</span>
          </div>
        );
      })}
    </div>
  );
}

/**
 * Helper: agrega múltiplos objetos de dados de funil somando qtd e ticket.
 * Usado para gerar o agregado de um colaborador a partir de seus contadores.
 */
export function agregarFunis(listaDeFunis) {
  const total = {
    suspect:      { qtd: 0, ticket: 0 },
    cadencia:     { qtd: 0, ticket: 0 },
    qualificacao: { qtd: 0, ticket: 0 },
    apresentacao: { qtd: 0, ticket: 0 },
    negociacao:   { qtd: 0, ticket: 0 },
  };
  for (const f of listaDeFunis) {
    if (!f) continue;
    for (const k of Object.keys(total)) {
      total[k].qtd += f[k]?.qtd || 0;
      total[k].ticket += f[k]?.ticket || 0;
    }
  }
  return total;
}
