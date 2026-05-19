// web/src/components/CarteiraGrupoDrawer.jsx
//
// Drawer lateral com drill-down de um grupo: lista de CNPJs + últimas tarefas.

import { useEffect, useState } from 'react';
import { X, Building2, ListChecks, MapPin, Users } from 'lucide-react';
import api from '../api';
import Badge from './ui/Badge';
import Empty from './ui/Empty';
import Table, { Th, Tr, Td } from './ui/Table';

function toneParceria(p) {
  if (p === 'Parceiro')      return 'success';
  if (p === 'Não Parceiro')  return 'neutral';
  return 'neutral';
}

function toneSituacao(s) {
  if (s === 'ATRASADA') return 'danger';
  if (s === 'FUTURA')   return 'info';
  if (s === 'EM_DIA')   return 'success';
  return 'neutral';
}

function fmtDate(d) {
  if (!d) return '—';
  try {
    return new Date(d).toLocaleString('pt-BR', {
      day: '2-digit',
      month: '2-digit',
      year: 'numeric',
      hour: '2-digit',
      minute: '2-digit',
    });
  } catch {
    return '—';
  }
}

export default function CarteiraGrupoDrawer({ idGrupo, onFechar, nomeGrupo }) {
  const [detalhe, setDetalhe] = useState(null);
  const [loading, setLoading] = useState(false);
  const [erro, setErro] = useState(null);

  useEffect(() => {
    if (!idGrupo) return;
    setLoading(true);
    setErro(null);
    setDetalhe(null);
    api
      .get(`/carteira/grupos/${encodeURIComponent(idGrupo)}`)
      .then((r) => setDetalhe(r.data))
      .catch((e) => setErro(e.response?.data?.detail || e.message))
      .finally(() => setLoading(false));
  }, [idGrupo]);

  if (!idGrupo) return null;

  return (
    <div
      className="fixed inset-0 z-40 flex"
      onClick={onFechar}
      role="dialog"
      aria-modal="true"
    >
      <div className="flex-1 bg-hipo-ink/40" />
      <aside
        className="w-full max-w-2xl bg-hipo-bg border-l border-hipo-border overflow-y-auto"
        onClick={(e) => e.stopPropagation()}
      >
        {/* Header */}
        <div className="sticky top-0 z-10 bg-hipo-card border-b border-hipo-border px-6 py-4 flex items-center justify-between">
          <div className="min-w-0">
            <h2 className="text-h2 text-hipo-ink truncate">
              {nomeGrupo || 'Grupo'}
            </h2>
            <p className="text-xs text-hipo-muted mt-0.5 font-mono">
              {idGrupo}
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

        {/* Conteúdo */}
        <div className="p-6 space-y-6">
          {loading && (
            <p className="text-sm text-hipo-slate">Carregando...</p>
          )}
          {erro && (
            <div className="text-sm text-hipo-danger bg-red-50 border border-red-100 rounded-lg p-3">
              {erro}
            </div>
          )}

          {detalhe && (
            <>
              {/* CNPJs do grupo */}
              <section>
                <div className="flex items-center gap-2 mb-3">
                  <Building2 size={16} className="text-hipo-blue" />
                  <h3 className="text-sm font-semibold text-hipo-ink">
                    CNPJs ({detalhe.qtd_cnpj})
                  </h3>
                </div>
                <div className="space-y-2">
                  {detalhe.cnpjs.map((c, i) => (
                    <div
                      key={c.cnpj_contador || i}
                      className="bg-hipo-card border border-hipo-border rounded-lg p-3 shadow-soft"
                    >
                      <div className="flex items-start justify-between gap-3 mb-1">
                        <span className="text-sm font-semibold text-hipo-ink">
                          {c.contabilidade || '—'}
                        </span>
                        <Badge tone={toneParceria(c.parceria)}>
                          {c.parceria || '—'}
                        </Badge>
                      </div>
                      <p className="text-xs text-hipo-muted font-mono">
                        {c.cnpj_contador}
                      </p>
                      <div className="flex items-center gap-4 mt-2 text-xs text-hipo-slate flex-wrap">
                        {c.cidade_uf && (
                          <span className="flex items-center gap-1">
                            <MapPin size={12} /> {c.cidade_uf}
                          </span>
                        )}
                        {c.colaborador_nome && (
                          <span className="flex items-center gap-1">
                            <Users size={12} /> {c.colaborador_nome}
                          </span>
                        )}
                        {c.apps_ativos != null && (
                          <span>{c.apps_ativos} apps ativos</span>
                        )}
                        {c.leads_no_mes != null && c.leads_no_mes > 0 && (
                          <span className="text-hipo-blue font-medium">
                            {c.leads_no_mes} leads/mês
                          </span>
                        )}
                      </div>
                    </div>
                  ))}
                </div>
              </section>

              {/* Tarefas */}
              <section>
                <div className="flex items-center gap-2 mb-3">
                  <ListChecks size={16} className="text-hipo-blue" />
                  <h3 className="text-sm font-semibold text-hipo-ink">
                    Tarefas ({detalhe.tarefas.length})
                  </h3>
                </div>
                {detalhe.tarefas.length === 0 ? (
                  <Empty
                    title="Sem tarefas"
                    description="Nenhuma tarefa registrada para esse grupo."
                  />
                ) : (
                  <div className="bg-hipo-card border border-hipo-border rounded-lg shadow-soft overflow-hidden">
                    <Table>
                      <thead>
                        <tr>
                          <Th>Data</Th>
                          <Th>Canal</Th>
                          <Th>Tipo</Th>
                          <Th>Situação</Th>
                          <Th>Executivo</Th>
                        </tr>
                      </thead>
                      <tbody>
                        {detalhe.tarefas.map((t, i) => (
                          <Tr key={i}>
                            <Td className="whitespace-nowrap text-hipo-slate">
                              {fmtDate(t.data_efetiva)}
                            </Td>
                            <Td>{t.tarefa_canal || '—'}</Td>
                            <Td className="text-hipo-slate">
                              {t.tipo_tarefa || '—'}
                            </Td>
                            <Td>
                              <Badge tone={toneSituacao(t.situacao)}>
                                {t.situacao}
                              </Badge>
                            </Td>
                            <Td className="text-hipo-slate">
                              {t.executivo_nome || '—'}
                            </Td>
                          </Tr>
                        ))}
                      </tbody>
                    </Table>
                  </div>
                )}
              </section>
            </>
          )}
        </div>
      </aside>
    </div>
  );
}
