// web/src/tests/ProducaoDoMes.test.jsx
//
// "Quantas reuniões tivemos em agosto?" — a pergunta que o HIPO não
// respondia. Quatro promessas que estes testes seguram:
//
//   1. o mês pedido é o mês inteiro, do dia 1 ao último — inclusive fevereiro
//   2. realizadas, agendadas e canceladas são três números distintos, e a
//      tela não os soma
//   3. clicar num tipo abre EXATAMENTE as tarefas que ele contou — mesmo
//      recorte, com base=conclusao
//   4. os filtros da barra da tela valem também para o agregado
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, fireEvent, cleanup, waitFor, within } from '@testing-library/react';

const mockGet = vi.fn();

vi.mock('../api', () => ({
  default: { get: (...a) => mockGet(...a) },
}));

import ProducaoDoMes, { limitesDoMes, rotuloDoMes } from '../components/crm/ProducaoDoMes';

const TIPOS = [
  ['ligacao', 'Ligação'], ['reuniao', 'Reunião'], ['visita', 'Visita'],
  ['proposta', 'Proposta'], ['email', 'E-mail'], ['whatsapp', 'WhatsApp'],
  ['outro', 'Outro'],
];

function resumo(extra = {}) {
  const contagens = { reuniao: [12, 15, 2], ligacao: [30, 33, 1], ...extra.contagens };
  return {
    de: '2026-08-01',
    ate: '2026-08-31',
    realizadas: 42,
    agendadas: 48,
    canceladas: 3,
    por_tipo: TIPOS.map(([tipo, rotulo]) => {
      const [realizadas, agendadas, canceladas] = contagens[tipo] || [0, 0, 0];
      return { tipo, rotulo, realizadas, agendadas, canceladas };
    }),
    por_responsavel: [
      { usuario_id: 'u1', nome: 'Jakeline Santana', realizadas: 25, agendadas: 28 },
      { usuario_id: 'u2', nome: 'Bruno Gonçalo', realizadas: 17, agendadas: 20 },
    ],
    ...extra.raiz,
  };
}

function itensDeReuniao() {
  return {
    total: 2,
    abertas: 0,
    atrasadas: 0,
    itens: [
      {
        id: 't1', tipo: 'reuniao', tipo_rotulo: 'Reunião',
        titulo: 'Apresentacao do PCMSO', conta_razao_social: 'Metalurgica Alfa LTDA',
        responsavel_nome: 'Jakeline Santana', situacao: 'concluida',
        prazo: '2026-08-12T13:00:00Z', concluida_em: '2026-08-12T16:00:00Z',
      },
      {
        id: 't2', tipo: 'reuniao', tipo_rotulo: 'Reunião',
        titulo: 'Fechamento do contrato', conta_razao_social: 'Transportadora Beta LTDA',
        responsavel_nome: 'Bruno Gonçalo', situacao: 'concluida',
        prazo: '2026-08-27T13:00:00Z', concluida_em: '2026-08-27T18:00:00Z',
      },
    ],
  };
}

function respostas({ resumoDados = resumo(), lista = itensDeReuniao() } = {}) {
  return (url) => {
    if (url === '/crm/tarefas/resumo') return Promise.resolve({ data: resumoDados });
    if (url === '/crm/tarefas') return Promise.resolve({ data: lista });
    return Promise.resolve({ data: {} });
  };
}

function montar(props = {}) {
  return render(
    <ProducaoDoMes aberto onFechar={() => {}} {...props} />
  );
}

const chamadasDe = (url) => mockGet.mock.calls.filter((c) => c[0] === url);
const ultimaChamada = (url) => chamadasDe(url).at(-1);

beforeEach(() => {
  // Só o relógio. Com os timers inteiros falsos, o waitFor do testing-library
  // nunca avança e todo teste assíncrono estoura por timeout.
  vi.useFakeTimers({ toFake: ['Date'] });
  vi.setSystemTime(new Date(2026, 7, 14, 12, 0, 0));
  mockGet.mockReset();
  mockGet.mockImplementation(respostas());
});

afterEach(() => {
  cleanup();
  vi.useRealTimers();
});

