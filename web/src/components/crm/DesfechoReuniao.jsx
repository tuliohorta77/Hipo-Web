// web/src/components/crm/DesfechoReuniao.jsx
//
// "O que aconteceu com a reunião?" — a pergunta e a resposta registrada,
// num componente só para as TRÊS telas que fecham reunião: a Agenda (dentro
// do ModalReuniao), a gestão de Tarefas e a aba de tarefas da oportunidade.
//
// Morava dentro do ModalReuniao. Enquanto só a Agenda perguntava, a tela de
// Tarefas fechava a mesma reunião com Concluir/Cancelar: um no-show virava
// "cancelada" pela hora do clique, e ninguém escolhia nada. Extrair para cá
// é o que garante que as três telas façam a mesma pergunta, com as mesmas
// três respostas e a mesma régua das 24h.

import { useState } from 'react';
import {
  AlertTriangle, ClipboardCheck, CalendarCheck, CalendarPlus, Pencil,
} from 'lucide-react';

import api from '../../api';
import Badge from '../ui/Badge';
import Button from '../ui/Button';
import { Textarea } from '../ui/Input';
import { DESFECHOS, POR_DESFECHO, antecedenciaEmPalavras } from './agendaComum';
import {
  CamposTarefa, PainelAcoesTarefa, TIPOS_AGENDAVEIS, corpoDaTarefa, dataCompleta,
  exigeProximaTarefa, formIncompleto, mensagemDeErro, podeEntrarNaAgenda, tarefaVazia,
} from './tarefaComum';

/**
 * A tarefa no formato que o painel de desfecho lê.
 *
 * A tarefa já traz do servidor tudo o que o painel precisa — sugestão,
 * status da oportunidade, outras abertas. Aqui só se renomeiam os campos
 * que a agenda chama de outro jeito (prazo é `inicio`, responsável é
 * `anfitriao_id`).
 */
export function reuniaoDaTarefa(tarefa) {
  return {
    id: tarefa.reuniao_id || tarefa.id,
    inicio: tarefa.prazo,
    anfitriao_id: tarefa.responsavel_id,
    oportunidade_id: tarefa.oportunidade_id,
    status_oportunidade: tarefa.status_oportunidade,
    outras_abertas: tarefa.outras_abertas,
    desfecho_sugerido: tarefa.desfecho_sugerido,
  };
}

/**
 * Se a próxima tarefa criada junto com um fechamento é reunião ou visita,
 * põe ela na agenda. "Toda reunião nasce na agenda" vale também para a
 * próxima marcada dentro do formulário de conclusão.
 *
 * Devolve null quando deu certo (ou não havia o que agendar) e a frase do
 * erro quando não deu — o fechamento já foi gravado, então o erro vira
 * AVISO: a tarefa existe, só não entrou na grade (horário ocupado, fim de
 * semana), e o botão "Colocar na agenda" continua nela.
 */
export async function agendarProximaSeForReuniao(proxima, proximaId) {
  if (!proxima || !proximaId || !TIPOS_AGENDAVEIS.includes(proxima.tipo)) return null;
  try {
    await api.post(`/crm/agenda/reunioes/de-tarefa/${proximaId}`, {
      modalidade: proxima.tipo === 'visita' ? 'presencial' : 'online',
    });
    return null;
  } catch (err) {
    return 'A próxima tarefa foi criada, mas não entrou na agenda: '
      + `${mensagemDeErro(err, 'erro ao agendar')} Use "Colocar na agenda" nela.`;
  }
}

// ── O desfecho ───────────────────────────────────────────────────────

/**
 * O que aconteceu com a reunião, depois de registrado.
 *
 * Mostra o EFETIVO, que pode não ter sido registrado por ninguém: quem
 * concluiu a tarefa pela aba de Tarefas fechou a reunião sem passar por
 * aqui, e o servidor deduz `realizada`. A tela diz qual dos dois é —
 * apresentar uma dedução com a mesma cara de um registro faria alguém
 * defender na reunião de segunda um número que ninguém afirmou.
 */
