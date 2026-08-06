// web/src/tests/Layout.test.jsx
//
// Sprint 0: a nav principal está vazia (NAV_ITEMS = []). Os testes cobrem
// o estado sem nav — hamburger e <nav> não renderizam — e o dropdown do
// usuário, que continua sendo o único caminho para Perfil e Sair.
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, fireEvent, cleanup } from '@testing-library/react';
import { MemoryRouter, Routes, Route } from 'react-router-dom';

const mockLogout = vi.fn();
const mockGetUser = vi.fn();
const mockGetModulos = vi.fn();

vi.mock('../api', () => ({
  getUser: () => mockGetUser(),
  getModulos: () => mockGetModulos(),
  logout: () => mockLogout(),
}));

import Layout from '../components/Layout';

function renderLayout(rotaInicial = '/perfil') {
  return render(
    <MemoryRouter initialEntries={[rotaInicial]}>
      <Routes>
        <Route path="/" element={<Layout />}>
          <Route path="perfil" element={<div>conteudo-perfil</div>} />
        </Route>
      </Routes>
    </MemoryRouter>
  );
}

beforeEach(() => {
  mockLogout.mockClear();
  mockGetUser.mockReturnValue({
    nome: 'Tulio Horta',
    email: 'tulio@teste.com',
    cargo: 'Franqueado',
  });
  mockGetModulos.mockReturnValue(['perfil', 'usuarios']);
});

afterEach(cleanup);

describe('Layout — nav vazia (Sprint 0)', () => {
  it('renderiza o conteúdo da rota filha', () => {
    renderLayout();
    expect(screen.getByText('conteudo-perfil')).toBeInTheDocument();
  });

  it('não renderiza a nav principal quando não há itens visíveis', () => {
    renderLayout();
    expect(screen.queryByLabelText('Navegação principal')).not.toBeInTheDocument();
  });

  it('não renderiza o botão hamburger quando não há itens visíveis', () => {
    renderLayout();
    expect(screen.queryByLabelText('Abrir menu')).not.toBeInTheDocument();
  });

  it('não mostra nenhum link de tela removida', () => {
    renderLayout();
    for (const label of ['PEX', 'POs', 'BD Ativados', 'Contadores', 'Clientes', 'Vendas', 'Agendamento', 'Bastões', 'Metas']) {
      expect(screen.queryByText(label)).not.toBeInTheDocument();
    }
  });
});

describe('Layout — dropdown do usuário', () => {
  it('mostra nome e cargo do usuário logado', () => {
    renderLayout();
    expect(screen.getByText('Tulio Horta')).toBeInTheDocument();
    expect(screen.getByText('Franqueado')).toBeInTheDocument();
  });

  it('abre o menu e mostra Perfil e Sair', () => {
    renderLayout();
    fireEvent.click(screen.getByLabelText('Menu do usuário'));
    expect(screen.getByRole('menu')).toBeInTheDocument();
    expect(screen.getByText('Perfil')).toBeInTheDocument();
    expect(screen.getByText('Sair')).toBeInTheDocument();
  });

  it('chama logout ao clicar em Sair', () => {
    renderLayout();
    fireEvent.click(screen.getByLabelText('Menu do usuário'));
    fireEvent.click(screen.getByText('Sair'));
    expect(mockLogout).toHaveBeenCalledTimes(1);
  });

  it('fecha o menu ao pressionar Esc', () => {
    renderLayout();
    fireEvent.click(screen.getByLabelText('Menu do usuário'));
    expect(screen.getByRole('menu')).toBeInTheDocument();
    fireEvent.keyDown(document, { key: 'Escape' });
    expect(screen.queryByRole('menu')).not.toBeInTheDocument();
  });

  it('não renderiza o avatar quando não há usuário', () => {
    mockGetUser.mockReturnValue(null);
    mockGetModulos.mockReturnValue([]);
    renderLayout();
    expect(screen.queryByLabelText('Menu do usuário')).not.toBeInTheDocument();
  });
});

describe('Layout — cargo sem módulos', () => {
  it('não quebra e mantém o dropdown para cargo extinto', () => {
    mockGetUser.mockReturnValue({ nome: 'Ex Gerente', email: 'ex@teste.com', cargo: 'Gerente' });
    mockGetModulos.mockReturnValue([]);
    renderLayout();
    expect(screen.getByText('conteudo-perfil')).toBeInTheDocument();
    expect(screen.getByLabelText('Menu do usuário')).toBeInTheDocument();
    expect(screen.queryByLabelText('Navegação principal')).not.toBeInTheDocument();
  });
});
