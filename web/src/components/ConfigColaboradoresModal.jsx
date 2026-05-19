// web/src/components/ConfigColaboradoresModal.jsx
//
// Modal para classificar colaboradores como EC_HUNTER, EC_FARMER ou OUTROS.
// Lista populada pelo backend a partir da última carteira carregada.
// Persistência: PUT /carteira/colaboradores/:id

import { useState, useEffect, useMemo } from 'react';
import { X, Save, Search } from 'lucide-react';
import api from '../api';
import Button from './ui/Button';
import AlertMessage from './ui/AlertMessage';

const OPCOES = [
  {
    v: 'EC_HUNTER',
    label: 'Hunter',
    activeClass: 'bg-hipo-blueSoft text-hipo-blue border-hipo-blue',
  },
  {
    v: 'EC_FARMER',
    label: 'Farmer',
    activeClass: 'bg-emerald-50 text-emerald-700 border-emerald-500',
  },
  {
    v: 'OUTROS',
    label: 'Outros',
    activeClass: 'bg-hipo-bg text-hipo-ink border-hipo-slate',
  },
];

export default function ConfigColaboradoresModal({ aberto, onFechar, onSalvo }) {
  const [colaboradores, setColaboradores] = useState([]);
  const [busca, setBusca] = useState('');
  const [dirty, setDirty] = useState({});
  const [salvando, setSalvando] = useState(false);
  const [msg, setMsg] = useState(null);

  useEffect(() => {
    if (!aberto) return;
    setMsg(null);
    setDirty({});
    api
      .get('/carteira/colaboradores')
      .then((r) => setColaboradores(r.data || []))
      .catch(() => setColaboradores([]));
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
      const results = await Promise.allSettled(
        entradas.map(([id, funcao]) =>
          api.put(`/carteira/colaboradores/${id}`, { funcao })
        )
      );
      const ok = results.filter((r) => r.status === 'fulfilled').length;
      const err = results.length - ok;
      setMsg({
        tipo: err === 0 ? 'ok' : 'aviso',
        texto:
          err === 0
            ? `${ok} colaborador(es) atualizado(s).`
            : `${ok} OK, ${err} com erro.`,
      });
      if (ok > 0 && onSalvo) onSalvo();
      if (err === 0) {
        setTimeout(onFechar, 600);
      }
    } catch (e) {
      setMsg({ tipo: 'erro', texto: e.message });
    } finally {
      setSalvando(false);
    }
  }

  if (!aberto) return null;

  return (
    <div
      className="fixed inset-0 bg-hipo-ink/40 z-50 flex items-center justify-center p-4"
      onClick={onFechar}
    >
      <div
        className="bg-hipo-card border border-hipo-border rounded-2xl w-full max-w-3xl max-h-[85vh] flex flex-col shadow-soft"
        onClick={(e) => e.stopPropagation()}
      >
        {/* Header */}
        <div className="px-6 py-4 border-b border-hipo-border flex items-center justify-between">
          <div>
            <h2 className="text-h2 text-hipo-ink">Configurar colaboradores</h2>
            <p className="text-sm text-hipo-slate mt-0.5">
              Classifique cada colaborador. Hunter/Farmer/Outros define em qual
              aba o grupo aparece.
            </p>
          </div>
          <button
            onClick={onFechar}
            className="text-hipo-slate hover:text-hipo-ink p-1.5 rounded-lg hover:bg-hipo-bg transition-colors"
            aria-label="Fechar"
          >
            <X size={20} />
          </button>
        </div>

        {/* Busca */}
        <div className="px-6 py-3 border-b border-hipo-border">
          <div className="relative">
            <Search
              size={16}
              className="absolute left-3 top-1/2 -translate-y-1/2 text-hipo-muted"
            />
            <input
              value={busca}
              onChange={(e) => setBusca(e.target.value)}
              placeholder="Buscar colaborador..."
              className="w-full h-10 bg-hipo-card border border-hipo-border rounded-lg pl-10 pr-3 text-sm text-hipo-ink placeholder:text-hipo-muted outline-none focus:border-hipo-blue focus:ring-2 focus:ring-blue-100"
            />
          </div>
        </div>

        {/* Mensagem */}
        {msg && (
          <div className="mx-6 mt-3">
            <AlertMessage tipo={msg.tipo}>{msg.texto}</AlertMessage>
          </div>
        )}

        {/* Lista */}
        <div className="flex-1 overflow-auto px-6 py-3">
          {filtrados.length === 0 ? (
            <p className="text-sm text-hipo-slate text-center py-8">
              {colaboradores.length === 0
                ? 'Nenhum colaborador. Faça o upload da carteira primeiro.'
                : 'Nenhum colaborador para essa busca.'}
            </p>
          ) : (
            <table className="w-full text-sm">
              <thead>
                <tr className="text-xs text-hipo-slate uppercase tracking-wide border-b border-hipo-border">
                  <th className="text-left py-2.5 px-2 font-medium">
                    Colaborador
                  </th>
                  <th className="text-left py-2.5 px-2 font-medium">
                    Função (planilha)
                  </th>
                  <th className="text-right py-2.5 px-2 font-medium">
                    Classificação Hipo
                  </th>
                </tr>
              </thead>
              <tbody>
                {filtrados.map((c) => {
                  const funcaoAtual = dirty[c.id] ?? c.funcao;
                  return (
                    <tr
                      key={c.id}
                      className="border-b border-hipo-border last:border-0 hover:bg-hipo-bg/60"
                    >
                      <td className="py-3 px-2 font-medium text-hipo-ink">
                        {c.nome}
                      </td>
                      <td className="py-3 px-2 text-hipo-slate text-xs">
                        {c.funcao_origem || '—'}
                      </td>
                      <td className="py-3 px-2">
                        <div className="flex gap-1 justify-end">
                          {OPCOES.map((op) => {
                            const ativo = funcaoAtual === op.v;
                            return (
                              <button
                                key={op.v}
                                onClick={() => marcar(c.id, op.v)}
                                className={
                                  'text-xs font-medium px-2.5 py-1 rounded-md border transition-all ' +
                                  (ativo
                                    ? op.activeClass
                                    : 'border-hipo-border text-hipo-slate hover:bg-hipo-bg hover:text-hipo-ink')
                                }
                              >
                                {op.label}
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
        <div className="px-6 py-3 border-t border-hipo-border flex justify-between items-center">
          <span className="text-sm text-hipo-slate">
            {Object.keys(dirty).length > 0
              ? `${Object.keys(dirty).length} alteração(ões) pendente(s)`
              : 'Sem alterações'}
          </span>
          <div className="flex gap-2">
            <Button variant="secondary" onClick={onFechar}>
              Cancelar
            </Button>
            <Button
              onClick={salvar}
              disabled={salvando || Object.keys(dirty).length === 0}
              loading={salvando}
              icon={!salvando ? Save : undefined}
            >
              {salvando ? 'Salvando...' : 'Salvar'}
            </Button>
          </div>
        </div>
      </div>
    </div>
  );
}
