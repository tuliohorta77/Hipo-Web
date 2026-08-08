// web/src/tests/AbaTarefas.test.jsx
//
// A aba é uma LINHA DO TEMPO. Quatro promessas que os testes seguram:
//   1. tudo num fluxo só, sem agrupamento e sem caixa por item
//   2. a ordem vem do servidor — o componente não reordena
//   3. a linha mostra o essencial; o resto e as AÇÕES vivem no drilldown
//   4. concluir com a oportunidade viva exige a próxima tarefa
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

// Já na ordem que o servidor devolve com ordenar=cronologico: prazo desc.
const LISTA = {
  total: 4,
  abertas: 3,
  atrasadas: 1,
  itens: [
    tarefa('3', { situacao: 'futura', titulo: 'Reuniao de fechamento', prazo: '2026-09-10T13:00:00Z' }),
    tarefa('2', { situacao: 'hoje', titulo: 'Enviar proposta', prazo: '2026-08-20T13:00:00Z' }),
    tarefa('1', {
      situacao: 'atrasada', titulo: 'Ligar de novo',
      prazo: '2026-08-01T13:00:00Z', tipo: 'whatsapp', tipo_rotulo: 'WhatsApp',
      descricao: 'Perguntar pelo numero de vidas',
    }),
    tarefa('4', {
      situacao: 'concluida', titulo: 'Primeiro contato',
      prazo: '2026-07-15T13:00:00Z',
      concluida_em: '2026-07-15T16:00:00Z', resultado: 'Atendeu, pediu proposta',
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

/** A linha da tarefa é o botão que a abre. */
function linha(titulo) {
  return screen.getByText(titulo).closest('button');
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

describe('AbaTarefas — a linha do tempo', () => {
  it('pede a ordem cronológica ao servidor', async () => {
    /*
      A ordem vem do servidor para não existir uma segunda regra de
      ordenação no navegador. A de urgência continua existindo na API, para
      a agenda por pessoa.
    */
    montar();
    await waitFor(() =>
      expect(mockGet).toHaveBeenCalledWith('/crm/tarefas', {
        params: { oportunidade_id: 'o1', ordenar: 'cronologico' },
      })
    );
  });

  it('mostra passadas, em aberto e futuras no mesmo fluxo', async () => {
    montar();
    expect(await screen.findByText('Reuniao de fechamento')).toBeInTheDocument();
    expect(screen.getByText('Enviar proposta')).toBeInTheDocument();
    expect(screen.getByText('Ligar de novo')).toBeInTheDocument();
    expect(screen.getByText('Primeiro contato')).toBeInTheDocument();
  });

  it('respeita a ordem que o servidor mandou, sem reordenar', async () => {
    montar();
    await screen.findByText('Ligar de novo');
    const titulos = within(screen.getByRole('list'))
      .getAllByRole('listitem')
      .map((li) => li.textContent);
    expect(titulos[0]).toContain('Reuniao de fechamento');
    expect(titulos[3]).toContain('Primeiro contato');
  });

  it('não agrupa mais por situação', async () => {
    /*
      O agrupamento em blocos foi o que fez a tela parecer lista de caixas.
      A sequência agora é contada pelo traço, não por cabeçalho.
    */
    montar();
    await screen.findByText('Ligar de novo');
    expect(screen.queryByRole('region', { name: 'Atrasadas' })).not.toBeInTheDocument();
    expect(screen.queryByRole('region', { name: 'Concluídas' })).not.toBeInTheDocument();
  });

  it('cada tarefa é um item da linha do tempo', async () => {
    montar();
    await screen.findByText('Ligar de novo');
    expect(screen.getByRole('list', { name: 'Linha do tempo das tarefas' }))
      .toBeInTheDocument();
    expect(screen.getAllByRole('listitem')).toHaveLength(4);
  });

  it('a linha diz o tipo e a situação em palavra, não só em cor', async () => {
    /* Daltônico não vê tom. */
    montar();
    await screen.findByText('Ligar de novo');
    expect(screen.getByText('WhatsApp')).toBeInTheDocument();
    expect(screen.getByText('Atrasado')).toBeInTheDocument();
    expect(screen.getByText('concluído')).toBeInTheDocument();
  });

  it('mostra os contadores do cabeçalho', async () => {
    montar();
    expect(await screen.findByText('1 atrasada')).toBeInTheDocument();
    expect(screen.getByText('3 em aberto')).toBeInTheDocument();
    expect(screen.getByText('4 no total')).toBeInTheDocument();
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

describe('AbaTarefas — drilldown', () => {
  it('a linha fechada não mostra detalhe nem ação', async () => {
    montar();
    await screen.findByText('Ligar de novo');
    expect(screen.queryByText('Perguntar pelo numero de vidas')).not.toBeInTheDocument();
    expect(screen.queryByLabelText('Concluir Ligar de novo')).not.toBeInTheDocument();
  });

  it('clicar abre o detalhe e as ações', async () => {
    montar();
    await screen.findByText('Ligar de novo');
    fireEvent.click(linha('Ligar de novo'));
    expect(await screen.findByText('Perguntar pelo numero de vidas')).toBeInTheDocument();
    expect(screen.getByLabelText('Concluir Ligar de novo')).toBeInTheDocument();
    expect(screen.getByLabelText('Editar Ligar de novo')).toBeInTheDocument();
    expect(screen.getByLabelText('Cancelar Ligar de novo')).toBeInTheDocument();
  });

  it('clicar de novo fecha', async () => {
    montar();
    await screen.findByText('Ligar de novo');
    fireEvent.click(linha('Ligar de novo'));
    await screen.findByLabelText('Concluir Ligar de novo');
    fireEvent.click(linha('Ligar de novo'));
    await waitFor(() =>
      expect(screen.queryByLabelText('Concluir Ligar de novo')).not.toBeInTheDocument()
    );
  });

  it('só uma tarefa fica aberta por vez', async () => {
    /* Duas abertas devolveriam à tela a altura que a caixa tinha. */
    montar();
    await screen.findByText('Ligar de novo');
    fireEvent.click(linha('Ligar de novo'));
    await screen.findByLabelText('Concluir Ligar de novo');
    fireEvent.click(linha('Enviar proposta'));
    expect(await screen.findByLabelText('Concluir Enviar proposta')).toBeInTheDocument();
    expect(screen.queryByLabelText('Concluir Ligar de novo')).not.toBeInTheDocument();
  });

  it('tarefa fechada abre o detalhe mas não oferece ação', async () => {
    /* Editar tarefa fechada apagaria o histórico — o backend recusa. */
    montar();
    await screen.findByText('Primeiro contato');
    fireEvent.click(linha('Primeiro contato'));
    expect(await screen.findByText(/Atendeu, pediu proposta/)).toBeInTheDocument();
    expect(screen.queryByLabelText('Concluir Primeiro contato')).not.toBeInTheDocument();
    expect(screen.queryByLabelText('Editar Primeiro contato')).not.toBeInTheDocument();
  });

  it('marca a corrente quando a tarefa veio de outra', async () => {
    mockGet.mockImplementation(respostas({
      ...LISTA,
      itens: [tarefa('9', { titulo: 'Veio de antes', tarefa_anterior_id: '1' })],
    }));
    montar();
    await screen.findByText('Veio de antes');
    fireEvent.click(linha('Veio de antes'));
    expect(await screen.findByText(/Veio da conclusão da tarefa anterior/))
      .toBeInTheDocument();
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
  async function abrirConcluir(titulo = 'Ligar de novo') {
    montar();
    await screen.findByText(titulo);
    fireEvent.click(linha(titulo));
    fireEvent.click(await screen.findByLabelText(`Concluir ${titulo}`));
  }

  it('o painel abre já com os campos da próxima', async () => {
    await abrirConcluir();
    expect(await screen.findByLabelText('Próxima: Título')).toBeInTheDocument();
    expect(screen.getByText(/Se não há próximo passo, finalize a oportunidade/))
      .toBeInTheDocument();
  });

  it('o botão fica travado enquanto a próxima está incompleta', async () => {
    await abrirConcluir();
    await screen.findByLabelText('Próxima: Título');
    expect(screen.getByText('Concluir tarefa').closest('button')).toBeDisabled();
  });

  it('envia conclusão e próxima na mesma chamada', async () => {
    /*
      Uma chamada só porque o backend faz as duas coisas na mesma transação:
      se a próxima falhar, a conclusão não vale.
    */
    await abrirConcluir();
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
    fireEvent.click(linha('Ligar de novo'));
    fireEvent.click(await screen.findByLabelText('Concluir Ligar de novo'));
    expect(await screen.findByText(/não é preciso agendar a próxima/)).toBeInTheDocument();
    expect(screen.queryByLabelText('Próxima: Título')).not.toBeInTheDocument();
    expect(screen.getByText('Concluir tarefa').closest('button')).not.toBeDisabled();
  });

  it('finalizada envia proxima nula', async () => {
    montar({ oportunidade: { ...OPP, status: 'perdido' } });
    await screen.findByText('Ligar de novo');
    fireEvent.click(linha('Ligar de novo'));
    fireEvent.click(await screen.findByLabelText('Concluir Ligar de novo'));
    fireEvent.click(await screen.findByText('Concluir tarefa'));
    await waitFor(() => expect(mockPost).toHaveBeenCalled());
    expect(mockPost.mock.calls[0][1].proxima).toBeNull();
  });

  it('suspensa continua exigindo a próxima', async () => {
    /* Pausa sem data para voltar é como oportunidade morre em silêncio. */
    montar({ oportunidade: { ...OPP, status: 'suspensa' } });
    await screen.findByText('Ligar de novo');
    fireEvent.click(linha('Ligar de novo'));
    fireEvent.click(await screen.findByLabelText('Concluir Ligar de novo'));
    expect(await screen.findByLabelText('Próxima: Título')).toBeInTheDocument();
  });

  it('o 422 do backend aparece na tela', async () => {
    mockPost.mockRejectedValue({
      response: { data: { detail: 'Concluir exige agendar a próxima tarefa.' } },
    });
    await abrirConcluir();
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
    fireEvent.click(linha('Ligar de novo'));
    fireEvent.click(await screen.findByLabelText('Cancelar Ligar de novo'));
    expect(await screen.findByLabelText('Motivo do cancelamento (opcional)'))
      .toBeInTheDocument();
    expect(screen.queryByLabelText('Próxima: Título')).not.toBeInTheDocument();
  });

  it('envia o motivo do cancelamento', async () => {
    montar();
    await screen.findByText('Ligar de novo');
    fireEvent.click(linha('Ligar de novo'));
    fireEvent.click(await screen.findByLabelText('Cancelar Ligar de novo'));
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
    fireEvent.click(linha('Ligar de novo'));
    fireEvent.click(await screen.findByLabelText('Editar Ligar de novo'));
    expect(await screen.findByLabelText('Título')).toHaveValue('Ligar de novo');
  });

  it('salvar edição chama PATCH', async () => {
    montar();
    await screen.findByText('Ligar de novo');
    fireEvent.click(linha('Ligar de novo'));
    fireEvent.click(await screen.findByLabelText('Editar Ligar de novo'));
    fireEvent.change(await screen.findByLabelText('Título'), {
      target: { value: 'Ligar amanhã' },
    });
    fireEvent.click(screen.getByText('Salvar tarefa'));
    await waitFor(() => expect(mockPatch).toHaveBeenCalled());
    expect(mockPatch.mock.calls[0][0]).toBe('/crm/tarefas/1');
    expect(mockPatch.mock.calls[0][1].titulo).toBe('Ligar amanhã');
  });
});
