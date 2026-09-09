// web/src/components/crm/ModalReuniao.jsx
//
// Marcar e editar uma reunião. Um componente só para os três caminhos que
// chegam aqui:
//
//   1. clicar num slot livre da grade      -> cria, com dia e hora prontos
//   2. clicar em "Agendar reunião" na      -> cria, com a oportunidade presa
//      oportunidade
//   3. clicar num cartão da grade          -> edita o que já existe
//
// Um componente e não três porque o formulário é o mesmo, e três cópias
// divergiriam no primeiro campo novo — a que divergisse seria a que o
// vendedor está usando na hora. É a mesma razão que fez `tarefaComum`
// existir para a aba e a tela de gestão de tarefas.
//
// ── O que muda entre criar e editar ──────────────────────────────────
// A oportunidade só é escolhida na CRIAÇÃO. Mover uma reunião de negócio
// mudaria o alvo da tarefa por baixo, e com ele a linha do tempo e a
// métrica de duas oportunidades ao mesmo tempo. Quem errou o negócio
// cancela e marca de novo — duas ações claras em vez de uma silenciosa.
//
// ── Por que o convite tem seção própria ──────────────────────────────
// Contato, convidados e participantes decidem QUEM recebe e-mail do
// Google. Misturados com tipo e duração, viravam mais três campos de
// formulário; separados e com o aviso do que vai ser enviado, quem
// preenche sabe que aquilo sai da máquina dele e chega no cliente.

import { useCallback, useEffect, useMemo, useState } from 'react';
import {
  CalendarPlus, Trash2, RefreshCw, AlertTriangle, CheckCircle2,
  Mail, X, Plus, ExternalLink,
} from 'lucide-react';

import api from '../../api';
import Modal from '../ui/Modal';
import Button from '../ui/Button';
import Badge from '../ui/Badge';
import AlertMessage from '../ui/AlertMessage';
import Input, { Select, Textarea } from '../ui/Input';
import EntityPicker from '../EntityPicker';
import {
  DURACOES, DURACAO_PADRAO, MODALIDADES,
  mensagemDeErro, paraCampoLocal, paraIso,
} from './agendaComum';

function formVazio(usuarioPadrao = '') {
  return {
    oportunidade: null,
    anfitriao_id: usuarioPadrao,
    inicio: '',
    duracao_min: DURACAO_PADRAO,
    tipo_id: '',
    modalidade: 'online',
    endereco: '',
    link_video: '',
    contato_id: '',
    convidados: [],
    participantes: [],
    titulo: '',
    observacoes: '',
  };
}

function formDaReuniao(r) {
  return {
    oportunidade: null,
    anfitriao_id: r.anfitriao_id,
    inicio: paraCampoLocal(r.inicio),
    duracao_min: r.duracao_min,
    tipo_id: r.tipo_id ?? '',
    modalidade: r.modalidade,
    endereco: r.endereco || '',
    link_video: r.link_video || '',
    contato_id: r.contato_id || '',
    convidados: r.convidados || [],
    participantes: (r.participantes || []).map((p) => p.usuario_id),
    titulo: r.titulo || '',
    observacoes: r.observacoes || '',
  };
}

// ── Convidados externos ──────────────────────────────────────────────

/**
 * Lista de e-mails em chips.
 *
 * Digitar e apertar Enter vira chip; o X remove. Um `<textarea>` separado
 * por vírgula seria menos código e um erro por reunião: ninguém confere
 * vírgula em texto corrido, e um endereço com espaço no meio faz o Google
 * recusar o evento INTEIRO — o convite dos outros convidados morre junto.
 * Com chip, o endereço torto fica visível antes de sair daqui.
 */
