// web/src/tests/AbaSocios.test.jsx
//
// O quadro societário virou aba própria. O que estes testes protegem é o
// que a aba promete: ler local ao abrir, e dizer ONDE procurou quando a
// resposta é "nenhuma outra empresa".
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, fireEvent, cleanup } from '@testing-library/react';

const mockGet = vi.fn();

vi.mock('../api', () => ({
  default: { get: (...a) => mockGet(...a) },
}));

import AbaSocios from '../components/crm/AbaSocios';

const SOCIO = {
  id: 's1',
  nome: 'JOSE DA SILVA',
  documento_mascarado: '***456789**',
  qualificacao: '49-Sócio-Administrador',
  faixa_etaria: 'Entre 41 a 50 anos',
  entrada_em: '2009-03-17',
  eh_pj: false,
  fonte: 'brasilapi',
  capturado_em: '2026-09-20T12:00:00Z',
};

const CONTA = {
  id: 'c1',
  razao_social: 'Metalurgica Alfa LTDA',
  enriquecida_em: '2026-09-20T12:00:00Z',
};

function renderAba(conta = CONTA) {
  return render(<AbaSocios conta={conta} />);
}

beforeEach(() => {
  mockGet.mockReset();
  mockGet.mockImplementation((url) => {
    if (url.endsWith('/socios')) return Promise.resolve({ data: [SOCIO] });
    return Promise.resolve({ data: { empresas: [], avisos: [] } });
  });
});

afterEach(cleanup);

describe('AbaSocios', () => {
  it('lê os sócios do HIPO, sem ir à fonte externa', async () => {
    renderAba();
    await screen.findByText('JOSE DA SILVA');

    expect(mockGet).toHaveBeenCalledTimes(1);
    expect(mockGet.mock.calls[0][0]).toBe('/crm/enriquecimento/contas/c1/socios');
  });

  it('mostra o documento mascarado, nunca o CPF inteiro', async () => {
    renderAba();
    await screen.findByText('JOSE DA SILVA');

    expect(screen.getByText('***456789**')).toBeInTheDocument();
    // A trava: nenhum bloco de 11 dígitos seguidos na tela.
    expect(document.body.textContent).not.toMatch(/\d{11}/);
  });

  it('conta quantos sócios são', async () => {
    renderAba();
    expect(await screen.findByText(/1 sócio registrado/)).toBeInTheDocument();
  });

  it('busca outras empresas do sócio e mostra a confiança', async () => {
    renderAba();
    await screen.findByText('JOSE DA SILVA');

    mockGet.mockImplementationOnce(() => Promise.resolve({
      data: {
        nome: 'JOSE DA SILVA',
        avisos: ['Busca externa de sócio não configurada.'],
        empresas: [{
          conta_id: 'c2', razao_social: 'Beta Servicos LTDA',
          cnpj_formatado: '34.028.316/0001-03', qualificacao: 'Sócio',
          entrada_em: null, confianca: 'alta', externa: false,
        }],
      },
    }));

    fireEvent.click(screen.getByText('Outras empresas'));

    expect(await screen.findByText('Beta Servicos LTDA')).toBeInTheDocument();
    expect(screen.getByText('nome e documento batem')).toBeInTheDocument();
    // O aviso é obrigatório: sem ele, "nenhuma outra empresa" seria lido
    // como "não existe" em vez de "não procurei fora daqui".
    expect(
      screen.getByText('Busca externa de sócio não configurada.')
    ).toBeInTheDocument();
  });

  it('a busca exclui a própria conta', async () => {
    renderAba();
    await screen.findByText('JOSE DA SILVA');
    fireEvent.click(screen.getByText('Outras empresas'));

    const chamada = mockGet.mock.calls.find(
      ([u]) => u === '/crm/enriquecimento/socios/empresas'
    );
    expect(chamada[1].params.excluir_conta_id).toBe('c1');
    expect(chamada[1].params.nome).toBe('JOSE DA SILVA');
  });

  it('sem sócios E já consultada explica que a Receita não tem o quadro', async () => {
    mockGet.mockImplementation(() => Promise.resolve({ data: [] }));
    renderAba();

    // Empresário individual e MEI não têm QSA. Dizer só "sem sócios"
    // faria parecer defeito do sistema num dado que não existe.
    expect(
      await screen.findByText('A Receita não tem quadro societário para este CNPJ')
    ).toBeInTheDocument();
  });

  it('sem sócios E nunca consultada manda consultar', async () => {
    mockGet.mockImplementation(() => Promise.resolve({ data: [] }));
    renderAba({ ...CONTA, enriquecida_em: null });

    expect(
      await screen.findByText('Sem sócios registrados')
    ).toBeInTheDocument();
    expect(screen.getByText(/aba Dados públicos/)).toBeInTheDocument();
  });

  it('erro na leitura não derruba a aba', async () => {
    mockGet.mockImplementation(() => Promise.reject({
      response: { status: 500, data: { detail: 'Banco fora do ar.' } },
    }));
    renderAba();

    expect(await screen.findByText('Banco fora do ar.')).toBeInTheDocument();
  });
});
