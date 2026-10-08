// web/src/components/crm/AbaContrato.jsx
//
// Contrato com assinatura eletrônica pela Autentique (entrega 053).
//
// ── O que esta aba faz ───────────────────────────────────────────────
// Painel e ferramenta ao mesmo tempo (diretriz 2): em cima, em que pé está o
// contrato — quantos já assinaram, de quem é a vez, há quantos dias está
// parado; logo abaixo, a ação que destrava (reenviar para quem é a vez,
// atualizar, baixar o assinado). A "próxima tarefa" que isto alimenta é
// "cobrar a assinatura de Fulano", e é por isso que o nome de quem é a vez
// vem em destaque.
//
// ── De onde nasce ────────────────────────────────────────────────────
// De uma versão APROVADA da proposta (botão "Contrato" na aba Proposta, ou
// "Novo contrato" aqui). O HIPO preenche o modelo com os números daquela
// versão e manda para a Autentique com os quatro signatários da minuta, na
// ordem: contratante, testemunha da contratante, contratada (o CEO, fixo
// no servidor) e testemunha da contratada.
//
// ── O que acontece quando todos assinam ──────────────────────────────
// Só registra e avisa: o PDF assinado fica disponível aqui e o executivo
// ganha uma tarefa para fazer o desfecho da oportunidade. Nada é finalizado
// sozinho.

import { useCallback, useEffect, useMemo, useState } from 'react';
import {
  FileSignature, RefreshCw, Send, Download, XCircle, Eye, CheckCircle2,
  Clock, ChevronDown, ChevronRight, UserCheck, AlertTriangle,
} from 'lucide-react';

import api from '../../api';
import Input, { Select, Textarea } from '../ui/Input';
import Button from '../ui/Button';
import Badge from '../ui/Badge';
import Empty from '../ui/Empty';
import AlertMessage from '../ui/AlertMessage';
import { mensagemDeErro } from './contatoComum';
import { diasDesde, emailValido } from './AbaEmails';

// ── Rótulos ──────────────────────────────────────────────────────────

export const STATUS_CONTRATO = {
  enviado: { rotulo: 'Aguardando assinaturas', tom: 'info' },
  assinado: { rotulo: 'Assinado por todos', tom: 'success' },
  recusado: { rotulo: 'Recusado', tom: 'danger' },
  cancelado: { rotulo: 'Cancelado', tom: 'neutral' },
};

export const SITUACAO_SIGNATARIO = {
  pendente: { rotulo: 'Aguardando', tom: 'neutral' },
  visualizado: { rotulo: 'Abriu', tom: 'info' },
  assinado: { rotulo: 'Assinou', tom: 'success' },
  recusado: { rotulo: 'Recusou', tom: 'danger' },
  falha_entrega: { rotulo: 'E-mail não entregue', tom: 'warning' },
};

function dataHora(iso) {
  if (!iso) return '—';
  return new Date(iso).toLocaleString('pt-BR', {
    timeZone: 'America/Sao_Paulo', day: '2-digit', month: '2-digit',
    hour: '2-digit', minute: '2-digit',
  });
}

function dataCurta(iso) {
  if (!iso) return '—';
  const [a, m, d] = String(iso).slice(0, 10).split('-');
  return `${d}/${m}/${a}`;
}

function rotuloDias(n) {
  if (n === null || n === undefined) return '';
  if (n === 0) return 'hoje';
  if (n === 1) return 'há 1 dia';
  return `há ${n} dias`;
}

// O contrato que importa agora: o em andamento; senão o mais recente.
export function contratoAtual(contratos) {
  if (!contratos?.length) return null;
  return contratos.find((c) => c.status === 'enviado') || contratos[0];
}

