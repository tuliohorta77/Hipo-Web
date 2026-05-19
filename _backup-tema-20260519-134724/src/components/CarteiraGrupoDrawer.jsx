// web/src/components/CarteiraGrupoDrawer.jsx
//
// Drawer lateral com drill-down de um grupo: lista de CNPJs + últimas tarefas.
import { useEffect, useState } from "react";
import { X, Building2, ListChecks, MapPin, Users } from "lucide-react";
import api from "../api";

function badgeParceria(p) {
  if (p === "Parceiro") return "bg-emerald-500/10 text-emerald-300 border-emerald-500/30";
  if (p === "Não Parceiro") return "bg-slate-700/40 text-slate-400 border-slate-600";
  return "bg-slate-700/40 text-slate-500 border-slate-700";
}

function badgeSituacao(s) {
  if (s === "ATRASADA") return "bg-red-500/10 text-red-300 border-red-500/30";
  if (s === "FUTURA")   return "bg-cyan-500/10 text-cyan-300 border-cyan-500/30";
  if (s === "EM_DIA")   return "bg-emerald-500/10 text-emerald-300 border-emerald-500/30";
  return "bg-slate-700/40 text-slate-500 border-slate-700";
}

function fmtDate(d) {
  if (!d) return "—";
  try {
    return new Date(d).toLocaleString("pt-BR", {
      day: "2-digit", month: "2-digit", year: "numeric",
      hour: "2-digit", minute: "2-digit",
    });
  } catch { return "—"; }
}

export default function CarteiraGrupoDrawer({ idGrupo, onFechar, nomeGrupo }) {
  const [detalhe, setDetalhe] = useState(null);
  const [loading, setLoading] = useState(false);
  const [erro, setErro] = useState(null);

  useEffect(() => {
    if (!idGrupo) return;
    setLoading(true);
    setErro(null);
    setDetalhe(null);
    api.get(`/carteira/grupos/${encodeURIComponent(idGrupo)}`)
      .then((r) => setDetalhe(r.data))
      .catch((e) => setErro(e.response?.data?.detail || e.message))
      .finally(() => setLoading(false));
  }, [idGrupo]);

  if (!idGrupo) return null;

  return (
    <div className="fixed inset-0 z-40 flex" onClick={onFechar}>
      <div className="flex-1 bg-black/60" />
      <aside
        className="w-full max-w-2xl bg-slate-950 border-l border-slate-800 overflow-y-auto"
        onClick={(e) => e.stopPropagation()}
      >
        {/* Header */}
        <div className="sticky top-0 z-10 bg-slate-950 border-b border-slate-800 px-6 py-4 flex items-center justify-between">
          <div>
            <h2 className="text-lg font-bold text-slate-100">{nomeGrupo || "Grupo"}</h2>
            <p className="text-xs text-slate-500 mt-0.5 font-mono">{idGrupo}</p>
          </div>
          <button
            onClick={onFechar}
            className="text-slate-500 hover:text-slate-300 p-1 rounded"
            aria-label="Fechar"
          >
            <X size={20} />
          </button>
        </div>

        {/* Conteúdo */}
        <div className="p-6 space-y-6">
          {loading && <p className="text-sm text-slate-500">Carregando...</p>}
          {erro && (
            <p className="text-sm text-red-400 bg-red-500/10 border border-red-500/30 rounded p-3">
              {erro}
            </p>
          )}

          {detalhe && (
            <>
              {/* CNPJs do grupo */}
              <section>
                <div className="flex items-center gap-2 mb-3">
                  <Building2 size={14} className="text-cyan-400" />
                  <h3 className="text-xs font-bold text-slate-400 tracking-widest">
                    CNPJS ({detalhe.qtd_cnpj})
                  </h3>
                </div>
                <div className="space-y-2">
                  {detalhe.cnpjs.map((c, i) => (
                    <div
                      key={c.cnpj_contador || i}
                      className="bg-slate-900 border border-slate-800 rounded-lg p-3"
                    >
                      <div className="flex items-start justify-between mb-1">
                        <span className="text-sm font-bold text-slate-200">
                          {c.contabilidade || "—"}
                        </span>
                        <span className={`text-[9px] tracking-widest px-2 py-0.5 rounded border ${badgeParceria(c.parceria)}`}>
                          {(c.parceria || "—").toUpperCase()}
                        </span>
                      </div>
                      <p className="text-xs text-slate-500 font-mono">{c.cnpj_contador}</p>
                      <div className="flex items-center gap-3 mt-2 text-xs text-slate-500">
                        {c.cidade_uf && (
                          <span className="flex items-center gap-1">
                            <MapPin size={10} /> {c.cidade_uf}
                          </span>
                        )}
                        {c.colaborador_nome && (
                          <span className="flex items-center gap-1">
                            <Users size={10} /> {c.colaborador_nome}
                          </span>
                        )}
                        {c.apps_ativos != null && (
                          <span>{c.apps_ativos} apps ativos</span>
                        )}
                        {c.leads_no_mes != null && c.leads_no_mes > 0 && (
                          <span className="text-cyan-300">{c.leads_no_mes} leads/mês</span>
                        )}
                      </div>
                    </div>
                  ))}
                </div>
              </section>

              {/* Tarefas */}
              <section>
                <div className="flex items-center gap-2 mb-3">
                  <ListChecks size={14} className="text-cyan-400" />
                  <h3 className="text-xs font-bold text-slate-400 tracking-widest">
                    TAREFAS ({detalhe.tarefas.length})
                  </h3>
                </div>
                {detalhe.tarefas.length === 0 ? (
                  <p className="text-sm text-slate-500 italic">Nenhuma tarefa registrada.</p>
                ) : (
                  <div className="bg-slate-900 border border-slate-800 rounded-lg overflow-hidden">
                    <table className="w-full text-xs">
                      <thead>
                        <tr className="text-slate-500 border-b border-slate-800 text-left">
                          <th className="px-3 py-2">Data</th>
                          <th className="px-3 py-2">Canal</th>
                          <th className="px-3 py-2">Tipo</th>
                          <th className="px-3 py-2">Situação</th>
                          <th className="px-3 py-2">Executivo</th>
                        </tr>
                      </thead>
                      <tbody className="divide-y divide-slate-800">
                        {detalhe.tarefas.map((t, i) => (
                          <tr key={i} className="hover:bg-slate-800/40">
                            <td className="px-3 py-2 text-slate-300 whitespace-nowrap">
                              {fmtDate(t.data_efetiva)}
                            </td>
                            <td className="px-3 py-2 text-slate-300">{t.tarefa_canal || "—"}</td>
                            <td className="px-3 py-2 text-slate-400">{t.tipo_tarefa || "—"}</td>
                            <td className="px-3 py-2">
                              <span className={`text-[9px] tracking-widest px-2 py-0.5 rounded border ${badgeSituacao(t.situacao)}`}>
                                {t.situacao}
                              </span>
                            </td>
                            <td className="px-3 py-2 text-slate-400">{t.executivo_nome || "—"}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                )}
              </section>
            </>
          )}
        </div>
      </aside>
    </div>
  );
}
