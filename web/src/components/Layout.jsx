// web/src/components/Layout.jsx
//
// Layout do Hipo — Fase 3: topbar horizontal (substitui sidebar lateral).
//
// Estrutura:
//   - Topbar branca (64px desktop, 56px mobile) com:
//     . Logo Hipo à esquerda
//     . Nav central (só texto, item ativo com underline azul)
//     . Avatar à direita com dropdown (Perfil + Sair)
//   - Mobile (< lg): nav some, vira hamburger. Click abre menu vertical
//     descendo do topbar.
//   - Conteúdo principal ocupa 100% da largura.
//
// Permissão por módulo (preservado do v1.2):
//   - ADM/Franqueado → tudo
//   - Gerente/EP → Contadores + Clientes + Perfil
//   - Hunter/Farmer/SDR/EV/EC → Contadores + Perfil
//
// Acessibilidade: NavLink renderiza <a>, dropdown e hamburger fecham
// ao clicar fora ou pressionar Esc.

import { useEffect, useRef, useState } from 'react';
import { Outlet, NavLink, useNavigate } from 'react-router-dom';
import { Menu, X, LogOut, User as UserIcon, ChevronDown } from 'lucide-react';
import { getUser, getModulos, logout } from '../api';
import Logo, { LogoWordmark } from './Logo';

// Cada item declara o módulo que precisa pra aparecer.
// 'perfil' não aparece na nav principal — está no dropdown do usuário.
// '__sempre' é especial: visível pra qualquer logado.
const NAV_ITEMS = [
  { to: '/pex',         label: 'PEX',         modulo: 'pex' },
  { to: '/pos',         label: 'POs',         modulo: 'po' },
  { to: '/bd-ativados', label: 'BD Ativados', modulo: 'bd' },
  { to: '/contadores',  label: 'Contadores',  modulo: 'carteira' },
  { to: '/clientes',    label: 'Clientes',    modulo: 'clientes' },
  { to: '/metas',       label: 'Metas',       modulo: 'metas' },
];

// Itens que vivem no dropdown do usuário (não na nav principal).
// Perfil entra aqui porque é "do usuário", não uma feature.
const USER_MENU_ITEMS = [
  { to: '/perfil', label: 'Perfil', Icon: UserIcon, modulo: '__sempre' },
];

// ── Subcomponentes ─────────────────────────────────────────────

function NavItemDesktop({ to, label }) {
  return (
    <NavLink
      to={to}
      className={({ isActive }) =>
        'h-full flex items-center px-3 text-sm font-medium transition-colors ' +
        (isActive
          ? 'text-hipo-blue border-b-2 border-hipo-blue -mb-px'
          : 'text-hipo-slate hover:text-hipo-ink border-b-2 border-transparent -mb-px')
      }
    >
      {label}
    </NavLink>
  );
}

function NavItemMobile({ to, label, onClick }) {
  return (
    <NavLink
      to={to}
      onClick={onClick}
      className={({ isActive }) =>
        'block px-5 py-3.5 text-sm font-medium transition-colors border-l-[3px] ' +
        (isActive
          ? 'text-hipo-blue bg-hipo-blueSoft border-hipo-blue'
          : 'text-hipo-slate hover:bg-hipo-bg border-transparent')
      }
    >
      {label}
    </NavLink>
  );
}

