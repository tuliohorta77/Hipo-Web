// web/src/tests/Layout.test.jsx
//
// Fase 3: layout migrado para topbar.
// v1.2.0 etapa 3: adicionado item "Bastões" na nav — visível só pra Gerente+Franqueado.
//
// Os testes existentes (filtragem por módulo) continuam validando que
// os links corretos aparecem na nav — independente do layout ser sidebar
// ou topbar, porque NavLink renderiza <a> em ambos.
//
// O item "Perfil" agora vive no dropdown do usuário, não na nav principal.
//
// Ordem dos itens: Vendas aparece ANTES de Clientes — decisão de UX
// (funil de vendas é a tela do dia-a-dia do EV). Há um teste dedicado
// para essa ordem; quem reverter sem propósito vai ver o CI estourar.

import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, cleanup, fireEvent } from '@testing-library/react'
import { MemoryRouter, Routes, Route } from 'react-router-dom'

// Helper pra mockar getUser + getModulos dinamicamente em cada teste
const userMock = { current: null }
const modulosMock = { current: [] }
const logoutMock = vi.fn()

vi.mock('../api', () => ({
  default: {},
  getUser: () => userMock.current,
  getModulos: () => modulosMock.current,
  logout: () => logoutMock(),
  isAuthenticated: () => true,
}))

import Layout from '../components/Layout'

function renderLayout(initialRoute = '/perfil') {
  return render(
    <MemoryRouter initialEntries={[initialRoute]}>
      <Routes>
        <Route path="/" element={<Layout />}>
          <Route path="perfil" element={<div>conteúdo</div>} />
          <Route path="contadores" element={<div>contadores</div>} />
          <Route path="pex" element={<div>pex</div>} />
        </Route>
      </Routes>
    </MemoryRouter>
  )
}

beforeEach(() => {
  cleanup()
  vi.clearAllMocks()
  logoutMock.mockClear()
})

