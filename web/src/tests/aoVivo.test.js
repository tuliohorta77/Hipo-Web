// web/src/tests/aoVivo.test.js
//
// A lógica da Reunião ao vivo que não depende de tela:
//
//   1. suporte: Chrome 133+ com reconhecimento de voz; antes disso o
//      `start(track)` ignora a trilha e os dois canais ouviriam o microfone
//   2. palavras: a mesma régua do servidor
//   3. a fila: seq fixo, reenvio do mesmo lote, só sai o confirmado
//   4. o reconhecedor: trecho final com início, parcial, religamento,
//      erro fatal para, e parar espera a última frase
import { describe, it, expect, vi } from 'vitest';
import {
  VERSAO_MINIMA_CHROME, contarPalavras, criarFila, criarReconhecedor,
  descreverNavegador, diagnosticarSuporte, erroEFatal, erroENormal,
  formatarCronometro, fraseDoErro, metricasDasFalas, versaoChromium,
  MAX_RELIGAMENTOS_POR_MINUTO,
} from '../components/crm/aoVivo';

function nav({ versao = 141, marca = 'Google Chrome', ua, media = true } = {}) {
  return {
    userAgentData: versao == null ? undefined : { brands: [{ brand: marca, version: String(versao) }] },
    userAgent: ua || `Mozilla/5.0 Chrome/${versao}.0.0.0 Safari/537.36`,
    mediaDevices: media ? { getDisplayMedia: () => {}, getUserMedia: () => {} } : undefined,
  };
}

function janela(opcoes = {}, comReconhecimento = true) {
  return {
    navigator: nav(opcoes),
    webkitSpeechRecognition: comReconhecimento ? function R() {} : undefined,
  };
}

describe('suporte', () => {
  it('lê a versão pelas marcas do userAgentData', () => {
    expect(versaoChromium(nav({ versao: 140 }))).toBe(140);
  });

  it('cai para o userAgent quando não há userAgentData', () => {
    expect(versaoChromium({ userAgent: 'x Chrome/135.0.1 y' })).toBe(135);
  });

  it('Firefox não é Chromium', () => {
    expect(versaoChromium({ userAgent: 'Mozilla/5.0 Firefox/130.0' })).toBeNull();
  });

  it('Chrome atual passa', () => {
    expect(diagnosticarSuporte(janela())).toEqual({ ok: true, motivo: null });
  });

  it('Chrome antigo não passa, e diz a versão', () => {
    const d = diagnosticarSuporte(janela({ versao: VERSAO_MINIMA_CHROME - 1 }));
    expect(d.ok).toBe(false);
    expect(d.motivo).toMatch(String(VERSAO_MINIMA_CHROME - 1));
  });

  it('sem reconhecimento de voz não passa', () => {
    const d = diagnosticarSuporte(janela({}, false));
    expect(d.ok).toBe(false);
    expect(d.motivo).toMatch(/Chrome/);
  });

  it('sem captura de tela não passa', () => {
    expect(diagnosticarSuporte(janela({ media: false })).ok).toBe(false);
  });

  it('descreve o navegador para a sessão', () => {
    expect(descreverNavegador(nav({ versao: 141 }))).toBe('Chrome 141');
    expect(descreverNavegador({
      userAgent: 'Mozilla Chrome/140.0 Edg/140.0',
      userAgentData: { brands: [{ brand: 'Microsoft Edge', version: '140' }, { brand: 'Chromium', version: '140' }] },
    })).toBe('Edge 140');
  });
});

describe('palavras', () => {
  it('conta sem acento e sem pontuação', () => {
    expect(contarPalavras('Você tem 120 vidas, não?')).toBe(5);
    expect(contarPalavras('')).toBe(0);
    expect(contarPalavras(null)).toBe(0);
  });

  it('proporção do vendedor por palavra, null sem palavra', () => {
    expect(metricasDasFalas([
      { canal: 'vendedor', texto: 'um dois tres' },
      { canal: 'cliente', texto: 'quatro' },
    ])).toEqual({
      palavras_vendedor: 3, palavras_cliente: 1, palavras_total: 4, proporcao_vendedor_pct: 75,
    });
    expect(metricasDasFalas([]).proporcao_vendedor_pct).toBeNull();
  });

  it('cronômetro', () => {
    expect(formatarCronometro(0)).toBe('00:00');
    expect(formatarCronometro(65_000)).toBe('01:05');
    expect(formatarCronometro(3_725_000)).toBe('1:02:05');
  });
});

