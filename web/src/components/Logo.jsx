// web/src/components/Logo.jsx
//
// Logo do Hipo — componente isolado e fácil de trocar.
//
// Uso padrão (SVG inline com "H" estilizado):
//   <Logo />
//   <Logo size={40} />
//
// Trocar por imagem no futuro:
//   <Logo src="/logo-hipo.svg" alt="Hipo" />
//
// Para mudar permanentemente: substitua o SVG abaixo OU forneça
// um asset em `public/` e use a prop `src`.

export default function Logo({ size = 32, src, alt = 'Hipo', className = '' }) {
  if (src) {
    return (
      <img
        src={src}
        alt={alt}
        width={size}
        height={size}
        className={className}
      />
    );
  }

  // SVG inline padrão — quadrado arredondado azul com "H" branco.
  return (
    <svg
      xmlns="http://www.w3.org/2000/svg"
      viewBox="0 0 40 40"
      width={size}
      height={size}
      role="img"
      aria-label={alt}
      className={className}
    >
      <rect width="40" height="40" rx="10" fill="#2563EB" />
      <path
        d="M13 11.5h3.2v6.7h7.6v-6.7H27v17h-3.2v-7.3h-7.6v7.3H13z"
        fill="#FFFFFF"
      />
    </svg>
  );
}

// Wordmark "Hipo" — texto ao lado do logo.
// Separado pra você poder usar só o logo em colapsado.
export function LogoWordmark({ className = '' }) {
  return (
    <span
      className={`text-hipo-ink font-bold tracking-tight text-lg ${className}`}
    >
      Hipo
    </span>
  );
}
