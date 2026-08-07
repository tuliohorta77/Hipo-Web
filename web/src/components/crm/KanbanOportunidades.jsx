// web/src/components/crm/KanbanOportunidades.jsx
//
// Kanban do funil: 5 colunas abertas mais a coluna Finalizado.
//
//   Suspect -> Lead -> Qualificação -> Apresentação -> Negociação -> Finalizado
//
// ── Altura ───────────────────────────────────────────────────────────
// O componente ocupa exatamente a altura que o pai der (`h-full`) e NUNCA
// cresce além dela. Quem rola é cada coluna, por dentro. Isso é requisito de
// produto, não estética: com a página inteira rolando, arrastar um cartão da
// primeira para a última coluna exigia rolar durante o arrasto — o auto-scroll
// do HTML5 DnD é irregular e o cartão se perde. Com altura fixa, as seis
// colunas estão sempre visíveis e o arrasto é um gesto só.
//
// Na horizontal a faixa rola quando não couberem as seis colunas na largura
// (`overflow-x-auto` + `min-w` por coluna). Empilhar em duas linhas quebraria
// a altura fixa.
//
// ── Drag and drop ────────────────────────────────────────────────────
// HTML5 nativo, sem biblioteca: o caso aqui é arrastar um cartão entre seis
// colunas. As bibliotecas de DnD resolvem listas aninhadas, reordenação com
// animação e acessibilidade por teclado — nada disso está em jogo, e cada
// dependência nova é mais uma coisa para manter atualizada.
//
// Como o DnD nativo não funciona por teclado, cada cartão aberto tem um
// seletor de fase que faz a mesma coisa.
//
// ── A coluna Finalizado ──────────────────────────────────────────────
// É só leitura e mostra o que fechou no mês. Não aceita cartão solto: soltar
// ali abre o modal de desfecho, porque fechar exige status e motivo. Sem essa
// regra o kanban criaria oportunidade finalizada sem desfecho e o backend
// recusaria com 422. Os cartões dela não têm seletor de fase nem botão
// Finalizar — já acabaram.

import { useState } from 'react';
import { Flag, GripVertical, ThermometerSun, CalendarClock, User } from 'lucide-react';

import Badge from '../ui/Badge';
import Button from '../ui/Button';

const TOM_TEMPERATURA = (t) => {
  if (t === null || t === undefined) return 'neutral';
  if (t >= 70) return 'danger';    // quente
  if (t >= 40) return 'warning';   // morno
  return 'info';                   // frio
};

const TOM_STATUS = {
  conquistado: 'success',
  perdido: 'danger',
  cancelado: 'neutral',
  suspensa: 'warning',
};

function formatarMoeda(v) {
  if (v === null || v === undefined) return null;
  return Number(v).toLocaleString('pt-BR', { style: 'currency', currency: 'BRL' });
}

function formatarData(iso) {
  if (!iso) return null;
  return new Date(iso).toLocaleDateString('pt-BR', { day: '2-digit', month: '2-digit' });
}

function Cartao({
  item, colunasAbertas, somenteLeitura,
  onAbrir, onMover, onDesfecho, arrastando, setArrastando,
}) {
  const evs = (item.envolvidos || []).filter((e) => e.papel === 'EV');
  const valor = formatarMoeda(item.valor_mensalidade);
  const previsao = formatarData(item.previsao_fechamento);

  return (
    <li
      draggable={!somenteLeitura}
      onDragStart={somenteLeitura ? undefined : (e) => {
        e.dataTransfer.setData('text/plain', item.id);
        e.dataTransfer.effectAllowed = 'move';
        setArrastando(item.id);
      }}
      onDragEnd={somenteLeitura ? undefined : () => setArrastando(null)}
      className={
        'bg-hipo-card border border-hipo-border rounded-lg p-2.5 space-y-1.5 ' +
        (somenteLeitura ? 'opacity-90 ' : 'cursor-grab active:cursor-grabbing ') +
        'transition-opacity ' +
        (arrastando === item.id ? 'opacity-40' : 'hover:shadow-md')
      }
    >
      <div className="flex items-start gap-1.5">
        {!somenteLeitura && (
          <GripVertical size={14} className="text-hipo-muted shrink-0 mt-0.5" aria-hidden="true" />
        )}
        <button
          type="button"
          onClick={() => onAbrir(item.id)}
          className="min-w-0 flex-1 text-left"
        >
          <span className="block text-sm font-medium text-hipo-ink truncate">
            {item.conta_razao_social}
          </span>
          <span className="block text-xs font-mono text-hipo-slate">{item.numero}</span>
        </button>
      </div>

      <div className="flex flex-wrap items-center gap-1">
        {valor && <Badge tone="neutral">{valor}</Badge>}
        {!somenteLeitura && item.temperatura !== null && item.temperatura !== undefined && (
          <Badge tone={TOM_TEMPERATURA(item.temperatura)}>
            <span className="inline-flex items-center gap-1">
              <ThermometerSun size={11} />{item.temperatura}
            </span>
          </Badge>
        )}
        {item.status === 'suspensa' && <Badge tone="warning">Suspensa</Badge>}
        {somenteLeitura && (
          <Badge tone={TOM_STATUS[item.status] || 'neutral'}>{item.status}</Badge>
        )}
      </div>

      {!somenteLeitura && (previsao || evs.length > 0) && (
        <div className="flex flex-wrap gap-x-2 gap-y-0.5 text-xs text-hipo-slate">
          {previsao && (
            <span className="inline-flex items-center gap-1">
              <CalendarClock size={11} />{previsao}
            </span>
          )}
          {evs.length > 0 && (
            <span className="inline-flex items-center gap-1 truncate">
              <User size={11} />{evs.map((e) => e.nome).join(', ')}
            </span>
          )}
        </div>
      )}

      {/*
        Cartão finalizado não ganha controles: mover de fase exige reabrir, e
        reabrir é decisão consciente, feita na tela da oportunidade.
      */}
      {!somenteLeitura && (
        <div className="flex items-center gap-1.5 pt-1 border-t border-hipo-border">
          {/* Alternativa por teclado ao arrastar. */}
          <select
            aria-label={`Mover ${item.numero} para outra fase`}
            value={item.fase}
            onChange={(e) => onMover(item.id, e.target.value)}
            className="flex-1 min-w-0 h-7 text-xs rounded border border-hipo-border bg-hipo-card text-hipo-slate px-1"
          >
            {colunasAbertas.map((c) => (
              <option key={c.fase} value={c.fase}>{c.rotulo}</option>
            ))}
          </select>
          <Button
            size="sm"
            variant="ghost"
            icon={Flag}
            onClick={() => onDesfecho(item)}
            aria-label={`Finalizar ${item.numero}`}
          >
            Fechar
          </Button>
        </div>
      )}
    </li>
  );
}

