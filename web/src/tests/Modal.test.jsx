// web/src/tests/Modal.test.jsx
//
// Duas regras do Modal que só aparecem em uso real:
//
//   1. o Esc com DOIS modais abertos. O drilldown da conta dentro da
//      oportunidade empilhou modais pela primeira vez, e cada instância
//      escutava `keydown` na window: um Esc chegava em todas ao mesmo
//      tempo: o usuário fechava o drilldown e perdia junto a oportunidade
//      que estava editando atrás dele — sem entender por quê.
//
//   2. as ações da tela no cabeçalho, ao lado do X, vindas de dois lugares
//      diferentes (prop `acoes`, do pai; <AcoesDoModal>, do filho por
//      portal).
import { describe, it, expect, vi, afterEach } from 'vitest';
import { render, screen, fireEvent, cleanup, within } from '@testing-library/react';
import { useState } from 'react';

import Modal, { AcoesDoModal } from '../components/ui/Modal';

afterEach(cleanup);

const esc = () => fireEvent.keyDown(window, { key: 'Escape', code: 'Escape' });

describe('Modal — Esc com modais empilhados', () => {
  it('fecha só o de cima', () => {
    const fecharBase = vi.fn();
    const fecharTopo = vi.fn();

    render(
      <>
        <Modal aberto onFechar={fecharBase} titulo="Oportunidade">
          <p>base</p>
        </Modal>
        <Modal aberto onFechar={fecharTopo} titulo="Conta">
          <p>topo</p>
        </Modal>
      </>
    );

    esc();
    expect(fecharTopo).toHaveBeenCalledTimes(1);
    expect(fecharBase).not.toHaveBeenCalled();
  });

  it('depois que o de cima fecha, o Esc volta para o de baixo', () => {
    const fecharBase = vi.fn();

    function Pilha() {
      const [topoAberto, setTopoAberto] = useState(true);
      return (
        <>
          <Modal aberto onFechar={fecharBase} titulo="Oportunidade">
            <p>base</p>
          </Modal>
          <Modal
            aberto={topoAberto}
            onFechar={() => setTopoAberto(false)}
            titulo="Conta"
          >
            <p>topo</p>
          </Modal>
        </>
      );
    }

    render(<Pilha />);

    esc();
    expect(screen.queryByText('topo')).not.toBeInTheDocument();
    expect(fecharBase).not.toHaveBeenCalled();

    esc();
    expect(fecharBase).toHaveBeenCalledTimes(1);
  });

  it('re-render do modal de baixo não rouba o Esc do de cima', () => {
    /*
      A armadilha que fez o `onFechar` sair das dependências do efeito: um pai
      que recria a função a cada render remontaria o efeito, e o modal de
      BAIXO voltaria para o topo da pilha. O sintoma seria intermitente —
      depende de o pai ter renderizado de novo desde a abertura.
    */
    const fecharBase = vi.fn();
    const fecharTopo = vi.fn();

    function Pilha() {
      const [n, setN] = useState(0);
      return (
        <>
          <button type="button" onClick={() => setN(n + 1)}>re-render</button>
          {/* onFechar recriado a cada render, de propósito */}
          <Modal aberto onFechar={() => fecharBase(n)} titulo="Oportunidade">
            <p>base</p>
          </Modal>
          <Modal aberto onFechar={() => fecharTopo(n)} titulo="Conta">
            <p>topo</p>
          </Modal>
        </>
      );
    }

    render(<Pilha />);
    fireEvent.click(screen.getByText('re-render'));

    esc();
    expect(fecharTopo).toHaveBeenCalledTimes(1);
    expect(fecharBase).not.toHaveBeenCalled();
  });

  it('modal único continua fechando com Esc', () => {
    const fechar = vi.fn();
    render(<Modal aberto onFechar={fechar} titulo="Sozinho"><p>x</p></Modal>);
    esc();
    expect(fechar).toHaveBeenCalledTimes(1);
  });

  it('modal fechado não responde ao Esc', () => {
    const fechar = vi.fn();
    render(<Modal aberto={false} onFechar={fechar} titulo="Fechado"><p>x</p></Modal>);
    esc();
    expect(fechar).not.toHaveBeenCalled();
  });
});

