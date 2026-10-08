// web/src/tests/RoleplayCarreira.test.jsx
//
// Carreira · Roleplay. O que estes testes seguram:
//   1. bloqueado: cadeado, motivo e botão para o quiz; sem botão de treinar
//   2. liberado: abre no próximo roleplay, números do mês, cenários e histórico
//   3. limite do dia batido desliga o Começar e diz por quê
//   4. modo leitura: sem botões de treinar
//   5. treino: termo obrigatório; começar abre a sessão, conecta a voz e
//      encerrar manda transcrição + gravação e vai para o resultado
//   6. resultado: transcrição e botão de ouvir a gravação
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, fireEvent, cleanup, waitFor, within } from '@testing-library/react';
import { MemoryRouter, Route, Routes } from 'react-router-dom';

const mockGet = vi.fn();
const mockPost = vi.fn();
vi.mock('../api', () => ({
  default: { get: (...a) => mockGet(...a), post: (...a) => mockPost(...a) },
  getUser: () => ({ id: 'u1', nome: 'Jakeline', cargo: 'EV' }),
  getModulos: () => ['perfil', 'crm'],
}));

import Roleplay from '../pages/carreira/Roleplay';
import RoleplayTreino, { ResultadoRoleplay } from '../pages/carreira/RoleplaySessao';

function cenario(extra = {}) {
  return {
    id: 'ev-ferrovale-descoberta', titulo: 'Abertura e descoberta · RH de indústria', formato: 'bloco',
    bloco: 'abertura_descoberta', bloco_rotulo: 'Abertura e descoberta', dificuldade: 1, duracao_alvo_min: 15,
    objetivo: 'Abrir bem e mapear as dores.', briefing: 'Metalúrgica Ferrovale, 180 funcionários.',
    versao: 1, tentativas: 0, ultima_em: null, ...extra,
  };
}

function tela(extra = {}) {
  const c = cenario();
  return {
    pessoa: { id: 'u1', nome: 'Jakeline', cargo: 'EV' }, modo_leitura: false,
    liberado: true, motivo: null, trilha_id: 't-roteiro', pode_treinar: true,
    disponivel: true, indisponivel_motivo: null, consentimento_pendente: false,
    termo: { versao: '2026-10-07', texto: 'Este treino grava a sua voz.' },
    proximo: c,
    cenarios: [c, cenario({ id: 'ev-ferrovale-completa', titulo: 'Reunião completa', formato: 'completa', bloco: null, bloco_rotulo: 'Reunião completa', dificuldade: 3, duracao_alvo_min: 45 })],
    resumo: { sessoes_mes: 3, minutos_mes: 41, sessoes_hoje: 1, limite_dia: 2, ultima_em: '2026-10-07T20:00:00Z' },
    historico: [{
      id: 's1', cenario_id: c.id, cenario_titulo: c.titulo, formato: 'bloco', bloco_rotulo: 'Abertura e descoberta',
      status: 'encerrada', conta_media: true, iniciada_em: '2026-10-07T20:00:00Z', encerrada_em: '2026-10-07T20:14:00Z',
      duracao_s: 840, motivo_fim: 'encerrou', fala_executivo_pct: 48, tem_audio: true,
    }],
    orcamento: null, duracao_max_min: 55, ...extra,
  };
}

function renderizar(caminho = '/carreira/roleplay', props = {}) {
  return render(
    <MemoryRouter initialEntries={[caminho]}>
      <Routes>
        <Route path="/carreira/roleplay" element={<Roleplay />} />
        <Route path="/carreira/roleplay/treino/:cenarioId" element={<RoleplayTreino {...props} />} />
        <Route path="/carreira/roleplay/sessoes/:sessaoId" element={<ResultadoRoleplay />} />
        <Route path="/uc/trilhas/:id/quiz" element={<p>tela do quiz</p>} />
      </Routes>
    </MemoryRouter>,
  );
}

beforeEach(() => { mockGet.mockReset(); mockPost.mockReset(); });
afterEach(cleanup);

