// web/src/tests/ModalReuniao.test.jsx
//
// O formulário da reunião, nos três caminhos que chegam nele: slot vazio da
// grade, botão dentro da oportunidade, e cartão já existente.
//
// O que estes testes seguram:
//   1. a oportunidade só se escolhe na CRIAÇÃO — mover uma reunião de
//      negócio mudaria o alvo da tarefa por baixo
//   2. o estado do convite fica no TOPO, com saída para reenviar
//   3. reunião fechada não oferece edição nem novo desfecho
//   4. convidado externo entra como chip, e o repetido não duplica
//   5. o desfecho tem TRÊS respostas, a sugerida já marcada, e só
//      "Realizada" exige a próxima tarefa
//   6. "Agendado por" nasce com quem está na tela e é editável — é dele o
//      crédito do agendamento, e ele não é sempre o anfitrião
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, fireEvent, cleanup, waitFor } from '@testing-library/react';

const mockGet = vi.fn();
const mockPost = vi.fn();
const mockPatch = vi.fn();

vi.mock('../api', () => ({
  default: {
    get: (...a) => mockGet(...a),
    post: (...a) => mockPost(...a),
    patch: (...a) => mockPatch(...a),
  },
  // Quem está na tela: o padrão de "Agendado por" na criação.
  getUser: () => ({ id: 'u2', nome: 'Bruno Gonçalo', cargo: 'SDR' }),
}));

import ModalReuniao from '../components/crm/ModalReuniao';

const USUARIOS = [
  { id: 'u1', nome: 'Jakeline Santana', cargo: 'EV' },
  { id: 'u2', nome: 'Bruno Gonçalo', cargo: 'EV' },
];

const TIPOS = [
  { id: 1, sigla: 'AP', nome: 'Apresentação', slug: 'apresentacao', ordem: 20, ativo: true },
  { id: 2, sigla: 'CF', nome: 'Fechamento', slug: 'fechamento', ordem: 30, ativo: true },
];

const CONTATOS = [
  { id: 'ct1', nome: 'Nivaldo', email: 'adm@nnredutores.com.br', telefone: '11999477607' },
];

function reuniao(extra = {}) {
  return {
    id: 'r1', tarefa_id: 't1',
    inicio: '2026-09-08T12:00:00Z', fim: '2026-09-08T12:30:00Z',
    duracao_min: 30, slot: '09:00', fora_da_grade: false,
    rotulo: 'AP - XPTO (Jakeline) - ON',
    tipo_id: 1, tipo_sigla: 'AP', tipo_nome: 'Apresentação',
    modalidade: 'online', modalidade_rotulo: 'Online',
    endereco: null, link_video: null,
    anfitriao_id: 'u1', anfitriao_nome: 'Jakeline Santana',
    agendado_por: 'u2', agendado_por_nome: 'Bruno Gonçalo',
    participantes: [],
    // Em aberto: nada registrado, e o relógio sugere. Marcada para o
    // futuro, a sugestão é "cancelada" — quem abre o formulário de uma
    // reunião que ainda não começou está desmarcando.
    desfecho: null, desfecho_efetivo: null, desfecho_rotulo: null,
    desfecho_em: null, desfecho_por_nome: null, desfecho_observacao: null,
    desfecho_antecedencia_horas: null,
    desfecho_sugerido: 'cancelada', pendente_de_desfecho: false,
    contato_id: 'ct1', contato_nome: 'Nivaldo',
    contato_email: 'adm@nnredutores.com.br',
    convidados: [],
    titulo: 'Apresentar a proposta', descricao: null,
    situacao: 'futura', concluida_em: null, cancelada_em: null,
    oportunidade_id: 'o1', oportunidade_numero: 'OPP-2026-00001',
    status_oportunidade: 'ativa',
    conta_id: 'c1', conta_razao_social: 'XPTO LTDA',
    convite_titulo: 'XPTO LTDA 11.222.333/0001-81 | Apresentação Controller MedSeg',
    convite_descricao: 'XPTO LTDA ...\n08/09 às 09:00\nONLINE',
    google_event_id: 'evt-1', google_link: 'https://meet.google.com/abc',
    google_sincronizado_em: '2026-09-01T12:00:00Z', google_erro: null,
    observacoes: null, criado_em: '2026-09-01T12:00:00Z',
    ...extra,
  };
}

