// web/src/components/crm/AbaTarefas.jsx
//
// Tarefas da oportunidade: o que passou, o que está aberto e o que vem.
//
// ── Por que tudo na mesma lista ──────────────────────────────────────
// Separar "histórico" de "agenda" em duas telas obrigaria o vendedor a
// cruzar as duas para responder a única pergunta que importa antes de
// ligar: o que já tentei e o que combinei. Aqui é uma lista só, agrupada
// por urgência — atrasada, hoje, futura, e o fechado embaixo.
//
// ── Por que nada abre modal ──────────────────────────────────────────
// Esta aba vive DENTRO do modal da oportunidade. Modal sobre modal empilha
// z-index, rouba foco e faz o Esc fechar os dois, perdendo o formulário em
// edição — a mesma razão que fez o EntityPicker virar popover. Criar e
// concluir acontecem em painéis que expandem no lugar.
//
// ── A regra que dá nome à tela ───────────────────────────────────────
// Concluir exige agendar a próxima enquanto a oportunidade está viva. O
// backend recusa com 422, e aqui o formulário da próxima já vem aberto e
// obrigatório — não adianta o servidor barrar se a tela deixa o usuário
// chegar até o botão achando que vai passar.

import { useCallback, useEffect, useMemo, useState } from 'react';
import {
  Plus, Check, X, Pencil, Phone, Users, MapPin, FileText,
  Mail, MessageCircle, CircleDot, AlertTriangle,
} from 'lucide-react';

import api from '../../api';
import Button from '../ui/Button';
import Badge from '../ui/Badge';
import Empty from '../ui/Empty';
import AlertMessage from '../ui/AlertMessage';
import Input, { Select } from '../ui/Input';

const TIPOS = [
  { valor: 'ligacao', rotulo: 'Ligação', Icone: Phone },
  { valor: 'reuniao', rotulo: 'Reunião', Icone: Users },
  { valor: 'visita', rotulo: 'Visita', Icone: MapPin },
  { valor: 'proposta', rotulo: 'Proposta', Icone: FileText },
  { valor: 'email', rotulo: 'E-mail', Icone: Mail },
  { valor: 'whatsapp', rotulo: 'WhatsApp', Icone: MessageCircle },
  { valor: 'outro', rotulo: 'Outro', Icone: CircleDot },
];

const ICONE_TIPO = Object.fromEntries(TIPOS.map((t) => [t.valor, t.Icone]));

// A ordem aqui é a ordem dos blocos na tela. Atrasada em cima porque é
// dívida; cancelada por último porque é ruído.
const GRUPOS = [
  { situacao: 'atrasada', titulo: 'Atrasadas', tom: 'danger' },
  { situacao: 'hoje', titulo: 'Hoje', tom: 'warning' },
  { situacao: 'futura', titulo: 'Futuras', tom: 'info' },
  { situacao: 'concluida', titulo: 'Concluídas', tom: 'success' },
  { situacao: 'cancelada', titulo: 'Canceladas', tom: 'neutral' },
];

const STATUS_ABERTOS = ['ativa', 'suspensa'];

function mensagemDeErro(err, padrao) {
  const d = err?.response?.data?.detail;
  if (typeof d === 'string') return d;
  if (Array.isArray(d) && d[0]?.msg) return d[0].msg;
  if (d?.mensagem) return d.mensagem;
  return padrao;
}

/** ISO (UTC) -> valor de <input type="datetime-local"> no fuso local. */
function paraCampoLocal(iso) {
  const d = iso ? new Date(iso) : new Date();
  const local = new Date(d.getTime() - d.getTimezoneOffset() * 60000);
  return local.toISOString().slice(0, 16);
}

/** Amanhã 09:00, no fuso do usuário. Default de qualquer tarefa nova. */
function amanhaDeManha() {
  const d = new Date();
  d.setDate(d.getDate() + 1);
  d.setHours(9, 0, 0, 0);
  return paraCampoLocal(d.toISOString());
}

