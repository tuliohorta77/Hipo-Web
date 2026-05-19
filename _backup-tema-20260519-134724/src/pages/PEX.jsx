import { useState, useEffect, useCallback } from "react";
import { Upload, RefreshCw, AlertTriangle, CheckCircle, TrendingUp, Users, BarChart3 } from "lucide-react";
import api from "../api";


const RISCO = {
  VERDE:    { bg: "bg-emerald-500/10", border: "border-emerald-500/40", text: "text-emerald-400", dot: "bg-emerald-500" },
  AMARELO:  { bg: "bg-yellow-500/10",  border: "border-yellow-500/40",  text: "text-yellow-400",  dot: "bg-yellow-400" },
  LARANJA:  { bg: "bg-orange-500/10",  border: "border-orange-500/40",  text: "text-orange-400",  dot: "bg-orange-400" },
  VERMELHO: { bg: "bg-red-500/10",     border: "border-red-500/40",     text: "text-red-400",     dot: "bg-red-500"    },
};

function ScoreRing({ score, risco }) {
  const r = 36, circ = 2 * Math.PI * r;
  const pct = Math.min(score / 100, 1);
  const colorMap = { VERDE:"#10b981", AMARELO:"#eab308", LARANJA:"#f97316", VERMELHO:"#ef4444" };
  const color = colorMap[risco] || "#64748b";
  return (
    <svg width="90" height="90" viewBox="0 0 90 90">
      <circle cx="45" cy="45" r={r} fill="none" stroke="#1e293b" strokeWidth="7" />
      <circle cx="45" cy="45" r={r} fill="none" stroke={color} strokeWidth="7"
        strokeDasharray={`${pct * circ} ${circ}`} strokeLinecap="round"
        transform="rotate(-90 45 45)" style={{ transition: "stroke-dasharray 1s ease" }} />
      <text x="45" y="50" textAnchor="middle" fill={color} fontSize="18" fontWeight="bold">{score?.toFixed(1)}</text>
    </svg>
  );
}

function Bar({ pct, pts, maxPts, label }) {
  const ok = pct >= 80;
  const color = pct >= 80 ? "bg-emerald-500" : pct >= 50 ? "bg-yellow-500" : "bg-red-500";
  return (
    <div className="mb-3">
      <div className="flex justify-between text-xs text-slate-400 mb-1">
        <span>{label}</span>
        <span className={ok ? "text-emerald-400" : "text-red-400"}>{pts?.toFixed(1)}/{maxPts}pts — {pct?.toFixed(1)}%</span>
      </div>
      <div className="w-full h-2 bg-slate-800 rounded-full overflow-hidden">
        <div className={`h-full ${color} rounded-full transition-all duration-700`} style={{ width: `${Math.min(pct, 100)}%` }} />
      </div>
    </div>
  );
}

