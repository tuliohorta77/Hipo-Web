// web/src/components/monitor/QuadroIndicador.jsx
//
// Um quadro do Monitor: sigla, carinha, resultado contra a meta do mês, a
// barra do quanto já foi feito e, embaixo, a meta de HOJE.
//
// ── Por que dois números diferentes no mesmo quadro ──────────────────
// "69 / 276" é o resultado contra a meta do MÊS — é o que a barra desenha e
// o que se leva para a reunião de fechamento. A CARINHA olha outra coisa: o
// resultado contra a meta de HOJE (proporcional aos dias úteis corridos).
// São perguntas diferentes e as duas importam: 25% do mês feito pode ser
// ritmo bom no dia 5 e desastre no dia 25. Por isso a linha "hoje: 160"
// aparece sob a barra — sem ela, a carinha vermelha ao lado de um número
// que parece bom fica sem explicação.
//
// ── Por que o quadro não clica ───────────────────────────────────────
// O Monitor é uma TV: ninguém está com o mouse nela. O drilldown de cada
// indicador vive na tela de origem (funil, agenda, parceiros), e um clique
// que leva a lugar nenhum é pior que nenhum clique.

import {
  TOM_CLASSE, carinhaDe, formatar, larguraDaBarra, pctCurto,
} from './monitorComum';

export default function QuadroIndicador({ indicador }) {
  const {
    sigla, rotulo, fonte, formato, resultado, meta, meta_mtd: metaHoje,
    atingimento_mes: doMes, carinha,
  } = indicador;

  const cara = carinhaDe(carinha);
  const tom = TOM_CLASSE[cara.tom] || TOM_CLASSE.neutro;
  const largura = larguraDaBarra(doMes);

  return (
    <section
      aria-label={rotulo}
      title={fonte}
      className="flex flex-col rounded-xl border border-hipo-border bg-hipo-card overflow-hidden"
    >
      <header className="shrink-0 px-2 py-1.5 bg-hipo-bg border-b border-hipo-border">
        <h3 className="text-center text-sm md:text-base font-bold tracking-wide text-hipo-blue truncate">
          {sigla}
        </h3>
      </header>

      <div className="flex-1 flex flex-col items-center justify-center gap-1 px-2 py-3">
        {/*
          A carinha é o que se lê de longe. `role="img"` com rótulo por
          extenso porque emoji sozinho não é texto para leitor de tela — e
          cor sozinha não carrega informação para quem não distingue tons.
        */}
        <span role="img" aria-label={cara.rotulo} className="text-4xl md:text-5xl leading-none">
          {cara.emoji}
        </span>

        <p className={`text-xl md:text-2xl font-bold tabular-nums ${tom.texto}`}>
          {formatar(resultado, formato)}
          <span className="text-hipo-slate font-medium text-base md:text-lg">
            {' / '}
            {formatar(meta, formato)}
          </span>
        </p>
      </div>

      <div className="shrink-0 px-2 pb-2 space-y-1">
        {/* A barra: quanto da meta do MÊS já foi feito. */}
        <div
          className="h-1.5 w-full rounded-full bg-hipo-bg overflow-hidden"
          role="progressbar"
          aria-valuenow={largura}
          aria-valuemin={0}
          aria-valuemax={100}
          aria-label={`${rotulo}: ${largura}% da meta do mês`}
        >
          <div className={`h-full ${tom.barra}`} style={{ width: `${largura}%` }} />
        </div>

        <p className="flex items-baseline justify-between gap-1 text-[11px] text-hipo-slate">
          <span className="truncate">{rotulo}</span>
          <span className="shrink-0 tabular-nums">
            {doMes === null || doMes === undefined ? '—' : pctCurto(doMes)}
          </span>
        </p>

        {/*
          A meta de hoje só aparece quando existe E quando é diferente da
          meta do mês: em taxa (no-show, ticket médio) as duas são iguais, e
          repetir o mesmo número duas vezes no quadro gastaria a linha.
        */}
        {metaHoje !== null && metaHoje !== undefined && metaHoje !== meta && (
          <p className="text-[11px] text-hipo-muted tabular-nums">
            hoje: {formatar(metaHoje, formato)}
          </p>
        )}
      </div>
    </section>
  );
}
