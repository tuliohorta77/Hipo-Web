// web/src/tests/ReuniaoAoVivo.test.jsx
//
// A tela da Reunião ao vivo. As promessas:
//
//   1. navegador sem suporte, reunião fora da janela ou pessoa sem
//      permissão: a tela diz o porquê e o Iniciar fica desligado
//   2. antes de capturar: as instruções; depois: as falas salvas, com
//      Você/Cliente, e a comparação com o Meet quando existe
//   3. iniciar: aba do Meet + microfone, sessão aberta com os dois canais,
//      a trilha da ABA vai para o reconhecedor do cliente
//   4. aba sem áudio: erro claro, e nenhuma sessão aberta
//   5. microfone negado: segue só com o cliente, avisando
//   6. a fala reconhecida aparece e entra na conta; encerrar manda o lote
//      final e recarrega o que ficou salvo
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import {
  render, screen, fireEvent, cleanup, waitFor, act,
} from '@testing-library/react';
import { MemoryRouter, Route, Routes } from 'react-router-dom';

const mockGet = vi.fn();
const mockPost = vi.fn();

vi.mock('../api', () => ({
  default: {
    get: (...a) => mockGet(...a),
    post: (...a) => mockPost(...a),
  },
  getUser: () => ({ id: 'u1', nome: 'Bruno Gonçalo', cargo: 'EV' }),
}));

import ReuniaoAoVivo from '../pages/crm/ReuniaoAoVivo';

const URL = '/crm/agenda/tarefas/t1/ao-vivo';

function dados(extra = {}) {
  return {
    tarefa_id: 't1',
    reuniao_id: 'r1',
    titulo: 'AP - UCX (Bruno) - ON',
    inicio: '2026-10-01T13:00:00Z',
    duracao_min: 30,
    empresa: 'UCX - CALDEIRARIA UNIVERSAL',
    google_link: 'https://meet.google.com/abc-defg-hij',
    pode_capturar: true,
    motivo_bloqueio: null,
    sessoes: [],
    falas: [],
    metricas: {
      falas: 0, palavras_vendedor: 0, palavras_cliente: 0,
      palavras_total: 0, proporcao_vendedor_pct: null,
    },
    comparacao: null,
    ...extra,
  };
}

// ── Navegador falso ──────────────────────────────────────────────────

let reconhecedores;

class ReconhecimentoFalso {
  constructor() {
    this.iniciadoCom = undefined;
    reconhecedores.push(this);
  }

  start(track) { this.iniciadoCom = track; }

  stop() {
    // O Chrome encerra de forma assíncrona depois do stop().
    setTimeout(() => this.onend?.(), 0);
  }

  falar(texto, isFinal = true) {
    const r = [{ transcript: texto, confidence: 0.9 }];
    r.isFinal = isFinal;
    this.onresult({ resultIndex: 0, results: [r] });
  }
}

function trilha(nome) {
  const ouvintes = {};
  return {
    nome,
    kind: 'audio',
    stop: vi.fn(),
    addEventListener: (ev, fn) => { ouvintes[ev] = fn; },
    disparar: (ev) => ouvintes[ev]?.(),
  };
}

let trilhaAba;
let trilhaMic;
let getDisplayMedia;
let getUserMedia;

function instalarNavegador({ versao = 141, semAudioNaAba = false, micNegado = false } = {}) {
  reconhecedores = [];
  trilhaAba = trilha('aba');
  trilhaMic = trilha('mic');
  const video = trilha('video');
  getDisplayMedia = vi.fn().mockResolvedValue({
    getAudioTracks: () => (semAudioNaAba ? [] : [trilhaAba]),
    getTracks: () => (semAudioNaAba ? [video] : [trilhaAba, video]),
  });
  getUserMedia = micNegado
    ? vi.fn().mockRejectedValue(Object.assign(new Error('x'), { name: 'NotAllowedError' }))
    : vi.fn().mockResolvedValue({
      getAudioTracks: () => [trilhaMic],
      getTracks: () => [trilhaMic],
    });
  Object.defineProperty(window.navigator, 'mediaDevices', {
    configurable: true, value: { getDisplayMedia, getUserMedia },
  });
  Object.defineProperty(window.navigator, 'userAgentData', {
    configurable: true,
    value: { brands: [{ brand: 'Google Chrome', version: String(versao) }] },
  });
  window.webkitSpeechRecognition = ReconhecimentoFalso;
}

