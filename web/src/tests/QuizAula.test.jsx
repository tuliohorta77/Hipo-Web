// web/src/tests/QuizAula.test.jsx
//
// O quiz no fim da aula. O que estes testes seguram:
//   1. aula com quiz não tem "Concluí"
//   2. trancado enquanto o tempo mínimo da aula corre
//   3. "Enviar" só com as 7 respondidas; manda {pergunta: alternativa}
//   4. aprovado: tela de concluída com o placar
//   5. reprovado: placar, números das erradas (sem gabarito) e a espera
//   6. o 429 do servidor aparece e recarrega a aula
//   7. modo leitura: só o resumo, sem pergunta para responder
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, fireEvent, cleanup, within } from '@testing-library/react';
import { MemoryRouter, Route, Routes } from 'react-router-dom';

const mockGet = vi.fn();
const mockPost = vi.fn();
vi.mock('../api', () => ({
  default: { get: (...a) => mockGet(...a), post: (...a) => mockPost(...a) },
  getUser: () => null,
  getModulos: () => ['perfil', 'crm'],
}));

import Aula from '../pages/uc/Aula';

function quiz(extra = {}) {
  return {
    total: 7, nota_minima: 85, acertos_para_aprovar: 6, tentativas: 0, aprovado: false,
    ultima: null, segundos_para_refazer: 0, espera_minutos: 10,
    perguntas: Array.from({ length: 7 }, (_, i) => ({
      id: `p${i + 1}`, numero: i + 1, enunciado: `Pergunta ${i + 1}?`,
      alternativas: [0, 1, 2, 3].map((k) => ({ id: `p${i + 1}a${k}`, texto: `Opção ${i + 1}.${k}` })),
    })),
    ...extra,
  };
}

function aula(extra = {}) {
  return {
    id: 'a1', trilha_id: 't1', trilha_titulo: 'Normas', pilar: 'tecnica', pilar_rotulo: 'Técnica',
    ordem: 1, titulo: 'NR-01', resumo: 'Resumo', conteudo_md: '## Texto\n\nTexto.',
    video_provedor: null, video_ref: null, video_url: null, duracao_min: 10, versao: 1,
    status: 'publicada', materiais: [], anterior: null, proxima: null,
    aberta_em: '2026-10-05T10:00:00Z', concluida_em: null, concluiu_versao_anterior: false,
    segundos_para_liberar: 0, modo_leitura: false, tour: null, quiz: quiz(),
    ...extra,
  };
}

function renderizar(caminho = '/uc/aulas/a1') {
  return render(
    <MemoryRouter initialEntries={[caminho]}>
      <Routes>
        <Route path="/uc/aulas/:aulaId" element={<Aula />} />
      </Routes>
    </MemoryRouter>,
  );
}

function erroHttp(status, detail) {
  return Object.assign(new Error(`HTTP ${status}`), { response: { status, data: { detail } } });
}

function responderTodas(ate = 7) {
  for (let i = 1; i <= ate; i += 1) {
    fireEvent.click(screen.getByLabelText(`Opção ${i}.1`));
  }
}

beforeEach(() => { mockGet.mockReset(); mockPost.mockReset(); });
afterEach(cleanup);

