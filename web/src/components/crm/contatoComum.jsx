// web/src/components/crm/contatoComum.jsx
//
// O que as telas de contato compartilham (entrega 045 — ABM/multithreading):
// a ficha da conta (ContatosDaConta), o comitê da oportunidade (AbaContatos)
// e o seletor de contato das tarefas (tarefaComum).
//
// Aqui vive: o vocabulário de papel no comitê (espelho de
// api/services/contato_oportunidade.py), os links de telefone/WhatsApp, o
// farol de multithreading e o formulário de EDITAR contato — que é o que
// acaba com o "excluir e cadastrar de novo" para trocar um telefone.

import { useState } from 'react';
import { Phone, MessageCircle, Linkedin, Save, X } from 'lucide-react';

import api from '../../api';
import { registrarLigacao } from './ligacoes';
import Button from '../ui/Button';
import Badge from '../ui/Badge';
import AlertMessage from '../ui/AlertMessage';
import Input, { Textarea } from '../ui/Input';

// Mesma ordem e mesmos rótulos de ROTULOS_PAPEL no backend. Vocabulário
// fechado: é a cobertura do comitê que a tela mede.
export const PAPEIS = [
  { valor: 'decisor', rotulo: 'Decisor' },
  { valor: 'campeao', rotulo: 'Campeão' },
  { valor: 'influenciador', rotulo: 'Influenciador' },
  { valor: 'operacional', rotulo: 'Operacional (RH/DP)' },
  { valor: 'compras', rotulo: 'Compras/Financeiro' },
  { valor: 'tecnico', rotulo: 'Técnico (SESMT/Médico)' },
];

export const ROTULO_PAPEL = Object.fromEntries(PAPEIS.map((p) => [p.valor, p.rotulo]));

export function mensagemDeErro(err, padrao) {
  const d = err?.response?.data?.detail;
  if (typeof d === 'string') return d;
  if (Array.isArray(d) && d[0]?.msg) return d[0].msg;
  if (d?.mensagem) return d.mensagem;
  return padrao;
}

// ── Telefones ────────────────────────────────────────────────────────

function soDigitos(numero) {
  return String(numero || '').replace(/\D/g, '');
}

/** Link do WhatsApp. Número sem DDI ganha o 55 do Brasil. */
export function linkWhatsapp(numero) {
  const d = soDigitos(numero);
  if (!d) return null;
  return `https://wa.me/${d.length <= 11 ? `55${d}` : d}`;
}

export function linkTelefone(numero) {
  const d = soDigitos(numero);
  return d ? `tel:${d}` : null;
}

/**
 * Os dois telefones do contato, clicáveis: o número liga, o ícone verde abre
 * o WhatsApp. É a ação que o SDR faz a partir da tarefa — "FUP do lead Y" —
 * e procurar o número em outra tela é o atrito que este componente tira.
 *
 * 056: com `ligacao` (de onde se está ligando: oportunidade, conta ou
 * tarefa, e o contato), o clique também avisa o HIPO. É o que permite casar
 * a gravação do Vivo Voz Negócio com esta negociação. O aviso não segura o
 * tel: — o softphone abre na hora, responda o servidor ou não.
 */
export function TelefonesDoContato({ contato, compacto = false, ligacao = null }) {
  const numeros = [
    { n: contato.telefone, wa: contato.telefone_whatsapp },
    { n: contato.telefone_2, wa: contato.telefone_2_whatsapp },
  ].filter((x) => x.n);
  if (!numeros.length) return null;
  return (
    <span className={`inline-flex flex-wrap items-center gap-x-3 gap-y-1 ${compacto ? 'text-xs' : 'text-sm'}`}>
      {numeros.map(({ n, wa }) => (
        <span key={n} className="inline-flex items-center gap-1">
          <a
            href={linkTelefone(n)}
            onClick={ligacao ? () => registrarLigacao(ligacao, n) : undefined}
            title={ligacao ? 'Ligar pelo Vivo Voz Negócio (gravada no HIPO)' : undefined}
            className="inline-flex items-center gap-1 text-hipo-slate hover:text-hipo-blue"
          >
            <Phone size={11} aria-hidden="true" />{n}
          </a>
          {wa && (
            <a
              href={linkWhatsapp(n)}
              target="_blank"
              rel="noreferrer"
              aria-label={`WhatsApp ${n}`}
              title="Abrir no WhatsApp"
              className="text-hipo-success hover:opacity-80"
            >
              <MessageCircle size={12} aria-hidden="true" />
            </a>
          )}
        </span>
      ))}
    </span>
  );
}

