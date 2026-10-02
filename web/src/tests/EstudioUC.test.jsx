// web/src/tests/EstudioUC.test.jsx
//
// O estúdio da gestão. O que estes testes seguram:
//   1. trilhas agrupadas pelos três pilares, com status e cargos
//   2. nova trilha vai para a API e abre o editor dela
//   3. o editor salva o manual da função só com os cargos marcados
//   4. o erro do servidor (publicar trilha vazia) aparece como veio
//   5. a aba Time leva à UC da pessoa em modo leitura
//   6. operacional que digita a URL vê o aviso do servidor
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, fireEvent, cleanup, within, waitFor } from '@testing-library/react';
import { MemoryRouter, Route, Routes } from 'react-router-dom';

const mockGet = vi.fn();
const mockPost = vi.fn();
const mockPatch = vi.fn();
const mockPut = vi.fn();
const mockDelete = vi.fn();
vi.mock('../api', () => ({
  default: {
    get: (...a) => mockGet(...a), post: (...a) => mockPost(...a),
    patch: (...a) => mockPatch(...a), put: (...a) => mockPut(...a), delete: (...a) => mockDelete(...a),
  },
  getUser: () => ({ id: 'g1', nome: 'Tulio', cargo: 'Franqueado' }),
}));

import Estudio from '../pages/uc/Estudio';

const VOCAB = {
  pilares: { tecnica: 'Técnica', metodo: 'Método', energia: 'Energia' },
  reforcos: { roteiro: 'Roteiro de vendas' },
  cargos: ['Franqueado', 'ADM', 'EC', 'SDR', 'EV', 'EP'],
  provedores: { youtube: 'YouTube' },
  status_trilha: ['rascunho', 'publicada', 'arquivada'],
};

const TRILHA = {
  id: 't1', titulo: 'Normas Regulamentadoras', descricao: 'NR-01 e NR-04', pilar: 'tecnica',
  pilar_rotulo: 'Técnica', reforca: null, status: 'rascunho',
  cargos: [{ cargo: 'EV', obrigatoria: true, prazo_dias: 30, desde: '2026-10-01T00:00:00Z' }],
  aulas_total: 0, aulas_publicadas: 0, concluintes: 0, atualizado_em: '2026-10-01T00:00:00Z',
};

const DETALHE = { ...TRILHA, aulas: [], materiais_disponiveis: true, materiais_problemas: [] };

const TIME = [{
  id: 'u9', nome: 'Jakeline Santana', cargo: 'EV', obrigatorias: 1, obrigatorias_concluidas: 0,
  atrasadas: 1, aulas_total: 6, aulas_concluidas: 2, percentual: 33, proxima_aula: 'GRO e PGR',
}];

function respostasPadrao() {
  mockGet.mockImplementation((url) => {
    if (url === '/uc/estudio/vocabulario') return Promise.resolve({ data: VOCAB });
    if (url === '/uc/estudio/trilhas') return Promise.resolve({ data: [TRILHA] });
    if (url === '/uc/estudio/time') return Promise.resolve({ data: TIME });
    if (url === '/uc/estudio/trilhas/t1') return Promise.resolve({ data: DETALHE });
    return Promise.reject(new Error(`GET inesperado ${url}`));
  });
}

function renderizar(caminho = '/uc/estudio') {
  return render(
    <MemoryRouter initialEntries={[caminho]}>
      <Routes>
        <Route path="/uc/estudio" element={<Estudio />} />
        <Route path="/uc" element={<p>tela da UC</p>} />
      </Routes>
    </MemoryRouter>,
  );
}

// Erro como o axios entrega: um Error com `response` pendurado.
function erroHttp(status, detail) {
  return Object.assign(new Error(`HTTP ${status}`), { response: { status, data: { detail } } });
}

beforeEach(() => {
  [mockGet, mockPost, mockPatch, mockPut, mockDelete].forEach((m) => m.mockReset());
  respostasPadrao();
});
afterEach(cleanup);

describe('Estúdio da UC', () => {
  it('trilhas agrupadas pelos três pilares', async () => {
    renderizar();
    expect(await screen.findByText('Normas Regulamentadoras')).toBeInTheDocument();
    for (const p of ['Técnica', 'Método', 'Energia']) {
      expect(screen.getByRole('heading', { name: p })).toBeInTheDocument();
    }
    expect(screen.getByText('EV*')).toBeInTheDocument();
    expect(screen.getByText('Rascunho')).toBeInTheDocument();
  });

  it('nova trilha vai para a API e abre o editor', async () => {
    mockPost.mockResolvedValue({ data: DETALHE });
    renderizar();
    fireEvent.click(await screen.findByRole('button', { name: /Nova trilha/ }));
    const dialogo = await screen.findByRole('dialog');
    fireEvent.change(within(dialogo).getByLabelText('Título'), { target: { value: 'Roteiro SPIN' } });
    fireEvent.change(within(dialogo).getByLabelText('Pilar'), { target: { value: 'metodo' } });
    fireEvent.click(within(dialogo).getByRole('button', { name: 'Criar trilha' }));
    await waitFor(() => expect(mockPost).toHaveBeenCalledWith('/uc/estudio/trilhas', {
      titulo: 'Roteiro SPIN', pilar: 'metodo', descricao: '', reforca: null,
    }));
    expect(await screen.findByText('Manual da função')).toBeInTheDocument();
  });

  it('manual da função salva só os cargos marcados', async () => {
    mockPut.mockResolvedValue({ data: DETALHE });
    renderizar();
    fireEvent.click(await screen.findByText('Normas Regulamentadoras'));
    await screen.findByText('Manual da função');
    fireEvent.click(screen.getByLabelText('SDR faz a trilha'));
    fireEvent.change(screen.getByLabelText('SDR prazo em dias'), { target: { value: '15' } });
    fireEvent.click(screen.getByRole('button', { name: 'Salvar manual da função' }));
    await waitFor(() => expect(mockPut).toHaveBeenCalledWith('/uc/estudio/trilhas/t1/cargos', {
      cargos: [
        { cargo: 'SDR', obrigatoria: true, prazo_dias: 15 },
        { cargo: 'EV', obrigatoria: true, prazo_dias: 30 },
      ],
    }));
  });

  it('publicar trilha vazia mostra o motivo do servidor', async () => {
    mockPatch.mockRejectedValue(erroHttp(422, 'Trilha sem aula publicada não pode ser publicada: ela apareceria vazia para a equipe.'));
    renderizar();
    fireEvent.click(await screen.findByText('Normas Regulamentadoras'));
    fireEvent.click(await screen.findByRole('button', { name: /Publicar/ }));
    expect(await screen.findByText(/apareceria vazia para a equipe/)).toBeInTheDocument();
  });

  it('aba Time leva à UC da pessoa em modo leitura', async () => {
    renderizar('/uc/estudio?aba=time');
    const linha = await screen.findByTestId('time-u9');
    expect(within(linha).getByText('1 atrasada')).toBeInTheDocument();
    expect(within(linha).getByText('33%')).toBeInTheDocument();
    fireEvent.click(linha);
    expect(await screen.findByText('tela da UC')).toBeInTheDocument();
  });

  it('operacional que digita a URL vê o aviso do servidor', async () => {
    mockGet.mockRejectedValue(erroHttp(403, "Cargo 'EV' não edita conteúdo da Universidade. Fale com a gestão."));
    renderizar();
    expect(await screen.findByText(/não edita conteúdo da Universidade/)).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /Nova trilha/ })).not.toBeInTheDocument();
  });
});