export default function KanbanOportunidades({
  colunas,
  onAbrir,
  onMover,
  onDesfecho,
  carregando,
}) {
  const [arrastando, setArrastando] = useState(null);
  const [alvo, setAlvo] = useState(null);

  const colunasAbertas = colunas.filter((c) => !c.somente_leitura);

  function itemPorId(id) {
    for (const c of colunas) {
      const achado = c.itens.find((i) => i.id === id);
      if (achado) return achado;
    }
    return null;
  }

  function soltar(e, coluna) {
    e.preventDefault();
    setAlvo(null);
    const id = e.dataTransfer.getData('text/plain');
    setArrastando(null);
    if (!id) return;

    const item = itemPorId(id);

    // Soltar na coluna de origem não é uma mudança — e o backend recusaria
    // com "a oportunidade já está nesta fase".
    if (item?.fase === coluna.fase) return;

    // Finalizado não recebe cartão: abre o modal, que pede status e motivo.
    if (coluna.somente_leitura) {
      if (item) onDesfecho(item);
      return;
    }

    onMover(id, coluna.fase);
  }

  if (carregando) {
    return <p className="py-16 text-center text-sm text-hipo-slate">Carregando funil…</p>;
  }

  return (
    <div className="h-full flex gap-3 overflow-x-auto overflow-y-hidden pb-1">
      {colunas.map((coluna) => (
        <section
          key={coluna.fase}
          onDragOver={(e) => { e.preventDefault(); setAlvo(coluna.fase); }}
          onDragLeave={() => setAlvo((a) => (a === coluna.fase ? null : a))}
          onDrop={(e) => soltar(e, coluna)}
          aria-label={`Fase ${coluna.rotulo}`}
          className={
            'flex-1 min-w-[12rem] h-full flex flex-col rounded-xl border p-2 transition-colors ' +
            (alvo === coluna.fase
              ? 'border-hipo-blue bg-hipo-blueSoft/40'
              : coluna.somente_leitura
                ? 'border-dashed border-hipo-border bg-hipo-bg/70'
                : 'border-hipo-border bg-hipo-bg/40')
          }
        >
          <header className="shrink-0 mb-2 px-1">
            <div className="flex items-baseline justify-between gap-2">
              <h3 className="text-sm font-semibold text-hipo-ink truncate">{coluna.rotulo}</h3>
              <span className="text-xs text-hipo-slate">{coluna.quantidade}</span>
            </div>
            {/* Ticket somado da coluna INTEIRA, não só dos cartões visíveis. */}
            <p className="text-xs text-hipo-slate truncate">
              {formatarMoeda(coluna.ticket_total) || 'R$ 0,00'}
              {coluna.somente_leitura && (
                <span className="text-hipo-muted"> ganho no mês</span>
              )}
            </p>
          </header>

          {/*
            O scroll da tela mora aqui. `min-h-0` não é decoração: sem ele o
            flex-item usa a altura do conteúdo como mínimo e a coluna cresce
            para fora do container em vez de rolar.
          */}
          <ul className="flex-1 min-h-0 overflow-y-auto space-y-2 pr-0.5">
            {coluna.itens.length === 0 ? (
              <li className="px-1 py-6 text-center text-xs text-hipo-muted list-none">
                {alvo === coluna.fase
                  ? (coluna.somente_leitura ? 'Solte para finalizar' : 'Solte aqui')
                  : 'Vazio'}
              </li>
            ) : (
              coluna.itens.map((item) => (
                <Cartao
                  key={item.id}
                  item={item}
                  colunasAbertas={colunasAbertas}
                  somenteLeitura={coluna.somente_leitura}
                  onAbrir={onAbrir}
                  onMover={onMover}
                  onDesfecho={onDesfecho}
                  arrastando={arrastando}
                  setArrastando={setArrastando}
                />
              ))
            )}
          </ul>

          {coluna.itens.length < coluna.quantidade && (
            <p className="shrink-0 pt-1.5 text-center text-xs text-hipo-muted">
              +{coluna.quantidade - coluna.itens.length} não exibidas
            </p>
          )}
        </section>
      ))}
    </div>
  );
}
