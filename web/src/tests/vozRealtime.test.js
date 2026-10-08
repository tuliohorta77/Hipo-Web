// web/src/tests/vozRealtime.test.js
//
// Conexão de voz do Roleplay com um WebSocket falso. O que segura:
//   1. abre com o token na URL e manda o setup só com modelo e retomada;
//   2. só manda áudio depois do setupComplete;
//   3. áudio, interrupção, transcrição e uso viram eventos;
//   4. goAway → pede TOKEN NOVO e reconecta com o último handle (o bug do PoC);
//   5. queda com motivo de cobrança encerra como "saldo";
//   6. três quedas seguidas logo após abrir encerram como "queda";
//   7. cliente sem resposta depois da fala → reconecta com o handle (no
//      máximo 3 vezes); resposta ou o executivo voltando a falar cancelam;
//   8. tudo vira evento do diário (onEvento);
//   9. funções puras de áudio, turno e uso.
import { describe, it, expect, vi, beforeEach } from 'vitest';
import {
  anotarTurno, base64ParaFloat, criarSessaoVoz, floatParaPcm16Base64, nivel, somarUso,
} from '../components/carreira/vozRealtime';

let sockets;
class WSFalso {
  constructor(url) {
    this.url = url;
    this.enviados = [];
    this.readyState = 0;
    sockets.push(this);
  }
  send(d) { this.enviados.push(JSON.parse(d)); }
  close() { this.readyState = 3; }
  abrir() { this.readyState = 1; this.onopen?.(); }
  receber(obj) { return this.onmessage?.({ data: JSON.stringify(obj) }); }
  cair(code = 1006, reason = '') { this.readyState = 3; this.onclose?.({ code, reason }); }
}

const espera = () => new Promise((ok) => setTimeout(ok, 0));

function nova(extra = {}) {
  const eventos = {
    onAberto: vi.fn(), onAudio: vi.fn(), onInterrompido: vi.fn(), onTranscricao: vi.fn(),
    onUso: vi.fn(), onReconectando: vi.fn(), onReconectado: vi.fn(), onFim: vi.fn(), onLog: vi.fn(),
    onSemResposta: vi.fn(), onEvento: vi.fn(),
  };
  const obterTokenNovo = vi.fn().mockResolvedValue('auth_tokens/novo');
  const voz = criarSessaoVoz({
    wsUrl: 'wss://gemini/BidiGenerateContentConstrained', token: 'auth_tokens/t1', modelo: 'gemini-3.8-live',
    obterTokenNovo, eventos, WebSocketImpl: WSFalso, vigia: false, ...extra,
  });
  return { voz, eventos, obterTokenNovo };
}

beforeEach(() => { sockets = []; });

