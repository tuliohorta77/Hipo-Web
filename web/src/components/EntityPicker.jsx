// web/src/components/EntityPicker.jsx
//
// Seletor de entidade reutilizável: campo + lupa (busca) + botão "+" (criar).
// Usado por Conta, Contato e Finder — é o componente que a especificação
// descreve como "uma lupa para procurar uma empresa já cadastrada e um botão
// de mais para cadastrar nova".
//
// Por que popover e não modal: o picker quase sempre vive DENTRO de um
// formulário que já é um modal. Modal sobre modal empilha z-index, rouba o
// foco e faz o Esc fechar os dois de uma vez — o usuário perde o formulário
// que estava preenchendo. O popover resolve no mesmo plano.
//
// Criar inline devolve o registro JÁ SELECIONADO e mantém o formulário pai
// intacto: esse é o ponto do botão "+", senão o usuário teria que sair,
// cadastrar em outra tela e voltar do zero.

import { useCallback, useEffect, useRef, useState } from 'react';
import { Search, Plus, X, ChevronDown, Check } from 'lucide-react';

import Button from './ui/Button';
import Input from './ui/Input';
import Badge from './ui/Badge';
import AlertMessage from './ui/AlertMessage';

const DEBOUNCE_MS = 300;

function mensagemDeErro(err, padrao) {
  const d = err?.response?.data?.detail;
  if (typeof d === 'string') return d;
  if (Array.isArray(d) && d[0]?.msg) return d[0].msg;
  if (d?.mensagem) return d.mensagem;
  return padrao;
}

