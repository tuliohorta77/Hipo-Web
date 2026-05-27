// web/src/pages/Vendas.jsx
//
// Módulo Vendas. Duas sub-abas:
//   - Conformidade: régua interna de utilização correta do CROmie.
//   - Funil: o Funil de Vendas — oportunidades ativas por fase x faixa
//     de temperatura, com valor (proposta_nmrr). A temperatura aqui é a
//     previsão de venda: quanto mais alta, mais perto de fechar.
//
// IMPORTANTE — a aba Conformidade NÃO é a apuração oficial do PEX:
//   cobra tarefa futura em todas as fases (régua interna, mais
//   exigente). O percentual tende a ser menor que o da consultoria.
//
// Funil — 5 faixas de temperatura: sem / fria (10–40) / morna (50–70) /
//   quente (80) / fechando (90). "Fechando" é separado de "quente"
//   porque 90 é a venda iminente. Temperatura 100 = conquistado: OP
//   ativa com 100 é incoerência, fica fora do funil.
//
// Clique numa faixa do funil abre um drawer com as oportunidades
// daquele recorte (fase + faixa). O drawer tem filtro por responsável
// (recalcula a soma de valor) e um link para abrir a OP no CROmie.
//
// Link do CROmie: a OP é acessível em
//   https://app.crm.omie.com.br/business-opportunity/44/{op_id}
// onde 44 é o funil (fixo para estas oportunidades) e op_id é o
// identificador da oportunidade — confirmado igual ao id da URL.
//
// Acesso: mesmo módulo 'clientes' (quem vê Clientes vê Vendas).

