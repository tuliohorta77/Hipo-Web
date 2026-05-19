// web/src/components/ui/Card.jsx
// Superfície base do Hipo: branca, borda sutil, sombra muito leve.
//
// Uso:
//   <Card><p>Conteúdo</p></Card>
//   <Card padding="lg" className="lg:col-span-2">...</Card>

export default function Card({
  children,
  padding = 'md',
  className = '',
  ...rest
}) {
  const pad = {
    none: '',
    sm: 'p-4',
    md: 'p-5 md:p-6',
    lg: 'p-6 md:p-8',
  }[padding] || 'p-5 md:p-6';

  return (
    <div
      className={`bg-hipo-card border border-hipo-border rounded-xl shadow-soft ${pad} ${className}`}
      {...rest}
    >
      {children}
    </div>
  );
}

// Cabeçalho semântico pra cards. Título à esquerda, ação opcional à direita.
export function CardHeader({ title, hint, right, className = '' }) {
  return (
    <div className={`flex items-start justify-between gap-4 mb-4 ${className}`}>
      <div className="min-w-0">
        <h3 className="text-h2 text-hipo-ink truncate">{title}</h3>
        {hint && <p className="text-sm text-hipo-slate mt-0.5">{hint}</p>}
      </div>
      {right && <div className="shrink-0">{right}</div>}
    </div>
  );
}
