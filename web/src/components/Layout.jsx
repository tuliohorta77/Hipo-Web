import { Outlet, NavLink } from "react-router-dom";
import { BarChart3, FileText, Menu } from "lucide-react";
import { useState } from "react";

export default function Layout() {
  const [open, setOpen] = useState(true);

  const nav = [
    { to: "/pex", label: "PEX",  Icon: BarChart3 },
    { to: "/pos", label: "POs",  Icon: FileText  },
  ];

  return (
    <div className="flex h-screen bg-slate-950 text-slate-100 font-mono overflow-hidden">
      {/* Sidebar */}
      <aside className={`${open ? "w-52" : "w-16"} transition-all bg-slate-900 border-r border-slate-800 flex flex-col`}>
        <div className="flex items-center justify-between px-4 py-4 border-b border-slate-800">
          {open && (
            <div className="flex items-center gap-2">
              <div className="w-7 h-7 rounded-lg bg-gradient-to-br from-cyan-500 to-blue-600 flex items-center justify-center text-xs font-bold">H</div>
              <span className="text-cyan-400 font-bold tracking-widest text-sm">HIPO</span>
            </div>
          )}
          <button onClick={() => setOpen(o => !o)} className="text-slate-500 hover:text-slate-300">
            <Menu size={18} />
          </button>
        </div>
        <nav className="flex-1 p-2 space-y-1 mt-2">
          {nav.map(({ to, label, Icon }) => (
            <NavLink key={to} to={to}
              className={({ isActive }) =>
                `flex items-center gap-3 px-3 py-2.5 rounded-lg text-sm transition-colors ${
                  isActive
                    ? "bg-cyan-500/10 text-cyan-400 font-bold"
                    : "text-slate-400 hover:text-slate-200 hover:bg-slate-800"
                }`
              }>
              <Icon size={18} />
              {open && <span>{label}</span>}
            </NavLink>
          ))}
        </nav>
        <div className="px-4 py-3 border-t border-slate-800">
          {open && <p className="text-xs text-slate-600">v1.0 — Fase 1</p>}
        </div>
      </aside>

      {/* Main */}
      <main className="flex-1 overflow-auto">
        <Outlet />
      </main>
    </div>
  );
}