function UserDropdown({ user }) {
  const [open, setOpen] = useState(false);
  const navigate = useNavigate();
  const wrapperRef = useRef(null);

  const initials = (user?.nome || user?.email || 'U')
    .split(' ')
    .slice(0, 2)
    .map((p) => p.charAt(0).toUpperCase())
    .join('');

  // Fecha ao clicar fora
  useEffect(() => {
    if (!open) return;
    function handleClickFora(e) {
      if (wrapperRef.current && !wrapperRef.current.contains(e.target)) {
        setOpen(false);
      }
    }
    function handleEsc(e) {
      if (e.key === 'Escape') setOpen(false);
    }
    document.addEventListener('mousedown', handleClickFora);
    document.addEventListener('keydown', handleEsc);
    return () => {
      document.removeEventListener('mousedown', handleClickFora);
      document.removeEventListener('keydown', handleEsc);
    };
  }, [open]);

  function handleItemClick(to) {
    setOpen(false);
    navigate(to);
  }

  function handleLogout() {
    setOpen(false);
    logout();
  }

  return (
    <div className="relative" ref={wrapperRef}>
      <button
        onClick={() => setOpen((v) => !v)}
        className="flex items-center gap-2 p-1 pr-2 rounded-lg hover:bg-hipo-bg transition-colors"
        aria-label="Menu do usuário"
        aria-expanded={open}
        aria-haspopup="menu"
      >
        <div className="w-9 h-9 rounded-full bg-hipo-blueSoft text-hipo-blue flex items-center justify-center text-sm font-semibold">
          {initials}
        </div>
        <div className="hidden sm:flex flex-col items-start leading-tight">
          <span className="text-sm font-semibold text-hipo-ink">{user?.nome || '—'}</span>
          <span className="text-xs text-hipo-slate">{user?.cargo || user?.email || ''}</span>
        </div>
        <ChevronDown
          size={14}
          className={`text-hipo-muted hidden sm:block transition-transform ${open ? 'rotate-180' : ''}`}
        />
      </button>

      {open && (
        <div
          role="menu"
          className="absolute right-0 top-full mt-1 w-56 bg-hipo-card border border-hipo-border rounded-lg shadow-soft py-1 z-50"
        >
          <div className="px-3 py-2 border-b border-hipo-border sm:hidden">
            <p className="text-sm font-semibold text-hipo-ink truncate">{user?.nome || '—'}</p>
            <p className="text-xs text-hipo-slate truncate">{user?.cargo || user?.email || ''}</p>
          </div>
          {USER_MENU_ITEMS.map(({ to, label, Icon }) => (
            <button
              key={to}
              role="menuitem"
              onClick={() => handleItemClick(to)}
              className="w-full flex items-center gap-2.5 px-3 py-2 text-sm text-hipo-slate hover:bg-hipo-bg hover:text-hipo-ink transition-colors text-left"
            >
              <Icon size={16} />
              <span>{label}</span>
            </button>
          ))}
          <div className="border-t border-hipo-border my-1" />
          <button
            role="menuitem"
            onClick={handleLogout}
            className="w-full flex items-center gap-2.5 px-3 py-2 text-sm text-hipo-slate hover:bg-hipo-dangerSoft hover:text-hipo-danger transition-colors text-left"
          >
            <LogOut size={16} />
            <span>Sair</span>
          </button>
        </div>
      )}
    </div>
  );
}

// ── Componente principal ──────────────────────────────────────

export default function Layout() {
  const user = getUser();
  const modulos = getModulos();
  const [mobileOpen, setMobileOpen] = useState(false);

  const itensVisiveis = NAV_ITEMS.filter((item) => modulos.includes(item.modulo));

  // Fecha menu mobile ao apertar Esc
  useEffect(() => {
    if (!mobileOpen) return;
    function handleEsc(e) {
      if (e.key === 'Escape') setMobileOpen(false);
    }
    document.addEventListener('keydown', handleEsc);
    return () => document.removeEventListener('keydown', handleEsc);
  }, [mobileOpen]);

  return (
    <div className="min-h-screen flex flex-col bg-hipo-bg">
      {/* Topbar */}
      <header className="bg-hipo-card border-b border-hipo-border sticky top-0 z-30">
        <div className="h-14 lg:h-16 flex items-center px-4 lg:px-6 gap-3 lg:gap-6">
          {/* Mobile: hamburger */}
          <button
            onClick={() => setMobileOpen((v) => !v)}
            className="lg:hidden p-2 -ml-2 rounded-lg text-hipo-slate hover:bg-hipo-bg transition-colors"
            aria-label={mobileOpen ? 'Fechar menu' : 'Abrir menu'}
            aria-expanded={mobileOpen}
          >
            {mobileOpen ? <X size={20} className="text-hipo-blue" /> : <Menu size={20} />}
          </button>

          {/* Logo */}
          <NavLink to="/" className="flex items-center gap-2 shrink-0">
            <Logo size={28} />
            <LogoWordmark />
          </NavLink>

          {/* Nav desktop — fica no meio, encostada à esquerda */}
          <nav
            className="hidden lg:flex items-center h-full ml-4"
            aria-label="Navegação principal"
          >
            {itensVisiveis.map((item) => (
              <NavItemDesktop key={item.to} {...item} />
            ))}
          </nav>

          {/* Spacer */}
          <div className="flex-1" />

          {/* User dropdown (sempre visível) */}
          {user && <UserDropdown user={user} />}
        </div>

        {/* Menu mobile — desce do topbar */}
        {mobileOpen && (
          <div className="lg:hidden border-t border-hipo-border bg-hipo-card">
            <nav className="py-1" aria-label="Navegação mobile">
              {itensVisiveis.map((item) => (
                <NavItemMobile
                  key={item.to}
                  {...item}
                  onClick={() => setMobileOpen(false)}
                />
              ))}
            </nav>
          </div>
        )}
      </header>

      {/* Overlay mobile que escurece o conteúdo (clicável pra fechar) */}
      {mobileOpen && (
        <div
          className="lg:hidden fixed inset-0 top-14 bg-hipo-ink/30 z-20"
          onClick={() => setMobileOpen(false)}
          aria-hidden="true"
        />
      )}

      {/* Conteúdo principal */}
      <main className="flex-1">
        <div className="p-6 lg:p-8 max-w-7xl mx-auto">
          <Outlet />
        </div>
      </main>
    </div>
  );
}
