// web/src/components/crm/SeletorComBusca.jsx
//
// Campo de busca que vira lista de chips: digita, escolhe na lista, o item
// entra como chip removível. Serve ao CNAE e ao município da Prospecção.
//
// `opcaoLivre(texto)` permite aceitar o que foi digitado sem estar na lista.
// É o que deixa o SDR escolher a DIVISÃO inteira ("41") em vez de catar as
// subclasses uma a uma — o filtro do backend trata o prefixo como faixa.
//
// A busca tem debounce de 250 ms e descarta resposta velha: quem digita
// "constr" rápido não pode ver a lista de "con" chegar por último.

import { useEffect, useRef, useState } from 'react';
import { X, Search, Loader2 } from 'lucide-react';

export default function SeletorComBusca({
  rotulo,
  placeholder,
  selecionados,          // [{ valor, rotulo }]
  onMudar,               // (novaLista) => void
  buscar,                // async (texto) => [{ valor, rotulo, detalhe? }]
  opcaoLivre,            // (texto) => { valor, rotulo } | null
  minimo = 2,
  maximo = 30,
  desabilitado = false,
}) {
  const [texto, setTexto] = useState('');
  const [opcoes, setOpcoes] = useState([]);
  const [carregando, setCarregando] = useState(false);
  const [aberto, setAberto] = useState(false);
  const pedido = useRef(0);
  const wrapper = useRef(null);

  useEffect(() => {
    const t = texto.trim();
    if (t.length < minimo) {
      setOpcoes([]);
      return undefined;
    }
    const meu = ++pedido.current;
    setCarregando(true);
    const id = setTimeout(async () => {
      try {
        const lista = await buscar(t);
        if (meu === pedido.current) setOpcoes(lista);
      } catch {
        if (meu === pedido.current) setOpcoes([]);
      } finally {
        if (meu === pedido.current) setCarregando(false);
      }
    }, 250);
    return () => clearTimeout(id);
  }, [texto, buscar, minimo]);

  useEffect(() => {
    if (!aberto) return undefined;
    function fora(e) {
      if (wrapper.current && !wrapper.current.contains(e.target)) setAberto(false);
    }
    document.addEventListener('mousedown', fora);
    return () => document.removeEventListener('mousedown', fora);
  }, [aberto]);

  const escolhidos = new Set(selecionados.map((s) => s.valor));
  const livre = opcaoLivre ? opcaoLivre(texto.trim()) : null;
  const lista = [
    ...(livre && !escolhidos.has(livre.valor) ? [{ ...livre, livre: true }] : []),
    ...opcoes.filter((o) => !escolhidos.has(o.valor) && o.valor !== livre?.valor),
  ];
  const cheio = selecionados.length >= maximo;

  function adicionar(opcao) {
    if (cheio) return;
    onMudar([...selecionados, { valor: opcao.valor, rotulo: opcao.rotulo }]);
    setTexto('');
    setOpcoes([]);
    setAberto(false);
  }

  function remover(valor) {
    onMudar(selecionados.filter((s) => s.valor !== valor));
  }

  function aoTeclar(e) {
    if (e.key === 'Enter' && lista.length) {
      e.preventDefault();
      adicionar(lista[0]);
    } else if (e.key === 'Escape') {
      setAberto(false);
    } else if (e.key === 'Backspace' && !texto && selecionados.length) {
      remover(selecionados[selecionados.length - 1].valor);
    }
  }

  return (
    <div ref={wrapper} className="relative">
      <span className="block text-xs font-medium text-hipo-slate mb-1">{rotulo}</span>
      <div
        className={
          'min-h-10 w-full flex flex-wrap items-center gap-1.5 px-2 py-1.5 rounded-lg border bg-hipo-card ' +
          (desabilitado ? 'opacity-60 border-hipo-border' : 'border-hipo-border focus-within:border-hipo-blue')
        }
      >
        {selecionados.map((s) => (
          <span
            key={s.valor}
            className="inline-flex items-center gap-1 pl-2 pr-1 h-7 rounded-md bg-hipo-blueSoft text-hipo-blueDark text-xs font-medium max-w-[16rem]"
            title={s.rotulo}
          >
            <span className="truncate">{s.rotulo}</span>
            <button
              type="button"
              onClick={() => remover(s.valor)}
              className="p-0.5 rounded hover:bg-white/60"
              aria-label={`Remover ${s.rotulo}`}
              disabled={desabilitado}
            >
              <X size={12} />
            </button>
          </span>
        ))}
        <div className="flex-1 min-w-[8rem] flex items-center gap-1.5">
          <Search size={13} className="text-hipo-muted shrink-0" aria-hidden="true" />
          <input
            value={texto}
            onChange={(e) => { setTexto(e.target.value); setAberto(true); }}
            onFocus={() => setAberto(true)}
            onKeyDown={aoTeclar}
            placeholder={cheio ? `Máximo de ${maximo}` : placeholder}
            disabled={desabilitado || cheio}
            aria-label={rotulo}
            className="w-full h-7 bg-transparent outline-none text-sm text-hipo-ink placeholder:text-hipo-muted"
          />
          {carregando && <Loader2 size={13} className="animate-spin text-hipo-muted" />}
        </div>
      </div>

      {aberto && lista.length > 0 && (
        <ul
          role="listbox"
          aria-label={`Opções de ${rotulo}`}
          className="absolute z-30 left-0 right-0 mt-1 max-h-72 overflow-auto bg-hipo-card border border-hipo-border rounded-lg shadow-soft py-1"
        >
          {lista.map((o) => (
            <li key={`${o.livre ? 'livre-' : ''}${o.valor}`}>
              <button
                type="button"
                role="option"
                aria-selected="false"
                onClick={() => adicionar(o)}
                className="w-full text-left px-3 py-2 text-sm hover:bg-hipo-bg flex items-baseline gap-2"
              >
                <span className={o.livre ? 'font-semibold text-hipo-blue' : 'text-hipo-ink'}>
                  {o.rotulo}
                </span>
                {o.detalhe && <span className="text-xs text-hipo-slate truncate">{o.detalhe}</span>}
              </button>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
