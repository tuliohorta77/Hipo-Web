// web/src/tests/EditorQuiz.test.jsx
//
// O quiz no estúdio. O que estes testes seguram:
//   1. aula sem quiz oferece "Criar quiz", que abre 7 perguntas em branco
//   2. em branco não vai para a API: a tela diz o que falta
//   3. preenchido, vai inteiro num PUT, com a correta marcada
//   4. "Remover quiz" manda lista vazia
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
    expect(problemaDoQuiz(quizEmBranco().slice(0, 3))).toMatch(/precisa de 7/);
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
    fireEvent.click(screen.getByRole('button', { name: /Criar quiz/ }));
    expect(screen.getAllByText(/^Pergunta \d$/)).toHaveLength(7);
    fireEvent.click(screen.getByRole('button', { name: /Salvar quiz/ }));
    expect(screen.getByText('Pergunta 1: escreva o enunciado.')).toBeInTheDocument();
    expect(mockPut).not.toHaveBeenCalled();
  });

  it('preenchido vai inteiro num PUT com a correta', async () => {
    const onSalvo = vi.fn();
    mockPut.mockResolvedValue({ data: { quiz: quizPronto(), nota_minima: 85 } });
    render(<EditorQuiz aula={{ id: 'a1', quiz: [] }} onSalvo={onSalvo} />);
    fireEvent.click(screen.getByRole('button', { name: /Criar quiz/ }));
    for (let i = 1; i <= 7; i += 1) {
      fireEvent.change(screen.getByLabelText(`Pergunta ${i}`), { target: { value: `P${i}?` } });
      for (let k = 1; k <= 4; k += 1) {
        fireEvent.change(screen.getByLabelText(`Pergunta ${i}, alternativa ${k}`), { target: { value: `R${i}.${k}` } });
      }
      fireEvent.click(screen.getByLabelText(`Pergunta ${i}: alternativa 3 é a correta`));
    }
    fireEvent.click(screen.getByRole('button', { name: /Salvar quiz/ }));
    expect(await screen.findByText('Quiz salvo.')).toBeInTheDocument();
    const [url, corpo] = mockPut.mock.calls[0];
    expect(url).toBe('/uc/estudio/aulas/a1/quiz');
    expect(corpo.perguntas).toHaveLength(7);
    expect(corpo.perguntas[0].alternativas.map((a) => a.correta)).toEqual([false, false, true, false]);
    expect(onSalvo).toHaveBeenCalled();
  });

  it('remover manda lista vazia', async () => {
    mockPut.mockResolvedValue({ data: { quiz: [], nota_minima: 85 } });
    render(<EditorQuiz aula={{ id: 'a1', quiz: quizPronto() }} />);
    fireEvent.click(screen.getByRole('button', { name: /Remover quiz/ }));
    expect(await screen.findByText(/Quiz removido/)).toBeInTheDocument();
    expect(mockPut).toHaveBeenCalledWith('/uc/estudio/aulas/a1/quiz', { perguntas: [] });
  });

  it('o 422 do servidor aparece', async () => {
    mockPut.mockRejectedValue(erroHttp(422, 'Pergunta 2: alternativas repetidas.'));
    render(<EditorQuiz aula={{ id: 'a1', quiz: quizPronto() }} />);
    fireEvent.click(screen.getByRole('button', { name: /Salvar quiz/ }));
    expect(await screen.findByText('Pergunta 2: alternativas repetidas.')).toBeInTheDocument();
  });

  it('tirar alternativa mantém uma correta e respeita o mínimo de 3', () => {
    render(<EditorQuiz aula={{ id: 'a1', quiz: [] }} />);
    fireEvent.click(screen.getByRole('button', { name: /Criar quiz/ }));
    fireEvent.click(screen.getByLabelText('Tirar a alternativa 1 da pergunta 1'));
    expect(screen.getByLabelText('Pergunta 1: alternativa 1 é a correta')).toBeChecked();
    expect(screen.queryByLabelText('Tirar a alternativa 1 da pergunta 1')).toBeNull();
  });
});
