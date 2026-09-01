// web/src/pages/crm/Tarefas.jsx
//
// Gestão de tarefas: tudo o que está aberto em TODAS as oportunidades, em
// quatro colunas — Atrasadas, Para hoje, Futuras e Concluídas.
//
// ── Por que esta tela existe separada da aba ─────────────────────────
// A aba dentro da oportunidade responde "como esta negociação andou" e por
// isso é uma linha do tempo. Esta responde outra pergunta: "quanta coisa
// está parada, e com quem". Carga de trabalho se lê em pilhas comparáveis,
// não em fluxo — a coluna de Atrasadas com 14 cartões diz mais em um olhar
// do que qualquer lista ordenada diria.
//
// ── Por que não arrasta ──────────────────────────────────────────────
// Arrastar entre colunas significaria mudar o prazo, e "para quando?" não
// tem resposta óbvia ao soltar em Futuras. Mais grave: soltar em Concluídas
// teria que abrir o formulário da próxima tarefa de qualquer jeito, porque
// concluir exige agendar a seguinte. O gesto prometeria uma simplicidade
// que a regra de negócio não permite. Clicar abre o cartão com as ações.
//
// ── Concluídas é janela, não histórico ───────────────────────────────
// Sete dias por padrão. Aberto é estoque e cresce devagar; concluído é
// fluxo e cresce para sempre. O histórico completo de cada negociação
// continua na aba da oportunidade.
//
// Canceladas não têm coluna: são ruído para quem está medindo carga.

import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import {
  Search, X, CircleDot, AlarmClock, CalendarCheck, CalendarClock, CheckCircle2,
  TrendingUp,
} from 'lucide-react';

import api from '../../api';
import Badge from '../../components/ui/Badge';
import Empty from '../../components/ui/Empty';
import AlertMessage from '../../components/ui/AlertMessage';
import Modal from '../../components/ui/Modal';
import KpiInline from '../../components/ui/KpiInline';
import ProducaoDoMes, {
  limitesDoMes, rotuloCurto,
} from '../../components/crm/ProducaoDoMes';
import {
  ABERTAS, ICONE_TIPO, SITUACAO, STATUS_ABERTOS,
  PainelAcoesTarefa,
  corpoDaTarefa, dataCompleta, dataCurta, mensagemDeErro,
} from '../../components/crm/tarefaComum';

const CLASSE_CAMPO =
  'h-8 text-xs rounded-lg border border-hipo-border bg-hipo-card text-hipo-ink ' +
  'focus:outline-none focus:ring-2 focus:ring-hipo-blue';

const ICONE_COLUNA = {
  atrasada: AlarmClock,
  hoje: CalendarCheck,
  futura: CalendarClock,
  concluida: CheckCircle2,
};

// ── Cartão ───────────────────────────────────────────────────────────

function Cartao({ tarefa, onAbrir }) {
  const Icone = ICONE_TIPO[tarefa.tipo] || CircleDot;
  const tom = SITUACAO[tarefa.situacao] || SITUACAO.cancelada;

  return (
    <li>
      <button
        type="button"
        onClick={() => onAbrir(tarefa)}
        className={
          'w-full text-left bg-hipo-card border border-hipo-border rounded-lg ' +
          'p-2.5 space-y-1.5 hover:shadow-md transition-shadow ' +
          'focus:outline-none focus-visible:ring-2 focus-visible:ring-hipo-blue'
        }
      >
        <span className="flex items-center gap-1.5">
          <Icone size={13} className={`shrink-0 ${tom.texto}`} aria-hidden="true" />
          <span className={`text-xs font-medium ${tom.texto}`}>{tarefa.tipo_rotulo}</span>
          <span className="ml-auto shrink-0 text-xs text-hipo-slate tabular-nums">
            {dataCurta(tarefa.prazo)}
          </span>
        </span>

        <span className="block text-sm text-hipo-ink line-clamp-2">
          {tarefa.titulo}
        </span>

        {/*
          A empresa é o que o gestor usa para se localizar; o número da
          oportunidade é o que ele usa para achar depois.
        */}
        <span className="block text-xs text-hipo-slate truncate">
          {tarefa.conta_razao_social}
        </span>
        <span className="flex items-center gap-2 text-[11px] text-hipo-muted">
          {/*
            Tarefa de parceiro não tem número de oportunidade. Mostrar a
            palavra "Parceiro" no lugar — e não deixar o espaço vazio — é o
            que evita o cartão parecer um registro quebrado.
          */}
          <span className="font-mono">
            {tarefa.oportunidade_numero || tarefa.alvo_rotulo}
          </span>
          {tarefa.responsavel_nome && (
            <span className="ml-auto truncate">{tarefa.responsavel_nome}</span>
          )}
        </span>
      </button>
    </li>
  );
}

