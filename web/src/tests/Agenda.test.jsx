// web/src/tests/Agenda.test.jsx
//
// A grade semanal. Cinco promessas que estes testes seguram:
//
//   1. desenha os cinco dias e os dezoito slots, com o almoço como SALTO
//   2. a reunião cai na linha do slot dela — inclusive a de horário
//      específico, que ancora na linha anterior e mostra a hora real
//   3. clicar no VAZIO é a ação principal, e leva o dia e a hora prontos
//   4. o que não cabe na grade (almoço, fora do expediente) aparece numa
//      faixa própria em vez de sumir
//   5. os números do topo saem da MESMA resposta que a lista
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, fireEvent, cleanup, waitFor } from '@testing-library/react';

const mockGet = vi.fn();
const mockPost = vi.fn();
const mockPatch = vi.fn();
const mockGetUser = vi.fn(() => ({ id: 'u1', nome: 'Jakeline Santana' }));

vi.mock('../api', () => ({
  default: {
    get: (...a) => mockGet(...a),
    post: (...a) => mockPost(...a),
    patch: (...a) => mockPatch(...a),
  },
  getUser: (...a) => mockGetUser(...a),
}));

import Agenda from '../pages/crm/Agenda';
import { alvoPadraoDoCargo } from '../components/crm/agendaComum';

// Semana de 07 a 11 de setembro de 2026 (segunda a sexta).
const SLOTS = [
  '08:00', '08:30', '09:00', '09:30', '10:00', '10:30', '11:00', '11:30',
  '13:00', '13:30', '14:00', '14:30', '15:00', '15:30', '16:00', '16:30',
  '17:00', '17:30',
];

function reuniao(id, extra = {}) {
  return {
    id,
    tarefa_id: `t-${id}`,
    inicio: '2026-09-08T12:00:00Z',   // 09:00 em Brasília
    fim: '2026-09-08T12:30:00Z',
    duracao_min: 30,
    slot: '09:00',
    fora_da_grade: false,
    rotulo: 'CF - XPTO (Bruno) - ON',
    tipo_id: 1, tipo_sigla: 'CF', tipo_nome: 'Fechamento',
    modalidade: 'online', modalidade_rotulo: 'Online',
    endereco: null, link_video: null,
    anfitriao_id: 'u1', anfitriao_nome: 'Jakeline Santana',
    participantes: [],
    contato_id: null, contato_nome: null, contato_email: null,
    convidados: [],
    titulo: 'Fechamento com o RH', descricao: null,
    situacao: 'futura', concluida_em: null, cancelada_em: null,
    oportunidade_id: 'o1', oportunidade_numero: 'OPP-2026-00001',
    status_oportunidade: 'ativa',
    conta_id: 'c1', conta_razao_social: 'XPTO LTDA',
    convite_titulo: 'XPTO LTDA 11.222.333/0001-81 | Fechamento Controller MedSeg',
    convite_descricao: 'XPTO LTDA ...',
    google_event_id: 'evt-1', google_link: 'https://meet.google.com/abc',
    google_sincronizado_em: '2026-09-01T12:00:00Z', google_erro: null,
    observacoes: null, criado_em: '2026-09-01T12:00:00Z',
    agendado_por: 'u2', agendado_por_nome: 'Bruno Gonçalo',
    desfecho: null, desfecho_efetivo: null, desfecho_rotulo: null,
    desfecho_em: null, desfecho_por_nome: null, desfecho_observacao: null,
    desfecho_antecedencia_horas: null,
    desfecho_sugerido: 'cancelada', pendente_de_desfecho: false,
    ...extra,
  };
}

function dia(data, dia_semana) {
  return {
    data, dia_semana, nao_util: false, motivo: null,
    reunioes: [], slots_ocultos: [],
  };
}

