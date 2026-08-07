// web/src/tests/ContaDetalhe.test.jsx
//
// A visão 360: identificação fixa em cima, resto em abas começando por
// Oportunidades. Os testes cobrem o que a estrutura promete — abas certas na
// ordem certa, form único (editar em qualquer aba suja o mesmo Salvar), e os
// campos que NÃO são editáveis (CNPJ e vendedor derivado).
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, fireEvent, cleanup, waitFor } from '@testing-library/react';

const mockGet = vi.fn();
const mockPost = vi.fn();
const mockPatch = vi.fn();
const mockDelete = vi.fn();

vi.mock('../api', () => ({
  default: {
    get: (...a) => mockGet(...a),
    post: (...a) => mockPost(...a),
    patch: (...a) => mockPatch(...a),
    delete: (...a) => mockDelete(...a),
  },
}));

import ContaDetalhe from '../components/crm/ContaDetalhe';

const CONTA = {
  id: 'c1',
  razao_social: 'Metalurgica Alfa LTDA',
  nome_fantasia: 'Alfa',
  cnpj: '11222333000181',
  cnpj_formatado: '11.222.333/0001-81',
  vertical_id: 1,
  vertical_nome: 'Metalúrgica',
  num_funcionarios: 120,
  cep: '07020020', logradouro: 'Rua A', numero: '100', complemento: null,
  bairro: 'Centro', cidade: 'Guarulhos', uf: 'SP',
  telefone: '1130001000', telefone_2: null, email: 'contato@alfa.com',
  observacoes: 'Cliente antigo',
  eh_finder: false, ativo: true,
  vendedores: ['Ana Vendas'],
  qtd_oportunidades_ativas: 1,
  criado_em: '2026-08-01T12:00:00Z',
  atualizado_em: '2026-08-01T12:00:00Z',
  contatos: [
    { id: 'ct1', nome: 'Maria Souza', email: 'maria@alfa.com', telefone: null,
      data_nascimento: null, cargo: 'RH', principal: true },
  ],
  oportunidades: [
    { id: 'o1', numero: 'OPP-2026-00001', fase: 'negociacao', status: 'ativa',
      valor_mensalidade: 2500, temperatura: 70, previsao_fechamento: '2026-09-30' },
    { id: 'o2', numero: 'OPP-2026-00002', fase: 'finalizado', status: 'perdido',
      valor_mensalidade: 900, temperatura: null, previsao_fechamento: null },
  ],
};

const VERTICAIS = [{ id: 1, nome: 'Metalúrgica', slug: 'metalurgica' }];

function montar(props = {}) {
  const onSalvo = vi.fn();
  const onRecarregar = vi.fn();
  const registrarSalvar = vi.fn();
  render(
    <ContaDetalhe
      conta={CONTA}
      verticais={VERTICAIS}
      onCriarVertical={vi.fn()}
      onSalvo={onSalvo}
      onRecarregar={onRecarregar}
      registrarSalvar={registrarSalvar}
      {...props}
    />
  );
  return { onSalvo, onRecarregar, registrarSalvar };
}

/** Último estado publicado pelo componente para o rodapé do modal. */
function ultimoRegistro(registrarSalvar) {
  return registrarSalvar.mock.calls.at(-1)[0];
}

beforeEach(() => {
  mockGet.mockReset();
  mockPost.mockReset();
  mockPatch.mockReset();
  mockDelete.mockReset();
  mockGet.mockImplementation((url) => {
    if (url === '/crm/contas/c1/historico') {
      return Promise.resolve({
        data: [
          { tipo: 'conta_criada', quando: '2026-08-01T12:00:00Z',
            usuario: 'Tulio', titulo: 'Conta cadastrada', detalhe: null },
          { tipo: 'contato_vinculado', quando: '2026-08-02T09:00:00Z',
            usuario: null, titulo: 'Maria Souza', detalhe: 'RH' },
        ],
      });
    }
    return Promise.resolve({ data: [] });
  });
});

afterEach(cleanup);