import { useState, useEffect, useCallback, useMemo } from 'react';
import {
  TrendingUp,
  CheckCircle2,
  AlertTriangle,
  Info,
  BarChart3,
  ClipboardCheck,
  DollarSign,
  ExternalLink,
  X,
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


// ── Helpers ──────────────────────────────────────────────────────

function fmtData(d) {
  if (!d) return '—';
  try {
    return new Date(d).toLocaleDateString('pt-BR');
  } catch {
    return '—';
  }
}

const BRL = new Intl.NumberFormat('pt-BR', {
  style: 'currency',
  currency: 'BRL',
  maximumFractionDigits: 0,
});

function fmtValor(v) {
  if (!v || v <= 0) return '—';
  return BRL.format(v);
}

function toneDoPct(pct) {
  if (pct >= 100) return 'success';
  if (pct >= 80) return 'warning';
  return 'danger';
}

// Base da URL de uma oportunidade no CROmie. O "44" é o funil — fixo
// para estas oportunidades. Basta concatenar o op_id.
const CROMIE_OP_BASE = 'https://app.crm.omie.com.br/business-opportunity/44/';

function linkCromie(opId) {
  return `${CROMIE_OP_BASE}${opId}`;
}

// Faixas de temperatura do funil — código, rótulo e cor.
// Mantida em sincronia com services/vendas_cromie.py
// (FAIXAS_TEMPERATURA / ROTULO_FAIXA). "fechando" usa um laranja
// escuro puxando pro vermelho — é a faixa de venda iminente.
const FAIXAS = [
  { key: 'sem',      label: 'Sem temperatura', cor: '#94a3b8' },
  { key: 'fria',     label: 'Fria (10–40)',    cor: '#60a5fa' },
  { key: 'morna',    label: 'Morna (50–70)',   cor: '#fbbf24' },
  { key: 'quente',   label: 'Quente (80)',     cor: '#f97316' },
  { key: 'fechando', label: 'Fechando (90)',   cor: '#9a3412' },
];

// Largura relativa de cada degrau do funil, na ordem das fases.
const LARGURA_FASE = [100, 86, 72, 58, 44];


// ── Sub-aba Conformidade ─────────────────────────────────────────

function AbaConformidade() {
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
      const { data } = await api.get('/vendas/funil-cromie/filtros');
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
      const { data } = await api.get(`/vendas/funil-cromie?${params}`);
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
                  <Th>Responsável</Th>
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


// ── Drawer: lista de oportunidades de um recorte (fase + faixa) ───

function DrawerRecorte({ fase, faixa, onClose }) {
  const [itens, setItens] = useState(null);
  const [loading, setLoading] = useState(true);
  const [erro, setErro] = useState(null);
  const [respFiltro, setRespFiltro] = useState('');

  const faixaInfo = FAIXAS.find((f) => f.key === faixa);

  useEffect(() => {
    let ativo = true;
    (async () => {
      setLoading(true);
      setErro(null);
      setRespFiltro('');
      try {
        const params = new URLSearchParams();
        params.set('fase', fase);
        params.set('temperatura', faixa);
        const { data } = await api.get(`/vendas/funil-cromie?${params}`);
        if (ativo) setItens(data.itens || []);
      } catch (e) {
        const detail = e.response?.data?.detail;
        const txt = typeof detail === 'string' ? detail : e.message;
        if (ativo) setErro(`Erro ao carregar: ${txt}`);
      } finally {
        if (ativo) setLoading(false);
      }
    })();
    return () => {
      ativo = false;
    };
  }, [fase, faixa]);

  // Responsáveis distintos PRESENTES neste recorte — popula o dropdown.
  const responsaveis = useMemo(() => {
    const set = new Set();
    (itens || []).forEach((o) => {
      const r = (o.responsavel || '').trim();
      if (r) set.add(r);
    });
    return [...set].sort();
  }, [itens]);

  const itensFiltrados = useMemo(() => {
    if (!respFiltro) return itens || [];
    return (itens || []).filter(
      (o) => (o.responsavel || '').trim() === respFiltro,
    );
  }, [itens, respFiltro]);

  const valorTotal = useMemo(
    () =>
      itensFiltrados.reduce(
        (acc, o) => acc + (Number(o.proposta_nmrr) || 0),
        0,
      ),
    [itensFiltrados],
  );

  return (
    <div
      className="fixed inset-0 z-50 flex justify-end bg-black/40"
      onClick={onClose}
    >
      <div
        className="w-full max-w-2xl h-full bg-hipo-card border-l border-hipo-border
                   overflow-y-auto shadow-xl"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-start justify-between p-5 border-b border-hipo-border">
          <div>
            <div className="text-sm font-medium text-hipo-ink">{fase}</div>
            <div className="flex items-center gap-2 mt-1">
              <span
                className="w-3 h-3 rounded-sm inline-block"
                style={{ backgroundColor: faixaInfo?.cor }}
              />
              <span className="text-xs text-hipo-slate">
                {faixaInfo?.label || faixa}
              </span>
            </div>
          </div>
          <button
            onClick={onClose}
            className="p-1 rounded hover:bg-hipo-bg text-hipo-slate"
            aria-label="Fechar"
          >
            <X size={18} />
          </button>
        </div>

        <div className="p-5">
          {loading ? (
            <p className="text-sm text-hipo-slate text-center py-8">
              Carregando oportunidades...
            </p>
          ) : erro ? (
            <AlertMessage tipo="erro">{erro}</AlertMessage>
          ) : !itens || itens.length === 0 ? (
            <Empty
              Icon={BarChart3}
              title="Nenhuma oportunidade"
              description="Este recorte não tem oportunidades."
            />
          ) : (
            <>
              <div className="flex flex-wrap items-center gap-2 mb-3">
                <select
                  value={respFiltro}
                  onChange={(e) => setRespFiltro(e.target.value)}
                  className="h-9 px-3 rounded-lg border border-hipo-border bg-hipo-card text-sm text-hipo-ink"
                >
                  <option value="">Todos os responsáveis</option>
                  {responsaveis.map((r) => (
                    <option key={r} value={r}>
                      {r}
                    </option>
                  ))}
                </select>
                {respFiltro && (
                  <Button variant="ghost" onClick={() => setRespFiltro('')}>
                    Limpar
                  </Button>
                )}
              </div>

              {itensFiltrados.length === 0 ? (
                <Empty
                  Icon={BarChart3}
                  title="Nenhuma oportunidade"
                  description="Este responsável não tem oportunidades neste recorte."
                />
              ) : (
                <>
                  <div className="flex items-center justify-between mb-3">
                    <p className="text-xs text-hipo-slate">
                      {itensFiltrados.length.toLocaleString('pt-BR')}{' '}
                      oportunidade(s)
                    </p>
                    <p className="text-sm font-medium text-hipo-ink">
                      {fmtValor(valorTotal)}
                    </p>
                  </div>
                  <Table>
                    <thead>
                      <Tr>
                        <Th>Razão Social / CNPJ</Th>
                        <Th>Responsável</Th>
                        <Th align="right">Valor (NMRR)</Th>
                        <Th align="center">CROmie</Th>
                      </Tr>
                    </thead>
                    <tbody>
                      {itensFiltrados.map((o) => (
                        <Tr key={o.op_id} hover>
                          <Td>
                            <div className="font-medium text-hipo-ink">
                              {o.razao_social || '—'}
                            </div>
                            <div className="text-xs text-hipo-muted font-mono">
                              {o.cnpj}
                            </div>
                          </Td>
                          <Td className="text-hipo-slate">
                            {o.responsavel || '—'}
                          </Td>
                          <Td align="right" className="whitespace-nowrap text-hipo-ink">
                            {fmtValor(Number(o.proposta_nmrr))}
                          </Td>
                          <Td align="center">
                            <a
                              href={linkCromie(o.op_id)}
                              target="_blank"
                              rel="noopener noreferrer"
                              className="inline-flex items-center justify-center p-1
                                         rounded text-hipo-blue hover:bg-hipo-bg"
                              aria-label={`Abrir ${o.razao_social || 'oportunidade'} no CROmie`}
                              title="Abrir no CROmie"
                            >
                              <ExternalLink size={16} />
                            </a>
                          </Td>
                        </Tr>
                      ))}
                    </tbody>
                  </Table>
                </>
              )}
            </>
          )}
        </div>
      </div>
    </div>
  );
}


// ── Sub-aba Funil ────────────────────────────────────────────────

function AbaFunil() {
  const [dados, setDados] = useState(null);
  const [loading, setLoading] = useState(false);
  const [msg, setMsg] = useState(null);
  const [recorte, setRecorte] = useState(null);

  const carregar = useCallback(async () => {
    setLoading(true);
    setMsg(null);
    try {
      const { data } = await api.get('/vendas/funil');
      setDados(data);
    } catch (e) {
      const detail = e.response?.data?.detail;
      const txt = typeof detail === 'string' ? detail : e.message;
      setMsg({ tipo: 'erro', texto: `Erro ao carregar o funil: ${txt}` });
      setDados(null);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    carregar();
  }, [carregar]);

  if (loading) {
    return (
      <Card>
        <p className="text-sm text-hipo-slate text-center py-8">
          Carregando o funil...
        </p>
      </Card>
    );
  }

  if (msg) {
    return <AlertMessage tipo={msg.tipo}>{msg.texto}</AlertMessage>;
  }

  if (!dados || dados.total_geral === 0) {
    return (
      <Card>
        <Empty
          Icon={BarChart3}
          title="Sem oportunidades no funil"
          description="Não há oportunidades ativas para exibir. Faça upload da planilha de Oportunidades no módulo Clientes."
        />
      </Card>
    );
  }

  const incoerentes = dados.temperatura_incoerente || 0;

  return (
    <>
      <div className="grid grid-cols-2 md:grid-cols-3 gap-4 mb-6">
        <KpiCard
          label="Oportunidades no funil"
          value={dados.total_geral.toLocaleString('pt-BR')}
          Icon={TrendingUp}
          tone="info"
        />
        <KpiCard
          label="Valor em proposta (NMRR)"
          value={fmtValor(dados.valor_geral)}
          Icon={DollarSign}
          tone="info"
        />
        <KpiCard
          label="Fases ativas"
          value={dados.fases.length.toLocaleString('pt-BR')}
          Icon={BarChart3}
          tone="info"
        />
      </div>

      {incoerentes > 0 && (
        <AlertMessage tipo="aviso" className="mb-4">
          {incoerentes.toLocaleString('pt-BR')} oportunidade(s) ativa(s) com
          temperatura 100 não entra(m) no funil. Veja na aba Conformidade.
        </AlertMessage>
      )}

      <Card>
        <div className="flex flex-wrap items-center gap-4 mb-5 text-xs text-hipo-slate">
          {FAIXAS.map((fx) => (
            <span key={fx.key} className="flex items-center gap-1.5">
              <span
                className="w-3 h-3 rounded-sm inline-block"
                style={{ backgroundColor: fx.cor }}
              />
              {fx.label}
            </span>
          ))}
        </div>

        <div className="space-y-2">
          {dados.fases.map((f, idx) => {
            const largura = LARGURA_FASE[idx] ?? 40;
            const total = f.total;
            return (
              <div key={f.fase} className="flex items-center gap-3">
                <div className="w-32 shrink-0 text-right">
                  <div className="text-sm font-medium text-hipo-ink">
                    {f.fase}
                  </div>
                  <div className="text-[11px] text-hipo-muted">
                    {fmtValor(f.valor)}
                  </div>
                </div>
                <div className="flex-1 flex justify-center">
                  <div
                    className="flex h-9 rounded-md overflow-hidden border border-hipo-border"
                    style={{ width: `${largura}%` }}
                  >
                    {total === 0 ? (
                      <div className="w-full bg-hipo-bg" />
                    ) : (
                      FAIXAS.map((fx) => {
                        const slot = f.faixas[fx.key] || { total: 0 };
                        const n = slot.total || 0;
                        if (n <= 0) return null;
                        const pct = (n / total) * 100;
                        return (
                          <button
                            key={fx.key}
                            title={`${fx.label}: ${n} — clique para ver`}
                            onClick={() =>
                              setRecorte({ fase: f.fase, faixa: fx.key })
                            }
                            style={{
                              width: `${pct}%`,
                              backgroundColor: fx.cor,
                            }}
                            className="h-full cursor-pointer hover:opacity-80
                                       transition-opacity"
                            aria-label={`${f.fase}, ${fx.label}, ${n} oportunidades`}
                          />
                        );
                      })
                    )}
                  </div>
                </div>
                <div className="w-24 shrink-0 text-left">
                  <div className="text-sm font-medium text-hipo-ink">
                    {total.toLocaleString('pt-BR')}
                  </div>
                  <div className="text-[11px] text-hipo-muted">
                    oportunidades
                  </div>
                </div>
              </div>
            );
          })}
        </div>

        <p className="text-xs text-hipo-muted mt-5">
          Clique numa faixa colorida para ver as oportunidades daquele
          recorte. A largura de cada fase é fixa decrescente — a quantidade
          real está no número ao lado.
        </p>
      </Card>

      {recorte && (
        <DrawerRecorte
          fase={recorte.fase}
          faixa={recorte.faixa}
          onClose={() => setRecorte(null)}
        />
      )}
    </>
  );
}


// ── Componente principal ─────────────────────────────────────────

const SUB_ABAS = [
  { v: 'CONFORMIDADE', label: 'Conformidade', Icon: ClipboardCheck },
  { v: 'FUNIL',        label: 'Funil',        Icon: BarChart3 },
];

export default function Vendas() {
  const [aba, setAba] = useState('CONFORMIDADE');

  return (
    <>
      <PageHeader
        title="Vendas"
        subtitle="Funil de Vendas — utilização correta do CROmie."
      />

      <div className="flex border-b border-hipo-border mb-4">
        {SUB_ABAS.map(({ v, label, Icon }) => (
          <button
            key={v}
            onClick={() => setAba(v)}
            className={`px-4 py-2.5 text-sm font-medium border-b-2 transition-colors ${
              aba === v
                ? 'border-hipo-blue text-hipo-blue'
                : 'border-transparent text-hipo-slate hover:text-hipo-ink'
            }`}
          >
            <span className="flex items-center gap-2">
              <Icon size={16} />
              {label}
            </span>
          </button>
        ))}
      </div>

      {aba === 'CONFORMIDADE' && <AbaConformidade />}
      {aba === 'FUNIL' && <AbaFunil />}
    </>
  );
}
