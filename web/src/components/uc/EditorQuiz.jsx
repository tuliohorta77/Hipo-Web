// web/src/components/uc/EditorQuiz.jsx
//
// Estúdio da UC: o quiz da aula. Nenhuma pergunta (a aula conclui pelo
// "Concluí" com a trava de tempo) ou exatamente 7, cada uma com 3 a 5
// alternativas e uma correta. Aprova com 85% (6 de 7).
//
// Salva o quiz inteiro de uma vez (PUT), separado do "Salvar" da aula: é
// outra rota, e um erro no quiz não pode segurar a correção do texto. A
// regra que vale é a do servidor; o que a tela confere aqui é só para não
// mandar o óbvio errado.

import { useEffect, useState } from 'react';
import { ClipboardList, Plus, Trash2, X } from 'lucide-react';
import api from '../../api';
import Button from '../ui/Button';
import AlertMessage from '../ui/AlertMessage';
import { mensagemDeErro } from '../crm/tarefaComum';

export const PERGUNTAS_POR_QUIZ = 7;
const ALT_MIN = 3;
const ALT_MAX = 5;

function perguntaVazia() {
  return { enunciado: '', alternativas: Array.from({ length: 4 }, (_, k) => ({ texto: '', correta: k === 0 })) };
}

export function quizEmBranco() {
  return Array.from({ length: PERGUNTAS_POR_QUIZ }, perguntaVazia);
}

/** O que falta para o quiz poder ser salvo; '' = pronto. */
export function problemaDoQuiz(perguntas) {
  if (perguntas.length !== PERGUNTAS_POR_QUIZ) return `O quiz precisa de ${PERGUNTAS_POR_QUIZ} perguntas.`;
  for (let i = 0; i < perguntas.length; i += 1) {
    const p = perguntas[i];
    if (!p.enunciado.trim()) return `Pergunta ${i + 1}: escreva o enunciado.`;
    if (p.alternativas.some((a) => !a.texto.trim())) return `Pergunta ${i + 1}: preencha todas as alternativas.`;
    if (p.alternativas.filter((a) => a.correta).length !== 1) return `Pergunta ${i + 1}: marque a alternativa correta.`;
  }
  return '';
}

export default function EditorQuiz({ aula, onSalvo }) {
  const [perguntas, setPerguntas] = useState(aula.quiz || []);
  const [salvando, setSalvando] = useState(false);
  const [erro, setErro] = useState('');
  const [ok, setOk] = useState('');

  useEffect(() => { setPerguntas(aula.quiz || []); setErro(''); setOk(''); }, [aula.id]); // eslint-disable-line react-hooks/exhaustive-deps

  function mudar(i, fn) {
    setOk('');
    setPerguntas((ps) => ps.map((p, j) => (j === i ? fn(p) : p)));
  }

  async function gravar(lista) {
    setSalvando(true);
    setErro('');
    setOk('');
    try {
      const { data } = await api.put(`/uc/estudio/aulas/${aula.id}/quiz`, { perguntas: lista });
      setPerguntas(data.quiz);
      setOk(data.quiz.length ? 'Quiz salvo.' : 'Quiz removido: a aula volta a concluir pelo tempo.');
      onSalvo?.(data);
    } catch (e) {
      setErro(mensagemDeErro(e, 'Não foi possível salvar o quiz.'));
    } finally {
      setSalvando(false);
    }
  }

  function salvar() {
    const problema = problemaDoQuiz(perguntas);
    if (problema) { setErro(problema); return; }
    gravar(perguntas);
  }

  return (
    <div data-testid="editor-quiz">
      <div className="flex items-center justify-between mb-1.5">
        <p className="text-sm font-medium text-hipo-ink">Quiz</p>
        {perguntas.length > 0 && (
          <div className="flex gap-2">
            <Button size="sm" variant="ghost" icon={Trash2} onClick={() => gravar([])} disabled={salvando}>
              Remover quiz
            </Button>
            <Button size="sm" onClick={salvar} loading={salvando}>Salvar quiz</Button>
          </div>
        )}
      </div>
      {erro && <AlertMessage tipo="erro" className="mb-2">{erro}</AlertMessage>}
      {ok && <AlertMessage tipo="ok" className="mb-2">{ok}</AlertMessage>}

      {perguntas.length === 0 ? (
        <div className="text-xs text-hipo-slate flex flex-col sm:flex-row sm:items-center gap-2">
          <span className="flex-1">
            Sem quiz, a aula conclui pelo botão Concluí depois da metade da duração. Com quiz, só
            conclui com {PERGUNTAS_POR_QUIZ} perguntas e 85% de acerto (6 de 7), e o quiz abre depois do mesmo tempo.
          </span>
          <Button size="sm" variant="secondary" icon={ClipboardList} onClick={() => setPerguntas(quizEmBranco())}>
            Criar quiz
          </Button>
        </div>
      ) : (
        <ol className="space-y-4">
          {perguntas.map((p, i) => (
            <li key={i} className="border border-hipo-border rounded-lg p-3">
              <label className="block text-xs font-medium text-hipo-slate mb-1" htmlFor={`quiz-p${i}`}>
                Pergunta {i + 1}
              </label>
              <input
                id={`quiz-p${i}`}
                className="w-full h-9 rounded-lg border border-hipo-border bg-hipo-card px-2 text-sm text-hipo-ink"
                value={p.enunciado}
                maxLength={300}
                onChange={(e) => mudar(i, (x) => ({ ...x, enunciado: e.target.value }))}
              />
              <div className="mt-2 space-y-1.5">
                {p.alternativas.map((a, k) => (
                  <div key={k} className="flex items-center gap-2">
                    <input
                      type="radio"
                      name={`quiz-certa-${i}`}
                      aria-label={`Pergunta ${i + 1}: alternativa ${k + 1} é a correta`}
                      checked={a.correta}
                      onChange={() => mudar(i, (x) => ({
                        ...x, alternativas: x.alternativas.map((y, z) => ({ ...y, correta: z === k })),
                      }))}
                    />
                    <input
                      aria-label={`Pergunta ${i + 1}, alternativa ${k + 1}`}
                      className="flex-1 h-8 rounded-lg border border-hipo-border bg-hipo-card px-2 text-sm text-hipo-ink"
                      value={a.texto}
                      maxLength={200}
                      onChange={(e) => mudar(i, (x) => ({
                        ...x, alternativas: x.alternativas.map((y, z) => (z === k ? { ...y, texto: e.target.value } : y)),
                      }))}
                    />
                    {p.alternativas.length > ALT_MIN && (
                      <button
                        type="button"
                        aria-label={`Tirar a alternativa ${k + 1} da pergunta ${i + 1}`}
                        className="p-1 text-hipo-slate hover:text-hipo-danger"
                        onClick={() => mudar(i, (x) => {
                          const resto = x.alternativas.filter((_, z) => z !== k);
                          if (!resto.some((y) => y.correta)) resto[0] = { ...resto[0], correta: true };
                          return { ...x, alternativas: resto };
                        })}
                      >
                        <X size={14} />
                      </button>
                    )}
                  </div>
                ))}
              </div>
              {p.alternativas.length < ALT_MAX && (
                <button
                  type="button"
                  className="mt-2 text-xs text-hipo-blue hover:underline inline-flex items-center gap-1"
                  onClick={() => mudar(i, (x) => ({ ...x, alternativas: [...x.alternativas, { texto: '', correta: false }] }))}
                >
                  <Plus size={12} /> alternativa
                </button>
              )}
            </li>
          ))}
        </ol>
      )}
    </div>
  );
}
