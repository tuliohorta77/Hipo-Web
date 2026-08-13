// web/src/tests/TarefasDoParceiro.test.jsx
//
// A diferença que importa em relação à aba da oportunidade é UMA: concluir
// não exige agendar a próxima. Parceria não tem estado final, e exigir a
// próxima ali produziria corrente infinita de tarefa que ninguém faz.
//
// Os testes seguram isso, mais o contrato com a tela: toda escrita avisa o
// pai, porque o farol e a contagem de abertas da LINHA mudaram.
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, fireEvent, cleanup, waitFor } from '@testing-library/react';

const mockGet = vi.fn();
const mockPost = vi.fn();

vi.mock('../api', () => ({
  default: {
    get: (...a) => mockGet(...a),
    post: (...a) => mockPost(...a),
  },
}));

import TarefasDoParceiro from '../components/crm/TarefasDoParceiro';

const USUARIOS = [
  { id: 'u1', nome: 'Ana EC' },
  { id: 'u2', nome: 'Bruno EC' },
];

function tarefa(extra = {}) {
  return {
    id: 't1', alvo: 'parceiro', alvo_rotulo: 'Parceiro',
    oportunidade_id: null, oportunidade_numero: null, status_oportunidade: null,
    conta_id: 'p1', conta_razao_social: 'Contabilidade Alfa',
    tipo: 'ligacao', tipo_rotulo: 'Ligação', titulo: 'Ligar para o contador',
    descricao: null, responsavel_id: 'u1', responsavel_nome: 'Ana EC',
    prazo: '2026-08-14T12:00:00Z', situacao: 'futura',
    concluida_em: null, resultado: null, cancelada_em: null,
    motivo_cancelamento: null, tarefa_anterior_id: null,
    criado_em: '2026-08-10T12:00:00Z',
    ...extra,
  };
}

function listaCom(...itens) {
  return { data: { total: itens.length, abertas: itens.length, atrasadas: 0, itens } };
}

function montar(props = {}) {
  return render(
    <TarefasDoParceiro
      parceiroId="p1"
      usuarios={USUARIOS}
      usuarioAtualId="u1"
      {...props}
    />
  );
}

beforeEach(() => {
  mockGet.mockReset();
  mockPost.mockReset();
  mockGet.mockResolvedValue(listaCom(tarefa()));
  mockPost.mockResolvedValue({ data: {} });
});

afterEach(cleanup);

describe('TarefasDoParceiro — a lista', () => {
  it('busca as tarefas DO PARCEIRO, não as da oportunidade', async () => {
    /*
      `conta_id` recorta as tarefas de cultivo da parceria. Mandar
      `oportunidade_id` aqui traria o follow-up de venda para dentro da aba
      do parceiro — outra pergunta, outra tela.
    */
    montar();
    await waitFor(() => expect(mockGet).toHaveBeenCalled());
    expect(mockGet).toHaveBeenCalledWith('/crm/tarefas', {
      params: { conta_id: 'p1', ordenar: 'urgencia' },
    });
  });

  it('mostra título, situação e responsável', async () => {
    montar();
    expect(await screen.findByText('Ligar para o contador')).toBeInTheDocument();
    expect(screen.getByText('Agendado')).toBeInTheDocument();
    expect(screen.getByText('Ana EC')).toBeInTheDocument();
  });

  it('conta as abertas no cabeçalho', async () => {
    mockGet.mockResolvedValue(listaCom(tarefa(), tarefa({ id: 't2' })));
    montar();
    expect(await screen.findByText('(2 em aberto)')).toBeInTheDocument();
  });

  it('sem tarefa nenhuma convida a agendar, em vez de só dizer "vazio"', async () => {
    mockGet.mockResolvedValue(listaCom());
    montar();
    expect(
      await screen.findByText(/Agende a próxima conversa com este parceiro/)
    ).toBeInTheDocument();
  });

  it('tarefa fechada não oferece ações', async () => {
    mockGet.mockResolvedValue(
      listaCom(tarefa({ situacao: 'concluida', concluida_em: '2026-08-12T12:00:00Z' }))
    );
    montar();
    await screen.findByText('Ligar para o contador');
    expect(screen.queryByRole('button', { name: /^Concluir Ligar/ })).not.toBeInTheDocument();
  });
});

describe('TarefasDoParceiro — criar', () => {
  it('manda conta_id, e nunca oportunidade_id', async () => {
    montar();
    await screen.findByText('Ligar para o contador');
    fireEvent.click(screen.getByRole('button', { name: /Nova/ }));

    fireEvent.change(screen.getByLabelText(/Título/), {
      target: { value: 'Almoço com o contador' },
    });
    fireEvent.click(screen.getByRole('button', { name: 'Agendar' }));

    await waitFor(() => expect(mockPost).toHaveBeenCalled());
    const [url, corpo] = mockPost.mock.calls[0];
    expect(url).toBe('/crm/tarefas');
    expect(corpo.conta_id).toBe('p1');
    expect(corpo).not.toHaveProperty('oportunidade_id');
    expect(corpo.titulo).toBe('Almoço com o contador');
  });

  it('o responsável já vem preenchido com quem está na tela', async () => {
    montar();
    await screen.findByText('Ligar para o contador');
    fireEvent.click(screen.getByRole('button', { name: /Nova/ }));
    expect(screen.getByLabelText(/Responsável/)).toHaveValue('u1');
  });

  it('sem título o botão fica desabilitado', async () => {
    montar();
    await screen.findByText('Ligar para o contador');
    fireEvent.click(screen.getByRole('button', { name: /Nova/ }));
    expect(screen.getByRole('button', { name: 'Agendar' })).toBeDisabled();
  });
});

