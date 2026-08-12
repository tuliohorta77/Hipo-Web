// web/src/components/crm/FunilOportunidades.jsx
//
// A terceira visão das oportunidades: o FUNIL.
//
//   * KANBAN — para trabalhar cartão a cartão.
//   * TABELA — para conferir e comparar linha a linha.
//   * FUNIL  — para ler a FORMA do pipeline: onde ele engorda, onde afunila
//              e em que fase o negócio morre.
//
// ── O que este funil mede (e o que ele NÃO mede) ─────────────────────
// É uma FOTO DO ESTOQUE de hoje: quantas oportunidades abertas estão em cada
// fase agora, e quanto de mensalidade elas somam. Não é conversão histórica —
// para isso seria preciso ler `oportunidade_eventos` e contar quantas
// ENTRARAM em cada fase no período, o que é outro endpoint.
//
// Por isso o número entre duas faixas se chama "passagem" e não "conversão":
// é a razão entre o estoque da fase seguinte e o da atual. Ele responde
// "o funil está equilibrado?", não "quantos por cento eu converto?". A
// distinção está no `title` de cada indicador, porque um vendedor lendo
// "conversão" tomaria decisão sobre um número que não é isso.
//
// A perda por fase, essa sim, é histórica: vem de `perda_por_fase`, que conta
// oportunidades com status 'perdido' pela fase em que morreram. É o sinal de
// vazamento — e por isso fica ao lado da faixa, não escondido num tooltip.
//
// ── Por que tem drawer ───────────────────────────────────────────────
// Diretriz pétrea 2: toda tela é dashboard E ferramenta. Um funil que só
// desenha barras é tela de visualização — dívida técnica por definição.
// Clicar na faixa abre o painel lateral com as oportunidades daquela fase, e
// dali dá para abrir, mover de fase e finalizar sem sair do funil.
//
// O painel busca a lista sob demanda (a faixa carrega só o agregado). Ele
// recarrega sempre que `resumo` troca de identidade — o que a página faz
// depois de cada mover/finalizar —, então a lista nunca fica atrasada em
// relação ao desenho.

import { useCallback, useEffect, useState } from 'react';
import {
  ChevronDown, Flag, ThermometerSun, CalendarClock, User, X, TrendingDown,
} from 'lucide-react';

import api from '../../api';
import Badge from '../ui/Badge';
import Button from '../ui/Button';
import Empty from '../ui/Empty';

// Largura mínima da faixa. Uma fase com 1 oportunidade contra outra com 300
// renderizaria uma tira de meio pixel — invisível e, pior, não clicável.
const LARGURA_MINIMA = 8;

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

function formatarMoedaCompacta(v) {
  const n = Number(v || 0);
  if (n >= 1_000_000) return `R$ ${(n / 1_000_000).toFixed(1).replace('.', ',')}M`;
  if (n >= 1_000) return `R$ ${(n / 1_000).toFixed(1).replace('.', ',')}k`;
  return `R$ ${n.toFixed(0)}`;
}

function formatarData(iso) {
  if (!iso) return null;
  return new Date(iso).toLocaleDateString('pt-BR', { day: '2-digit', month: '2-digit' });
}

function valorDaMetrica(fase, metrica) {
  return metrica === 'ticket' ? Number(fase?.ticket || 0) : Number(fase?.quantidade || 0);
}

/**
 * Percentual de passagem entre duas fases vizinhas, na métrica escolhida.
 *
 * Devolve `null` quando a fase de origem está zerada: dividir por zero daria
 * Infinity, e "∞% de passagem" é pior do que não mostrar nada.
 */
export function passagem(atual, proxima, metrica) {
  const base = valorDaMetrica(atual, metrica);
  if (!base) return null;
  return Math.round((valorDaMetrica(proxima, metrica) / base) * 100);
}

// ── Cartão do painel lateral ─────────────────────────────────────────