const OPORTUNIDADE = {
  id: 'o1', numero: 'OPP-2026-00001',
  conta_id: 'c1', conta_razao_social: 'XPTO LTDA', contato_id: 'ct1',
};

beforeEach(() => {
  mockGet.mockReset();
  mockPost.mockReset();
  mockPatch.mockReset();
  mockGet.mockImplementation((url) => {
    if (url === '/crm/agenda/tipos') return Promise.resolve({ data: TIPOS });
    if (url === '/crm/contatos') return Promise.resolve({ data: { itens: CONTATOS } });
    return Promise.resolve({ data: [] });
  });
});

afterEach(cleanup);

/*
  Renderiza e ESPERA os dois carregamentos assíncronos do modal (tipos de
  reunião e contatos da conta) assentarem.

  Sem a espera, todo teste síncrono terminava com a promessa da API ainda
  no ar e o React avisava "update not wrapped in act". O aviso não quebra
  nada, mas enche a saída da suíte de ruído — e ruído constante é o que faz
  ninguém ler o aviso que importa.
*/
async function abrir(props = {}) {
  const r = render(
    <ModalReuniao
      aberto
      onFechar={props.onFechar || vi.fn()}
      onSalvo={props.onSalvo || vi.fn()}
      usuarios={USUARIOS}
      {...props}
    />
  );
  await screen.findByText('AP · Apresentação');
  return r;
}

// ── Criar ────────────────────────────────────────────────────────────

describe('ModalReuniao — marcar', () => {
  it('abre com o slot clicado já preenchido', async () => {
    await abrir({ slotInicial: '2026-09-09T14:00', anfitriaoInicial: 'u1' });
    expect(screen.getByLabelText('Data e hora').value).toBe('2026-09-09T14:00');
  });

  it('já vem com o anfitrião da agenda aberta', async () => {
    await abrir({ slotInicial: '2026-09-09T14:00', anfitriaoInicial: 'u2' });
    expect(screen.getByLabelText('Anfitrião').value).toBe('u2');
  });

  it('pede a oportunidade quando veio de um slot vazio', async () => {
    await abrir({ slotInicial: '2026-09-09T14:00', anfitriaoInicial: 'u1' });
    expect(screen.getByText('Oportunidade')).toBeInTheDocument();
  });

  it('não deixa marcar sem oportunidade', async () => {
    await abrir({ slotInicial: '2026-09-09T14:00', anfitriaoInicial: 'u1' });
    expect(screen.getByText('Marcar e enviar convite').closest('button')).toBeDisabled();
  });

  it('com a oportunidade presa, o botão libera', async () => {
    /*
      Quem clicou "Agendar reunião" dentro do negócio já respondeu de qual
      negócio é — perguntar de novo seria atrito puro.
    */
    await abrir({ oportunidade: OPORTUNIDADE, anfitriaoInicial: 'u1' });
    fireEvent.change(screen.getByLabelText('Data e hora'), {
      target: { value: '2026-09-09T14:00' },
    });
    await waitFor(() => {
      expect(
        screen.getByText('Marcar e enviar convite').closest('button')
      ).not.toBeDisabled();
    });
  });

  it('manda o POST com os campos da grade', async () => {
    mockPost.mockResolvedValue({ data: reuniao() });
    const onSalvo = vi.fn();
    await abrir({ oportunidade: OPORTUNIDADE, anfitriaoInicial: 'u1', onSalvo });
    fireEvent.change(screen.getByLabelText('Data e hora'), {
      target: { value: '2026-09-09T14:00' },
    });
    fireEvent.change(screen.getByLabelText('Duração'), { target: { value: '60' } });
    fireEvent.click(screen.getByText('Marcar e enviar convite'));
    await waitFor(() => expect(mockPost).toHaveBeenCalled());
    const [url, corpo] = mockPost.mock.calls[0];
    expect(url).toBe('/crm/agenda/reunioes');
    expect(corpo.oportunidade_id).toBe('o1');
    expect(corpo.duracao_min).toBe(60);
    expect(corpo.anfitriao_id).toBe('u1');
    expect(onSalvo).toHaveBeenCalled();
  });

  it('mostra o erro do servidor sem fechar o formulário', async () => {
    /*
      Fechar num erro jogaria fora tudo o que o usuário digitou — o mesmo
      cuidado dos painéis de tarefa.
    */
    mockPost.mockRejectedValue({
      response: { data: { detail: 'Esse horário já está ocupado: “Fechamento”.' } },
    });
    const onFechar = vi.fn();
    await abrir({ oportunidade: OPORTUNIDADE, anfitriaoInicial: 'u1', onFechar });
    fireEvent.change(screen.getByLabelText('Data e hora'), {
      target: { value: '2026-09-09T14:00' },
    });
    fireEvent.click(screen.getByText('Marcar e enviar convite'));
    expect(await screen.findByText(/já está ocupado/)).toBeInTheDocument();
    expect(onFechar).not.toHaveBeenCalled();
  });
});

