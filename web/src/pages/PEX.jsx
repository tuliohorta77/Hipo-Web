// web/src/pages/PEX.jsx
import { useState, useEffect, useCallback } from 'react';
import {
  RefreshCw,
  AlertTriangle,
  BarChart3,
} from 'lucide-react';
import api from '../api';
import Card, { CardHeader } from '../components/ui/Card';
import PageHeader from '../components/ui/PageHeader';
import Button from '../components/ui/Button';
import UploadButton from '../components/ui/UploadButton';
import AlertMessage from '../components/ui/AlertMessage';
import Empty from '../components/ui/Empty';
import Tabs from '../components/ui/Tabs';
import Table, { Th, Tr, Td } from '../components/ui/Table';
import Badge from '../components/ui/Badge';

// Mapa de risco para cores semânticas
const RISCO_TONES = {
  VERDE:    { tone: 'success', color: '#16A34A', label: 'Em dia' },
  AMARELO:  { tone: 'warning', color: '#F59E0B', label: 'Atenção' },
  LARANJA:  { tone: 'warning', color: '#F97316', label: 'Risco' },
  VERMELHO: { tone: 'danger',  color: '#DC2626', label: 'Crítico' },
};

function ScoreRing({ score, risco }) {
  const r = 38;
  const circ = 2 * Math.PI * r;
  const pct = Math.min((score || 0) / 100, 1);
  const cfg = RISCO_TONES[risco] || RISCO_TONES.AMARELO;

  return (
    <svg width="100" height="100" viewBox="0 0 100 100">
      <circle
        cx="50"
        cy="50"
        r={r}
        fill="none"
        stroke="#E2E8F0"
        strokeWidth="8"
      />
      <circle
        cx="50"
        cy="50"
        r={r}
        fill="none"
        stroke={cfg.color}
        strokeWidth="8"
        strokeDasharray={`${pct * circ} ${circ}`}
        strokeLinecap="round"
        transform="rotate(-90 50 50)"
        style={{ transition: 'stroke-dasharray 1s ease' }}
      />
      <text
        x="50"
        y="56"
        textAnchor="middle"
        fill="#0F172A"
        fontSize="20"
        fontWeight="700"
      >
        {(score ?? 0).toFixed(1)}
      </text>
    </svg>
  );
}

function ProgressBar({ pct, pts, maxPts, label }) {
  const safePct = Math.max(0, Math.min(pct || 0, 100));
  const color =
    safePct >= 80
      ? 'bg-emerald-500'
      : safePct >= 50
      ? 'bg-amber-500'
      : 'bg-rose-500';
  const ok = safePct >= 80;
  return (
    <div className="mb-3.5">
      <div className="flex justify-between text-xs mb-1.5">
        <span className="text-hipo-slate font-medium">{label}</span>
        <span
          className={
            ok ? 'text-emerald-700 font-semibold' : 'text-red-700 font-semibold'
          }
        >
          {(pts ?? 0).toFixed(1)}/{maxPts}pts · {(pct ?? 0).toFixed(1)}%
        </span>
      </div>
      <div className="w-full h-2 bg-hipo-bg rounded-full overflow-hidden">
        <div
          className={`h-full ${color} rounded-full transition-all duration-700`}
          style={{ width: `${safePct}%` }}
        />
      </div>
    </div>
  );
}

