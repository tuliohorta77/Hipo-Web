// web/src/components/uc/QuizAula.jsx
//
// O quiz no fim da aula. Aula com quiz só conclui com aprovação: 7
// perguntas, 85% (6 de 7). As duas travas valem — o quiz só abre depois
// do tempo mínimo da aula — e quem reprova espera 10 minutos.
//
// O que a tela NÃO sabe: o gabarito. As alternativas chegam sem `correta`
// e já embaralhadas pelo servidor; o resultado marca quais perguntas
// errou, nunca qual era a certa. A correção, a nota e as esperas são do
// servidor; as contagens daqui são só conforto (o 409/429 manda).
//
// Estados, na ordem em que a pessoa passa por eles:
//   trancado    tempo mínimo da aula correndo
//   respondendo as 7 perguntas, "Enviar" só com todas respondidas
//   esperando   reprovou: resultado + contagem dos 10 minutos
//   aprovado    aula concluída
// Modo leitura (gestão vendo alguém) mostra só o resumo das tentativas.

import { useEffect, useMemo, useState } from 'react';
import {
  CheckCircle2, ClipboardCheck, Lock, RotateCcw, Send, XCircle,
} from 'lucide-react';
import api from '../../api';
import Card, { CardHeader } from '../ui/Card';
import Button from '../ui/Button';
import AlertMessage from '../ui/AlertMessage';
import { mensagemDeErro } from '../crm/tarefaComum';
import { tempoRestante } from './ucComum';

export function resumoDaTentativa(t) {
  if (!t) return '';
  return `${t.acertos} de ${t.total} (${t.nota}%)`;
}

function Resultado({ ultima, quiz }) {
  if (!ultima) return null;
  const numeros = quiz.perguntas
    .filter((p) => ultima.erradas.includes(p.id))
    .map((p) => p.numero);
  return (
    <div
      data-testid="quiz-resultado"
      className={`rounded-lg border px-3 py-2 text-sm ${ultima.aprovada
        ? 'border-hipo-successBorder bg-hipo-successSoft text-hipo-ink'
        : 'border-hipo-dangerBorder bg-hipo-dangerSoft text-hipo-ink'}`}
    >
      <p className="font-medium flex items-center gap-2">
        {ultima.aprovada
          ? <CheckCircle2 size={16} className="text-hipo-success" aria-hidden="true" />
          : <XCircle size={16} className="text-hipo-danger" aria-hidden="true" />}
        {ultima.aprovada ? 'Aprovado' : 'Não foi desta vez'}: você acertou {resumoDaTentativa(ultima)}.
      </p>
      {!ultima.aprovada && (
        <p className="text-hipo-slate mt-1">
          Precisa de {quiz.acertos_para_aprovar} de {quiz.total}.
          {numeros.length > 0 && (
            <> Reveja no texto da aula o assunto {numeros.length === 1 ? 'da pergunta' : 'das perguntas'}{' '}
              <strong className="text-hipo-ink">{numeros.join(', ')}</strong>.</>
          )}
        </p>
      )}
    </div>
  );
}

