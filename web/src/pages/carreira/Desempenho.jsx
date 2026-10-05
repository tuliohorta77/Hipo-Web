// web/src/pages/carreira/Desempenho.jsx
//
// Carreira · Desempenho: o mês de cada pessoa contra a meta dela.
//
// Os números são os da RPeR (mesma conta, services/rper.py) e as metas são
// as que a gestão grava em Monitor › RPeR › "Metas por squad e pessoa".
// O colaborador vê, antes da reunião, exatamente o que vai ser discutido
// nela.
//
// As três diretrizes:
//   1. uma tela por função: os indicadores e o funil são os do squad da
//      pessoa (SDR, EV ou EC);
//   2. dashboard operacional: cada indicador tem o atalho para a tela onde
//      se age sobre ele;
//   3. próxima tarefa: a tela abre no "ponto de atenção", o indicador que
//      mais pede ação agora, com quanto falta e onde agir.
//
// As REGRAS (meta de hoje, atingimento, carinha) são do servidor; aqui só
// se desenha. A gestão escolhe a pessoa e vê em modo leitura.

import { useCallback, useEffect, useState } from 'react';
import { useNavigate, useSearchParams } from 'react-router-dom';
import {
  ArrowRight, ChevronLeft, ChevronRight, AlertTriangle, CalendarDays,
} from 'lucide-react';
import api from '../../api';
import PageHeader from '../../components/ui/PageHeader';
import Card, { CardHeader } from '../../components/ui/Card';
import Button from '../../components/ui/Button';
import AlertMessage from '../../components/ui/AlertMessage';
import Empty from '../../components/ui/Empty';
import { mensagemDeErro } from '../../components/crm/tarefaComum';
import AbasCarreira from '../../components/carreira/AbasCarreira';
import {
  TOM_CLASSE, carinhaDe, larguraDaBarra, pctCurto,
} from '../../components/monitor/monitorComum';

// Onde se age sobre cada indicador. Indicador fora da tabela não ganha
// atalho (melhor nenhum botão do que um que leva à tela errada).
const TELA = {
  agenda: { rota: '/crm/agenda', nome: 'Agenda' },
  tarefas: { rota: '/crm/tarefas', nome: 'Tarefas' },
  oportunidades: { rota: '/crm/oportunidades', nome: 'Oportunidades' },
  parceiros: { rota: '/crm/parceiros', nome: 'Parceiros' },
  prospeccao: { rota: '/crm/prospeccao', nome: 'Prospecção' },
};

export const ONDE_AGIR = {
  SDR: {
    agendamentos: 'agenda', reunioes_realizadas: 'agenda', noshow: 'agenda',
    leads: 'oportunidades', tarefas: 'tarefas', contas: 'prospeccao',
    taxa_execucao: 'tarefas', pipeline_gerado: 'oportunidades', nmrr: 'oportunidades',
  },
  EV: {
    followups: 'tarefas', taxa_execucao: 'tarefas', oportunidades: 'tarefas',
    propostas: 'oportunidades', reunioes_realizadas: 'agenda', vendas: 'oportunidades',
    taxa_conversao: 'oportunidades', nmrr: 'oportunidades', ticket_medio: 'oportunidades',
    em_negociacao: 'oportunidades', pipeline: 'oportunidades',
  },
  EC: {
    contas_gestao: 'parceiros', reunioes_carteira: 'agenda', parcerias: 'parceiros',
    leads: 'oportunidades', tarefas: 'tarefas', taxa_execucao: 'tarefas',
    vendas: 'oportunidades', mrr: 'oportunidades',
  },
};

export function telaDoIndicador(squad, chave) {
  const t = ONDE_AGIR[squad]?.[chave];
  return t ? TELA[t] : null;
}

export function mesVizinho(ano, mes, passo) {
  const m = mes + passo;
  if (m < 1) return { ano: ano - 1, mes: 12 };
  if (m > 12) return { ano: ano + 1, mes: 1 };
  return { ano, mes: m };
}

function Atingimento({ linha }) {
  const c = carinhaDe(linha.carinha);
  const tom = TOM_CLASSE[c.tom] || TOM_CLASSE.neutro;
  if (linha.atingimento === null || linha.atingimento === undefined) {
    return <span className="text-xs text-hipo-muted">sem meta</span>;
  }
  return (
    <div className="flex items-center gap-2 min-w-[9rem]">
      <span aria-label={c.rotulo} title={c.rotulo}>{c.emoji}</span>
      <div className="flex-1 h-1.5 rounded-full bg-hipo-bg overflow-hidden" aria-hidden="true">
        <div className={`h-full rounded-full ${tom.barra}`} style={{ width: `${larguraDaBarra(linha.atingimento)}%` }} />
      </div>
      <span className={`text-sm font-semibold tabular-nums ${tom.texto}`}>{pctCurto(linha.atingimento)}</span>
    </div>
  );
}

