// web/src/tests/QuizTrilha.test.jsx
//
// O quiz final da trilha, na tela própria. O que estes testes seguram:
//   1. trancado enquanto faltam aulas
//   2. "Enviar" só com as 10 respondidas; manda {pergunta: alternativa}
//   3. reprovado: placar, as perguntas erradas (enunciado + o que marcou,
//      sem gabarito) agrupadas por aula, com a espera
//   4. aprovado: trilha concluída
//   5. o 429 do servidor aparece e a tela recarrega
//   6. modo leitura: só o resumo
//   7. a aula oferece "Fazer o quiz final" quando a trilha libera
//   8. a trilha mostra o quiz como última linha
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, fireEvent, cleanup } from '@testing-library/react';
import { MemoryRouter, Route, Routes } from 'react-router-dom';

const mockGet = vi.fn();
const mockPost = vi.fn();
vi.mock('../api', () => ({
  default: { get: (...a) => mockGet(...a), post: (...a) => mockPost(...a) },
  getUser: () => null,
  getModulos: () => ['perfil', 'crm'],
}));

import QuizTrilha, { aulasParaRever } from '../pages/uc/QuizTrilha';
import Aula from '../pages/uc/Aula';
import Trilha from '../pages/uc/Trilha';

function quiz(extra = {}) {
  return {
    trilha_id: 't1', trilha_titulo: 'HIPO - SDR', pilar: 'metodo', pilar_rotulo: 'Método',
    total: 10, nota_minima: 85, acertos_para_aprovar: 9, tentativas: 0, aprovado: false,
    aprovado_em: null, liberado: true, aulas_pendentes: 0, ultima: null,
    segundos_para_refazer: 0, espera_minutos: 10, modo_leitura: false,
    perguntas: Array.from({ length: 10 }, (_, i) => ({
      id: `p${i + 1}`, numero: i + 1, enunciado: `Pergunta ${i + 1}?`,
      alternativas: [0, 1, 2, 3].map((k) => ({ id: `p${i + 1}a${k}`, texto: `Opção ${i + 1}.${k}` })),
    })),
    ...extra,
  };
}

const REPROVADA = {
  acertos: 8, total: 10, nota: 80, aprovada: false, em: '2026-10-05T10:00:00Z',
  erradas: [
    { numero: 2, aula_ordem: 1, aula_titulo: 'O HIPO no dia do SDR', enunciado: 'Onde fica a próxima tarefa?', sua_resposta: 'No relatório' },
    { numero: 7, aula_ordem: 4, aula_titulo: 'Oportunidades', enunciado: 'Quando a fase muda?', sua_resposta: 'No fim do mês' },
  ],
};

function renderizar(caminho = '/uc/trilhas/t1/quiz') {
  return render(
    <MemoryRouter initialEntries={[caminho]}>
      <Routes>
        <Route path="/uc/trilhas/:trilhaId/quiz" element={<QuizTrilha />} />
        <Route path="/uc/trilhas/:trilhaId" element={<Trilha />} />
        <Route path="/uc/aulas/:aulaId" element={<Aula />} />
        <Route path="/uc" element={<p>tela da UC</p>} />
      </Routes>
    </MemoryRouter>,
  );
}

function erroHttp(status, detail) {
  return Object.assign(new Error(`HTTP ${status}`), { response: { status, data: { detail } } });
}

function responder(ate = 10) {
  for (let i = 1; i <= ate; i += 1) fireEvent.click(screen.getByLabelText(`Opção ${i}.1`));
}

beforeEach(() => { mockGet.mockReset(); mockPost.mockReset(); });
afterEach(cleanup);

describe('aulasParaRever', () => {
  it('agrupa as erradas por aula, na ordem da trilha', () => {
    const r = aulasParaRever([
      { numero: 9, aula_ordem: 3, aula_titulo: 'C' },
      { numero: 1, aula_ordem: 1, aula_titulo: 'A' },
      { numero: 2, aula_ordem: 1, aula_titulo: 'A' },
    ]);
    expect(r.map((a) => [a.aula_ordem, a.perguntas.map((e) => e.numero)])).toEqual([[1, [1, 2]], [3, [9]]]);
  });
});