describe('Modal — ações no cabeçalho', () => {
  // O cabeçalho é o pai do <h2>: a caixa que tem título, ações e X.
  const cabecalho = (nome) =>
    screen.getByRole('heading', { name: nome }).closest('div').parentElement;

  it('a prop `acoes` desenha os botões na linha do título, junto do X', () => {
    render(
      <Modal aberto onFechar={() => {}} titulo="Conta"
        acoes={<button type="button">Salvar</button>}>
        <p>corpo</p>
      </Modal>
    );

    const topo = within(cabecalho('Conta'));
    expect(topo.getByText('Salvar')).toBeInTheDocument();
    expect(topo.getByLabelText('Fechar')).toBeInTheDocument(); // o X
  });

  it('<AcoesDoModal> leva os botões do filho para o cabeçalho', () => {
    /*
      O ponto do portal: o botão nasce lá embaixo, junto do estado que ele
      usa, e aparece em cima. Sem isso, o componente filho teria de
      publicar `sujo`/`salvando`/`salvar` para o pai só para desenhar um
      botão — o canal que já causou loop de renderização uma vez.
    */
    function Filho() {
      const [n, setN] = useState(0);
      return (
        <>
          <p>corpo do filho</p>
          <AcoesDoModal>
            <button type="button" onClick={() => setN(n + 1)}>
              Salvar ({n})
            </button>
          </AcoesDoModal>
        </>
      );
    }

    render(
      <Modal aberto onFechar={() => {}} titulo="Oportunidade">
        <Filho />
      </Modal>
    );

    const topo = within(cabecalho('Oportunidade'));
    const botao = topo.getByText('Salvar (0)');

    // O estado continua sendo do filho, mesmo com o botão renderizado em
    // outro lugar da árvore do DOM.
    fireEvent.click(botao);
    expect(topo.getByText('Salvar (1)')).toBeInTheDocument();
  });

  it('sem ações, o cabeçalho não ganha espaço vazio', () => {
    render(
      <Modal aberto onFechar={() => {}} titulo="Simples"><p>corpo</p></Modal>
    );
    // Só o X.
    expect(within(cabecalho('Simples')).getAllByRole('button')).toHaveLength(1);
  });

  it('<AcoesDoModal> fora de um Modal não quebra nem renderiza nada', () => {
    render(<AcoesDoModal><button type="button">Salvar</button></AcoesDoModal>);
    expect(screen.queryByText('Salvar')).not.toBeInTheDocument();
  });
});

describe('Modal — empilhamento por nível', () => {
  /*
    Todo modal usava z-50, e com z-index empatado quem ganha é o último no
    DOM. Como o Modal renderiza no lugar em que foi escrito, isso amarrava o
    empilhamento à ordem do JSX — e foi assim que o modal de desfecho passou
    a abrir ATRÁS da oportunidade: bastou alguém escrevê-lo antes.

    O nível é a informação que a ordem do arquivo não consegue carregar.
  */
  const camada = (nome) =>
    screen.getByRole('heading', { name: nome }).closest('[role="dialog"]');

  it('sem nível declarado, fica na camada base', () => {
    render(<Modal aberto onFechar={() => {}} titulo="Base"><p>x</p></Modal>);
    expect(camada('Base').className).toContain('z-50');
  });

  it('nivel 2 fica acima da base, independente da ordem no JSX', () => {
    render(
      <>
        {/* De propósito: o de cima está escrito PRIMEIRO. */}
        <Modal aberto onFechar={() => {}} titulo="Desfecho" nivel={2}>
          <p>desfecho</p>
        </Modal>
        <Modal aberto onFechar={() => {}} titulo="Oportunidade">
          <p>oportunidade</p>
        </Modal>
      </>
    );
    expect(camada('Desfecho').className).toContain('z-[60]');
    expect(camada('Oportunidade').className).toContain('z-50');
  });

  it('nivel 3 existe para confirmação sobre um modal de nível 2', () => {
    render(<Modal aberto onFechar={() => {}} titulo="Confirma" nivel={3}><p>x</p></Modal>);
    expect(camada('Confirma').className).toContain('z-[70]');
  });

  it('nível desconhecido cai na base em vez de ficar sem camada', () => {
    render(<Modal aberto onFechar={() => {}} titulo="Estranho" nivel={99}><p>x</p></Modal>);
    expect(camada('Estranho').className).toContain('z-50');
  });
});
