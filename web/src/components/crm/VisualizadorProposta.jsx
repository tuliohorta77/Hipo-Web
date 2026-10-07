// web/src/components/crm/VisualizadorProposta.jsx
//
// O visualizador da proposta, dentro do HIPO (entrega 051).
//
// ── Por que existe ───────────────────────────────────────────────────
// Antes, o vendedor gerava, baixava o PPTX, abria no PC para conferir e só
// então ia mandar o e-mail. O objetivo é tirar do caminho tudo o que
// acontece fora do HIPO: aqui ele VÊ o arquivo exatamente como o cliente vai
// receber (o mesmo PDF que vai anexado) e dá o ok. Só proposta aprovada
// aparece para anexar na aba E-mails.
//
// ── Como mostra ──────────────────────────────────────────────────────
// Pede o PDF à mesma rota do download (/crm/propostas/{id}/arquivo) e
// mostra num <iframe> com URL de blob — o visualizador de PDF do próprio
// navegador. Com vários CNPJs, um seletor troca entre a consolidada e a de
// cada CNPJ; a aprovação vale para a versão inteira.
//
// Servidor sem LibreOffice não gera PDF: o visualizador diz isso, oferece o
// PPTX e deixa aprovar (o e-mail, que também precisa do PDF, é que fica
// indisponível — e ele já avisa).
//
// ── Nível ────────────────────────────────────────────────────────────
// Abre por cima da oportunidade, que pode estar no nível 1 (funil) ou 2
// (módulo de Tarefas). Por isso o padrão é 3 — ver CAMADAS em ui/Modal.

import { useEffect, useRef, useState } from 'react';
import { CheckCircle2, Download, FileType2, Loader2 } from 'lucide-react';

import api from '../../api';
import Modal from '../ui/Modal';
import Button from '../ui/Button';
import Badge from '../ui/Badge';
import AlertMessage from '../ui/AlertMessage';

async function mensagemDoBlob(err, padrao) {
  const corpo = err?.response?.data;
  if (corpo instanceof Blob) {
    try {
      return JSON.parse(await corpo.text()).detail || padrao;
    } catch {
      return padrao;
    }
  }
  const d = err?.response?.data?.detail;
  if (typeof d === 'string') return d;
  return padrao;
}

function formatarDataHora(iso) {
  if (!iso) return '';
  return new Date(iso).toLocaleString('pt-BR', {
    day: '2-digit', month: '2-digit', year: 'numeric', hour: '2-digit', minute: '2-digit',
  });
}