function CartaoFunil({ item, fasesAbertas, onAbrir, onMover, onDesfecho }) {
  const evs = (item.envolvidos || []).filter((e) => e.papel === 'EV');
  const valor = formatarMoeda(item.valor_mensalidade);
  const previsao = formatarData(item.previsao_fechamento);

  return (
    <li className="bg-hipo-card border border-hipo-border rounded-lg p-2.5 space-y-1.5">
      <button
        type="button"
        onClick={() => onAbrir(item.id)}
        className="block w-full min-w-0 text-left"
      >
        <span className="block text-sm font-medium text-hipo-ink truncate">
          {item.conta_razao_social}
        </span>
        <span className="block text-xs font-mono text-hipo-slate">{item.numero}</span>
      </button>

      <div className="flex flex-wrap items-center gap-1">
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

      <div className="flex items-center gap-1.5 pt-1 border-t border-hipo-border">
        <select
          aria-label={`Mover ${item.numero} para outra fase`}
          value={item.fase}
          onChange={(e) => onMover(item.id, e.target.value)}
          className="flex-1 min-w-0 h-7 text-xs rounded border border-hipo-border bg-hipo-card text-hipo-slate px-1"
        >
          {fasesAbertas.map((f) => (
            <option key={f.fase} value={f.fase}>{f.rotulo}</option>
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
    </li>
  );
}

// ── Painel lateral ───────────────────────────────────────────────────

function PainelDaFase({
  fase, params, resumo, fasesAbertas, onFechar, onAbrir, onMover, onDesfecho,
}) {
  const [itens, setItens] = useState([]);
  const [total, setTotal] = useState(0);
  const [carregando, setCarregando] = useState(true);
  const [erro, setErro] = useState(null);

  const carregar = useCallback(async () => {
    setCarregando(true);
    setErro(null);
    try {
      const { data } = await api.get('/crm/oportunidades', {
        params: {
          ...params,
          fase: fase.fase,
          apenas_abertas: true,
          ordenar_por: 'temperatura',
          desc: true,
          limit: 100,
        },
      });
      setItens(data.itens);
      setTotal(data.total);
    } catch {
      setErro('Não foi possível carregar as oportunidades desta fase.');
    } finally {
      setCarregando(false);
    }
    // `resumo` entra de propósito: a página troca o objeto a cada recarga do
    // funil, e é isso que mantém o painel em dia depois de mover ou finalizar.
  }, [fase.fase, params, resumo]);

  useEffect(() => { carregar(); }, [carregar]);

  return (
    <aside
      aria-label={`Oportunidades em ${fase.rotulo}`}
      className="w-[21rem] shrink-0 h-full min-h-0 flex flex-col rounded-xl border border-hipo-border bg-hipo-bg/60"
    >
      <header className="shrink-0 flex items-start justify-between gap-2 px-3 py-2 border-b border-hipo-border">
        <div className="min-w-0">
          <h3 className="text-sm font-semibold text-hipo-ink truncate">{fase.rotulo}</h3>
          <p className="text-[11px] text-hipo-slate">
            {fase.quantidade} em aberto · {formatarMoeda(fase.ticket) || 'R$ 0,00'}
          </p>
        </div>
        <button
          type="button"
          onClick={onFechar}
          aria-label="Fechar painel da fase"
          className="h-7 w-7 shrink-0 inline-flex items-center justify-center rounded-lg border border-hipo-border text-hipo-slate hover:bg-hipo-card transition-colors"
        >
          <X size={14} />
        </button>
      </header>

      <div className="flex-1 min-h-0 overflow-y-auto p-2">
        {carregando ? (
          <p className="py-8 text-center text-xs text-hipo-slate">Carregando…</p>
        ) : erro ? (
          <p className="py-8 text-center text-xs text-hipo-danger">{erro}</p>
        ) : itens.length === 0 ? (
          <p className="py-8 text-center text-xs text-hipo-muted">
            Nenhuma oportunidade aberta nesta fase.
          </p>
        ) : (
          <ul className="space-y-1.5">
            {itens.map((item) => (
              <CartaoFunil
                key={item.id}
                item={item}
                fasesAbertas={fasesAbertas}
                onAbrir={onAbrir}
                onMover={onMover}
                onDesfecho={onDesfecho}
              />
            ))}
          </ul>
        )}
      </div>

      {itens.length < total && (
        <p className="shrink-0 px-3 py-1.5 text-center text-[11px] text-hipo-muted border-t border-hipo-border">
          +{total - itens.length} não exibidas
        </p>
      )}
    </aside>
  );
}

// ── Visão ────────────────────────────────────────────────────────────

export default function FunilOportunidades({
  resumo,
  carregando,
  metrica,
  onTrocarMetrica,
  params,
  onAbrir,
  onMover,
  onDesfecho,
}) {
  const [faseAberta, setFaseAberta] = useState(null);

  const fases = resumo?.por_fase || [];
  const perdas = Object.fromEntries(
    (resumo?.perda_por_fase || []).map((p) => [p.fase, p.quantidade])
  );

  const maior = Math.max(...fases.map((f) => valorDaMetrica(f, metrica)), 0);
  const totalQtd = fases.reduce((acc, f) => acc + Number(f.quantidade || 0), 0);
  const totalTicket = fases.reduce((acc, f) => acc + Number(f.ticket || 0), 0);

  // A fase aberta no painel vem sempre do `resumo` mais recente: guardar o
  // objeto no estado deixaria os totais do cabeçalho do painel congelados no
  // que estava na tela quando o usuário clicou.
  const faseSelecionada = fases.find((f) => f.fase === faseAberta) || null;

  if (carregando) {
    return <p className="py-16 text-center text-sm text-hipo-slate">Carregando funil…</p>;
  }

  return (
    <div className="h-full min-h-0 flex gap-2">
      <section
        aria-label="Funil de vendas"
        className="flex-1 min-w-0 h-full min-h-0 flex flex-col rounded-xl border border-hipo-border bg-hipo-card"
      >
        <header className="shrink-0 flex flex-wrap items-center justify-between gap-2 px-3 py-1.5 border-b border-hipo-border">
          <h2 className="text-xs font-semibold text-hipo-ink">
            {totalQtd} em aberto · {formatarMoeda(totalTicket) || 'R$ 0,00'}
          </h2>

          {/*
            O toggle da métrica muda o que dimensiona a faixa, não o que ela
            informa: quantidade e valor aparecem no rótulo nas duas posições.
            Quem escolhe "R$" quer ver onde está o dinheiro; quem fica em
            "Qtd" normalmente tem muita oportunidade sem mensalidade
            preenchida, e o funil por valor mentiria para ele.
          */}
          <div
            role="group"
            aria-label="Dimensionar o funil por"
            className="flex rounded-lg border border-hipo-border overflow-hidden"
          >
            <button
              type="button"
              onClick={() => onTrocarMetrica('quantidade')}
              aria-pressed={metrica === 'quantidade'}
              className={
                'h-7 px-2 text-[11px] transition-colors ' +
                (metrica === 'quantidade'
                  ? 'bg-hipo-blue text-white'
                  : 'bg-hipo-card text-hipo-slate hover:bg-hipo-bg')
              }
            >
              Qtd
            </button>
            <button
              type="button"
              onClick={() => onTrocarMetrica('ticket')}
              aria-pressed={metrica === 'ticket'}
              className={
                'h-7 px-2 text-[11px] transition-colors ' +
                (metrica === 'ticket'
                  ? 'bg-hipo-blue text-white'
                  : 'bg-hipo-card text-hipo-slate hover:bg-hipo-bg')
              }
            >
              R$
            </button>
          </div>
        </header>

        <div className="flex-1 min-h-0 overflow-y-auto px-3 py-3">
          {totalQtd === 0 ? (
            <Empty
              title="Funil vazio"
              description="Nenhuma oportunidade aberta com os filtros atuais."
              icon={TrendingDown}
            />
          ) : (
            <ol className="space-y-0">
              {fases.map((f, i) => {
                const valor = valorDaMetrica(f, metrica);
                const largura = maior > 0
                  ? Math.max(LARGURA_MINIMA, Math.round((valor / maior) * 100))
                  : LARGURA_MINIMA;
                const vazia = Number(f.quantidade || 0) === 0;
                const perdidas = perdas[f.fase] || 0;
                const proxima = fases[i + 1];
                const taxa = proxima ? passagem(f, proxima, metrica) : null;
                const aberta = faseAberta === f.fase;

                return (
                  <li key={f.fase}>
                    <button
                      type="button"
                      onClick={() => setFaseAberta(aberta ? null : f.fase)}
                      aria-expanded={aberta}
                      aria-label={`Ver oportunidades em ${f.rotulo}`}
                      className={
                        'w-full flex items-center gap-3 rounded-lg px-2 py-1.5 text-left ' +
                        'transition-colors focus:outline-none focus-visible:ring-2 ' +
                        'focus-visible:ring-hipo-blue ' +
                        (aberta ? 'bg-hipo-blueSoft' : 'hover:bg-hipo-bg')
                      }
                    >
                      <span className="w-28 shrink-0 text-right">
                        <span className="block text-xs font-medium text-hipo-ink truncate">
                          {f.rotulo}
                        </span>
                        <span className="block text-[10px] text-hipo-slate">
                          {f.quantidade} · {formatarMoedaCompacta(f.ticket)}
                        </span>
                      </span>

                      {/*
                        A faixa é centralizada: é o que dá a silhueta de funil.
                        Alinhada à esquerda viraria gráfico de barras, e a
                        leitura de "afunilamento" se perde.
                      */}
                      <span className="flex-1 min-w-0">
                        <span
                          data-testid={`faixa-${f.fase}`}
                          data-largura={largura}
                          style={{ width: `${largura}%` }}
                          className={
                            'mx-auto h-9 rounded-md flex items-center justify-center ' +
                            'px-2 transition-all ' +
                            (vazia
                              ? 'bg-hipo-bg border border-dashed border-hipo-border text-hipo-muted'
                              : 'bg-hipo-blue text-white') +
                            (aberta ? ' ring-2 ring-hipo-blueDark ring-offset-1' : '')
                          }
                        >
                          <span className="text-xs font-semibold truncate">
                            {metrica === 'ticket'
                              ? formatarMoedaCompacta(f.ticket)
                              : f.quantidade}
                          </span>
                        </span>
                      </span>

                      {/*
                        Perda por fase é histórica e é o sinal de vazamento —
                        fica visível ao lado da faixa, não num tooltip.
                      */}
                      <span className="w-20 shrink-0 text-left">
                        {perdidas > 0 ? (
                          <span
                            title={`${perdidas} oportunidade(s) perdida(s) nesta fase`}
                            className="text-[10px] text-hipo-danger"
                          >
                            −{perdidas} perdidas
                          </span>
                        ) : (
                          <span className="text-[10px] text-hipo-muted">sem perdas</span>
                        )}
                      </span>
                    </button>

                    {proxima && (
                      <div className="flex items-center justify-center py-0.5">
                        <span
                          title={
                            'Razão entre o estoque desta fase e o da seguinte. ' +
                            'Não é conversão histórica — é a leitura do pipeline de hoje.'
                          }
                          className="inline-flex items-center gap-1 text-[10px] text-hipo-slate"
                        >
                          <ChevronDown size={11} aria-hidden="true" />
                          {taxa === null ? '—' : `${taxa}% de passagem`}
                        </span>
                      </div>
                    )}
                  </li>
                );
              })}
            </ol>
          )}
        </div>
      </section>

      {faseSelecionada && (
        <PainelDaFase
          fase={faseSelecionada}
          params={params}
          resumo={resumo}
          fasesAbertas={fases}
          onFechar={() => setFaseAberta(null)}
          onAbrir={onAbrir}
          onMover={onMover}
          onDesfecho={onDesfecho}
        />
      )}
    </div>
  );
}