function semana(extra = {}) {
  const dias = [
    dia('2026-09-07', 'seg'),
    dia('2026-09-08', 'ter'),
    dia('2026-09-09', 'qua'),
    dia('2026-09-10', 'qui'),
    dia('2026-09-11', 'sex'),
  ];
  return {
    inicio: '2026-09-07', fim: '2026-09-11',
    anfitriao_id: 'u1', anfitriao_nome: 'Jakeline Santana',
    slots: SLOTS,
    dias,
    total: 0, concluidas: 0, canceladas: 0, pendentes: 0,
    livres: 90, nao_sincronizadas: 0,
    google_configurado: true,
    alvo: null, ocultas: 0,
    ...extra,
  };
}

const USUARIOS = [
  { id: 'u1', nome: 'Jakeline Santana', cargo: 'EV' },
  { id: 'u2', nome: 'Bruno Gonçalo', cargo: 'EV' },
];

function responder(corpo) {
  mockGet.mockImplementation((url) => {
    if (url === '/crm/agenda/semana') return Promise.resolve({ data: corpo });
    if (url === '/crm/dominio/usuarios') return Promise.resolve({ data: USUARIOS });
    if (url === '/crm/agenda/tipos') return Promise.resolve({ data: [] });
    if (url === '/crm/contatos') return Promise.resolve({ data: { itens: [] } });
    return Promise.resolve({ data: {} });
  });
}

beforeEach(() => {
  mockGet.mockReset();
  mockPost.mockReset();
  mockPatch.mockReset();
  mockGetUser.mockReturnValue({ id: 'u1', nome: 'Jakeline Santana' });
  responder(semana());
});

afterEach(cleanup);

async function renderizar() {
  render(<Agenda />);
  await screen.findByText('07 a 11/set');
}

// ── A grade ──────────────────────────────────────────────────────────

describe('Agenda — a grade', () => {
  it('desenha os cinco dias, de segunda a sexta', async () => {
    await renderizar();
    for (const dia of ['seg', 'ter', 'qua', 'qui', 'sex']) {
      expect(screen.getByText(dia)).toBeInTheDocument();
    }
    expect(screen.queryByText('sáb')).not.toBeInTheDocument();
    expect(screen.queryByText('dom')).not.toBeInTheDocument();
  });

  it('desenha os dezoito slots, das 8h às 17h30', async () => {
    await renderizar();
    expect(screen.getByText('08:00')).toBeInTheDocument();
    expect(screen.getByText('17:30')).toBeInTheDocument();
    expect(screen.getByText('11:30')).toBeInTheDocument();
    expect(screen.getByText('13:00')).toBeInTheDocument();
  });

  it('o almoço não é linha da grade', async () => {
    /*
      É ausência de slot, não slot vazio: uma faixa de células cinzas
      gastaria a altura de três reuniões dizendo que ninguém trabalha ali.
    */
    await renderizar();
    expect(screen.queryByText('12:00')).not.toBeInTheDocument();
    expect(screen.queryByText('12:30')).not.toBeInTheDocument();
  });

  it('mostra a data de cada coluna', async () => {
    await renderizar();
    expect(screen.getByText('07/set')).toBeInTheDocument();
    expect(screen.getByText('11/set')).toBeInTheDocument();
  });
});

// ── As reuniões ──────────────────────────────────────────────────────

