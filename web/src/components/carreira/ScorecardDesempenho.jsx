// web/src/components/carreira/ScorecardDesempenho.jsx
//
// Carreira · Desempenho · Scorecard das reuniões (só EV).
//
// A nota do roteiro de vendas (0 a 20) das reuniões que a pessoa conduziu
// no mês: a mesma conta do quadro SCORECARD do Monitor, recortada por ela.
// As regras (quais reuniões entram, média, meta, carinha, item mais
// fraco) são do servidor (services/desempenho.py); aqui só se desenha.
//
// As três diretrizes:
//   1. uma tela por função: só aparece para quem é avaliado pelo roteiro;
//   2. dashboard operacional: a média, os 10 itens e a lista; cada reunião
//      abre o MESMO formulário da Agenda, onde está o scorecard completo
//      (trecho, justificativa, sugestão);
//   3. próxima tarefa: o card abre no foco — o item que mais derruba a nota
//      e o "foco para a próxima" da última reunião avaliada.

import { useState } from 'react';
import { Crosshair, ShieldCheck } from 'lucide-react';
import api from '../../api';
import Card, { CardHeader } from '../ui/Card';
import Badge from '../ui/Badge';
import ModalReuniao from '../crm/ModalReuniao';
import { dataCompleta } from '../crm/tarefaComum';
import { TOM_CLASSE, carinhaDe, larguraDaBarra, pctCurto } from '../monitor/monitorComum';

// Mesma régua da tela da reunião e do relatório: 15+ é a meta do roteiro.
export const TOM_FAIXA = { boa: 'success', media: 'warning', baixa: 'danger' };

const BARRA_FAIXA = {
  boa: 'bg-hipo-success', media: 'bg-hipo-warning', baixa: 'bg-hipo-danger',
};

/** Faixa de um item (0 a 2): 1,5+ bom, 1+ médio, abaixo disso baixo. */
export function faixaDoItem(media) {
  if (media === null || media === undefined) return null;
  if (media >= 1.5) return 'boa';
  if (media >= 1) return 'media';
  return 'baixa';
}

function SeloNota({ r }) {
  if (r.nota === null || r.nota === undefined) {
    const texto = { avaliando: 'avaliando…', erro: 'falhou' }[r.nota_status] || 'sem nota';
    return <span className="text-xs text-hipo-muted">{texto}</span>;
  }
  return (
    <span className="inline-flex items-center gap-1">
      <Badge tone={TOM_FAIXA[r.faixa] || 'neutral'}>
        <span className="tabular-nums">{Math.round(r.nota)}/20</span>
      </Badge>
      {r.nota_status === 'validada' && (
        <ShieldCheck size={13} className="text-hipo-success" aria-label="Validada pela gestão" />
      )}
    </span>
  );
}

function Itens({ itens, fraco }) {
  return (
    <ul className="space-y-2" aria-label="Média por item do roteiro">
      {itens.map((i) => {
        const faixa = faixaDoItem(i.media);
        const destaque = fraco && fraco.item === i.item;
        return (
          <li key={i.item} className="grid grid-cols-[1.5rem_1fr_6rem_2.5rem] items-center gap-2" data-testid={`item-${i.item}`}>
            <span className="text-xs text-hipo-muted tabular-nums text-right">{i.item}.</span>
            <span className={`text-sm truncate ${destaque ? 'font-semibold text-hipo-ink' : 'text-hipo-slate'}`} title={i.etapa}>
              {i.nome}
            </span>
            <span className="h-1.5 rounded-full bg-hipo-bg overflow-hidden" aria-hidden="true">
              <span
                className={`block h-full rounded-full ${BARRA_FAIXA[faixa] || 'bg-hipo-border'}`}
                style={{ width: `${larguraDaBarra(i.fracao)}%` }}
              />
            </span>
            <span className="text-xs tabular-nums text-right text-hipo-ink">{i.media === null ? '—' : i.media_txt}</span>
          </li>
        );
      })}
    </ul>
  );
}

function Historico({ historico }) {
  return (
    <div className="flex items-end gap-2 overflow-x-auto" aria-label="Média dos últimos meses">
      {historico.map((h) => (
        <div key={`${h.ano}-${h.mes}`} className="flex-1 min-w-[3.5rem] text-center">
          <div className="h-16 flex items-end justify-center">
            <div
              className={`w-6 rounded-t ${BARRA_FAIXA[h.faixa] || 'bg-hipo-border'}`}
              style={{ height: `${h.media === null ? 4 : Math.max(4, Math.round((h.media / 20) * 64))}px` }}
              aria-hidden="true"
            />
          </div>
          <p className="text-xs font-semibold tabular-nums text-hipo-ink mt-1">{h.media === null ? '—' : h.media_txt}</p>
          <p className="text-[11px] text-hipo-slate capitalize">{h.rotulo}</p>
        </div>
      ))}
    </div>
  );
}

