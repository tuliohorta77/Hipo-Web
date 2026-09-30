// web/src/tests/RperMonitor.test.jsx
//
// O RPeR no Monitor. Promessas que os testes seguram:
//   1. a prévia mostra os números que vão para o PPT, por squad
//   2. baixar pede o arquivo como blob, com o mês escolhido e a IA ligada
//      só quando o servidor tem chave
//   3. o botão do PDF fica desligado onde não há LibreOffice
//   4. metas: squad e pessoa vão no mesmo PUT; vazio apaga (null); campo
//      inválido trava o Salvar
//   5. o botão RPeR no Monitor abre o modal (gestão)
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import {
  render, screen, fireEvent, cleanup, waitFor, within,
} from '@testing-library/react';

const mockGet = vi.fn();
const mockPut = vi.fn();
const mockPost = vi.fn();

vi.mock('../api', () => ({
  default: {
    get: (...a) => mockGet(...a),
    put: (...a) => mockPut(...a),
    post: (...a) => mockPost(...a),
    delete: vi.fn(),
  },
  getUser: () => ({ id: 'u1', nome: 'Tulio Horta', cargo: 'Franqueado' }),
}));

import RperMonitor, {
  mesesAnteriores, numeroDoCampo, mesSeguinte, rotuloMes,
} from '../components/monitor/RperMonitor';

const STATUS = {
  pptx_disponivel: true,
  pdf_disponivel: false,
  ia_configurada: true,
  ano: 2026,
  mes: 8,
  rotulo_fechado: 'agosto/2026',
  rotulo_novo: 'setembro/2026',
};

function linha(chave, rotulo, realizado_txt, extra = {}) {
  return {
    chave, rotulo, formato: 'inteiro', realizado: 0, meta: null, atingimento: null,
    realizado_txt, meta_txt: '', atingimento_txt: '', carinha: null, posicao: false,
    ...extra,
  };
}

const PREVIA = {
  ano: 2026, mes: 8,
  squads: [
    { squad: 'EC', nome: 'EC', total: [linha('mrr', 'MRR FECHADO', 'R$ 450')], pessoas: [] },
    {
      squad: 'SDR',
      nome: 'SDR',
      total: [linha('agendamentos', 'AGENDAMENTOS', '48', {
        meta_txt: '80', atingimento_txt: '60%', carinha: 'triste',
      })],
      pessoas: [{
        id: 'k1', nome: 'Kethlleen Gomes',
        indicadores: [{ chave: 'agendamentos', realizado_txt: '30' }],
      }],
    },
    { squad: 'EV', nome: 'EV', total: [linha('nmrr', 'NMRR', 'R$ 453')], pessoas: [] },
  ],
};

const METAS = {
  ano: 2026, mes: 9, rotulo: 'setembro/2026',
  squads: [
    {
      squad: 'EC', nome: 'EC',
      indicadores: [{ chave: 'mrr', rotulo: 'MRR FECHADO', formato: 'moeda', fonte: 'x' }],
      squad_metas: { mrr: 5000 },
      pessoas: [{ id: 'a1', nome: 'Aline Martins', metas: { mrr: null } }],
    },
    {
      squad: 'SDR', nome: 'SDR',
      indicadores: [{ chave: 'agendamentos', rotulo: 'AGENDAMENTOS', formato: 'inteiro', fonte: 'x' }],
      squad_metas: { agendamentos: 80 },
      pessoas: [{ id: 'k1', nome: 'Kethlleen Gomes', metas: { agendamentos: 40 } }],
    },
    {
      squad: 'EV', nome: 'EV',
      indicadores: [{ chave: 'nmrr', rotulo: 'NMRR', formato: 'moeda', fonte: 'x' }],
      squad_metas: { nmrr: null },
      pessoas: [],
    },
  ],
};

