// web/src/tests/PdiCarreira.test.jsx
//
// Carreira · PDI. O que estes testes seguram:
//   1. abre na próxima ação, com situação e prazo; o dono marca como feita
//   2. colaborador não vê sugestões nem botões de gestão, só o aviso
//   3. gestão confirma sugestão pelo formulário, já preenchido, com a chave
//   4. gestão descarta sugestão
//   5. gestão cria ação do zero e o formulário exige o objetivo
//   6. sem ação, a tela diz o que fazer
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, fireEvent, cleanup, within } from '@testing-library/react';
import { MemoryRouter, Route, Routes } from 'react-router-dom';

const mockGet = vi.fn();
const mockPost = vi.fn();
const mockPatch = vi.fn();
vi.mock('../api', () => ({
  default: {
    get: (...a) => mockGet(...a), post: (...a) => mockPost(...a), patch: (...a) => mockPatch(...a),
  },
  getUser: () => ({ id: 'u1', nome: 'Jakeline', cargo: 'EV' }),
  getModulos: () => ['perfil', 'crm'],
}));

import Pdi, { dataBr } from '../pages/carreira/Pdi';

function acao(extra = {}) {
  return {
    id: 'a1', origem: 'desempenho', origem_rotulo: 'Desempenho', objetivo: 'Dobrar o NMRR',
    o_que_fazer: 'Revisar as propostas abertas toda segunda.', trilha: { id: 't1', titulo: '02 · Roteiro do EV' },
    prazo: '2026-10-20', status: 'aberta',
    situacao: { codigo: 'vence_logo', rotulo: 'Vence logo', dias_restantes: 2 },
    criado_em: '2026-10-05T10:00:00Z', criada_por: 'Tulio', concluida_em: null,
    concluida_automatica: false, nota_conclusao: null, ...extra,
  };
}

function dados(extra = {}) {
  const a = acao();
  return {
    pessoa: { id: 'u1', nome: 'Jakeline', cargo: 'EV' }, modo_leitura: false,
    pode_gerir: false, pode_concluir: true, pessoas: [], hoje: '2026-10-18',
    proxima: a, resumo: { abertas: 1, atrasadas: 0, feitas_no_mes: 2 },
    acoes_abertas: [a], acoes_feitas: [], sugestoes: [], sugestoes_pendentes: 0, trilhas: [],
    ...extra,
  };
}

const SUGESTAO = {
  chave: 'desempenho:2026-10:nmrr', origem: 'desempenho', origem_rotulo: 'Desempenho',
  objetivo: 'NMRR: sair de 40% e chegar a 100% da meta', o_que_fazer: 'Em Oportunidades, revise as abertas.',
  prazo: '2026-10-31', trilha_id: null,
};

function gestao(extra = {}) {
  return dados({
    pessoa: { id: 'u9', nome: 'Jakeline', cargo: 'EV' }, modo_leitura: true, pode_gerir: true, pode_concluir: false,
    pessoas: [{ id: 'u9', nome: 'Jakeline', cargo: 'EV' }], sugestoes: [SUGESTAO], sugestoes_pendentes: 1,
    trilhas: [{ id: 't1', titulo: '02 · Roteiro do EV', pilar_rotulo: 'Método' }], ...extra,
  });
}

function renderizar(caminho = '/carreira/pdi') {
  return render(
    <MemoryRouter initialEntries={[caminho]}>
      <Routes>
        <Route path="/carreira/pdi" element={<Pdi />} />
        <Route path="/uc/trilhas/:id" element={<p>tela da trilha</p>} />
      </Routes>
    </MemoryRouter>,
  );
}

beforeEach(() => { mockGet.mockReset(); mockPost.mockReset(); mockPatch.mockReset(); });
afterEach(cleanup);

