// web/src/components/relatorios/FiltroCampo.jsx
//
// Editor de um filtro, no espírito do autofiltro do Excel: a lista de
// valores vem do banco, com quantos registros cada um tem, e já descontados
// os OUTROS filtros e o período — só aparece o que existe.
//
// "(em branco)" é um valor de verdade na lista: oportunidade sem origem é
// uma pergunta legítima ("quantas estão sem origem?"), e não um buraco.
//
// Operadores por tipo:
//   texto    — é um destes · não é nenhum destes · contém
//   número   — é um destes · não é nenhum destes · está entre
//   data     — está entre · é um destes (por dia/semana/mês/…)
//   sim/não  — é um destes

import { useEffect, useMemo, useRef, useState } from 'react';
import { Loader2, Search } from 'lucide-react';
import api from '../../api';
import Modal from '../ui/Modal';
import Button from '../ui/Button';
import AlertMessage from '../ui/AlertMessage';
import { Select } from '../ui/Input';
import { formatarDimensao } from './pivot';
import { mensagemDeErro } from '../crm/tarefaComum';

const NULO = '__em_branco__';

export function operadoresDoTipo(tipo) {
  switch (tipo) {
    case 'texto':
      return ['em', 'nao_em', 'contem'];
    case 'numero':
    case 'moeda':
      return ['em', 'nao_em', 'entre'];
    case 'data':
      return ['entre', 'em'];
    default:
      return ['em'];
  }
}

/** Resumo curto do filtro para o chip. */
export function resumoFiltro(filtro, campo, granularidades = {}) {
  if (!campo) return '';
  const dim = { ...campo, granularidade: filtro.granularidade };
  switch (filtro.operador) {
    case 'entre': {
      const f = (v) => (campo.tipo === 'data' ? formatarDimensao(v, { tipo: 'data', granularidade: 'dia' }) : v);
      if (filtro.minimo && filtro.maximo) return `${f(filtro.minimo)} a ${f(filtro.maximo)}`;
      if (filtro.minimo) return `a partir de ${f(filtro.minimo)}`;
      return `até ${f(filtro.maximo)}`;
    }
    case 'contem':
      return `contém "${filtro.texto}"`;
    default: {
      const nomes = (filtro.valores || []).map((v) => formatarDimensao(v, dim));
      const prefixo = filtro.operador === 'nao_em' ? 'exceto ' : '';
      const gran = campo.tipo === 'data' && filtro.granularidade
        ? ` (${(granularidades[filtro.granularidade] || '').toLowerCase()})` : '';
      if (nomes.length <= 2) return `${prefixo}${nomes.join(', ')}${gran}`;
      return `${prefixo}${nomes.slice(0, 2).join(', ')} +${nomes.length - 2}${gran}`;
    }
  }
}

