// web/src/tests/AvaliacaoRoteiro.test.jsx
//
// O scorecard da reunião contra o Roteiro de Vendas. As promessas:
//
//   1. não elegível (parceiro, no-show) ou 404: nenhum bloco
//   2. na fila / erro: o motivo e o botão de avaliar
//   3. pronta: nota x/20, fala do vendedor, foco, pontos; itens a um clique
//   4. vendedor só lê; gestão ajusta item (0/1/2), desfaz e valida
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, fireEvent, cleanup, waitFor } from '@testing-library/react';

const mockGet = vi.fn();
const mockPost = vi.fn();
const mockPatch = vi.fn();
const mockDelete = vi.fn();

vi.mock('../api', () => ({
  default: {
    get: (...a) => mockGet(...a),
    post: (...a) => mockPost(...a),
    patch: (...a) => mockPatch(...a),
    delete: (...a) => mockDelete(...a),
  },
  getUser: () => null,
}));

import AvaliacaoRoteiro, { formatarNota } from '../components/crm/AvaliacaoRoteiro';

const URL = '/crm/agenda/tarefas/t1/avaliacao';

const NOMES = [
  'Preparação', 'Contrato de abertura', 'Perguntas de Situação', 'Perguntas de Problema',
  'Perguntas de Implicação', 'Resumo de confirmação', 'GPCT', 'Apresentação ligada às dores',
  'Objeções com LAER', 'Próximo passo com data',
];
const NOTAS = [2, 2, 1, 1, 0, 2, 1, 1, null, 2];

function itens(extra = {}) {
  return NOMES.map((nome, i) => ({
    item: i + 1,
    nome,
    etapa: 'Etapa',
    o_que_procurar: 'o que procurar',
    criterios: ['zero', 'um', 'dois'],
    nota: NOTAS[i],
    nota_ia: NOTAS[i],
    nota_gestor: null,
    evidencia: NOTAS[i] ? 'o que te incomoda hoje' : null,
    justificativa: `Justificativa ${i + 1}`,
    sugestao: `Sugestão ${i + 1}`,
    descartado: NOTAS[i] === null ? 'Trecho citado não foi encontrado na transcrição.' : null,
    ajustada_por_nome: null,
    ajustada_em: null,
    ...(extra[i + 1] || {}),
  }));
}

function estado(extra = {}) {
  return {
    reuniao_id: 'r1',
    tarefa_id: 't1',
    status: 'pronta',
    motivo: null,
    versao_roteiro: '2026-09-30',
    nota_total: 12,
    nota_maxima: 20,
    faixa: 'media',
    meta: 15,
    vendedor_nome: 'Bruno',
    fala_vendedor_pct: 62.5,
    meta_fala_pct: 40,
    resumo: 'Boa abertura, diagnóstico raso.',
    foco_proxima: 'Perguntar o custo do problema.',
    pontos_fortes: [{ texto: 'Usou a pesquisa', evidencia: 'abriram a unidade' }],
    pontos_melhorar: [{
      texto: 'Faltou implicação', evidencia: null, como_fazer: 'Pergunte o custo do atraso.',
    }],
    modelo: 'claude',
    erro: null,
    tentativas: 1,
    gerada_em: '2026-10-01T12:00:00Z',
    validada: false,
    validada_por_nome: null,
    validada_em: null,
    ajustada: false,
    itens: itens(),
    ia_configurada: true,
    pode_gerar: true,
    pode_ajustar: false,
    ...extra,
  };
}

function montar(dados) {
  mockGet.mockImplementation((url) => {
    if (url === URL) return Promise.resolve({ data: dados });
    return Promise.reject(new Error(`GET inesperado: ${url}`));
  });
  return render(<AvaliacaoRoteiro tarefa={{ id: 't1' }} />);
}

beforeEach(() => {
  mockGet.mockReset();
  mockPost.mockReset();
  mockPatch.mockReset();
  mockDelete.mockReset();
});
afterEach(cleanup);

