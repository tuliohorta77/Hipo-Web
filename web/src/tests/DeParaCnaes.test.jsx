// web/src/tests/DeParaCnaes.test.jsx
//
// O de-para existe para uma coisa: classificar um CNAE e, com isso,
// preencher a vertical das contas que JÁ existem. Estes testes protegem
// exatamente esse comportamento — e a ordem da fila, que é o que faz a
// pessoa começar pelo código que resolve mais.
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, fireEvent, cleanup, waitFor } from '@testing-library/react';

const mockGet = vi.fn();
const mockPatch = vi.fn();

let USUARIO = { id: 'u1', nome: 'Tulio', cargo: 'ADM' };

vi.mock('../api', () => ({
  default: {
    get: (...a) => mockGet(...a),
    patch: (...a) => mockPatch(...a),
  },
  getUser: () => USUARIO,
}));

import DeParaCnaes from '../components/crm/DeParaCnaes';

const VERTICAIS = [
  { id: 1, nome: 'Indústria', slug: 'industria' },
  { id: 2, nome: 'Serviços', slug: 'servicos' },
];

const RESUMO = {
  fontes: ['brasilapi'],
  contas_ativas: 1751,
  contas_enriquecidas: 12,
  contas_sem_cnae: 1739,
  cnaes_conhecidos: 8,
  cnaes_a_mapear: 6,
  contas_em_cnae_nao_mapeado: 47,
};

const CNAE_GRANDE = {
  codigo: '8610101', descricao: 'Atividades de atendimento hospitalar',
  vertical_id: null, vertical_nome: null, grau_risco: null, mapeado_em: null,
  qtd_contas: 40, qtd_contas_sem_vertical: 40,
};

const CNAE_PEQUENO = {
  codigo: '9609208', descricao: 'Higiene e embelezamento de animais domésticos',
  vertical_id: null, vertical_nome: null, grau_risco: null, mapeado_em: null,
  qtd_contas: 1, qtd_contas_sem_vertical: 1,
};

const CNAE_MAPEADO = {
  codigo: '2511000', descricao: 'Fabricação de estruturas metálicas',
  vertical_id: 1, vertical_nome: 'Indústria', grau_risco: 3,
  mapeado_em: '2026-09-21T12:00:00Z',
  qtd_contas: 5, qtd_contas_sem_vertical: 0,
};

function renderTela(props = {}) {
  return render(
    <DeParaCnaes
      verticais={VERTICAIS}
      onCriarVertical={vi.fn(async (nome) => ({ id: 9, nome }))}
      onMudou={vi.fn()}
      {...props}
    />
  );
}

beforeEach(() => {
  USUARIO = { id: 'u1', nome: 'Tulio', cargo: 'ADM' };
  mockGet.mockReset();
  mockPatch.mockReset();
  mockGet.mockImplementation((url) => {
    if (url === '/crm/enriquecimento/cnaes') {
      return Promise.resolve({ data: [CNAE_GRANDE, CNAE_PEQUENO] });
    }
    if (url === '/crm/enriquecimento/resumo') return Promise.resolve({ data: RESUMO });
    return Promise.resolve({ data: {} });
  });
});

afterEach(cleanup);