describe('PDI', () => {
  it('data em formato brasileiro', () => {
    expect(dataBr('2026-10-20')).toBe('20/10/2026');
  });

  it('abre na próxima ação e o dono marca como feita', async () => {
    mockGet.mockResolvedValue({ data: dados() });
    mockPatch.mockResolvedValue({ data: dados({ proxima: null, acoes_abertas: [], resumo: { abertas: 0, atrasadas: 0, feitas_no_mes: 3 } }) });
    renderizar();
    const card = await screen.findByTestId('pdi-proxima');
    expect(within(card).getByText('Dobrar o NMRR')).toBeInTheDocument();
    expect(within(card).getByText('vence em 2 dia(s)')).toBeInTheDocument();
    fireEvent.click(within(card).getByRole('button', { name: /Feita/ }));
    expect(await screen.findByText('Nenhuma ação aberta')).toBeInTheDocument();
    expect(mockPatch).toHaveBeenCalledWith('/carreira/pdi/acoes/a1', { status: 'concluida' });
  });

  it('colaborador não vê sugestões nem gestão, só o aviso', async () => {
    mockGet.mockResolvedValue({ data: dados({ sugestoes_pendentes: 2 }) });
    renderizar();
    expect(await screen.findByText(/O HIPO tem 2 sugestão/)).toBeInTheDocument();
    expect(screen.queryByTestId('pdi-sugestoes')).toBeNull();
    expect(screen.queryByRole('button', { name: /Nova ação/ })).toBeNull();
    expect(screen.queryByRole('button', { name: /Editar/ })).toBeNull();
  });

  it('abrir a trilha da ação', async () => {
    mockGet.mockResolvedValue({ data: dados() });
    renderizar();
    const card = await screen.findByTestId('pdi-proxima');
    fireEvent.click(within(card).getByRole('button', { name: /Abrir trilha/ }));
    expect(await screen.findByText('tela da trilha')).toBeInTheDocument();
  });

  it('gestão confirma a sugestão pelo formulário preenchido', async () => {
    mockGet.mockResolvedValue({ data: gestao() });
    mockPost.mockResolvedValue({ data: gestao({ sugestoes: [] }) });
    renderizar('/carreira/pdi?usuario_id=u9');
    const sug = await screen.findByTestId('pdi-sugestoes');
    fireEvent.click(within(sug).getByRole('button', { name: 'Confirmar' }));
    expect(screen.getByLabelText('Objetivo').value).toBe(SUGESTAO.objetivo);
    expect(screen.getByLabelText('Prazo').value).toBe('2026-10-31');
    fireEvent.change(screen.getByLabelText('Objetivo'), { target: { value: 'NMRR na meta em outubro' } });
    fireEvent.change(screen.getByLabelText('Trilha de reforço (opcional)'), { target: { value: 't1' } });
    fireEvent.click(screen.getByRole('button', { name: 'Criar ação' }));
    await screen.findByText('Nada a sugerir agora.');
    expect(mockPost).toHaveBeenCalledWith('/carreira/pdi/acoes', {
      objetivo: 'NMRR na meta em outubro', o_que_fazer: SUGESTAO.o_que_fazer, prazo: '2026-10-31',
      trilha_id: 't1', usuario_id: 'u9', chave_origem: SUGESTAO.chave,
    });
  });

  it('gestão descarta a sugestão', async () => {
    mockGet.mockResolvedValue({ data: gestao() });
    mockPost.mockResolvedValue({ data: gestao({ sugestoes: [] }) });
    renderizar('/carreira/pdi?usuario_id=u9');
    const sug = await screen.findByTestId('pdi-sugestoes');
    fireEvent.click(within(sug).getByRole('button', { name: 'Descartar' }));
    await screen.findByText('Nada a sugerir agora.');
    expect(mockPost).toHaveBeenCalledWith('/carreira/pdi/sugestoes/descartar', { usuario_id: 'u9', chave: SUGESTAO.chave });
  });

  it('gestão cria do zero e o formulário exige objetivo', async () => {
    mockGet.mockResolvedValue({ data: gestao() });
    renderizar('/carreira/pdi?usuario_id=u9');
    fireEvent.click(await screen.findByRole('button', { name: /Nova ação/ }));
    fireEvent.click(screen.getByRole('button', { name: 'Criar ação' }));
    expect(screen.getByText('Escreva o objetivo.')).toBeInTheDocument();
    expect(mockPost).not.toHaveBeenCalled();
  });

  it('gestão edita e cancela ações abertas', async () => {
    mockGet.mockResolvedValue({ data: gestao() });
    mockPatch.mockResolvedValue({ data: gestao({ acoes_abertas: [], proxima: null }) });
    renderizar('/carreira/pdi?usuario_id=u9');
    fireEvent.click(await screen.findByRole('button', { name: 'Cancelar Dobrar o NMRR' }));
    await screen.findByText('Nenhuma ação aberta');
    expect(mockPatch).toHaveBeenCalledWith('/carreira/pdi/acoes/a1', { status: 'cancelada' });
  });

  it('erro da API aparece com as abas', async () => {
    mockGet.mockRejectedValue(Object.assign(new Error('x'), { response: { status: 403, data: { detail: 'Só a gestão abre a UC de outra pessoa.' } } }));
    renderizar('/carreira/pdi?usuario_id=u9');
    expect(await screen.findByText('Só a gestão abre a UC de outra pessoa.')).toBeInTheDocument();
    expect(screen.getByRole('navigation', { name: 'Carreira' })).toBeInTheDocument();
  });
});