describe('Agenda — as reuniões', () => {
  it('mostra o rótulo da reunião no cartão', async () => {
    responder(semana({
      total: 1,
      dias: semana().dias.map((d) => (
        d.dia_semana === 'ter' ? { ...d, reunioes: [reuniao('r1')] } : d
      )),
    }));
    await renderizar();
    expect(screen.getByText('CF - XPTO (Bruno) - ON')).toBeInTheDocument();
  });

  it('não repete a hora quando ela bate com a linha', async () => {
    /*
      Repeti-la em toda célula gastaria metade da largura do cartão dizendo
      o que a coluna da esquerda já diz.
    */
    responder(semana({
      total: 1,
      dias: semana().dias.map((d) => (
        d.dia_semana === 'ter' ? { ...d, reunioes: [reuniao('r1')] } : d
      )),
    }));
    await renderizar();
    const cartao = screen.getByTitle('CF - XPTO (Bruno) - ON');
    expect(cartao.textContent).not.toContain('09:00');
  });

  it('mostra a hora real quando a reunião está fora do slot', async () => {
    /*
      "O SDR pode editar para um horário mais específico." A reunião é
      desenhada na linha do slot que a contém, e a hora exata vai no cartão
      — senão a grade mentiria sobre quando ela começa.
    */
    responder(semana({
      total: 1,
      dias: semana().dias.map((d) => (
        d.dia_semana === 'ter'
          ? { ...d, reunioes: [reuniao('r1', {
              inicio: '2026-09-08T12:15:00Z', fora_da_grade: true, slot: '09:00',
            })] }
          : d
      )),
    }));
    await renderizar();
    const cartao = screen.getByTitle('CF - XPTO (Bruno) - ON');
    expect(cartao.textContent).toContain('09:15');
  });

  it('o que não cabe na grade aparece numa faixa própria', async () => {
    /*
      Reunião invisível é pior que reunião fora do lugar: quem não a vê,
      marca por cima.
    */
    responder(semana({
      total: 1,
      dias: semana().dias.map((d) => (
        d.dia_semana === 'ter'
          ? { ...d, reunioes: [reuniao('r1', {
              inicio: '2026-09-08T15:10:00Z', slot: null, fora_da_grade: true,
              rotulo: 'CF - Almoco (Bruno) - PRES',
            })] }
          : d
      )),
    }));
    await renderizar();
    expect(screen.getByText('Fora da grade:')).toBeInTheDocument();
    expect(screen.getByTitle('CF - Almoco (Bruno) - PRES')).toBeInTheDocument();
  });

  it('marca a reunião cujo convite não saiu', async () => {
    responder(semana({
      total: 1, nao_sincronizadas: 1,
      dias: semana().dias.map((d) => (
        d.dia_semana === 'ter'
          ? { ...d, reunioes: [reuniao('r1', {
              google_event_id: null, google_erro: 'O Google recusou o acesso.',
            })] }
          : d
      )),
    }));
    await renderizar();
    expect(screen.getByLabelText('convite não enviado')).toBeInTheDocument();
    expect(screen.getByText('1 sem convite')).toBeInTheDocument();
  });

  it('abre o detalhe ao clicar no cartão', async () => {
    responder(semana({
      total: 1,
      dias: semana().dias.map((d) => (
        d.dia_semana === 'ter' ? { ...d, reunioes: [reuniao('r1')] } : d
      )),
    }));
    await renderizar();
    fireEvent.click(screen.getByTitle('CF - XPTO (Bruno) - ON'));
    expect(await screen.findByRole('dialog')).toBeInTheDocument();
    expect(screen.getByText('XPTO LTDA')).toBeInTheDocument();
  });
});

// ── Clicar no vazio ──────────────────────────────────────────────────