// ── Coluna ───────────────────────────────────────────────────────────

function Coluna({ coluna, onAbrir }) {
  const Icone = ICONE_COLUNA[coluna.situacao] || CircleDot;
  const tom = SITUACAO[coluna.situacao] || SITUACAO.cancelada;

  return (
    <section
      aria-label={coluna.rotulo}
      className={
        'flex-1 min-w-[13rem] h-full flex flex-col rounded-xl border p-2 ' +
        (coluna.somente_leitura
          ? 'border-dashed border-hipo-border bg-hipo-bg/70'
          : 'border-hipo-border bg-hipo-bg/40')
      }
    >
      <header className="shrink-0 mb-2 px-1 flex items-center gap-1.5">
        <Icone size={14} className={tom.texto} aria-hidden="true" />
        <h3 className="text-xs font-semibold text-hipo-ink truncate">{coluna.rotulo}</h3>
        <Badge tone={coluna.quantidade > 0 ? tom.tom : 'neutral'}>
          {coluna.quantidade}
        </Badge>
      </header>

      {/*
        O scroll da tela mora aqui. `min-h-0` não é decoração: sem ele o
        flex-item usa a altura do conteúdo como mínimo e a coluna cresce
        para fora do container em vez de rolar.
      */}
      <ul className="flex-1 min-h-0 overflow-y-auto space-y-2 pr-0.5">
        {coluna.itens.length === 0 ? (
          <li className="px-1 py-6 text-center text-xs text-hipo-muted list-none">
            Vazio
          </li>
        ) : (
          coluna.itens.map((t) => <Cartao key={t.id} tarefa={t} onAbrir={onAbrir} />)
        )}
      </ul>

      {coluna.itens.length < coluna.quantidade && (
        <p className="shrink-0 pt-1.5 text-center text-xs text-hipo-muted">
          +{coluna.quantidade - coluna.itens.length} não exibidas
        </p>
      )}
    </section>
  );
}

// ── Tela ─────────────────────────────────────────────────────────────