describe('limitesDoMes — o mês inteiro, do dia 1 ao último', () => {
  it('agosto vai de 01 a 31', () => {
    expect(limitesDoMes(2026, 7)).toEqual({ de: '2026-08-01', ate: '2026-08-31' });
  });

  it('fevereiro comum termina em 28', () => {
    expect(limitesDoMes(2026, 1).ate).toBe('2026-02-28');
  });

  it('fevereiro bissexto termina em 29', () => {
    /* Dia 0 do mês seguinte é o último deste — acerta bissexto sem tabela. */
    expect(limitesDoMes(2024, 1).ate).toBe('2024-02-29');
  });

  it('dezembro não vaza para o ano seguinte', () => {
    expect(limitesDoMes(2026, 11)).toEqual({ de: '2026-12-01', ate: '2026-12-31' });
  });

  it('todo mês começa no dia 1', () => {
    for (let m = 0; m < 12; m += 1) {
      expect(limitesDoMes(2026, m).de.endsWith('-01')).toBe(true);
    }
  });

  it('o rótulo é o mês por extenso', () => {
    expect(rotuloDoMes(2026, 7)).toBe('agosto de 2026');
  });
});

describe('ProducaoDoMes — o resumo', () => {
  it('abre no mês corrente e pede o mês inteiro', async () => {
    montar();
    await waitFor(() => expect(chamadasDe('/crm/tarefas/resumo').length).toBe(1));
    expect(ultimaChamada('/crm/tarefas/resumo')[1].params).toMatchObject({
      de: '2026-08-01', ate: '2026-08-31',
    });
    expect(screen.getByText('agosto de 2026')).toBeInTheDocument();
  });

  it('mostra os três números separados, sem somá-los', async () => {
    /*
      Realizadas, agendadas e canceladas usam datas diferentes. A mesma
      reunião marcada e feita em agosto conta nas duas primeiras — somar daria
      um número sem significado.
    */
    montar();
    expect(await screen.findByText('42')).toBeInTheDocument();
    expect(screen.getByText('48')).toBeInTheDocument();
    expect(screen.getByText('3')).toBeInTheDocument();
    expect(screen.queryByText('93')).not.toBeInTheDocument();
  });

  it('lista os sete tipos, inclusive os zerados', async () => {
    /* Zero é informação: nenhuma visita em agosto é um fato sobre agosto. */
    montar();
    await screen.findByText('Reunião');
    for (const [, rotulo] of TIPOS) {
      expect(screen.getByText(rotulo)).toBeInTheDocument();
    }
  });

  it('mostra a quebra por responsável', async () => {
    montar();
    expect(await screen.findByText('Jakeline Santana')).toBeInTheDocument();
    expect(screen.getByText('Bruno Gonçalo')).toBeInTheDocument();
  });

  it('avisa quando ninguém registrou nada no período', async () => {
    mockGet.mockImplementation(respostas({
      resumoDados: resumo({ raiz: { por_responsavel: [] } }),
    }));
    montar();
    expect(
      await screen.findByText('Ninguém registrou tarefa neste período.')
    ).toBeInTheDocument();
  });

  it('erro da API aparece na tela', async () => {
    mockGet.mockImplementation((url) => {
      if (url === '/crm/tarefas/resumo') {
        return Promise.reject({ response: { data: { detail: 'Boom' } } });
      }
      return respostas()(url);
    });
    montar();
    expect(await screen.findByText('Boom')).toBeInTheDocument();
  });
});

describe('ProducaoDoMes — navegação de mês', () => {
  it('o mês anterior refaz a consulta com a janela nova', async () => {
    montar();
    await waitFor(() => expect(chamadasDe('/crm/tarefas/resumo').length).toBe(1));

    fireEvent.click(screen.getByLabelText('Mês anterior'));

    await waitFor(() => expect(chamadasDe('/crm/tarefas/resumo').length).toBe(2));
    expect(ultimaChamada('/crm/tarefas/resumo')[1].params).toMatchObject({
      de: '2026-07-01', ate: '2026-07-31',
    });
    expect(screen.getByText('julho de 2026')).toBeInTheDocument();
  });

  it('atravessa a virada do ano para trás', async () => {
    vi.setSystemTime(new Date(2026, 0, 15, 12, 0, 0));
    montar();
    await screen.findByText('janeiro de 2026');

    fireEvent.click(screen.getByLabelText('Mês anterior'));

    await screen.findByText('dezembro de 2025');
    await waitFor(() =>
      expect(ultimaChamada('/crm/tarefas/resumo')[1].params).toMatchObject({
        de: '2025-12-01', ate: '2025-12-31',
      })
    );
  });

  it('não deixa navegar para o futuro', async () => {
    /* Mês que ainda não aconteceu só pode devolver zero, e zero sem causa
       parece defeito. */
    montar();
    await screen.findByText('agosto de 2026');
    expect(screen.getByLabelText('Mês seguinte')).toBeDisabled();
  });

  it('depois de voltar, o mês seguinte volta a funcionar', async () => {
    montar();
    await screen.findByText('agosto de 2026');
    fireEvent.click(screen.getByLabelText('Mês anterior'));
    await screen.findByText('julho de 2026');

    const seguinte = screen.getByLabelText('Mês seguinte');
    expect(seguinte).not.toBeDisabled();
    fireEvent.click(seguinte);
    await screen.findByText('agosto de 2026');
  });
});