describe('criarSessaoVoz', () => {
  it('abre com o token e manda o setup só com modelo e retomada', async () => {
    const { voz, eventos } = nova();
    voz.conectar();
    expect(sockets[0].url).toBe('wss://gemini/BidiGenerateContentConstrained?access_token=auth_tokens%2Ft1');
    sockets[0].abrir();
    expect(sockets[0].enviados[0]).toEqual({ setup: { model: 'models/gemini-3.8-live', sessionResumption: {} } });
    expect(voz.enviarAudio('AAAA')).toBe(false); // antes do setupComplete
    await sockets[0].receber({ setupComplete: {} });
    expect(eventos.onAberto).toHaveBeenCalledTimes(1);
    expect(voz.enviarAudio('AAAA')).toBe(true);
    expect(sockets[0].enviados[1]).toEqual({ realtimeInput: { audio: { data: 'AAAA', mimeType: 'audio/pcm;rate=16000' } } });
  });

  it('áudio, interrupção, transcrição e uso viram eventos (texto e Blob)', async () => {
    const { voz, eventos } = nova();
    voz.conectar();
    sockets[0].abrir();
    await sockets[0].receber({ setupComplete: {} });
    await sockets[0].receber({ serverContent: { modelTurn: { parts: [{ inlineData: { data: 'QUJD' } }] } } });
    await sockets[0].receber({ serverContent: { interrupted: true, inputTranscription: { text: 'Oi Patrícia' } } });
    await sockets[0].onmessage({
      data: new Blob([JSON.stringify({ serverContent: { outputTranscription: { text: 'Oi!' } }, usageMetadata: { totalTokenCount: 10 } })]),
    });
    expect(eventos.onAudio).toHaveBeenCalledWith('QUJD');
    expect(eventos.onInterrompido).toHaveBeenCalled();
    expect(eventos.onTranscricao).toHaveBeenCalledWith('executivo', 'Oi Patrícia');
    expect(eventos.onTranscricao).toHaveBeenCalledWith('cliente', 'Oi!');
    expect(eventos.onUso).toHaveBeenCalledWith({ totalTokenCount: 10 });
  });

  it('goAway: pede token novo e reconecta com o último handle', async () => {
    const { voz, eventos, obterTokenNovo } = nova();
    voz.conectar();
    sockets[0].abrir();
    await sockets[0].receber({ setupComplete: {} });
    await sockets[0].receber({ sessionResumptionUpdate: { resumable: true, newHandle: 'h-42' } });
    await sockets[0].receber({ goAway: { timeLeft: '50s' } });
    await espera();
    expect(obterTokenNovo).toHaveBeenCalledTimes(1);
    expect(eventos.onReconectando).toHaveBeenCalled();
    expect(sockets).toHaveLength(2);
    expect(sockets[1].url).toContain('access_token=auth_tokens%2Fnovo');
    expect(voz.enviarAudio('AAAA')).toBe(false); // durante a troca
    sockets[1].abrir();
    expect(sockets[1].enviados[0].setup.sessionResumption).toEqual({ handle: 'h-42' });
    await sockets[1].receber({ setupComplete: {} });
    expect(eventos.onReconectado).toHaveBeenCalledWith(1);
    expect(voz.reconexoes).toBe(1);
    expect(eventos.onAberto).toHaveBeenCalledTimes(1);
    // a conexão antiga fechando depois não derruba nada
    sockets[0].cair(1000);
    expect(eventos.onFim).not.toHaveBeenCalled();
  });

  it('queda por cobrança encerra como saldo', async () => {
    const { voz, eventos } = nova();
    voz.conectar();
    sockets[0].abrir();
    await sockets[0].receber({ setupComplete: {} });
    sockets[0].cair(1011, 'Quota exceeded for prepay balance');
    expect(eventos.onFim).toHaveBeenCalledWith('saldo');
  });

  it('queda sem handle encerra; três quedas rápidas seguidas também', async () => {
    const a = nova();
    a.voz.conectar();
    sockets[0].abrir();
    sockets[0].cair(1006);
    expect(a.eventos.onFim).toHaveBeenCalledWith('queda');

    sockets = [];
    const b = nova();
    b.voz.conectar();
    sockets[0].abrir();
    await sockets[0].receber({ setupComplete: {} });
    await sockets[0].receber({ sessionResumptionUpdate: { resumable: true, newHandle: 'h1' } });
    for (let i = 0; i < 3; i += 1) {
      const atual = sockets[sockets.length - 1];
      atual.abrir();
      atual.cair(1006);
      await espera();
    }
    expect(b.eventos.onFim).toHaveBeenCalledWith('queda');
  });

  describe('cliente sem resposta', () => {
    async function conversando() {
      let t = 0;
      const r = nova({ agora: () => t });
      r.voz.conectar();
      sockets[0].abrir();
      await sockets[0].receber({ setupComplete: {} });
      await sockets[0].receber({ sessionResumptionUpdate: { resumable: true, newHandle: 'h-7' } });
      return { ...r, avancar: (ms) => { t += ms; } };
    }

    it('9 s sem resposta depois da fala: reconecta com o handle e registra', async () => {
      const { voz, eventos, obterTokenNovo, avancar } = await conversando();
      voz.fimDaFala();
      avancar(8000);
      voz.verificar();
      expect(eventos.onSemResposta).not.toHaveBeenCalled();
      avancar(1500);
      voz.verificar();
      expect(eventos.onSemResposta).toHaveBeenCalledWith(1, true);
      expect(eventos.onReconectando).toHaveBeenCalledWith('sem_resposta');
      expect(eventos.onEvento).toHaveBeenCalledWith('sem_resposta', '10s');
      await espera();
      expect(obterTokenNovo).toHaveBeenCalledTimes(1);
      sockets[1].abrir();
      expect(sockets[1].enviados[0].setup.sessionResumption).toEqual({ handle: 'h-7' });
      await sockets[1].receber({ setupComplete: {} });
      expect(eventos.onReconectado).toHaveBeenCalledWith(1);
      expect(eventos.onEvento).toHaveBeenCalledWith('reconectado', '1');
      expect(voz.semResposta).toBe(1);
    });

    it('resposta da cliente ou o executivo voltando a falar cancelam', async () => {
      const { voz, eventos, avancar } = await conversando();
      voz.fimDaFala();
      await sockets[0].receber({ serverContent: { modelTurn: { parts: [{ inlineData: { data: 'QUJD' } }] } } });
      avancar(20000);
      voz.verificar();
      voz.fimDaFala();
      voz.inicioDaFala();
      avancar(20000);
      voz.verificar();
      expect(eventos.onSemResposta).not.toHaveBeenCalled();
      expect(sockets).toHaveLength(1);
    });

    it('depois de 3 vezes só registra, sem reconectar', async () => {
      const { voz, eventos, obterTokenNovo, avancar } = await conversando();
      for (let i = 0; i < 4; i += 1) {
        voz.fimDaFala();
        avancar(10000);
        voz.verificar();
        await espera();
        const atual = sockets[sockets.length - 1];
        if (atual.readyState === 0) {
          atual.abrir();
          await atual.receber({ setupComplete: {} });
        }
      }
      expect(obterTokenNovo).toHaveBeenCalledTimes(3);
      expect(eventos.onSemResposta).toHaveBeenLastCalledWith(4, false);
      expect(eventos.onEvento).toHaveBeenCalledWith('sem_resposta', '10s · sem reconectar');
      expect(eventos.onFim).not.toHaveBeenCalled();
    });
  });

  it('diário: abertura, queda e fim viram eventos', async () => {
    const { voz, eventos } = nova();
    voz.conectar();
    sockets[0].abrir();
    await sockets[0].receber({ setupComplete: {} });
    await sockets[0].receber({ goAway: { timeLeft: '30s' } });
    voz.encerrar();
    const tipos = eventos.onEvento.mock.calls.map(([t]) => t);
    expect(tipos).toEqual(['aberto', 'goaway', 'reconectando', 'fim']);
    expect(eventos.onEvento).toHaveBeenCalledWith('goaway', '30s');
  });

  it('encerrar avisa o fim uma vez só', () => {
    const { voz, eventos } = nova();
    voz.conectar();
    voz.encerrar();
    voz.encerrar();
    expect(eventos.onFim).toHaveBeenCalledTimes(1);
    expect(eventos.onFim).toHaveBeenCalledWith('encerrou');
  });
});

