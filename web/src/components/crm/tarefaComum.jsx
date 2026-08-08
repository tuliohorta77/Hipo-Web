// web/src/components/crm/tarefaComum.jsx
//
// O que as DUAS telas de tarefa compartilham: a aba dentro da oportunidade
// (linha do tempo) e a tela de gestão (quatro colunas).
//
// Existe para que a regra mais importante do módulo — concluir exige agendar
// a próxima — tenha uma implementação só. Duas cópias do mesmo formulário
// divergem no primeiro ajuste, e a que divergir vai ser a que o usuário está
// usando na hora.
//
// Aqui vive: vocabulário de tipo e situação, formatadores de data, o
// formulário de tarefa e os painéis de concluir / cancelar / editar. Cada
// tela decide onde encaixá-los e como desenhar a lista.

import { useState } from 'react';
import {
  Check, X, Pencil, Phone, Users, MapPin, FileText,
  Mail, MessageCircle, CircleDot, AlertTriangle,
} from 'lucide-react';

import Button from '../ui/Button';
import Input, { Select } from '../ui/Input';

export const TIPOS = [
  { valor: 'ligacao', rotulo: 'Ligação', Icone: Phone },
  { valor: 'reuniao', rotulo: 'Reunião', Icone: Users },
  { valor: 'visita', rotulo: 'Visita', Icone: MapPin },
  { valor: 'proposta', rotulo: 'Proposta', Icone: FileText },
  { valor: 'email', rotulo: 'E-mail', Icone: Mail },
  { valor: 'whatsapp', rotulo: 'WhatsApp', Icone: MessageCircle },
  { valor: 'outro', rotulo: 'Outro', Icone: CircleDot },
];

export const ICONE_TIPO = Object.fromEntries(TIPOS.map((t) => [t.valor, t.Icone]));

// Cada situação tem um tom e uma palavra. A palavra não é redundância: cor
// sozinha não carrega informação para quem não distingue tons.
export const SITUACAO = {
  atrasada: {
    palavra: 'Atrasado',
    ponto: 'border-hipo-danger bg-hipo-card',
    texto: 'text-hipo-danger',
    icone: 'text-hipo-danger',
    tom: 'danger',
  },
  hoje: {
    palavra: 'Hoje',
    ponto: 'border-hipo-warning bg-hipo-warningSoft',
    texto: 'text-hipo-warning',
    icone: 'text-hipo-warning',
    tom: 'warning',
  },
  futura: {
    palavra: 'Agendado',
    ponto: 'border-hipo-blue bg-hipo-blueSoft',
    texto: 'text-hipo-blue',
    icone: 'text-hipo-blue',
    tom: 'info',
  },
  concluida: {
    palavra: 'concluído',
    ponto: 'border-hipo-success bg-hipo-success',
    texto: 'text-hipo-success',
    icone: 'text-white',
    tom: 'success',
  },
  cancelada: {
    palavra: 'cancelado',
    ponto: 'border-hipo-border bg-hipo-bg',
    texto: 'text-hipo-muted',
    icone: 'text-hipo-muted',
    tom: 'neutral',
  },
};

export const ABERTAS = ['atrasada', 'hoje', 'futura'];
export const STATUS_ABERTOS = ['ativa', 'suspensa'];

export function mensagemDeErro(err, padrao) {
  const d = err?.response?.data?.detail;
  if (typeof d === 'string') return d;
  if (Array.isArray(d) && d[0]?.msg) return d[0].msg;
  if (d?.mensagem) return d.mensagem;
  return padrao;
}

// ── Datas ────────────────────────────────────────────────────────────

/** ISO (UTC) -> valor de <input type="datetime-local"> no fuso local. */
export function paraCampoLocal(iso) {
  const d = iso ? new Date(iso) : new Date();
  const local = new Date(d.getTime() - d.getTimezoneOffset() * 60000);
  return local.toISOString().slice(0, 16);
}

