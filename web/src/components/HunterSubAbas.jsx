// web/src/components/HunterSubAbas.jsx
//
// Wrapper que aparece quando o Hunter é expandido na aba Hunter de Contadores.
// Substitui o que antes era SÓ a tabela de Prospecção.
//
// Agora oferece 2 sub-abas:
//   - Prospecção: contadores frios em que o Hunter está trabalhando
//                  (lista atual, vinda de carteira_cnpj.colaborador_nome)
//   - Relacionamento: contadores que ele já passou pro Farmer
//                     (lista vinda de carteira_bastao)
//
// A Prospecção renderiza o conteúdo existente (DrilldownTabela do EC_HUNTER).
// O Relacionamento renderiza o BastaoLista.
//
// Por que isto é um componente separado em vez de inline em Contadores.jsx?
//   - Contadores.jsx tem 36KB e é frágil
//   - Toda a lógica de bastão fica encapsulada aqui
//   - Edição cirúrgica em Contadores.jsx fica em 1 ponto só
//
// v1.3.0 (etapa 2c): a prop `farmersDisponiveis` foi removida. Antes ela
// descia de Contadores.jsx (derivada de /dashboard/farmer) ate o
// BastaoModal. Como /dashboard/farmer passou a ser filtrado por usuario,
// essa lista ficaria vazia para um Hunter logado. Agora o BastaoLista
// busca os Farmers diretamente de /carteira/colaboradores (nao filtrado).

import { useState } from "react";
import { Target, Award } from "lucide-react";
import BastaoLista from "./BastaoLista";


export default function HunterSubAbas({
  // Dados do colaborador Hunter expandido (vem do Contadores.jsx)
  hunterNome,

  // Conteúdo da sub-aba "Prospecção" — passado pelo Contadores.jsx
  // (é o JSX antigo: DrilldownTabela com aba="EC_HUNTER")
  prospecaoContent,
}) {
  const [subAba, setSubAba] = useState("PROSPECCAO");

  return (
    <div className="space-y-3">
      {/* Sub-abas — visual menor que abas principais */}
      <div className="flex border-b border-hipo-border">
        <button
          type="button"
          onClick={() => setSubAba("PROSPECCAO")}
          className={`px-3 py-2 text-xs font-medium border-b-2 transition-colors flex items-center gap-1.5 ${
            subAba === "PROSPECCAO"
              ? "border-hipo-blue text-hipo-blue"
              : "border-transparent text-hipo-slate hover:text-hipo-ink"
          }`}
        >
          <Target size={13} />
          Prospecção
        </button>
        <button
          type="button"
          onClick={() => setSubAba("RELACIONAMENTO")}
          className={`px-3 py-2 text-xs font-medium border-b-2 transition-colors flex items-center gap-1.5 ${
            subAba === "RELACIONAMENTO"
              ? "border-hipo-blue text-hipo-blue"
              : "border-transparent text-hipo-slate hover:text-hipo-ink"
          }`}
        >
          <Award size={13} />
          Relacionamento
          <span className="text-[10px] text-hipo-muted ml-1">(bastões)</span>
        </button>
      </div>

      {/* Conteúdo da sub-aba ativa */}
      {subAba === "PROSPECCAO" && (
        <div>{prospecaoContent}</div>
      )}

      {subAba === "RELACIONAMENTO" && (
        <BastaoLista hunterNome={hunterNome} />
      )}
    </div>
  );
}
