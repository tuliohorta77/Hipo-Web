// web/src/tests/TextoAula.test.jsx
//
// O markdown pequeno da aula. Duas promessas: o subconjunto vira os
// elementos certos, e HTML digitado no estúdio aparece como TEXTO.
import { describe, it, expect, afterEach } from 'vitest';
import { render, screen, cleanup } from '@testing-library/react';
import TextoAula, { blocos } from '../components/uc/TextoAula';

afterEach(cleanup);

describe('TextoAula', () => {
  it('títulos, listas, destaque e negrito', () => {
    render(<TextoAula md={'## Seção\n\nTexto com **negrito**.\n\n- um\n- dois\n\n1. primeiro\n2. segundo\n\n> Na conversa com o cliente: pergunte.'} />);
    expect(screen.getByRole('heading', { level: 2, name: 'Seção' })).toBeInTheDocument();
    expect(screen.getByText('negrito').tagName).toBe('STRONG');
    expect(screen.getAllByRole('list')).toHaveLength(2);
    expect(screen.getByText('primeiro').closest('ol')).not.toBeNull();
    expect(screen.getByText(/Na conversa com o cliente/).closest('blockquote')).not.toBeNull();
  });

  it('linhas seguidas viram um parágrafo; linha em branco separa', () => {
    const b = blocos('linha um\nlinha dois\n\noutro');
    expect(b).toEqual([
      { tipo: 'p', linhas: ['linha um', 'linha dois'] },
      { tipo: 'p', linhas: ['outro'] },
    ]);
  });

  it('HTML digitado aparece como texto, não executa', () => {
    const { container } = render(<TextoAula md={'<script>alert(1)</script> <img src=x onerror=alert(1)>'} />);
    expect(container.querySelector('script')).toBeNull();
    expect(container.querySelector('img')).toBeNull();
    expect(screen.getByText(/<script>alert\(1\)<\/script>/)).toBeInTheDocument();
  });

  it('texto vazio não desenha nada', () => {
    const { container } = render(<TextoAula md="" />);
    expect(container).toBeEmptyDOMElement();
  });
});