// O que o painel mostra. "Parado há" conta desde a última assinatura (ou do
// envio, se ninguém assinou): é o tempo que a vez está com a mesma pessoa.
export function resumoContrato(contrato, agora = new Date()) {
  if (!contrato) return null;
  const assinaturas = contrato.signatarios
    .map((s) => s.assinado_em)
    .filter(Boolean)
    .sort();
  const desde = assinaturas.length ? assinaturas[assinaturas.length - 1] : contrato.criado_em;
  return {
    assinados: contrato.assinados,
    total: contrato.total_signatarios,
    vez: contrato.signatarios.find((s) => s.da_vez) || null,
    paradoDias: contrato.status === 'enviado' ? diasDesde(desde, agora) : null,
  };
}

// Download autenticado (a rota exige o Bearer): blob + âncora.
async function baixarPdf(url, nomePadrao, params) {
  const resp = await api.get(url, { params, responseType: 'blob' });
  const disposicao = resp.headers?.['content-disposition'] || '';
  const achado = /filename="?([^";]+)"?/.exec(disposicao);
  const link = document.createElement('a');
  const href = URL.createObjectURL(resp.data);
  link.href = href;
  link.download = achado ? achado[1] : nomePadrao;
  document.body.appendChild(link);
  link.click();
  link.remove();
  URL.revokeObjectURL(href);
}

async function erroDeBlob(err, padrao) {
  const corpo = err?.response?.data;
  if (corpo instanceof Blob) {
    try {
      return JSON.parse(await corpo.text()).detail || padrao;
    } catch {
      return padrao;
    }
  }
  return mensagemDeErro(err, padrao);
}

// ── Uma pessoa do formulário ─────────────────────────────────────────
// Escolhe do cadastro (preenche nome e e-mail) ou digita. Nome e e-mail
// ficam sempre editáveis: o cadastro pode ter o e-mail antigo.

function CampoPessoa({ titulo, opcoes, valor, onChange, idBase, ajuda }) {
  const escolhido = valor.origem_id || '';
  return (
    <fieldset className="rounded-lg border border-hipo-border p-3 space-y-2">
      <legend className="px-1 text-xs font-semibold text-hipo-ink">{titulo}</legend>
      <Select
        id={`${idBase}-origem`}
        label="Do cadastro"
        value={escolhido}
        onChange={(e) => {
          const id = e.target.value;
          const p = opcoes.find((o) => o.id === id);
          onChange(p
            ? { origem_id: p.id, nome: p.nome, email: p.email || '' }
            : { ...valor, origem_id: '' });
        }}
      >
        <option value="">Outra pessoa (digitar)</option>
        {opcoes.map((o) => (
          <option key={o.id} value={o.id}>
            {o.nome}{o.detalhe ? ` · ${o.detalhe}` : ''}{o.email ? '' : ' (sem e-mail)'}
          </option>
        ))}
      </Select>
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
        <Input
          id={`${idBase}-nome`}
          label="Nome"
          value={valor.nome}
          onChange={(e) => onChange({ ...valor, nome: e.target.value })}
        />
        <Input
          id={`${idBase}-email`}
          label="E-mail"
          type="email"
          value={valor.email}
          error={valor.email && !emailValido(valor.email) ? 'E-mail inválido' : undefined}
          onChange={(e) => onChange({ ...valor, email: e.target.value })}
        />
      </div>
      {ajuda && <p className="text-[11px] text-hipo-slate">{ajuda}</p>}
    </fieldset>
  );
}

const VAZIA = { origem_id: '', nome: '', email: '' };

function pessoaDe(lista, id) {
  const p = lista.find((o) => o.id === id);
  return p ? { origem_id: p.id, nome: p.nome, email: p.email || '' } : VAZIA;
}

// ── Formulário de envio ──────────────────────────────────────────────

