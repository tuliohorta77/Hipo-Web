// web/src/components/CarteiraTimeline.jsx
//
// Timeline visual estilo SimplesVet: cada célula é um período (mês para Hunter,
// semana ISO para Farmer) com uma bolinha colorida indicando o status.
//
// Status (alinhado com services/carteira_agg.py):
//   ok     → verde   (meta atingida no período)
//   miss   → vermelho (período passou sem cumprir)
//   now    → âmbar   (período atual, ainda sem cumprir)
//   future → cinza   (período no futuro — não conta para meta)
//
// Props:
//   cells: [{ key, label, status, count }, ...]
//   compact: boolean — versão compacta para a linha da tabela

const STATUS_STYLES = {
  ok:     { dot: "bg-emerald-400", ring: "ring-emerald-400/30", text: "text-emerald-300" },
  miss:   { dot: "bg-red-500",     ring: "ring-red-500/30",     text: "text-red-300"     },
  now:    { dot: "bg-amber-400",   ring: "ring-amber-400/30",   text: "text-amber-300"   },
  future: { dot: "bg-slate-700",   ring: "ring-slate-700/30",   text: "text-slate-500"   },
};

export default function CarteiraTimeline({ cells = [], compact = false }) {
  if (!cells.length) {
    return <span className="text-slate-600 text-xs">—</span>;
  }

  const size = compact ? "w-3 h-3" : "w-4 h-4";
  const gap = compact ? "gap-1.5" : "gap-2.5";

  return (
    <div className={`flex items-center ${gap}`}>
      {cells.map((c) => {
        const s = STATUS_STYLES[c.status] || STATUS_STYLES.future;
        const title = `${c.label}: ${c.count} tarefa(s) — ${c.status}`;
        return (
          <div key={c.key} className="flex flex-col items-center" title={title}>
            <div
              className={`${size} rounded-full ${s.dot} ring-2 ${s.ring} transition-all`}
              aria-label={title}
            />
            {!compact && (
              <span className={`text-[9px] mt-1 tracking-wider ${s.text}`}>
                {c.label}
              </span>
            )}
          </div>
        );
      })}
    </div>
  );
}