export default function QuizAula({ aula, faltaAula, onAtualizar, onRecarregar }) {
  const { quiz } = aula;
  const concluida = !!aula.concluida_em;
  const [respostas, setRespostas] = useState({});
  const [enviando, setEnviando] = useState(false);
  const [erro, setErro] = useState('');
  const [espera, setEspera] = useState(quiz.segundos_para_refazer || 0);

  // Tentativa nova = alternativas reembaralhadas: começa em branco.
  useEffect(() => {
    setRespostas({});
    setEspera(quiz.segundos_para_refazer || 0);
  }, [quiz.tentativas, quiz.segundos_para_refazer]);

  useEffect(() => {
    if (espera <= 0) return undefined;
    const t = setInterval(() => setEspera((s) => Math.max(0, s - 1)), 1000);
    return () => clearInterval(t);
  }, [espera > 0]); // eslint-disable-line react-hooks/exhaustive-deps

  const respondidas = useMemo(
    () => quiz.perguntas.filter((p) => respostas[p.id]).length,
    [quiz.perguntas, respostas],
  );
  const erradasAntes = quiz.ultima && !quiz.ultima.aprovada ? quiz.ultima.erradas : [];

  async function enviar() {
    setEnviando(true);
    setErro('');
    try {
      const { data } = await api.post(`/uc/aulas/${aula.id}/quiz`, { respostas });
      onAtualizar(data);
    } catch (e) {
      setErro(mensagemDeErro(e, 'Não foi possível enviar as respostas.'));
      const st = e?.response?.status;
      if (st === 409 || st === 429) onRecarregar();
    } finally {
      setEnviando(false);
    }
  }

  const cabecalho = (
    <CardHeader
      title="Quiz da aula"
      hint={`${quiz.total} perguntas · aprova com ${quiz.acertos_para_aprovar} acertos (${quiz.nota_minima}%)`}
    />
  );

  if (aula.modo_leitura) {
    return (
      <Card data-testid="quiz-aula">
        {cabecalho}
        <p className="text-sm text-hipo-slate">
          {quiz.tentativas === 0
            ? 'A pessoa ainda não respondeu o quiz.'
            : `${quiz.tentativas} tentativa(s). ${quiz.aprovado ? 'Aprovada.' : 'Ainda não aprovada.'}`}
        </p>
        {quiz.ultima && <div className="mt-3"><Resultado ultima={quiz.ultima} quiz={quiz} /></div>}
      </Card>
    );
  }

  if (concluida) {
    return (
      <Card data-testid="quiz-aula">
        {cabecalho}
        {quiz.aprovado
          ? <Resultado ultima={quiz.ultima} quiz={quiz} />
          : <p className="text-sm text-hipo-slate">Você concluiu esta aula antes de ela ter quiz.</p>}
      </Card>
    );
  }

  if (aula.status !== 'publicada') {
    return (
      <Card data-testid="quiz-aula">
        {cabecalho}
        <p className="text-sm text-hipo-slate">Aula em rascunho: o quiz vale depois de publicada.</p>
      </Card>
    );
  }

  if (faltaAula > 0) {
    return (
      <Card data-testid="quiz-aula">
        {cabecalho}
        <p className="text-sm text-hipo-slate flex items-center gap-2">
          <Lock size={16} className="text-hipo-slate" aria-hidden="true" />
          O quiz abre em <strong className="text-hipo-ink">{tempoRestante(faltaAula)}</strong>.
          Aproveite para ler o texto e o material: as perguntas saem dele.
        </p>
      </Card>
    );
  }

  if (espera > 0) {
    return (
      <Card data-testid="quiz-aula">
        {cabecalho}
        <Resultado ultima={quiz.ultima} quiz={quiz} />
        <p className="text-sm text-hipo-slate mt-3">
          Nova tentativa em <strong className="text-hipo-ink">{tempoRestante(espera)}</strong>.
          As alternativas vêm em outra ordem.
        </p>
      </Card>
    );
  }

  return (
    <Card data-testid="quiz-aula">
      {cabecalho}
      {quiz.ultima && !quiz.ultima.aprovada && (
        <div className="mb-4">
          <Resultado ultima={quiz.ultima} quiz={quiz} />
        </div>
      )}
      <ol className="space-y-5">
        {quiz.perguntas.map((p) => (
          <li key={p.id}>
            <fieldset>
              <legend className="text-sm font-medium text-hipo-ink">
                {p.numero}. {p.enunciado}
                {erradasAntes.includes(p.id) && (
                  <span className="ml-2 text-xs font-normal text-hipo-danger">errou na última tentativa</span>
                )}
              </legend>
              <div className="mt-2 space-y-1.5">
                {p.alternativas.map((a) => (
                  <label
                    key={a.id}
                    className={`flex items-start gap-2 rounded-lg border px-3 py-2 text-sm cursor-pointer ${respostas[p.id] === a.id
                      ? 'border-hipo-blue bg-hipo-blueSoft text-hipo-ink'
                      : 'border-hipo-border hover:bg-hipo-bg text-hipo-ink'}`}
                  >
                    <input
                      type="radio"
                      name={`pergunta-${p.id}`}
                      value={a.id}
                      checked={respostas[p.id] === a.id}
                      onChange={() => setRespostas((r) => ({ ...r, [p.id]: a.id }))}
                      className="mt-0.5"
                    />
                    <span>{a.texto}</span>
                  </label>
                ))}
              </div>
            </fieldset>
          </li>
        ))}
      </ol>
      {erro && <AlertMessage tipo="erro" className="mt-3">{erro}</AlertMessage>}
      <div className="mt-4 flex flex-col sm:flex-row sm:items-center gap-3">
        <p className="text-xs text-hipo-slate flex-1">
          <ClipboardCheck size={13} className="inline mr-1" aria-hidden="true" />
          {respondidas} de {quiz.total} respondidas
          {quiz.tentativas > 0 && ` · tentativa ${quiz.tentativas + 1}`}
        </p>
        <Button
          icon={quiz.tentativas > 0 ? RotateCcw : Send}
          onClick={enviar}
          loading={enviando}
          disabled={respondidas < quiz.total}
        >
          Enviar respostas
        </Button>
      </div>
    </Card>
  );
}
