// web/src/components/carreira/vozRealtime.js
//
// Conexão de voz do Roleplay com o Gemini Live, por WebSocket, sem SDK.
//
// O navegador fala DIRETO com o Google (o áudio não passa pelo HIPO). O
// HIPO só entrega um token efêmero com a persona travada dentro dele; o
// primeiro frame (setup) manda só o modelo e o handle de retomada.
//
// A conexão do Live dura ~10 min. Quando o Google avisa (goAway) ou a
// conexão cai sem motivo de cobrança, este módulo pede um TOKEN NOVO ao
// HIPO (`obterTokenNovo`) e reconecta com o último handle: o contexto da
// conversa continua. Três quedas seguidas logo após abrir → desiste.
// (No PoC, reusar o token antigo virou um laço de 1011.)
//
// Cliente "travada": às vezes o Live ouve a fala e não responde nunca
// (teste de 07/10/2026: o executivo chamou "Patrícia?" três vezes). Quando
// o executivo termina de falar (`fimDaFala`) e nenhuma resposta chega em
// SEM_RESPOSTA_MS, conta como "sem resposta" e reconecta com o handle: a
// conversa continua e a tela pede para repetir a última frase. No máximo
// MAX_SEM_RESPOSTA vezes por sessão (depois só registra), para não laçar.
//
// Tudo o que acontece com a conexão vira `onEvento(tipo, detalhe)`: a tela
// junta num diário que vai junto no encerramento (diagnóstico da gestão).
//
// Separado da tela para ser testado com um WebSocket falso e, se um dia
// for preciso, trocar de provedor sem mexer na página.

export const MIME_ENTRADA = 'audio/pcm;rate=16000';
const QUEDA_RAPIDA_MS = 5000;
const MAX_QUEDAS_RAPIDAS = 3;
const RE_SALDO = /quota|billing|credit|exhaust|prepay|resource_exhausted/i;
export const SEM_RESPOSTA_MS = 9000;
export const MAX_SEM_RESPOSTA = 3;

async function textoDaMensagem(dado) {
  if (typeof dado === 'string') return dado;
  if (dado instanceof ArrayBuffer) return new TextDecoder().decode(dado);
  if (typeof Blob !== 'undefined' && dado instanceof Blob) {
    if (typeof dado.text === 'function') return dado.text();
    return new Promise((ok, falha) => {
      const leitor = new FileReader();
      leitor.onload = () => ok(String(leitor.result));
      leitor.onerror = () => falha(leitor.error);
      leitor.readAsText(dado);
    });
  }
  return String(dado ?? '');
}

/**
 * @param {object} cfg
 * @param {string} cfg.wsUrl   endpoint BidiGenerateContentConstrained
 * @param {string} cfg.token   token efêmero (auth_tokens/...)
 * @param {string} cfg.modelo  ex.: gemini-3.8-live
 * @param {() => Promise<string>} cfg.obterTokenNovo  pede token ao HIPO
 * @param {object} cfg.eventos onAberto, onAudio(b64), onInterrompido,
 *   onTranscricao(quem, texto), onUso(usageMetadata), onReconectando,
 *   onReconectado, onSemResposta(n), onFim(motivo), onLog(texto),
 *   onEvento(tipo, detalhe)
 * @param {() => number} [cfg.agora]  relógio (testes)
 * @param {boolean} [cfg.vigia=true]  liga o setInterval do "sem resposta"
 */