function responder() {
  mockGet.mockImplementation((url) => {
    if (url === '/rper/status') return Promise.resolve({ data: STATUS });
    if (url === '/rper/previa') return Promise.resolve({ data: PREVIA });
    if (url === '/rper/metas') return Promise.resolve({ data: METAS });
    if (url === '/rper/arquivo') {
      return Promise.resolve({
        data: new Blob(['pptx']),
        headers: {
          'content-disposition': 'attachment; filename="RPeR_SETEMBRO_2026_CONTROLLER_MEDSEG.pptx"',
          'x-rper-ia': '1',
          'x-rper-textos-descartados': '2',
        },
      });
    }
    return Promise.resolve({ data: {} });
  });
}

beforeEach(() => {
  mockGet.mockReset();
  mockPut.mockReset();
  mockPost.mockReset();
  responder();
  global.URL.createObjectURL = vi.fn(() => 'blob:x');
  global.URL.revokeObjectURL = vi.fn();
});

afterEach(() => cleanup());

describe('helpers', () => {
  it('lista os meses do mais recente para trás, virando o ano', () => {
    const m = mesesAnteriores(2026, 2, 3);
    expect(m.map((x) => x.valor)).toEqual(['2026-2', '2026-1', '2025-12']);
  });

  it('mês seguinte e rótulo', () => {
    expect(mesSeguinte(2026, 12)).toEqual({ ano: 2027, mes: 1 });
    expect(rotuloMes(2026, 3)).toBe('março/2026');
  });

  it('lê número como se digita aqui', () => {
    expect(numeroDoCampo('')).toBeNull();
    expect(numeroDoCampo('7.200')).toBe(7200);
    expect(numeroDoCampo('1.234,50')).toBe(1234.5);
    expect(numeroDoCampo('1.5')).toBe(1.5);
    expect(numeroDoCampo('33,33')).toBe(33.33);
    expect(numeroDoCampo('R$ 5.000')).toBe(5000);
    expect(numeroDoCampo('10%')).toBe(10);
    expect(numeroDoCampo('abc')).toBeNaN();
    expect(numeroDoCampo('-3')).toBeNaN();
  });
});

describe('RperMonitor — Gerar', () => {
  it('mostra a prévia do squad escolhido', async () => {
    render(<RperMonitor aberto onFechar={() => {}} />);
    expect(await screen.findByText(/Resultados de agosto\/2026/)).toBeInTheDocument();
    fireEvent.click(await screen.findByTestId('tab-SDR'));
    const tabela = await screen.findByRole('table', { name: 'Prévia SDR' });
    expect(within(tabela).getByText('AGENDAMENTOS')).toBeInTheDocument();
    expect(within(tabela).getByText('48')).toBeInTheDocument();
    expect(within(tabela).getByText('60%')).toBeInTheDocument();
    expect(within(tabela).getByText('30')).toBeInTheDocument();
    expect(mockGet).toHaveBeenCalledWith('/rper/previa', { params: { ano: 2026, mes: 8 } });
  });

  it('baixa o PPTX com IA e avisa os textos descartados', async () => {
    render(<RperMonitor aberto onFechar={() => {}} />);
    const botao = await screen.findByText('Baixar PPTX');
    await waitFor(() => expect(botao.closest('button')).not.toBeDisabled());
    fireEvent.click(botao);
    await waitFor(() => expect(mockGet).toHaveBeenCalledWith('/rper/arquivo', {
      params: { ano: 2026, mes: 8, formato: 'pptx', ia: true },
      responseType: 'blob',
    }));
    expect(await screen.findByText(/2 textos da IA citavam número/)).toBeInTheDocument();
  });

  it('oferece o mês corrente como prévia parcial, mas abre no mês fechado', async () => {
    render(<RperMonitor aberto onFechar={() => {}} />);
    const seletor = await screen.findByLabelText('Mês dos resultados');
    await waitFor(() => expect(seletor.value).toBe('2026-8'));
    const opcoes = within(seletor).getAllByRole('option').map((o) => o.textContent);
    expect(opcoes[0]).toBe('setembro/2026 (parcial, até hoje)');
    expect(opcoes[1]).toBe('agosto/2026');
    fireEvent.change(seletor, { target: { value: '2026-9' } });
    expect(await screen.findByText(/Mês ainda aberto/)).toBeInTheDocument();
    await waitFor(() => expect(mockGet).toHaveBeenCalledWith(
      '/rper/previa', { params: { ano: 2026, mes: 9 } },
    ));
  });

  it('sem LibreOffice, o PDF fica desligado', async () => {
    render(<RperMonitor aberto onFechar={() => {}} />);
    await screen.findByText('Baixar PPTX');
    await waitFor(() => expect(screen.getByText('Baixar PDF').closest('button')).toBeDisabled());
  });

  it('erro do servidor em blob vira a mensagem dele', async () => {
    mockGet.mockImplementation((url) => {
      if (url === '/rper/arquivo') {
        const blob = new Blob([JSON.stringify({ detail: 'python-pptx não está instalado' })]);
        return Promise.reject({ response: { status: 503, data: blob } });
      }
      if (url === '/rper/status') return Promise.resolve({ data: STATUS });
      return Promise.resolve({ data: PREVIA });
    });
    render(<RperMonitor aberto onFechar={() => {}} />);
    const botao = await screen.findByText('Baixar PPTX');
    await waitFor(() => expect(botao.closest('button')).not.toBeDisabled());
    fireEvent.click(botao);
    expect(await screen.findByText('python-pptx não está instalado')).toBeInTheDocument();
  });
});