export function DesfechoRegistrado({ reuniao }) {
  const d = POR_DESFECHO[reuniao.desfecho_efetivo];
  if (!d) return null;
  const Icone = d.Icone;
  const deduzido = !reuniao.desfecho;
  const antecedencia = antecedenciaEmPalavras(reuniao.desfecho_antecedencia_horas);

  return (
    <div className="border-t border-hipo-border pt-4">
      <div className="flex flex-wrap items-center gap-2">
        <Badge tone={d.tom}>
          <Icone size={12} aria-hidden="true" />
          {d.rotulo}
        </Badge>
        {deduzido ? (
          <span className="text-xs text-hipo-slate">
            deduzido do fechamento da tarefa — ninguém registrou pela agenda
          </span>
        ) : (
          <span className="text-xs text-hipo-slate">
            registrado por {reuniao.desfecho_por_nome || 'alguém'} em{' '}
            {dataCompleta(reuniao.desfecho_em)}
            {/*
              A antecedência que o SERVIDOR gravou no instante do registro
              — não a recalculada agora. É ela que responde, seis meses
              depois, "esse no-show foi avisado com quanto tempo?".
            */}
            {antecedencia && ` · ${antecedencia}`}
          </span>
        )}
      </div>
      {reuniao.desfecho_observacao && (
        <p className="mt-2 text-sm text-hipo-ink whitespace-pre-wrap">
          {reuniao.desfecho_observacao}
        </p>
      )}
    </div>
  );
}

/**
 * Registrar o que aconteceu: realizada, cancelada ou no-show.
 *
 * ── Por que três botões e não "Cancelar reunião" ─────────────────────
 * A pergunta que a operação precisa responder não é "cancelo?", é "o que
 * aconteceu?" — e ela tem três respostas, não duas. Um botão de cancelar
 * ao lado de um de concluir deixaria o no-show sem porta, e ele é
 * justamente o número que dói.
 *
 * ── Por que a sugestão vem pronta do servidor ────────────────────────
 * A régua das 24h mora em `services/agenda`, e quem decide o que
 * pré-selecionar é ele (`desfecho_sugerido`). Recalcular aqui daria uma
 * segunda versão da mesma conta, e a que divergisse seria a que a pessoa
 * está olhando na hora de responder.
 *
 * A ANTECEDÊNCIA ao lado é calculada no navegador de propósito: ela muda a
 * cada minuto que o modal fica aberto, e é rótulo, não dado. O número que
 * vale fica gravado pelo servidor no instante do registro.
 */
