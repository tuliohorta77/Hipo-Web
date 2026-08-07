// web/src/pages/crm/Oportunidades.jsx
//
// O funil. Dashboard operacional (diretriz pétrea 2): os KPIs do topo aplicam
// filtro na visão de baixo, e a visão de baixo permite agir sem sair da tela.
//
// Duas visões da MESMA lista, com toggle persistido no banco:
//
//   * KANBAN — para trabalhar o funil. Arrasta o cartão, muda a fase.
//   * TABELA — para conferir e comparar. Ordena, filtra, vê tudo junto.
//
// A preferência vai para usuarios_preferencias, não localStorage: o HIPO é a
// fonte primária, e a escolha deve acompanhar a pessoa entre máquinas.

import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import {
  Briefcase, Search, Plus, LayoutGrid, Table as TableIcon, X,
  TrendingUp, Trophy,
} from 'lucide-react';

import api from '../../api';
import KpiCard from '../../components/ui/KpiCard';
import Table, { Th, Tr, Td } from '../../components/ui/Table';
import Button from '../../components/ui/Button';
import Input, { Select } from '../../components/ui/Input';
import Modal from '../../components/ui/Modal';
import Badge from '../../components/ui/Badge';
import Empty from '../../components/ui/Empty';
import AlertMessage from '../../components/ui/AlertMessage';
import EntityPicker from '../../components/EntityPicker';
import KanbanOportunidades from '../../components/crm/KanbanOportunidades';
import OportunidadeDetalhe from '../../components/crm/OportunidadeDetalhe';
import ModalDesfecho from '../../components/crm/ModalDesfecho';

const POR_PAGINA = 50;
const CHAVE_VISAO = 'crm_oportunidades_visao';

// Seis etapas. 'suspect' é a boca do funil: empresa na base que ninguém ainda
// tocou. Vira 'lead' quando há contato e interesse demonstrado.
const FASES = {
  suspect: 'Suspect', lead: 'Lead', qualificacao: 'Qualificação',
  apresentacao: 'Apresentação', negociacao: 'Negociação', finalizado: 'Finalizado',
};

const FASES_ABERTAS = ['suspect', 'lead', 'qualificacao', 'apresentacao', 'negociacao'];

const TOM_STATUS = {
  ativa: 'success', suspensa: 'warning', conquistado: 'success',
  perdido: 'danger', cancelado: 'neutral',
};

const FILTROS_VAZIOS = {
  q: '', fase: '', status: '', envolvido_id: '', apenas_abertas: false,
};

function mensagemDeErro(err, padrao) {
  const d = err?.response?.data?.detail;
  if (typeof d === 'string') return d;
  if (Array.isArray(d) && d[0]?.msg) return d[0].msg;
  if (d?.mensagem) return d.mensagem;
  return padrao;
}

function formatarMoeda(v) {
  if (v === null || v === undefined) return '—';
  return Number(v).toLocaleString('pt-BR', { style: 'currency', currency: 'BRL' });
}

function formatarData(iso) {
  return iso ? new Date(iso).toLocaleDateString('pt-BR') : '—';
}

// Controles compactos da barra: 36px de altura, rótulo por aria-label em vez
// de <label> acima. O bloco de filtros antigo custava ~90px de altura, e cada
// pixel aqui sai da altura das colunas do kanban.
const CLASSE_CAMPO =
  'h-9 text-sm rounded-lg border border-hipo-border bg-hipo-card text-hipo-ink ' +
  'focus:outline-none focus:ring-2 focus:ring-hipo-blue';

function KpiBotao({ onClick, ativo, children }) {
  return (
    <button
      type="button"
      onClick={onClick}
      aria-pressed={ativo}
      className={
        'text-left w-full rounded-xl transition-shadow focus:outline-none ' +
        'focus-visible:ring-2 focus-visible:ring-hipo-blue ' +
        (ativo ? 'ring-2 ring-hipo-blue' : 'hover:shadow-md')
      }
    >
      {children}
    </button>
  );
}

// ── Criação ──────────────────────────────────────────────────────────

