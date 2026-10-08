// web/src/components/carreira/AvaliacaoRoleplay.jsx
//
// A nota do roleplay contra o Roteiro de Vendas (RP-2).
//
// Mesma régua do scorecard das reuniões: itens de 0 a 2, cada nota com o
// trecho literal da fala. No bloco de 15 minutos só os itens do bloco
// contam, e a nota vem reescalada para /20 (a tela mostra quais itens).
//
// O que vem primeiro: a nota, o foco do próximo treino e o resumo; depois
// pontos fortes e a melhorar; os itens numa lista compacta. Clicar no
// trecho pula a gravação para aquele momento (quando ela está aberta).
//
// Gestão (pode_ajustar, decidido no servidor): seletor 0/1/2 por item,
// "voltar para a IA", Validar. A nota vale assim que sai — o selo marca
// que a gestão conferiu.
//
// Enquanto a avaliação roda (~1 min), a página consulta de novo sozinha.

import { useState } from 'react';
import {
  ChevronDown, ChevronRight, Loader2, RefreshCw, ShieldCheck, Target, ThumbsUp, TrendingUp,
} from 'lucide-react';
import Badge from '../ui/Badge';
import Button from '../ui/Button';
import AlertMessage from '../ui/AlertMessage';

const TOM_FAIXA = { boa: 'success', media: 'warning', baixa: 'danger' };
const COR_NOTA = {
  0: 'bg-hipo-dangerSoft text-hipo-danger border-hipo-dangerBorder',
  1: 'bg-hipo-warningSoft text-hipo-warning border-hipo-warningBorder',
  2: 'bg-hipo-successSoft text-hipo-success border-hipo-successBorder',
};
const COR_SEM_NOTA = 'bg-hipo-bg text-hipo-muted border-hipo-border';

export function notaBr(n) {
  if (n === null || n === undefined) return '—';
  return Number(n).toFixed(1).replace('.', ',');
}

function normalizar(t) {
  return (t || '').normalize('NFD').replace(/[̀-ͯ]/g, '').toLowerCase()
    .replace(/[^0-9a-z]+/g, ' ').trim();
}

/** Em que momento da conversa o trecho aparece (ms), para pular a gravação. */
export function momentoDoTrecho(trecho, transcricao) {
  const alvo = normalizar((trecho || '').split(/\.{3}|…/)[0]).split(' ').slice(0, 6).join(' ');
  if (!alvo) return null;
  const turno = (transcricao || []).find((t) => normalizar(t.texto).includes(alvo));
  return turno ? turno.t_ms || 0 : null;
}

function Trecho({ texto, transcricao, onPular }) {
  if (!texto) return null;
  const ms = momentoDoTrecho(texto, transcricao);
  return (
    <button
      type="button"
      className="mt-1 text-left text-xs italic text-hipo-slate hover:text-hipo-blue"
      onClick={() => ms !== null && onPular?.(ms)}
      title={ms !== null ? 'Ouvir este trecho' : undefined}
    >
      “{texto}”
    </button>
  );
}

function Item({ it, transcricao, podeAjustar, onAjustar, onPular }) {
  const [aberto, setAberto] = useState(false);
  const cor = it.nota === null || it.nota === undefined ? COR_SEM_NOTA : COR_NOTA[it.nota];
  return (
    <li className="py-2" data-testid={`item-${it.item}`}>
      <div className="flex items-center gap-3">
        <span className={`w-8 h-8 shrink-0 rounded-md border flex items-center justify-center text-sm font-semibold ${cor}`}>
          {it.nota ?? '–'}
        </span>
        <button type="button" className="flex-1 text-left flex items-center gap-1.5 min-w-0" onClick={() => setAberto((v) => !v)}>
          {aberto ? <ChevronDown size={14} /> : <ChevronRight size={14} />}
          <span className="text-sm font-medium text-hipo-ink truncate">{it.item}. {it.nome}</span>
          <span className="text-xs text-hipo-slate hidden sm:inline">· {it.etapa}</span>
        </button>
        {it.ajustada_por && <Badge tone="info">ajustada por {it.ajustada_por}</Badge>}
        {podeAjustar && (
          <div className="flex gap-1" role="group" aria-label={`Nota do item ${it.item}`}>
            {[0, 1, 2].map((n) => (
              <button
                key={n}
                type="button"
                aria-pressed={it.nota === n}
                className={`w-7 h-7 rounded border text-xs ${it.nota === n ? COR_NOTA[n] : 'border-hipo-border text-hipo-slate hover:bg-hipo-bg'}`}
                onClick={() => onAjustar(it.item, n)}
              >
                {n}
              </button>
            ))}
            {it.nota_gestor !== null && it.nota_gestor !== undefined && (
              <button type="button" className="text-xs text-hipo-blue px-1" onClick={() => onAjustar(it.item, null)}>
                IA
              </button>
            )}
          </div>
        )}
      </div>
      {aberto && (
        <div className="ml-11 mt-1 space-y-1 text-sm">
          {it.descartado && <p className="text-xs text-hipo-warning">{it.descartado}</p>}
          {it.justificativa && <p className="text-hipo-ink">{it.justificativa}</p>}
          <Trecho texto={it.evidencia} transcricao={transcricao} onPular={onPular} />
          {it.sugestao && <p className="text-hipo-slate"><b>Próxima vez:</b> {it.sugestao}</p>}
          <p className="text-xs text-hipo-muted">Nota 2: {it.criterio_2}</p>
        </div>
      )}
    </li>
  );
}