function CartaoPrincipal({ linha, aberto }) {
  const c = carinhaDe(linha.carinha);
  const tom = TOM_CLASSE[c.tom] || TOM_CLASSE.neutro;
  return (
    <Card padding="md">
      <div className="flex items-start justify-between gap-2">
        <p className="text-xs font-semibold uppercase tracking-wide text-hipo-slate">{linha.rotulo}</p>
        <span className="text-xl" aria-label={c.rotulo} title={c.rotulo}>{c.emoji}</span>
      </div>
      <p className={`text-2xl font-semibold tabular-nums mt-1 ${tom.texto}`}>{linha.realizado_txt}</p>
      <p className="text-xs text-hipo-slate mt-1">
        {linha.meta_mes_txt
          ? <>meta {aberto && linha.meta_hoje_txt ? <>de hoje <strong>{linha.meta_hoje_txt}</strong> · do mês </> : 'do mês '}<strong>{linha.meta_mes_txt}</strong></>
          : 'sem meta cadastrada'}
      </p>
      {linha.atingimento !== null && linha.atingimento !== undefined && (
        <div className="mt-2 h-1.5 rounded-full bg-hipo-bg overflow-hidden" aria-hidden="true">
          <div className={`h-full rounded-full ${tom.barra}`} style={{ width: `${larguraDaBarra(linha.atingimento)}%` }} />
        </div>
      )}
    </Card>
  );
}

function Funil({ etapas }) {
  return (
    <div className="flex flex-col md:flex-row md:items-stretch gap-2">
      {etapas.map((e, i) => (
        <div key={e.chave} className="flex flex-col md:flex-row md:items-center gap-2 flex-1">
          {i > 0 && (
            <div className="flex md:flex-col items-center justify-center gap-1 px-1 text-center md:w-28 shrink-0">
              <ArrowRight size={16} className="text-hipo-muted rotate-90 md:rotate-0" aria-hidden="true" />
              <span className="text-sm font-semibold text-hipo-ink tabular-nums">{e.taxa_txt}</span>
              <span className="text-[11px] leading-tight text-hipo-slate">{e.taxa_rotulo}</span>
            </div>
          )}
          <div className="flex-1 rounded-lg border border-hipo-border bg-hipo-bg/40 px-3 py-3 text-center">
            <p className="text-2xl font-semibold text-hipo-ink tabular-nums">{e.valor_txt}</p>
            <p className="text-xs text-hipo-slate mt-0.5">{e.rotulo}</p>
          </div>
        </div>
      ))}
    </div>
  );
}

