// web/src/components/uc/TourGuiado.jsx
//
// O tour guiado da Universidade, desenhado POR CIMA da tela real do HIPO.
//
// Montado uma vez no Layout. Enquanto há tour ativo (tour.js), ele:
//   1. leva para a tela do passo (navigate);
//   2. prepara a tela: remonta a página se ficou algo aberto que o passo
//      não quer, e clica nas âncoras de `clicar` (abrir um cartão, uma aba);
//   3. espera o alvo aparecer (as telas carregam dado depois de montar),
//      rola até ele, ilumina o recorte e põe o balão ao lado;
//   4. no último passo, volta para a aula.
//
// SÓ OLHA. Uma camada transparente cobre a tela inteira e engole o mouse:
// enquanto o tour roda ninguém arrasta cartão, troca fase ou clica em
// Salvar sem querer. Esc, setas e Enter são do tour (a captura impede que
// o Esc feche o modal que o próprio tour abriu).
//
// Alvo que não aparece (tela sem dado, ou estreita demais e o item mora no
// menu sanfona) não trava o tour: o balão vai para o centro e explica.

import { useCallback, useEffect, useLayoutEffect, useRef, useState } from 'react';
import { useLocation, useNavigate } from 'react-router-dom';
import { ArrowLeft, ArrowRight, GraduationCap, X } from 'lucide-react';
import {
  acharAncora, encerrarTour, irParaPasso, pedacosDoTexto, planoDoPasso,
  posicaoDoBalao, recorteDoAlvo, useTour,
} from './tour';

const ESPERA_MS = 6000;
const PASSO_ESPERA_MS = 150;
const PAUSA_CLIQUE_MS = 300;
const LARGURA_BALAO = 360;

function pausa(ms) {
  return new Promise((r) => setTimeout(r, ms));
}

async function esperarAncora(id, cancelado, esperaMs) {
  const fim = Date.now() + esperaMs;
  for (;;) {
    if (cancelado()) return null;
    const el = acharAncora(id);
    if (el) return el;
    if (Date.now() >= fim) return null;
    await pausa(PASSO_ESPERA_MS);
  }
}

function TextoDoPasso({ texto }) {
  return (
    <p className="text-sm text-hipo-slate leading-relaxed whitespace-pre-line">
      {pedacosDoTexto(texto).map((p, i) => (
        p.negrito
          ? <strong key={i} className="text-hipo-ink font-semibold">{p.texto}</strong>
          : <span key={i}>{p.texto}</span>
      ))}
    </p>
  );
}

