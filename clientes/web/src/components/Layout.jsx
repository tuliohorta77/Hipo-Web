// web/src/components/Layout.jsx
//
// Layout do Hipo — sidebar branca 264px, topbar branca, item ativo azul.
//
// v1.2: módulo "Carteira" renomeado visualmente para "Contadores".
//       Novo módulo "Clientes" (oportunidades + tarefas de leads).
//       Hunter/Farmer veem só Contadores + Perfil.
//       Gerente/EP veem Contadores + Clientes + Perfil.
//       ADM/Franqueado veem tudo.

import { useState } from 'react';
import { Outlet, NavLink } from 'react-router-dom';
import {
  BarChart3,
  FileText,
  Database,
  Target,
  Users,
  Briefcase,
  Menu,
  LogOut,
  X,
  User,
} from 'lucide-react';
import { getUser, getModulos, logout } from '../api';
import Logo, { LogoWordmark } from './Logo';

// Cada item declara o módulo que precisa pra aparecer.
// 'perfil' é especial: sempre visível pra qualquer logado.
const NAV_ITEMS = [
  { to: '/pex',          label: 'PEX',         Icon: BarChart3, modulo: 'pex' },
  { to: '/pos',          label: 'POs',         Icon: FileText,  modulo: 'po' },
  { to: '/bd-ativados',  label: 'BD Ativados', Icon: Database,  modulo: 'bd' },
  { to: '/contadores',   label: 'Contadores',  Icon: Briefcase, modulo: 'carteira' },
  { to: '/clientes',     label: 'Clientes',    Icon: Users,     modulo: 'clientes' },
  { to: '/metas',        label: 'Metas',       Icon: Target,    modulo: 'metas' },
  { to: '/perfil',       label: 'Perfil',      Icon: User,      modulo: '__sempre' },
];

function NavItem({ to, label, Icon, onClick }) {
  return (
    <NavLink
      to={to}
      onClick={onClick}
      className={({ isActive }) =>
        `flex items-center gap-3 px-3 h-10 rounded-lg text-sm font-medium transition-colors ` +
        (isActive
          ? 'bg-hipo-blueSoft text-hipo-blue'
          : 'text-hipo-slate hover:bg-hipo-bg hover:text-hipo-ink')
      }
    >
      <Icon size={18} />
      <span>{label}</span>
    </NavLink>
  );
}

function Sidebar({ user, modulos, onClose, isMobile = false }) {
  const itensVisiveis = NAV_ITEMS.filter(
    (item) => item.modulo === '__sempre' || modulos.includes(item.modulo),
  );

  return (
    <aside
      className={
        'w-64 shrink-0 bg-hipo-card border-r border-hipo-border flex flex-col h-full ' +
        (isMobile ? '' : 'hidden lg:flex')
      }
    >
      <div className="h-16 flex items-center justify-between px-5 border-b border-hipo-border">
        <div className="flex items-center gap-2.5">
          <Logo size={28} />
          <LogoWordmark />
        </div>
        {isMobile && (
          <button
            onClick={onClose}
            className="text-hipo-slate hover:text-hipo-ink"
            aria-label="Fechar menu"
          >
            <X size={18} />
          </button>
        )}
      </div>

      <nav className="flex-1 px-3 py-4 space-y-1 overflow-y-auto">
        {itensVisiveis.map((item) => (
          <NavItem key={item.to} {...item} onClick={isMobile ? onClose : undefined} />
        ))}
      </nav>

      <div className="border-t border-hipo-border p-3 space-y-1">
        {user && (
          <div className="px-3 py-2">
            <p className="text-sm font-semibold text-hipo-ink truncate">
              {user.nome}
            </p>
            <p className="text-xs text-hipo-slate truncate">
              {user.cargo || user.email}
            </p>
          </div>
        )}
        <button
          onClick={logout}
          className="w-full flex items-center gap-3 px-3 h-10 rounded-lg text-sm font-medium text-hipo-slate hover:bg-red-50 hover:text-hipo-danger transition-colors"
          title="Sair"
        >
          <LogOut size={18} />
          <span>Sair</span>
        </button>
      </div>
    </aside>
  );
}

function Topbar({ user, onOpenMenu }) {
  const initials = (user?.nome || user?.email || 'U')
    .split(' ')
    .slice(0, 2)
    .map((p) => p.charAt(0).toUpperCase())
    .join('');

  return (
    <header className="h-16 bg-hipo-card border-b border-hipo-border flex items-center justify-between px-4 lg:px-6 shrink-0">
      <button
        onClick={onOpenMenu}
        className="lg:hidden p-2 -ml-2 rounded-lg text-hipo-slate hover:bg-hipo-bg"
        aria-label="Abrir menu"
      >
        <Menu size={20} />
      </button>

      <div className="hidden lg:block" />

      {user && (
        <div className="flex items-center gap-3">
          <div className="hidden sm:block text-right">
            <p className="text-sm font-semibold text-hipo-ink leading-tight">
              {user.nome}
            </p>
            <p className="text-xs text-hipo-slate leading-tight">
              {user.cargo || user.email}
            </p>
          </div>
          <div className="w-9 h-9 rounded-full bg-hipo-blueSoft text-hipo-blue flex items-center justify-center text-sm font-semibold">
            {initials}
          </div>
        </div>
      )}
    </header>
  );
}

export default function Layout() {
  const user = getUser();
  const modulos = getModulos();
  const [mobileOpen, setMobileOpen] = useState(false);

  return (
    <div className="h-screen flex bg-hipo-bg overflow-hidden">
      <Sidebar user={user} modulos={modulos} />

      {mobileOpen && (
        <>
          <div
            className="lg:hidden fixed inset-0 bg-hipo-ink/40 z-40"
            onClick={() => setMobileOpen(false)}
          />
          <div className="lg:hidden fixed inset-y-0 left-0 z-50">
            <Sidebar
              user={user}
              modulos={modulos}
              isMobile
              onClose={() => setMobileOpen(false)}
            />
          </div>
        </>
      )}

      <div className="flex-1 flex flex-col min-w-0">
        <Topbar user={user} onOpenMenu={() => setMobileOpen(true)} />
        <main className="flex-1 overflow-auto">
          <div className="p-6 lg:p-8 max-w-7xl mx-auto">
            <Outlet />
          </div>
        </main>
      </div>
    </div>
  );
}