export function FormContrato({ propostaId, situacao, onCancelar, onEnviado }) {
  const [padrao, setPadrao] = useState(null);
  const [erro, setErro] = useState(null);
  const [contratante, setContratante] = useState(VAZIA);
  const [testContratante, setTestContratante] = useState(VAZIA);
  const [testContratada, setTestContratada] = useState(VAZIA);
  const [datas, setDatas] = useState({ data_contrato: '', inicio_vigencia: '', dia_vencimento: 10 });
  const [ocupado, setOcupado] = useState(null);

  useEffect(() => {
    let vivo = true;
    api.get(`/crm/propostas/${propostaId}/contrato-padrao`)
      .then(({ data }) => {
        if (!vivo) return;
        setPadrao(data);
        setContratante(pessoaDe(data.contatos, data.sugestao_contratante_id));
        setTestContratada(pessoaDe(data.usuarios, data.sugestao_testemunha_contratada_id));
        setDatas({
          data_contrato: data.data_contrato,
          inicio_vigencia: data.inicio_vigencia,
          dia_vencimento: data.dia_vencimento,
        });
      })
      .catch((err) => vivo && setErro(mensagemDeErro(err, 'Não foi possível carregar o contrato.')));
    return () => { vivo = false; };
  }, [propostaId]);

  const pessoas = [contratante, testContratante, testContratada];
  const emails = pessoas.map((p) => p.email.trim().toLowerCase()).filter(Boolean);
  const repetido = new Set(emails).size !== emails.length
    || (padrao && emails.includes((padrao.contratada_email || '').toLowerCase()));
  const completo = pessoas.every((p) => p.nome.trim() && emailValido(p.email));
  const bloqueio = !padrao ? 'carregando'
    : !padrao.aprovada ? 'Aprove esta versão da proposta antes de mandar o contrato.'
      : !padrao.oportunidade_aberta ? 'A oportunidade já foi finalizada.'
        : padrao.contrato_em_aberto_id ? 'Já há um contrato aguardando assinatura. Cancele-o antes de mandar outro.'
          : padrao.pendencias_endereco.length
            ? `Complete o endereço da conta (falta: ${padrao.pendencias_endereco.join(', ')}).`
            : !situacao?.configurado ? 'O envio está desligado neste servidor.'
              : !completo ? 'Preencha nome e e-mail válidos dos três signatários.'
                : repetido ? 'Cada assinatura precisa ser de uma pessoa diferente (e-mail repetido).'
                  : null;

  function corpoDatas() {
    return {
      data_contrato: datas.data_contrato || null,
      inicio_vigencia: datas.inicio_vigencia || null,
      dia_vencimento: Number(datas.dia_vencimento) || 10,
    };
  }

  async function previa() {
    setOcupado('previa');
    setErro(null);
    try {
      const resp = await api.post(`/crm/propostas/${propostaId}/contrato/previa`, corpoDatas(),
        { responseType: 'blob' });
      const url = URL.createObjectURL(resp.data);
      window.open(url, '_blank', 'noopener');
      setTimeout(() => URL.revokeObjectURL(url), 60000);
    } catch (err) {
      setErro(await erroDeBlob(err, 'Não foi possível montar a prévia.'));
    } finally {
      setOcupado(null);
    }
  }

  async function enviar() {
    setOcupado('enviar');
    setErro(null);
    const sig = (papel, p, campoOrigem) => ({
      papel,
      nome: p.nome.trim(),
      email: p.email.trim(),
      ...(p.origem_id ? { [campoOrigem]: p.origem_id } : {}),
    });
    try {
      const { data } = await api.post(`/crm/propostas/${propostaId}/contratos`, {
        ...corpoDatas(),
        signatarios: [
          sig('contratante', contratante, 'contato_id'),
          sig('testemunha_contratante', testContratante, 'contato_id'),
          sig('testemunha_contratada', testContratada, 'usuario_id'),
        ],
      });
      onEnviado(data);
    } catch (err) {
      setErro(mensagemDeErro(err, 'Não foi possível enviar o contrato.'));
    } finally {
      setOcupado(null);
    }
  }

  if (!padrao) {
    return erro
      ? <AlertMessage tipo="erro">{erro}</AlertMessage>
      : <p className="text-sm text-hipo-slate">Carregando contrato…</p>;
  }

  const contatosComEmail = padrao.contatos;
  return (
    <section aria-label="Novo contrato" className="rounded-lg border border-hipo-blue/40 bg-hipo-card p-4 space-y-4">
      <div className="flex items-start gap-2">
        <FileSignature size={18} className="text-hipo-blue mt-0.5" aria-hidden="true" />
        <div className="min-w-0">
          <h3 className="text-sm font-semibold text-hipo-ink">
            Contrato a partir da proposta v{padrao.proposta_versao}
          </h3>
          <p className="text-xs text-hipo-slate">
            {padrao.cliente_razao_social} · CNPJ {padrao.cliente_cnpj}
          </p>
          <p className="text-xs text-hipo-slate truncate" title={padrao.endereco}>
            {padrao.endereco || 'Sem endereço no cadastro'}
          </p>
        </div>
      </div>

      {erro && <AlertMessage tipo="erro">{erro}</AlertMessage>}
      {situacao?.sandbox && (
        <AlertMessage tipo="aviso">
          Ambiente de teste: o documento vai para o sandbox da Autentique e não tem valor.
        </AlertMessage>
      )}

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-3">
        <CampoPessoa
          idBase="contratante"
          titulo="1 · Contratante (quem assina pelo cliente)"
          opcoes={contatosComEmail}
          valor={contratante}
          onChange={setContratante}
        />
        <CampoPessoa
          idBase="test-contratante"
          titulo="2 · Testemunha da contratante"
          opcoes={contatosComEmail}
          valor={testContratante}
          onChange={setTestContratante}
          ajuda="Alguém do cliente que não seja quem assina."
        />
        <fieldset className="rounded-lg border border-hipo-border p-3">
          <legend className="px-1 text-xs font-semibold text-hipo-ink">3 · Contratada</legend>
          <p className="text-sm text-hipo-ink flex items-center gap-1.5">
            <UserCheck size={14} className="text-hipo-success" aria-hidden="true" />
            {padrao.contratada_nome || '—'}
          </p>
          <p className="text-xs text-hipo-slate">{padrao.contratada_email || 'não configurado no servidor'}</p>
          <p className="text-[11px] text-hipo-slate mt-1">Fixo: assina sempre pela Controller.</p>
        </fieldset>
        <CampoPessoa
          idBase="test-contratada"
          titulo="4 · Testemunha da contratada"
          opcoes={padrao.usuarios}
          valor={testContratada}
          onChange={setTestContratada}
        />
      </div>

      <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
        <Input
          id="contrato-data"
          label="Data do contrato"
          type="date"
          value={datas.data_contrato || ''}
          onChange={(e) => setDatas((d) => ({ ...d, data_contrato: e.target.value }))}
        />
        <Input
          id="contrato-inicio"
          label="Início da vigência"
          type="date"
          value={datas.inicio_vigencia || ''}
          onChange={(e) => setDatas((d) => ({ ...d, inicio_vigencia: e.target.value }))}
        />
        <Input
          id="contrato-vencimento"
          label="Vencimento (dia do mês)"
          type="number"
          min="1"
          max="28"
          value={datas.dia_vencimento}
          onChange={(e) => setDatas((d) => ({ ...d, dia_vencimento: e.target.value }))}
        />
      </div>

      <div className="rounded-lg bg-hipo-bg border border-hipo-border p-3">
        <p className="text-xs font-semibold text-hipo-ink mb-1">Cláusula 5 — como vai sair</p>
        <ul className="space-y-0.5" aria-label="Valores do contrato">
          {padrao.linhas_preco.map((l) => (
            <li key={l} className="text-xs text-hipo-slate">{l}</li>
          ))}
        </ul>
      </div>

      {bloqueio && bloqueio !== 'carregando' && (
        <p className="text-xs text-hipo-warning flex items-center gap-1" role="status">
          <AlertTriangle size={12} aria-hidden="true" /> {bloqueio}
        </p>
      )}

      <div className="flex flex-wrap justify-end gap-2">
        <Button variant="ghost" onClick={onCancelar} disabled={Boolean(ocupado)}>Cancelar</Button>
        <Button
          variant="secondary"
          icon={Eye}
          onClick={previa}
          loading={ocupado === 'previa'}
          disabled={Boolean(ocupado) || !situacao?.previa_disponivel
            || padrao.pendencias_endereco.length > 0}
        >
          Prévia do PDF
        </Button>
        <Button icon={Send} onClick={enviar} loading={ocupado === 'enviar'}
          disabled={Boolean(ocupado) || Boolean(bloqueio)}>
          Enviar para assinatura
        </Button>
      </div>
    </section>
  );
}

