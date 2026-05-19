// web/src/components/ui/AlertMessage.jsx
// Caixa de feedback consistente para resultados de operações
// (upload, save, etc).

import { CheckCircle2, AlertTriangle, XCircle, Info } from 'lucide-react';

const STYLES = {
  ok: {
    container: 'bg-emerald-50 border-emerald-100 text-emerald-800',
    Icon: CheckCircle2,
    iconClass: 'text-hipo-success',
  },
  aviso: {
    container: 'bg-amber-50 border-amber-100 text-amber-800',
    Icon: AlertTriangle,
    iconClass: 'text-hipo-warning',
  },
  erro: {
    container: 'bg-red-50 border-red-100 text-red-800',
    Icon: XCircle,
    iconClass: 'text-hipo-danger',
  },
  info: {
    container: 'bg-hipo-blueSoft border-blue-100 text-hipo-blueDark',
    Icon: Info,
    iconClass: 'text-hipo-blue',
  },
};

export default function AlertMessage({ tipo = 'info', children, className = '' }) {
  const cfg = STYLES[tipo] || STYLES.info;
  const { Icon } = cfg;
  return (
    <div
      role="alert"
      className={`flex items-start gap-2.5 px-4 py-3 rounded-lg border text-sm ${cfg.container} ${className}`}
    >
      <Icon size={18} className={`shrink-0 mt-0.5 ${cfg.iconClass}`} />
      <div className="flex-1">{children}</div>
    </div>
  );
}
