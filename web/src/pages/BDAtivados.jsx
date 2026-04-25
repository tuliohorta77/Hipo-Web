import { useState, useEffect, useCallback } from "react";
import { Upload, RefreshCw, Database, Users, TrendingUp, Calendar } from "lucide-react";
import axios from "axios";

const API = "/api";

function KpiCard({ label, value, sub, color = "text-cyan-400", Icon }) {
  return (
    <div className="bg-slate-900 border border-slate-800 rounded-xl p-4">
      <div className="flex items-center justify-between mb-2">
        <p className="text-xs text-slate-500 tracking-wider">{label}</p>
        {Icon && <Icon size={14} className="text-slate-600" />}
      </div>
      <p className={`text-2xl font-bold ${color}`}>{value ?? "—"}</p>
      {sub && <p className="text-xs text-slate-500 mt-1">{sub}</p>}
    </div>
  );
}

export default function BDAtivadosDashboard() {
  const [resumo, setResumo] = useState(null);
  const [historico, setHistorico] = useState([]);
  const [uploading, setUploading] = useState(false);
  const [msg, setMsg] = useState(null);

  const carregar = useCallback(async () => {
    try {
      const [r, h] = await Promise.all([
        axios.get(`${API}/bd-ativados/resumo`).catch(() => ({ data: null })),
        axios.get(`${API}/bd-ativados/historico`).catch(() => ({ data: [] })),
      ]);
      setResumo(r.data);
      setHistorico(h.data);
    } catch (e) {
      console.error(e);
    }
  }, []);

  useEffect(() => { carregar(); }, [carregar]);

  async function uploadBD(e) {
    const file = e.target.files[0];
    if (!file) return;
    setUploading(true);
    setMsg(null);
    const form = new FormData();
    form.append("arquivo", file);
    try {
      const { data } = await axios.post(`${API}/bd-ativados/upload`, form, {
        headers: { "Content-Type": "multipart/form-data" },
      });
      setMsg({
        tipo: "ok",
        texto: `✅ ${data.total_registros} registros processados — ${data.estatisticas.ativos} ativos, ${data.estatisticas.arquivados} arquivados. MRR: R$ ${data.estatisticas.mrr_total.toLocaleString("pt-BR", {minimumFractionDigits:2})}`,
      });
      carregar();
    } catch (err) {
      setMsg({ tipo: "erro", texto: `Erro: ${err.response?.data?.detail || err.message}` });
    } finally {
      setUploading(false);
      e.target.value = "";
    }
  }

  return (
    <div className="p-6 max-w-6xl mx-auto">
      {/* Header */}
      <div className="flex items-center justify-between mb-6">
        <div>
          <h1 className="text-xl font-bold text-slate-100 tracking-wide">BD Ativados</h1>
          <p className="text-xs text-slate-500 mt-0.5">
            Snapshot da base de clientes ativos — upload diário pelo ADM
          </p>
        </div>
        <div className="flex items-center gap-3">
          <button onClick={carregar} className="p-2 rounded-lg text-slate-400 hover:text-slate-200 hover:bg-slate-800 transition-colors">
            <RefreshCw size={16} />
          </button>
          <label className={`flex items-center gap-2 px-4 py-2 rounded-lg text-sm font-bold cursor-pointer transition-all ${
            uploading ? "bg-slate-700 text-slate-400" : "bg-cyan-600 hover:bg-cyan-500 text-white"
          }`}>
            <Upload size={15} />
            {uploading ? "Processando..." : "Upload BD Ativados"}
            <input type="file" accept=".xlsx" className="hidden" onChange={uploadBD} disabled={uploading} />
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

      {/* KPIs */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4 mb-6">
        <KpiCard
          label="Total de Clientes"
          value={resumo?.total ?? 0}
          color="text-cyan-400"
          Icon={Database}
        />
        <KpiCard
          label="Ativos"
          value={resumo?.ativos ?? 0}
          sub={`${resumo?.arquivados ?? 0} arquivados`}
          color="text-emerald-400"
          Icon={Users}
        />
        <KpiCard
          label="MRR Mensal"
          value={resumo?.mrr_total
            ? `R$ ${(resumo.mrr_total / 1000).toFixed(1)}k`
            : "R$ 0"}
          color="text-yellow-400"
          Icon={TrendingUp}
        />
        <KpiCard
          label="Contadores"
          value={resumo?.contadores_distintos ?? 0}
          sub={`${resumo?.com_integracao ?? 0} com integração`}
          color="text-orange-400"
          Icon={Users}
        />
      </div>

      {/* Último upload */}
      {resumo?.ultimo_upload && (
        <div className="bg-slate-900 border border-slate-800 rounded-xl p-4 mb-6">
          <div className="flex items-center gap-2 text-xs text-slate-500 mb-1">
            <Calendar size={12} />
            <span>Última atualização</span>
          </div>
          <p className="text-sm text-slate-300">
            {new Date(resumo.ultimo_upload.data_upload).toLocaleString("pt-BR")} —{" "}
            <span className="text-slate-500">{resumo.ultimo_upload.nome_arquivo}</span>
          </p>
        </div>
      )}

      {/* Histórico */}
      <div className="bg-slate-900 border border-slate-800 rounded-xl overflow-hidden">
        <div className="px-5 py-3 border-b border-slate-800">
          <h3 className="text-xs font-bold text-slate-400 tracking-widest">HISTÓRICO DE UPLOADS</h3>
        </div>
        {historico.length === 0 ? (
          <div className="p-8 text-center text-slate-500 text-sm">
            Nenhum upload realizado. Faça o primeiro upload do BD Ativados.
          </div>
        ) : (
          <table className="w-full text-xs">
            <thead>
              <tr className="text-slate-500 border-b border-slate-800 text-left">
                <th className="px-4 py-3">Data</th>
                <th className="px-4 py-3">Arquivo</th>
                <th className="px-4 py-3">Usuário</th>
                <th className="px-4 py-3 text-right">Registros</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-800">
              {historico.map((h, i) => (
                <tr key={i} className="hover:bg-slate-800/40">
                  <td className="px-4 py-3 text-slate-300">
                    {new Date(h.data_upload).toLocaleString("pt-BR")}
                  </td>
                  <td className="px-4 py-3 text-slate-400">{h.nome_arquivo}</td>
                  <td className="px-4 py-3 text-slate-400">{h.usuario_nome || "—"}</td>
                  <td className="px-4 py-3 text-right text-slate-300 font-mono">{h.total_registros}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </div>
  );
}