export function LinkLinkedin({ url }) {
  if (!url) return null;
  return (
    <a
      href={url}
      target="_blank"
      rel="noreferrer"
      className="inline-flex items-center gap-1 text-xs text-hipo-blue hover:underline"
    >
      <Linkedin size={11} aria-hidden="true" />LinkedIn
    </a>
  );
}

// ── Farol do comitê ──────────────────────────────────────────────────

/**
 * O farol de multithreading, a partir da contagem que a lista/kanban já
 * trazem (`qtd_contatos`, `tem_decisor`). Espelha
 * `farol_multithreading` do backend — a aba completa usa o objeto que o
 * servidor manda; aqui é só o selo do cartão.
 */
export function tomDoComite(qtd) {
  if (!qtd) return 'danger';
  if (qtd < 2) return 'warning';
  return 'success';
}

export function SeloComite({ qtd = 0, temDecisor = false }) {
  const tom = tomDoComite(qtd);
  const texto = qtd === 1 ? '1 contato' : `${qtd} contatos`;
  return (
    <Badge tone={tom} className="!px-2 !py-0.5">
      <span title={
        qtd >= 2
          ? (temDecisor ? 'Comitê com decisor mapeado' : 'Falta mapear o decisor')
          : 'Ideal: 2 a 4 contatos envolvidos'
      }>
        {texto}{qtd >= 2 && !temDecisor ? ' · sem decisor' : ''}
      </span>
    </Badge>
  );
}

// ── Editar contato ───────────────────────────────────────────────────

export function formDoContato(c, cargo) {
  return {
    nome: c.nome || '',
    cargo: cargo ?? c.cargo ?? '',
    telefone: c.telefone || '',
    telefone_whatsapp: Boolean(c.telefone_whatsapp),
    telefone_2: c.telefone_2 || '',
    telefone_2_whatsapp: Boolean(c.telefone_2_whatsapp),
    email: c.email || '',
    linkedin: c.linkedin || '',
    data_nascimento: c.data_nascimento || '',
    observacoes: c.observacoes || '',
  };
}

function Marca({ id, label, checked, onChange }) {
  return (
    <label htmlFor={id} className="inline-flex items-center gap-1.5 text-xs text-hipo-slate mt-1">
      <input id={id} type="checkbox" checked={checked} onChange={(e) => onChange(e.target.checked)} />
      {label}
    </label>
  );
}

/**
 * Edita o contato no lugar — nome, telefones (com a marca de WhatsApp de
 * cada um), e-mail, LinkedIn, nascimento, observações — e, com `contaId`,
 * o CARGO, que mora no vínculo com aquela empresa.
 *
 * Inline e não modal: vive dentro da ficha da conta e da oportunidade, que
 * já são modais. Modal sobre modal rouba o foco e o Esc fecha os dois.
 */
export function FormContato({ contato, contaId, cargoAtual, onSalvo, onCancelar }) {
  const [form, setForm] = useState(() => formDoContato(contato, cargoAtual));
  const [erro, setErro] = useState(null);
  const [salvando, setSalvando] = useState(false);
  const id = (campo) => `contato-${contato.id}-${campo}`;
  const set = (campo) => (e) => setForm((f) => ({ ...f, [campo]: e.target.value }));
  const marca = (campo) => (v) => setForm((f) => ({ ...f, [campo]: v }));

  async function salvar() {
    setSalvando(true);
    setErro(null);
    try {
      await api.patch(`/crm/contatos/${contato.id}`, {
        nome: form.nome.trim(),
        telefone: form.telefone.trim() || null,
        telefone_whatsapp: form.telefone_whatsapp,
        telefone_2: form.telefone_2.trim() || null,
        telefone_2_whatsapp: form.telefone_2_whatsapp,
        email: form.email.trim() || null,
        linkedin: form.linkedin.trim() || null,
        data_nascimento: form.data_nascimento || null,
        observacoes: form.observacoes.trim() || null,
      });
      const cargoNovo = form.cargo.trim() || null;
      if (contaId && cargoNovo !== ((cargoAtual ?? contato.cargo) || null)) {
        await api.patch(`/crm/contatos/${contato.id}/vinculos/${contaId}`, { cargo: cargoNovo });
      }
      onSalvo?.();
    } catch (err) {
      setErro(mensagemDeErro(err, 'Não foi possível salvar o contato.'));
    } finally {
      setSalvando(false);
    }
  }

  return (
    <div className="space-y-3 border-l-2 border-hipo-blue pl-3 py-1">
      {erro && <AlertMessage tipo="erro">{erro}</AlertMessage>}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
        <Input id={id('nome')} label="Nome" value={form.nome} onChange={set('nome')} />
        {contaId && (
          <Input id={id('cargo')} label="Cargo nesta empresa" value={form.cargo} onChange={set('cargo')} />
        )}
        <div>
          <Input id={id('telefone')} label="Telefone" value={form.telefone} onChange={set('telefone')} />
          <Marca id={id('wa1')} label="É WhatsApp" checked={form.telefone_whatsapp} onChange={marca('telefone_whatsapp')} />
        </div>
        <div>
          <Input id={id('telefone2')} label="2º telefone" value={form.telefone_2} onChange={set('telefone_2')} />
          <Marca id={id('wa2')} label="É WhatsApp" checked={form.telefone_2_whatsapp} onChange={marca('telefone_2_whatsapp')} />
        </div>
        <Input
          id={id('email')}
          label="E-mail"
          type="text"
          inputMode="email"
          autoComplete="email"
          hint="Mais de um? Separe com ponto e vírgula — todos recebem o convite."
          value={form.email}
          onChange={set('email')}
        />
        <Input
          id={id('linkedin')}
          label="LinkedIn"
          placeholder="linkedin.com/in/..."
          value={form.linkedin}
          onChange={set('linkedin')}
        />
        <Input id={id('nascimento')} label="Nascimento" type="date" value={form.data_nascimento} onChange={set('data_nascimento')} />
        <div className="md:col-span-2">
          <Textarea id={id('obs')} label="Observações" rows={2} value={form.observacoes} onChange={set('observacoes')} />
        </div>
      </div>
      <div className="flex justify-end gap-2">
        <Button size="sm" variant="ghost" icon={X} onClick={onCancelar}>Voltar</Button>
        <Button size="sm" icon={Save} loading={salvando} disabled={!form.nome.trim()} onClick={salvar}>
          Salvar contato
        </Button>
      </div>
    </div>
  );
}

