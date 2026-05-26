// web/src/components/BastaoLista.jsx
//
// Sub-aba "Relacionamento" do Hunter expandido.
//
// v1.3.0 (etapa 2c): o cruzamento bastao <-> grupo Farmer agora e feito
// no BACKEND, pelo endpoint GET /carteira/relacionamento. Antes este
// componente baixava /carteira/dashboard/farmer inteiro e cruzava os
// CNPJs no JS — isso quebraria quando /dashboard/farmer passou a ser
// filtrado por usuario. Agora o backend entrega pronto:
//   - grupos: grupos Farmer dos contadores passados via bastao aprovado
//   - bastoes_sem_grupo: bastoes aprovados que ainda nao tem grupo
//   - kpis: total_grupos, com_atrasada, com_futura, leads
//
// Este componente ainda chama /carteira/bastoes/meus para obter os
// bastoes PENDENTES e o HISTORICO (rejeitados/removidos) — informacao
// que /relacionamento nao devolve por nao ser ligada a grupos.
//
// A lista de Farmers do BastaoModal vem de /carteira/colaboradores
// (nao filtrado) — todos os colaboradores EC_FARMER ativos.

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


export default function BastaoLista({ hunterNome }) {
  const [grupos, setGrupos] = useState([]);
  const [bastoesSemGrupo, setBastoesSemGrupo] = useState([]);
  const [kpis, setKpis] = useState({
    total_grupos: 0,
    com_atrasada: 0,
    com_futura: 0,
    leads: 0,
  });
  const [pendentes, setPendentes] = useState([]);
  const [historico, setHistorico] = useState([]);
  const [farmersDisponiveis, setFarmersDisponiveis] = useState([]);
  const [funilPorGrupo, setFunilPorGrupo] = useState({});
  const [loading, setLoading] = useState(false);
  const [erro, setErro] = useState(null);
  const [avisoSemVinculo, setAvisoSemVinculo] = useState(null);

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
      // /relacionamento  -> grupos via bastao (cruzamento ja feito no backend)
      // /bastoes/meus    -> pendentes + historico (rejeitados/removidos)
      // /colaboradores   -> lista de Farmers ativos para o modal de passagem
      const [resRel, resBastoes, resColab] = await Promise.all([
        api.get("/carteira/relacionamento", {
          params: hunterNome ? { hunter: hunterNome } : {},
        }),
        api.get("/carteira/bastoes/meus", {
          params: hunterNome ? { hunter: hunterNome } : {},
        }),
        api.get("/carteira/colaboradores"),
      ]);

      const rel = resRel.data || {};
      setGrupos(rel.grupos || []);
      setBastoesSemGrupo(rel.bastoes_sem_grupo || []);
      setKpis(
        rel.kpis || {
          total_grupos: 0,
          com_atrasada: 0,
          com_futura: 0,
          leads: 0,
        }
      );
      setAvisoSemVinculo(rel.aviso || null);

      const todosBastoes = resBastoes.data || [];
      setPendentes(todosBastoes.filter((b) => b.status === "PENDENTE"));
      setHistorico(
        todosBastoes.filter((b) =>
          ["REJEITADO", "REMOVIDO"].includes(b.status)
        )
      );

      const colaboradores = resColab.data || [];
      setFarmersDisponiveis(
        colaboradores
          .filter((c) => c.funcao === "EC_FARMER")
          .map((c) => c.nome)
      );
    } catch (e) {
      setErro(
        e.response?.data?.detail || e.message || "Erro ao carregar relacionamento."
      );
      setGrupos([]);
      setBastoesSemGrupo([]);
      setPendentes([]);
      setHistorico([]);
    } finally {
      setLoading(false);
    }
  }, [hunterNome]);

  useEffect(() => {
    carregar();
  }, [carregar]);

  // ── Funil dos grupos (lazy, igual Contadores.jsx) ───────────────────────

  useEffect(() => {
    const idGrupos = grupos
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
  }, [grupos, funilPorGrupo]);

  // ── Filtro local do drilldown ───────────────────────────────────────────

  const gruposFiltrados = useMemo(() => {
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
  }, [grupos, filtros]);

  // ── Render ──────────────────────────────────────────────────────────────

  // Operacional sem vinculo: o backend devolve aviso e listas vazias.
  if (avisoSemVinculo) {
    return (
      <div className="space-y-4">
        <AlertMessage tipo="info">{avisoSemVinculo}</AlertMessage>
      </div>
    );
  }

  return (
    <div className="space-y-4">
      {/* Header: KPIs estilo Farmer + acoes */}
      <div className="flex items-start justify-between gap-3 flex-wrap">
        <div className="grid grid-cols-2 md:grid-cols-4 gap-2 flex-1 min-w-[420px]">
          <KpiCard
            label="Contadores via bastao"
            value={loading ? "—" : kpis.total_grupos.toLocaleString("pt-BR")}
            icon={Users}
            tone="success"
          />
          <KpiCard
            label="Com tarefa atrasada"
            value={loading ? "—" : kpis.com_atrasada.toLocaleString("pt-BR")}
            icon={AlertTriangle}
            tone={kpis.com_atrasada > 0 ? "danger" : "slate"}
          />
          <KpiCard
            label="Com tarefa futura"
            value={loading ? "—" : kpis.com_futura.toLocaleString("pt-BR")}
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
      {bastoesSemGrupo.length > 0 && (
        <AlertMessage tipo="aviso">
          {bastoesSemGrupo.length === 1
            ? "1 contador aprovado ainda nao aparece na carteira do Farmer "
            : `${bastoesSemGrupo.length} contadores aprovados ainda nao aparecem na carteira do Farmer `}
          (atribuicao pendente ou base CROmie desatualizada):{" "}
          <span className="font-mono text-xs">
            {bastoesSemGrupo
              .map((b) => b.contabilidade || b.cnpj_contador)
              .join(", ")}
          </span>
        </AlertMessage>
      )}

      {/* Estado vazio total */}
      {!loading &&
        grupos.length === 0 &&
        pendentes.length === 0 &&
        bastoesSemGrupo.length === 0 &&
        historico.length === 0 && (
          <Empty
            title="Nenhum bastao registrado"
            description="Quando voce fechar parceria com um contador (Termo + 2 leads), clique em 'Passar contador' pra entregar pro Farmer. Apos a aprovacao, a performance do Farmer com esse contador aparece aqui."
          />
        )}

      {/* Tabela Farmer dos contadores via bastao */}
      {grupos.length > 0 && (
        <DrilldownTabela
          aba="EC_FARMER"
          grupos={gruposFiltrados}
          totalSemFiltro={grupos.length}
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
