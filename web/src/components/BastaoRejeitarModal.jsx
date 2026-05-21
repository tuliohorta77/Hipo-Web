// web/src/components/BastaoRejeitarModal.jsx
//
// Modal pra capturar o motivo ao rejeitar um bastão.
// Aparece quando o Gerente/Franqueado clica em "Rejeitar" na fila.

import { useEffect, useState } from "react";
import { XCircle, AlertCircle } from "lucide-react";
import Modal from "./ui/Modal";
import Button from "./ui/Button";


export default function BastaoRejeitarModal({
  bastao,           // objeto do bastão (null = modal fechado)
  onFechar,
  onConfirmar,      // (motivo: string) => void
  loading = false,
}) {
  const [motivo, setMotivo] = useState("");
  const [erroLocal, setErroLocal] = useState(null);

  // Reset quando reabre
  useEffect(() => {
    if (bastao) {
      setMotivo("");
      setErroLocal(null);
    }
  }, [bastao]);

  function handleConfirmar() {
    const txt = motivo.trim();
    if (!txt) {
      setErroLocal("Informe o motivo da rejeição.");
      return;
    }
    if (txt.length < 5) {
      setErroLocal("Motivo muito curto (mínimo 5 caracteres).");
      return;
    }
    setErroLocal(null);
    onConfirmar(txt);
  }

  return (
    <Modal
      aberto={!!bastao}
      onFechar={onFechar}
      titulo="Rejeitar bastão"
      subtitulo={
        bastao
          ? `${bastao.hunter_nome} → ${bastao.farmer_nome} (${bastao.contabilidade || bastao.cnpj_contador})`
          : ""
      }
      size="md"
      footer={
        <div className="flex justify-end gap-2">
          <Button variant="ghost" onClick={onFechar} disabled={loading}>
            Cancelar
          </Button>
          <Button
            variant="danger"
            onClick={handleConfirmar}
            loading={loading}
            icon={XCircle}
          >
            Rejeitar bastão
          </Button>
        </div>
      }
    >
      <div className="space-y-3">
        <div className="flex items-start gap-2 bg-hipo-warningSoft border border-hipo-warningBorder rounded-md p-3 text-sm">
          <AlertCircle size={16} className="text-hipo-warning shrink-0 mt-0.5" />
          <p className="text-hipo-ink">
            O Hunter verá esse motivo na própria sub-aba "Relacionamento".
            Seja claro pra ele saber o que ajustar antes de reenviar.
          </p>
        </div>

        <div>
          <label className="block text-xs font-medium text-hipo-slate mb-1">
            Motivo da rejeição <span className="text-hipo-danger">*</span>
          </label>
          <textarea
            value={motivo}
            onChange={(e) => {
              setMotivo(e.target.value);
              setErroLocal(null);
            }}
            rows={4}
            maxLength={500}
            placeholder="Ex: Termo de parceria ainda nao foi assinado. Pendente confirmacao do RG do socio."
            disabled={loading}
            className="w-full px-3 py-2 rounded-lg border border-hipo-border bg-hipo-card text-sm text-hipo-ink resize-none focus:outline-none focus:ring-2 focus:ring-hipo-blue/30 disabled:opacity-50"
          />
          <div className="flex justify-between mt-1">
            <span className="text-xs text-hipo-danger">
              {erroLocal || "\u00A0"}
            </span>
            <span className="text-xs text-hipo-muted">
              {motivo.length}/500
            </span>
          </div>
        </div>
      </div>
    </Modal>
  );
}
