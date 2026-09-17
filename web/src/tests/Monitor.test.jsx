// web/src/tests/Monitor.test.jsx
//
// O painel de parede. Cinco promessas que os testes seguram:
//   1. dez quadros, com carinha, resultado contra a meta DE HOJE e a do mês
//   2. se atualiza sozinho, sem ninguém dar F5 — e para quando a aba esconde
//   3. leitura que falha NÃO apaga o painel da parede: mostra o aviso e o
//      último dado bom
//   4. quem não é gestão não vê o botão de metas
//   5. indicador sem meta e indicador sem fonte ficam sem carinha, e não com
//      carinha de zero
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import {
  render, screen, fireEvent, cleanup, waitFor, within, act,
} from '@testing-library/react';

const mockGet = vi.fn();
const mockPut = vi.fn();
const mockPost = vi.fn();
const mockDelete = vi.fn();
const mockGetUser = vi.fn(() => ({ id: 'u1', nome: 'Tulio Horta', cargo: 'Franqueado' }));

vi.mock('../api', () => ({
  default: {
    get: (...a) => mockGet(...a),
    put: (...a) => mockPut(...a),
    post: (...a) => mockPost(...a),
    delete: (...a) => mockDelete(...a),
  },
  getUser: (...a) => mockGetUser(...a),
}));

import Monitor from '../pages/Monitor';

function ind(chave, extra = {}) {
  return {
    chave,
    sigla: chave.toUpperCase(),
    rotulo: chave,
    fonte: `de onde vem ${chave}`,
    natureza: 'acumulativo',
    formato: 'inteiro',
    resultado: 0,
    meta: null,
    meta_mtd: null,
    atingimento: null,
    atingimento_mes: null,
    carinha: null,
    ...extra,
  };
}

const CHAVES = [
  'lead', 'agen', 'apre', 'nmrr', 'ticket_medio',
  'reunioes_parceria', 'agendamentos_mes', 'noshow', 'contratos', 'treinamento',
];

function painel(extra = {}) {
  return {
    ano: 2026, mes: 9, rotulo: 'setembro de 2026',
    hoje: '2026-09-17', dia_util_atual: 13, dias_uteis: 22,
    progresso: 13 / 22,
    atualizado_em: '2026-09-17T13:45:09Z',
    indicadores: CHAVES.map((c) => ind(c)),
    ...extra,
  };
}

function comLead(extra) {
  const p = painel();
  p.indicadores = p.indicadores.map((i) => (i.chave === 'lead' ? { ...i, ...extra } : i));
  return p;
}

function responder(corpo) {
  mockGet.mockImplementation((url) => {
    if (url === '/monitor/painel') return Promise.resolve({ data: corpo });
    if (url === '/monitor/metas') {
      return Promise.resolve({
        data: {
          ano: 2026, mes: 9, rotulo: 'setembro de 2026',
          metas: CHAVES.map((c) => ({
            indicador: c, sigla: c.toUpperCase(), rotulo: c,
            formato: 'inteiro', natureza: 'acumulativo',
            valor: c === 'lead' ? 276 : null,
            atualizado_em: null, atualizado_por_nome: null,
          })),
        },
      });
    }
    if (url === '/monitor/feriados') {
      return Promise.resolve({
        data: [{ id: 7, data: '2026-09-07', motivo: 'Independência do Brasil' }],
      });
    }
    return Promise.resolve({ data: {} });
  });
}

beforeEach(() => {
  mockGet.mockReset();
  mockPut.mockReset();
  mockPost.mockReset();
  mockDelete.mockReset();
  mockGetUser.mockReturnValue({ id: 'u1', nome: 'Tulio Horta', cargo: 'Franqueado' });
  responder(painel());
  mockPut.mockResolvedValue({ data: { ano: 2026, mes: 9, rotulo: 'setembro de 2026', metas: [] } });
  mockPost.mockResolvedValue({ data: [] });
  mockDelete.mockResolvedValue({ data: null });
});

