// web/src/components/crm/ParceiroDetalhe.jsx
//
// Visão 360 do parceiro — a MESMA casca do OportunidadeDetalhe: trilho de
// 208px à esquerda com o estado e as ações, abas verticais, conteúdo à
// direita e uma barra única no rodapé.
//
// ── Por que igual, e não parecido ────────────────────────────────────
// Abrir um parceiro e abrir uma oportunidade são o mesmo gesto — clicar
// numa linha para trabalhar aquele registro. Duas cascas diferentes para o
// mesmo gesto obrigam o usuário a reaprender onde ficam as coisas a cada
// troca de tela, e é ele que paga por uma decisão que foi nossa.
//
// A aba de Tarefas é literalmente o mesmo componente (`AbaTarefas`), com o
// mesmo mecanismo: linha do tempo, drilldown ao clicar, painéis de concluir
// / cancelar / editar, e a próxima obrigatória ao concluir.
//
// ── O que muda em relação à venda ────────────────────────────────────
// Só o conjunto de abas. O parceiro não tem proposta, envolvidos nem
// concorrentes; tem indicações e trilha de carteira. Quando as abas do
// parceiro forem definidas de verdade, é este array que muda — não o
// layout, não o mecanismo de tarefa.
//
// No lugar de Fase e Temperatura, o trilho traz EC responsável e a situação
// da relação. Mesmo papel: o estado que se muda por AÇÃO, não por formulário
// com Salvar. Trocar o EC chama o endpoint na hora e grava evento, igual a
// mover de fase.

import { useCallback, useEffect, useState } from 'react';
import { ExternalLink, History, Handshake, UserMinus } from 'lucide-react';

import api from '../../api';
import AbaTarefas from './AbaTarefas';
import Tabs from '../ui/Tabs';
import Button from '../ui/Button';
import Badge from '../ui/Badge';
import Empty from '../ui/Empty';
import AlertMessage from '../ui/AlertMessage';
import FarolSemanal, { resumoDoFarol } from '../ui/FarolSemanal';
import MiniFunil from '../ui/MiniFunil';

const TOM_SITUACAO = {
  ativo: 'success',
  esfriando: 'warning',
  dormente: 'danger',
  sem_indicacao: 'neutral',
};

const TOM_STATUS_OPP = {
  ativa: 'info', suspensa: 'warning', conquistado: 'success',
  perdido: 'danger', cancelado: 'neutral',
};

const ROTULO_EVENTO = {
  marcado: 'Virou parceiro',
  desmarcado: 'Saiu da carteira',
  atribuido: 'Assumido por',
  transferido: 'Transferido',
  removido: 'Ficou sem responsável',
};

// Mesmo componente e mesma classe do CampoInline do OportunidadeDetalhe: no
// trilho estreito, rótulo em cima gastaria duas alturas por campo.
function CampoInline({ id, rotulo, children }) {
  return (
    <div className="flex items-center gap-2">
      <label htmlFor={id} className="w-16 shrink-0 text-xs text-hipo-slate">
        {rotulo}
      </label>
      {children}
    </div>
  );
}

const CLASSE_INLINE =
  'flex-1 min-w-0 h-8 px-2 text-xs rounded-lg border border-hipo-border ' +
  'bg-hipo-card text-hipo-ink focus:outline-none focus:ring-2 focus:ring-hipo-blue ' +
  'disabled:bg-hipo-bg disabled:text-hipo-slate';

function mensagemDeErro(err, padrao) {
  const d = err?.response?.data?.detail;
  if (typeof d === 'string') return d;
  if (Array.isArray(d) && d[0]?.msg) return d[0].msg;
  if (d?.mensagem) return d.mensagem;
  return padrao;
}

function moeda(v) {
  if (v === null || v === undefined) return '—';
  return Number(v).toLocaleString('pt-BR', { style: 'currency', currency: 'BRL' });
}

function data(iso) {
  return iso ? new Date(iso).toLocaleDateString('pt-BR') : '—';
}

/** Percentual, ou travessão quando não há denominador. null e 0 diferem. */
function percentual(v) {
  if (v === null || v === undefined) return '—';
  return `${Math.round(v * 100)}%`;
}

