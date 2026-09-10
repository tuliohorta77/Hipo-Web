// web/src/tests/Tarefas.test.jsx
//
// A tela de gestão: quatro colunas com as tarefas de TODAS as oportunidades.
//
// Quatro promessas que os testes seguram:
//   1. junta tarefas de oportunidades diferentes, com o contexto no cartão
//   2. não arrasta — clicar abre o detalhe com as ações
//   3. Concluídas é só leitura; tarefa fechada não oferece ação
//   4. concluir continua exigindo a próxima quando a oportunidade está viva
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, fireEvent, cleanup, waitFor, within } from '@testing-library/react';

const mockGet = vi.fn();
const mockPost = vi.fn();
const mockPatch = vi.fn();
// Usuário logado: a tela abre filtrando o próprio responsável, e é daqui que
// ela descobre quem é. `null` reproduz a sessão sem usuário gravado.
const mockGetUser = vi.fn(() => null);

vi.mock('../api', () => ({
  default: {
    get: (...a) => mockGet(...a),
    post: (...a) => mockPost(...a),
    patch: (...a) => mockPatch(...a),
  },
  getUser: (...a) => mockGetUser(...a),
}));

import Tarefas from '../pages/crm/Tarefas';

function tarefa(id, extra = {}) {
  return {
    id,
    // `alvo` vem pronto do servidor em toda tarefa, e é ele — não o
    // status_oportunidade nulo — que diz se a tarefa é de parceiro.
    alvo: 'oportunidade',
    alvo_rotulo: 'Oportunidade',
    oportunidade_id: 'o1',
    oportunidade_numero: 'OPP-2026-00001',
    status_oportunidade: 'ativa',
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
    // Quantas OUTRAS tarefas do mesmo alvo estão em aberto. Zero = esta é a
    // última, e é só nesse caso que concluir exige a próxima.
    outras_abertas: 0,
    criado_em: '2026-08-01T12:00:00Z',
    ...extra,
  };
}

const COLUNAS = [
  {
    situacao: 'atrasada', rotulo: 'Atrasadas', quantidade: 2, somente_leitura: false,
    itens: [
      tarefa('1', { situacao: 'atrasada', titulo: 'Cobrar proposta', prazo: '2026-08-01T13:00:00Z' }),
      tarefa('2', {
        situacao: 'atrasada', titulo: 'Ligar para o socio',
        prazo: '2026-08-04T13:00:00Z',
        oportunidade_id: 'o2', oportunidade_numero: 'OPP-2026-00007',
        conta_razao_social: 'Transportadora Beta LTDA',
        responsavel_nome: 'Bruno Gonçalo',
      }),
    ],
  },
  {
    situacao: 'hoje', rotulo: 'Para hoje', quantidade: 1, somente_leitura: false,
    itens: [tarefa('3', { situacao: 'hoje', titulo: 'Enviar contrato' })],
  },
  { situacao: 'futura', rotulo: 'Futuras', quantidade: 0, somente_leitura: false, itens: [] },
  {
    situacao: 'concluida', rotulo: 'Concluídas', quantidade: 1, somente_leitura: true,
    itens: [tarefa('4', {
      situacao: 'concluida', titulo: 'Primeiro contato',
      concluida_em: '2026-08-05T16:00:00Z', resultado: 'Atendeu, pediu proposta',
    })],
  },
];

const USUARIOS = [
  { id: 'u1', nome: 'Jakeline Santana', cargo: 'EV' },
  { id: 'u2', nome: 'Bruno Gonçalo', cargo: 'EV' },
];

const TIPOS_RESUMO = [
  ['ligacao', 'Ligação'], ['reuniao', 'Reunião'], ['visita', 'Visita'],
  ['proposta', 'Proposta'], ['email', 'E-mail'], ['whatsapp', 'WhatsApp'],
  ['outro', 'Outro'],
];

const RESUMO = {
  de: '2026-08-01',
  ate: '2026-08-31',
  realizadas: 42,
  agendadas: 48,
  canceladas: 3,
  por_tipo: TIPOS_RESUMO.map(([tipo, rotulo]) => ({
    tipo, rotulo,
    realizadas: tipo === 'reuniao' ? 12 : 0,
    agendadas: tipo === 'reuniao' ? 15 : 0,
    canceladas: 0,
  })),
  por_responsavel: [
    { usuario_id: 'u1', nome: 'Jakeline Santana', realizadas: 42, agendadas: 48 },
  ],
};

function respostas(colunas = COLUNAS) {
  return (url) => {
    if (url === '/crm/tarefas/kanban') return Promise.resolve({ data: colunas });
    if (url === '/crm/dominio/usuarios') return Promise.resolve({ data: USUARIOS });
    if (url === '/crm/tarefas/resumo') return Promise.resolve({ data: RESUMO });
    if (url === '/crm/tarefas') return Promise.resolve({ data: { total: 0, abertas: 0, atrasadas: 0, itens: [] } });
    return Promise.resolve({ data: [] });
  };
}

