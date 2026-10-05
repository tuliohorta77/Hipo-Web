// web/src/pages/uc/QuizTrilha.jsx
//
// O quiz final da trilha, numa tela só dele: sem o texto das aulas ao
// lado. Abre quando todas as aulas da trilha estão concluídas; sorteia 10
// perguntas do banco das aulas e aprova com 85% (9 de 10). A trilha só
// fica concluída com a aprovação.
//
// O que a tela NÃO sabe: o gabarito. As perguntas chegam sem `correta`,
// com as alternativas já embaralhadas pelo servidor; o resultado diz quais
// perguntas errou e de qual aula, nunca qual era a certa. Correção, nota e
// esperas são do servidor (409/429 mandam); as contagens daqui são conforto.
//
// Estados: trancado (faltam aulas) · respondendo · esperando (reprovou,
// 10 min) · aprovado. Modo leitura (gestão vendo alguém): só o resumo.

import { useCallback, useEffect, useMemo, useState } from 'react';
import { useNavigate, useParams, useSearchParams } from 'react-router-dom';
import {
  ArrowLeft, CheckCircle2, ClipboardCheck, Lock, RotateCcw, Send, Trophy, XCircle,
} from 'lucide-react';
import api from '../../api';
import PageHeader from '../../components/ui/PageHeader';
import Card from '../../components/ui/Card';
import Badge from '../../components/ui/Badge';
import Button from '../../components/ui/Button';
import AlertMessage from '../../components/ui/AlertMessage';
import { mensagemDeErro } from '../../components/crm/tarefaComum';
import { tempoRestante, tomDoPilar } from '../../components/uc/ucComum';

export function aulasParaRever(erradas) {
  const vistas = new Map();
  for (const e of erradas || []) {
    if (!vistas.has(e.aula_ordem)) vistas.set(e.aula_ordem, { ...e, perguntas: [] });
    vistas.get(e.aula_ordem).perguntas.push(e.numero);
  }
  return [...vistas.values()].sort((a, b) => a.aula_ordem - b.aula_ordem);
}

function Resultado({ quiz }) {
  const u = quiz.ultima;
  if (!u) return null;
  const rever = aulasParaRever(u.erradas);
  return (
    <div
      data-testid="quiz-resultado"
      className={`rounded-lg border px-4 py-3 text-sm ${u.aprovada
        ? 'border-hipo-successBorder bg-hipo-successSoft'
        : 'border-hipo-dangerBorder bg-hipo-dangerSoft'} text-hipo-ink`}
    >
      <p className="font-medium flex items-center gap-2">
        {u.aprovada
          ? <CheckCircle2 size={16} className="text-hipo-success" aria-hidden="true" />
          : <XCircle size={16} className="text-hipo-danger" aria-hidden="true" />}
        {u.aprovada ? 'Aprovado' : 'Não foi desta vez'}: você acertou {u.acertos} de {u.total} ({u.nota}%).
      </p>
      {!u.aprovada && (
        <>
          <p className="text-hipo-slate mt-1">Precisa de {quiz.acertos_para_aprovar} de {quiz.total}. Reveja:</p>
          <ul className="mt-1 space-y-0.5">
            {rever.map((a) => (
              <li key={a.aula_ordem}>
                <strong>Aula {a.aula_ordem}. {a.aula_titulo}</strong>
                <span className="text-hipo-slate"> · pergunta{a.perguntas.length > 1 ? 's' : ''} {a.perguntas.join(', ')}</span>
              </li>
            ))}
          </ul>
        </>
      )}
    </div>
  );
}