function FormNovaOportunidade({ aberto, contaFixa, onFechar, onCriada }) {
  const [conta, setConta] = useState(null);
  const [fase, setFase] = useState('suspect');
  const [temperatura, setTemperatura] = useState(50);
  const [valor, setValor] = useState('');
  const [previsao, setPrevisao] = useState('');
  const [descricao, setDescricao] = useState('');
  const [erro, setErro] = useState(null);
  const [salvando, setSalvando] = useState(false);

  useEffect(() => {
    if (!aberto) return;
    setConta(contaFixa || null);
    setFase('suspect');
    setTemperatura(50);
    setValor('');
    setPrevisao('');
    setDescricao('');
    setErro(null);
  }, [aberto, contaFixa]);

  async function salvar() {
    if (!conta) {
      setErro('Escolha a conta.');
      return;
    }
    setSalvando(true);
    setErro(null);
    try {
      const { data } = await api.post('/crm/oportunidades', {
        conta_id: conta.id,
        fase,
        temperatura: Number(temperatura),
        valor_mensalidade: valor === '' ? null : Number(valor),
        previsao_fechamento: previsao || null,
        descricao: descricao.trim() || null,
      });
      onCriada(data);
    } catch (err) {
      setErro(mensagemDeErro(err, 'Não foi possível criar a oportunidade.'));
    } finally {
      setSalvando(false);
    }
  }

  return (
    <Modal
      aberto={aberto}
      onFechar={onFechar}
      titulo="Nova oportunidade"
      subtitulo="O restante você completa na tela da oportunidade"
      size="md"
      footer={
        <div className="flex justify-end gap-2">
          <Button variant="ghost" onClick={onFechar}>Cancelar</Button>
          <Button onClick={salvar} loading={salvando}>Criar</Button>
        </div>
      }
    >
      <div className="space-y-4">
        {erro && <AlertMessage tipo="erro">{erro}</AlertMessage>}

        <EntityPicker
          label="Conta *"
          value={conta}
          disabled={Boolean(contaFixa)}
          onChange={setConta}
          buscar={async (q) => (await api.get('/crm/contas/busca', { params: { q } })).data}
          paraItem={(c) => ({
            id: c.id, titulo: c.razao_social, subtitulo: c.cnpj_formatado,
          })}
          placeholder="Buscar empresa…"
          hint={contaFixa ? 'Criando dentro desta conta.' : undefined}
        />

        <div className="grid grid-cols-2 gap-4">
          <Select label="Fase" value={fase} onChange={(e) => setFase(e.target.value)}>
            {FASES_ABERTAS.map((f) => (
              <option key={f} value={f}>{FASES[f]}</option>
            ))}
          </Select>
          <Select
            label="Temperatura"
            value={temperatura}
            onChange={(e) => setTemperatura(e.target.value)}
          >
            {[0, 10, 20, 30, 40, 50, 60, 70, 80, 90].map((t) => (
              <option key={t} value={t}>{t}</option>
            ))}
          </Select>
        </div>

        <div className="grid grid-cols-2 gap-4">
          <Input
            label="Mensalidade (R$)"
            type="number"
            min="0"
            step="0.01"
            value={valor}
            onChange={(e) => setValor(e.target.value)}
          />
          <Input
            label="Previsão de fechamento"
            type="date"
            value={previsao}
            onChange={(e) => setPrevisao(e.target.value)}
          />
        </div>

        <Input
          label="Descrição"
          value={descricao}
          onChange={(e) => setDescricao(e.target.value)}
        />
      </div>
    </Modal>
  );
}

// ── Página ───────────────────────────────────────────────────────────