export default function PEXDashboard() {
  const [painel, setPainel] = useState(null);
  const [compliance, setCompliance] = useState([]);
  const [historico, setHistorico] = useState([]);
  const [uploading, setUploading] = useState(false);
  const [msg, setMsg] = useState(null);
  const [tab, setTab] = useState("painel");

  const carregar = useCallback(async () => {
    try {
      const [p, c, h] = await Promise.all([
        api.get(`/pex/painel`).catch(() => ({ data: null })),
        api.get(`/pex/compliance`).catch(() => ({ data: [] })),
        api.get(`/pex/historico?meses=6`).catch(() => ({ data: [] })),
      ]);
      setPainel(p.data);
      setCompliance(c.data);
      setHistorico(h.data);
    } catch (e) {
      console.error(e);
    }
  }, []);

  useEffect(() => { carregar(); }, [carregar]);

  async function uploadCromie(e) {
    const file = e.target.files[0];
    if (!file) return;
    setUploading(true);
    setMsg(null);
    const form = new FormData();
    form.append("arquivo", file);
    try {
      const { data } = await api.post(`/pex/cromie/upload`, form, {
        headers: { "Content-Type": "multipart/form-data" },
      });
      setMsg({
        tipo: data.schema_alterado ? "aviso" : "ok",
        texto: data.schema_alterado
          ? `⚠️ Schema alterado! Colunas novas: ${data.colunas_novas.join(", ") || "nenhuma"}. Removidas: ${data.colunas_removidas.join(", ") || "nenhuma"}`
          : `✅ CROmie processado — ${data.totais?.total_cliente_final} leads, ${data.totais?.total_contador} contadores. PEX: ${data.pex?.total_geral_pts} pts (${data.pex?.risco})`,
      });
      carregar();
    } catch (err) {
      setMsg({ tipo: "erro", texto: `Erro: ${err.response?.data?.detail || err.message}` });
    } finally {
      setUploading(false);
      e.target.value = "";
    }
  }

  const riscoCfg = RISCO[painel?.risco_classificacao] || RISCO.AMARELO;

  return (
    <div className="p-6 max-w-6xl mx-auto">
      {/* Header */}
      <div className="flex items-center justify-between mb-6">
        <div>
          <h1 className="text-xl font-bold text-slate-100 tracking-wide">Painel PEX</h1>
          <p className="text-xs text-slate-500 mt-0.5">
            {painel ? `Última atualização: ${new Date(painel.created_at).toLocaleString("pt-BR")}` : "Aguardando primeiro upload"}
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
            {uploading ? "Processando..." : "Upload CROmie"}
            <input type="file" accept=".xlsx" className="hidden" onChange={uploadCromie} disabled={uploading} />
          </label>
        </div>
      </div>

      {/* Mensagem de upload */}
      {msg && (
        <div className={`mb-4 px-4 py-3 rounded-lg text-sm ${
          msg.tipo === "ok" ? "bg-emerald-500/10 text-emerald-400 border border-emerald-500/30" :
          msg.tipo === "aviso" ? "bg-yellow-500/10 text-yellow-400 border border-yellow-500/30" :
          "bg-red-500/10 text-red-400 border border-red-500/30"
        }`}>
          {msg.texto}
        </div>
      )}

      {/* Tabs */}
      <div className="flex gap-1 mb-6 border-b border-slate-800">
        {[["painel","Painel"], ["compliance","Compliance"], ["historico","Histórico"]].map(([k, l]) => (
          <button key={k} onClick={() => setTab(k)}
            className={`px-4 py-2.5 text-xs font-bold tracking-wider transition-all ${
              tab === k ? "text-cyan-400 border-b-2 border-cyan-400" : "text-slate-500 hover:text-slate-300"
            }`}>
            {l.toUpperCase()}
          </button>
        ))}
      </div>

      {/* TAB: PAINEL */}
      {tab === "painel" && painel && (
        <div className="space-y-6">
          {/* Score geral */}
          <div className={`rounded-xl border p-6 ${riscoCfg.bg} ${riscoCfg.border}`}>
            <div className="flex items-center gap-6">
              <ScoreRing score={painel.total_geral_pts} risco={painel.risco_classificacao} />
              <div>
                <p className={`text-2xl font-bold ${riscoCfg.text}`}>
                  {painel.total_geral_pts?.toFixed(1)} / 100 pontos
                </p>
                <p className="text-sm text-slate-300 mt-1">
                  {painel.total_geral_pts >= 95 ? "Franquia Excelente" :
                   painel.total_geral_pts >= 76 ? "Franquia Certificada" :
                   painel.total_geral_pts >= 60 ? "Franquia Qualificada" :
                   painel.total_geral_pts >= 50 ? "Franquia Aderente" :
                   painel.total_geral_pts >= 36 ? "Franquia em Desenvolvimento" :
                   "Franquia Não Aderente ⚠️"}
                </p>
                <div className="flex items-center gap-2 mt-2">
                  <div className={`w-2 h-2 rounded-full ${riscoCfg.dot}`} />
                  <span className={`text-xs ${riscoCfg.text}`}>{painel.risco_classificacao}</span>
                  {painel.total_geral_pts < 40 && (
                    <span className="text-xs text-red-400 ml-2">⚠️ Risco de descredenciamento</span>
                  )}
                </div>
              </div>
              {/* Pilares resumidos */}
              <div className="ml-auto grid grid-cols-3 gap-4 text-center">
                {[
                  ["Resultado", painel.total_resultado_pts, 60],
                  ["Gestão", painel.total_gestao_pts, 20],
                  ["Engajamento", painel.total_engajamento_pts, 20],
                ].map(([nome, pts, max]) => (
                  <div key={nome} className="bg-slate-900/60 rounded-lg p-3">
                    <p className="text-xs text-slate-500">{nome}</p>
                    <p className="text-lg font-bold text-slate-200 mt-1">{(pts || 0).toFixed(1)}</p>
                    <p className="text-xs text-slate-500">/ {max} pts</p>
                  </div>
                ))}
              </div>
            </div>
          </div>

          {/* Indicadores do Pilar Resultado */}
          <div className="bg-slate-900 border border-slate-800 rounded-xl p-5">
            <h3 className="text-xs font-bold text-slate-400 tracking-widest mb-4">PILAR RESULTADO — DETALHAMENTO</h3>
            <div className="grid grid-cols-2 gap-x-8">
              <div>
                <Bar pct={painel.nmrr_pct} pts={painel.nmrr_pts} maxPts={10} label="NMRR" />
                <Bar pct={painel.reunioes_ec_du_realizado * 25} pts={painel.reunioes_ec_du_pts} maxPts={3} label="Reuniões EC/DU" />
                <Bar pct={painel.contadores_trabalhados_pct} pts={painel.contadores_trabalhados_pts} maxPts={2} label="Contadores Trabalhados" />
                <Bar pct={painel.contadores_indicando_pct} pts={painel.contadores_indicando_pts} maxPts={3} label="Contadores Indicando" />
                <Bar pct={painel.contadores_ativando_pct} pts={painel.contadores_ativando_pts} maxPts={4} label="Contadores Ativando" />
                <Bar pct={painel.conversao_total_pct} pts={painel.conversao_total_pts} maxPts={4} label="Conversão Total de Leads" />
                <Bar pct={painel.conversao_m0_pct} pts={painel.conversao_m0_pts} maxPts={3} label="Conversão M0" />
                <Bar pct={painel.conversao_inbound_pct} pts={painel.conversao_inbound_pts} maxPts={2} label="Conversão Inbound" />
              </div>
              <div>
                <Bar pct={painel.demo_du_realizado * 25} pts={painel.demo_du_pts} maxPts={4} label="Demo/dia útil" />
                <Bar pct={painel.demos_outbound_pct} pts={painel.demos_outbound_pts} maxPts={3} label="Demos Outbound" />
                <Bar pct={painel.sow_pct} pts={painel.sow_pts} maxPts={3} label="Share of Wallet" />
                <Bar pct={painel.mapeamento_carteira_pct} pts={painel.mapeamento_carteira_pts} maxPts={2} label="Mapeamento Carteira" />
                <Bar pct={painel.reuniao_contador_inbound_pct} pts={painel.reuniao_contador_inbound_pts} maxPts={4} label="Reunião Contador Inbound" />
                <Bar pct={painel.integracao_contabil_pct} pts={painel.integracao_contabil_pts} maxPts={3} label="Integração Contábil" />
                <Bar pct={100 - (painel.early_churn_pct || 0) * 10} pts={painel.early_churn_pts} maxPts={3} label="Early Churn" />
                <Bar pct={painel.crescimento_40_pct} pts={painel.crescimento_40_pts} maxPts={5} label="Crescimento 40%" />
              </div>
            </div>
          </div>
        </div>
      )}

      {/* TAB: COMPLIANCE */}
      {tab === "compliance" && (
        <div className="bg-slate-900 border border-slate-800 rounded-xl overflow-hidden">
          <div className="px-5 py-3 border-b border-slate-800">
            <h3 className="text-xs font-bold text-slate-400 tracking-widest">GAPS DE COMPLIANCE POR COLABORADOR</h3>
          </div>
          {compliance.length === 0 ? (
            <div className="p-8 text-center text-slate-500 text-sm">
              Nenhum dado de compliance. Faça o upload do CROmie.
            </div>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full text-xs">
                <thead>
                  <tr className="text-slate-500 border-b border-slate-800 text-left">
                    <th className="px-4 py-3">Colaborador</th>
                    <th className="px-4 py-3 text-center">Sem Tarefa Futura</th>
                    <th className="px-4 py-3 text-center">Sem Temperatura</th>
                    <th className="px-4 py-3 text-center">Sem Previsão</th>
                    <th className="px-4 py-3 text-center">Sem Ticket</th>
                    <th className="px-4 py-3 text-center">Contadores s/ Tarefa</th>
                    <th className="px-4 py-3 text-center">Pontos em Risco</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-800">
                  {compliance.map((row, i) => {
                    const risco = row.pontos_em_risco > 2 ? "text-red-400" :
                                  row.pontos_em_risco > 1 ? "text-yellow-400" : "text-emerald-400";
                    return (
                      <tr key={i} className="hover:bg-slate-800/40">
                        <td className="px-4 py-3 font-bold text-slate-200">{row.usuario_responsavel}</td>
                        {[
                          row.leads_sem_tarefa_futura,
                          row.leads_sem_temperatura,
                          row.leads_sem_previsao,
                          row.leads_sem_ticket,
                          row.contadores_sem_tarefa_mes,
                        ].map((v, j) => (
                          <td key={j} className={`px-4 py-3 text-center font-mono ${v > 0 ? "text-red-400" : "text-slate-600"}`}>
                            {v > 0 ? v : "—"}
                          </td>
                        ))}
                        <td className={`px-4 py-3 text-center font-bold ${risco}`}>
                          {row.pontos_em_risco?.toFixed(1)}
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          )}
        </div>
      )}

      {/* TAB: HISTÓRICO */}
      {tab === "historico" && (
        <div className="space-y-3">
          {historico.length === 0 ? (
            <div className="p-8 text-center text-slate-500 text-sm">Sem histórico disponível.</div>
          ) : (
            historico.map((h, i) => {
              const cfg = RISCO[h.risco] || RISCO.AMARELO;
              return (
                <div key={i} className={`rounded-xl border px-5 py-4 flex items-center justify-between ${cfg.bg} ${cfg.border}`}>
                  <div className="flex items-center gap-4">
                    <div className={`w-2.5 h-2.5 rounded-full ${cfg.dot}`} />
                    <span className="text-sm font-bold text-slate-200">{h.mes_ref}</span>
                  </div>
                  <div className="flex items-center gap-8 text-xs text-slate-400">
                    <span>Resultado: <strong className="text-slate-200">{h.resultado_pts?.toFixed(1)}</strong></span>
                    <span>Gestão: <strong className="text-slate-200">{h.gestao_pts?.toFixed(1)}</strong></span>
                    <span>Engajamento: <strong className="text-slate-200">{h.engajamento_pts?.toFixed(1)}</strong></span>
                    <span className={`font-bold text-sm ${cfg.text}`}>{h.pontuacao?.toFixed(1)} pts</span>
                  </div>
                </div>
              );
            })
          )}
        </div>
      )}

      {/* Estado vazio */}
      {tab === "painel" && !painel && (
        <div className="text-center py-20">
          <BarChart3 size={48} className="mx-auto text-slate-700 mb-4" />
          <p className="text-slate-500 text-sm">Nenhum dado carregado.</p>
          <p className="text-slate-600 text-xs mt-1">Faça o upload do Excel do CROmie para calcular os indicadores.</p>
        </div>
      )}
    </div>
  );
}