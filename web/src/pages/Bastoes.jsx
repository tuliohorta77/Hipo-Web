// web/src/pages/Bastoes.jsx
//
// Página de aprovação de bastões (Gerente + Franqueado).
//
// Layout:
//   - PageHeader com botão Atualizar
//   - 4 KpiCards: Pendentes, Aprovados, Rejeitados, Removidos
//   - Aba "Pendentes" como padrão (fila de trabalho) + abas Aprovados/Rejeitados/Removidos
//   - Tabela com Hunter, Farmer, Contador, Data, Leads, ações
//
// Ações por status:
//   - PENDENTE: botões Aprovar (verde) e Rejeitar (vermelho, abre modal de motivo)
//   - APROVADO / REJEITADO / REMOVIDO: read-only, mostra quem validou e quando
//
// Após uma ação, a lista recarrega — bastão muda de status (não some, decisão
// de produto v1.2.0 etapa 3).

import { useCallback, useEffect, useMemo, useState } from "react";
import {
  RefreshCw, CheckCircle, XCircle, Clock, Ban, AlertCircle, Award,
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

function classesStatus(status) {
  if (status === "PENDENTE")
    return "bg-hipo-warningSoft text-hipo-warning border-hipo-warningBorder";
  if (status === "APROVADO")
    return "bg-hipo-successSoft text-hipo-success border-hipo-successBorder";
  if (status === "REJEITADO")
    return "bg-hipo-dangerSoft text-hipo-danger border-hipo-dangerBorder";
  return "bg-hipo-bg text-hipo-slate border-hipo-border";
}

function IconePorStatus({ status, size = 12 }) {
  if (status === "PENDENTE")  return <Clock size={size} />;
  if (status === "APROVADO")  return <CheckCircle size={size} />;
  if (status === "REJEITADO") return <XCircle size={size} />;
  if (status === "REMOVIDO")  return <Ban size={size} />;
  return null;
}


// ── Página ────────────────────────────────────────────────────

export default function Bastoes() {
  // bastoes guarda TODOS os bastões (todos os hunters, todos os status).
  // Como o backend só expõe /bastoes/pendentes pra aprovador e /bastoes/meus
  // pra cada usuário, precisamos puxar todos via /bastoes/pendentes + /bastoes/meus
  // de cada hunter. Como isso seria N+1, optamos por chamar /bastoes/pendentes
  // como fonte primária e mostrar APROVADO/REJEITADO/REMOVIDO em abas separadas
  // só quando o Gerente clicar — buscando via outro endpoint.
  //
  // SIMPLIFICAÇÃO PRA ESTA FASE: backend retorna SÓ pendentes via
  // /carteira/bastoes/pendentes. Pra ver bastões finalizados (aprovados,
  // rejeitados, removidos), o Gerente precisa abrir o drilldown do Hunter
  // específico em Contadores. A tela Bastões é primariamente a FILA DE TRABALHO.
  //
  // Abas "Aprovados / Rejeitados / Removidos" mostram listas vazias com aviso.

  const [aba, setAba] = useState("PENDENTES");
  const [pendentes, setPendentes] = useState([]);
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
      const { data } = await api.get("/carteira/bastoes/pendentes");
      setPendentes(data || []);
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

  // ── KPIs ────────────────────────────────────────────────────

  const kpis = useMemo(() => {
    return {
      pendentes: pendentes.length,
    };
  }, [pendentes]);

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
          value={kpis.pendentes.toLocaleString("pt-BR")}
          Icon={Clock}
          tone={kpis.pendentes > 0 ? "warning" : "default"}
        />
        <KpiCard
          label="Aprovados"
          value="—"
          Icon={CheckCircle}
          tone="default"
        />
        <KpiCard
          label="Rejeitados"
          value="—"
          Icon={XCircle}
          tone="default"
        />
        <KpiCard
          label="Removidos"
          value="—"
          Icon={Ban}
          tone="default"
        />
      </div>

      {/* Tabs */}
      <div className="flex border-b border-hipo-border mb-4">
        {[
          { v: "PENDENTES",  label: "Pendentes",  Icon: Clock },
          { v: "APROVADOS",  label: "Aprovados",  Icon: CheckCircle },
          { v: "REJEITADOS", label: "Rejeitados", Icon: XCircle },
          { v: "REMOVIDOS",  label: "Removidos",  Icon: Ban },
        ].map(({ v, label, Icon }) => {
          const ativo = aba === v;
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
                {v === "PENDENTES" && kpis.pendentes > 0 && (
                  <span className="ml-1 text-[10px] bg-hipo-warningSoft text-hipo-warning px-1.5 py-0.5 rounded-full">
                    {kpis.pendentes}
                  </span>
                )}
              </span>
            </button>
          );
        })}
      </div>

      {/* Conteúdo da aba PENDENTES */}
      {aba === "PENDENTES" && (
        <Card padding="none">
          {loading ? (
            <p className="p-6 text-sm text-hipo-slate">Carregando...</p>
          ) : pendentes.length === 0 ? (
            <Empty
              Icon={Award}
              title="Nenhum bastão pendente"
              description="Quando um Hunter passar um contador pra um Farmer, ele aparece aqui pra você aprovar ou rejeitar."
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
                  <Th>Criado em</Th>
                  <Th align="right" className="w-44">Ações</Th>
                </tr>
              </thead>
              <tbody>
                {pendentes.map((b) => {
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
                    </Tr>
                  );
                })}
              </tbody>
            </Table>
          )}
        </Card>
      )}

      {/* Outras abas: aviso de scope futuro */}
      {aba !== "PENDENTES" && (
        <Card>
          <div className="text-center py-8">
            <AlertCircle size={32} className="mx-auto text-hipo-muted mb-2" />
            <p className="text-sm text-hipo-slate">
              Lista de bastões {aba.toLowerCase()} fica disponível no drilldown do Hunter
              em <strong>Contadores</strong>.
            </p>
            <p className="text-xs text-hipo-muted mt-1">
              Esta tela foca na fila de trabalho do Gerente/Franqueado.
            </p>
          </div>
        </Card>
      )}

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
