import { useState, useEffect, useCallback } from "react";
import { Upload, RefreshCw, AlertCircle, CheckCircle, XCircle, HelpCircle } from "lucide-react";
import axios from "axios";

const API = "/api";

const STATUS_CFG = {
  CONFORME:   { label: "Conforme",   bg: "bg-emerald-500/10", text: "text-emerald-400", border: "border-emerald-500/30", Icon: CheckCircle },
  DIVERGENTE: { label: "Divergente", bg: "bg-yellow-500/10",  text: "text-yellow-400",  border: "border-yellow-500/30", Icon: AlertCircle },
  AUSENTE:    { label: "Ausente",    bg: "bg-red-500/10",     text: "text-red-400",     border: "border-red-500/30",    Icon: XCircle    },
  INESPERADO: { label: "Inesperado", bg: "bg-slate-500/10",   text: "text-slate-400",   border: "border-slate-500/30",  Icon: HelpCircle },
};

function StatusBadge({ status }) {
  const cfg = STATUS_CFG[status] || STATUS_CFG.INESPERADO;
  const { Icon } = cfg;
  return (
    <span className={`inline-flex items-center gap-1 px-2 py-0.5 rounded text-xs font-bold ${cfg.bg} ${cfg.text}`}>
      <Icon size={11} />
      {cfg.label}
    </span>
  );
}

function KpiCard({ label, value, sub, color = "text-cyan-400" }) {
  return (
    <div className="bg-slate-900 border border-slate-800 rounded-xl p-4">
      <p className="text-xs text-slate-500 tracking-wider mb-2">{label}</p>
      <p className={`text-2xl font-bold ${color}`}>{value ?? "—"}</p>
      {sub && <p className="text-xs text-slate-500 mt-1">{sub}</p>}
    </div>
  );
}