function paraIso(valorDoCampo) {
  return valorDoCampo ? new Date(valorDoCampo).toISOString() : null;
}

function formatarPrazo(iso) {
  if (!iso) return '—';
  return new Date(iso).toLocaleString('pt-BR', {
    day: '2-digit', month: '2-digit', year: 'numeric',
    hour: '2-digit', minute: '2-digit',
  });
}

// ── Formulário de tarefa (criar / editar / próxima) ──────────────────

function CamposTarefa({ valor, onChange, usuarios, prefixo }) {
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
        {usuarios.map((u) => (
          <option key={u.id} value={u.id}>{u.nome}</option>
        ))}
      </Select>

      <Input
        label={`${prefixo}Detalhe (opcional)`}
        value={valor.descricao}
        onChange={set('descricao')}
      />
    </div>
  );
}

function tarefaVazia(usuarioPadrao = '') {
  return {
    tipo: 'ligacao',
    titulo: '',
    descricao: '',
    responsavel_id: usuarioPadrao,
    prazo: amanhaDeManha(),
  };
}

function corpoDaTarefa(form) {
  return {
    tipo: form.tipo,
    titulo: form.titulo.trim(),
    descricao: form.descricao.trim() || null,
    responsavel_id: form.responsavel_id,
    prazo: paraIso(form.prazo),
  };
}

function formIncompleto(form) {
  return !form.titulo.trim() || !form.responsavel_id || !form.prazo;
}

// ── Linha da tarefa ──────────────────────────────────────────────────

function LinhaTarefa({
  tarefa, usuarios, exigeProxima, onConcluir, onCancelar, onEditar, ocupado,
}) {
  const [painel, setPainel] = useState(null);   // 'concluir' | 'cancelar' | 'editar'
  const [resultado, setResultado] = useState('');
  const [motivo, setMotivo] = useState('');
  const [proxima, setProxima] = useState(() => tarefaVazia());
  const [edicao, setEdicao] = useState(null);

  const Icone = ICONE_TIPO[tarefa.tipo] || CircleDot;
  const aberta = ['atrasada', 'hoje', 'futura'].includes(tarefa.situacao);

  function abrirConcluir() {
    setResultado('');
    setProxima({ ...tarefaVazia(tarefa.responsavel_id) });
    setPainel(painel === 'concluir' ? null : 'concluir');
  }

  function abrirEditar() {
    setEdicao({
      tipo: tarefa.tipo,
      titulo: tarefa.titulo,
      descricao: tarefa.descricao || '',
      responsavel_id: tarefa.responsavel_id,
      prazo: paraCampoLocal(tarefa.prazo),
    });
    setPainel(painel === 'editar' ? null : 'editar');
  }

  return (
    <li className="border border-hipo-border rounded-lg bg-hipo-card">
      <div className="p-3 flex items-start gap-3">
        <span className="shrink-0 w-7 h-7 rounded-md grid place-items-center bg-hipo-bg text-hipo-slate">
          <Icone size={14} />
        </span>

        <div className="min-w-0 flex-1">
          <p className={
            'text-sm font-medium truncate ' +
            (aberta ? 'text-hipo-ink' : 'text-hipo-slate line-through')
          }>
            {tarefa.titulo}
          </p>
          <p className="text-xs text-hipo-slate">
            {tarefa.tipo_rotulo} · {formatarPrazo(tarefa.prazo)}
            {tarefa.responsavel_nome && ` · ${tarefa.responsavel_nome}`}
          </p>
          {tarefa.descricao && (
            <p className="text-xs text-hipo-muted mt-1">{tarefa.descricao}</p>
          )}
          {tarefa.resultado && (
            <p className="text-xs text-hipo-slate mt-1">
              <span className="font-medium">Resultado:</span> {tarefa.resultado}
            </p>
          )}
          {tarefa.motivo_cancelamento && (
            <p className="text-xs text-hipo-muted mt-1">
              Cancelada: {tarefa.motivo_cancelamento}
            </p>
          )}
        </div>

        {aberta && (
          <div className="shrink-0 flex items-center gap-1">
            <Button
              size="sm" variant="ghost" icon={Pencil}
              aria-label={`Editar ${tarefa.titulo}`}
              onClick={abrirEditar}
            />
            <Button
              size="sm" variant="ghost" icon={X}
              aria-label={`Cancelar ${tarefa.titulo}`}
              onClick={() => setPainel(painel === 'cancelar' ? null : 'cancelar')}
            />
            <Button
              size="sm" icon={Check}
              aria-label={`Concluir ${tarefa.titulo}`}
              onClick={abrirConcluir}
            >
              Concluir
            </Button>
          </div>
        )}
      </div>

      {/* ── Painel de conclusão ── */}
      {painel === 'concluir' && (
        <div className="border-t border-hipo-border p-3 space-y-3 bg-hipo-bg/40">
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
                  Toda tarefa concluída exige a próxima. Se não há próximo
                  passo, finalize a oportunidade.
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
      )}

      {/* ── Painel de cancelamento ── */}
      {painel === 'cancelar' && (
        <div className="border-t border-hipo-border p-3 space-y-3 bg-hipo-bg/40">
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
      )}

      {/* ── Painel de edição ── */}
      {painel === 'editar' && edicao && (
        <div className="border-t border-hipo-border p-3 space-y-3 bg-hipo-bg/40">
          <CamposTarefa
            valor={edicao}
            onChange={setEdicao}
            usuarios={usuarios}
            prefixo=""
          />
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
      )}
    </li>
  );
}

