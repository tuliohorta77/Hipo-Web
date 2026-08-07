// web/src/components/ui/Modal.jsx
//
// Modal genérico reutilizável. Implementa:
//   - Overlay escurecido com clique-fora fechando
//   - Esc fecha
//   - Foco preso dentro do modal (Tab/Shift+Tab — implementação básica)
//   - Botão X no canto superior direito
//   - Body com scroll interno se necessário
//
// Uso:
//   <Modal aberto={modalAberto} onFechar={() => setModalAberto(false)} titulo="Foo">
//     <p>Conteúdo</p>
//   </Modal>
//
// Tamanhos:
//   size="sm"   (max-w-md)  — 448px  — confirmações
//   size="md"   (max-w-lg)  — 512px  — formulários simples (padrão)
//   size="lg"   (max-w-2xl) — 672px  — formulários complexos / listas
//   size="xl"   (max-w-5xl) — 1024px — telas com abas
//   size="full" (max-w-7xl) — 1280px — visão 360 de um registro
//
// ALTURA ESTÁVEL: xl e full têm altura FIXA, não máxima. Um modal que cresce
// e encolhe conforme a aba selecionada passa sensação de instabilidade — o
// rodapé pula, o fundo reflui e o usuário perde a referência visual. Com
// altura fixa, só o conteúdo interno rola.
//
// Para os tamanhos menores a altura continua sendo máxima: um modal de
// confirmação com 90vh de altura seria pior que o problema que resolve. Use
// alturaFixa para forçar em casos específicos.

import { useEffect, useRef } from "react";
import { X } from "lucide-react";

const TAMANHOS = {
  sm: "max-w-md",
  md: "max-w-lg",
  lg: "max-w-2xl",
  xl: "max-w-5xl",
  full: "max-w-7xl",
};

// Telas com abas precisam de mais altura útil que um formulário curto — e
// fixa, não máxima (ver nota acima).
const ALTURAS_FIXAS = {
  xl: "h-[92vh]",
  full: "h-[92vh]",
};

export default function Modal({
  aberto,
  onFechar,
  titulo,
  subtitulo,
  size = "md",
  children,
  footer,
  bodySemPadding = false,
  alturaFixa = false,
}) {
  const containerRef = useRef(null);

  // Fecha com Esc
  useEffect(() => {
    if (!aberto) return;
    function onKey(e) {
      if (e.key === "Escape") onFechar?.();
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [aberto, onFechar]);

  // Trava scroll do body enquanto aberto
  useEffect(() => {
    if (!aberto) return;
    const prev = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    return () => {
      document.body.style.overflow = prev;
    };
  }, [aberto]);

  // Foco inicial no container
  useEffect(() => {
    if (aberto && containerRef.current) {
      containerRef.current.focus();
    }
  }, [aberto]);

  if (!aberto) return null;

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center p-4"
      role="dialog"
      aria-modal="true"
      aria-labelledby={titulo ? "modal-titulo" : undefined}
      onMouseDown={(e) => {
        // Clique no overlay (não no conteúdo) fecha
        if (e.target === e.currentTarget) onFechar?.();
      }}
    >
      {/* Overlay */}
      <div className="absolute inset-0 bg-hipo-ink/50" />

      {/* Conteúdo */}
      <div
        ref={containerRef}
        tabIndex={-1}
        className={
          "relative bg-hipo-card border border-hipo-border rounded-xl shadow-xl " +
          "w-full flex flex-col outline-none " +
          `${TAMANHOS[size] || TAMANHOS.md} ` +
          (ALTURAS_FIXAS[size] || (alturaFixa ? "h-[90vh]" : "max-h-[90vh]"))
        }
        onMouseDown={(e) => e.stopPropagation()}
      >
        {/* Header */}
        {(titulo || subtitulo) && (
          <div className="px-5 py-4 border-b border-hipo-border flex items-start justify-between gap-3">
            <div className="flex-1 min-w-0">
              {titulo && (
                <h2 id="modal-titulo" className="text-base font-semibold text-hipo-ink">
                  {titulo}
                </h2>
              )}
              {subtitulo && (
                <p className="text-xs text-hipo-slate mt-0.5">{subtitulo}</p>
              )}
            </div>
            <button
              type="button"
              onClick={onFechar}
              className="text-hipo-slate hover:text-hipo-ink p-1 rounded shrink-0"
              aria-label="Fechar"
            >
              <X size={18} />
            </button>
          </div>
        )}

        {/* Body */}
        <div
          className={
            (bodySemPadding ? "" : "px-5 py-4 ") +
            "flex-1 min-h-0 " +
            // min-h-0 é o que permite ao filho flex encolher e rolar dentro
            // de um container flex — sem isso o conteúdo empurra o rodapé
            // para fora da tela.
            (bodySemPadding ? "overflow-hidden" : "overflow-y-auto")
          }
        >
          {children}
        </div>

        {/* Footer */}
        {footer && (
          <div className="px-5 py-3 border-t border-hipo-border bg-hipo-bg/30 rounded-b-xl">
            {footer}
          </div>
        )}
      </div>
    </div>
  );
}
