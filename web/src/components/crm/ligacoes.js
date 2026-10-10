// web/src/components/crm/ligacoes.js
//
// O que as telas de ligação compartilham (entrega 056 — Vivo Voz Negócio):
// o aviso de clique em "ligar", os rótulos e as formatações.
//
// Sem JSX de propósito: o contatoComum importa daqui e é importado por
// meio CRM; um arquivo só de funções não arrasta componente nenhum junto.

import api from '../../api';

/**
 * Avisa o HIPO que a pessoa vai ligar. Fogo e esquece: o tel: abre o
 * softphone na mesma hora, e a ligação não pode esperar o servidor (nem
 * falhar porque ele caiu). Se o aviso não chegar, a gravação entra sem
 * vínculo e a pessoa vincula depois.
 *
 * `contexto`: { oportunidade_id?, conta_id?, tarefa_id?, contato_id? }
 */
export function registrarLigacao(contexto, numero) {
  const corpo = { telefone: String(numero || '') };
  for (const [k, v] of Object.entries(contexto || {})) {
    if (v) corpo[k] = v;
  }
  try {
    const p = api.post('/crm/ligacoes', corpo);
    if (p && typeof p.catch === 'function') p.catch(() => {});
  } catch {
    /* nada: o softphone já está abrindo */
  }
}

/** 185 → "3:05"; 3725 → "1:02:05"; vazio → "—". */
export function duracaoTexto(segundos) {
  if (segundos === null || segundos === undefined || segundos === '') return '—';
  const s = Math.max(0, Math.round(Number(segundos)));
  const h = Math.floor(s / 3600);
  const m = Math.floor((s % 3600) / 60);
  const ss = String(s % 60).padStart(2, '0');
  return h ? `${h}:${String(m).padStart(2, '0')}:${ss}` : `${m}:${ss}`;
}

export function dataHoraCurta(iso) {
  if (!iso) return '—';
  return new Date(iso).toLocaleString('pt-BR', {
    timeZone: 'America/Sao_Paulo', day: '2-digit', month: '2-digit',
    hour: '2-digit', minute: '2-digit',
  });
}

// Mesmo vocabulário de services/ligacao.ROTULO_STATUS; o servidor manda o
// rótulo pronto, e isto é só o tom da etiqueta.
export const TOM_STATUS = {
  discando: 'neutral',
  enviando: 'info',
  transcrevendo: 'info',
  pronta: 'success',
  sem_fala: 'neutral',
  sem_gravacao: 'warning',
  erro: 'danger',
};

export const EM_ANDAMENTO = ['discando', 'enviando', 'transcrevendo'];

/** A hora em que a ligação aconteceu: início do áudio, ou o clique. */
export function quando(lig) {
  return lig.inicio_em || lig.clicada_em || lig.criado_em;
}
