// web/src/tests/ModalReuniao.test.jsx
//
// O formulário da reunião, nos três caminhos que chegam nele: slot vazio da
// grade, botão dentro da oportunidade, e cartão já existente.
//
// O que estes testes seguram:
//   1. a oportunidade só se escolhe na CRIAÇÃO — mover uma reunião de
//      negócio mudaria o alvo da tarefa por baixo
//   2. o estado do convite fica no TOPO, com saída para reenviar
//   3. reunião fechada não oferece edição nem cancelamento
//   4. convidado externo entra como chip, e o repetido não duplica
//   5. cancelar pede confirmação e avisa que o cliente será notificado
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
    participantes: [],
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

// ── Cancelar ─────────────────────────────────────────────────────────

describe('ModalReuniao — cancelar', () => {
  it('pede confirmação antes de cancelar', async () => {
    await abrir({ reuniao: reuniao() });
    fireEvent.click(screen.getByText('Cancelar reunião'));
    expect(
      await screen.findByText(/O evento sai da agenda de todo mundo/)
    ).toBeInTheDocument();
  });

  it('manda o motivo na rota de cancelamento', async () => {
    mockPost.mockResolvedValue({ data: reuniao({ situacao: 'cancelada' }) });
    await abrir({ reuniao: reuniao() });
    fireEvent.click(screen.getByText('Cancelar reunião'));
    fireEvent.change(
      await screen.findByLabelText('Motivo do cancelamento (opcional)'),
      { target: { value: 'cliente remarcou' } }
    );
    fireEvent.click(screen.getAllByText('Cancelar reunião').at(-1));
    await waitFor(() => expect(mockPost).toHaveBeenCalledWith(
      '/crm/agenda/reunioes/r1/cancelar', { motivo: 'cliente remarcou' }
    ));
  });
});

// ── Reunião fechada ──────────────────────────────────────────────────

describe('ModalReuniao — reunião fechada', () => {
  it('não oferece salvar nem cancelar', async () => {
    /*
      Reescrever o horário de uma reunião que já aconteceu apagaria o
      histórico que a linha do tempo existe para mostrar. Mostrar o botão
      seria mentira: o backend recusa com 422.
    */
    await abrir({ reuniao: reuniao({ situacao: 'concluida', concluida_em: '2026-09-08T13:00:00Z' }) });
    expect(screen.queryByText('Salvar reunião')).not.toBeInTheDocument();
    expect(screen.queryByText('Cancelar reunião')).not.toBeInTheDocument();
    expect(screen.getByText(/O histórico é imutável/)).toBeInTheDocument();
  });

  it('trava os campos', async () => {
    await abrir({ reuniao: reuniao({ situacao: 'cancelada', cancelada_em: '2026-09-08T13:00:00Z' }) });
    expect(screen.getByLabelText('Data e hora')).toBeDisabled();
    expect(screen.getByLabelText('Duração')).toBeDisabled();
  });
});
