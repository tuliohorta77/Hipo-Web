// web/src/components/ui/Badge.jsx
// Badges pastel — sem saturação excessiva (regra do Manual de Marca).
//
// tones:
//   neutral, info, success, warning, danger
//
// Variantes especializadas para os status canônicos do Hipo:
//   <StatusBadge status="Em andamento" />
//   <StatusBadge status="Concluído" />

const TONES = {
  neutral: 'bg-hipo-bg text-hipo-slate border-hipo-border',
  info:    'bg-hipo-blueSoft text-hipo-blueDark border-blue-100',
  success: 'bg-emerald-50 text-emerald-700 border-emerald-100',
  warning: 'bg-amber-50 text-amber-700 border-amber-100',
  danger:  'bg-red-50 text-red-700 border-red-100',
};

export default function Badge({ tone = 'neutral', children, className = '' }) {
  return (
    <span
      className={
        'inline-flex items-center gap-1 px-2.5 py-1 rounded-full text-xs ' +
        `font-medium border ${TONES[tone]} ${className}`
      }
    >
      {children}
    </span>
  );
}

// Mapa de status canônicos (Manual §9 — nomes consistentes).
const STATUS_TONE = {
  'Em andamento': 'info',
  'Planejamento': 'warning',
  'Em revisão':   'warning',
  'Concluído':    'success',
  'Pendente':     'neutral',
  'Atrasado':     'danger',
  'OK':           'success',
  'Em dia':       'success',
};

export function StatusBadge({ status, className = '' }) {
  const tone = STATUS_TONE[status] || 'neutral';
  return <Badge tone={tone} className={className}>{status}</Badge>;
}