describe('Quiz final da trilha', () => {
  it('trancado enquanto faltam aulas', async () => {
    mockGet.mockResolvedValue({ data: quiz({ liberado: false, aulas_pendentes: 3, perguntas: [] }) });
    renderizar();
    expect(await screen.findByText(/concluir as 3 aulas que faltam/)).toBeInTheDocument();
    expect(screen.queryByRole('radio')).toBeNull();
  });

  it('tela só do quiz; enviar só com as dez respondidas', async () => {
    mockGet.mockResolvedValue({ data: quiz() });
    mockPost.mockResolvedValue({
      data: quiz({ aprovado: true, tentativas: 1, perguntas: [], ultima: { ...REPROVADA, acertos: 9, nota: 90, aprovada: true, erradas: [REPROVADA.erradas[0]] } }),
    });
    renderizar();
    await screen.findByTestId('quiz-trilha');
    expect(screen.getByText(/aprova com 9 acertos \(85%\)/)).toBeInTheDocument();
    responder(9);
    const enviar = screen.getByRole('button', { name: /Enviar respostas/ });
    expect(enviar).toBeDisabled();
    responder(10);
    fireEvent.click(enviar);
    expect(await screen.findByText('Trilha concluída')).toBeInTheDocument();
    const [url, corpo] = mockPost.mock.calls[0];
    expect(url).toBe('/uc/trilhas/t1/quiz');
    expect(Object.keys(corpo.respostas)).toHaveLength(10);
    expect(corpo.respostas.p3).toBe('p3a1');
  });

  it('reprovado: placar, aulas a rever e a espera, sem gabarito', async () => {
    mockGet.mockResolvedValue({ data: quiz({ tentativas: 1, ultima: REPROVADA, segundos_para_refazer: 540, perguntas: [] }) });
    renderizar();
    const res = await screen.findByTestId('quiz-resultado');
    expect(res.textContent).toMatch(/acertou 8 de 10 \(80%\)/);
    expect(res.textContent).toMatch(/Precisa de 9 de 10/);
    expect(screen.getByText('Aula 1. O HIPO no dia do SDR')).toBeInTheDocument();
    expect(screen.getByText('Aula 4. Oportunidades')).toBeInTheDocument();
    const erradas = screen.getAllByTestId('quiz-errada');
    expect(erradas).toHaveLength(2);
    expect(erradas[0].textContent).toMatch(/2\. Onde fica a próxima tarefa\?/);
    expect(erradas[0].textContent).toMatch(/Você marcou: No relatório/);
    expect(erradas[1].textContent).toMatch(/Você marcou: No fim do mês/);
    expect(res.textContent).toMatch(/As perguntas que você errou/);
    expect(screen.getByText('9 min')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /Tentar de novo/ })).toBeDisabled();
  });

  it('tentativa antiga sem o texto: mostra só o número da pergunta', async () => {
    const antiga = { ...REPROVADA, erradas: [{ numero: 5, aula_ordem: 2, aula_titulo: 'Agenda', enunciado: null, sua_resposta: null }] };
    mockGet.mockResolvedValue({ data: quiz({ tentativas: 1, ultima: antiga, segundos_para_refazer: 300, perguntas: [] }) });
    renderizar();
    const res = await screen.findByTestId('quiz-resultado');
    expect(res.textContent).toMatch(/A pergunta que você errou/);
    expect(screen.getByText('Pergunta 5')).toBeInTheDocument();
    expect(screen.queryByTestId('quiz-errada')).toBeNull();
  });

  it('aprovado com um erro: mostra a que errou', async () => {
    mockGet.mockResolvedValue({
      data: quiz({ aprovado: true, tentativas: 1, perguntas: [], ultima: { ...REPROVADA, acertos: 9, nota: 90, aprovada: true, erradas: [REPROVADA.erradas[1]] } }),
    });
    renderizar();
    expect(await screen.findByText('Trilha concluída')).toBeInTheDocument();
    expect(screen.getByTestId('quiz-errada').textContent).toMatch(/Quando a fase muda\?/);
  });

  it('o 429 do servidor aparece e recarrega', async () => {
    mockGet.mockResolvedValue({ data: quiz() });
    mockPost.mockRejectedValue(erroHttp(429, 'Nova tentativa em 4 min.'));
    renderizar();
    await screen.findByTestId('quiz-trilha');
    responder();
    fireEvent.click(screen.getByRole('button', { name: /Enviar respostas/ }));
    expect(await screen.findByText('Nova tentativa em 4 min.')).toBeInTheDocument();
    expect(mockGet).toHaveBeenCalledTimes(2);
  });

  it('modo leitura: só o resumo', async () => {
    mockGet.mockResolvedValue({ data: quiz({ modo_leitura: true, tentativas: 2, ultima: REPROVADA, perguntas: [] }) });
    renderizar('/uc/trilhas/t1/quiz?usuario_id=u9');
    expect(await screen.findByText(/2 tentativa\(s\)\. Ainda não aprovada\./)).toBeInTheDocument();
    expect(mockGet).toHaveBeenCalledWith('/uc/trilhas/t1/quiz', { params: { usuario_id: 'u9' } });
    expect(screen.queryByRole('radio')).toBeNull();
  });
});

