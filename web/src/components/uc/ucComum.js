// web/src/components/uc/ucComum.js
//
// Universidade Corporativa: o que as telas da UC dividem.
//
// O vídeo chega da API como (provedor, ref), nunca como URL. A URL de embed
// é montada AQUI, a partir de uma tabela fechada: nenhum texto vindo do
// banco vira `<iframe src>` direto. Provedor desconhecido → null, e a tela
// simplesmente não mostra player.

const EMBED = {
  // youtube-nocookie: o player não grava cookie de rastreio antes do play.
  youtube: (ref) => `https://www.youtube-nocookie.com/embed/${ref}?rel=0`,
  vimeo: (ref) => `https://player.vimeo.com/video/${ref}`,
  loom: (ref) => `https://www.loom.com/embed/${ref}`,
  drive: (ref) => `https://drive.google.com/file/d/${ref}/preview`,
};

const REF_SEGURA = /^[A-Za-z0-9_-]{1,120}$/;

export function urlDeEmbed(provedor, ref) {
  if (!provedor || !ref || !REF_SEGURA.test(ref)) return null;
  const montar = EMBED[provedor];
  return montar ? montar(ref) : null;
}

// Cor de cada pilar. Só tokens do manual de marca: azul para Técnica
// (conhecimento), verde para Método (processo que funciona), âmbar para
// Energia (esforço).
export const PILAR_TOM = {
  tecnica: { badge: 'info', barra: 'bg-hipo-blue', icone: 'bg-hipo-blueSoft text-hipo-blue' },
  metodo: { badge: 'success', barra: 'bg-hipo-success', icone: 'bg-hipo-successSoft text-hipo-success' },
  energia: { badge: 'warning', barra: 'bg-hipo-warning', icone: 'bg-hipo-warningSoft text-hipo-warning' },
};

export function tomDoPilar(pilar) {
  return PILAR_TOM[pilar] || PILAR_TOM.tecnica;
}

// Situação da trilha obrigatória → tom do Badge.
export const SITUACAO_TOM = {
  concluida: 'success',
  em_dia: 'info',
  vence_logo: 'warning',
  atrasada: 'danger',
  sem_prazo: 'neutral',
};

/** "2026-10-31" → "31/10/2026", sem passar por Date (fuso não mexe no dia). */
export function dataCurta(iso) {
  if (!iso) return '';
  const [a, m, d] = String(iso).slice(0, 10).split('-');
  return a && m && d ? `${d}/${m}/${a}` : '';
}

export function textoPrazo(situacao, prazo) {
  if (!prazo || !situacao) return '';
  const dias = situacao.dias_restantes;
  if (situacao.codigo === 'concluida') return '';
  if (situacao.codigo === 'atrasada') {
    const n = Math.abs(dias);
    return `venceu há ${n} dia${n === 1 ? '' : 's'} (${dataCurta(prazo)})`;
  }
  if (dias === 0) return `vence hoje (${dataCurta(prazo)})`;
  return `até ${dataCurta(prazo)} · ${dias} dia${dias === 1 ? '' : 's'}`;
}

/** 125 → "2 min 5 s"; 59 → "59 s". Para a trava do "Concluí". */
export function tempoRestante(segundos) {
  const s = Math.max(0, Math.ceil(segundos || 0));
  if (s < 60) return `${s} s`;
  const m = Math.floor(s / 60);
  const r = s % 60;
  return r ? `${m} min ${r} s` : `${m} min`;
}

export function tamanhoArquivo(bytes) {
  if (!bytes) return '';
  if (bytes < 1024 * 1024) return `${Math.max(1, Math.round(bytes / 1024))} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1).replace('.', ',')} MB`;
}

export const ESTADO_AULA = {
  concluida: { rotulo: 'Concluída', tom: 'success' },
  atualizada: { rotulo: 'Atualizada', tom: 'warning' },
  pendente: { rotulo: 'Pendente', tom: 'neutral' },
};