function Numero({ rotulo, valor, detalhe, tom = 'text-hipo-ink' }) {
  return (
    <div className="rounded-lg border border-hipo-border bg-hipo-card p-2.5">
      <span className="block text-[11px] text-hipo-slate">{rotulo}</span>
      <span className={`block text-lg font-semibold ${tom}`}>{valor}</span>
      {detalhe && <span className="block text-[11px] text-hipo-slate">{detalhe}</span>}
    </div>
  );
}

// ── Aba: indicações ──────────────────────────────────────────────────

function AbaIndicacoes({ parceiro, periodo, onAbrirNoFunil, setErro }) {
  const [itens, setItens] = useState([]);
  const [carregando, setCarregando] = useState(true);

  useEffect(() => {
    let vivo = true;
    setCarregando(true);
    api.get(`/crm/parceiros/${parceiro.id}/indicacoes`, { params: { periodo } })
      .then(({ data: d }) => { if (vivo) setItens(d); })
      .catch((err) => {
        if (vivo) setErro(mensagemDeErro(err, 'Não foi possível carregar as indicações.'));
      })
      .finally(() => { if (vivo) setCarregando(false); });
    return () => { vivo = false; };
  }, [parceiro.id, periodo, setErro]);

  if (carregando) {
    return <p className="py-8 text-center text-sm text-hipo-slate">Carregando…</p>;
  }
  if (itens.length === 0) {
    return (
      <Empty
        title="Nenhuma indicação no período"
        description="Quando este parceiro indicar uma empresa, ela aparece aqui — em qualquer fase, inclusive as que não deram em nada."
        icon={Handshake}
      />
    );
  }

  return (
    <ul className="space-y-2">
      {itens.map((i) => (
        <li
          key={i.id}
          className="flex items-start justify-between gap-3 rounded-lg border border-hipo-border bg-hipo-card p-3"
        >
          <div className="min-w-0">
            <span className="block text-sm font-medium text-hipo-ink truncate">
              {i.conta_razao_social}
            </span>
            <span className="block text-xs font-mono text-hipo-slate">{i.numero}</span>
            <span className="mt-1 flex flex-wrap items-center gap-2">
              <Badge tone={TOM_STATUS_OPP[i.status] || 'neutral'}>{i.status}</Badge>
              <span className="text-xs text-hipo-slate">{i.fase}</span>
              <span className="text-xs text-hipo-slate">{moeda(i.valor_mensalidade)}</span>
              <span className="text-xs text-hipo-muted">{data(i.criado_em)}</span>
            </span>
          </div>
          {/*
            O caminho mais curto entre "quem indicou" e "o que virou". Semeia
            a busca da tela de Oportunidades pelo número.
          */}
          <Button
            size="sm"
            variant="ghost"
            icon={ExternalLink}
            aria-label={`Abrir ${i.numero} no funil`}
            onClick={() => onAbrirNoFunil(i.numero)}
          >
            Abrir
          </Button>
        </li>
      ))}
    </ul>
  );
}

// ── Aba: trilha da carteira ──────────────────────────────────────────

function AbaCarteira({ parceiro }) {
  const eventos = parceiro.eventos || [];
  if (eventos.length === 0) {
    return (
      <Empty
        title="Sem histórico de carteira"
        description="Toda troca de EC responsável vira um evento aqui — é o que responde 'de quem era isso antes'."
        icon={History}
      />
    );
  }
  return (
    <ul className="space-y-1.5">
      {eventos.map((e, i) => (
        <li
          key={i}
          className="flex items-baseline gap-2 text-sm border-b border-hipo-border pb-1.5"
        >
          <span className="text-hipo-ink">{ROTULO_EVENTO[e.tipo] || e.tipo}</span>
          {e.para_nome && <span className="text-hipo-slate">{e.para_nome}</span>}
          {e.de_nome && e.tipo === 'transferido' && (
            <span className="text-xs text-hipo-slate">(era de {e.de_nome})</span>
          )}
          <span className="ml-auto shrink-0 text-xs text-hipo-muted">
            {data(e.criado_em)}
            {e.autor_nome && ` · ${e.autor_nome}`}
          </span>
        </li>
      ))}
    </ul>
  );
}

// ── Detalhe ──────────────────────────────────────────────────────────

