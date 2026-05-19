// web/src/pages/Carteira.jsx
//
// Dashboard da Carteira de Hunter e Farmer.
// Layout: 1 linha por colaborador, drilldown inline (clique na linha)
// abre a lista de grupos/contadores do colaborador. Layout aprovado
// no mockup v2 (linhas + bolinhas semanais pro Farmer).

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

const ABAS = [
  { v: 'EC_HUNTER', label: 'Hunter', Icon: Target,      hint: 'Meta: ≥1 tarefa por mês' },
  { v: 'EC_FARMER', label: 'Farmer', Icon: Activity,    hint: 'Meta: ≥1 reunião por semana' },
  { v: 'OUTROS',    label: 'Outros', Icon: AlertCircle, hint: 'Reclassifique no botão Configurar' },
];

// Cores semânticas pro compliance (consistentes com o manual de marca)
function corCompliance(pct) {
  if (pct >= 75) return 'text-emerald-700';
  if (pct >= 50) return 'text-amber-700';
  return 'text-red-700';
}

export default function Carteira() {
  const [resumo, setResumo] = useState(null);
  const [aba, setAba] = useState('EC_HUNTER');
  const [hunter, setHunter] = useState({ total: 0, linhas: [] });
  const [farmer, setFarmer] = useState({ total: 0, linhas: [] });
  const [outros, setOutros] = useState([]);
  const [busca, setBusca] = useState('');

  // Drilldown inline: nome do colaborador atualmente expandido
  const [drilldown, setDrilldown] = useState({ colab_id: null, grupos: [], loading: false });

  // Estado de uploads e modais
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
    // 'Outros' continua usando o endpoint antigo de grupos — não tem
    // colaborador majoritário definido, então a granularidade por
    // grupo continua sendo a mais útil aqui (fila de correção).
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

  // Limpar drilldown ao trocar de aba
  useEffect(() => {
    setDrilldown({ colab_id: null, grupos: [], loading: false });
  }, [aba]);

  // ── Drilldown de colaborador ────────────────────────────────

  async function toggleDrilldown(colab_id) {
    if (!colab_id) return;
    if (drilldown.colab_id === colab_id) {
      setDrilldown({ colab_id: null, grupos: [], loading: false });
      return;
    }
    setDrilldown({ colab_id, grupos: [], loading: true });
    try {
      const { data } = await api.get(`/carteira/colaboradores/${colab_id}/grupos`);
      setDrilldown({ colab_id, grupos: data.grupos || [], loading: false });
    } catch {
      setDrilldown({ colab_id, grupos: [], loading: false });
    }
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

  // ── Filtro de busca ─────────────────────────────────────────

  const linhasFiltradas = useMemo(() => {
    const fonte = aba === 'EC_HUNTER' ? hunter.linhas : farmer.linhas;
    if (!busca.trim()) return fonte;
    const q = busca.trim().toLowerCase();
    return fonte.filter((l) => (l.nome || '').toLowerCase().includes(q));
  }, [aba, hunter.linhas, farmer.linhas, busca]);

  const abaInfo = ABAS.find((a) => a.v === aba);

  // ── KPIs do topo (da aba ativa, igual ao layout anterior) ───

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
        title="Carteira"
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

      {/* Histórico expansível */}
      {historicoAberto && (
        <Card padding="none" className="mb-4">
          <div className="px-5 py-3 border-b border-hipo-border flex items-center justify-between">
            <h3 className="text-sm font-semibold text-hipo-ink">
              Histórico de uploads
            </h3>
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
            <Table>
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
                (ativo
                  ? 'text-hipo-blue'
                  : 'text-hipo-slate hover:text-hipo-ink')
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

      {/* KPIs do topo (resumo geral da aba) */}
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
            label="Tarefa atrasada"
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

      {/* Busca por colaborador */}
      {aba !== 'OUTROS' && (
        <Card padding="sm" className="mb-4">
          <div className="relative">
            <Search
              size={16}
              className="absolute left-3 top-1/2 -translate-y-1/2 text-hipo-muted"
            />
            <input
              value={busca}
              onChange={(e) => setBusca(e.target.value)}
              placeholder="Buscar colaborador..."
              className="w-full h-10 bg-hipo-card border border-hipo-border rounded-lg pl-10 pr-3 text-sm text-hipo-ink placeholder:text-hipo-muted outline-none focus:border-hipo-blue focus:ring-2 focus:ring-blue-100"
            />
          </div>
        </Card>
      )}

      {/* ── ABA HUNTER ──────────────────────────────────────── */}
      {aba === 'EC_HUNTER' && (
        <Card padding="none">
          <div className="px-5 py-3 border-b border-hipo-border flex items-center justify-between">
            <h3 className="text-sm font-semibold text-hipo-ink">
              {abaInfo.label} — {linhasFiltradas.length} colaborador(es)
            </h3>
            <span className="text-xs text-hipo-slate">{abaInfo.hint}</span>
          </div>

          {linhasFiltradas.length === 0 ? (
            <Empty
              title="Nenhum colaborador Hunter"
              description="Faça o upload da carteira ou classifique colaboradores no botão Configurar."
              icon={Users}
            />
          ) : (
            <Table>
              <thead>
                <tr>
                  <Th className="w-8"></Th>
                  <Th>Colaborador</Th>
                  <Th align="center">Grupos</Th>
                  <Th align="center">Meta atingida</Th>
                  <Th align="center">Atrasadas</Th>
                  <Th align="center">Sem futura</Th>
                  <Th align="center">Leads / mês</Th>
                </tr>
              </thead>
              <tbody>
                {linhasFiltradas.map((l) => {
                  const expandido = drilldown.colab_id === l.colaborador_id;
                  return [
                    <Tr
                      key={l.colaborador_id}
                      onClick={() => toggleDrilldown(l.colaborador_id)}
                      className={expandido ? 'bg-hipo-blueSoft hover:bg-hipo-blueSoft' : ''}
                    >
                      <Td className="text-hipo-muted">
                        {expandido ? <ChevronDown size={14} /> : <ChevronRight size={14} />}
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
                      <Td
                        align="center"
                        className="text-hipo-blue font-semibold"
                      >
                        {l.leads_no_mes}
                      </Td>
                    </Tr>,
                    expandido && (
                      <tr key={`${l.colaborador_id}-drill`} className="bg-hipo-bg">
                        <td colSpan={7} className="px-5 py-4">
                          <DrilldownGrupos
                            loading={drilldown.loading}
                            grupos={drilldown.grupos}
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
              {abaInfo.label} — {linhasFiltradas.length} colaborador(es)
            </h3>
            <span className="text-xs text-hipo-slate">{abaInfo.hint}</span>
          </div>

          {linhasFiltradas.length === 0 ? (
            <Empty
              title="Nenhum colaborador Farmer"
              description="Faça o upload da carteira ou classifique colaboradores no botão Configurar."
              icon={Users}
            />
          ) : (
            <>
              <Table>
                <thead>
                  <tr>
                    <Th className="w-8"></Th>
                    <Th>Colaborador</Th>
                    <Th align="center">Semanas</Th>
                    <Th align="center">Atrasadas</Th>
                    <Th align="center">Futuras</Th>
                    <Th align="center">Leads / mês</Th>
                  </tr>
                </thead>
                <tbody>
                  {linhasFiltradas.map((l) => {
                    const expandido = drilldown.colab_id === l.colaborador_id;
                    return [
                      <Tr
                        key={l.colaborador_id}
                        onClick={() => toggleDrilldown(l.colaborador_id)}
                        className={expandido ? 'bg-hipo-blueSoft hover:bg-hipo-blueSoft' : ''}
                      >
                        <Td className="text-hipo-muted">
                          {expandido ? <ChevronDown size={14} /> : <ChevronRight size={14} />}
                        </Td>
                        <Td>
                          <div className="flex flex-col">
                            <span className="font-semibold text-hipo-ink">{l.nome}</span>
                            <span className="text-xs text-hipo-slate">
                              {l.total_contadores} contadores
                            </span>
                          </div>
                        </Td>
                        <Td>
                          <CarteiraBolinhasSemana semanas={l.semanas} />
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
                            l.tarefas_futuras > 0
                              ? 'text-hipo-blue font-medium'
                              : 'text-hipo-muted'
                          }
                        >
                          {l.tarefas_futuras}
                        </Td>
                        <Td
                          align="center"
                          className="text-hipo-blue font-semibold"
                        >
                          {l.leads_no_mes}
                        </Td>
                      </Tr>,
                      expandido && (
                        <tr key={`${l.colaborador_id}-drill`} className="bg-hipo-bg">
                          <td colSpan={6} className="px-5 py-4">
                            <DrilldownGrupos
                              loading={drilldown.loading}
                              grupos={drilldown.grupos}
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

              {/* Legenda */}
              <div className="px-5 py-3 border-t border-hipo-border bg-hipo-bg">
                <div className="flex flex-wrap gap-5 justify-center text-xs text-hipo-slate">
                  <span className="flex items-center gap-1.5">
                    <span className="w-3 h-3 rounded-full bg-emerald-600" />
                    Contadores com reunião na semana
                  </span>
                  <span className="flex items-center gap-1.5">
                    <span className="w-3 h-3 rounded-full bg-amber-500" />
                    Sem reunião (semana já passou)
                  </span>
                  <span className="flex items-center gap-1.5">
                    <span className="w-3 h-3 rounded-full bg-slate-400" />
                    Sem reunião ainda (semana corrente)
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
            <Table>
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
                    <Td className="text-hipo-slate">
                      {g.colaborador_nome || '—'}
                    </Td>
                    <Td align="center">{g.tarefas_mes_total}</Td>
                  </Tr>
                ))}
              </tbody>
            </Table>
          )}
        </Card>
      )}

      {/* Datas dos últimos uploads */}
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
// Componente interno: lista de grupos no drilldown inline
// ─────────────────────────────────────────────────────────────────

function DrilldownGrupos({ loading, grupos, onAbrirGrupo }) {
  if (loading) {
    return (
      <p className="text-sm text-hipo-slate text-center py-4">Carregando...</p>
    );
  }
  if (!grupos.length) {
    return (
      <p className="text-sm text-hipo-slate text-center py-4">
        Nenhum grupo encontrado.
      </p>
    );
  }

  return (
    <div className="bg-hipo-card border border-hipo-border rounded-lg overflow-hidden">
      <div className="px-4 py-2 border-b border-hipo-border bg-hipo-bg">
        <p className="text-xs text-hipo-slate font-medium">
          {grupos.length} grupo(s) — clique para detalhar
        </p>
      </div>
      <ul className="divide-y divide-hipo-border">
        {grupos.map((g) => (
          <li
            key={g.id_grupo}
            onClick={() => onAbrirGrupo(g)}
            className="px-4 py-3 flex items-center justify-between gap-4 hover:bg-hipo-bg cursor-pointer transition-colors"
          >
            <div className="min-w-0">
              <p className="text-sm font-semibold text-hipo-ink truncate">
                {g.nome_grupo || '—'}
              </p>
              <p className="text-xs text-hipo-slate truncate">
                {g.contabilidade_principal} · {g.cidade_uf}
                {g.parceria && (
                  <span
                    className={`ml-2 ${
                      g.parceria === 'Parceiro'
                        ? 'text-emerald-700 font-medium'
                        : 'text-hipo-muted'
                    }`}
                  >
                    {g.parceria === 'Parceiro' ? '● parceiro' : '○ não parceiro'}
                  </span>
                )}
              </p>
            </div>
            <div className="flex items-center gap-4 text-xs shrink-0">
              {g.meta_atingida ? (
                <Badge tone="success">✓ meta</Badge>
              ) : (
                <Badge tone="danger">✗ sem meta</Badge>
              )}
              {g.tarefas_atrasadas > 0 && (
                <span className="text-red-700 font-medium">
                  {g.tarefas_atrasadas} atrasadas
                </span>
              )}
              {g.tarefas_futuras > 0 && (
                <span className="text-hipo-blue font-medium">
                  {g.tarefas_futuras} futuras
                </span>
              )}
              <ChevronRight size={14} className="text-hipo-muted" />
            </div>
          </li>
        ))}
      </ul>
    </div>
  );
}
