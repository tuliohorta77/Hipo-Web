// web/src/components/BastaoLista.jsx
//
// Sub-aba "Relacionamento" do Hunter expandido (v1.2.0 etapa 5.2).
//
// Mostra a VISAO FARMER dos contadores que o Hunter passou via bastao
// aprovado — a mesma UI da aba Farmer de Contadores (tabela de grupos com
// timeline semanal, atrasadas, futuras, leads, funil + drilldown), porem
// filtrada apenas aos grupos cujos CNPJs vieram de bastao aprovado deste
// Hunter.
//
// Como funciona o cruzamento (Estrategia A' — sem endpoint dedicado):
//   1. GET /carteira/bastoes/meus?hunter=X  → bastoes do Hunter
//   2. GET /carteira/dashboard/farmer       → todas as linhas Farmer; cada
//      linha traz grupos[] embutidos, e cada grupo agora tem cnpjs[] (5.1)
//   3. Monta o Set de CNPJs com bastao APROVADO e filtra os grupos do
//      dashboard Farmer: fica so quem tem >=1 CNPJ nesse Set.
//   4. Renderiza DrilldownTabela aba="EC_FARMER" com esses grupos.
//
// O bastao em si deixa de ser linha de tabela — vira contexto. KPIs do
// topo passam a ser estilo Farmer (grupos, atrasadas, futuras, leads).
// Contadores com bastao aprovado que ainda nao aparecem em nenhum grupo
// Farmer (nao atribuidos na carteira / CROmie desatualizado) entram num
// aviso discreto, nao somem silenciosamente.

import { useCallback, useEffect, useMemo, useState } from "react";
import { Plus, RefreshCw, Users, AlertTriangle, Clock, Inbox } from "lucide-react";
import api from "../api";
import Button from "./ui/Button";
import KpiCard from "./ui/KpiCard";
import Empty from "./ui/Empty";
import AlertMessage from "./ui/AlertMessage";
import BastaoModal from "./BastaoModal";
import CarteiraGrupoDrawer from "./CarteiraGrupoDrawer";
import DrilldownTabela from "./DrilldownTabela";


// ── Normalizacao de CNPJ ──────────────────────────────────────────────────
// Os bastoes guardam cnpj_contador com mascara (08.279.542/0001-57). O grupo
// do dashboard expoe cnpjs[] tambem com mascara (vem da mesma coluna
// carteira_cnpj.cnpj_contador). Mesmo assim normalizamos pra so digitos nos
// dois lados — blinda contra divergencia de mascara/espaco.
function soDigitos(cnpj) {
  return (cnpj || "").replace(/\D/g, "");
}


// ── Componente ────────────────────────────────────────────────────────────

