// web/src/components/BastaoModal.jsx
//
// Modal que o Hunter usa pra passar bastão pra um Farmer.
// Fluxo:
//   1. Hunter digita CNPJ → onChange dispara lookup automatico após 600ms
//   2. Lookup mostra a contabilidade encontrada (ou erro se nao existir)
//   3. Hunter escolhe Farmer (dropdown com farmers conhecidos)
//   4. Hunter preenche data da parceria + leads iniciais
//   5. Submit → POST /carteira/bastoes (status=PENDENTE, ADM aprova)
//
// Lista de Farmers: o backend não tem endpoint "listar farmers", mas
// vem na resposta do /carteira/dashboard/farmer. Em vez de chamar tudo
// isso aqui, recebemos `farmersDisponiveis` via prop — quem chama o
// modal já tem isso em mão.

import { useEffect, useState, useRef } from "react";
import { Search, AlertCircle, CheckCircle, Loader2 } from "lucide-react";
import api from "../api";
import Modal from "./ui/Modal";
import Button from "./ui/Button";
import Input from "./ui/Input";
import AlertMessage from "./ui/AlertMessage";


// ── Helpers ───────────────────────────────────────────────────

function fmtCnpjInput(v) {
  // Mantém o que o usuário digita; só remove caracteres inválidos
  return (v || "").replace(/[^\d./-]/g, "").slice(0, 18);
}

function hoje() {
  return new Date().toISOString().slice(0, 10);
}