export default function ScorecardDesempenho({ scorecard: s, modoLeitura, onMudou }) {
  const [reuniaoAberta, setReuniaoAberta] = useState(null);
  const [usuarios, setUsuarios] = useState([]);

  function abrir(id) {
    if (usuarios.length === 0) {
      api.get('/crm/dominio/usuarios')
        .then(({ data }) => setUsuarios(Array.isArray(data) ? data : []))
        .catch(() => setUsuarios([]));
    }
    setReuniaoAberta(id);
  }

  const c = carinhaDe(s.carinha);
  const tom = TOM_CLASSE[c.tom] || TOM_CLASSE.neutro;
  const semNota = s.avaliadas === 0;

  return (
    <Card data-testid="scorecard" data-tour="des-scorecard">
      <CardHeader
        title="Scorecard das reuniões"
        hint="Nota do roteiro de vendas (0 a 20) das reuniões com cliente que você conduziu. A mesma conta do quadro SCORECARD do Monitor."
      />

      <div className="grid gap-6 lg:grid-cols-[16rem_1fr]">
        <div className="space-y-4">
          <div>
            <div className="flex items-baseline gap-2">
              <span className={`text-4xl font-semibold tabular-nums ${semNota ? 'text-hipo-muted' : tom.texto}`} data-testid="scorecard-media">
                {s.media_txt}
              </span>
              <span className="text-sm text-hipo-slate">/ {s.nota_maxima}</span>
              {!semNota && <span className="text-2xl ml-auto" aria-label={c.rotulo} title={c.rotulo}>{c.emoji}</span>}
            </div>
            <p className="text-xs text-hipo-slate mt-1">
              meta <strong>{s.meta_txt}</strong>{s.meta_padrao ? ' (padrão do roteiro)' : ''}
              {s.atingimento !== null && s.atingimento !== undefined && <> · {pctCurto(s.atingimento)} da meta</>}
            </p>
            {!semNota && (
              <div className="mt-2 h-1.5 rounded-full bg-hipo-bg overflow-hidden" aria-hidden="true">
                <div className={`h-full rounded-full ${tom.barra}`} style={{ width: `${larguraDaBarra(s.atingimento)}%` }} />
              </div>
            )}
            <p className="text-xs text-hipo-slate mt-2">
              {s.avaliadas} de {s.realizadas} {s.realizadas === 1 ? 'reunião realizada avaliada' : 'reuniões realizadas avaliadas'}
              {s.sem_nota > 0 && <> · as sem nota ficam fora da média</>}
            </p>
          </div>

          {(s.item_fraco || s.foco) && (
            <div className="rounded-lg border border-hipo-warningBorder bg-hipo-warningSoft/40 p-3 space-y-2" data-testid="scorecard-foco">
              <p className="flex items-center gap-1.5 text-xs font-semibold uppercase tracking-wide text-hipo-warning">
                <Crosshair size={13} aria-hidden="true" /> {modoLeitura ? 'Foco' : 'Seu foco'}
              </p>
              {s.item_fraco && (
                <p className="text-sm text-hipo-ink">
                  <strong>{s.item_fraco.nome}</strong> é o item que mais pesa: média {s.item_fraco.media_txt} de 2.
                </p>
              )}
              {s.foco && (
                <p className="text-sm text-hipo-slate">
                  Última reunião{s.foco.empresa ? ` (${s.foco.empresa})` : ''}: “{s.foco.texto}”
                </p>
              )}
            </div>
          )}
        </div>

        <div>
          {semNota ? (
            <p className="text-sm text-hipo-slate py-6 text-center">
              {s.realizadas === 0
                ? 'Nenhuma reunião com cliente realizada neste mês.'
                : 'Nenhuma reunião avaliada ainda. A nota sai quando a transcrição do Meet chega.'}
            </p>
          ) : (
            <Itens itens={s.itens} fraco={s.item_fraco} />
          )}
        </div>
      </div>

      {s.reunioes.length > 0 && (
        <div className="mt-6">
          <p className="text-xs font-semibold uppercase tracking-wide text-hipo-slate mb-2">Reuniões do mês</p>
          <ul className="divide-y divide-hipo-border/60 border-y border-hipo-border/60">
            {s.reunioes.map((r) => (
              <li key={r.reuniao_id}>
                <button
                  type="button"
                  onClick={() => abrir(r.reuniao_id)}
                  className="w-full flex items-center gap-3 py-2 px-1 text-left hover:bg-hipo-bg/60"
                  aria-label={`Abrir reunião com ${r.empresa || 'empresa sem nome'}`}
                >
                  <span className="text-xs tabular-nums text-hipo-slate whitespace-nowrap w-28 shrink-0">{dataCompleta(r.data)}</span>
                  <span className="flex-1 min-w-0">
                    <span className="block text-sm text-hipo-ink truncate">{r.empresa || '—'}</span>
                    {r.oportunidade_numero && <span className="block text-xs text-hipo-slate">{r.oportunidade_numero}</span>}
                  </span>
                  <SeloNota r={r} />
                </button>
              </li>
            ))}
          </ul>
          <p className="text-xs text-hipo-muted mt-1">Clique numa reunião para ver o scorecard completo, item a item.</p>
        </div>
      )}

      {s.historico?.length > 0 && (
        <div className="mt-6">
          <p className="text-xs font-semibold uppercase tracking-wide text-hipo-slate mb-2">Média dos últimos meses</p>
          <Historico historico={s.historico} />
        </div>
      )}

      {reuniaoAberta && (
        <ModalReuniao
          aberto
          nivel={2}
          reuniaoId={reuniaoAberta}
          usuarios={usuarios}
          onFechar={() => { setReuniaoAberta(null); onMudou?.(); }}
          onSalvo={() => onMudou?.()}
        />
      )}
    </Card>
  );
}