describe('Agenda — marcar clicando no horário livre', () => {
  it('cada célula livre é um botão que diz o dia e a hora', async () => {
    /*
      A ação principal da tela é apontar o buraco. Um "Nova reunião" no
      topo pedindo dia e hora num formulário trocaria um gesto por três
      campos.
    */
    await renderizar();
    expect(
      screen.getByLabelText('Marcar reunião em 09/set às 14:00')
    ).toBeInTheDocument();
  });

  it('abre o formulário com a data e a hora prontas', async () => {
    await renderizar();
    fireEvent.click(screen.getByLabelText('Marcar reunião em 09/set às 14:00'));
    const dialog = await screen.findByRole('dialog');
    expect(dialog).toBeInTheDocument();
    const campo = screen.getByLabelText('Data e hora');
    expect(campo.value).toBe('2026-09-09T14:00');
  });

  it('na visão da equipe também dá para marcar', async () => {
    /*
      Quem abre a grade da equipe é o SDR, e ele abre justamente para achar
      onde cabe a reunião do EV. Trancar o clique ali mandava trocar de
      agenda antes de marcar — e a visão que mostra o buraco não era a que
      deixava tapá-lo.
    */
    mockGetUser.mockReturnValue(null);
    responder(semana({ anfitriao_id: null, anfitriao_nome: null, livres: null }));
    await renderizar();
    fireEvent.click(screen.getByLabelText('Marcar reunião em 09/set às 14:00'));
    expect(await screen.findByRole('dialog')).toBeInTheDocument();
    expect(screen.getByLabelText('Data e hora').value).toBe('2026-09-09T14:00');
  });

  it('sem anfitrião escolhido, o formulário abre vazio e travado', async () => {
    /*
      A trava saiu da grade e ficou no formulário, que é onde ela cabe: o
      dono da reunião é uma pergunta do formulário, não uma condição para
      abri-lo.
    */
    mockGetUser.mockReturnValue(null);
    responder(semana({ anfitriao_id: null, anfitriao_nome: null, livres: null }));
    await renderizar();
    fireEvent.click(screen.getByLabelText('Marcar reunião em 09/set às 14:00'));
    await screen.findByRole('dialog');
    expect(screen.getByLabelText('Anfitrião').value).toBe('');
    expect(
      screen.getByText('Marcar e enviar convite').closest('button')
    ).toBeDisabled();
  });

  it('avisa que a grade da equipe é a mesma para todo mundo', async () => {
    mockGetUser.mockReturnValue(null);
    responder(semana({ anfitriao_id: null, anfitriao_nome: null, livres: null }));
    await renderizar();
    expect(
      screen.getByText(/aparece ocupado aqui para todo mundo/)
    ).toBeInTheDocument();
  });
});

// ── Rastreio: quem marcou e o que aconteceu ──────────────────────────

describe('Agenda — rastreio', () => {
  it('filtra por quem marcou, sem mexer no filtro de anfitrião', async () => {
    /*
      "As reuniões que EU marquei para o Bruno" precisa dos dois filtros ao
      mesmo tempo. Um seletor só obrigaria a escolher qual das duas visões
      existe — e o SDR perderia a única que mostra o trabalho dele.
    */
    await renderizar();
    fireEvent.change(screen.getByLabelText('Agendado por'), {
      target: { value: 'u2' },
    });
    await waitFor(() => {
      const ultima = mockGet.mock.calls
        .filter((c) => c[0] === '/crm/agenda/semana').at(-1);
      expect(ultima[1].params.agendado_por).toBe('u2');
      expect(ultima[1].params.anfitriao_id).toBe('u1');
    });
  });

  it('cobra as reuniões que passaram sem desfecho', async () => {
    /*
      A contrapartida de não adivinhar: sem um número visível cobrando, a
      reunião esquecida sairia de toda estatística em silêncio.
    */
    responder(semana({ pendentes: 3 }));
    await renderizar();
    expect(await screen.findByText('Sem desfecho')).toBeInTheDocument();
    expect(screen.getByText('3')).toBeInTheDocument();
  });

  it('sem pendências, o contador não aparece', async () => {
    await renderizar();
    expect(screen.queryByText('Sem desfecho')).not.toBeInTheDocument();
  });

  it('marca o cartão pendente com borda tracejada', async () => {
    const s = semana();
    s.dias[1].reunioes = [reuniao('r1', {
      situacao: 'atrasada', pendente_de_desfecho: true,
      desfecho_sugerido: 'realizada',
    })];
    responder(s);
    await renderizar();
    const cartao = (await screen.findByTitle(/falta registrar o que aconteceu/));
    expect(cartao.className).toContain('border-dashed');
  });

  it('o no-show não some junto com a cancelada', async () => {
    /*
      Riscado e cinza igual à cancelada, os dois somem juntos da leitura da
      grade — e é justamente o no-show que precisa saltar aos olhos.
    */
    const s = semana();
    s.dias[1].reunioes = [reuniao('r1', {
      situacao: 'cancelada', cancelada_em: '2026-09-08T13:00:00Z',
      desfecho: 'no_show', desfecho_efetivo: 'no_show',
      desfecho_rotulo: 'No-show', desfecho_sugerido: null,
    })];
    responder(s);
    await renderizar();
    const cartao = await screen.findByTitle(/No-show/);
    expect(cartao.className).toContain('text-hipo-danger');
    expect(cartao.className).not.toContain('line-through');
  });

  it('abre a produtividade da semana que está na tela', async () => {
    /*
      Um seletor de período próprio faria o número aberto discordar da
      grade atrás dele.
    */
    await renderizar();
    fireEvent.click(screen.getByLabelText('Produtividade da agenda'));
    await waitFor(() => {
      const chamada = mockGet.mock.calls
        .find((c) => c[0] === '/crm/agenda/produtividade');
      expect(chamada[1].params).toEqual({ de: '2026-09-07', ate: '2026-09-11' });
    });
  });
});