function renderizar() {
  return render(
    <MemoryRouter initialEntries={['/crm/agenda/ao-vivo/t1']}>
      <Routes>
        <Route path="/crm/agenda/ao-vivo/:tarefaId" element={<ReuniaoAoVivo />} />
      </Routes>
    </MemoryRouter>,
  );
}

// A reunião como a Agenda a devolve: é dela que saem os botões de
// Realizada / No-show e a regra da próxima tarefa.
function reuniaoDaAgenda(extra = {}) {
  return {
    id: 'r1', tarefa_id: 't1', inicio: '2026-10-01T13:00:00Z',
    anfitriao_id: 'u1', situacao: 'hoje',
    desfecho: null, desfecho_efetivo: null, desfecho_sugerido: 'realizada',
    oportunidade_id: 'o1', status_oportunidade: 'ativa', outras_abertas: 1,
    ...extra,
  };
}

let respostaAoVivo;
let respostaReuniao;

function rotearGet() {
  mockGet.mockImplementation((url) => {
    if (url === URL) {
      return respostaAoVivo instanceof Error || respostaAoVivo?.response
        ? Promise.reject(respostaAoVivo)
        : Promise.resolve({ data: respostaAoVivo });
    }
    if (url === '/crm/agenda/reunioes/r1') return Promise.resolve({ data: respostaReuniao });
    if (url === '/crm/dominio/usuarios') {
      return Promise.resolve({ data: [{ id: 'u1', nome: 'Bruno Gonçalo', cargo: 'EV' }] });
    }
    return Promise.resolve({ data: null });
  });
}

async function abrir(resposta = dados(), reuniao = reuniaoDaAgenda()) {
  respostaAoVivo = resposta;
  respostaReuniao = reuniao;
  rotearGet();
  renderizar();
  await screen.findByText('Reunião ao vivo');
}

const chamadasAoVivo = () => mockGet.mock.calls.filter(([u]) => u === URL).length;

const botaoIniciar = () => screen.getByRole('button', { name: /Iniciar transcrição/ });

beforeEach(() => {
  mockGet.mockReset();
  mockPost.mockReset();
  instalarNavegador();
  Element.prototype.scrollIntoView = vi.fn();
});

afterEach(() => {
  cleanup();
  delete window.webkitSpeechRecognition;
});

// ── Antes de capturar ────────────────────────────────────────────────

describe('ReuniaoAoVivo — antes de capturar', () => {
  it('mostra a reunião, o link do Meet e as instruções', async () => {
    await abrir();
    expect(mockGet).toHaveBeenCalledWith(URL);
    expect(screen.getByText(/UCX - CALDEIRARIA UNIVERSAL/)).toBeInTheDocument();
    expect(screen.getByText('Abrir o Meet').closest('a'))
      .toHaveAttribute('href', 'https://meet.google.com/abc-defg-hij');
    expect(screen.getByText(/Compartilhar áudio da guia/)).toBeInTheDocument();
    expect(botaoIniciar()).not.toBeDisabled();
  });

  it('Chrome antigo: diz a versão mínima e não deixa iniciar', async () => {
    instalarNavegador({ versao: 120 });
    await abrir();
    expect(screen.getByText(/Chrome 133 ou mais novo/)).toBeInTheDocument();
    expect(botaoIniciar()).toBeDisabled();
  });

  it('fora da janela: mostra o motivo do servidor', async () => {
    await abrir(dados({ pode_capturar: false, motivo_bloqueio: 'Ainda é cedo: a captura abre 1 hora antes do início da reunião.' }));
    expect(screen.getByText(/Ainda é cedo/)).toBeInTheDocument();
    expect(botaoIniciar()).toBeDisabled();
  });

  it('quem não está na reunião vê, mas não inicia', async () => {
    await abrir(dados({ pode_capturar: false }));
    expect(screen.getByText(/Só o anfitrião, um participante/)).toBeInTheDocument();
    expect(botaoIniciar()).toBeDisabled();
  });

  it('falas salvas aparecem com quem falou, e a proporção é calculada', async () => {
    await abrir(dados({
      sessoes: [{ id: 's0' }],
      falas: [
        { sessao_id: 's0', seq: 0, canal: 'vendedor', inicio: '2026-10-01T13:01:00Z', fim: null, texto: 'bom dia tudo bem' },
        { sessao_id: 's0', seq: 1, canal: 'cliente', inicio: '2026-10-01T13:01:05Z', fim: null, texto: 'tudo ótimo' },
      ],
      comparacao: { palavras_meet: 10, palavras_ao_vivo: 6, cobertura_pct: 60 },
    }));
    const lista = screen.getByRole('list', { name: 'Transcrição ao vivo' });
    expect(lista).toHaveTextContent('Você');
    expect(lista).toHaveTextContent('bom dia tudo bem');
    expect(lista).toHaveTextContent('Cliente');
    expect(screen.getByText('67%')).toBeInTheDocument();
    expect(screen.getByText('60%')).toBeInTheDocument();
    expect(screen.getByText(/1 captura anterior/)).toBeInTheDocument();
  });

  it('erro ao carregar', async () => {
    respostaAoVivo = { response: { status: 404, data: { detail: 'Esta tarefa não é uma reunião da agenda.' } } };
    rotearGet();
    renderizar();
    expect(await screen.findByText('Esta tarefa não é uma reunião da agenda.')).toBeInTheDocument();
  });
});

