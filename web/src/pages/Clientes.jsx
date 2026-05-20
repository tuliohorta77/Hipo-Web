// web/src/pages/Clientes.jsx
//
// Modulo Clientes: oportunidades + tarefas dos leads.
//
// 2 uploads independentes:
//   - Oportunidades: snapshot completo da base de leads do CRM
//   - Tarefas:       snapshot completo das atividades dos leads
//
// Abas:
//   - Oportunidades (tabela paginada com filtros)
//   - Tarefas       (tabela paginada com filtros)
//
// Acesso: ADM, Franqueado, Gerente, EP.

import { useState, useEffect, useCallback } from 'react';
import {
  RefreshCw,
  Users,
  Target,
  ListChecks,
  AlertCircle,
  Search,
  Upload,
} from 'lucide-react';
import api from '../api';

import Card from '../components/ui/Card';
import KpiCard from '../components/ui/KpiCard';
import PageHeader from '../components/ui/PageHeader';
import Button from '../components/ui/Button';
import UploadButton from '../components/ui/UploadButton';
import AlertMessage from '../components/ui/AlertMessage';
import Empty from '../components/ui/Empty';
import Badge from '../components/ui/Badge';
import Input from '../components/ui/Input';
import Table, { Th, Tr, Td } from '../components/ui/Table';


// ── Helpers ──────────────────────────────────────────────────────

function fmtData(d) {
  if (!d) return '—';
  try {
    return new Date(d).toLocaleDateString('pt-BR');
  } catch { return '—'; }
}

function fmtMoeda(v) {
  if (v == null) return '—';
  return Number(v).toLocaleString('pt-BR', {
    style: 'currency', currency: 'BRL', maximumFractionDigits: 0,
  });
}

function badgeStatus(s) {
  const v = (s || '').toLowerCase();
  if (v === 'em andamento') return 'info';
  if (v === 'conquistado')  return 'success';
  if (v === 'perdido')      return 'danger';
  return 'default';
}

function badgeSituacao(s) {
  const v = (s || '').toLowerCase();
  if (v === 'atrasada') return 'danger';
  if (v === 'em dia')   return 'success';
  return 'default';
}


// ── Componente principal ─────────────────────────────────────────

