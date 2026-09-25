// web/src/components/relatorios/ListaSalvos.jsx
//
// Os relatórios salvos: os meus primeiro, depois os que a equipe
// compartilhou. Clicar abre — e recalcula, porque o que se guarda é a
// pergunta, nunca a resposta.

import { useMemo, useState } from 'react';
import { Search, Users, FileBarChart2 } from 'lucide-react';
import { descreverPeriodo } from './periodo';

function Item({ r, ativo, onAbrir }) {
  return (
    <li>
      <button
        type="button"
        onClick={() => onAbrir(r)}
        aria-current={ativo ? 'true' : undefined}
        className={
          'w-full text-left px-2.5 py-2 rounded-lg transition-colors border ' +
          (ativo ? 'bg-hipo-blueSoft border-hipo-blue/30' : 'border-transparent hover:bg-hipo-bg')
        }
      >
        <span className="flex items-center gap-1.5">
          <span className="text-sm font-medium text-hipo-ink truncate">{r.nome}</span>
          {r.compartilhado && r.eh_meu && (
            <Users size={12} className="text-hipo-blue shrink-0" aria-label="Compartilhado" />
          )}
        </span>
        <span className="block text-[11px] text-hipo-slate truncate">
          {r.fonte_rotulo} · {descreverPeriodo(r.config?.periodo)}
        </span>
        {!r.eh_meu && (
          <span className="block text-[11px] text-hipo-muted truncate">por {r.dono_nome}</span>
        )}
      </button>
    </li>
  );
}

export default function ListaSalvos({ salvos, ativoId, onAbrir }) {
  const [busca, setBusca] = useState('');
  const filtrados = useMemo(() => {
    const t = busca.trim().toLowerCase();
    return t ? salvos.filter((r) => r.nome.toLowerCase().includes(t)) : salvos;
  }, [salvos, busca]);
  const meus = filtrados.filter((r) => r.eh_meu);
  const deles = filtrados.filter((r) => !r.eh_meu);

  return (
    <nav aria-label="Relatórios salvos" className="space-y-3">
      {salvos.length > 5 && (
        <div className="relative">
          <Search size={13} className="absolute left-2.5 top-1/2 -translate-y-1/2 text-hipo-muted" />
          <input
            aria-label="Buscar relatório salvo"
            value={busca}
            onChange={(e) => setBusca(e.target.value)}
            placeholder="Buscar…"
            className="w-full h-8 pl-8 pr-2 rounded-lg border border-hipo-border text-xs outline-none focus:border-hipo-blue"
          />
        </div>
      )}
      <section>
        <h3 className="text-[11px] uppercase tracking-wide font-semibold text-hipo-muted mb-1 px-1">Meus relatórios</h3>
        {meus.length === 0 ? (
          <p className="text-xs text-hipo-slate px-1 py-2 flex items-center gap-1.5">
            <FileBarChart2 size={13} /> Nenhum salvo ainda.
          </p>
        ) : (
          <ul className="space-y-0.5">
            {meus.map((r) => <Item key={r.id} r={r} ativo={r.id === ativoId} onAbrir={onAbrir} />)}
          </ul>
        )}
      </section>
      {deles.length > 0 && (
        <section>
          <h3 className="text-[11px] uppercase tracking-wide font-semibold text-hipo-muted mb-1 px-1">Compartilhados pela equipe</h3>
          <ul className="space-y-0.5">
            {deles.map((r) => <Item key={r.id} r={r} ativo={r.id === ativoId} onAbrir={onAbrir} />)}
          </ul>
        </section>
      )}
    </nav>
  );
}