afterEach(() => { cleanup(); vi.useRealTimers(); });

// Espera o painel chegar antes de olhar o quadro: a tela abre vazia e
// preenche na resposta.
async function quadro(rotulo) {
  return within(await screen.findByRole('region', { name: rotulo }));
}

describe('Monitor — os quadros', () => {
  it('desenha os dez quadros do mês corrente', async () => {
    render(<Monitor />);
    await screen.findByText('setembro de 2026');
    for (const c of CHAVES) {
      expect(screen.getByRole('region', { name: c })).toBeInTheDocument();
    }
    // O denominador de toda carinha da tela.
    expect(screen.getByText(/dia útil 13 de 22/)).toBeInTheDocument();
  });

  it('o par grande e a barra são o RITMO: resultado contra a meta de hoje', async () => {
    /*
      Antes o par era contra a meta do mês, e a tela dizia duas coisas: "69
      de 276" com carinha triste não se explica sozinho. O que se cobra hoje
      são 163.
    */
    responder(comLead({
      resultado: 69, meta: 276, meta_mtd: 163, carinha: 'triste',
      atingimento: 0.42, atingimento_mes: 0.25,
    }));
    render(<Monitor />);
    const lead = await quadro('lead');
    expect(lead.getByText('69')).toBeInTheDocument();
    expect(lead.getByText(/163/)).toBeInTheDocument();
    expect(lead.getByText('42%')).toBeInTheDocument();
    expect(lead.getByRole('progressbar')).toHaveAttribute('aria-valuenow', '42');
    // A meta do mês não desaparece: vai para a linha pequena.
    expect(lead.getByText('mês: 276')).toBeInTheDocument();
    // A carinha tem rótulo por extenso: cor e emoji sozinhos não são texto.
    expect(lead.getByRole('img', { name: 'abaixo da meta' })).toBeInTheDocument();
  });

  it('indicador sem meta fica sem carinha, não com carinha de zero', async () => {
    render(<Monitor />);
    const lead = await quadro('lead');
    expect(lead.getByText('0')).toBeInTheDocument();
    expect(lead.getByRole('img', { name: 'sem meta definida' })).toBeInTheDocument();
  });

  it('valor indefinido aparece como travessão, não como zero', async () => {
    /* Ticket médio sem contrato nenhum é indefinido; "R$ 0" seria uma
       afirmação sobre o mês. */
    const p = painel();
    p.indicadores = p.indicadores.map((i) => (i.chave === 'ticket_medio'
      ? { ...i, formato: 'moeda', resultado: null, meta: 450 } : i));
    responder(p);
    render(<Monitor />);
    const tm = await screen.findByRole('region', { name: 'ticket_medio' });
    // O resultado é o travessão; a meta ao lado continua escrita. Em taxa,
    // meta de hoje e meta do mês são a mesma.
    expect(tm).toHaveTextContent('— / —');
    expect(tm).toHaveTextContent('mês: 450');
  });

  it('dinheiro grande vira valor curto, legível de longe', async () => {
    const p = painel();
    p.indicadores = p.indicadores.map((i) => (i.chave === 'nmrr'
      ? { ...i, formato: 'moeda', resultado: 39312, meta: 67000, carinha: 'neutro' } : i));
    responder(p);
    render(<Monitor />);
    const nmrr = await quadro('nmrr');
    expect(nmrr.getByText('39,3 K')).toBeInTheDocument();
    expect(nmrr.getByText('mês: 67,0 K')).toBeInTheDocument();
  });

  it('no-show aparece em percentual', async () => {
    const p = painel();
    p.indicadores = p.indicadores.map((i) => (i.chave === 'noshow'
      ? { ...i, formato: 'percentual', natureza: 'taxa_inversa',
        resultado: 11, meta: 30, meta_mtd: 30, carinha: 'muito_feliz' } : i));
    responder(p);
    render(<Monitor />);
    const ns = await quadro('noshow');
    expect(ns.getByText('11%')).toBeInTheDocument();
    // Em taxa a meta de hoje É a do mês: repetir a linha gastaria espaço.
    expect(ns.queryByText('mês: 30%')).not.toBeInTheDocument();
  });
});

