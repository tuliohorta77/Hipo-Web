// web/src/components/uc/tour.js
//
// Estado e regras do tour guiado da Universidade ("Me mostra no HIPO").
//
// O tour atravessa telas: começa na aula, abre Oportunidades, Tarefas,
// Agenda... e volta para a aula no fim. Por isso o estado não vive em
// componente nenhum — fica no sessionStorage (sobrevive à troca de rota e
// ao F5, morre com a aba) e quem precisa reagir escuta o evento EVENTO.
//
// Cada passo diz a tela (`rota`), o elemento a destacar (`alvo`, o valor de
// um atributo data-tour) e, se for preciso abrir algo antes, a lista de
// âncoras a clicar (`clicar`: um cartão, uma aba, um formulário em branco).
// O tour nunca grava nada: o clique é dado só no que abre, e a tela fica
// bloqueada para o mouse enquanto ele roda.

import { useEffect, useState } from 'react';

const CHAVE = 'hipo_tour';
export const EVENTO = 'hipo-tour';

function avisar() {
  window.dispatchEvent(new Event(EVENTO));
}

function valido(t) {
  return !!t && typeof t === 'object' && Array.isArray(t.passos) && t.passos.length > 0
    && Number.isInteger(t.indice) && t.indice >= 0 && t.indice < t.passos.length
    && typeof t.aulaId === 'string' && t.aulaId.length > 0;
}

export function lerTour() {
  try {
    const t = JSON.parse(sessionStorage.getItem(CHAVE) || 'null');
    return valido(t) ? t : null;
  } catch {
    return null;
  }
}

function gravar(t) {
  try {
    sessionStorage.setItem(CHAVE, JSON.stringify(t));
  } catch {
    // Sem sessionStorage (aba privada bloqueada): o tour não começa.
  }
  avisar();
}

export function iniciarTour({ aulaId, aulaTitulo, passos }) {
  if (!Array.isArray(passos) || passos.length === 0) return;
  gravar({ aulaId: String(aulaId), aulaTitulo: aulaTitulo || '', passos, indice: 0 });
}

export function irParaPasso(indice) {
  const t = lerTour();
  if (!t) return;
  const i = Math.max(0, Math.min(indice, t.passos.length - 1));
  if (i === t.indice) return;
  gravar({ ...t, indice: i });
}

export function encerrarTour() {
  try {
    sessionStorage.removeItem(CHAVE);
  } catch {
    // nada a limpar
  }
  avisar();
}

/** O tour ativo, atualizado a cada passo. null quando não há tour. */
export function useTour() {
  const [tour, setTour] = useState(lerTour);
  useEffect(() => {
    const atualizar = () => setTour(lerTour());
    window.addEventListener(EVENTO, atualizar);
    return () => window.removeEventListener(EVENTO, atualizar);
  }, []);
  return tour;
}

// ── Regras puras ─────────────────────────────────────────────────────

/**
 * O que fazer com a tela antes de mostrar um passo.
 *
 * `atuais` são os cliques já dados desde que a tela foi montada; `passo.clicar`
 * é o que o passo precisa ver aberto. Se o que está aberto é o começo do que
 * o passo quer, basta continuar clicando. Se não é (outro cartão aberto, ou
 * o passo quer a tela limpa), a tela é remontada do zero e os cliques
 * refeitos: é o único jeito garantido de fechar o que ficou aberto.
 */
export function planoDoPasso(atuais, passo) {
  const desejados = (passo && passo.clicar) || [];
  const prefixo = atuais.length <= desejados.length
    && atuais.every((c, i) => c === desejados[i]);
  if (prefixo) return { remontar: false, cliques: desejados.slice(atuais.length) };
  return { remontar: true, cliques: desejados };
}

export function seletorDaAncora(id) {
  return `[data-tour="${String(id).replace(/[^a-z0-9-]/g, '')}"]`;
}

/** O primeiro elemento da âncora que está de fato na tela (tem tamanho). */
export function acharAncora(id, raiz = document) {
  const todos = raiz.querySelectorAll(seletorDaAncora(id));
  for (const el of todos) {
    const r = el.getBoundingClientRect();
    if (r.width > 0 && r.height > 0) return el;
  }
  return null;
}

const MARGEM = 12;
const BORDA = 16;

/**
 * Onde o balão fica. Embaixo do alvo se couber, senão em cima, senão
 * encostado no rodapé da tela (alvo grande, como o quadro inteiro).
 * Sem alvo, no centro.
 */
export function posicaoDoBalao(alvo, tela, balao) {
  const largura = Math.min(balao.largura, tela.largura - 2 * BORDA);
  if (!alvo) {
    return {
      lado: 'centro',
      top: Math.max(BORDA, Math.round((tela.altura - balao.altura) / 2)),
      left: Math.round((tela.largura - largura) / 2),
      largura,
    };
  }
  const centro = alvo.left + alvo.width / 2;
  const left = Math.round(Math.min(
    Math.max(BORDA, centro - largura / 2),
    tela.largura - largura - BORDA,
  ));
  if (alvo.bottom + MARGEM + balao.altura <= tela.altura - BORDA) {
    return { lado: 'baixo', top: Math.round(alvo.bottom + MARGEM), left, largura };
  }
  if (alvo.top - MARGEM - balao.altura >= BORDA) {
    return { lado: 'cima', top: Math.round(alvo.top - MARGEM - balao.altura), left, largura };
  }
  return {
    lado: 'rodape',
    top: Math.round(tela.altura - balao.altura - BORDA),
    left: Math.round((tela.largura - largura) / 2),
    largura,
  };
}

/** O recorte iluminado: o alvo com folga, sem sair da tela. */
export function recorteDoAlvo(alvo, tela, folga = 6) {
  const top = Math.max(0, alvo.top - folga);
  const left = Math.max(0, alvo.left - folga);
  const bottom = Math.min(tela.altura, alvo.bottom + folga);
  const right = Math.min(tela.largura, alvo.right + folga);
  return { top, left, width: Math.max(0, right - left), height: Math.max(0, bottom - top) };
}

/** Texto do balão com **negrito**, em pedaços (nada de innerHTML). */
export function pedacosDoTexto(texto) {
  return String(texto || '').split(/(\*\*[^*]+\*\*)/g).filter(Boolean).map((p) => (
    p.startsWith('**') && p.endsWith('**')
      ? { negrito: true, texto: p.slice(2, -2) }
      : { negrito: false, texto: p }
  ));
}