export default function ParceiroDetalhe({
  parceiro, usuarios, periodo,
  onRecarregar, onSalvo, onFechar, onAbrirNoFunil,
}) {
  const [aba, setAba] = useState('dados');
  const [erro, setErro] = useState(null);
  const [acaoEmCurso, setAcaoEmCurso] = useState(null);

  useEffect(() => {
    setAba('dados');
    setErro(null);
  }, [parceiro.id]);

  const acao = useCallback(async (chave, fn) => {
    setAcaoEmCurso(chave);
    setErro(null);
    try {
      const { data: d } = await fn();
      onSalvo(d);
    } catch (err) {
      setErro(mensagemDeErro(err, 'Não foi possível concluir a ação.'));
    } finally {
      setAcaoEmCurso(null);
    }
  }, [onSalvo]);

  const abas = [
    { key: 'dados', label: 'Dados' },
    // Tarefas em segundo, igual à oportunidade: é a aba que responde "e
    // agora?", que é a pergunta que traz o EC a esta tela.
    { key: 'tarefas', label: 'Tarefas', badge: parceiro.tarefas_abertas || undefined },
    { key: 'indicacoes', label: 'Indicações', badge: parceiro.indicacoes || undefined },
    { key: 'carteira', label: 'Carteira' },
  ];

  return (
    <div className="flex h-full min-h-0">

      {/* ── Trilho: estado, navegação e ações ── */}
      <aside className="shrink-0 w-52 border-r border-hipo-border bg-hipo-bg/40 flex flex-col min-h-0">
        <div className="px-3 pt-3 pb-3 space-y-2">
          {/*
            O EC responsável ocupa aqui o lugar que a Fase ocupa na
            oportunidade, e pelo mesmo motivo: é estado que muda por AÇÃO —
            chama o endpoint na hora e grava evento na trilha — e não campo
            de formulário com Salvar.
          */}
          <CampoInline id="parc-ec" rotulo="EC">
            <select
              id="parc-ec"
              aria-label="EC responsável"
              className={CLASSE_INLINE}
              value={parceiro.ec_responsavel_id || ''}
              disabled={Boolean(acaoEmCurso)}
              onChange={(e) => acao('ec', () =>
                api.patch(`/crm/parceiros/${parceiro.id}`,
                  { ec_responsavel_id: e.target.value || null },
                  { params: { periodo } })
              )}
            >
              <option value="">Sem responsável</option>
              {usuarios.map((u) => <option key={u.id} value={u.id}>{u.nome}</option>)}
            </select>
          </CampoInline>

          <CampoInline id="parc-situacao" rotulo="Relação">
            <span className="flex-1 min-w-0">
              <Badge tone={TOM_SITUACAO[parceiro.situacao] || 'neutral'}>
                {parceiro.situacao_rotulo}
              </Badge>
            </span>
          </CampoInline>
        </div>

        <div className="flex-1 min-h-0 overflow-y-auto px-2 py-2 border-t border-hipo-border">
          <Tabs items={abas} value={aba} onChange={setAba} orientacao="vertical" />
        </div>
      </aside>

      {/* ── Conteúdo da aba ── */}
      <div className="flex-1 min-w-0 flex flex-col min-h-0">
        {erro && (
          <div className="shrink-0 px-5 pt-4">
            <AlertMessage tipo="erro">{erro}</AlertMessage>
          </div>
        )}

        <div className="px-5 py-5 flex-1 min-h-0 overflow-y-auto">
          {aba === 'dados' && (
            <div className="space-y-5">
              {/*
                As duas leituras opostas, uma ao lado da outra — mesma razão
                de estarem lado a lado na linha da tabela. Parceiro sem
                indicação com quatro semanas verdes é problema de mercado;
                com quatro vermelhas é abandono.
              */}
              <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                <div className="rounded-lg border border-hipo-border bg-hipo-card p-3">
                  <span className="flex items-center justify-between gap-2">
                    <span className="text-xs font-medium text-hipo-slate">
                      Contato nas 4 semanas
                    </span>
                    <FarolSemanal
                      semanas={parceiro.farol}
                      semanasSemContato={parceiro.semanas_sem_contato}
                    />
                  </span>
                  <span className="block mt-1.5 text-sm text-hipo-ink">
                    {resumoDoFarol(parceiro.farol, parceiro.semanas_sem_contato)}
                  </span>
                </div>

                <div className="rounded-lg border border-hipo-border bg-hipo-card p-3">
                  <span className="block text-xs font-medium text-hipo-slate mb-1.5">
                    Indicações em aberto
                  </span>
                  <MiniFunil dados={parceiro.funil} />
                </div>
              </div>

              <div className="grid grid-cols-2 md:grid-cols-4 gap-2">
                <Numero
                  rotulo="Conversão"
                  valor={percentual(parceiro.taxa_conversao)}
                  detalhe={`${parceiro.convertidas} de ${parceiro.convertidas + parceiro.perdidas} fechadas`}
                  tom="text-hipo-success"
                />
                <Numero
                  rotulo="Cancelamento"
                  valor={percentual(parceiro.taxa_cancelamento)}
                  detalhe={`${parceiro.canceladas} de ${parceiro.indicacoes} indicações`}
                  tom={parceiro.canceladas > 0 ? 'text-hipo-danger' : 'text-hipo-ink'}
                />
                <Numero rotulo="Ticket ganho" valor={moeda(parceiro.ticket_convertido)} />
                <Numero
                  rotulo="Última indicação"
                  valor={data(parceiro.ultima_indicacao_em)}
                />
              </div>

              <dl className="grid grid-cols-1 sm:grid-cols-2 gap-x-6 gap-y-1.5 text-sm">
                <div className="flex gap-2">
                  <dt className="text-hipo-slate shrink-0">Cidade</dt>
                  <dd className="text-hipo-ink truncate">
                    {parceiro.cidade ? `${parceiro.cidade}/${parceiro.uf || ''}` : '—'}
                  </dd>
                </div>
                <div className="flex gap-2">
                  <dt className="text-hipo-slate shrink-0">Telefone</dt>
                  <dd className="text-hipo-ink">{parceiro.telefone || '—'}</dd>
                </div>
                <div className="flex gap-2">
                  <dt className="text-hipo-slate shrink-0">E-mail</dt>
                  <dd className="text-hipo-ink truncate">{parceiro.email || '—'}</dd>
                </div>
              </dl>

              {/*
                Cadastro da empresa se edita na tela de Contas, que é a dona
                dele. Duplicar o formulário aqui criaria dois lugares para
                mudar a mesma razão social — e eles divergem no primeiro
                ajuste.
              */}
              <p className="text-xs text-hipo-slate">
                Razão social, endereço e contatos se editam na tela de Contas.
              </p>
            </div>
          )}

          {/*
            O MESMO componente da oportunidade. Mesma linha do tempo, mesmo
            drilldown, mesmos painéis, mesma regra da próxima obrigatória.
          */}
          {aba === 'tarefas' && (
            <AbaTarefas parceiro={parceiro} onMudou={onRecarregar} />
          )}

          {aba === 'indicacoes' && (
            <AbaIndicacoes
              parceiro={parceiro}
              periodo={periodo}
              onAbrirNoFunil={onAbrirNoFunil}
              setErro={setErro}
            />
          )}

          {aba === 'carteira' && <AbaCarteira parceiro={parceiro} />}
        </div>

        {/*
          Uma barra só, igual à da oportunidade. "Remover da carteira" ocupa
          o lugar de "Finalizar": é a saída desta tela, e saída mora junto
          com Fechar.

          Não há Salvar porque não há formulário: as duas coisas que se
          mudam daqui — o EC e a permanência na carteira — são ações que
          gravam evento na hora.
        */}
        <div
          aria-label="Ações do parceiro"
          className="shrink-0 flex flex-wrap items-center gap-2 px-5 py-3 border-t border-hipo-border bg-hipo-bg/40"
        >
          <span className="text-xs text-hipo-slate">
            {parceiro.ec_responsavel_nome
              ? `Carteira de ${parceiro.ec_responsavel_nome}`
              : 'Sem responsável'}
          </span>

          <div className="ml-auto flex flex-wrap items-center gap-2">
            <Button
              size="sm"
              variant="secondary"
              icon={UserMinus}
              loading={acaoEmCurso === 'desmarcar'}
              onClick={() => acao('desmarcar', () =>
                api.patch(`/crm/parceiros/${parceiro.id}`,
                  { eh_finder: false }, { params: { periodo } })
              )}
            >
              Remover da carteira
            </Button>
            <Button size="sm" variant="ghost" onClick={onFechar}>Fechar</Button>
          </div>
        </div>
      </div>
    </div>
  );
}