export default function TourGuiado({ chaveTela = 0, onRemontar, esperaMs = ESPERA_MS }) {
  const tour = useTour();
  const navigate = useNavigate();
  const { pathname } = useLocation();

  // Cliques já dados desde que a página atual foi montada.
  const cliques = useRef([]);
  const ultimaChave = useRef(chaveTela);
  const ultimaRota = useRef(pathname);

  const [estado, setEstado] = useState('preparando'); // preparando | pronto | sem-alvo
  const [elemento, setElemento] = useState(null);
  const [rect, setRect] = useState(null);
  const [tela, setTela] = useState({ largura: window.innerWidth, altura: window.innerHeight });
  const balaoRef = useRef(null);
  const [alturaBalao, setAlturaBalao] = useState(180);

  const passo = tour ? tour.passos[tour.indice] : null;
  const ultimo = tour ? tour.indice === tour.passos.length - 1 : false;

  // Página remontada ou trocada = nada aberto nela.
  if (ultimaChave.current !== chaveTela || ultimaRota.current !== pathname) {
    ultimaChave.current = chaveTela;
    ultimaRota.current = pathname;
    cliques.current = [];
  }

  // ── Preparar a tela do passo ───────────────────────────────────────
  useEffect(() => {
    if (!tour || !passo) return undefined;
    let cancelado = false;
    const foiCancelado = () => cancelado;
    setEstado('preparando');
    setElemento(null);
    setRect(null);

    if (pathname !== passo.rota) {
      navigate(passo.rota);
      return () => { cancelado = true; };
    }

    const plano = planoDoPasso(cliques.current, passo);
    if (plano.remontar) {
      cliques.current = [];
      onRemontar?.();
      return () => { cancelado = true; };
    }

    (async () => {
      for (const id of plano.cliques) {
        const el = await esperarAncora(id, foiCancelado, esperaMs);
        if (cancelado) return;
        if (!el) {
          setEstado('sem-alvo');
          return;
        }
        el.click();
        cliques.current = [...cliques.current, id];
        await pausa(PAUSA_CLIQUE_MS);
      }
      if (!passo.alvo) {
        if (!cancelado) setEstado('pronto');
        return;
      }
      const el = await esperarAncora(passo.alvo, foiCancelado, esperaMs);
      if (cancelado) return;
      if (!el) {
        setEstado('sem-alvo');
        return;
      }
      el.scrollIntoView?.({ block: 'center', inline: 'center' });
      setElemento(el);
      setEstado('pronto');
    })();

    return () => { cancelado = true; };
  }, [tour?.indice, tour?.aulaId, pathname, chaveTela]); // eslint-disable-line react-hooks/exhaustive-deps

  // ── Acompanhar o alvo (a tela rola, carrega e redimensiona) ────────
  useEffect(() => {
    if (!tour) return undefined;
    function medir() {
      setTela({ largura: window.innerWidth, altura: window.innerHeight });
      if (elemento) {
        let el = elemento;
        if (!el.isConnected && passo?.alvo) {
          el = acharAncora(passo.alvo);
          if (el && el !== elemento) setElemento(el);
        }
        if (el && el.isConnected) {
          const r = el.getBoundingClientRect();
          setRect((a) => (a && a.top === r.top && a.left === r.left
            && a.width === r.width && a.height === r.height ? a : {
              top: r.top, left: r.left, width: r.width, height: r.height,
              bottom: r.bottom, right: r.right,
            }));
        }
      }
    }
    medir();
    const t = setInterval(medir, 250);
    window.addEventListener('resize', medir);
    window.addEventListener('scroll', medir, true);
    return () => {
      clearInterval(t);
      window.removeEventListener('resize', medir);
      window.removeEventListener('scroll', medir, true);
    };
  }, [tour, elemento, passo?.alvo]);

  useLayoutEffect(() => {
    if (balaoRef.current) {
      const h = balaoRef.current.offsetHeight;
      if (h && Math.abs(h - alturaBalao) > 2) setAlturaBalao(h);
    }
  });

  const sair = useCallback(() => {
    encerrarTour();
  }, []);

  const avancar = useCallback(() => {
    if (!tour) return;
    if (ultimo) {
      const aula = tour.aulaId;
      encerrarTour();
      navigate(`/uc/aulas/${aula}?tour=fim`);
      return;
    }
    irParaPasso(tour.indice + 1);
  }, [tour, ultimo, navigate]);

  const voltar = useCallback(() => {
    if (tour && tour.indice > 0) irParaPasso(tour.indice - 1);
  }, [tour]);

  // Teclado: o tour fala primeiro (captura), e a tecla não chega na tela.
  useEffect(() => {
    if (!tour) return undefined;
    function onKey(e) {
      const tecla = e.key;
      if (!['Escape', 'ArrowRight', 'ArrowLeft', 'Enter'].includes(tecla)) return;
      e.preventDefault();
      e.stopPropagation();
      if (tecla === 'Escape') sair();
      else if (tecla === 'ArrowLeft') voltar();
      else avancar();
    }
    window.addEventListener('keydown', onKey, true);
    return () => window.removeEventListener('keydown', onKey, true);
  }, [tour, sair, voltar, avancar]);

  if (!tour || !passo) return null;

  const mostrarRecorte = estado === 'pronto' && passo.alvo && rect;
  const recorte = mostrarRecorte ? recorteDoAlvo(rect, tela) : null;
  const pos = posicaoDoBalao(
    mostrarRecorte ? rect : null,
    tela,
    { largura: LARGURA_BALAO, altura: alturaBalao },
  );

  // Clique e mousedown param aqui: nem a tela nem os "clicou fora, fecha"
  // dos painéis abertos ficam sabendo.
  const engolir = (e) => {
    e.stopPropagation();
    e.nativeEvent?.stopImmediatePropagation?.();
  };

  return (
    <div
      className="fixed inset-0 z-[1000]"
      data-testid="tour-guiado"
      onMouseDown={engolir}
      onClick={engolir}
      onPointerDown={engolir}
    >
      {/* Camada que bloqueia a tela. Escurece sozinha quando não há recorte. */}
      <div
        className={'absolute inset-0 ' + (recorte ? '' : 'bg-hipo-ink/50')}
        aria-hidden="true"
      />

      {recorte && (
        <div
          aria-hidden="true"
          data-testid="tour-recorte"
          className="absolute rounded-lg ring-2 ring-hipo-blue pointer-events-none transition-all duration-200"
          style={{
            top: recorte.top,
            left: recorte.left,
            width: recorte.width,
            height: recorte.height,
            boxShadow: '0 0 0 9999px rgba(15, 23, 42, 0.55)',
          }}
        />
      )}

      <div
        ref={balaoRef}
        role="dialog"
        aria-modal="true"
        aria-labelledby="tour-titulo"
        className="absolute bg-hipo-card border border-hipo-border rounded-xl shadow-soft p-4 space-y-3"
        style={{ top: pos.top, left: pos.left, width: pos.largura }}
      >
        <div className="flex items-start gap-2">
          <GraduationCap size={16} className="text-hipo-blue shrink-0 mt-0.5" aria-hidden="true" />
          <div className="flex-1 min-w-0">
            <p className="text-[11px] uppercase tracking-wide text-hipo-muted truncate">
              Passo {tour.indice + 1} de {tour.passos.length}
              {tour.aulaTitulo ? ` · ${tour.aulaTitulo}` : ''}
            </p>
            <h2 id="tour-titulo" className="text-sm font-semibold text-hipo-ink">{passo.titulo}</h2>
          </div>
          <button
            type="button"
            onClick={sair}
            aria-label="Sair do tour"
            title="Sair do tour (Esc)"
            className="p-1 -m-1 rounded text-hipo-slate hover:bg-hipo-bg"
          >
            <X size={16} />
          </button>
        </div>

        {estado === 'preparando' ? (
          <p className="text-sm text-hipo-slate">Abrindo a tela…</p>
        ) : (
          <>
            <TextoDoPasso texto={passo.texto} />
            {estado === 'sem-alvo' && (
              <p className="text-xs text-hipo-warning bg-hipo-warningSoft rounded-md px-2 py-1.5">
                Isto não está aparecendo agora: a tela ainda não tem esse dado para você,
                ou ele fica escondido nesta largura de tela. Siga para o próximo passo.
              </p>
            )}
          </>
        )}

        <div className="flex items-center gap-2 pt-1">
          <div className="flex gap-1 flex-1" aria-hidden="true">
            {tour.passos.map((_, i) => (
              <span
                key={i}
                className={'h-1.5 rounded-full ' + (i === tour.indice ? 'w-4 bg-hipo-blue' : 'w-1.5 bg-hipo-border')}
              />
            ))}
          </div>
          <button
            type="button"
            onClick={voltar}
            disabled={tour.indice === 0}
            className="h-8 px-2.5 rounded-lg text-xs font-medium text-hipo-slate hover:bg-hipo-bg disabled:opacity-40 inline-flex items-center gap-1"
          >
            <ArrowLeft size={14} /> Voltar
          </button>
          <button
            type="button"
            onClick={avancar}
            className="h-8 px-3 rounded-lg text-xs font-semibold bg-hipo-blue text-white hover:opacity-90 inline-flex items-center gap-1"
          >
            {ultimo ? 'Voltar para a aula' : <>Próximo <ArrowRight size={14} /></>}
          </button>
        </div>
      </div>
    </div>
  );
}
