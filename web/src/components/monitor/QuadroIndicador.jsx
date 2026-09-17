// web/src/components/monitor/QuadroIndicador.jsx
//
// Um quadro do Monitor: sigla, carinha, resultado contra a meta do mês, a
// barra do quanto já foi feito e, embaixo, a meta de HOJE.
//
// ── O quadro fala de RITMO ───────────────────────────────────────────
// O par grande é `resultado / meta de HOJE` e a barra é o atingimento dessa
// meta — a mesma conta da carinha. Antes o par era contra a meta do mês, e
// isso deixava a tela dizendo duas coisas ao mesmo tempo: "16 de 48" com
// carinha triste não se explica sozinho, porque no dia 12 de 21 o que se
// cobra são 27,4 e não 48.
//
// A meta do MÊS não desaparece: vai para a linha pequena ("mês: 48"), que é
// onde ela serve — fechar o mês e comparar com a planilha. Decisão do
// Tulio, 17/09.
//
// ── Por que o quadro não clica ───────────────────────────────────────
// O Monitor é uma TV: ninguém está com o mouse nela. O drilldown de cada
// indicador vive na tela de origem (funil, agenda, parceiros), e um clique
// que leva a lugar nenhum é pior que nenhum clique.

import {
  TOM_CLASSE, carinhaDe, formatar, larguraDaBarra, pctCurto,
} from './monitorComum';

export default function QuadroIndicador({ indicador, grande = false }) {
  const {
    sigla, rotulo, fonte, formato, resultado, meta, meta_mtd: metaHoje,
    atingimento, carinha,
  } = indicador;

  const cara = carinhaDe(carinha);
  const tom = TOM_CLASSE[cara.tom] || TOM_CLASSE.neutro;
  const largura = larguraDaBarra(atingimento);

  return (
    <section
      aria-label={rotulo}
      title={fonte}
      className="flex flex-col rounded-xl border border-hipo-border bg-hipo-card overflow-hidden"
    >
      <header className="shrink-0 px-2 py-1.5 bg-hipo-bg border-b border-hipo-border">
        <h3 className={
          'text-center font-bold tracking-wide text-hipo-blue truncate '
          + (grande ? 'text-xl xl:text-2xl' : 'text-sm md:text-base')
        }>
          {sigla}
        </h3>
      </header>

      <div className="flex-1 flex flex-col items-center justify-center gap-1 px-2 py-3">
        {/*
          A carinha é o que se lê de longe. `role="img"` com rótulo por
          extenso porque emoji sozinho não é texto para leitor de tela — e
          cor sozinha não carrega informação para quem não distingue tons.
        */}
        <span
          role="img"
          aria-label={cara.rotulo}
          className={'leading-none ' + (grande ? 'text-6xl xl:text-7xl' : 'text-4xl md:text-5xl')}
        >
          {cara.emoji}
        </span>

        {/* Resultado contra a meta de HOJE: é o número que a carinha explica. */}
        <p className={
          'font-bold tabular-nums ' + tom.texto + ' '
          + (grande ? 'text-3xl xl:text-4xl' : 'text-xl md:text-2xl')
        }>
          {formatar(resultado, formato)}
          <span className={
            'text-hipo-slate font-medium '
            + (grande ? 'text-xl xl:text-2xl' : 'text-base md:text-lg')
          }>
            {' / '}
            {formatar(metaHoje, formato)}
          </span>
        </p>
      </div>

      <div className="shrink-0 px-2 pb-2 space-y-1">
        {/* A barra: quanto da meta DE HOJE já foi feito. */}
        <div
          className={
            'w-full rounded-full bg-hipo-bg overflow-hidden '
            + (grande ? 'h-2.5' : 'h-1.5')
          }
          role="progressbar"
          aria-valuenow={largura}
          aria-valuemin={0}
          aria-valuemax={100}
          aria-label={`${rotulo}: ${largura}% da meta de hoje`}
        >
          <div className={`h-full ${tom.barra}`} style={{ width: `${largura}%` }} />
        </div>

        <p className={
          'flex items-baseline justify-between gap-1 text-hipo-slate '
          + (grande ? 'text-sm' : 'text-[11px]')
        }>
          <span className="truncate">{rotulo}</span>
          <span className="shrink-0 tabular-nums">
            {atingimento === null || atingimento === undefined
              ? '—' : pctCurto(atingimento)}
          </span>
        </p>

        {/*
          A meta do mês só aparece quando é diferente da meta de hoje: em
          taxa (no-show, ticket médio) as duas são iguais, e repetir o mesmo
          número duas vezes no quadro gastaria a linha.
        */}
        {meta !== null && meta !== undefined && metaHoje !== meta && (
          <p className={
            'text-hipo-muted tabular-nums ' + (grande ? 'text-sm' : 'text-[11px]')
          }>
            mês: {formatar(meta, formato)}
          </p>
        )}
      </div>
    </section>
  );
}
