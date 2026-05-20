// web/src/components/CarteiraGrupoDrawer.jsx
//
// Drawer lateral do drilldown de um grupo no módulo Contadores.
// v2: tema claro + 2 abas (Tarefas | Leads).
//   - Tarefas: o que já existia (carteira_tarefa do grupo)
//   - Leads:   oportunidades por CNPJ Contador (cliente_oportunidade)
//
// Quando vê 1 CNPJ no grupo: aba Leads mostra os leads desse CNPJ.
// Quando vê N CNPJs: agrega leads de TODOS os CNPJs do grupo.

import { useEffect, useMemo, useState } from "react";
import {
  X, Building2, ListChecks, MapPin, Users, Target,
  TrendingUp, AlertTriangle, ExternalLink,
} from "lucide-react";
import api from "../api";

// ── Badges/utilitários ───────────────────────────────────────────

function badgeParceria(p) {
  if (p === "Parceiro") return "bg-emerald-50 text-emerald-700 border-emerald-100";
  if (p === "Não Parceiro") return "bg-hipo-bg text-hipo-slate border-hipo-border";
  return "bg-hipo-bg text-hipo-muted border-hipo-border";
}

function badgeSituacao(s) {
  if (s === "ATRASADA") return "bg-red-50 text-hipo-danger border-red-100";
  if (s === "FUTURA")   return "bg-blue-50 text-hipo-blue border-blue-100";
  if (s === "EM_DIA")   return "bg-emerald-50 text-emerald-700 border-emerald-100";
  return "bg-hipo-bg text-hipo-muted border-hipo-border";
}

function badgeStatusLead(s) {
  const v = (s || "").toLowerCase();
  if (v === "em andamento")  return "bg-blue-50 text-hipo-blue border-blue-100";
  if (v === "conquistado")   return "bg-emerald-50 text-emerald-700 border-emerald-100";
  if (v === "perdido")       return "bg-red-50 text-hipo-danger border-red-100";
  if (v === "cancelado")     return "bg-hipo-bg text-hipo-slate border-hipo-border";
  return "bg-hipo-bg text-hipo-muted border-hipo-border";
}

function fmtDate(d) {
  if (!d) return "—";
  try {
    return new Date(d).toLocaleString("pt-BR", {
      day: "2-digit", month: "2-digit", year: "numeric",
    });
  } catch { return "—"; }
}

function fmtMoeda(v) {
  if (v == null) return "—";
  return Number(v).toLocaleString("pt-BR", {
    style: "currency", currency: "BRL", maximumFractionDigits: 0,
  });
}


// ── Componente ───────────────────────────────────────────────────

