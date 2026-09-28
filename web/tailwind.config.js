/** @type {import('tailwindcss').Config} */
// HIPO — Design tokens conforme Manual de Marca v1.0
// Cores nomeadas com prefixo `hipo.*` para clareza e para evitar
// colisão com utilitários do Tailwind padrão.
//
// ── Os tokens são VARIÁVEIS CSS, e não hex fixo ──────────────────────
// O valor de cada cor mora em src/index.css (:root), em canais RGB. Aqui
// cada token só aponta para a variável. Motivo: o tema escuro do Monitor
// (.tema-escuro) redefine as MESMAS variáveis num container, e tudo que
// está dentro dele — quadros, modais, tabelas, formulário da reunião —
// escurece sem nenhum `dark:` espalhado pelos componentes.
//
// O hex do manual está no index.css, ao lado de cada variável. `<alpha-value>` mantém funcionando os
// modificadores de opacidade (bg-hipo-blueSoft/60, bg-hipo-overlay/50).
const v = (nome) => `rgb(var(--hipo-${nome}) / <alpha-value>)`;
export default {
  content: ['./index.html', './src/**/*.{js,jsx}'],
  theme: {
    extend: {
      colors: {
        hipo: {
          blue:        v('blue'),  // Ações principais, links, estados ativos
          blueDark:    v('blueDark'),  // Hover de primário
          blueSoft:    v('blueSoft'),  // Fundo de item ativo, badges informativos
          ink:         v('ink'),  // Títulos e textos de alta importância
          slate:       v('slate'),  // Labels e textos de apoio
          muted:       v('muted'),  // Variante mais clara de slate
          border:      v('border'),  // Bordas e divisórias
          bg:          v('bg'),  // Background geral
          card:        v('card'),  // Superfícies (cards, sidebar, topbar)

          // Cores semânticas (sólidas — texto, ícones, dots)
          success:     v('success'),
          warning:     v('warning'),
          danger:      v('danger'),

          // Variantes "soft" (pastel — fundos de badge, alerts)
          // Cumprem a regra do manual §6: "badges suaves, sem saturação excessiva"
          successSoft: v('successSoft'),  // equivalente a emerald-50
          warningSoft: v('warningSoft'),  // equivalente a amber-50
          dangerSoft:  v('dangerSoft'),  // equivalente a red-50

          // Bordas suaves equivalentes aos -100 do Tailwind, usadas com
          // os fundos soft acima para dar profundidade discreta
          successBorder: v('successBorder'),  // emerald-200 (mais suave que emerald-100 puro)
          warningBorder: v('warningBorder'),  // amber-200
          dangerBorder:  v('dangerBorder'),  // red-200

          // Fundo do overlay dos modais. No claro é o próprio ink; no
          // escuro não pode ser (ink vira texto claro), então tem token
          // próprio.
          overlay:       v('overlay'),
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
