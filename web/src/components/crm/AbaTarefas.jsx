// web/src/components/crm/AbaTarefas.jsx
//
// Tarefas da oportunidade como LINHA DO TEMPO: o que passou, o que está
// aberto e o que vem, num fluxo vertical único.
//
// ── Por que linha do tempo e não lista de cartões ────────────────────
// Cartão com borda cria uma unidade visual fechada, e o olho lê cada um
// como um item isolado. A pergunta que essa aba responde não é "quais são
// os itens", é "como essa negociação andou" — e história se lê em fluxo. O
// ponto com o ícone do tipo mais o traço ligando dão a sequência de graça:
// dá para ver de longe que foram três ligações e um WhatsApp, sem ler.
//
// ── Ordem cronológica decrescente ────────────────────────────────────
// Futuro no topo, passado embaixo. O que está por vir é o que exige
// decisão; o histórico é consulta. A ordem vem do servidor
// (`ordenar=cronologico`) para não existir uma segunda regra de ordenação
// no navegador.
//
// ── Drilldown em vez de tudo na linha ────────────────────────────────
// A linha mostra data, tipo, título e responsável. Descrição completa,
// resultado, motivo de cancelamento e as AÇÕES ficam no drilldown, que abre
// ao clicar. Botões em toda linha devolveriam o peso visual que a caixa
// tinha — e a maioria das linhas é histórico, onde não há o que fazer.
//
// ── Por que nada abre modal ──────────────────────────────────────────
// Esta aba vive DENTRO do modal da oportunidade. Modal sobre modal empilha
// z-index, rouba foco e faz o Esc fechar os dois, perdendo o formulário em
// edição — a mesma razão que fez o EntityPicker virar popover.
//
// ── A regra que dá nome à tela ───────────────────────────────────────
// Concluir exige agendar a próxima enquanto a oportunidade está viva. O
// backend recusa com 422, e aqui o formulário da próxima já vem aberto e
// obrigatório.

import { useCallback, useEffect, useState } from 'react';
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

// Cada situação tem um tom e uma palavra. A palavra fica sob a linha porque
// 'Atrasado' precisa saltar sem depender só de cor — daltônico não vê tom.
const SITUACAO = {
  atrasada: {
    palavra: 'Atrasado',
    ponto: 'border-hipo-danger bg-hipo-card',
    texto: 'text-hipo-danger',
    icone: 'text-hipo-danger',
  },
  hoje: {
    palavra: 'Hoje',
    ponto: 'border-hipo-warning bg-hipo-warningSoft',
    texto: 'text-hipo-warning',
    icone: 'text-hipo-warning',
  },
  futura: {
    palavra: 'Agendado',
    ponto: 'border-hipo-blue bg-hipo-blueSoft',
    texto: 'text-hipo-blue',
    icone: 'text-hipo-blue',
  },
  concluida: {
    palavra: 'concluído',
    ponto: 'border-hipo-success bg-hipo-success',
    texto: 'text-hipo-success',
    icone: 'text-white',
  },
  cancelada: {
    palavra: 'cancelado',
    ponto: 'border-hipo-border bg-hipo-bg',
    texto: 'text-hipo-muted',
    icone: 'text-hipo-muted',
  },
};

const ABERTAS = ['atrasada', 'hoje', 'futura'];
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

/**
 * '15/mar' — a coluna da esquerda da linha do tempo.
 *
 * Montado à mão porque `toLocaleDateString('pt-BR', {month:'short'})` devolve
 * "15 de mar." — o "de" quebra a coluna em duas linhas e desalinha os pontos.
 */
const MESES = ['jan', 'fev', 'mar', 'abr', 'mai', 'jun',
               'jul', 'ago', 'set', 'out', 'nov', 'dez'];

function dataCurta(iso) {
  const d = new Date(iso);
  return `${String(d.getDate()).padStart(2, '0')}/${MESES[d.getMonth()]}`;
}

