// web/src/components/ui/Tabs.jsx
//
// Duas orientações, mesma API.
//
//   horizontal — a de sempre, sublinhado no item ativo.
//   vertical   — trilho à esquerda, barra no item ativo.
//
// A vertical existe porque num modal a aba horizontal come uma faixa da
// altura, que é o recurso escasso; à esquerda ela come largura, que sobra.
// O `data-testid` é o mesmo nos dois, então teste que troca de aba não sabe
// nem precisa saber qual está em uso.

export default function Tabs({
  items, value, onChange, className = '', orientacao = 'horizontal',
}) {
  const vertical = orientacao === 'vertical';

  return (
    <div
      role="tablist"
      aria-orientation={vertical ? 'vertical' : 'horizontal'}
      className={
        (vertical
          ? 'flex flex-col gap-0.5'
          : 'flex gap-1 border-b border-hipo-border') + ' ' + className
      }
    >
      {items.map(({ key, label, badge }) => {
        const isActive = value === key;
        return (
          <button
            key={key}
            role="tab"
            aria-selected={isActive}
            data-testid={`tab-${key}`}
            onClick={() => onChange(key)}
            className={
              vertical
                ? (
                  'relative w-full text-left pl-3 pr-2 h-8 rounded-md text-sm ' +
                  'font-medium transition-colors ' +
                  (isActive
                    ? 'text-hipo-blue bg-hipo-blueSoft'
                    : 'text-hipo-slate hover:text-hipo-ink hover:bg-hipo-bg')
                )
                : (
                  'relative px-4 h-11 text-sm font-medium transition-colors ' +
                  (isActive ? 'text-hipo-blue' : 'text-hipo-slate hover:text-hipo-ink')
                )
            }
          >
            <span className={
              'inline-flex items-center gap-2 ' + (vertical ? 'w-full' : '')
            }>
              {label}
              {badge ? (
                <span className={
                  'inline-flex items-center justify-center min-w-[20px] h-5 px-1.5 ' +
                  'rounded-full bg-hipo-danger text-white text-xs font-semibold ' +
                  (vertical ? 'ml-auto' : '')
                }>
                  {badge}
                </span>
              ) : null}
            </span>
            {isActive && (
              vertical
                ? <span className="absolute left-0 top-1 bottom-1 w-0.5 bg-hipo-blue rounded-full" />
                : <span className="absolute left-0 right-0 -bottom-px h-0.5 bg-hipo-blue rounded-full" />
            )}
          </button>
        );
      })}
    </div>
  );
}
