// web/src/components/ui/PageHeader.jsx
// Cabeçalho padrão das páginas: título grande, subtítulo, ações à direita.

export default function PageHeader({ title, subtitle, actions, className = '' }) {
  return (
    <div className={`flex flex-wrap items-start justify-between gap-4 mb-6 ${className}`}>
      <div className="min-w-0">
        <h1 className="text-h1 text-hipo-ink">{title}</h1>
        {subtitle && (
          <p className="text-sm text-hipo-slate mt-1">{subtitle}</p>
        )}
      </div>
      {actions && (
        <div className="flex items-center gap-2 flex-wrap shrink-0">
          {actions}
        </div>
      )}
    </div>
  );
}