describe('Layout — filtragem por módulos (nav principal)', () => {
  it('ADM vê PEX, POs, BD, Contadores, Clientes, Metas (mas NÃO Bastões)', () => {
    userMock.current = { nome: 'Tulio', email: 't@hipo.com', cargo: 'ADM' }
    modulosMock.current = ['pex', 'po', 'bd', 'carteira', 'clientes', 'metas', 'usuarios']
    renderLayout()

    const navLinks = screen.getAllByRole('link').map((a) => a.textContent.trim())
    expect(navLinks).toContain('PEX')
    expect(navLinks).toContain('POs')
    expect(navLinks).toContain('BD Ativados')
    expect(navLinks).toContain('Contadores')
    expect(navLinks).toContain('Clientes')
    expect(navLinks).toContain('Vendas')
    expect(navLinks).toContain('Metas')
    // Não tem mais "Carteira" no menu
    expect(navLinks).not.toContain('Carteira')
    // v1.2.0 etapa 3: ADM perdeu Bastões (operações é do Gerente)
    expect(navLinks).not.toContain('Bastões')
  })

  it('Franqueado vê todos os itens (incluindo Bastões)', () => {
    userMock.current = { nome: 'Wellington', email: 'w@omie.com.vc', cargo: 'Franqueado' }
    modulosMock.current = ['pex', 'po', 'bd', 'carteira', 'clientes', 'metas', 'usuarios']
    renderLayout()

    const navLinks = screen.getAllByRole('link').map((a) => a.textContent.trim())
    expect(navLinks).toContain('PEX')
    expect(navLinks).toContain('Contadores')
    expect(navLinks).toContain('Clientes')
    expect(navLinks).toContain('Vendas')
    expect(navLinks).toContain('Bastões')
  })

  it('Farmer vê APENAS Contadores na nav principal', () => {
    userMock.current = { nome: 'Aline', email: 'a@omie.com.vc', cargo: 'Farmer' }
    modulosMock.current = ['carteira']
    renderLayout()

    const navLinks = screen.getAllByRole('link').map((a) => a.textContent.trim())
    expect(navLinks).toContain('Contadores')
    expect(navLinks).not.toContain('PEX')
    expect(navLinks).not.toContain('POs')
    expect(navLinks).not.toContain('BD Ativados')
    expect(navLinks).not.toContain('Metas')
    expect(navLinks).not.toContain('Clientes')
    expect(navLinks).not.toContain('Vendas')
    expect(navLinks).not.toContain('Bastões')
  })

  it('Hunter vê APENAS Contadores na nav principal (NÃO Bastões)', () => {
    userMock.current = { nome: 'Beatriz', email: 'b@omie.com.vc', cargo: 'Hunter' }
    modulosMock.current = ['carteira']
    renderLayout()

    const navLinks = screen.getAllByRole('link').map((a) => a.textContent.trim())
    expect(navLinks).toContain('Contadores')
    expect(navLinks).not.toContain('PEX')
    expect(navLinks).not.toContain('Clientes')
    expect(navLinks).not.toContain('Vendas')
    // Hunter tem o módulo 'carteira', mas Bastões exige cargo Gerente/Franqueado
    expect(navLinks).not.toContain('Bastões')
  })

  it('EP vê Contadores + Clientes + Vendas (NÃO Bastões)', () => {
    userMock.current = { nome: 'Kethlleen', email: 'k@omie.com.vc', cargo: 'EP' }
    modulosMock.current = ['carteira', 'clientes']
    renderLayout()

    const navLinks = screen.getAllByRole('link').map((a) => a.textContent.trim())
    expect(navLinks).toContain('Contadores')
    expect(navLinks).toContain('Clientes')
    expect(navLinks).toContain('Vendas')
    expect(navLinks).not.toContain('PEX')
    expect(navLinks).not.toContain('POs')
    expect(navLinks).not.toContain('Metas')
    // EP é operacional mas não aprova bastões
    expect(navLinks).not.toContain('Bastões')
  })

  it('Gerente vê Contadores + Clientes + Vendas + Bastões', () => {
    userMock.current = { nome: 'Vinícius', email: 'v@omie.com.vc', cargo: 'Gerente' }
    modulosMock.current = ['carteira', 'clientes']
    renderLayout()

    const navLinks = screen.getAllByRole('link').map((a) => a.textContent.trim())
    expect(navLinks).toContain('Contadores')
    expect(navLinks).toContain('Clientes')
    expect(navLinks).toContain('Vendas')
    expect(navLinks).toContain('Bastões')
    expect(navLinks).not.toContain('PEX')
    expect(navLinks).not.toContain('POs')
  })

  it('EV vê Clientes + Vendas (sem Contadores, sem Bastões)', () => {
    userMock.current = { nome: 'Bruno Goncalo', email: 'bruno.goncalo@omie.com.vc', cargo: 'EV' }
    modulosMock.current = ['clientes']
    renderLayout()

    const navLinks = screen.getAllByRole('link').map((a) => a.textContent.trim())
    expect(navLinks).toContain('Vendas')
    expect(navLinks).toContain('Clientes')
    expect(navLinks).not.toContain('Contadores')
    expect(navLinks).not.toContain('Bastões')
    expect(navLinks).not.toContain('PEX')
  })

  it('Usuário sem módulos não vê nenhum item de nav principal', () => {
    userMock.current = { nome: 'Estranho', email: 'x@x.com', cargo: 'Desconhecido' }
    modulosMock.current = []
    renderLayout()

    const navLinks = screen.getAllByRole('link').map((a) => a.textContent.trim())
    expect(navLinks).not.toContain('Contadores')
    expect(navLinks).not.toContain('Clientes')
    expect(navLinks).not.toContain('Vendas')
    expect(navLinks).not.toContain('PEX')
    expect(navLinks).not.toContain('Bastões')
  })

  // ── Testes específicos do v1.2.0 etapa 3 — restrição por cargo ──

  it('Bastões aparece pra Gerente mesmo sem ter outros módulos especiais', () => {
    userMock.current = { nome: 'Vinícius', email: 'v@omie.com.vc', cargo: 'Gerente' }
    modulosMock.current = ['carteira']  // só carteira
    renderLayout()

    const navLinks = screen.getAllByRole('link').map((a) => a.textContent.trim())
    expect(navLinks).toContain('Bastões')
  })

  it('Bastões NÃO aparece quando o cargo é ADM (mesmo com todos os módulos)', () => {
    userMock.current = { nome: 'Tulio', email: 't@hipo.com', cargo: 'ADM' }
    modulosMock.current = ['pex', 'po', 'bd', 'carteira', 'clientes', 'metas', 'usuarios']
    renderLayout()

    const navLinks = screen.getAllByRole('link').map((a) => a.textContent.trim())
    expect(navLinks).not.toContain('Bastões')
  })

  // ── Ordem dos itens (UX) ─────────────────────────────────────

  it('Vendas aparece ANTES de Clientes na nav', () => {
    // Decisão de UX: funil de Vendas é a tela do dia-a-dia do EV;
    // Clientes fica em segundo plano. Quem tem os dois módulos vê
    // Vendas primeiro no menu.
    userMock.current = { nome: 'Tulio', email: 't@hipo.com', cargo: 'ADM' }
    modulosMock.current = ['pex', 'po', 'bd', 'carteira', 'clientes', 'metas', 'usuarios']
    renderLayout()

    const navLinks = screen.getAllByRole('link').map((a) => a.textContent.trim())
    const idxVendas = navLinks.indexOf('Vendas')
    const idxClientes = navLinks.indexOf('Clientes')
    expect(idxVendas).toBeGreaterThanOrEqual(0)
    expect(idxClientes).toBeGreaterThanOrEqual(0)
    expect(idxVendas).toBeLessThan(idxClientes)
  })
})

