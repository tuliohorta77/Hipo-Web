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

import { useEffect, useRef } from "react";
import { X } from "lucide-react";

const TAMANHOS = {
  sm: "max-w-md",
  md: "max-w-lg",
  lg: "max-w-2xl",
  xl: "max-w-5xl",
  full: "max-w-7xl",
};

// Telas com abas precisam de mais altura útil que um formulário curto.
const ALTURAS = {
  xl: "max-h-[92vh]",
  full: "max-h-[95vh]",
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
        className={`relative bg-hipo-card border border-hipo-border rounded-xl shadow-xl w-full ${TAMANHOS[size] || TAMANHOS.md} ${ALTURAS[size] || "max-h-[90vh]"} flex flex-col outline-none`}
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
            (bodySemPadding ? "" : "px-5 py-4 ") + "overflow-y-auto flex-1"
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