// ── Os números do topo ───────────────────────────────────────────────

describe('Agenda — os agregados', () => {
  it('mostra marcadas e slots livres', async () => {
    responder(semana({ total: 3, livres: 87 }));
    await renderizar();
    expect(screen.getByText('Marcadas')).toBeInTheDocument();
    expect(screen.getByText('3')).toBeInTheDocument();
    expect(screen.getByText('Slots livres')).toBeInTheDocument();
    expect(screen.getByText('87')).toBeInTheDocument();
  });

  it('esconde "slots livres" quando não há uma agenda escolhida', async () => {
    /*
      Somar os slots vagos de cinco pessoas produziria um número que não
      responde à pergunta de ninguém. O backend devolve null, e a tela some
      com o KPI em vez de mostrar um traço sem explicação.
    */
    mockGetUser.mockReturnValue(null);
    responder(semana({ livres: null }));
    await renderizar();
    expect(screen.queryByText('Slots livres')).not.toBeInTheDocument();
  });

  it('avisa quando a integração com o Google não está configurada', async () => {
    responder(semana({ google_configurado: false }));
    await renderizar();
    expect(
      screen.getByText(/os convites não são enviados/)
    ).toBeInTheDocument();
  });
});

// ── Feriado ──────────────────────────────────────────────────────────

describe('Agenda — feriado', () => {
  it('pinta o dia e mostra o motivo, sem bloquear', async () => {
    /*
      O calendário de dias não úteis é mantido à mão e pode estar
      desatualizado; recusar com base nele transformaria uma tabela
      esquecida em erro para o usuário.
    */
    responder(semana({
      dias: semana().dias.map((d) => (
        d.dia_semana === 'qua'
          ? { ...d, nao_util: true, motivo: 'Feriado municipal' }
          : d
      )),
      livres: 72,
    }));
    await renderizar();
    expect(screen.getByText('Feriado municipal')).toBeInTheDocument();
    expect(
      screen.getByLabelText('Marcar reunião em 09/set às 14:00')
    ).not.toBeDisabled();
  });
});

// ── Navegação e filtro ───────────────────────────────────────────────

describe('Agenda — navegação', () => {
  it('abre na agenda de quem entrou', async () => {
    /*
      Aberta em "todos", a grade da equipe empilha reuniões no mesmo slot e
      nenhum buraco é confiável — a tela deixaria de responder "onde cabe a
      próxima".
    */
    await renderizar();
    await waitFor(() => {
      const chamada = mockGet.mock.calls.find((c) => c[0] === '/crm/agenda/semana');
      expect(chamada[1].params.anfitriao_id).toBe('u1');
    });
  });

  it('marca o usuário logado como "(você)" no seletor', async () => {
    await renderizar();
    expect(await screen.findByText('Jakeline Santana (você)')).toBeInTheDocument();
  });

  it('a seta avança uma semana', async () => {
    await renderizar();
    mockGet.mockClear();
    fireEvent.click(screen.getByLabelText('Próxima semana'));
    await waitFor(() => {
      const chamadas = mockGet.mock.calls.filter((c) => c[0] === '/crm/agenda/semana');
      expect(chamadas.length).toBeGreaterThan(0);
    });
  });

  it('trocar de pessoa recarrega a grade daquela pessoa', async () => {
    await renderizar();
    mockGet.mockClear();
    fireEvent.change(screen.getByLabelText('Agenda de'), {
      target: { value: 'u2' },
    });
    await waitFor(() => {
      const chamada = mockGet.mock.calls.find((c) => c[0] === '/crm/agenda/semana');
      expect(chamada[1].params.anfitriao_id).toBe('u2');
    });
  });

  it('mostra o erro quando a carga falha', async () => {
    mockGet.mockImplementation((url) => {
      if (url === '/crm/agenda/semana') {
        return Promise.reject({ response: { data: { detail: 'banco fora' } } });
      }
      return Promise.resolve({ data: [] });
    });
    render(<Agenda />);
    expect(await screen.findByText('banco fora')).toBeInTheDocument();
  });
});


