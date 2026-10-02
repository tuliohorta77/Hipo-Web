// web/src/components/crm/AvaliacaoRoteiro.jsx
//
// O scorecard da reunião contra o Roteiro de Vendas (entrega 030).
//
// ── Onde aparece ─────────────────────────────────────────────────────
// Dentro do bloco da transcrição (TranscricaoReuniao), quando ela está
// pronta: a avaliação nasce da conversa e mora ao lado dela. Mesmos três
// lugares da transcrição — modal da tarefa, aba da oportunidade e o
// formulário da reunião na Agenda.
//
// ── O que vem primeiro ───────────────────────────────────────────────
// A nota (x/20), o tempo de fala e o FOCO da próxima reunião: é o que o
// vendedor lê saindo da call. Os pontos fortes e a melhorar vêm logo
// abaixo; os 10 itens ficam numa lista compacta — nota de cada um à vista,
// trecho e sugestão a um clique. É a diretriz do dashboard operacional:
// o número agregado e, no clique, os itens que o compõem.
//
// ── A IA sugere, a gestão ajusta ─────────────────────────────────────
// A nota vale assim que sai (vai para o Monitor). Para a gestão
// (`pode_ajustar`, decidido no servidor), cada item vira um seletor
// 0/1/2 e aparece o botão Validar. O vendedor vê quem ajustou e o selo.
//
// ── Some quando não se aplica ────────────────────────────────────────
// Reunião de parceiro, no-show ou desmarcada: nenhum bloco. Scorecard de
// venda numa reunião que não é venda só ensinaria a ignorar o bloco.

import { useCallback, useEffect, useState } from 'react';
import {
  Award, ChevronDown, ChevronRight, Loader2, RefreshCw, ShieldCheck, Target,
  ThumbsUp, TrendingUp,
} from 'lucide-react';

import api from '../../api';
import AlertMessage from '../ui/AlertMessage';
import Badge from '../ui/Badge';
import { mensagemDeErro } from './tarefaComum';

const TOM_FAIXA = { boa: 'success', media: 'warning', baixa: 'danger' };
const TEXTO_FAIXA = {
  boa: 'text-hipo-success',
  media: 'text-hipo-warning',
  baixa: 'text-hipo-danger',
};

// Nota do item: 0 vermelho, 1 amarelo, 2 verde, sem nota cinza.
const COR_NOTA = {
  0: 'bg-hipo-dangerSoft text-hipo-danger border-hipo-dangerBorder',
  1: 'bg-hipo-warningSoft text-hipo-warning border-hipo-warningBorder',
  2: 'bg-hipo-successSoft text-hipo-success border-hipo-successBorder',
};
const COR_SEM_NOTA = 'bg-hipo-bg text-hipo-muted border-hipo-border';

const BOTAO_PEQUENO =
  'inline-flex items-center gap-1 px-2 py-1 rounded-md text-xs ' +
  'border border-hipo-border bg-hipo-card text-hipo-slate ' +
  'hover:bg-hipo-blueSoft hover:text-hipo-blue hover:border-hipo-blue ' +
  'disabled:opacity-50 transition-colors ' +
  'focus:outline-none focus-visible:ring-2 focus-visible:ring-hipo-blue';

export function formatarNota(n) {
  if (n === null || n === undefined) return '—';
  return Number(n).toLocaleString('pt-BR', { maximumFractionDigits: 1 });
}

function Citacao({ children }) {
  if (!children) return null;
  return (
    <blockquote className="border-l-2 border-hipo-blue pl-2 text-xs italic text-hipo-slate">
      “{children}”
    </blockquote>
  );
}

function SeloNota({ nota, titulo }) {
  return (
    <span
      title={titulo}
      className={
        'inline-flex h-6 min-w-[1.5rem] items-center justify-center rounded border ' +
        'px-1 text-xs font-semibold tabular-nums ' +
        (nota === null || nota === undefined ? COR_SEM_NOTA : COR_NOTA[nota])
      }
    >
      {nota === null || nota === undefined ? '–' : nota}
    </span>
  );
}

