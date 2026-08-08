// web/src/tests/Tabs.test.jsx
//
// O Tabs ganhou orientação vertical na tela de Oportunidade: num modal, a
// faixa horizontal come altura, que é o recurso escasso; à esquerda come
// largura, que sobra.
//
// O contrato que estes testes seguram é o que permite trocar a orientação de
// uma tela sem tocar em teste nenhum: mesmo `data-testid`, mesmo `onChange`,
// mesmo badge. Só muda a semântica de orientação para o leitor de tela.
import { describe, it, expect, vi, afterEach } from 'vitest';
import { render, screen, fireEvent, cleanup } from '@testing-library/react';

import Tabs from '../components/ui/Tabs';

const ITENS = [
  { key: 'dados', label: 'Dados' },
  { key: 'tarefas', label: 'Tarefas', badge: 3 },
  { key: 'proposta', label: 'Proposta' },
];

function montar(props = {}) {
  const onChange = vi.fn();
  render(<Tabs items={ITENS} value="dados" onChange={onChange} {...props} />);
  return { onChange };
}

afterEach(cleanup);

describe('Tabs — contrato comum às duas orientações', () => {
  it.each(['horizontal', 'vertical'])('renderiza todos os itens (%s)', (orientacao) => {
    montar({ orientacao });
    expect(screen.getByText('Dados')).toBeInTheDocument();
    expect(screen.getByText('Tarefas')).toBeInTheDocument();
    expect(screen.getByText('Proposta')).toBeInTheDocument();
  });

  it.each(['horizontal', 'vertical'])('o testid não muda (%s)', (orientacao) => {
    /* É o que deixa teste de tela sobreviver à troca de orientação. */
    montar({ orientacao });
    expect(screen.getByTestId('tab-tarefas')).toBeInTheDocument();
  });

  it.each(['horizontal', 'vertical'])('clicar avisa o pai (%s)', (orientacao) => {
    const { onChange } = montar({ orientacao });
    fireEvent.click(screen.getByTestId('tab-proposta'));
    expect(onChange).toHaveBeenCalledWith('proposta');
  });

  it.each(['horizontal', 'vertical'])('mostra o badge (%s)', (orientacao) => {
    montar({ orientacao });
    expect(screen.getByText('3')).toBeInTheDocument();
  });

  it.each(['horizontal', 'vertical'])('badge zero não aparece (%s)', (orientacao) => {
    montar({ orientacao, items: [{ key: 'dados', label: 'Dados', badge: 0 }] });
    expect(screen.queryByText('0')).not.toBeInTheDocument();
  });

  it.each(['horizontal', 'vertical'])('marca a aba ativa (%s)', (orientacao) => {
    montar({ orientacao });
    expect(screen.getByTestId('tab-dados')).toHaveAttribute('aria-selected', 'true');
    expect(screen.getByTestId('tab-tarefas')).toHaveAttribute('aria-selected', 'false');
  });
});

describe('Tabs — orientação', () => {
  it('horizontal é o padrão', () => {
    montar();
    expect(screen.getByRole('tablist')).toHaveAttribute('aria-orientation', 'horizontal');
  });

  it('vertical anuncia a orientação para o leitor de tela', () => {
    montar({ orientacao: 'vertical' });
    expect(screen.getByRole('tablist')).toHaveAttribute('aria-orientation', 'vertical');
  });

  it('vertical empilha, horizontal não', () => {
    const { container } = render(
      <Tabs items={ITENS} value="dados" onChange={() => {}} orientacao="vertical" />
    );
    expect(container.querySelector('[role="tablist"]').className).toContain('flex-col');
  });
});
