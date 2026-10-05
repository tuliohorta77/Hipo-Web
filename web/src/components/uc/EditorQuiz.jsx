// web/src/components/uc/EditorQuiz.jsx
//
// Estúdio da UC: as perguntas da aula. São o BANCO de onde o quiz final da
// trilha sorteia 10 perguntas (aprova com 85%). De 0 a 10 por aula, cada
// uma com 3 a 5 alternativas e uma correta. A aula em si conclui pela
// trava de tempo, com ou sem perguntas.
//
// Salva o banco inteiro de uma vez (PUT), separado do "Salvar" da aula: é
// outra rota, e um erro aqui não pode segurar a correção do texto. A
// regra que vale é a do servidor; o que a tela confere aqui é só para não
// mandar o óbvio errado.

import { useEffect, useState } from 'react';
import { ClipboardList, Plus, Trash2, X } from 'lucide-react';
import api from '../../api';
import Button from '../ui/Button';
import AlertMessage from '../ui/AlertMessage';
import { mensagemDeErro } from '../crm/tarefaComum';

export const PERGUNTAS_POR_QUIZ = 7;   // sugestão ao começar
export const MAX_PERGUNTAS = 10;
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
  if (perguntas.length > MAX_PERGUNTAS) return `O banco vai até ${MAX_PERGUNTAS} perguntas por aula.`;
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
      setOk(data.quiz.length ? 'Perguntas salvas.' : 'Perguntas removidas: a aula sai do sorteio do quiz final.');
      onSalvo?.(data);
    } catch (e) {
      setErro(mensagemDeErro(e, 'Não foi possível salvar as perguntas.'));
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
        <p className="text-sm font-medium text-hipo-ink">Perguntas para o quiz final</p>
        {perguntas.length > 0 && (
          <div className="flex gap-2">
            <Button size="sm" variant="ghost" icon={Trash2} onClick={() => gravar([])} disabled={salvando}>
              Remover todas
            </Button>
            <Button size="sm" onClick={salvar} loading={salvando}>Salvar perguntas</Button>
          </div>
        )}
      </div>
      {erro && <AlertMessage tipo="erro" className="mb-2">{erro}</AlertMessage>}
      {ok && <AlertMessage tipo="ok" className="mb-2">{ok}</AlertMessage>}

      {perguntas.length === 0 ? (
        <div className="text-xs text-hipo-slate flex flex-col sm:flex-row sm:items-center gap-2">
          <span className="flex-1">
            O quiz é um só, no final da trilha: sorteia 10 perguntas das aulas e aprova com 85%.
            Sem perguntas, esta aula fica fora do sorteio. A aula conclui pelo botão Concluí,
            depois da metade da duração.
          </span>
          <Button size="sm" variant="secondary" icon={ClipboardList} onClick={() => setPerguntas(quizEmBranco())}>
            Escrever perguntas
          </Button>
        </div>
      ) : (
        <ol className="space-y-4">
          {perguntas.map((p, i) => (
            <li key={i} className="border border-hipo-border rounded-lg p-3">
              <div className="flex items-center justify-between mb-1">
                <label className="block text-xs font-medium text-hipo-slate" htmlFor={`quiz-p${i}`}>
                  Pergunta {i + 1}
                </label>
                <button
                  type="button"
                  aria-label={`Tirar a pergunta ${i + 1}`}
                  className="p-1 text-hipo-slate hover:text-hipo-danger"
                  onClick={() => { setOk(''); setPerguntas((ps) => ps.filter((_, j) => j !== i)); }}
                >
                  <Trash2 size={14} />
                </button>
              </div>
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
          {perguntas.length < MAX_PERGUNTAS && (
            <li>
              <Button
                size="sm"
                variant="secondary"
                icon={Plus}
                onClick={() => { setOk(''); setPerguntas((ps) => [...ps, perguntaVazia()]); }}
              >
                Pergunta
              </Button>
            </li>
          )}
        </ol>
      )}
    </div>
  );
}