// ── Editar ───────────────────────────────────────────────────────────

describe('ModalReuniao — editar', () => {
  it('não oferece trocar a oportunidade', async () => {
    /*
      Mover uma reunião de negócio mudaria o alvo da tarefa por baixo, e com
      ele a linha do tempo e a métrica de duas oportunidades ao mesmo tempo.
      Quem errou cancela e marca de novo.
    */
    await abrir({ reuniao: reuniao() });
    expect(screen.queryByText('Oportunidade')).not.toBeInTheDocument();
  });

  it('carrega os valores da reunião', async () => {
    await abrir({ reuniao: reuniao({ duracao_min: 90, modalidade: 'presencial' }) });
    expect(screen.getByLabelText('Duração').value).toBe('90');
    expect(screen.getByLabelText('Modalidade').value).toBe('presencial');
    expect(screen.getByLabelText('Anfitrião').value).toBe('u1');
  });

  it('manda PATCH e não POST', async () => {
    mockPatch.mockResolvedValue({ data: reuniao({ duracao_min: 60 }) });
    await abrir({ reuniao: reuniao() });
    fireEvent.change(screen.getByLabelText('Duração'), { target: { value: '60' } });
    fireEvent.click(screen.getByText('Salvar reunião'));
    await waitFor(() => expect(mockPatch).toHaveBeenCalled());
    expect(mockPatch.mock.calls[0][0]).toBe('/crm/agenda/reunioes/r1');
    expect(mockPost).not.toHaveBeenCalled();
  });

  it('marca a reunião fora da grade', async () => {
    await abrir({ reuniao: reuniao({ fora_da_grade: true, slot: '09:00' }) });
    expect(screen.getByText('fora da grade')).toBeInTheDocument();
  });
});

// ── O convite ────────────────────────────────────────────────────────

describe('ModalReuniao — o estado do convite', () => {
  it('diz que o convite saiu, com link para a agenda', async () => {
    await abrir({ reuniao: reuniao() });
    expect(screen.getByText(/Convite enviado/)).toBeInTheDocument();
    expect(screen.getByText('abrir').closest('a')).toHaveAttribute(
      'href', 'https://meet.google.com/abc'
    );
  });

  it('mostra o erro e oferece tentar de novo', async () => {
    /*
      Sem a saída, uma queda momentânea do Google deixaria a reunião
      invisível para o cliente para sempre.
    */
    await abrir({
      reuniao: reuniao({
        google_event_id: null, google_link: null,
        google_erro: 'O Google recusou o acesso.',
      }),
    });
    expect(screen.getByText('O Google recusou o acesso.')).toBeInTheDocument();
    expect(screen.getByText('Tentar de novo')).toBeInTheDocument();
  });

  it('o botão de reenviar chama a rota de sincronizar', async () => {
    mockPost.mockResolvedValue({ data: reuniao() });
    await abrir({
      reuniao: reuniao({ google_event_id: null, google_erro: 'fora do ar' }),
    });
    fireEvent.click(screen.getByText('Tentar de novo'));
    await waitFor(() => expect(mockPost).toHaveBeenCalledWith(
      '/crm/agenda/reunioes/r1/sincronizar', {}
    ));
  });
});

// ── Quem recebe ──────────────────────────────────────────────────────