describe('TarefasDoParceiro — concluir', () => {
  it('conclui SEM próxima, e o payload manda null', async () => {
    /*
      Esta é a regra que separa a tarefa de parceiro da tarefa de
      oportunidade. Se um dia ela virar obrigatória aqui, este teste cai —
      e é para cair.
    */
    montar();
    await screen.findByText('Ligar para o contador');
    fireEvent.click(screen.getByRole('button', { name: /Concluir Ligar para o contador/ }));
    fireEvent.click(screen.getByRole('button', { name: 'Concluir tarefa' }));

    await waitFor(() => expect(mockPost).toHaveBeenCalled());
    const [url, corpo] = mockPost.mock.calls[0];
    expect(url).toBe('/crm/tarefas/t1/concluir');
    expect(corpo.proxima).toBeNull();
  });

  it('a próxima é oferecida, não exigida', async () => {
    montar();
    await screen.findByText('Ligar para o contador');
    fireEvent.click(screen.getByRole('button', { name: /Concluir Ligar para o contador/ }));

    // O botão de concluir está livre desde o começo — nada bloqueia.
    expect(screen.getByRole('button', { name: 'Concluir tarefa' })).not.toBeDisabled();
    // E o convite para agendar está lá para quem já sabe a data.
    expect(screen.getByText('Agendar a próxima conversa')).toBeInTheDocument();
  });

  it('quem quiser agendar a próxima, agenda no mesmo clique', async () => {
    montar();
    await screen.findByText('Ligar para o contador');
    fireEvent.click(screen.getByRole('button', { name: /Concluir Ligar para o contador/ }));
    fireEvent.click(screen.getByText('Agendar a próxima conversa'));

    fireEvent.change(screen.getByLabelText(/Próxima: Título/), {
      target: { value: 'Visita ao escritório' },
    });
    fireEvent.click(screen.getByRole('button', { name: 'Concluir tarefa' }));

    await waitFor(() => expect(mockPost).toHaveBeenCalled());
    const [, corpo] = mockPost.mock.calls[0];
    expect(corpo.proxima.titulo).toBe('Visita ao escritório');
  });

  it('abrir a próxima e desistir volta a mandar null', async () => {
    montar();
    await screen.findByText('Ligar para o contador');
    fireEvent.click(screen.getByRole('button', { name: /Concluir Ligar para o contador/ }));
    fireEvent.click(screen.getByText('Agendar a próxima conversa'));
    fireEvent.click(screen.getByText('Não agendar agora'));
    fireEvent.click(screen.getByRole('button', { name: 'Concluir tarefa' }));

    await waitFor(() => expect(mockPost).toHaveBeenCalled());
    expect(mockPost.mock.calls[0][1].proxima).toBeNull();
  });

  it('próxima aberta e incompleta bloqueia o botão', async () => {
    montar();
    await screen.findByText('Ligar para o contador');
    fireEvent.click(screen.getByRole('button', { name: /Concluir Ligar para o contador/ }));
    fireEvent.click(screen.getByText('Agendar a próxima conversa'));
    expect(screen.getByRole('button', { name: 'Concluir tarefa' })).toBeDisabled();
  });
});

describe('TarefasDoParceiro — contrato com a tela', () => {
  it('concluir avisa o pai: o farol da linha mudou', async () => {
    /*
      Sem este aviso, o quadradinho da semana continuaria vermelho depois de
      a tarefa ser concluída — a tela mentindo sobre o que o usuário acabou
      de fazer nela.
    */
    const aoMudar = vi.fn();
    montar({ onMudou: aoMudar });
    await screen.findByText('Ligar para o contador');
    fireEvent.click(screen.getByRole('button', { name: /Concluir Ligar para o contador/ }));
    fireEvent.click(screen.getByRole('button', { name: 'Concluir tarefa' }));
    await waitFor(() => expect(aoMudar).toHaveBeenCalled());
  });

  it('criar também avisa o pai', async () => {
    const aoMudar = vi.fn();
    montar({ onMudou: aoMudar });
    await screen.findByText('Ligar para o contador');
    fireEvent.click(screen.getByRole('button', { name: /Nova/ }));
    fireEvent.change(screen.getByLabelText(/Título/), { target: { value: 'Café' } });
    fireEvent.click(screen.getByRole('button', { name: 'Agendar' }));
    await waitFor(() => expect(aoMudar).toHaveBeenCalled());
  });

  it('erro do backend aparece na tela e não some com a lista', async () => {
    mockPost.mockRejectedValue({
      response: { data: { detail: 'Responsável não encontrado ou inativo.' } },
    });
    montar();
    await screen.findByText('Ligar para o contador');
    fireEvent.click(screen.getByRole('button', { name: /Concluir Ligar para o contador/ }));
    fireEvent.click(screen.getByRole('button', { name: 'Concluir tarefa' }));

    expect(
      await screen.findByText('Responsável não encontrado ou inativo.')
    ).toBeInTheDocument();
    expect(screen.getByText('Ligar para o contador')).toBeInTheDocument();
  });

  it('cancelar manda o motivo', async () => {
    montar();
    await screen.findByText('Ligar para o contador');
    fireEvent.click(screen.getByRole('button', { name: /Cancelar Ligar para o contador/ }));
    fireEvent.change(screen.getByLabelText(/Motivo/), {
      target: { value: 'Agendei duplicado' },
    });
    fireEvent.click(screen.getByRole('button', { name: 'Cancelar tarefa' }));

    await waitFor(() => expect(mockPost).toHaveBeenCalled());
    expect(mockPost.mock.calls[0]).toEqual([
      '/crm/tarefas/t1/cancelar', { motivo: 'Agendei duplicado' },
    ]);
  });
});
