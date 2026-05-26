// web/src/components/ConfigColaboradoresModal.jsx
//
// Modal para classificar colaboradores como EC_HUNTER, EC_FARMER ou OUTROS
// e VINCULAR cada colaborador a um usuário do sistema (v1.3.0 etapa 3).
//
// O vínculo usuário<->colaborador (carteira_colaborador.usuario_id) é o que
// faz a visibilidade por colaborador funcionar: um Hunter/Farmer logado só
// enxerga a carteira do colaborador vinculado ao seu usuário.
//
// Persistência: PUT /carteira/colaboradores/:id
//   - body { funcao }                    -> só muda a função
//   - body { funcao, usuario_id }        -> também grava/limpa o vínculo
//   O backend distingue "campo ausente" (preserva vínculo) de "null"
//   (desvincula). Por isso só enviamos usuario_id quando o gestor mexeu
//   no dropdown daquela linha.
//
// Cardinalidade 1:1: um usuário só pode estar vinculado a um colaborador.
// O dropdown mostra todos os usuários ativos; os já vinculados a OUTRO
// colaborador aparecem com sufixo "(já em: Nome)". Se o gestor escolher
// um já ocupado, o backend devolve 409 e a mensagem é exibida.

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

// Valor especial do <select> que representa "sem usuário vinculado".
const SEM_USUARIO = '';

