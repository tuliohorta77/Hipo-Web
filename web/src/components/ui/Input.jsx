// web/src/components/ui/Input.jsx
// Input do Hipo: branco, borda fina, foco azul.
// Altura 40px (acessibilidade — Manual §9).
//
// v2 (etapa 2a do v1.2.0): adiciona suporte opcional a prop `icon`.
// Quando `icon` é passado (componente lucide-react), renderiza ícone
// dentro da borda no canto esquerdo e adiciona padding-left ao input.

export default function Input({
  label,
  hint,
  error,
  icon: Icon,
  className = '',
  inputClassName = '',
  id,
  ...rest
}) {
  const inputId =
    id || (label ? `inp-${label.toLowerCase().replace(/\s+/g, '-')}` : undefined);

  const paddingLeft = Icon ? 'pl-9' : 'px-3';
  const paddingRight = 'pr-3';

  return (
    <div className={className}>
      {label && (
        <label
          htmlFor={inputId}
          className="block text-sm font-medium text-hipo-ink mb-1.5"
        >
          {label}
        </label>
      )}
      <div className="relative">
        {Icon && (
          <span
            className="absolute left-3 top-1/2 -translate-y-1/2 text-hipo-muted pointer-events-none"
            aria-hidden="true"
          >
            <Icon size={14} />
          </span>
        )}
        <input
          id={inputId}
          className={
            `w-full h-10 ${paddingLeft} ${paddingRight} rounded-lg bg-hipo-card border outline-none ` +
            'placeholder:text-hipo-muted text-hipo-ink text-sm ' +
            'transition-colors ' +
            (error
              ? 'border-hipo-danger focus:border-hipo-danger focus:ring-2 focus:ring-red-100 '
              : 'border-hipo-border focus:border-hipo-blue focus:ring-2 focus:ring-blue-100 ') +
            inputClassName
          }
          {...rest}
        />
      </div>
      {error && (
        <p className="mt-1 text-xs text-hipo-danger">{error}</p>
      )}
      {hint && !error && (
        <p className="mt-1 text-xs text-hipo-slate">{hint}</p>
      )}
    </div>
  );
}

// Select segue o mesmo visual do Input
export function Select({
  label,
  children,
  className = '',
  selectClassName = '',
  id,
  ...rest
}) {
  const selectId =
    id || (label ? `sel-${label.toLowerCase().replace(/\s+/g, '-')}` : undefined);
  return (
    <div className={className}>
      {label && (
        <label
          htmlFor={selectId}
          className="block text-sm font-medium text-hipo-ink mb-1.5"
        >
          {label}
        </label>
      )}
      <select
        id={selectId}
        className={
          'w-full h-10 px-3 rounded-lg bg-hipo-card border border-hipo-border ' +
          'text-hipo-ink text-sm outline-none transition-colors ' +
          'focus:border-hipo-blue focus:ring-2 focus:ring-blue-100 ' +
          selectClassName
        }
        {...rest}
      >
        {children}
      </select>
    </div>
  );
}