describe('funções puras', () => {
  it('PCM 16 bits ida e volta', () => {
    const f = new Float32Array([0, 0.5, -0.5, 1, -1]);
    const volta = base64ParaFloat(floatParaPcm16Base64(f));
    expect(volta).toHaveLength(5);
    volta.forEach((v, i) => expect(v).toBeCloseTo(f[i], 3));
    expect(nivel(new Float32Array([1, -1]))).toBe(1);
    expect(nivel(new Float32Array([]))).toBe(0);
  });

  it('junta pedaços do mesmo falante num turno', () => {
    const t = [];
    anotarTurno(t, 'executivo', 'Oi, ', 100);
    anotarTurno(t, 'executivo', 'Patrícia.', 200);
    anotarTurno(t, 'cliente', 'Oi!', 900);
    anotarTurno(t, 'cliente', '', 950);
    expect(t).toEqual([
      { quem: 'executivo', texto: 'Oi, Patrícia.', t_ms: 100 },
      { quem: 'cliente', texto: 'Oi!', t_ms: 900 },
    ]);
  });

  it('soma o uso por modalidade', () => {
    const u = {};
    somarUso(u, {
      totalTokenCount: 30,
      promptTokensDetails: [{ modality: 'AUDIO', tokenCount: 20 }, { modality: 'TEXT', tokenCount: 5 }],
      responseTokensDetails: [{ modality: 'AUDIO', tokenCount: 5 }],
    });
    somarUso(u, { totalTokenCount: 10, promptTokensDetails: [{ modality: 'AUDIO', tokenCount: 10 }] });
    expect(u).toEqual({ audio_in: 30, texto_in: 5, audio_out: 5, total: 40 });
  });
});
