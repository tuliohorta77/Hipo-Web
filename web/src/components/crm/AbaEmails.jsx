// web/src/components/crm/AbaEmails.jsx
//
// E-mail comercial da oportunidade (entrega 050).
//
// ── O que esta aba faz ───────────────────────────────────────────────
// É painel e ferramenta ao mesmo tempo (diretriz 2): em cima, quantos
// e-mails saíram, quantos o cliente respondeu e há quanto tempo o último
// está sem resposta; embaixo, o que saiu, e o botão que escreve o próximo.
//
// O e-mail sai DA CAIXA DE QUEM ESTÁ LOGADO, pelo Gmail, com a assinatura
// que a pessoa já usa. A resposta do cliente cai na caixa dela — o HIPO só
// olha os cabeçalhos para saber SE respondeu.
//
// ── Modelo → rascunho → envio ────────────────────────────────────────
// Escolher modelo, contato ou proposta pede ao servidor o rascunho
// preenchido. O vendedor lê, ajusta e manda; o que vai é o que está na
// tela. Se ele já mexeu no texto, trocar o modelo NÃO apaga a edição: a
// tela avisa que o rascunho ficou para trás e oferece preencher de novo.

import { useCallback, useEffect, useMemo, useState } from 'react';
import {
  Mail, Send, RefreshCw, Paperclip, X, ChevronDown, ChevronRight, Reply,
  Clock, PenLine,
} from 'lucide-react';

import api from '../../api';
import Input, { Select, Textarea } from '../ui/Input';
import Button from '../ui/Button';
import Badge from '../ui/Badge';
import Empty from '../ui/Empty';
import AlertMessage from '../ui/AlertMessage';
import ModelosEmail from './ModelosEmail';
import { mensagemDeErro } from './contatoComum';

const EMAIL_RE = /^[^@\s,;<>()"']+@[^@\s,;<>()"']+\.[^@\s,;<>()"']{2,}$/;

export function emailValido(e) {
  return EMAIL_RE.test(String(e || '').trim());
}

// "há 3 dias" / "hoje". Dias corridos: é o que o vendedor fala ("mandei
// segunda e até agora nada"), e a cadência dos Touchs vai decidir os úteis.
export function diasDesde(iso, agora = new Date()) {
  if (!iso) return null;
  return Math.max(0, Math.floor((agora.getTime() - new Date(iso).getTime()) / 86400000));
}

function rotuloDias(n) {
  if (n === null || n === undefined) return '';
  if (n === 0) return 'hoje';
  if (n === 1) return 'há 1 dia';
  return `há ${n} dias`;
}

function dataHora(iso) {
  if (!iso) return '—';
  return new Date(iso).toLocaleString('pt-BR', {
    timeZone: 'America/Sao_Paulo', day: '2-digit', month: '2-digit',
    hour: '2-digit', minute: '2-digit',
  });
}

// Agregados do topo, da MESMA lista que aparece embaixo.
export function resumoEmails(emails, agora = new Date()) {
  const respondidos = emails.filter((e) => e.respondido_em).length;
  const semResposta = emails.filter((e) => !e.respondido_em);
  const ultimoSem = semResposta.length
    ? diasDesde(semResposta.reduce((a, e) => (e.enviado_em > a ? e.enviado_em : a), ''), agora)
    : null;
  return { total: emails.length, respondidos, semResposta: semResposta.length, ultimoSem };
}

// ── Campo de endereços (chips) ───────────────────────────────────────
// Chips e não texto com vírgula, pelo mesmo motivo dos convidados da
// agenda: ninguém confere vírgula em texto corrido, e um endereço torto
// derruba o envio inteiro.

