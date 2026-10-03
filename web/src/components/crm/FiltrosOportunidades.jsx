// web/src/components/crm/FiltrosOportunidades.jsx
//
// O botão "Filtros" da barra do funil e o painel que ele abre.
//
// ── Por que um botão só ──────────────────────────────────────────────
// A barra de Oportunidades tem orçamento de altura: tudo que não é o funil
// cabe em ~48px (ver o comentário da página). Com os filtros do Relatórios —
// situação, fase, temperatura, período, mensalidade, equipe, origem,
// vertical, parceiro — espalhados na barra, ela quebraria em três linhas e
// comeria as colunas do kanban. Fechados atrás de um botão, custam 32px de
// largura e o número no selo diz quantos estão valendo.
//
// ── Rascunho e Aplicar ───────────────────────────────────────────────
// O painel edita um RASCUNHO; a tela só busca quando o usuário aplica. Com
// aplicação imediata, digitar "2500" na mensalidade faria quatro buscas
// (2, 25, 250, 2500) e cada uma recarregaria o kanban inteiro. Enter em
// qualquer campo aplica, como num formulário.
//
// ── Contrato com o backend ───────────────────────────────────────────
// `paramsDosFiltros` produz exatamente os parâmetros de
// GET /crm/oportunidades{,/resumo,/kanban,/kanban/coluna} — todos aceitam o
// mesmo conjunto (dependência `filtros_funil` no router). Listas (fase,
// situação) vão repetidas na query: `fase=lead&fase=negociacao`.

import { useEffect, useRef, useState } from 'react';
import { SlidersHorizontal, X } from 'lucide-react';

import api from '../../api';
import Button from '../ui/Button';

export const FASES_FILTRO = [
  ['suspect', 'Suspect'],
  ['lead', 'Lead'],
  ['qualificacao', 'Qualificação'],
  ['apresentacao', 'Apresentação'],
  ['negociacao', 'Negociação'],
  ['finalizado', 'Finalizado'],
];

// Mesmos rótulos do Relatórios (services/relatorios.py, SITUACOES_OPP):
// quem monta um relatório e depois filtra o funil lê as mesmas palavras.
export const SITUACOES_FILTRO = [
  ['ativa', 'Ativa'],
  ['suspensa', 'Suspensa'],
  ['conquistado', 'Conquistada'],
  ['perdido', 'Perdida'],
  ['cancelado', 'Cancelada'],
];

export const DATAS_FILTRO = [
  ['criacao', 'Criação'],
  ['previsao', 'Previsão de fechamento'],
  ['desfecho', 'Desfecho (ganho/perda)'],
  ['atualizacao', 'Última atualização'],
];

const PAPEIS = ['EV', 'SDR', 'EC'];
const TEMPERATURAS = [0, 10, 20, 30, 40, 50, 60, 70, 80, 90];

export const FILTROS_PADRAO = {
  status: [],
  fase: [],
  temperatura_min: '',
  temperatura_max: '',
  data_campo: 'criacao',
  data_de: '',
  data_ate: '',
  valor_min: '',
  valor_max: '',
  envolvido_id: '',
  papel: '',
  origem_id: '',
  vertical_id: '',
  veio_de_parceiro: '',   // '' = qualquer · 'sim' · 'nao'
};

const preenchido = (v) => v !== '' && v !== null && v !== undefined;

/** Parâmetros de query para a API. Só entra o que está preenchido. */
export function paramsDosFiltros(f) {
  const p = {};
  if (f.status?.length) p.status = f.status;
  if (f.fase?.length) p.fase = f.fase;
  if (preenchido(f.temperatura_min)) p.temperatura_min = Number(f.temperatura_min);
  if (preenchido(f.temperatura_max)) p.temperatura_max = Number(f.temperatura_max);
  if (f.data_de || f.data_ate) {
    p.data_campo = f.data_campo || 'criacao';
    if (f.data_de) p.data_de = f.data_de;
    if (f.data_ate) p.data_ate = f.data_ate;
  }
  if (preenchido(f.valor_min)) p.valor_min = Number(f.valor_min);
  if (preenchido(f.valor_max)) p.valor_max = Number(f.valor_max);
  if (f.envolvido_id) p.envolvido_id = f.envolvido_id;
  if (f.papel) p.papel = f.papel;
  if (f.origem_id) p.origem_id = Number(f.origem_id);
  if (f.vertical_id) p.vertical_id = Number(f.vertical_id);
  if (f.veio_de_parceiro) p.veio_de_parceiro = f.veio_de_parceiro === 'sim';
  return p;
}