export default function ConfigColaboradoresModal({ aberto, onFechar, onSalvo }) {
  const [colaboradores, setColaboradores] = useState([]);
  const [usuarios, setUsuarios] = useState([]);
  const [busca, setBusca] = useState('');
  // dirty[id] = { funcao?, usuario_id? } — só as chaves que o gestor mexeu.
  const [dirty, setDirty] = useState({});
  const [salvando, setSalvando] = useState(false);
  const [msg, setMsg] = useState(null);

  useEffect(() => {
    if (!aberto) return;
    setMsg(null);
    setDirty({});
    setBusca('');
    // Carrega colaboradores + usuários ativos em paralelo.
    Promise.all([
      api.get('/carteira/colaboradores'),
      api.get('/carteira/usuarios-ativos'),
    ])
      .then(([rColab, rUsr]) => {
        setColaboradores(rColab.data || []);
        setUsuarios(rUsr.data || []);
      })
      .catch(() => {
        setColaboradores([]);
        setUsuarios([]);
        setMsg({
          tipo: 'erro',
          texto: 'Erro ao carregar colaboradores ou usuários.',
        });
      });
  }, [aberto]);

  const filtrados = useMemo(() => {
    const n = busca.trim().toLowerCase();
    if (!n) return colaboradores;
    return colaboradores.filter((c) => c.nome.toLowerCase().includes(n));
  }, [colaboradores, busca]);

  // Mapa usuario_id -> nome do colaborador que já o usa (estado salvo no
  // servidor). Serve para marcar "(já em: Nome)" no dropdown — opção (b).
  const usuarioOcupadoPor = useMemo(() => {
    const mapa = {};
    for (const c of colaboradores) {
      if (c.usuario_id) mapa[c.usuario_id] = c.nome;
    }
    return mapa;
  }, [colaboradores]);

  // Valor atual da função de um colaborador (considerando edições pendentes).
  function funcaoDe(c) {
    return dirty[c.id]?.funcao ?? c.funcao;
  }

  // Valor atual do vínculo (usuario_id) de um colaborador.
  // Retorna string (UUID) ou SEM_USUARIO ('').
  function usuarioDe(c) {
    const d = dirty[c.id];
    if (d && 'usuario_id' in d) {
      return d.usuario_id ?? SEM_USUARIO;
    }
    return c.usuario_id ?? SEM_USUARIO;
  }

  function marcarFuncao(id, funcao) {
    setDirty((prev) => ({
      ...prev,
      [id]: { ...prev[id], funcao },
    }));
  }

  function marcarUsuario(id, valor) {
    // valor vem do <select>: '' = sem usuário; senão é o UUID.
    setDirty((prev) => ({
      ...prev,
      [id]: { ...prev[id], usuario_id: valor === SEM_USUARIO ? null : valor },
    }));
  }

  async function salvar() {
    const entradas = Object.entries(dirty);
    if (entradas.length === 0) {
      onFechar();
      return;
    }
    setSalvando(true);
    setMsg(null);

    const results = await Promise.allSettled(
      entradas.map(([id, mud]) => {
        // Monta o body. funcao é sempre obrigatório no PUT — se o gestor
        // só mexeu no vínculo, mandamos a função atual do colaborador.
        const colab = colaboradores.find((c) => c.id === id);
        const body = { funcao: mud.funcao ?? colab?.funcao };
        // usuario_id só entra no body se o dropdown foi tocado.
        if ('usuario_id' in mud) {
          body.usuario_id = mud.usuario_id; // string (UUID) ou null
        }
        return api.put(`/carteira/colaboradores/${id}`, body);
      })
    );

    const ok = results.filter((r) => r.status === 'fulfilled').length;
    const falhas = results.filter((r) => r.status === 'rejected');

    if (falhas.length === 0) {
      setMsg({ tipo: 'ok', texto: `${ok} colaborador(es) atualizado(s).` });
      if (onSalvo) onSalvo();
      setTimeout(onFechar, 600);
    } else {
      // Extrai a 1ª mensagem de erro útil (ex: 409 de usuário já vinculado).
      const primeiroDetalhe =
        falhas
          .map((f) => f.reason?.response?.data?.detail)
          .find((d) => typeof d === 'string') || 'Erro ao salvar.';
      setMsg({
        tipo: 'aviso',
        texto:
          `${ok} salvo(s), ${falhas.length} com erro. ` + primeiroDetalhe,
      });
      if (ok > 0 && onSalvo) onSalvo();
    }
    setSalvando(false);
  }

  if (!aberto) return null;

  const qtdPendente = Object.keys(dirty).length;

  return (
    <div
      className="fixed inset-0 bg-hipo-ink/40 z-50 flex items-center justify-center p-4"
      onClick={onFechar}
    >
      <div
        className="bg-hipo-card border border-hipo-border rounded-2xl w-full max-w-4xl max-h-[85vh] flex flex-col shadow-soft"
        onClick={(e) => e.stopPropagation()}
      >
        {/* Header */}
        <div className="px-6 py-4 border-b border-hipo-border flex items-center justify-between">
          <div>
            <h2 className="text-h2 text-hipo-ink">Configurar colaboradores</h2>
            <p className="text-sm text-hipo-slate mt-0.5">
              Classifique a função e vincule cada colaborador ao usuário do
              sistema. O vínculo define o que cada Hunter/Farmer enxerga.
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
                    Usuário vinculado
                  </th>
                  <th className="text-right py-2.5 px-2 font-medium">
                    Classificação Hipo
                  </th>
                </tr>
              </thead>
              <tbody>
                {filtrados.map((c) => {
                  const funcaoAtual = funcaoDe(c);
                  const usuarioAtual = usuarioDe(c);
                  const semVinculo = usuarioAtual === SEM_USUARIO;
                  return (
                    <tr
                      key={c.id}
                      className="border-b border-hipo-border last:border-0 hover:bg-hipo-bg/60"
                    >
                      {/* Nome + função de origem */}
                      <td className="py-3 px-2">
                        <div className="font-medium text-hipo-ink">
                          {c.nome}
                        </div>
                        <div className="text-xs text-hipo-slate">
                          {c.funcao_origem || '—'}
                        </div>
                      </td>

                      {/* Dropdown de vínculo */}
                      <td className="py-3 px-2">
                        <select
                          value={usuarioAtual}
                          onChange={(e) => marcarUsuario(c.id, e.target.value)}
                          className={
                            'w-full max-w-[260px] h-9 px-2 rounded-md border bg-hipo-card ' +
                            'text-sm outline-none focus:border-hipo-blue focus:ring-2 focus:ring-blue-100 ' +
                            (semVinculo
                              ? 'border-hipo-border text-hipo-slate'
                              : 'border-hipo-border text-hipo-ink')
                          }
                        >
                          <option value={SEM_USUARIO}>
                            — sem usuário —
                          </option>
                          {usuarios.map((u) => {
                            // Marca usuários já vinculados a OUTRO colaborador.
                            const ocupadoPor = usuarioOcupadoPor[u.id];
                            const ehOutro =
                              ocupadoPor && ocupadoPor !== c.nome;
                            return (
                              <option key={u.id} value={u.id}>
                                {u.email}
                                {ehOutro ? ` (já em: ${ocupadoPor})` : ''}
                              </option>
                            );
                          })}
                        </select>
                        {semVinculo && (
                          <div className="text-[11px] text-hipo-warning mt-1">
                            sem usuário — este colaborador não aparece para
                            nenhum Hunter/Farmer
                          </div>
                        )}
                      </td>

                      {/* Botões de classificação */}
                      <td className="py-3 px-2">
                        <div className="flex gap-1 justify-end">
                          {OPCOES.map((op) => {
                            const ativo = funcaoAtual === op.v;
                            return (
                              <button
                                key={op.v}
                                onClick={() => marcarFuncao(c.id, op.v)}
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
            {qtdPendente > 0
              ? `${qtdPendente} alteração(ões) pendente(s)`
              : 'Sem alterações'}
          </span>
          <div className="flex gap-2">
            <Button variant="secondary" onClick={onFechar}>
              Cancelar
            </Button>
            <Button
              onClick={salvar}
              disabled={salvando || qtdPendente === 0}
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