// ── Temperatura do contato (046) ─────────────────────────────────────

/*
  Quente / morno / frio, calculado no servidor (services/temperatura_contato)
  pelas conversas CONCLUÍDAS com a pessoa: quantas, quão recentes e se foram
  reunião/visita realizada (vale o dobro). Tarefa futura, aberta ou
  cancelada (inclui no-show) não conta.

  Cor + palavra: cor sozinha não carrega informação para quem não distingue
  tons.
*/
const SINAL = {
  quente: { ponto: 'bg-hipo-danger', caixa: 'border-hipo-dangerBorder bg-hipo-dangerSoft text-hipo-danger' },
  morno: { ponto: 'bg-hipo-warning', caixa: 'border-hipo-warningBorder bg-hipo-warningSoft text-hipo-warning' },
  frio: { ponto: 'bg-hipo-blue', caixa: 'border-hipo-blueSoft bg-hipo-blueSoft text-hipo-blueDark' },
};

export function explicacaoTemperatura(c) {
  const n = c.interacoes_60d || 0;
  const conversas = n === 0
    ? 'nenhuma conversa concluída nos últimos 60 dias'
    : `${n} conversa${n === 1 ? '' : 's'} concluída${n === 1 ? '' : 's'} nos últimos 60 dias`;
  const d = c.dias_desde_ultima_conversa;
  const ultima = d == null
    ? 'nunca houve conversa concluída'
    : d === 0 ? 'última hoje' : d === 1 ? 'última ontem' : `última há ${d} dias`;
  return `${conversas} · ${ultima}`;
}

/**
 * O sinal de temperatura. Botão: clicar mostra/esconde o porquê (quantas
 * conversas e quando foi a última), sem tooltip — tooltip não existe no
 * celular, e o vendedor usa o HIPO no celular.
 */
export function SinalTemperatura({ contato }) {
  const [aberto, setAberto] = useState(false);
  const nivel = contato.temperatura || 'frio';
  const s = SINAL[nivel] || SINAL.frio;
  const rotulo = contato.temperatura_rotulo || nivel;
  return (
    <span className="inline-flex flex-wrap items-center gap-1.5">
      <button
        type="button"
        onClick={() => setAberto((v) => !v)}
        aria-expanded={aberto}
        aria-label={`Contato ${rotulo.toLowerCase()}: ver o porquê`}
        className={`inline-flex items-center gap-1.5 px-2 py-0.5 rounded-full border text-xs font-medium ${s.caixa}`}
      >
        <span aria-hidden="true" className={`w-2 h-2 rounded-full ${s.ponto}`} />
        {rotulo}
      </button>
      {aberto && (
        <span className="text-xs text-hipo-slate">{explicacaoTemperatura(contato)}</span>
      )}
    </span>
  );
}
