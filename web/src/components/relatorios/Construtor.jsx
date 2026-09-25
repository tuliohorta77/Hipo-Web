// web/src/components/relatorios/Construtor.jsx
//
// As quatro áreas da tabela dinâmica, como no Excel: Filtros, Linhas,
// Colunas e Valores.
//
// Arrastar um campo entre Linhas e Colunas (ou reordenar dentro de uma
// delas) funciona como no Excel. Tudo o que o arrastar faz também tem
// botão: arrastar não existe no celular nem para quem navega por teclado, e
// é o botão que os testes exercitam.

import { useState } from 'react';
import {
  Plus, X, ArrowLeftRight, Filter, Rows3, Columns3, Sigma, GripVertical, Repeat,
} from 'lucide-react';
import SeletorCampo, { REGISTROS } from './SeletorCampo';
import FiltroCampo, { resumoFiltro } from './FiltroCampo';

const ZONAS = {
  filtros: { titulo: 'Filtros', Icone: Filter, dica: 'Restringe os registros considerados.' },
  linhas: { titulo: 'Linhas', Icone: Rows3, dica: 'Cada valor vira uma linha.' },
  colunas: { titulo: 'Colunas', Icone: Columns3, dica: 'Cada valor vira uma coluna.' },
  valores: { titulo: 'Valores', Icone: Sigma, dica: 'O que contar, somar ou calcular.' },
};

// ── Operações puras sobre a configuração (exportadas para teste) ─────

export function adicionarNaZona(config, zona, campo, catalogoFonte) {
  if (zona === 'valores') {
    const agregacao = campo === REGISTROS
      ? 'contagem'
      : catalogoFonte.campos.find((c) => c.chave === campo).agregacoes[0];
    return { ...config, valores: [...config.valores, { campo, agregacao }] };
  }
  const def = catalogoFonte.campos.find((c) => c.chave === campo);
  const item = { campo, granularidade: def?.tipo === 'data' ? 'mes' : null };
  return { ...config, [zona]: [...config[zona], item] };
}

export function removerDaZona(config, zona, indice) {
  return { ...config, [zona]: config[zona].filter((_, i) => i !== indice) };
}

export function atualizarNaZona(config, zona, indice, parcial) {
  return {
    ...config,
    [zona]: config[zona].map((x, i) => (i === indice ? { ...x, ...parcial } : x)),
  };
}

/** Move um campo de linhas<->colunas, ou reordena dentro da mesma zona. */
export function moverCampo(config, de, indice, para, posicao = null) {
  const item = config[de][indice];
  const origem = config[de].filter((_, i) => i !== indice);
  const destinoBase = de === para ? origem : [...config[para]];
  const pos = posicao === null ? destinoBase.length : Math.min(posicao, destinoBase.length);
  const destino = [...destinoBase.slice(0, pos), item, ...destinoBase.slice(pos)];
  return de === para
    ? { ...config, [de]: destino }
    : { ...config, [de]: origem, [para]: destino };
}

export function inverterEixos(config) {
  return { ...config, linhas: config.colunas, colunas: config.linhas };
}

// ── Componente ───────────────────────────────────────────────────────

function Chip({ children, onRemover, rotuloRemover, arrastavel, onDragStart, onDrop, destaque }) {
  return (
    <div
      draggable={arrastavel}
      onDragStart={onDragStart}
      onDragOver={onDrop ? (e) => e.preventDefault() : undefined}
      onDrop={onDrop}
      className={
        'group inline-flex items-center gap-1 max-w-full min-h-8 pl-1.5 pr-1 py-1 rounded-lg border text-xs ' +
        (destaque ? 'bg-hipo-blueSoft border-hipo-blue/30 ' : 'bg-hipo-card border-hipo-border ') +
        (arrastavel ? 'cursor-grab active:cursor-grabbing' : '')
      }
    >
      {arrastavel && <GripVertical size={12} className="text-hipo-muted shrink-0" />}
      {children}
      <button
        type="button"
        onClick={onRemover}
        aria-label={rotuloRemover}
        className="p-0.5 rounded text-hipo-muted hover:text-hipo-danger hover:bg-hipo-dangerSoft shrink-0"
      >
        <X size={12} />
      </button>
    </div>
  );
}

const SELECT_CHIP =
  'h-6 rounded-md border border-hipo-border bg-hipo-card text-[11px] text-hipo-slate px-1 ' +
  'outline-none focus:border-hipo-blue';