describe('fila', () => {
  const ini = new Date('2026-10-01T13:00:00Z');

  it('numera na entrada e ignora texto vazio', () => {
    const f = criarFila();
    expect(f.adicionar({ canal: 'vendedor', texto: '  ', inicio: ini })).toBeNull();
    const a = f.adicionar({ canal: 'vendedor', texto: ' bom   dia ', inicio: ini, fim: ini, confianca: 0.9 });
    const b = f.adicionar({ canal: 'cliente', texto: 'oi', inicio: ini, confianca: 0 });
    expect([a.seq, b.seq]).toEqual([0, 1]);
    expect(a.texto).toBe('bom dia');
    expect(a.inicio).toBe('2026-10-01T13:00:00.000Z');
    // Confiança 0 é o "não sei" do Chrome, não uma nota.
    expect(b.confianca).toBeNull();
    expect(f.pendentes).toBe(2);
  });

  it('só sai o que foi confirmado; o que falhou vai de novo com o mesmo seq', () => {
    const f = criarFila();
    f.adicionar({ canal: 'vendedor', texto: 'um', inicio: ini });
    const lote1 = f.lote();
    // o envio falhou: nada confirmado
    f.adicionar({ canal: 'vendedor', texto: 'dois', inicio: ini });
    const lote2 = f.lote();
    expect(lote2.falas.map((x) => x.seq)).toEqual([0, 1]);
    f.confirmar(lote1);
    expect(f.lote().falas.map((x) => x.seq)).toEqual([1]);
  });

  it('respeita o tamanho do lote', () => {
    const f = criarFila();
    for (let i = 0; i < 5; i += 1) f.adicionar({ canal: 'cliente', texto: `f${i}`, inicio: ini });
    expect(f.lote(2).falas).toHaveLength(2);
  });

  it('erros viajam no lote e saem ao confirmar', () => {
    const f = criarFila();
    f.registrarErro('cliente', 'network');
    expect(f.temAlgo).toBe(true);
    const l = f.lote();
    expect(l.erros[0]).toMatchObject({ canal: 'cliente', erro: 'network' });
    f.confirmar(l);
    expect(f.temAlgo).toBe(false);
  });
});

describe('erros', () => {
  it('silêncio e aborted são normais', () => {
    expect(erroENormal('no-speech')).toBe(true);
    expect(erroENormal('aborted')).toBe(true);
    expect(erroENormal('network')).toBe(false);
  });

  it('permissão e idioma são fatais; rede não', () => {
    expect(erroEFatal('not-allowed')).toBe(true);
    expect(erroEFatal('language-not-supported')).toBe(true);
    expect(erroEFatal('network')).toBe(false);
  });

  it('frase em português, com o código quando desconhecido', () => {
    expect(fraseDoErro('network')).toMatch(/conexão/);
    expect(fraseDoErro('xyz')).toMatch(/xyz/);
  });
});

// ── Reconhecedor ─────────────────────────────────────────────────────

function fabricaDeReconhecedores() {
  const instancias = [];
  class Falso {
    constructor() {
      this.iniciadoCom = undefined;
      this.parou = false;
      instancias.push(this);
    }

    start(track) { this.iniciadoCom = track; }

    stop() { this.parou = true; }

    // helpers de teste
    resultado(itens, resultIndex = 0) {
      const results = itens.map(([texto, isFinal, confidence = 0.8]) => {
        const r = [{ transcript: texto, confidence }];
        r.isFinal = isFinal;
        return r;
      });
      this.onresult({ resultIndex, results });
    }
  }
  return { Falso, instancias };
}

function montar(extra = {}) {
  const { Falso, instancias } = fabricaDeReconhecedores();
  const eventos = { finais: [], parciais: [], erros: [], estados: [] };
  let relogio = new Date('2026-10-01T13:00:00Z').getTime();
  const r = criarReconhecedor({
    canal: 'cliente',
    track: 'trilha-da-aba',
    Construtor: Falso,
    aoFinal: (f) => eventos.finais.push(f),
    aoParcial: (c, t) => eventos.parciais.push(t),
    aoErro: (c, codigo, fatal) => eventos.erros.push([codigo, fatal]),
    aoEstado: (c, e) => eventos.estados.push(e),
    agora: () => new Date(relogio),
    ...extra,
  });
  return {
    r, instancias, eventos,
    andar: (ms) => { relogio += ms; },
  };
}