// ── Aba ──────────────────────────────────────────────────────────────

export default function AbaTarefas({ oportunidade, onMudou }) {
  const [dados, setDados] = useState({ total: 0, abertas: 0, atrasadas: 0, itens: [] });
  const [usuarios, setUsuarios] = useState([]);
  const [carregando, setCarregando] = useState(true);
  const [erro, setErro] = useState(null);
  const [ocupado, setOcupado] = useState(false);
  const [criando, setCriando] = useState(false);
  const [nova, setNova] = useState(() => tarefaVazia());

  const oportunidadeId = oportunidade.id;
  const exigeProxima = STATUS_ABERTOS.includes(oportunidade.status);

  const carregar = useCallback(async () => {
    setCarregando(true);
    setErro(null);
    try {
      const { data } = await api.get('/crm/tarefas', {
        params: { oportunidade_id: oportunidadeId },
      });
      setDados(data);
    } catch (err) {
      setErro(mensagemDeErro(err, 'Não foi possível carregar as tarefas.'));
    } finally {
      setCarregando(false);
    }
  }, [oportunidadeId]);

  useEffect(() => { carregar(); }, [carregar]);

  useEffect(() => {
    api.get('/crm/dominio/usuarios')
      .then(({ data }) => setUsuarios(data))
      .catch(() => setUsuarios([]));
  }, []);

  /**
   * Envolve toda mutação: liga o "ocupado", traduz o erro e recarrega.
   * Devolve true/false para o painel saber se pode fechar — fechar num erro
   * jogaria fora o que o usuário digitou.
   */
  const mutar = useCallback(async (fn, padrao) => {
    setOcupado(true);
    setErro(null);
    try {
      await fn();
      await carregar();
      onMudou?.();
      return true;
    } catch (err) {
      setErro(mensagemDeErro(err, padrao));
      return false;
    } finally {
      setOcupado(false);
    }
  }, [carregar, onMudou]);

  const criar = () => mutar(
    () => api.post('/crm/tarefas', {
      oportunidade_id: oportunidadeId, ...corpoDaTarefa(nova),
    }),
    'Não foi possível criar a tarefa.',
  ).then((ok) => {
    if (ok) { setNova(tarefaVazia()); setCriando(false); }
    return ok;
  });

  const concluir = (tarefa, resultado, proxima) => mutar(
    () => api.post(`/crm/tarefas/${tarefa.id}/concluir`, {
      resultado: resultado.trim() || null,
      proxima: proxima ? corpoDaTarefa(proxima) : null,
    }),
    'Não foi possível concluir a tarefa.',
  );

  const cancelar = (tarefa, motivo) => mutar(
    () => api.post(`/crm/tarefas/${tarefa.id}/cancelar`, {
      motivo: motivo.trim() || null,
    }),
    'Não foi possível cancelar a tarefa.',
  );

  const editar = (tarefa, form) => mutar(
    () => api.patch(`/crm/tarefas/${tarefa.id}`, corpoDaTarefa(form)),
    'Não foi possível salvar a tarefa.',
  );

  const grupos = useMemo(
    () => GRUPOS
      .map((g) => ({ ...g, itens: dados.itens.filter((t) => t.situacao === g.situacao) }))
      .filter((g) => g.itens.length > 0),
    [dados.itens],
  );

  return (
    <div className="space-y-4">
      {erro && <AlertMessage tipo="erro">{erro}</AlertMessage>}

      {/* ── Cabeçalho: o estado em números, e a ação ── */}
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="flex items-center gap-2">
          <Badge tone={dados.atrasadas > 0 ? 'danger' : 'neutral'}>
            {dados.atrasadas} atrasada{dados.atrasadas === 1 ? '' : 's'}
          </Badge>
          <Badge tone="info">{dados.abertas} em aberto</Badge>
          <span className="text-xs text-hipo-slate">{dados.total} no total</span>
        </div>
        <Button
          size="sm"
          icon={Plus}
          variant={criando ? 'secondary' : 'primary'}
          onClick={() => {
            setNova(tarefaVazia());
            setCriando((v) => !v);
          }}
        >
          {criando ? 'Fechar' : 'Nova tarefa'}
        </Button>
      </div>

      {/* ── Criação inline. Nunca modal: esta aba já vive dentro de um. ── */}
      {criando && (
        <div className="border border-hipo-border rounded-lg p-3 space-y-3 bg-hipo-bg/40">
          <CamposTarefa
            valor={nova}
            onChange={setNova}
            usuarios={usuarios}
            prefixo=""
          />
          <div className="flex justify-end gap-2">
            <Button size="sm" variant="ghost" onClick={() => setCriando(false)}>
              Cancelar
            </Button>
            <Button
              size="sm" loading={ocupado} disabled={formIncompleto(nova)}
              onClick={criar}
            >
              Criar tarefa
            </Button>
          </div>
        </div>
      )}

      {carregando ? (
        <p className="py-8 text-center text-sm text-hipo-slate">Carregando tarefas…</p>
      ) : dados.itens.length === 0 ? (
        <Empty
          title="Nenhuma tarefa nesta oportunidade"
          description="Agende o próximo contato para a negociação não parar."
          icon={CircleDot}
          action={
            <Button icon={Plus} onClick={() => setCriando(true)}>Nova tarefa</Button>
          }
        />
      ) : (
        grupos.map((grupo) => (
          <section key={grupo.situacao} aria-label={grupo.titulo} className="space-y-2">
            <div className="flex items-center gap-2">
              <h4 className="text-xs font-semibold uppercase tracking-wide text-hipo-slate">
                {grupo.titulo}
              </h4>
              <Badge tone={grupo.tom}>{grupo.itens.length}</Badge>
            </div>
            <ul className="space-y-2">
              {grupo.itens.map((t) => (
                <LinhaTarefa
                  key={t.id}
                  tarefa={t}
                  usuarios={usuarios}
                  exigeProxima={exigeProxima}
                  onConcluir={concluir}
                  onCancelar={cancelar}
                  onEditar={editar}
                  ocupado={ocupado}
                />
              ))}
            </ul>
          </section>
        ))
      )}
    </div>
  );
}
