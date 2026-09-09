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
// ── Abre no recorte de quem entrou ───────────────────────────────────
// O filtro de responsável já vem preenchido com o usuário logado. A pergunta
// que a tela responde primeiro é "o que é meu"; a carga da equipe fica a um
// clique no mesmo seletor, com "Todos os responsáveis". É o passo possível
// hoje na direção da diretriz da "próxima tarefa".
//
// Canceladas não têm coluna: são ruído para quem está medindo carga.
//
// ── Da tarefa para a negociação ──────────────────────────────────────
// A tarefa é sempre sobre ALGUMA COISA, e essa coisa é a oportunidade. Quem
// abre "Cobrar proposta" quase sempre precisa, no mesmo minuto, do que está
// atrás dela: em que fase está, quanto vale, o que foi conversado antes.
// Sem caminho daqui para lá, o gestor fechava tudo, ia para o funil e
// buscava o número na mão — e voltava para cá sem lembrar em que cartão
// estava.
//
// A oportunidade abre EM CIMA da tarefa, não no lugar dela — mesma escolha
// do drilldown da conta dentro da oportunidade, e pelo mesmo motivo: fechar
// o drilldown devolve o cartão exatamente como estava, com o painel de
// concluir aberto e o que já foi digitado intacto. A pilha vai a três
// níveis: tarefa (1) → oportunidade (2) → conta (3).
//
// Tarefa de parceiro não tem oportunidade, e por isso não tem o botão. O
// alvo vem pronto do servidor (`alvo`, `oportunidade_id`); a tela não
// deduz de campo nulo.

import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import {
  Search, X, CircleDot, AlarmClock, CalendarCheck, CalendarClock, CheckCircle2,
  TrendingUp, Briefcase, Maximize2,
} from 'lucide-react';

import api, { getUser } from '../../api';
import Badge from '../../components/ui/Badge';
import Button from '../../components/ui/Button';
import Empty from '../../components/ui/Empty';
import AlertMessage from '../../components/ui/AlertMessage';
import Modal from '../../components/ui/Modal';
import KpiInline from '../../components/ui/KpiInline';
import ProducaoDoMes, {
  limitesDoMes, rotuloCurto,
} from '../../components/crm/ProducaoDoMes';
import OportunidadeDetalhe from '../../components/crm/OportunidadeDetalhe';
import ContaDetalhe from '../../components/crm/ContaDetalhe';
import ModalDesfecho from '../../components/crm/ModalDesfecho';
import AnexosTarefa from '../../components/crm/AnexosTarefa';
import ModalReuniao from '../../components/crm/ModalReuniao';
import {
  ABERTAS, ICONE_TIPO, SITUACAO,
  PainelAcoesTarefa,
  corpoDaTarefa, dataCompleta, dataCurta, exigeProximaTarefa, mensagemDeErro,
} from '../../components/crm/tarefaComum';

const CLASSE_CAMPO =
  'h-8 text-xs rounded-lg border border-hipo-border bg-hipo-card text-hipo-ink ' +
  'focus:outline-none focus:ring-2 focus:ring-hipo-blue';

