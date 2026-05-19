// web/src/pages/BDAtivados.jsx
import { useState, useEffect, useCallback } from 'react';
import {
  RefreshCw,
  Database,
  Users,
  TrendingUp,
  Calendar,
  Wallet,
  PiggyBank,
} from 'lucide-react';
import api from '../api';
import Card, { CardHeader } from '../components/ui/Card';
import KpiCard from '../components/ui/KpiCard';
import PageHeader from '../components/ui/PageHeader';
import Button from '../components/ui/Button';
import UploadButton from '../components/ui/UploadButton';
import AlertMessage from '../components/ui/AlertMessage';
import Empty from '../components/ui/Empty';
import Table, { Th, Tr, Td } from '../components/ui/Table';

const fmtBRL = (v) =>
  (Number(v) || 0).toLocaleString('pt-BR', {
    style: 'currency',
    currency: 'BRL',
    minimumFractionDigits: 2,
  });

const fmtBRLcompacto = (v) => {
  const n = Number(v) || 0;
  if (n >= 1000) return `R$ ${(n / 1000).toFixed(1)}k`;
  return fmtBRL(n);
};

export default function BDAtivadosDashboard() {
  const [resumo, setResumo] = useState(null);
  const [historico, setHistorico] = useState([]);
  const [uploading, setUploading] = useState(false);
  const [msg, setMsg] = useState(null);

  const carregar = useCallback(async () => {
    try {
      const [r, h] = await Promise.all([
        api.get('/bd-ativados/resumo').catch(() => ({ data: null })),
        api.get('/bd-ativados/historico').catch(() => ({ data: [] })),
      ]);
      setResumo(r.data);
      setHistorico(h.data);
    } catch (e) {
      console.error(e);
    }
  }, []);

  useEffect(() => {
    carregar();
  }, [carregar]);

  async function uploadBD(e) {
    const file = e.target.files[0];
    if (!file) return;
    setUploading(true);
    setMsg(null);
    const form = new FormData();
    form.append('arquivo', file);
    try {
      const { data } = await api.post('/bd-ativados/upload', form, {
        headers: { 'Content-Type': 'multipart/form-data' },
      });
      const ativos = data?.estatisticas?.ativos ?? 0;
      const liquido = data?.estatisticas?.liquido_pos_mkt ?? 0;
      setMsg({
        tipo: 'ok',
        texto: `${data.total_registros} registros processados — ${ativos} ativos. MRR Líquido: ${fmtBRL(liquido)}.`,
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

  return (
    <>
      <PageHeader
        title="BD Ativados"
        subtitle="Snapshot da base de clientes ativos — upload diário pelo ADM."
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
              onChange={uploadBD}
              loading={uploading}
              label="Upload BD Ativados"
            />
          </>
        }
      />

      {msg && (
        <AlertMessage tipo={msg.tipo} className="mb-6">
          {msg.texto}
        </AlertMessage>
      )}

      {/* KPIs gerais */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4 mb-4">
        <KpiCard
          label="Total de clientes"
          value={resumo?.total ?? 0}
          icon={Database}
          tone="blue"
        />
        <KpiCard
          label="Ativos"
          value={resumo?.ativos ?? 0}
          hint={`${resumo?.arquivados ?? 0} arquivados`}
          icon={Users}
          tone="emerald"
        />
        <KpiCard
          label="Contadores"
          value={resumo?.contadores_distintos ?? 0}
          hint={`${resumo?.com_integracao ?? 0} com integração`}
          icon={Users}
          tone="amber"
        />
        <KpiCard
          label="Data emissão"
          value={resumo?.data_emissao ? resumo.data_emissao.split(' ')[0] : '—'}
          hint={resumo?.data_emissao ? resumo.data_emissao.split(' ')[1] : null}
          icon={Calendar}
          tone="slate"
        />
      </div>

      {/* KPIs de MRR */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-4 mb-6">
        <KpiCard
          label="MRR bruto"
          value={fmtBRLcompacto(resumo?.mrr_bruto)}
          hint="Soma das mensalidades ACTIVE"
          icon={TrendingUp}
          tone="blue"
        />
        <KpiCard
          label="Repasse franqueado"
          value={fmtBRLcompacto(resumo?.repasse_franqueado)}
          hint="30,51% do MRR bruto"
          icon={Wallet}
          tone="amber"
        />
        <KpiCard
          label="MRR líquido (pós-mkt)"
          value={fmtBRLcompacto(resumo?.liquido_pos_mkt)}
          hint="Repasse − 2,5% fundo de marketing"
          icon={PiggyBank}
          tone="emerald"
        />
      </div>

      {/* Histórico */}
      <Card padding="none">
        <div className="p-5 pb-3">
          <CardHeader
            title="Histórico de uploads"
            hint={
              resumo?.data_upload
                ? `Última atualização: ${new Date(resumo.data_upload).toLocaleString('pt-BR')}`
                : undefined
            }
          />
        </div>

        {historico.length === 0 ? (
          <Empty
            title="Nenhum upload realizado"
            description="Faça o primeiro upload do BD Ativados para começar."
            icon={Database}
          />
        ) : (
          <Table>
            <thead>
              <tr>
                <Th>Data</Th>
                <Th>Arquivo</Th>
                <Th>Usuário</Th>
                <Th align="right">Ativos</Th>
                <Th align="right">MRR bruto</Th>
                <Th align="right">Líquido pós-mkt</Th>
              </tr>
            </thead>
            <tbody>
              {historico.map((h, i) => (
                <Tr key={h.id ?? i}>
                  <Td className="text-hipo-slate">
                    {new Date(h.data_upload).toLocaleString('pt-BR')}
                  </Td>
                  <Td className="font-medium">{h.nome_arquivo}</Td>
                  <Td className="text-hipo-slate">{h.usuario_nome || '—'}</Td>
                  <Td align="right">{h.linhas_ativas ?? '—'}</Td>
                  <Td align="right">
                    {h.mrr_bruto != null ? fmtBRL(h.mrr_bruto) : '—'}
                  </Td>
                  <Td align="right" className="font-semibold text-emerald-700">
                    {h.liquido_pos_mkt != null ? fmtBRL(h.liquido_pos_mkt) : '—'}
                  </Td>
                </Tr>
              ))}
            </tbody>
          </Table>
        )}
      </Card>
    </>
  );
}