describe('reconhecedor', () => {
  it('liga com a trilha, em português, contínuo e com parcial', () => {
    const { r, instancias, eventos } = montar();
    r.iniciar();
    const rec = instancias[0];
    expect(rec.iniciadoCom).toBe('trilha-da-aba');
    expect(rec.lang).toBe('pt-BR');
    expect(rec.continuous).toBe(true);
    expect(rec.interimResults).toBe(true);
    expect(eventos.estados).toEqual(['ouvindo']);
  });

  it('o trecho final leva o início do primeiro parcial', () => {
    const { r, instancias, eventos, andar } = montar();
    r.iniciar();
    const rec = instancias[0];
    rec.resultado([['temos', false]]);
    andar(3000);
    rec.resultado([['temos 120 vidas', true, 0.91]]);
    expect(eventos.finais).toHaveLength(1);
    const f = eventos.finais[0];
    expect(f.texto).toBe('temos 120 vidas');
    expect(f.canal).toBe('cliente');
    expect(f.fim.getTime() - f.inicio.getTime()).toBe(3000);
    expect(f.confianca).toBe(0.91);
    expect(eventos.parciais).toEqual(['temos', '']);
  });

  it('religa sozinho quando o Chrome encerra por silêncio', () => {
    const { r, instancias, eventos } = montar();
    r.iniciar();
    instancias[0].onerror({ error: 'no-speech' });
    instancias[0].onend();
    expect(instancias).toHaveLength(2);
    expect(instancias[1].iniciadoCom).toBe('trilha-da-aba');
    expect(eventos.erros).toEqual([]);
    expect(eventos.estados).toEqual(['ouvindo', 'religando', 'ouvindo']);
  });

  it('erro fatal para de vez', () => {
    const { r, instancias, eventos } = montar();
    r.iniciar();
    instancias[0].onerror({ error: 'not-allowed' });
    instancias[0].onend();
    expect(instancias).toHaveLength(1);
    expect(eventos.erros).toEqual([['not-allowed', true]]);
    expect(eventos.estados).toContain('falhou');
    expect(r.ativo).toBe(false);
  });

  it('rede é relatada mas religa', () => {
    const { r, instancias, eventos } = montar();
    r.iniciar();
    instancias[0].onerror({ error: 'network' });
    instancias[0].onend();
    expect(eventos.erros).toEqual([['network', false]]);
    expect(instancias).toHaveLength(2);
  });

  it('religando demais em um minuto, desiste', () => {
    const { r, instancias, eventos } = montar();
    r.iniciar();
    for (let i = 0; i <= MAX_RELIGAMENTOS_POR_MINUTO; i += 1) {
      instancias[instancias.length - 1].onend();
    }
    expect(instancias).toHaveLength(MAX_RELIGAMENTOS_POR_MINUTO + 1);
    expect(eventos.erros.at(-1)).toEqual(['religamentos', true]);
    expect(eventos.estados.at(-1)).toBe('falhou');
  });

  it('parar espera a última frase antes de resolver', async () => {
    const { r, instancias, eventos } = montar();
    r.iniciar();
    const rec = instancias[0];
    const promessa = r.parar(5000);
    expect(rec.parou).toBe(true);
    rec.resultado([['obrigado', true]]);
    rec.onend();
    await promessa;
    expect(eventos.finais.map((f) => f.texto)).toEqual(['obrigado']);
    expect(instancias).toHaveLength(1);
    expect(eventos.estados.at(-1)).toBe('parado');
  });

  it('parar resolve pelo tempo se o Chrome não encerrar', async () => {
    vi.useFakeTimers();
    try {
      const { r } = montar();
      r.iniciar();
      const promessa = r.parar(100);
      vi.advanceTimersByTime(150);
      await expect(promessa).resolves.toBeUndefined();
    } finally {
      vi.useRealTimers();
    }
  });

  it('start que explode vira falha, não exceção', () => {
    class Quebrado {
      start() { const e = new Error('x'); e.name = 'InvalidStateError'; throw e; }
    }
    const { r, eventos } = montar({ Construtor: Quebrado });
    expect(() => r.iniciar()).not.toThrow();
    expect(eventos.erros).toEqual([['InvalidStateError', true]]);
    expect(eventos.estados).toEqual(['falhou']);
  });
});