export default function EntityPicker({
  label,
  value,               // item selecionado (objeto) ou null
  onChange,            // (item | null) => void
  buscar,              // async (q) => item[]
  paraItem,            // (bruto) => { id, titulo, subtitulo?, badge?, desabilitado?, motivoDesabilitado? }
  criar,               // { titulo, campos: [{nome,label,tipo?,obrigatorio?,placeholder?}], onSubmit }
  placeholder = 'Selecione…',
  hint,
  error,
  disabled = false,
  limparAvisoDuplicata,  // opcional: (dados) => Promise<{mensagem, itens}[]> antes de criar
}) {
  const [aberto, setAberto] = useState(false);
  const [modo, setModo] = useState('buscar');   // 'buscar' | 'criar'
  const [termo, setTermo] = useState('');
  const [resultados, setResultados] = useState([]);
  const [carregando, setCarregando] = useState(false);
  const [erroBusca, setErroBusca] = useState(null);
  const [novo, setNovo] = useState({});
  const [erroCriar, setErroCriar] = useState(null);
  const [criando, setCriando] = useState(false);
  const [avisos, setAvisos] = useState([]);
  const wrapper = useRef(null);
  const debounce = useRef(null);

  const selecionado = value ? paraItem(value) : null;

  // Fecha ao clicar fora ou apertar Esc — sem propagar o Esc para o modal pai.
  useEffect(() => {
    if (!aberto) return;
    function fora(e) {
      if (wrapper.current && !wrapper.current.contains(e.target)) setAberto(false);
    }
    function esc(e) {
      if (e.key === 'Escape') {
        e.stopPropagation();
        setAberto(false);
      }
    }
    document.addEventListener('mousedown', fora);
    document.addEventListener('keydown', esc, true);
    return () => {
      document.removeEventListener('mousedown', fora);
      document.removeEventListener('keydown', esc, true);
    };
  }, [aberto]);

  const executarBusca = useCallback(async (q) => {
    setCarregando(true);
    setErroBusca(null);
    try {
      setResultados(await buscar(q));
    } catch (err) {
      setErroBusca(mensagemDeErro(err, 'Não foi possível buscar.'));
      setResultados([]);
    } finally {
      setCarregando(false);
    }
  }, [buscar]);

  useEffect(() => {
    if (!aberto || modo !== 'buscar') return;
    clearTimeout(debounce.current);
    if (!termo.trim()) {
      setResultados([]);
      setCarregando(false);
      return;
    }
    debounce.current = setTimeout(() => executarBusca(termo.trim()), DEBOUNCE_MS);
    return () => clearTimeout(debounce.current);
  }, [termo, aberto, modo, executarBusca]);

  function abrir(modoInicial) {
    if (disabled) return;
    setModo(modoInicial);
    setAberto(true);
    if (modoInicial === 'criar') {
      setNovo({});
      setErroCriar(null);
      setAvisos([]);
    }
  }

  function selecionar(bruto) {
    const item = paraItem(bruto);
    if (item.desabilitado) return;
    onChange(bruto);
    setAberto(false);
    setTermo('');
    setResultados([]);
  }

  async function submeterNovo() {
    const faltando = (criar.campos || [])
      .filter((c) => c.obrigatorio && !String(novo[c.nome] || '').trim())
      .map((c) => c.label);
    if (faltando.length) {
      setErroCriar(`Preencha: ${faltando.join(', ')}.`);
      return;
    }

    setCriando(true);
    setErroCriar(null);
    try {
      // Checagem de duplicata opcional: sugere, não bloqueia. O usuário
      // confirma clicando em criar de novo com os avisos já visíveis.
      if (limparAvisoDuplicata && avisos.length === 0) {
        const encontrados = await limparAvisoDuplicata(novo);
        if (encontrados?.length) {
          setAvisos(encontrados);
          setCriando(false);
          return;
        }
      }
      const criado = await criar.onSubmit(novo);
      onChange(criado);
      setAberto(false);
      setNovo({});
      setAvisos([]);
      setTermo('');
    } catch (err) {
      setErroCriar(mensagemDeErro(err, 'Não foi possível criar.'));
    } finally {
      setCriando(false);
    }
  }

  return (
    <div className={label ? '' : 'mt-0'} ref={wrapper}>
      {label && (
        <label className="block text-sm font-medium text-hipo-ink mb-1.5">{label}</label>
      )}

      <div className="relative">
        <div className="flex gap-2">
          <button
            type="button"
            disabled={disabled}
            onClick={() => abrir('buscar')}
            aria-haspopup="dialog"
            aria-expanded={aberto}
            className={
              'flex-1 h-10 px-3 flex items-center justify-between gap-2 rounded-lg border text-sm text-left ' +
              'transition-colors focus:outline-none focus-visible:ring-2 focus-visible:ring-hipo-blue ' +
              'disabled:opacity-60 disabled:cursor-not-allowed ' +
              (error
                ? 'border-hipo-danger bg-hipo-card'
                : 'border-hipo-border bg-hipo-card hover:bg-hipo-bg')
            }
          >
            <span className="min-w-0 truncate">
              {selecionado ? (
                <>
                  <span className="text-hipo-ink">{selecionado.titulo}</span>
                  {selecionado.subtitulo && (
                    <span className="text-hipo-slate"> · {selecionado.subtitulo}</span>
                  )}
                </>
              ) : (
                <span className="text-hipo-muted">{placeholder}</span>
              )}
            </span>
            <ChevronDown size={14} className="text-hipo-muted shrink-0" />
          </button>

          {selecionado && !disabled && (
            <button
              type="button"
              onClick={() => onChange(null)}
              aria-label={`Limpar ${label || 'seleção'}`}
              className="h-10 w-10 flex items-center justify-center rounded-lg border border-hipo-border text-hipo-slate hover:bg-hipo-bg"
            >
              <X size={16} />
            </button>
          )}

          <button
            type="button"
            disabled={disabled}
            onClick={() => abrir('buscar')}
            aria-label={`Buscar ${label || 'registro'}`}
            className="h-10 w-10 flex items-center justify-center rounded-lg border border-hipo-border text-hipo-slate hover:bg-hipo-bg disabled:opacity-60"
          >
            <Search size={16} />
          </button>

          {criar && (
            <button
              type="button"
              disabled={disabled}
              onClick={() => abrir('criar')}
              aria-label={`Cadastrar ${label || 'novo registro'}`}
              className="h-10 w-10 flex items-center justify-center rounded-lg border border-hipo-border text-hipo-blue hover:bg-hipo-blueSoft disabled:opacity-60"
            >
              <Plus size={16} />
            </button>
          )}
        </div>

        {aberto && (
          <div
            role="dialog"
            aria-label={modo === 'criar' ? criar?.titulo : `Buscar ${label || ''}`}
            className="absolute z-40 mt-1 w-full bg-hipo-card border border-hipo-border rounded-lg shadow-xl p-3 space-y-3"
          >
            {modo === 'buscar' ? (
              <>
                <Input
                  icon={Search}
                  placeholder="Digite para buscar…"
                  value={termo}
                  autoFocus
                  onChange={(e) => setTermo(e.target.value)}
                />

                {erroBusca && <AlertMessage tipo="erro">{erroBusca}</AlertMessage>}

                <div className="max-h-64 overflow-y-auto -mx-1">
                  {carregando ? (
                    <p className="px-3 py-4 text-sm text-hipo-slate text-center">Buscando…</p>
                  ) : !termo.trim() ? (
                    <p className="px-3 py-4 text-sm text-hipo-muted text-center">
                      Digite ao menos uma letra.
                    </p>
                  ) : resultados.length === 0 ? (
                    <p className="px-3 py-4 text-sm text-hipo-slate text-center">
                      Nada encontrado.
                    </p>
                  ) : (
                    <ul>
                      {resultados.map((bruto) => {
                        const it = paraItem(bruto);
                        return (
                          <li key={it.id}>
                            <button
                              type="button"
                              disabled={it.desabilitado}
                              onClick={() => selecionar(bruto)}
                              className={
                                'w-full text-left px-3 py-2 rounded-md flex items-center justify-between gap-2 ' +
                                (it.desabilitado
                                  ? 'opacity-60 cursor-not-allowed'
                                  : 'hover:bg-hipo-bg')
                              }
                            >
                              <span className="min-w-0">
                                <span className="block text-sm text-hipo-ink truncate">
                                  {it.titulo}
                                </span>
                                {it.subtitulo && (
                                  <span className="block text-xs text-hipo-slate truncate">
                                    {it.subtitulo}
                                  </span>
                                )}
                              </span>
                              {it.desabilitado ? (
                                <Badge tone="neutral">
                                  {it.motivoDesabilitado || 'indisponível'}
                                </Badge>
                              ) : it.badge ? (
                                <Badge tone={it.badge.tone || 'info'}>{it.badge.texto}</Badge>
                              ) : null}
                            </button>
                          </li>
                        );
                      })}
                    </ul>
                  )}
                </div>

                {criar && (
                  <div className="pt-1 border-t border-hipo-border">
                    <Button
                      variant="ghost"
                      size="sm"
                      icon={Plus}
                      onClick={() => abrir('criar')}
                      className="w-full"
                    >
                      {criar.titulo || 'Cadastrar novo'}
                    </Button>
                  </div>
                )}
              </>
            ) : (
              <>
                <p className="text-sm font-semibold text-hipo-ink">
                  {criar.titulo || 'Cadastrar novo'}
                </p>

                {erroCriar && <AlertMessage tipo="erro">{erroCriar}</AlertMessage>}

                {avisos.length > 0 && (
                  <AlertMessage tipo="aviso">
                    <div className="space-y-1">
                      <p className="font-medium">Já existe alguém parecido:</p>
                      <ul className="list-disc list-inside">
                        {avisos.map((a) => (
                          <li key={a.id}>{a.texto}</li>
                        ))}
                      </ul>
                      <p>Clique em Criar de novo para cadastrar mesmo assim.</p>
                    </div>
                  </AlertMessage>
                )}

                <div className="space-y-2">
                  {(criar.campos || []).map((campo) => (
                    <Input
                      key={campo.nome}
                      label={campo.obrigatorio ? `${campo.label} *` : campo.label}
                      type={campo.tipo || 'text'}
                      placeholder={campo.placeholder}
                      value={novo[campo.nome] || ''}
                      onChange={(e) =>
                        setNovo((n) => ({ ...n, [campo.nome]: e.target.value }))
                      }
                    />
                  ))}
                </div>

                <div className="flex justify-end gap-2 pt-1">
                  <Button variant="ghost" size="sm" onClick={() => setModo('buscar')}>
                    Voltar
                  </Button>
                  <Button size="sm" icon={Check} loading={criando} onClick={submeterNovo}>
                    Criar
                  </Button>
                </div>
              </>
            )}
          </div>
        )}
      </div>

      {error && <p className="text-sm text-hipo-danger mt-1.5">{error}</p>}
      {hint && !error && <p className="text-sm text-hipo-slate mt-1.5">{hint}</p>}
    </div>
  );
}
