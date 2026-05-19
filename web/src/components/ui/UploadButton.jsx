// web/src/components/ui/UploadButton.jsx
// Botão de upload (label + input file escondido).
// Encapsula o padrão repetido em PEX/POs/BD Ativados/Carteira.

import { Upload, Loader2 } from 'lucide-react';

export default function UploadButton({
  onChange,
  loading = false,
  label = 'Upload',
  accept = '.xlsx',
  variant = 'primary',
  className = '',
  size = 'md',
}) {
  const baseInteractive = loading ? '' : 'cursor-pointer';
  const variants = {
    primary:
      loading
        ? 'bg-hipo-bg text-hipo-muted border border-hipo-border'
        : 'bg-hipo-blue hover:bg-hipo-blueDark text-white',
    secondary:
      loading
        ? 'bg-hipo-bg text-hipo-muted border border-hipo-border'
        : 'bg-hipo-card text-hipo-ink border border-hipo-border hover:bg-hipo-bg',
  };
  const sizes = {
    sm: 'h-9 px-3 text-sm',
    md: 'h-10 px-4 text-sm',
  };

  return (
    <label
      className={
        `inline-flex items-center gap-2 rounded-lg font-medium transition-colors ` +
        `${variants[variant]} ${sizes[size]} ${baseInteractive} ${className}`
      }
    >
      {loading ? (
        <Loader2 size={16} className="animate-spin" />
      ) : (
        <Upload size={16} />
      )}
      <span>{loading ? 'Processando...' : label}</span>
      <input
        type="file"
        accept={accept}
        className="hidden"
        onChange={onChange}
        disabled={loading}
      />
    </label>
  );
}
