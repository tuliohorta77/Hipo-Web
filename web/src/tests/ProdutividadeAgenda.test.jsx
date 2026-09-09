// web/src/tests/ProdutividadeAgenda.test.jsx
//
// O relatório da agenda. O que estes testes seguram:
//
//   1. os DOIS eixos de data são diferentes, e a tela diz isso em texto —
//      SDR pelo dia em que marcou, EV pelo dia em que a reunião aconteceu
//   2. taxa sem denominador é traço, nunca "0%": uma semana sem reunião
//      fechada tem taxa indefinida, e 0% descreve uma semana ruim de verdade
//   3. pendente aparece SEPARADO e fora das taxas — o sistema não inventa
//      desfecho
//   4. resposta incompleta não vira tela branca (a lição do `itens` da
//      Sprint 4)
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, cleanup, waitFor } from '@testing-library/react';

const mockGet = vi.fn();

vi.mock('../api', () => ({
  default: { get: (...a) => mockGet(...a) },
}));

import ProdutividadeAgenda from '../components/crm/ProdutividadeAgenda';

const DIAS = ['2026-09-07', '2026-09-08', '2026-09-09', '2026-09-10', '2026-09-11'];

function diaSdr(dia, agendamentos) {
  return { dia, agendamentos };
}

function diaEv(dia, extra = {}) {
  return {
    dia, total: 0, realizadas: 0, canceladas: 0, no_show: 0, pendentes: 0,
    ...extra,
  };
}

function dados(extra = {}) {
  return {
    de: '2026-09-07', ate: '2026-09-11', dias: DIAS,
    por_sdr: [
      {
        usuario_id: 'u2', nome: 'Bruno Gonçalo', total: 7,
        por_dia: [
          diaSdr('2026-09-07', 3), diaSdr('2026-09-08', 2),
          diaSdr('2026-09-09', 0), diaSdr('2026-09-10', 2),
          diaSdr('2026-09-11', 0),
        ],
      },
    ],
    por_ev: [
      {
        usuario_id: 'u1', nome: 'Jakeline Santana', total: 5,
        realizadas: 3, canceladas: 1, no_show: 1, pendentes: 0,
        por_dia: [
          diaEv('2026-09-07', { total: 2, realizadas: 2 }),
          diaEv('2026-09-08', { total: 1, no_show: 1 }),
          diaEv('2026-09-09'),
          diaEv('2026-09-10', { total: 2, realizadas: 1, canceladas: 1 }),
          diaEv('2026-09-11'),
        ],
      },
    ],
    agendamentos: 7,
    realizadas: 3, canceladas: 1, no_show: 1, pendentes: 0,
    taxa_realizacao: 0.6, taxa_no_show: 0.2,
    ...extra,
  };
}

function abrir(props = {}) {
  return render(
    <ProdutividadeAgenda
      aberto
      onFechar={vi.fn()}
      de="2026-09-07"
      ate="2026-09-11"
      {...props}
    />
  );
}

beforeEach(() => {
  mockGet.mockReset();
  mockGet.mockResolvedValue({ data: dados() });
});

afterEach(cleanup);

describe('ProdutividadeAgenda — a janela', () => {
  it('busca exatamente o período que recebeu', async () => {
    abrir();
    await waitFor(() => expect(mockGet).toHaveBeenCalledWith(
      '/crm/agenda/produtividade',
      { params: { de: '2026-09-07', ate: '2026-09-11' } }
    ));
  });

  it('fechado, não busca nada', async () => {
    abrir({ aberto: false });
    await new Promise((r) => setTimeout(r, 10));
    expect(mockGet).not.toHaveBeenCalled();
  });

  it('sem período, não busca — a semana ainda não carregou', async () => {
    /*
      A Agenda passa `semana?.inicio`, que é undefined no primeiro render.
      Buscar ali daria um 422 na cara do usuário antes de a tela existir.
    */
    abrir({ de: undefined, ate: undefined });
    await new Promise((r) => setTimeout(r, 10));
    expect(mockGet).not.toHaveBeenCalled();
  });
});

