// web/src/pages/carreira/Roleplay.jsx
//
// Carreira · Roleplay com IA. O executivo treina por voz com uma IA no
// papel do cliente; a sessão é gravada (RP-1) e ganha nota (RP-2).
//
// As três diretrizes:
//   1. uma tela por função: cada um vê os cenários do próprio cargo; a
//      gestão abre a de qualquer pessoa em modo leitura (?usuario_id=);
//   2. dashboard operacional: média /20 do mês, treinos, hoje contra o
//      limite; cada cenário tem a melhor nota e o botão de treinar; cada
//      linha do histórico abre a nota com os trechos;
//   3. próxima tarefa: a tela abre no "Seu próximo roleplay".
//
// Libera com o quiz final do roteiro aprovado. Quem decide é o servidor;
// aqui só se mostra o cadeado e o caminho até o quiz.

import { useCallback, useEffect, useState } from 'react';
import { useNavigate, useSearchParams } from 'react-router-dom';
import {
  Award, CalendarDays, Clock, Drama, Lock, Mic, Play, Repeat, Wallet,
} from 'lucide-react';
import api from '../../api';
import PageHeader from '../../components/ui/PageHeader';
import Card, { CardHeader } from '../../components/ui/Card';
import KpiCard from '../../components/ui/KpiCard';
import Badge from '../../components/ui/Badge';
import Button from '../../components/ui/Button';
import AlertMessage from '../../components/ui/AlertMessage';
import Empty from '../../components/ui/Empty';
import { mensagemDeErro } from '../../components/crm/tarefaComum';
import AbasCarreira from '../../components/carreira/AbasCarreira';
import { notaBr } from '../../components/carreira/AvaliacaoRoleplay';

export const DIFICULDADE = { 1: 'Fácil', 2: 'Médio', 3: 'Difícil' };
export const MOTIVO_FIM = {
  encerrou: 'Encerrado', tempo: 'Tempo esgotado', queda: 'Conexão caiu', saldo: 'Crédito de IA acabou',
};

export function dataHoraBr(iso) {
  if (!iso) return '';
  const d = new Date(iso);
  return d.toLocaleString('pt-BR', { day: '2-digit', month: '2-digit', hour: '2-digit', minute: '2-digit' });
}

const TOM_NOTA = (n) => (n >= 15 ? 'success' : n >= 10 ? 'warning' : 'danger');

function NotaHistorico({ s }) {
  if (s.avaliacao_status === 'pronta' && s.nota_total !== null && s.nota_total !== undefined) {
    return <Badge tone={TOM_NOTA(s.nota_total)}>{notaBr(s.nota_total)}/20</Badge>;
  }
  if (s.avaliacao_status === 'aguardando') return <Badge>avaliando…</Badge>;
  return null;
}

export function duracaoBr(seg) {
  if (seg === null || seg === undefined) return '—';
  const m = Math.floor(seg / 60);
  const s = seg % 60;
  return m ? `${m} min ${String(s).padStart(2, '0')} s` : `${s} s`;
}

function CartaoCenario({ c, podeTreinar, onTreinar }) {
  return (
    <li className="px-5 py-4 flex flex-col sm:flex-row sm:items-center gap-3" data-testid={`cenario-${c.id}`}>
      <div className="flex-1 min-w-0">
        <div className="flex flex-wrap items-center gap-2 mb-1">
          <Badge tone={c.formato === 'completa' ? 'warning' : 'info'}>{c.bloco_rotulo}</Badge>
          <Badge>{DIFICULDADE[c.dificuldade]}</Badge>
          <span className="text-xs text-hipo-slate inline-flex items-center gap-1">
            <Clock size={12} aria-hidden="true" /> {c.duracao_alvo_min} min
          </span>
          {c.tentativas > 0 && (
            <span className="text-xs text-hipo-slate">
              {c.tentativas} treino(s) · último {dataHoraBr(c.ultima_em)}
            </span>
          )}
          {c.melhor_nota !== null && c.melhor_nota !== undefined && (
            <Badge tone={TOM_NOTA(c.melhor_nota)}>melhor {notaBr(c.melhor_nota)}/20</Badge>
          )}
        </div>
        <p className="font-medium text-hipo-ink">{c.titulo}</p>
        <p className="text-sm text-hipo-slate mt-0.5">{c.objetivo}</p>
      </div>
      {podeTreinar && (
        <Button size="sm" variant="secondary" icon={Play} onClick={() => onTreinar(c)} aria-label={`Treinar ${c.titulo}`}>
          Treinar
        </Button>
      )}
    </li>
  );
}