export default function VisualizadorProposta({
  proposta,
  itemInicial = null,
  pdfDisponivel,
  onFechar,
  onAprovada,
  onBaixar,
  nivel = 3,
}) {
  const [recorte, setRecorte] = useState(itemInicial?.id || '');
  const [url, setUrl] = useState(null);
  const [carregando, setCarregando] = useState(false);
  const [erro, setErro] = useState(null);
  const [aprovando, setAprovando] = useState(false);
  const urlAtual = useRef(null);

  const aberto = Boolean(proposta);
  const itens = proposta?.itens || [];
  const varios = itens.length > 1;
  const item = recorte ? itens.find((i) => i.id === recorte) || null : null;

  // Troca de proposta (outra versão aberta) volta para o recorte pedido.
  useEffect(() => {
    setRecorte(itemInicial?.id || '');
  }, [proposta?.id, itemInicial?.id]);

  useEffect(() => {
    if (!aberto || !pdfDisponivel) return undefined;
    let vivo = true;
    setCarregando(true);
    setErro(null);
    const params = { formato: 'pdf' };
    if (recorte) params.item = recorte;
    api.get(`/crm/propostas/${proposta.id}/arquivo`, { params, responseType: 'blob' })
      .then((resp) => {
        if (!vivo) return;
        const blob = resp.data instanceof Blob
          ? resp.data
          : new Blob([resp.data], { type: 'application/pdf' });
        const novo = URL.createObjectURL(
          blob.type === 'application/pdf' ? blob : new Blob([blob], { type: 'application/pdf' }),
        );
        if (urlAtual.current) URL.revokeObjectURL(urlAtual.current);
        urlAtual.current = novo;
        setUrl(novo);
      })
      .catch(async (err) => {
        if (vivo) setErro(await mensagemDoBlob(err, 'Não foi possível montar o PDF da proposta.'));
      })
      .finally(() => { if (vivo) setCarregando(false); });
    return () => { vivo = false; };
  }, [aberto, pdfDisponivel, proposta?.id, recorte]);

  // Fechou: solta a memória do PDF (7 MB por arquivo).
  useEffect(() => {
    if (aberto) return;
    if (urlAtual.current) URL.revokeObjectURL(urlAtual.current);
    urlAtual.current = null;
    setUrl(null);
  }, [aberto]);

  async function aprovar() {
    setAprovando(true);
    setErro(null);
    try {
      const { data } = await api.post(`/crm/propostas/${proposta.id}/aprovar`, {});
      onAprovada?.(data);
    } catch (err) {
      setErro(await mensagemDoBlob(err, 'Não foi possível aprovar a proposta.'));
    } finally {
      setAprovando(false);
    }
  }

  const aprovada = Boolean(proposta?.aprovada_em);

  return (
    <Modal
      aberto={aberto}
      onFechar={onFechar}
      nivel={nivel}
      size="full"
      titulo={proposta ? `Proposta v${proposta.versao}` : ''}
      subtitulo={item ? `Só ${item.razao_social}` : (varios ? `Consolidada — ${itens.length} CNPJs` : undefined)}
      acoes={proposta ? (
        <div className="flex items-center gap-2">
          {aprovada ? (
            <Badge tone="success">
              Aprovada{proposta.aprovada_por_nome ? ` por ${proposta.aprovada_por_nome}` : ''}
              {proposta.aprovada_em ? ` em ${formatarDataHora(proposta.aprovada_em)}` : ''}
            </Badge>
          ) : (
            <Button
              size="sm"
              icon={CheckCircle2}
              loading={aprovando}
              onClick={aprovar}
              disabled={carregando && pdfDisponivel}
            >
              Aprovar para envio
            </Button>
          )}
        </div>
      ) : undefined}
    >
      {proposta && (
        <div className="flex flex-col h-full gap-3">
          <div className="flex flex-wrap items-center gap-2">
            {varios && (
              <label className="text-xs text-hipo-slate flex items-center gap-2">
                Ver
                <select
                  aria-label="Qual arquivo ver"
                  value={recorte}
                  onChange={(e) => setRecorte(e.target.value)}
                  className="h-8 px-2 text-xs rounded-lg border border-hipo-border bg-hipo-card text-hipo-ink focus:outline-none focus:ring-2 focus:ring-hipo-blue"
                >
                  <option value="">Consolidada ({itens.length} CNPJs)</option>
                  {itens.filter((i) => i.id).map((i) => (
                    <option key={i.id} value={i.id}>Só {i.razao_social}</option>
                  ))}
                </select>
              </label>
            )}
            <div className="flex-1" />
            <Button size="sm" variant="secondary" icon={Download}
              onClick={() => onBaixar?.(proposta, 'pptx', item)}>
              PPTX
            </Button>
            {pdfDisponivel && (
              <Button size="sm" variant="secondary" icon={FileType2}
                onClick={() => onBaixar?.(proposta, 'pdf', item)}>
                PDF
              </Button>
            )}
          </div>

          {!aprovada && (
            <p className="text-xs text-hipo-slate">
              Confira o arquivo como o cliente vai receber. Aprovar libera esta
              versão para ir anexada na aba E-mails. Achou algo errado? Feche,
              ajuste o formulário e gere outra versão.
            </p>
          )}
          {erro && <AlertMessage tipo="erro">{erro}</AlertMessage>}

          {!pdfDisponivel ? (
            <AlertMessage tipo="aviso">
              Este servidor não gera PDF (sem LibreOffice), então não dá para
              mostrar a proposta aqui. Baixe o PPTX para conferir.
            </AlertMessage>
          ) : (
            <div className="relative flex-1 min-h-[60vh] rounded-lg border border-hipo-border bg-hipo-bg overflow-hidden">
              {carregando && (
                <div className="absolute inset-0 flex flex-col items-center justify-center gap-2 text-sm text-hipo-slate bg-hipo-bg/80 z-10">
                  <Loader2 size={20} className="animate-spin" aria-hidden="true" />
                  Montando o PDF — leva alguns segundos…
                </div>
              )}
              {url && (
                <iframe
                  title="Visualização da proposta"
                  src={url}
                  className="w-full h-full min-h-[60vh] border-0"
                />
              )}
            </div>
          )}
        </div>
      )}
    </Modal>
  );
}
