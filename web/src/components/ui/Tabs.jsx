// web/src/components/ui/Tabs.jsx
// Tabs simples — usadas em PEX e POs.

export default function Tabs({ items, value, onChange, className = '' }) {
  return (
    <div className={`flex gap-1 border-b border-hipo-border ${className}`}>
      {items.map(({ key, label, badge }) => {
        const isActive = value === key;
        return (
          <button
            key={key}
            data-testid={`tab-${key}`}
            onClick={() => onChange(key)}
            className={
              'relative px-4 h-11 text-sm font-medium transition-colors ' +
              (isActive
                ? 'text-hipo-blue'
                : 'text-hipo-slate hover:text-hipo-ink')
            }
          >
            <span className="inline-flex items-center gap-2">
              {label}
              {badge ? (
                <span className="inline-flex items-center justify-center min-w-[20px] h-5 px-1.5 rounded-full bg-hipo-danger text-white text-xs font-semibold">
                  {badge}
                </span>
              ) : null}
            </span>
            {isActive && (
              <span className="absolute left-0 right-0 -bottom-px h-0.5 bg-hipo-blue rounded-full" />
            )}
          </button>
        );
      })}
    </div>
  );
}
