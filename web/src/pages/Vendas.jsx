// web/src/pages/Vendas.jsx
//
// Módulo Vendas — primeira visualização: Funil de Vendas CROmie.
//
// Classifica as oportunidades ATIVAS pela "régua interna" de utilização
// correta do CROmie. Cada oportunidade aparece como conforme (✓) ou com
// problema (✗ + quais regras falharam), conforme a fase em que está.
//
// IMPORTANTE — esta NÃO é a apuração oficial do PEX:
//   O indicador PEX "Utilização correta do CROmie" cobra tarefa futura
//   apenas em Suspect/Cadência/Qualificação. Por decisão de gestão, esta
//   tela cobra tarefa futura em TODAS as fases ativas — é uma régua
//   interna, mais exigente. O percentual aqui tende a ser menor que o
//   número apurado pela consultoria de campo da Omie. A tela deixa isso
//   explícito para ninguém confundir.
//
// Acesso: mesmo módulo 'clientes' (quem vê Clientes vê Vendas).

import { useState, useEffect, useCallback } from 'react';
import {
  RefreshCw,
  TrendingUp,
  CheckCircle2,
  AlertTriangle,
  Search,
  Info,
} from 'lucide-react';
import api from '../api';

import Card from '../components/ui/Card';
import KpiCard from '../components/ui/KpiCard';
import PageHeader from '../components/ui/PageHeader';
import Button from '../components/ui/Button';
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
  } catch {
    return '—';
  }
}

// Cor do percentual de conformidade — termômetro visual.
function toneDoPct(pct) {
  if (pct >= 100) return 'success';
  if (pct >= 80) return 'warning';
  return 'danger';
}


// ── Componente principal ─────────────────────────────────────────

