// web/src/pages/Carteira.jsx
//
// Gestão da Carteira de Prospecção (Hunter) e Relacionamento (Farmer).
// Carrega-se por upload de duas planilhas (carteira + tarefas), agrupa
// por ID Grupo de Empresas, e mostra timeline de execução por grupo.
import { useState, useEffect, useCallback, useMemo } from "react";
import {
  Upload, RefreshCw, Settings, Users, AlertCircle, Calendar,
  Target, Activity, Search, History, ChevronDown, ChevronRight,
  Wifi, ListChecks,
} from "lucide-react";
import api from "../api";
import CarteiraTimeline from "../components/CarteiraTimeline";
import ConfigColaboradoresModal from "../components/ConfigColaboradoresModal";
import CarteiraGrupoDrawer from "../components/CarteiraGrupoDrawer";


const ABAS = [
  { v: "EC_HUNTER", label: "Hunter", color: "text-cyan-400",    Icon: Target },
  { v: "EC_FARMER", label: "Farmer", color: "text-emerald-400", Icon: Activity },
  { v: "OUTROS",    label: "Outros", color: "text-amber-400",   Icon: AlertCircle },
];


function KpiCard({ label, value, sub, color = "text-cyan-400", Icon }) {
  return (
    <div className="bg-slate-900 border border-slate-800 rounded-xl p-4">
      <div className="flex items-center justify-between mb-2">
        <p className="text-[10px] text-slate-500 tracking-widest">{label}</p>
        {Icon && <Icon size={14} className="text-slate-600" />}
      </div>
      <p className={`text-2xl font-bold ${color}`}>{value ?? "—"}</p>
      {sub && <p className="text-xs text-slate-500 mt-1">{sub}</p>}
    </div>
  );
}