export default function POsDashboard() {
  const [reconciliacao, setReconciliacao] = useState([]);
  const [ausentes, setAusentes] = useState([]);
  const [divergentes, setDivergentes] = useState([]);
  const [historico, setHistorico] = useState([]);
  const [financeiro, setFinanceiro] = useState([]);
  const [uploading, setUploading] = useState(false);
  const [msg, setMsg] = useState(null);
  const [tab, setTab] = useState("resumo");

  const carregar = useCallback(async () => {
    try {
      const [r, a, d, h, f] = await Promise.all([
        axios.get(`${API}/po/reconciliacao/ultima`).catch(() => ({ data: [] })),
        axios.get(`${API}/po/reconciliacao/ausentes`).catch(() => ({ data: [] })),
        axios.get(`${API}/po/reconciliacao/divergentes`).catch(() => ({ data: [] })),
        axios.get(`${API}/po/historico`).catch(() => ({ data: [] })),
        axios.get(`${API}/po/resumo/financeiro`).catch(() => ({ data: [] })),
      ]);
      setReconciliacao(r.data);
      setAusentes(a.data);
      setDivergentes(d.data);
      setHistorico(h.data);
      setFinanceiro(f.data);
    } catch (e) {
      console.error(e);
    }
  }, []);

  useEffect(() => { carregar(); }, [carregar]);

  async function uploadPO(e) {
    const file = e.target.files[0];
    if (!file) return;
    setUploading(true);
    setMsg(null);
    const form = new FormData();
    form.append("arquivo", file);
    try {
      const { data } = await axios.post(`${API}/po/upload`, form, {
        headers: { "Content-Type": "multipart/form-data" },
      });
      setMsg({
        tipo: "ok",
        texto: `✅ PO processada — ${data.tipo}${data.tem_enabler ? " (Enabler)" : ""} — ${data.total_linhas} linhas. Semana: ${data.semana_ref || "não identificada"}`,
      });
      carregar();
    } catch (err) {
      setMsg({ tipo: "erro", texto: `Erro: ${err.response?.data?.detail || err.message}` });
    } finally {
      setUploading(false);
      e.target.value = "";
    }
  }

  // Calcula KPIs do resumo
  const totalConforme  = reconciliacao.filter(r => r.status_reconciliacao === "CONFORME").reduce((s, r) => s + Number(r.valor_total), 0);
  const totalAusente   = reconciliacao.filter(r => r.status_reconciliacao === "AUSENTE").reduce((s, r) => s + Number(r.valor_total), 0);
  const qtdAusentes    = ausentes.length;
  const qtdDivergentes = divergentes.length;

  return (
    <div className="p-6 max-w-6xl mx-auto">
      {/* Header */}
      <div className="flex items-center justify-between mb-6">
        <div>
          <h1 className="text-xl font-bold text-slate-100 tracking-wide">Módulo POs</h1>
          <p className="text-xs text-slate-500 mt-0.5">Reconciliação semanal de comissões, incentivos e repasses</p>
        </div>
        <div className="flex items-center gap-3">
          <button onClick={carregar} className="p-2 rounded-lg text-slate-400 hover:text-slate-200 hover:bg-slate-800 transition-colors">
            <RefreshCw size={16} />
          </button>
          <label className={`flex items-center gap-2 px-4 py-2 rounded-lg text-sm font-bold cursor-pointer transition-all ${
            uploading ? "bg-slate-700 text-slate-400" : "bg-cyan-600 hover:bg-cyan-500 text-white"
          }`}>
            <Upload size={15} />
            {uploading ? "Processando..." : "Upload PO"}
            <input type="file" accept=".xlsx" className="hidden" onChange={uploadPO} disabled={uploading} />
          </label>
        </div>
      </div>

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
        <KpiCard label="Recebido (semana)" value={`R$ ${(totalConforme/1000).toFixed(1)}k`} color="text-emerald-400" />
        <KpiCard label="Em Risco" value={`R$ ${(totalAusente/1000).toFixed(1)}k`} sub={`${qtdAusentes} cliente(s) ausente(s)`} color="text-red-400" />
        <KpiCard label="Divergentes" value={qtdDivergentes} sub="aguardando resolução" color="text-yellow-400" />
        <KpiCard label="Uploads este mês" value={historico.filter(h => {
          const d = new Date(h.data_upload);
          const now = new Date();
          return d.getMonth() === now.getMonth() && d.getFullYear() === now.getFullYear();
        }).length} color="text-cyan-400" />
      </div>

      {/* Tabs */}
      <div className="flex gap-1 mb-6 border-b border-slate-800">
        {[["resumo","Resumo"], ["ausentes","Ausentes"], ["divergentes","Divergentes"], ["historico","Histórico"]].map(([k, l]) => (
          <button key={k} onClick={() => setTab(k)}
            data-testid={`tab-${k}`}
            className={`px-4 py-2.5 text-xs font-bold tracking-wider transition-all ${
              tab === k ? "text-cyan-400 border-b-2 border-cyan-400" : "text-slate-500 hover:text-slate-300"
            }`}>
            {l.toUpperCase()}
            {k === "ausentes" && qtdAusentes > 0 && (
              <span className="ml-1.5 bg-red-500 text-white text-xs px-1.5 py-0.5 rounded-full">{qtdAusentes}</span>
            )}
            {k === "divergentes" && qtdDivergentes > 0 && (
              <span className="ml-1.5 bg-yellow-500 text-slate-900 text-xs px-1.5 py-0.5 rounded-full">{qtdDivergentes}</span>
            )}
          </button>
        ))}
      </div>

      {/* TAB: RESUMO */}
      {tab === "resumo" && (
        <div className="space-y-4">
          {reconciliacao.length === 0 ? (
            <div className="text-center py-20">
              <Upload size={48} className="mx-auto text-slate-700 mb-4" />
              <p className="text-slate-500 text-sm">Nenhuma PO processada.</p>
              <p className="text-slate-600 text-xs mt-1">Faça o upload dos arquivos de PO da semana.</p>
            </div>
          ) : (
            <div className="bg-slate-900 border border-slate-800 rounded-xl overflow-hidden">
              <table className="w-full text-xs">
                <thead>
                  <tr className="text-slate-500 border-b border-slate-800 text-left">
                    <th className="px-4 py-3">Tipo</th>
                    <th className="px-4 py-3">Status</th>
                    <th className="px-4 py-3 text-right">Qtd</th>
                    <th className="px-4 py-3 text-right">Valor</th>
                    <th className="px-4 py-3 text-right">Divergência</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-800">
                  {reconciliacao.map((r, i) => (
                    <tr key={i} className="hover:bg-slate-800/40">
                      <td className="px-4 py-3 font-bold text-slate-200">
                        {r.tipo}{r.tem_enabler ? " (Enabler)" : ""}
                      </td>
                      <td className="px-4 py-3"><StatusBadge status={r.status_reconciliacao} /></td>
                      <td className="px-4 py-3 text-right text-slate-300 font-mono">{r.quantidade}</td>
                      <td className="px-4 py-3 text-right text-slate-300 font-mono">
                        R$ {Number(r.valor_total).toLocaleString("pt-BR", {minimumFractionDigits:2})}
                      </td>
                      <td className={`px-4 py-3 text-right font-mono ${
                        r.divergencia_total > 0 ? "text-yellow-400" :
                        r.divergencia_total < 0 ? "text-red-400" : "text-slate-600"
                      }`}>
                        {r.divergencia_total != 0
                          ? `R$ ${Number(r.divergencia_total).toLocaleString("pt-BR", {minimumFractionDigits:2})}`
                          : "—"}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      )}

      {/* TAB: AUSENTES */}
      {tab === "ausentes" && (
        <div className="bg-slate-900 border border-red-500/20 rounded-xl overflow-hidden">
          {ausentes.length === 0 ? (
            <div className="p-8 text-center text-slate-500 text-sm">Nenhum cliente ausente. ✅</div>
          ) : (
            <table className="w-full text-xs">
              <thead>
                <tr className="text-slate-500 border-b border-slate-800 text-left">
                  <th className="px-4 py-3">Cliente</th>
                  <th className="px-4 py-3">Tipo</th>
                  <th className="px-4 py-3 text-right">Valor Esperado</th>
                  <th className="px-4 py-3">Situação</th>
                  <th className="px-4 py-3">Saúde</th>
                  <th className="px-4 py-3">Contador</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-800">
                {ausentes.map((a, i) => (
                  <tr key={i} className="hover:bg-slate-800/40">
                    <td className="px-4 py-3">
                      <p className="font-bold text-slate-200">{a.razao_social || a.referencia_aplicativo}</p>
                      <p className="text-slate-500 text-xs">{a.referencia_aplicativo}</p>
                    </td>
                    <td className="px-4 py-3 text-slate-400">{a.tipo}</td>
                    <td className="px-4 py-3 text-right text-red-400 font-mono font-bold">
                      R$ {Number(a.valor_esperado).toLocaleString("pt-BR", {minimumFractionDigits:2})}
                    </td>
                    <td className="px-4 py-3">
                      <span className={`text-xs px-2 py-0.5 rounded ${
                        a.situacao === "ARCHIVED" ? "bg-red-500/20 text-red-400" : "bg-slate-700 text-slate-300"
                      }`}>{a.situacao || "—"}</span>
                    </td>
                    <td className="px-4 py-3 text-slate-400">{a.saude_paciente || "—"}</td>
                    <td className="px-4 py-3 text-slate-400">{a.contador_nome || "Sem contador"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>
      )}

      {/* TAB: DIVERGENTES */}
      {tab === "divergentes" && (
        <div className="bg-slate-900 border border-yellow-500/20 rounded-xl overflow-hidden">
          {divergentes.length === 0 ? (
            <div className="p-8 text-center text-slate-500 text-sm">Nenhuma divergência encontrada. ✅</div>
          ) : (
            <table className="w-full text-xs">
              <thead>
                <tr className="text-slate-500 border-b border-slate-800 text-left">
                  <th className="px-4 py-3">Cliente</th>
                  <th className="px-4 py-3 text-right">Esperado</th>
                  <th className="px-4 py-3 text-right">Recebido</th>
                  <th className="px-4 py-3 text-right">Diferença</th>
                  <th className="px-4 py-3">Semana</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-800">
                {divergentes.map((d, i) => (
                  <tr key={i} className="hover:bg-slate-800/40">
                    <td className="px-4 py-3">
                      <p className="font-bold text-slate-200">{d.razao_social || d.referencia_aplicativo}</p>
                      <p className="text-slate-500">{d.tipo}</p>
                    </td>
                    <td className="px-4 py-3 text-right text-slate-300 font-mono">
                      R$ {Number(d.valor_esperado).toLocaleString("pt-BR", {minimumFractionDigits:2})}
                    </td>
                    <td className="px-4 py-3 text-right text-slate-300 font-mono">
                      R$ {Number(d.valor_recebido).toLocaleString("pt-BR", {minimumFractionDigits:2})}
                    </td>
                    <td className={`px-4 py-3 text-right font-mono font-bold ${
                      d.divergencia_valor > 0 ? "text-yellow-400" : "text-red-400"
                    }`}>
                      {d.divergencia_valor > 0 ? "+" : ""}
                      R$ {Number(d.divergencia_valor).toLocaleString("pt-BR", {minimumFractionDigits:2})}
                    </td>
                    <td className="px-4 py-3 text-slate-400">{d.semana_ref}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>
      )}

      {/* TAB: HISTÓRICO */}
      {tab === "historico" && (
        <div className="space-y-2">
          {historico.length === 0 ? (
            <div className="p-8 text-center text-slate-500 text-sm">Sem histórico de uploads.</div>
          ) : (
            historico.map((h, i) => (
              <div key={i} className="bg-slate-900 border border-slate-800 rounded-xl px-4 py-3 flex items-center justify-between">
                <div>
                  <p className="text-sm font-bold text-slate-200">{h.nome_arquivo}</p>
                  <p className="text-xs text-slate-500">{new Date(h.data_upload).toLocaleString("pt-BR")} — Semana: {h.semana_ref || "—"}</p>
                </div>
                <div className="flex items-center gap-4 text-xs">
                  <span className="text-emerald-400">{h.conformes} ✓</span>
                  {h.ausentes > 0 && <span className="text-red-400">{h.ausentes} ausentes</span>}
                  {h.divergentes > 0 && <span className="text-yellow-400">{h.divergentes} div.</span>}
                  <span className="text-slate-500">{h.total_linhas} linhas</span>
                </div>
              </div>
            ))
          )}
        </div>
      )}
    </div>
  );
}