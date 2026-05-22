// web/src/pages/Bastoes.jsx
//
// Página de aprovação de bastões (Gerente + Franqueado).
//
// v1.2.0 etapa 4: passou a buscar /carteira/bastoes/todos — então as 4 abas
// (Pendentes/Aprovados/Rejeitados/Removidos) e os 4 KPIs são reais.
//
// Layout:
//   - PageHeader com botão Atualizar
//   - 4 KpiCards: Pendentes, Aprovados, Rejeitados, Removidos (valores reais)
//   - 4 abas; cada uma mostra a tabela filtrada pelo status
//
// Ações por status:
//   - PENDENTE: botões Aprovar (verde) e Rejeitar (vermelho, abre modal de motivo)
//   - APROVADO / REJEITADO / REMOVIDO: read-only, mostra quem validou e quando
//
// Após uma ação, a lista recarrega — bastão muda de status (não some).

import { useCallback, useEffect, useMemo, useState } from "react";
import {
  RefreshCw, CheckCircle, XCircle, Clock, Ban, Award,
} from "lucide-react";
import api from "../api";

import PageHeader from "../components/ui/PageHeader";
import Button from "../components/ui/Button";
import KpiCard from "../components/ui/KpiCard";
import AlertMessage from "../components/ui/AlertMessage";
import Empty from "../components/ui/Empty";
import Card from "../components/ui/Card";
import Table, { Th, Tr, Td } from "../components/ui/Table";
import BastaoRejeitarModal from "../components/BastaoRejeitarModal";


// ── Helpers ───────────────────────────────────────────────────

function fmtData(d) {
  if (!d) return "—";
  try {
    return new Date(d).toLocaleDateString("pt-BR");
  } catch { return "—"; }
}

function fmtDataHora(d) {
  if (!d) return "—";
  try {
    return new Date(d).toLocaleString("pt-BR", {
      day: "2-digit", month: "2-digit", year: "numeric",
      hour: "2-digit", minute: "2-digit",
    });
  } catch { return "—"; }
}


// ── Página ────────────────────────────────────────────────────

const ABAS = [
  { v: "PENDENTE",  label: "Pendentes",  Icon: Clock },
  { v: "APROVADO",  label: "Aprovados",  Icon: CheckCircle },
  { v: "REJEITADO", label: "Rejeitados", Icon: XCircle },
  { v: "REMOVIDO",  label: "Removidos",  Icon: Ban },
];