function montar() {
  return render(<Tarefas />);
}

const coluna = (rotulo) => within(screen.getByRole('region', { name: rotulo }));

beforeEach(() => {
  mockGet.mockReset();
  mockPost.mockReset();
  mockPatch.mockReset();
  mockGetUser.mockReset();
  mockGetUser.mockReturnValue(null);
  mockGet.mockImplementation(respostas());
  mockPost.mockResolvedValue({ data: {} });
  mockPatch.mockResolvedValue({ data: {} });
});

afterEach(cleanup);

describe('Tarefas — as quatro colunas', () => {
  it('busca o kanban de tarefas', async () => {
    montar();
    await waitFor(() =>
      expect(mockGet).toHaveBeenCalledWith('/crm/tarefas/kanban', { params: {} })
    );
  });

  it('mostra as quatro colunas na ordem da urgência', async () => {
    montar();
    await screen.findByRole('region', { name: 'Atrasadas' });
    const rotulos = screen.getAllByRole('region').map((s) => s.getAttribute('aria-label'));
    expect(rotulos).toEqual(['Atrasadas', 'Para hoje', 'Futuras', 'Concluídas']);
  });

  it('não tem coluna de canceladas', async () => {
    /* Ruído para quem está medindo carga; segue na linha do tempo. */
    montar();
    await screen.findByRole('region', { name: 'Atrasadas' });
    expect(screen.queryByRole('region', { name: 'Canceladas' })).not.toBeInTheDocument();
  });

  it('junta tarefas de oportunidades diferentes', async () => {
    /* O ponto da tela: gestão olha a carga, não uma negociação. */
    montar();
    await screen.findByText('Cobrar proposta');
    const atrasadas = coluna('Atrasadas');
    expect(atrasadas.getByText('Metalurgica Alfa LTDA')).toBeInTheDocument();
    expect(atrasadas.getByText('Transportadora Beta LTDA')).toBeInTheDocument();
    expect(atrasadas.getByText('OPP-2026-00007')).toBeInTheDocument();
  });

  it('o cartão mostra o responsável — é o que a gestão está olhando', async () => {
    montar();
    await screen.findByText('Cobrar proposta');
    expect(coluna('Atrasadas').getByText('Bruno Gonçalo')).toBeInTheDocument();
  });

  it('cada coluna mostra a contagem inteira, não a dos cartões', async () => {
    montar();
    await screen.findByRole('region', { name: 'Atrasadas' });
    expect(coluna('Atrasadas').getByText('2')).toBeInTheDocument();
  });

  it('coluna vazia mostra o estado vazio', async () => {
    montar();
    await screen.findByRole('region', { name: 'Futuras' });
    expect(coluna('Futuras').getByText('Vazio')).toBeInTheDocument();
  });

  it('avisa quando há mais itens do que cartões exibidos', async () => {
    mockGet.mockImplementation(respostas(
      COLUNAS.map((c) => (c.situacao === 'atrasada' ? { ...c, quantidade: 12 } : c))
    ));
    montar();
    expect(await screen.findByText('+10 não exibidas')).toBeInTheDocument();
  });

  it('cada coluna rola por dentro; a tela não rola', async () => {
    montar();
    await screen.findByRole('region', { name: 'Atrasadas' });
    for (const r of ['Atrasadas', 'Para hoje', 'Futuras', 'Concluídas']) {
      const secao = screen.getByRole('region', { name: r });
      expect(secao.className).toContain('h-full');
      expect(secao.querySelector('ul').className).toContain('overflow-y-auto');
    }
  });

  it('mostra os contadores do topo', async () => {
    montar();
    expect(await screen.findByText('2 atrasadas')).toBeInTheDocument();
    // Em aberto soma atrasadas + hoje + futuras, e ignora concluídas.
    expect(screen.getByText('3 em aberto')).toBeInTheDocument();
  });

  it('estado vazio quando não há nada', async () => {
    mockGet.mockImplementation(respostas(
      COLUNAS.map((c) => ({ ...c, quantidade: 0, itens: [] }))
    ));
    montar();
    expect(await screen.findByText('Nenhuma tarefa agendada')).toBeInTheDocument();
  });

  it('erro da API aparece na tela', async () => {
    mockGet.mockImplementation((url) => {
      if (url === '/crm/tarefas/kanban') {
        return Promise.reject({ response: { data: { detail: 'Boom' } } });
      }
      return respostas()(url);
    });
    montar();
    expect(await screen.findByText('Boom')).toBeInTheDocument();
  });
});

