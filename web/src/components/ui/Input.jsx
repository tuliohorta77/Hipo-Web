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

/*
 * Textarea segue o mesmo visual do Input, e a diferença não é estética.
 *
 * Texto que passa de uma linha precisa CABER na tela. Num input de 40px o
 * relato rola para a direita e some: quem escreve "O Marcelo deu retorno
 * via whats informando que encontrou duas clinicas proximas daquele
 * endereco" enxerga o fim da frase e perde o começo, sem jeito de reler o
 * que já digitou sem navegar com as setas. O campo comunica quanto se
 * espera que seja escrito, e um campo apertado ensina a escrever pouco.
 *
 * `resize-y` e não `resize`: crescer na vertical é do usuário, mas a
 * largura pertence ao grid do formulário — arrastar na horizontal
 * atravessa a coluna vizinha e quebra o alinhamento da tela inteira.
 *
 * Passe `id` explícito quando o rótulo tiver pontuação. O id derivado de
 * "O que aconteceu (opcional)" carrega parênteses: legal em HTML5, mas
 * quebra `querySelector('#...')` sem escape — a mesma armadilha que já
 * documentamos no `CamposTarefa` para os rótulos com dois-pontos.
 */
export function Textarea({
  label,
  hint,
  className = '',
  textareaClassName = '',
  id,
  rows = 3,
  ...rest
}) {
  const areaId =
    id || (label ? `txt-${label.toLowerCase().replace(/\s+/g, '-')}` : undefined);
  return (
    <div className={className}>
      {label && (
        <label
          htmlFor={areaId}
          className="block text-sm font-medium text-hipo-ink mb-1.5"
        >
          {label}
        </label>
      )}
      <textarea
        id={areaId}
        rows={rows}
        className={
          'w-full px-3 py-2 rounded-lg bg-hipo-card border border-hipo-border ' +
          'text-hipo-ink text-sm outline-none transition-colors resize-y ' +
          'placeholder:text-hipo-muted ' +
          'focus:border-hipo-blue focus:ring-2 focus:ring-blue-100 ' +
          textareaClassName
        }
        {...rest}
      />
      {hint && <p className="mt-1 text-xs text-hipo-slate">{hint}</p>}
    </div>
  );
}
