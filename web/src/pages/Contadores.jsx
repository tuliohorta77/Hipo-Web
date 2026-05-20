// web/src/pages/Contadores.jsx
//
// Dashboard de Contadores (Hunter / Farmer / Outros).
//
// Renomeado de "Carteira" pra "Contadores" no nivel visual.
// O backend continua respondendo em /api/carteira/*.
//
// Layout:
//   - Aba Hunter:  1 linha por colaborador, KPIs agregados. Clica → expande
//                  inline mostrando a TABELA COMPLETA antiga (timeline mensal,
//                  atrasadas, futuras, leads). Cada linha de grupo é clicável
//                  e abre o drawer lateral com detalhes (CNPJs + tarefas).
//   - Aba Farmer:  igual, mas com bolinhas verticais por semana (slots fixos
//                  para alinhar os labels) e drilldown com timeline semanal
//                  por grupo.
//   - Aba Outros:  grupo a grupo (fila de correção — sem colab definido).
//
// Performance: o dashboard já vem com os 'grupos' detalhados embutidos
// (sem segundo request) — drilldown é instantâneo.

import { useState, useEffect, useCallback, useMemo } from 'react';
import {
  RefreshCw,
  Settings,
  Users,
  AlertCircle,
  Target,
  Activity,
  Search,
  History,
  ChevronRight,
  ChevronDown,
  X,
} from 'lucide-react';
import api from '../api';

import CarteiraBolinhasSemana from '../components/CarteiraBolinhasSemana';
import CarteiraTimeline from '../components/CarteiraTimeline';
import ConfigColaboradoresModal from '../components/ConfigColaboradoresModal';
import CarteiraGrupoDrawer from '../components/CarteiraGrupoDrawer';

import Card from '../components/ui/Card';
import KpiCard from '../components/ui/KpiCard';
import PageHeader from '../components/ui/PageHeader';
import Button from '../components/ui/Button';
import UploadButton from '../components/ui/UploadButton';
import AlertMessage from '../components/ui/AlertMessage';
import Empty from '../components/ui/Empty';
import Badge from '../components/ui/Badge';
import Table, { Th, Tr, Td } from '../components/ui/Table';
import MiniFunil, { agregarFunis } from '../components/ui/MiniFunil';

const ABAS = [
  { v: 'EC_HUNTER', label: 'Hunter', Icon: Target,      hint: 'Meta: ≥1 tarefa por mês' },
  { v: 'EC_FARMER', label: 'Farmer', Icon: Activity,    hint: 'Meta: ≥1 reunião por semana' },
  { v: 'OUTROS',    label: 'Outros', Icon: AlertCircle, hint: 'Reclassifique no botão Configurar' },
];

function corCompliance(pct) {
  if (pct >= 75) return 'text-emerald-700';
  if (pct >= 50) return 'text-amber-700';
  return 'text-red-700';
}

