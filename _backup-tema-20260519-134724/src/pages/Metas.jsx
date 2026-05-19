// web/src/pages/Metas.jsx
import { useEffect, useMemo, useState } from "react";
import { Save, Calendar, Target, Info } from "lucide-react";
import api, { getUser } from "../api";

const PILARES = [
  { codigo: "RESULTADO", label: "Pilar Resultado", cor: "text-cyan-400", pts: 60 },
  { codigo: "GESTAO", label: "Pilar Gestão", cor: "text-yellow-400", pts: 20 },
  { codigo: "ENGAJAMENTO", label: "Pilar Engajamento", cor: "text-emerald-400", pts: 20 },
];

function mesRefAtual() {
  const d = new Date();
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}`;
}

function nomeMes(ref) {
  const [y, m] = ref.split("-");
  const meses = ["jan", "fev", "mar", "abr", "mai", "jun", "jul", "ago", "set", "out", "nov", "dez"];
  return `${meses[parseInt(m, 10) - 1]}/${y.slice(2)}`;
}

function gerarOpcoesMes() {
  // 6 meses pra trás + atual + 6 meses à frente
  const opts = [];
  const hoje = new Date();
  for (let delta = -6; delta <= 6; delta++) {
    const d = new Date(hoje.getFullYear(), hoje.getMonth() + delta, 1);
    const ref = `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}`;
    opts.push({ ref, label: nomeMes(ref) });
  }
  return opts;
}

export default function Metas() {
  const user = getUser();
  const isAdm = (user?.cargo || "").toUpperCase() === "ADM";

  const [mesRef, setMesRef] = useState(mesRefAtual());
  const [catalogo, setCatalogo] = useState({ clusters: [], indicadores: [] });
  const [meta, setMeta] = useState(null);  // dados do mês selecionado
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [msg, setMsg] = useState(null);

  // Carrega catálogo (1x)
  useEffect(() => {
    api.get("/metas/catalogo").then(({ data }) => setCatalogo(data));
  }, []);

  // Carrega mês selecionado
  useEffect(() => {
    setLoading(true);
    setMsg(null);
    api
      .get(`/metas/${mesRef}`)
      .then(({ data }) => setMeta(data))
      .catch(() => setMeta(null))
      .finally(() => setLoading(false));
  }, [mesRef]);

  // Indicadores editáveis (do catálogo)
  const indicadoresEditaveis = useMemo(
    () => catalogo.indicadores.filter((i) => i.meta_editavel),
    [catalogo]
  );

  // Map código → meta_valor
  const metasMap = useMemo(() => {
    const m = {};
    if (meta?.indicadores) for (const ind of meta.indicadores) m[ind.codigo] = ind.meta_valor;
    return m;
  }, [meta]);

  // Big3: garante 3 ações sempre presentes
  const big3 = useMemo(() => {
    const arr = (meta?.big3 || []).slice();
    while (arr.length < 3) arr.push({ ordem: arr.length + 1, descricao: "", atingiu: false });
    return arr.sort((a, b) => a.ordem - b.ordem);
  }, [meta]);

  // Atualizadores
  const setCab = (key, value) => setMeta((prev) => ({ ...prev, [key]: value }));
  const setMetaInd = (codigo, value) => {
    setMeta((prev) => {
      const inds = (prev?.indicadores || []).filter((i) => i.codigo !== codigo);
      const novo = value === "" || value === null ? null : Number(value);
      if (novo !== null && !isNaN(novo)) inds.push({ codigo, meta_valor: novo });
      return { ...prev, indicadores: inds };
    });
  };
  const setBig3Campo = (ordem, key, value) => {
    setMeta((prev) => {
      const arr = (prev?.big3 || []).slice();
      const idx = arr.findIndex((b) => b.ordem === ordem);
      if (idx === -1) arr.push({ ordem, descricao: "", atingiu: false, [key]: value });
      else arr[idx] = { ...arr[idx], [key]: value };
      return { ...prev, big3: arr.sort((a, b) => a.ordem - b.ordem) };
    });
  };

  async function salvar() {
    if (!isAdm) return;
    setSaving(true);
    setMsg(null);
    try {
      // Garante big3 com 3 entradas (preenche descrições vazias se faltar)
      const big3Final = [1, 2, 3].map((ord) => {
        const existente = (meta.big3 || []).find((b) => b.ordem === ord);
        return existente || { ordem: ord, descricao: "", atingiu: false };
      });
      const payload = {
        mes_ref: mesRef,
        cluster_unidade: meta.cluster_unidade || "BASE",
        dias_uteis: Number(meta.dias_uteis) || 22,
        ecs_ativos_m3: Number(meta.ecs_ativos_m3) || 0,
        evs_ativos: Number(meta.evs_ativos) || 0,
        carteira_total_contadores: Number(meta.carteira_total_contadores) || 0,
        apps_ativos: Number(meta.apps_ativos) || 0,
        headcount_recomendado:
          meta.headcount_recomendado != null && meta.headcount_recomendado !== ""
            ? Number(meta.headcount_recomendado)
            : null,
        indicadores: (meta.indicadores || []).filter((i) => i.meta_valor != null),
        big3: big3Final,
      };
      await api.post(`/metas/${mesRef}`, payload);
      setMsg({ tipo: "ok", texto: "✅ Metas salvas com sucesso." });
      // Recarrega pra ver os valores derivados de cluster
      const { data } = await api.get(`/metas/${mesRef}`);
      setMeta(data);
    } catch (err) {
      setMsg({ tipo: "erro", texto: `Erro: ${err.response?.data?.detail || err.message}` });
    } finally {
      setSaving(false);
    }
  }

  const opcoesMes = gerarOpcoesMes();

  return (
    <div className="p-6 max-w-6xl mx-auto">
      {/* Header */}
      <div className="flex items-center justify-between mb-6">
        <div>
          <h1 className="text-xl font-bold text-slate-100 tracking-wide flex items-center gap-2">
            <Target size={20} className="text-cyan-400" />
            Metas PEX
          </h1>
          <p className="text-xs text-slate-500 mt-0.5">
            Cadastro mensal de metas — configuração da unidade e indicadores variáveis
          </p>
        </div>
        <div className="flex items-center gap-3">
          <select
            value={mesRef}
            onChange={(e) => setMesRef(e.target.value)}
            className="bg-slate-900 border border-slate-700 rounded-lg px-3 py-2 text-sm text-slate-200"
          >
            {opcoesMes.map((o) => (
              <option key={o.ref} value={o.ref}>
                {o.label}
              </option>
            ))}
          </select>
          {isAdm && (
            <button
              onClick={salvar}
              disabled={saving || loading || !meta}
              className="flex items-center gap-2 px-4 py-2 rounded-lg text-sm font-bold bg-cyan-600 hover:bg-cyan-500 disabled:bg-slate-700 disabled:text-slate-400 text-white transition-all"
            >
              <Save size={15} />
              {saving ? "Salvando..." : "Salvar"}
            </button>
          )}
        </div>
      </div>

      {/* Aviso ADM-only */}
      {!isAdm && (
        <div className="mb-4 px-4 py-3 rounded-lg text-sm bg-amber-500/10 text-amber-400 border border-amber-500/30">
          Apenas usuários ADM podem editar metas. Você está em modo somente leitura.
        </div>
      )}

      {/* Status */}
      {meta?.pre_populado && !meta.existente && (
        <div className="mb-4 px-4 py-3 rounded-lg text-sm bg-cyan-500/10 text-cyan-400 border border-cyan-500/30 flex items-center gap-2">
          <Info size={14} />
          Mês ainda não cadastrado. Valores pré-populados a partir do último mês existente.
          Clique em <b>Salvar</b> para confirmar.
        </div>
      )}
      {meta?.existente && meta?.atualizado_em && (
        <div className="mb-4 px-4 py-3 rounded-lg text-sm bg-slate-800/50 text-slate-400 border border-slate-700 flex items-center gap-2">
          <Calendar size={14} />
          Última atualização: {new Date(meta.atualizado_em).toLocaleString("pt-BR")}
        </div>
      )}
      {msg && (
        <div
          className={`mb-4 px-4 py-3 rounded-lg text-sm ${
            msg.tipo === "ok"
              ? "bg-emerald-500/10 text-emerald-400 border border-emerald-500/30"
              : "bg-red-500/10 text-red-400 border border-red-500/30"
          }`}
        >
          {msg.texto}
        </div>
      )}

      {loading || !meta ? (
        <div className="text-center text-slate-500 py-12">Carregando...</div>
      ) : (
        <>
          {/* Header da configuração do mês */}
          <Section title="CONFIGURAÇÃO DA UNIDADE">
            <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
              <Field label="Cluster">
                <select
                  value={meta.cluster_unidade || "BASE"}
                  onChange={(e) => setCab("cluster_unidade", e.target.value)}
                  disabled={!isAdm}
                  className="input-base"
                >
                  {(catalogo.clusters || []).map((c) => (
                    <option key={c} value={c}>
                      {c.replace("_", " ")}
                    </option>
                  ))}
                </select>
              </Field>
              <Field label="Dias úteis">
                <input
                  type="number"
                  value={meta.dias_uteis ?? ""}
                  onChange={(e) => setCab("dias_uteis", e.target.value)}
                  disabled={!isAdm}
                  className="input-base"
                />
              </Field>
              <Field label="ECs ativos M3">
                <input
                  type="number"
                  value={meta.ecs_ativos_m3 ?? ""}
                  onChange={(e) => setCab("ecs_ativos_m3", e.target.value)}
                  disabled={!isAdm}
                  className="input-base"
                />
              </Field>
              <Field label="EVs ativos">
                <input
                  type="number"
                  value={meta.evs_ativos ?? ""}
                  onChange={(e) => setCab("evs_ativos", e.target.value)}
                  disabled={!isAdm}
                  className="input-base"
                />
              </Field>
              <Field label="Carteira contadores">
                <input
                  type="number"
                  value={meta.carteira_total_contadores ?? ""}
                  onChange={(e) => setCab("carteira_total_contadores", e.target.value)}
                  disabled={!isAdm}
                  className="input-base"
                />
              </Field>
              <Field label="Apps ativos (SoW)">
                <input
                  type="number"
                  value={meta.apps_ativos ?? ""}
                  onChange={(e) => setCab("apps_ativos", e.target.value)}
                  disabled={!isAdm}
                  className="input-base"
                />
              </Field>
              <Field label="Headcount alvo">
                <input
                  type="number"
                  value={meta.headcount_recomendado ?? ""}
                  onChange={(e) => setCab("headcount_recomendado", e.target.value)}
                  disabled={!isAdm}
                  className="input-base"
                />
              </Field>
            </div>
          </Section>

          {/* Indicadores editáveis agrupados por pilar */}
          {PILARES.map(({ codigo, label, cor, pts }) => {
            const inds = indicadoresEditaveis.filter((i) => i.pilar === codigo);
            if (inds.length === 0 && codigo !== "ENGAJAMENTO") return null;
            return (
              <Section key={codigo} title={`${label.toUpperCase()} — ${pts} PTS`} cor={cor}>
                {inds.length > 0 ? (
                  <div className="space-y-2">
                    {inds.map((ind) => (
                      <IndicadorRow
                        key={ind.codigo}
                        ind={ind}
                        valor={metasMap[ind.codigo]}
                        cluster={meta.cluster_unidade}
                        onChange={(v) => setMetaInd(ind.codigo, v)}
                        readOnly={!isAdm}
                      />
                    ))}
                  </div>
                ) : (
                  <p className="text-xs text-slate-500 italic">
                    Sem metas numéricas editáveis neste pilar (todas universais).
                  </p>
                )}

                {/* Big3 só aparece em Engajamento */}
                {codigo === "ENGAJAMENTO" && (
                  <div className="mt-4 pt-4 border-t border-slate-800">
                    <p className="text-xs font-bold text-slate-400 tracking-widest mb-3">
                      BIG 3 — AÇÕES MENSAIS (6 PTS)
                    </p>
                    <div className="space-y-2">
                      {big3.map((acao) => (
                        <div key={acao.ordem} className="flex items-center gap-3">
                          <span className="text-xs font-bold text-slate-500 w-12">
                            Ação {acao.ordem}
                          </span>
                          <input
                            type="text"
                            placeholder="Descrição da ação..."
                            value={acao.descricao || ""}
                            onChange={(e) => setBig3Campo(acao.ordem, "descricao", e.target.value)}
                            disabled={!isAdm}
                            className="input-base flex-1"
                          />
                          <label className="flex items-center gap-2 text-xs text-slate-400 whitespace-nowrap cursor-pointer">
                            <input
                              type="checkbox"
                              checked={!!acao.atingiu}
                              onChange={(e) => setBig3Campo(acao.ordem, "atingiu", e.target.checked)}
                              disabled={!isAdm}
                              className="w-4 h-4 accent-emerald-500"
                            />
                            Atingiu
                          </label>
                        </div>
                      ))}
                    </div>
                    <p className="text-xs text-slate-500 mt-2 italic">
                      2 pts por ação atingida (max 6 pts)
                    </p>
                  </div>
                )}
              </Section>
            );
          })}
        </>
      )}

      {/* Estilos do input — usados em vários campos */}
      <style>{`
        .input-base {
          width: 100%;
          background-color: rgb(15 23 42);
          border: 1px solid rgb(51 65 85);
          border-radius: 0.5rem;
          padding: 0.5rem 0.75rem;
          font-size: 0.875rem;
          color: rgb(226 232 240);
          font-family: ui-monospace, monospace;
        }
        .input-base:focus { outline: 2px solid rgb(8 145 178); outline-offset: -1px; }
        .input-base:disabled { opacity: 0.6; cursor: not-allowed; }
      `}</style>
    </div>
  );
}

// ─────────── Componentes auxiliares ───────────

function Section({ title, cor = "text-slate-400", children }) {
  return (
    <div className="bg-slate-900 border border-slate-800 rounded-xl p-5 mb-4">
      <h3 className={`text-xs font-bold ${cor} tracking-widest mb-4`}>{title}</h3>
      {children}
    </div>
  );
}

function Field({ label, children }) {
  return (
    <label className="flex flex-col gap-1">
      <span className="text-xs text-slate-500 tracking-wider">{label}</span>
      {children}
    </label>
  );
}

function IndicadorRow({ ind, valor, cluster, onChange, readOnly }) {
  const metaPorCluster = ind.meta_por_cluster?.[cluster];
  const placeholder = metaPorCluster ? `Auto: ${metaPorCluster}` : "";
  return (
    <div className="flex items-center gap-3 py-2 border-b border-slate-800/50 last:border-0">
      <div className="flex-1">
        <p className="text-sm text-slate-200">{ind.nome}</p>
        <p className="text-xs text-slate-500">
          {ind.pts} pts · {ind.meta_label}
          {metaPorCluster != null && (
            <span className="ml-2 text-cyan-500">→ {cluster}: {metaPorCluster}</span>
          )}
        </p>
      </div>
      <input
        type="number"
        step="any"
        value={valor ?? ""}
        onChange={(e) => onChange(e.target.value)}
        placeholder={placeholder}
        disabled={readOnly}
        className="input-base w-32 text-right"
      />
    </div>
  );
}
