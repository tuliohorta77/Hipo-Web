// web/src/components/ui/KpiInline.jsx
//
// KPI de barra: o mesmo dado do KpiCard em 40px de altura, em vez de 110.
//
// Nasceu dentro da tela de Oportunidades na Sprint 4, quando três KpiCard
// empurraram o kanban para baixo da dobra num notebook. A regra de layout das
// telas operacionais é que tudo que não é o conteúdo cabe em ~20% da tela — e
// card de 110px não cabe.
//
// Saiu de lá para cá quando a tela de Parceiros precisou do mesmo componente:
// duas cópias divergiriam no primeiro ajuste de altura, e aí as duas barras
// operacionais deixariam de parecer a mesma coisa.
//
// Quando recebe `onClick`, o KPI é um botão com `aria-pressed` e aplica
// filtro. É isso que faz a diretriz do dashboard operacional valer: o número
// leva à ação, não mora num card grande.

export default function KpiInline({
  label, valor, detalhe, titulo, icone: Icone, tom, ativo, onClick,
}) {
  const conteudo = (
    <>
      <span className={`shrink-0 w-6 h-6 rounded-md grid place-items-center ${tom}`}>
        <Icone size={13} />
      </span>
      <span className="min-w-0 leading-none">
        <span className="block text-[10px] text-hipo-slate truncate">{label}</span>
        <span className="block text-sm font-semibold text-hipo-ink truncate mt-0.5">
          {valor}
          {detalhe && (
            <span className="ml-1 text-[10px] font-normal text-hipo-slate">{detalhe}</span>
          )}
        </span>
      </span>
    </>
  );

  const base =
    'h-10 px-2 flex items-center gap-1.5 rounded-lg border bg-hipo-card ' +
    'max-w-[10.5rem] transition-colors ';

  if (!onClick) {
    return <div title={titulo} className={`${base} border-hipo-border`}>{conteudo}</div>;
  }
  return (
    <button
      type="button"
      onClick={onClick}
      aria-pressed={ativo}
      title={titulo}
      className={
        base + 'text-left focus:outline-none focus-visible:ring-2 focus-visible:ring-hipo-blue ' +
        (ativo ? 'border-hipo-blue ring-1 ring-hipo-blue' : 'border-hipo-border hover:bg-hipo-bg')
      }
    >
      {conteudo}
    </button>
  );
}