describe('DeParaCnaes', () => {
  it('abre filtrando só os não classificados', async () => {
    renderTela();
    await screen.findByText('Atividades de atendimento hospitalar');

    const chamada = mockGet.mock.calls.find(
      ([u]) => u === '/crm/enriquecimento/cnaes'
    );
    expect(chamada[1].params.apenas_nao_mapeados).toBe(true);
  });

  it('mostra o tamanho do problema, não só a lista', async () => {
    renderTela();
    await screen.findByText('Atividades de atendimento hospitalar');

    expect(screen.getByText('Contas esperando vertical')).toBeInTheDocument();
    expect(screen.getByText('47')).toBeInTheDocument();
    expect(screen.getByText('40 sem vertical')).toBeInTheDocument();
  });

  it('classificar aplica nas contas que já existem', async () => {
    renderTela();
    await screen.findByText('Atividades de atendimento hospitalar');

    fireEvent.change(
      screen.getByLabelText('Vertical do CNAE 8610101'),
      { target: { value: '1' } }
    );
    fireEvent.change(
      screen.getByLabelText('Grau de risco do CNAE 8610101'),
      { target: { value: '3' } }
    );

    mockPatch.mockResolvedValueOnce({
      data: {
        codigo: '8610101', descricao: 'Atividades de atendimento hospitalar',
        vertical_id: 1, vertical_nome: 'Indústria', grau_risco: 3,
        qtd_contas: 40, qtd_contas_sem_vertical: 0, contas_atualizadas: 40,
      },
    });

    fireEvent.click(screen.getAllByText('Aplicar')[0]);

    await waitFor(() => expect(mockPatch).toHaveBeenCalledWith(
      '/crm/enriquecimento/cnaes/8610101',
      { vertical_id: 1, grau_risco: 3, aplicar_em_contas: true },
    ));
    // A confirmação aparece NO TOPO, não na linha: com o filtro "só os
    // não classificados", a linha some assim que é classificada.
    expect(
      await screen.findByText(/8610101: 40 conta\(s\) classificada\(s\) como Indústria/)
    ).toBeInTheDocument();
  });

  it('o botão só habilita depois de mudar alguma coisa', async () => {
    renderTela();
    await screen.findByText('Atividades de atendimento hospitalar');

    expect(screen.getAllByText('Aplicar')[0].closest('button')).toBeDisabled();
    fireEvent.change(
      screen.getByLabelText('Vertical do CNAE 8610101'),
      { target: { value: '2' } }
    );
    expect(screen.getAllByText('Aplicar')[0].closest('button')).not.toBeDisabled();
  });

  it('recarrega a lista e os números depois de classificar', async () => {
    const onMudou = vi.fn();
    renderTela({ onMudou });
    await screen.findByText('Atividades de atendimento hospitalar');

    const antes = mockGet.mock.calls.filter(
      ([u]) => u === '/crm/enriquecimento/resumo'
    ).length;

    fireEvent.change(
      screen.getByLabelText('Vertical do CNAE 8610101'),
      { target: { value: '1' } }
    );
    mockPatch.mockResolvedValueOnce({
      data: { ...CNAE_GRANDE, vertical_id: 1, vertical_nome: 'Indústria', contas_atualizadas: 40 },
    });
    fireEvent.click(screen.getAllByText('Aplicar')[0]);

    await waitFor(() => {
      const depois = mockGet.mock.calls.filter(
        ([u]) => u === '/crm/enriquecimento/resumo'
      ).length;
      expect(depois).toBeGreaterThan(antes);
    });
    expect(onMudou).toHaveBeenCalled();
  });

  it('operacional não pode remapear CNAE já classificado', async () => {
    USUARIO = { id: 'u2', nome: 'SDR', cargo: 'SDR' };
    mockGet.mockImplementation((url) => {
      if (url === '/crm/enriquecimento/cnaes') {
        return Promise.resolve({ data: [CNAE_MAPEADO] });
      }
      if (url === '/crm/enriquecimento/resumo') return Promise.resolve({ data: RESUMO });
      return Promise.resolve({ data: {} });
    });

    renderTela();
    await screen.findByText('Fabricação de estruturas metálicas');

    expect(screen.getByText(/só gestão altera/)).toBeInTheDocument();
    expect(screen.queryByLabelText('Vertical do CNAE 2511000')).not.toBeInTheDocument();
  });

  it('gestão pode remapear CNAE já classificado', async () => {
    mockGet.mockImplementation((url) => {
      if (url === '/crm/enriquecimento/cnaes') {
        return Promise.resolve({ data: [CNAE_MAPEADO] });
      }
      if (url === '/crm/enriquecimento/resumo') return Promise.resolve({ data: RESUMO });
      return Promise.resolve({ data: {} });
    });

    renderTela();
    await screen.findByText('Fabricação de estruturas metálicas');
    expect(screen.getByLabelText('Vertical do CNAE 2511000')).toBeInTheDocument();
  });

  it('mostra o erro do backend na linha, sem derrubar a tela', async () => {
    renderTela();
    await screen.findByText('Atividades de atendimento hospitalar');

    fireEvent.change(
      screen.getByLabelText('Vertical do CNAE 8610101'),
      { target: { value: '1' } }
    );
    mockPatch.mockRejectedValueOnce({
      response: { status: 403, data: { detail: 'Só gestão pode alterar.' } },
    });
    fireEvent.click(screen.getAllByText('Aplicar')[0]);

    expect(await screen.findByText('Só gestão pode alterar.')).toBeInTheDocument();
    // A outra linha continua utilizável.
    expect(
      screen.getByText('Higiene e embelezamento de animais domésticos')
    ).toBeInTheDocument();
  });

  it('lista vazia oferece ver todos', async () => {
    mockGet.mockImplementation((url) => {
      if (url === '/crm/enriquecimento/cnaes') return Promise.resolve({ data: [] });
      if (url === '/crm/enriquecimento/resumo') return Promise.resolve({ data: RESUMO });
      return Promise.resolve({ data: {} });
    });

    renderTela();
    expect(
      await screen.findByText('Nenhum CNAE esperando classificação')
    ).toBeInTheDocument();
    fireEvent.click(screen.getByText('Ver todos'));

    await waitFor(() => {
      const ultima = mockGet.mock.calls
        .filter(([u]) => u === '/crm/enriquecimento/cnaes').at(-1);
      expect(ultima[1].params.apenas_nao_mapeados).toBeUndefined();
    });
  });
});
