// web/src/tests/AbaDadosPublicos.test.jsx
//
// Cobre o que dá identidade à aba:
//   1. abrir a aba NÃO consulta a fonte (em fonte paga isso é crédito);
//   2. o número estimado aparece marcado como estimado;
//   3. a divergência com o cadastro vira escolha do usuário, não
//      sobrescrita silenciosa;
//   4. CNAE sem classificação traz o formulário de mapeamento ali mesmo;
//   5. a busca de outras empresas do sócio diz o grau de confiança.
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
  getUser: () => ({ id: 'u1', nome: 'Tulio', cargo: 'ADM' }),
}));

import AbaDadosPublicos from '../components/crm/AbaDadosPublicos';

const VERTICAIS = [
  { id: 1, nome: 'Indústria', slug: 'industria' },
  { id: 2, nome: 'Serviços', slug: 'servicos' },
];

const CONTA_ENRIQUECIDA = {
  id: 'c1',
  razao_social: 'Metalurgica Alfa LTDA',
  cnpj_formatado: '11.222.333/0001-81',
  cnae_codigo: '2511000',
  cnae_descricao: 'Fabricação de estruturas metálicas',
  cnae_grau_risco: 3,
  cnae_vertical_id: 1,
  // 'humano': alguem decidiu. E o que tira o bloco de classificar da aba.
  cnae_mapeamento_origem: 'humano',
  cnae_vertical_nome: 'Indústria',
  porte: 'DEMAIS',
  situacao_cadastral: 'ATIVA',
  data_abertura: '2009-03-17',
  capital_social: 250000,
  num_funcionarios: 180,
  num_funcionarios_origem: 'estimado',
  enriquecida_em: '2026-09-20T12:00:00Z',
  enriquecida_fonte: 'leadcnpj+brasilapi',
};

function renderAba(conta = CONTA_ENRIQUECIDA) {
  return render(
    <AbaDadosPublicos
      conta={conta}
      verticais={VERTICAIS}
      onCriarVertical={vi.fn(async (nome) => ({ id: 9, nome }))}
      onRecarregar={vi.fn()}
    />
  );
}

beforeEach(() => {
  mockGet.mockReset();
  mockPost.mockReset();
  mockPatch.mockReset();
  mockGet.mockImplementation((url) => {
    return Promise.resolve({ data: { empresas: [], avisos: [] } });
  });
});

afterEach(cleanup);