export default function Oportunidades() {
  const [visao, setVisao] = useState(null);   // null = ainda carregando a preferência
  const [resumo, setResumo] = useState(null);
  const [lista, setLista] = useState({ total: 0, itens: [] });
  const [colunas, setColunas] = useState([]);
  const [usuarios, setUsuarios] = useState([]);
  const [filtros, setFiltros] = useState(FILTROS_VAZIOS);
  const [busca, setBusca] = useState('');
  const [pagina, setPagina] = useState(0);
  const [carregando, setCarregando] = useState(true);
  const [erro, setErro] = useState(null);
  const [novaAberta, setNovaAberta] = useState(false);
  const [detalhe, setDetalhe] = useState(null);
  const [desfechoDe, setDesfechoDe] = useState(null);
  const [kpiAtivo, setKpiAtivo] = useState(null);
  const [acaoSalvar, setAcaoSalvar] = useState(null);
  const debounce = useRef(null);

  // O `f.q === busca ? f : ...` nao e microtuning: devolver o MESMO objeto faz
  // o React abortar o re-render. Sem isso, o timer dispara uma vez na montagem
  // com a busca vazia, cria um `filtros` novo por identidade, o useMemo de
  // `params` recalcula, o useCallback de `carregar` troca e a tela busca tudo
  // de novo — piscando o estado de carregando e desmontando o conteudo que ja
  // estava na tela.
  useEffect(() => {
    clearTimeout(debounce.current);
    debounce.current = setTimeout(() => {
      setFiltros((f) => (f.q === busca ? f : { ...f, q: busca }));
      setPagina((p) => (p === 0 ? p : 0));
    }, 350);
    return () => clearTimeout(debounce.current);
  }, [busca]);

  // Preferência de visão: carrega uma vez, com kanban como padrão.
  useEffect(() => {
    api.get('/crm/dominio/preferencias')
      .then(({ data }) => {
        const p = data.find((x) => x.chave === CHAVE_VISAO);
        setVisao(p?.valor === 'tabela' ? 'tabela' : 'kanban');
      })
      .catch(() => setVisao('kanban'));
    api.get('/crm/dominio/usuarios')
      .then(({ data }) => setUsuarios(data))
      .catch(() => setUsuarios([]));
  }, []);

  async function trocarVisao(nova) {
    setVisao(nova);
    try {
      await api.put(`/crm/dominio/preferencias/${CHAVE_VISAO}`, { valor: nova });
    } catch {
      // Preferência é conforto, não função: se falhar, a visão da sessão já
      // mudou e o usuário não fica travado.
    }
  }

  // Depende dos VALORES, nao do objeto `filtros`. Qualquer troca de identidade
  // do estado sem mudanca real de conteudo passaria por aqui e viraria refetch.
  const params = useMemo(() => {
    const p = {};
    if (filtros.q) p.q = filtros.q;
    if (filtros.envolvido_id) p.envolvido_id = filtros.envolvido_id;
    return p;
  }, [filtros.q, filtros.envolvido_id]);

  const carregar = useCallback(async () => {
    if (!visao) return;
    setCarregando(true);
    setErro(null);
    try {
      const [kpis, dados] = await Promise.all([
        api.get('/crm/oportunidades/resumo'),
        visao === 'kanban'
          ? api.get('/crm/oportunidades/kanban', { params })
          : api.get('/crm/oportunidades', {
              params: {
                ...params,
                ...(filtros.fase ? { fase: filtros.fase } : {}),
                ...(filtros.status ? { status: filtros.status } : {}),
                apenas_abertas: filtros.apenas_abertas || undefined,
                limit: POR_PAGINA,
                offset: pagina * POR_PAGINA,
              },
            }),
      ]);
      setResumo(kpis.data);
      if (visao === 'kanban') setColunas(dados.data);
      else setLista(dados.data);
    } catch (err) {
      setErro(mensagemDeErro(err, 'Não foi possível carregar o funil.'));
    } finally {
      setCarregando(false);
    }
  }, [visao, params, filtros.fase, filtros.status, filtros.apenas_abertas, pagina]);

  useEffect(() => { carregar(); }, [carregar]);

  const carregarDetalhe = useCallback(async (id) => {
    const { data } = await api.get(`/crm/oportunidades/${id}`);
    return data;
  }, []);

  async function abrir(id) {
    setErro(null);
    try {
      setDetalhe(await carregarDetalhe(id));
    } catch (err) {
      setErro(mensagemDeErro(err, 'Não foi possível abrir a oportunidade.'));
    }
  }

  const recarregarDetalhe = useCallback(async () => {
    if (!detalhe) return;
    try {
      setDetalhe(await carregarDetalhe(detalhe.id));
      carregar();
    } catch (err) {
      setErro(mensagemDeErro(err, 'Não foi possível recarregar a oportunidade.'));
    }
  }, [detalhe, carregarDetalhe, carregar]);

  const aoSalvar = useCallback((atualizada) => {
    setDetalhe(atualizada);
    carregar();
  }, [carregar]);

  async function mover(id, fase) {
    setErro(null);
    try {
      await api.patch(`/crm/oportunidades/${id}/fase`, { fase });
      carregar();
    } catch (err) {
      setErro(mensagemDeErro(err, 'Não foi possível mover a oportunidade.'));
    }
  }

  function alternarKpi(chave, parciais) {
    const base = { ...FILTROS_VAZIOS, q: filtros.q };
    if (kpiAtivo === chave) {
      setKpiAtivo(null);
      setFiltros(base);
    } else {
      setKpiAtivo(chave);
      setFiltros({ ...base, ...parciais });
    }
    setPagina(0);
  }

  function limpar() {
    setFiltros(FILTROS_VAZIOS);
    setBusca('');
    setKpiAtivo(null);
    setPagina(0);
  }

  const temFiltro =
    JSON.stringify({ ...filtros, q: '' }) !== JSON.stringify({ ...FILTROS_VAZIOS, q: '' })
    || Boolean(filtros.q);

  const totalPaginas = Math.max(1, Math.ceil(lista.total / POR_PAGINA));

  return (
    // h-full + min-h-0: a tela ocupa a altura da viewport e NÃO rola. Quem
    // rola é cada coluna do kanban (ou o corpo da tabela). O container que
    // torna isso possível é o <main> do Layout — ver o comentário lá.
    <div className="h-full min-h-0 flex flex-col gap-3">

      {/* ── Barra: título, filtros, visão e ação, tudo em uma linha ── */}
      <div className="shrink-0 flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="text-2xl font-semibold text-hipo-ink leading-tight">
            Oportunidades
          </h1>
          <p className="text-sm text-hipo-slate">Funil de vendas</p>
        </div>

        <div className="flex flex-wrap items-center gap-2">
          <div className="relative">
            <Search
              size={15}
              className="absolute left-2.5 top-1/2 -translate-y-1/2 text-hipo-muted pointer-events-none"
              aria-hidden="true"
            />
            <input
              aria-label="Buscar"
              placeholder="Número, empresa ou descrição"
              value={busca}
              onChange={(e) => setBusca(e.target.value)}
              className={`${CLASSE_CAMPO} w-60 pl-8 pr-2 placeholder:text-hipo-muted`}
            />
          </div>

          <select
            aria-label="Envolvido"
            value={filtros.envolvido_id}
            onChange={(e) => {
              setFiltros((f) => ({ ...f, envolvido_id: e.target.value }));
              setPagina(0);
            }}
            className={`${CLASSE_CAMPO} px-2`}
          >
            <option value="">Todos</option>
            {usuarios.map((u) => <option key={u.id} value={u.id}>{u.nome}</option>)}
          </select>

          {/*
            Fase só na tabela: no kanban a fase É a coluna, e filtrar por fase
            deixaria a tela com uma coluna cheia e cinco vazias.
          */}
          {visao === 'tabela' && (
            <select
              aria-label="Fase"
              value={filtros.fase}
              onChange={(e) => {
                setFiltros((f) => ({ ...f, fase: e.target.value }));
                setPagina(0);
              }}
              className={`${CLASSE_CAMPO} px-2`}
            >
              <option value="">Todas as fases</option>
              {Object.entries(FASES).map(([v, r]) => <option key={v} value={v}>{r}</option>)}
            </select>
          )}

          {temFiltro && (
            <button
              type="button"
              onClick={limpar}
              aria-label="Limpar filtros"
              title="Limpar filtros"
              className="h-9 w-9 inline-flex items-center justify-center rounded-lg border border-hipo-border text-hipo-slate hover:bg-hipo-bg transition-colors"
            >
              <X size={15} />
            </button>
          )}

          <div className="flex rounded-lg border border-hipo-border overflow-hidden">
            <button
              type="button"
              onClick={() => trocarVisao('kanban')}
              aria-pressed={visao === 'kanban'}
              aria-label="Ver como kanban"
              className={
                'h-9 px-3 text-sm inline-flex items-center gap-1.5 transition-colors ' +
                (visao === 'kanban'
                  ? 'bg-hipo-blue text-white'
                  : 'bg-hipo-card text-hipo-slate hover:bg-hipo-bg')
              }
            >
              <LayoutGrid size={15} />Kanban
            </button>
            <button
              type="button"
              onClick={() => trocarVisao('tabela')}
              aria-pressed={visao === 'tabela'}
              aria-label="Ver como tabela"
              className={
                'h-9 px-3 text-sm inline-flex items-center gap-1.5 transition-colors ' +
                (visao === 'tabela'
                  ? 'bg-hipo-blue text-white'
                  : 'bg-hipo-card text-hipo-slate hover:bg-hipo-bg')
              }
            >
              <TableIcon size={15} />Tabela
            </button>
          </div>

          <Button icon={Plus} onClick={() => setNovaAberta(true)}>Nova oportunidade</Button>
        </div>
      </div>

      {erro && (
        <div className="shrink-0"><AlertMessage tipo="erro">{erro}</AlertMessage></div>
      )}

      {/*
        Três KPIs, não quatro. "Sem próxima ação" saiu: concluir uma tarefa vai
        obrigar o vendedor a criar a próxima, então o indicador nasce zerado
        para sempre — e um KPI que nunca sai de zero só ocupa altura.
      */}
      <div className="shrink-0 grid grid-cols-1 sm:grid-cols-3 gap-3">
        <KpiBotao
          ativo={kpiAtivo === 'abertas'}
          onClick={() => alternarKpi('abertas', { apenas_abertas: true })}
        >
          <KpiCard
            label="Em aberto"
            value={resumo?.abertas ?? '—'}
            hint={resumo ? formatarMoeda(resumo.ticket_aberto) : undefined}
            icon={Briefcase}
            tone="blue"
          />
        </KpiBotao>

        <KpiBotao ativo={false} onClick={() => {}}>
          <KpiCard
            label="Previsto no mês"
            value={resumo ? formatarMoeda(resumo.previsto_no_mes) : '—'}
            hint="mensalidade das ativas"
            icon={TrendingUp}
            tone="emerald"
          />
        </KpiBotao>

        <KpiBotao ativo={false} onClick={() => {}}>
          <KpiCard
            label="Ganhas no mês"
            value={resumo?.ganhas_mes ?? '—'}
            hint={resumo ? `${resumo.perdidas_mes} perdidas` : undefined}
            icon={Trophy}
            tone="violet"
          />
        </KpiBotao>
      </div>

      {/* ── Área do funil: come toda a altura restante ── */}
      <div className="flex-1 min-h-0 flex flex-col rounded-xl border border-hipo-border bg-hipo-card">
        <div className="shrink-0 flex items-baseline justify-between gap-2 px-4 py-2 border-b border-hipo-border">
          <h2 className="text-sm font-semibold text-hipo-ink">
            {visao === 'kanban'
              ? 'Funil'
              : `${lista.total} oportunidade${lista.total === 1 ? '' : 's'}`}
          </h2>
          {temFiltro && <span className="text-xs text-hipo-slate">resultado filtrado</span>}
        </div>

        <div className="flex-1 min-h-0 p-3">
          {visao === 'kanban' ? (
            <KanbanOportunidades
              colunas={colunas}
              carregando={carregando || !visao}
              onAbrir={abrir}
              onMover={mover}
              onDesfecho={setDesfechoDe}
            />
          ) : carregando ? (
            <p className="py-10 text-center text-sm text-hipo-slate">Carregando…</p>
          ) : lista.itens.length === 0 ? (
            <Empty
              title={temFiltro ? 'Nenhuma oportunidade com esses filtros' : 'Nenhuma oportunidade'}
              description={temFiltro ? 'Ajuste os filtros.' : 'Crie a primeira para começar o funil.'}
              icon={Briefcase}
              action={
                temFiltro
                  ? <Button variant="secondary" onClick={limpar}>Limpar filtros</Button>
                  : <Button icon={Plus} onClick={() => setNovaAberta(true)}>Nova oportunidade</Button>
              }
            />
          ) : (
            <div className="h-full min-h-0 flex flex-col">
              {/* O scroll da tabela é aqui dentro, não na página. */}
              <div className="flex-1 min-h-0 overflow-auto border border-hipo-border rounded-lg">
                <Table>
                  <thead>
                    <tr>
                      <Th>Número</Th>
                      <Th>Empresa</Th>
                      <Th>Fase</Th>
                      <Th>Status</Th>
                      <Th align="right">Mensalidade</Th>
                      <Th align="right">Temp.</Th>
                      <Th>Previsão</Th>
                      <Th>Envolvidos</Th>
                    </tr>
                  </thead>
                  <tbody>
                    {lista.itens.map((o) => (
                      <Tr key={o.id} onClick={() => abrir(o.id)}>
                        <Td className="font-mono text-sm">{o.numero}</Td>
                        <Td>
                          <span className="font-medium text-hipo-ink">{o.conta_razao_social}</span>
                          {o.contato_nome && (
                            <span className="block text-xs text-hipo-slate">{o.contato_nome}</span>
                          )}
                        </Td>
                        <Td>{FASES[o.fase] || o.fase}</Td>
                        <Td>
                          <Badge tone={TOM_STATUS[o.status] || 'neutral'}>{o.status}</Badge>
                          {o.fase_desfecho && (
                            <span className="block text-xs text-hipo-muted">
                              de {FASES[o.fase_desfecho]}
                            </span>
                          )}
                        </Td>
                        <Td align="right">{formatarMoeda(o.valor_mensalidade)}</Td>
                        <Td align="right">
                          {o.temperatura ?? <span className="text-hipo-muted">—</span>}
                        </Td>
                        <Td>{formatarData(o.previsao_fechamento)}</Td>
                        <Td>
                          <div className="flex flex-wrap gap-1">
                            {(o.envolvidos || []).map((e) => (
                              <Badge key={`${e.usuario_id}-${e.papel}`} tone="neutral">
                                {e.papel}
                              </Badge>
                            ))}
                          </div>
                        </Td>
                      </Tr>
                    ))}
                  </tbody>
                </Table>
              </div>

              {totalPaginas > 1 && (
                <div className="shrink-0 flex items-center justify-between pt-3">
                  <span className="text-sm text-hipo-slate">
                    Página {pagina + 1} de {totalPaginas}
                  </span>
                  <div className="flex gap-2">
                    <Button
                      size="sm" variant="secondary" disabled={pagina === 0}
                      onClick={() => setPagina((p) => p - 1)}
                    >
                      Anterior
                    </Button>
                    <Button
                      size="sm" variant="secondary" disabled={pagina + 1 >= totalPaginas}
                      onClick={() => setPagina((p) => p + 1)}
                    >
                      Próxima
                    </Button>
                  </div>
                </div>
              )}
            </div>
          )}
        </div>
      </div>

      <FormNovaOportunidade
        aberto={novaAberta}
        onFechar={() => setNovaAberta(false)}
        onCriada={(o) => { setNovaAberta(false); setDetalhe(o); carregar(); }}
      />

      <ModalDesfecho
        oportunidade={desfechoDe}
        onFechar={() => setDesfechoDe(null)}
        onConcluido={(o) => {
          setDesfechoDe(null);
          if (detalhe?.id === o.id) setDetalhe(o);
          carregar();
        }}
      />

      <Modal
        aberto={Boolean(detalhe)}
        onFechar={() => { setDetalhe(null); setAcaoSalvar(null); }}
        titulo={detalhe ? `${detalhe.numero} · ${detalhe.conta_razao_social}` : undefined}
        subtitulo={detalhe ? FASES[detalhe.fase] : undefined}
        size="full"
        bodySemPadding
        footer={
          <div className="flex items-center justify-between gap-3">
            <span className="text-xs text-hipo-slate">
              {acaoSalvar?.sujo ? 'Alterações não salvas' : 'Tudo salvo'}
            </span>
            <div className="flex gap-2">
              <Button variant="ghost" onClick={() => { setDetalhe(null); setAcaoSalvar(null); }}>
                Fechar
              </Button>
              <Button
                onClick={() => acaoSalvar?.salvar()}
                disabled={!acaoSalvar?.sujo}
                loading={acaoSalvar?.salvando}
              >
                Salvar
              </Button>
            </div>
          </div>
        }
      >
        {detalhe && (
          <OportunidadeDetalhe
            oportunidade={detalhe}
            onRecarregar={recarregarDetalhe}
            onSalvo={aoSalvar}
            onDesfecho={setDesfechoDe}
            registrarSalvar={setAcaoSalvar}
          />
        )}
      </Modal>
    </div>
  );
}
