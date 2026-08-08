// web/src/tests/AbaTarefas.test.jsx
//
// A aba tem três promessas que os testes precisam segurar:
//   1. passadas, em aberto e futuras aparecem na MESMA lista, agrupadas
//   2. concluir com a oportunidade viva exige a próxima tarefa
//   3. nada abre modal — a aba já vive dentro de um
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, fireEvent, cleanup, waitFor, within } from '@testing-library/react';

const mockGet = vi.fn();
const mockPost = vi.fn();
const mockPatch = vi.fn();

vi.mock('../api', () => ({
  default: {
    get: (...a) => mockGet(...a),
    post: (...a) => mockPost(...a),
    patch: (...a) => mockPatch(...a),
  },
}));

import AbaTarefas from '../components/crm/AbaTarefas';

const OPP = { id: 'o1', numero: 'OPP-2026-00001', status: 'ativa' };

function tarefa(id, extra = {}) {
  return {
    id,
    oportunidade_id: 'o1',
    oportunidade_numero: 'OPP-2026-00001',
    conta_razao_social: 'Metalurgica Alfa LTDA',
    tipo: 'ligacao',
    tipo_rotulo: 'Ligação',
    titulo: `Tarefa ${id}`,
    descricao: null,
    responsavel_id: 'u1',
    responsavel_nome: 'Jakeline Santana',
    prazo: '2026-08-20T13:00:00Z',
    situacao: 'futura',
    concluida_em: null,
    resultado: null,
    cancelada_em: null,
    motivo_cancelamento: null,
    tarefa_anterior_id: null,
    criado_em: '2026-08-01T12:00:00Z',
    ...extra,
  };
}

const LISTA = {
  total: 4,
  abertas: 3,
  atrasadas: 1,
  itens: [
    tarefa('1', { situacao: 'atrasada', titulo: 'Ligar de novo', prazo: '2026-08-01T13:00:00Z' }),
    tarefa('2', { situacao: 'hoje', titulo: 'Enviar proposta' }),
    tarefa('3', { situacao: 'futura', titulo: 'Reuniao de fechamento' }),
    tarefa('4', {
      situacao: 'concluida', titulo: 'Primeiro contato',
      concluida_em: '2026-08-02T13:00:00Z', resultado: 'Atendeu, pediu proposta',
    }),
  ],
};

const USUARIOS = [
  { id: 'u1', nome: 'Jakeline Santana', cargo: 'EV' },
  { id: 'u2', nome: 'Bruno Gonçalo', cargo: 'EV' },
];

function respostas(lista = LISTA) {
  return (url) => {
    if (url === '/crm/tarefas') return Promise.resolve({ data: lista });
    if (url === '/crm/dominio/usuarios') return Promise.resolve({ data: USUARIOS });
    return Promise.resolve({ data: [] });
  };
}

function montar(props = {}) {
  const onMudou = vi.fn();
  render(<AbaTarefas oportunidade={OPP} onMudou={onMudou} {...props} />);
  return { onMudou };
}

beforeEach(() => {
  mockGet.mockReset();
  mockPost.mockReset();
  mockPatch.mockReset();
  mockGet.mockImplementation(respostas());
  mockPost.mockResolvedValue({ data: {} });
  mockPatch.mockResolvedValue({ data: {} });
});

afterEach(cleanup);

describe('AbaTarefas — a lista', () => {
  it('carrega só as tarefas desta oportunidade', async () => {
    montar();
    await waitFor(() =>
      expect(mockGet).toHaveBeenCalledWith('/crm/tarefas', {
        params: { oportunidade_id: 'o1' },
      })
    );
  });

  it('mostra passadas, em aberto e futuras na mesma lista', async () => {
    /*
      O pedido original. Separar histórico de agenda obrigaria o vendedor a
      cruzar duas telas para saber o que já tentou e o que combinou.
    */
    montar();
    expect(await screen.findByText('Ligar de novo')).toBeInTheDocument();
    expect(screen.getByText('Enviar proposta')).toBeInTheDocument();
    expect(screen.getByText('Reuniao de fechamento')).toBeInTheDocument();
    expect(screen.getByText('Primeiro contato')).toBeInTheDocument();
  });

  it('agrupa por urgência, com atrasadas primeiro', async () => {
    montar();
    await screen.findByText('Ligar de novo');
    const grupos = screen.getAllByRole('region').map((s) => s.getAttribute('aria-label'));
    expect(grupos).toEqual(['Atrasadas', 'Hoje', 'Futuras', 'Concluídas']);
  });

  it('não cria grupo vazio', async () => {
    montar();
    await screen.findByText('Ligar de novo');
    expect(screen.queryByRole('region', { name: 'Canceladas' })).not.toBeInTheDocument();
  });

  it('mostra os contadores do cabeçalho', async () => {
    montar();
    expect(await screen.findByText('1 atrasada')).toBeInTheDocument();
    expect(screen.getByText('3 em aberto')).toBeInTheDocument();
    expect(screen.getByText('4 no total')).toBeInTheDocument();
  });

  it('mostra o resultado de uma tarefa concluída', async () => {
    montar();
    await screen.findByText('Primeiro contato');
    expect(screen.getByText(/Atendeu, pediu proposta/)).toBeInTheDocument();
  });

  it('tarefa fechada não oferece ações', async () => {
    /* Reescrever tarefa fechada apagaria o histórico — o backend recusa. */
    montar();
    await screen.findByText('Primeiro contato');
    expect(screen.queryByLabelText('Concluir Primeiro contato')).not.toBeInTheDocument();
    expect(screen.queryByLabelText('Editar Primeiro contato')).not.toBeInTheDocument();
  });

  it('estado vazio convida a agendar', async () => {
    mockGet.mockImplementation(respostas({ total: 0, abertas: 0, atrasadas: 0, itens: [] }));
    montar();
    expect(await screen.findByText('Nenhuma tarefa nesta oportunidade')).toBeInTheDocument();
  });

  it('erro da API aparece na tela', async () => {
    mockGet.mockImplementation((url) => {
      if (url === '/crm/tarefas') {
        return Promise.reject({ response: { data: { detail: 'Boom' } } });
      }
      return respostas()(url);
    });
    montar();
    expect(await screen.findByText('Boom')).toBeInTheDocument();
  });
});

