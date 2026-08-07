// web/src/tests/Layout.test.jsx
//
// Sprint 1: a nav tem um item (Contas), visível para todo cargo com o módulo
// 'crm'. Os testes cobrem os três estados: com nav, sem nav (cargo extinto)
// e o dropdown do usuário.
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
          <Route path="crm/contas" element={<div>conteudo-contas</div>} />
          <Route path="crm/oportunidades" element={<div>conteudo-oportunidades</div>} />
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
  mockGetModulos.mockReturnValue(['perfil', 'crm', 'usuarios']);
});

afterEach(cleanup);

describe('Layout — nav com o módulo crm', () => {
  it('renderiza o conteúdo da rota filha', () => {
    renderLayout();
    expect(screen.getByText('conteudo-perfil')).toBeInTheDocument();
  });

  it('mostra Oportunidades e Contas na nav', () => {
    renderLayout();
    expect(screen.getByLabelText('Navegação principal')).toBeInTheDocument();
    expect(screen.getAllByText('Oportunidades').length).toBeGreaterThan(0);
    expect(screen.getAllByText('Contas').length).toBeGreaterThan(0);
  });

  it('Oportunidades vem antes de Contas — o funil é a tela do dia a dia', () => {
    renderLayout();
    const nav = screen.getByLabelText('Navegação principal');
    const hrefs = [...nav.querySelectorAll('a')].map((a) => a.getAttribute('href'));
    expect(hrefs).toEqual(['/crm/oportunidades', '/crm/contas']);
  });

  it('renderiza o botão hamburger quando há itens', () => {
    renderLayout();
    expect(screen.getByLabelText('Abrir menu')).toBeInTheDocument();
  });

  it('não mostra nenhum link de tela removida na Sprint 0', () => {
    renderLayout();
    for (const label of ['PEX', 'POs', 'BD Ativados', 'Contadores', 'Vendas', 'Agendamento', 'Bastões', 'Metas']) {
      expect(screen.queryByText(label)).not.toBeInTheDocument();
    }
  });
});

describe('Layout — cargo sem o módulo crm', () => {
  beforeEach(() => {
    mockGetUser.mockReturnValue({ nome: 'Ex Gerente', email: 'ex@teste.com', cargo: 'Gerente' });
    mockGetModulos.mockReturnValue([]);
  });

  it('não renderiza a nav principal', () => {
    renderLayout();
    expect(screen.queryByLabelText('Navegação principal')).not.toBeInTheDocument();
  });

  it('não renderiza o hamburger', () => {
    renderLayout();
    expect(screen.queryByLabelText('Abrir menu')).not.toBeInTheDocument();
  });

  it('ainda alcança Perfil e Sair pelo dropdown', () => {
    renderLayout();
    fireEvent.click(screen.getByLabelText('Menu do usuário'));
    expect(screen.getByText('Perfil')).toBeInTheDocument();
    expect(screen.getByText('Sair')).toBeInTheDocument();
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