export default function Bastoes() {
  const [aba, setAba] = useState("PENDENTE");
  const [bastoes, setBastoes] = useState([]);   // todos os status
  const [loading, setLoading] = useState(false);
  const [erro, setErro] = useState(null);
  const [acaoErro, setAcaoErro] = useState(null);
  const [acaoLoading, setAcaoLoading] = useState(null); // id do bastão em ação

  const [rejeitarBastao, setRejeitarBastao] = useState(null);

  // ── Carregar ────────────────────────────────────────────────

  const carregar = useCallback(async () => {
    setLoading(true);
    setErro(null);
    setAcaoErro(null);
    try {
      const { data } = await api.get("/carteira/bastoes/todos");
      setBastoes(data || []);
    } catch (e) {
      setErro(e.response?.data?.detail || e.message || "Erro ao carregar bastões.");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    carregar();
  }, [carregar]);

  // ── Ações ───────────────────────────────────────────────────

  async function aprovar(b) {
    setAcaoLoading(b.id);
    setAcaoErro(null);
    try {
      await api.patch(`/carteira/bastoes/${b.id}/aprovar`);
      await carregar();
    } catch (e) {
      setAcaoErro(
        `Erro ao aprovar ${b.contabilidade || b.cnpj_contador}: ${
          e.response?.data?.detail || e.message
        }`
      );
    } finally {
      setAcaoLoading(null);
    }
  }

  async function confirmarRejeicao(motivo) {
    if (!rejeitarBastao) return;
    setAcaoLoading(rejeitarBastao.id);
    setAcaoErro(null);
    try {
      await api.patch(`/carteira/bastoes/${rejeitarBastao.id}/rejeitar`, {
        motivo,
      });
      setRejeitarBastao(null);
      await carregar();
    } catch (e) {
      setAcaoErro(
        `Erro ao rejeitar: ${e.response?.data?.detail || e.message}`
      );
    } finally {
      setAcaoLoading(null);
    }
  }

  // ── Agrupamento + KPIs ──────────────────────────────────────

  const porStatus = useMemo(() => {
    const buckets = { PENDENTE: [], APROVADO: [], REJEITADO: [], REMOVIDO: [] };
    for (const b of bastoes) {
      if (buckets[b.status]) buckets[b.status].push(b);
    }
    return buckets;
  }, [bastoes]);

  const kpis = useMemo(() => ({
    PENDENTE:  porStatus.PENDENTE.length,
    APROVADO:  porStatus.APROVADO.length,
    REJEITADO: porStatus.REJEITADO.length,
    REMOVIDO:  porStatus.REMOVIDO.length,
  }), [porStatus]);

  const listaAba = porStatus[aba] || [];

  // ── Render ──────────────────────────────────────────────────

  return (
    <>
      <PageHeader
        title="Bastões"
        subtitle="Fila de aprovação de passagens Hunter → Farmer."
        actions={
          <Button
            variant="ghost"
            icon={RefreshCw}
            onClick={carregar}
            disabled={loading}
          >
            Atualizar
          </Button>
        }
      />

      {erro && <AlertMessage tipo="erro" className="mb-4">{erro}</AlertMessage>}
      {acaoErro && <AlertMessage tipo="erro" className="mb-4">{acaoErro}</AlertMessage>}

      {/* KPIs */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-6">
        <KpiCard
          label="Pendentes"
          value={kpis.PENDENTE.toLocaleString("pt-BR")}
          Icon={Clock}
          tone={kpis.PENDENTE > 0 ? "warning" : "default"}
        />
        <KpiCard
          label="Aprovados"
          value={kpis.APROVADO.toLocaleString("pt-BR")}
          Icon={CheckCircle}
          tone={kpis.APROVADO > 0 ? "success" : "default"}
        />
        <KpiCard
          label="Rejeitados"
          value={kpis.REJEITADO.toLocaleString("pt-BR")}
          Icon={XCircle}
          tone="default"
        />
        <KpiCard
          label="Removidos"
          value={kpis.REMOVIDO.toLocaleString("pt-BR")}
          Icon={Ban}
          tone="default"
        />
      </div>

      {/* Tabs */}
      <div className="flex border-b border-hipo-border mb-4">
        {ABAS.map(({ v, label, Icon }) => {
          const ativo = aba === v;
          const count = kpis[v];
          return (
            <button
              key={v}
              type="button"
              onClick={() => setAba(v)}
              className={`px-4 py-2.5 text-sm font-medium border-b-2 transition-colors ${
                ativo
                  ? "border-hipo-blue text-hipo-blue"
                  : "border-transparent text-hipo-slate hover:text-hipo-ink"
              }`}
            >
              <span className="flex items-center gap-2">
                <Icon size={14} />
                {label}
                {count > 0 && (
                  <span
                    className={`ml-1 text-[10px] px-1.5 py-0.5 rounded-full ${
                      v === "PENDENTE"
                        ? "bg-hipo-warningSoft text-hipo-warning"
                        : "bg-hipo-bg text-hipo-slate"
                    }`}
                  >
                    {count}
                  </span>
                )}
              </span>
            </button>
          );
        })}
      </div>

      {/* Conteúdo da aba */}
      <Card padding="none">
        {loading ? (
          <p className="p-6 text-sm text-hipo-slate">Carregando...</p>
        ) : listaAba.length === 0 ? (
          <Empty
            Icon={Award}
            title={`Nenhum bastão ${ABAS.find((a) => a.v === aba)?.label.toLowerCase()}`}
            description={
              aba === "PENDENTE"
                ? "Quando um Hunter passar um contador pra um Farmer, ele aparece aqui pra você aprovar ou rejeitar."
                : "Nada por aqui ainda."
            }
          />
        ) : (
          <Table className="[&_th]:!py-2 [&_th]:!text-[11px] [&_td]:!py-2 [&_td]:!text-[13px]">
            <thead>
              <tr>
                <Th>Hunter</Th>
                <Th>Farmer</Th>
                <Th>Contador</Th>
                <Th align="center">Data parceria</Th>
                <Th align="center">Leads</Th>
                {aba === "PENDENTE" && <Th>Criado em</Th>}
                {aba === "APROVADO" && <Th>Aprovado por</Th>}
                {aba === "REJEITADO" && <Th>Motivo da rejeição</Th>}
                {aba === "REMOVIDO" && <Th>Removido em</Th>}
                {aba === "PENDENTE" && <Th align="right" className="w-44">Ações</Th>}
              </tr>
            </thead>
            <tbody>
              {listaAba.map((b) => {
                const esteEmAcao = acaoLoading === b.id;
                return (
                  <Tr key={b.id} hover>
                    <Td className="font-medium text-hipo-ink">{b.hunter_nome}</Td>
                    <Td className="text-hipo-ink">{b.farmer_nome}</Td>
                    <Td>
                      <div className="text-hipo-ink">{b.contabilidade || "—"}</div>
                      <div className="text-xs text-hipo-muted font-mono">{b.cnpj_contador}</div>
                      {b.cidade_uf && (
                        <div className="text-xs text-hipo-slate">{b.cidade_uf}</div>
                      )}
                    </Td>
                    <Td align="center" className="whitespace-nowrap">
                      {fmtData(b.data_parceria)}
                    </Td>
                    <Td align="center" className="text-hipo-blue font-semibold">
                      {b.leads_iniciais}
                    </Td>

                    {/* Coluna que varia por aba */}
                    {aba === "PENDENTE" && (
                      <Td className="text-xs text-hipo-slate whitespace-nowrap">
                        {fmtDataHora(b.criado_em)}
                        {b.observacoes && (
                          <div
                            className="mt-1 text-[10px] text-hipo-muted truncate max-w-[180px]"
                            title={b.observacoes}
                          >
                            "{b.observacoes}"
                          </div>
                        )}
                      </Td>
                    )}
                    {aba === "APROVADO" && (
                      <Td className="text-xs text-hipo-slate whitespace-nowrap">
                        {b.validado_por_nome || "—"}
                        <div className="text-[10px] text-hipo-muted">
                          {fmtDataHora(b.validado_em)}
                        </div>
                      </Td>
                    )}
                    {aba === "REJEITADO" && (
                      <Td className="text-xs text-hipo-slate max-w-[240px]">
                        {b.motivo_rejeicao || "—"}
                        {b.validado_por_nome && (
                          <div className="text-[10px] text-hipo-muted mt-0.5">
                            por {b.validado_por_nome} · {fmtDataHora(b.validado_em)}
                          </div>
                        )}
                      </Td>
                    )}
                    {aba === "REMOVIDO" && (
                      <Td className="text-xs text-hipo-slate whitespace-nowrap">
                        {fmtDataHora(b.removido_em)}
                      </Td>
                    )}

                    {/* Ações só na aba Pendentes */}
                    {aba === "PENDENTE" && (
                      <Td align="right">
                        <div className="flex justify-end gap-1">
                          <button
                            type="button"
                            onClick={() => aprovar(b)}
                            disabled={esteEmAcao || acaoLoading !== null}
                            className="px-2.5 py-1 text-xs rounded border border-hipo-successBorder bg-hipo-successSoft text-hipo-success hover:bg-hipo-success hover:text-white transition-colors disabled:opacity-50 disabled:cursor-not-allowed flex items-center gap-1"
                            title="Aprovar bastão"
                          >
                            <CheckCircle size={12} />
                            Aprovar
                          </button>
                          <button
                            type="button"
                            onClick={() => setRejeitarBastao(b)}
                            disabled={esteEmAcao || acaoLoading !== null}
                            className="px-2.5 py-1 text-xs rounded border border-hipo-dangerBorder bg-hipo-dangerSoft text-hipo-danger hover:bg-hipo-danger hover:text-white transition-colors disabled:opacity-50 disabled:cursor-not-allowed flex items-center gap-1"
                            title="Rejeitar bastão"
                          >
                            <XCircle size={12} />
                            Rejeitar
                          </button>
                        </div>
                      </Td>
                    )}
                  </Tr>
                );
              })}
            </tbody>
          </Table>
        )}
      </Card>

      {/* Modal de rejeição */}
      <BastaoRejeitarModal
        bastao={rejeitarBastao}
        onFechar={() => acaoLoading === null && setRejeitarBastao(null)}
        onConfirmar={confirmarRejeicao}
        loading={acaoLoading === rejeitarBastao?.id}
      />
    </>
  );
}
