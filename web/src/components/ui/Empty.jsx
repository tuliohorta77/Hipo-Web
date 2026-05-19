// web/src/components/ui/Empty.jsx
// Estado vazio reusável. Texto curto e direto (Manual §8).

import { Inbox } from 'lucide-react';

export default function Empty({
  title = 'Sem dados ainda',
  description,
  icon: Icon = Inbox,
  action,           // ReactNode opcional (ex: <Button>...</Button>)
  className = '',
}) {
  return (
    <div
      className={`flex flex-col items-center justify-center text-center py-12 px-4 ${className}`}
    >
      <div className="w-12 h-12 rounded-full bg-hipo-bg flex items-center justify-center mb-3">
        <Icon size={22} className="text-hipo-muted" />
      </div>
      <p className="text-base font-semibold text-hipo-ink">{title}</p>
      {description && (
        <p className="text-sm text-hipo-slate mt-1 max-w-sm">{description}</p>
      )}
      {action && <div className="mt-4">{action}</div>}
    </div>
  );
}