// ── O recorte de quem entrou ─────────────────────────────────────────
//
// Aberta em "todos", a primeira coisa que qualquer pessoa fazia era procurar
// o próprio nome no seletor — e, enquanto não achava, lia a carga da equipe
// inteira como se fosse a dela.

describe('Tarefas — abre nas tarefas de quem entrou', () => {
  beforeEach(() => {
    mockGetUser.mockReturnValue({ id: 'u1', nome: 'Jakeline Santana', cargo: 'EV' });
  });

  it('a primeira carga já vem filtrada pelo usuário logado', async () => {
    montar();
    await waitFor(() =>
      expect(mockGet).toHaveBeenCalledWith('/crm/tarefas/kanban', {
        params: { responsavel_id: 'u1' },
      })
    );
  });

  it('o seletor mostra o próprio usuário selecionado, marcado como você', async () => {
    montar();
    await screen.findByRole('region', { name: 'Atrasadas' });
    const select = screen.getByLabelText('Responsável');
    expect(select.value).toBe('u1');
    expect(within(select).getByRole('option', { name: 'Jakeline Santana (você)' }))
      .toBeInTheDocument();
  });

  it('trocar para "Todos os responsáveis" tira o recorte', async () => {
    montar();
    await screen.findByRole('region', { name: 'Atrasadas' });
    fireEvent.change(screen.getByLabelText('Responsável'), { target: { value: '' } });
    await waitFor(() =>
      expect(mockGet).toHaveBeenCalledWith('/crm/tarefas/kanban', { params: {} })
    );
  });

  it('o agregado do mês nasce com o mesmo recorte', async () => {
    /* Número global ao lado de um kanban filtrado seriam duas respostas. */
    montar();
    await waitFor(() => {
      const ultima = mockGet.mock.calls
        .filter((c) => c[0] === '/crm/tarefas/resumo').at(-1);
      expect(ultima[1].params).toMatchObject({ responsavel_id: 'u1' });
    });
  });

  it('sem outro filtro, o botão de limpar nem aparece', async () => {
    /* O padrão da tela não é filtro a limpar. */
    montar();
    await screen.findByRole('region', { name: 'Atrasadas' });
    expect(screen.queryByLabelText('Limpar filtros')).not.toBeInTheDocument();
  });

  it('limpar devolve ao padrão — as minhas —, não a todos', async () => {
    montar();
    await screen.findByRole('region', { name: 'Atrasadas' });
    fireEvent.change(screen.getByLabelText('Responsável'), { target: { value: 'u2' } });

    fireEvent.click(await screen.findByLabelText('Limpar filtros'));
    expect(screen.getByLabelText('Responsável').value).toBe('u1');
  });

  it('o usuário logado entra no seletor mesmo se a lista de domínio falhar', async () => {
    /*
      Filtro aplicado com o seletor mostrando outra coisa faria a tela mentir
      sobre o próprio recorte.
    */
    mockGet.mockImplementation((url) => {
      if (url === '/crm/dominio/usuarios') return Promise.reject(new Error('502'));
      return respostas()(url);
    });
    montar();
    await screen.findByRole('region', { name: 'Atrasadas' });
    expect(screen.getByLabelText('Responsável').value).toBe('u1');
  });

  it('vazio das minhas oferece ver as da equipe', async () => {
    mockGet.mockImplementation(respostas(
      COLUNAS.map((c) => ({ ...c, quantidade: 0, itens: [] }))
    ));
    montar();
    expect(await screen.findByText('Nenhuma tarefa sua em aberto')).toBeInTheDocument();

    fireEvent.click(screen.getByText('Ver de todos'));
    await waitFor(() =>
      expect(mockGet).toHaveBeenCalledWith('/crm/tarefas/kanban', { params: {} })
    );
  });

  it('sessão sem usuário gravado continua abrindo em todos', async () => {
    mockGetUser.mockReturnValue(null);
    montar();
    await waitFor(() =>
      expect(mockGet).toHaveBeenCalledWith('/crm/tarefas/kanban', { params: {} })
    );
  });
});