function Historico({ historico, indicadores }) {
  const linhas = indicadores.filter((l) => !l.posicao);
  return (
    <div className="overflow-x-auto">
      <table className="w-full text-sm">
        <thead>
          <tr className="text-left text-xs text-hipo-slate border-b border-hipo-border">
            <th className="py-2 pr-3 font-medium">Indicador</th>
            {historico.map((h) => (
              <th key={`${h.ano}-${h.mes}`} className="py-2 px-2 font-medium capitalize text-right">{h.rotulo}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {linhas.map((l) => (
            <tr key={l.chave} className="border-b border-hipo-border/60">
              <td className="py-2 pr-3 text-hipo-ink">{l.rotulo}</td>
              {historico.map((h) => {
                const item = h.indicadores[l.chave];
                const ating = item?.atingimento;
                const tom = ating === null || ating === undefined
                  ? 'text-hipo-muted'
                  : ating >= 1 ? 'text-hipo-success' : ating >= 0.7 ? 'text-hipo-warning' : 'text-hipo-danger';
                return (
                  <td key={`${h.ano}-${h.mes}`} className="py-2 px-2 text-right tabular-nums">
                    <span className="block text-hipo-ink">{item?.realizado_txt ?? '—'}</span>
                    {item?.atingimento_txt && <span className={`block text-xs ${tom}`}>{item.atingimento_txt}</span>}
                  </td>
                );
              })}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

export default function Desempenho() {
  const navigate = useNavigate();
  const [params, setParams] = useSearchParams();
  const usuarioId = params.get('usuario_id');
  const ano = params.get('ano');
  const mes = params.get('mes');

  const [dados, setDados] = useState(null);
  const [erro, setErro] = useState('');

  const carregar = useCallback(async () => {
    setErro('');
    try {
      const p = {};
      if (usuarioId) p.usuario_id = usuarioId;
      if (ano && mes) { p.ano = ano; p.mes = mes; }
      const { data } = await api.get('/carreira/desempenho', { params: p });
      setDados(data);
    } catch (e) {
      setErro(mensagemDeErro(e, 'Não foi possível carregar o desempenho.'));
    }
  }, [usuarioId, ano, mes]);

  useEffect(() => { carregar(); }, [carregar]);

  function irPara(mudancas) {
    const p = new URLSearchParams(params);
    Object.entries(mudancas).forEach(([k, v]) => (v === null || v === '' ? p.delete(k) : p.set(k, String(v))));
    setParams(p);
  }

  const cabecalho = (
    <>
      <PageHeader
        title={dados?.modo_leitura ? `Carreira · ${dados.pessoa.nome}` : 'Carreira'}
        subtitle={dados?.modo_leitura ? `${dados.pessoa.cargo || 'sem cargo'} · modo leitura` : 'Seu desempenho contra as suas metas do mês.'}
      />
      <AbasCarreira ativa="Desempenho" />
    </>
  );

  if (erro && !dados) {
    return <div className="max-w-6xl mx-auto space-y-4">{cabecalho}<AlertMessage tipo="erro">{erro}</AlertMessage></div>;
  }
  if (!dados) {
    return <div className="max-w-6xl mx-auto space-y-4">{cabecalho}<p className="text-sm text-hipo-slate p-4">Carregando…</p></div>;
  }

  const anterior = mesVizinho(dados.ano, dados.mes, -1);
  const seguinte = mesVizinho(dados.ano, dados.mes, 1);
  const naoHaSeguinte = dados.aberto;
  const principais = dados.indicadores.filter((l) => l.principal);
  const atencao = dados.ponto_de_atencao;
  const telaAtencao = atencao ? telaDoIndicador(dados.squad, atencao.chave) : null;

  return (
    <div className="max-w-6xl mx-auto space-y-5">
      {cabecalho}

      <div className="flex flex-wrap items-center gap-3">
        <div className="flex items-center gap-1" data-tour="des-mes">
          <Button
            size="sm" variant="ghost" icon={ChevronLeft} aria-label="Mês anterior"
            onClick={() => irPara({ ano: anterior.ano, mes: anterior.mes })}
          />
          <span className="text-sm font-semibold text-hipo-ink capitalize min-w-[9rem] text-center" data-testid="mes-desempenho">
            {dados.rotulo}
          </span>
          <Button
            size="sm" variant="ghost" icon={ChevronRight} aria-label="Próximo mês"
            disabled={naoHaSeguinte}
            onClick={() => {
              const atual = dados.mes_atual;
              const ehAtual = seguinte.ano === atual.ano && seguinte.mes === atual.mes;
              irPara(ehAtual ? { ano: null, mes: null } : { ano: seguinte.ano, mes: seguinte.mes });
            }}
          />
        </div>
        {dados.aberto && dados.dia_util !== null && (
          <span className="inline-flex items-center gap-1 text-xs text-hipo-slate">
            <CalendarDays size={13} aria-hidden="true" />
            dia útil {dados.dia_util} de {dados.dias_uteis} · a meta de hoje acompanha esse ritmo
          </span>
        )}
        {!dados.aberto && <span className="text-xs text-hipo-slate">mês fechado · comparado com a meta do mês inteiro</span>}

        {dados.pode_escolher_pessoa && (
          <label className="ml-auto text-sm text-hipo-slate inline-flex items-center gap-2">
            Pessoa
            <select
              aria-label="Pessoa"
              className="h-9 rounded-lg border border-hipo-border bg-hipo-card px-2 text-sm text-hipo-ink"
              value={usuarioId || ''}
              onChange={(e) => irPara({ usuario_id: e.target.value || null })}
            >
              <option value="">Eu</option>
              {dados.pessoas.map((p) => (
                <option key={p.id} value={p.id}>{p.nome} · {p.cargo}</option>
              ))}
            </select>
          </label>
        )}
      </div>

      {erro && <AlertMessage tipo="erro">{erro}</AlertMessage>}

      {!dados.squad ? (
        <Card>
          <Empty
            title="Este cargo não tem metas individuais na RPeR"
            description="O Desempenho mostra os indicadores de SDR, EV e EC contra as metas de cada pessoa. A gestão pode escolher a pessoa no seletor acima."
          />
        </Card>
      ) : (
        <>
          {atencao && (
            <Card padding="md" className="border-hipo-warningBorder bg-hipo-warningSoft/40" data-testid="ponto-de-atencao" data-tour="des-atencao">
              <div className="flex flex-col sm:flex-row sm:items-center gap-3">
                <AlertTriangle size={20} className="text-hipo-warning shrink-0" aria-hidden="true" />
                <div className="flex-1">
                  <p className="text-sm font-semibold text-hipo-ink">
                    {dados.modo_leitura ? 'Ponto de atenção' : 'Seu ponto de atenção'}: {atencao.rotulo}
                  </p>
                  <p className="text-sm text-hipo-slate">
                    Está em <strong>{pctCurto(atencao.atingimento)}</strong> da meta{dados.aberto && !atencao.posicao ? ' de hoje' : ''}
                    {atencao.falta_mes_txt ? <> · faltam <strong>{atencao.falta_mes_txt}</strong> para a meta do mês</> : null}.
                  </p>
                </div>
                {telaAtencao && !dados.modo_leitura && (
                  <Button size="sm" iconRight={ArrowRight} onClick={() => navigate(telaAtencao.rota)}>
                    Agir em {telaAtencao.nome}
                  </Button>
                )}
              </div>
            </Card>
          )}

          {!dados.tem_meta && (
            <AlertMessage tipo="info">
              A meta individual de {dados.rotulo} ainda não foi cadastrada. A gestão grava em Monitor › RPeR ›
              Metas por squad e pessoa. Enquanto isso, você vê os resultados sem a comparação.
            </AlertMessage>
          )}

          {principais.length > 0 && (
            <div className="grid gap-4 grid-cols-1 sm:grid-cols-2" data-tour="des-principais">
              {principais.map((l) => <CartaoPrincipal key={l.chave} linha={l} aberto={dados.aberto} />)}
            </div>
          )}

          <Card padding="none" data-tour="des-indicadores">
            <div className="px-5 pt-4"><CardHeader title="Indicadores do mês" hint="Os mesmos números da RPeR, contra a sua meta." /></div>
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="text-left text-xs text-hipo-slate border-b border-hipo-border">
                    <th className="py-2 px-5 font-medium">Indicador</th>
                    <th className="py-2 px-3 font-medium text-right">Realizado</th>
                    {dados.aberto && <th className="py-2 px-3 font-medium text-right">Meta de hoje</th>}
                    <th className="py-2 px-3 font-medium text-right">Meta do mês</th>
                    <th className="py-2 px-3 font-medium">Atingimento</th>
                    {!dados.modo_leitura && <th className="py-2 px-5 font-medium"><span className="sr-only">Agir</span></th>}
                  </tr>
                </thead>
                <tbody>
                  {dados.indicadores.map((l) => {
                    const tela = telaDoIndicador(dados.squad, l.chave);
                    return (
                      <tr key={l.chave} className="border-b border-hipo-border/60" data-testid={`ind-${l.chave}`}>
                        <td className="py-2.5 px-5">
                          <span className="block text-hipo-ink font-medium">{l.rotulo}</span>
                          <span className="block text-xs text-hipo-slate">{l.fonte}</span>
                        </td>
                        <td className="py-2.5 px-3 text-right tabular-nums text-hipo-ink">{l.realizado_txt}</td>
                        {dados.aberto && <td className="py-2.5 px-3 text-right tabular-nums text-hipo-slate">{l.meta_hoje_txt || '—'}</td>}
                        <td className="py-2.5 px-3 text-right tabular-nums text-hipo-slate">{l.meta_mes_txt || '—'}</td>
                        <td className="py-2.5 px-3"><Atingimento linha={l} /></td>
                        {!dados.modo_leitura && (
                          <td className="py-2.5 px-5 text-right">
                            {tela && (
                              <button
                                type="button"
                                onClick={() => navigate(tela.rota)}
                                className="text-xs text-hipo-blue hover:underline whitespace-nowrap"
                              >
                                {tela.nome} →
                              </button>
                            )}
                          </td>
                        )}
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          </Card>

          <Card data-tour="des-funil">
            <CardHeader
              title="Funil e taxas de conversão"
              hint="Passagem entre as etapas dentro do mês. Mostra onde o funil afina."
            />
            <Funil etapas={dados.funil} />
          </Card>

          <Card data-tour="des-historico">
            <CardHeader
              title="Últimos meses"
              hint="Realizado e atingimento contra a meta de cada mês. O mês aberto é parcial."
            />
            <Historico historico={dados.historico} indicadores={dados.indicadores} />
          </Card>
        </>
      )}
    </div>
  );
}