export default function Clientes() {
  const [resumo, setResumo] = useState(null);
  const [aba, setAba] = useState('OPORTUNIDADES');
  const [uploading, setUploading] = useState(null); // null | "OPORTUNIDADES" | "TAREFAS"
  const [msg, setMsg] = useState(null);

  // Listagens
  const [ops, setOps] = useState({ total: 0, items: [], page: 1, page_size: 50 });
  const [tarefas, setTarefas] = useState({ total: 0, items: [], page: 1, page_size: 50 });

  // Filtros
  const [filtroOps, setFiltroOps] = useState({ q: '', status: '', fase: '', origem_macro: '' });
  const [filtroTar, setFiltroTar] = useState({ q: '', canal: '', situacao: '', status: '' });

  // ── Loaders ────────────────────────────────────────────────────

  const carregarResumo = useCallback(async () => {
    try {
      const { data } = await api.get('/clientes/resumo');
      setResumo(data);
    } catch (e) {
      setMsg({ tipo: 'erro', texto: `Erro ao carregar resumo: ${e.message}` });
    }
  }, []);

  const carregarOps = useCallback(async (page = 1) => {
    try {
      const params = new URLSearchParams();
      if (filtroOps.q) params.set('q', filtroOps.q);
      if (filtroOps.status) params.set('status', filtroOps.status);
      if (filtroOps.fase) params.set('fase', filtroOps.fase);
      if (filtroOps.origem_macro) params.set('origem_macro', filtroOps.origem_macro);
      params.set('page', page);
      const { data } = await api.get(`/clientes/oportunidades?${params}`);
      setOps(data);
    } catch (e) {
      setMsg({ tipo: 'erro', texto: `Erro: ${e.message}` });
    }
  }, [filtroOps]);

  const carregarTarefas = useCallback(async (page = 1) => {
    try {
      const params = new URLSearchParams();
      if (filtroTar.q) params.set('q', filtroTar.q);
      if (filtroTar.canal) params.set('canal', filtroTar.canal);
      if (filtroTar.situacao) params.set('situacao', filtroTar.situacao);
      if (filtroTar.status) params.set('status', filtroTar.status);
      params.set('page', page);
      const { data } = await api.get(`/clientes/tarefas?${params}`);
      setTarefas(data);
    } catch (e) {
      setMsg({ tipo: 'erro', texto: `Erro: ${e.message}` });
    }
  }, [filtroTar]);

  useEffect(() => { carregarResumo(); }, [carregarResumo]);
  useEffect(() => {
    if (aba === 'OPORTUNIDADES') carregarOps(1);
    else carregarTarefas(1);
  }, [aba, carregarOps, carregarTarefas]);

  // ── Upload ─────────────────────────────────────────────────────

  async function handleUpload(tipo, file) {
    setUploading(tipo);
    setMsg(null);
    try {
      const fd = new FormData();
      fd.append('arquivo', file);
      const endpoint = tipo === 'OPORTUNIDADES'
        ? '/clientes/upload-oportunidades'
        : '/clientes/upload-tarefas';
      const { data } = await api.post(endpoint, fd);
      setMsg({
        tipo: 'sucesso',
        texto: `Upload OK — ${data.total_validos} de ${data.total_linhas} linhas processadas${
          data.erros?.length ? ` (${data.erros.length} avisos)` : ''
        }.`,
      });
      await carregarResumo();
      if (tipo === 'OPORTUNIDADES') await carregarOps(1);
      else await carregarTarefas(1);
    } catch (e) {
      const detail = e.response?.data?.detail;
      const txt = typeof detail === 'string' ? detail
                : detail?.message || e.message;
      setMsg({ tipo: 'erro', texto: `Falha no upload: ${txt}` });
    } finally {
      setUploading(null);
    }
  }

  // ── Render ─────────────────────────────────────────────────────

  return (
    <>
      <PageHeader
        title="Clientes"
        subtitle="Oportunidades comerciais e tarefas dos leads."
        actions={
          <div className="flex gap-2">
            <UploadButton
              label="Oportunidades"
              accept=".xlsx"
              loading={uploading === 'OPORTUNIDADES'}
              onChange={(e) => handleUpload('OPORTUNIDADES', e.target.files[0])}
            />
            <UploadButton
              label="Tarefas"
              accept=".xlsx"
              loading={uploading === 'TAREFAS'}
              onChange={(e) => handleUpload('TAREFAS', e.target.files[0])}
            />
            <Button
              variant="ghost"
              onClick={() => { carregarResumo(); if (aba === 'OPORTUNIDADES') carregarOps(1); else carregarTarefas(1); }}
              icon={RefreshCw}
            >
              Atualizar
            </Button>
          </div>
        }
      />

      {msg && <AlertMessage tipo={msg.tipo} className="mb-4">{msg.texto}</AlertMessage>}

      {/* KPIs */}
      {resumo && (
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-6">
          <KpiCard
            label="Total de Oportunidades"
            value={(resumo?.oportunidades?.total ?? 0).toLocaleString('pt-BR')}
            Icon={Target}
            tone="info"
          />
          <KpiCard
            label="Em andamento"
            value={(resumo?.oportunidades?.em_andamento ?? 0).toLocaleString('pt-BR')}
            Icon={Target}
            tone="info"
          />
          <KpiCard
            label="Conquistadas"
            value={(resumo?.oportunidades?.conquistado ?? 0).toLocaleString('pt-BR')}
            Icon={Target}
            tone="success"
          />
          <KpiCard
            label="Tarefas Atrasadas"
            value={(resumo?.tarefas?.atrasada ?? 0).toLocaleString('pt-BR')}
            Icon={AlertCircle}
            tone="danger"
          />
        </div>
      )}

      {/* Tabs */}
      <div className="flex border-b border-hipo-border mb-4">
        <button
          onClick={() => setAba('OPORTUNIDADES')}
          className={`px-4 py-2.5 text-sm font-medium border-b-2 transition-colors ${
            aba === 'OPORTUNIDADES'
              ? 'border-hipo-blue text-hipo-blue'
              : 'border-transparent text-hipo-slate hover:text-hipo-ink'
          }`}
        >
          <span className="flex items-center gap-2">
            <Target size={16} />
            Oportunidades
          </span>
        </button>
        <button
          onClick={() => setAba('TAREFAS')}
          className={`px-4 py-2.5 text-sm font-medium border-b-2 transition-colors ${
            aba === 'TAREFAS'
              ? 'border-hipo-blue text-hipo-blue'
              : 'border-transparent text-hipo-slate hover:text-hipo-ink'
          }`}
        >
          <span className="flex items-center gap-2">
            <ListChecks size={16} />
            Tarefas
          </span>
        </button>
      </div>

      {/* Aba OPORTUNIDADES */}
      {aba === 'OPORTUNIDADES' && (
        <Card>
          {/* Filtros */}
          <div className="flex flex-wrap gap-2 mb-4">
            <div className="flex-1 min-w-[200px]">
              <Input
                placeholder="Buscar por razão social ou CNPJ..."
                value={filtroOps.q}
                onChange={(e) => setFiltroOps({ ...filtroOps, q: e.target.value })}
                onKeyDown={(e) => { if (e.key === 'Enter') carregarOps(1); }}
                icon={Search}
              />
            </div>
            <select
              value={filtroOps.status}
              onChange={(e) => { setFiltroOps({ ...filtroOps, status: e.target.value }); setTimeout(() => carregarOps(1), 0); }}
              className="h-10 px-3 rounded-lg border border-hipo-border bg-hipo-card text-sm text-hipo-ink"
            >
              <option value="">Todos os status</option>
              <option value="Em andamento">Em andamento</option>
              <option value="Conquistado">Conquistado</option>
              <option value="Perdido">Perdido</option>
              <option value="Cancelado">Cancelado</option>
            </select>
            <select
              value={filtroOps.origem_macro}
              onChange={(e) => { setFiltroOps({ ...filtroOps, origem_macro: e.target.value }); setTimeout(() => carregarOps(1), 0); }}
              className="h-10 px-3 rounded-lg border border-hipo-border bg-hipo-card text-sm text-hipo-ink"
            >
              <option value="">Todas as origens</option>
              <option value="Inbound">Inbound</option>
              <option value="Outbound">Outbound</option>
            </select>
            <Button variant="ghost" onClick={() => carregarOps(1)} icon={Search}>
              Filtrar
            </Button>
          </div>

          {ops.items.length === 0 ? (
            <Empty
              Icon={Target}
              title="Nenhuma oportunidade"
              description="Faça upload da planilha de Oportunidades exportada do CRM."
            />
          ) : (
            <>
              <p className="text-xs text-hipo-slate mb-2">
                {ops.total.toLocaleString('pt-BR')} oportunidades — página {ops.page}
              </p>
              <Table>
                <thead>
                  <Tr>
                    <Th>Razão Social / CNPJ</Th>
                    <Th>Status</Th>
                    <Th>Fase</Th>
                    <Th>Contador</Th>
                    <Th align="right">Previsão</Th>
                    <Th align="right">Dias parado</Th>
                  </Tr>
                </thead>
                <tbody>
                  {ops.items.map((o) => (
                    <Tr key={o.op_id} hover>
                      <Td>
                        <div className="font-medium text-hipo-ink">{o.razao_social || '—'}</div>
                        <div className="text-xs text-hipo-muted font-mono">{o.cnpj}</div>
                      </Td>
                      <Td><Badge tone={badgeStatus(o.status)}>{o.status || '—'}</Badge></Td>
                      <Td className="text-hipo-slate">{o.fase || '—'}</Td>
                      <Td>
                        <div className="text-sm text-hipo-ink">{o.razao_contador || '—'}</div>
                        <div className="text-xs text-hipo-muted font-mono">{o.cnpj_contador || '—'}</div>
                      </Td>
                      <Td align="right">{fmtMoeda(o.previsao_valor)}</Td>
                      <Td align="right">{o.dias_parado != null ? `${o.dias_parado}d` : '—'}</Td>
                    </Tr>
                  ))}
                </tbody>
              </Table>

              {/* Paginação */}
              {ops.total > ops.page_size && (
                <div className="flex justify-between items-center mt-4 text-sm">
                  <span className="text-hipo-slate">
                    Página {ops.page} de {Math.ceil(ops.total / ops.page_size)}
                  </span>
                  <div className="flex gap-2">
                    <Button
                      variant="ghost"
                      disabled={ops.page <= 1}
                      onClick={() => carregarOps(ops.page - 1)}
                    >
                      Anterior
                    </Button>
                    <Button
                      variant="ghost"
                      disabled={ops.page >= Math.ceil(ops.total / ops.page_size)}
                      onClick={() => carregarOps(ops.page + 1)}
                    >
                      Próxima
                    </Button>
                  </div>
                </div>
              )}
            </>
          )}
        </Card>
      )}

      {/* Aba TAREFAS */}
      {aba === 'TAREFAS' && (
        <Card>
          {/* Filtros */}
          <div className="flex flex-wrap gap-2 mb-4">
            <div className="flex-1 min-w-[200px]">
              <Input
                placeholder="Buscar por razão social ou CNPJ..."
                value={filtroTar.q}
                onChange={(e) => setFiltroTar({ ...filtroTar, q: e.target.value })}
                onKeyDown={(e) => { if (e.key === 'Enter') carregarTarefas(1); }}
                icon={Search}
              />
            </div>
            <select
              value={filtroTar.situacao}
              onChange={(e) => { setFiltroTar({ ...filtroTar, situacao: e.target.value }); setTimeout(() => carregarTarefas(1), 0); }}
              className="h-10 px-3 rounded-lg border border-hipo-border bg-hipo-card text-sm text-hipo-ink"
            >
              <option value="">Todas as situações</option>
              <option value="Em dia">Em dia</option>
              <option value="Atrasada">Atrasada</option>
              <option value="Futura">Futura</option>
            </select>
            <select
              value={filtroTar.canal}
              onChange={(e) => { setFiltroTar({ ...filtroTar, canal: e.target.value }); setTimeout(() => carregarTarefas(1), 0); }}
              className="h-10 px-3 rounded-lg border border-hipo-border bg-hipo-card text-sm text-hipo-ink"
            >
              <option value="">Todos os canais</option>
              <option value="Telefone">Telefone</option>
              <option value="WhatsApp">WhatsApp</option>
              <option value="Email">Email</option>
              <option value="Online">Online</option>
            </select>
            <Button variant="ghost" onClick={() => carregarTarefas(1)} icon={Search}>
              Filtrar
            </Button>
          </div>

          {tarefas.items.length === 0 ? (
            <Empty
              Icon={ListChecks}
              title="Nenhuma tarefa"
              description="Faça upload da planilha de Tarefas exportada do CRM."
            />
          ) : (
            <>
              <p className="text-xs text-hipo-slate mb-2">
                {tarefas.total.toLocaleString('pt-BR')} tarefas — página {tarefas.page}
              </p>
              <Table>
                <thead>
                  <Tr>
                    <Th>Data</Th>
                    <Th>Razão Social</Th>
                    <Th>Finalidade</Th>
                    <Th>Canal</Th>
                    <Th>Situação</Th>
                    <Th>Status</Th>
                    <Th>Usuário</Th>
                  </Tr>
                </thead>
                <tbody>
                  {tarefas.items.map((t) => (
                    <Tr key={t.tarefa_id} hover>
                      <Td className="whitespace-nowrap">{fmtData(t.data_agendamento)}</Td>
                      <Td>
                        <div className="font-medium text-hipo-ink">{t.razao_social || '—'}</div>
                        <div className="text-xs text-hipo-muted font-mono">{t.cnpj}</div>
                      </Td>
                      <Td className="text-hipo-slate">{t.finalidade || '—'}</Td>
                      <Td className="text-hipo-slate">{t.canal || '—'}</Td>
                      <Td><Badge tone={badgeSituacao(t.situacao_tarefa)}>{t.situacao_tarefa || '—'}</Badge></Td>
                      <Td className="text-hipo-slate">{t.status || '—'}</Td>
                      <Td className="text-hipo-slate">{t.usuario_atribuido || '—'}</Td>
                    </Tr>
                  ))}
                </tbody>
              </Table>

              {tarefas.total > tarefas.page_size && (
                <div className="flex justify-between items-center mt-4 text-sm">
                  <span className="text-hipo-slate">
                    Página {tarefas.page} de {Math.ceil(tarefas.total / tarefas.page_size)}
                  </span>
                  <div className="flex gap-2">
                    <Button
                      variant="ghost"
                      disabled={tarefas.page <= 1}
                      onClick={() => carregarTarefas(tarefas.page - 1)}
                    >
                      Anterior
                    </Button>
                    <Button
                      variant="ghost"
                      disabled={tarefas.page >= Math.ceil(tarefas.total / tarefas.page_size)}
                      onClick={() => carregarTarefas(tarefas.page + 1)}
                    >
                      Próxima
                    </Button>
                  </div>
                </div>
              )}
            </>
          )}
        </Card>
      )}

      {/* Info do último upload */}
      {resumo && (resumo.ultimo_upload_oportunidades || resumo.ultimo_upload_tarefas) && (
        <div className="mt-4 text-xs text-hipo-muted text-center space-y-1">
          {resumo.ultimo_upload_oportunidades && (
            <p>
              Último upload de Oportunidades:{' '}
              {new Date(resumo.ultimo_upload_oportunidades.data_upload).toLocaleString('pt-BR')}
              {' — '}{(resumo.ultimo_upload_oportunidades.total_validos ?? 0).toLocaleString('pt-BR')} linhas
            </p>
          )}
          {resumo.ultimo_upload_tarefas && (
            <p>
              Último upload de Tarefas:{' '}
              {new Date(resumo.ultimo_upload_tarefas.data_upload).toLocaleString('pt-BR')}
              {' — '}{(resumo.ultimo_upload_tarefas.total_validos ?? 0).toLocaleString('pt-BR')} linhas
            </p>
          )}
        </div>
      )}
    </>
  );
}