describe('Monitor — atualização sozinho', () => {
  it('busca de novo sem ninguém dar F5', async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    render(<Monitor />);
    await screen.findByText('setembro de 2026');
    expect(mockGet.mock.calls.filter(([u]) => u === '/monitor/painel')).toHaveLength(1);

    await act(async () => { await vi.advanceTimersByTimeAsync(60000); });
    expect(
      mockGet.mock.calls.filter(([u]) => u === '/monitor/painel').length
    ).toBeGreaterThanOrEqual(2);
  });

  it('aba escondida não busca; ao voltar, busca na hora', async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    render(<Monitor />);
    await screen.findByText('setembro de 2026');
    const antes = mockGet.mock.calls.filter(([u]) => u === '/monitor/painel').length;

    const spy = vi.spyOn(document, 'hidden', 'get').mockReturnValue(true);
    await act(async () => { await vi.advanceTimersByTimeAsync(120000); });
    expect(mockGet.mock.calls.filter(([u]) => u === '/monitor/painel')).toHaveLength(antes);

    spy.mockReturnValue(false);
    await act(async () => {
      document.dispatchEvent(new Event('visibilitychange'));
      await Promise.resolve();
    });
    expect(
      mockGet.mock.calls.filter(([u]) => u === '/monitor/painel').length
    ).toBeGreaterThan(antes);
    spy.mockRestore();
  });

  it('mostra a hora da última leitura', async () => {
    render(<Monitor />);
    // 13:45:09 UTC no fuso do runner (UTC no CI): a hora existe e é a da leitura.
    expect(await screen.findByLabelText(/^Atualizado às/)).toBeInTheDocument();
  });

  it('erro na atualização não apaga o painel da parede', async () => {
    render(<Monitor />);
    await screen.findByText('setembro de 2026');
    mockGet.mockRejectedValue({ response: { data: { detail: 'Servidor fora' } } });
    fireEvent.click(screen.getByLabelText('Atualizar agora'));

    expect(await screen.findByText(/Servidor fora/)).toBeInTheDocument();
    // Os quadros continuam lá, com o último dado bom.
    expect(screen.getByRole('region', { name: 'lead' })).toBeInTheDocument();
    expect(screen.getByText('setembro de 2026')).toBeInTheDocument();
  });

  it('erro na PRIMEIRA leitura mostra o erro no lugar do painel', async () => {
    mockGet.mockRejectedValue(new Error('offline'));
    render(<Monitor />);
    expect(await screen.findByText(/Não foi possível atualizar o painel/)).toBeInTheDocument();
    expect(screen.queryByRole('region', { name: 'lead' })).not.toBeInTheDocument();
  });
});