function dataCompleta(iso) {
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

// ── Um evento da linha do tempo ──────────────────────────────────────

function Evento({
  tarefa, ultima, aberta, expandida, usuarios, exigeProxima, ocupado,
  onAlternar, onConcluir, onCancelar, onEditar,
}) {
  const [painel, setPainel] = useState(null);   // 'concluir' | 'cancelar' | 'editar'
  const [resultado, setResultado] = useState('');
  const [motivo, setMotivo] = useState('');
  const [proxima, setProxima] = useState(() => tarefaVazia());
  const [edicao, setEdicao] = useState(null);

  const Icone = ICONE_TIPO[tarefa.tipo] || CircleDot;
  const tom = SITUACAO[tarefa.situacao] || SITUACAO.cancelada;

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
    <li className="relative flex gap-3">
      {/* Data à esquerda, fora do fluxo do texto — é eixo, não conteúdo. */}
      <span className="shrink-0 w-12 pt-1 text-right text-xs text-hipo-slate tabular-nums">
        {dataCurta(tarefa.prazo)}
      </span>

      {/* Ponto + traço. O traço não desce na última: linha do tempo termina. */}
      <div className="shrink-0 flex flex-col items-center">
        <span
          aria-hidden="true"
          className={`w-6 h-6 rounded-full border-2 grid place-items-center ${tom.ponto}`}
        >
          <Icone size={12} className={tom.icone} />
        </span>
        {!ultima && <span className="w-px flex-1 bg-hipo-border" />}
      </div>

      <div className="min-w-0 flex-1 pb-4">
        <button
          type="button"
          onClick={onAlternar}
          aria-expanded={expandida}
          className="w-full text-left group"
        >
          <span className="flex items-baseline gap-2">
            <span className={`text-sm font-medium ${tom.texto}`}>
              {tarefa.tipo_rotulo}
            </span>
            <span className={
              'text-sm truncate group-hover:underline ' +
              (aberta ? 'text-hipo-ink' : 'text-hipo-slate')
            }>
              {tarefa.titulo}
            </span>
            {tarefa.responsavel_nome && (
              <span className="ml-auto shrink-0 text-xs text-hipo-slate">
                {tarefa.responsavel_nome}
              </span>
            )}
          </span>
          <span className={`block text-xs ${tom.texto}`}>{tom.palavra}</span>
        </button>

        {/* ── Drilldown ── */}
        {expandida && (
          <div className="mt-2 space-y-3 text-sm">
            <dl className="grid grid-cols-1 sm:grid-cols-2 gap-x-4 gap-y-1 text-xs">
              <div>
                <dt className="inline text-hipo-slate">Prazo: </dt>
                <dd className="inline text-hipo-ink">{dataCompleta(tarefa.prazo)}</dd>
              </div>
              {tarefa.concluida_em && (
                <div>
                  <dt className="inline text-hipo-slate">Concluída em: </dt>
                  <dd className="inline text-hipo-ink">{dataCompleta(tarefa.concluida_em)}</dd>
                </div>
              )}
              {tarefa.cancelada_em && (
                <div>
                  <dt className="inline text-hipo-slate">Cancelada em: </dt>
                  <dd className="inline text-hipo-ink">{dataCompleta(tarefa.cancelada_em)}</dd>
                </div>
              )}
            </dl>

            {tarefa.descricao && (
              <p className="text-hipo-slate">{tarefa.descricao}</p>
            )}
            {tarefa.resultado && (
              <p className="text-hipo-ink">
                <span className="text-hipo-slate">Resultado: </span>
                {tarefa.resultado}
              </p>
            )}
            {tarefa.motivo_cancelamento && (
              <p className="text-hipo-muted">
                Cancelada: {tarefa.motivo_cancelamento}
              </p>
            )}
            {tarefa.tarefa_anterior_id && (
              <p className="text-xs text-hipo-muted">
                Veio da conclusão da tarefa anterior.
              </p>
            )}

            {/*
              Ações só em tarefa aberta. Tarefa fechada é histórico, e o
              backend recusa edição — mostrar o botão seria mentira.
            */}
            {aberta && !painel && (
              <div className="flex flex-wrap items-center gap-2 pt-1">
                <Button
                  size="sm" icon={Check}
                  aria-label={`Concluir ${tarefa.titulo}`}
                  onClick={abrirConcluir}
                >
                  Concluir
                </Button>
                <Button
                  size="sm" variant="ghost" icon={Pencil}
                  aria-label={`Editar ${tarefa.titulo}`}
                  onClick={abrirEditar}
                >
                  Editar
                </Button>
                <Button
                  size="sm" variant="ghost" icon={X}
                  aria-label={`Cancelar ${tarefa.titulo}`}
                  onClick={() => setPainel('cancelar')}
                >
                  Cancelar
                </Button>
              </div>
            )}

            {painel === 'concluir' && (
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
                    onClick={() =>
                      onConcluir(tarefa, resultado, exigeProxima ? proxima : null)
                        .then((ok) => ok && setPainel(null))}
                  >
                    Concluir tarefa
                  </Button>
                </div>
              </div>
            )}

            {painel === 'cancelar' && (
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
                    onClick={() =>
                      onCancelar(tarefa, motivo).then((ok) => ok && setPainel(null))}
                  >
                    Cancelar tarefa
                  </Button>
                </div>
              </div>
            )}

            {painel === 'editar' && edicao && (
              <div className="space-y-3 border-l-2 border-hipo-border pl-3">
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
                    onClick={() =>
                      onEditar(tarefa, edicao).then((ok) => ok && setPainel(null))}
                  >
                    Salvar tarefa
                  </Button>
                </div>
              </div>
            )}
          </div>
        )}
      </div>
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
  const [expandida, setExpandida] = useState(null);

  const oportunidadeId = oportunidade.id;
  const exigeProxima = STATUS_ABERTOS.includes(oportunidade.status);

  const carregar = useCallback(async () => {
    setCarregando(true);
    setErro(null);
    try {
      const { data } = await api.get('/crm/tarefas', {
        params: { oportunidade_id: oportunidadeId, ordenar: 'cronologico' },
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
        <ol aria-label="Linha do tempo das tarefas" className="pt-1">
          {dados.itens.map((t, i) => (
            <Evento
              key={t.id}
              tarefa={t}
              ultima={i === dados.itens.length - 1}
              aberta={ABERTAS.includes(t.situacao)}
              expandida={expandida === t.id}
              onAlternar={() => setExpandida((atual) => (atual === t.id ? null : t.id))}
              usuarios={usuarios}
              exigeProxima={exigeProxima}
              ocupado={ocupado}
              onConcluir={concluir}
              onCancelar={cancelar}
              onEditar={editar}
            />
          ))}
        </ol>
      )}
    </div>
  );
}
