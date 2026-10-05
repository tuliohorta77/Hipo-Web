// web/src/tests/Prospeccao.test.jsx
//
// O que esta tela não pode errar:
//   * consultar sem UF e CNAE (a API recusa, e a tela precisa dizer por quê
//     antes de perguntar);
//   * deixar marcar empresa que não é puxável (em negociação, cliente,
//     bloqueada);
//   * passar de 50 no lote;
//   * mandar o lote e não dizer o que ficou de fora.
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, fireEvent, cleanup, waitFor, within } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';

const mockGet = vi.fn();
const mockPost = vi.fn();

vi.mock('../api', () => ({
  default: {
    get: (...a) => mockGet(...a),
    post: (...a) => mockPost(...a),
  },
  getUser: () => ({ id: 'u1', nome: 'Kethlleen', cargo: 'SDR' }),
}));

import Prospeccao, {
  montarParams, fatiaPronta, opcaoCnaeLivre, prazoParaApi, hojeLocal,
  FILTROS_INICIAIS, LIMITE_LOTE,
} from '../pages/crm/Prospeccao';

const BASE = {
  carregada: true, referencia: '2026-09', ufs: ['SP'],
  estabelecimentos: 3200000, concluida_em: '2026-10-01T10:00:00Z',
};

const RESUMO = {
  total: 812, puxaveis: 640, novas: 600, conta_sem_negocio: 40,
  em_negociacao: 150, clientes: 15, bloqueadas: 6, inativas: 1,
  meus_suspects_abertos: 37, minhas_puxadas_no_mes: 90,
};

function item(cnpj, situacao = 'nova', extra = {}) {
  return {
    cnpj, cnpj_formatado: cnpj, razao_social: `EMPRESA ${cnpj} LTDA`,
    nome_fantasia: null, matriz: true, cnae_principal: '4120400',
    cnae_descricao: 'Construção de edifícios', porte: 'DEMAIS', simples: false,
    capital_social: '500000.00', data_abertura: '2012-01-01', bairro: 'CENTRO',
    municipio: 'GUARULHOS', uf: 'SP', telefone: '1123456789', email: null,
    situacao, conta_id: null, ...extra,
  };
}

function rotear({ itens = [item('11222333000181')], total, resumo = RESUMO, base = BASE } = {}) {
  mockGet.mockImplementation((url) => {
    if (url === '/crm/prospeccao/base') return Promise.resolve({ data: base });
    if (url === '/crm/prospeccao/resumo') return Promise.resolve({ data: resumo });
    if (url === '/crm/prospeccao') {
      return Promise.resolve({ data: { itens, total: total ?? itens.length, limit: 50, offset: 0 } });
    }
    if (url === '/crm/prospeccao/cnaes') {
      return Promise.resolve({ data: [{ codigo: '4120400', descricao: 'Construção de edifícios' }] });
    }
    if (url === '/crm/prospeccao/municipios') return Promise.resolve({ data: [] });
    return Promise.reject(new Error(`rota inesperada ${url}`));
  });
}

function renderTela() {
  return render(<MemoryRouter><Prospeccao /></MemoryRouter>);
}

async function escolherCnae(texto = '41') {
  const campo = screen.getByLabelText('CNAE');
  fireEvent.change(campo, { target: { value: texto } });
  fireEvent.keyDown(campo, { key: 'Enter' });
}

beforeEach(() => {
  mockGet.mockReset();
  mockPost.mockReset();
});
afterEach(cleanup);

// ── Funções puras ────────────────────────────────────────────────────

describe('montarParams', () => {
  it('manda só o que foi preenchido', () => {
    const p = montarParams({
      ...FILTROS_INICIAIS, ufs: ['SP'], cnaes: [{ valor: '41', rotulo: '41' }],
    });
    expect(p).toEqual({ uf: ['SP'], cnae: ['41'], situacao: 'puxaveis' });
  });

  it('traduz cada filtro para o nome da API', () => {
    const p = montarParams({
      ...FILTROS_INICIAIS,
      ufs: ['SP'], cnaes: [{ valor: '41' }], municipios: [{ valor: '6477' }],
      portes: ['05'], regime: 'nao_simples', idadeMin: '3', capitalMin: '100000',
      secundarios: true, comTelefone: true, comEmail: true, soMatriz: true,
      q: '  acme ', todas: true,
    });
    expect(p).toEqual({
      uf: ['SP'], cnae: ['41'], municipio: ['6477'], porte: ['05'],
      regime: 'nao_simples', idade_min: 3, capital_min: 100000,
      secundarios: true, com_telefone: true, com_email: true, so_matriz: true,
      q: 'acme', situacao: 'todas',
    });
  });

  it('fatia precisa de UF e CNAE', () => {
    expect(fatiaPronta({ ...FILTROS_INICIAIS, ufs: ['SP'] })).toBe(false);
    expect(fatiaPronta({ ...FILTROS_INICIAIS, ufs: ['SP'], cnaes: [{ valor: '41' }] })).toBe(true);
  });
});