describe('AbaDadosPublicos', () => {
  it('não consulta a fonte externa ao abrir', async () => {
    renderAba();
    await screen.findByText('Fabricação de estruturas metálicas');

    // Depois que os sócios viraram aba própria, esta aba não faz NENHUMA
    // chamada ao abrir: tudo que ela desenha veio junto com a conta. POST
    // é o que vai à fonte e gasta crédito.
    expect(mockGet).not.toHaveBeenCalled();
    expect(mockPost).not.toHaveBeenCalled();
  });

  it('mostra os dados do cadastro público', async () => {
    renderAba();
    await screen.findByText('Fabricação de estruturas metálicas');

    expect(screen.getAllByText('2511000').length).toBeGreaterThan(0);
    expect(screen.getByText('Fabricação de estruturas metálicas')).toBeInTheDocument();
    expect(screen.getByText(/grau 3/)).toBeInTheDocument();
    expect(screen.getByText('DEMAIS')).toBeInTheDocument();
  });

  it('marca o número de funcionários como estimado', async () => {
    renderAba();
    await screen.findByText('Fabricação de estruturas metálicas');

    expect(screen.getByText('estimado')).toBeInTheDocument();
    expect(
      screen.getByText(/confirme com o cliente antes de precificar/)
    ).toBeInTheDocument();
  });

  it('oferece mapear o CNAE quando ele não tem classificação', async () => {
    renderAba({
      ...CONTA_ENRIQUECIDA, cnae_vertical_id: null, cnae_grau_risco: null,
      cnae_mapeamento_origem: null, cnae_vertical_nome: null,
    });
    await screen.findByText('Fabricação de estruturas metálicas');

    expect(screen.getByText(/ainda não foi classificado/)).toBeInTheDocument();

    fireEvent.change(screen.getByLabelText('Vertical'), { target: { value: '1' } });
    fireEvent.change(screen.getByLabelText('Grau de risco (NR-4)'), {
      target: { value: '3' },
    });
    mockPatch.mockResolvedValueOnce({ data: { codigo: '2511000', grau_risco: 3 } });
    fireEvent.click(screen.getByText('Classificar CNAE'));

    // `aplicar_em_contas` não é detalhe: o texto do bloco promete que
    // classificar vale para todas as contas daquele código.
    await waitFor(() => expect(mockPatch).toHaveBeenCalledWith(
      '/crm/enriquecimento/cnaes/2511000',
      { vertical_id: 1, grau_risco: 3, aplicar_em_contas: true },
    ));
  });

  it('não oferece mapeamento para CNAE decidido por gente', async () => {
    renderAba();
    await screen.findByText('Fabricação de estruturas metálicas');
    expect(screen.queryByText(/ainda não foi classificado/)).not.toBeInTheDocument();
    expect(screen.queryByText(/Vertical sugerida/)).not.toBeInTheDocument();
    expect(screen.queryByLabelText('Vertical')).not.toBeInTheDocument();
  });

  // ── sugestão derivada (015) ──────────────────────────────────────────
  //
  // O bug que estes testes prendem: com `!cnae_vertical_id` como condição,
  // o bloco sumia de TODAS as contas no dia em que a carga derivou as
  // verticais — e a pessoa com a conta aberta ficava sem como discordar.

  const CONTA_SUGERIDA = {
    ...CONTA_ENRIQUECIDA,
    cnae_vertical_id: 2,
    cnae_vertical_nome: 'Serviços',
    cnae_grau_risco: null,
    cnae_mapeamento_origem: 'derivado',
  };

  it('CNAE com vertical apenas SUGERIDA continua oferecendo o bloco', async () => {
    renderAba(CONTA_SUGERIDA);
    await screen.findByText('Fabricação de estruturas metálicas');

    expect(screen.getByText(/Vertical sugerida: Serviços/)).toBeInTheDocument();
    expect(screen.getByText(/seção da CNAE 2.0/)).toBeInTheDocument();
    // Já vem escolhida: quem concorda não digita nada, só confirma.
    expect(screen.getByLabelText('Vertical')).toHaveValue('2');
    expect(screen.getByText('Confirmar vertical')).toBeInTheDocument();
  });

  it('confirmar a sugestão grava sem mudar nada', async () => {
    renderAba(CONTA_SUGERIDA);
    await screen.findByText('Fabricação de estruturas metálicas');

    mockPatch.mockResolvedValueOnce({ data: { codigo: '2511000' } });
    fireEvent.click(screen.getByText('Confirmar vertical'));

    await waitFor(() => expect(mockPatch).toHaveBeenCalledWith(
      '/crm/enriquecimento/cnaes/2511000',
      { vertical_id: 2, grau_risco: null, aplicar_em_contas: true },
    ));
  });

  it('trocar a sugestão muda o rótulo do botão', async () => {
    renderAba(CONTA_SUGERIDA);
    await screen.findByText('Fabricação de estruturas metálicas');

    fireEvent.change(screen.getByLabelText('Vertical'), { target: { value: '1' } });
    expect(screen.getByText('Classificar CNAE')).toBeInTheDocument();
    expect(screen.queryByText('Confirmar vertical')).not.toBeInTheDocument();

    mockPatch.mockResolvedValueOnce({ data: { codigo: '2511000' } });
    fireEvent.click(screen.getByText('Classificar CNAE'));

    await waitFor(() => expect(mockPatch).toHaveBeenCalledWith(
      '/crm/enriquecimento/cnaes/2511000',
      { vertical_id: 1, grau_risco: null, aplicar_em_contas: true },
    ));
  });

  it('avisa quando a empresa não está operando', async () => {
    renderAba({ ...CONTA_ENRIQUECIDA, situacao_cadastral: 'BAIXADA' });
    await screen.findByText('Fabricação de estruturas metálicas');
    expect(screen.getByText(/fora de operação/)).toBeInTheDocument();
  });

  it('atualizar consulta a fonte e mostra o que entrou', async () => {
    mockPost.mockResolvedValueOnce({
      data: {
        conta_id: 'c1', fonte: 'brasilapi', avisos: [],
        aplicados: { cidade: 'GUARULHOS', cep: '07190000' },
        mantidos: [], socios_novos: 0, cnaes_secundarios_novos: 0,
      },
    });
    renderAba();
    await screen.findByText('Fabricação de estruturas metálicas');

    fireEvent.click(screen.getByText('Atualizar dados públicos'));

    await waitFor(() => expect(mockPost).toHaveBeenCalledWith(
      '/crm/enriquecimento/contas/c1/aplicar',
      { forcar: true, sobrescrever: false },
    ));
    expect(await screen.findByText(/Preenchidos:/)).toBeInTheDocument();
    expect(screen.getByText(/Cidade, CEP/)).toBeInTheDocument();
  });

  it('divergência vira escolha do usuário, não sobrescrita', async () => {
    mockPost.mockResolvedValueOnce({
      data: {
        conta_id: 'c1', fonte: 'brasilapi', avisos: [], aplicados: {},
        mantidos: [{
          campo: 'razao_social',
          atual: "ORACULU'S CONTABIL LTDA",
          sugerido: 'ORACULUS CONTABIL LTDA',
          motivo: 'já preenchido',
        }],
        socios_novos: 0, cnaes_secundarios_novos: 0,
      },
    });
    renderAba();
    await screen.findByText('Fabricação de estruturas metálicas');
    fireEvent.click(screen.getByText('Atualizar dados públicos'));

    // O "não" da frase vive num <strong>, então o texto não é um nó só —
    // o matcher casa com o trecho contínuo.
    expect(await screen.findByText(/já tinham valor/)).toBeInTheDocument();
    expect(screen.getByText("ORACULU'S CONTABIL LTDA")).toBeInTheDocument();

    mockPost.mockResolvedValueOnce({
      data: {
        conta_id: 'c1', fonte: 'brasilapi', avisos: [],
        aplicados: { razao_social: 'ORACULUS CONTABIL LTDA' },
        mantidos: [], socios_novos: 0, cnaes_secundarios_novos: 0,
      },
    });
    fireEvent.click(screen.getByText('Usar os dados da fonte'));

    await waitFor(() => expect(mockPost).toHaveBeenLastCalledWith(
      '/crm/enriquecimento/contas/c1/aplicar',
      { forcar: true, sobrescrever: true },
    ));
  });

  it('número declarado pelo cliente não oferece sobrescrita', async () => {
    mockPost.mockResolvedValueOnce({
      data: {
        conta_id: 'c1', fonte: 'leadcnpj', avisos: [], aplicados: {},
        mantidos: [{
          campo: 'num_funcionarios',
          atual: '42',
          sugerido: '180',
          motivo: 'número declarado pelo cliente',
        }],
        socios_novos: 0, cnaes_secundarios_novos: 0,
      },
    });
    renderAba();
    await screen.findByText('Fabricação de estruturas metálicas');
    fireEvent.click(screen.getByText('Atualizar dados públicos'));

    expect(await screen.findByText(/declarado pelo cliente/)).toBeInTheDocument();
    // O botão de sobrescrever NÃO pode aparecer: o número do cliente é o
    // que vira proposta.
    expect(screen.queryByText('Usar os dados da fonte')).not.toBeInTheDocument();
  });

  it('conta nunca consultada mostra o estado vazio com o botão', async () => {
    renderAba({
      id: 'c1', razao_social: 'Nova LTDA', cnpj_formatado: '11.222.333/0001-81',
      enriquecida_em: null,
    });

    expect(
      await screen.findByText('Esta conta nunca foi consultada')
    ).toBeInTheDocument();
    expect(screen.getByText('Buscar dados públicos')).toBeInTheDocument();
    expect(mockPost).not.toHaveBeenCalled();
  });
});