describe('Monitor — metas e calendário', () => {
  it('gestão abre a configuração com as metas e os feriados', async () => {
    render(<Monitor />);
    fireEvent.click(await screen.findByText('Metas e calendário'));

    expect(await screen.findByLabelText('LEAD — lead')).toHaveValue('276');
    expect(screen.getByText('07/09/2026')).toBeInTheDocument();
    expect(screen.getByText('Independência do Brasil')).toBeInTheDocument();
    expect(mockGet).toHaveBeenCalledWith('/monitor/metas', { params: { ano: 2026, mes: 9 } });
  });

  it('salvar manda todas as metas de uma vez; vazio apaga', async () => {
    render(<Monitor />);
    fireEvent.click(await screen.findByText('Metas e calendário'));
    const campo = await screen.findByLabelText('LEAD — lead');
    fireEvent.change(campo, { target: { value: '300' } });
    fireEvent.click(screen.getByText('Salvar metas'));

    await waitFor(() => expect(mockPut).toHaveBeenCalled());
    const [url, corpo] = mockPut.mock.calls[0];
    expect(url).toBe('/monitor/metas');
    expect(corpo.ano).toBe(2026);
    expect(corpo.mes).toBe(9);
    const porChave = Object.fromEntries(corpo.metas.map((m) => [m.indicador, m.valor]));
    expect(porChave.lead).toBe(300);
    expect(porChave.apre).toBeNull();     // campo em branco apaga
    expect(corpo.metas).toHaveLength(10);
  });

  it('marca um dia sem expediente e carrega os nacionais', async () => {
    render(<Monitor />);
    fireEvent.click(await screen.findByText('Metas e calendário'));
    await screen.findByLabelText('LEAD — lead');

    fireEvent.change(screen.getByLabelText('Data'), { target: { value: '2026-10-15' } });
    fireEvent.change(screen.getByLabelText('Motivo'), { target: { value: 'Aniversário' } });
    fireEvent.click(screen.getByText('Marcar'));
    await waitFor(() => expect(mockPost).toHaveBeenCalledWith('/monitor/feriados', {
      data: '2026-10-15', motivo: 'Aniversário',
    }));

    fireEvent.click(screen.getByText('Carregar feriados nacionais'));
    await waitFor(() => expect(mockPost).toHaveBeenCalledWith(
      '/monitor/feriados/nacionais', null, { params: { ano: 2026 } },
    ));
  });

  it('remove um dia marcado', async () => {
    render(<Monitor />);
    fireEvent.click(await screen.findByText('Metas e calendário'));
    fireEvent.click(await screen.findByLabelText('Remover 07/09/2026'));
    await waitFor(() => expect(mockDelete).toHaveBeenCalledWith('/monitor/feriados/7'));
  });

  it('quem não é gestão não vê o botão de metas', async () => {
    mockGetUser.mockReturnValue({ id: 'u2', nome: 'Aline', cargo: 'EV' });
    render(<Monitor />);
    await screen.findByText('setembro de 2026');
    expect(screen.queryByText('Metas e calendário')).not.toBeInTheDocument();
  });
});

describe('Monitor — tela cheia', () => {
  it('pede tela cheia para o painel e o botão passa a oferecer a saída', async () => {
    const pedir = vi.fn().mockImplementation(() => {
      // O navegador é quem manda: o estado vem do evento, não do clique.
      Object.defineProperty(document, 'fullscreenElement', {
        value: {}, configurable: true,
      });
      document.dispatchEvent(new Event('fullscreenchange'));
      return Promise.resolve();
    });
    const sair = vi.fn().mockImplementation(() => {
      Object.defineProperty(document, 'fullscreenElement', {
        value: null, configurable: true,
      });
      document.dispatchEvent(new Event('fullscreenchange'));
      return Promise.resolve();
    });
    Element.prototype.requestFullscreen = pedir;
    document.exitFullscreen = sair;

    render(<Monitor />);
    fireEvent.click(await screen.findByLabelText('Tela cheia'));
    await waitFor(() => expect(pedir).toHaveBeenCalled());

    fireEvent.click(await screen.findByLabelText('Sair da tela cheia'));
    await waitFor(() => expect(sair).toHaveBeenCalled());
    expect(await screen.findByLabelText('Tela cheia')).toBeInTheDocument();

    delete Element.prototype.requestFullscreen;
    delete document.exitFullscreen;
  });

  it('navegador que recusa não derruba o painel', async () => {
    Element.prototype.requestFullscreen = vi.fn().mockRejectedValue(new Error('nope'));
    render(<Monitor />);
    fireEvent.click(await screen.findByLabelText('Tela cheia'));
    expect(await screen.findByText(/recusou a tela cheia/)).toBeInTheDocument();
    // Os quadros continuam na parede.
    expect(screen.getByRole('region', { name: 'lead' })).toBeInTheDocument();
    delete Element.prototype.requestFullscreen;
  });
});