describe('Tarefas — filtros', () => {
  it('filtra por responsável', async () => {
    montar();
    await screen.findByRole('region', { name: 'Atrasadas' });
    fireEvent.change(screen.getByLabelText('Responsável'), { target: { value: 'u2' } });
    await waitFor(() =>
      expect(mockGet).toHaveBeenCalledWith('/crm/tarefas/kanban', {
        params: { responsavel_id: 'u2' },
      })
    );
  });

  it('busca por empresa, número ou tarefa', async () => {
    montar();
    await screen.findByRole('region', { name: 'Atrasadas' });
    fireEvent.change(screen.getByLabelText('Buscar'), { target: { value: 'beta' } });
    await waitFor(() =>
      expect(mockGet).toHaveBeenCalledWith('/crm/tarefas/kanban', {
        params: { q: 'beta' },
      })
    , { timeout: 3000 });
  });

  it('não recarrega sozinha depois do debounce', async () => {
    /*
      Mesma regressão de Contas e do funil: o timer dispara na montagem com
      a busca vazia e, se trocar a identidade do estado, a tela busca tudo de
      novo e desmonta o que já estava renderizado.
    */
    montar();
    await screen.findByRole('region', { name: 'Atrasadas' });
    await new Promise((r) => setTimeout(r, 700));
    const chamadas = mockGet.mock.calls.filter(([u]) => u === '/crm/tarefas/kanban');
    expect(chamadas).toHaveLength(1);
  });
});