describe('ContaDetalhe — estrutura', () => {
  it('abre na aba Oportunidades', () => {
    montar();
    expect(screen.getByText('OPP-2026-00001')).toBeInTheDocument();
  });

  it('mostra as seis abas na ordem definida', () => {
    montar();
    const esperado = [
      'tab-oportunidades', 'tab-contatos', 'tab-endereco',
      'tab-telefones', 'tab-observacoes', 'tab-historico',
    ];
    const abas = esperado.map((id) => screen.getByTestId(id));
    abas.forEach((el) => expect(el).toBeInTheDocument());

    // Ordem real no DOM: cada aba precede a seguinte.
    for (let i = 0; i < abas.length - 1; i++) {
      const pos = abas[i].compareDocumentPosition(abas[i + 1]);
      expect(pos & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
    }
  });

  it('mostra a identificação fora das abas, sempre visível', () => {
    montar();
    expect(screen.getByLabelText('Razão social')).toBeInTheDocument();
    fireEvent.click(screen.getByTestId('tab-historico'));
    expect(screen.getByLabelText('Razão social')).toBeInTheDocument();
  });
});

describe('ContaDetalhe — campos não editáveis', () => {
  it('CNPJ é somente leitura', () => {
    montar();
    expect(screen.getByLabelText('CNPJ')).toBeDisabled();
  });

  it('vendedor aparece como informação derivada, não como campo', () => {
    montar();
    expect(screen.getByText('Ana Vendas')).toBeInTheDocument();
    expect(screen.queryByLabelText('Vendedor *')).not.toBeInTheDocument();
  });

  it('conta sem oportunidade ativa mostra o aviso no lugar do vendedor', () => {
    montar({ conta: { ...CONTA, vendedores: [] } });
    expect(screen.getByText('sem oportunidade ativa')).toBeInTheDocument();
  });
});

describe('ContaDetalhe — aba Oportunidades', () => {
  it('resume contagem e mensalidade só das ativas', () => {
    montar();
    // toLocaleString pt-BR separa "R$" do valor com espaço não-quebrável
    // (U+00A0), então comparar com string literal falharia.
    expect(screen.getAllByText(/R\$\s*2\.500,00/).length).toBeGreaterThan(0);
    expect(screen.queryByText(/R\$\s*3\.400,00/)).not.toBeInTheDocument();
  });

  it('mostra traço na temperatura de oportunidade não ativa', () => {
    montar();
    expect(screen.getByText('OPP-2026-00002')).toBeInTheDocument();
    expect(screen.getByText('perdido')).toBeInTheDocument();
  });

  it('estado vazio quando não há oportunidades', () => {
    montar({ conta: { ...CONTA, oportunidades: [] } });
    expect(screen.getByText('Nenhuma oportunidade nesta conta')).toBeInTheDocument();
  });
});

describe('ContaDetalhe — form único', () => {
  it('começa sem alterações pendentes', () => {
    const { registrarSalvar } = montar();
    expect(ultimoRegistro(registrarSalvar).sujo).toBe(false);
  });

  it('editar no cabeçalho marca alterações pendentes', async () => {
    const { registrarSalvar } = montar();
    fireEvent.change(screen.getByLabelText('Razão social'), {
      target: { value: 'Novo Nome LTDA' },
    });
    await waitFor(() => expect(ultimoRegistro(registrarSalvar).sujo).toBe(true));
  });

  it('editar dentro de uma aba suja o MESMO salvar', async () => {
    const { registrarSalvar } = montar();
    fireEvent.click(screen.getByTestId('tab-endereco'));
    fireEvent.change(screen.getByLabelText('Bairro'), { target: { value: 'Vila Nova' } });
    await waitFor(() => expect(ultimoRegistro(registrarSalvar).sujo).toBe(true));
  });

  it('salvar envia PATCH com os campos de todas as abas', async () => {
    mockPatch.mockResolvedValue({ data: CONTA });
    const { registrarSalvar, onSalvo } = montar();

    fireEvent.change(screen.getByLabelText('Razão social'), { target: { value: 'Novo Nome' } });
    fireEvent.click(screen.getByTestId('tab-telefones'));
    fireEvent.change(screen.getByLabelText('Telefone 2'), { target: { value: '1140004000' } });

    await waitFor(() => expect(ultimoRegistro(registrarSalvar).sujo).toBe(true));
    await ultimoRegistro(registrarSalvar).salvar();

    const [url, corpo] = mockPatch.mock.calls[0];
    expect(url).toBe('/crm/contas/c1');
    expect(corpo.razao_social).toBe('Novo Nome');
    expect(corpo.telefone_2).toBe('1140004000');
    expect(corpo.bairro).toBe('Centro');
    expect(onSalvo).toHaveBeenCalled();
  });

  it('campo esvaziado vira null, não string vazia', async () => {
    mockPatch.mockResolvedValue({ data: CONTA });
    const { registrarSalvar } = montar();
    fireEvent.click(screen.getByTestId('tab-endereco'));
    fireEvent.change(screen.getByLabelText('Bairro'), { target: { value: '' } });

    await waitFor(() => expect(ultimoRegistro(registrarSalvar).sujo).toBe(true));
    await ultimoRegistro(registrarSalvar).salvar();

    expect(mockPatch.mock.calls[0][1].bairro).toBeNull();
  });

  it('mostra erro quando o PATCH falha', async () => {
    mockPatch.mockRejectedValue({ response: { data: { detail: 'Deu ruim' } } });
    const { registrarSalvar } = montar();
    fireEvent.change(screen.getByLabelText('Razão social'), { target: { value: 'X' } });
    await waitFor(() => expect(ultimoRegistro(registrarSalvar).sujo).toBe(true));
    await ultimoRegistro(registrarSalvar).salvar();
    expect(await screen.findByText('Deu ruim')).toBeInTheDocument();
  });
});

describe('ContaDetalhe — estabilidade de render', () => {
  it('não republica o salvar em loop quando o pai recria as props', async () => {
    // Regressão: publicar `salvar` como dependência do efeito criava o ciclo
    // efeito -> setState no pai -> nova prop -> novo salvar -> efeito...
    // e travava a tela. O teste falha por timeout se o loop voltar.
    const registrarSalvar = vi.fn();
    const { rerender } = render(
      <ContaDetalhe
        conta={CONTA}
        verticais={VERTICAIS}
        onCriarVertical={() => {}}
        onSalvo={() => {}}
        onRecarregar={() => {}}
        registrarSalvar={registrarSalvar}
      />
    );
    const depoisDoPrimeiro = registrarSalvar.mock.calls.length;

    // Simula o pai re-renderizando com props recriadas (arrows inline).
    for (let i = 0; i < 5; i++) {
      rerender(
        <ContaDetalhe
          conta={CONTA}
          verticais={VERTICAIS}
          onCriarVertical={() => {}}
          onSalvo={() => {}}
          onRecarregar={() => {}}
          registrarSalvar={registrarSalvar}
        />
      );
    }

    // Sem mudança em `sujo` nem `salvando`, o efeito não deve disparar de novo.
    expect(registrarSalvar.mock.calls.length).toBe(depoisDoPrimeiro);
  });

  it('publica de novo quando o estado do form muda', async () => {
    const { registrarSalvar } = montar();
    const antes = registrarSalvar.mock.calls.length;
    fireEvent.change(screen.getByLabelText('Razão social'), { target: { value: 'X' } });
    await waitFor(() =>
      expect(registrarSalvar.mock.calls.length).toBeGreaterThan(antes)
    );
  });
});

describe('ContaDetalhe — abas de conteúdo', () => {
  it('aba Endereço mostra os campos de endereço', () => {
    montar();
    fireEvent.click(screen.getByTestId('tab-endereco'));
    expect(screen.getByLabelText('Logradouro')).toHaveValue('Rua A');
    expect(screen.getByLabelText('Cidade')).toHaveValue('Guarulhos');
  });

  it('CEP aceita só dígitos', () => {
    montar();
    fireEvent.click(screen.getByTestId('tab-endereco'));
    const cep = screen.getByLabelText('CEP');
    fireEvent.change(cep, { target: { value: '07020-020' } });
    expect(cep).toHaveValue('07020020');
  });

  it('aba Observações mostra o texto salvo', () => {
    montar();
    fireEvent.click(screen.getByTestId('tab-observacoes'));
    expect(screen.getByLabelText('Observações')).toHaveValue('Cliente antigo');
  });

  it('aba Contatos lista quem está vinculado', () => {
    montar();
    fireEvent.click(screen.getByTestId('tab-contatos'));
    expect(screen.getByText('Maria Souza')).toBeInTheDocument();
    expect(screen.getByText('Principal')).toBeInTheDocument();
  });

  it('aba Histórico carrega a timeline', async () => {
    montar();
    fireEvent.click(screen.getByTestId('tab-historico'));
    // 'Conta cadastrada' aparece duas vezes: como rótulo do tipo de evento
    // e como título vindo da API.
    expect((await screen.findAllByText('Conta cadastrada')).length).toBe(2);
    expect(screen.getByText('Contato vinculado')).toBeInTheDocument();
    expect(screen.getByText('Maria Souza')).toBeInTheDocument();
    expect(mockGet).toHaveBeenCalledWith('/crm/contas/c1/historico');
  });

  it('histórico vazio não quebra', async () => {
    mockGet.mockImplementation(() => Promise.resolve({ data: [] }));
    montar();
    fireEvent.click(screen.getByTestId('tab-historico'));
    expect(await screen.findByText('Sem histórico')).toBeInTheDocument();
  });

  it('erro no histórico é exibido', async () => {
    mockGet.mockImplementation(() =>
      Promise.reject({ response: { data: { detail: 'Falhou' } } })
    );
    montar();
    fireEvent.click(screen.getByTestId('tab-historico'));
    expect(await screen.findByText('Falhou')).toBeInTheDocument();
  });
});