// ── O filtro de assunto ──────────────────────────────────────────────
//
// Duas carteiras na mesma grade: a de parceiros (do EC) e a de
// oportunidades (do SDR e do EV). Três promessas:
//
//   1. a tela abre no assunto do CARGO, sem ninguém clicar
//   2. o botão ativo desliga no segundo clique, e aí vem a semana inteira
//   3. o que o filtro esconde continua OCUPANDO o horário — a célula não
//      vira buraco clicável

describe('Agenda — filtro de assunto', () => {
  function ultimaChamada() {
    return mockGet.mock.calls
      .filter((c) => c[0] === '/crm/agenda/semana').at(-1);
  }

  it('o EC abre a agenda em Parceiros', async () => {
    mockGetUser.mockReturnValue({ id: 'u1', nome: 'Aline Martins', cargo: 'EC' });
    await renderizar();
    expect(screen.getByRole('button', { name: 'Parceiros' }))
      .toHaveAttribute('aria-pressed', 'true');
    await waitFor(() => expect(ultimaChamada()[1].params.alvo).toBe('parceiro'));
  });

  it('o EV abre a agenda em Oportunidades', async () => {
    mockGetUser.mockReturnValue({ id: 'u1', nome: 'Jakeline Santana', cargo: 'EV' });
    await renderizar();
    expect(screen.getByRole('button', { name: 'Oportunidades' }))
      .toHaveAttribute('aria-pressed', 'true');
    await waitFor(() => expect(ultimaChamada()[1].params.alvo).toBe('oportunidade'));
  });

  it('o franqueado também abre em Oportunidades', async () => {
    /*
      Ele TEM o módulo de parceiros, mas quando abre a agenda a pergunta é
      a da operação comercial. Foi essa a decisão.
    */
    mockGetUser.mockReturnValue({ id: 'u1', nome: 'Tulio', cargo: 'Franqueado' });
    await renderizar();
    await waitFor(() => expect(ultimaChamada()[1].params.alvo).toBe('oportunidade'));
  });

  it('clicar no botão ativo desliga o filtro e traz a semana inteira', async () => {
    /*
      É por isso que são dois toggles e não um seletor de três opções:
      "sem filtro" não é uma terceira carteira, é nenhum dos dois ligado.
    */
    mockGetUser.mockReturnValue({ id: 'u1', nome: 'Aline', cargo: 'EC' });
    await renderizar();
    fireEvent.click(screen.getByRole('button', { name: 'Parceiros' }));
    await waitFor(() => expect(ultimaChamada()[1].params.alvo).toBeUndefined());
    expect(screen.getByRole('button', { name: 'Parceiros' }))
      .toHaveAttribute('aria-pressed', 'false');
  });

  it('clicar no outro assunto troca o recorte', async () => {
    mockGetUser.mockReturnValue({ id: 'u1', nome: 'Aline', cargo: 'EC' });
    await renderizar();
    fireEvent.click(screen.getByRole('button', { name: 'Oportunidades' }));
    await waitFor(() => expect(ultimaChamada()[1].params.alvo).toBe('oportunidade'));
  });

  it('o horário escondido pelo filtro NÃO vira buraco clicável', async () => {
    /*
      O teste que trava a decisão: esconder o cartão não desocupa o
      horário. Oferecer este slot como livre faria o EC prometer ao
      parceiro um horário em que o EV já tem cliente — e o 409 só
      apareceria depois da ligação.
    */
    const corpo = semana({ alvo: 'parceiro', ocultas: 1 });
    corpo.dias[1].slots_ocultos = ['09:00'];
    responder(corpo);
    mockGetUser.mockReturnValue({ id: 'u1', nome: 'Aline', cargo: 'EC' });
    await renderizar();
    expect(
      screen.queryByLabelText('Marcar reunião em 08/set às 09:00')
    ).not.toBeInTheDocument();
    expect(
      screen.getByLabelText('08/set às 09:00: ocupado por reunião fora do filtro')
    ).toBeInTheDocument();
    // Os outros horários continuam livres e clicáveis.
    expect(
      screen.getByLabelText('Marcar reunião em 08/set às 09:30')
    ).toBeInTheDocument();
  });

  it('diz quantas reuniões o filtro escondeu, e o número desliga o filtro', async () => {
    /*
      Filtro que esconde em silêncio é a versão educada de perder
      registro: sem este número, quem abre numa semana em que todo o
      movimento é do outro assunto lê "Marcadas: 0" e conclui que a semana
      está vazia.
    */
    responder(semana({ alvo: 'parceiro', ocultas: 3 }));
    mockGetUser.mockReturnValue({ id: 'u1', nome: 'Aline', cargo: 'EC' });
    await renderizar();
    const aviso = screen.getByText('+3 fora do filtro');
    fireEvent.click(aviso);
    await waitFor(() => expect(ultimaChamada()[1].params.alvo).toBeUndefined());
  });

  it('sem nada escondido, o aviso não aparece', async () => {
    await renderizar();
    expect(screen.queryByText(/fora do filtro/)).not.toBeInTheDocument();
  });
});

