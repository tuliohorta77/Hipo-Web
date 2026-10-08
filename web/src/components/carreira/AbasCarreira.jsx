// web/src/components/carreira/AbasCarreira.jsx
//
// As abas da Carreira: Universidade, PDI, Desempenho e Roleplay.
//
// São LINKS, não estado: cada aba é uma rota (/carreira, /carreira/pdi,
// /carreira/desempenho, /carreira/roleplay), então o F5 e o link mandado
// no WhatsApp abrem na aba certa. O ?usuario_id= da gestão (modo leitura)
// atravessa as abas.
//
// A conta que só estuda (cargo UC, sem o módulo 'crm') não tem PDI nem
// Desempenho nem Roleplay: vê só a Universidade, e as abas nem aparecem.

import { NavLink, useSearchParams } from 'react-router-dom';
import { Drama, GraduationCap, Target, TrendingUp } from 'lucide-react';
import { getModulos } from '../../api';

export const ABAS_CARREIRA = [
  { to: '/carreira', label: 'Universidade', Icone: GraduationCap, fim: true },
  { to: '/carreira/pdi', label: 'PDI', Icone: Target },
  { to: '/carreira/desempenho', label: 'Desempenho', Icone: TrendingUp },
  { to: '/carreira/roleplay', label: 'Roleplay', Icone: Drama },
];

export default function AbasCarreira({ ativa }) {
  const [params] = useSearchParams();
  if (!getModulos().includes('crm')) return null;
  const usuarioId = params.get('usuario_id');
  const sufixo = usuarioId ? `?usuario_id=${encodeURIComponent(usuarioId)}` : '';

  return (
    <nav aria-label="Carreira" className="flex gap-1 border-b border-hipo-border" data-tour="carreira-abas">
      {ABAS_CARREIRA.map(({ to, label, Icone, fim }) => (
        <NavLink
          key={to}
          to={`${to}${sufixo}`}
          end={fim}
          className={({ isActive }) => {
            const ligada = ativa ? ativa === label : isActive;
            return (
              'relative inline-flex items-center gap-1.5 px-4 h-10 text-sm font-medium transition-colors ' +
              (ligada
                ? 'text-hipo-blue after:absolute after:left-0 after:right-0 after:-bottom-px after:h-0.5 after:bg-hipo-blue after:rounded-full'
                : 'text-hipo-slate hover:text-hipo-ink')
            );
          }}
        >
          <Icone size={15} aria-hidden="true" />
          {label}
        </NavLink>
      ))}
    </nav>
  );
}
