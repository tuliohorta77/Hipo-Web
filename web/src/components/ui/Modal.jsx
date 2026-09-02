// web/src/components/ui/Modal.jsx
//
// Modal genérico reutilizável. Implementa:
//   - Overlay escurecido com clique-fora fechando
//   - Esc fecha
//   - Foco preso dentro do modal (Tab/Shift+Tab — implementação básica)
//   - Botão X no canto superior direito
//   - Ações da tela na mesma linha do título, à esquerda do X (ver
//     SlotDeAcoes / AcoesDoModal mais abaixo)
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

import { createContext, useContext, useEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";
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

// ── Esc fecha UM modal: o de cima ────────────────────────────────────
//
// Modais empilhados existem desde o drilldown da conta dentro da
// oportunidade. Cada instância escutava `keydown` na window, então um Esc
// chegava em todas ao mesmo tempo e derrubava a pilha inteira: o usuário
// fechava o drilldown e perdia junto a oportunidade que estava editando
// atrás dele.
//
// A pilha guarda a identidade de cada modal ABERTO, na ordem de abertura, e
// só o último trata a tecla. É module-level de propósito: precisa ser uma
// só entre todas as instâncias, e contexto do React seria cerimônia demais
// para uma lista de três posições.
const pilhaDeModais = [];

// ── Ações no cabeçalho, ao lado do X ─────────────────────────────────
//
// As ações de uma tela (Salvar, Fechar, e o que mais a tela ofereça)
// moram na MESMA linha do título. Num modal alto — os `xl` e `full` têm
// 92vh — o rodapé fica longe do que se está editando: quem mexe num campo
// do topo precisa percorrer a tela inteira com os olhos para achar Salvar,
// e em notebook de tela curta o rodapé disputa espaço com o conteúdo.
//
// Há dois caminhos para preencher esse espaço, e a diferença é só de quem
// tem o estado:
//
//   `acoes`        — o PAI monta os botões (quando é ele quem sabe se há
//                    alteração pendente, via um canal tipo registrarSalvar).
//   <AcoesDoModal> — o FILHO monta os botões e eles aparecem no cabeçalho
//                    por portal. É o caminho preferido: o componente que
//                    tem o estado é o mesmo que desenha o botão, sem canal
//                    nenhum entre eles.
//
// Os dois moram em divs irmãos de propósito. Um portal apontando para um
// container que o React também popula é receita de nó removido na
// reconciliação.
const SlotDeAcoes = createContext(null);

/**
 * Envolve botões que devem aparecer no cabeçalho do Modal mais próximo.
 * Fora de um Modal — ou num Modal sem título, que não desenha cabeçalho —
 * não renderiza nada.
 */
export function AcoesDoModal({ children }) {
  const slot = useContext(SlotDeAcoes);
  if (!slot) return null;
  return createPortal(children, slot);
}

export default function Modal({
  aberto,
  onFechar,
  titulo,
  subtitulo,
  size = "md",
  children,
  acoes,
  footer,
  bodySemPadding = false,
  alturaFixa = false,
}) {
  const containerRef = useRef(null);

  // O div do cabeçalho que recebe o portal. Guardado em estado, e não em
  // ref, porque o portal só pode ser criado depois que o nó existe — e um
  // ref puro não avisa ninguém quando isso acontece. `setSlotAcoes` do
  // useState é estável entre renders, então dá para passá-lo direto como
  // ref callback sem o React desmontar e remontar o slot a cada render.
  const [slotAcoes, setSlotAcoes] = useState(null);

  // Identidade estável desta instância, para achar seu lugar na pilha.
  const identidade = useRef(null);
  if (identidade.current === null) identidade.current = {};

  // O `onFechar` chega por ref, não pelas dependências do efeito abaixo. Um
  // pai que recria a função a cada render faria o efeito rodar de novo, e o
  // modal de BAIXO voltaria para o topo da pilha — passando a engolir o Esc
  // que era do de cima. A pilha só pode mudar quando um modal abre ou fecha.
  const fecharRef = useRef(onFechar);
  useEffect(() => { fecharRef.current = onFechar; });

  // Fecha com Esc — mas só o modal do topo da pilha.
  useEffect(() => {
    if (!aberto) return;
    const eu = identidade.current;
    pilhaDeModais.push(eu);

    function onKey(e) {
      if (e.key !== "Escape") return;
      if (pilhaDeModais[pilhaDeModais.length - 1] !== eu) return;
      fecharRef.current?.();
    }
    window.addEventListener("keydown", onKey);

    return () => {
      window.removeEventListener("keydown", onKey);
      const i = pilhaDeModais.indexOf(eu);
      if (i !== -1) pilhaDeModais.splice(i, 1);
    };
  }, [aberto]);

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
            <div className="flex items-center gap-2 shrink-0">
              {acoes && (
                <div className="flex flex-wrap items-center justify-end gap-2">
                  {acoes}
                </div>
              )}
              {/* empty:hidden para não abrir um gap fantasma quando ninguém
                  usa o portal. */}
              <div
                ref={setSlotAcoes}
                className="flex flex-wrap items-center justify-end gap-2 empty:hidden"
              />
              <button
                type="button"
                onClick={onFechar}
                className="text-hipo-slate hover:text-hipo-ink p-1 rounded shrink-0"
                aria-label="Fechar"
              >
                <X size={18} />
              </button>
            </div>
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
          <SlotDeAcoes.Provider value={slotAcoes}>
            {children}
          </SlotDeAcoes.Provider>
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