export default function Contadores() {
  const [resumo, setResumo] = useState(null);
  const [aba, setAba] = useState('EC_HUNTER');
  const [hunter, setHunter] = useState({ total: 0, linhas: [] });
  const [farmer, setFarmer] = useState({ total: 0, linhas: [] });
  const [outros, setOutros] = useState([]);

  // Filtros do drilldown (operam só nos grupos do colaborador expandido)
  const [filtrosDrill, setFiltrosDrill] = useState({
    tarefa_atrasada: false,
    sem_tarefa_futura: false,
    busca_grupo: '',
  });

  // Drilldown inline: id do colaborador atualmente expandido
  const [expandido, setExpandido] = useState(null);

  // Mini-funil: map id_grupo → { suspect, cadencia, qualificacao, apresentacao, negociacao }
  // Carregado sob demanda quando expande um colaborador.
  const [funilPorGrupo, setFunilPorGrupo] = useState({});
  const [funilLoading, setFunilLoading] = useState(false);
  const [funilVersao, setFunilVersao] = useState(0);

  // Uploads / modais
  const [uploading, setUploading] = useState(null); // null | "CARTEIRA" | "TAREFAS"
  const [msg, setMsg] = useState(null);
  const [modalConfig, setModalConfig] = useState(false);
  const [drawerGrupo, setDrawerGrupo] = useState(null);
  const [historicoAberto, setHistoricoAberto] = useState(false);
  const [historico, setHistorico] = useState([]);

  // ── Carregamento ────────────────────────────────────────────

  const carregarResumo = useCallback(async () => {
    try {
      const { data } = await api.get('/carteira/resumo');
      setResumo(data);
    } catch {
      setResumo(null);
    }
  }, []);

  const carregarHunter = useCallback(async () => {
    try {
      const { data } = await api.get('/carteira/dashboard/hunter');
      setHunter(data);
    } catch {
      setHunter({ total: 0, linhas: [] });
    }
  }, []);

  const carregarFarmer = useCallback(async () => {
    try {
      const { data } = await api.get('/carteira/dashboard/farmer');
      setFarmer(data);
    } catch {
      setFarmer({ total: 0, linhas: [] });
    }
  }, []);

  const carregarOutros = useCallback(async () => {
    try {
      const { data } = await api.get('/carteira/grupos?funcao=OUTROS');
      setOutros(data.grupos || []);
    } catch {
      setOutros([]);
    }
  }, []);

  useEffect(() => { carregarResumo(); }, [carregarResumo]);
  useEffect(() => { carregarHunter(); }, [carregarHunter]);
  useEffect(() => { carregarFarmer(); }, [carregarFarmer]);
  useEffect(() => { carregarOutros(); }, [carregarOutros]);

  // Limpar drilldown e filtros ao trocar de aba
  useEffect(() => {
    setExpandido(null);
    setFiltrosDrill({ tarefa_atrasada: false, sem_tarefa_futura: false, busca_grupo: '' });
  }, [aba]);

  // ── Drilldown (instantâneo: usa grupos embutidos no payload) ─

  async function toggleExpandir(colab_id) {
    if (!colab_id) return;
    const fechando = expandido === colab_id;
    setExpandido(fechando ? null : colab_id);
    setFiltrosDrill({ tarefa_atrasada: false, sem_tarefa_futura: false, busca_grupo: '' });
    if (fechando) return;

    // Buscar funil agregado de todos os grupos desse colaborador
    const linha = [...hunter.linhas, ...farmer.linhas].find(
      (l) => l.colaborador_id === colab_id
    );
    if (!linha || !linha.grupos?.length) return;

    const idGrupos = linha.grupos
      .map((g) => g.id_grupo)
      .filter(Boolean)
      .filter((gid) => !funilPorGrupo[gid]); // só os ainda não carregados

    if (idGrupos.length === 0) return;

    setFunilLoading(true);
    try {
      const { data } = await api.post('/clientes/funil-por-grupos', {
        id_grupos: idGrupos,
      });
      setFunilPorGrupo((atual) => ({ ...atual, ...(data.por_grupo || {}) }));
      setFunilVersao((v) => v + 1);
    } catch (e) {
      // Erro silencioso — mini-funil só não aparece se a chamada falhou
      console.error('Funil:', e);
    } finally {
      setFunilLoading(false);
    }
  }

  function aplicarFiltrosDrill(grupos) {
    let out = grupos;
    if (filtrosDrill.tarefa_atrasada) {
      out = out.filter((g) => g.tarefas_atrasadas > 0);
    }
    if (filtrosDrill.sem_tarefa_futura) {
      out = out.filter((g) => g.tarefas_futuras === 0);
    }
    const q = filtrosDrill.busca_grupo.trim().toLowerCase();
    if (q) {
      out = out.filter(
        (g) =>
          (g.nome_grupo || '').toLowerCase().includes(q) ||
          (g.contabilidade_principal || '').toLowerCase().includes(q),
      );
    }
    return out;
  }

  // ── Upload ──────────────────────────────────────────────────

  async function upload(tipo, file) {
    if (!file) return;
    setUploading(tipo);
    setMsg(null);
    const form = new FormData();
    form.append('arquivo', file);
    const endpoint =
      tipo === 'CARTEIRA'
        ? '/carteira/upload-carteira'
        : '/carteira/upload-tarefas';
    try {
      const { data } = await api.post(endpoint, form, {
        headers: { 'Content-Type': 'multipart/form-data' },
      });
      setMsg({ tipo: 'ok', texto: data.message });
      reloadAll();
    } catch (err) {
      const detail = err.response?.data?.detail;
      const texto =
        typeof detail === 'string'
          ? detail
          : Array.isArray(detail?.erros)
          ? detail.erros.join(' • ')
          : err.message;
      setMsg({ tipo: 'erro', texto: `Erro: ${texto}` });
    } finally {
      setUploading(null);
    }
  }

  async function toggleHistorico() {
    if (historicoAberto) {
      setHistoricoAberto(false);
      return;
    }
    try {
      const { data } = await api.get('/carteira/historico');
      setHistorico(data || []);
      setHistoricoAberto(true);
    } catch {
      setHistorico([]);
      setHistoricoAberto(true);
    }
  }

  function reloadAll() {
    carregarResumo();
    carregarHunter();
    carregarFarmer();
    carregarOutros();
  }

  // ── Lista da aba ativa (sem mais filtro de busca por colaborador) ──

  const linhasAba = useMemo(() => {
    return aba === 'EC_HUNTER' ? hunter.linhas : farmer.linhas;
  }, [aba, hunter.linhas, farmer.linhas]);

  const abaInfo = ABAS.find((a) => a.v === aba);

  const kpis = useMemo(() => {
    if (!resumo) return null;
    if (aba === 'EC_HUNTER') return resumo.hunter;
    if (aba === 'EC_FARMER') return resumo.farmer;
    return resumo.outros;
  }, [resumo, aba]);

  // ── Render ──────────────────────────────────────────────────

  return (
    <>
      <PageHeader
        title="Contadores"
        subtitle="Performance por colaborador — Hunter e Farmer."
        actions={
          <>
            <Button
              variant="ghost"
              size="md"
              icon={RefreshCw}
              onClick={reloadAll}
              aria-label="Atualizar"
            />
            <Button
              variant="ghost"
              size="md"
              icon={History}
              onClick={toggleHistorico}
              aria-label="Histórico"
            />
            <Button
              variant="secondary"
              icon={Settings}
              onClick={() => setModalConfig(true)}
            >
              <span className="hidden md:inline">Configurar</span>
            </Button>
            <UploadButton
              variant="secondary"
              label="Carteira"
              onChange={(e) => {
                upload('CARTEIRA', e.target.files[0]);
                e.target.value = '';
              }}
              loading={uploading === 'CARTEIRA'}
            />
            <UploadButton
              label="Tarefas"
              onChange={(e) => {
                upload('TAREFAS', e.target.files[0]);
                e.target.value = '';
              }}
              loading={uploading === 'TAREFAS'}
            />
          </>
        }
      />

      {msg && (
        <AlertMessage tipo={msg.tipo} className="mb-6">
          {msg.texto}
        </AlertMessage>
      )}

      {historicoAberto && (
        <Card padding="none" className="mb-4">
          <div className="px-5 py-3 border-b border-hipo-border flex items-center justify-between">
            <h3 className="text-sm font-semibold text-hipo-ink">Histórico de uploads</h3>
            <button
              onClick={() => setHistoricoAberto(false)}
              className="text-hipo-slate hover:text-hipo-ink p-1 rounded hover:bg-hipo-bg"
              aria-label="Fechar histórico"
            >
              <X size={16} />
            </button>
          </div>
          {historico.length === 0 ? (
            <Empty
              title="Nenhum upload registrado"
              description="Faça o primeiro upload da carteira ou de tarefas."
            />
          ) : (
            <Table className="[&_th]:!py-2 [&_th]:!text-[11px] [&_th]:!tracking-wide [&_td]:!py-1.5 [&_td]:!text-[13px]">
              <thead>
                <tr>
                  <Th>Data</Th>
                  <Th>Tipo</Th>
                  <Th>Arquivo</Th>
                  <Th>Usuário</Th>
                  <Th align="right">Linhas</Th>
                  <Th align="right">Válidas</Th>
                </tr>
              </thead>
              <tbody>
                {historico.map((h) => (
                  <Tr key={h.id}>
                    <Td className="text-hipo-slate">
                      {new Date(h.data_upload).toLocaleString('pt-BR')}
                    </Td>
                    <Td>
                      <Badge tone={h.tipo === 'CARTEIRA' ? 'info' : 'success'}>
                        {h.tipo}
                      </Badge>
                    </Td>
                    <Td className="truncate max-w-xs">{h.nome_arquivo}</Td>
                    <Td className="text-hipo-slate">{h.usuario_nome || '—'}</Td>
                    <Td align="right">{h.total_linhas}</Td>
                    <Td align="right" className="text-emerald-700 font-semibold">
                      {h.total_validos}
                    </Td>
                  </Tr>
                ))}
              </tbody>
            </Table>
          )}
        </Card>
      )}

      {/* Abas */}
      <div className="flex items-center gap-1 mb-6 border-b border-hipo-border">
        {ABAS.map(({ v, label, Icon }) => {
          const ativo = aba === v;
          const counter =
            v === 'EC_HUNTER' ? hunter.total
            : v === 'EC_FARMER' ? farmer.total
            : outros.length;
          return (
            <button
              key={v}
              onClick={() => setAba(v)}
              className={
                'relative flex items-center gap-2 px-4 h-11 text-sm font-medium transition-colors ' +
                (ativo ? 'text-hipo-blue' : 'text-hipo-slate hover:text-hipo-ink')
              }
            >
              <Icon size={16} />
              <span>{label}</span>
              {counter != null && (
                <span
                  className={
                    'text-xs font-medium px-1.5 py-0.5 rounded-full ' +
                    (ativo
                      ? 'bg-hipo-blueSoft text-hipo-blue'
                      : 'bg-hipo-bg text-hipo-slate')
                  }
                >
                  {counter}
                </span>
              )}
              {ativo && (
                <span className="absolute left-0 right-0 -bottom-px h-0.5 bg-hipo-blue rounded-full" />
              )}
            </button>
          );
        })}
      </div>

      {/* KPIs do topo */}
      {kpis && aba !== 'OUTROS' && (
        <div className="grid grid-cols-2 lg:grid-cols-4 gap-4 mb-6">
          <KpiCard
            label="Total de grupos"
            value={kpis.total_grupos}
            icon={Users}
            tone="blue"
          />
          <KpiCard
            label="Meta atingida"
            value={kpis.meta_atingida}
            hint={`${kpis.compliance_pct}% de compliance`}
            icon={Target}
            tone="emerald"
          />
          <KpiCard
            label="Com tarefa atrasada"
            value={kpis.com_tarefa_atrasada}
            icon={AlertCircle}
            tone="rose"
          />
          <KpiCard
            label="Leads do mês"
            value={kpis.leads_no_mes}
            icon={Target}
            tone="blue"
          />
        </div>
      )}

      {/* ── ABA HUNTER ──────────────────────────────────────── */}
      {aba === 'EC_HUNTER' && (
        <Card padding="none">
          <div className="px-5 py-3 border-b border-hipo-border flex items-center justify-between">
            <h3 className="text-sm font-semibold text-hipo-ink">
              {abaInfo.label} — {linhasAba.length} colaborador(es)
            </h3>
            <span className="text-xs text-hipo-slate">{abaInfo.hint}</span>
          </div>

          {linhasAba.length === 0 ? (
            <Empty
              title="Nenhum colaborador Hunter"
              description="Faça o upload da carteira ou classifique colaboradores no botão Configurar."
              icon={Users}
            />
          ) : (
            <Table className="[&_th]:!py-2 [&_th]:!text-[11px] [&_th]:!tracking-wide [&_td]:!py-1.5 [&_td]:!text-[13px]">
              <thead>
                <tr>
                  <Th className="w-8"></Th>
                  <Th>Colaborador</Th>
                  <Th align="center">Grupos</Th>
                  <Th align="center">Meta atingida</Th>
                  <Th align="center">Com atrasada</Th>
                  <Th align="center">Sem futura</Th>
                  <Th align="center">Leads / mês</Th>
                  <Th align="left">Funil (5 etapas ativas)</Th>
                </tr>
              </thead>
              <tbody>
                {linhasAba.map((l) => {
                  const aberto = expandido === l.colaborador_id;
                  return [
                    <Tr
                      key={l.colaborador_id}
                      onClick={() => toggleExpandir(l.colaborador_id)}
                      className={aberto ? 'bg-hipo-blueSoft hover:bg-hipo-blueSoft' : ''}
                    >
                      <Td className="text-hipo-muted">
                        {aberto ? <ChevronDown size={14} /> : <ChevronRight size={14} />}
                      </Td>
                      <Td className="font-semibold">{l.nome}</Td>
                      <Td align="center">{l.total_grupos}</Td>
                      <Td align="center">
                        <span className={`font-semibold ${corCompliance(l.compliance_pct)}`}>
                          {l.meta_atingida}
                        </span>
                        <span className="text-xs text-hipo-muted"> / {l.total_grupos}</span>
                      </Td>
                      <Td
                        align="center"
                        className={
                          l.tarefas_atrasadas > 0
                            ? 'text-red-700 font-semibold'
                            : 'text-hipo-muted'
                        }
                      >
                        {l.tarefas_atrasadas}
                      </Td>
                      <Td
                        align="center"
                        className={
                          l.sem_tarefa_futura > 0
                            ? 'text-amber-700 font-semibold'
                            : 'text-hipo-muted'
                        }
                      >
                        {l.sem_tarefa_futura}
                      </Td>
                      <Td align="center" className="text-hipo-blue font-semibold">
                        {l.leads_no_mes}
                      </Td>
                      <Td>
                        <MiniFunil
                          loading={expandido === l.colaborador_id && funilLoading}
                          dados={agregarFunis(
                            (l.grupos || [])
                              .map((g) => funilPorGrupo[g.id_grupo])
                              .filter(Boolean)
                          )}
                          vazio="—"
                        />
                      </Td>
                    </Tr>,
                    aberto && (
                      <tr key={`${l.colaborador_id}-drill-${funilVersao}`} className="bg-hipo-bg">
                        <td colSpan={8} className="px-5 py-4">
                          <DrilldownTabela
                            aba="EC_HUNTER"
                            grupos={aplicarFiltrosDrill(l.grupos)}
                            totalSemFiltro={l.grupos.length}
                            funilPorGrupo={funilPorGrupo}
                            filtros={filtrosDrill}
                            onFiltros={setFiltrosDrill}
                            onAbrirGrupo={(g) =>
                              setDrawerGrupo({
                                id_grupo: g.id_grupo,
                                nome_grupo: g.nome_grupo,
                              })
                            }
                          />
                        </td>
                      </tr>
                    ),
                  ];
                })}
              </tbody>
            </Table>
          )}
        </Card>
      )}

      {/* ── ABA FARMER ──────────────────────────────────────── */}
      {aba === 'EC_FARMER' && (
        <Card padding="none">
          <div className="px-5 py-3 border-b border-hipo-border flex items-center justify-between">
            <h3 className="text-sm font-semibold text-hipo-ink">
              {abaInfo.label} — {linhasAba.length} colaborador(es)
            </h3>
            <span className="text-xs text-hipo-slate">{abaInfo.hint}</span>
          </div>

          {linhasAba.length === 0 ? (
            <Empty
              title="Nenhum colaborador Farmer"
              description="Faça o upload da carteira ou classifique colaboradores no botão Configurar."
              icon={Users}
            />
          ) : (
            <>
              <Table className="[&_th]:!py-2 [&_th]:!text-[11px] [&_th]:!tracking-wide [&_td]:!py-1.5 [&_td]:!text-[13px]">
                <thead>
                  <tr>
                    <Th className="w-8"></Th>
                    <Th>Colaborador</Th>
                    <Th align="center">Semanas</Th>
                    <Th align="center">Com atrasada</Th>
                    <Th align="center">Com futura</Th>
                    <Th align="center">Leads / mês</Th>
                    <Th align="left">Funil (5 etapas ativas)</Th>
                  </tr>
                </thead>
                <tbody>
                  {linhasAba.map((l) => {
                    const aberto = expandido === l.colaborador_id;
                    return [
                      <Tr
                        key={l.colaborador_id}
                        onClick={() => toggleExpandir(l.colaborador_id)}
                        className={aberto ? 'bg-hipo-blueSoft hover:bg-hipo-blueSoft' : ''}
                      >
                        <Td className="text-hipo-muted align-top pt-5">
                          {aberto ? <ChevronDown size={14} /> : <ChevronRight size={14} />}
                        </Td>
                        <Td className="align-top pt-5">
                          <div className="flex flex-col">
                            <span className="font-semibold text-hipo-ink">{l.nome}</span>
                            <span className="text-xs text-hipo-slate">
                              {l.total_grupos} grupos · {l.total_contadores} contadores
                            </span>
                          </div>
                        </Td>
                        <Td>
                          <CarteiraBolinhasSemana semanas={l.semanas} />
                        </Td>
                        <Td
                          align="center"
                          className={
                            'align-top pt-5 ' +
                            (l.tarefas_atrasadas > 0
                              ? 'text-red-700 font-semibold'
                              : 'text-hipo-muted')
                          }
                        >
                          {l.tarefas_atrasadas}
                        </Td>
                        <Td
                          align="center"
                          className={
                            'align-top pt-5 ' +
                            (l.tarefas_futuras > 0
                              ? 'text-hipo-blue font-medium'
                              : 'text-hipo-muted')
                          }
                        >
                          {l.tarefas_futuras}
                        </Td>
                        <Td align="center" className="align-top pt-5 text-hipo-blue font-semibold">
                          {l.leads_no_mes}
                        </Td>
                        <Td className="align-top pt-5">
                          <MiniFunil
                            loading={expandido === l.colaborador_id && funilLoading}
                            dados={agregarFunis(
                              (l.grupos || [])
                                .map((g) => funilPorGrupo[g.id_grupo])
                                .filter(Boolean)
                            )}
                            vazio="—"
                          />
                        </Td>
                      </Tr>,
                      aberto && (
                        <tr key={`${l.colaborador_id}-drill-${funilVersao}`} className="bg-hipo-bg">
                          <td colSpan={7} className="px-5 py-4">
                            <DrilldownTabela
                              aba="EC_FARMER"
                              grupos={aplicarFiltrosDrill(l.grupos)}
                              totalSemFiltro={l.grupos.length}
                              funilPorGrupo={funilPorGrupo}
                              filtros={filtrosDrill}
                              onFiltros={setFiltrosDrill}
                              onAbrirGrupo={(g) =>
                                setDrawerGrupo({
                                  id_grupo: g.id_grupo,
                                  nome_grupo: g.nome_grupo,
                                })
                              }
                            />
                          </td>
                        </tr>
                      ),
                    ];
                  })}
                </tbody>
              </Table>

              <div className="px-5 py-3 border-t border-hipo-border bg-hipo-bg">
                <div className="flex flex-wrap gap-5 justify-center text-xs text-hipo-slate">
                  <span className="flex items-center gap-1.5">
                    <span className="w-3 h-3 rounded-full bg-emerald-600" />
                    Grupos com reunião na semana
                  </span>
                  <span className="flex items-center gap-1.5">
                    <span className="w-3 h-3 rounded-full bg-amber-500" />
                    Grupos sem reunião (semana já passou)
                  </span>
                  <span className="flex items-center gap-1.5">
                    <span className="w-3 h-3 rounded-full bg-slate-400" />
                    Grupos sem reunião ainda (semana corrente)
                  </span>
                </div>
              </div>
            </>
          )}
        </Card>
      )}

      {/* ── ABA OUTROS ──────────────────────────────────────── */}
      {aba === 'OUTROS' && (
        <Card padding="none">
          <div className="px-5 py-3 border-b border-hipo-border flex items-center justify-between">
            <h3 className="text-sm font-semibold text-hipo-ink">
              Outros — {outros.length} grupo(s)
            </h3>
            <span className="text-xs text-hipo-warning">{abaInfo.hint}</span>
          </div>

          {outros.length === 0 ? (
            <Empty
              title="Nenhum grupo nessa aba"
              description="Todos os grupos têm um colaborador Hunter ou Farmer atribuído."
            />
          ) : (
            <Table className="[&_th]:!py-2 [&_th]:!text-[11px] [&_th]:!tracking-wide [&_td]:!py-1.5 [&_td]:!text-[13px]">
              <thead>
                <tr>
                  <Th>Grupo</Th>
                  <Th align="center">CNPJs</Th>
                  <Th>Colaborador (planilha)</Th>
                  <Th align="center">Tarefas no mês</Th>
                </tr>
              </thead>
              <tbody>
                {outros.map((g) => (
                  <Tr
                    key={g.id_grupo}
                    onClick={() =>
                      setDrawerGrupo({
                        id_grupo: g.id_grupo,
                        nome_grupo: g.nome_grupo,
                      })
                    }
                  >
                    <Td>
                      <div className="flex flex-col">
                        <span className="font-semibold text-hipo-ink">
                          {g.nome_grupo || '—'}
                        </span>
                        <span className="text-xs text-hipo-slate">
                          {g.contabilidade_principal} · {g.cidade_uf}
                        </span>
                      </div>
                    </Td>
                    <Td align="center">{g.qtd_cnpj}</Td>
                    <Td className="text-hipo-slate">{g.colaborador_nome || '—'}</Td>
                    <Td align="center">{g.tarefas_mes_total}</Td>
                  </Tr>
                ))}
              </tbody>
            </Table>
          )}
        </Card>
      )}

      {resumo && (resumo.ultima_carteira || resumo.ultima_tarefas) && (
        <div className="mt-3 text-xs text-hipo-muted flex items-center gap-4 flex-wrap">
          {resumo.ultima_carteira && (
            <span>
              Carteira: {new Date(resumo.ultima_carteira).toLocaleString('pt-BR')}
            </span>
          )}
          {resumo.ultima_tarefas && (
            <span>
              Tarefas: {new Date(resumo.ultima_tarefas).toLocaleString('pt-BR')}
            </span>
          )}
        </div>
      )}

      <ConfigColaboradoresModal
        aberto={modalConfig}
        onFechar={() => setModalConfig(false)}
        onSalvo={reloadAll}
      />

      <CarteiraGrupoDrawer
        idGrupo={drawerGrupo?.id_grupo}
        nomeGrupo={drawerGrupo?.nome_grupo}
        onFechar={() => setDrawerGrupo(null)}
      />
    </>
  );
}