export default function Tarefas() {
  const [colunas, setColunas] = useState([]);
  const [usuarios, setUsuarios] = useState([]);
  const [responsavel, setResponsavel] = useState('');
  const [busca, setBusca] = useState('');
  const [q, setQ] = useState('');
  const [carregando, setCarregando] = useState(true);
  const [erro, setErro] = useState(null);
  const [ocupado, setOcupado] = useState(false);
  const [aberta, setAberta] = useState(null);      // tarefa no modal
  const [painel, setPainel] = useState(null);
  const [producao, setProducao] = useState(null);  // resumo do mês corrente
  const [verProducao, setVerProducao] = useState(false);
  const debounce = useRef(null);

  // O `q === busca ? q : busca` não é microtuning: sem ele o timer dispara
  // uma vez na montagem, troca a identidade do estado e a tela recarrega
  // sozinha — mesmo bug que já custou uma carga dupla em Contas e no funil.
  useEffect(() => {
    clearTimeout(debounce.current);
    debounce.current = setTimeout(() => {
      setQ((atual) => (atual === busca ? atual : busca));
    }, 350);
    return () => clearTimeout(debounce.current);
  }, [busca]);

  const params = useMemo(() => {
    const p = {};
    if (q) p.q = q;
    if (responsavel) p.responsavel_id = responsavel;
    return p;
  }, [q, responsavel]);

  const carregar = useCallback(async () => {
    setCarregando(true);
    setErro(null);
    try {
      const { data } = await api.get('/crm/tarefas/kanban', { params });
      setColunas(data);
    } catch (err) {
      setErro(mensagemDeErro(err, 'Não foi possível carregar as tarefas.'));
    } finally {
      setCarregando(false);
    }
  }, [params]);

  useEffect(() => { carregar(); }, [carregar]);

  useEffect(() => {
    api.get('/crm/dominio/usuarios')
      .then(({ data }) => setUsuarios(data))
      .catch(() => setUsuarios([]));
  }, []);

  /*
    O KPI do mês corrente, com os MESMOS filtros da barra. Agregado que
    ignora o filtro da tela produz um número global ao lado de uma lista
    filtrada — duas respostas para a mesma pergunta, na mesma tela.

    Falha em silêncio de propósito: o kanban é o conteúdo, e um erro no
    contador do mês não pode roubar a faixa de erro de quem está tentando
    concluir uma tarefa.
  */
  const mesCorrente = useMemo(() => {
    const hoje = new Date();
    return {
      ...limitesDoMes(hoje.getFullYear(), hoje.getMonth()),
      rotulo: rotuloCurto(hoje.getFullYear(), hoje.getMonth()),
    };
  }, []);

  useEffect(() => {
    let vivo = true;
    api.get('/crm/tarefas/resumo', {
      params: { de: mesCorrente.de, ate: mesCorrente.ate, ...params },
    })
      .then(({ data }) => { if (vivo) setProducao(data); })
      .catch(() => { if (vivo) setProducao(null); });
    return () => { vivo = false; };
  }, [params, mesCorrente]);

  const mutar = useCallback(async (fn, padrao) => {
    setOcupado(true);
    setErro(null);
    try {
      await fn();
      await carregar();
      setAberta(null);
      setPainel(null);
      return true;
    } catch (err) {
      setErro(mensagemDeErro(err, padrao));
      return false;
    } finally {
      setOcupado(false);
    }
  }, [carregar]);

  const concluir = (tarefa, resultado, proxima) => mutar(
    () => api.post(`/crm/tarefas/${tarefa.id}/concluir`, {
      resultado: resultado.trim() || null,
      proxima: proxima ? corpoDaTarefa(proxima) : null,
    }),
    'Não foi possível concluir a tarefa.',
  );

  const cancelar = (tarefa, motivo) => mutar(
    () => api.post(`/crm/tarefas/${tarefa.id}/cancelar`, {
      motivo: motivo.trim() || null,
    }),
    'Não foi possível cancelar a tarefa.',
  );

  const editar = (tarefa, form) => mutar(
    () => api.patch(`/crm/tarefas/${tarefa.id}`, corpoDaTarefa(form)),
    'Não foi possível salvar a tarefa.',
  );

  const atrasadas = colunas.find((c) => c.situacao === 'atrasada')?.quantidade ?? 0;
  const emAberto = colunas
    .filter((c) => ABERTAS.includes(c.situacao))
    .reduce((soma, c) => soma + c.quantidade, 0);
  const temFiltro = Boolean(q || responsavel);

  /*
    Concluir exige a próxima enquanto a oportunidade está viva. O status vem
    no próprio payload da tarefa (o JOIN já existia no backend) — buscar por
    tarefa aberta seria N+1, e assumir "sempre exige" faria a tela pedir uma
    próxima tarefa para negócio já fechado.
  */
  const exigeProxima = aberta
    ? STATUS_ABERTOS.includes(aberta.status_oportunidade)
    : false;

  return (
    <div className="h-full min-h-0 flex flex-col gap-2">

      {/* ── Barra única: título, contadores, filtros ── */}
      <div className="shrink-0 flex flex-wrap items-center gap-x-2 gap-y-2">
        <h1 className="sr-only">Tarefas — gestão</h1>

        <div className="flex items-center gap-2">
          <Badge tone={atrasadas > 0 ? 'danger' : 'neutral'}>
            {atrasadas} atrasada{atrasadas === 1 ? '' : 's'}
          </Badge>
          <Badge tone="info">{emAberto} em aberto</Badge>

          {/*
            O contrapeso das duas badges acima. Elas contam o que está
            PARADO; esta conta o que ANDOU. Uma tela que só mostra dívida
            ensina que o trabalho nunca rende.
          */}
          <KpiInline
            label={`Realizadas em ${mesCorrente.rotulo}`}
            valor={producao?.realizadas ?? '—'}
            titulo="Tarefas concluídas no mês corrente. Clique para abrir a produção por tipo e por responsável."
            icone={TrendingUp}
            tom="bg-hipo-successSoft text-hipo-success"
            ativo={verProducao}
            onClick={() => setVerProducao(true)}
          />
        </div>

        <div className="ml-auto flex flex-wrap items-center gap-2">
          <div className="relative">
            <Search
              size={14}
              className="absolute left-2.5 top-1/2 -translate-y-1/2 text-hipo-muted pointer-events-none"
              aria-hidden="true"
            />
            <input
              aria-label="Buscar"
              placeholder="Empresa, número ou tarefa"
              value={busca}
              onChange={(e) => setBusca(e.target.value)}
              className={`${CLASSE_CAMPO} w-52 pl-7 pr-2 placeholder:text-hipo-muted`}
            />
          </div>

          <select
            aria-label="Responsável"
            value={responsavel}
            onChange={(e) => setResponsavel(e.target.value)}
            className={`${CLASSE_CAMPO} px-1.5 max-w-[11rem]`}
          >
            <option value="">Todos os responsáveis</option>
            {usuarios.map((u) => <option key={u.id} value={u.id}>{u.nome}</option>)}
          </select>

          {temFiltro && (
            <button
              type="button"
              onClick={() => { setBusca(''); setResponsavel(''); }}
              aria-label="Limpar filtros"
              title="Limpar filtros"
              className="h-8 w-8 inline-flex items-center justify-center rounded-lg border border-hipo-border text-hipo-slate hover:bg-hipo-bg transition-colors"
            >
              <X size={14} />
            </button>
          )}
        </div>
      </div>

      {/*
        Só quando o modal está fechado. As duas superfícies mostravam a mesma
        mensagem ao mesmo tempo — o usuário lia o erro em duplicado e não
        sabia qual dos dois era o dele.
      */}
      {erro && !aberta && (
        <div className="shrink-0"><AlertMessage tipo="erro">{erro}</AlertMessage></div>
      )}

      <div className="flex-1 min-h-0">
        {carregando ? (
          <p className="py-16 text-center text-sm text-hipo-slate">Carregando tarefas…</p>
        ) : colunas.every((c) => c.quantidade === 0) ? (
          <Empty
            title={temFiltro ? 'Nenhuma tarefa com esses filtros' : 'Nenhuma tarefa agendada'}
            description={
              temFiltro
                ? 'Ajuste a busca ou o responsável.'
                : 'As tarefas são criadas dentro de cada oportunidade.'
            }
            icon={CircleDot}
          />
        ) : (
          <div className="h-full flex gap-2 overflow-x-auto overflow-y-hidden pb-1">
            {colunas.map((c) => (
              <Coluna key={c.situacao} coluna={c} onAbrir={(t) => { setAberta(t); setPainel(null); }} />
            ))}
          </div>
        )}
      </div>

      {/* ── Detalhe da tarefa ── */}
      <Modal
        aberto={Boolean(aberta)}
        onFechar={() => { setAberta(null); setPainel(null); }}
        titulo={aberta ? aberta.titulo : undefined}
        subtitulo={aberta ? (
          <span>
            {aberta.conta_razao_social} ·{' '}
            <span className="font-mono">
              {aberta.oportunidade_numero || aberta.alvo_rotulo}
            </span>
          </span>
        ) : undefined}
        size="lg"
      >
        {aberta && (
          <div className="space-y-4">
            {erro && <AlertMessage tipo="erro">{erro}</AlertMessage>}

            <dl className="grid grid-cols-1 sm:grid-cols-2 gap-x-4 gap-y-1 text-xs">
              <div>
                <dt className="inline text-hipo-slate">Tipo: </dt>
                <dd className="inline text-hipo-ink">{aberta.tipo_rotulo}</dd>
              </div>
              <div>
                <dt className="inline text-hipo-slate">Situação: </dt>
                <dd className="inline text-hipo-ink">
                  {(SITUACAO[aberta.situacao] || SITUACAO.cancelada).palavra}
                </dd>
              </div>
              <div>
                <dt className="inline text-hipo-slate">Prazo: </dt>
                <dd className="inline text-hipo-ink">{dataCompleta(aberta.prazo)}</dd>
              </div>
              <div>
                <dt className="inline text-hipo-slate">Responsável: </dt>
                <dd className="inline text-hipo-ink">{aberta.responsavel_nome || '—'}</dd>
              </div>
              {aberta.concluida_em && (
                <div>
                  <dt className="inline text-hipo-slate">Concluída em: </dt>
                  <dd className="inline text-hipo-ink">{dataCompleta(aberta.concluida_em)}</dd>
                </div>
              )}
            </dl>

            {aberta.descricao && (
              <p className="text-sm text-hipo-slate">{aberta.descricao}</p>
            )}
            {aberta.resultado && (
              <p className="text-sm text-hipo-ink">
                <span className="text-hipo-slate">Resultado: </span>{aberta.resultado}
              </p>
            )}

            {ABERTAS.includes(aberta.situacao) ? (
              <PainelAcoesTarefa
                tarefa={aberta}
                painel={painel}
                setPainel={setPainel}
                usuarios={usuarios}
                exigeProxima={exigeProxima}
                ocupado={ocupado}
                onConcluir={concluir}
                onCancelar={cancelar}
                onEditar={editar}
              />
            ) : (
              <p className="text-xs text-hipo-slate">
                Tarefa fechada. O histórico é imutável — abra a oportunidade
                para ver a linha do tempo completa.
              </p>
            )}
          </div>
        )}
      </Modal>

      <ProducaoDoMes
        aberto={verProducao}
        onFechar={() => setVerProducao(false)}
        filtros={params}
      />
    </div>
  );
}
