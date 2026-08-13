// web/src/tests/FarolSemanal.test.jsx
//
// O farol tem quatro promessas que estes testes seguram:
//   1. desenha uma casa por semana, na ordem que veio — mais antiga à
//      esquerda, corrente à direita
//   2. a cor vem PRONTA do backend; a tela não recalcula nada
//   3. a leitura não depende de enxergar cor — cada casa tem title e o grupo
//      tem um resumo em texto
//   4. com onClick ele é botão de verdade, porque o farol leva à ação
import { describe, it, expect, vi, afterEach } from 'vitest';
import { render, screen, fireEvent, cleanup } from '@testing-library/react';

import FarolSemanal, { resumoDoFarol } from '../components/ui/FarolSemanal';

function semana(inicio, fim, cor, extra = {}) {
  return {
    inicio, fim, cor, concluidas: 0, agendadas: 0, corrente: false, ...extra,
  };
}

const TRILHA = [
  semana('2026-07-20', '2026-07-26', 'vermelho'),
  semana('2026-07-27', '2026-08-02', 'amarelo', { agendadas: 2 }),
  semana('2026-08-03', '2026-08-09', 'vermelho'),
  semana('2026-08-10', '2026-08-16', 'verde', { concluidas: 3, corrente: true }),
];

afterEach(cleanup);

describe('FarolSemanal — a trilha', () => {
  it('desenha uma casa por semana', () => {
    const { container } = render(<FarolSemanal semanas={TRILHA} />);
    // As casas não têm texto: a contagem é pelos títulos, que é justamente
    // como um leitor de tela as percorre.
    expect(container.querySelectorAll('[title]').length).toBeGreaterThanOrEqual(
      TRILHA.length
    );
  });

  it('sem dado nenhum mostra travessão, não uma trilha vazia', () => {
    render(<FarolSemanal semanas={[]} />);
    expect(screen.getByText('—')).toBeInTheDocument();
  });

  it('cada casa descreve o período e o que aconteceu nele', () => {
    render(<FarolSemanal semanas={TRILHA} />);
    // Semana passada: só agendou.
    expect(
      screen.getByTitle('27/07 a 02/08 · agendado, não feito · 2 em aberto')
    ).toBeInTheDocument();
  });

  it('a semana corrente é nomeada, não datada', () => {
    /*
      Quatro quadrados idênticos não dizem qual é "agora". A palavra resolve
      isso para quem lê o title e o anel resolve para quem enxerga.
    */
    render(<FarolSemanal semanas={TRILHA} />);
    expect(
      screen.getByTitle('Esta semana · contato feito · 3 concluídas')
    ).toBeInTheDocument();
  });

  it('marca a semana corrente com anel', () => {
    const { container } = render(<FarolSemanal semanas={TRILHA} />);
    const comAnel = container.querySelectorAll('.ring-2');
    expect(comAnel.length).toBe(1);
  });
});

describe('FarolSemanal — leitura sem cor', () => {
  it('o grupo inteiro tem um resumo em texto', () => {
    render(<FarolSemanal semanas={TRILHA} semanasSemContato={0} />);
    expect(screen.getByLabelText('Contato feito esta semana')).toBeInTheDocument();
  });

  it('resumo diz há quantas semanas ninguém fala com o parceiro', () => {
    const parado = TRILHA.map((s) => ({ ...s, cor: 'vermelho' }));
    expect(resumoDoFarol(parado, 3)).toBe('Sem contato há 3 semanas');
  });

  it('uma semana no singular', () => {
    const parado = TRILHA.map((s) => ({ ...s, cor: 'vermelho' }));
    expect(resumoDoFarol(parado, 1)).toBe('Sem contato há 1 semana');
  });

  it('trilha inteira vermelha vira "4+ semanas"', () => {
    /*
      A trilha tem quatro casas. Dizer "há 4 semanas" quando pode ser há um
      ano seria afirmar mais do que o dado sustenta.
    */
    const parado = TRILHA.map((s) => ({ ...s, cor: 'vermelho' }));
    expect(resumoDoFarol(parado, 4)).toBe('Sem contato há 4+ semanas');
  });

  it('amarelo na corrente é lido como promessa, não como contato', () => {
    const trilha = [...TRILHA.slice(0, 3), { ...TRILHA[3], cor: 'amarelo' }];
    expect(resumoDoFarol(trilha, 1)).toBe(
      'Tarefa marcada para esta semana, ainda não feita'
    );
  });

  it('sem histórico nenhum não inventa número', () => {
    expect(resumoDoFarol([], 0)).toBe('Sem histórico de contato');
  });
});

describe('FarolSemanal — operacional', () => {
  it('sem onClick não é botão', () => {
    render(<FarolSemanal semanas={TRILHA} />);
    expect(screen.queryByRole('button')).not.toBeInTheDocument();
  });

  it('com onClick vira botão e chama a ação', () => {
    /*
      Diretriz pétrea 2: a tela mostra o panorama E permite agir dali. O
      farol vermelho que não leva a lugar nenhum é relatório.
    */
    const aoClicar = vi.fn();
    render(<FarolSemanal semanas={TRILHA} onClick={aoClicar} />);
    fireEvent.click(screen.getByRole('button'));
    expect(aoClicar).toHaveBeenCalledTimes(1);
  });

  it('o botão diz o que faz, além do estado', () => {
    render(
      <FarolSemanal semanas={TRILHA} semanasSemContato={0} onClick={() => {}} />
    );
    expect(
      screen.getByRole('button', { name: 'Contato feito esta semana. Abrir tarefas.' })
    ).toBeInTheDocument();
  });
});