export function CampoEnderecos({ label, valores, onChange, id }) {
  const [texto, setTexto] = useState('');
  const [erro, setErro] = useState(null);

  function adicionar(bruto) {
    const partes = String(bruto || '').split(/[\s,;]+/).map((p) => p.trim()).filter(Boolean);
    if (!partes.length) return;
    const invalidos = partes.filter((p) => !emailValido(p));
    if (invalidos.length) {
      setErro(`Endereço inválido: ${invalidos.join(', ')}`);
      return;
    }
    const vistos = new Set(valores.map((v) => v.toLowerCase()));
    const novos = partes.filter((p) => !vistos.has(p.toLowerCase()) && vistos.add(p.toLowerCase()));
    onChange([...valores, ...novos]);
    setTexto('');
    setErro(null);
  }

  return (
    <div>
      <label htmlFor={id} className="block text-sm font-medium text-hipo-ink mb-1.5">{label}</label>
      <div className="flex flex-wrap items-center gap-1.5 min-h-10 px-2 py-1.5 rounded-lg border border-hipo-border bg-hipo-card focus-within:ring-2 focus-within:ring-blue-100 focus-within:border-hipo-blue">
        {valores.map((v) => (
          <span key={v} className="inline-flex items-center gap-1 h-7 pl-2 pr-1 rounded-md bg-hipo-bg border border-hipo-border text-xs text-hipo-ink">
            {v}
            <button
              type="button"
              aria-label={`Tirar ${v}`}
              onClick={() => onChange(valores.filter((x) => x !== v))}
              className="h-5 w-5 inline-flex items-center justify-center rounded text-hipo-slate hover:bg-hipo-card"
            >
              <X size={12} />
            </button>
          </span>
        ))}
        <input
          id={id}
          value={texto}
          onChange={(e) => { setTexto(e.target.value); setErro(null); }}
          onKeyDown={(e) => {
            if (['Enter', ',', ';', 'Tab'].includes(e.key) && texto.trim()) {
              e.preventDefault();
              adicionar(texto);
            } else if (e.key === 'Backspace' && !texto && valores.length) {
              onChange(valores.slice(0, -1));
            }
          }}
          onBlur={() => texto.trim() && adicionar(texto)}
          placeholder={valores.length ? '' : 'nome@empresa.com.br'}
          className="flex-1 min-w-[10rem] h-7 bg-transparent text-sm text-hipo-ink outline-none placeholder:text-hipo-muted"
        />
      </div>
      {erro && <p className="mt-1 text-xs text-hipo-danger">{erro}</p>}
    </div>
  );
}

// ── Um e-mail enviado ────────────────────────────────────────────────

function EmailEnviado({ email, agora }) {
  const [aberto, setAberto] = useState(false);
  const dias = diasDesde(email.enviado_em, agora);
  return (
    <li className="border border-hipo-border rounded-lg p-3 bg-hipo-card">
      <div className="flex items-start gap-2">
        <Mail size={16} className="mt-0.5 text-hipo-slate shrink-0" aria-hidden="true" />
        <div className="min-w-0 flex-1">
          <p className="text-sm font-medium text-hipo-ink truncate" title={email.assunto}>
            {email.assunto}
          </p>
          <p className="text-xs text-hipo-slate mt-0.5 truncate">
            Para {email.contato_nome ? `${email.contato_nome} · ` : ''}{email.para.join(', ')}
            {email.cc.length ? ` · cc ${email.cc.join(', ')}` : ''}
          </p>
          <p className="text-[11px] text-hipo-muted mt-0.5">
            {dataHora(email.enviado_em)} · {email.remetente_nome || email.remetente_email}
            {email.modelo_nome ? ` · ${email.modelo_nome}` : ''}
          </p>
          {email.anexo_nome && (
            <p className="text-[11px] text-hipo-slate mt-0.5 inline-flex items-center gap-1">
              <Paperclip size={11} aria-hidden="true" />
              {email.anexo_nome}
              {email.proposta_versao ? ` (proposta v${email.proposta_versao})` : ''}
            </p>
          )}
        </div>
        <div className="shrink-0 text-right">
          {email.respondido_em ? (
            <Badge tone="success">Respondeu {dataHora(email.respondido_em)}</Badge>
          ) : (
            <Badge tone={dias >= 3 ? 'warning' : 'neutral'}>Sem resposta · {rotuloDias(dias)}</Badge>
          )}
          {email.verificacao_erro && (
            <p className="text-[11px] text-hipo-danger mt-1 max-w-[16rem]" title={email.verificacao_erro}>
              Não deu para ver a resposta
            </p>
          )}
        </div>
      </div>
      <button
        type="button"
        onClick={() => setAberto((a) => !a)}
        aria-expanded={aberto}
        className="mt-2 text-xs text-hipo-blue inline-flex items-center gap-1 hover:underline"
      >
        {aberto ? <ChevronDown size={12} /> : <ChevronRight size={12} />}
        Texto enviado
      </button>
      {aberto && (
        <pre className="mt-2 whitespace-pre-wrap font-sans text-xs text-hipo-ink bg-hipo-bg/50 rounded-md p-2 border border-hipo-border">
          {email.corpo}
        </pre>
      )}
    </li>
  );
}