// ── O contrato ───────────────────────────────────────────────────────

function Signatario({ s }) {
  const sit = SITUACAO_SIGNATARIO[s.situacao] || SITUACAO_SIGNATARIO.pendente;
  const quando = s.assinado_em || s.recusado_em || s.visualizado_em;
  return (
    <li className={`flex items-start gap-3 rounded-lg border p-2.5 ${
      s.da_vez ? 'border-hipo-blue bg-hipo-blueSoft/40' : 'border-hipo-border bg-hipo-card'}`}
    >
      <span className={`shrink-0 w-6 h-6 rounded-full grid place-items-center text-xs font-semibold ${
        s.situacao === 'assinado' ? 'bg-hipo-successSoft text-hipo-success' : 'bg-hipo-bg text-hipo-slate'}`}
      >
        {s.situacao === 'assinado' ? <CheckCircle2 size={14} /> : s.ordem}
      </span>
      <div className="min-w-0 flex-1">
        <p className="text-sm text-hipo-ink truncate">
          {s.nome}
          <span className="text-xs text-hipo-slate"> · {s.papel_rotulo}</span>
        </p>
        <p className="text-xs text-hipo-slate truncate">{s.email}</p>
        {s.motivo_recusa && <p className="text-xs text-hipo-danger mt-0.5">Motivo: {s.motivo_recusa}</p>}
      </div>
      <div className="flex flex-col items-end gap-1 shrink-0">
        <Badge tone={sit.tom}>{s.da_vez && s.situacao !== 'assinado' ? 'É a vez' : sit.rotulo}</Badge>
        {quando && <span className="text-[11px] text-hipo-slate">{dataHora(quando)}</span>}
      </div>
    </li>
  );
}