describe('AbaTarefas — criar', () => {
  it('o formulário só aparece depois de clicar', async () => {
    montar();
    await screen.findByText('Ligar de novo');
    expect(screen.queryByLabelText('Título')).not.toBeInTheDocument();
    fireEvent.click(screen.getByText('Nova tarefa'));
    expect(await screen.findByLabelText('Título')).toBeInTheDocument();
  });

  it('o botão de criar fica travado sem título', async () => {
    montar();
    await screen.findByText('Ligar de novo');
    fireEvent.click(screen.getByText('Nova tarefa'));
    await screen.findByLabelText('Título');
    expect(screen.getByText('Criar tarefa').closest('button')).toBeDisabled();
  });

  it('cria com a oportunidade no corpo', async () => {
    const { onMudou } = montar();
    await screen.findByText('Ligar de novo');
    fireEvent.click(screen.getByText('Nova tarefa'));
    fireEvent.change(await screen.findByLabelText('Título'), {
      target: { value: 'Ligar para o RH' },
    });
    fireEvent.change(screen.getByLabelText('Responsável'), { target: { value: 'u2' } });
    fireEvent.click(screen.getByText('Criar tarefa'));

    await waitFor(() => expect(mockPost).toHaveBeenCalled());
    const [url, corpo] = mockPost.mock.calls[0];
    expect(url).toBe('/crm/tarefas');
    expect(corpo.oportunidade_id).toBe('o1');
    expect(corpo.titulo).toBe('Ligar para o RH');
    expect(corpo.responsavel_id).toBe('u2');
    expect(corpo.prazo).toMatch(/^\d{4}-\d{2}-\d{2}T/);
    await waitFor(() => expect(onMudou).toHaveBeenCalled());
  });

  it('erro ao criar não fecha o formulário', async () => {
    /* Fechar num erro jogaria fora o que o usuário digitou. */
    mockPost.mockRejectedValue({ response: { data: { detail: 'Prazo inválido' } } });
    montar();
    await screen.findByText('Ligar de novo');
    fireEvent.click(screen.getByText('Nova tarefa'));
    fireEvent.change(await screen.findByLabelText('Título'), { target: { value: 'X' } });
    fireEvent.change(screen.getByLabelText('Responsável'), { target: { value: 'u1' } });
    fireEvent.click(screen.getByText('Criar tarefa'));

    expect(await screen.findByText('Prazo inválido')).toBeInTheDocument();
    expect(screen.getByLabelText('Título')).toBeInTheDocument();
  });
});