// Mesmo mapa do funil. Duplicado em três arquivos e sempre igual: extrair
// para um módulo compartilhado é item de faxina, não desta mudança.
const TOM_STATUS = {
  ativa: 'success', suspensa: 'warning', conquistado: 'success',
  perdido: 'danger', cancelado: 'neutral',
};

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
  /*
    A tela abre nas tarefas de QUEM ENTROU, não nas de todo mundo.

    Aberta em "todos", a primeira coisa que qualquer pessoa fazia era
    procurar o próprio nome no seletor — e, enquanto não achava, lia a carga
    da equipe inteira como se fosse a dela. O caminho para a diretriz da
    "próxima tarefa" passa por aqui: a tela precisa responder "o que é meu"
    antes de responder "o que existe". Ver a carga dos outros continua a um
    clique no mesmo seletor.

    `getUser()` lê o usuário gravado no login (localStorage). Sessão sem
    usuário gravado — teste, ou localStorage limpo com token vivo — cai em
    string vazia e a tela se comporta como antes: todos os responsáveis.
  */
  const usuarioLogado = useMemo(() => getUser(), []);
  const padraoResponsavel = usuarioLogado?.id ? String(usuarioLogado.id) : '';

  const [colunas, setColunas] = useState([]);
  const [usuarios, setUsuarios] = useState([]);
  const [responsavel, setResponsavel] = useState(padraoResponsavel);
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

  /*
    ── A pilha do drilldown ──
    `oportunidade` é o nível 2 (aberto de dentro da tarefa) e `contaAberta` o
    nível 3 (aberto de dentro da oportunidade). `verticais` só é buscada
    quando a conta abre pela primeira vez: o kanban de tarefas não precisa
    dela para nada, e uma request a mais em toda abertura da tela seria custo
    fixo para um caminho que quase ninguém percorre.
  */
  const [oportunidade, setOportunidade] = useState(null);
  const [desfechoDe, setDesfechoDe] = useState(null);
  // Marcar reunião a partir da oportunidade aberta no drilldown. Vive na
  // página, e não no OportunidadeDetalhe, porque só a página sabe em que
  // nível da pilha o modal precisa abrir — aqui a oportunidade já é o 2.
  const [agendandoPara, setAgendandoPara] = useState(null);
  const [contaAberta, setContaAberta] = useState(null);
  const [acaoSalvarConta, setAcaoSalvarConta] = useState(null);
  const [verticais, setVerticais] = useState([]);
  const verticaisRef = useRef([]);

  /*
    Os ids do que está aberto vivem em ref, não nas dependências dos
    callbacks. `onRecarregar` e `onSalvo` do OportunidadeDetalhe alimentam o
    `mutar` da aba de tarefas dele; prop que troca de identidade a cada
    render nesse caminho já produziu recarregamento em loop nas outras telas.
    Com ref, os handlers nascem estáveis e continuam sabendo em quem mexer.
  */
  const abertaRef = useRef(null);
  const oportunidadeRef = useRef(null);
  useEffect(() => { abertaRef.current = aberta?.id ?? null; });
  useEffect(() => { oportunidadeRef.current = oportunidade?.id ?? null; });

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
    O usuário logado é garantido na lista mesmo que a chamada de domínio falhe
    ou não o traga. Sem isso o filtro estaria aplicado com o seletor mostrando
    a opção errada — a tela mentiria sobre o próprio recorte.
  */
  const opcoesResponsavel = useMemo(() => {
    const lista = usuarios.map((u) => ({
      id: String(u.id),
      nome: String(u.id) === padraoResponsavel ? `${u.nome} (você)` : u.nome,
    }));
    if (padraoResponsavel && !lista.some((u) => u.id === padraoResponsavel)) {
      lista.unshift({
        id: padraoResponsavel,
        nome: `${usuarioLogado?.nome || 'Você'} (você)`,
      });
    }
    return lista;
  }, [usuarios, padraoResponsavel, usuarioLogado]);

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

  /*
    Põe a tarefa na grade REAPROVEITANDO a tarefa: horário, dono, título e
    alvo já são dela, e o backend os herda. Criar uma segunda diria a mesma
    coisa duas vezes na linha do tempo e contaria duas reuniões na produção
    do mês.

    `mutar` fecha o cartão ao terminar, o que aqui é o comportamento certo:
    a tarefa mudou de natureza, e a lista recarregada já a mostra com o
    selo "na agenda".
  */
  const agendar = (tarefa) => mutar(
    () => api.post(`/crm/agenda/reunioes/de-tarefa/${tarefa.id}`, {
      modalidade: tarefa.tipo === 'visita' ? 'presencial' : 'online',
    }),
    'Não foi possível colocar a tarefa na agenda.',
  );

  // ── Drilldown: tarefa → oportunidade → conta ───────────────────────

  /*
    A tarefa aberta atrás do drilldown pode ter mudado por lá: concluir pela
    aba de tarefas da oportunidade, ou finalizar a negociação, muda situação
    e `status_oportunidade` — e é esse status que decide se a conclusão vai
    exigir a próxima tarefa. Sem recarregar, o usuário voltaria para um
    cartão que mente sobre o próprio estado.

    Falha em silêncio: o kanban atrás já foi recarregado, e trocar a faixa de
    erro por causa de um refresh de cortesia atrapalharia quem está no meio
    de uma ação.
  */
  const recarregarTarefaAberta = useCallback(async () => {
    const id = abertaRef.current;
    if (!id) return;
    try {
      const { data } = await api.get(`/crm/tarefas/${id}`);
      setAberta(data);
    } catch {
      /* silencioso de propósito — ver comentário acima */
    }
  }, []);

  const abrirOportunidade = useCallback(async (id) => {
    setErro(null);
    try {
      const { data } = await api.get(`/crm/oportunidades/${id}`);
      setOportunidade(data);
    } catch (err) {
      setErro(mensagemDeErro(err, 'Não foi possível abrir a oportunidade.'));
    }
  }, []);

  const fecharOportunidade = useCallback(() => {
    setOportunidade(null);
    setContaAberta(null);
    setAcaoSalvarConta(null);
  }, []);

  const recarregarOportunidade = useCallback(async () => {
    const id = oportunidadeRef.current;
    if (!id) return;
    try {
      const { data } = await api.get(`/crm/oportunidades/${id}`);
      setOportunidade(data);
    } catch (err) {
      setErro(mensagemDeErro(err, 'Não foi possível recarregar a oportunidade.'));
    }
  }, []);

  /*
    Qualquer mudança dentro do drilldown repercute em TRÊS superfícies: a
    própria oportunidade, o kanban atrás e o cartão aberto. Recarregar só a
    oportunidade era o caminho curto — e deixava a coluna Atrasadas com a
    tarefa que o usuário acabou de concluir por dentro da aba.
  */
  const aoMudarOportunidade = useCallback(async () => {
    await Promise.all([
      recarregarOportunidade(),
      carregar(),
      recarregarTarefaAberta(),
    ]);
  }, [recarregarOportunidade, carregar, recarregarTarefaAberta]);

  const aoSalvarOportunidade = useCallback((atualizada) => {
    setOportunidade(atualizada);
    carregar();
    recarregarTarefaAberta();
  }, [carregar, recarregarTarefaAberta]);

  const abrirConta = useCallback(async (contaId) => {
    setErro(null);
    try {
      const [conta, verts] = await Promise.all([
        api.get(`/crm/contas/${contaId}`),
        verticaisRef.current.length
          ? Promise.resolve({ data: verticaisRef.current })
          : api.get('/crm/dominio/verticais'),
      ]);
      verticaisRef.current = verts.data;
      setVerticais(verts.data);
      setContaAberta(conta.data);
    } catch (err) {
      setErro(mensagemDeErro(err, 'Não foi possível abrir a conta.'));
    }
  }, []);

  const fecharConta = useCallback(() => {
    setContaAberta(null);
    setAcaoSalvarConta(null);
  }, []);

  const recarregarConta = useCallback(async () => {
    const id = contaAberta?.id;
    if (!id) return;
    try {
      const { data } = await api.get(`/crm/contas/${id}`);
      setContaAberta(data);
    } catch (err) {
      setErro(mensagemDeErro(err, 'Não foi possível recarregar a conta.'));
    }
  }, [contaAberta]);

  const criarVertical = useCallback(async (nome) => {
    const { data } = await api.post('/crm/dominio/verticais', { nome });
    setVerticais((vs) => {
      const lista = vs.some((v) => v.id === data.id) ? vs : [...vs, data];
      verticaisRef.current = lista;
      return lista;
    });
    return data;
  }, []);

  /*
    Renomear a empresa aqui muda o nome que aparece no cartão do kanban, no
    subtítulo do modal da tarefa e no título da oportunidade. Sem recarregar
    as três, o usuário salva e vê o nome antigo assim que fecha — e conclui
    que não salvou.
  */
  const aoSalvarConta = useCallback((atualizada) => {
    setContaAberta(atualizada);
    carregar();
    recarregarOportunidade();
    recarregarTarefaAberta();
  }, [carregar, recarregarOportunidade, recarregarTarefaAberta]);

  const atrasadas = colunas.find((c) => c.situacao === 'atrasada')?.quantidade ?? 0;
  const emAberto = colunas
    .filter((c) => ABERTAS.includes(c.situacao))
    .reduce((soma, c) => soma + c.quantidade, 0);
  /*
    "Tem filtro" é o que difere do PADRÃO da tela, não do vazio absoluto. Com
    o responsável já vindo preenchido, comparar com vazio deixaria o botão de
    limpar aceso o tempo todo sem nada para limpar.
  */
  const temFiltro = Boolean(q) || responsavel !== padraoResponsavel;

  // Sem filtro extra e olhando só as próprias tarefas: o vazio aqui não é
  // "não há tarefas no sistema", é "não há tarefa sua" — e a saída é ver as
  // dos outros, não ajustar filtro nenhum.
  const soAsMinhas = Boolean(padraoResponsavel) && responsavel === padraoResponsavel && !q;

  const limpar = () => { setBusca(''); setResponsavel(padraoResponsavel); };

  /*
    Concluir exige a próxima enquanto a oportunidade está viva — e SEMPRE em
    tarefa de parceiro. Alvo e status vêm no próprio payload da tarefa (o
    JOIN já existia no backend); buscar por tarefa aberta seria N+1.

    O `alvo` não pode faltar aqui. Olhar só para `status_oportunidade` foi o
    que quebrou a conclusão de tarefa de parceiro nesta tela: o campo chega
    nulo, a regra devolvia "não exige", o formulário da próxima não abria e
    o backend recusava com 422 — sem saída dentro do módulo de tarefas. A
    regra mora em `exigeProximaTarefa`, uma só, compartilhada com a aba.
  */
  const exigeProxima = aberta
    ? exigeProximaTarefa(aberta.alvo, aberta.status_oportunidade)
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
            {opcoesResponsavel.map((u) => (
              <option key={u.id} value={u.id}>{u.nome}</option>
            ))}
          </select>

          {temFiltro && (
            <button
              type="button"
              onClick={limpar}
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
            title={
              temFiltro
                ? 'Nenhuma tarefa com esses filtros'
                : soAsMinhas
                  ? 'Nenhuma tarefa sua em aberto'
                  : 'Nenhuma tarefa agendada'
            }
            description={
              temFiltro
                ? 'Ajuste a busca ou o responsável.'
                : soAsMinhas
                  ? 'A tela abre nas suas tarefas. Veja as da equipe pelo seletor de responsável.'
                  : 'As tarefas são criadas dentro de cada oportunidade.'
            }
            icon={CircleDot}
            action={
              soAsMinhas ? (
                <Button variant="secondary" size="sm" onClick={() => setResponsavel('')}>
                  Ver de todos
                </Button>
              ) : undefined
            }
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

            {/*
              ── A negociação, a um clique ──
              O subtítulo do modal já DIZ o número; dizer não é o mesmo que
              levar. Quem está decidindo o que fazer com a tarefa precisa da
              fase, do valor e do histórico — e tinha que fechar tudo e
              buscar o número na mão no funil.

              Só existe quando a tarefa É de uma oportunidade. Em tarefa de
              parceiro `oportunidade_id` vem nulo e o botão não aparece: um
              botão que abre nada seria pior que a ausência dele.
            */}
            {aberta.oportunidade_id && (
              <button
                type="button"
                onClick={() => abrirOportunidade(aberta.oportunidade_id)}
                title={`Abrir a oportunidade ${aberta.oportunidade_numero}`}
                aria-label={`Abrir a oportunidade ${aberta.oportunidade_numero}`}
                className={
                  'w-full flex items-center gap-2 px-3 py-2 rounded-lg text-xs ' +
                  'border border-hipo-border bg-hipo-bg/40 text-hipo-ink text-left ' +
                  'hover:bg-hipo-blueSoft hover:border-hipo-blue transition-colors ' +
                  'focus:outline-none focus-visible:ring-2 focus-visible:ring-hipo-blue'
                }
              >
                <Briefcase size={14} className="shrink-0 text-hipo-blue" aria-hidden="true" />
                <span className="font-mono font-medium shrink-0">
                  {aberta.oportunidade_numero}
                </span>
                <span className="truncate text-hipo-slate">
                  {aberta.conta_razao_social}
                </span>
                <Maximize2
                  size={12}
                  className="ml-auto shrink-0 text-hipo-slate"
                  aria-hidden="true"
                />
              </button>
            )}

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

            {/*
              Anexos fora do ternário de baixo: tarefa fechada continua
              mostrando o print que provou o relato, só não deixa mexer.

              nivel 2 no lightbox porque o modal da tarefa aqui é o 1. A
              oportunidade também abre no 2, mas as duas nunca estão
              abertas ao mesmo tempo: para clicar na miniatura, o
              drilldown precisa estar fechado.
            */}
            <AnexosTarefa
              tarefa={aberta}
              nivelLightbox={2}
              onMudou={recarregarTarefaAberta}
            />

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
                onAgendar={agendar}
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

      {/*
        ── Drilldown da oportunidade (nível 2) ──
        Abre de dentro do modal da tarefa, então é nível 2 — declarado na
        chamada, não deduzido da ordem do JSX. É o MESMO componente do funil,
        com as mesmas props e editável: uma versão "só leitura" aqui viraria
        uma segunda tela da oportunidade para manter, e ela envelheceria.

        O Esc fecha só este, não os dois — ver a pilha em components/ui/Modal.
      */}
      <Modal
        aberto={Boolean(oportunidade)}
        onFechar={fecharOportunidade}
        titulo={oportunidade
          ? `${oportunidade.numero} · ${oportunidade.conta_razao_social}`
          : undefined}
        subtitulo={oportunidade ? (
          <Badge tone={TOM_STATUS[oportunidade.status] || 'neutral'}>
            {oportunidade.status}
          </Badge>
        ) : undefined}
        size="full"
        nivel={2}
        bodySemPadding
      >
        {oportunidade && (
          <OportunidadeDetalhe
            oportunidade={oportunidade}
            onRecarregar={aoMudarOportunidade}
            onSalvo={aoSalvarOportunidade}
            onDesfecho={setDesfechoDe}
            onFechar={fecharOportunidade}
            onAbrirConta={abrirConta}
            onAgendarReuniao={setAgendandoPara}
          />
        )}
      </Modal>

      {/*
        ── Drilldown da conta (nível 3) ──
        Terceiro degrau da mesma pilha: tarefa → oportunidade → empresa. O
        caminho inteiro existe no funil a partir do segundo degrau; aqui ele
        só ganhou o primeiro.
      */}
      <Modal
        aberto={Boolean(contaAberta)}
        onFechar={fecharConta}
        titulo={contaAberta?.razao_social}
        subtitulo={contaAberta ? `CNPJ ${contaAberta.cnpj_formatado}` : undefined}
        size="full"
        nivel={3}
        bodySemPadding
        acoes={
          // O aria-label separa esta barra da do modal de baixo: com dois
          // modais no DOM há dois "Salvar", e sem rótulo nem o leitor de tela
          // nem o teste sabem qual é de quem.
          <div className="flex items-center gap-2" aria-label="Ações da conta">
            <span className="text-xs text-hipo-slate mr-1">
              {acaoSalvarConta?.sujo ? 'Alterações não salvas' : 'Tudo salvo'}
            </span>
            <Button size="sm" variant="ghost" onClick={fecharConta}>
              Voltar à oportunidade
            </Button>
            <Button
              size="sm"
              onClick={() => acaoSalvarConta?.salvar()}
              disabled={!acaoSalvarConta?.sujo}
              loading={acaoSalvarConta?.salvando}
            >
              Salvar
            </Button>
          </div>
        }
      >
        {contaAberta && (
          <ContaDetalhe
            conta={contaAberta}
            verticais={verticais}
            onCriarVertical={criarVertical}
            onRecarregar={recarregarConta}
            onSalvo={aoSalvarConta}
            registrarSalvar={setAcaoSalvarConta}
          />
        )}
      </Modal>

      {/*
        ── Finalizar a oportunidade (nível 3) ──
        Aqui a oportunidade já é o nível 2, então o desfecho precisa ser o 3 —
        por isso o `nivel` é passado, e não deixado no padrão do componente.
        Com o padrão, o formulário abriria ATRÁS da oportunidade e pareceria
        que o botão Finalizar não faz nada.
      */}
      <ModalDesfecho
        oportunidade={desfechoDe}
        nivel={3}
        onFechar={() => setDesfechoDe(null)}
        onConcluido={(o) => {
          setDesfechoDe(null);
          if (oportunidadeRef.current === o.id) setOportunidade(o);
          carregar();
          // O desfecho grava uma tarefa concluída e pode mudar o
          // `status_oportunidade` da tarefa aberta atrás — que é o que decide
          // se concluir ainda vai exigir a próxima.
          recarregarTarefaAberta();
        }}
      />

      {/*
        ── Marcar reunião (nível 3) ──
        A pilha aqui já é tarefa (1) → oportunidade (2), então a reunião
        precisa do 3. Com o padrão, abriria ATRÁS da oportunidade e
        pareceria que o botão não faz nada — a mesma armadilha que o
        ModalDesfecho acima também precisa declarar.
      */}
      <ModalReuniao
        aberto={Boolean(agendandoPara)}
        nivel={3}
        onFechar={() => setAgendandoPara(null)}
        onSalvo={() => { aoMudarOportunidade(); }}
        oportunidade={agendandoPara}
        usuarios={usuarios}
      />

      <ProducaoDoMes
        aberto={verProducao}
        onFechar={() => setVerProducao(false)}
        filtros={params}
      />
    </div>
  );
}