export default function Construtor({ catalogo, fonte, config, consultaBase, onChange }) {
  const [seletor, setSeletor] = useState(null);     // zona aberta no seletor
  const [filtroAberto, setFiltroAberto] = useState(null); // {indice|null, campo}
  const [arrastando, setArrastando] = useState(null); // {zona, indice}

  const campoDe = (chave) => fonte.campos.find((c) => c.chave === chave);
  const limites = catalogo.limites;

  function rotuloValor(v) {
    if (v.campo === REGISTROS) return `Quantidade de ${fonte.rotulo_registro}`;
    return campoDe(v.campo)?.rotulo || v.campo;
  }

  function escolherCampo(chave) {
    const zona = seletor;
    setSeletor(null);
    if (zona === 'filtros') {
      setFiltroAberto({ indice: null, campo: campoDe(chave) });
      return;
    }
    onChange(adicionarNaZona(config, zona, chave, fonte));
  }

  function soltarEm(zona, posicao) {
    return (e) => {
      e.preventDefault();
      e.stopPropagation();
      if (!arrastando) return;
      if (!['linhas', 'colunas'].includes(arrastando.zona) || !['linhas', 'colunas'].includes(zona)) return;
      const limite = limites[zona];
      if (arrastando.zona !== zona && config[zona].length >= limite) return;
      onChange(moverCampo(config, arrastando.zona, arrastando.indice, zona, posicao));
      setArrastando(null);
    };
  }

  function lotada(zona) {
    return config[zona].length >= limites[zona];
  }

  function renderDim(zona) {
    const outra = zona === 'linhas' ? 'colunas' : 'linhas';
    return config[zona].map((item, i) => {
      const def = campoDe(item.campo);
      return (
        <Chip
          key={`${item.campo}-${item.granularidade}-${i}`}
          arrastavel
          onDragStart={() => setArrastando({ zona, indice: i })}
          onDrop={soltarEm(zona, i)}
          onRemover={() => onChange(removerDaZona(config, zona, i))}
          rotuloRemover={`Remover ${def?.rotulo || item.campo} de ${ZONAS[zona].titulo}`}
        >
          <span className="truncate text-hipo-ink">{def?.rotulo || item.campo}</span>
          {def?.tipo === 'data' && (
            <select
              aria-label={`Agrupar ${def.rotulo} por`}
              value={item.granularidade || 'mes'}
              onChange={(e) => onChange(atualizarNaZona(config, zona, i, { granularidade: e.target.value }))}
              className={SELECT_CHIP}
            >
              {Object.entries(catalogo.granularidades).map(([k, r]) => <option key={k} value={k}>{r}</option>)}
            </select>
          )}
          <button
            type="button"
            title={`Mover para ${ZONAS[outra].titulo}`}
            aria-label={`Mover ${def?.rotulo || item.campo} para ${ZONAS[outra].titulo}`}
            disabled={lotada(outra)}
            onClick={() => onChange(moverCampo(config, zona, i, outra))}
            className="p-0.5 rounded text-hipo-muted hover:text-hipo-blue disabled:opacity-30"
          >
            <ArrowLeftRight size={12} />
          </button>
        </Chip>
      );
    });
  }

  function renderValores() {
    return config.valores.map((v, i) => {
      const def = v.campo === REGISTROS ? null : campoDe(v.campo);
      const ags = def ? def.agregacoes : ['contagem'];
      return (
        <Chip
          key={`${v.campo}-${v.agregacao}-${i}`}
          destaque
          onRemover={() => onChange(removerDaZona(config, 'valores', i))}
          rotuloRemover={`Remover valor ${rotuloValor(v)}`}
        >
          {ags.length > 1 ? (
            <select
              aria-label={`Cálculo de ${rotuloValor(v)}`}
              value={v.agregacao}
              onChange={(e) => onChange(atualizarNaZona(config, 'valores', i, { agregacao: e.target.value }))}
              className={SELECT_CHIP}
            >
              {ags.map((a) => <option key={a} value={a}>{catalogo.agregacoes[a]}</option>)}
            </select>
          ) : (
            <span className="text-[11px] text-hipo-slate">{catalogo.agregacoes[v.agregacao]}</span>
          )}
          <span className="truncate text-hipo-ink">{rotuloValor(v)}</span>
        </Chip>
      );
    });
  }

  function renderFiltros() {
    return config.filtros.map((f, i) => {
      const def = campoDe(f.campo);
      return (
        <Chip
          key={`${f.campo}-${i}`}
          onRemover={() => onChange(removerDaZona(config, 'filtros', i))}
          rotuloRemover={`Remover filtro ${def?.rotulo || f.campo}`}
        >
          <button
            type="button"
            onClick={() => setFiltroAberto({ indice: i, campo: def })}
            className="truncate text-left hover:text-hipo-blue"
            title="Editar filtro"
          >
            <span className="text-hipo-ink">{def?.rotulo || f.campo}:</span>{' '}
            <span className="text-hipo-slate">{resumoFiltro(f, def, catalogo.granularidades)}</span>
          </button>
        </Chip>
      );
    });
  }

  const conteudo = {
    filtros: renderFiltros(),
    linhas: renderDim('linhas'),
    colunas: renderDim('colunas'),
    valores: renderValores(),
  };

  const usados = {
    linhas: [...config.linhas, ...config.colunas].map((x) => x.campo),
    colunas: [...config.linhas, ...config.colunas].map((x) => x.campo),
    valores: config.valores.map((x) => x.campo),
    filtros: config.filtros.map((x) => x.campo),
  };

  return (
    <div>
      <div className="grid grid-cols-[minmax(0,1fr)] gap-2 sm:grid-cols-2 xl:grid-cols-4">
        {Object.entries(ZONAS).map(([zona, { titulo, Icone, dica }]) => (
          <section
            key={zona}
            data-testid={`zona-${zona}`}
            aria-label={titulo}
            onDragOver={(e) => e.preventDefault()}
            onDrop={soltarEm(zona, null)}
            className={
              'min-w-0 rounded-lg border border-dashed p-2 min-h-[5.5rem] flex flex-col gap-1.5 transition-colors ' +
              (arrastando && ['linhas', 'colunas'].includes(zona) && arrastando.zona !== zona
                ? 'border-hipo-blue bg-hipo-blueSoft/40' : 'border-hipo-border bg-hipo-bg/40')
            }
          >
            <header className="flex items-center justify-between gap-2">
              <span className="flex items-center gap-1.5 text-xs font-semibold text-hipo-slate" title={dica}>
                <Icone size={13} /> {titulo}
                <span className="font-normal text-hipo-muted">
                  {config[zona].length}/{limites[zona]}
                </span>
              </span>
              <button
                type="button"
                onClick={() => setSeletor(zona)}
                disabled={lotada(zona)}
                aria-label={`Adicionar em ${titulo}`}
                className="inline-flex items-center gap-0.5 text-xs text-hipo-blue hover:underline disabled:opacity-40 disabled:no-underline"
              >
                <Plus size={12} /> Adicionar
              </button>
            </header>
            <div className="flex flex-wrap gap-1.5">
              {conteudo[zona].length ? conteudo[zona] : (
                <span className="text-[11px] text-hipo-muted">{dica}</span>
              )}
            </div>
          </section>
        ))}
      </div>

      {(config.linhas.length > 0 || config.colunas.length > 0) && (
        <div className="flex justify-end mt-1.5">
          <button
            type="button"
            onClick={() => onChange(inverterEixos(config))}
            disabled={config.linhas.length > limites.colunas || config.colunas.length > limites.linhas}
            className="inline-flex items-center gap-1 text-xs text-hipo-slate hover:text-hipo-blue disabled:opacity-40"
          >
            <Repeat size={12} /> Inverter linhas e colunas
          </button>
        </div>
      )}

      <SeletorCampo
        aberto={!!seletor}
        zona={seletor}
        fonte={fonte}
        usados={seletor ? usados[seletor] : []}
        onEscolher={escolherCampo}
        onFechar={() => setSeletor(null)}
      />

      <FiltroCampo
        aberto={!!filtroAberto}
        campo={filtroAberto?.campo}
        filtroInicial={filtroAberto?.indice != null ? config.filtros[filtroAberto.indice] : null}
        consultaBase={consultaBase}
        operadores={catalogo.operadores}
        granularidades={catalogo.granularidades}
        onFechar={() => setFiltroAberto(null)}
        onSalvar={(filtro) => {
          const { indice } = filtroAberto;
          const filtros = indice == null
            ? [...config.filtros, filtro]
            : config.filtros.map((f, i) => (i === indice ? filtro : f));
          setFiltroAberto(null);
          onChange({ ...config, filtros });
        }}
      />
    </div>
  );
}