export default function Vendas() {
  const [dados, setDados] = useState(null); // { itens, resumo, por_fase }
  const [opcoesFiltro, setOpcoesFiltro] = useState({ fases: [], executivos: [] });
  const [loading, setLoading] = useState(false);
  const [msg, setMsg] = useState(null);

  // Filtros
  const [fase, setFase] = useState('');
  const [executivo, setExecutivo] = useState('');
  const [soProblema, setSoProblema] = useState(false);

  // ── Loaders ────────────────────────────────────────────────────

  const carregarFiltros = useCallback(async () => {
    try {
      const { data } = await api.get('/vendas/funil-cromie/filtros');
      setOpcoesFiltro(data);
    } catch {
      setOpcoesFiltro({ fases: [], executivos: [] });
    }
  }, []);

  const carregar = useCallback(async () => {
    setLoading(true);
    setMsg(null);
    try {
      const params = new URLSearchParams();
      if (fase) params.set('fase', fase);
      if (executivo) params.set('executivo', executivo);
      if (soProblema) params.set('so_problema', 'true');
      const { data } = await api.get(`/vendas/funil-cromie?${params}`);
      setDados(data);
    } catch (e) {
      const detail = e.response?.data?.detail;
      const txt = typeof detail === 'string' ? detail : e.message;
      setMsg({ tipo: 'erro', texto: `Erro ao carregar o funil: ${txt}` });
      setDados(null);
    } finally {
      setLoading(false);
    }
  }, [fase, executivo, soProblema]);

  useEffect(() => {
    carregarFiltros();
  }, [carregarFiltros]);

  useEffect(() => {
    carregar();
  }, [carregar]);

  const resumo = dados?.resumo;
  const itens = dados?.itens || [];

  // ── Render ─────────────────────────────────────────────────────

  return (
    <>
      <PageHeader
        title="Vendas"
        subtitle="Funil de Vendas — utilização correta do CROmie."
        actions={
          <Button variant="ghost" onClick={carregar} icon={RefreshCw}>
            Atualizar
          </Button>
        }
      />

      {/* Aviso fixo: esta é a régua interna, não o PEX oficial. */}
      <div className="mb-4 flex items-start gap-2 rounded-lg border border-hipo-border bg-hipo-bg px-4 py-3 text-sm text-hipo-slate">
        <Info size={16} className="mt-0.5 shrink-0 text-hipo-blue" />
        <p>
          <strong className="text-hipo-ink">Régua interna.</strong>{' '}
          Esta tela é mais exigente que o indicador PEX oficial: cobra{' '}
          <strong>tarefa futura em todas as fases</strong>, não só em
          Suspect/Cadência/Qualificação. O percentual abaixo é uma
          ferramenta de correção e tende a ser menor que a apuração da
          consultoria de campo da Omie.
        </p>
      </div>

      {msg && (
        <AlertMessage tipo={msg.tipo} className="mb-4">
          {msg.texto}
        </AlertMessage>
      )}

      {/* KPIs */}
      {resumo && (
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-6">
          <KpiCard
            label="Conformidade interna"
            value={`${resumo.pct_conforme.toLocaleString('pt-BR')}%`}
            Icon={TrendingUp}
            tone={toneDoPct(resumo.pct_conforme)}
          />
          <KpiCard
            label="Oportunidades conformes"
            value={resumo.conformes.toLocaleString('pt-BR')}
            Icon={CheckCircle2}
            tone="success"
          />
          <KpiCard
            label="Com problema"
            value={resumo.nao_conformes.toLocaleString('pt-BR')}
            Icon={AlertTriangle}
            tone={resumo.nao_conformes > 0 ? 'danger' : 'success'}
          />
          <KpiCard
            label="Oportunidades ativas"
            value={resumo.total_analisadas.toLocaleString('pt-BR')}
            Icon={TrendingUp}
            tone="info"
          />
        </div>
      )}

      <Card>
        {/* Filtros */}
        <div className="flex flex-wrap items-center gap-2 mb-4">
          <select
            value={fase}
            onChange={(e) => setFase(e.target.value)}
            className="h-10 px-3 rounded-lg border border-hipo-border bg-hipo-card text-sm text-hipo-ink"
          >
            <option value="">Todas as fases</option>
            {opcoesFiltro.fases.map((f) => (
              <option key={f} value={f}>
                {f}
              </option>
            ))}
          </select>

          <select
            value={executivo}
            onChange={(e) => setExecutivo(e.target.value)}
            className="h-10 px-3 rounded-lg border border-hipo-border bg-hipo-card text-sm text-hipo-ink"
          >
            <option value="">Todos os executivos</option>
            {opcoesFiltro.executivos.map((ex) => (
              <option key={ex} value={ex}>
                {ex}
              </option>
            ))}
          </select>

          <label className="flex items-center gap-2 text-sm text-hipo-slate cursor-pointer select-none px-2">
            <input
              type="checkbox"
              checked={soProblema}
              onChange={(e) => setSoProblema(e.target.checked)}
              className="w-4 h-4 accent-hipo-blue cursor-pointer"
            />
            Só com problema
          </label>

          {(fase || executivo || soProblema) && (
            <Button
              variant="ghost"
              onClick={() => {
                setFase('');
                setExecutivo('');
                setSoProblema(false);
              }}
            >
              Limpar filtros
            </Button>
          )}
        </div>

        {loading ? (
          <p className="text-sm text-hipo-slate text-center py-8">
            Carregando oportunidades...
          </p>
        ) : itens.length === 0 ? (
          <Empty
            Icon={CheckCircle2}
            title={
              soProblema
                ? 'Nenhuma oportunidade com problema'
                : 'Nenhuma oportunidade ativa'
            }
            description={
              soProblema
                ? 'Com os filtros atuais, todas as oportunidades estão conformes.'
                : 'Faça upload da planilha de Oportunidades no módulo Clientes.'
            }
          />
        ) : (
          <>
            <p className="text-xs text-hipo-slate mb-2">
              {itens.length.toLocaleString('pt-BR')} oportunidade(s) exibida(s)
            </p>
            <Table>
              <thead>
                <Tr>
                  <Th>Razão Social / CNPJ</Th>
                  <Th>Fase</Th>
                  <Th>Executivo</Th>
                  <Th align="center">Situação</Th>
                  <Th>Pendências</Th>
                  <Th align="right">Atualizada</Th>
                </Tr>
              </thead>
              <tbody>
                {itens.map((o) => {
                  const cls = o.classificacao;
                  return (
                    <Tr key={o.op_id} hover>
                      <Td>
                        <div className="font-medium text-hipo-ink">
                          {o.razao_social || '—'}
                        </div>
                        <div className="text-xs text-hipo-muted font-mono">
                          {o.cnpj}
                        </div>
                      </Td>
                      <Td className="text-hipo-slate whitespace-nowrap">
                        {o.fase || '—'}
                      </Td>
                      <Td className="text-hipo-slate">
                        {o.executivo_vendas || '—'}
                      </Td>
                      <Td align="center">
                        {cls.conforme ? (
                          <Badge tone="success">✓ Conforme</Badge>
                        ) : (
                          <Badge tone="danger">✗ Problema</Badge>
                        )}
                      </Td>
                      <Td>
                        {cls.conforme ? (
                          <span className="text-xs text-hipo-muted">—</span>
                        ) : (
                          <div className="flex flex-wrap gap-1">
                            {cls.problemas_rotulos.map((p) => (
                              <span
                                key={p}
                                className="text-[11px] font-medium px-1.5 py-0.5 rounded
                                           bg-hipo-dangerSoft text-hipo-danger"
                              >
                                {p}
                              </span>
                            ))}
                          </div>
                        )}
                      </Td>
                      <Td align="right" className="whitespace-nowrap text-hipo-slate">
                        {fmtData(o.data_atualizacao)}
                      </Td>
                    </Tr>
                  );
                })}
              </tbody>
            </Table>
          </>
        )}
      </Card>
    </>
  );
}
