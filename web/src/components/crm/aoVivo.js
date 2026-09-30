// web/src/components/crm/aoVivo.js
//
// A lógica da "Reunião ao vivo" que não depende de tela: suporte do
// navegador, fila de falas a enviar, contagem de palavras, e o
// reconhecedor de voz com religamento automático.
//
// ── Como a captura funciona ──────────────────────────────────────────
// Dois áudios, dois reconhecedores do próprio Chrome (Web Speech API):
//
//   vendedor -> microfone (getUserMedia)
//   cliente  -> som da aba do Meet (getDisplayMedia, "Compartilhar áudio
//               da guia")
//
// O Meet não devolve para a aba a voz de quem fala nela, então cada canal
// tem uma pessoa só: a separação de quem falou vem de graça.
//
// Desde o Chrome 133 o reconhecedor aceita uma MediaStreamTrack em
// `start(track)`. Antes disso ele IGNORA o argumento e escuta o microfone
// — e os dois canais transcreveriam o vendedor sem erro nenhum. Por isso a
// versão é conferida antes, e não confiada.
//
// ── O áudio não sai do navegador para o HIPO ─────────────────────────
// Só texto vai para o servidor, em lotes. O reconhecimento do Chrome manda
// o áudio para o serviço de voz do Google — é isso que deixa o custo em
// zero. Avisar o cliente de que a conversa é transcrita continua sendo do
// vendedor, como já é com a transcrição do Meet.

export const VERSAO_MINIMA_CHROME = 133;
export const CANAIS = ['vendedor', 'cliente'];
export const ROTULO_CANAL = { vendedor: 'Você', cliente: 'Cliente' };
export const INTERVALO_ENVIO_MS = 10000;
export const MAX_FALAS_POR_LOTE = 300;

// Religamento: o reconhecedor do Chrome encerra sozinho depois de
// silêncio ou de ~1 minuto de fala contínua, e a tela o religa. Se ele
// morrer mais que isto em um minuto, o problema não é silêncio — é rede
// ou serviço — e insistir só enche o log.
export const MAX_RELIGAMENTOS_POR_MINUTO = 12;

// ── Suporte ──────────────────────────────────────────────────────────