export default function CarteiraGrupoDrawer({ idGrupo, onFechar, nomeGrupo }) {
  const [detalhe, setDetalhe] = useState(null);
  const [loading, setLoading] = useState(false);
  const [erro, setErro] = useState(null);
  const [aba, setAba] = useState("TAREFAS");

  // Leads agregados de todos os CNPJs do grupo (carregamento lazy)
  const [leadsPorCnpj, setLeadsPorCnpj] = useState({}); // { cnpj: {kpis, leads} }
  const [loadingLeads, setLoadingLeads] = useState(false);

  // Carrega o drilldown principal (CNPJs + tarefas) — igual à v1
  useEffect(() => {
    if (!idGrupo) return;
    setLoading(true);
    setErro(null);
    setDetalhe(null);
    setLeadsPorCnpj({});
    setAba("TAREFAS");
    api.get(`/carteira/grupos/${encodeURIComponent(idGrupo)}`)
      .then((r) => setDetalhe(r.data))
      .catch((e) => setErro(e.response?.data?.detail || e.message))
      .finally(() => setLoading(false));
  }, [idGrupo]);

  // Lazy-load dos leads ao mudar pra aba Leads
  useEffect(() => {
    if (aba !== "LEADS" || !detalhe?.cnpjs?.length) return;
    if (Object.keys(leadsPorCnpj).length > 0) return; // já carregou

    setLoadingLeads(true);
    const cnpjs = detalhe.cnpjs.map((c) => c.cnpj_contador).filter(Boolean);

    Promise.all(
      cnpjs.map((cnpj) =>
        api.get('/clientes/contador-leads', { params: { cnpj } })
          .then((r) => [cnpj, r.data])
          .catch(() => [cnpj, null])
      )
    )
      .then((pares) => {
        const map = {};
        for (const [cnpj, data] of pares) {
          if (data) map[cnpj] = data;
        }
        setLeadsPorCnpj(map);
      })
      .finally(() => setLoadingLeads(false));
  }, [aba, detalhe, leadsPorCnpj]);

  // Agrega todos os leads de todos os CNPJs num único array
  const leadsAgregados = useMemo(() => {
    const out = [];
    for (const [cnpj, data] of Object.entries(leadsPorCnpj)) {
      for (const lead of data.leads || []) {
        out.push({ ...lead, _cnpj_contador: cnpj });
      }
    }
    out.sort((a, b) => {
      const da = new Date(a.data_atualizacao || 0).getTime();
      const db = new Date(b.data_atualizacao || 0).getTime();
      return db - da;
    });
    return out;
  }, [leadsPorCnpj]);

  const kpisLeads = useMemo(() => {
    const k = { total: 0, em_andamento: 0, conquistado: 0, perdido: 0 };
    for (const data of Object.values(leadsPorCnpj)) {
      k.total += data.kpis?.total || 0;
      k.em_andamento += data.kpis?.em_andamento || 0;
      k.conquistado += data.kpis?.conquistado || 0;
      k.perdido += data.kpis?.perdido || 0;
    }
    return k;
  }, [leadsPorCnpj]);

  if (!idGrupo) return null;

  return (
    <div className="fixed inset-0 z-40 flex" onClick={onFechar}>
      <div className="flex-1 bg-hipo-ink/40" />
      <aside
        className="w-full max-w-2xl bg-hipo-card border-l border-hipo-border overflow-y-auto"
        onClick={(e) => e.stopPropagation()}
      >
        {/* Header */}
        <div className="sticky top-0 z-10 bg-hipo-card border-b border-hipo-border px-6 py-4 flex items-center justify-between">
          <div>
            <h2 className="text-lg font-semibold text-hipo-ink">{nomeGrupo || "Grupo"}</h2>
            <p className="text-xs text-hipo-muted mt-0.5 font-mono">{idGrupo}</p>
          </div>
          <button
            onClick={onFechar}
            className="text-hipo-slate hover:text-hipo-ink p-1 rounded"
            aria-label="Fechar"
          >
            <X size={20} />
          </button>
        </div>

        {/* Conteúdo */}
        <div className="p-6 space-y-6">
          {loading && <p className="text-sm text-hipo-slate">Carregando...</p>}
          {erro && (
            <p className="text-sm text-hipo-danger bg-red-50 border border-red-100 rounded-lg p-3">
              {erro}
            </p>
          )}

          {detalhe && (
            <>
              {/* CNPJs do grupo */}
              <section>
                <div className="flex items-center gap-2 mb-3">
                  <Building2 size={14} className="text-hipo-blue" />
                  <h3 className="text-xs font-semibold text-hipo-slate tracking-wider uppercase">
                    CNPJs ({detalhe.qtd_cnpj})
                  </h3>
                </div>
                <div className="space-y-2">
                  {detalhe.cnpjs.map((c, i) => (
                    <div
                      key={c.cnpj_contador || i}
                      className="bg-hipo-bg border border-hipo-border rounded-lg p-3"
                    >
                      <div className="flex items-start justify-between mb-1">
                        <span className="text-sm font-semibold text-hipo-ink">
                          {c.contabilidade || "—"}
                        </span>
                        <span className={`text-[10px] tracking-wider px-2 py-0.5 rounded-full border ${badgeParceria(c.parceria)}`}>
                          {(c.parceria || "—").toUpperCase()}
                        </span>
                      </div>
                      <p className="text-xs text-hipo-muted font-mono">{c.cnpj_contador}</p>
                      <div className="flex items-center gap-3 mt-2 text-xs text-hipo-slate flex-wrap">
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
                      </div>
                    </div>
                  ))}
                </div>
              </section>

              {/* Tabs: Tarefas | Leads */}
              <section>
                <div className="flex border-b border-hipo-border mb-4">
                  <button
                    onClick={() => setAba("TAREFAS")}
                    className={`px-4 py-2 text-sm font-medium border-b-2 transition-colors ${
                      aba === "TAREFAS"
                        ? "border-hipo-blue text-hipo-blue"
                        : "border-transparent text-hipo-slate hover:text-hipo-ink"
                    }`}
                  >
                    <span className="flex items-center gap-2">
                      <ListChecks size={14} />
                      Tarefas ({detalhe.tarefas.length})
                    </span>
                  </button>
                  <button
                    onClick={() => setAba("LEADS")}
                    className={`px-4 py-2 text-sm font-medium border-b-2 transition-colors ${
                      aba === "LEADS"
                        ? "border-hipo-blue text-hipo-blue"
                        : "border-transparent text-hipo-slate hover:text-hipo-ink"
                    }`}
                  >
                    <span className="flex items-center gap-2">
                      <Target size={14} />
                      Leads
                      {aba === "LEADS" && !loadingLeads && (
                        <span className="text-xs text-hipo-muted">({kpisLeads.total})</span>
                      )}
                    </span>
                  </button>
                </div>

                {/* Aba TAREFAS */}
                {aba === "TAREFAS" && (
                  detalhe.tarefas.length === 0 ? (
                    <p className="text-sm text-hipo-slate italic">Nenhuma tarefa registrada.</p>
                  ) : (
                    <div className="bg-hipo-card border border-hipo-border rounded-lg overflow-hidden">
                      <table className="w-full text-xs">
                        <thead>
                          <tr className="text-hipo-slate border-b border-hipo-border text-left">
                            <th className="px-3 py-2 font-medium">Data</th>
                            <th className="px-3 py-2 font-medium">Canal</th>
                            <th className="px-3 py-2 font-medium">Tipo</th>
                            <th className="px-3 py-2 font-medium">Situação</th>
                            <th className="px-3 py-2 font-medium">Executivo</th>
                          </tr>
                        </thead>
                        <tbody className="divide-y divide-hipo-border">
                          {detalhe.tarefas.map((t, i) => (
                            <tr key={i} className="hover:bg-hipo-bg">
                              <td className="px-3 py-2 text-hipo-ink whitespace-nowrap">
                                {fmtDate(t.data_efetiva)}
                              </td>
                              <td className="px-3 py-2 text-hipo-ink">{t.tarefa_canal || "—"}</td>
                              <td className="px-3 py-2 text-hipo-slate">{t.tipo_tarefa || "—"}</td>
                              <td className="px-3 py-2">
                                <span className={`text-[10px] tracking-wider px-2 py-0.5 rounded-full border ${badgeSituacao(t.situacao)}`}>
                                  {t.situacao}
                                </span>
                              </td>
                              <td className="px-3 py-2 text-hipo-slate">{t.executivo_nome || "—"}</td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  )
                )}

                {/* Aba LEADS */}
                {aba === "LEADS" && (
                  <>
                    {loadingLeads ? (
                      <p className="text-sm text-hipo-slate italic">Carregando leads...</p>
                    ) : kpisLeads.total === 0 ? (
                      <div className="text-center py-8">
                        <Target size={32} className="mx-auto text-hipo-muted mb-2" />
                        <p className="text-sm text-hipo-slate">
                          Nenhum lead vinculado a esses contadores.
                        </p>
                        <p className="text-xs text-hipo-muted mt-1">
                          Faça upload das oportunidades em <strong>Clientes</strong> pra ver os leads aqui.
                        </p>
                      </div>
                    ) : (
                      <>
                        {/* Mini-KPIs */}
                        <div className="grid grid-cols-4 gap-2 mb-4">
                          <div className="bg-hipo-bg border border-hipo-border rounded-lg p-2 text-center">
                            <p className="text-xs text-hipo-slate">Total</p>
                            <p className="text-lg font-semibold text-hipo-ink">{kpisLeads.total}</p>
                          </div>
                          <div className="bg-blue-50 border border-blue-100 rounded-lg p-2 text-center">
                            <p className="text-xs text-hipo-blue">Em andam.</p>
                            <p className="text-lg font-semibold text-hipo-blue">{kpisLeads.em_andamento}</p>
                          </div>
                          <div className="bg-emerald-50 border border-emerald-100 rounded-lg p-2 text-center">
                            <p className="text-xs text-emerald-700">Conquist.</p>
                            <p className="text-lg font-semibold text-emerald-700">{kpisLeads.conquistado}</p>
                          </div>
                          <div className="bg-red-50 border border-red-100 rounded-lg p-2 text-center">
                            <p className="text-xs text-hipo-danger">Perdido</p>
                            <p className="text-lg font-semibold text-hipo-danger">{kpisLeads.perdido}</p>
                          </div>
                        </div>

                        {/* Tabela de leads */}
                        <div className="bg-hipo-card border border-hipo-border rounded-lg overflow-hidden">
                          <table className="w-full text-xs">
                            <thead>
                              <tr className="text-hipo-slate border-b border-hipo-border text-left">
                                <th className="px-3 py-2 font-medium">Razão Social</th>
                                <th className="px-3 py-2 font-medium">Fase</th>
                                <th className="px-3 py-2 font-medium">Status</th>
                                <th className="px-3 py-2 font-medium text-right">Proposta NMRR</th>
                                <th className="px-3 py-2 font-medium text-right">Dias</th>
                              </tr>
                            </thead>
                            <tbody className="divide-y divide-hipo-border">
                              {leadsAgregados.slice(0, 50).map((l) => (
                                <tr key={l.op_id} className="hover:bg-hipo-bg">
                                  <td className="px-3 py-2 text-hipo-ink">
                                    <div className="font-medium">{l.razao_social || "—"}</div>
                                    <div className="text-xs text-hipo-muted font-mono">{l.cnpj}</div>
                                  </td>
                                  <td className="px-3 py-2 text-hipo-slate">{l.fase || "—"}</td>
                                  <td className="px-3 py-2">
                                    <span className={`text-[10px] tracking-wider px-2 py-0.5 rounded-full border ${badgeStatusLead(l.status)}`}>
                                      {(l.status || "—").toUpperCase()}
                                    </span>
                                  </td>
                                  <td className="px-3 py-2 text-right text-hipo-ink whitespace-nowrap">
                                    {fmtMoeda(l.proposta_nmrr)}
                                  </td>
                                  <td className="px-3 py-2 text-right text-hipo-slate whitespace-nowrap">
                                    {l.dias_parado != null ? `${l.dias_parado}d` : "—"}
                                  </td>
                                </tr>
                              ))}
                            </tbody>
                          </table>
                          {leadsAgregados.length > 50 && (
                            <div className="px-3 py-2 text-xs text-hipo-muted bg-hipo-bg border-t border-hipo-border text-center">
                              Mostrando 50 de {leadsAgregados.length} leads. Veja todos em <strong>Clientes</strong>.
                            </div>
                          )}
                        </div>
                      </>
                    )}
                  </>
                )}
              </section>
            </>
          )}
        </div>
      </aside>
    </div>
  );
}