export function criarSessaoVoz({
  wsUrl, token, modelo, obterTokenNovo, eventos = {}, WebSocketImpl,
  agora = () => Date.now(), vigia = true, semRespostaMs = SEM_RESPOSTA_MS,
}) {
  const WS = WebSocketImpl || globalThis.WebSocket;
  const ev = (nome, ...args) => { try { eventos[nome]?.(...args); } catch { /* evento da tela não derruba a conexão */ } };
  const diario = (tipo, detalhe = '') => { ev('onEvento', tipo, detalhe); ev('onLog', detalhe ? `${tipo}: ${detalhe}` : tipo); };
  const st = {
    ws: null, token, handle: null, pronto: false, encerrando: false,
    // reconectando: buscando o token novo (sem conexão nenhuma aberta).
    // retomando: conexão nova aberta, esperando o setupComplete.
    reconectando: false, retomando: false, reconexoes: 0, quedasRapidas: 0, abertoEm: 0,
    // Vigia: desde quando o executivo terminou de falar sem resposta.
    esperandoDesde: null, semResposta: 0, timer: null,
  };

  function abrir() {
    const ws = new WS(`${wsUrl}?access_token=${encodeURIComponent(st.token)}`);
    st.ws = ws;
    st.pronto = false;
    ws.onopen = () => {
      st.abertoEm = Date.now();
      const setup = { model: `models/${modelo}` };
      setup.sessionResumption = st.handle ? { handle: st.handle } : {};
      ws.send(JSON.stringify({ setup }));
    };
    ws.onmessage = async (e) => {
      let msg;
      try { msg = JSON.parse(await textoDaMensagem(e.data)); } catch { return; }
      if (ws !== st.ws) return;
      tratar(msg);
    };
    ws.onerror = () => diario('erro', 'erro de conexão');
    ws.onclose = (e) => { if (ws === st.ws) aoFechar(e); };
  }

  function tratar(msg) {
    if (msg.setupComplete !== undefined) {
      st.pronto = true;
      st.quedasRapidas = 0;
      st.esperandoDesde = null;
      if (st.retomando) {
        st.retomando = false;
        st.reconexoes += 1;
        diario('reconectado', String(st.reconexoes));
        ev('onReconectado', st.reconexoes);
      } else {
        diario('aberto');
        ev('onAberto');
      }
    }
    const sc = msg.serverContent;
    if (sc) {
      const partes = sc.modelTurn?.parts || [];
      // A cliente respondeu (voz ou texto dela): o vigia para de contar.
      if (partes.length || sc.outputTranscription?.text) st.esperandoDesde = null;
      for (const p of partes) {
        if (p.inlineData?.data) ev('onAudio', p.inlineData.data);
      }
      if (sc.interrupted) ev('onInterrompido');
      if (sc.inputTranscription?.text) ev('onTranscricao', 'executivo', sc.inputTranscription.text);
      if (sc.outputTranscription?.text) ev('onTranscricao', 'cliente', sc.outputTranscription.text);
    }
    if (msg.usageMetadata) ev('onUso', msg.usageMetadata);
    const r = msg.sessionResumptionUpdate;
    if (r?.resumable && r.newHandle) st.handle = r.newHandle;
    if (msg.goAway) {
      diario('goaway', msg.goAway.timeLeft || '');
      reconectar('goaway');
    }
  }

  function aoFechar(e) {
    const motivo = `${e?.code || ''} ${e?.reason || ''}`.trim();
    diario('fechada', motivo);
    if (st.encerrando || st.reconectando) return;
    if (RE_SALDO.test(motivo)) { finalizar('saldo'); return; }
    // Caiu antes do setupComplete ou logo depois de abrir: conta como falha.
    const rapida = !st.pronto || Date.now() - st.abertoEm < QUEDA_RAPIDA_MS;
    st.quedasRapidas = rapida ? st.quedasRapidas + 1 : 0;
    if (st.quedasRapidas >= MAX_QUEDAS_RAPIDAS || !st.handle) { finalizar('queda'); return; }
    reconectar('queda');
  }

  async function reconectar(motivo) {
    if (st.reconectando || st.encerrando) return;
    st.reconectando = true;
    st.retomando = true;
    st.esperandoDesde = null;
    diario('reconectando', motivo);
    ev('onReconectando', motivo);
    const antiga = st.ws;
    st.ws = null;
    try { antiga?.close(); } catch { /* já fechada */ }
    for (let tentativa = 1; tentativa <= 3; tentativa += 1) {
      try {
        st.token = await obterTokenNovo();
        if (st.encerrando) return;
        st.reconectando = false;
        abrir();
        return;
      } catch (err) {
        diario('reconexao_falhou', `${tentativa}/3: ${err?.message || err}`);
        if (st.encerrando) return;
        await new Promise((ok) => setTimeout(ok, 800 * tentativa));
      }
    }
    st.reconectando = false;
    st.retomando = false;
    finalizar('queda');
  }

  function finalizar(motivo) {
    if (st.encerrando) return;
    st.encerrando = true;
    clearInterval(st.timer);
    try { st.ws?.close(); } catch { /* já fechada */ }
    diario('fim', motivo);
    ev('onFim', motivo);
  }

  const conectado = () => !!st.ws && st.pronto && !st.reconectando && !st.retomando;

  /** O vigia: chamado a cada segundo (ou à mão nos testes). */
  function verificar() {
    if (st.encerrando || st.esperandoDesde === null || !conectado()) return;
    const esperou = agora() - st.esperandoDesde;
    if (esperou < semRespostaMs) return;
    st.esperandoDesde = null;
    st.semResposta += 1;
    const seg = Math.round(esperou / 1000);
    if (st.semResposta > MAX_SEM_RESPOSTA || !st.handle) {
      diario('sem_resposta', `${seg}s · sem reconectar`);
      ev('onSemResposta', st.semResposta, false);
      return;
    }
    diario('sem_resposta', `${seg}s`);
    ev('onSemResposta', st.semResposta, true);
    reconectar('sem_resposta');
  }

  return {
    conectar() {
      abrir();
      if (vigia && !st.timer) st.timer = setInterval(verificar, 1000);
    },
    /** O executivo parou de falar: começa a contar a espera pela resposta. */
    fimDaFala() { if (conectado()) st.esperandoDesde = agora(); },
    /** Voltou a falar: não é falta de resposta, é ele com a palavra. */
    inicioDaFala() { st.esperandoDesde = null; },
    verificar,
    /** Áudio do microfone, PCM 16 kHz em base64. Ignorado durante a troca de conexão. */
    enviarAudio(b64) {
      const ws = st.ws;
      if (!ws || !st.pronto || st.reconectando || st.retomando || ws.readyState !== 1) return false;
      ws.send(JSON.stringify({ realtimeInput: { audio: { data: b64, mimeType: MIME_ENTRADA } } }));
      return true;
    },
    encerrar() { finalizar('encerrou'); },
    get reconexoes() { return st.reconexoes; },
    get conectado() { return conectado(); },
    get semResposta() { return st.semResposta; },
  };
}