export function PainelDesfecho({
  reuniao, usuarios, ocupado, onRegistrar, onVoltar,
}) {
  const [escolha, setEscolha] = useState(reuniao.desfecho_sugerido || 'realizada');
  const [observacao, setObservacao] = useState('');
  const [proxima, setProxima] = useState(() => tarefaVazia(reuniao.anfitriao_id));

  // O alvo sai de `oportunidade_id`: a reunião aberta pela aba de tarefas
  // do parceiro é de parceiro. A regra vem da função compartilhada, e não de um
  // `STATUS_ABERTOS.includes(...)` escrito aqui: foi exatamente essa cópia
  // que produziu o bug do formulário que não aparecia (ver `exigeProximaTarefa`).
  //
  // `outras_abertas` é o que conserta a esteira: a reunião É uma tarefa da
  // oportunidade, e com outra ainda aberta fechá-la não deixa o negócio sem
  // próximo passo. Sem isso, cada reunião concluída obrigava a criar mais
  // uma tarefa e o número de abertas nunca voltava para um.
  const exigeProxima = escolha === 'realizada'
    && exigeProximaTarefa(
      reuniao.oportunidade_id ? 'oportunidade' : 'parceiro',
      reuniao.status_oportunidade, reuniao.outras_abertas,
    );

  const agora = Date.now();
  const horas = (new Date(reuniao.inicio).getTime() - agora) / 3600000;
  const antecedencia = antecedenciaEmPalavras(horas);

  return (
    <div className="border-t border-hipo-border pt-4 space-y-3">
      <p className="flex items-center gap-1.5 text-sm font-medium text-hipo-ink">
        <ClipboardCheck size={14} className="text-hipo-blue" />
        O que aconteceu?
      </p>

      <div
        role="radiogroup"
        aria-label="Desfecho da reunião"
        className="grid grid-cols-1 sm:grid-cols-3 gap-2"
      >
        {DESFECHOS.map((d) => {
          const Icone = d.Icone;
          const marcado = escolha === d.valor;
          return (
            <button
              key={d.valor}
              type="button"
              role="radio"
              aria-checked={marcado}
              onClick={() => setEscolha(d.valor)}
              className={
                'text-left px-3 py-2 rounded-lg border transition-colors ' +
                'focus:outline-none focus-visible:ring-2 focus-visible:ring-hipo-blue ' +
                (marcado
                  ? 'border-hipo-blue bg-hipo-blueSoft'
                  : 'border-hipo-border hover:bg-hipo-bg')
              }
            >
              <span className="flex items-center gap-1.5 text-sm font-medium text-hipo-ink">
                <Icone size={14} aria-hidden="true" />
                {d.rotulo}
              </span>
              <span className="block mt-0.5 text-[11px] leading-snug text-hipo-slate">
                {d.ajuda}
              </span>
            </button>
          );
        })}
      </div>

      {/*
        A régua das 24h escrita por extenso, e não deixada como conta de
        cabeça. Quem lê "avisado 3h antes" entende num relance por que o
        sistema propôs no-show — e discorda com conhecimento de causa, se
        for o caso.
      */}
      {antecedencia && reuniao.desfecho_sugerido !== 'realizada' && (
        <p className="text-xs text-hipo-slate">
          A reunião foi {antecedencia === 'depois da hora marcada'
            ? 'marcada para antes de agora'
            : `avisada ${antecedencia}`}
          {' '}— pela régua das 24h isso é{' '}
          <strong className="font-medium text-hipo-ink">
            {POR_DESFECHO[reuniao.desfecho_sugerido]?.rotulo?.toLowerCase()}
          </strong>.
        </p>
      )}

      <Textarea
        id={`desfecho-obs-${reuniao.id}`}
        label="O que aconteceu (opcional)"
        rows={2}
        value={observacao}
        onChange={(e) => setObservacao(e.target.value)}
        placeholder={escolha === 'realizada'
          ? 'Gostaram do PCMSO, pediram proposta para 40 vidas'
          : 'Cliente pediu para remarcar na semana que vem'}
      />

      {/*
        Só "Realizada" conclui a tarefa, e é por isso que só ela exige a
        próxima: concluir é dizer que o negócio ANDOU, e negócio que anda
        tem próximo passo. Cancelar não é isso — mas aceita a próxima do
        mesmo jeito, porque remarcar é o desfecho natural de um no-show.
      */}
      {exigeProxima ? (
        <div className="space-y-2">
          <p className="flex items-center gap-1.5 text-xs text-hipo-slate">
            <AlertTriangle size={13} className="text-hipo-warning shrink-0" />
            Toda reunião realizada exige a próxima. Se não há próximo passo,
            finalize a oportunidade.
          </p>
          <CamposTarefa
            valor={proxima}
            onChange={setProxima}
            usuarios={usuarios}
            prefixo="Próxima: "
            idBase={`proxima-reuniao-${reuniao.id}`}
          />
        </div>
      ) : escolha === 'realizada' && reuniao.outras_abertas > 0 ? (
        /*
          Dizer POR QUE a próxima não está sendo pedida. Sem a frase, o
          formulário pede às vezes e às vezes não, a diferença fica
          invisível, e o usuário conclui que é bug.
        */
        <p className="text-xs text-hipo-slate">
          Esta oportunidade já tem{' '}
          {reuniao.outras_abertas === 1
            ? 'outra tarefa em aberto'
            : `outras ${reuniao.outras_abertas} tarefas em aberto`}
          {' '}— não é preciso agendar a próxima.
        </p>
      ) : (
        escolha !== 'realizada' && (
          <p className="text-xs text-hipo-slate">
            O evento sai da agenda de todo mundo e o Google avisa o cliente.
            O horário volta a ficar livre.
          </p>
        )
      )}

      <div className="flex justify-end gap-2">
        {onVoltar && (
          <Button variant="ghost" onClick={onVoltar}>Voltar</Button>
        )}
        <Button
          loading={ocupado}
          disabled={exigeProxima && formIncompleto(proxima)}
          onClick={() => onRegistrar({
            desfecho: escolha,
            observacao: observacao.trim() || null,
            proxima: exigeProxima ? corpoDaTarefa(proxima) : null,
          })}
        >
          Registrar {POR_DESFECHO[escolha]?.rotulo?.toLowerCase()}
        </Button>
      </div>
    </div>
  );
}


