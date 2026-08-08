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
// A tela de gestão (/crm/tarefas) responde outra pergunta — "quanta coisa
// está parada e com quem" — e por isso usa colunas, não fluxo. As duas
// compartilham vocabulário, formulário e painéis de ação via `tarefaComum`.
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

import { useCallback, useEffect, useState } from 'react';
import { Plus, CircleDot } from 'lucide-react';

import api from '../../api';
import Button from '../ui/Button';
import Badge from '../ui/Badge';
import Empty from '../ui/Empty';
import AlertMessage from '../ui/AlertMessage';
import {
  ABERTAS, ICONE_TIPO, SITUACAO, STATUS_ABERTOS,
  CamposTarefa, PainelAcoesTarefa,
  corpoDaTarefa, dataCompleta, dataCurta, formIncompleto,
  mensagemDeErro, tarefaVazia,
} from './tarefaComum';

// ── Um evento da linha do tempo ──────────────────────────────────────

function Evento({
  tarefa, ultima, aberta, expandida, usuarios, exigeProxima, ocupado,
  onAlternar, onConcluir, onCancelar, onEditar,
}) {
  const [painel, setPainel] = useState(null);   // 'concluir' | 'cancelar' | 'editar'

  const Icone = ICONE_TIPO[tarefa.tipo] || CircleDot;
  const tom = SITUACAO[tarefa.situacao] || SITUACAO.cancelada;

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

            {tarefa.descricao && <p className="text-hipo-slate">{tarefa.descricao}</p>}
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
            {aberta && (
              <PainelAcoesTarefa
                tarefa={tarefa}
                painel={painel}
                setPainel={setPainel}
                usuarios={usuarios}
                exigeProxima={exigeProxima}
                ocupado={ocupado}
                onConcluir={onConcluir}
                onCancelar={onCancelar}
                onEditar={onEditar}
              />
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
          <CamposTarefa valor={nova} onChange={setNova} usuarios={usuarios} />
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
