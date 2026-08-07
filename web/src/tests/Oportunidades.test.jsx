// web/src/tests/Oportunidades.test.jsx
//
// A página do funil: duas visões da mesma lista, com a preferência gravada no
// banco (não no localStorage), e KPIs que aplicam filtro.
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, fireEvent, cleanup, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';

const mockGet = vi.fn();
const mockPost = vi.fn();
const mockPatch = vi.fn();
const mockPut = vi.fn();

vi.mock('../api', () => ({
  default: {
    get: (...a) => mockGet(...a),
    post: (...a) => mockPost(...a),
    patch: (...a) => mockPatch(...a),
    put: (...a) => mockPut(...a),
  },
}));

import Oportunidades from '../pages/crm/Oportunidades';

const RESUMO = {
  abertas: 3, ticket_aberto: 7500, previsto_no_mes: 2500,
  sem_proxima_acao: 1, paradas: 0, ganhas_mes: 2, perdidas_mes: 1,
  por_fase: [], perda_por_fase: [],
};

const OPP = {
  id: 'o1', numero: 'OPP-2026-00001', conta_id: 'c1',
  conta_razao_social: 'Metalurgica Alfa', contato_id: null, contato_nome: null,
  fase: 'negociacao', status: 'ativa', fase_desfecho: null, motivo_desfecho: null,
  valor_mensalidade: 2500, temperatura: 70, previsao_fechamento: '2026-09-30',
  proxima_acao_em: null, proxima_acao_tipo: null, origem_nome: null,
  finder_conta_id: null, finder_razao_social: null, envolvidos: [],
  criado_em: '2026-08-01T12:00:00Z', atualizado_em: '2026-08-01T12:00:00Z',
};

const COLUNAS = [
  { fase: 'lead', rotulo: 'Lead', quantidade: 0, ticket_total: 0, itens: [] },
  { fase: 'qualificacao', rotulo: 'Qualificação', quantidade: 0, ticket_total: 0, itens: [] },
  { fase: 'apresentacao', rotulo: 'Apresentação', quantidade: 0, ticket_total: 0, itens: [] },
  { fase: 'negociacao', rotulo: 'Negociação', quantidade: 1, ticket_total: 2500, itens: [OPP] },
];

function respostas(visaoSalva) {
  return (url) => {
    if (url === '/crm/dominio/preferencias') {
      return Promise.resolve({
        data: visaoSalva ? [{ chave: 'crm_oportunidades_visao', valor: visaoSalva }] : [],
      });
    }
    if (url === '/crm/dominio/usuarios') {
      return Promise.resolve({ data: [{ id: 'u1', nome: 'Ana Vendas', cargo: 'EV' }] });
    }
    if (url === '/crm/oportunidades/resumo') return Promise.resolve({ data: RESUMO });
    if (url === '/crm/oportunidades/kanban') return Promise.resolve({ data: COLUNAS });
    if (url === '/crm/oportunidades') {
      return Promise.resolve({ data: { total: 1, limit: 50, offset: 0, itens: [OPP] } });
    }
    return Promise.resolve({ data: [] });
  };
}

function montar() {
  return render(<MemoryRouter><Oportunidades /></MemoryRouter>);
}

beforeEach(() => {
  mockGet.mockReset();
  mockPost.mockReset();
  mockPatch.mockReset();
  mockPut.mockReset();
  mockGet.mockImplementation(respostas(null));
});

afterEach(cleanup);

describe('Oportunidades — visão padrão e preferência', () => {
  it('abre no kanban quando não há preferência salva', async () => {
    montar();
    expect(await screen.findByRole('region', { name: 'Fase Lead' })).toBeInTheDocument();
  });

  it('respeita a preferência de tabela vinda do banco', async () => {
    mockGet.mockImplementation(respostas('tabela'));
    montar();
    expect(await screen.findByText('OPP-2026-00001')).toBeInTheDocument();
    expect(screen.queryByRole('region', { name: 'Fase Lead' })).not.toBeInTheDocument();
  });

  it('trocar de visão grava a preferência no banco', async () => {
    /*
      No banco e não no localStorage: o HIPO é a fonte primária, e a escolha
      deve acompanhar a pessoa entre máquinas.
    */
    montar();
    await screen.findByRole('region', { name: 'Fase Lead' });
    fireEvent.click(screen.getByLabelText('Ver como tabela'));
    await waitFor(() =>
      expect(mockPut).toHaveBeenCalledWith(
        '/crm/dominio/preferencias/crm_oportunidades_visao',
        { valor: 'tabela' }
      )
    );
  });

  it('falha ao gravar a preferência não trava a troca de visão', async () => {
    mockPut.mockRejectedValue(new Error('offline'));
    montar();
    await screen.findByRole('region', { name: 'Fase Lead' });
    fireEvent.click(screen.getByLabelText('Ver como tabela'));
    expect(await screen.findByText('OPP-2026-00001')).toBeInTheDocument();
  });
});

