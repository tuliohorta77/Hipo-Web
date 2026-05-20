// web/src/components/CarteiraTimeline.jsx
//
// Timeline visual: cada célula é um período (mês para Hunter, semana ISO
// para Farmer) com uma bolinha colorida indicando o status.
//
// Manual §6: "badges suaves, sem saturação excessiva".
// Manual §9: "não depender apenas de cor para indicar status; usar texto,
// ícone ou badge".
//
// Por isso usamos bg pastel (soft) + texto/borda semântico, em vez de
// dots sólidos saturados. A leitura visual continua imediata (verde =
// ok, vermelho = miss, âmbar = now, cinza = future) mas com tom calmo.
//
// Status (alinhado com services/carteira_agg.py):
//   ok     → verde   (meta atingida no período)
//   miss   → vermelho (período passou sem cumprir)
//   now    → âmbar   (período atual, ainda sem cumprir)
//   future → cinza   (período no futuro — não conta para meta)

const STATUS_STYLES = {
  ok: {
    bg: 'bg-hipo-successSoft',
    text: 'text-hipo-success',
    border: 'border-hipo-successBorder',
  },
  miss: {
    bg: 'bg-hipo-dangerSoft',
    text: 'text-hipo-danger',
    border: 'border-hipo-dangerBorder',
  },
  now: {
    bg: 'bg-hipo-warningSoft',
    text: 'text-hipo-warning',
    border: 'border-hipo-warningBorder',
  },
  future: {
    bg: 'bg-hipo-bg',
    text: 'text-hipo-muted',
    border: 'border-hipo-border',
  },
};

export default function CarteiraTimeline({ cells = [], compact = false }) {
  if (!cells.length) {
    return <span className="text-hipo-muted text-xs">—</span>;
  }

  const size = compact ? 'w-6 h-6 text-[9px]' : 'w-7 h-7 text-[10px]';
  const gap  = compact ? 'gap-1' : 'gap-1.5';

  return (
    <div className={`flex items-center ${gap}`}>
      {cells.map((c) => {
        const s = STATUS_STYLES[c.status] || STATUS_STYLES.future;
        const title = `${c.label}: ${c.count} tarefa(s) — ${c.status}`;
        return (
          <div
            key={c.key}
            className="flex flex-col items-center"
            title={title}
          >
            <div
              className={`${size} rounded-full border flex items-center justify-center font-semibold ${s.bg} ${s.text} ${s.border} transition-colors`}
              aria-label={title}
            >
              {c.count > 0 ? c.count : ''}
            </div>
            {!compact && (
              <span className={`text-[10px] mt-1 font-medium ${s.text}`}>
                {c.label}
              </span>
            )}
          </div>
        );
      })}
    </div>
  );
}