describe('Tarefas — o detalhe', () => {
  async function abrir(titulo = 'Cobrar proposta') {
    montar();
    await screen.findByText(titulo);
    fireEvent.click(screen.getByText(titulo).closest('button'));
    return screen.findByText('Concluir');
  }

  it('clicar no cartão abre o detalhe com as ações', async () => {
    await abrir();
    expect(screen.getByLabelText('Concluir Cobrar proposta')).toBeInTheDocument();
    expect(screen.getByLabelText('Editar Cobrar proposta')).toBeInTheDocument();
    expect(screen.getByLabelText('Cancelar Cobrar proposta')).toBeInTheDocument();
  });

  it('o detalhe diz de qual oportunidade a tarefa é', async () => {
    await abrir();
    expect(screen.getAllByText('Metalurgica Alfa LTDA').length).toBeGreaterThan(0);
  });

  it('tarefa concluída não oferece ação', async () => {
    /* Histórico é imutável — o backend recusa edição. */
    montar();
    await screen.findByText('Primeiro contato');
    fireEvent.click(screen.getByText('Primeiro contato').closest('button'));
    expect(await screen.findByText(/O histórico é imutável/)).toBeInTheDocument();
    expect(screen.queryByLabelText('Concluir Primeiro contato')).not.toBeInTheDocument();
  });

  it('concluir exige a próxima quando a oportunidade está viva', async () => {
    await abrir();
    fireEvent.click(screen.getByLabelText('Concluir Cobrar proposta'));
    expect(await screen.findByLabelText('Próxima: Título')).toBeInTheDocument();
    expect(screen.getByText('Concluir tarefa').closest('button')).toBeDisabled();
  });

  it('com outra tarefa aberta no alvo, não pede a próxima', async () => {
    /*
      A regra é do ALVO: a oportunidade nunca fica sem próximo passo. Com
      outra tarefa aberta ela não fica — e cobrar mais uma era o que fazia o
      número de abertas crescer a cada conclusão, sem nunca voltar.
    */
    mockGet.mockImplementation(respostas(
      COLUNAS.map((c) => (c.situacao === 'atrasada'
        ? { ...c, itens: [{ ...c.itens[0], outras_abertas: 1 }] }
        : c))
    ));
    await abrir();
    fireEvent.click(screen.getByLabelText('Concluir Cobrar proposta'));
    expect(
      await screen.findByText(/já tem outra tarefa em aberto/)
    ).toBeInTheDocument();
    expect(screen.queryByLabelText('Próxima: Título')).not.toBeInTheDocument();
    // E o botão libera sem preencher nada.
    expect(
      screen.getByText('Concluir tarefa').closest('button')
    ).not.toBeDisabled();
  });

  it('a frase diz QUANTAS estão abertas, para a dispensa não parecer bug', async () => {
    mockGet.mockImplementation(respostas(
      COLUNAS.map((c) => (c.situacao === 'atrasada'
        ? { ...c, itens: [{ ...c.itens[0], outras_abertas: 3 }] }
        : c))
    ));
    await abrir();
    fireEvent.click(screen.getByLabelText('Concluir Cobrar proposta'));
    expect(
      await screen.findByText(/outras 3 tarefas em aberto/)
    ).toBeInTheDocument();
  });

  it('parceiro com outra aberta também é dispensado', async () => {
    mockGet.mockImplementation(respostas(
      COLUNAS.map((c) => (c.situacao === 'atrasada'
        ? {
          ...c,
          itens: [{
            ...c.itens[0],
            alvo: 'parceiro', alvo_rotulo: 'Parceiro',
            oportunidade_id: null, oportunidade_numero: null,
            status_oportunidade: null, outras_abertas: 1,
          }],
        }
        : c))
    ));
    await abrir();
    fireEvent.click(screen.getByLabelText('Concluir Cobrar proposta'));
    expect(
      await screen.findByText(/Esta parceria já tem outra tarefa em aberto/)
    ).toBeInTheDocument();
  });

  it('oportunidade finalizada não pede a próxima', async () => {
    /*
      O status vem no payload da tarefa. Assumir "sempre exige" faria a tela
      pedir próxima tarefa para negócio já fechado.
    */
    mockGet.mockImplementation(respostas(
      COLUNAS.map((c) => (c.situacao === 'atrasada'
        ? { ...c, itens: [{ ...c.itens[0], status_oportunidade: 'conquistado' }] }
        : c))
    ));
    await abrir();
    fireEvent.click(screen.getByLabelText('Concluir Cobrar proposta'));
    expect(await screen.findByText(/não é preciso agendar a próxima/)).toBeInTheDocument();
  });

  it('tarefa de PARCEIRO exige a próxima, mesmo sem status de oportunidade', async () => {
    /*
      O bug que travou o EC: em tarefa de parceiro `status_oportunidade` chega
      nulo, e a tela olhava só para ele. Resultado — o formulário da próxima
      não abria, a tela ainda dizia "oportunidade finalizada", e o backend
      recusava a conclusão com 422. Não havia saída dentro do módulo de
      tarefas: era preciso abrir o parceiro pelo módulo de Parceiros só para
      conseguir concluir.

      Quem decide é `alvo`, não o nulo. Parceria não tem estado final que
      dispense o próximo contato.
    */
    mockGet.mockImplementation(respostas(
      COLUNAS.map((c) => (c.situacao === 'atrasada'
        ? {
          ...c,
          itens: [{
            ...c.itens[0],
            alvo: 'parceiro',
            alvo_rotulo: 'Parceiro',
            oportunidade_id: null,
            oportunidade_numero: null,
            status_oportunidade: null,
            conta_razao_social: 'Contabil Gama ME',
          }],
        }
        : c))
    ));
    await abrir();
    fireEvent.click(screen.getByLabelText('Concluir Cobrar proposta'));

    expect(await screen.findByLabelText('Próxima: Título')).toBeInTheDocument();
    expect(screen.queryByText(/não é preciso agendar a próxima/)).not.toBeInTheDocument();
  });

  it('a saída sem próxima do parceiro é cancelar, não finalizar oportunidade', async () => {
    /*
      Mandar "finalize a oportunidade" para quem está numa tarefa de parceiro
      é pedir uma ação que a tela não oferece — pior do que não explicar.
    */
    mockGet.mockImplementation(respostas(
      COLUNAS.map((c) => (c.situacao === 'atrasada'
        ? {
          ...c,
          itens: [{
            ...c.itens[0],
            alvo: 'parceiro', alvo_rotulo: 'Parceiro',
            oportunidade_id: null, oportunidade_numero: null,
            status_oportunidade: null,
          }],
        }
        : c))
    ));
    await abrir();
    fireEvent.click(screen.getByLabelText('Concluir Cobrar proposta'));
    expect(await screen.findByText(/cancele a tarefa em vez de concluir/))
      .toBeInTheDocument();
  });

  it('concluir tarefa de parceiro envia a próxima e não estoura', async () => {
    mockPost.mockResolvedValue({ data: {} });
    mockGet.mockImplementation(respostas(
      COLUNAS.map((c) => (c.situacao === 'atrasada'
        ? {
          ...c,
          itens: [{
            ...c.itens[0],
            alvo: 'parceiro', alvo_rotulo: 'Parceiro',
            oportunidade_id: null, oportunidade_numero: null,
            status_oportunidade: null,
          }],
        }
        : c))
    ));
    await abrir();
    fireEvent.click(screen.getByLabelText('Concluir Cobrar proposta'));
    fireEvent.change(await screen.findByLabelText('Próxima: Título'), {
      target: { value: 'Café com o contador' },
    });
    fireEvent.click(screen.getByText('Concluir tarefa'));

    await waitFor(() => expect(mockPost).toHaveBeenCalled());
    const [url, corpo] = mockPost.mock.calls[0];
    expect(url).toBe('/crm/tarefas/1/concluir');
    expect(corpo.proxima.titulo).toBe('Café com o contador');
  });

  it('concluir envia a próxima e recarrega', async () => {
    await abrir();
    fireEvent.click(screen.getByLabelText('Concluir Cobrar proposta'));
    fireEvent.change(await screen.findByLabelText('Próxima: Título'), {
      target: { value: 'Apresentar proposta' },
    });
    fireEvent.click(screen.getByText('Concluir tarefa'));

    await waitFor(() => expect(mockPost).toHaveBeenCalled());
    const [url, corpo] = mockPost.mock.calls[0];
    expect(url).toBe('/crm/tarefas/1/concluir');
    expect(corpo.proxima.titulo).toBe('Apresentar proposta');
  });

  it('o relato do que aconteceu quebra linha — é textarea, não input', async () => {
    /*
      Era um input de 40px. O relato de uma ligação inteira rolava para a
      direita e sumia: quem escrevia perdia de vista o começo da própria
      frase, sem jeito de reler sem navegar com as setas.

      O assert é na TAG porque é ela que decide o comportamento. Conferir
      classe CSS aqui passaria com um input estilizado, que é justamente o
      que não resolve o problema.
    */
    await abrir();
    fireEvent.click(screen.getByLabelText('Concluir Cobrar proposta'));
    const campo = await screen.findByLabelText('O que aconteceu (opcional)');
    expect(campo.tagName).toBe('TEXTAREA');
  });

  it('o motivo do cancelamento também quebra linha', async () => {
    await abrir();
    fireEvent.click(screen.getByLabelText('Cancelar Cobrar proposta'));
    const campo = await screen.findByLabelText('Motivo do cancelamento (opcional)');
    expect(campo.tagName).toBe('TEXTAREA');
  });

  it('cancelar não pede a próxima', async () => {
    await abrir();
    fireEvent.click(screen.getByLabelText('Cancelar Cobrar proposta'));
    expect(await screen.findByLabelText('Motivo do cancelamento (opcional)'))
      .toBeInTheDocument();
    expect(screen.queryByLabelText('Próxima: Título')).not.toBeInTheDocument();
  });

  it('editar reagenda a tarefa', async () => {
    /* É como se muda o prazo aqui: por data explícita, não por arrasto. */
    await abrir();
    fireEvent.click(screen.getByLabelText('Editar Cobrar proposta'));
    fireEvent.change(await screen.findByLabelText('Prazo'), {
      target: { value: '2026-09-01T10:00' },
    });
    fireEvent.click(screen.getByText('Salvar tarefa'));
    await waitFor(() => expect(mockPatch).toHaveBeenCalled());
    expect(mockPatch.mock.calls[0][0]).toBe('/crm/tarefas/1');
  });

  it('o 422 do backend aparece', async () => {
    mockPost.mockRejectedValue({
      response: { data: { detail: 'Concluir exige agendar a próxima tarefa.' } },
    });
    await abrir();
    fireEvent.click(screen.getByLabelText('Concluir Cobrar proposta'));
    fireEvent.change(await screen.findByLabelText('Próxima: Título'), {
      target: { value: 'X' },
    });
    fireEvent.click(screen.getByText('Concluir tarefa'));
    expect(await screen.findByText('Concluir exige agendar a próxima tarefa.'))
      .toBeInTheDocument();
  });
});