function CartaoContrato({ contrato, onMudou, agora }) {
  const [ocupado, setOcupado] = useState(null);
  const [erro, setErro] = useState(null);
  const [cancelando, setCancelando] = useState(false);
  const [motivo, setMotivo] = useState('');
  const st = STATUS_CONTRATO[contrato.status];
  const resumo = resumoContrato(contrato, agora);
  const vez = resumo.vez;

  async function acao(chave, fn, padrao) {
    setOcupado(chave);
    setErro(null);
    try {
      const { data } = await fn();
      onMudou(data);
      return true;
    } catch (err) {
      setErro(mensagemDeErro(err, padrao));
      return false;
    } finally {
      setOcupado(null);
    }
  }

  async function baixar(tipo) {
    setOcupado(`baixar-${tipo}`);
    setErro(null);
    try {
      await baixarPdf(`/crm/contratos/${contrato.id}/arquivo`,
        `contrato-v${contrato.versao}${tipo === 'assinado' ? '-assinado' : ''}.pdf`, { tipo });
    } catch (err) {
      setErro(await erroDeBlob(err, 'Não foi possível baixar o contrato.'));
    } finally {
      setOcupado(null);
    }
  }

  return (
    <article aria-label={`Contrato v${contrato.versao}`} className="rounded-lg border border-hipo-border bg-hipo-card p-4 space-y-3">
      <header className="flex flex-wrap items-center gap-2">
        <Badge tone="info">v{contrato.versao}</Badge>
        <Badge tone={st.tom}>{st.rotulo}</Badge>
        {contrato.sandbox && <Badge tone="warning">Teste (sandbox)</Badge>}
        <span className="text-xs text-hipo-slate">
          proposta v{contrato.proposta_versao} · enviado {dataHora(contrato.criado_em)}
          {contrato.criado_por_nome ? ` por ${contrato.criado_por_nome}` : ''}
        </span>
      </header>

      {erro && <AlertMessage tipo="erro">{erro}</AlertMessage>}
      {contrato.sincronizacao_erro && contrato.status === 'enviado' && (
        <AlertMessage tipo="aviso">Última leitura da Autentique falhou: {contrato.sincronizacao_erro}</AlertMessage>
      )}

      <ol className="space-y-1.5" aria-label="Signatários">
        {contrato.signatarios.map((s) => <Signatario key={s.id} s={s} />)}
      </ol>

      <p className="text-[11px] text-hipo-muted">
        Vigência a partir de {dataCurta(contrato.inicio_vigencia)} · vencimento dia{' '}
        {String(contrato.dia_vencimento).padStart(2, '0')} · hash {contrato.hash_original.slice(0, 12)}…
        {contrato.cancelado_em && ` · cancelado ${dataHora(contrato.cancelado_em)}`}
        {contrato.motivo_cancelamento && ` (${contrato.motivo_cancelamento})`}
      </p>

      <div className="flex flex-wrap justify-end gap-2">
        {contrato.status === 'enviado' && vez && (
          <Button size="sm" variant="secondary" icon={Send}
            loading={ocupado === 'reenviar'} disabled={Boolean(ocupado)}
            onClick={() => acao('reenviar',
              () => api.post(`/crm/contratos/${contrato.id}/reenviar`, {}),
              'Não foi possível reenviar.')}
          >
            Reenviar para {vez.nome.split(' ')[0]}
          </Button>
        )}
        {contrato.status === 'enviado' && (
          <Button size="sm" variant="secondary" icon={RefreshCw}
            loading={ocupado === 'sincronizar'} disabled={Boolean(ocupado)}
            onClick={() => acao('sincronizar',
              () => api.post(`/crm/contratos/${contrato.id}/sincronizar`, {}),
              'Não foi possível ler a Autentique agora.')}
          >
            Atualizar
          </Button>
        )}
        <Button size="sm" variant="secondary" icon={Download}
          loading={ocupado === 'baixar-original'} disabled={Boolean(ocupado)}
          onClick={() => baixar('original')}
        >
          Original
        </Button>
        {contrato.status === 'assinado' && (
          <Button size="sm" icon={Download}
            loading={ocupado === 'baixar-assinado'} disabled={Boolean(ocupado)}
            onClick={() => baixar('assinado')}
          >
            Contrato assinado
          </Button>
        )}
        {contrato.pode_cancelar && !cancelando && (
          <Button size="sm" variant="ghost" icon={XCircle} disabled={Boolean(ocupado)}
            onClick={() => setCancelando(true)}
          >
            Cancelar
          </Button>
        )}
      </div>

      {cancelando && (
        <div className="rounded-lg border border-hipo-dangerBorder bg-hipo-dangerSoft/40 p-3 space-y-2">
          <Textarea
            id={`motivo-${contrato.id}`}
            label="Por que cancelar?"
            rows={2}
            value={motivo}
            onChange={(e) => setMotivo(e.target.value)}
            hint="O documento é bloqueado na Autentique: ninguém mais consegue assinar esta versão."
          />
          <div className="flex justify-end gap-2">
            <Button size="sm" variant="ghost" onClick={() => setCancelando(false)}>Voltar</Button>
            <Button size="sm" variant="danger" loading={ocupado === 'cancelar'}
              disabled={motivo.trim().length < 3 || Boolean(ocupado)}
              onClick={async () => {
                const ok = await acao('cancelar',
                  () => api.post(`/crm/contratos/${contrato.id}/cancelar`, { motivo: motivo.trim() }),
                  'Não foi possível cancelar.');
                if (ok) setCancelando(false);
              }}
            >
              Cancelar contrato
            </Button>
          </div>
        </div>
      )}

      {contrato.eventos.length > 0 && (
        <details className="text-xs">
          <summary className="cursor-pointer text-hipo-blue">Linha do tempo</summary>
          <ul className="mt-2 space-y-1" aria-label="Eventos do contrato">
            {contrato.eventos.map((e) => (
              <li key={e.id} className="flex gap-2 text-hipo-slate">
                <span className="shrink-0 tabular-nums">{dataHora(e.criado_em)}</span>
                <span className="text-hipo-ink">{e.descricao || e.tipo}</span>
                {e.usuario_nome && <span>· {e.usuario_nome}</span>}
              </li>
            ))}
          </ul>
        </details>
      )}
    </article>
  );
}

