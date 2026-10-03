// web/src/tests/tour.test.js
//
// Regras puras do tour guiado (components/uc/tour.js): estado no
// sessionStorage, plano de cliques, posição do balão e o texto com negrito.
import { describe, it, expect, beforeEach } from 'vitest';
import {
  encerrarTour, iniciarTour, irParaPasso, lerTour, pedacosDoTexto, planoDoPasso,
  posicaoDoBalao, recorteDoAlvo, seletorDaAncora,
} from '../components/uc/tour';

const PASSOS = [
  { rota: '/crm/tarefas', alvo: 'tar-area', titulo: 'A', texto: 'a' },
  { rota: '/crm/tarefas', alvo: 'tar-modal-dados', titulo: 'B', texto: 'b', clicar: ['tar-cartao'] },
  { rota: '/crm/agenda', alvo: null, titulo: 'C', texto: 'c' },
];

beforeEach(() => sessionStorage.clear());

describe('estado do tour', () => {
  it('inicia, anda e encerra', () => {
    expect(lerTour()).toBeNull();
    iniciarTour({ aulaId: 'a1', aulaTitulo: 'Aula', passos: PASSOS });
    expect(lerTour()).toMatchObject({ aulaId: 'a1', indice: 0 });
    irParaPasso(2);
    expect(lerTour().indice).toBe(2);
    irParaPasso(99);
    expect(lerTour().indice).toBe(2);
    irParaPasso(-5);
    expect(lerTour().indice).toBe(0);
    encerrarTour();
    expect(lerTour()).toBeNull();
  });

  it('não inicia sem passos', () => {
    iniciarTour({ aulaId: 'a1', passos: [] });
    expect(lerTour()).toBeNull();
  });

  it('ignora estado quebrado no sessionStorage', () => {
    sessionStorage.setItem('hipo_tour', '{quebrado');
    expect(lerTour()).toBeNull();
    sessionStorage.setItem('hipo_tour', JSON.stringify({ aulaId: 'a1', passos: PASSOS, indice: 7 }));
    expect(lerTour()).toBeNull();
  });
});

describe('planoDoPasso', () => {
  it('tela limpa: só clica', () => {
    expect(planoDoPasso([], PASSOS[1])).toEqual({ remontar: false, cliques: ['tar-cartao'] });
    expect(planoDoPasso([], PASSOS[0])).toEqual({ remontar: false, cliques: [] });
  });

  it('o que está aberto é o começo do que o passo quer: continua', () => {
    expect(planoDoPasso(['opo-cartao-abrir'], { clicar: ['opo-cartao-abrir', 'aba-tarefas'] }))
      .toEqual({ remontar: false, cliques: ['aba-tarefas'] });
    expect(planoDoPasso(['tar-cartao'], PASSOS[1])).toEqual({ remontar: false, cliques: [] });
  });

  it('o passo quer outra coisa ou a tela limpa: remonta e refaz', () => {
    expect(planoDoPasso(['tar-cartao'], PASSOS[0])).toEqual({ remontar: true, cliques: [] });
    expect(planoDoPasso(['opo-cartao-abrir', 'aba-tarefas'], { clicar: ['opo-cartao-abrir', 'aba-proposta'] }))
      .toEqual({ remontar: true, cliques: ['opo-cartao-abrir', 'aba-proposta'] });
  });
});

describe('posição do balão', () => {
  const tela = { largura: 1200, altura: 800 };
  const balao = { largura: 360, altura: 180 };

  it('sem alvo: centro', () => {
    expect(posicaoDoBalao(null, tela, balao)).toEqual({ lado: 'centro', top: 310, left: 420, largura: 360 });
  });

  it('embaixo quando cabe, em cima quando não', () => {
    const alto = { top: 100, left: 500, width: 200, height: 40, bottom: 140, right: 700 };
    expect(posicaoDoBalao(alto, tela, balao)).toMatchObject({ lado: 'baixo', top: 152, left: 420 });
    const baixo = { top: 700, left: 500, width: 200, height: 40, bottom: 740, right: 700 };
    expect(posicaoDoBalao(baixo, tela, balao)).toMatchObject({ lado: 'cima', top: 508 });
  });

  it('alvo do tamanho da tela: rodapé', () => {
    const enorme = { top: 50, left: 0, width: 1200, height: 740, bottom: 790, right: 1200 };
    expect(posicaoDoBalao(enorme, tela, balao)).toMatchObject({ lado: 'rodape', top: 604 });
  });

  it('não sai pela lateral', () => {
    const canto = { top: 100, left: 1150, width: 40, height: 20, bottom: 120, right: 1190 };
    expect(posicaoDoBalao(canto, tela, balao).left).toBe(1200 - 360 - 16);
    const estreita = posicaoDoBalao(null, { largura: 320, altura: 600 }, balao);
    expect(estreita.largura).toBe(288);
  });

  it('recorte com folga, preso na tela', () => {
    expect(recorteDoAlvo({ top: 2, left: 10, width: 100, height: 20, bottom: 22, right: 110 }, tela))
      .toEqual({ top: 0, left: 4, width: 112, height: 28 });
  });
});

describe('texto e seletor', () => {
  it('negrito em pedaços', () => {
    expect(pedacosDoTexto('Clique em **Salvar** agora')).toEqual([
      { negrito: false, texto: 'Clique em ' },
      { negrito: true, texto: 'Salvar' },
      { negrito: false, texto: ' agora' },
    ]);
  });

  it('seletor não deixa passar nada estranho', () => {
    expect(seletorDaAncora('opo-kpis')).toBe('[data-tour="opo-kpis"]');
    expect(seletorDaAncora('x"] , body [a="')).toBe('[data-tour="xbodya"]');
  });
});