describe('ProdutividadeAgenda — os dois eixos', () => {
  it('diz que o SDR é contado pelo dia em que MARCOU', async () => {
    /*
      Sem a frase, as duas tabelas teriam o mesmo cabeçalho de data
      querendo dizer coisas diferentes — e alguém somaria as duas.
    */
    abrir();
    expect(await screen.findByText(/foi MARCADA/)).toBeInTheDocument();
  });

  it('diz que o EV é contado pelo dia em que ACONTECEU', async () => {
    abrir();
    expect(await screen.findByText(/ACONTECEU/)).toBeInTheDocument();
  });

  it('mostra o total de cada pessoa', async () => {
    abrir();
    expect(await screen.findByText('Bruno Gonçalo')).toBeInTheDocument();
    expect(screen.getByText('Jakeline Santana')).toBeInTheDocument();
  });

  it('quebra o dia do EV por desfecho', async () => {
    // Terça: 1 reunião, e ela foi no-show -> "0·0·1"
    abrir();
    expect(await screen.findByText('0·0·1')).toBeInTheDocument();
  });

  it('dia vazio não vira "0·0·0"', async () => {
    abrir();
    await screen.findByText('Jakeline Santana');
    expect(screen.queryByText('0·0·0')).not.toBeInTheDocument();
  });

  it('o dia inteiramente pendente mostra o "+N"', async () => {
    /*
      Sem ele, um dia com uma reunião só, ainda pendente, mostrava "1" em
      cima e "0·0·0" embaixo — e quem lê procura a reunião que sumiu.
    */
    mockGet.mockResolvedValue({ data: dados({
      por_ev: [{
        usuario_id: 'u1', nome: 'Jakeline Santana', total: 1,
        realizadas: 0, canceladas: 0, no_show: 0, pendentes: 1,
        por_dia: [
          diaEv('2026-09-07', { total: 1, pendentes: 1 }),
          diaEv('2026-09-08'), diaEv('2026-09-09'),
          diaEv('2026-09-10'), diaEv('2026-09-11'),
        ],
      }],
      pendentes: 1,
    }) });
    abrir();
    expect(await screen.findByText('+1')).toBeInTheDocument();
    expect(screen.getByText('0·0·0')).toBeInTheDocument();
  });
});

describe('ProdutividadeAgenda — as taxas', () => {
  it('mostra as duas em percentual', async () => {
    abrir();
    expect(await screen.findByText('60%')).toBeInTheDocument();
    expect(screen.getByText('20%')).toBeInTheDocument();
  });

  it('sem denominador, traço — e nunca 0%', async () => {
    /*
      Uma semana sem nenhuma reunião fechada tem taxa INDEFINIDA. Escrever
      "0%" ali diria que ninguém realizou nada — a mesma frase que descreve
      uma semana ruim de verdade.
    */
    mockGet.mockResolvedValue({ data: dados({
      taxa_realizacao: null, taxa_no_show: null,
      realizadas: 0, canceladas: 0, no_show: 0,
    }) });
    abrir();
    await screen.findByText(/foi MARCADA/);
    expect(screen.getAllByText('—')).toHaveLength(2);
    expect(screen.queryByText('0%')).not.toBeInTheDocument();
  });
});

describe('ProdutividadeAgenda — o que passou sem resposta', () => {
  it('cobra as pendentes, separadas das taxas', async () => {
    mockGet.mockResolvedValue({ data: dados({ pendentes: 4 }) });
    abrir();
    expect(await screen.findByText('4 sem desfecho')).toBeInTheDocument();
    expect(
      screen.getByText(/o sistema não inventa desfecho/)
    ).toBeInTheDocument();
  });

  it('sem pendências, não cobra nada', async () => {
    abrir();
    await screen.findByText(/foi MARCADA/);
    expect(screen.queryByText(/sem desfecho/)).not.toBeInTheDocument();
  });

  it('concorda no singular', async () => {
    mockGet.mockResolvedValue({ data: dados({ pendentes: 1 }) });
    abrir();
    expect(await screen.findByText(/1 reunião já passou sem/)).toBeInTheDocument();
  });
});

describe('ProdutividadeAgenda — resiliência', () => {
  it('janela sem movimento mostra vazio, não tabela em branco', async () => {
    mockGet.mockResolvedValue({ data: dados({
      por_sdr: [], por_ev: [], agendamentos: 0,
      realizadas: 0, canceladas: 0, no_show: 0,
      taxa_realizacao: null, taxa_no_show: null,
    }) });
    abrir();
    expect(
      await screen.findByText('Nenhum agendamento nesta janela.')
    ).toBeInTheDocument();
    expect(screen.getByText('Nenhuma reunião nesta janela.')).toBeInTheDocument();
  });

  it('resposta incompleta não vira tela branca', async () => {
    /*
      A lição do `itens` da Sprint 4: um `.length` em campo ausente
      derrubava a tela inteira. Aqui derrubaria o modal DENTRO da Agenda,
      levando a grade junto.
    */
    mockGet.mockResolvedValue({ data: { de: '2026-09-07', ate: '2026-09-11' } });
    abrir();
    expect(
      await screen.findByText('Nenhum agendamento nesta janela.')
    ).toBeInTheDocument();
  });

  it('erro do servidor aparece na tela', async () => {
    mockGet.mockRejectedValue({
      response: { data: { detail: 'A data inicial não pode ser depois da final.' } },
    });
    abrir();
    expect(
      await screen.findByText('A data inicial não pode ser depois da final.')
    ).toBeInTheDocument();
  });
});
