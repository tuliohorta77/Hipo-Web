// web/src/pages/Agendamento.jsx
//
// Módulo Agendamento (cargo SDR). v1.3.1 — primeira versão.
//
// Esta v1 REPLICA a aba Conformidade do módulo Vendas: a régua interna
// de utilização correta do CROmie sobre as oportunidades ativas. A
// diferença em relação a Vendas é a fonte de dados — aqui o front
// consome /agendamento/conformidade* (router próprio do SDR), e não
// /vendas/funil-cromie* (que exige o módulo 'clientes', que o SDR não
// tem).
//
// É uma CÓPIA INDEPENDENTE de propósito (estratégia B): nas próximas
// versões o Agendamento vai divergir da conformidade de Vendas (régua
// e colunas próprias do SDR). Manter este arquivo separado evita
// refator no módulo Vendas, que é estável e afeta indicadores PEX.
//
// IMPORTANTE — esta tela NÃO é a apuração oficial do PEX: cobra tarefa
// futura em todas as fases (régua interna, mais exigente). O percentual
// tende a ser menor que o da consultoria de campo da Omie.
//
// Link do CROmie: a oportunidade vive no funil 44 do CROmie, acessível
// em https://app.crm.omie.com.br/business-opportunity/44/{op_id}.
//
// Acesso: módulo 'agendamento' (cargo SDR).

import { useState, useEffect, useCallback } from 'react';
import {
  TrendingUp,
  CheckCircle2,
  AlertTriangle,
  Info,
  ExternalLink,
} from 'lucide-react';
import api from '../api';

import Card from '../components/ui/Card';
import KpiCard from '../components/ui/KpiCard';
import PageHeader from '../components/ui/PageHeader';
import Button from '../components/ui/Button';
import AlertMessage from '../components/ui/AlertMessage';
import Empty from '../components/ui/Empty';
import Badge from '../components/ui/Badge';
import Table, { Th, Tr, Td } from '../components/ui/Table';


// ── Helpers ──────────────────────────────────────────────────────────

function fmtData(d) {
  if (!d) return '—';
  try {
    return new Date(d).toLocaleDateString('pt-BR');
  } catch {
    return '—';
  }
}

function toneDoPct(pct) {
  if (pct >= 100) return 'success';
  if (pct >= 80) return 'warning';
  return 'danger';
}

// Base da URL de uma oportunidade no CROmie. O "44" é o funil de
// Oportunidades de Parcerias — fixo para estas oportunidades.
const CROMIE_OP_BASE = 'https://app.crm.omie.com.br/business-opportunity/44/';

function linkCromie(opId) {
  return `${CROMIE_OP_BASE}${opId}`;
}

// Ícone-link para abrir uma oportunidade no CROmie.
function LinkCromie({ opId, nome }) {
  return (
    <a
      href={linkCromie(opId)}
      target="_blank"
      rel="noopener noreferrer"
      className="inline-flex items-center justify-center p-1
                 rounded text-hipo-blue hover:bg-hipo-bg"
      aria-label={`Abrir ${nome || 'oportunidade'} no CROmie`}
      title="Abrir no CROmie"
    >
      <ExternalLink size={16} />
    </a>
  );
}


// ── Página ───────────────────────────────────────────────────────────