export default function PEXDashboard() {
  const [painel, setPainel] = useState(null);
  const [compliance, setCompliance] = useState([]);
  const [historico, setHistorico] = useState([]);
  const [uploading, setUploading] = useState(false);
  const [msg, setMsg] = useState(null);
  const [tab, setTab] = useState('painel');

  const carregar = useCallback(async () => {
    try {
      const [p, c, h] = await Promise.all([
        api.get('/pex/painel').catch(() => ({ data: null })),
        api.get('/pex/compliance').catch(() => ({ data: [] })),
        api.get('/pex/historico?meses=6').catch(() => ({ data: [] })),
      ]);
      setPainel(p.data);
      setCompliance(c.data);
      setHistorico(h.data);
    } catch (e) {
      console.error(e);
    }
  }, []);

  useEffect(() => {
    carregar();
  }, [carregar]);

  async function uploadCromie(e) {
    const file = e.target.files[0];
    if (!file) return;
    setUploading(true);
    setMsg(null);
    const form = new FormData();
    form.append('arquivo', file);
    try {
      const { data } = await api.post('/pex/cromie/upload', form, {
        headers: { 'Content-Type': 'multipart/form-data' },
      });
      setMsg({
        tipo: data.schema_alterado ? 'aviso' : 'ok',
        texto: data.schema_alterado
          ? `Schema alterado. Colunas novas: ${data.colunas_novas.join(', ') || 'nenhuma'}. Removidas: ${data.colunas_removidas.join(', ') || 'nenhuma'}.`
          : `CROmie processado — ${data.totais?.total_cliente_final} leads, ${data.totais?.total_contador} contadores. PEX: ${data.pex?.total_geral_pts} pts (${data.pex?.risco}).`,
      });
      carregar();
    } catch (err) {
      setMsg({
        tipo: 'erro',
        texto: `Erro: ${err.response?.data?.detail || err.message}`,
      });
    } finally {
      setUploading(false);
      e.target.value = '';
    }
  }

  const tabItems = [
    { key: 'painel',     label: 'Painel' },
    { key: 'compliance', label: 'Compliance' },
    { key: 'historico',  label: 'Histórico' },
  ];

  return (
    <>
      <PageHeader
        title="Painel PEX"
        subtitle={
          painel
            ? `Última atualização: ${new Date(painel.snapshot?.data_ref || painel.created_at || Date.now()).toLocaleString('pt-BR')}`
            : 'Aguardando primeiro upload'
        }
        actions={
          <>
            <Button
              variant="ghost"
              size="md"
              icon={RefreshCw}
              onClick={carregar}
              aria-label="Recarregar"
            />
            <UploadButton
              onChange={uploadCromie}
              loading={uploading}
              label="Upload CROmie"
            />
          </>
        }
      />

      {msg && (
        <AlertMessage tipo={msg.tipo} className="mb-6">
          {msg.texto}
        </AlertMessage>
      )}

      <Tabs items={tabItems} value={tab} onChange={setTab} className="mb-6" />

      {/* PAINEL */}
      {tab === 'painel' && painel && (
        <div className="space-y-6">
          {/* Score geral */}
          <Card>
            <div className="flex flex-col md:flex-row items-start md:items-center gap-6">
              <ScoreRing
                score={painel.total_geral_pts}
                risco={painel.risco_classificacao}
              />
              <div className="flex-1">
                <p className="text-h1 text-hipo-ink">
                  {(painel.total_geral_pts ?? 0).toFixed(1)}{' '}
                  <span className="text-hipo-slate font-medium text-base">
                    / 100 pontos
                  </span>
                </p>
                <p className="text-sm text-hipo-slate mt-1">
                  {painel.total_geral_pts >= 95
                    ? 'Franquia Excelente'
                    : painel.total_geral_pts >= 76
                    ? 'Franquia Certificada'
                    : painel.total_geral_pts >= 60
                    ? 'Franquia Qualificada'
                    : painel.total_geral_pts >= 50
                    ? 'Franquia Aderente'
                    : painel.total_geral_pts >= 36
                    ? 'Franquia em Desenvolvimento'
                    : 'Franquia Não Aderente'}
                </p>
                <div className="flex items-center gap-2 mt-2 flex-wrap">
                  <Badge
                    tone={
                      (RISCO_TONES[painel.risco_classificacao] || RISCO_TONES.AMARELO).tone
                    }
                  >
                    {(RISCO_TONES[painel.risco_classificacao] || RISCO_TONES.AMARELO).label}
                  </Badge>
                  {painel.total_geral_pts < 40 && (
                    <span className="text-xs text-hipo-danger flex items-center gap-1">
                      <AlertTriangle size={12} />
                      Risco de descredenciamento
                    </span>
                  )}
                </div>
              </div>

              <div className="grid grid-cols-3 gap-3 w-full md:w-auto">
                {[
                  ['Resultado',   painel.total_resultado_pts,   60],
                  ['Gestão',      painel.total_gestao_pts,      20],
                  ['Engajamento', painel.total_engajamento_pts, 20],
                ].map(([nome, pts, max]) => (
                  <div
                    key={nome}
                    className="bg-hipo-bg rounded-lg px-4 py-3 text-center min-w-[88px]"
                  >
                    <p className="text-xs text-hipo-slate">{nome}</p>
                    <p className="text-lg font-bold text-hipo-ink mt-0.5">
                      {(pts || 0).toFixed(1)}
                    </p>
                    <p className="text-xs text-hipo-muted">/ {max} pts</p>
                  </div>
                ))}
              </div>
            </div>
          </Card>

          {/* Pilar Resultado */}
          <Card>
            <CardHeader title="Pilar Resultado" hint="Detalhamento dos indicadores" />
            <div className="grid grid-cols-1 md:grid-cols-2 gap-x-8">
              <div>
                <ProgressBar
                  pct={painel.nmrr_pct}
                  pts={painel.nmrr_pts}
                  maxPts={10}
                  label="NMRR"
                />
                <ProgressBar
                  pct={(painel.reunioes_ec_du_realizado || 0) * 25}
                  pts={painel.reunioes_ec_du_pts}
                  maxPts={3}
                  label="Reuniões EC/DU"
                />
                <ProgressBar
                  pct={painel.contadores_trabalhados_pct}
                  pts={painel.contadores_trabalhados_pts}
                  maxPts={2}
                  label="Contadores trabalhados"
                />
                <ProgressBar
                  pct={painel.contadores_indicando_pct}
                  pts={painel.contadores_indicando_pts}
                  maxPts={3}
                  label="Contadores indicando"
                />
                <ProgressBar
                  pct={painel.contadores_ativando_pct}
                  pts={painel.contadores_ativando_pts}
                  maxPts={4}
                  label="Contadores ativando"
                />
                <ProgressBar
                  pct={painel.conversao_total_pct}
                  pts={painel.conversao_total_pts}
                  maxPts={4}
                  label="Conversão total de leads"
                />
                <ProgressBar
                  pct={painel.conversao_m0_pct}
                  pts={painel.conversao_m0_pts}
                  maxPts={3}
                  label="Conversão M0"
                />
                <ProgressBar
                  pct={painel.conversao_inbound_pct}
                  pts={painel.conversao_inbound_pts}
                  maxPts={2}
                  label="Conversão inbound"
                />
              </div>
              <div>
                <ProgressBar
                  pct={(painel.demo_du_realizado || 0) * 25}
                  pts={painel.demo_du_pts}
                  maxPts={4}
                  label="Demo / dia útil"
                />
                <ProgressBar
                  pct={painel.demos_outbound_pct}
                  pts={painel.demos_outbound_pts}
                  maxPts={3}
                  label="Demos outbound"
                />
                <ProgressBar
                  pct={painel.sow_pct}
                  pts={painel.sow_pts}
                  maxPts={3}
                  label="Share of Wallet"
                />
                <ProgressBar
                  pct={painel.mapeamento_carteira_pct}
                  pts={painel.mapeamento_carteira_pts}
                  maxPts={2}
                  label="Mapeamento carteira"
                />
                <ProgressBar
                  pct={painel.reuniao_contador_inbound_pct}
                  pts={painel.reuniao_contador_inbound_pts}
                  maxPts={4}
                  label="Reunião contador inbound"
                />
                <ProgressBar
                  pct={painel.integracao_contabil_pct}
                  pts={painel.integracao_contabil_pts}
                  maxPts={3}
                  label="Integração contábil"
                />
                <ProgressBar
                  pct={100 - (painel.early_churn_pct || 0) * 10}
                  pts={painel.early_churn_pts}
                  maxPts={3}
                  label="Early churn"
                />
                <ProgressBar
                  pct={painel.crescimento_40_pct}
                  pts={painel.crescimento_40_pts}
                  maxPts={5}
                  label="Crescimento 40%"
                />
              </div>
            </div>
          </Card>
        </div>
      )}

      {tab === 'painel' && !painel && (
        <Card>
          <Empty
            title="Nenhum dado carregado"
            description="Faça o upload do Excel do CROmie para calcular os indicadores."
            icon={BarChart3}
          />
        </Card>
      )}

      {/* COMPLIANCE */}
      {tab === 'compliance' && (
        <Card padding="none">
          <div className="p-5 pb-3">
            <CardHeader
              title="Gaps de compliance por colaborador"
              hint="Indicadores em risco no mês corrente"
            />
          </div>
          {compliance.length === 0 ? (
            <Empty
              title="Sem dados de compliance"
              description="Faça o upload do CROmie."
            />
          ) : (
            <Table>
              <thead>
                <tr>
                  <Th>Colaborador</Th>
                  <Th align="center">Sem tarefa futura</Th>
                  <Th align="center">Sem temperatura</Th>
                  <Th align="center">Sem previsão</Th>
                  <Th align="center">Sem ticket</Th>
                  <Th align="center">Contadores s/ tarefa</Th>
                  <Th align="center">Pontos em risco</Th>
                </tr>
              </thead>
              <tbody>
                {compliance.map((row, i) => {
                  const riscoColor =
                    row.pontos_em_risco > 2
                      ? 'text-red-700'
                      : row.pontos_em_risco > 1
                      ? 'text-amber-700'
                      : 'text-emerald-700';
                  return (
                    <Tr key={i}>
                      <Td className="font-semibold">{row.usuario_responsavel}</Td>
                      {[
                        row.leads_sem_tarefa_futura,
                        row.leads_sem_temperatura,
                        row.leads_sem_previsao,
                        row.leads_sem_ticket,
                        row.contadores_sem_tarefa_mes,
                      ].map((v, j) => (
                        <Td
                          key={j}
                          align="center"
                          className={
                            v > 0 ? 'text-red-700 font-semibold' : 'text-hipo-muted'
                          }
                        >
                          {v > 0 ? v : '—'}
                        </Td>
                      ))}
                      <Td align="center" className={`font-bold ${riscoColor}`}>
                        {row.pontos_em_risco?.toFixed(1)}
                      </Td>
                    </Tr>
                  );
                })}
              </tbody>
            </Table>
          )}
        </Card>
      )}

      {/* HISTÓRICO */}
      {tab === 'historico' && (
        <div className="space-y-3">
          {historico.length === 0 ? (
            <Card>
              <Empty title="Sem histórico" description="Sem snapshots dos últimos meses." />
            </Card>
          ) : (
            historico.map((h, i) => {
              const cfg = RISCO_TONES[h.risco] || RISCO_TONES.AMARELO;
              return (
                <Card key={i} padding="sm">
                  <div className="flex items-center justify-between gap-4 flex-wrap">
                    <div className="flex items-center gap-3">
                      <div
                        className="w-3 h-3 rounded-full"
                        style={{ backgroundColor: cfg.color }}
                      />
                      <span className="font-semibold text-hipo-ink">
                        {h.mes_ref}
                      </span>
                      <Badge tone={cfg.tone}>{cfg.label}</Badge>
                    </div>
                    <div className="flex items-center gap-6 text-sm text-hipo-slate flex-wrap">
                      <span>
                        Resultado:{' '}
                        <strong className="text-hipo-ink">
                          {h.resultado_pts?.toFixed(1)}
                        </strong>
                      </span>
                      <span>
                        Gestão:{' '}
                        <strong className="text-hipo-ink">
                          {h.gestao_pts?.toFixed(1)}
                        </strong>
                      </span>
                      <span>
                        Engajamento:{' '}
                        <strong className="text-hipo-ink">
                          {h.engajamento_pts?.toFixed(1)}
                        </strong>
                      </span>
                      <span
                        className="font-bold text-base"
                        style={{ color: cfg.color }}
                      >
                        {h.pontuacao?.toFixed(1)} pts
                      </span>
                    </div>
                  </div>
                </Card>
              );
            })
          )}
        </div>
      )}
    </>
  );
}
