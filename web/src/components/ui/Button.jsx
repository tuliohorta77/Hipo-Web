// web/src/components/ui/Button.jsx
// Botões do Hipo. Altura mínima 40px (acessibilidade).
//
// Variantes:
//   primary:   azul cheio
//   secondary: branco com borda
//   ghost:     transparente, ação discreta
//   danger:    vermelho cheio (ações destrutivas)

import { Loader2 } from 'lucide-react';

const BASE =
  'inline-flex items-center justify-center gap-2 font-medium rounded-lg ' +
  'transition-colors disabled:cursor-not-allowed disabled:opacity-60 ' +
  'focus:outline-none focus-visible:ring-2 focus-visible:ring-hipo-blue focus-visible:ring-offset-2';

const VARIANTS = {
  primary:
    'bg-hipo-blue text-white hover:bg-hipo-blueDark active:bg-hipo-blueDark',
  secondary:
    'bg-hipo-card text-hipo-ink border border-hipo-border hover:bg-hipo-bg',
  ghost: 'bg-transparent text-hipo-slate hover:bg-hipo-bg hover:text-hipo-ink',
  danger: 'bg-hipo-danger text-white hover:opacity-90',
};

const SIZES = {
  sm: 'h-9 px-3 text-sm',
  md: 'h-10 px-4 text-sm',
  lg: 'h-11 px-5 text-base',
};

export default function Button({
  variant = 'primary',
  size = 'md',
  loading = false,
  icon: Icon,
  iconRight: IconRight,
  children,
  className = '',
  disabled,
  ...rest
}) {
  return (
    <button
      disabled={disabled || loading}
      className={`${BASE} ${VARIANTS[variant]} ${SIZES[size]} ${className}`}
      {...rest}
    >
      {loading && <Loader2 size={16} className="animate-spin" />}
      {!loading && Icon && <Icon size={16} />}
      {children}
      {!loading && IconRight && <IconRight size={16} />}
    </button>
  );
}
