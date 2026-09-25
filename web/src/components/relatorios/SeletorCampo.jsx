// web/src/components/relatorios/SeletorCampo.jsx
//
// Lista de campos da fonte, agrupada e pesquisável, para colocar em Linhas,
// Colunas, Valores ou Filtros.
//
// O nome que aparece é o do catálogo da API ("Mensalidade (R$)", "Fase em
// que foi finalizada"), e a ajuda do campo vem logo abaixo: quem monta
// relatório é a operação, e "fase_desfecho" não diz nada para ela.

import { useMemo, useState } from 'react';
import { Search, Hash, Type, CalendarDays, ToggleLeft, DollarSign, ListOrdered } from 'lucide-react';
import Modal from '../ui/Modal';

const ICONES = {
  texto: Type,
  numero: Hash,
  moeda: DollarSign,
  data: CalendarDays,
  booleano: ToggleLeft,
};

const TITULOS = {
  linhas: 'Adicionar campo nas linhas',
  colunas: 'Adicionar campo nas colunas',
  valores: 'Adicionar valor (o que somar, contar ou calcular)',
  filtros: 'Filtrar por qual campo?',
};

export const REGISTROS = '*';

/** Campos elegíveis para cada zona. */
export function camposDaZona(fonte, zona) {
  if (!fonte) return [];
  if (zona === 'valores') return fonte.campos.filter((c) => c.agregacoes.length > 0);
  return fonte.campos.filter((c) => c.dimensao);
}

function normalizar(s) {
  return String(s || '')
    .normalize('NFD')
    .replace(/[̀-ͯ]/g, '')
    .toLowerCase();
}

export default function SeletorCampo({ aberto, zona, fonte, usados = [], onEscolher, onFechar }) {
  const [busca, setBusca] = useState('');

  const grupos = useMemo(() => {
    const termo = normalizar(busca);
    const lista = camposDaZona(fonte, zona).filter((c) => (
      !termo || normalizar(c.rotulo).includes(termo) || normalizar(c.ajuda).includes(termo)
        || normalizar(c.grupo).includes(termo)
    ));
    const mapa = new Map();
    lista.forEach((c) => {
      if (!mapa.has(c.grupo)) mapa.set(c.grupo, []);
      mapa.get(c.grupo).push(c);
    });
    return [...mapa.entries()];
  }, [busca, fonte, zona]);

  function escolher(chave) {
    setBusca('');
    onEscolher(chave);
  }

  const mostrarRegistros = zona === 'valores' && !busca;

  return (
    <Modal
      aberto={aberto}
      onFechar={() => { setBusca(''); onFechar(); }}
      titulo={TITULOS[zona] || 'Escolher campo'}
      subtitulo={fonte ? `Fonte: ${fonte.rotulo}` : undefined}
      size="lg"
      nivel={2}
    >
      <div className="relative mb-3">
        <Search size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-hipo-muted" />
        <input
          autoFocus
          aria-label="Buscar campo"
          value={busca}
          onChange={(e) => setBusca(e.target.value)}
          placeholder="Buscar campo…"
          className="w-full h-10 pl-9 pr-3 rounded-lg border border-hipo-border text-sm outline-none focus:border-hipo-blue focus:ring-2 focus:ring-blue-100"
        />
      </div>

      {mostrarRegistros && (
        <button
          type="button"
          onClick={() => escolher(REGISTROS)}
          className="w-full flex items-start gap-3 text-left px-3 py-2.5 mb-3 rounded-lg border border-hipo-blueSoft bg-hipo-blueSoft/50 hover:bg-hipo-blueSoft"
        >
          <ListOrdered size={16} className="text-hipo-blue mt-0.5 shrink-0" />
          <span>
            <span className="block text-sm font-medium text-hipo-ink">
              Quantidade de {fonte?.rotulo_registro}
            </span>
            <span className="block text-xs text-hipo-slate">Conta quantos registros caem em cada célula.</span>
          </span>
        </button>
      )}

      {grupos.length === 0 && (
        <p className="text-sm text-hipo-slate py-6 text-center">Nenhum campo com esse nome.</p>
      )}

      <div className="space-y-4">
        {grupos.map(([grupo, campos]) => (
          <section key={grupo}>
            <h4 className="text-[11px] uppercase tracking-wide font-semibold text-hipo-muted mb-1.5">{grupo}</h4>
            <ul className="grid sm:grid-cols-2 gap-1.5">
              {campos.map((c) => {
                const Icone = ICONES[c.tipo] || Type;
                const jaUsado = usados.includes(c.chave);
                return (
                  <li key={c.chave}>
                    <button
                      type="button"
                      onClick={() => escolher(c.chave)}
                      className="w-full h-full flex items-start gap-2.5 text-left px-3 py-2 rounded-lg border border-hipo-border hover:border-hipo-blue hover:bg-hipo-bg transition-colors"
                    >
                      <Icone size={14} className="text-hipo-muted mt-0.5 shrink-0" />
                      <span className="min-w-0">
                        <span className="block text-sm text-hipo-ink">
                          {c.rotulo}
                          {jaUsado && <span className="ml-1.5 text-[10px] text-hipo-blue">em uso</span>}
                        </span>
                        {c.ajuda && <span className="block text-xs text-hipo-slate mt-0.5">{c.ajuda}</span>}
                      </span>
                    </button>
                  </li>
                );
              })}
            </ul>
          </section>
        ))}
      </div>
    </Modal>
  );
}