/** Versão principal do Chromium, ou null quando não é Chromium. */
export function versaoChromium(nav = globalThis.navigator) {
  const marcas = nav?.userAgentData?.brands;
  if (Array.isArray(marcas)) {
    const m = marcas.find((b) => /Chromium|Google Chrome/i.test(b?.brand || ''));
    if (m) {
      const v = parseInt(m.version, 10);
      return Number.isFinite(v) ? v : null;
    }
  }
  const ua = nav?.userAgent || '';
  if (/Firefox\//.test(ua)) return null;
  const achado = ua.match(/Chrom(?:e|ium)\/(\d+)/);
  return achado ? parseInt(achado[1], 10) : null;
}

/** "Chrome 141" para gravar na sessão; ajuda a ler as falhas depois. */
export function descreverNavegador(nav = globalThis.navigator) {
  const v = versaoChromium(nav);
  if (v == null) return (nav?.userAgent || 'desconhecido').slice(0, 120);
  const edge = /Edg\//.test(nav?.userAgent || '')
    || (nav?.userAgentData?.brands || []).some((b) => /Edge/i.test(b?.brand || ''));
  return `${edge ? 'Edge' : 'Chrome'} ${v}`;
}

export function construtorDeReconhecimento(win = globalThis.window) {
  return win?.SpeechRecognition || win?.webkitSpeechRecognition || null;
}

/**
 * { ok, motivo }. `motivo` é a frase para a tela quando não dá.
 */
export function diagnosticarSuporte(win = globalThis.window) {
  const nav = win?.navigator;
  if (!construtorDeReconhecimento(win)) {
    return {
      ok: false,
      motivo: 'Este navegador não tem reconhecimento de voz. Use o Google Chrome atualizado.',
    };
  }
  const v = versaoChromium(nav);
  if (v == null || v < VERSAO_MINIMA_CHROME) {
    return {
      ok: false,
      motivo:
        `A transcrição ao vivo precisa do Chrome ${VERSAO_MINIMA_CHROME} ou mais novo` +
        (v ? ` (este é o ${v}).` : '.') +
        ' Atualize em Menu → Ajuda → Sobre o Google Chrome.',
    };
  }
  if (!nav?.mediaDevices?.getDisplayMedia || !nav?.mediaDevices?.getUserMedia) {
    return { ok: false, motivo: 'Este navegador não permite capturar o áudio da aba.' };
  }
  return { ok: true, motivo: null };
}

// ── Palavras ─────────────────────────────────────────────────────────

/** Mesma régua do servidor (services/ao_vivo.palavras). */
export function contarPalavras(texto) {
  if (!texto) return 0;
  const limpo = texto
    .toLowerCase()
    .normalize('NFD')
    .replace(/[̀-ͯ]/g, '');
  const achadas = limpo.match(/[\p{L}\p{N}_]+/gu);
  return achadas ? achadas.length : 0;
}

/** Palavras por canal e a proporção do vendedor (null sem palavra). */
export function metricasDasFalas(falas) {
  let vendedor = 0;
  let cliente = 0;
  for (const f of falas || []) {
    const n = contarPalavras(f.texto);
    if (f.canal === 'vendedor') vendedor += n;
    else if (f.canal === 'cliente') cliente += n;
  }
  const total = vendedor + cliente;
  return {
    palavras_vendedor: vendedor,
    palavras_cliente: cliente,
    palavras_total: total,
    proporcao_vendedor_pct: total ? Math.round((100 * vendedor) / total) : null,
  };
}

export function formatarCronometro(ms) {
  const s = Math.max(0, Math.floor((ms || 0) / 1000));
  const h = Math.floor(s / 3600);
  const m = Math.floor((s % 3600) / 60);
  const seg = s % 60;
  const dois = (n) => String(n).padStart(2, '0');
  return h ? `${h}:${dois(m)}:${dois(seg)}` : `${dois(m)}:${dois(seg)}`;
}

// ── Fila de envio ────────────────────────────────────────────────────

/**
 * As falas reconhecidas esperando para ir ao servidor.
 *
 * Cada fala ganha um `seq` na hora em que entra, e ele não muda: se o
 * envio falhar, o mesmo lote vai de novo com os mesmos números, e o
 * servidor ignora o que já tinha (UNIQUE por sessão). Só sai da fila o que
 * o servidor confirmou.
 */
export function criarFila() {
  let proximo = 0;
  let pendentes = [];
  let erros = [];
  return {
    adicionar({ canal, texto, inicio, fim, confianca }) {
      const limpo = (texto || '').replace(/\s+/g, ' ').trim();
      if (!limpo) return null;
      const fala = {
        seq: proximo++,
        canal,
        texto: limpo,
        inicio: inicio instanceof Date ? inicio.toISOString() : inicio,
        fim: fim instanceof Date ? fim.toISOString() : (fim ?? null),
        confianca: typeof confianca === 'number' && confianca > 0 && confianca <= 1
          ? confianca : null,
      };
      pendentes.push(fala);
      return fala;
    },
    registrarErro(canal, erro) {
      erros.push({ canal, erro: String(erro).slice(0, 200), em: new Date().toISOString() });
    },
    lote(max = MAX_FALAS_POR_LOTE) {
      return { falas: pendentes.slice(0, max), erros: erros.slice(0, 50) };
    },
    confirmar(lote) {
      const enviados = new Set(lote.falas.map((f) => f.seq));
      pendentes = pendentes.filter((f) => !enviados.has(f.seq));
      erros = erros.slice(lote.erros.length);
    },
    get pendentes() { return pendentes.length; },
    get temAlgo() { return pendentes.length > 0 || erros.length > 0; },
  };
}

// ── Erros do reconhecimento ──────────────────────────────────────────

// Os que acontecem em toda call e não querem dizer nada: silêncio, e o
// `aborted` que o próprio `stop()` provoca.
const ERROS_NORMAIS = new Set(['no-speech', 'aborted']);

// Os que não se resolvem religando: permissão, idioma, serviço bloqueado.
const ERROS_FATAIS = new Set([
  'not-allowed', 'service-not-allowed', 'language-not-supported', 'audio-capture',
]);

const FRASE_ERRO = {
  'not-allowed': 'o navegador não permitiu o reconhecimento de voz',
  'service-not-allowed': 'o serviço de voz do Chrome está bloqueado nesta máquina',
  'language-not-supported': 'o português não está disponível no reconhecimento de voz',
  'audio-capture': 'não chegou áudio deste canal',
  network: 'o reconhecimento de voz perdeu a conexão com o serviço do Google',
};

export function erroENormal(codigo) {
  return ERROS_NORMAIS.has(codigo);
}

export function erroEFatal(codigo) {
  return ERROS_FATAIS.has(codigo);
}

export function fraseDoErro(codigo) {
  return FRASE_ERRO[codigo] || `erro do reconhecimento de voz (${codigo})`;
}

// ── Reconhecedor com religamento ─────────────────────────────────────

/**
 * Um reconhecedor de voz preso a uma trilha de áudio.
 *
 *   aoFinal({ canal, texto, inicio, fim, confianca })   trecho fechado
 *   aoParcial(canal, texto)                             o que está saindo
 *   aoErro(canal, codigo, fatal)                        erro relevante
 *   aoEstado(canal, estado)   'ouvindo' | 'religando' | 'parado' | 'falhou'
 *
 * `agora` é injetável para teste, como o `hoje` das regras do backend.
 */
export function criarReconhecedor({
  canal, track, Construtor, lang = 'pt-BR',
  aoFinal, aoParcial, aoErro, aoEstado,
  agora = () => new Date(),
}) {
  let ativo = false;
  let rec = null;
  let inicioDoTrecho = null;
  let religamentos = [];
  let aoTerminar = null;

  function montar() {
    const r = new Construtor();
    r.lang = lang;
    r.continuous = true;
    r.interimResults = true;
    r.maxAlternatives = 1;

    r.onresult = (ev) => {
      let parcial = '';
      for (let i = ev.resultIndex; i < ev.results.length; i += 1) {
        const res = ev.results[i];
        const alt = res[0] || {};
        if (res.isFinal) {
          const texto = (alt.transcript || '').trim();
          if (texto) {
            aoFinal?.({
              canal,
              texto,
              inicio: inicioDoTrecho || agora(),
              fim: agora(),
              confianca: alt.confidence,
            });
          }
          inicioDoTrecho = null;
        } else {
          if (!inicioDoTrecho) inicioDoTrecho = agora();
          parcial += alt.transcript || '';
        }
      }
      aoParcial?.(canal, parcial.trim());
    };

    r.onerror = (ev) => {
      const codigo = ev?.error || 'desconhecido';
      if (erroENormal(codigo)) return;
      const fatal = erroEFatal(codigo);
      aoErro?.(canal, codigo, fatal);
      if (fatal) {
        ativo = false;
        aoEstado?.(canal, 'falhou');
      }
    };

    r.onend = () => {
      aoParcial?.(canal, '');
      inicioDoTrecho = null;
      if (!ativo) {
        const fim = aoTerminar;
        aoTerminar = null;
        fim?.();
        return;
      }
      const t = agora().getTime();
      religamentos = religamentos.filter((x) => t - x < 60000);
      if (religamentos.length >= MAX_RELIGAMENTOS_POR_MINUTO) {
        ativo = false;
        aoErro?.(canal, 'religamentos', true);
        aoEstado?.(canal, 'falhou');
        return;
      }
      religamentos.push(t);
      aoEstado?.(canal, 'religando');
      ligar();
    };
    return r;
  }

  function ligar() {
    rec = montar();
    try {
      rec.start(track);
      aoEstado?.(canal, 'ouvindo');
    } catch (e) {
      ativo = false;
      aoErro?.(canal, e?.name || 'start', true);
      aoEstado?.(canal, 'falhou');
    }
  }

  return {
    iniciar() {
      if (ativo) return;
      ativo = true;
      religamentos = [];
      ligar();
    },
    /**
     * Para e espera o último trecho. O Chrome entrega o resultado final
     * antes do `onend` — parar sem esperar perderia a última frase.
     */
    parar(timeoutMs = 1500) {
      if (!rec || !ativo) {
        ativo = false;
        aoEstado?.(canal, 'parado');
        return Promise.resolve();
      }
      ativo = false;
      return new Promise((resolve) => {
        const pronto = () => { clearTimeout(t); aoEstado?.(canal, 'parado'); resolve(); };
        const t = setTimeout(() => { aoTerminar = null; pronto(); }, timeoutMs);
        aoTerminar = pronto;
        try { rec.stop(); } catch { pronto(); }
      });
    },
    get ativo() { return ativo; },
  };
}