describe('Oportunidades — KPIs', () => {
  it('mostra os quatro indicadores', async () => {
    montar();
    expect(await screen.findByText('Em aberto')).toBeInTheDocument();
    expect(screen.getByText('Previsto no mês')).toBeInTheDocument();
    expect(screen.getByText('Sem próxima ação')).toBeInTheDocument();
    expect(screen.getByText('Ganhas no mês')).toBeInTheDocument();
  });

  it('clicar em "Sem próxima ação" filtra', async () => {
    montar();
    await screen.findByText('Sem próxima ação');
    mockGet.mockClear();
    fireEvent.click(screen.getByText('Sem próxima ação').closest('button'));
    await waitFor(() => {
      const chamada = mockGet.mock.calls.find(([u]) => u === '/crm/oportunidades/kanban');
      expect(chamada[1].params.sem_proxima_acao).toBe(true);
    });
  });

  it('clicar de novo desfaz o filtro', async () => {
    montar();
    await screen.findByText('Sem próxima ação');
    const kpi = screen.getByText('Sem próxima ação').closest('button');
    fireEvent.click(kpi);
    await waitFor(() => expect(kpi).toHaveAttribute('aria-pressed', 'true'));
    fireEvent.click(kpi);
    await waitFor(() => expect(kpi).toHaveAttribute('aria-pressed', 'false'));
  });
});

describe('Oportunidades — tabela', () => {
  beforeEach(() => { mockGet.mockImplementation(respostas('tabela')); });

  it('lista com número, empresa e valor', async () => {
    montar();
    expect(await screen.findByText('OPP-2026-00001')).toBeInTheDocument();
    expect(screen.getByText('Metalurgica Alfa')).toBeInTheDocument();
  });

  it('mostra o filtro de fase só na tabela', async () => {
    montar();
    await screen.findByText('OPP-2026-00001');
    expect(screen.getByLabelText('Fase')).toBeInTheDocument();
  });

  it('estado vazio quando não há oportunidades', async () => {
    mockGet.mockImplementation((url) => {
      if (url === '/crm/oportunidades') {
        return Promise.resolve({ data: { total: 0, limit: 50, offset: 0, itens: [] } });
      }
      return respostas('tabela')(url);
    });
    montar();
    expect(await screen.findByText('Nenhuma oportunidade')).toBeInTheDocument();
  });
});

describe('Oportunidades — kanban', () => {
  it('mover cartão chama o endpoint de fase', async () => {
    montar();
    await screen.findByRole('region', { name: 'Fase Lead' });
    const seletor = screen.getByLabelText('Mover OPP-2026-00001 para outra fase');
    fireEvent.change(seletor, { target: { value: 'lead' } });
    await waitFor(() =>
      expect(mockPatch).toHaveBeenCalledWith(
        '/crm/oportunidades/o1/fase', { fase: 'lead' }
      )
    );
  });

  it('erro ao mover é exibido', async () => {
    mockPatch.mockRejectedValue({ response: { data: { detail: 'Reabra antes.' } } });
    montar();
    await screen.findByRole('region', { name: 'Fase Lead' });
    fireEvent.change(
      screen.getByLabelText('Mover OPP-2026-00001 para outra fase'),
      { target: { value: 'lead' } }
    );
    expect(await screen.findByText('Reabra antes.')).toBeInTheDocument();
  });

  it('botão Finalizar do cartão abre o modal de desfecho', async () => {
    montar();
    await screen.findByRole('region', { name: 'Fase Lead' });
    fireEvent.click(screen.getByLabelText('Finalizar OPP-2026-00001'));
    expect(await screen.findByText('Finalizar oportunidade')).toBeInTheDocument();
  });
});

describe('Oportunidades — erro de carga', () => {
  it('mostra a mensagem da API', async () => {
    mockGet.mockImplementation((url) => {
      if (url === '/crm/oportunidades/resumo') {
        return Promise.reject({ response: { data: { detail: 'Boom' } } });
      }
      return respostas(null)(url);
    });
    montar();
    expect(await screen.findByText('Boom')).toBeInTheDocument();
  });
});