// ── Produção do mês ──────────────────────────────────────────────────
//
// A barra contava só o que está PARADO — atrasadas e em aberto. Uma tela que
// só mostra dívida ensina que o trabalho nunca rende. O KPI do mês é o
// contrapeso, e é por onde se chega à resposta de "quantas reuniões tivemos
// em agosto".

describe('Tarefas — a produção do mês', () => {
  beforeEach(() => {
    // Só o relógio: com os timers inteiros falsos o debounce da busca nunca
    // dispara e o waitFor estoura por timeout.
    vi.useFakeTimers({ toFake: ['Date'] });
    vi.setSystemTime(new Date(2026, 7, 14, 12, 0, 0));
  });

  afterEach(() => vi.useRealTimers());

  const chamadasDe = (url) => mockGet.mock.calls.filter((c) => c[0] === url);

  it('pede o resumo do mês corrente', async () => {
    montar();
    await waitFor(() => expect(chamadasDe('/crm/tarefas/resumo').length).toBe(1));
    expect(chamadasDe('/crm/tarefas/resumo')[0][1].params).toMatchObject({
      de: '2026-08-01', ate: '2026-08-31',
    });
  });

  it('mostra o total realizado na barra', async () => {
    montar();
    expect(await screen.findByText('42')).toBeInTheDocument();
    expect(screen.getByText('Realizadas em ago')).toBeInTheDocument();
  });

  it('o agregado usa os MESMOS filtros da barra', async () => {
    /*
      Número global ao lado de uma lista filtrada são duas respostas para a
      mesma pergunta, na mesma tela.
    */
    montar();
    await screen.findByRole('region', { name: 'Atrasadas' });

    fireEvent.change(screen.getByLabelText('Responsável'), { target: { value: 'u2' } });

    await waitFor(() => {
      const ultima = chamadasDe('/crm/tarefas/resumo').at(-1);
      expect(ultima[1].params).toMatchObject({ responsavel_id: 'u2' });
    });
  });

  it('clicar abre a produção por tipo e por responsável', async () => {
    montar();
    fireEvent.click(await screen.findByText('Realizadas em ago'));

    expect(await screen.findByText('Produção do mês')).toBeInTheDocument();
    expect(screen.getByText('agosto de 2026')).toBeInTheDocument();
    expect(screen.getByText('Reunião')).toBeInTheDocument();
  });

  it('falha do resumo não derruba o kanban nem rouba a faixa de erro', async () => {
    /*
      O kanban é o conteúdo. Um erro no contador do mês não pode aparecer no
      lugar do erro de quem está tentando concluir uma tarefa.
    */
    mockGet.mockImplementation((url) => {
      if (url === '/crm/tarefas/resumo') return Promise.reject(new Error('502'));
      return respostas()(url);
    });
    montar();

    await screen.findByRole('region', { name: 'Atrasadas' });
    expect(screen.getByText('Cobrar proposta')).toBeInTheDocument();
    expect(screen.getByText('—')).toBeInTheDocument();
  });
});