/** Amanhã 09:00, no fuso do usuário. Default de qualquer tarefa nova. */
export function amanhaDeManha() {
  const d = new Date();
  d.setDate(d.getDate() + 1);
  d.setHours(9, 0, 0, 0);
  return paraCampoLocal(d.toISOString());
}

export function paraIso(valorDoCampo) {
  return valorDoCampo ? new Date(valorDoCampo).toISOString() : null;
}

/**
 * '15/mar'.
 *
 * Montado à mão porque `toLocaleDateString('pt-BR', {month:'short'})` devolve
 * "15 de mar." — o "de" quebra a coluna em duas linhas e desalinha os pontos
 * da linha do tempo.
 */
const MESES = ['jan', 'fev', 'mar', 'abr', 'mai', 'jun',
               'jul', 'ago', 'set', 'out', 'nov', 'dez'];

export function dataCurta(iso) {
  const d = new Date(iso);
  return `${String(d.getDate()).padStart(2, '0')}/${MESES[d.getMonth()]}`;
}

export function dataCompleta(iso) {
  if (!iso) return '—';
  return new Date(iso).toLocaleString('pt-BR', {
    day: '2-digit', month: '2-digit', year: 'numeric',
    hour: '2-digit', minute: '2-digit',
  });
}

// ── Formulário ───────────────────────────────────────────────────────

export function tarefaVazia(usuarioPadrao = '') {
  return {
    tipo: 'ligacao',
    titulo: '',
    descricao: '',
    responsavel_id: usuarioPadrao,
    prazo: amanhaDeManha(),
  };
}

export function corpoDaTarefa(form) {
  return {
    tipo: form.tipo,
    titulo: form.titulo.trim(),
    descricao: form.descricao.trim() || null,
    responsavel_id: form.responsavel_id,
    prazo: paraIso(form.prazo),
  };
}

export function formIncompleto(form) {
  return !form.titulo.trim() || !form.responsavel_id || !form.prazo;
}

export function formDaTarefa(tarefa) {
  return {
    tipo: tarefa.tipo,
    titulo: tarefa.titulo,
    descricao: tarefa.descricao || '',
    responsavel_id: tarefa.responsavel_id,
    prazo: paraCampoLocal(tarefa.prazo),
  };
}

export function CamposTarefa({ valor, onChange, usuarios, prefixo = '' }) {
  const set = (campo) => (e) => onChange({ ...valor, [campo]: e.target.value });

  return (
    <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
      <Select label={`${prefixo}Tipo`} value={valor.tipo} onChange={set('tipo')}>
        {TIPOS.map((t) => <option key={t.valor} value={t.valor}>{t.rotulo}</option>)}
      </Select>

      <Input
        label={`${prefixo}Prazo`}
        type="datetime-local"
        value={valor.prazo}
        onChange={set('prazo')}
      />

      <div className="md:col-span-2">
        <Input
          label={`${prefixo}Título`}
          placeholder="ex.: Ligar para o RH confirmando os exames"
          value={valor.titulo}
          onChange={set('titulo')}
        />
      </div>

      <Select
        label={`${prefixo}Responsável`}
        value={valor.responsavel_id}
        onChange={set('responsavel_id')}
      >
        <option value="">— selecione —</option>
        {usuarios.map((u) => <option key={u.id} value={u.id}>{u.nome}</option>)}
      </Select>

      <Input
        label={`${prefixo}Detalhe (opcional)`}
        value={valor.descricao}
        onChange={set('descricao')}
      />
    </div>
  );
}

// ── Painéis de ação ──────────────────────────────────────────────────

/**
 * Concluir, cancelar e editar — os três painéis, num componente só.
 *
 * `exigeProxima` vem de fora porque depende do STATUS DA OPORTUNIDADE, e
 * cada tela o descobre de um jeito: a aba já tem a oportunidade em mãos, a
 * tela de gestão recebe o status junto do cartão. O backend recusa com 422 de
 * qualquer forma; aqui a tela só evita levar o usuário até o botão achando
 * que vai passar.
 */
