// web/src/components/CarteiraGrupoDrawer.jsx
//
// Drawer lateral do drilldown de um grupo no módulo Contadores.
// v2: tema claro + 2 abas (Tarefas | Leads).
//   - Tarefas: o que já existia (carteira_tarefa do grupo)
//   - Leads:   oportunidades por CNPJ Contador (cliente_oportunidade)
//
// Quando vê 1 CNPJ no grupo: aba Leads mostra os leads desse CNPJ.
// Quando vê N CNPJs: agrega leads de TODOS os CNPJs do grupo.
//
// Patch 7 (filtro clicável):
//   - Cards de KPI (Em andamento/Conquistado/Perdido) agora são clicáveis
//   - Click filtra a tabela; click no card já ativo limpa o filtro
//   - Card "Total" funciona como "limpar filtro" (volta a mostrar todos)
//   - Abreviações removidas: "Em andam." → "Em andamento", "Conquist." → "Conquistado",
//     coluna "Temp." → "Temperatura"

import { Fragment, useEffect, useMemo, useRef, useState } from "react";
import {
  X, Building2, ListChecks, MapPin, Users, Target, ChevronRight, ChevronDown,
  TrendingUp, AlertTriangle, ExternalLink,
} from "lucide-react";
import api from "../api";

// ── Badges/utilitários (Manual de Marca §6: pastel, sem saturação excessiva)

function badgeParceria(p) {
  if (p === "Parceiro") return "bg-hipo-successSoft text-hipo-success border-hipo-successBorder";
  if (p === "Não Parceiro") return "bg-hipo-bg text-hipo-slate border-hipo-border";
  return "bg-hipo-bg text-hipo-muted border-hipo-border";
}

function badgeSituacao(s) {
  if (s === "ATRASADA") return "bg-hipo-dangerSoft text-hipo-danger border-hipo-dangerBorder";
  if (s === "FUTURA")   return "bg-hipo-blueSoft text-hipo-blue border-hipo-blueSoft";
  if (s === "EM_DIA")   return "bg-hipo-successSoft text-hipo-success border-hipo-successBorder";
  return "bg-hipo-bg text-hipo-muted border-hipo-border";
}

function badgeStatusLead(s) {
  const v = (s || "").toLowerCase();
  if (v === "ativo")         return "bg-hipo-blueSoft text-hipo-blue border-hipo-blueSoft";
  if (v === "em andamento")  return "bg-hipo-blueSoft text-hipo-blue border-hipo-blueSoft";
  if (v === "conquistado")   return "bg-hipo-successSoft text-hipo-success border-hipo-successBorder";
  if (v === "perdido")       return "bg-hipo-dangerSoft text-hipo-danger border-hipo-dangerBorder";
  if (v === "cancelado")     return "bg-hipo-bg text-hipo-slate border-hipo-border";
  return "bg-hipo-bg text-hipo-muted border-hipo-border";
}