describe('ModalReuniao — quem recebe o convite', () => {
  it('lista os contatos da empresa com o e-mail à vista', async () => {
    await abrir({ reuniao: reuniao() });
    expect(
      await screen.findByText('Nivaldo · adm@nnredutores.com.br')
    ).toBeInTheDocument();
  });

  it('o anfitrião não aparece como participante', async () => {
    /*
      Ele é o dono da tarefa. Marcá-lo de novo criaria a pergunta "e se as
      duas discordarem?", que não tem resposta boa.
    */
    await abrir({ reuniao: reuniao({ anfitriao_id: 'u1' }) });
    const equipe = screen.getByText('Nossa equipe').parentElement;
    expect(equipe.textContent).toContain('Bruno Gonçalo');
    expect(equipe.textContent).not.toContain('Jakeline Santana');
  });

  it('convidado externo vira chip ao apertar Enter', async () => {
    await abrir({ reuniao: reuniao() });
    const campo = screen.getByLabelText('Convidados externos');
    fireEvent.change(campo, { target: { value: 'socio@xpto.com.br' } });
    fireEvent.keyDown(campo, { key: 'Enter' });
    expect(
      await screen.findByLabelText('Remover socio@xpto.com.br')
    ).toBeInTheDocument();
  });

  it('o mesmo e-mail duas vezes não duplica', async () => {
    /*
      O Google recusa o evento INTEIRO com 400 quando um endereço aparece
      repetido — o convite dos outros morre junto.
    */
    await abrir({ reuniao: reuniao({ convidados: ['socio@xpto.com.br'] }) });
    const campo = screen.getByLabelText('Convidados externos');
    fireEvent.change(campo, { target: { value: 'Socio@XPTO.com.br' } });
    fireEvent.keyDown(campo, { key: 'Enter' });
    await waitFor(() => {
      expect(screen.getAllByLabelText(/^Remover socio@xpto/i)).toHaveLength(1);
    });
  });

  it('remove o chip ao clicar nele', async () => {
    await abrir({ reuniao: reuniao({ convidados: ['socio@xpto.com.br'] }) });
    fireEvent.click(screen.getByLabelText('Remover socio@xpto.com.br'));
    await waitFor(() => {
      expect(
        screen.queryByLabelText('Remover socio@xpto.com.br')
      ).not.toBeInTheDocument();
    });
  });
});

// ── Agendado por ─────────────────────────────────────────────────────

describe('ModalReuniao — agendado por', () => {
  it('nasce com quem está na tela, não com o anfitrião', async () => {
    /*
      É a diferença que a métrica inteira depende: o SDR marca para o EV, e
      o agendamento do dia é DELE. Copiar o anfitrião aqui daria o crédito
      a quem vai receber a reunião.
    */
    await abrir({ slotInicial: '2026-09-09T14:00', anfitriaoInicial: 'u1' });
    expect(screen.getByLabelText('Anfitrião').value).toBe('u1');
    expect(screen.getByLabelText('Agendado por').value).toBe('u2');
  });

  it('vai no corpo do POST', async () => {
    mockPost.mockResolvedValue({ data: reuniao() });
    await abrir({ oportunidade: OPORTUNIDADE, anfitriaoInicial: 'u1' });
    fireEvent.change(screen.getByLabelText('Data e hora'), {
      target: { value: '2026-09-09T14:00' },
    });
    fireEvent.click(screen.getByText('Marcar e enviar convite'));
    await waitFor(() => expect(mockPost).toHaveBeenCalled());
    expect(mockPost.mock.calls[0][1].agendado_por).toBe('u2');
  });

  it('é editável — quem lançou nem sempre é quem marcou', async () => {
    mockPatch.mockResolvedValue({ data: reuniao() });
    await abrir({ reuniao: reuniao() });
    fireEvent.change(screen.getByLabelText('Agendado por'), {
      target: { value: 'u1' },
    });
    fireEvent.click(screen.getByText('Salvar reunião'));
    await waitFor(() => expect(mockPatch).toHaveBeenCalled());
    expect(mockPatch.mock.calls[0][1].agendado_por).toBe('u1');
  });

  it('carrega o que está gravado ao editar', async () => {
    await abrir({ reuniao: reuniao({ agendado_por: 'u1' }) });
    expect(screen.getByLabelText('Agendado por').value).toBe('u1');
  });
});

// ── O desfecho ───────────────────────────────────────────────────────

