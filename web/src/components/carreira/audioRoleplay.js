// web/src/components/carreira/audioRoleplay.js
//
// Áudio do Roleplay no navegador: microfone em PCM 16 kHz para o Gemini,
// voz da IA em PCM 24 kHz para o fone, e a GRAVAÇÃO das duas vozes juntas
// (WebM/Opus a 32 kbps: ~11 MB por 45 min).
//
// Só roda em navegador de verdade (AudioWorklet, MediaRecorder): a página
// injeta este módulo, e os testes da página trocam por um dublê.

import { floatParaPcm16Base64, base64ParaFloat, nivel } from './vozRealtime';

const WORKLET = `
class Captura extends AudioWorkletProcessor {
  constructor() { super(); this.buf = []; this.n = 0; }
  process(inputs) {
    const ch = inputs[0][0];
    if (!ch) return true;
    this.buf.push(new Float32Array(ch)); this.n += ch.length;
    if (this.n >= 1600) {
      const out = new Float32Array(this.n); let o = 0;
      for (const b of this.buf) { out.set(b, o); o += b.length; }
      this.port.postMessage(out, [out.buffer]); this.buf = []; this.n = 0;
    }
    return true;
  }
}
registerProcessor('captura-roleplay', Captura);`;

export function navegadorSuporta() {
  return !!(globalThis.navigator?.mediaDevices?.getUserMedia && globalThis.AudioContext
    && globalThis.AudioWorkletNode && globalThis.MediaRecorder);
}

/**
 * @param {object} cb onMicrofone(b64), onNivelMic(0..1), onNivelIa(0..1), onFimDaFala()
 */
export async function iniciarAudio(cb) {
  const mic = await navigator.mediaDevices.getUserMedia({
    audio: { echoCancellation: true, noiseSuppression: true, autoGainControl: true, channelCount: 1 },
  });
  const ctxMic = new AudioContext({ sampleRate: 16000 });
  await ctxMic.audioWorklet.addModule(URL.createObjectURL(new Blob([WORKLET], { type: 'application/javascript' })));
  const no = new AudioWorkletNode(ctxMic, 'captura-roleplay');
  ctxMic.createMediaStreamSource(mic).connect(no);
  let falando = false;
  let silencio = 0;
  no.port.onmessage = (e) => {
    const f = e.data;
    const n = nivel(f);
    cb.onNivelMic?.(Math.min(1, n * 4));
    // Fim da fala do executivo (500 ms de silêncio): marca para medir a latência.
    if (n > 0.02) { falando = true; silencio = 0; } else if (falando && ++silencio >= 5) { falando = false; cb.onFimDaFala?.(); }
    cb.onMicrofone?.(floatParaPcm16Base64(f));
  };

  // Saída da IA e gravação no mesmo contexto: a gravação leva as duas vozes.
  const ctxOut = new AudioContext({ sampleRate: 24000 });
  const destino = ctxOut.createMediaStreamDestination();
  ctxOut.createMediaStreamSource(mic).connect(destino);
  const tipo = MediaRecorder.isTypeSupported('audio/webm;codecs=opus') ? 'audio/webm;codecs=opus' : 'audio/webm';
  const gravador = new MediaRecorder(destino.stream, { mimeType: tipo, audioBitsPerSecond: 32000 });
  const pedacos = [];
  gravador.ondataavailable = (e) => { if (e.data.size) pedacos.push(e.data); };
  gravador.start(1000);

  let proximo = ctxOut.currentTime;
  const fontes = new Set();

  return {
    tocar(b64) {
      const f = base64ParaFloat(b64);
      if (!f.length) return;
      cb.onNivelIa?.(Math.min(1, nivel(f) * 4));
      const buf = ctxOut.createBuffer(1, f.length, 24000);
      buf.copyToChannel(f, 0);
      const fonte = ctxOut.createBufferSource();
      fonte.buffer = buf;
      fonte.connect(ctxOut.destination);
      fonte.connect(destino);
      const ini = Math.max(ctxOut.currentTime, proximo);
      fonte.start(ini);
      proximo = ini + buf.duration;
      fontes.add(fonte);
      fonte.onended = () => { fontes.delete(fonte); if (!fontes.size) cb.onNivelIa?.(0); };
    },
    /** A pessoa falou por cima: corta a fala da IA na hora. */
    interromper() {
      for (const f of fontes) { try { f.stop(); } catch { /* já parou */ } }
      fontes.clear();
      proximo = ctxOut.currentTime;
      cb.onNivelIa?.(0);
    },
    /** Para tudo e devolve a gravação. */
    async parar() {
      await new Promise((ok) => {
        if (gravador.state === 'recording') { gravador.onstop = ok; gravador.stop(); } else ok();
      });
      mic.getTracks().forEach((t) => t.stop());
      await Promise.allSettled([ctxMic.close(), ctxOut.close()]);
      return new Blob(pedacos, { type: 'audio/webm' });
    },
  };
}