function SeletorNota({ item, ocupado, onAjustar }) {
  return (
    <span role="group" aria-label={`Nota do item ${item.item}`} className="inline-flex gap-1">
      {[0, 1, 2].map((n) => {
        const ativa = item.nota === n;
        return (
          <button
            key={n}
            type="button"
            disabled={ocupado}
            aria-pressed={ativa}
            aria-label={`Dar nota ${n} ao item ${item.item}`}
            onClick={(e) => { e.stopPropagation(); if (!ativa) onAjustar(item.item, n); }}
            className={
              'h-6 w-6 rounded border text-xs font-semibold tabular-nums transition-colors ' +
              'focus:outline-none focus-visible:ring-2 focus-visible:ring-hipo-blue ' +
              'disabled:opacity-50 ' +
              (ativa ? COR_NOTA[n] : 'bg-hipo-card text-hipo-muted border-hipo-border hover:border-hipo-blue')
            }
          >
            {n}
          </button>
        );
      })}
    </span>
  );
}

function LinhaItem({ item, podeAjustar, ocupado, onAjustar }) {
  const [aberto, setAberto] = useState(false);
  const ajustado = item.nota_gestor !== null && item.nota_gestor !== undefined;
  return (
    <li className="rounded-md border border-hipo-border bg-hipo-card">
      <div className="flex items-center gap-2 px-2 py-1.5">
        <button
          type="button"
          aria-expanded={aberto}
          onClick={() => setAberto((v) => !v)}
          className={
            'flex min-w-0 flex-1 items-center gap-1.5 text-left text-xs text-hipo-ink ' +
            'focus:outline-none focus-visible:ring-2 focus-visible:ring-hipo-blue rounded'
          }
        >
          {aberto
            ? <ChevronDown size={12} className="shrink-0 text-hipo-slate" aria-hidden="true" />
            : <ChevronRight size={12} className="shrink-0 text-hipo-slate" aria-hidden="true" />}
          <span className="tabular-nums text-hipo-muted">{item.item}.</span>
          <span className="truncate font-medium">{item.nome}</span>
          {ajustado && (
            <span className="shrink-0 text-[10px] text-hipo-blue">ajustada</span>
          )}
        </button>
        {podeAjustar
          ? <SeletorNota item={item} ocupado={ocupado} onAjustar={onAjustar} />
          : (
            <SeloNota
              nota={item.nota}
              titulo={ajustado ? `Nota da gestão (IA deu ${item.nota_ia ?? '–'})` : 'Nota da IA'}
            />
          )}
      </div>

      {aberto && (
        <div className="space-y-1.5 border-t border-hipo-border px-3 py-2 text-xs">
          {item.etapa && <p className="text-hipo-muted">{item.etapa}</p>}
          <Citacao>{item.evidencia}</Citacao>
          {item.descartado && (
            <p className="text-hipo-warning">
              Nota da IA descartada: {item.descartado} O item conta 0 até a gestão avaliar.
            </p>
          )}
          {item.justificativa && <p className="text-hipo-slate">{item.justificativa}</p>}
          {item.sugestao && (
            <p className="text-hipo-ink">
              <span className="font-medium">Na próxima: </span>{item.sugestao}
            </p>
          )}
          {ajustado && (
            <p className="text-hipo-muted">
              Ajustada por {item.ajustada_por_nome || 'gestão'} (a IA deu {item.nota_ia ?? 'sem nota'}).
              {podeAjustar && (
                <button
                  type="button"
                  disabled={ocupado}
                  onClick={() => onAjustar(item.item, null)}
                  className="ml-1 text-hipo-blue hover:underline"
                >
                  Voltar para a nota da IA
                </button>
              )}
            </p>
          )}
          {item.criterios?.length === 3 && (
            <details className="text-hipo-muted">
              <summary className="cursor-pointer">Critério do roteiro</summary>
              <ul className="mt-1 space-y-0.5">
                {item.criterios.map((c, n) => (
                  <li key={n}><span className="font-semibold">{n}:</span> {c}</li>
                ))}
              </ul>
            </details>
          )}
        </div>
      )}
    </li>
  );
}

function ListaPontos({ titulo, Icone, pontos, tom }) {
  if (!pontos?.length) return null;
  return (
    <div className="space-y-1">
      <p className={`flex items-center gap-1 text-xs font-medium ${tom}`}>
        <Icone size={12} aria-hidden="true" />
        {titulo}
      </p>
      <ul className="space-y-1.5">
        {pontos.map((p, i) => (
          <li key={i} className="space-y-0.5 text-sm text-hipo-slate">
            <p>{p.texto}</p>
            <Citacao>{p.evidencia}</Citacao>
            {p.como_fazer && (
              <p className="text-xs text-hipo-ink">
                <span className="font-medium">Como fazer: </span>{p.como_fazer}
              </p>
            )}
          </li>
        ))}
      </ul>
    </div>
  );
}

