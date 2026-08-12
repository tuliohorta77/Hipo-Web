// web/src/components/Layout.jsx
//
// Layout do HIPO — topbar horizontal.
//
// Estrutura:
//   - Topbar (64px desktop, 56px mobile) com:
//     . Logo à esquerda
//     . Nav central (só texto, item ativo com underline azul)
//     . Avatar à direita com dropdown (Perfil + Sair)
//   - Mobile (< lg): nav vira hamburger, menu desce do topbar.
//   - Conteúdo principal ocupa 100% da largura.
//
// Quando NAV_ITEMS fica vazio para o cargo (ex.: cargo extinto, sem módulo
// nenhum), a nav desktop e o hamburger não são renderizados — o usuário
// ainda alcança Perfil e Sair pelo dropdown do avatar.
//
// Items podem ter:
//   - modulo: string  → checa modulos.includes(modulo)
//   - cargos: array   → checa user.cargo in cargos (opcional, restringe mais)
//
// Acessibilidade: NavLink renderiza <a>, dropdown e hamburger fecham ao
// clicar fora ou pressionar Esc.

import { useEffect, useRef, useState } from 'react';
import { Outlet, NavLink, useNavigate } from 'react-router-dom';
import { Menu, X, LogOut, User as UserIcon, ChevronDown } from 'lucide-react';
import { getUser, getModulos, logout } from '../api';
import Logo, { LogoWordmark } from './Logo';

// Nav principal, na ordem em que o dia acontece: o funil é onde se trabalha,
// Tarefas é o que está pendente nele, e Contas é o cadastro de apoio.
//
// Parceiros vem por último e é o primeiro item da nav com módulo PRÓPRIO: só
// EC e gestão o enxergam. Para SDR, EV e EP a barra continua com três itens —
// é a diretriz "uma tela por função" aplicada também à navegação.
const NAV_ITEMS = [
  { to: '/crm/oportunidades', label: 'Oportunidades', modulo: 'crm' },
  { to: '/crm/tarefas', label: 'Tarefas', modulo: 'crm' },
  { to: '/crm/contas', label: 'Contas', modulo: 'crm' },
  { to: '/crm/parceiros', label: 'Parceiros', modulo: 'parceiros' },
];

// Itens do dropdown do usuário (não da nav principal).
// '__sempre' é especial: visível para qualquer usuário autenticado.
const USER_MENU_ITEMS = [
  { to: '/perfil', label: 'Perfil', Icon: UserIcon, modulo: '__sempre' },
];

// ── Helpers ──────────────────────────────────────────────────────────

function itemVisivel(item, modulos, cargo) {
  if (item.modulo !== '__sempre' && !modulos.includes(item.modulo)) return false;
  if (item.cargos && !item.cargos.includes(cargo)) return false;
  return true;
}

// ── Subcomponentes ───────────────────────────────────────────────────

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

// ── Componente principal ─────────────────────────────────────────────

export default function Layout() {
  const user = getUser();
  const modulos = getModulos();
  const cargo = user?.cargo;
  const [mobileOpen, setMobileOpen] = useState(false);

  const itensVisiveis = NAV_ITEMS.filter((item) => itemVisivel(item, modulos, cargo));
  const temNav = itensVisiveis.length > 0;

  useEffect(() => {
    if (!mobileOpen) return;
    function handleEsc(e) {
      if (e.key === 'Escape') setMobileOpen(false);
    }
    document.addEventListener('keydown', handleEsc);
    return () => document.removeEventListener('keydown', handleEsc);
  }, [mobileOpen]);

  // Se a nav esvaziar (Sprint 0, ou cargo sem módulo), fecha o menu mobile
  // para não deixar um painel vazio aberto.
  useEffect(() => {
    if (!temNav && mobileOpen) setMobileOpen(false);
  }, [temNav, mobileOpen]);

  return (
    <div className="h-screen flex flex-col bg-hipo-bg overflow-hidden">
      <header className="bg-hipo-card border-b border-hipo-border shrink-0 z-30">
        {/* 48/52px. Era 56/64 — 20% a menos, para devolver altura ao conteudo. */}
        <div className="h-12 lg:h-[52px] flex items-center px-3 lg:px-5 gap-3 lg:gap-5">
          {temNav && (
            <button
              onClick={() => setMobileOpen((v) => !v)}
              className="lg:hidden p-2 -ml-2 rounded-lg text-hipo-slate hover:bg-hipo-bg transition-colors"
              aria-label={mobileOpen ? 'Fechar menu' : 'Abrir menu'}
              aria-expanded={mobileOpen}
            >
              {mobileOpen ? <X size={20} className="text-hipo-blue" /> : <Menu size={20} />}
            </button>
          )}

          <NavLink to="/" className="flex items-center gap-2 shrink-0">
            <Logo size={24} />
            <LogoWordmark />
          </NavLink>

          {temNav && (
            <nav
              className="hidden lg:flex items-center h-full ml-4"
              aria-label="Navegação principal"
            >
              {itensVisiveis.map((item) => (
                <NavItemDesktop key={item.to} {...item} />
              ))}
            </nav>
          )}

          <div className="flex-1" />

          {user && <UserDropdown user={user} />}
        </div>

        {temNav && mobileOpen && (
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

      {temNav && mobileOpen && (
        <div
          className="lg:hidden fixed inset-0 top-12 bg-hipo-ink/30 z-20"
          onClick={() => setMobileOpen(false)}
          aria-hidden="true"
        />
      )}

      {/*
        O shell tem a altura exata da viewport e o scroll vive aqui, no <main>,
        não no <body>. Duas consequências, ambas intencionais:

          - Página comum (Contas, Perfil) continua rolando normalmente: o
            conteúdo passa da altura do container e o <main> rola.
          - Página que quer altura fixa (o funil de Oportunidades) se declara
            `h-full` e nunca ultrapassa o container, então o <main> não rola e
            o scroll fica onde a tela quiser — nas colunas do kanban, por
            exemplo. Sem isso não dá para ter "scroll por coluna": o
            navegador não sabe qual é a altura disponível.
      */}
      <main className="flex-1 min-h-0 overflow-y-auto">
        <div className="px-3 lg:px-5 py-3 h-full">
          <Outlet />
        </div>
      </main>
    </div>
  );
}
