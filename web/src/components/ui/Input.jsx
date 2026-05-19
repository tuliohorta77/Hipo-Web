// web/src/components/ui/Input.jsx
// Input do Hipo: branco, borda fina, foco azul.
// Altura 40px (acessibilidade — Manual §9).

export default function Input({
  label,
  hint,
  error,
  className = '',
  inputClassName = '',
  id,
  ...rest
}) {
  const inputId =
    id || (label ? `inp-${label.toLowerCase().replace(/\s+/g, '-')}` : undefined);

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
      <input
        id={inputId}
        className={
          'w-full h-10 px-3 rounded-lg bg-hipo-card border outline-none ' +
          'placeholder:text-hipo-muted text-hipo-ink text-sm ' +
          'transition-colors ' +
          (error
            ? 'border-hipo-danger focus:border-hipo-danger focus:ring-2 focus:ring-red-100 '
            : 'border-hipo-border focus:border-hipo-blue focus:ring-2 focus:ring-blue-100 ') +
          inputClassName
        }
        {...rest}
      />
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