// ── Capturando ───────────────────────────────────────────────────────

describe('ReuniaoAoVivo — capturando', () => {
  function sessaoAberta(canais = ['vendedor', 'cliente']) {
    mockPost.mockImplementation((url, corpo) => {
      if (url === URL) {
        return Promise.resolve({ data: { id: 's1', canais: corpo.canais } });
      }
      return Promise.resolve({ data: {} });
    });
    return canais;
  }

  it('abre a sessão com os dois canais e liga cada trilha no seu reconhecedor', async () => {
    sessaoAberta();
    await abrir();
    fireEvent.click(botaoIniciar());
    await screen.findByText('Só parar');

    expect(getDisplayMedia).toHaveBeenCalledWith(expect.objectContaining({
      audio: expect.anything(), selfBrowserSurface: 'exclude',
    }));
    expect(mockPost).toHaveBeenCalledWith(URL, {
      canais: ['vendedor', 'cliente'], navegador: 'Chrome 141',
    });
    const trilhas = reconhecedores.map((r) => r.iniciadoCom?.nome).sort();
    expect(trilhas).toEqual(['aba', 'mic']);
    expect(reconhecedores.every((r) => r.lang === 'pt-BR')).toBe(true);
  });

  it('aba compartilhada sem áudio: explica e não abre sessão', async () => {
    instalarNavegador({ semAudioNaAba: true });
    await abrir();
    fireEvent.click(botaoIniciar());
    expect(await screen.findByText(/compartilhada sem áudio/)).toBeInTheDocument();
    expect(mockPost).not.toHaveBeenCalled();
    expect(reconhecedores).toHaveLength(0);
  });

  it('escolha da aba cancelada: volta ao início com a frase certa', async () => {
    await abrir();
    getDisplayMedia.mockRejectedValueOnce(Object.assign(new Error('x'), { name: 'NotAllowedError' }));
    fireEvent.click(botaoIniciar());
    expect(await screen.findByText(/escolha da aba foi cancelada/)).toBeInTheDocument();
    expect(botaoIniciar()).not.toBeDisabled();
  });

  it('microfone negado: segue só com o cliente, avisando', async () => {
    instalarNavegador({ micNegado: true });
    sessaoAberta();
    await abrir();
    fireEvent.click(botaoIniciar());
    await screen.findByText('Só parar');
    expect(screen.getByText(/Sem acesso ao microfone/)).toBeInTheDocument();
    expect(mockPost).toHaveBeenCalledWith(URL, { canais: ['cliente'], navegador: 'Chrome 141' });
    expect(reconhecedores).toHaveLength(1);
    expect(reconhecedores[0].iniciadoCom.nome).toBe('aba');
  });

  it('servidor recusa a sessão: mostra o motivo e solta as trilhas', async () => {
    mockPost.mockRejectedValue({ response: { status: 403, data: { detail: 'Só o anfitrião pode.' } } });
    await abrir();
    fireEvent.click(botaoIniciar());
    expect(await screen.findByText('Só o anfitrião pode.')).toBeInTheDocument();
    expect(trilhaAba.stop).toHaveBeenCalled();
    expect(trilhaMic.stop).toHaveBeenCalled();
  });

  it('a fala aparece, entra na conta, e encerrar manda o lote final', async () => {
    sessaoAberta();
    await abrir();
    fireEvent.click(botaoIniciar());
    await screen.findByText('Só parar');

    const cliente = reconhecedores.find((r) => r.iniciadoCom.nome === 'aba');
    const vendedor = reconhecedores.find((r) => r.iniciadoCom.nome === 'mic');
    act(() => { cliente.falar('temos cento e vinte', false); });
    expect(screen.getByTestId('parcial-cliente')).toHaveTextContent('temos cento e vinte');

    act(() => { cliente.falar('temos 120 vidas'); });
    act(() => { vendedor.falar('perfeito'); });
    const lista = screen.getByRole('list', { name: 'Transcrição ao vivo' });
    expect(lista).toHaveTextContent('temos 120 vidas');
    expect(lista).toHaveTextContent('perfeito');
    // 1 palavra do vendedor em 4: 25%
    expect(screen.getByText('25%')).toBeInTheDocument();

    respostaAoVivo = dados({ sessoes: [{ id: 's1' }] });
    fireEvent.click(screen.getByText('Só parar'));
    await waitFor(() => expect(mockPost).toHaveBeenCalledWith(
      '/crm/agenda/ao-vivo/s1/encerrar',
      expect.objectContaining({
        falas: expect.arrayContaining([
          expect.objectContaining({ canal: 'cliente', texto: 'temos 120 vidas', seq: 0 }),
          expect.objectContaining({ canal: 'vendedor', texto: 'perfeito', seq: 1 }),
        ]),
      }),
    ));
    await screen.findByRole('button', { name: /Iniciar transcrição/ });
    expect(trilhaAba.stop).toHaveBeenCalled();
    expect(chamadasAoVivo()).toBe(2);
  });

  it('parar o compartilhamento da aba avisa que o cliente parou de ser transcrito', async () => {
    sessaoAberta();
    await abrir();
    fireEvent.click(botaoIniciar());
    await screen.findByText('Só parar');
    act(() => { trilhaAba.disparar('ended'); });
    expect(await screen.findByText(/compartilhamento da aba do Meet foi interrompido/)).toBeInTheDocument();
  });

  it('erro fatal do reconhecimento aparece em português', async () => {
    sessaoAberta();
    await abrir();
    fireEvent.click(botaoIniciar());
    await screen.findByText('Só parar');
    const vendedor = reconhecedores.find((r) => r.iniciadoCom.nome === 'mic');
    act(() => { vendedor.onerror({ error: 'language-not-supported' }); });
    expect(screen.getByText(/Você: o português não está disponível/)).toBeInTheDocument();
  });
});