// Badge de temperatura: escala definida pelo produto.
//   >= 80  → quente (success)
//   40-79  → morno  (warning)
//   < 40   → frio   (info azul)
//   null/0 → "—" neutro
function badgeTemperatura(t) {
  if (t == null || t === 0) {
    return "bg-hipo-bg text-hipo-muted border-hipo-border";
  }
  const v = Number(t);
  if (v >= 80) return "bg-hipo-successSoft text-hipo-success border-hipo-successBorder";
  if (v >= 40) return "bg-hipo-warningSoft text-hipo-warning border-hipo-warningBorder";
  return "bg-hipo-blueSoft text-hipo-blue border-hipo-blueSoft";
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

function fmtTemperatura(t) {
  if (t == null || t === 0) return "—";
  return `${Math.round(Number(t))}°`;
}

// Mapa de status (canônico) → label legível pro contador no rodapé
const FILTRO_LABELS = {
  ativo:        "Em andamento",
  conquistado:  "Conquistado",
  perdido:      "Perdido",
};


// ── Componente ─────────────────────────────────────────────────

export default function CarteiraGrupoDrawer({ idGrupo, onFechar, nomeGrupo }) {
  const [detalhe, setDetalhe] = useState(null);
  const [loading, setLoading] = useState(false);
  const [erro, setErro] = useState(null);
  const [aba, setAba] = useState("TAREFAS");

  // Leads agregados por CNPJ. Cada valor pode ser:
  //   - { kpis, leads }       → sucesso
  //   - { _erro: true, status }→ falha (ex: 403, 500)
  const [leadsPorCnpj, setLeadsPorCnpj] = useState({});
  const [loadingLeads, setLoadingLeads] = useState(false);

  // Patch 7: filtro de status aplicado na tabela. null = sem filtro.
  // Valores canônicos: "ativo" | "conquistado" | "perdido" (case-insensitive ao comparar).
  const [filtroStatus, setFiltroStatus] = useState(null);

  // Flag idempotente: "já tentei carregar leads deste detalhe?"
  // Necessária pra evitar loop quando TODOS os requests falham (e o map
  // fica vazio). Reseta toda vez que muda de grupo.
  const leadsCarregados = useRef(false);

  // Drill-in nas linhas de lead: mostra tarefas do op_id ao expandir
  const [leadExpandido, setLeadExpandido] = useState(null);
  const [tarefasPorOp, setTarefasPorOp] = useState({});

  // Carrega o drilldown principal (CNPJs + tarefas)
  useEffect(() => {
    if (!idGrupo) return;
    setLoading(true);
    setErro(null);
    setDetalhe(null);
    setLeadsPorCnpj({});
    setLeadExpandido(null);
    setTarefasPorOp({});
    setAba("TAREFAS");
    setFiltroStatus(null);
    leadsCarregados.current = false;
    api.get(`/carteira/grupos/${encodeURIComponent(idGrupo)}`)
      .then((r) => setDetalhe(r.data))
      .catch((e) => setErro(e.response?.data?.detail || e.message))
      .finally(() => setLoading(false));
  }, [idGrupo]);

  // Lazy-load dos leads ao mudar pra aba Leads.
  //
  // Bug histórico: usar `leadsPorCnpj` nas deps + guard "if (keys > 0) return"
  // causava loop infinito quando TODOS os requests falhavam (403, etc),
  // porque o map ficava {} e o guard nunca travava. Solução: ref booleana
  // que marca 'já tentei' independente do resultado.
  useEffect(() => {
    if (aba !== "LEADS" || !detalhe?.cnpjs?.length) return;
    if (leadsCarregados.current) return;
    leadsCarregados.current = true;

    setLoadingLeads(true);
    const cnpjs = detalhe.cnpjs.map((c) => c.cnpj_contador).filter(Boolean);

    Promise.all(
      cnpjs.map((cnpj) =>
        api.get("/clientes/contador-leads", { params: { cnpj } })
          .then((r) => [cnpj, r.data])
          .catch((e) => [cnpj, { _erro: true, status: e?.response?.status }])
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
  }, [aba, detalhe]);

  // Agrega só os CNPJs que tiveram resposta OK
  const leadsAgregados = useMemo(() => {
    const out = [];
    for (const [cnpj, data] of Object.entries(leadsPorCnpj)) {
      if (data?._erro) continue;
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

  // Patch 7: leads filtrados conforme o card clicado
  const leadsFiltrados = useMemo(() => {
    if (!filtroStatus) return leadsAgregados;
    return leadsAgregados.filter(
      (l) => (l.status || "").toLowerCase() === filtroStatus
    );
  }, [leadsAgregados, filtroStatus]);

  const kpisLeads = useMemo(() => {
    const k = { total: 0, em_andamento: 0, conquistado: 0, perdido: 0 };
    for (const data of Object.values(leadsPorCnpj)) {
      if (data?._erro) continue;
      k.total += data.kpis?.total || 0;
      k.em_andamento += data.kpis?.em_andamento || 0;
      k.conquistado += data.kpis?.conquistado || 0;
      k.perdido += data.kpis?.perdido || 0;
    }
    return k;
  }, [leadsPorCnpj]);

  // Detecta o caso "todas as chamadas falharam por permissão" pra mostrar
  // mensagem específica em vez do estado vazio genérico.
  const todosForbidden = useMemo(() => {
    const vals = Object.values(leadsPorCnpj);
    if (!vals.length) return false;
    return vals.every((d) => d?._erro && d?.status === 403);
  }, [leadsPorCnpj]);

  if (!idGrupo) return null;

  // Patch 7: toggle de filtro. Click no card já ativo → limpa.
  function toggleFiltro(status) {
    setFiltroStatus((atual) => (atual === status ? null : status));
  }

  // Acordeao: abre/fecha tarefas de um lead. Lazy fetch via /clientes/oportunidades/{op_id}.
  async function toggleLead(opId) {
    if (!opId) return;
    if (leadExpandido === opId) {
      setLeadExpandido(null);
      return;
    }
    setLeadExpandido(opId);
    if (tarefasPorOp[opId]?.tarefas) return;
    setTarefasPorOp((atual) => ({
      ...atual,
      [opId]: { loading: true, tarefas: null, erro: null },
    }));
    try {
      const { data } = await api.get(`/clientes/oportunidades/${opId}`);
      setTarefasPorOp((atual) => ({
        ...atual,
        [opId]: { loading: false, tarefas: data.tarefas || [], erro: null },
      }));
    } catch (e) {
      setTarefasPorOp((atual) => ({
        ...atual,
        [opId]: {
          loading: false,
          tarefas: null,
          erro: e.response?.data?.detail || e.message || "Erro ao carregar tarefas.",
        },
      }));
    }
  }

  function badgeSituacaoTarefa(s) {
    const v = (s || "").toLowerCase();
    if (v === "atrasada") return "bg-hipo-dangerSoft text-hipo-danger border-hipo-dangerBorder";
    if (v === "em dia")   return "bg-hipo-successSoft text-hipo-success border-hipo-successBorder";
    if (v === "futura")   return "bg-hipo-blueSoft text-hipo-blue border-hipo-blueSoft";
    return "bg-hipo-bg text-hipo-muted border-hipo-border";
  }

  // Helper: classes do KPI card considerando estado de seleção.
  // Card ativo = borda azul espessa + opacidade 100%.
  // Outros cards quando há filtro = opacidade 50% pra atenuar visualmente.
  // Sem filtro = todos os cards normais.
  function classesKpiCard(statusDoCard, classesBase) {
    const algumAtivo = filtroStatus !== null;
    const ehEsteAtivo = filtroStatus === statusDoCard;

    if (!algumAtivo) {
      // Sem filtro: todos normais, com hover sutil pra indicar clicabilidade
      return `${classesBase} hover:ring-2 hover:ring-hipo-blue/30 transition-all`;
    }
    if (ehEsteAtivo) {
      // Este card é o filtro ativo: borda azul espessa
      return `${classesBase} ring-2 ring-hipo-blue opacity-100 transition-all`;
    }
    // Outro card é o ativo: este fica atenuado
    return `${classesBase} opacity-50 hover:opacity-80 transition-all`;
  }


  return (
    <div className="fixed inset-0 z-40 flex" onClick={onFechar}>
      <div className="flex-1 bg-hipo-ink/40" />
      <aside
        className="w-full max-w-4xl bg-hipo-card border-l border-hipo-border overflow-y-auto"
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
            <p className="text-sm text-hipo-danger bg-hipo-dangerSoft border border-hipo-dangerBorder rounded-lg p-3">
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
                    ) : todosForbidden ? (
                      <div className="text-center py-8" data-testid="leads-forbidden">
                        <AlertTriangle size={32} className="mx-auto text-hipo-danger mb-2" />
                        <p className="text-sm text-hipo-danger font-medium">
                          Sem permissão para ver os leads.
                        </p>
                        <p className="text-xs text-hipo-muted mt-1">
                          Peça acesso ao módulo Clientes para o ADM.
                        </p>
                      </div>
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
                        {/* Mini-KPIs clicáveis (patch 7) */}
                        <div className="grid grid-cols-4 gap-2 mb-4">
                          {/* Card Total — funciona como "limpar filtro" */}
                          <button
                            type="button"
                            onClick={() => setFiltroStatus(null)}
                            className={classesKpiCard(
                              null,
                              "bg-hipo-bg border border-hipo-border rounded-lg p-2 text-center cursor-pointer"
                            )}
                            aria-pressed={filtroStatus === null}
                            title="Mostrar todos"
                          >
                            <p className="text-xs text-hipo-slate">Total</p>
                            <p className="text-lg font-semibold text-hipo-ink">{kpisLeads.total}</p>
                          </button>

                          <button
                            type="button"
                            onClick={() => toggleFiltro("ativo")}
                            className={classesKpiCard(
                              "ativo",
                              "bg-hipo-blueSoft border border-hipo-blueSoft rounded-lg p-2 text-center cursor-pointer"
                            )}
                            aria-pressed={filtroStatus === "ativo"}
                            title="Filtrar leads em andamento"
                          >
                            <p className="text-xs text-hipo-blue">Em andamento</p>
                            <p className="text-lg font-semibold text-hipo-blue">{kpisLeads.em_andamento}</p>
                          </button>

                          <button
                            type="button"
                            onClick={() => toggleFiltro("conquistado")}
                            className={classesKpiCard(
                              "conquistado",
                              "bg-hipo-successSoft border border-hipo-successBorder rounded-lg p-2 text-center cursor-pointer"
                            )}
                            aria-pressed={filtroStatus === "conquistado"}
                            title="Filtrar leads conquistados"
                          >
                            <p className="text-xs text-hipo-success">Conquistado</p>
                            <p className="text-lg font-semibold text-hipo-success">{kpisLeads.conquistado}</p>
                          </button>

                          <button
                            type="button"
                            onClick={() => toggleFiltro("perdido")}
                            className={classesKpiCard(
                              "perdido",
                              "bg-hipo-dangerSoft border border-hipo-dangerBorder rounded-lg p-2 text-center cursor-pointer"
                            )}
                            aria-pressed={filtroStatus === "perdido"}
                            title="Filtrar leads perdidos"
                          >
                            <p className="text-xs text-hipo-danger">Perdido</p>
                            <p className="text-lg font-semibold text-hipo-danger">{kpisLeads.perdido}</p>
                          </button>
                        </div>

                        {/* Tabela de leads */}
                        <div className="bg-hipo-card border border-hipo-border rounded-lg overflow-hidden">
                          <table className="w-full text-xs">
                            <thead>
                              <tr className="text-hipo-slate border-b border-hipo-border text-left">
                                <th className="px-2 py-2 font-medium w-6"></th>
                                <th className="px-3 py-2 font-medium">Razão Social</th>
                                <th className="px-3 py-2 font-medium">Fase</th>
                                <th className="px-3 py-2 font-medium">Status</th>
                                <th className="px-3 py-2 font-medium">Executivo</th>
                                <th className="px-3 py-2 font-medium text-center">Temperatura</th>
                                <th className="px-3 py-2 font-medium text-right">Proposta NMRR</th>
                                <th className="px-3 py-2 font-medium text-right">Dias</th>
                              </tr>
                            </thead>
                            <tbody className="divide-y divide-hipo-border">
                              {leadsFiltrados.slice(0, 50).map((l) => {
                                const aberto = leadExpandido === l.op_id;
                                const cache = tarefasPorOp[l.op_id];
                                return (
                                  <Fragment key={l.op_id}>
                                    <tr
                                      onClick={() => toggleLead(l.op_id)}
                                      className={`hover:bg-hipo-bg cursor-pointer ${aberto ? "bg-hipo-blueSoft hover:bg-hipo-blueSoft" : ""}`}
                                    >
                                      <td className="px-2 py-2 text-hipo-muted">
                                        {aberto ? <ChevronDown size={14} /> : <ChevronRight size={14} />}
                                      </td>
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
                                      <td
                                        className="px-3 py-2 text-hipo-slate truncate max-w-[140px]"
                                        title={l.executivo_vendas || ""}
                                      >
                                        {l.executivo_vendas || "—"}
                                      </td>
                                      <td className="px-3 py-2 text-center">
                                        <span
                                          className={`text-[10px] tracking-wider px-2 py-0.5 rounded-full border ${badgeTemperatura(l.temperatura)}`}
                                          title={l.temperatura != null ? `Temperatura: ${l.temperatura}` : ""}
                                        >
                                          {fmtTemperatura(l.temperatura)}
                                        </span>
                                      </td>
                                      <td className="px-3 py-2 text-right text-hipo-ink whitespace-nowrap">
                                        {fmtMoeda(l.proposta_nmrr)}
                                      </td>
                                      <td className="px-3 py-2 text-right text-hipo-slate whitespace-nowrap">
                                        {l.dias_parado != null ? `${l.dias_parado}d` : "—"}
                                      </td>
                                    </tr>
                                    {aberto && (
                                      <tr className="bg-hipo-bg">
                                        <td colSpan={8} className="px-4 py-3">
                                          {cache?.loading && (
                                            <p className="text-xs text-hipo-slate italic">Carregando tarefas...</p>
                                          )}
                                          {cache?.erro && (
                                            <p className="text-xs text-hipo-danger">{cache.erro}</p>
                                          )}
                                          {cache?.tarefas && cache.tarefas.length === 0 && (
                                            <p className="text-xs text-hipo-slate italic">Nenhuma tarefa registrada para este lead.</p>
                                          )}
                                          {cache?.tarefas && cache.tarefas.length > 0 && (
                                            <div className="bg-hipo-card border border-hipo-border rounded-md overflow-hidden">
                                              <table className="w-full text-xs">
                                                <thead>
                                                  <tr className="text-hipo-slate border-b border-hipo-border text-left">
                                                    <th className="px-3 py-1.5 font-medium">Data</th>
                                                    <th className="px-3 py-1.5 font-medium">Canal</th>
                                                    <th className="px-3 py-1.5 font-medium">Finalidade</th>
                                                    <th className="px-3 py-1.5 font-medium">Situação</th>
                                                    <th className="px-3 py-1.5 font-medium">Resultado</th>
                                                    <th className="px-3 py-1.5 font-medium">Executivo</th>
                                                  </tr>
                                                </thead>
                                                <tbody className="divide-y divide-hipo-border">
                                                  {cache.tarefas.map((t) => (
                                                    <tr key={t.tarefa_id} className="hover:bg-hipo-bg/60">
                                                      <td className="px-3 py-1.5 text-hipo-ink whitespace-nowrap">{fmtDate(t.data_agendamento)}</td>
                                                      <td className="px-3 py-1.5 text-hipo-slate">{t.canal || "—"}</td>
                                                      <td className="px-3 py-1.5 text-hipo-slate">{t.finalidade || "—"}</td>
                                                      <td className="px-3 py-1.5">
                                                        <span className={`text-[10px] tracking-wider px-2 py-0.5 rounded-full border ${badgeSituacaoTarefa(t.situacao_tarefa)}`}>
                                                          {(t.situacao_tarefa || "—").toUpperCase()}
                                                        </span>
                                                      </td>
                                                      <td className="px-3 py-1.5 text-hipo-slate">{t.resultado || "—"}</td>
                                                      <td className="px-3 py-1.5 text-hipo-slate">{t.usuario_atribuido || "—"}</td>
                                                    </tr>
                                                  ))}
                                                </tbody>
                                              </table>
                                            </div>
                                          )}
                                        </td>
                                      </tr>
                                    )}
                                  </Fragment>
                                );
                              })}
                            </tbody>
                          </table>
                          {/* Rodapé: contador adaptado ao filtro */}
                          {leadsFiltrados.length > 0 && (
                            <div className="px-3 py-2 text-xs text-hipo-muted bg-hipo-bg border-t border-hipo-border text-center">
                              {filtroStatus ? (
                                <>
                                  Mostrando {Math.min(leadsFiltrados.length, 50)} de {leadsFiltrados.length} leads
                                  {' '}<span className="text-hipo-blue font-medium">(filtrado por {FILTRO_LABELS[filtroStatus]})</span>
                                </>
                              ) : leadsFiltrados.length > 50 ? (
                                <>
                                  Mostrando 50 de {leadsFiltrados.length} leads. Veja todos em <strong>Clientes</strong>.
                                </>
                              ) : (
                                <>Mostrando {leadsFiltrados.length} {leadsFiltrados.length === 1 ? 'lead' : 'leads'}.</>
                              )}
                            </div>
                          )}
                          {/* Estado vazio do filtro: existe lead, mas nenhum bate com filtro */}
                          {leadsFiltrados.length === 0 && (
                            <div className="px-3 py-6 text-xs text-hipo-muted bg-hipo-bg text-center">
                              Nenhum lead {filtroStatus ? `com status "${FILTRO_LABELS[filtroStatus]}"` : ''} encontrado.
                              {filtroStatus && (
                                <button
                                  type="button"
                                  onClick={() => setFiltroStatus(null)}
                                  className="ml-2 text-hipo-blue hover:underline"
                                >
                                  Limpar filtro
                                </button>
                              )}
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