/**
 * @param tarefa  a tarefa da reunião (precisa de `id`)
 */
export default function AvaliacaoRoteiro({ tarefa }) {
  const [dados, setDados] = useState(null);
  const [carregando, setCarregando] = useState(true);
  const [ocupado, setOcupado] = useState(null);   // 'gerar' | 'validar' | 'item'
  const [erro, setErro] = useState(null);
  const [itensAbertos, setItensAbertos] = useState(false);

  const url = `/crm/agenda/tarefas/${tarefa.id}/avaliacao`;

  const carregar = useCallback(async () => {
    setCarregando(true);
    try {
      const resposta = await api.get(url);
      const data = resposta?.data;
      setDados(data && typeof data === 'object' && data.status ? data : null);
    } catch (err) {
      if (err?.response?.status !== 404) {
        setErro(mensagemDeErro(err, 'Não foi possível carregar o scorecard.'));
      }
      setDados(null);
    } finally {
      setCarregando(false);
    }
  }, [url]);

  useEffect(() => { carregar(); }, [carregar]);

  async function executar(tipo, chamada, padrao) {
    setOcupado(tipo);
    setErro(null);
    try {
      const { data } = await chamada();
      setDados(data);
    } catch (err) {
      setErro(mensagemDeErro(err, padrao));
    } finally {
      setOcupado(null);
    }
  }

  const gerar = () => executar(
    'gerar', () => api.post(`${url}/gerar`), 'Não foi possível avaliar a reunião.',
  );
  const ajustar = (item, nota) => executar(
    'item', () => api.patch(`${url}/itens/${item}`, { nota }),
    'Não foi possível ajustar a nota.',
  );
  const validar = (sim) => executar(
    'validar',
    () => (sim ? api.post(`${url}/validar`) : api.delete(`${url}/validar`)),
    'Não foi possível mudar a validação.',
  );

  if (carregando) return null;
  if (!dados) return erro ? <AlertMessage tipo="erro">{erro}</AlertMessage> : null;
  if (dados.status === 'nao_elegivel') return null;

  const pronta = dados.status === 'pronta';
  const fala = dados.fala_vendedor_pct;
  const falaAcima = fala !== null && fala !== undefined && fala > dados.meta_fala_pct;
  const itens = dados.itens || [];
  const comDois = itens.filter((i) => i.nota === 2).length;

  return (
    <section
      aria-label="Scorecard da reunião"
      className="space-y-2 rounded-md border border-hipo-border bg-hipo-card p-2.5"
    >
      <div className="flex flex-wrap items-center gap-2">
        <Award size={13} className="shrink-0 text-hipo-blue" aria-hidden="true" />
        <span className="text-xs font-medium text-hipo-ink">Scorecard do roteiro</span>
        {pronta && (
          <Badge tone={TOM_FAIXA[dados.faixa] || 'neutral'}>
            <span data-testid="nota-total" className="tabular-nums">
              {dados.nota_total}/{dados.nota_maxima}
            </span>
          </Badge>
        )}
        {pronta && (dados.validada ? (
          <Badge tone="success">
            <ShieldCheck size={12} aria-hidden="true" />
            Validada{dados.validada_por_nome ? ` por ${dados.validada_por_nome}` : ''}
          </Badge>
        ) : (
          <Badge tone="neutral">
            {dados.ajustada ? 'Ajustada pela gestão' : 'Sugestão da IA'}
          </Badge>
        ))}

        <span className="ml-auto flex items-center gap-1.5">
          {pronta && dados.pode_ajustar && (
            <button
              type="button"
              className={BOTAO_PEQUENO}
              disabled={Boolean(ocupado)}
              onClick={() => validar(!dados.validada)}
            >
              <ShieldCheck size={12} aria-hidden="true" />
              {dados.validada ? 'Tirar validação' : 'Validar'}
            </button>
          )}
          {dados.pode_gerar && (
            <button
              type="button"
              className={BOTAO_PEQUENO}
              disabled={Boolean(ocupado)}
              onClick={gerar}
            >
              {ocupado === 'gerar'
                ? <Loader2 size={12} className="animate-spin" aria-hidden="true" />
                : <RefreshCw size={12} aria-hidden="true" />}
              {ocupado === 'gerar'
                ? 'Avaliando… (até 2 min)'
                : pronta ? 'Avaliar de novo' : 'Avaliar agora'}
            </button>
          )}
        </span>
      </div>

      {erro && <AlertMessage tipo="erro">{erro}</AlertMessage>}

      {!pronta && dados.motivo && (
        <p className="flex items-center gap-1 text-xs text-hipo-muted">
          {dados.status === 'aguardando' && (
            <Loader2 size={12} className="animate-spin" aria-hidden="true" />
          )}
          {dados.motivo}
        </p>
      )}

      {dados.erro && (
        <AlertMessage tipo="aviso">
          {pronta ? `A última reavaliação falhou (${dados.erro}). Vale a nota abaixo.` : dados.erro}
        </AlertMessage>
      )}

      {pronta && (
        <>
          <div className="grid grid-cols-3 gap-2">
            <div className="rounded-md border border-hipo-border bg-hipo-bg/40 p-2">
              <p className="text-[11px] text-hipo-muted">Nota</p>
              <p className={`text-lg font-bold tabular-nums ${TEXTO_FAIXA[dados.faixa] || 'text-hipo-ink'}`}>
                {dados.nota_total}
                <span className="text-xs font-normal text-hipo-muted">/{dados.nota_maxima}</span>
              </p>
              <p className="text-[11px] text-hipo-muted">meta {formatarNota(dados.meta)}</p>
            </div>
            <div className="rounded-md border border-hipo-border bg-hipo-bg/40 p-2">
              <p className="text-[11px] text-hipo-muted">Fala do vendedor</p>
              <p
                data-testid="fala-vendedor"
                className={`text-lg font-bold tabular-nums ${falaAcima ? 'text-hipo-warning' : 'text-hipo-ink'}`}
              >
                {fala === null || fala === undefined ? '—' : `${formatarNota(fala)}%`}
              </p>
              <p className="text-[11px] text-hipo-muted">
                {fala === null || fala === undefined
                  ? 'vendedor não identificado'
                  : `ideal até ${formatarNota(dados.meta_fala_pct)}%`}
              </p>
            </div>
            <div className="rounded-md border border-hipo-border bg-hipo-bg/40 p-2">
              <p className="text-[11px] text-hipo-muted">Itens completos</p>
              <p className="text-lg font-bold tabular-nums text-hipo-ink">
                {comDois}<span className="text-xs font-normal text-hipo-muted">/{itens.length}</span>
              </p>
              <p className="text-[11px] text-hipo-muted">com nota 2</p>
            </div>
          </div>

          {dados.foco_proxima && (
            <div className="rounded-md border border-hipo-blueSoft bg-hipo-blueSoft p-2">
              <p className="flex items-center gap-1 text-xs font-medium text-hipo-blueDark">
                <Target size={12} aria-hidden="true" />
                Foco da próxima reunião
              </p>
              <p className="text-sm text-hipo-ink">{dados.foco_proxima}</p>
            </div>
          )}

          {dados.resumo && <p className="text-sm text-hipo-slate">{dados.resumo}</p>}

          <div className="grid gap-3 sm:grid-cols-2">
            <ListaPontos
              titulo="Pontos fortes"
              Icone={ThumbsUp}
              pontos={dados.pontos_fortes}
              tom="text-hipo-success"
            />
            <ListaPontos
              titulo="Pontos a melhorar"
              Icone={TrendingUp}
              pontos={dados.pontos_melhorar}
              tom="text-hipo-warning"
            />
          </div>

          <button
            type="button"
            aria-expanded={itensAbertos}
            onClick={() => setItensAbertos((v) => !v)}
            className={
              'flex items-center gap-1 text-xs text-hipo-blue hover:underline ' +
              'focus:outline-none focus-visible:ring-2 focus-visible:ring-hipo-blue rounded'
            }
          >
            {itensAbertos
              ? <ChevronDown size={12} aria-hidden="true" />
              : <ChevronRight size={12} aria-hidden="true" />}
            {itensAbertos ? 'Esconder os 10 itens' : 'Ver os 10 itens do scorecard'}
          </button>

          {itensAbertos && (
            <ul className="space-y-1" data-testid="itens-scorecard">
              {itens.map((i) => (
                <LinhaItem
                  key={i.item}
                  item={i}
                  podeAjustar={dados.pode_ajustar}
                  ocupado={Boolean(ocupado)}
                  onAjustar={ajustar}
                />
              ))}
            </ul>
          )}

          <p className="text-[11px] text-hipo-muted">
            Avaliação da IA contra o Roteiro de Vendas ({dados.versao_roteiro}); nota sem trecho
            da conversa que a comprove é descartada.
            {dados.pode_ajustar ? ' A gestão pode ajustar cada item.' : ''}
          </p>
        </>
      )}
    </section>
  );
}