export default function Carteira() {
  const [resumo, setResumo] = useState(null);
  const [aba, setAba] = useState("EC_HUNTER");
  const [grupos, setGrupos] = useState([]);
  const [loading, setLoading] = useState(false);
  const [filtros, setFiltros] = useState({
    tarefa_atrasada: false,
    sem_tarefa_futura: false,
    busca: "",
  });

  const [uploading, setUploading] = useState(null); // null | "CARTEIRA" | "TAREFAS"
  const [msg, setMsg] = useState(null);
  const [modalConfig, setModalConfig] = useState(false);
  const [drawer, setDrawer] = useState(null); // { id_grupo, nome_grupo } | null
  const [historicoAberto, setHistoricoAberto] = useState(false);
  const [historico, setHistorico] = useState([]);

  // ── Carregamento ────────────────────────────────────────────

  const carregarResumo = useCallback(async () => {
    try {
      const { data } = await api.get("/carteira/resumo");
      setResumo(data);
    } catch (e) {
      // silencioso: o usuário pode não ter feito uploads ainda
      setResumo(null);
    }
  }, []);

  const carregarGrupos = useCallback(async () => {
    setLoading(true);
    try {
      const params = new URLSearchParams({ funcao: aba });
      if (filtros.tarefa_atrasada)   params.append("tarefa_atrasada", "true");
      if (filtros.sem_tarefa_futura) params.append("sem_tarefa_futura", "true");
      if (filtros.busca)             params.append("busca", filtros.busca);
      const { data } = await api.get(`/carteira/grupos?${params}`);
      setGrupos(data.grupos || []);
    } catch (e) {
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
    form.append("arquivo", file);
    const endpoint = tipo === "CARTEIRA" ? "/carteira/upload-carteira" : "/carteira/upload-tarefas";
    try {
      const { data } = await api.post(endpoint, form, {
        headers: { "Content-Type": "multipart/form-data" },
      });
      setMsg({ tipo: "ok", texto: `✅ ${data.message}` });
      carregarResumo();
      carregarGrupos();
    } catch (err) {
      const detail = err.response?.data?.detail;
      const texto = typeof detail === "string" ? detail :
                    Array.isArray(detail?.erros) ? detail.erros.join(" • ") :
                    err.message;
      setMsg({ tipo: "erro", texto: `Erro: ${texto}` });
    } finally {
      setUploading(null);
    }
  }

  async function carregarHistorico() {
    if (historicoAberto) {
      setHistoricoAberto(false);
      return;
    }
    try {
      const { data } = await api.get("/carteira/historico");
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
    if (aba === "EC_HUNTER") return resumo.hunter;
    if (aba === "EC_FARMER") return resumo.farmer;
    return resumo.outros;
  }, [resumo, aba]);

  const abaInfo = ABAS.find((a) => a.v === aba);

  // ── Render ──────────────────────────────────────────────────

  return (
    <div className="p-6 max-w-7xl mx-auto">
      {/* Header */}
      <div className="flex items-center justify-between mb-6">
        <div>
          <h1 className="text-xl font-bold text-slate-100 tracking-wide">Carteira</h1>
          <p className="text-xs text-slate-500 mt-0.5">
            Gestão de prospecção (Hunter) e relacionamento com parceiros (Farmer)
          </p>
        </div>
        <div className="flex items-center gap-2">
          <button
            onClick={() => { carregarResumo(); carregarGrupos(); }}
            className="p-2 rounded-lg text-slate-400 hover:text-slate-200 hover:bg-slate-800 transition-colors"
            title="Atualizar"
          >
            <RefreshCw size={16} />
          </button>
          <button
            onClick={carregarHistorico}
            className="p-2 rounded-lg text-slate-400 hover:text-slate-200 hover:bg-slate-800 transition-colors"
            title="Histórico"
          >
            <History size={16} />
          </button>
          <button
            onClick={() => setModalConfig(true)}
            className="flex items-center gap-2 px-3 py-2 rounded-lg text-sm text-slate-300 hover:text-cyan-400 hover:bg-slate-800 transition-colors border border-slate-800"
          >
            <Settings size={14} />
            <span className="hidden md:inline">Configurar</span>
          </button>

          <label className={`flex items-center gap-2 px-3 py-2 rounded-lg text-sm font-bold cursor-pointer transition-all border ${
            uploading === "CARTEIRA" ? "bg-slate-700 text-slate-400 border-slate-700"
            : "bg-slate-900 text-cyan-400 border-cyan-500/40 hover:bg-cyan-500/10"
          }`}>
            <Upload size={14} />
            {uploading === "CARTEIRA" ? "Processando..." : "Carteira"}
            <input
              type="file" accept=".xlsx" className="hidden"
              onChange={(e) => { upload("CARTEIRA", e.target.files[0]); e.target.value = ""; }}
              disabled={uploading !== null}
            />
          </label>

          <label className={`flex items-center gap-2 px-3 py-2 rounded-lg text-sm font-bold cursor-pointer transition-all ${
            uploading === "TAREFAS" ? "bg-slate-700 text-slate-400"
            : "bg-cyan-600 hover:bg-cyan-500 text-white"
          }`}>
            <Upload size={14} />
            {uploading === "TAREFAS" ? "Processando..." : "Tarefas"}
            <input
              type="file" accept=".xlsx" className="hidden"
              onChange={(e) => { upload("TAREFAS", e.target.files[0]); e.target.value = ""; }}
              disabled={uploading !== null}
            />
          </label>
        </div>
      </div>

      {/* Mensagem */}
      {msg && (
        <div className={`mb-4 px-4 py-3 rounded-lg text-sm ${
          msg.tipo === "ok"
            ? "bg-emerald-500/10 text-emerald-400 border border-emerald-500/30"
            : "bg-red-500/10 text-red-400 border border-red-500/30"
        }`}>
          {msg.texto}
        </div>
      )}

      {/* Histórico (expand) */}
      {historicoAberto && (
        <div className="bg-slate-900 border border-slate-800 rounded-xl mb-4 overflow-hidden">
          <div className="px-5 py-2 border-b border-slate-800 flex items-center justify-between">
            <h3 className="text-xs font-bold text-slate-400 tracking-widest">HISTÓRICO DE UPLOADS</h3>
            <button
              onClick={() => setHistoricoAberto(false)}
              className="text-slate-500 hover:text-slate-300 text-xs"
            >
              Fechar
            </button>
          </div>
          {historico.length === 0 ? (
            <p className="px-5 py-4 text-sm text-slate-500">Nenhum upload registrado.</p>
          ) : (
            <table className="w-full text-xs">
              <thead>
                <tr className="text-slate-500 border-b border-slate-800 text-left">
                  <th className="px-4 py-2">Data</th>
                  <th className="px-4 py-2">Tipo</th>
                  <th className="px-4 py-2">Arquivo</th>
                  <th className="px-4 py-2">Usuário</th>
                  <th className="px-4 py-2 text-right">Linhas</th>
                  <th className="px-4 py-2 text-right">Válidas</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-800">
                {historico.map((h) => (
                  <tr key={h.id} className="hover:bg-slate-800/40">
                    <td className="px-4 py-2 text-slate-300">
                      {new Date(h.data_upload).toLocaleString("pt-BR")}
                    </td>
                    <td className="px-4 py-2">
                      <span className={`text-[9px] tracking-widest px-2 py-0.5 rounded border ${
                        h.tipo === "CARTEIRA"
                          ? "border-cyan-500/40 text-cyan-300 bg-cyan-500/10"
                          : "border-emerald-500/40 text-emerald-300 bg-emerald-500/10"
                      }`}>
                        {h.tipo}
                      </span>
                    </td>
                    <td className="px-4 py-2 text-slate-400 truncate max-w-xs">{h.nome_arquivo}</td>
                    <td className="px-4 py-2 text-slate-400">{h.usuario_nome || "—"}</td>
                    <td className="px-4 py-2 text-right text-slate-300 font-mono">{h.total_linhas}</td>
                    <td className="px-4 py-2 text-right text-emerald-400 font-mono">{h.total_validos}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>
      )}

      {/* Abas */}
      <div className="flex items-center gap-1 mb-4 border-b border-slate-800">
        {ABAS.map(({ v, label, color, Icon }) => {
          const ativo = aba === v;
          const counter = resumo?.[v.toLowerCase().replace("ec_", "")]?.total_grupos;
          return (
            <button
              key={v}
              onClick={() => setAba(v)}
              className={`flex items-center gap-2 px-4 py-2.5 text-sm border-b-2 -mb-px transition-colors ${
                ativo
                  ? `${color} border-current font-bold`
                  : "border-transparent text-slate-500 hover:text-slate-300"
              }`}
            >
              <Icon size={14} />
              <span>{label}</span>
              {counter != null && (
                <span className={`text-[10px] px-1.5 py-0.5 rounded-full ${
                  ativo ? "bg-current/10" : "bg-slate-800 text-slate-400"
                }`}>
                  {counter}
                </span>
              )}
            </button>
          );
        })}
      </div>

      {/* KPIs da aba */}
      {kpis && (
        <div className="grid grid-cols-2 lg:grid-cols-5 gap-3 mb-4">
          <KpiCard
            label="Total de grupos" value={kpis.total_grupos}
            color={abaInfo.color} Icon={Users}
          />
          <KpiCard
            label="Meta atingida" value={kpis.meta_atingida}
            sub={`${kpis.compliance_pct}% compliance`}
            color="text-emerald-400" Icon={Target}
          />
          <KpiCard
            label="Tarefa atrasada" value={kpis.com_tarefa_atrasada}
            color="text-red-400" Icon={AlertCircle}
          />
          <KpiCard
            label="Sem tarefa futura" value={kpis.sem_tarefa_futura}
            color="text-amber-400" Icon={Calendar}
          />
          <KpiCard
            label="Leads do mês" value={kpis.leads_no_mes}
            color="text-cyan-300" Icon={Wifi}
          />
        </div>
      )}

      {/* Filtros */}
      <div className="bg-slate-900 border border-slate-800 rounded-xl p-3 mb-4 flex flex-wrap items-center gap-3">
        <div className="relative flex-1 min-w-[200px]">
          <Search size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-slate-500" />
          <input
            value={filtros.busca}
            onChange={(e) => setFiltros({ ...filtros, busca: e.target.value })}
            placeholder="Buscar por grupo, contabilidade ou colaborador..."
            className="w-full bg-slate-950 border border-slate-800 rounded-lg pl-9 pr-3 py-2 text-sm text-slate-200 focus:outline-none focus:border-cyan-500"
          />
        </div>
        <label className="flex items-center gap-2 text-xs text-slate-400 cursor-pointer hover:text-slate-200">
          <input
            type="checkbox"
            checked={filtros.tarefa_atrasada}
            onChange={(e) => setFiltros({ ...filtros, tarefa_atrasada: e.target.checked })}
            className="accent-cyan-500"
          />
          Tarefa atrasada
        </label>
        <label className="flex items-center gap-2 text-xs text-slate-400 cursor-pointer hover:text-slate-200">
          <input
            type="checkbox"
            checked={filtros.sem_tarefa_futura}
            onChange={(e) => setFiltros({ ...filtros, sem_tarefa_futura: e.target.checked })}
            className="accent-cyan-500"
          />
          Sem tarefa futura
        </label>
        <span className="text-xs text-slate-600 ml-auto">
          Score (em breve) <span className="bg-slate-800 text-slate-500 px-1.5 py-0.5 rounded text-[9px] tracking-widest">V2</span>
        </span>
      </div>

      {/* Tabela */}
      <div className="bg-slate-900 border border-slate-800 rounded-xl overflow-hidden">
        <div className="px-5 py-3 border-b border-slate-800 flex items-center justify-between">
          <h3 className="text-xs font-bold text-slate-400 tracking-widest">
            {abaInfo.label.toUpperCase()} — {grupos.length} GRUPO(S)
          </h3>
          {aba === "EC_FARMER" && (
            <span className="text-[10px] text-slate-500">Meta: ≥1 reunião por semana</span>
          )}
          {aba === "EC_HUNTER" && (
            <span className="text-[10px] text-slate-500">Meta: ≥1 tarefa por mês</span>
          )}
          {aba === "OUTROS" && (
            <span className="text-[10px] text-amber-400">
              Lista para correção — classifique no botão "Configurar"
            </span>
          )}
        </div>

        {loading ? (
          <div className="p-8 text-center text-sm text-slate-500">Carregando...</div>
        ) : grupos.length === 0 ? (
          <div className="p-8 text-center text-sm text-slate-500">
            Nenhum grupo nessa aba. Faça o upload da carteira e das tarefas, ou ajuste os filtros.
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-xs">
              <thead>
                <tr className="text-[10px] text-slate-500 border-b border-slate-800 text-left tracking-widest">
                  <th className="px-4 py-3 w-6"></th>
                  <th className="px-4 py-3">GRUPO</th>
                  <th className="px-4 py-3 text-center">CNPJS</th>
                  <th className="px-4 py-3">COLABORADOR</th>
                  <th className="px-4 py-3">EXECUÇÃO</th>
                  <th className="px-4 py-3 text-center">ATRASADAS</th>
                  <th className="px-4 py-3 text-center">FUTURAS</th>
                  {aba === "EC_FARMER" && (
                    <th className="px-4 py-3 text-center">LEADS/MÊS</th>
                  )}
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-800">
                {grupos.map((g) => (
                  <tr
                    key={g.id_grupo}
                    onClick={() => setDrawer({ id_grupo: g.id_grupo, nome_grupo: g.nome_grupo })}
                    className="hover:bg-slate-800/40 cursor-pointer"
                  >
                    <td className="px-4 py-3 text-slate-600">
                      <ChevronRight size={14} />
                    </td>
                    <td className="px-4 py-3">
                      <div className="flex flex-col">
                        <span className="text-slate-200 font-bold">
                          {g.nome_grupo || "—"}
                          {g.colaboradores_multiplos && (
                            <span
                              className="ml-2 text-[9px] text-amber-400 tracking-wider"
                              title="Múltiplos colaboradores neste grupo"
                            >⚠ MÚLT</span>
                          )}
                        </span>
                        <span className="text-[10px] text-slate-500">
                          {g.contabilidade_principal} · {g.cidade_uf}
                          {g.parceria && (
                            <span className={`ml-2 ${
                              g.parceria === "Parceiro" ? "text-emerald-400" : "text-slate-400"
                            }`}>
                              {g.parceria === "Parceiro" ? "● parceiro" : "○ não parceiro"}
                            </span>
                          )}
                        </span>
                      </div>
                    </td>
                    <td className="px-4 py-3 text-center text-slate-300 font-mono">
                      {g.qtd_cnpj}
                    </td>
                    <td className="px-4 py-3 text-slate-300">
                      {g.colaborador_nome || "—"}
                    </td>
                    <td className="px-4 py-3">
                      <CarteiraTimeline cells={g.timeline} compact />
                    </td>
                    <td className={`px-4 py-3 text-center font-mono ${
                      g.tarefas_atrasadas > 0 ? "text-red-400 font-bold" : "text-slate-500"
                    }`}>
                      {g.tarefas_atrasadas}
                    </td>
                    <td className={`px-4 py-3 text-center font-mono ${
                      g.tarefas_futuras > 0 ? "text-cyan-300" : "text-slate-500"
                    }`}>
                      {g.tarefas_futuras}
                    </td>
                    {aba === "EC_FARMER" && (
                      <td className="px-4 py-3 text-center font-mono text-cyan-300 font-bold">
                        {g.leads_no_mes || 0}
                      </td>
                    )}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {/* Legenda */}
      <div className="mt-4 flex items-center gap-5 text-[10px] text-slate-500 tracking-widest">
        <span className="flex items-center gap-1.5">
          <span className="w-2.5 h-2.5 rounded-full bg-emerald-400" /> META ATINGIDA
        </span>
        <span className="flex items-center gap-1.5">
          <span className="w-2.5 h-2.5 rounded-full bg-red-500" /> PERDEU
        </span>
        <span className="flex items-center gap-1.5">
          <span className="w-2.5 h-2.5 rounded-full bg-amber-400" /> PERÍODO ATUAL
        </span>
        <span className="flex items-center gap-1.5">
          <span className="w-2.5 h-2.5 rounded-full bg-slate-700" /> FUTURO
        </span>
      </div>

      {/* Datas dos últimos uploads */}
      {resumo && (resumo.ultima_carteira || resumo.ultima_tarefas) && (
        <div className="mt-3 text-[10px] text-slate-600 flex items-center gap-4">
          {resumo.ultima_carteira && (
            <span>Carteira: {new Date(resumo.ultima_carteira).toLocaleString("pt-BR")}</span>
          )}
          {resumo.ultima_tarefas && (
            <span>Tarefas: {new Date(resumo.ultima_tarefas).toLocaleString("pt-BR")}</span>
          )}
        </div>
      )}

      {/* Modal de configuração */}
      <ConfigColaboradoresModal
        aberto={modalConfig}
        onFechar={() => setModalConfig(false)}
        onSalvo={() => { carregarResumo(); carregarGrupos(); }}
      />

      {/* Drawer de detalhe */}
      <CarteiraGrupoDrawer
        idGrupo={drawer?.id_grupo}
        nomeGrupo={drawer?.nome_grupo}
        onFechar={() => setDrawer(null)}
      />
    </div>
  );
}