export default function FiltroCampo({
  aberto, campo, filtroInicial, consultaBase, operadores, granularidades, onSalvar, onFechar,
}) {
  const ops = campo ? operadoresDoTipo(campo.tipo) : [];
  const [operador, setOperador] = useState(ops[0]);
  const [granularidade, setGranularidade] = useState('mes');
  const [marcados, setMarcados] = useState(new Set());
  const [minimo, setMinimo] = useState('');
  const [maximo, setMaximo] = useState('');
  const [texto, setTexto] = useState('');
  const [busca, setBusca] = useState('');
  const [itens, setItens] = useState([]);
  const [truncado, setTruncado] = useState(false);
  const [carregando, setCarregando] = useState(false);
  const [erro, setErro] = useState(null);
  const pedido = useRef(0);

  // Semeia o formulário quando abre.
  useEffect(() => {
    if (!aberto || !campo) return;
    const f = filtroInicial || {};
    setOperador(f.operador && ops.includes(f.operador) ? f.operador : ops[0]);
    setGranularidade(f.granularidade || 'mes');
    setMarcados(new Set((f.valores || []).map((v) => (v === null ? NULO : v))));
    setMinimo(f.minimo || '');
    setMaximo(f.maximo || '');
    setTexto(f.texto || '');
    setBusca('');
    setErro(null);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [aberto, campo?.chave]);

  const usaLista = operador === 'em' || operador === 'nao_em';

  // Valores distintos do campo (com busca, debounced).
  useEffect(() => {
    if (!aberto || !campo || !usaLista || !consultaBase) return undefined;
    const meu = ++pedido.current;
    const t = setTimeout(async () => {
      setCarregando(true);
      try {
        const { data } = await api.post('/crm/relatorios/valores', {
          ...consultaBase,
          campo: campo.chave,
          granularidade: campo.tipo === 'data' ? granularidade : null,
          busca: busca || null,
        });
        if (meu !== pedido.current) return;
        setItens(data.itens || []);
        setTruncado(!!data.truncado);
        setErro(null);
      } catch (err) {
        if (meu === pedido.current) setErro(mensagemDeErro(err, 'Não foi possível carregar os valores.'));
      } finally {
        if (meu === pedido.current) setCarregando(false);
      }
    }, busca ? 300 : 0);
    return () => clearTimeout(t);
  }, [aberto, campo, usaLista, busca, granularidade, consultaBase]);

  const dim = useMemo(() => (campo ? { ...campo, granularidade } : {}), [campo, granularidade]);

  function alternar(valor) {
    const k = valor === null ? NULO : valor;
    setMarcados((atual) => {
      const novo = new Set(atual);
      if (novo.has(k)) novo.delete(k); else novo.add(k);
      return novo;
    });
  }

  function marcarTodos() {
    setMarcados(new Set(itens.map((i) => (i.valor === null ? NULO : i.valor))));
  }

  function aplicar() {
    const base = { campo: campo.chave, operador };
    if (campo.tipo === 'data' && usaLista) base.granularidade = granularidade;
    if (usaLista) {
      if (marcados.size === 0) { setErro('Marque pelo menos um valor.'); return; }
      base.valores = [...marcados].map((v) => (v === NULO ? null : v));
    } else if (operador === 'entre') {
      if (!minimo && !maximo) { setErro('Informe o mínimo, o máximo ou os dois.'); return; }
      base.minimo = minimo || null;
      base.maximo = maximo || null;
    } else {
      if (!texto.trim()) { setErro('Digite o texto a procurar.'); return; }
      base.texto = texto.trim();
    }
    onSalvar(base);
  }

  if (!campo) return null;
  const tipoInput = campo.tipo === 'data' ? 'date' : 'number';

  return (
    <Modal
      aberto={aberto}
      onFechar={onFechar}
      titulo={`Filtro: ${campo.rotulo}`}
      subtitulo={campo.ajuda || undefined}
      size="md"
      nivel={2}
      footer={(
        <div className="flex justify-end gap-2">
          <Button variant="secondary" onClick={onFechar}>Cancelar</Button>
          <Button onClick={aplicar}>Aplicar filtro</Button>
        </div>
      )}
    >
      <div className="space-y-3">
        <div className="flex gap-2">
          <Select
            label="Condição"
            value={operador}
            onChange={(e) => { setOperador(e.target.value); setErro(null); }}
            className="flex-1"
          >
            {ops.map((o) => <option key={o} value={o}>{operadores?.[o] || o}</option>)}
          </Select>
          {campo.tipo === 'data' && usaLista && (
            <Select
              label="Agrupar por"
              value={granularidade}
              onChange={(e) => { setGranularidade(e.target.value); setMarcados(new Set()); }}
              className="w-36"
            >
              {Object.entries(granularidades || {}).map(([k, r]) => <option key={k} value={k}>{r}</option>)}
            </Select>
          )}
        </div>

        {erro && <AlertMessage tipo="erro">{erro}</AlertMessage>}

        {usaLista && (
          <div>
            <div className="relative mb-2">
              <Search size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-hipo-muted" />
              <input
                aria-label="Buscar valor"
                value={busca}
                onChange={(e) => setBusca(e.target.value)}
                placeholder="Buscar valor…"
                className="w-full h-9 pl-9 pr-3 rounded-lg border border-hipo-border text-sm outline-none focus:border-hipo-blue"
              />
            </div>
            <div className="flex items-center justify-between text-xs mb-1.5">
              <span className="text-hipo-slate">{marcados.size} marcado(s)</span>
              <span className="flex gap-3">
                <button type="button" className="text-hipo-blue hover:underline" onClick={marcarTodos}>Marcar todos</button>
                <button type="button" className="text-hipo-blue hover:underline" onClick={() => setMarcados(new Set())}>Limpar</button>
              </span>
            </div>
            <ul className="max-h-72 overflow-y-auto border border-hipo-border rounded-lg divide-y divide-hipo-border">
              {carregando && itens.length === 0 && (
                <li className="px-3 py-4 text-sm text-hipo-slate flex items-center gap-2">
                  <Loader2 size={14} className="animate-spin" /> Carregando valores…
                </li>
              )}
              {!carregando && itens.length === 0 && (
                <li className="px-3 py-4 text-sm text-hipo-slate">Nenhum valor no período.</li>
              )}
              {itens.map((i) => {
                const k = i.valor === null ? NULO : i.valor;
                return (
                  <li key={k}>
                    <label className="flex items-center gap-2.5 px-3 py-2 text-sm cursor-pointer hover:bg-hipo-bg">
                      <input
                        type="checkbox"
                        checked={marcados.has(k)}
                        onChange={() => alternar(i.valor)}
                        className="accent-hipo-blue"
                      />
                      <span className={`flex-1 truncate ${i.valor === null ? 'italic text-hipo-slate' : 'text-hipo-ink'}`}>
                        {formatarDimensao(i.valor, dim)}
                      </span>
                      <span className="text-xs text-hipo-muted tabular-nums">{i.n}</span>
                    </label>
                  </li>
                );
              })}
            </ul>
            {truncado && (
              <p className="text-xs text-hipo-slate mt-1.5">
                Mostrando os 500 valores mais frequentes. Use a busca para achar os demais.
              </p>
            )}
          </div>
        )}

        {operador === 'entre' && (
          <div className="grid grid-cols-2 gap-2">
            <label className="text-sm">
              <span className="block font-medium text-hipo-ink mb-1.5">De</span>
              <input
                type={tipoInput}
                aria-label="Mínimo"
                value={minimo}
                onChange={(e) => setMinimo(e.target.value)}
                className="w-full h-10 px-3 rounded-lg border border-hipo-border text-sm outline-none focus:border-hipo-blue"
              />
            </label>
            <label className="text-sm">
              <span className="block font-medium text-hipo-ink mb-1.5">Até</span>
              <input
                type={tipoInput}
                aria-label="Máximo"
                value={maximo}
                onChange={(e) => setMaximo(e.target.value)}
                className="w-full h-10 px-3 rounded-lg border border-hipo-border text-sm outline-none focus:border-hipo-blue"
              />
            </label>
          </div>
        )}

        {operador === 'contem' && (
          <label className="text-sm block">
            <span className="block font-medium text-hipo-ink mb-1.5">Texto</span>
            <input
              aria-label="Texto do filtro"
              value={texto}
              onChange={(e) => setTexto(e.target.value)}
              className="w-full h-10 px-3 rounded-lg border border-hipo-border text-sm outline-none focus:border-hipo-blue"
            />
          </label>
        )}
      </div>
    </Modal>
  );
}
