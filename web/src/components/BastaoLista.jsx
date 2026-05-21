// web/src/components/BastaoLista.jsx
//
// Sub-aba "Relacionamento" do Hunter expandido.
// Mostra:
//   - KPIs no topo: total passados (aprovados), pendentes, leads iniciais
//   - Botao [+ Passar contador] que abre BastaoModal
//   - Tabela de contadores que o Hunter passou:
//       * status (badge colorido)
//       * contabilidade
//       * farmer que recebeu
//       * data parceria + leads iniciais
//       * botão remover (soft delete) — só se status é PENDENTE ou APROVADO
//
// Quando clica numa linha APROVADA → abre o CarteiraGrupoDrawer (drilldown
// igual o do Farmer) pra ver tarefas e leads daquele contador.

import { useCallback, useEffect, useMemo, useState } from "react";
import {
  Plus,
  RefreshCw,
  Trash2,
  Clock,
  CheckCircle,
  XCircle,
  Eye,
  AlertCircle,
} from "lucide-react";
import api from "../api";
import Button from "./ui/Button";
import KpiCard from "./ui/KpiCard";
import Empty from "./ui/Empty";
import AlertMessage from "./ui/AlertMessage";
import Table, { Th, Tr, Td } from "./ui/Table";
import Modal from "./ui/Modal";
import BastaoModal from "./BastaoModal";
import CarteiraGrupoDrawer from "./CarteiraGrupoDrawer";


// ── Helpers ───────────────────────────────────────────────────

function fmtData(d) {
  if (!d) return "—";
  try {
    return new Date(d).toLocaleDateString("pt-BR");
  } catch { return "—"; }
}

function classesStatus(status) {
  // Pastéis do manual de marca
  if (status === "PENDENTE")
    return "bg-hipo-warningSoft text-hipo-warning border-hipo-warningBorder";
  if (status === "APROVADO")
    return "bg-hipo-successSoft text-hipo-success border-hipo-successBorder";
  if (status === "REJEITADO")
    return "bg-hipo-dangerSoft text-hipo-danger border-hipo-dangerBorder";
  return "bg-hipo-bg text-hipo-slate border-hipo-border";
}

function IconePorStatus({ status, size = 12 }) {
  if (status === "PENDENTE") return <Clock size={size} />;
  if (status === "APROVADO") return <CheckCircle size={size} />;
  if (status === "REJEITADO") return <XCircle size={size} />;
  return null;
}


// ── Componente ────────────────────────────────────────────────

