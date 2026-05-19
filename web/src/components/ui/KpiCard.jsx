// web/src/components/ui/KpiCard.jsx
// Card de KPI: ícone em badge pastel, número grande, variação discreta.
// Conforme Manual §6 ("Cards KPI").

import { ArrowUp, ArrowDown, Minus } from 'lucide-react';

const ICON_TONES = {
  blue:    'bg-hipo-blueSoft text-hipo-blue',
  emerald: 'bg-emerald-50    text-emerald-600',
  amber:   'bg-amber-50      text-amber-600',
  rose:    'bg-rose-50       text-rose-600',
  violet:  'bg-violet-50     text-violet-600',
  slate:   'bg-hipo-bg       text-hipo-slate',
};

export default function KpiCard({
  label,
  value,
  hint,                 // texto auxiliar embaixo do número (ex: "vs. semana anterior")
  delta,                // número: positivo = subiu, negativo = caiu, 0 = neutro
  deltaPositiveIsGood = true, // pra inverter cor (ex: pendências subindo é ruim)
  icon: Icon,
  tone = 'blue',
}) {
  let DeltaIcon = Minus;
  let deltaColor = 'text-hipo-slate';
  let deltaText = '0%';

  if (delta !== undefined && delta !== null) {
    const v = Number(delta);
    if (v > 0) {
      DeltaIcon = ArrowUp;
      deltaColor = deltaPositiveIsGood ? 'text-emerald-600' : 'text-red-600';
      deltaText = `${v}%`;
    } else if (v < 0) {
      DeltaIcon = ArrowDown;
      deltaColor = deltaPositiveIsGood ? 'text-red-600' : 'text-emerald-600';
      deltaText = `${v}%`;
    } else {
      deltaText = '0%';
    }
  }

  return (
    <div className="bg-hipo-card border border-hipo-border rounded-xl shadow-soft p-5">
      <div className="flex items-start justify-between mb-3">
        <p className="text-sm text-hipo-slate font-medium">{label}</p>
        {Icon && (
          <div
            className={`w-10 h-10 rounded-lg flex items-center justify-center ${ICON_TONES[tone] || ICON_TONES.blue}`}
          >
            <Icon size={20} />
          </div>
        )}
      </div>

      <p className="text-kpi text-hipo-ink">{value}</p>

      {(delta !== undefined || hint) && (
        <div className="flex items-center gap-2 mt-2 text-xs">
          {delta !== undefined && delta !== null && (
            <span className={`inline-flex items-center gap-0.5 font-medium ${deltaColor}`}>
              <DeltaIcon size={12} />
              {deltaText}
            </span>
          )}
          {hint && <span className="text-hipo-slate">{hint}</span>}
        </div>
      )}
    </div>
  );
}