describe('RperMonitor — Metas', () => {
  async function abrirMetas() {
    render(<RperMonitor aberto onFechar={() => {}} />);
    fireEvent.click(await screen.findByTestId('tab-metas'));
    await waitFor(() => expect(mockGet).toHaveBeenCalledWith(
      '/rper/metas', { params: { ano: 2026, mes: 9 } },
    ));
  }

  it('abre no mês do planejamento e salva squad e pessoa no mesmo PUT', async () => {
    mockPut.mockResolvedValue({ data: METAS });
    await abrirMetas();
    fireEvent.click(screen.getByTestId('tab-SDR'));
    const squad = await screen.findByLabelText('AGENDAMENTOS — squad');
    expect(squad.value).toBe('80');
    fireEvent.change(squad, { target: { value: '90' } });
    fireEvent.change(screen.getByLabelText('AGENDAMENTOS — Kethlleen Gomes'), {
      target: { value: '' },
    });
    fireEvent.click(screen.getByText('Salvar metas'));
    await waitFor(() => expect(mockPut).toHaveBeenCalled());
    const [url, corpo] = mockPut.mock.calls[0];
    expect(url).toBe('/rper/metas');
    expect(corpo.ano).toBe(2026);
    expect(corpo.mes).toBe(9);
    expect(corpo.metas).toContainEqual({
      squad: 'SDR', usuario_id: null, indicador: 'agendamentos', valor: 90,
    });
    expect(corpo.metas).toContainEqual({
      squad: 'SDR', usuario_id: 'k1', indicador: 'agendamentos', valor: null,
    });
    expect(await screen.findByText('Metas salvas.')).toBeInTheDocument();
  });

  it('campo inválido trava o salvar', async () => {
    await abrirMetas();
    const campo = await screen.findByLabelText('MRR FECHADO — squad');
    fireEvent.change(campo, { target: { value: 'muito' } });
    expect(screen.getByText('Salvar metas').closest('button')).toBeDisabled();
  });

  it('copia do mês anterior', async () => {
    mockPost.mockResolvedValue({ data: METAS });
    await abrirMetas();
    fireEvent.click(await screen.findByText('Copiar do mês anterior'));
    await waitFor(() => expect(mockPost).toHaveBeenCalledWith(
      '/rper/metas/copiar', null, { params: { ano: 2026, mes: 9 } },
    ));
  });
});
