// web/src/components/crm/agendaComum.js
//
// O vocabulário da agenda, num lugar só: o que a grade, o formulário e o
// cartão precisam concordar.
//
// Existe pelo mesmo motivo de `tarefaComum.jsx` — a tela da semana e o
// modal de reunião compartilham modalidade, duração e formatação de
// horário, e duas cópias divergiriam no primeiro ajuste. Só que aqui há um
// terceiro consumidor que não é código nosso: o convite que chega no
// e-mail do cliente.
//
// POR ISSO O RÓTULO NÃO ESTÁ AQUI. "CF - XPTO (Bruno) - ON" é montado no
// SERVIDOR (services/agenda.rotulo) e chega pronto em `reuniao.rotulo`,
// junto com `slot`, `fim` e `fora_da_grade`. Reimplementar essa string no
// navegador criaria uma quarta versão dela, e a versão que o cliente vê
// não é nenhuma das que dá para conferir olhando a tela.
//
// O que mora aqui é o que o navegador precisa ANTES de o servidor
// responder: os rótulos dos seletores e o desenho de datas.

import { Video, MapPin, CheckCircle2, CalendarX, UserX } from 'lucide-react';

// ── Modalidade ───────────────────────────────────────────────────────
//
// A sigla é a mesma do backend (services/agenda.SIGLA_MODALIDADE) porque é
// a que aparece no rótulo. Duplicada, e não derivada da resposta, porque o
// seletor precisa dela antes de existir uma reunião para responder.
export const MODALIDADES = [
  { valor: 'online', rotulo: 'Online', sigla: 'ON', Icone: Video },
  { valor: 'presencial', rotulo: 'Presencial', sigla: 'PRES', Icone: MapPin },
];

export const ICONE_MODALIDADE = Object.fromEntries(
  MODALIDADES.map((m) => [m.valor, m.Icone])
);

// Durações oferecidas. Múltiplos do passo da grade (30 min) mais os 45 —
// que não fecha slot, mas é a duração real de muita reunião comercial, e o
// backend aceita qualquer valor entre 5 e 480. Oferecer uma lista curta em
// vez de um campo numérico é o que evita "300 minutos" digitado por
// engano pintar a semana inteira de ocupado.
export const DURACOES = [
  { valor: 30, rotulo: '30 min' },
  { valor: 45, rotulo: '45 min' },
  { valor: 60, rotulo: '1 hora' },
  { valor: 90, rotulo: '1h30' },
  { valor: 120, rotulo: '2 horas' },
];

export const DURACAO_PADRAO = 30;

// ── O desfecho ───────────────────────────────────────────────────────
//
// Três resultados, e a diferença entre os dois últimos é uma régua de
// relógio: 24h de antecedência. Espelha `services/agenda.DESFECHOS` e
// `ROTULO_DESFECHO`.
//
// Duplicado aqui, e não lido da resposta, porque o formulário precisa
// oferecer as três opções ANTES de existir uma reunião para responder. O
// que NÃO é duplicado é a decisão de qual delas sugerir: isso vem pronto
// em `reuniao.desfecho_sugerido`, calculado no servidor — a régua das 24h
// existe num lugar só.
export const DESFECHOS = [
  {
    valor: 'realizada',
    rotulo: 'Realizada',
    ajuda: 'A reunião aconteceu.',
    Icone: CheckCircle2,
    tom: 'success',
    // É o único que CONCLUI a tarefa, e por isso o único que exige a
    // próxima enquanto a oportunidade está viva. Ver `exigeProximaTarefa`.
    conclui: true,
  },
  {
    valor: 'cancelada',
    rotulo: 'Cancelada',
    ajuda: 'Desmarcada com 24h ou mais de antecedência.',
    Icone: CalendarX,
    tom: 'neutral',
    conclui: false,
  },
  {
    valor: 'no_show',
    rotulo: 'No-show',
    ajuda: 'Desmarcada em cima da hora, ou o cliente não apareceu.',
    Icone: UserX,
    tom: 'danger',
    conclui: false,
  },
];

export const POR_DESFECHO = Object.fromEntries(
  DESFECHOS.map((d) => [d.valor, d])
);

/**
 * "avisado com 3h de antecedência" / "2 dias antes" / "depois da hora".
 *
 * Escrito ao lado da opção sugerida para a regra das 24h ficar VISÍVEL em
 * vez de virar conta de cabeça. Quem lê "avisado com 3h" entende num
 * relance por que o sistema propôs no-show — e discorda com conhecimento
 * de causa, se for o caso.
 */
export function antecedenciaEmPalavras(horas) {
  if (horas === null || horas === undefined) return null;
  if (horas < 0) return 'depois da hora marcada';
  if (horas < 1) return 'menos de 1h antes';
  if (horas < 24) {
    const h = Math.round(horas);
    return `${h}h antes`;
  }
  const dias = Math.floor(horas / 24);
  return `${dias} dia${dias === 1 ? '' : 's'} antes`;
}

// ── Datas ────────────────────────────────────────────────────────────

const MESES = ['jan', 'fev', 'mar', 'abr', 'mai', 'jun',
               'jul', 'ago', 'set', 'out', 'nov', 'dez'];