describe('ModalReuniao — registrar o desfecho', () => {
  it('oferece as três respostas', async () => {
    /*
      A pergunta não é "cancelo?", é "o que aconteceu?" — e ela tem três
      respostas. Com só duas, o no-show ficaria sem porta, e ele é
      justamente o número que dói.
    */
    await abrir({ reuniao: reuniao() });
    const opcoes = screen.getAllByRole('radio');
    expect(opcoes.map((o) => o.textContent.slice(0, 9))).toEqual(
      expect.arrayContaining([
        expect.stringContaining('Realizada'),
        expect.stringContaining('Cancelada'),
        expect.stringContaining('No-show'),
      ])
    );
  });

  it('já vem com a sugestão do servidor marcada', async () => {
    await abrir({ reuniao: reuniao({ desfecho_sugerido: 'no_show' }) });
    const marcado = screen.getAllByRole('radio').find(
      (o) => o.getAttribute('aria-checked') === 'true'
    );
    expect(marcado.textContent).toContain('No-show');
  });

  it('a régua das 24h aparece escrita, não como conta de cabeça', async () => {
    await abrir({ reuniao: reuniao({ desfecho_sugerido: 'cancelada' }) });
    expect(screen.getByText(/pela régua das 24h/)).toBeInTheDocument();
  });

  it('reunião que já passou sugere realizada, sem falar em régua', async () => {
    /*
      O caso mais comum: alguém fechando na sexta as reuniões da semana.
      Oferecer "avisada X antes" ali seria falar de cancelamento numa
      reunião que aconteceu.
    */
    await abrir({
      reuniao: reuniao({ situacao: 'atrasada', desfecho_sugerido: 'realizada' }),
    });
    const marcado = screen.getAllByRole('radio').find(
      (o) => o.getAttribute('aria-checked') === 'true'
    );
    expect(marcado.textContent).toContain('Realizada');
    expect(screen.queryByText(/pela régua das 24h/)).not.toBeInTheDocument();
  });

  it('realizada exige a próxima enquanto a oportunidade está viva', async () => {
    await abrir({ reuniao: reuniao({ desfecho_sugerido: 'realizada' }) });
    expect(screen.getByText(/exige a próxima/)).toBeInTheDocument();
    expect(
      screen.getByText(/^Registrar realizada$/).closest('button')
    ).toBeDisabled();
  });

  it('cancelada não exige a próxima', async () => {
    /*
      Cancelar é dizer que aquilo não ia acontecer, não que o negócio
      andou. Exigir a próxima aqui seria cobrar um passo de um funil que
      não se moveu.
    */
    await abrir({ reuniao: reuniao() });
    expect(screen.queryByText(/exige a próxima/)).not.toBeInTheDocument();
    expect(
      screen.getByText(/^Registrar cancelada$/).closest('button')
    ).not.toBeDisabled();
  });

  it('oportunidade finalizada dispensa a próxima', async () => {
    await abrir({
      reuniao: reuniao({
        desfecho_sugerido: 'realizada', status_oportunidade: 'ganha',
      }),
    });
    expect(screen.queryByText(/exige a próxima/)).not.toBeInTheDocument();
    expect(
      screen.getByText(/^Registrar realizada$/).closest('button')
    ).not.toBeDisabled();
  });

  it('manda a rota de desfecho, não a de cancelamento', async () => {
    /*
      Cancelar pela rota antiga fecharia a tarefa sem gravar desfecho: a
      reunião sairia da contagem de canceladas e de no-shows ao mesmo
      tempo — some do numerador sem sair do denominador.
    */
    mockPost.mockResolvedValue({ data: reuniao({ situacao: 'cancelada' }) });
    const onFechar = vi.fn();
    await abrir({ reuniao: reuniao(), onFechar });
    fireEvent.change(
      screen.getByLabelText('O que aconteceu (opcional)'),
      { target: { value: 'cliente remarcou' } }
    );
    fireEvent.click(screen.getByText(/^Registrar cancelada$/));
    await waitFor(() => expect(mockPost).toHaveBeenCalledWith(
      '/crm/agenda/reunioes/r1/desfecho',
      { desfecho: 'cancelada', observacao: 'cliente remarcou', proxima: null }
    ));
    expect(onFechar).toHaveBeenCalled();
  });

  it('trocar a resposta troca o que é enviado', async () => {
    mockPost.mockResolvedValue({ data: reuniao({ situacao: 'cancelada' }) });
    await abrir({ reuniao: reuniao() });
    fireEvent.click(
      screen.getAllByRole('radio').find((o) => o.textContent.includes('No-show'))
    );
    fireEvent.click(screen.getByText(/^Registrar no-show$/));
    await waitFor(() => expect(mockPost).toHaveBeenCalled());
    expect(mockPost.mock.calls[0][1].desfecho).toBe('no_show');
  });

  it('realizada manda a próxima tarefa junto', async () => {
    mockPost.mockResolvedValue({ data: reuniao({ situacao: 'concluida' }) });
    await abrir({ reuniao: reuniao({ desfecho_sugerido: 'realizada' }) });
    fireEvent.change(screen.getByLabelText('Próxima: Título'), {
      target: { value: 'Mandar a proposta' },
    });
    fireEvent.change(screen.getByLabelText('Próxima: Responsável'), {
      target: { value: 'u1' },
    });
    fireEvent.click(screen.getByText(/^Registrar realizada$/));
    await waitFor(() => expect(mockPost).toHaveBeenCalled());
    const corpo = mockPost.mock.calls[0][1];
    expect(corpo.desfecho).toBe('realizada');
    expect(corpo.proxima.titulo).toBe('Mandar a proposta');
    expect(corpo.proxima.responsavel_id).toBe('u1');
  });

  it('o erro do servidor não fecha o painel', async () => {
    mockPost.mockRejectedValue({
      response: { data: { detail: 'Esta reunião já foi registrada como Cancelada.' } },
    });
    const onFechar = vi.fn();
    await abrir({ reuniao: reuniao(), onFechar });
    fireEvent.click(screen.getByText(/^Registrar cancelada$/));
    expect(await screen.findByText(/já foi registrada/)).toBeInTheDocument();
    expect(onFechar).not.toHaveBeenCalled();
  });
});