export default function BastaoModal({
  aberto,
  onFechar,
  farmersDisponiveis = [],
  onSucesso,
}) {
  const [cnpj, setCnpj] = useState("");
  const [contadorEncontrado, setContadorEncontrado] = useState(null);
  const [lookupErro, setLookupErro] = useState(null);
  const [lookupLoading, setLookupLoading] = useState(false);

  const [farmerNome, setFarmerNome] = useState("");
  const [dataParceria, setDataParceria] = useState(hoje());
  const [leadsIniciais, setLeadsIniciais] = useState(2);
  const [observacoes, setObservacoes] = useState("");

  const [submitLoading, setSubmitLoading] = useState(false);
  const [submitErro, setSubmitErro] = useState(null);

  const lookupTimerRef = useRef(null);

  // Reset ao abrir
  useEffect(() => {
    if (!aberto) return;
    setCnpj("");
    setContadorEncontrado(null);
    setLookupErro(null);
    setLookupLoading(false);
    setFarmerNome("");
    setDataParceria(hoje());
    setLeadsIniciais(2);
    setObservacoes("");
    setSubmitLoading(false);
    setSubmitErro(null);
  }, [aberto]);

  // Lookup automático com debounce (600ms)
  useEffect(() => {
    if (!aberto) return;

    // Limpa estado anterior
    setContadorEncontrado(null);
    setLookupErro(null);

    if (lookupTimerRef.current) {
      clearTimeout(lookupTimerRef.current);
    }

    const cnpjLimpo = (cnpj || "").replace(/\D/g, "");
    if (cnpjLimpo.length !== 14) return;

    lookupTimerRef.current = setTimeout(async () => {
      setLookupLoading(true);
      try {
        const { data } = await api.get("/carteira/bastoes/contador", {
          params: { cnpj: cnpj.trim() },
        });
        setContadorEncontrado(data);
        setLookupErro(null);
      } catch (e) {
        setContadorEncontrado(null);
        const detail = e.response?.data?.detail;
        if (e.response?.status === 404) {
          setLookupErro("CNPJ não encontrado na carteira. Confira o número.");
        } else {
          setLookupErro(detail || e.message || "Erro ao buscar contador.");
        }
      } finally {
        setLookupLoading(false);
      }
    }, 600);

    return () => {
      if (lookupTimerRef.current) clearTimeout(lookupTimerRef.current);
    };
  }, [cnpj, aberto]);

  // Submit
  async function handleSubmit() {
    setSubmitErro(null);

    if (!contadorEncontrado) {
      setSubmitErro("Selecione um CNPJ válido antes de continuar.");
      return;
    }
    if (!farmerNome) {
      setSubmitErro("Escolha o Farmer que vai receber o bastão.");
      return;
    }
    if (!dataParceria) {
      setSubmitErro("Informe a data da parceria.");
      return;
    }
    if (leadsIniciais < 0) {
      setSubmitErro("Leads iniciais não pode ser negativo.");
      return;
    }

    setSubmitLoading(true);
    try {
      const { data } = await api.post("/carteira/bastoes", {
        farmer_nome: farmerNome,
        cnpj_contador: contadorEncontrado.cnpj_contador,
        data_parceria: dataParceria,
        leads_iniciais: Number(leadsIniciais),
        observacoes: observacoes.trim() || null,
      });
      onSucesso?.(data);
      onFechar?.();
    } catch (e) {
      const detail = e.response?.data?.detail;
      setSubmitErro(detail || e.message || "Erro ao criar bastão.");
    } finally {
      setSubmitLoading(false);
    }
  }

  const podeSubmeter =
    contadorEncontrado &&
    farmerNome &&
    dataParceria &&
    leadsIniciais >= 0 &&
    !submitLoading;

  return (
    <Modal
      aberto={aberto}
      onFechar={onFechar}
      titulo="Passar bastão pra um Farmer"
      subtitulo="O Gerente ou Franqueado precisa aprovar antes do contador aparecer na sua aba Relacionamento."
      size="lg"
      footer={
        <div className="flex justify-end gap-2">
          <Button variant="ghost" onClick={onFechar} disabled={submitLoading}>
            Cancelar
          </Button>
          <Button
            onClick={handleSubmit}
            disabled={!podeSubmeter}
            loading={submitLoading}
          >
            Enviar pra aprovação
          </Button>
        </div>
      }
    >
      <div className="space-y-4">
        {/* CNPJ */}
        <div>
          <label className="block text-xs font-medium text-hipo-slate mb-1">
            CNPJ do contador
          </label>
          <Input
            placeholder="00.000.000/0000-00"
            value={cnpj}
            onChange={(e) => setCnpj(fmtCnpjInput(e.target.value))}
            icon={Search}
          />
          {/* Status do lookup */}
          <div className="mt-1.5 min-h-[20px] text-xs">
            {lookupLoading && (
              <span className="flex items-center gap-1.5 text-hipo-slate">
                <Loader2 size={12} className="animate-spin" /> Buscando contador...
              </span>
            )}
            {!lookupLoading && contadorEncontrado && (
              <span className="flex items-center gap-1.5 text-hipo-success">
                <CheckCircle size={12} />
                <span className="font-medium">{contadorEncontrado.contabilidade}</span>
                <span className="text-hipo-muted">
                  · {contadorEncontrado.cidade_uf || "—"}
                  {contadorEncontrado.colaborador_atual &&
                    ` · hoje com ${contadorEncontrado.colaborador_atual}`}
                </span>
              </span>
            )}
            {!lookupLoading && lookupErro && (
              <span className="flex items-center gap-1.5 text-hipo-danger">
                <AlertCircle size={12} /> {lookupErro}
              </span>
            )}
          </div>
        </div>

        {/* Farmer */}
        <div>
          <label className="block text-xs font-medium text-hipo-slate mb-1">
            Farmer que vai cuidar do relacionamento
          </label>
          <select
            value={farmerNome}
            onChange={(e) => setFarmerNome(e.target.value)}
            className="w-full h-10 px-3 rounded-lg border border-hipo-border bg-hipo-card text-sm text-hipo-ink focus:outline-none focus:ring-2 focus:ring-hipo-blue/30"
          >
            <option value="">— Selecionar Farmer —</option>
            {farmersDisponiveis.map((f) => (
              <option key={f} value={f}>
                {f}
              </option>
            ))}
          </select>
          {farmersDisponiveis.length === 0 && (
            <p className="text-xs text-hipo-warning mt-1">
              Nenhum Farmer cadastrado na carteira. Faça upload da carteira primeiro.
            </p>
          )}
        </div>

        {/* Data + Leads na mesma linha */}
        <div className="grid grid-cols-2 gap-3">
          <div>
            <label className="block text-xs font-medium text-hipo-slate mb-1">
              Data da parceria
            </label>
            <input
              type="date"
              value={dataParceria}
              onChange={(e) => setDataParceria(e.target.value)}
              max={hoje()}
              className="w-full h-10 px-3 rounded-lg border border-hipo-border bg-hipo-card text-sm text-hipo-ink focus:outline-none focus:ring-2 focus:ring-hipo-blue/30"
            />
          </div>
          <div>
            <label className="block text-xs font-medium text-hipo-slate mb-1">
              Leads iniciais
              <span className="text-hipo-muted font-normal"> (indicados nesse momento)</span>
            </label>
            <input
              type="number"
              min={0}
              value={leadsIniciais}
              onChange={(e) => setLeadsIniciais(e.target.value === "" ? 0 : Number(e.target.value))}
              className="w-full h-10 px-3 rounded-lg border border-hipo-border bg-hipo-card text-sm text-hipo-ink focus:outline-none focus:ring-2 focus:ring-hipo-blue/30"
            />
          </div>
        </div>

        {/* Observações (opcional) */}
        <div>
          <label className="block text-xs font-medium text-hipo-slate mb-1">
            Observações <span className="text-hipo-muted font-normal">(opcional)</span>
          </label>
          <textarea
            rows={2}
            value={observacoes}
            onChange={(e) => setObservacoes(e.target.value)}
            placeholder="Algum contexto que o aprovador precise saber..."
            className="w-full px-3 py-2 rounded-lg border border-hipo-border bg-hipo-card text-sm text-hipo-ink resize-none focus:outline-none focus:ring-2 focus:ring-hipo-blue/30"
            maxLength={1000}
          />
        </div>

        {/* Erro de submit */}
        {submitErro && <AlertMessage tipo="erro">{submitErro}</AlertMessage>}

        {/* Aviso pra confirmação */}
        <div className="text-xs text-hipo-slate bg-hipo-bg border border-hipo-border rounded-md px-3 py-2">
          <strong>Importante:</strong> esse registro fica como{" "}
          <span className="text-hipo-warning font-medium">PENDENTE</span> até o Gerente/Franqueado
          aprovar. Você verá o status do bastão na sub-aba "Relacionamento".
        </div>
      </div>
    </Modal>
  );
}