export default function Roleplay() {
  const navigate = useNavigate();
  const [params] = useSearchParams();
  const usuarioId = params.get('usuario_id');
  const [dados, setDados] = useState(null);
  const [erro, setErro] = useState('');

  const carregar = useCallback(async () => {
    setErro('');
    try {
      const { data } = await api.get('/carreira/roleplay', { params: usuarioId ? { usuario_id: usuarioId } : {} });
      setDados(data);
    } catch (e) {
      setErro(mensagemDeErro(e, 'Não foi possível carregar o roleplay.'));
    }
  }, [usuarioId]);

  useEffect(() => { carregar(); }, [carregar]);

  if (erro && !dados) {
    return (
      <div className="max-w-6xl mx-auto space-y-5">
        <PageHeader title="Carreira" />
        <AbasCarreira ativa="Roleplay" />
        <AlertMessage tipo="erro">{erro}</AlertMessage>
      </div>
    );
  }
  if (!dados) return <p className="text-sm text-hipo-slate p-4">Carregando…</p>;

  const leitura = dados.modo_leitura;
  const r = dados.resumo;
  const limiteBatido = r.limite_dia > 0 && r.sessoes_hoje >= r.limite_dia;
  const podeTreinar = dados.pode_treinar && dados.disponivel && !limiteBatido;
  const treinar = (c) => navigate(`/carreira/roleplay/treino/${c.id}`);
  const sufixo = usuarioId ? `?usuario_id=${encodeURIComponent(usuarioId)}` : '';

  return (
    <div className="max-w-6xl mx-auto space-y-5">
      <PageHeader
        title={leitura ? `Carreira · ${dados.pessoa.nome}` : 'Carreira'}
        subtitle={leitura
          ? `${dados.pessoa.cargo || 'sem cargo'} · modo leitura`
          : 'Roleplay com IA: treine a reunião por voz com um cliente simulado.'}
      />

      <AbasCarreira ativa="Roleplay" />

      {erro && <AlertMessage tipo="erro">{erro}</AlertMessage>}
      {!dados.disponivel && dados.liberado && (
        <AlertMessage tipo="aviso">{dados.indisponivel_motivo} Avise a gestão.</AlertMessage>
      )}

      {!dados.liberado ? (
        <Card data-testid="roleplay-bloqueado">
          <div className="flex flex-col sm:flex-row sm:items-center gap-4">
            <div className="w-12 h-12 rounded-full bg-hipo-bg flex items-center justify-center shrink-0">
              <Lock size={22} className="text-hipo-slate" aria-hidden="true" />
            </div>
            <div className="flex-1">
              <p className="font-semibold text-hipo-ink">Roleplay bloqueado</p>
              <p className="text-sm text-hipo-slate mt-0.5">{dados.motivo}</p>
            </div>
            {dados.trilha_id && !leitura && (
              <Button onClick={() => navigate(`/uc/trilhas/${dados.trilha_id}/quiz`)}>Ir para o quiz</Button>
            )}
          </div>
        </Card>
      ) : (
        <div className="grid gap-4 grid-cols-1 lg:grid-cols-5">
          <Card className="lg:col-span-3" data-testid="proximo-roleplay">
            <CardHeader title="Seu próximo roleplay" hint={dados.proximo ? dados.proximo.bloco_rotulo : undefined} />
            {dados.proximo ? (
              <div className="space-y-3">
                <p className="text-lg font-semibold text-hipo-ink">{dados.proximo.titulo}</p>
                <p className="text-sm text-hipo-slate">{dados.proximo.objetivo}</p>
                <div className="flex flex-wrap items-center gap-3">
                  {!leitura && (
                    <Button icon={Mic} disabled={!podeTreinar} onClick={() => treinar(dados.proximo)}>
                      Começar
                    </Button>
                  )}
                  <span className="text-xs text-hipo-slate inline-flex items-center gap-1">
                    <Clock size={12} aria-hidden="true" /> {dados.proximo.duracao_alvo_min} min · use fone de ouvido
                  </span>
                </div>
                {limiteBatido && !leitura && (
                  <p className="text-sm text-hipo-warning">
                    Você já fez {r.sessoes_hoje} roleplay(s) hoje, que é o limite. Volte amanhã.
                  </p>
                )}
              </div>
            ) : (
              <Empty icon={Drama} title="Sem cenário para este cargo" />
            )}
          </Card>
          <div className="lg:col-span-2 grid grid-cols-2 gap-4">
            <KpiCard
              label="Média do mês"
              value={r.media_mes !== null && r.media_mes !== undefined ? `${notaBr(r.media_mes)}/20` : '—'}
              hint={r.avaliadas_mes ? `${r.avaliadas_mes} treino(s) avaliado(s) · meta 15` : 'meta 15'}
              icon={Award}
              tone={r.media_mes === null || r.media_mes === undefined ? 'slate' : r.media_mes >= 15 ? 'success' : 'warning'}
            />
            <KpiCard label="Treinos no mês" value={r.sessoes_mes} hint={`${r.minutos_mes} min`} icon={Repeat} />
            <KpiCard
              label="Hoje"
              value={r.limite_dia ? `${r.sessoes_hoje}/${r.limite_dia}` : r.sessoes_hoje}
              icon={CalendarDays}
              tone={limiteBatido ? 'warning' : 'blue'}
            />
            {dados.orcamento ? (
              <KpiCard
                label="IA no mês (todos)"
                value={`US$ ${dados.orcamento.gasto_mes_usd.toFixed(2)}`}
                hint={dados.orcamento.orcamento_mes_usd ? `de US$ ${dados.orcamento.orcamento_mes_usd.toFixed(0)}` : 'sem teto'}
                icon={Wallet}
                tone="slate"
              />
            ) : (
              <KpiCard label="Último treino" value={r.ultima_em ? dataHoraBr(r.ultima_em) : '—'} icon={Clock} tone="slate" />
            )}
          </div>
        </div>
      )}

      <Card padding="none">
        <div className="px-5 pt-5">
          <CardHeader title="Cenários" hint="Blocos de 15 minutos para o dia a dia; a reunião completa é a prova." />
        </div>
        {dados.cenarios.length ? (
          <ul className="divide-y divide-hipo-border">
            {dados.cenarios.map((c) => (
              <CartaoCenario key={c.id} c={c} podeTreinar={podeTreinar && !leitura} onTreinar={treinar} />
            ))}
          </ul>
        ) : (
          <Empty icon={Drama} title="Sem cenário para este cargo" />
        )}
      </Card>

      <Card padding="none">
        <div className="px-5 pt-5">
          <CardHeader title="Histórico" hint="Clique para ver a nota, os trechos e ouvir a gravação." />
        </div>
        {dados.historico.length ? (
          <ul className="divide-y divide-hipo-border">
            {dados.historico.map((s) => (
              <li key={s.id}>
                <button
                  type="button"
                  className="w-full text-left px-5 py-3 flex flex-wrap items-center gap-x-4 gap-y-1 hover:bg-hipo-bg"
                  onClick={() => navigate(`/carreira/roleplay/sessoes/${s.id}${sufixo}`)}
                >
                  <span className="text-sm text-hipo-slate w-28">{dataHoraBr(s.iniciada_em)}</span>
                  <span className="text-sm font-medium text-hipo-ink flex-1 min-w-[12rem]">{s.cenario_titulo}</span>
                  <span className="text-sm text-hipo-slate">{duracaoBr(s.duracao_s)}</span>
                  <NotaHistorico s={s} />
                  {s.status === 'abandonada'
                    ? <Badge tone="warning">Não encerrado</Badge>
                    : <Badge tone={s.motivo_fim === 'encerrou' ? 'success' : 'warning'}>{MOTIVO_FIM[s.motivo_fim] || 'Encerrado'}</Badge>}
                  {!s.conta_media && <Badge>Fora da média</Badge>}
                </button>
              </li>
            ))}
          </ul>
        ) : (
          <Empty icon={Mic} title="Nenhum treino ainda" description="O primeiro roleplay aparece aqui, com a gravação e a transcrição." />
        )}
      </Card>
    </div>
  );
}