// ─────────────────────────────────────────────────────────────────
// DrilldownTabela — tabela completa de grupos de um colaborador
// (formato da tela antiga: timeline + atrasadas + futuras + leads)
// ─────────────────────────────────────────────────────────────────

function DrilldownTabela({
  aba,
  grupos,
  totalSemFiltro,
  filtros,
  onFiltros,
  onAbrirGrupo,
  funilPorGrupo,
}) {
  const ehFarmer = aba === 'EC_FARMER';
  const titulo =
    grupos.length === totalSemFiltro
      ? `${totalSemFiltro} grupo(s)`
      : `${grupos.length} de ${totalSemFiltro} grupo(s)`;

  return (
    <div className="bg-hipo-card border border-hipo-border rounded-lg overflow-hidden">
      {/* Filtros locais (mesma UX da tela antiga) */}
      <div className="px-4 py-3 border-b border-hipo-border bg-hipo-bg flex flex-wrap items-center gap-3">
        <span className="text-xs text-hipo-slate font-medium">{titulo}</span>

        <div className="relative flex-1 min-w-[200px]">
          <Search
            size={14}
            className="absolute left-3 top-1/2 -translate-y-1/2 text-hipo-muted"
          />
          <input
            value={filtros.busca_grupo}
            onChange={(e) =>
              onFiltros({ ...filtros, busca_grupo: e.target.value })
            }
            placeholder="Buscar grupo ou contabilidade..."
            onClick={(e) => e.stopPropagation()}
            className="w-full h-9 bg-hipo-card border border-hipo-border rounded-md pl-9 pr-3 text-sm text-hipo-ink placeholder:text-hipo-muted outline-none focus:border-hipo-blue focus:ring-2 focus:ring-blue-100"
          />
        </div>

        <label
          className="flex items-center gap-2 text-xs text-hipo-slate cursor-pointer hover:text-hipo-ink"
          onClick={(e) => e.stopPropagation()}
        >
          <input
            type="checkbox"
            checked={filtros.tarefa_atrasada}
            onChange={(e) =>
              onFiltros({ ...filtros, tarefa_atrasada: e.target.checked })
            }
            className="w-4 h-4 accent-hipo-blue cursor-pointer"
          />
          Tarefa atrasada
        </label>
        <label
          className="flex items-center gap-2 text-xs text-hipo-slate cursor-pointer hover:text-hipo-ink"
          onClick={(e) => e.stopPropagation()}
        >
          <input
            type="checkbox"
            checked={filtros.sem_tarefa_futura}
            onChange={(e) =>
              onFiltros({ ...filtros, sem_tarefa_futura: e.target.checked })
            }
            className="w-4 h-4 accent-hipo-blue cursor-pointer"
          />
          Sem tarefa futura
        </label>
      </div>

      {grupos.length === 0 ? (
        <p className="text-sm text-hipo-slate text-center py-6">
          Nenhum grupo nesse filtro.
        </p>
      ) : (
        <Table className="[&_th]:!py-2 [&_th]:!text-[11px] [&_th]:!tracking-wide [&_td]:!py-1.5 [&_td]:!text-[13px]">
          <thead>
            <tr>
              <Th className="w-6"></Th>
              <Th>Grupo</Th>
              <Th align="center">CNPJs</Th>
              <Th>Execução</Th>
              <Th align="center">Atrasadas</Th>
              <Th align="center">Futuras</Th>
              {ehFarmer && <Th align="center">Leads/mês</Th>}
              <Th align="left">Funil</Th>
            </tr>
          </thead>
          <tbody>
            {grupos.map((g) => (
              <Tr key={g.id_grupo} onClick={() => onAbrirGrupo(g)}>
                <Td className="text-hipo-muted">
                  <ChevronRight size={14} />
                </Td>
                <Td>
                  <div className="flex flex-col">
                    <span className="font-semibold text-hipo-ink">
                      {g.nome_grupo || '—'}
                      {g.colaboradores_multiplos && (
                        <Badge tone="warning" className="ml-2">
                          ⚠ Múlt
                        </Badge>
                      )}
                    </span>
                    <span className="text-xs text-hipo-slate mt-0.5">
                      {g.contabilidade_principal} · {g.cidade_uf}
                      {g.parceria && (
                        <span
                          className={`ml-2 ${
                            g.parceria === 'Parceiro'
                              ? 'text-emerald-700 font-medium'
                              : 'text-hipo-slate'
                          }`}
                        >
                          {g.parceria === 'Parceiro' ? '● parceiro' : '○ não parceiro'}
                        </span>
                      )}
                    </span>
                  </div>
                </Td>
                <Td align="center">{g.qtd_cnpj}</Td>
                <Td>
                  <CarteiraTimeline cells={g.timeline} compact />
                </Td>
                <Td
                  align="center"
                  className={
                    g.tarefas_atrasadas > 0
                      ? 'text-red-700 font-semibold'
                      : 'text-hipo-muted'
                  }
                >
                  {g.tarefas_atrasadas}
                </Td>
                <Td
                  align="center"
                  className={
                    g.tarefas_futuras > 0
                      ? 'text-hipo-blue font-medium'
                      : 'text-hipo-muted'
                  }
                >
                  {g.tarefas_futuras}
                </Td>
                {ehFarmer && (
                  <Td align="center" className="text-hipo-blue font-semibold">
                    {g.leads_no_mes || 0}
                  </Td>
                )}
                <Td onClick={(e) => e.stopPropagation()}>
                  <MiniFunil dados={funilPorGrupo[g.id_grupo]} vazio="—" />
                </Td>
              </Tr>
            ))}
          </tbody>
        </Table>
      )}
    </div>
  );
}
