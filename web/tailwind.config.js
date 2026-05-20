/** @type {import('tailwindcss').Config} */
// HIPO — Design tokens conforme Manual de Marca v1.0
// Cores nomeadas com prefixo `hipo.*` para clareza e para evitar
// colisão com utilitários do Tailwind padrão.
export default {
  content: ['./index.html', './src/**/*.{js,jsx}'],
  theme: {
    extend: {
      colors: {
        hipo: {
          blue:        '#2563EB',  // Ações principais, links, estados ativos
          blueDark:    '#1D4ED8',  // Hover de primário
          blueSoft:    '#EFF6FF',  // Fundo de item ativo, badges informativos
          ink:         '#0F172A',  // Títulos e textos de alta importância
          slate:       '#475569',  // Labels e textos de apoio
          muted:       '#64748B',  // Variante mais clara de slate
          border:      '#E2E8F0',  // Bordas e divisórias
          bg:          '#F8FAFC',  // Background geral
          card:        '#FFFFFF',  // Superfícies (cards, sidebar, topbar)

          // Cores semânticas (sólidas — texto, ícones, dots)
          success:     '#16A34A',
          warning:     '#F59E0B',
          danger:      '#DC2626',

          // Variantes "soft" (pastel — fundos de badge, alerts)
          // Cumprem a regra do manual §6: "badges suaves, sem saturação excessiva"
          successSoft: '#ECFDF5',  // equivalente a emerald-50
          warningSoft: '#FFFBEB',  // equivalente a amber-50
          dangerSoft:  '#FEF2F2',  // equivalente a red-50

          // Bordas suaves equivalentes aos -100 do Tailwind, usadas com
          // os fundos soft acima para dar profundidade discreta
          successBorder: '#A7F3D0',  // emerald-200 (mais suave que emerald-100 puro)
          warningBorder: '#FDE68A',  // amber-200
          dangerBorder:  '#FECACA',  // red-200
        },
      },
      fontFamily: {
        sans: [
          'Inter',
          'Manrope',
          'system-ui',
          '-apple-system',
          'BlinkMacSystemFont',
          'Segoe UI',
          'sans-serif',
        ],
      },
      borderRadius: {
        xl: '1rem',       // 16px — cards
        '2xl': '1.25rem', // 20px — cards grandes
      },
      boxShadow: {
        soft: '0 8px 24px rgba(15, 23, 42, 0.04)',
        focus: '0 0 0 3px rgba(37, 99, 235, 0.18)',
      },
      fontSize: {
        // tamanhos canônicos do manual
        kpi: ['2rem',     { lineHeight: '1.2', fontWeight: '700' }], // 32px
        h1:  ['1.625rem', { lineHeight: '1.3', fontWeight: '700' }], // 26px
        h2:  ['1.125rem', { lineHeight: '1.4', fontWeight: '600' }], // 18px
      },
    },
  },
  plugins: [],
}