describe('Layout — dropdown do usuário', () => {
  beforeEach(() => {
    userMock.current = { nome: 'Aline Martins', email: 'a@omie.com.vc', cargo: 'Farmer' }
    modulosMock.current = ['carteira']
  })

  it('exibe nome do usuário no topbar (avatar/dropdown)', () => {
    renderLayout()
    expect(screen.getAllByText('Aline Martins').length).toBeGreaterThanOrEqual(1)
  })

  it('mostra Perfil e Sair ao abrir o dropdown', () => {
    renderLayout()
    // Dropdown fechado: itens não estão visíveis
    expect(screen.queryByRole('menuitem', { name: /perfil/i })).toBeNull()
    expect(screen.queryByRole('menuitem', { name: /sair/i })).toBeNull()

    // Clica no botão do dropdown (aria-label="Menu do usuário")
    fireEvent.click(screen.getByLabelText('Menu do usuário'))

    // Agora aparecem
    expect(screen.getByRole('menuitem', { name: /perfil/i })).toBeTruthy()
    expect(screen.getByRole('menuitem', { name: /sair/i })).toBeTruthy()
  })

  it('chama logout ao clicar em Sair no dropdown', () => {
    renderLayout()
    fireEvent.click(screen.getByLabelText('Menu do usuário'))
    fireEvent.click(screen.getByRole('menuitem', { name: /sair/i }))
    expect(logoutMock).toHaveBeenCalledTimes(1)
  })

  it('fecha o dropdown ao apertar Esc', () => {
    renderLayout()
    fireEvent.click(screen.getByLabelText('Menu do usuário'))
    expect(screen.getByRole('menuitem', { name: /sair/i })).toBeTruthy()

    fireEvent.keyDown(document, { key: 'Escape' })
    expect(screen.queryByRole('menuitem', { name: /sair/i })).toBeNull()
  })
})

describe('Layout — menu mobile (hamburger)', () => {
  beforeEach(() => {
    userMock.current = { nome: 'Tulio', email: 't@hipo.com', cargo: 'ADM' }
    modulosMock.current = ['pex', 'po', 'bd', 'carteira', 'clientes', 'metas', 'usuarios']
  })

  it('renderiza botão hamburger com aria-label correto', () => {
    renderLayout()
    expect(screen.getByLabelText('Abrir menu')).toBeTruthy()
  })

  it('alterna aria-label e abre a nav mobile ao clicar', () => {
    renderLayout()
    const btn = screen.getByLabelText('Abrir menu')
    fireEvent.click(btn)

    // aria-label muda pra "Fechar menu"
    expect(screen.getByLabelText('Fechar menu')).toBeTruthy()
    // nav mobile aparece com os itens
    expect(screen.getByLabelText('Navegação mobile')).toBeTruthy()
  })
})