describe('AbaTarefas — concluir exige a próxima', () => {
  it('o painel abre já com os campos da próxima', async () => {
    montar();
    await screen.findByText('Ligar de novo');
    fireEvent.click(screen.getByLabelText('Concluir Ligar de novo'));
    expect(await screen.findByLabelText('Próxima: Título')).toBeInTheDocument();
    expect(screen.getByText(/Se não há próximo passo, finalize a oportunidade/))
      .toBeInTheDocument();
  });

  it('o botão fica travado enquanto a próxima está incompleta', async () => {
    montar();
    await screen.findByText('Ligar de novo');
    fireEvent.click(screen.getByLabelText('Concluir Ligar de novo'));
    await screen.findByLabelText('Próxima: Título');
    expect(screen.getByText('Concluir tarefa').closest('button')).toBeDisabled();
  });

  it('envia conclusão e próxima na mesma chamada', async () => {
    /*
      Uma chamada só porque o backend faz as duas coisas na mesma transação:
      se a próxima falhar, a conclusão não vale.
    */
    montar();
    await screen.findByText('Ligar de novo');
    fireEvent.click(screen.getByLabelText('Concluir Ligar de novo'));
    fireEvent.change(await screen.findByLabelText('Próxima: Título'), {
      target: { value: 'Apresentar proposta' },
    });
    fireEvent.change(screen.getByLabelText('O que aconteceu (opcional)'), {
      target: { value: 'Atendeu' },
    });
    fireEvent.click(screen.getByText('Concluir tarefa'));

    await waitFor(() => expect(mockPost).toHaveBeenCalled());
    const [url, corpo] = mockPost.mock.calls[0];
    expect(url).toBe('/crm/tarefas/1/concluir');
    expect(corpo.resultado).toBe('Atendeu');
    expect(corpo.proxima.titulo).toBe('Apresentar proposta');
  });

  it('oportunidade finalizada não pede a próxima', async () => {
    montar({ oportunidade: { ...OPP, status: 'conquistado' } });
    await screen.findByText('Ligar de novo');
    fireEvent.click(screen.getByLabelText('Concluir Ligar de novo'));
    expect(await screen.findByText(/não é preciso agendar a próxima/)).toBeInTheDocument();
    expect(screen.queryByLabelText('Próxima: Título')).not.toBeInTheDocument();
    expect(screen.getByText('Concluir tarefa').closest('button')).not.toBeDisabled();
  });

  it('finalizada envia proxima nula', async () => {
    montar({ oportunidade: { ...OPP, status: 'perdido' } });
    await screen.findByText('Ligar de novo');
    fireEvent.click(screen.getByLabelText('Concluir Ligar de novo'));
    fireEvent.click(await screen.findByText('Concluir tarefa'));
    await waitFor(() => expect(mockPost).toHaveBeenCalled());
    expect(mockPost.mock.calls[0][1].proxima).toBeNull();
  });

  it('suspensa continua exigindo a próxima', async () => {
    /* Pausa sem data para voltar é como oportunidade morre em silêncio. */
    montar({ oportunidade: { ...OPP, status: 'suspensa' } });
    await screen.findByText('Ligar de novo');
    fireEvent.click(screen.getByLabelText('Concluir Ligar de novo'));
    expect(await screen.findByLabelText('Próxima: Título')).toBeInTheDocument();
  });

  it('o 422 do backend aparece na tela', async () => {
    mockPost.mockRejectedValue({
      response: { data: { detail: 'Concluir exige agendar a próxima tarefa.' } },
    });
    montar();
    await screen.findByText('Ligar de novo');
    fireEvent.click(screen.getByLabelText('Concluir Ligar de novo'));
    fireEvent.change(await screen.findByLabelText('Próxima: Título'), {
      target: { value: 'X' },
    });
    fireEvent.click(screen.getByText('Concluir tarefa'));
    expect(await screen.findByText('Concluir exige agendar a próxima tarefa.'))
      .toBeInTheDocument();
  });
});

describe('AbaTarefas — cancelar e editar', () => {
  it('cancelar não pede a próxima', async () => {
    /* Cancelar é dizer que aquilo não deveria ter sido agendado. */
    montar();
    await screen.findByText('Ligar de novo');
    fireEvent.click(screen.getByLabelText('Cancelar Ligar de novo'));
    expect(await screen.findByLabelText('Motivo do cancelamento (opcional)'))
      .toBeInTheDocument();
    expect(screen.queryByLabelText('Próxima: Título')).not.toBeInTheDocument();
  });

  it('envia o motivo do cancelamento', async () => {
    montar();
    await screen.findByText('Ligar de novo');
    fireEvent.click(screen.getByLabelText('Cancelar Ligar de novo'));
    fireEvent.change(await screen.findByLabelText('Motivo do cancelamento (opcional)'), {
      target: { value: 'Agendei duplicado' },
    });
    fireEvent.click(screen.getByText('Cancelar tarefa'));
    await waitFor(() =>
      expect(mockPost).toHaveBeenCalledWith('/crm/tarefas/1/cancelar', {
        motivo: 'Agendei duplicado',
      })
    );
  });

  it('editar abre com os valores atuais', async () => {
    montar();
    await screen.findByText('Ligar de novo');
    fireEvent.click(screen.getByLabelText('Editar Ligar de novo'));
    expect(await screen.findByLabelText('Título')).toHaveValue('Ligar de novo');
  });

  it('salvar edição chama PATCH', async () => {
    montar();
    await screen.findByText('Ligar de novo');
    fireEvent.click(screen.getByLabelText('Editar Ligar de novo'));
    fireEvent.change(await screen.findByLabelText('Título'), {
      target: { value: 'Ligar amanhã' },
    });
    fireEvent.click(screen.getByText('Salvar tarefa'));
    await waitFor(() => expect(mockPatch).toHaveBeenCalled());
    expect(mockPatch.mock.calls[0][0]).toBe('/crm/tarefas/1');
    expect(mockPatch.mock.calls[0][1].titulo).toBe('Ligar amanhã');
  });
});