// ── Desfecho: Realizada / No-show dão baixa daqui ────────────────────

describe('ReuniaoAoVivo — desfecho', () => {
  const URL_DESFECHO = '/crm/agenda/reunioes/r1/desfecho';

  function servidor({ desfechoFalha = false } = {}) {
    mockPost.mockImplementation((url, corpo) => {
      if (url === URL) return Promise.resolve({ data: { id: 's1', canais: corpo.canais } });
      if (url === URL_DESFECHO) {
        if (desfechoFalha) {
          return Promise.reject({ response: { status: 422, data: { detail: 'Esta reunião já foi registrada como no-show.' } } });
        }
        const fechada = reuniaoDaAgenda({
          situacao: corpo.desfecho === 'realizada' ? 'concluida' : 'cancelada',
          desfecho: corpo.desfecho, desfecho_efetivo: corpo.desfecho,
        });
        respostaReuniao = fechada;
        return Promise.resolve({ data: fechada });
      }
      return Promise.resolve({ data: {} });
    });
  }

  const urlsPost = () => mockPost.mock.calls.map(([u]) => u);

  it('capturando: Realizada encerra a transcrição e depois conclui a reunião', async () => {
    servidor();
    await abrir();
    fireEvent.click(botaoIniciar());
    await screen.findByText('Só parar');
    const cliente = reconhecedores.find((r) => r.iniciadoCom.nome === 'aba');
    act(() => { cliente.falar('fechado então'); });

    fireEvent.click(screen.getByRole('button', { name: /Realizada/ }));
    expect(await screen.findByText(/registrada como realizada/)).toBeInTheDocument();
    expect(urlsPost()).toEqual([URL, '/crm/agenda/ao-vivo/s1/encerrar', URL_DESFECHO]);
    expect(mockPost).toHaveBeenCalledWith(URL_DESFECHO, {
      desfecho: 'realizada', observacao: null, proxima: null,
    });
    // Fechada: somem os botões e aparece o desfecho registrado.
    expect(screen.queryByRole('button', { name: /No-show/ })).not.toBeInTheDocument();
    expect(screen.getByLabelText('Desfecho da reunião')).toHaveTextContent('Realizada');
  });

  it('sem captura: No-show dá baixa direto, sem sessão para encerrar', async () => {
    servidor();
    await abrir();
    fireEvent.click(screen.getByRole('button', { name: /No-show/ }));
    expect(await screen.findByText(/registrada como no-show/)).toBeInTheDocument();
    expect(urlsPost()).toEqual([URL_DESFECHO]);
    expect(mockPost).toHaveBeenCalledWith(URL_DESFECHO, {
      desfecho: 'no_show', observacao: null, proxima: null,
    });
  });

  it('última tarefa aberta da oportunidade: Realizada pede a próxima antes de gravar', async () => {
    servidor();
    await abrir(dados(), reuniaoDaAgenda({ outras_abertas: 0 }));
    fireEvent.click(screen.getByRole('button', { name: /Realizada/ }));
    expect(await screen.findByText(/Toda reunião realizada exige a próxima/)).toBeInTheDocument();
    expect(screen.getByRole('radio', { name: /Realizada/ })).toHaveAttribute('aria-checked', 'true');
    expect(urlsPost()).not.toContain(URL_DESFECHO);
    // Enquanto o painel está aberto, os botões do topo saem de cena.
    expect(screen.queryByRole('button', { name: /No-show/ })).not.toBeInTheDocument();
  });

  it('oportunidade finalizada: Realizada não pede próxima', async () => {
    servidor();
    await abrir(dados(), reuniaoDaAgenda({ outras_abertas: 0, status_oportunidade: 'ganha' }));
    fireEvent.click(screen.getByRole('button', { name: /Realizada/ }));
    expect(await screen.findByText(/registrada como realizada/)).toBeInTheDocument();
  });

  it('reunião já fechada: sem Iniciar, sem Realizada/No-show, com o desfecho', async () => {
    await abrir(dados(), reuniaoDaAgenda({
      situacao: 'concluida', desfecho: 'realizada', desfecho_efetivo: 'realizada',
    }));
    await screen.findByLabelText('Desfecho da reunião');
    expect(screen.queryByRole('button', { name: /Iniciar transcrição/ })).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /Realizada/ })).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /No-show/ })).not.toBeInTheDocument();
  });

  it('erro do servidor aparece e a reunião continua aberta', async () => {
    servidor({ desfechoFalha: true });
    await abrir();
    fireEvent.click(screen.getByRole('button', { name: /No-show/ }));
    expect(await screen.findByText('Esta reunião já foi registrada como no-show.')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /No-show/ })).toBeInTheDocument();
  });

  it('Só parar encerra a transcrição sem registrar desfecho', async () => {
    servidor();
    await abrir();
    fireEvent.click(botaoIniciar());
    await screen.findByText('Só parar');
    fireEvent.click(screen.getByText('Só parar'));
    await screen.findByRole('button', { name: /Iniciar transcrição/ });
    expect(urlsPost()).toEqual([URL, '/crm/agenda/ao-vivo/s1/encerrar']);
    expect(screen.getByRole('button', { name: /Realizada/ })).toBeInTheDocument();
  });

  it('sem a reunião da agenda, a captura segue e os botões de desfecho não aparecem', async () => {
    await abrir(dados(), null);
    expect(botaoIniciar()).not.toBeDisabled();
    expect(screen.queryByRole('button', { name: /No-show/ })).not.toBeInTheDocument();
  });
});
