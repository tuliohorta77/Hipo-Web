// web/src/tests/TranscricaoReuniao.test.jsx
//
// A transcrição do Meet dentro da tarefa. As promessas:
//
//   1. reunião sem Meet, ou servidor sem Google: nenhum bloco
//   2. antes de pronta: o motivo, o erro do Google e o "Buscar agora"
//   3. pronta: resumo e próximos passos à vista, conversa fechada até pedir
//   4. resumo descartado: o motivo e o "gerar de novo"
//   5. o aviso de "ligue à mão" quando a transcrição automática falhou
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, fireEvent, cleanup, waitFor } from '@testing-library/react';

const mockGet = vi.fn();
const mockPost = vi.fn();

vi.mock('../api', () => ({
  default: {
    get: (...a) => mockGet(...a),
    post: (...a) => mockPost(...a),
  },
  getUser: () => null,
}));

import TranscricaoReuniao from '../components/crm/TranscricaoReuniao';

const URL = '/crm/agenda/tarefas/t1/transcricao';

function estado(extra = {}) {
  return {
    reuniao_id: 'r1',
    tarefa_id: 't1',
    status: 'nao_iniciada',
    rotulo: null,
    motivo: 'A transcrição é buscada automaticamente depois que a reunião termina.',
    erro: null,
    tentativas: 0,
    ultima_tentativa_em: null,
    tem_meet: true,
    documento_url: null,
    idioma: null,
    texto: null,
    falas: 0,
    coletada_em: null,
    resumo: null,
    proximos_passos: [],
    resumo_modelo: null,
    resumo_em: null,
    resumo_erro: null,
    transcricao_auto_em: '2026-09-24T12:00:00Z',
    transcricao_auto_erro: null,
    google_configurado: true,
    ia_configurada: true,
    pode_buscar: false,
    pode_resumir: false,
    ...extra,
  };
}

const PRONTA = estado({
  status: 'pronta',
  rotulo: 'Transcrição pronta',
  motivo: null,
  texto: '[09:00] Ana: Bom dia\n[09:01] Cliente: Temos 120 vidas',
  falas: 2,
  documento_url: 'https://docs.google.com/d/x',
  resumo: 'Cliente com 120 vidas quer PCMSO.',
  proximos_passos: ['Enviar a proposta', 'Ligar na sexta'],
  pode_resumir: true,
});

function montar(dados) {
  mockGet.mockImplementation((url) => {
    if (url === URL) return Promise.resolve({ data: dados });
    return Promise.reject(new Error(`GET inesperado: ${url}`));
  });
  return render(<TranscricaoReuniao tarefa={{ id: 't1' }} />);
}

beforeEach(() => {
  mockGet.mockReset();
  mockPost.mockReset();
});
afterEach(cleanup);

describe('TranscricaoReuniao — quando some', () => {
  it('reunião sem Meet não mostra bloco', async () => {
    const { container } = montar(estado({ status: 'sem_meet', tem_meet: false }));
    await waitFor(() => expect(mockGet).toHaveBeenCalledWith(URL));
    expect(container).toBeEmptyDOMElement();
  });

  it('servidor sem Google não mostra bloco', async () => {
    const { container } = montar(estado({ google_configurado: false }));
    await waitFor(() => expect(mockGet).toHaveBeenCalled());
    expect(container).toBeEmptyDOMElement();
  });

  it('404 (tarefa que não é reunião) não é erro na tela', async () => {
    mockGet.mockRejectedValue({ response: { status: 404, data: { detail: 'x' } } });
    const { container } = render(<TranscricaoReuniao tarefa={{ id: 't1' }} />);
    await waitFor(() => expect(mockGet).toHaveBeenCalled());
    expect(container).toBeEmptyDOMElement();
  });

  it('resposta fora do formato não derruba nada', async () => {
    mockGet.mockResolvedValue(undefined);
    const { container } = render(<TranscricaoReuniao tarefa={{ id: 't1' }} />);
    await waitFor(() => expect(mockGet).toHaveBeenCalled());
    expect(container).toBeEmptyDOMElement();
  });
});