// ── A reunião dentro das telas de Tarefas ────────────────────────────

/**
 * As ações de uma tarefa que é REUNIÃO ou VISITA, nas telas de Tarefas.
 *
 * Substitui Concluir / Cancelar / Editar da tarefa comum, porque essas três
 * perguntas estão erradas para uma reunião:
 *
 *   Concluir e Cancelar  -> viram "O que aconteceu?", com Realizada,
 *                           Cancelada e No-show — o MESMO painel da Agenda.
 *   Editar               -> na agenda, abre o formulário completo da reunião
 *                           (tipo, duração, convite, quem agendou). Fora
 *                           dela, a edição simples da tarefa, e ao lado o
 *                           botão de colocar na agenda.
 *
 * O backend recusa fechar pela rota de tarefa uma reunião que está na
 * agenda; aqui a tela só não leva o usuário até esse 422.
 */
export function PainelReuniaoDaTarefa({
  tarefa, painel, setPainel, usuarios, ocupado,
  onRegistrarDesfecho, onAbrirReuniao, onEditar, onAgendar,
}) {
  if (painel === 'desfecho') {
    return (
      <PainelDesfecho
        key={tarefa.id}
        reuniao={reuniaoDaTarefa(tarefa)}
        usuarios={usuarios}
        ocupado={ocupado}
        onVoltar={() => setPainel(null)}
        onRegistrar={(corpo) => onRegistrarDesfecho(tarefa, corpo)
          .then((ok) => ok && setPainel(null))}
      />
    );
  }

  if (painel === 'editar') {
    // A edição simples é a mesma da tarefa comum — só existe para reunião
    // que ainda não está na agenda. A que está abre o formulário inteiro.
    return (
      <PainelAcoesTarefa
        tarefa={tarefa}
        painel="editar"
        setPainel={setPainel}
        usuarios={usuarios}
        exigeProxima={() => false}
        ocupado={ocupado}
        onConcluir={async () => false}
        onCancelar={async () => false}
        onEditar={onEditar}
      />
    );
  }

  const naAgenda = Boolean(tarefa.reuniao_id);

  return (
    <div className="flex flex-wrap items-center gap-2">
      <Button
        size="sm" icon={ClipboardCheck}
        aria-label={`Registrar o que aconteceu em ${tarefa.titulo}`}
        onClick={() => setPainel('desfecho')}
      >
        O que aconteceu?
      </Button>

      {naAgenda && onAbrirReuniao ? (
        <Button
          size="sm" variant="ghost" icon={Pencil}
          aria-label={`Abrir a reunião ${tarefa.titulo}`}
          onClick={() => onAbrirReuniao(tarefa.reuniao_id)}
        >
          Editar reunião
        </Button>
      ) : (
        <Button
          size="sm" variant="ghost" icon={Pencil}
          aria-label={`Editar ${tarefa.titulo}`}
          onClick={() => setPainel('editar')}
        >
          Editar
        </Button>
      )}

      {!naAgenda && onAgendar && podeEntrarNaAgenda(tarefa) && (
        <Button
          size="sm" variant="ghost" icon={CalendarPlus}
          loading={ocupado}
          aria-label={`Colocar ${tarefa.titulo} na agenda`}
          onClick={() => onAgendar(tarefa)}
        >
          Colocar na agenda
        </Button>
      )}

      {naAgenda && (
        <span className="inline-flex items-center gap-1 text-xs text-hipo-success">
          <CalendarCheck size={13} aria-hidden="true" />
          na agenda{tarefa.reuniao_tipo_sigla ? ` · ${tarefa.reuniao_tipo_sigla}` : ''}
        </span>
      )}
    </div>
  );
}

/**
 * O desfecho de uma reunião já fechada, no tamanho de um selo — para o
 * cartão do kanban e a linha do tempo, onde "cancelado" escondia o no-show.
 */
export function SeloDesfecho({ tarefa }) {
  const d = POR_DESFECHO[tarefa.desfecho_efetivo];
  if (!d) return null;
  const Icone = d.Icone;
  return (
    <Badge tone={d.tom}>
      <Icone size={11} aria-hidden="true" />
      {d.rotulo}
    </Badge>
  );
}