describe('AvaliacaoRoteiro — quando some', () => {
  it('não elegível não mostra bloco', async () => {
    const { container } = montar({ status: 'nao_elegivel', motivo: 'Reunião de parceiro…' });
    await waitFor(() => expect(mockGet).toHaveBeenCalledWith(URL));
    expect(container).toBeEmptyDOMElement();
  });

  it('404 não é erro na tela', async () => {
    mockGet.mockRejectedValue({ response: { status: 404 } });
    const { container } = render(<AvaliacaoRoteiro tarefa={{ id: 't1' }} />);
    await waitFor(() => expect(mockGet).toHaveBeenCalled());
    expect(container).toBeEmptyDOMElement();
  });
});

describe('AvaliacaoRoteiro — antes de pronta', () => {
  it('na fila: motivo e avaliar agora', async () => {
    montar(estado({
      status: 'na_fila', motivo: 'Na fila: a avaliação sai na próxima passada do coletor.',
      nota_total: null, faixa: null, itens: [],
    }));
    expect(await screen.findByText(/Na fila/)).toBeInTheDocument();
    mockPost.mockResolvedValue({ data: estado() });
    fireEvent.click(screen.getByRole('button', { name: /Avaliar agora/ }));
    await waitFor(() => expect(mockPost).toHaveBeenCalledWith(`${URL}/gerar`));
    expect(await screen.findByTestId('nota-total')).toHaveTextContent('12/20');
  });

  it('erro da IA aparece e permite tentar de novo', async () => {
    montar(estado({
      status: 'erro', erro: 'A IA respondeu HTTP 529.', nota_total: null, itens: [],
    }));
    expect(await screen.findByText('A IA respondeu HTTP 529.')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /Avaliar agora/ })).toBeInTheDocument();
  });

  it('409 do backend aparece com o texto dele', async () => {
    montar(estado({ status: 'na_fila', nota_total: null, itens: [] }));
    mockPost.mockRejectedValue({
      response: { status: 409, data: { detail: 'Esta reunião já está sendo avaliada.' } },
    });
    fireEvent.click(await screen.findByRole('button', { name: /Avaliar agora/ }));
    expect(await screen.findByText('Esta reunião já está sendo avaliada.')).toBeInTheDocument();
  });
});

describe('AvaliacaoRoteiro — pronta', () => {
  it('mostra nota, fala, foco e pontos; itens fechados até pedir', async () => {
    montar(estado());
    expect(await screen.findByTestId('nota-total')).toHaveTextContent('12/20');
    expect(screen.getByText('Sugestão da IA')).toBeInTheDocument();
    expect(screen.getByTestId('fala-vendedor')).toHaveTextContent('62,5%');
    expect(screen.getByTestId('fala-vendedor').className).toContain('text-hipo-warning');
    expect(screen.getByText('Perguntar o custo do problema.')).toBeInTheDocument();
    expect(screen.getByText('Usou a pesquisa')).toBeInTheDocument();
    expect(screen.getByText(/Pergunte o custo do atraso/)).toBeInTheDocument();
    expect(screen.queryByTestId('itens-scorecard')).toBeNull();
    // Vendedor: não valida.
    expect(screen.queryByRole('button', { name: /^Validar$/ })).toBeNull();

    fireEvent.click(screen.getByRole('button', { name: /Ver os 10 itens/ }));
    expect(screen.getByTestId('itens-scorecard').querySelectorAll('li')).toHaveLength(10);
    fireEvent.click(screen.getByRole('button', { name: /Objeções com LAER/ }));
    expect(screen.getByText(/Nota da IA descartada/)).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: /Perguntas de Problema/ }));
    expect(screen.getAllByText(/o que te incomoda hoje/).length).toBeGreaterThan(0);
    expect(screen.getByText('Sugestão 4')).toBeInTheDocument();
  });

  it('vendedor não identificado não vira número', async () => {
    montar(estado({ fala_vendedor_pct: null }));
    expect(await screen.findByText('vendedor não identificado')).toBeInTheDocument();
    expect(screen.getByTestId('fala-vendedor')).toHaveTextContent('—');
  });

  it('reavaliação que falhou avisa e mantém a nota', async () => {
    montar(estado({ erro: 'Caiu.' }));
    expect(await screen.findByText(/A última reavaliação falhou \(Caiu\.\)/)).toBeInTheDocument();
    expect(screen.getByTestId('nota-total')).toHaveTextContent('12/20');
  });

  it('validada mostra o selo e não oferece avaliar de novo', async () => {
    montar(estado({ validada: true, validada_por_nome: 'Tulio', pode_gerar: false }));
    expect(await screen.findByText('Validada por Tulio')).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /Avaliar de novo/ })).toBeNull();
  });
});