export function PainelAcoesTarefa({
  tarefa, painel, setPainel, usuarios, exigeProxima, ocupado,
  onConcluir, onCancelar, onEditar,
}) {
  const [resultado, setResultado] = useState('');
  const [motivo, setMotivo] = useState('');
  const [proxima, setProxima] = useState(() => tarefaVazia(tarefa.responsavel_id));
  const [edicao, setEdicao] = useState(() => formDaTarefa(tarefa));

  if (!painel) {
    return (
      <div className="flex flex-wrap items-center gap-2">
        <Button
          size="sm" icon={Check}
          aria-label={`Concluir ${tarefa.titulo}`}
          onClick={() => {
            setResultado('');
            setProxima(tarefaVazia(tarefa.responsavel_id));
            setPainel('concluir');
          }}
        >
          Concluir
        </Button>
        <Button
          size="sm" variant="ghost" icon={Pencil}
          aria-label={`Editar ${tarefa.titulo}`}
          onClick={() => { setEdicao(formDaTarefa(tarefa)); setPainel('editar'); }}
        >
          Editar
        </Button>
        <Button
          size="sm" variant="ghost" icon={X}
          aria-label={`Cancelar ${tarefa.titulo}`}
          onClick={() => { setMotivo(''); setPainel('cancelar'); }}
        >
          Cancelar
        </Button>
      </div>
    );
  }

  if (painel === 'concluir') {
    return (
      <div className="space-y-3 border-l-2 border-hipo-border pl-3">
        <Input
          label="O que aconteceu (opcional)"
          placeholder="Atendeu, pediu proposta para 15 vidas"
          value={resultado}
          onChange={(e) => setResultado(e.target.value)}
        />

        {exigeProxima ? (
          <div className="space-y-2">
            <div className="flex items-center gap-2 text-xs text-hipo-slate">
              <AlertTriangle size={13} className="text-hipo-warning" />
              <span>
                Toda tarefa concluída exige a próxima. Se não há próximo passo,
                finalize a oportunidade.
              </span>
            </div>
            <CamposTarefa
              valor={proxima}
              onChange={setProxima}
              usuarios={usuarios}
              prefixo="Próxima: "
            />
          </div>
        ) : (
          <p className="text-xs text-hipo-slate">
            Oportunidade finalizada — não é preciso agendar a próxima.
          </p>
        )}

        <div className="flex justify-end gap-2">
          <Button size="sm" variant="ghost" onClick={() => setPainel(null)}>
            Voltar
          </Button>
          <Button
            size="sm"
            loading={ocupado}
            disabled={exigeProxima && formIncompleto(proxima)}
            onClick={() => onConcluir(tarefa, resultado, exigeProxima ? proxima : null)
              .then((ok) => ok && setPainel(null))}
          >
            Concluir tarefa
          </Button>
        </div>
      </div>
    );
  }

  if (painel === 'cancelar') {
    return (
      <div className="space-y-3 border-l-2 border-hipo-border pl-3">
        <Input
          label="Motivo do cancelamento (opcional)"
          placeholder="Agendei duplicado"
          value={motivo}
          onChange={(e) => setMotivo(e.target.value)}
        />
        <div className="flex justify-end gap-2">
          <Button size="sm" variant="ghost" onClick={() => setPainel(null)}>
            Voltar
          </Button>
          <Button
            size="sm" variant="secondary" loading={ocupado}
            onClick={() => onCancelar(tarefa, motivo).then((ok) => ok && setPainel(null))}
          >
            Cancelar tarefa
          </Button>
        </div>
      </div>
    );
  }

  return (
    <div className="space-y-3 border-l-2 border-hipo-border pl-3">
      <CamposTarefa valor={edicao} onChange={setEdicao} usuarios={usuarios} />
      <div className="flex justify-end gap-2">
        <Button size="sm" variant="ghost" onClick={() => setPainel(null)}>
          Voltar
        </Button>
        <Button
          size="sm" loading={ocupado} disabled={formIncompleto(edicao)}
          onClick={() => onEditar(tarefa, edicao).then((ok) => ok && setPainel(null))}
        >
          Salvar tarefa
        </Button>
      </div>
    </div>
  );
}
