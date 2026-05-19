// web/src/components/ConfigColaboradoresModal.jsx
//
// Modal para classificar colaboradores como EC_HUNTER, EC_FARMER ou OUTROS.
// Lista populada pelo backend a partir da última carteira carregada.
// Persistência: PUT /carteira/colaboradores/:id
import { useState, useEffect, useMemo } from "react";
import { X, Save, Search } from "lucide-react";
import api from "../api";

const OPCOES = [
  { v: "EC_HUNTER", label: "Hunter",  color: "text-cyan-400 bg-cyan-500/10 border-cyan-500/40" },
  { v: "EC_FARMER", label: "Farmer",  color: "text-emerald-400 bg-emerald-500/10 border-emerald-500/40" },
  { v: "OUTROS",    label: "Outros",  color: "text-slate-400 bg-slate-700/40 border-slate-600" },
];

export default function ConfigColaboradoresModal({ aberto, onFechar, onSalvo }) {
  const [colaboradores, setColaboradores] = useState([]);
  const [busca, setBusca] = useState("");
  const [dirty, setDirty] = useState({}); // { id: novaFuncao }
  const [salvando, setSalvando] = useState(false);
  const [msg, setMsg] = useState(null);

  useEffect(() => {
    if (!aberto) return;
    setMsg(null);
    setDirty({});
    api.get("/carteira/colaboradores").then((r) => {
      setColaboradores(r.data || []);
    }).catch(() => setColaboradores([]));
  }, [aberto]);

  const filtrados = useMemo(() => {
    const n = busca.trim().toLowerCase();
    if (!n) return colaboradores;
    return colaboradores.filter((c) => c.nome.toLowerCase().includes(n));
  }, [colaboradores, busca]);

  function marcar(id, funcao) {
    setDirty((prev) => ({ ...prev, [id]: funcao }));
  }

  async function salvar() {
    if (!Object.keys(dirty).length) {
      onFechar();
      return;
    }
    setSalvando(true);
    setMsg(null);
    try {
      const entradas = Object.entries(dirty);
      // Salva em paralelo, mas tolerando falhas individuais
      const results = await Promise.allSettled(
        entradas.map(([id, funcao]) =>
          api.put(`/carteira/colaboradores/${id}`, { funcao })
        )
      );
      const ok = results.filter((r) => r.status === "fulfilled").length;
      const err = results.length - ok;
      setMsg({
        tipo: err === 0 ? "ok" : "warn",
        texto: err === 0
          ? `${ok} colaborador(es) atualizado(s).`
          : `${ok} OK, ${err} com erro.`,
      });
      if (ok > 0 && onSalvo) onSalvo();
      if (err === 0) {
        setTimeout(onFechar, 600);
      }
    } catch (e) {
      setMsg({ tipo: "erro", texto: e.message });
    } finally {
      setSalvando(false);
    }
  }

  if (!aberto) return null;

  return (
    <div
      className="fixed inset-0 bg-black/70 z-50 flex items-center justify-center p-4"
      onClick={onFechar}
    >
      <div
        className="bg-slate-900 border border-slate-800 rounded-xl w-full max-w-3xl max-h-[85vh] flex flex-col"
        onClick={(e) => e.stopPropagation()}
      >
        {/* Header */}
        <div className="px-6 py-4 border-b border-slate-800 flex items-center justify-between">
          <div>
            <h2 className="text-lg font-bold text-slate-100">Configurar Colaboradores</h2>
            <p className="text-xs text-slate-500 mt-0.5">
              Classifique cada colaborador. Hunter/Farmer/Outros define em qual aba o grupo aparece.
            </p>
          </div>
          <button
            onClick={onFechar}
            className="text-slate-500 hover:text-slate-300 p-1 rounded"
            aria-label="Fechar"
          >
            <X size={20} />
          </button>
        </div>

        {/* Search */}
        <div className="px-6 py-3 border-b border-slate-800">
          <div className="relative">
            <Search size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-slate-500" />
            <input
              value={busca}
              onChange={(e) => setBusca(e.target.value)}
              placeholder="Buscar colaborador..."
              className="w-full bg-slate-950 border border-slate-800 rounded-lg pl-9 pr-3 py-2 text-sm text-slate-200 focus:outline-none focus:border-cyan-500"
            />
          </div>
        </div>

        {/* Mensagem */}
        {msg && (
          <div
            className={`mx-6 mt-3 px-4 py-2 rounded-lg text-sm ${
              msg.tipo === "ok"
                ? "bg-emerald-500/10 text-emerald-400 border border-emerald-500/30"
                : msg.tipo === "warn"
                ? "bg-amber-500/10 text-amber-400 border border-amber-500/30"
                : "bg-red-500/10 text-red-400 border border-red-500/30"
            }`}
          >
            {msg.texto}
          </div>
        )}

        {/* Lista */}
        <div className="flex-1 overflow-auto px-6 py-3">
          {filtrados.length === 0 ? (
            <p className="text-sm text-slate-500 text-center py-8">
              {colaboradores.length === 0
                ? "Nenhum colaborador. Faça o upload da carteira primeiro."
                : "Nenhum colaborador para essa busca."}
            </p>
          ) : (
            <table className="w-full text-sm">
              <thead>
                <tr className="text-[10px] text-slate-500 border-b border-slate-800 tracking-widest">
                  <th className="text-left py-2 px-2">COLABORADOR</th>
                  <th className="text-left py-2 px-2">FUNÇÃO ATUAL (PLANILHA)</th>
                  <th className="text-right py-2 px-2">CLASSIFICAÇÃO HIPO</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-800">
                {filtrados.map((c) => {
                  const funcaoAtual = dirty[c.id] ?? c.funcao;
                  return (
                    <tr key={c.id} className="hover:bg-slate-800/40">
                      <td className="py-2 px-2 text-slate-200 font-medium">{c.nome}</td>
                      <td className="py-2 px-2 text-slate-500 text-xs">
                        {c.funcao_origem || "—"}
                      </td>
                      <td className="py-2 px-2">
                        <div className="flex gap-1 justify-end">
                          {OPCOES.map((op) => {
                            const ativo = funcaoAtual === op.v;
                            return (
                              <button
                                key={op.v}
                                onClick={() => marcar(c.id, op.v)}
                                className={`text-[10px] tracking-widest px-2 py-1 rounded border transition-all ${
                                  ativo
                                    ? op.color
                                    : "border-slate-700 text-slate-500 hover:text-slate-300 hover:border-slate-600"
                                }`}
                              >
                                {op.label.toUpperCase()}
                              </button>
                            );
                          })}
                        </div>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          )}
        </div>

        {/* Footer */}
        <div className="px-6 py-3 border-t border-slate-800 flex justify-between items-center">
          <span className="text-xs text-slate-500">
            {Object.keys(dirty).length > 0
              ? `${Object.keys(dirty).length} alteração(ões) pendente(s)`
              : "Sem alterações"}
          </span>
          <div className="flex gap-2">
            <button
              onClick={onFechar}
              className="px-4 py-2 rounded-lg text-sm text-slate-400 hover:text-slate-200 hover:bg-slate-800 transition-colors"
            >
              Cancelar
            </button>
            <button
              onClick={salvar}
              disabled={salvando || Object.keys(dirty).length === 0}
              className="flex items-center gap-2 px-4 py-2 rounded-lg text-sm font-bold bg-cyan-600 hover:bg-cyan-500 text-white disabled:bg-slate-700 disabled:text-slate-500 transition-all"
            >
              <Save size={14} />
              {salvando ? "Salvando..." : "Salvar"}
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