export default function QuizTrilha() {
  const { trilhaId } = useParams();
  const [params] = useSearchParams();
  const usuarioId = params.get('usuario_id');
  const sufixo = usuarioId ? `?usuario_id=${usuarioId}` : '';
  const navigate = useNavigate();

  const [quiz, setQuiz] = useState(null);
  const [erro, setErro] = useState('');
  const [erroEnvio, setErroEnvio] = useState('');
  const [respostas, setRespostas] = useState({});
  const [enviando, setEnviando] = useState(false);
  const [espera, setEspera] = useState(0);

  const carregar = useCallback(async () => {
    setErro('');
    try {
      const { data } = await api.get(`/uc/trilhas/${trilhaId}/quiz`, {
        params: usuarioId ? { usuario_id: usuarioId } : undefined,
      });
      setQuiz(data);
      setRespostas({});
      setEspera(data.segundos_para_refazer || 0);
    } catch (e) {
      setErro(mensagemDeErro(e, 'Não foi possível abrir o quiz.'));
    }
  }, [trilhaId, usuarioId]);

  useEffect(() => { carregar(); }, [carregar]);

  useEffect(() => {
    if (espera <= 0) return undefined;
    const t = setInterval(() => setEspera((s) => Math.max(0, s - 1)), 1000);
    return () => clearInterval(t);
  }, [espera > 0]); // eslint-disable-line react-hooks/exhaustive-deps

  const respondidas = useMemo(
    () => (quiz?.perguntas || []).filter((p) => respostas[p.id]).length,
    [quiz, respostas],
  );

  async function enviar() {
    setEnviando(true);
    setErroEnvio('');
    try {
      const { data } = await api.post(`/uc/trilhas/${trilhaId}/quiz`, { respostas });
      setQuiz(data);
      setRespostas({});
      setEspera(data.segundos_para_refazer || 0);
    } catch (e) {
      setErroEnvio(mensagemDeErro(e, 'Não foi possível enviar as respostas.'));
      const st = e?.response?.status;
      if (st === 409 || st === 429) carregar();
    } finally {
      setEnviando(false);
    }
  }

  const voltar = (
    <Button variant="ghost" icon={ArrowLeft} onClick={() => navigate(`/uc/trilhas/${trilhaId}${sufixo}`)}>
      Trilha
    </Button>
  );

  if (erro && !quiz) {
    return (
      <div className="max-w-3xl mx-auto">
        <PageHeader title="Quiz final" actions={voltar} />
        <AlertMessage tipo="erro">{erro}</AlertMessage>
      </div>
    );
  }
  if (!quiz) return <p className="text-sm text-hipo-slate p-4">Carregando…</p>;

  const regra = `${quiz.total} perguntas sorteadas das aulas · aprova com ${quiz.acertos_para_aprovar} acertos (${quiz.nota_minima}%)`;

  let corpo;
  if (quiz.modo_leitura) {
    corpo = (
      <Card>
        <p className="text-sm text-hipo-slate">
          {quiz.tentativas === 0
            ? 'A pessoa ainda não fez o quiz.'
            : `${quiz.tentativas} tentativa(s). ${quiz.aprovado ? 'Aprovada.' : 'Ainda não aprovada.'}`}
        </p>
        {quiz.ultima && <div className="mt-3"><Resultado quiz={quiz} /></div>}
      </Card>
    );
  } else if (quiz.aprovado) {
    corpo = (
      <Card>
        <div className="flex flex-col items-center text-center gap-3 py-4">
          <div className="w-12 h-12 rounded-full bg-hipo-successSoft text-hipo-success flex items-center justify-center">
            <Trophy size={22} aria-hidden="true" />
          </div>
          <p className="text-lg font-semibold text-hipo-ink">Trilha concluída</p>
          {quiz.ultima?.aprovada && <Resultado quiz={quiz} />}
          <Button onClick={() => navigate('/uc')}>Voltar para a Universidade</Button>
        </div>
      </Card>
    );
  } else if (!quiz.liberado) {
    corpo = (
      <Card>
        <p className="text-sm text-hipo-slate flex items-center gap-2">
          <Lock size={16} aria-hidden="true" />
          O quiz abre quando você concluir {quiz.aulas_pendentes === 1 ? 'a aula que falta' : `as ${quiz.aulas_pendentes} aulas que faltam`} da trilha.
        </p>
        <Button className="mt-4" variant="secondary" onClick={() => navigate(`/uc/trilhas/${trilhaId}`)}>
          Ver as aulas
        </Button>
      </Card>
    );
  } else if (espera > 0) {
    corpo = (
      <Card>
        <Resultado quiz={quiz} />
        <p className="text-sm text-hipo-slate mt-4">
          Nova tentativa em <strong className="text-hipo-ink">{tempoRestante(espera)}</strong>, com outras
          perguntas. Aproveite para rever as aulas acima.
        </p>
        <Button className="mt-3" variant="secondary" icon={RotateCcw} disabled>
          Tentar de novo
        </Button>
      </Card>
    );
  } else if (quiz.perguntas.length === 0) {
    // A espera acabou aqui na tela: busca o sorteio novo.
    corpo = (
      <Card>
        {quiz.ultima && <Resultado quiz={quiz} />}
        <Button className="mt-4" icon={RotateCcw} onClick={carregar}>Tentar de novo</Button>
      </Card>
    );
  } else {
    corpo = (
      <>
        {quiz.ultima && !quiz.ultima.aprovada && <Resultado quiz={quiz} />}
        <ol className="space-y-4">
          {quiz.perguntas.map((p) => (
            <li key={p.id}>
              <Card>
                <fieldset>
                  <legend className="text-sm font-medium text-hipo-ink">
                    {p.numero}. {p.enunciado}
                  </legend>
                  <div className="mt-3 space-y-1.5">
                    {p.alternativas.map((a) => (
                      <label
                        key={a.id}
                        className={`flex items-start gap-2 rounded-lg border px-3 py-2 text-sm cursor-pointer ${respostas[p.id] === a.id
                          ? 'border-hipo-blue bg-hipo-blueSoft'
                          : 'border-hipo-border hover:bg-hipo-bg'} text-hipo-ink`}
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
              </Card>
            </li>
          ))}
        </ol>
        {erroEnvio && <AlertMessage tipo="erro">{erroEnvio}</AlertMessage>}
        <Card>
          <div className="flex flex-col sm:flex-row sm:items-center gap-3">
            <p className="text-sm text-hipo-slate flex-1">
              <ClipboardCheck size={14} className="inline mr-1" aria-hidden="true" />
              {respondidas} de {quiz.total} respondidas
              {quiz.tentativas > 0 && ` · tentativa ${quiz.tentativas + 1}`}
            </p>
            <Button icon={Send} onClick={enviar} loading={enviando} disabled={respondidas < quiz.total}>
              Enviar respostas
            </Button>
          </div>
        </Card>
      </>
    );
  }

  return (
    <div className="max-w-3xl mx-auto space-y-4" data-testid="quiz-trilha">
      <PageHeader title="Quiz final" subtitle={quiz.trilha_titulo} actions={voltar} />
      <div className="flex flex-wrap items-center gap-2">
        <Badge tone={tomDoPilar(quiz.pilar).badge}>{quiz.pilar_rotulo}</Badge>
        {quiz.modo_leitura && <Badge tone="info">Modo leitura</Badge>}
        <span className="text-xs text-hipo-slate">{regra}</span>
      </div>
      {corpo}
    </div>
  );
}