// ── Áudio (puro) ─────────────────────────────────────────────────────

export function floatParaPcm16Base64(f32) {
  const i16 = new Int16Array(f32.length);
  for (let i = 0; i < f32.length; i += 1) {
    const s = Math.max(-1, Math.min(1, f32[i]));
    i16[i] = s < 0 ? s * 0x8000 : s * 0x7fff;
  }
  const u8 = new Uint8Array(i16.buffer);
  let bin = '';
  for (let i = 0; i < u8.length; i += 0x8000) bin += String.fromCharCode.apply(null, u8.subarray(i, i + 0x8000));
  return btoa(bin);
}

export function base64ParaFloat(b64) {
  const bin = atob(b64);
  const u8 = new Uint8Array(bin.length);
  for (let i = 0; i < bin.length; i += 1) u8[i] = bin.charCodeAt(i);
  const i16 = new Int16Array(u8.buffer, 0, Math.floor(u8.length / 2));
  const f = new Float32Array(i16.length);
  for (let i = 0; i < i16.length; i += 1) f[i] = i16[i] / 0x8000;
  return f;
}

export function nivel(f32) {
  if (!f32?.length) return 0;
  let s = 0;
  for (let i = 0; i < f32.length; i += 1) s += f32[i] * f32[i];
  return Math.sqrt(s / f32.length);
}

/** Junta pedaços de transcrição do mesmo falante num turno só. */
export function anotarTurno(turnos, quem, texto, tMs) {
  if (!texto) return turnos;
  const ult = turnos[turnos.length - 1];
  if (ult && ult.quem === quem) {
    ult.texto += texto;
    return turnos;
  }
  turnos.push({ quem, texto, t_ms: tMs });
  return turnos;
}

/** Soma o usageMetadata por modalidade (áudio/texto, entrada/saída). */
export function somarUso(acumulado, u) {
  const somar = (lista, sufixo) => (lista || []).forEach((d) => {
    const tipo = String(d.modality || '').toLowerCase().includes('audio') ? 'audio' : 'texto';
    acumulado[`${tipo}_${sufixo}`] = (acumulado[`${tipo}_${sufixo}`] || 0) + (d.tokenCount || 0);
  });
  somar(u?.promptTokensDetails, 'in');
  somar(u?.responseTokensDetails, 'out');
  acumulado.total = (acumulado.total || 0) + (u?.totalTokenCount || 0);
  return acumulado;
}