/**
 * '2026-09-07' -> Date local ao MEIO-DIA.
 *
 * `new Date('2026-09-07')` é interpretado como meia-noite UTC, que em
 * Brasília (UTC-3) é 21h do dia 6 — a segunda-feira da grade aparecia como
 * domingo. Meio-dia dá 12 horas de folga para os dois lados e sobrevive a
 * qualquer fuso do Brasil e ao horário de verão.
 */
export function diaLocal(iso) {
  const [ano, mes, dia] = String(iso).slice(0, 10).split('-').map(Number);
  return new Date(ano, mes - 1, dia, 12, 0, 0, 0);
}

/** Date -> 'AAAA-MM-DD', sem passar por UTC (mesma armadilha acima). */
export function paraIsoDia(d) {
  const mes = String(d.getMonth() + 1).padStart(2, '0');
  const dia = String(d.getDate()).padStart(2, '0');
  return `${d.getFullYear()}-${mes}-${dia}`;
}

/** '07/set' — o cabeçalho da coluna do dia. */
export function diaCurto(iso) {
  const d = diaLocal(iso);
  return `${String(d.getDate()).padStart(2, '0')}/${MESES[d.getMonth()]}`;
}

/** '07 a 11/set' ou '29/set a 03/out' — o título da semana. */
export function faixaDaSemana(inicioIso, fimIso) {
  const a = diaLocal(inicioIso);
  const b = diaLocal(fimIso);
  const dia = (d) => String(d.getDate()).padStart(2, '0');
  if (a.getMonth() === b.getMonth()) {
    return `${dia(a)} a ${dia(b)}/${MESES[b.getMonth()]}`;
  }
  return `${dia(a)}/${MESES[a.getMonth()]} a ${dia(b)}/${MESES[b.getMonth()]}`;
}

// O fuso da OPERAÇÃO, não o do navegador. Espelha
// `services/agenda.FUSO_OPERACAO`.
//
// Quem decide em que LINHA da grade a reunião é desenhada é o servidor, e
// ele decide em horário de Brasília (`reuniao.slot`). Se o cartão
// escrevesse a hora no fuso da máquina de quem está olhando, os dois
// discordariam: num navegador em UTC, a reunião das 09:15 apareceria como
// "12:15" ancorada na linha das 09:00 — a grade mentindo sobre si mesma,
// e a pessoa concluindo que o horário foi gravado errado.
//
// Não é hipótese remota: o runner de teste roda em UTC, e foi ele quem
// pegou isto. Um notebook com fuso trocado ou alguém viajando produz
// exatamente o mesmo sintoma.
const FUSO_OPERACAO = 'America/Sao_Paulo';

/**
 * ISO com fuso -> '09:15', SEMPRE no fuso da operação.
 *
 * É a hora real da reunião, que pode não ser a do slot — e é justamente
 * por poder divergir do slot que ela precisa estar na mesma régua que ele.
 */
export function horaCurta(iso) {
  return new Date(iso).toLocaleTimeString('pt-BR', {
    hour: '2-digit', minute: '2-digit', timeZone: FUSO_OPERACAO,
  });
}

/**
 * ISO (UTC) -> valor de <input type="datetime-local"> no fuso do NAVEGADOR.
 *
 * Aqui o fuso é o da máquina, e não dá para ser diferente: `datetime-local`
 * não tem fuso, e o que o usuário digita volta por `paraIso` interpretado
 * pelo mesmo relógio — ida e volta fecham sozinhas. Escrever no campo uma
 * hora de Brasília e lê-la de volta como hora local produziria um
 * deslocamento a cada salvamento.
 *
 * A operação inteira trabalha em BRT, e o Brasil não tem horário de verão
 * desde 2019, então na prática este campo e o `horaCurta` acima mostram a
 * mesma hora. Mantido igual ao `paraCampoLocal` de `tarefaComum`, que
 * resolve o mesmo problema para o prazo da tarefa.
 */
export function paraCampoLocal(iso) {
  const d = iso ? new Date(iso) : new Date();
  const local = new Date(d.getTime() - d.getTimezoneOffset() * 60000);
  return local.toISOString().slice(0, 16);
}

/** Dia + slot 'HH:MM' -> valor de <input type="datetime-local">. */
export function campoLocalDoSlot(diaIso, slot) {
  return `${String(diaIso).slice(0, 10)}T${slot}`;
}

export function paraIso(valorDoCampo) {
  return valorDoCampo ? new Date(valorDoCampo).toISOString() : null;
}

/** Soma semanas a um 'AAAA-MM-DD' e devolve outro 'AAAA-MM-DD'. */
export function somarSemanas(inicioIso, semanas) {
  const d = diaLocal(inicioIso);
  d.setDate(d.getDate() + semanas * 7);
  return paraIsoDia(d);
}

export function hojeIso() {
  return paraIsoDia(new Date());
}

// ── Erros ────────────────────────────────────────────────────────────
//
// Cópia literal de `tarefaComum.mensagemDeErro`. Duplicada de propósito:
// importar `tarefaComum` daqui puxaria junto todos os ícones e o
// `PainelAcoesTarefa` para dentro do bundle da agenda, por seis linhas.
export function mensagemDeErro(err, padrao) {
  const d = err?.response?.data?.detail;
  if (typeof d === 'string') return d;
  if (Array.isArray(d) && d[0]?.msg) return d[0].msg;
  if (d?.mensagem) return d.mensagem;
  return padrao;
}
