// web/src/tests/CarregarMais.test.jsx
//
// O "carregar mais" das colunas. Três promessas:
//   1. o botão aparece sempre que a coluna tem mais itens do que cartões
//   2. juntar páginas nunca repete cartão (chave duplicada embaralha o React)
//   3. recarregar a tela devolve a coluna até onde o usuário já tinha puxado
import { describe, it, expect, vi, afterEach } from 'vitest';
import { render, screen, fireEvent, cleanup } from '@testing-library/react';

import CarregarMais, {
  PAGINA_KANBAN, completarColuna, mesclarItens,
} from '../components/crm/CarregarMais';

afterEach(cleanup);

const itens = (de, ate) => Array.from({ length: ate - de }, (_, i) => ({ id: `i${de + i}` }));

describe('CarregarMais — o botão', () => {
  it('puxa de 100 em 100', () => {
    expect(PAGINA_KANBAN).toBe(100);
  });

  it('mostra quanto falta e quantos vêm no próximo clique', () => {
    const onCarregar = vi.fn();
    render(<CarregarMais exibidos={50} total={1124} onCarregar={onCarregar} />);
    expect(screen.getByText('+1074 não exibidas')).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: /Carregar mais 100/ }));
    expect(onCarregar).toHaveBeenCalledTimes(1);
  });

  it('no fim da coluna, oferece só o que falta', () => {
    render(<CarregarMais exibidos={100} total={146} onCarregar={() => {}} />);
    expect(screen.getByRole('button', { name: /Carregar mais 46/ })).toBeInTheDocument();
  });

  it('some quando todos os cartões já estão na tela', () => {
    const { container } = render(
      <CarregarMais exibidos={10} total={10} onCarregar={() => {}} />
    );
    expect(container).toBeEmptyDOMElement();
  });

  it('desabilita enquanto carrega, para não pedir a mesma página duas vezes', () => {
    render(<CarregarMais exibidos={10} total={30} onCarregar={() => {}} carregando />);
    expect(screen.getByRole('button', { name: /Carregando/ })).toBeDisabled();
  });
});

describe('CarregarMais — mesclarItens', () => {
  it('anexa a página nova sem repetir id', () => {
    const r = mesclarItens([{ id: 'a' }, { id: 'b' }], [{ id: 'b' }, { id: 'c' }]);
    expect(r.map((i) => i.id)).toEqual(['a', 'b', 'c']);
  });
});

describe('CarregarMais — completarColuna', () => {
  const coluna = (n, quantidade) => ({ fase: 'suspect', quantidade, itens: itens(0, n) });

  it('sem limite guardado, não busca nada', async () => {
    const buscar = vi.fn();
    const c = coluna(100, 1124);
    expect(await completarColuna(c, undefined, buscar)).toBe(c);
    expect(buscar).not.toHaveBeenCalled();
  });

  it('busca o que falta para voltar até onde o usuário estava', async () => {
    const buscar = vi.fn(async (offset, limit) => ({
      quantidade: 1124, itens: itens(offset, offset + limit),
    }));
    const r = await completarColuna(coluna(100, 1124), 300, buscar);
    expect(buscar).toHaveBeenCalledWith(100, 200);
    expect(r.itens).toHaveLength(300);
  });

  it('não passa do tamanho real da coluna', async () => {
    const buscar = vi.fn(async (offset, limit) => ({
      quantidade: 120, itens: itens(offset, Math.min(offset + limit, 120)),
    }));
    const r = await completarColuna(coluna(100, 120), 300, buscar);
    expect(buscar).toHaveBeenCalledWith(100, 20);
    expect(r.itens).toHaveLength(120);
  });

  it('para quando o servidor devolve página vazia (coluna encolheu)', async () => {
    const buscar = vi.fn(async () => ({ quantidade: 100, itens: [] }));
    const r = await completarColuna(coluna(100, 200), 200, buscar);
    expect(buscar).toHaveBeenCalledTimes(1);
    expect(r.itens).toHaveLength(100);
  });
});