describe('Roleplay', () => {
  it('bloqueado: motivo e caminho até o quiz, sem treinar', async () => {
    mockGet.mockResolvedValue({ data: tela({ liberado: false, pode_treinar: false, motivo: 'Libera quando você for aprovado no quiz final da trilha 02 · Roteiro do EV.' }) });
    renderizar();
    const bloco = await screen.findByTestId('roleplay-bloqueado');
    expect(within(bloco).getByText(/aprovado no quiz final/)).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /Treinar/ })).not.toBeInTheDocument();
    fireEvent.click(within(bloco).getByRole('button', { name: 'Ir para o quiz' }));
    expect(await screen.findByText('tela do quiz')).toBeInTheDocument();
  });

  it('liberado: próximo roleplay, números, cenários e histórico', async () => {
    mockGet.mockResolvedValue({ data: tela() });
    renderizar();
    const prox = await screen.findByTestId('proximo-roleplay');
    expect(within(prox).getByText('Abertura e descoberta · RH de indústria')).toBeInTheDocument();
    expect(screen.getByText('41')).toBeInTheDocument();
    expect(screen.getByText('1/2')).toBeInTheDocument();
    expect(screen.getByTestId('cenario-ev-ferrovale-completa')).toBeInTheDocument();
    expect(screen.getByText('14 min 00 s')).toBeInTheDocument();
    const abas = screen.getByRole('navigation', { name: 'Carreira' });
    expect(within(abas).getByText('Roleplay').closest('a').getAttribute('href')).toBe('/carreira/roleplay');
    fireEvent.click(within(prox).getByRole('button', { name: /Começar/ }));
    expect(mockGet).toHaveBeenCalledWith('/carreira/roleplay');
  });

  it('limite do dia batido desliga o Começar', async () => {
    mockGet.mockResolvedValue({ data: tela({ resumo: { ...tela().resumo, sessoes_hoje: 2 } }) });
    renderizar();
    const prox = await screen.findByTestId('proximo-roleplay');
    expect(within(prox).getByRole('button', { name: /Começar/ })).toBeDisabled();
    expect(within(prox).getByText(/limite/)).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /Treinar/ })).not.toBeInTheDocument();
  });

  it('modo leitura: sem botões de treinar', async () => {
    mockGet.mockResolvedValue({ data: tela({ modo_leitura: true, pode_treinar: false }) });
    renderizar('/carreira/roleplay?usuario_id=u9');
    expect(await screen.findByText('Carreira · Jakeline')).toBeInTheDocument();
    expect(mockGet).toHaveBeenCalledWith('/carreira/roleplay', { params: { usuario_id: 'u9' } });
    expect(screen.queryByRole('button', { name: /Começar/ })).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /Treinar/ })).not.toBeInTheDocument();
  });
});