describe('Quiz final nas telas da aula e da trilha', () => {
  it('a aula concluída oferece o quiz final quando a trilha libera', async () => {
    mockGet.mockResolvedValue({
      data: {
        id: 'a3', trilha_id: 't1', trilha_titulo: 'HIPO - SDR', pilar: 'metodo', pilar_rotulo: 'Método',
        ordem: 3, titulo: 'Última', resumo: null, conteudo_md: '## X\n\nY', video_provedor: null,
        video_ref: null, video_url: null, duracao_min: 5, versao: 1, status: 'publicada', materiais: [],
        anterior: null, proxima: null, aberta_em: '2026-10-05T10:00:00Z',
        concluida_em: '2026-10-05T10:10:00Z', concluiu_versao_anterior: false,
        segundos_para_liberar: 0, modo_leitura: false, tour: null,
        quiz_da_trilha: { perguntas: 10, aprovado: false, liberado: true },
      },
    });
    renderizar('/uc/aulas/a3');
    fireEvent.click(await screen.findByRole('button', { name: /Fazer o quiz final/ }));
    expect(await screen.findByTestId('quiz-trilha')).toBeInTheDocument();
  });

  it('a trilha mostra o quiz como última linha', async () => {
    mockGet.mockImplementation((url) => Promise.resolve({
      data: url.endsWith('/quiz') ? quiz() : {
        id: 't1', titulo: 'HIPO - SDR', descricao: null, pilar: 'metodo', pilar_rotulo: 'Método',
        status: 'publicada', obrigatoria: true, prazo: null,
        situacao: { codigo: 'em_dia', rotulo: 'Em dia', dias_restantes: 10 }, percentual: 67,
        aulas: [{ id: 'a1', ordem: 1, titulo: 'Aula 1', resumo: null, duracao_min: 5, tem_video: false, materiais: 0, estado: 'concluida', status: 'publicada' }],
        quiz: { perguntas: 10, aprovado: false, liberado: true },
      },
    }));
    renderizar('/uc/trilhas/t1');
    const linha = await screen.findByTestId('trilha-quiz');
    expect(linha.textContent).toMatch(/Quiz final da trilha/);
    expect(linha.textContent).toMatch(/Disponível/);
    fireEvent.click(screen.getByRole('button', { name: /Fazer o quiz final/ }));
    expect(await screen.findByTestId('quiz-trilha')).toBeInTheDocument();
  });
});