// ── Aba ──────────────────────────────────────────────────────────────

export default function AbaContrato({ oportunidade, preset, onPresetUsado, onMudou, agora: agoraTeste }) {
  const oppId = oportunidade.id;
  const [situacao, setSituacao] = useState(null);
  const [contratos, setContratos] = useState(null);
  const [aprovadas, setAprovadas] = useState([]);
  const [compondo, setCompondo] = useState(null);
  const [verAnteriores, setVerAnteriores] = useState(false);
  const [erro, setErro] = useState(null);
  const [aviso, setAviso] = useState(null);
  const agora = useMemo(() => agoraTeste || new Date(), [agoraTeste]);

  const carregar = useCallback(async () => {
    try {
      const [sit, lista, props] = await Promise.all([
        api.get('/crm/contratos/situacao'),
        api.get(`/crm/oportunidades/${oppId}/contratos`),
        api.get(`/crm/oportunidades/${oppId}/propostas`),
      ]);
      setSituacao(sit.data);
      setContratos(lista.data);
      setAprovadas((props.data || []).filter((p) => p.aprovada_em));
    } catch (err) {
      setErro(mensagemDeErro(err, 'Não foi possível carregar os contratos.'));
      setContratos((c) => c || []);
    }
  }, [oppId]);

  useEffect(() => { carregar(); }, [carregar]);

  // Vindo do botão "Contrato" de uma versão da proposta.
  useEffect(() => {
    if (preset?.proposta_id && contratos) {
      setCompondo(preset.proposta_id);
      onPresetUsado?.();
    }
  }, [preset, contratos, onPresetUsado]);

  const atual = contratoAtual(contratos);
  const anteriores = (contratos || []).filter((c) => c !== atual);
  const resumo = resumoContrato(atual, agora);
  const emAndamento = atual?.status === 'enviado';
  const ligado = Boolean(situacao?.configurado);

  function trocar(contrato) {
    setContratos((lista) => (lista || []).map((c) => (c.id === contrato.id ? contrato : c)));
    onMudou?.();
  }

  if (!contratos) return <p className="text-sm text-hipo-slate">Carregando contratos…</p>;

  return (
    <div className="space-y-4">
      {erro && <AlertMessage tipo="erro">{erro}</AlertMessage>}
      {aviso && <AlertMessage tipo="ok">{aviso}</AlertMessage>}
      {situacao && !ligado && (
        <AlertMessage tipo="aviso">
          O envio de contrato pela Autentique está desligado neste servidor. {situacao.problemas.join('; ')}.
        </AlertMessage>
      )}

      {/* ── Painel ── */}
      <section aria-label="Resumo do contrato" className="flex flex-wrap items-center gap-x-6 gap-y-2 rounded-lg border border-hipo-border bg-hipo-card px-4 py-3">
        <div>
          <p className="text-[11px] uppercase tracking-wide text-hipo-slate">Situação</p>
          <p className="text-sm font-semibold text-hipo-ink" data-testid="kpi-situacao">
            {atual ? STATUS_CONTRATO[atual.status].rotulo : 'Sem contrato'}
          </p>
        </div>
        <div>
          <p className="text-[11px] uppercase tracking-wide text-hipo-slate">Assinaturas</p>
          <p className="text-lg font-semibold text-hipo-ink" data-testid="kpi-assinaturas">
            {resumo ? `${resumo.assinados} de ${resumo.total}` : '—'}
          </p>
        </div>
        {emAndamento && resumo.vez && (
          <div>
            <p className="text-[11px] uppercase tracking-wide text-hipo-slate">É a vez de</p>
            <p className="text-sm font-semibold text-hipo-ink" data-testid="kpi-vez">
              {resumo.vez.nome}
              <span className="ml-1 text-xs font-normal text-hipo-slate inline-flex items-center gap-0.5">
                <Clock size={11} aria-hidden="true" /> parado {rotuloDias(resumo.paradoDias)}
              </span>
            </p>
          </div>
        )}
        <div className="ml-auto">
          {!compondo && (
            <Button
              size="sm"
              icon={FileSignature}
              disabled={!ligado || emAndamento || aprovadas.length === 0}
              title={emAndamento ? 'Já há um contrato aguardando assinatura.'
                : aprovadas.length === 0 ? 'Aprove uma versão da proposta primeiro.' : undefined}
              onClick={() => setCompondo(aprovadas[0].id)}
            >
              Novo contrato
            </Button>
          )}
        </div>
      </section>

      {compondo && (
        <>
          {aprovadas.length > 1 && (
            <Select
              id="contrato-proposta"
              label="Versão da proposta"
              value={compondo}
              onChange={(e) => setCompondo(e.target.value)}
              className="max-w-xs"
            >
              {aprovadas.map((p) => (
                <option key={p.id} value={p.id}>v{p.versao}</option>
              ))}
            </Select>
          )}
          <FormContrato
            key={compondo}
            propostaId={compondo}
            situacao={situacao}
            onCancelar={() => setCompondo(null)}
            onEnviado={(novo) => {
              setContratos((lista) => [novo, ...(lista || [])]);
              setCompondo(null);
              setAviso(`Contrato enviado. ${novo.proximo_nome} recebe o e-mail para assinar primeiro.`);
              onMudou?.();
            }}
          />
        </>
      )}

      {atual ? (
        <CartaoContrato contrato={atual} onMudou={trocar} agora={agora} />
      ) : !compondo && (
        <Empty
          title="Nenhum contrato enviado"
          description={aprovadas.length
            ? 'Use “Novo contrato” (ou o botão Contrato numa versão aprovada da proposta). O cliente assina pela Autentique.'
            : 'O contrato sai de uma versão APROVADA da proposta. Gere e aprove a proposta primeiro.'}
          icon={FileSignature}
        />
      )}

      {anteriores.length > 0 && (
        <div>
          <button
            type="button"
            onClick={() => setVerAnteriores((v) => !v)}
            aria-expanded={verAnteriores}
            className="text-xs text-hipo-blue inline-flex items-center gap-1 hover:underline"
          >
            {verAnteriores ? <ChevronDown size={12} /> : <ChevronRight size={12} />}
            Versões anteriores ({anteriores.length})
          </button>
          {verAnteriores && (
            <div className="mt-2 space-y-2">
              {anteriores.map((c) => (
                <CartaoContrato key={c.id} contrato={c} onMudou={trocar} agora={agora} />
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  );
}