/** Quantos GRUPOS de filtro estão valendo — é o número do selo. */
export function contarFiltros(f) {
  return [
    f.status?.length > 0,
    f.fase?.length > 0,
    preenchido(f.temperatura_min) || preenchido(f.temperatura_max),
    Boolean(f.data_de || f.data_ate),
    preenchido(f.valor_min) || preenchido(f.valor_max),
    Boolean(f.envolvido_id || f.papel),
    Boolean(f.origem_id),
    Boolean(f.vertical_id),
    Boolean(f.veio_de_parceiro),
  ].filter(Boolean).length;
}

// Data local em YYYY-MM-DD. toISOString() daria o dia em UTC, e às 22h de
// São Paulo "hoje" já seria amanhã.
function iso(d) {
  const m = String(d.getMonth() + 1).padStart(2, '0');
  const dia = String(d.getDate()).padStart(2, '0');
  return `${d.getFullYear()}-${m}-${dia}`;
}

export function periodoRapido(chave, hoje = new Date()) {
  const a = hoje.getFullYear();
  const m = hoje.getMonth();
  switch (chave) {
    case 'este_mes':
      return [iso(new Date(a, m, 1)), iso(new Date(a, m + 1, 0))];
    case 'mes_passado':
      return [iso(new Date(a, m - 1, 1)), iso(new Date(a, m, 0))];
    case 'ultimos_30':
      return [iso(new Date(a, m, hoje.getDate() - 29)), iso(hoje)];
    default:
      return ['', ''];
  }
}

const PERIODOS_RAPIDOS = [
  ['este_mes', 'Este mês'],
  ['mes_passado', 'Mês passado'],
  ['ultimos_30', 'Últimos 30 dias'],
];

const CLASSE_CAMPO =
  'h-8 w-full text-xs rounded-lg border border-hipo-border bg-hipo-card text-hipo-ink px-2 ' +
  'focus:outline-none focus:ring-2 focus:ring-hipo-blue';

function Chip({ ativo, onClick, children }) {
  return (
    <button
      type="button"
      aria-pressed={ativo}
      onClick={onClick}
      className={
        'h-7 px-2.5 rounded-full text-xs border transition-colors ' +
        (ativo
          ? 'bg-hipo-blue text-white border-hipo-blue'
          : 'bg-hipo-card text-hipo-slate border-hipo-border hover:bg-hipo-bg')
      }
    >
      {children}
    </button>
  );
}

function Secao({ titulo, children, erro }) {
  return (
    <fieldset className="space-y-1.5">
      <legend className="text-[11px] font-semibold uppercase tracking-wide text-hipo-slate mb-1.5">
        {titulo}
      </legend>
      {children}
      {erro && <p className="text-[11px] text-hipo-danger">{erro}</p>}
    </fieldset>
  );
}

function alternar(lista, valor) {
  return lista.includes(valor) ? lista.filter((v) => v !== valor) : [...lista, valor];
}

function faixaInvertida(min, max) {
  return preenchido(min) && preenchido(max) && Number(min) > Number(max);
}

