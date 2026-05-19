// web/src/pages/POs.jsx
import { useState, useEffect, useCallback } from 'react';
import {
  RefreshCw,
  CheckCircle2,
  AlertCircle,
  XCircle,
  HelpCircle,
  Upload,
} from 'lucide-react';
import api from '../api';
import Card, { CardHeader } from '../components/ui/Card';
import KpiCard from '../components/ui/KpiCard';
import PageHeader from '../components/ui/PageHeader';
import Button from '../components/ui/Button';
import UploadButton from '../components/ui/UploadButton';
import AlertMessage from '../components/ui/AlertMessage';
import Empty from '../components/ui/Empty';
import Tabs from '../components/ui/Tabs';
import Badge from '../components/ui/Badge';
import Table, { Th, Tr, Td } from '../components/ui/Table';

const STATUS_CFG = {
  CONFORME:   { label: 'Conforme',   tone: 'success', Icon: CheckCircle2 },
  DIVERGENTE: { label: 'Divergente', tone: 'warning', Icon: AlertCircle  },
  AUSENTE:    { label: 'Ausente',    tone: 'danger',  Icon: XCircle      },
  INESPERADO: { label: 'Inesperado', tone: 'neutral', Icon: HelpCircle   },
};

function StatusBadge({ status }) {
  const cfg = STATUS_CFG[status] || STATUS_CFG.INESPERADO;
  const { Icon } = cfg;
  return (
    <Badge tone={cfg.tone}>
      <Icon size={12} />
      {cfg.label}
    </Badge>
  );
}

const fmtBRL = (v) =>
  Number(v || 0).toLocaleString('pt-BR', {
    minimumFractionDigits: 2,
  });