export default function BastaoLista({
  hunterNome,
  farmersDisponiveis = [],
}) {
  const [bastoes, setBastoes] = useState([]);
  const [kpis, setKpis] = useState(null);
  const [loading, setLoading] = useState(false);
  const [erro, setErro] = useState(null);

  const [modalAberto, setModalAberto] = useState(false);

  // Confirmação de remoção
  const [bastaoARemover, setBastaoARemover] = useState(null);
  const [removendoLoading, setRemovendoLoading] = useState(false);

  // Drawer de drilldown ao clicar em bastão APROVADO
  const [drawerGrupo, setDrawerGrupo] = useState(null);

  // ── Carregar dados ──────────────────────────────────────────

  const carregar = useCallback(async () => {
    setLoading(true);
    setErro(null);
    try {
      const [meus, kp] = await Promise.all([
        api.get("/carteira/bastoes/meus"),
        api.get(`/carteira/bastoes/kpis/${encodeURIComponent(hunterNome)}`),
      ]);
      setBastoes(meus.data || []);
      setKpis(kp.data);
    } catch (e) {
      setErro(e.response?.data?.detail || e.message || "Erro ao carregar bastões.");
    } finally {
      setLoading(false);
    }
  }, [hunterNome]);

  useEffect(() => {
    carregar();
  }, [carregar]);

  // ── Ações ───────────────────────────────────────────────────

  function onSucessoModal() {
    // Recarrega lista + KPIs após criar bastão
    carregar();
  }

  async function confirmarRemover() {
    if (!bastaoARemover) return;
    setRemovendoLoading(true);
    try {
      await api.delete(`/carteira/bastoes/${bastaoARemover.id}`);
      setBastaoARemover(null);
      await carregar();
    } catch (e) {
      const detail = e.response?.data?.detail;
      setErro(detail || e.message || "Erro ao remover bastão.");
    } finally {
      setRemovendoLoading(false);
    }
  }

  function abrirDrilldown(b) {
    // Bastões APROVADOS abrem o drawer do grupo (igual o do Farmer).
    // Precisamos do id_grupo do contador — não temos direto no bastao,
    // então usamos o CNPJ como id (o backend aceita ambos no /grupos).
    // Como o backend espera id_grupo, vamos buscar por CNPJ via outro path.
    // Por enquanto, abrimos o drawer com o cnpj_contador como id_grupo —
    // SE o backend não suportar, exibimos erro amigável.
    //
    // NOTA: o /carteira/grupos/{id_grupo} espera id_grupo (varchar curto).
    // Como não temos, e o backend não tem rota por CNPJ, vamos abrir o
    // drawer com cnpj_contador. CarteiraGrupoDrawer eventualmente lida
    // bem se o backend retorna 404 (mostra mensagem de erro).
    //
    // PENDÊNCIA: backend precisa de /carteira/grupos-por-cnpj/{cnpj} ou
    // similar pra fechar essa lacuna. Por enquanto, deixamos o usuário
    // ver o erro e abrimos uma issue (será resolvido na Etapa 2b se
    // necessário).
    setDrawerGrupo({
      id_grupo: b.cnpj_contador,
      nome_grupo: b.contabilidade || b.cnpj_contador,
    });
  }

  // ── Memos ───────────────────────────────────────────────────

  // Separa em 2 buckets visuais: ativos (PENDENTE+APROVADO) e historico (REJEITADO+REMOVIDO)
  const ativos = useMemo(
    () => bastoes.filter((b) => ["PENDENTE", "APROVADO"].includes(b.status)),
    [bastoes]
  );
  const historico = useMemo(
    () => bastoes.filter((b) => ["REJEITADO", "REMOVIDO"].includes(b.status)),
    [bastoes]
  );

  // ── Render ──────────────────────────────────────────────────

  return (
    <div className="space-y-4">
      {/* Header: KPIs + Acoes */}
      <div className="flex items-start justify-between gap-3 flex-wrap">
        <div className="grid grid-cols-3 gap-2 flex-1 min-w-[400px]">
          <KpiCard
            label="Passados (aprovados)"
            value={kpis ? kpis.total_passados.toLocaleString("pt-BR") : "—"}
            tone="success"
          />
          <KpiCard
            label="Aguardando ADM"
            value={kpis ? kpis.pendentes.toLocaleString("pt-BR") : "—"}
            tone={kpis?.pendentes > 0 ? "warning" : "default"}
          />
          <KpiCard
            label="Leads iniciais (soma)"
            value={kpis ? kpis.leads_iniciais_soma.toLocaleString("pt-BR") : "—"}
            tone="info"
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

      {/* Estado vazio */}
      {!loading && ativos.length === 0 && historico.length === 0 && (
        <Empty
          title="Nenhum bastão registrado"
          description="Quando você fechar parceria com um contador (Termo + 2 leads), clique em 'Passar contador' pra entregar pro Farmer."
        />
      )}

      {/* Lista de bastões ATIVOS */}
      {ativos.length > 0 && (
        <div>
          <h4 className="text-xs font-semibold text-hipo-slate tracking-wider uppercase mb-2">
            Ativos ({ativos.length})
          </h4>
          <Table className="[&_th]:!py-2 [&_th]:!text-[11px] [&_td]:!py-2 [&_td]:!text-[13px]">
            <thead>
              <tr>
                <Th>Status</Th>
                <Th>Contabilidade / CNPJ</Th>
                <Th>Farmer responsável</Th>
                <Th align="center">Data parceria</Th>
                <Th align="center">Leads iniciais</Th>
                <Th align="right" className="w-24">Ações</Th>
              </tr>
            </thead>
            <tbody>
              {ativos.map((b) => (
                <Tr key={b.id} hover>
                  <Td>
                    <span
                      className={`inline-flex items-center gap-1 text-[10px] font-medium tracking-wider px-2 py-0.5 rounded-full border ${classesStatus(b.status)}`}
                    >
                      <IconePorStatus status={b.status} />
                      {b.status}
                    </span>
                  </Td>
                  <Td>
                    <div className="font-medium text-hipo-ink">{b.contabilidade || "—"}</div>
                    <div className="text-xs text-hipo-muted font-mono">{b.cnpj_contador}</div>
                  </Td>
                  <Td className="text-hipo-ink">{b.farmer_nome}</Td>
                  <Td align="center" className="whitespace-nowrap">
                    {fmtData(b.data_parceria)}
                  </Td>
                  <Td align="center" className="text-hipo-blue font-semibold">
                    {b.leads_iniciais}
                  </Td>
                  <Td align="right">
                    <div className="flex justify-end gap-1">
                      {b.status === "APROVADO" && (
                        <button
                          type="button"
                          onClick={() => abrirDrilldown(b)}
                          className="p-1.5 rounded text-hipo-blue hover:bg-hipo-blueSoft"
                          title="Ver drilldown"
                        >
                          <Eye size={14} />
                        </button>
                      )}
                      <button
                        type="button"
                        onClick={() => setBastaoARemover(b)}
                        className="p-1.5 rounded text-hipo-danger hover:bg-hipo-dangerSoft"
                        title="Remover bastão"
                      >
                        <Trash2 size={14} />
                      </button>
                    </div>
                  </Td>
                </Tr>
              ))}
            </tbody>
          </Table>
        </div>
      )}

      {/* Lista de bastões HISTÓRICO (rejeitados/removidos) — colapsável visualmente */}
      {historico.length > 0 && (
        <details className="group">
          <summary className="cursor-pointer text-xs font-semibold text-hipo-slate tracking-wider uppercase mb-2 hover:text-hipo-ink">
            Histórico ({historico.length}) — rejeitados e removidos
          </summary>
          <Table className="mt-2 opacity-70 [&_th]:!py-2 [&_th]:!text-[11px] [&_td]:!py-2 [&_td]:!text-[13px]">
            <thead>
              <tr>
                <Th>Status</Th>
                <Th>Contabilidade / CNPJ</Th>
                <Th>Farmer</Th>
                <Th align="center">Data parceria</Th>
                <Th>Motivo / Removido em</Th>
              </tr>
            </thead>
            <tbody>
              {historico.map((b) => (
                <Tr key={b.id}>
                  <Td>
                    <span
                      className={`inline-flex items-center gap-1 text-[10px] font-medium tracking-wider px-2 py-0.5 rounded-full border ${classesStatus(b.status)}`}
                    >
                      <IconePorStatus status={b.status} />
                      {b.status}
                    </span>
                  </Td>
                  <Td>
                    <div className="text-hipo-ink">{b.contabilidade || "—"}</div>
                    <div className="text-xs text-hipo-muted font-mono">{b.cnpj_contador}</div>
                  </Td>
                  <Td className="text-hipo-slate">{b.farmer_nome}</Td>
                  <Td align="center" className="text-hipo-slate whitespace-nowrap">
                    {fmtData(b.data_parceria)}
                  </Td>
                  <Td className="text-xs text-hipo-slate">
                    {b.status === "REJEITADO" && (b.motivo_rejeicao || "—")}
                    {b.status === "REMOVIDO" && `Removido em ${fmtData(b.removido_em)}`}
                  </Td>
                </Tr>
              ))}
            </tbody>
          </Table>
        </details>
      )}

      {/* Modal de inclusão */}
      <BastaoModal
        aberto={modalAberto}
        onFechar={() => setModalAberto(false)}
        farmersDisponiveis={farmersDisponiveis}
        onSucesso={onSucessoModal}
      />

      {/* Modal de confirmação de remoção */}
      <Modal
        aberto={!!bastaoARemover}
        onFechar={() => !removendoLoading && setBastaoARemover(null)}
        titulo="Remover bastão?"
        size="sm"
        footer={
          <div className="flex justify-end gap-2">
            <Button
              variant="ghost"
              onClick={() => setBastaoARemover(null)}
              disabled={removendoLoading}
            >
              Cancelar
            </Button>
            <Button
              onClick={confirmarRemover}
              loading={removendoLoading}
              variant="danger"
            >
              Remover
            </Button>
          </div>
        }
      >
        <div className="flex items-start gap-3">
          <AlertCircle size={20} className="text-hipo-danger shrink-0 mt-0.5" />
          <div className="space-y-1.5 text-sm">
            <p className="text-hipo-ink">
              O bastão de <strong>{bastaoARemover?.contabilidade || bastaoARemover?.cnpj_contador}</strong>{" "}
              será removido da sua aba Relacionamento.
            </p>
            <p className="text-xs text-hipo-slate">
              O contador continua na base. Você pode passar bastão de novo depois,
              se quiser. Ação reversível só com novo registro.
            </p>
          </div>
        </div>
      </Modal>

      {/* Drilldown drawer — abre quando clica em bastão APROVADO */}
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