function Convidados({ valor, onChange, desabilitado }) {
  const [texto, setTexto] = useState('');

  function adicionar() {
    const limpo = texto.trim();
    if (!limpo) return;
    if (!valor.some((e) => e.toLowerCase() === limpo.toLowerCase())) {
      onChange([...valor, limpo]);
    }
    setTexto('');
  }

  return (
    <div>
      <label htmlFor="reuniao-convidado" className="block text-sm font-medium text-hipo-ink mb-1.5">
        Convidados externos
      </label>
      <div className="flex gap-2">
        <input
          id="reuniao-convidado"
          type="email"
          value={texto}
          disabled={desabilitado}
          placeholder="email@empresa.com.br"
          onChange={(e) => setTexto(e.target.value)}
          onKeyDown={(e) => {
            // Enter no meio de um formulário submeteria o form inteiro. Aqui
            // ele significa "terminei este e-mail", que é o gesto natural de
            // quem está digitando uma lista.
            if (e.key === 'Enter') { e.preventDefault(); adicionar(); }
          }}
          className={
            'flex-1 h-10 px-3 rounded-lg bg-hipo-card border border-hipo-border ' +
            'text-hipo-ink text-sm outline-none transition-colors ' +
            'placeholder:text-hipo-muted disabled:bg-hipo-bg ' +
            'focus:border-hipo-blue focus:ring-2 focus:ring-blue-100'
          }
        />
        <Button
          variant="secondary" icon={Plus} disabled={desabilitado || !texto.trim()}
          onClick={adicionar} aria-label="Adicionar convidado"
        >
          Adicionar
        </Button>
      </div>
      {valor.length > 0 && (
        <ul className="flex flex-wrap gap-1.5 mt-2">
          {valor.map((email) => (
            <li key={email}>
              <button
                type="button"
                disabled={desabilitado}
                onClick={() => onChange(valor.filter((e) => e !== email))}
                aria-label={`Remover ${email}`}
                className={
                  'inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs ' +
                  'border border-hipo-border text-hipo-ink ' +
                  'hover:bg-hipo-dangerSoft hover:border-hipo-dangerBorder'
                }
              >
                {email}<X size={12} />
              </button>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

// ── O estado do convite ──────────────────────────────────────────────

/**
 * Diz se o convite chegou ao Google — e o que fazer quando não chegou.
 *
 * Fica no TOPO do modal, não no rodapé: uma reunião cujo convite não saiu
 * é uma reunião que não vai acontecer, e essa informação não pode depender
 * de o usuário rolar até o fim para aparecer.
 */
function EstadoDoConvite({ reuniao, onSincronizar, ocupado }) {
  if (!reuniao) return null;

  if (reuniao.google_event_id && !reuniao.google_erro) {
    return (
      <div className="flex items-center gap-2 text-xs text-hipo-success">
        <CheckCircle2 size={14} />
        <span>Convite enviado pelo Google Agenda.</span>
        {reuniao.google_link && (
          <a
            href={reuniao.google_link}
            target="_blank"
            rel="noreferrer"
            className="inline-flex items-center gap-1 text-hipo-blue hover:underline"
          >
            abrir <ExternalLink size={11} />
          </a>
        )}
      </div>
    );
  }

  return (
    <AlertMessage tipo="aviso">
      <div className="flex flex-wrap items-center gap-x-3 gap-y-1">
        <span>
          {reuniao.google_erro || 'O convite ainda não foi enviado.'}
        </span>
        <Button
          size="sm" variant="secondary" icon={RefreshCw}
          loading={ocupado} onClick={onSincronizar}
        >
          Tentar de novo
        </Button>
      </div>
    </AlertMessage>
  );
}

// ── Componente ───────────────────────────────────────────────────────

export default function ModalReuniao({
  aberto,
  onFechar,
  onSalvo,
  nivel = 1,
  // Criar: um destes dois chega preenchido.
  //   `slotInicial`  — 'AAAA-MM-DDTHH:MM', de um clique num slot vazio
  //   `oportunidade` — { id, numero, conta_razao_social, conta_id, contato_id }
  //                    de quem clicou "Agendar reunião" dentro do negócio
  slotInicial = '',
  oportunidade = null,
  anfitriaoInicial = '',
  // Editar: a reunião existente. Presente = modo edição.
  reuniao = null,
  usuarios = [],
}) {
  const editando = Boolean(reuniao);

  const [form, setForm] = useState(() => formVazio());
  const [tipos, setTipos] = useState([]);
  const [contatos, setContatos] = useState([]);
  const [erro, setErro] = useState(null);
  const [ocupado, setOcupado] = useState(false);
  const [confirmandoCancelamento, setConfirmandoCancelamento] = useState(false);
  const [motivo, setMotivo] = useState('');

  // Remonta o formulário sempre que o modal abre num alvo diferente. A
  // chave é o id da reunião (ou o slot, na criação): sem ela, abrir um
  // cartão depois de outro mostraria os dados do anterior por um render.
  const chave = reuniao?.id || slotInicial || oportunidade?.id || 'novo';
  useEffect(() => {
    if (!aberto) return;
    setErro(null);
    setConfirmandoCancelamento(false);
    setMotivo('');
    if (reuniao) {
      setForm(formDaReuniao(reuniao));
    } else {
      setForm({
        ...formVazio(anfitriaoInicial),
        inicio: slotInicial || '',
        oportunidade: oportunidade || null,
        contato_id: oportunidade?.contato_id || '',
      });
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [aberto, chave]);

  useEffect(() => {
    if (!aberto) return;
    api.get('/crm/agenda/tipos')
      .then(({ data }) => setTipos(data))
      .catch(() => setTipos([]));
  }, [aberto]);

  // Os contatos da EMPRESA da reunião — é entre eles que está quem recebe
  // o convite. `|| []` não é paranoia: uma resposta sem `itens` deixava o
  // map estourar e a tela inteira virava branco (Sprint 4).
  const contaId = reuniao?.conta_id || form.oportunidade?.conta_id || oportunidade?.conta_id;
  useEffect(() => {
    if (!aberto || !contaId) { setContatos([]); return; }
    api.get('/crm/contatos', { params: { conta_id: contaId, limit: 100 } })
      .then(({ data }) => setContatos(data.itens || []))
      .catch(() => setContatos([]));
  }, [aberto, contaId]);

  const set = (campo) => (e) => setForm((f) => ({ ...f, [campo]: e.target.value }));

  const fechada = editando && !['atrasada', 'hoje', 'futura'].includes(reuniao.situacao);

  const incompleto = useMemo(() => {
    if (!form.anfitriao_id || !form.inicio) return true;
    if (!editando && !form.oportunidade) return true;
    return false;
  }, [form, editando]);

  const corpo = useCallback(() => {
    const base = {
      tipo_id: form.tipo_id === '' ? null : Number(form.tipo_id),
      modalidade: form.modalidade,
      duracao_min: Number(form.duracao_min),
      endereco: form.endereco.trim() || null,
      link_video: form.link_video.trim() || null,
      contato_id: form.contato_id || null,
      convidados: form.convidados,
      participantes: form.participantes,
      observacoes: form.observacoes.trim() || null,
      titulo: form.titulo.trim() || null,
      inicio: paraIso(form.inicio),
      anfitriao_id: form.anfitriao_id,
    };
    if (editando) return base;
    return { ...base, oportunidade_id: form.oportunidade.id };
  }, [form, editando]);

  async function acao(fn, padrao) {
    setOcupado(true);
    setErro(null);
    try {
      const { data } = await fn();
      onSalvo?.(data);
      return data;
    } catch (err) {
      setErro(mensagemDeErro(err, padrao));
      return null;
    } finally {
      setOcupado(false);
    }
  }

  async function salvar() {
    const dados = corpo();
    const salva = editando
      ? await acao(
          () => api.patch(`/crm/agenda/reunioes/${reuniao.id}`, dados),
          'Não foi possível salvar a reunião.',
        )
      : await acao(
          () => api.post('/crm/agenda/reunioes', dados),
          'Não foi possível marcar a reunião.',
        );
    if (salva) onFechar();
  }

  async function cancelarReuniao() {
    const feita = await acao(
      () => api.post(`/crm/agenda/reunioes/${reuniao.id}/cancelar`, {
        motivo: motivo.trim() || null,
      }),
      'Não foi possível cancelar a reunião.',
    );
    if (feita) onFechar();
  }

  function sincronizar() {
    return acao(
      () => api.post(`/crm/agenda/reunioes/${reuniao.id}/sincronizar`, {}),
      'Não foi possível sincronizar com o Google.',
    );
  }

  const onlineSemLink = form.modalidade === 'online';

  return (
    <Modal
      aberto={aberto}
      onFechar={onFechar}
      nivel={nivel}
      size="lg"
      titulo={editando ? reuniao.rotulo : 'Marcar reunião'}
      subtitulo={
        editando ? (
          <span className="flex flex-wrap items-center gap-2">
            <span>{reuniao.conta_razao_social}</span>
            {reuniao.oportunidade_numero && (
              <span className="font-mono">{reuniao.oportunidade_numero}</span>
            )}
            {reuniao.fora_da_grade && (
              <Badge tone="warning">fora da grade</Badge>
            )}
          </span>
        ) : undefined
      }
    >
      <div className="space-y-4">
        {erro && <AlertMessage tipo="erro">{erro}</AlertMessage>}

        {editando && (
          <EstadoDoConvite
            reuniao={reuniao}
            onSincronizar={sincronizar}
            ocupado={ocupado}
          />
        )}

        {fechada && (
          <AlertMessage tipo="info">
            Esta reunião já foi {reuniao.situacao === 'cancelada' ? 'cancelada' : 'realizada'}.
            O histórico é imutável.
          </AlertMessage>
        )}

        {/* ── Quando e com quem ── */}
        <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
          {!editando && (
            <div className="md:col-span-2">
              <EntityPicker
                label="Oportunidade"
                value={form.oportunidade}
                // Preso quando veio de dentro do negócio: quem clicou
                // "Agendar reunião" na oportunidade já respondeu isso.
                disabled={Boolean(oportunidade)}
                onChange={(o) => setForm((f) => ({
                  ...f, oportunidade: o, contato_id: o?.contato_id || '',
                }))}
                buscar={async (q) => {
                  const { data } = await api.get('/crm/oportunidades', {
                    params: { q, limit: 20 },
                  });
                  return data.itens || [];
                }}
                paraItem={(o) => ({
                  id: o.id,
                  titulo: o.conta_razao_social,
                  subtitulo: o.numero,
                })}
                placeholder="Buscar por empresa, número ou CNPJ"
              />
            </div>
          )}

          <Input
            id="reuniao-inicio"
            label="Data e hora"
            type="datetime-local"
            value={form.inicio}
            disabled={fechada}
            onChange={set('inicio')}
            hint="A grade vai de 8h às 11h30 e de 13h às 17h30, de 30 em 30 minutos — mas pode ajustar."
          />

          <Select
            id="reuniao-duracao"
            label="Duração"
            value={form.duracao_min}
            disabled={fechada}
            onChange={set('duracao_min')}
          >
            {DURACOES.map((d) => (
              <option key={d.valor} value={d.valor}>{d.rotulo}</option>
            ))}
          </Select>

          <Select
            id="reuniao-anfitriao"
            label="Anfitrião"
            value={form.anfitriao_id}
            disabled={fechada}
            onChange={set('anfitriao_id')}
          >
            <option value="">— selecione —</option>
            {usuarios.map((u) => (
              <option key={u.id} value={u.id}>{u.nome}</option>
            ))}
          </Select>

          <Select
            id="reuniao-tipo"
            label="Tipo"
            value={form.tipo_id}
            disabled={fechada}
            onChange={set('tipo_id')}
          >
            <option value="">— sem tipo —</option>
            {tipos.map((t) => (
              <option key={t.id} value={t.id}>{t.sigla} · {t.nome}</option>
            ))}
          </Select>

          <Select
            id="reuniao-modalidade"
            label="Modalidade"
            value={form.modalidade}
            disabled={fechada}
            onChange={set('modalidade')}
          >
            {MODALIDADES.map((m) => (
              <option key={m.valor} value={m.valor}>{m.rotulo}</option>
            ))}
          </Select>

          {/*
            Os dois campos aparecem juntos e nenhum é obrigatório: reunião
            online com endereço (a sala de onde o vendedor fala) e
            presencial com link (o sócio que entra remoto) são casos reais.
            O que muda com a modalidade é a DICA, não a permissão.
          */}
          <Input
            id="reuniao-endereco"
            label="Endereço"
            value={form.endereco}
            disabled={fechada}
            onChange={set('endereco')}
            placeholder="Rua, número, cidade"
          />

          <div className="md:col-span-2">
            <Input
              id="reuniao-link"
              label="Link da chamada"
              value={form.link_video}
              disabled={fechada}
              onChange={set('link_video')}
              placeholder="deixe em branco para o Google criar um Meet"
              hint={onlineSemLink && !form.link_video
                ? 'Em branco, o Google gera um link do Meet e manda no convite.'
                : undefined}
            />
          </div>
        </div>

        {/* ── Quem recebe o convite ── */}
        <div className="border-t border-hipo-border pt-4 space-y-3">
          <p className="flex items-center gap-1.5 text-xs text-hipo-slate">
            <Mail size={13} className="text-hipo-blue" />
            O Google manda o convite para todo mundo desta seção, mais o
            anfitrião.
          </p>

          <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
            <Select
              id="reuniao-contato"
              label="Contato do cliente"
              value={form.contato_id}
              disabled={fechada}
              onChange={set('contato_id')}
            >
              <option value="">— sem contato —</option>
              {contatos.map((c) => (
                <option key={c.id} value={c.id}>
                  {c.nome}{c.email ? ` · ${c.email}` : ' · sem e-mail'}
                </option>
              ))}
            </Select>

            <div>
              <span className="block text-sm font-medium text-hipo-ink mb-1.5">
                Nossa equipe
              </span>
              {/*
                Lista com rolagem e não um <select multiple>: em select
                múltiplo, clicar sem segurar Ctrl apaga a seleção inteira
                sem avisar — e quem descobre isso descobre depois de
                mandar o convite sem o EP.
              */}
              <ul className="max-h-28 overflow-y-auto border border-hipo-border rounded-lg p-2 space-y-1">
                {usuarios
                  .filter((u) => u.id !== form.anfitriao_id)
                  .map((u) => (
                    <li key={u.id}>
                      <label className="flex items-center gap-2 text-sm text-hipo-ink">
                        <input
                          type="checkbox"
                          disabled={fechada}
                          checked={form.participantes.includes(u.id)}
                          onChange={(e) => setForm((f) => ({
                            ...f,
                            participantes: e.target.checked
                              ? [...f.participantes, u.id]
                              : f.participantes.filter((x) => x !== u.id),
                          }))}
                        />
                        {u.nome}
                      </label>
                    </li>
                  ))}
              </ul>
            </div>
          </div>

          <Convidados
            valor={form.convidados}
            desabilitado={fechada}
            onChange={(v) => setForm((f) => ({ ...f, convidados: v }))}
          />
        </div>

        {/* ── Detalhe ── */}
        <div className="border-t border-hipo-border pt-4 space-y-3">
          <Input
            id="reuniao-titulo"
            label="Título (opcional)"
            value={form.titulo}
            disabled={fechada}
            onChange={set('titulo')}
            placeholder="em branco, usamos o rótulo da grade"
          />
          <Textarea
            id="reuniao-observacoes"
            label="Observações"
            rows={3}
            value={form.observacoes}
            disabled={fechada}
            onChange={set('observacoes')}
            placeholder="O que precisa levar, o que já foi combinado"
          />
        </div>

        {/* ── Cancelamento ── */}
        {editando && !fechada && (
          <div className="border-t border-hipo-border pt-4">
            {confirmandoCancelamento ? (
              <div className="space-y-2">
                <Textarea
                  id="reuniao-motivo"
                  label="Motivo do cancelamento (opcional)"
                  rows={2}
                  value={motivo}
                  onChange={(e) => setMotivo(e.target.value)}
                  placeholder="Cliente pediu para remarcar"
                />
                <p className="flex items-start gap-1.5 text-xs text-hipo-slate">
                  <AlertTriangle size={13} className="text-hipo-warning shrink-0 mt-0.5" />
                  O evento sai da agenda de todo mundo e o Google avisa o
                  cliente. O horário volta a ficar livre.
                </p>
                <div className="flex justify-end gap-2">
                  <Button
                    size="sm" variant="ghost"
                    onClick={() => setConfirmandoCancelamento(false)}
                  >
                    Voltar
                  </Button>
                  <Button
                    size="sm" variant="danger" loading={ocupado}
                    onClick={cancelarReuniao}
                  >
                    Cancelar reunião
                  </Button>
                </div>
              </div>
            ) : (
              <Button
                size="sm" variant="ghost" icon={Trash2}
                onClick={() => setConfirmandoCancelamento(true)}
              >
                Cancelar reunião
              </Button>
            )}
          </div>
        )}

        {/* ── Ações ── */}
        {!fechada && (
          <div className="flex justify-end gap-2 pt-1">
            <Button variant="ghost" onClick={onFechar}>Fechar</Button>
            <Button
              icon={editando ? undefined : CalendarPlus}
              loading={ocupado}
              disabled={incompleto}
              onClick={salvar}
            >
              {editando ? 'Salvar reunião' : 'Marcar e enviar convite'}
            </Button>
          </div>
        )}
      </div>
    </Modal>
  );
}