export default function POsDashboard() {
  const [reconciliacao, setReconciliacao] = useState([]);
  const [ausentes, setAusentes] = useState([]);
  const [divergentes, setDivergentes] = useState([]);
  const [historico, setHistorico] = useState([]);
  const [uploading, setUploading] = useState(false);
  const [msg, setMsg] = useState(null);
  const [tab, setTab] = useState('resumo');

  const carregar = useCallback(async () => {
    try {
      const [r, a, d, h] = await Promise.all([
        api.get('/po/reconciliacao/ultima').catch(() => ({ data: [] })),
        api.get('/po/reconciliacao/ausentes').catch(() => ({ data: [] })),
        api.get('/po/reconciliacao/divergentes').catch(() => ({ data: [] })),
        api.get('/po/historico').catch(() => ({ data: [] })),
      ]);
      setReconciliacao(r.data);
      setAusentes(a.data);
      setDivergentes(d.data);
      setHistorico(h.data);
    } catch (e) {
      console.error(e);
    }
  }, []);

  useEffect(() => {
    carregar();
  }, [carregar]);

  async function uploadPO(e) {
    const file = e.target.files[0];
    if (!file) return;
    setUploading(true);
    setMsg(null);
    const form = new FormData();
    form.append('arquivo', file);
    try {
      const { data } = await api.post('/po/upload', form, {
        headers: { 'Content-Type': 'multipart/form-data' },
      });
      const aReceber = Number(data.valor_a_receber || 0).toLocaleString('pt-BR', {
        style: 'currency',
        currency: 'BRL',
      });
      const tipoLabel = `${data.tipo}${data.tem_enabler ? ' (Enabler)' : ''}`;
      const poLabel = data.numero_po ? ` PO #${data.numero_po}` : '';
      const semana = data.semana_ref || 'não identificada';

      if (data.tem_diferenca_calculo) {
        setMsg({
          tipo: 'aviso',
          texto: `${tipoLabel}${poLabel} processada com aviso — ${data.total_linhas} linhas, semana ${semana}. Valor a receber: ${aReceber}. ${data.observacao_calculo || ''}`,
        });
      } else {
        setMsg({
          tipo: 'ok',
          texto: `${tipoLabel}${poLabel} processada — ${data.total_linhas} linhas, semana ${semana}. Valor a receber: ${aReceber}.${data.observacao_calculo ? ' ' + data.observacao_calculo : ''}`,
        });
      }
      carregar();
    } catch (err) {
      setMsg({ tipo: 'erro', texto: `Erro: ${err.response?.data?.detail || err.message}` });
    } finally {
      setUploading(false);
      e.target.value = '';
    }
  }

  const totalConforme = reconciliacao
    .filter((r) => r.status_reconciliacao === 'CONFORME')
    .reduce((s, r) => s + Number(r.valor_total), 0);
  const totalAusente = reconciliacao
    .filter((r) => r.status_reconciliacao === 'AUSENTE')
    .reduce((s, r) => s + Number(r.valor_total), 0);
  const qtdAusentes = ausentes.length;
  const qtdDivergentes = divergentes.length;
  const uploadsMes = historico.filter((h) => {
    const d = new Date(h.data_upload);
    const now = new Date();
    return (
      d.getMonth() === now.getMonth() && d.getFullYear() === now.getFullYear()
    );
  }).length;

  const tabItems = [
    { key: 'resumo',      label: 'Resumo' },
    { key: 'ausentes',    label: 'Ausentes',    badge: qtdAusentes > 0 ? qtdAusentes : null },
    { key: 'divergentes', label: 'Divergentes', badge: qtdDivergentes > 0 ? qtdDivergentes : null },
    { key: 'historico',   label: 'Histórico' },
  ];

  return (
    <>
      <PageHeader
        title="POs"
        subtitle="Reconciliação semanal de comissões, incentivos e repasses."
        actions={
          <>
            <Button
              variant="ghost"
              size="md"
              icon={RefreshCw}
              onClick={carregar}
              aria-label="Recarregar"
            />
            <UploadButton onChange={uploadPO} loading={uploading} label="Upload PO" />
          </>
        }
      />

      {msg && (
        <AlertMessage tipo={msg.tipo} className="mb-6">
          {msg.texto}
        </AlertMessage>
      )}

      {/* KPIs */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4 mb-6">
        <KpiCard
          label="Recebido (semana)"
          value={`R$ ${(totalConforme / 1000).toFixed(1)}k`}
          icon={CheckCircle2}
          tone="emerald"
        />
        <KpiCard
          label="Em risco"
          value={`R$ ${(totalAusente / 1000).toFixed(1)}k`}
          hint={`${qtdAusentes} cliente(s) ausente(s)`}
          icon={XCircle}
          tone="rose"
        />
        <KpiCard
          label="Divergentes"
          value={qtdDivergentes}
          hint="aguardando resolução"
          icon={AlertCircle}
          tone="amber"
        />
        <KpiCard
          label="Uploads este mês"
          value={uploadsMes}
          icon={Upload}
          tone="blue"
        />
      </div>

      <Tabs items={tabItems} value={tab} onChange={setTab} className="mb-6" />

      {tab === 'resumo' && (
        <Card padding="none">
          {reconciliacao.length === 0 ? (
            <Empty
              title="Nenhuma PO processada"
              description="Faça o upload dos arquivos de PO da semana."
              icon={Upload}
            />
          ) : (
            <Table>
              <thead>
                <tr>
                  <Th>Tipo</Th>
                  <Th>Status</Th>
                  <Th align="right">Qtd</Th>
                  <Th align="right">Valor</Th>
                  <Th align="right">Divergência</Th>
                </tr>
              </thead>
              <tbody>
                {reconciliacao.map((r, i) => (
                  <Tr key={i}>
                    <Td className="font-semibold">
                      {r.tipo}
                      {r.tem_enabler ? ' (Enabler)' : ''}
                    </Td>
                    <Td>
                      <StatusBadge status={r.status_reconciliacao} />
                    </Td>
                    <Td align="right">{r.quantidade}</Td>
                    <Td align="right">R$ {fmtBRL(r.valor_total)}</Td>
                    <Td
                      align="right"
                      className={
                        r.divergencia_total > 0
                          ? 'text-amber-700 font-semibold'
                          : r.divergencia_total < 0
                          ? 'text-red-700 font-semibold'
                          : 'text-hipo-muted'
                      }
                    >
                      {r.divergencia_total != 0
                        ? `R$ ${fmtBRL(r.divergencia_total)}`
                        : '—'}
                    </Td>
                  </Tr>
                ))}
              </tbody>
            </Table>
          )}
        </Card>
      )}

      {tab === 'ausentes' && (
        <Card padding="none">
          {ausentes.length === 0 ? (
            <Empty
              title="Nenhum cliente ausente"
              description="Todos os clientes da semana foram contemplados."
              icon={CheckCircle2}
            />
          ) : (
            <Table>
              <thead>
                <tr>
                  <Th>Cliente</Th>
                  <Th>Tipo</Th>
                  <Th align="right">Valor esperado</Th>
                  <Th>Situação</Th>
                  <Th>Saúde</Th>
                  <Th>Contador</Th>
                </tr>
              </thead>
              <tbody>
                {ausentes.map((a, i) => (
                  <Tr key={i}>
                    <Td>
                      <p className="font-semibold">
                        {a.razao_social || a.referencia_aplicativo}
                      </p>
                      <p className="text-xs text-hipo-muted">
                        {a.referencia_aplicativo}
                      </p>
                    </Td>
                    <Td className="text-hipo-slate">{a.tipo}</Td>
                    <Td align="right" className="font-semibold text-red-700">
                      R$ {fmtBRL(a.valor_esperado)}
                    </Td>
                    <Td>
                      {a.situacao === 'ARCHIVED' ? (
                        <Badge tone="danger">{a.situacao}</Badge>
                      ) : (
                        <Badge tone="neutral">{a.situacao || '—'}</Badge>
                      )}
                    </Td>
                    <Td className="text-hipo-slate">{a.saude_paciente || '—'}</Td>
                    <Td className="text-hipo-slate">
                      {a.contador_nome || 'Sem contador'}
                    </Td>
                  </Tr>
                ))}
              </tbody>
            </Table>
          )}
        </Card>
      )}

      {tab === 'divergentes' && (
        <Card padding="none">
          {divergentes.length === 0 ? (
            <Empty
              title="Nenhuma divergência"
              description="Todos os valores recebidos batem com o esperado."
              icon={CheckCircle2}
            />
          ) : (
            <Table>
              <thead>
                <tr>
                  <Th>Cliente</Th>
                  <Th align="right">Esperado</Th>
                  <Th align="right">Recebido</Th>
                  <Th align="right">Diferença</Th>
                  <Th>Semana</Th>
                </tr>
              </thead>
              <tbody>
                {divergentes.map((d, i) => (
                  <Tr key={i}>
                    <Td>
                      <p className="font-semibold">
                        {d.razao_social || d.referencia_aplicativo}
                      </p>
                      <p className="text-xs text-hipo-muted">{d.tipo}</p>
                    </Td>
                    <Td align="right">R$ {fmtBRL(d.valor_esperado)}</Td>
                    <Td align="right">R$ {fmtBRL(d.valor_recebido)}</Td>
                    <Td
                      align="right"
                      className={
                        d.divergencia_valor > 0
                          ? 'text-amber-700 font-semibold'
                          : 'text-red-700 font-semibold'
                      }
                    >
                      {d.divergencia_valor > 0 ? '+' : ''}R${' '}
                      {fmtBRL(d.divergencia_valor)}
                    </Td>
                    <Td className="text-hipo-slate">{d.semana_ref}</Td>
                  </Tr>
                ))}
              </tbody>
            </Table>
          )}
        </Card>
      )}

      {tab === 'historico' && (
        <div className="space-y-3">
          {historico.length === 0 ? (
            <Card>
              <Empty
                title="Sem histórico"
                description="Nenhum upload realizado ainda."
              />
            </Card>
          ) : (
            historico.map((h, i) => (
              <Card
                key={i}
                padding="sm"
                className={
                  h.tem_diferenca_calculo
                    ? 'border-amber-200 bg-amber-50/50'
                    : ''
                }
              >
                <div className="flex items-center justify-between gap-4">
                  <div className="min-w-0 flex-1">
                    <p className="font-semibold text-hipo-ink truncate">
                      {h.nome_arquivo}
                      {h.tem_diferenca_calculo && (
                        <AlertCircle
                          size={14}
                          className="inline ml-2 text-hipo-warning"
                          title={h.observacao_calculo}
                        />
                      )}
                    </p>
                    <p className="text-xs text-hipo-slate mt-0.5">
                      {new Date(h.data_upload).toLocaleString('pt-BR')}
                      {h.numero_po && <> · PO #{h.numero_po}</>}
                      {h.semana_ref && <> · Semana: {h.semana_ref}</>}
                    </p>
                  </div>
                  <div className="flex items-center gap-4 text-xs text-hipo-slate shrink-0 flex-wrap justify-end">
                    {h.valor_a_receber != null && (
                      <span className="text-hipo-blue font-semibold">
                        R$ {fmtBRL(h.valor_a_receber)}
                      </span>
                    )}
                    <Badge tone="success">{h.conformes} ok</Badge>
                    {h.ausentes > 0 && (
                      <Badge tone="danger">{h.ausentes} ausentes</Badge>
                    )}
                    {h.divergentes > 0 && (
                      <Badge tone="warning">{h.divergentes} div.</Badge>
                    )}
                    <span>{h.total_linhas} linhas</span>
                  </div>
                </div>
              </Card>
            ))
          )}
        </div>
      )}
    </>
  );
}
