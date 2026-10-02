// web/src/tests/ucComum.test.js
//
// O que a UC divide entre as telas. A promessa mais importante: o src do
// player sai de uma tabela fechada, e nada que não seja um id limpo vira
// endereço de iframe.
import { describe, it, expect } from 'vitest';
import {
  urlDeEmbed, dataCurta, textoPrazo, tempoRestante, tamanhoArquivo, tomDoPilar,
} from '../components/uc/ucComum';

describe('urlDeEmbed', () => {
  it('monta o player de cada provedor', () => {
    expect(urlDeEmbed('youtube', 'dQw4w9WgXcQ')).toBe('https://www.youtube-nocookie.com/embed/dQw4w9WgXcQ?rel=0');
    expect(urlDeEmbed('vimeo', '76979871')).toBe('https://player.vimeo.com/video/76979871');
    expect(urlDeEmbed('loom', 'abc123')).toBe('https://www.loom.com/embed/abc123');
    expect(urlDeEmbed('drive', '1AbC_-x')).toBe('https://drive.google.com/file/d/1AbC_-x/preview');
  });

  it('provedor desconhecido não vira player', () => {
    expect(urlDeEmbed('evil', 'x')).toBeNull();
    expect(urlDeEmbed(null, null)).toBeNull();
  });

  it('id com caractere estranho não vira player', () => {
    expect(urlDeEmbed('youtube', 'abc"><script>')).toBeNull();
    expect(urlDeEmbed('youtube', '../../x')).toBeNull();
  });
});

describe('datas e prazos', () => {
  it('data curta sem passar por Date', () => {
    expect(dataCurta('2026-10-31')).toBe('31/10/2026');
    expect(dataCurta(null)).toBe('');
  });

  it('prazo atrasado diz há quantos dias venceu', () => {
    expect(textoPrazo({ codigo: 'atrasada', dias_restantes: -3 }, '2026-10-01'))
      .toBe('venceu há 3 dias (01/10/2026)');
    expect(textoPrazo({ codigo: 'atrasada', dias_restantes: -1 }, '2026-10-01'))
      .toBe('venceu há 1 dia (01/10/2026)');
  });

  it('prazo do dia e prazo futuro', () => {
    expect(textoPrazo({ codigo: 'vence_logo', dias_restantes: 0 }, '2026-10-01')).toBe('vence hoje (01/10/2026)');
    expect(textoPrazo({ codigo: 'em_dia', dias_restantes: 12 }, '2026-10-13')).toBe('até 13/10/2026 · 12 dias');
  });

  it('trilha concluída não mostra prazo', () => {
    expect(textoPrazo({ codigo: 'concluida', dias_restantes: null }, '2026-10-01')).toBe('');
  });
});

describe('formatos', () => {
  it('tempo restante', () => {
    expect(tempoRestante(59)).toBe('59 s');
    expect(tempoRestante(125)).toBe('2 min 5 s');
    expect(tempoRestante(300)).toBe('5 min');
    expect(tempoRestante(-4)).toBe('0 s');
  });

  it('tamanho de arquivo', () => {
    expect(tamanhoArquivo(398620)).toBe('389 KB');
    expect(tamanhoArquivo(2.5 * 1024 * 1024)).toBe('2,5 MB');
  });

  it('pilar desconhecido cai no tom de Técnica', () => {
    expect(tomDoPilar('xyz')).toEqual(tomDoPilar('tecnica'));
  });
});
