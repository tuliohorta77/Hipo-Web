// web/src/tests/Modal.test.jsx
//
// O Esc do modal — a regra que só aparece quando há DOIS abertos.
//
// O drilldown da conta dentro da oportunidade empilhou modais pela primeira
// vez. Cada instância escutava `keydown` na window, então um Esc chegava em
// todas ao mesmo tempo: o usuário fechava o drilldown e perdia junto a
// oportunidade que estava editando atrás dele — sem entender por quê.
//
// Estes testes seguram a pilha: só o modal do topo responde à tecla.
import { describe, it, expect, vi, afterEach } from 'vitest';
import { render, screen, fireEvent, cleanup } from '@testing-library/react';
import { useState } from 'react';

import Modal from '../components/ui/Modal';

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