export default function Agendamento() {
  const [dados, setDados] = useState(null);
  const [opcoesFiltro, setOpcoesFiltro] = useState({ fases: [], responsaveis: [] });
  const [loading, setLoading] = useState(false);
  const [msg, setMsg] = useState(null);

  const [fase, setFase] = useState('');
  const [responsavel, setResponsavel] = useState('');
  const [soProblema, setSoProblema] = useState(false);
  const [soIncoerente, setSoIncoerente] = useState(false);

  const carregarFiltros = useCallback(async () => {
    try {
      const { data } = await api.get('/agendamento/conformidade/filtros');
      setOpcoesFiltro(data);
    } catch {
      setOpcoesFiltro({ fases: [], responsaveis: [] });
    }
  }, []);

  const carregar = useCallback(async () => {
    setLoading(true);
    setMsg(null);
    try {
      const params = new URLSearchParams();
      if (fase) params.set('fase', fase);
      if (responsavel) params.set('responsavel', responsavel);
      if (soProblema) params.set('so_problema', 'true');
      if (soIncoerente) params.set('so_incoerente', 'true');
      const { data } = await api.get(`/agendamento/conformidade?${params}`);
      setDados(data);
    } catch (e) {
      const detail = e.response?.data?.detail;
      const txt = typeof detail === 'string' ? detail : e.message;
      setMsg({ tipo: 'erro', texto: `Erro ao carregar: ${txt}` });
      setDados(null);
    } finally {
      setLoading(false);
    }
  }, [fase, responsavel, soProblema, soIncoerente]);

  useEffect(() => {
    carregarFiltros();
  }, [carregarFiltros]);

  useEffect(() => {
    carregar();
  }, [carregar]);

  const resumo = dados?.resumo;
  const itens = dados?.itens || [];
  const incoerentes = resumo?.temperatura_incoerente || 0;
  const temFiltro = fase || responsavel || soProblema || soIncoerente;

  return (
    <>
      <PageHeader
        title="Agendamento"
        subtitle="Conformidade do CROmie — utilização correta do funil."
      />

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
          {incoerentes > 0 ? (
            <KpiCard
              label="A revisar (temp. 100)"
              value={incoerentes.toLocaleString('pt-BR')}
              Icon={AlertTriangle}
              tone="danger"
            />
          ) : (
            <KpiCard
              label="Oportunidades ativas"
              value={resumo.total_analisadas.toLocaleString('pt-BR')}
              Icon={TrendingUp}
              tone="info"
            />
          )}
        </div>
      )}

      {incoerentes > 0 && (
        <AlertMessage tipo="aviso" className="mb-4">
          {incoerentes.toLocaleString('pt-BR')} oportunidade(s) ativa(s) com
          temperatura 100 (valor reservado a "Conquistado"). Provável
          oportunidade fechada sem atualização do status no CROmie —
          recomendamos revisar.
        </AlertMessage>
      )}

      <Card>
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
            value={responsavel}
            onChange={(e) => setResponsavel(e.target.value)}
            className="h-10 px-3 rounded-lg border border-hipo-border bg-hipo-card text-sm text-hipo-ink"
          >
            <option value="">Todos os responsáveis</option>
            {opcoesFiltro.responsaveis.map((r) => (
              <option key={r} value={r}>
                {r}
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

          {incoerentes > 0 && (
            <label className="flex items-center gap-2 text-sm text-hipo-danger cursor-pointer select-none px-2">
              <input
                type="checkbox"
                checked={soIncoerente}
                onChange={(e) => setSoIncoerente(e.target.checked)}
                className="w-4 h-4 accent-hipo-danger cursor-pointer"
              />
              Só temperatura incoerente
            </label>
          )}

          {temFiltro && (
            <Button
              variant="ghost"
              onClick={() => {
                setFase('');
                setResponsavel('');
                setSoProblema(false);
                setSoIncoerente(false);
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
              soProblema || soIncoerente
                ? 'Nenhuma oportunidade no filtro'
                : 'Nenhuma oportunidade ativa'
            }
            description={
              soProblema || soIncoerente
                ? 'Com os filtros atuais, nenhuma oportunidade foi encontrada.'
                : 'Aguarde o upload da planilha de Oportunidades pelo ADM.'
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
                  <Th>Responsável</Th>
                  <Th align="center">Situação</Th>
                  <Th>Pendências</Th>
                  <Th align="right">Atualizada</Th>
                  <Th align="center">CROmie</Th>
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
                        {o.responsavel || '—'}
                      </Td>
                      <Td align="center">
                        {cls.conforme ? (
                          <Badge tone="success">✓ Conforme</Badge>
                        ) : (
                          <Badge tone="danger">✗ Problema</Badge>
                        )}
                      </Td>
                      <Td>
                        <div className="flex flex-wrap gap-1">
                          {cls.temperatura_incoerente && (
                            <span
                              className="text-[11px] font-medium px-1.5 py-0.5 rounded
                                         bg-hipo-dangerSoft text-hipo-danger"
                            >
                              ⚠ Revisar temperatura
                            </span>
                          )}
                          {cls.conforme && !cls.temperatura_incoerente ? (
                            <span className="text-xs text-hipo-muted">—</span>
                          ) : (
                            cls.problemas_rotulos.map((p) => (
                              <span
                                key={p}
                                className="text-[11px] font-medium px-1.5 py-0.5 rounded
                                           bg-hipo-dangerSoft text-hipo-danger"
                              >
                                {p}
                              </span>
                            ))
                          )}
                        </div>
                      </Td>
                      <Td align="right" className="whitespace-nowrap text-hipo-slate">
                        {fmtData(o.data_atualizacao)}
                      </Td>
                      <Td align="center">
                        <LinkCromie opId={o.op_id} nome={o.razao_social} />
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
