// web/src/components/ui/KpiCard.jsx
// Card de KPI: ícone em badge pastel, número grande, variação discreta.
// Conforme Manual §6 ("Cards KPI") e tokens do Manual de Marca v1.0.

import { ArrowUp, ArrowDown, Minus } from 'lucide-react';

// Tones para o badge do ícone. Manual §6: "ícone em badge pastel".
// Reduzido de 6 cores genéricas (emerald/amber/rose/violet) para a paleta
// canônica do manual: azul (padrão), success/warning/danger e slate neutro.
const ICON_TONES = {
  blue:    'bg-hipo-blueSoft    text-hipo-blue',
  success: 'bg-hipo-successSoft text-hipo-success',
  warning: 'bg-hipo-warningSoft text-hipo-warning',
  danger:  'bg-hipo-dangerSoft  text-hipo-danger',
  slate:   'bg-hipo-bg          text-hipo-slate',

  // Aliases retrocompatíveis pra não quebrar usos existentes
  // (emerald/amber/rose/violet caem nas variantes canônicas mais próximas)
  emerald: 'bg-hipo-successSoft text-hipo-success',
  amber:   'bg-hipo-warningSoft text-hipo-warning',
  rose:    'bg-hipo-dangerSoft  text-hipo-danger',
  violet:  'bg-hipo-blueSoft    text-hipo-blue',
};

export default function KpiCard({
  label,
  value,
  hint,                       // texto auxiliar embaixo do número (ex: "vs. semana anterior")
  delta,                      // número: positivo = subiu, negativo = caiu, 0 = neutro
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
      deltaColor = deltaPositiveIsGood ? 'text-hipo-success' : 'text-hipo-danger';
      deltaText = `${v}%`;
    } else if (v < 0) {
      DeltaIcon = ArrowDown;
      deltaColor = deltaPositiveIsGood ? 'text-hipo-danger' : 'text-hipo-success';
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