export default function BastaoLista({
  hunterNome,
  farmersDisponiveis = [],
}) {
  const [bastoes, setBastoes] = useState([]);
  const [linhasFarmer, setLinhasFarmer] = useState([]);
  const [funilPorGrupo, setFunilPorGrupo] = useState({});
  const [loading, setLoading] = useState(false);
  const [erro, setErro] = useState(null);

  const [modalAberto, setModalAberto] = useState(false);
  const [drawerGrupo, setDrawerGrupo] = useState(null);

  // Filtros locais do DrilldownTabela (mesma forma usada em Contadores.jsx)
  const [filtros, setFiltros] = useState({
    tarefa_atrasada: false,
    sem_tarefa_futura: false,
    busca_grupo: "",
  });

  // ── Carregar dados ──────────────────────────────────────────────────────

  const carregar = useCallback(async () => {
    setLoading(true);
    setErro(null);
    try {
      const [resBastoes, resFarmer] = await Promise.all([
        api.get("/carteira/bastoes/meus", { params: { hunter: hunterNome } }),
        api.get("/carteira/dashboard/farmer"),
      ]);
      setBastoes(resBastoes.data || []);
      setLinhasFarmer(resFarmer.data?.linhas || []);
    } catch (e) {
      setErro(
        e.response?.data?.detail || e.message || "Erro ao carregar relacionamento."
      );
      setBastoes([]);
      setLinhasFarmer([]);
    } finally {
      setLoading(false);
    }
  }, [hunterNome]);

  useEffect(() => {
    carregar();
  }, [carregar]);

  // ── Cruzamento bastao ↔ grupo ───────────────────────────────────────────

  // Set de CNPJs (so digitos) com bastao APROVADO deste Hunter.
  const cnpjsAprovados = useMemo(() => {
    const s = new Set();
    for (const b of bastoes) {
      if (b.status === "APROVADO") {
        const d = soDigitos(b.cnpj_contador);
        if (d) s.add(d);
      }
    }
    return s;
  }, [bastoes]);

  // Grupos do dashboard Farmer que tem >=1 CNPJ no Set de aprovados.
  // Cada grupo ja vem com timeline, atrasadas, futuras, leads, cnpjs[].
  const gruposViaBastao = useMemo(() => {
    if (cnpjsAprovados.size === 0) return [];
    const vistos = new Set();
    const out = [];
    for (const linha of linhasFarmer) {
      for (const g of linha.grupos || []) {
        if (vistos.has(g.id_grupo)) continue;
        const cnpjsDoGrupo = (g.cnpjs || []).map(soDigitos);
        const casa = cnpjsDoGrupo.some((c) => cnpjsAprovados.has(c));
        if (casa) {
          vistos.add(g.id_grupo);
          // Anexa o nome do Farmer responsavel (vem da linha, nao do grupo)
          out.push({ ...g, _farmer_nome: linha.nome });
        }
      }
    }
    return out;
  }, [linhasFarmer, cnpjsAprovados]);

  // CNPJs aprovados que NAO casaram com nenhum grupo Farmer — contadores
  // que ainda nao aparecem na carteira. Avisamos sem esconder.
  const cnpjsSemGrupo = useMemo(() => {
    if (cnpjsAprovados.size === 0) return [];
    const cnpjsComGrupo = new Set();
    for (const g of gruposViaBastao) {
      for (const c of g.cnpjs || []) cnpjsComGrupo.add(soDigitos(c));
    }
    // Lista os bastoes aprovados cujo CNPJ nao apareceu em grupo nenhum
    return bastoes.filter(
      (b) =>
        b.status === "APROVADO" &&
        !cnpjsComGrupo.has(soDigitos(b.cnpj_contador))
    );
  }, [bastoes, gruposViaBastao, cnpjsAprovados]);

  // Bastoes ainda pendentes de aprovacao — contam num aviso, nao na tabela.
  const pendentes = useMemo(
    () => bastoes.filter((b) => b.status === "PENDENTE"),
    [bastoes]
  );

  // Historico: rejeitados e removidos.
  const historico = useMemo(
    () => bastoes.filter((b) => ["REJEITADO", "REMOVIDO"].includes(b.status)),
    [bastoes]
  );

  // ── KPIs estilo Farmer (agregados dos grupos via bastao) ────────────────

  const kpis = useMemo(() => {
    const totalGrupos = gruposViaBastao.length;
    const comAtrasada = gruposViaBastao.filter(
      (g) => (g.tarefas_atrasadas || 0) > 0
    ).length;
    const comFutura = gruposViaBastao.filter(
      (g) => (g.tarefas_futuras || 0) > 0
    ).length;
    const leads = gruposViaBastao.reduce(
      (acc, g) => acc + (g.leads_no_mes || 0),
      0
    );
    return { totalGrupos, comAtrasada, comFutura, leads };
  }, [gruposViaBastao]);

  // ── Funil dos grupos (lazy, igual Contadores.jsx) ───────────────────────

  useEffect(() => {
    const idGrupos = gruposViaBastao
      .map((g) => g.id_grupo)
      .filter(Boolean)
      .filter((gid) => !funilPorGrupo[gid]);
    if (idGrupos.length === 0) return;

    let cancelado = false;
    api
      .post("/clientes/funil-por-grupos", { id_grupos: idGrupos })
      .then(({ data }) => {
        if (cancelado) return;
        setFunilPorGrupo((atual) => ({ ...atual, ...(data.por_grupo || {}) }));
      })
      .catch((e) => {
        if (!cancelado) console.error("Funil (Relacionamento):", e);
      });
    return () => {
      cancelado = true;
    };
  }, [gruposViaBastao, funilPorGrupo]);

  // ── Filtro local do drilldown ───────────────────────────────────────────

  function aplicarFiltros(grupos) {
    let out = grupos;
    if (filtros.tarefa_atrasada) {
      out = out.filter((g) => g.tarefas_atrasadas > 0);
    }
    if (filtros.sem_tarefa_futura) {
      out = out.filter((g) => g.tarefas_futuras === 0);
    }
    const q = filtros.busca_grupo.trim().toLowerCase();
    if (q) {
      out = out.filter(
        (g) =>
          (g.nome_grupo || "").toLowerCase().includes(q) ||
          (g.contabilidade_principal || "").toLowerCase().includes(q)
      );
    }
    return out;
  }

  const gruposFiltrados = useMemo(
    () => aplicarFiltros(gruposViaBastao),
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [gruposViaBastao, filtros]
  );

  // ── Render ──────────────────────────────────────────────────────────────

  return (
    <div className="space-y-4">
      {/* Header: KPIs estilo Farmer + acoes */}
      <div className="flex items-start justify-between gap-3 flex-wrap">
        <div className="grid grid-cols-2 md:grid-cols-4 gap-2 flex-1 min-w-[420px]">
          <KpiCard
            label="Contadores via bastao"
            value={loading ? "—" : kpis.totalGrupos.toLocaleString("pt-BR")}
            icon={Users}
            tone="success"
          />
          <KpiCard
            label="Com tarefa atrasada"
            value={loading ? "—" : kpis.comAtrasada.toLocaleString("pt-BR")}
            icon={AlertTriangle}
            tone={kpis.comAtrasada > 0 ? "danger" : "slate"}
          />
          <KpiCard
            label="Com tarefa futura"
            value={loading ? "—" : kpis.comFutura.toLocaleString("pt-BR")}
            icon={Clock}
            tone="blue"
          />
          <KpiCard
            label="Leads no mes"
            value={loading ? "—" : kpis.leads.toLocaleString("pt-BR")}
            icon={Inbox}
            tone="blue"
          />
        </div>
        <div className="flex gap-2">
          <Button
            variant="ghost"
            icon={RefreshCw}
            onClick={carregar}
            disabled={loading}
          >
            Atualizar
          </Button>
          <Button icon={Plus} onClick={() => setModalAberto(true)}>
            Passar contador
          </Button>
        </div>
      </div>

      {erro && <AlertMessage tipo="erro">{erro}</AlertMessage>}

      {/* Aviso: bastoes pendentes de aprovacao */}
      {pendentes.length > 0 && (
        <AlertMessage tipo="info">
          {pendentes.length === 1
            ? "1 contador aguardando aprovacao do Gerente/Franqueado — aparece aqui assim que for aprovado."
            : `${pendentes.length} contadores aguardando aprovacao do Gerente/Franqueado — aparecem aqui assim que forem aprovados.`}
        </AlertMessage>
      )}

      {/* Aviso: bastoes aprovados sem grupo na carteira */}
      {cnpjsSemGrupo.length > 0 && (
        <AlertMessage tipo="aviso">
          {cnpjsSemGrupo.length === 1
            ? "1 contador aprovado ainda nao aparece na carteira do Farmer "
            : `${cnpjsSemGrupo.length} contadores aprovados ainda nao aparecem na carteira do Farmer `}
          (atribuicao pendente ou base CROmie desatualizada):{" "}
          <span className="font-mono text-xs">
            {cnpjsSemGrupo
              .map((b) => b.contabilidade || b.cnpj_contador)
              .join(", ")}
          </span>
        </AlertMessage>
      )}

      {/* Estado vazio total */}
      {!loading &&
        gruposViaBastao.length === 0 &&
        pendentes.length === 0 &&
        cnpjsSemGrupo.length === 0 &&
        historico.length === 0 && (
          <Empty
            title="Nenhum bastao registrado"
            description="Quando voce fechar parceria com um contador (Termo + 2 leads), clique em 'Passar contador' pra entregar pro Farmer. Apos a aprovacao, a performance do Farmer com esse contador aparece aqui."
          />
        )}

      {/* Tabela Farmer dos contadores via bastao */}
      {gruposViaBastao.length > 0 && (
        <DrilldownTabela
          aba="EC_FARMER"
          grupos={gruposFiltrados}
          totalSemFiltro={gruposViaBastao.length}
          funilPorGrupo={funilPorGrupo}
          filtros={filtros}
          onFiltros={setFiltros}
          onAbrirGrupo={(g) =>
            setDrawerGrupo({
              id_grupo: g.id_grupo,
              nome_grupo: g.nome_grupo,
            })
          }
        />
      )}

      {/* Historico (rejeitados/removidos) — discreto, colapsavel */}
      {historico.length > 0 && (
        <details className="group">
          <summary className="cursor-pointer text-xs font-semibold text-hipo-slate tracking-wider uppercase hover:text-hipo-ink">
            Historico ({historico.length}) — rejeitados e removidos
          </summary>
          <ul className="mt-2 space-y-1.5 text-xs">
            {historico.map((b) => (
              <li
                key={b.id}
                className="flex items-center gap-2 text-hipo-slate"
              >
                <span
                  className={`inline-block px-1.5 py-0.5 rounded-full text-[10px] font-medium ${
                    b.status === "REJEITADO"
                      ? "bg-hipo-dangerSoft text-hipo-danger"
                      : "bg-hipo-bg text-hipo-slate"
                  }`}
                >
                  {b.status}
                </span>
                <span className="text-hipo-ink">
                  {b.contabilidade || b.cnpj_contador}
                </span>
                {b.status === "REJEITADO" && b.motivo_rejeicao && (
                  <span className="text-hipo-muted">— {b.motivo_rejeicao}</span>
                )}
              </li>
            ))}
          </ul>
        </details>
      )}

      {/* Modal de inclusao */}
      <BastaoModal
        aberto={modalAberto}
        onFechar={() => setModalAberto(false)}
        farmersDisponiveis={farmersDisponiveis}
        onSucesso={carregar}
      />

      {/* Drilldown drawer — abre ao clicar num grupo */}
      {drawerGrupo && (
        <CarteiraGrupoDrawer
          idGrupo={drawerGrupo.id_grupo}
          nomeGrupo={drawerGrupo.nome_grupo}
          onFechar={() => setDrawerGrupo(null)}
        />
      )}
    </div>
  );
}