export default function AvaliacaoRoleplay({
  avaliacao, transcricao, onReavaliar, onAjustar, onValidar, onPular, ocupado,
}) {
  if (!avaliacao) return null;
  const a = avaliacao;

  if (a.status === 'aguardando') {
    return (
      <p className="flex items-center gap-2 text-sm text-hipo-slate" data-testid="avaliando">
        <Loader2 size={16} className="animate-spin" /> Avaliando contra o Roteiro de Vendas… leva cerca de 1 minuto.
      </p>
    );
  }
  if (a.status === 'sem_conteudo' || a.status === 'erro') {
    return (
      <div className="space-y-3">
        <AlertMessage tipo={a.status === 'erro' ? 'erro' : 'info'}>{a.erro}</AlertMessage>
        {a.pode_reavaliar && (
          <Button variant="secondary" icon={RefreshCw} loading={ocupado} onClick={onReavaliar}>Avaliar de novo</Button>
        )}
      </div>
    );
  }

  return (
    <div className="space-y-5" data-testid="avaliacao-roleplay">
      <div className="flex flex-wrap items-center gap-3">
        <span className="text-kpi text-hipo-ink">{notaBr(a.nota_total)}<span className="text-base text-hipo-slate">/{a.nota_maxima}</span></span>
        <Badge tone={TOM_FAIXA[a.faixa] || 'neutral'}>
          {a.faixa === 'boa' ? 'Na meta' : a.faixa === 'media' ? 'Quase lá' : 'Abaixo da meta'}
        </Badge>
        {a.validada && <Badge tone="success"><ShieldCheck size={12} /> Validada pela gestão</Badge>}
        <div className="flex-1" />
        {a.pode_reavaliar && (
          <Button size="sm" variant="ghost" icon={RefreshCw} loading={ocupado} onClick={onReavaliar}>Avaliar de novo</Button>
        )}
        {a.pode_validar && (
          a.validada
            ? <Button size="sm" variant="secondary" onClick={() => onValidar(false)}>Tirar validação</Button>
            : <Button size="sm" icon={ShieldCheck} onClick={() => onValidar(true)}>Validar</Button>
        )}
      </div>

      {a.foco_proxima && (
        <div className="rounded-lg bg-hipo-blueSoft px-4 py-3 text-sm text-hipo-blueDark flex gap-2">
          <Target size={16} className="shrink-0 mt-0.5" /> <span><b>Foco do próximo treino:</b> {a.foco_proxima}</span>
        </div>
      )}
      {a.resumo && <p className="text-sm text-hipo-ink">{a.resumo}</p>}

      <div className="grid gap-4 sm:grid-cols-2">
        <div>
          <p className="text-sm font-semibold text-hipo-ink flex items-center gap-1.5 mb-1"><ThumbsUp size={14} /> Pontos fortes</p>
          {a.pontos_fortes.length ? a.pontos_fortes.map((p, i) => (
            <div key={i} className="text-sm mb-2">
              <p className="text-hipo-ink">{p.texto}</p>
              <Trecho texto={p.evidencia} transcricao={transcricao} onPular={onPular} />
            </div>
          )) : <p className="text-sm text-hipo-slate">—</p>}
        </div>
        <div>
          <p className="text-sm font-semibold text-hipo-ink flex items-center gap-1.5 mb-1"><TrendingUp size={14} /> A melhorar</p>
          {a.pontos_melhorar.length ? a.pontos_melhorar.map((p, i) => (
            <div key={i} className="text-sm mb-2">
              <p className="text-hipo-ink">{p.texto}</p>
              {p.como_fazer && <p className="text-hipo-slate"><b>Como:</b> {p.como_fazer}</p>}
              <Trecho texto={p.evidencia} transcricao={transcricao} onPular={onPular} />
            </div>
          )) : <p className="text-sm text-hipo-slate">—</p>}
        </div>
      </div>

      <div>
        <p className="text-sm font-semibold text-hipo-ink mb-1">
          Itens do roteiro neste treino ({a.itens.length})
        </p>
        <ul className="divide-y divide-hipo-border">
          {a.itens.map((it) => (
            <Item key={it.item} it={it} transcricao={transcricao} podeAjustar={a.pode_ajustar}
              onAjustar={onAjustar} onPular={onPular} />
          ))}
        </ul>
      </div>
    </div>
  );
}