describe('AvaliacaoRoteiro — gestão', () => {
  it('ajusta a nota de um item', async () => {
    montar(estado({ pode_ajustar: true }));
    fireEvent.click(await screen.findByRole('button', { name: /Ver os 10 itens/ }));
    mockPatch.mockResolvedValue({
      data: estado({
        pode_ajustar: true, nota_total: 14, ajustada: true,
        itens: itens({ 9: { nota: 2, nota_gestor: 2, ajustada_por_nome: 'Tulio', ajustada_em: 'x' } }),
      }),
    });
    fireEvent.click(screen.getByRole('button', { name: 'Dar nota 2 ao item 9' }));
    await waitFor(() => expect(mockPatch).toHaveBeenCalledWith(`${URL}/itens/9`, { nota: 2 }));
    expect(await screen.findByTestId('nota-total')).toHaveTextContent('14/20');
    expect(screen.getByText('Ajustada pela gestão')).toBeInTheDocument();
  });

  it('nota já ativa não dispara chamada', async () => {
    montar(estado({ pode_ajustar: true }));
    fireEvent.click(await screen.findByRole('button', { name: /Ver os 10 itens/ }));
    fireEvent.click(screen.getByRole('button', { name: 'Dar nota 2 ao item 1' }));
    expect(mockPatch).not.toHaveBeenCalled();
  });

  it('desfaz o ajuste e volta para a nota da IA', async () => {
    montar(estado({
      pode_ajustar: true, ajustada: true,
      itens: itens({ 5: { nota: 1, nota_gestor: 1, ajustada_por_nome: 'Tulio', ajustada_em: 'x' } }),
    }));
    fireEvent.click(await screen.findByRole('button', { name: /Ver os 10 itens/ }));
    fireEvent.click(screen.getByRole('button', { name: /Perguntas de Implicação/ }));
    mockPatch.mockResolvedValue({ data: estado({ pode_ajustar: true }) });
    fireEvent.click(screen.getByRole('button', { name: 'Voltar para a nota da IA' }));
    await waitFor(() => expect(mockPatch).toHaveBeenCalledWith(`${URL}/itens/5`, { nota: null }));
  });

  it('valida e tira a validação', async () => {
    montar(estado({ pode_ajustar: true }));
    mockPost.mockResolvedValue({
      data: estado({ pode_ajustar: true, validada: true, validada_por_nome: 'Tulio', pode_gerar: false }),
    });
    fireEvent.click(await screen.findByRole('button', { name: /^Validar$/ }));
    await waitFor(() => expect(mockPost).toHaveBeenCalledWith(`${URL}/validar`));
    expect(await screen.findByText('Validada por Tulio')).toBeInTheDocument();

    mockDelete.mockResolvedValue({ data: estado({ pode_ajustar: true }) });
    fireEvent.click(screen.getByRole('button', { name: /Tirar validação/ }));
    await waitFor(() => expect(mockDelete).toHaveBeenCalledWith(`${URL}/validar`));
    expect(await screen.findByText('Sugestão da IA')).toBeInTheDocument();
  });
});

describe('formatarNota', () => {
  it('uma casa, vírgula, travessão para vazio', () => {
    expect(formatarNota(12.5)).toBe('12,5');
    expect(formatarNota(15)).toBe('15');
    expect(formatarNota(null)).toBe('—');
  });
});
