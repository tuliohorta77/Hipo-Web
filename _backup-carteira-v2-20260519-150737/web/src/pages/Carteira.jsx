// web/src/pages/Carteira.jsx
//
// Gestão da Carteira de Prospecção (Hunter) e Relacionamento (Farmer).
// Carrega-se por upload de duas planilhas (carteira + tarefas), agrupa
// por ID Grupo de Empresas, e mostra timeline de execução por grupo.

import { useState, useEffect, useCallback, useMemo } from 'react';
import {
  RefreshCw,
  Settings,
  Users,
  AlertCircle,
  Calendar,
  Target,
  Activity,
  Search,
  History,
  ChevronRight,
  Wifi,
  X,
} from 'lucide-react';
import api from '../api';

import CarteiraTimeline from '../components/CarteiraTimeline';
import ConfigColaboradoresModal from '../components/ConfigColaboradoresModal';
import CarteiraGrupoDrawer from '../components/CarteiraGrupoDrawer';

import Card, { CardHeader } from '../components/ui/Card';
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
  { v: 'OUTROS',    label: 'Outros', Icon: AlertCircle, hint: 'Classifique no botão "Configurar"' },
];

export default function Carteira() {
  const [resumo, setResumo] = useState(null);
  const [aba, setAba] = useState('EC_HUNTER');
  const [grupos, setGrupos] = useState([]);
  const [loading, setLoading] = useState(false);
  const [filtros, setFiltros] = useState({
    tarefa_atrasada: false,
    sem_tarefa_futura: false,
    busca: '',
  });

  const [uploading, setUploading] = useState(null); // null | "CARTEIRA" | "TAREFAS"
  const [msg, setMsg] = useState(null);
  const [modalConfig, setModalConfig] = useState(false);
  const [drawer, setDrawer] = useState(null);
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

  const carregarGrupos = useCallback(async () => {
    setLoading(true);
    try {
      const params = new URLSearchParams({ funcao: aba });
      if (filtros.tarefa_atrasada)   params.append('tarefa_atrasada', 'true');
      if (filtros.sem_tarefa_futura) params.append('sem_tarefa_futura', 'true');
      if (filtros.busca)             params.append('busca', filtros.busca);
      const { data } = await api.get(`/carteira/grupos?${params}`);
      setGrupos(data.grupos || []);
    } catch {
      setGrupos([]);
    } finally {
      setLoading(false);
    }
  }, [aba, filtros]);

  useEffect(() => { carregarResumo(); }, [carregarResumo]);
  useEffect(() => { carregarGrupos();  }, [carregarGrupos]);

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
      carregarResumo();
      carregarGrupos();
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

  // ── KPIs da aba atual ────────────────────────────────────────

  const kpis = useMemo(() => {
    if (!resumo) return null;
    if (aba === 'EC_HUNTER') return resumo.hunter;
    if (aba === 'EC_FARMER') return resumo.farmer;
    return resumo.outros;
  }, [resumo, aba]);

  const abaInfo = ABAS.find((a) => a.v === aba);

  function reload() {
    carregarResumo();
    carregarGrupos();
  }

  return (
    <>
      <PageHeader
        title="Carteira"
        subtitle="Gestão de prospecção (Hunter) e relacionamento com parceiros (Farmer)."
        actions={
          <>
            <Button
              variant="ghost"
              size="md"
              icon={RefreshCw}
              onClick={reload}
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
          const counter = resumo?.[v.toLowerCase().replace('ec_', '')]?.total_grupos;
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

      {/* KPIs da aba */}
      {kpis && (
        <div className="grid grid-cols-2 lg:grid-cols-5 gap-4 mb-4">
          <KpiCard
            label="Total de grupos"
            value={kpis.total_grupos}
            icon={Users}
            tone="blue"
          />
          <KpiCard
            label="Meta atingida"
            value={kpis.meta_atingida}
            hint={`${kpis.compliance_pct}% compliance`}
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
            label="Sem tarefa futura"
            value={kpis.sem_tarefa_futura}
            icon={Calendar}
            tone="amber"
          />
          <KpiCard
            label="Leads do mês"
            value={kpis.leads_no_mes}
            icon={Wifi}
            tone="blue"
          />
        </div>
      )}

      {/* Filtros */}
      <Card padding="sm" className="mb-4">
        <div className="flex flex-wrap items-center gap-3">
          <div className="relative flex-1 min-w-[220px]">
            <Search
              size={16}
              className="absolute left-3 top-1/2 -translate-y-1/2 text-hipo-muted"
            />
            <input
              value={filtros.busca}
              onChange={(e) => setFiltros({ ...filtros, busca: e.target.value })}
              placeholder="Buscar por grupo, contabilidade ou colaborador..."
              className="w-full h-10 bg-hipo-card border border-hipo-border rounded-lg pl-10 pr-3 text-sm text-hipo-ink placeholder:text-hipo-muted outline-none focus:border-hipo-blue focus:ring-2 focus:ring-blue-100"
            />
          </div>
          <label className="flex items-center gap-2 text-sm text-hipo-slate cursor-pointer hover:text-hipo-ink">
            <input
              type="checkbox"
              checked={filtros.tarefa_atrasada}
              onChange={(e) =>
                setFiltros({ ...filtros, tarefa_atrasada: e.target.checked })
              }
              className="w-4 h-4 accent-hipo-blue cursor-pointer"
            />
            Tarefa atrasada
          </label>
          <label className="flex items-center gap-2 text-sm text-hipo-slate cursor-pointer hover:text-hipo-ink">
            <input
              type="checkbox"
              checked={filtros.sem_tarefa_futura}
              onChange={(e) =>
                setFiltros({ ...filtros, sem_tarefa_futura: e.target.checked })
              }
              className="w-4 h-4 accent-hipo-blue cursor-pointer"
            />
            Sem tarefa futura
          </label>
          <span className="text-xs text-hipo-muted ml-auto">
            Score (em breve){' '}
            <Badge tone="neutral" className="ml-1">
              V2
            </Badge>
          </span>
        </div>
      </Card>

      {/* Tabela de grupos */}
      <Card padding="none">
        <div className="px-5 py-3 border-b border-hipo-border flex items-center justify-between flex-wrap gap-2">
          <h3 className="text-sm font-semibold text-hipo-ink">
            {abaInfo.label} — {grupos.length} grupo(s)
          </h3>
          <span
            className={`text-xs ${
              aba === 'OUTROS' ? 'text-hipo-warning' : 'text-hipo-slate'
            }`}
          >
            {abaInfo.hint}
          </span>
        </div>

        {loading ? (
          <div className="p-8 text-center text-sm text-hipo-slate">
            Carregando...
          </div>
        ) : grupos.length === 0 ? (
          <Empty
            title="Nenhum grupo nessa aba"
            description="Faça o upload da carteira e das tarefas, ou ajuste os filtros."
            icon={Users}
          />
        ) : (
          <Table>
            <thead>
              <tr>
                <Th className="w-6"></Th>
                <Th>Grupo</Th>
                <Th align="center">CNPJs</Th>
                <Th>Colaborador</Th>
                <Th>Execução</Th>
                <Th align="center">Atrasadas</Th>
                <Th align="center">Futuras</Th>
                {aba === 'EC_FARMER' && <Th align="center">Leads/mês</Th>}
              </tr>
            </thead>
            <tbody>
              {grupos.map((g) => (
                <Tr
                  key={g.id_grupo}
                  onClick={() =>
                    setDrawer({
                      id_grupo: g.id_grupo,
                      nome_grupo: g.nome_grupo,
                    })
                  }
                >
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
                  <Td className="text-hipo-slate">
                    {g.colaborador_nome || '—'}
                  </Td>
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
                  {aba === 'EC_FARMER' && (
                    <Td
                      align="center"
                      className="text-hipo-blue font-semibold"
                    >
                      {g.leads_no_mes || 0}
                    </Td>
                  )}
                </Tr>
              ))}
            </tbody>
          </Table>
        )}
      </Card>

      {/* Legenda */}
      <div className="mt-4 flex items-center gap-5 text-xs text-hipo-slate flex-wrap">
        <span className="flex items-center gap-1.5">
          <span className="w-2.5 h-2.5 rounded-full bg-hipo-success" /> Meta
          atingida
        </span>
        <span className="flex items-center gap-1.5">
          <span className="w-2.5 h-2.5 rounded-full bg-hipo-danger" /> Perdeu
        </span>
        <span className="flex items-center gap-1.5">
          <span className="w-2.5 h-2.5 rounded-full bg-hipo-warning" />{' '}
          Período atual
        </span>
        <span className="flex items-center gap-1.5">
          <span className="w-2.5 h-2.5 rounded-full bg-hipo-border" /> Futuro
        </span>
      </div>

      {/* Datas dos últimos uploads */}
      {resumo && (resumo.ultima_carteira || resumo.ultima_tarefas) && (
        <div className="mt-3 text-xs text-hipo-muted flex items-center gap-4 flex-wrap">
          {resumo.ultima_carteira && (
            <span>
              Carteira:{' '}
              {new Date(resumo.ultima_carteira).toLocaleString('pt-BR')}
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
        onSalvo={reload}
      />

      <CarteiraGrupoDrawer
        idGrupo={drawer?.id_grupo}
        nomeGrupo={drawer?.nome_grupo}
        onFechar={() => setDrawer(null)}
      />
    </>
  );
}