describe('Treino', () => {
  function dubles() {
    const audio = {
      tocar: vi.fn(), interromper: vi.fn(),
      parar: vi.fn().mockResolvedValue(new Blob(['webm'], { type: 'audio/webm' })),
    };
    const motorAudio = { navegadorSuporta: () => true, iniciarAudio: vi.fn().mockResolvedValue(audio) };
    const voz = { conectar: vi.fn(), enviarAudio: vi.fn(), encerrar: vi.fn(), reconexoes: 0 };
    let cfg;
    const criarVoz = vi.fn((c) => { cfg = c; return voz; });
    return { audio, motorAudio, voz, criarVoz, cfg: () => cfg };
  }

  it('termo obrigatório, conversa e encerramento com transcrição e gravação', async () => {
    mockGet.mockResolvedValue({ data: tela({ consentimento_pendente: true }) });
    mockPost.mockImplementation((url) => {
      if (url === '/carreira/roleplay/sessoes') {
        return Promise.resolve({ data: { sessao_id: 's9', token: 'auth_tokens/a', ws_url: 'wss://g', modelo: 'gemini-3.8-live', duracao_max_s: 3300 } });
      }
      return Promise.resolve({ data: {} });
    });
    const d = dubles();
    renderizar('/carreira/roleplay/treino/ev-ferrovale-descoberta', { motorAudio: d.motorAudio, criarVoz: d.criarVoz });

    expect(await screen.findByTestId('briefing')).toHaveTextContent('Metalúrgica Ferrovale');
    const comecar = screen.getByRole('button', { name: /Começar/ });
    expect(comecar).toBeDisabled();
    fireEvent.click(screen.getByRole('checkbox'));
    fireEvent.click(comecar);

    await waitFor(() => expect(d.voz.conectar).toHaveBeenCalled());
    expect(mockPost).toHaveBeenCalledWith('/carreira/roleplay/consentimento');
    expect(mockPost).toHaveBeenCalledWith('/carreira/roleplay/sessoes', { cenario_id: 'ev-ferrovale-descoberta' });
    expect(d.cfg().token).toBe('auth_tokens/a');

    // O Gemini abre e conversa; a reconexão pede token ao HIPO.
    const ev = d.cfg().eventos;
    ev.onAberto();
    expect(await screen.findByText('Em conversa')).toBeInTheDocument();
    ev.onTranscricao('executivo', 'Oi Patrícia', 1000);
    ev.onTranscricao('cliente', 'Oi, pode falar.', 3000);
    ev.onAudio('QUJD');
    expect(d.audio.tocar).toHaveBeenCalledWith('QUJD');
    ev.onUso({ totalTokenCount: 50, promptTokensDetails: [{ modality: 'AUDIO', tokenCount: 40 }] });
    mockPost.mockResolvedValueOnce({ data: { token: 'auth_tokens/b' } });
    expect(await d.cfg().obterTokenNovo()).toBe('auth_tokens/b');
    expect(mockPost).toHaveBeenCalledWith('/carreira/roleplay/sessoes/s9/token');
    // Sem transcrição na tela durante a conversa.
    expect(screen.queryByText('Oi Patrícia')).not.toBeInTheDocument();

    mockGet.mockResolvedValue({ data: { id: 's9', cenario_titulo: 'Abertura e descoberta', transcricao: [], tem_audio: false, status: 'encerrada', motivo_fim: 'encerrou', conta_media: true } });
    fireEvent.click(screen.getByRole('button', { name: /Encerrar/ }));
    await waitFor(() => expect(mockPost).toHaveBeenCalledWith('/carreira/roleplay/sessoes/s9/encerrar', expect.any(FormData)));
    expect(d.voz.encerrar).toHaveBeenCalled();
    const form = mockPost.mock.calls.find(([u]) => u.endsWith('/encerrar'))[1];
    const dados = JSON.parse(form.get('dados'));
    expect(dados.motivo_fim).toBe('encerrou');
    expect(dados.transcricao.map((t) => t.quem)).toEqual(['executivo', 'cliente']);
    expect(dados.tokens).toEqual({ audio_in: 40, total: 50 });
    expect(form.get('audio')).toBeInstanceOf(Blob);
    expect(await screen.findByText('Sem transcrição.')).toBeInTheDocument();
  });

  it('erro do servidor ao abrir volta para a pré-sala com a mensagem', async () => {
    mockGet.mockResolvedValue({ data: tela() });
    mockPost.mockRejectedValue({ response: { data: { detail: 'Você já fez 2 roleplay(s) hoje, que é o limite diário. Volte amanhã.' } } });
    const d = dubles();
    renderizar('/carreira/roleplay/treino/ev-ferrovale-descoberta', { motorAudio: d.motorAudio, criarVoz: d.criarVoz });
    fireEvent.click(await screen.findByRole('button', { name: /Começar/ }));
    expect(await screen.findByText(/limite diário/)).toBeInTheDocument();
    expect(d.motorAudio.iniciarAudio).not.toHaveBeenCalled();
    expect(screen.getByRole('button', { name: /Começar/ })).toBeEnabled();
  });
});

describe('Resultado', () => {
  it('mostra transcrição e abre a gravação', async () => {
    mockGet.mockImplementation((url) => {
      if (url.endsWith('/audio')) return Promise.resolve({ data: { url: 'https://s3/roleplay.webm' } });
      return Promise.resolve({ data: {
        id: 's1', cenario_titulo: 'Abertura e descoberta · RH de indústria', bloco_rotulo: 'Abertura e descoberta',
        iniciada_em: '2026-10-07T20:00:00Z', duracao_s: 840, fala_executivo_pct: 48, motivo_fim: 'encerrou',
        status: 'encerrada', conta_media: true, tem_audio: true, modo_leitura: false,
        transcricao: [{ quem: 'executivo', texto: 'Oi Patrícia', t_ms: 1000 }, { quem: 'cliente', texto: 'Oi!', t_ms: 65000 }],
      } });
    });
    renderizar('/carreira/roleplay/sessoes/s1');
    expect(await screen.findByText(/Oi Patrícia/)).toBeInTheDocument();
    expect(screen.getByText(/01:05/)).toBeInTheDocument();
    expect(screen.getByText('48%')).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: /Ouvir gravação/ }));
    expect(await screen.findByTestId('player-roleplay')).toHaveAttribute('src', 'https://s3/roleplay.webm');
  });
});