describe('ProducaoDoMes — drilldown', () => {
  const abrirReuniao = () => fireEvent.click(screen.getByText('Reunião'));

  it('clicar num tipo abre exatamente as tarefas que ele contou', async () => {
    montar();
    await screen.findByText('Reunião');
    abrirReuniao();

    await waitFor(() => expect(chamadasDe('/crm/tarefas').length).toBe(1));
    const { params } = ultimaChamada('/crm/tarefas')[1];
    expect(params).toMatchObject({
      tipo: 'reuniao',
      de: '2026-08-01',
      ate: '2026-08-31',
      // Sem isto viriam as MARCADAS para o mês, que é outro conjunto.
      base: 'conclusao',
      situacao: ['concluida'],
    });
  });

  it('mostra os itens com empresa e responsável', async () => {
    montar();
    await screen.findByText('Reunião');
    abrirReuniao();

    const lista = within(
      await screen.findByRole('region', { name: /Realizadas — Reunião/ })
    );
    expect(lista.getByText('Apresentacao do PCMSO')).toBeInTheDocument();
    expect(lista.getByText('Transportadora Beta LTDA')).toBeInTheDocument();
    expect(lista.getByText('Bruno Gonçalo')).toBeInTheDocument();
  });

  it('clicar de novo fecha', async () => {
    montar();
    await screen.findByText('Reunião');
    abrirReuniao();
    await screen.findByRole('region', { name: /Realizadas — Reunião/ });

    abrirReuniao();
    await waitFor(() =>
      expect(screen.queryByRole('region', { name: /Realizadas — Reunião/ }))
        .not.toBeInTheDocument()
    );
  });

  it('tipo zerado não abre lista nenhuma', async () => {
    /* Não há o que mostrar, e a linha que reage ao clique sem produzir nada
       ensina que a tela está quebrada. */
    montar();
    await screen.findByText('Visita');
    fireEvent.click(screen.getByText('Visita'));

    await waitFor(() => expect(chamadasDe('/crm/tarefas').length).toBe(0));
  });

  it('trocar de mês fecha o drilldown', async () => {
    /* A lista aberta é de um mês que não está mais na tela — dado errado com
       cara de certo. */
    montar();
    await screen.findByText('Reunião');
    abrirReuniao();
    await screen.findByRole('region', { name: /Realizadas — Reunião/ });

    fireEvent.click(screen.getByLabelText('Mês anterior'));

    await waitFor(() =>
      expect(screen.queryByRole('region', { name: /Realizadas — Reunião/ }))
        .not.toBeInTheDocument()
    );
  });
});

describe('ProducaoDoMes — os filtros da tela', () => {
  it('o agregado respeita responsável e busca', async () => {
    /*
      Agregado que ignora o filtro da tela produz um número global ao lado de
      uma lista filtrada — duas respostas para a mesma pergunta.
    */
    montar({ filtros: { responsavel_id: 'u2', q: 'Beta' } });
    await waitFor(() => expect(chamadasDe('/crm/tarefas/resumo').length).toBe(1));
    expect(ultimaChamada('/crm/tarefas/resumo')[1].params).toMatchObject({
      responsavel_id: 'u2', q: 'Beta', de: '2026-08-01', ate: '2026-08-31',
    });
  });

  it('o drilldown herda os mesmos filtros', async () => {
    montar({ filtros: { responsavel_id: 'u2' } });
    await screen.findByText('Reunião');
    fireEvent.click(screen.getByText('Reunião'));

    await waitFor(() => expect(chamadasDe('/crm/tarefas').length).toBe(1));
    expect(ultimaChamada('/crm/tarefas')[1].params).toMatchObject({
      responsavel_id: 'u2', tipo: 'reuniao', base: 'conclusao',
    });
  });

  it('avisa no subtítulo que há filtro aplicado', async () => {
    montar({ filtros: { q: 'Beta' } });
    expect(
      await screen.findByText('Com os filtros da tela aplicados.')
    ).toBeInTheDocument();
  });

  it('sem filtro, o subtítulo explica os três números', async () => {
    montar();
    expect(
      await screen.findByText('Tarefas realizadas, agendadas e canceladas no período.')
    ).toBeInTheDocument();
  });

  it('não consulta nada enquanto está fechado', async () => {
    render(<ProducaoDoMes aberto={false} onFechar={() => {}} />);
    await waitFor(() => expect(chamadasDe('/crm/tarefas/resumo').length).toBe(0));
  });
});
