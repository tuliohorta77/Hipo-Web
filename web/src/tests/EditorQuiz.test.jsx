// web/src/tests/EditorQuiz.test.jsx
//
// As perguntas da aula no estúdio (banco do quiz final da trilha):
//   1. aula sem perguntas oferece "Escrever perguntas", que abre 7 em branco
//   2. em branco não vai para a API: a tela diz o que falta
//   3. preenchido, vai inteiro num PUT, com a correta marcada
//   4. "Remover todas" manda lista vazia; dá para tirar e pôr pergunta
//   5. o 422 do servidor aparece como veio
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, fireEvent, cleanup } from '@testing-library/react';

const mockPut = vi.fn();
vi.mock('../api', () => ({ default: { put: (...a) => mockPut(...a) } }));

import EditorQuiz, { problemaDoQuiz, quizEmBranco } from '../components/uc/EditorQuiz';

function quizPronto() {
  return quizEmBranco().map((p, i) => ({
    enunciado: `P${i + 1}?`,
    alternativas: p.alternativas.map((a, k) => ({ texto: `R${i + 1}.${k}`, correta: k === 2 })),
  }));
}

function erroHttp(status, detail) {
  return Object.assign(new Error(`HTTP ${status}`), { response: { status, data: { detail } } });
}

beforeEach(() => { mockPut.mockReset(); });
afterEach(cleanup);

describe('problemaDoQuiz', () => {
  it('aponta a primeira coisa que falta', () => {
    expect(problemaDoQuiz([...quizEmBranco(), ...quizEmBranco()])).toMatch(/vai até 10/);
    expect(problemaDoQuiz(quizPronto().slice(0, 3))).toBe('');
    expect(problemaDoQuiz(quizEmBranco())).toBe('Pergunta 1: escreva o enunciado.');
    const q = quizPronto();
    q[4].alternativas[1].texto = ' ';
    expect(problemaDoQuiz(q)).toBe('Pergunta 5: preencha todas as alternativas.');
    expect(problemaDoQuiz(quizPronto())).toBe('');
  });
});

describe('EditorQuiz', () => {
  it('cria em branco e não salva vazio', () => {
    render(<EditorQuiz aula={{ id: 'a1', quiz: [] }} />);
    fireEvent.click(screen.getByRole('button', { name: /Escrever perguntas/ }));
    expect(screen.getAllByText(/^Pergunta \d$/)).toHaveLength(7);
    fireEvent.click(screen.getByRole('button', { name: /Salvar perguntas/ }));
    expect(screen.getByText('Pergunta 1: escreva o enunciado.')).toBeInTheDocument();
    expect(mockPut).not.toHaveBeenCalled();
  });

  it('preenchido vai inteiro num PUT com a correta', async () => {
    const onSalvo = vi.fn();
    mockPut.mockResolvedValue({ data: { quiz: quizPronto(), nota_minima: 85 } });
    render(<EditorQuiz aula={{ id: 'a1', quiz: [] }} onSalvo={onSalvo} />);
    fireEvent.click(screen.getByRole('button', { name: /Escrever perguntas/ }));
    for (let i = 1; i <= 7; i += 1) {
      fireEvent.change(screen.getByLabelText(`Pergunta ${i}`), { target: { value: `P${i}?` } });
      for (let k = 1; k <= 4; k += 1) {
        fireEvent.change(screen.getByLabelText(`Pergunta ${i}, alternativa ${k}`), { target: { value: `R${i}.${k}` } });
      }
      fireEvent.click(screen.getByLabelText(`Pergunta ${i}: alternativa 3 é a correta`));
    }
    fireEvent.click(screen.getByRole('button', { name: /Salvar perguntas/ }));
    expect(await screen.findByText('Perguntas salvas.')).toBeInTheDocument();
    const [url, corpo] = mockPut.mock.calls[0];
    expect(url).toBe('/uc/estudio/aulas/a1/quiz');
    expect(corpo.perguntas).toHaveLength(7);
    expect(corpo.perguntas[0].alternativas.map((a) => a.correta)).toEqual([false, false, true, false]);
    expect(onSalvo).toHaveBeenCalled();
  });

  it('remover manda lista vazia', async () => {
    mockPut.mockResolvedValue({ data: { quiz: [], nota_minima: 85 } });
    render(<EditorQuiz aula={{ id: 'a1', quiz: quizPronto() }} />);
    fireEvent.click(screen.getByRole('button', { name: /Remover todas/ }));
    expect(await screen.findByText(/Perguntas removidas/)).toBeInTheDocument();
    expect(mockPut).toHaveBeenCalledWith('/uc/estudio/aulas/a1/quiz', { perguntas: [] });
  });

  it('o 422 do servidor aparece', async () => {
    mockPut.mockRejectedValue(erroHttp(422, 'Pergunta 2: alternativas repetidas.'));
    render(<EditorQuiz aula={{ id: 'a1', quiz: quizPronto() }} />);
    fireEvent.click(screen.getByRole('button', { name: /Salvar perguntas/ }));
    expect(await screen.findByText('Pergunta 2: alternativas repetidas.')).toBeInTheDocument();
  });

  it('tira e põe pergunta', () => {
    render(<EditorQuiz aula={{ id: 'a1', quiz: [] }} />);
    fireEvent.click(screen.getByRole('button', { name: /Escrever perguntas/ }));
    fireEvent.click(screen.getByLabelText('Tirar a pergunta 7'));
    expect(screen.getAllByText(/^Pergunta \d$/)).toHaveLength(6);
    fireEvent.click(screen.getByRole('button', { name: /^Pergunta$/ }));
    expect(screen.getAllByText(/^Pergunta \d+$/)).toHaveLength(7);
  });

  it('tirar alternativa mantém uma correta e respeita o mínimo de 3', () => {
    render(<EditorQuiz aula={{ id: 'a1', quiz: [] }} />);
    fireEvent.click(screen.getByRole('button', { name: /Escrever perguntas/ }));
    fireEvent.click(screen.getByLabelText('Tirar a alternativa 1 da pergunta 1'));
    expect(screen.getByLabelText('Pergunta 1: alternativa 1 é a correta')).toBeChecked();
    expect(screen.queryByLabelText('Tirar a alternativa 1 da pergunta 1')).toBeNull();
  });
});