describe('alvoPadraoDoCargo', () => {
  it('EC trabalha carteira de parceiro', () => {
    expect(alvoPadraoDoCargo('EC')).toBe('parceiro');
  });

  it('os cargos de venda e a gestão abrem em oportunidades', () => {
    for (const cargo of ['SDR', 'EV', 'EP', 'ADM', 'Franqueado']) {
      expect(alvoPadraoDoCargo(cargo)).toBe('oportunidade');
    }
  });

  it('cargo ausente ou desconhecido cai no padrão, nunca em "sem filtro"', () => {
    /*
      Abrir sem filtro seria abrir na semana da operação inteira — que é
      justamente o que esta tela deixou de ser.
    */
    expect(alvoPadraoDoCargo(undefined)).toBe('oportunidade');
    expect(alvoPadraoDoCargo('Gerente')).toBe('oportunidade');
  });
});


describe('Agenda — a reunião que a pessoa acompanha', () => {
  function comUma(extra) {
    const corpo = semana({ total: 1 });
    corpo.dias[1].reunioes = [reuniao('r1', extra)];
    return corpo;
  }

  it('reunião de outro anfitrião aparece marcada como acompanhando', async () => {
    responder(comUma({
      papel_na_agenda: 'participante', anfitriao_id: 'u2', anfitriao_nome: 'Bruno Gonçalo',
    }));
    await renderizar();
    const cartao = screen.getByTitle(/acompanhando \(anfitrião: Bruno Gonçalo\)/);
    expect(cartao).toBeInTheDocument();
    expect(screen.getByLabelText('acompanhando')).toBeInTheDocument();
  });

  it('reunião da própria pessoa não ganha a marca', async () => {
    responder(comUma({ papel_na_agenda: 'anfitriao' }));
    await renderizar();
    expect(screen.getByTitle('CF - XPTO (Bruno) - ON')).toBeInTheDocument();
    expect(screen.queryByLabelText('acompanhando')).not.toBeInTheDocument();
  });
});