describe('Quiz da aula', () => {
  it('aula com quiz não tem o botão Concluí', async () => {
    mockGet.mockResolvedValue({ data: aula() });
    renderizar();
    await screen.findByTestId('quiz-aula');
    expect(screen.queryByRole('button', { name: /Concluí/ })).toBeNull();
    expect(screen.getByText(/aprova com 6 acertos \(85%\)/)).toBeInTheDocument();
  });

  it('trancado enquanto o tempo mínimo corre', async () => {
    mockGet.mockResolvedValue({ data: aula({ segundos_para_liberar: 300 }) });
    renderizar();
    const card = await screen.findByTestId('quiz-aula');
    expect(within(card).getByText(/O quiz abre em/)).toBeInTheDocument();
    expect(within(card).getByText('5 min')).toBeInTheDocument();
    expect(screen.queryByText('Pergunta 1?', { exact: false })).toBeNull();
  });

  it('enviar só com as sete respondidas, no formato pergunta → alternativa', async () => {
    mockGet.mockResolvedValue({ data: aula() });
    mockPost.mockResolvedValue({
      data: aula({
        concluida_em: '2026-10-05T10:20:00Z',
        quiz: quiz({ tentativas: 1, aprovado: true, ultima: { acertos: 6, total: 7, nota: 85, aprovada: true, erradas: ['p3'], em: '2026-10-05T10:20:00Z' } }),
      }),
    });
    renderizar();
    await screen.findByTestId('quiz-aula');
    responderTodas(6);
    const enviar = screen.getByRole('button', { name: /Enviar respostas/ });
    expect(enviar).toBeDisabled();
    expect(screen.getByText(/6 de 7 respondidas/)).toBeInTheDocument();
    responderTodas(7);
    expect(enviar).not.toBeDisabled();
    fireEvent.click(enviar);
    expect(await screen.findByText(/Aprovado/)).toBeInTheDocument();
    expect(screen.getByText(/6 de 7 \(85%\)/)).toBeInTheDocument();
    expect(screen.getByText('Aula concluída.')).toBeInTheDocument();
    const [url, corpo] = mockPost.mock.calls[0];
    expect(url).toBe('/uc/aulas/a1/quiz');
    expect(Object.keys(corpo.respostas)).toHaveLength(7);
    expect(corpo.respostas.p1).toBe('p1a1');
  });

  it('reprovado: placar, perguntas erradas e a espera, sem revelar a certa', async () => {
    mockGet.mockResolvedValue({
      data: aula({
        quiz: quiz({
          tentativas: 1, segundos_para_refazer: 540,
          ultima: { acertos: 5, total: 7, nota: 71, aprovada: false, erradas: ['p2', 'p5'], em: '2026-10-05T10:20:00Z' },
        }),
      }),
    });
    renderizar();
    const res = await screen.findByTestId('quiz-resultado');
    expect(res.textContent).toMatch(/Não foi desta vez: você acertou 5 de 7 \(71%\)/);
    expect(res.textContent).toMatch(/Precisa de 6 de 7/);
    expect(within(res).getByText('2, 5')).toBeInTheDocument();
    expect(screen.getByText(/Nova tentativa em/)).toBeInTheDocument();
    expect(screen.getByText('9 min')).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /Enviar respostas/ })).toBeNull();
  });

  it('passada a espera, marca as que errou e conta a tentativa', async () => {
    mockGet.mockResolvedValue({
      data: aula({
        quiz: quiz({
          tentativas: 1, segundos_para_refazer: 0,
          ultima: { acertos: 5, total: 7, nota: 71, aprovada: false, erradas: ['p2', 'p5'], em: '2026-10-05T10:00:00Z' },
        }),
      }),
    });
    renderizar();
    await screen.findByTestId('quiz-aula');
    expect(screen.getAllByText('errou na última tentativa')).toHaveLength(2);
    expect(screen.getByText(/tentativa 2/)).toBeInTheDocument();
  });

  it('o 429 do servidor aparece e a aula é recarregada', async () => {
    mockGet.mockResolvedValue({ data: aula() });
    mockPost.mockRejectedValue(erroHttp(429, 'Nova tentativa em 4 min.'));
    renderizar();
    await screen.findByTestId('quiz-aula');
    responderTodas();
    fireEvent.click(screen.getByRole('button', { name: /Enviar respostas/ }));
    expect(await screen.findByText('Nova tentativa em 4 min.')).toBeInTheDocument();
    expect(mockGet).toHaveBeenCalledTimes(2);
  });

  it('modo leitura: só o resumo', async () => {
    mockGet.mockResolvedValue({
      data: aula({
        modo_leitura: true,
        quiz: quiz({ tentativas: 2, ultima: { acertos: 4, total: 7, nota: 57, aprovada: false, erradas: ['p1', 'p2', 'p3'], em: '2026-10-05T10:00:00Z' } }),
      }),
    });
    renderizar('/uc/aulas/a1?usuario_id=u9');
    expect(await screen.findByText(/2 tentativa\(s\)\. Ainda não aprovada\./)).toBeInTheDocument();
    expect(screen.queryByRole('radio')).toBeNull();
  });

  it('concluiu antes de a aula ter quiz', async () => {
    mockGet.mockResolvedValue({ data: aula({ concluida_em: '2026-10-01T10:00:00Z' }) });
    renderizar();
    expect(await screen.findByText('Você concluiu esta aula antes de ela ter quiz.')).toBeInTheDocument();
  });
});