export default function FiltrosOportunidades({ valor, usuarios = [], onAplicar }) {
  const [aberto, setAberto] = useState(false);
  const [rascunho, setRascunho] = useState(valor);
  const [origens, setOrigens] = useState(null);
  const [verticais, setVerticais] = useState(null);
  const raiz = useRef(null);

  const ativos = contarFiltros(valor);

  // Toda abertura começa do que está APLICADO: fechar sem aplicar descarta
  // o rascunho, como qualquer painel de filtro.
  useEffect(() => {
    if (aberto) setRascunho(valor);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [aberto]);

  // Origens e verticais só na primeira abertura: a maioria das cargas da tela
  // nunca abre o painel, e duas requests fixas por carga seriam desperdício.
  // Ref e não o estado como guarda: com `origens` nas dependências, a chegada
  // da primeira lista re-rodava o efeito e buscava a segunda de novo.
  const listasPedidas = useRef(false);
  useEffect(() => {
    if (!aberto || listasPedidas.current) return;
    listasPedidas.current = true;
    api.get('/crm/dominio/origens')
      .then(({ data }) => setOrigens(Array.isArray(data) ? data : []))
      .catch(() => setOrigens([]));
    api.get('/crm/dominio/verticais')
      .then(({ data }) => setVerticais(Array.isArray(data) ? data : []))
      .catch(() => setVerticais([]));
  }, [aberto]);

  // Fecha com clique fora e com Esc.
  useEffect(() => {
    if (!aberto) return undefined;
    function fora(e) {
      if (raiz.current && !raiz.current.contains(e.target)) setAberto(false);
    }
    function esc(e) {
      if (e.key === 'Escape') setAberto(false);
    }
    document.addEventListener('mousedown', fora);
    document.addEventListener('keydown', esc);
    return () => {
      document.removeEventListener('mousedown', fora);
      document.removeEventListener('keydown', esc);
    };
  }, [aberto]);

  const set = (campo, v) => setRascunho((r) => ({ ...r, [campo]: v }));

  const erroTemp = faixaInvertida(rascunho.temperatura_min, rascunho.temperatura_max)
    ? 'A mínima é maior que a máxima.' : null;
  const erroValor = faixaInvertida(rascunho.valor_min, rascunho.valor_max)
    ? 'O mínimo é maior que o máximo.' : null;
  const erroData = rascunho.data_de && rascunho.data_ate && rascunho.data_de > rascunho.data_ate
    ? 'A data inicial é depois da final.' : null;
  const invalido = Boolean(erroTemp || erroValor || erroData);

  function aplicar(e) {
    e?.preventDefault();
    if (invalido) return;
    onAplicar(rascunho);
    setAberto(false);
  }

  return (
    <div data-tour="opo-filtros" ref={raiz} className="relative">
      <button
        type="button"
        onClick={() => setAberto((a) => !a)}
        aria-expanded={aberto}
        data-tour="opo-filtros-botao"
        aria-haspopup="dialog"
        aria-label={ativos ? `Filtros (${ativos} ativos)` : 'Filtros'}
        className={
          'h-8 px-2.5 text-xs rounded-lg border inline-flex items-center gap-1.5 transition-colors ' +
          (ativos || aberto
            ? 'border-hipo-blue text-hipo-blue bg-hipo-blueSoft'
            : 'border-hipo-border text-hipo-slate bg-hipo-card hover:bg-hipo-bg')
        }
      >
        <SlidersHorizontal size={14} />
        Filtros
        {ativos > 0 && (
          <span className="min-w-[1.1rem] h-[1.1rem] px-1 rounded-full bg-hipo-blue text-white text-[10px] font-semibold grid place-items-center">
            {ativos}
          </span>
        )}
      </button>

      {aberto && (
        <form
          role="dialog"
          aria-label="Filtrar oportunidades"
          onSubmit={aplicar}
          className="absolute right-0 top-full mt-1 z-40 w-[26rem] max-w-[calc(100vw-2rem)] rounded-xl border border-hipo-border bg-hipo-card shadow-lg flex flex-col max-h-[75vh]"
        >
          <div className="shrink-0 flex items-center justify-between px-4 py-2.5 border-b border-hipo-border">
            <h2 className="text-sm font-semibold text-hipo-ink">Filtrar oportunidades</h2>
            <button
              type="button"
              onClick={() => setAberto(false)}
              aria-label="Fechar filtros"
              className="h-7 w-7 inline-flex items-center justify-center rounded-lg text-hipo-slate hover:bg-hipo-bg"
            >
              <X size={14} />
            </button>
          </div>

          <div className="flex-1 min-h-0 overflow-y-auto px-4 py-3 space-y-4">
            <Secao titulo="Situação">
              <div className="flex flex-wrap gap-1.5">
                {SITUACOES_FILTRO.map(([v, r]) => (
                  <Chip key={v} ativo={rascunho.status.includes(v)}
                    onClick={() => set('status', alternar(rascunho.status, v))}>
                    {r}
                  </Chip>
                ))}
              </div>
            </Secao>

            <Secao titulo="Fase">
              <div className="flex flex-wrap gap-1.5">
                {FASES_FILTRO.map(([v, r]) => (
                  <Chip key={v} ativo={rascunho.fase.includes(v)}
                    onClick={() => set('fase', alternar(rascunho.fase, v))}>
                    {r}
                  </Chip>
                ))}
              </div>
            </Secao>

            <Secao titulo="Período" erro={erroData}>
              <select
                aria-label="Data de referência"
                value={rascunho.data_campo}
                onChange={(e) => set('data_campo', e.target.value)}
                className={CLASSE_CAMPO}
              >
                {DATAS_FILTRO.map(([v, r]) => <option key={v} value={v}>{r}</option>)}
              </select>
              <div className="grid grid-cols-2 gap-2">
                <input type="date" aria-label="Data inicial" value={rascunho.data_de}
                  onChange={(e) => set('data_de', e.target.value)} className={CLASSE_CAMPO} />
                <input type="date" aria-label="Data final" value={rascunho.data_ate}
                  onChange={(e) => set('data_ate', e.target.value)} className={CLASSE_CAMPO} />
              </div>
              <div className="flex flex-wrap gap-1.5">
                {PERIODOS_RAPIDOS.map(([k, r]) => {
                  const [de, ate] = periodoRapido(k);
                  return (
                    <Chip key={k} ativo={rascunho.data_de === de && rascunho.data_ate === ate}
                      onClick={() => setRascunho((x) => ({ ...x, data_de: de, data_ate: ate }))}>
                      {r}
                    </Chip>
                  );
                })}
              </div>
            </Secao>

            <div className="grid grid-cols-2 gap-4">
              <Secao titulo="Temperatura (%)" erro={erroTemp}>
                <div className="grid grid-cols-2 gap-2">
                  <select aria-label="Temperatura mínima" value={rascunho.temperatura_min}
                    onChange={(e) => set('temperatura_min', e.target.value)} className={CLASSE_CAMPO}>
                    <option value="">de</option>
                    {TEMPERATURAS.map((t) => <option key={t} value={t}>{t}</option>)}
                  </select>
                  <select aria-label="Temperatura máxima" value={rascunho.temperatura_max}
                    onChange={(e) => set('temperatura_max', e.target.value)} className={CLASSE_CAMPO}>
                    <option value="">até</option>
                    {TEMPERATURAS.map((t) => <option key={t} value={t}>{t}</option>)}
                  </select>
                </div>
              </Secao>

              <Secao titulo="Mensalidade (R$)" erro={erroValor}>
                <div className="grid grid-cols-2 gap-2">
                  <input type="number" min="0" step="0.01" placeholder="mín."
                    aria-label="Mensalidade mínima" value={rascunho.valor_min}
                    onChange={(e) => set('valor_min', e.target.value)} className={CLASSE_CAMPO} />
                  <input type="number" min="0" step="0.01" placeholder="máx."
                    aria-label="Mensalidade máxima" value={rascunho.valor_max}
                    onChange={(e) => set('valor_max', e.target.value)} className={CLASSE_CAMPO} />
                </div>
              </Secao>
            </div>

            <Secao titulo="Equipe">
              <div className="grid grid-cols-[1fr_7rem] gap-2">
                <select aria-label="Envolvido" value={rascunho.envolvido_id}
                  onChange={(e) => set('envolvido_id', e.target.value)} className={CLASSE_CAMPO}>
                  <option value="">Qualquer pessoa</option>
                  {usuarios.map((u) => <option key={u.id} value={u.id}>{u.nome}</option>)}
                </select>
                <select aria-label="Papel" value={rascunho.papel}
                  onChange={(e) => set('papel', e.target.value)} className={CLASSE_CAMPO}>
                  <option value="">Todo papel</option>
                  {PAPEIS.map((p) => <option key={p} value={p}>{p}</option>)}
                </select>
              </div>
            </Secao>

            <div className="grid grid-cols-2 gap-4">
              <Secao titulo="Origem do lead">
                <select aria-label="Origem" value={rascunho.origem_id}
                  onChange={(e) => set('origem_id', e.target.value)} className={CLASSE_CAMPO}>
                  <option value="">Todas</option>
                  {(origens || []).map((o) => <option key={o.id} value={o.id}>{o.nome}</option>)}
                </select>
              </Secao>
              <Secao titulo="Vertical">
                <select aria-label="Vertical" value={rascunho.vertical_id}
                  onChange={(e) => set('vertical_id', e.target.value)} className={CLASSE_CAMPO}>
                  <option value="">Todas</option>
                  {(verticais || []).map((v) => <option key={v.id} value={v.id}>{v.nome}</option>)}
                </select>
              </Secao>
            </div>

            <Secao titulo="Indicação de parceiro">
              <div className="flex flex-wrap gap-1.5">
                {[['', 'Qualquer'], ['sim', 'Veio de parceiro'], ['nao', 'Sem parceiro']].map(([v, r]) => (
                  <Chip key={v || 'qualquer'} ativo={rascunho.veio_de_parceiro === v}
                    onClick={() => set('veio_de_parceiro', v)}>
                    {r}
                  </Chip>
                ))}
              </div>
            </Secao>
          </div>

          <div className="shrink-0 flex items-center justify-between gap-2 px-4 py-2.5 border-t border-hipo-border">
            <Button type="button" size="sm" variant="ghost" onClick={() => setRascunho(FILTROS_PADRAO)}>
              Limpar
            </Button>
            <Button type="submit" size="sm" disabled={invalido}>
              Aplicar filtros
            </Button>
          </div>
        </form>
      )}
    </div>
  );
}
