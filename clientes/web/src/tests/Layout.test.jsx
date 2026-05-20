import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, cleanup } from '@testing-library/react'
import { MemoryRouter, Routes, Route } from 'react-router-dom'

// Helper pra mockar getUser + getModulos dinamicamente em cada teste
const userMock = { current: null }
const modulosMock = { current: [] }

vi.mock('../api', () => ({
  default: {},
  getUser: () => userMock.current,
  getModulos: () => modulosMock.current,
  logout: vi.fn(),
  isAuthenticated: () => true,
}))

import Layout from '../components/Layout'

function renderLayout() {
  return render(
    <MemoryRouter initialEntries={['/perfil']}>
      <Routes>
        <Route path="/" element={<Layout />}>
          <Route path="perfil" element={<div>conteúdo</div>} />
        </Route>
      </Routes>
    </MemoryRouter>
  )
}

beforeEach(() => {
  cleanup()
  vi.clearAllMocks()
})

describe('Layout — filtragem por módulos', () => {
  it('ADM vê todos os itens (PEX, POs, BD, Contadores, Clientes, Metas, Perfil)', () => {
    userMock.current = { nome: 'Tulio', email: 't@hipo.com', cargo: 'ADM' }
    modulosMock.current = ['pex', 'po', 'bd', 'carteira', 'clientes', 'metas', 'usuarios']
    renderLayout()

    const links = screen.getAllByRole('link').map((a) => a.textContent.trim())
    expect(links).toContain('PEX')
    expect(links).toContain('POs')
    expect(links).toContain('BD Ativados')
    expect(links).toContain('Contadores')
    expect(links).toContain('Clientes')
    expect(links).toContain('Metas')
    expect(links).toContain('Perfil')
    // Não tem mais "Carteira" no menu
    expect(links).not.toContain('Carteira')
  })

  it('Franqueado vê todos os itens', () => {
    userMock.current = { nome: 'Wellington', email: 'w@omie.com.vc', cargo: 'Franqueado' }
    modulosMock.current = ['pex', 'po', 'bd', 'carteira', 'clientes', 'metas', 'usuarios']
    renderLayout()

    const links = screen.getAllByRole('link').map((a) => a.textContent.trim())
    expect(links).toContain('PEX')
    expect(links).toContain('Contadores')
    expect(links).toContain('Clientes')
    expect(links).toContain('Perfil')
  })

  it('Farmer vê APENAS Contadores e Perfil', () => {
    userMock.current = { nome: 'Aline', email: 'a@omie.com.vc', cargo: 'Farmer' }
    modulosMock.current = ['carteira']
    renderLayout()

    const links = screen.getAllByRole('link').map((a) => a.textContent.trim())
    expect(links).toContain('Contadores')
    expect(links).toContain('Perfil')
    expect(links).not.toContain('PEX')
    expect(links).not.toContain('POs')
    expect(links).not.toContain('BD Ativados')
    expect(links).not.toContain('Metas')
    expect(links).not.toContain('Clientes')
  })

  it('Hunter vê APENAS Contadores e Perfil', () => {
    userMock.current = { nome: 'Beatriz', email: 'b@omie.com.vc', cargo: 'Hunter' }
    modulosMock.current = ['carteira']
    renderLayout()

    const links = screen.getAllByRole('link').map((a) => a.textContent.trim())
    expect(links).toContain('Contadores')
    expect(links).toContain('Perfil')
    expect(links).not.toContain('PEX')
    expect(links).not.toContain('Clientes')
  })

  it('EP vê Contadores + Clientes + Perfil', () => {
    userMock.current = { nome: 'Kethlleen', email: 'k@omie.com.vc', cargo: 'EP' }
    modulosMock.current = ['carteira', 'clientes']
    renderLayout()

    const links = screen.getAllByRole('link').map((a) => a.textContent.trim())
    expect(links).toContain('Contadores')
    expect(links).toContain('Clientes')
    expect(links).toContain('Perfil')
    expect(links).not.toContain('PEX')
    expect(links).not.toContain('POs')
    expect(links).not.toContain('Metas')
  })

  it('Gerente vê Contadores + Clientes + Perfil', () => {
    userMock.current = { nome: 'Vinícius', email: 'v@omie.com.vc', cargo: 'Gerente' }
    modulosMock.current = ['carteira', 'clientes']
    renderLayout()

    const links = screen.getAllByRole('link').map((a) => a.textContent.trim())
    expect(links).toContain('Contadores')
    expect(links).toContain('Clientes')
    expect(links).toContain('Perfil')
    expect(links).not.toContain('PEX')
    expect(links).not.toContain('POs')
  })

  it('Usuário sem módulos vê APENAS Perfil', () => {
    userMock.current = { nome: 'Estranho', email: 'x@x.com', cargo: 'Desconhecido' }
    modulosMock.current = []
    renderLayout()

    const links = screen.getAllByRole('link').map((a) => a.textContent.trim())
    expect(links).toContain('Perfil')
    expect(links).not.toContain('Contadores')
    expect(links).not.toContain('Clientes')
    expect(links).not.toContain('PEX')
  })

  it('exibe nome do usuário no footer da sidebar', () => {
    userMock.current = { nome: 'Aline Martins', email: 'a@omie.com.vc', cargo: 'Farmer' }
    modulosMock.current = ['carteira']
    renderLayout()
    expect(screen.getAllByText('Aline Martins').length).toBeGreaterThanOrEqual(1)
  })
})
