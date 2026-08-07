// web/src/components/crm/KanbanOportunidades.jsx
//
// Kanban do funil: 4 colunas abertas, drag-and-drop nativo.
//
// Por que HTML5 drag-and-drop e não uma biblioteca: o caso aqui é arrastar
// um cartão entre 4 colunas. As bibliotecas de DnD resolvem listas aninhadas,
// reordenação com animação e acessibilidade por teclado — nada disso está em
// jogo, e cada dependência nova é mais uma coisa para manter atualizada.
//
// Acessibilidade: como o DnD nativo não funciona por teclado, cada cartão tem
// um seletor de fase que faz a mesma coisa. Quem usa mouse arrasta; quem usa
// teclado escolhe na lista.
//
// A coluna Finalizado NÃO existe aqui. Fechar exige status e motivo, então o
// desfecho é um botão no cartão que abre modal — arrastar para uma coluna
// "Finalizado" criaria registro sem desfecho, e o backend recusa isso com 422.

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

function formatarMoeda(v) {
  if (v === null || v === undefined) return null;
  return Number(v).toLocaleString('pt-BR', { style: 'currency', currency: 'BRL' });
}

function formatarData(iso) {
  if (!iso) return null;
  return new Date(iso).toLocaleDateString('pt-BR', { day: '2-digit', month: '2-digit' });
}

function Cartao({ item, colunas, onAbrir, onMover, onDesfecho, arrastando, setArrastando }) {
  const evs = (item.envolvidos || []).filter((e) => e.papel === 'EV');
  const valor = formatarMoeda(item.valor_mensalidade);
  const previsao = formatarData(item.previsao_fechamento);

  return (
    <li
      draggable
      onDragStart={(e) => {
        e.dataTransfer.setData('text/plain', item.id);
        e.dataTransfer.effectAllowed = 'move';
        setArrastando(item.id);
      }}
      onDragEnd={() => setArrastando(null)}
      className={
        'bg-hipo-card border border-hipo-border rounded-lg p-3 space-y-2 ' +
        'cursor-grab active:cursor-grabbing transition-opacity ' +
        (arrastando === item.id ? 'opacity-40' : 'hover:shadow-md')
      }
    >
      <div className="flex items-start gap-2">
        <GripVertical size={14} className="text-hipo-muted shrink-0 mt-0.5" aria-hidden="true" />
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

      <div className="flex flex-wrap items-center gap-1.5">
        {valor && <Badge tone="neutral">{valor}</Badge>}
        {item.temperatura !== null && item.temperatura !== undefined && (
          <Badge tone={TOM_TEMPERATURA(item.temperatura)}>
            <span className="inline-flex items-center gap-1">
              <ThermometerSun size={11} />{item.temperatura}
            </span>
          </Badge>
        )}
        {item.status === 'suspensa' && <Badge tone="warning">Suspensa</Badge>}
      </div>

      {(previsao || evs.length > 0) && (
        <div className="flex flex-wrap gap-x-3 gap-y-1 text-xs text-hipo-slate">
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

      <div className="flex items-center gap-2 pt-1 border-t border-hipo-border">
        {/* Alternativa por teclado ao arrastar. */}
        <select
          aria-label={`Mover ${item.numero} para outra fase`}
          value={item.fase}
          onChange={(e) => onMover(item.id, e.target.value)}
          className="flex-1 h-8 text-xs rounded border border-hipo-border bg-hipo-card text-hipo-slate px-1.5"
        >
          {colunas.map((c) => (
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
          Finalizar
        </Button>
      </div>
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

  function soltar(e, fase) {
    e.preventDefault();
    setAlvo(null);
    const id = e.dataTransfer.getData('text/plain');
    setArrastando(null);
    if (!id) return;

    // Soltar na coluna de origem não é uma mudança — e o backend recusaria
    // com "a oportunidade já está nesta fase".
    const origem = colunas.find((c) => c.itens.some((i) => i.id === id));
    if (origem?.fase === fase) return;

    onMover(id, fase);
  }

  if (carregando) {
    return <p className="py-16 text-center text-sm text-hipo-slate">Carregando funil…</p>;
  }

  return (
    <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-4 gap-4">
      {colunas.map((coluna) => (
        <section
          key={coluna.fase}
          onDragOver={(e) => { e.preventDefault(); setAlvo(coluna.fase); }}
          onDragLeave={() => setAlvo((a) => (a === coluna.fase ? null : a))}
          onDrop={(e) => soltar(e, coluna.fase)}
          aria-label={`Fase ${coluna.rotulo}`}
          className={
            'rounded-xl border p-3 min-h-[12rem] transition-colors ' +
            (alvo === coluna.fase
              ? 'border-hipo-blue bg-hipo-blueSoft/40'
              : 'border-hipo-border bg-hipo-bg/40')
          }
        >
          <header className="mb-3 px-1">
            <div className="flex items-baseline justify-between gap-2">
              <h3 className="text-sm font-semibold text-hipo-ink">{coluna.rotulo}</h3>
              <span className="text-xs text-hipo-slate">{coluna.quantidade}</span>
            </div>
            {/* Ticket somado da coluna INTEIRA, não só dos cartões visíveis. */}
            <p className="text-xs text-hipo-slate">
              {formatarMoeda(coluna.ticket_total) || 'R$ 0,00'}
            </p>
          </header>

          {coluna.itens.length === 0 ? (
            <p className="px-1 py-6 text-center text-xs text-hipo-muted">
              {alvo === coluna.fase ? 'Solte aqui' : 'Vazio'}
            </p>
          ) : (
            <ul className="space-y-2">
              {coluna.itens.map((item) => (
                <Cartao
                  key={item.id}
                  item={item}
                  colunas={colunas}
                  onAbrir={onAbrir}
                  onMover={onMover}
                  onDesfecho={onDesfecho}
                  arrastando={arrastando}
                  setArrastando={setArrastando}
                />
              ))}
            </ul>
          )}

          {coluna.itens.length < coluna.quantidade && (
            <p className="pt-2 text-center text-xs text-hipo-muted">
              +{coluna.quantidade - coluna.itens.length} não exibidas
            </p>
          )}
        </section>
      ))}
    </div>
  );
}