// ── Reunião fechada ──────────────────────────────────────────────────

describe('ModalReuniao — reunião fechada', () => {
  it('não oferece salvar nem registrar de novo', async () => {
    /*
      Reescrever o horário de uma reunião que já aconteceu apagaria o
      histórico que a linha do tempo existe para mostrar. Mostrar o botão
      seria mentira: o backend recusa com 422.
    */
    await abrir({
      reuniao: reuniao({
        situacao: 'concluida', concluida_em: '2026-09-08T13:00:00Z',
        desfecho: 'realizada', desfecho_efetivo: 'realizada',
        desfecho_rotulo: 'Realizada', desfecho_em: '2026-09-08T13:00:00Z',
        desfecho_por_nome: 'Jakeline Santana', desfecho_sugerido: null,
      }),
    });
    expect(screen.queryByText('Salvar reunião')).not.toBeInTheDocument();
    expect(screen.queryByRole('radio')).not.toBeInTheDocument();
    expect(screen.getByText(/histórico é imutável/)).toBeInTheDocument();
  });

  it('mostra o desfecho registrado, com quem e quando', async () => {
    await abrir({
      reuniao: reuniao({
        situacao: 'cancelada', cancelada_em: '2026-09-08T13:00:00Z',
        desfecho: 'no_show', desfecho_efetivo: 'no_show',
        desfecho_rotulo: 'No-show', desfecho_em: '2026-09-08T13:00:00Z',
        desfecho_por_nome: 'Jakeline Santana', desfecho_sugerido: null,
        desfecho_antecedencia_horas: -1.5,
        desfecho_observacao: 'Cliente não entrou na sala.',
      }),
    });
    expect(screen.getByText('No-show')).toBeInTheDocument();
    expect(
      screen.getByText(/registrado por Jakeline Santana/)
    ).toBeInTheDocument();
    expect(screen.getByText(/depois da hora marcada/)).toBeInTheDocument();
    expect(screen.getByText('Cliente não entrou na sala.')).toBeInTheDocument();
  });

  it('diz quando o desfecho foi DEDUZIDO, e não registrado', async () => {
    /*
      Quem concluiu a tarefa pela aba de Tarefas fechou a reunião sem
      passar pela agenda. Apresentar a dedução com a mesma cara de um
      registro faria alguém defender na segunda um número que ninguém
      afirmou.
    */
    await abrir({
      reuniao: reuniao({
        situacao: 'concluida', concluida_em: '2026-09-08T13:00:00Z',
        desfecho: null, desfecho_efetivo: 'realizada',
        desfecho_rotulo: 'Realizada', desfecho_sugerido: null,
      }),
    });
    expect(screen.getByText(/deduzido do fechamento da tarefa/)).toBeInTheDocument();
  });

  it('trava os campos', async () => {
    await abrir({ reuniao: reuniao({ situacao: 'cancelada', cancelada_em: '2026-09-08T13:00:00Z' }) });
    expect(screen.getByLabelText('Data e hora')).toBeDisabled();
    expect(screen.getByLabelText('Duração')).toBeDisabled();
    expect(screen.getByLabelText('Agendado por')).toBeDisabled();
  });
});