describe('opcaoCnaeLivre', () => {
  it('prefixo de 2 a 6 dígitos vira faixa; 7 é a subclasse', () => {
    expect(opcaoCnaeLivre('41').valor).toBe('41');
    expect(opcaoCnaeLivre('41').rotulo).toMatch(/começam/);
    expect(opcaoCnaeLivre('4120-4/00')).toEqual({ valor: '4120400', rotulo: '4120400' });
  });

  it('texto ou 1 dígito não vira opção', () => {
    expect(opcaoCnaeLivre('4')).toBeNull();
    expect(opcaoCnaeLivre('constru')).toBeNull();
  });
});

describe('prazoParaApi', () => {
  it('hoje vai vazio (a API usa agora); outro dia vai às 9h locais', () => {
    expect(prazoParaApi('2026-10-02', '2026-10-02')).toBeNull();
    const iso = prazoParaApi('2026-10-05', '2026-10-02');
    expect(new Date(iso).getHours()).toBe(9);
  });

  it('hojeLocal formata a data local', () => {
    expect(hojeLocal(new Date(2026, 0, 5))).toBe('2026-01-05');
  });
});

// ── Tela ─────────────────────────────────────────────────────────────

describe('Prospeccao', () => {
  it('sem base carregada explica como carregar', async () => {
    rotear({ base: { carregada: false, ufs: [] } });
    renderTela();
    expect(await screen.findByText('A base da Receita ainda não foi carregada')).toBeInTheDocument();
  });

  it('pede o CNAE antes de consultar, com a única UF já marcada', async () => {
    rotear();
    renderTela();
    expect(await screen.findByText('Escolha a UF e ao menos um CNAE')).toBeInTheDocument();
    // O aviso aparece antes de /base responder; os botões de UF chegam com
    // ela. Esperar o botão (e não buscá-lo na hora) tira a corrida que
    // derrubava o teste quando o CI estava lento.
    const sp = await screen.findByRole('button', { name: 'SP' });
    await waitFor(() => expect(sp).toHaveAttribute('aria-pressed', 'true'));
    expect(mockGet).not.toHaveBeenCalledWith('/crm/prospeccao', expect.anything());
  });

  it('com CNAE, mostra o resumo e a lista', async () => {
    rotear();
    renderTela();
    await screen.findByText('Escolha a UF e ao menos um CNAE');
    await escolherCnae('41');

    expect(await screen.findByText('EMPRESA 11222333000181 LTDA')).toBeInTheDocument();
    const resumo = screen.getByLabelText('Resumo da fatia');
    expect(within(resumo).getByText('812')).toBeInTheDocument();
    expect(within(resumo).getByText('640')).toBeInTheDocument();
    expect(within(resumo).getByText('37')).toBeInTheDocument();

    const chamada = mockGet.mock.calls.find(([u]) => u === '/crm/prospeccao');
    expect(chamada[1].params).toMatchObject({ uf: ['SP'], cnae: ['41'], situacao: 'puxaveis' });
  });

  it('o KPI de negociação mostra a fatia inteira', async () => {
    rotear();
    renderTela();
    await screen.findByText('Escolha a UF e ao menos um CNAE');
    await escolherCnae('41');
    await screen.findByText('EMPRESA 11222333000181 LTDA');

    fireEvent.click(screen.getByTitle('Mostrar a fatia inteira, com a situação de cada empresa'));
    await waitFor(() => {
      const ultimas = mockGet.mock.calls.filter(([u]) => u === '/crm/prospeccao');
      expect(ultimas.at(-1)[1].params.situacao).toBe('todas');
    });
  });

  it('não deixa marcar quem não é puxável', async () => {
    rotear({ itens: [item('1', 'nova'), item('2', 'em_negociacao'), item('3', 'bloqueada')] });
    renderTela();
    await screen.findByText('Escolha a UF e ao menos um CNAE');
    await escolherCnae('41');
    await screen.findByText('EMPRESA 1 LTDA');

    expect(screen.getByLabelText('Selecionar EMPRESA 1 LTDA')).not.toBeDisabled();
    expect(screen.getByLabelText('Selecionar EMPRESA 2 LTDA')).toBeDisabled();
    expect(screen.getByLabelText('Selecionar EMPRESA 3 LTDA')).toBeDisabled();

    fireEvent.click(screen.getByLabelText('Selecionar a página'));
    expect(screen.getByText(/empresa selecionada/)).toBeInTheDocument();
  });

  it(`selecionar a página para em ${LIMITE_LOTE}`, async () => {
    const itens = Array.from({ length: LIMITE_LOTE + 5 }, (_, i) => item(String(i)));
    rotear({ itens, total: 200 });
    renderTela();
    await screen.findByText('Escolha a UF e ao menos um CNAE');
    await escolherCnae('41');
    await screen.findByText('EMPRESA 0 LTDA');

    fireEvent.click(screen.getByLabelText('Selecionar a página'));
    expect(screen.getByText(String(LIMITE_LOTE), { selector: 'strong' })).toBeInTheDocument();
    expect(screen.getByLabelText(`Selecionar EMPRESA ${LIMITE_LOTE + 1} LTDA`)).toBeDisabled();
  });

  it('puxa o lote, mostra o que ficou de fora e recarrega', async () => {
    rotear({ itens: [item('11222333000181'), item('34028316000103')] });
    mockPost.mockResolvedValue({
      data: {
        puxadas: [{
          cnpj: '11222333000181', razao_social: 'EMPRESA 1', conta_id: 'c1',
          conta_nova: true, oportunidade_id: 'o1', oportunidade_numero: 'OPP-2026-00001',
          tarefa_id: 't1',
        }],
        puladas: [{
          cnpj: '34028316000103', razao_social: 'EMPRESA 2', motivo: 'em_negociacao',
          mensagem: 'Já tem oportunidade aberta.',
        }],
        enriquecimento_em_segundo_plano: 1,
      },
    });
    renderTela();
    await screen.findByText('Escolha a UF e ao menos um CNAE');
    await escolherCnae('41');
    await screen.findByText('EMPRESA 11222333000181 LTDA');

    fireEvent.click(screen.getByLabelText('Selecionar EMPRESA 11222333000181 LTDA'));
    fireEvent.click(screen.getByLabelText('Selecionar EMPRESA 34028316000103 LTDA'));
    const consultasAntes = mockGet.mock.calls.filter(([u]) => u === '/crm/prospeccao').length;
    fireEvent.click(screen.getByRole('button', { name: /Puxar para o HIPO/ }));

    expect(await screen.findByText(/1 empresa puxada para o funil/)).toBeInTheDocument();
    expect(mockPost).toHaveBeenCalledWith('/crm/prospeccao/puxar', {
      cnpjs: ['11222333000181', '34028316000103'],
      prazo: null,
    });
    expect(screen.getByText('EMPRESA 2: Já tem oportunidade aberta.')).toBeInTheDocument();
    expect(screen.getByRole('link', { name: 'Ir para minhas tarefas' })).toHaveAttribute('href', '/crm/tarefas');
    expect(screen.queryByRole('button', { name: /Puxar para o HIPO/ })).not.toBeInTheDocument();
    await waitFor(() => {
      expect(mockGet.mock.calls.filter(([u]) => u === '/crm/prospeccao').length)
        .toBeGreaterThan(consultasAntes);
    });
  });

  it('mostra o erro da API (fatia grande demais)', async () => {
    rotear();
    mockGet.mockImplementation((url) => {
      if (url === '/crm/prospeccao/base') return Promise.resolve({ data: BASE });
      return Promise.reject({ response: { data: { detail: 'A fatia ficou grande demais para consultar de uma vez.' } } });
    });
    renderTela();
    await screen.findByText('Escolha a UF e ao menos um CNAE');
    await escolherCnae('41');
    expect(await screen.findByText(/grande demais/)).toBeInTheDocument();
  });
});