// ── Compositor ───────────────────────────────────────────────────────

function opcoesDeProposta(versoes) {
  const saida = [];
  for (const p of versoes) {
    const varios = (p.itens || []).length > 1;
    saida.push({
      valor: `${p.id}|`,
      rotulo: `v${p.versao} — ${varios ? 'consolidada' : (p.cliente_razao_social || 'proposta')}`,
    });
    if (varios) {
      for (const i of p.itens) {
        if (i.id) saida.push({ valor: `${p.id}|${i.id}`, rotulo: `v${p.versao} — só ${i.razao_social}` });
      }
    }
  }
  return saida;
}

function Compositor({
  oportunidade, modelos, contatos, versoes, preset, pdfDisponivel, onEnviado, onCancelar,
}) {
  const oppId = oportunidade.id;
  const principal = contatos.find((c) => c.principal) || contatos[0];

  const [modelo, setModelo] = useState(preset?.modelo ?? 'primeiro_contato');
  const [contatoId, setContatoId] = useState(principal?.id || '');
  const [propostaSel, setPropostaSel] = useState(
    preset?.proposta_id ? `${preset.proposta_id}|${preset.proposta_item_id || ''}` : '',
  );
  const [para, setPara] = useState([]);
  const [cc, setCc] = useState([]);
  const [assunto, setAssunto] = useState('');
  const [corpo, setCorpo] = useState('');
  const [anexo, setAnexo] = useState(null);
  const [assinatura, setAssinatura] = useState(false);
  const [avisos, setAvisos] = useState([]);
  const [editado, setEditado] = useState(false);
  const [desatualizado, setDesatualizado] = useState(false);
  const [preenchendo, setPreenchendo] = useState(false);
  const [enviando, setEnviando] = useState(false);
  const [erro, setErro] = useState(null);

  const modeloAtual = modelos.find((m) => m.slug === modelo);
  const anexaProposta = Boolean(modeloAtual?.anexa_proposta) || Boolean(propostaSel);
  const [propostaId, itemId] = propostaSel ? propostaSel.split('|') : [null, null];

  // Modelo de proposta sem versão escolhida: a mais nova, consolidada.
  useEffect(() => {
    if (modeloAtual?.anexa_proposta && !propostaSel && versoes.length) {
      setPropostaSel(`${versoes[0].id}|`);
    }
  }, [modeloAtual, propostaSel, versoes]);

  const preencher = useCallback(async () => {
    if (!contatoId) return;
    setPreenchendo(true);
    setErro(null);
    try {
      const { data } = await api.post(`/crm/oportunidades/${oppId}/emails/rascunho`, {
        modelo: modelo || null,
        contato_id: contatoId,
        proposta_id: propostaId || null,
        proposta_item_id: itemId || null,
      });
      setPara(data.para);
      setAssunto(data.assunto);
      setCorpo(data.corpo);
      setAnexo(data.anexo_nome);
      setAssinatura(data.assinatura);
      setAvisos(data.avisos);
      setEditado(false);
      setDesatualizado(false);
    } catch (err) {
      setErro(mensagemDeErro(err, 'Não foi possível montar o rascunho.'));
    } finally {
      setPreenchendo(false);
    }
  }, [oppId, modelo, contatoId, propostaId, itemId]);

  // Trocar modelo/contato/proposta refaz o rascunho — a não ser que o
  // vendedor já tenha mexido no texto. Aí só avisa.
  useEffect(() => {
    if (editado) setDesatualizado(true);
    else preencher();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [modelo, contatoId, propostaSel]);

  const sobraVariavel = /\{\{|\}\}/.test(assunto + corpo);
  const podeEnviar = para.length > 0 && assunto.trim() && corpo.trim() && contatoId
    && !sobraVariavel && !enviando && !preenchendo
    && !(propostaSel && !pdfDisponivel);

  async function enviar() {
    setEnviando(true);
    setErro(null);
    try {
      const { data } = await api.post(`/crm/oportunidades/${oppId}/emails`, {
        contato_id: contatoId,
        para, cc, assunto, corpo,
        modelo: modelo || null,
        proposta_id: propostaId || null,
        proposta_item_id: itemId || null,
      });
      onEnviado(data);
    } catch (err) {
      setErro(mensagemDeErro(err, 'O e-mail não foi enviado.'));
    } finally {
      setEnviando(false);
    }
  }

  return (
    <section aria-label="Novo e-mail" className="rounded-lg border border-hipo-blue/40 bg-hipo-card p-4 space-y-3">
      <div className="flex items-center gap-2">
        <PenLine size={16} className="text-hipo-blue" aria-hidden="true" />
        <h3 className="text-sm font-semibold text-hipo-ink">Novo e-mail</h3>
        <span className="text-xs text-hipo-slate">sai da sua caixa do Gmail</span>
        <button
          type="button"
          onClick={onCancelar}
          aria-label="Fechar o rascunho"
          className="ml-auto h-8 w-8 inline-flex items-center justify-center rounded-lg text-hipo-slate hover:bg-hipo-bg"
        >
          <X size={14} />
        </button>
      </div>

      {erro && <AlertMessage tipo="erro">{erro}</AlertMessage>}

      <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
        <Select id="email-modelo" label="Modelo" value={modelo} onChange={(e) => setModelo(e.target.value)}>
          {modelos.map((m) => <option key={m.slug} value={m.slug}>{m.nome}</option>)}
          <option value="">Em branco</option>
        </Select>
        <Select id="email-contato" label="Contato" value={contatoId} onChange={(e) => setContatoId(e.target.value)}>
          {contatos.length === 0 && <option value="">— cadastre um contato na aba Contatos —</option>}
          {contatos.map((c) => (
            <option key={c.id} value={c.id}>
              {c.nome}{c.email ? ` · ${c.email}` : ' · sem e-mail'}{c.principal ? ' (principal)' : ''}
            </option>
          ))}
        </Select>
        <Select
          id="email-proposta"
          label="Proposta anexada"
          value={propostaSel}
          onChange={(e) => setPropostaSel(e.target.value)}
          disabled={versoes.length === 0}
        >
          <option value="">{versoes.length ? 'Sem anexo' : 'Nenhuma proposta gerada'}</option>
          {opcoesDeProposta(versoes).map((o) => <option key={o.valor} value={o.valor}>{o.rotulo}</option>)}
        </Select>
      </div>

      {desatualizado && (
        <AlertMessage tipo="info">
          Você mudou a escolha acima depois de editar o texto, então o rascunho não foi refeito.{' '}
          <button type="button" className="underline font-medium" onClick={preencher}>
            Preencher de novo
          </button>{' '}
          (substitui o que você escreveu).
        </AlertMessage>
      )}
      {avisos.length > 0 && (
        <AlertMessage tipo="aviso">
          <ul className="list-disc pl-4 space-y-0.5">
            {avisos.map((a) => <li key={a}>{a}</li>)}
          </ul>
        </AlertMessage>
      )}

      <CampoEnderecos id="email-para" label="Para" valores={para} onChange={setPara} />
      <CampoEnderecos id="email-cc" label="Cc (opcional)" valores={cc} onChange={setCc} />
      <Input
        label="Assunto"
        value={assunto}
        onChange={(e) => { setAssunto(e.target.value); setEditado(true); }}
      />
      <Textarea
        label="Texto"
        rows={12}
        value={corpo}
        onChange={(e) => { setCorpo(e.target.value); setEditado(true); }}
        hint={assinatura
          ? 'Sua assinatura do Gmail entra no fim, como no Gmail.'
          : 'Este e-mail sai sem assinatura.'}
      />
      {sobraVariavel && (
        <p className="text-xs text-hipo-danger">
          Ainda há {'{{…}}'} no texto. Troque pelo valor — o cliente veria as chaves.
        </p>
      )}

      <div className="flex flex-wrap items-center gap-2">
        {anexaProposta && anexo && (
          <span className="inline-flex items-center gap-1 text-xs text-hipo-slate">
            <Paperclip size={12} aria-hidden="true" /> {anexo}
          </span>
        )}
        <div className="ml-auto flex items-center gap-2">
          <Button size="sm" variant="ghost" icon={RefreshCw} onClick={preencher} loading={preenchendo}>
            Refazer do modelo
          </Button>
          <Button size="sm" icon={Send} onClick={enviar} disabled={!podeEnviar} loading={enviando}>
            {enviando ? 'Enviando…' : `Enviar${para.length ? ` para ${para[0]}${para.length > 1 ? ` +${para.length - 1}` : ''}` : ''}`}
          </Button>
        </div>
      </div>
    </section>
  );
}

// ── Aba ──────────────────────────────────────────────────────────────

export default function AbaEmails({ oportunidade, preset, onPresetUsado, agora }) {
  const oppId = oportunidade.id;
  const [emails, setEmails] = useState(null);
  const [config, setConfig] = useState(null);
  const [contatos, setContatos] = useState([]);
  const [versoes, setVersoes] = useState([]);
  const [compondo, setCompondo] = useState(null);
  const [verificando, setVerificando] = useState(false);
  const [aviso, setAviso] = useState(null);
  const [erro, setErro] = useState(null);

  const carregar = useCallback(async () => {
    setErro(null);
    try {
      const [l, m, c, p] = await Promise.all([
        api.get(`/crm/oportunidades/${oppId}/emails`),
        api.get('/crm/email/modelos'),
        api.get('/crm/contatos/por-alvo', { params: { oportunidade_id: oppId } }),
        api.get(`/crm/oportunidades/${oppId}/propostas`),
      ]);
      setEmails(l.data);
      setConfig(m.data);
      setContatos(c.data || []);
      setVersoes(p.data || []);
    } catch (err) {
      setErro(mensagemDeErro(err, 'Não foi possível carregar os e-mails.'));
      setEmails((e) => e || []);
    }
  }, [oppId]);

  useEffect(() => { carregar(); }, [carregar]);

  // Vindo do botão "Enviar por e-mail" de uma versão da proposta.
  useEffect(() => {
    if (preset && config) {
      setCompondo({ ...preset, chave: Date.now() });
      onPresetUsado?.();
    }
  }, [preset, config, onPresetUsado]);

  const resumo = useMemo(() => resumoEmails(emails || [], agora), [emails, agora]);

  async function verificar() {
    setVerificando(true);
    setAviso(null);
    setErro(null);
    try {
      const { data } = await api.post(`/crm/oportunidades/${oppId}/emails/verificar`, {});
      if (data.erros.length) setErro(data.erros.join(' '));
      else if (data.verificados === 0) setAviso('Nenhum e-mail aguardando resposta para olhar.');
      else if (data.respondidos === 0) setAviso('Olhei agora: ainda sem resposta.');
      else setAviso(`${data.respondidos} resposta${data.respondidos > 1 ? 's' : ''} nova${data.respondidos > 1 ? 's' : ''}.`);
      const { data: lista } = await api.get(`/crm/oportunidades/${oppId}/emails`);
      setEmails(lista);
    } catch (err) {
      setErro(mensagemDeErro(err, 'Não foi possível olhar o Gmail agora.'));
    } finally {
      setVerificando(false);
    }
  }

  if (!emails || !config) return <p className="text-sm text-hipo-slate">Carregando e-mails…</p>;

  const ligado = config.gmail.ligado;

  return (
    <div className="space-y-4">
      {erro && <AlertMessage tipo="erro">{erro}</AlertMessage>}
      {aviso && <AlertMessage tipo="ok">{aviso}</AlertMessage>}
      {!ligado && (
        <AlertMessage tipo="aviso">
          O envio pelo Gmail está desligado neste servidor. {config.gmail.problemas.join(' ')}
        </AlertMessage>
      )}

      {/* ── Painel ── */}
      <section aria-label="Resumo dos e-mails" className="flex flex-wrap items-center gap-x-6 gap-y-2 rounded-lg border border-hipo-border bg-hipo-card px-4 py-3">
        <div>
          <p className="text-[11px] uppercase tracking-wide text-hipo-slate">Enviados</p>
          <p className="text-lg font-semibold text-hipo-ink" data-testid="kpi-enviados">{resumo.total}</p>
        </div>
        <div>
          <p className="text-[11px] uppercase tracking-wide text-hipo-slate">Respondidos</p>
          <p className="text-lg font-semibold text-hipo-success" data-testid="kpi-respondidos">{resumo.respondidos}</p>
        </div>
        <div>
          <p className="text-[11px] uppercase tracking-wide text-hipo-slate">Sem resposta</p>
          <p className="text-lg font-semibold text-hipo-ink" data-testid="kpi-sem-resposta">
            {resumo.semResposta}
            {resumo.ultimoSem !== null && (
              <span className="ml-1 text-xs font-normal text-hipo-slate inline-flex items-center gap-0.5">
                <Clock size={11} aria-hidden="true" /> último {rotuloDias(resumo.ultimoSem)}
              </span>
            )}
          </p>
        </div>
        <div className="ml-auto flex items-center gap-2">
          {resumo.semResposta > 0 && ligado && (
            <Button size="sm" variant="secondary" icon={Reply} onClick={verificar} loading={verificando}>
              Ver se respondeu
            </Button>
          )}
          {!compondo && (
            <Button size="sm" icon={Mail} disabled={!ligado} onClick={() => setCompondo({ chave: Date.now() })}>
              Novo e-mail
            </Button>
          )}
        </div>
      </section>

      {compondo && (
        <Compositor
          key={compondo.chave}
          oportunidade={oportunidade}
          modelos={config.modelos}
          contatos={contatos}
          versoes={versoes}
          preset={compondo}
          pdfDisponivel={config.pdf_disponivel}
          onCancelar={() => setCompondo(null)}
          onEnviado={(novo) => {
            setEmails((l) => [novo, ...(l || [])]);
            setCompondo(null);
            setAviso(`E-mail enviado para ${novo.para.join(', ')}.`);
          }}
        />
      )}

      {emails.length === 0 ? (
        <Empty
          title="Nenhum e-mail enviado por aqui"
          description="O primeiro contato e a proposta saem da sua caixa do Gmail, com a sua assinatura — e ficam registrados nesta oportunidade."
          icon={Mail}
        />
      ) : (
        <ul className="space-y-2" aria-label="E-mails enviados">
          {emails.map((e) => <EmailEnviado key={e.id} email={e} agora={agora} />)}
        </ul>
      )}

      {config.pode_editar && (
        <ModelosEmail
          modelos={config.modelos}
          variaveis={config.variaveis}
          onSalvo={(m) => setConfig((c) => ({
            ...c, modelos: c.modelos.map((x) => (x.slug === m.slug ? m : x)),
          }))}
        />
      )}
    </div>
  );
}