describe('TranscricaoReuniao — antes de pronta', () => {
  it('mostra o motivo e não oferece buscar antes do fim', async () => {
    montar(estado());
    expect(await screen.findByText(/depois que a reunião termina/)).toBeInTheDocument();
    expect(screen.getByText('Depois da reunião')).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /Buscar agora/ })).toBeNull();
  });

  it('mostra o erro do Google e busca de novo', async () => {
    montar(estado({
      status: 'aguardando', rotulo: 'Aguardando transcrição',
      motivo: 'Não foi possível consultar o Google Meet.',
      erro: 'Falta o escopo meetings.space.readonly.',
      pode_buscar: true,
    }));
    expect(await screen.findByText(/Falta o escopo/)).toBeInTheDocument();
    mockPost.mockResolvedValue({ data: PRONTA });
    fireEvent.click(screen.getByRole('button', { name: /Buscar agora/ }));
    await waitFor(() => expect(mockPost).toHaveBeenCalledWith(`${URL}/buscar`));
    expect(await screen.findByText('Transcrição pronta')).toBeInTheDocument();
  });

  it('erro ao buscar aparece com o texto do backend', async () => {
    montar(estado({ status: 'aguardando', pode_buscar: true }));
    mockPost.mockRejectedValue({ response: { data: { detail: 'Ainda não dá para buscar.' } } });
    fireEvent.click(await screen.findByRole('button', { name: /Buscar agora/ }));
    expect(await screen.findByText('Ainda não dá para buscar.')).toBeInTheDocument();
  });

  it('avisa para ligar à mão quando a automática falhou', async () => {
    montar(estado({ transcricao_auto_erro: 'Falta o escopo meetings.space.settings.' }));
    expect(await screen.findByText(/ligue em Atividades/)).toBeInTheDocument();
  });

  it('indisponível mostra o porquê', async () => {
    montar(estado({
      status: 'indisponivel', rotulo: 'Sem transcrição',
      motivo: 'Ninguém entrou na sala do Meet desta reunião.',
    }));
    expect(await screen.findByText(/Ninguém entrou/)).toBeInTheDocument();
    expect(screen.getByText('Sem transcrição')).toBeInTheDocument();
  });
});

describe('TranscricaoReuniao — pronta', () => {
  it('resumo e próximos passos à vista; conversa só quando pede', async () => {
    montar(PRONTA);
    expect(await screen.findByText('Cliente com 120 vidas quer PCMSO.')).toBeInTheDocument();
    expect(screen.getByText('Enviar a proposta')).toBeInTheDocument();
    expect(screen.getByText('Ligar na sexta')).toBeInTheDocument();
    expect(screen.getByText(/confira antes de registrar/)).toBeInTheDocument();
    expect(screen.getByRole('link', { name: /Google Docs/ }))
      .toHaveAttribute('href', 'https://docs.google.com/d/x');

    expect(screen.queryByTestId('texto-transcricao')).toBeNull();
    fireEvent.click(screen.getByRole('button', { name: /Ver a conversa \(2 falas\)/ }));
    expect(screen.getByTestId('texto-transcricao')).toHaveTextContent('Temos 120 vidas');
    fireEvent.click(screen.getByRole('button', { name: /Esconder a conversa/ }));
    expect(screen.queryByTestId('texto-transcricao')).toBeNull();
  });

  it('resumo descartado mostra o motivo e gera de novo', async () => {
    montar({ ...PRONTA, resumo: null, proximos_passos: [],
             resumo_erro: 'Resumo descartado: citou número (45).' });
    expect(await screen.findByText(/Resumo descartado/)).toBeInTheDocument();
    mockPost.mockResolvedValue({ data: PRONTA });
    fireEvent.click(screen.getByRole('button', { name: /Gerar resumo de novo/ }));
    await waitFor(() => expect(mockPost).toHaveBeenCalledWith(`${URL}/resumo`));
    expect(await screen.findByText('Cliente com 120 vidas quer PCMSO.')).toBeInTheDocument();
  });

  it('sem IA configurada não oferece resumo', async () => {
    montar({ ...PRONTA, resumo: null, proximos_passos: [], ia_configurada: false });
    expect(await screen.findByText('Transcrição pronta')).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /Gerar resumo/ })).toBeNull();
  });

  it('pronta sem resumo e com IA oferece gerar', async () => {
    montar({ ...PRONTA, resumo: null, proximos_passos: [] });
    mockPost.mockResolvedValue({ data: PRONTA });
    fireEvent.click(await screen.findByRole('button', { name: /^Gerar resumo$/ }));
    await waitFor(() => expect(mockPost).toHaveBeenCalledWith(`${URL}/resumo`));
  });

  it('pronta aparece mesmo com o Google desligado depois', async () => {
    montar({ ...PRONTA, google_configurado: false });
    expect(await screen.findByText('Cliente com 120 vidas quer PCMSO.')).toBeInTheDocument();
  });
});