// ── Drilldown da oportunidade ────────────────────────────────────────
//
// A tarefa é sempre sobre alguma coisa, e essa coisa é a oportunidade. Quem
// abre "Cobrar proposta" precisa, no mesmo minuto, da fase, do valor e do que
// foi conversado antes — e isso custava fechar tudo, ir ao funil e buscar o
// número na mão.
//
// A oportunidade abre EM CIMA da tarefa, editável, e some sem levar junto o
// que estava aberto atrás. Mesma escolha do drilldown da conta dentro da
// oportunidade, e pelo mesmo motivo.

describe('Tarefas — drilldown da oportunidade', () => {
  const DETALHE_OPP = {
    id: 'o1', numero: 'OPP-2026-00001', conta_id: 'c1',
    conta_razao_social: 'Metalurgica Alfa LTDA',
    contato_id: null, contato_nome: null,
    fase: 'negociacao', status: 'ativa', fase_desfecho: null, motivo_desfecho: null,
    valor_mensalidade: 2500, temperatura: 70, previsao_fechamento: '2026-09-30',
    descricao: null, observacoes: null, origem_id: null, origem_nome: null,
    finder_conta_id: null, finder_razao_social: null,
    envolvidos: [], concorrentes: [], tarefas_abertas: 1,
    criado_em: '2026-08-01T12:00:00Z', atualizado_em: '2026-08-01T12:00:00Z',
  };

  const CONTA = {
    id: 'c1',
    razao_social: 'Metalurgica Alfa LTDA', nome_fantasia: 'Alfa',
    cnpj: '11222333000181', cnpj_formatado: '11.222.333/0001-81',
    vertical_id: 1, vertical_nome: 'Metalúrgica', num_funcionarios: 120,
    cep: '07020020', logradouro: 'Rua A', numero: '100', complemento: null,
    bairro: 'Centro', cidade: 'Guarulhos', uf: 'SP',
    telefone: '1130001000', telefone_2: null, email: 'contato@alfa.com',
    observacoes: null, eh_finder: false, ativo: true,
    vendedores: ['Jakeline Santana'], qtd_oportunidades_ativas: 1,
    criado_em: '2026-08-01T12:00:00Z', atualizado_em: '2026-08-01T12:00:00Z',
    contatos: [], oportunidades: [],
  };

  // A tarefa 1 é a que os testes abrem. O GET individual existe porque
  // qualquer mudança dentro do drilldown pode alterar situação e
  // status_oportunidade do cartão que ficou atrás.
  const TAREFA_1 = COLUNAS[0].itens[0];

  function respostasComOportunidade(colunas = COLUNAS) {
    return (url) => {
      if (url === '/crm/oportunidades/o1') return Promise.resolve({ data: DETALHE_OPP });
      if (url === '/crm/tarefas/1') return Promise.resolve({ data: TAREFA_1 });
      if (url === '/crm/contas/c1') return Promise.resolve({ data: CONTA });
      if (url === '/crm/dominio/verticais') {
        return Promise.resolve({ data: [{ id: 1, nome: 'Metalúrgica', slug: 'metalurgica' }] });
      }
      if (url === '/crm/contatos') {
        return Promise.resolve({ data: { total: 0, limit: 100, offset: 0, itens: [] } });
      }
      return respostas(colunas)(url);
    };
  }

  const botaoDaOportunidade = () =>
    screen.getByLabelText('Abrir a oportunidade OPP-2026-00001');

  async function abrirTarefa(colunas = COLUNAS) {
    mockGet.mockImplementation(respostasComOportunidade(colunas));
    montar();
    await screen.findByText('Cobrar proposta');
    fireEvent.click(screen.getByText('Cobrar proposta').closest('button'));
    return screen.findByText('Concluir');
  }

  async function abrirOportunidade() {
    await abrirTarefa();
    fireEvent.click(botaoDaOportunidade());
    return screen.findByTestId('tab-dados');
  }

  it('o detalhe da tarefa traz a oportunidade como botão', async () => {
    await abrirTarefa();
    expect(botaoDaOportunidade()).toBeInTheDocument();
  });

  it('clicar abre a visão 360 da oportunidade, editável', async () => {
    /*
      Editável é o ponto: o drilldown é o MESMO componente do funil, não uma
      cópia só-leitura que envelheceria em paralelo.
    */
    await abrirOportunidade();
    expect(mockGet.mock.calls.some(([u]) => u === '/crm/oportunidades/o1')).toBe(true);
    expect(screen.getByLabelText('Fase')).not.toBeDisabled();
  });

  it('a tarefa continua aberta atrás', async () => {
    /* Empilhar em vez de navegar é o que preserva o que já estava aqui. */
    await abrirOportunidade();
    expect(screen.getByLabelText('Concluir Cobrar proposta')).toBeInTheDocument();
  });

  it('o painel de concluir sobrevive ao drilldown', async () => {
    /*
      O motivo de empilhar. Com rota nova o modal desmontaria e o formulário
      da próxima tarefa iria junto — sem aviso nenhum.
    */
    await abrirTarefa();
    fireEvent.click(screen.getByLabelText('Concluir Cobrar proposta'));
    fireEvent.change(await screen.findByLabelText('Próxima: Título'), {
      target: { value: 'Apresentar proposta' },
    });

    fireEvent.click(botaoDaOportunidade());
    await screen.findByTestId('tab-dados');

    const barra = within(screen.getByLabelText('Ações da oportunidade'));
    fireEvent.click(barra.getByText('Fechar'));

    await waitFor(() =>
      expect(screen.queryByTestId('tab-dados')).not.toBeInTheDocument()
    );
    expect(screen.getByLabelText('Próxima: Título').value).toBe('Apresentar proposta');
  });

  it('mexer na oportunidade recarrega o kanban e a tarefa aberta', async () => {
    /*
      Finalizar ou mover a negociação muda o `status_oportunidade` da tarefa
      que ficou atrás — e é ele que decide se concluir ainda vai exigir a
      próxima. Sem recarregar, o cartão mente sobre o próprio estado.
    */
    mockPatch.mockResolvedValue({ data: { ...DETALHE_OPP, fase: 'apresentacao' } });
    await abrirOportunidade();

    fireEvent.change(screen.getByLabelText('Fase'), { target: { value: 'apresentacao' } });

    await waitFor(() =>
      expect(mockGet.mock.calls.some(([u]) => u === '/crm/tarefas/1')).toBe(true)
    );
    expect(mockPatch.mock.calls[0][0]).toBe('/crm/oportunidades/o1/fase');
  });

  it('da oportunidade a pilha segue até a empresa', async () => {
    /* Três degraus: tarefa → oportunidade → conta. */
    await abrirOportunidade();
    fireEvent.click(screen.getByLabelText('Abrir a conta Metalurgica Alfa LTDA'));

    const razao = await screen.findByLabelText('Razão social');
    expect(razao.value).toBe('Metalurgica Alfa LTDA');
    expect(screen.getByTestId('tab-dados')).toBeInTheDocument();
  });

  it('tarefa de parceiro não oferece o botão', async () => {
    /*
      Parceiro não tem oportunidade. Um botão que abre nada seria pior que a
      ausência dele — e quem decide é `alvo`/`oportunidade_id`, não a
      inferência de um campo nulo.
    */
    await abrirTarefa(COLUNAS.map((c) => (c.situacao === 'atrasada'
      ? {
        ...c,
        itens: [{
          ...c.itens[0],
          alvo: 'parceiro', alvo_rotulo: 'Parceiro',
          oportunidade_id: null, oportunidade_numero: null,
          status_oportunidade: null,
          conta_razao_social: 'Contabil Gama ME',
        }],
      }
      : c)));

    expect(screen.queryByLabelText(/^Abrir a oportunidade/)).not.toBeInTheDocument();
  });

  it('erro ao abrir a oportunidade aparece e não abre modal nenhum', async () => {
    mockGet.mockImplementation((url) => {
      if (url === '/crm/oportunidades/o1') {
        return Promise.reject({ response: { data: { detail: 'Sem permissão' } } });
      }
      return respostasComOportunidade()(url);
    });
    montar();
    await screen.findByText('Cobrar proposta');
    fireEvent.click(screen.getByText('Cobrar proposta').closest('button'));
    await screen.findByText('Concluir');

    fireEvent.click(botaoDaOportunidade());
    expect(await screen.findByText('Sem permissão')).toBeInTheDocument();
    expect(screen.queryByTestId('tab-dados')).not.toBeInTheDocument();
  });
});
