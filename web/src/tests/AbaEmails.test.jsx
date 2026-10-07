// web/src/tests/AbaEmails.test.jsx
//
// E-mail comercial dentro da oportunidade (050).
//
// O que os testes seguram:
//   1. o painel conta da MESMA lista que aparece embaixo
//   2. o rascunho vem do servidor, já preenchido, para o contato principal
//   3. o que vai no envio é o texto da tela (editado), e não o modelo
//   4. editar e depois trocar de modelo NÃO apaga a edição — avisa
//   5. {{variável}} sobrando trava o envio
//   6. vindo da proposta, abre com o modelo de proposta e a versão escolhida
//   7. Gmail desligado: a tela diz, e "Novo e-mail" fica desabilitado
//   8. só a gestão vê o editor de modelos
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, fireEvent, cleanup, waitFor, within } from '@testing-library/react';

const mockGet = vi.fn();
const mockPost = vi.fn();
const mockPut = vi.fn();

vi.mock('../api', () => ({
  default: {
    get: (...a) => mockGet(...a),
    post: (...a) => mockPost(...a),
    put: (...a) => mockPut(...a),
  },
}));

import AbaEmails, {
  emailValido, diasDesde, resumoEmails, CampoEnderecos,
} from '../components/crm/AbaEmails';

const OPP = { id: 'o1', numero: 'OPP-2026-00001', conta_id: 'c1' };
const AGORA = new Date('2026-10-10T15:00:00Z');

const MODELOS = [
  { slug: 'primeiro_contato', nome: 'Primeiro contato', assunto: 'Medicina Ocupacional',
    corpo: 'Olá, {{contato_primeiro_nome}}', anexa_proposta: false, ordem: 1 },
  { slug: 'proposta', nome: 'Envio de proposta', assunto: 'Proposta {{empresa}}',
    corpo: '{{saudacao}}', anexa_proposta: true, ordem: 2 },
];

function config(troca = {}) {
  return {
    modelos: MODELOS,
    variaveis: [{ nome: 'contato_primeiro_nome', rotulo: 'Primeiro nome', exemplo: 'Ana' }],
    gmail: { ligado: true, problemas: [], remetente: 'gabriel@controllermedseg.com' },
    pode_editar: false,
    pdf_disponivel: true,
    ...troca,
  };
}

const CONTATOS = [
  { id: 'k2', nome: 'Rita RH', email: 'rita@cliente.com', principal: false },
  { id: 'k1', nome: 'Nivaldo', email: 'nivaldo@cliente.com', principal: true },
];

const VERSOES = [
  { id: 'p2', versao: 2, cliente_razao_social: 'NN LTDA', itens: [{ id: 'i1', razao_social: 'NN LTDA' }],
    aprovada_em: '2026-10-07T12:00:00Z' },
  { id: 'p1', versao: 1, cliente_razao_social: 'NN LTDA', itens: [{ id: 'i0', razao_social: 'NN LTDA' }],
    aprovada_em: '2026-10-06T12:00:00Z' },
];

const ENVIADO = {
  id: 'e1', oportunidade_id: 'o1', contato_id: 'k1', contato_nome: 'Nivaldo',
  modelo_slug: 'primeiro_contato', modelo_nome: 'Primeiro contato',
  proposta_id: null, proposta_versao: null, anexo_nome: null,
  remetente_id: 'u1', remetente_nome: 'Gabriel Lira', remetente_email: 'gabriel@controllermedseg.com',
  para: ['nivaldo@cliente.com'], cc: [], assunto: 'Medicina Ocupacional', corpo: 'Olá',
  com_assinatura: true, gmail_thread_id: 'f1', enviado_em: '2026-10-05T15:00:00Z',
  respondido_em: null, resposta_de: null, verificado_em: null, verificacao_erro: null,
};

function rascunho(troca = {}) {
  return {
    modelo: 'primeiro_contato', para: ['nivaldo@cliente.com'],
    assunto: 'Medicina Ocupacional', corpo: 'Olá, Nivaldo, tudo bem?',
    anexo_nome: null, assinatura: true, avisos: [], ...troca,
  };
}

function montarGets({ emails = [], cfg = config(), contatos = CONTATOS, versoes = VERSOES } = {}) {
  mockGet.mockImplementation((url) => {
    if (url === '/crm/oportunidades/o1/emails') return Promise.resolve({ data: emails });
    if (url === '/crm/email/modelos') return Promise.resolve({ data: cfg });
    if (url === '/crm/contatos/por-alvo') return Promise.resolve({ data: contatos });
    if (url === '/crm/oportunidades/o1/propostas') return Promise.resolve({ data: versoes });
    return Promise.reject(new Error(`GET inesperado: ${url}`));
  });
}

beforeEach(() => {
  mockGet.mockReset();
  mockPost.mockReset();
  mockPut.mockReset();
});
afterEach(cleanup);

describe('funções puras', () => {
  it('valida e-mail', () => {
    expect(emailValido('a@b.com')).toBe(true);
    expect(emailValido('a@b')).toBe(false);
    expect(emailValido('Ana <a@b.com>')).toBe(false);
  });

  it('conta dias corridos', () => {
    expect(diasDesde('2026-10-05T15:00:00Z', AGORA)).toBe(5);
    expect(diasDesde(null, AGORA)).toBe(null);
  });

  it('resumo sai da mesma lista', () => {
    const r = resumoEmails([
      ENVIADO,
      { ...ENVIADO, id: 'e2', enviado_em: '2026-10-09T15:00:00Z' },
      { ...ENVIADO, id: 'e3', respondido_em: '2026-10-06T10:00:00Z' },
    ], AGORA);
    expect(r).toEqual({ total: 3, respondidos: 1, semResposta: 2, ultimoSem: 1 });
  });
});

describe('CampoEnderecos', () => {
  it('vira chip no Enter, recusa inválido e não repete', () => {
    const onChange = vi.fn();
    const { rerender } = render(
      <CampoEnderecos id="x" label="Para" valores={[]} onChange={onChange} />,
    );
    const campo = screen.getByLabelText('Para');
    fireEvent.change(campo, { target: { value: 'ana@x' } });
    fireEvent.keyDown(campo, { key: 'Enter' });
    expect(screen.getByText(/Endereço inválido/)).toBeInTheDocument();
    expect(onChange).not.toHaveBeenCalled();

    fireEvent.change(campo, { target: { value: 'ana@x.com, ANA@x.com' } });
    fireEvent.keyDown(campo, { key: 'Enter' });
    expect(onChange).toHaveBeenCalledWith(['ana@x.com']);

    rerender(<CampoEnderecos id="x" label="Para" valores={['ana@x.com']} onChange={onChange} />);
    fireEvent.click(screen.getByLabelText('Tirar ana@x.com'));
    expect(onChange).toHaveBeenLastCalledWith([]);
  });
});

describe('AbaEmails', () => {
  it('mostra o painel e a lista', async () => {
    montarGets({ emails: [ENVIADO, { ...ENVIADO, id: 'e2', respondido_em: '2026-10-06T10:00:00Z' }] });
    render(<AbaEmails oportunidade={OPP} agora={AGORA} />);
    expect(await screen.findByTestId('kpi-enviados')).toHaveTextContent('2');
    expect(screen.getByTestId('kpi-respondidos')).toHaveTextContent('1');
    expect(screen.getByTestId('kpi-sem-resposta')).toHaveTextContent('1');
    expect(screen.getByText(/Sem resposta · há 5 dias/)).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /Ver se respondeu/ })).toBeInTheDocument();
  });

  it('rascunho preenchido para o principal e envio do texto editado', async () => {
    montarGets();
    mockPost.mockImplementation((url, corpo) => {
      if (url.endsWith('/rascunho')) return Promise.resolve({ data: rascunho() });
      return Promise.resolve({ data: { ...ENVIADO, corpo: corpo.corpo } });
    });
    render(<AbaEmails oportunidade={OPP} agora={AGORA} />);
    fireEvent.click(await screen.findByRole('button', { name: 'Novo e-mail' }));

    await waitFor(() => expect(screen.getByLabelText('Texto')).toHaveValue('Olá, Nivaldo, tudo bem?'));
    expect(mockPost).toHaveBeenCalledWith('/crm/oportunidades/o1/emails/rascunho', {
      modelo: 'primeiro_contato', contato_id: 'k1', proposta_id: null, proposta_item_id: null,
    });
    expect(screen.getByText('nivaldo@cliente.com', { selector: 'span' })).toBeInTheDocument();

    fireEvent.change(screen.getByLabelText('Texto'), { target: { value: 'Texto meu.' } });
    fireEvent.click(screen.getByRole('button', { name: /Enviar para nivaldo@cliente.com/ }));

    await waitFor(() => expect(mockPost).toHaveBeenCalledWith('/crm/oportunidades/o1/emails', {
      contato_id: 'k1', para: ['nivaldo@cliente.com'], cc: [],
      assunto: 'Medicina Ocupacional', corpo: 'Texto meu.',
      modelo: 'primeiro_contato', proposta_id: null, proposta_item_id: null,
    }));
    expect(await screen.findByText(/E-mail enviado para nivaldo@cliente.com/)).toBeInTheDocument();
    expect(screen.queryByRole('region', { name: 'Novo e-mail' })).not.toBeInTheDocument();
  });

  it('editar e trocar de modelo não apaga a edição', async () => {
    montarGets();
    mockPost.mockResolvedValue({ data: rascunho() });
    render(<AbaEmails oportunidade={OPP} agora={AGORA} />);
    fireEvent.click(await screen.findByRole('button', { name: 'Novo e-mail' }));
    await waitFor(() => expect(screen.getByLabelText('Texto')).toHaveValue('Olá, Nivaldo, tudo bem?'));

    fireEvent.change(screen.getByLabelText('Texto'), { target: { value: 'Meu texto' } });
    const chamadas = mockPost.mock.calls.length;
    fireEvent.change(screen.getByLabelText('Contato'), { target: { value: 'k2' } });

    expect(await screen.findByText(/o rascunho não foi refeito/)).toBeInTheDocument();
    expect(screen.getByLabelText('Texto')).toHaveValue('Meu texto');
    expect(mockPost.mock.calls.length).toBe(chamadas);
  });

  it('variável sobrando trava o envio', async () => {
    montarGets();
    mockPost.mockResolvedValue({ data: rascunho() });
    render(<AbaEmails oportunidade={OPP} agora={AGORA} />);
    fireEvent.click(await screen.findByRole('button', { name: 'Novo e-mail' }));
    await waitFor(() => expect(screen.getByLabelText('Texto')).toHaveValue('Olá, Nivaldo, tudo bem?'));
    fireEvent.change(screen.getByLabelText('Texto'), { target: { value: 'Olá {{contato_nome}}' } });
    expect(screen.getByText(/o cliente veria as chaves/)).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /Enviar para/ })).toBeDisabled();
  });

  it('avisos do rascunho aparecem', async () => {
    montarGets();
    mockPost.mockResolvedValue({ data: rascunho({ avisos: ['Você não tem assinatura configurada no Gmail.'] }) });
    render(<AbaEmails oportunidade={OPP} agora={AGORA} />);
    fireEvent.click(await screen.findByRole('button', { name: 'Novo e-mail' }));
    expect(await screen.findByText('Você não tem assinatura configurada no Gmail.')).toBeInTheDocument();
  });

  it('vindo da proposta abre com o modelo e a versão escolhida', async () => {
    montarGets();
    mockPost.mockResolvedValue({ data: rascunho({ anexo_nome: 'OPP_v1.pdf' }) });
    const usado = vi.fn();
    render(
      <AbaEmails
        oportunidade={OPP}
        agora={AGORA}
        preset={{ modelo: 'proposta', proposta_id: 'p1', proposta_item_id: null }}
        onPresetUsado={usado}
      />,
    );
    await waitFor(() => expect(mockPost).toHaveBeenCalledWith('/crm/oportunidades/o1/emails/rascunho', {
      modelo: 'proposta', contato_id: 'k1', proposta_id: 'p1', proposta_item_id: null,
    }));
    expect(usado).toHaveBeenCalled();
    expect(screen.getByLabelText('Modelo')).toHaveValue('proposta');
    expect(await screen.findByText('OPP_v1.pdf')).toBeInTheDocument();
  });

  it('modelo de proposta escolhe a versão mais nova sozinho', async () => {
    montarGets();
    mockPost.mockResolvedValue({ data: rascunho() });
    render(<AbaEmails oportunidade={OPP} agora={AGORA} />);
    fireEvent.click(await screen.findByRole('button', { name: 'Novo e-mail' }));
    await waitFor(() => expect(mockPost).toHaveBeenCalled());
    fireEvent.change(screen.getByLabelText('Modelo'), { target: { value: 'proposta' } });
    await waitFor(() => expect(mockPost).toHaveBeenLastCalledWith(
      '/crm/oportunidades/o1/emails/rascunho',
      { modelo: 'proposta', contato_id: 'k1', proposta_id: 'p2', proposta_item_id: null },
    ));
  });

  it('só proposta aprovada aparece para anexar (051)', async () => {
    montarGets({ versoes: [
      { ...VERSOES[0], id: 'p3', versao: 3, aprovada_em: null },
      ...VERSOES,
    ] });
    mockPost.mockResolvedValue({ data: rascunho() });
    render(<AbaEmails oportunidade={OPP} agora={AGORA} />);
    fireEvent.click(await screen.findByRole('button', { name: 'Novo e-mail' }));
    await waitFor(() => expect(mockPost).toHaveBeenCalled());
    fireEvent.change(screen.getByLabelText('Modelo'), { target: { value: 'proposta' } });
    // A mais nova APROVADA é a v2 — a v3 espera o ok do EV.
    await waitFor(() => expect(mockPost).toHaveBeenLastCalledWith(
      '/crm/oportunidades/o1/emails/rascunho',
      { modelo: 'proposta', contato_id: 'k1', proposta_id: 'p2', proposta_item_id: null },
    ));
    const opcoes = [...screen.getByLabelText('Proposta anexada').options].map((o) => o.textContent);
    expect(opcoes.some((t) => t.startsWith('v3'))).toBe(false);
  });

  it('sem proposta aprovada, diz o que fazer', async () => {
    montarGets({ versoes: [{ ...VERSOES[0], aprovada_em: null }] });
    mockPost.mockResolvedValue({ data: rascunho() });
    render(<AbaEmails oportunidade={OPP} agora={AGORA} />);
    fireEvent.click(await screen.findByRole('button', { name: 'Novo e-mail' }));
    fireEvent.change(await screen.findByLabelText('Modelo'), { target: { value: 'proposta' } });
    expect(await screen.findByText(/esperando aprovação/)).toBeInTheDocument();
    expect(screen.getByText('Nenhuma proposta aprovada')).toBeInTheDocument();
  });

  it('erro do envio aparece e o rascunho continua', async () => {
    montarGets();
    mockPost.mockImplementation((url) => {
      if (url.endsWith('/rascunho')) return Promise.resolve({ data: rascunho() });
      return Promise.reject({ response: { data: { detail: 'O Google recusou o acesso ao Gmail.' } } });
    });
    render(<AbaEmails oportunidade={OPP} agora={AGORA} />);
    fireEvent.click(await screen.findByRole('button', { name: 'Novo e-mail' }));
    await waitFor(() => expect(screen.getByLabelText('Texto')).toHaveValue('Olá, Nivaldo, tudo bem?'));
    fireEvent.click(screen.getByRole('button', { name: /Enviar para/ }));
    expect(await screen.findByText('O Google recusou o acesso ao Gmail.')).toBeInTheDocument();
    expect(screen.getByLabelText('Texto')).toHaveValue('Olá, Nivaldo, tudo bem?');
  });

  it('Gmail desligado: avisa e desabilita', async () => {
    montarGets({ cfg: config({ gmail: { ligado: false, problemas: ['GOOGLE_SA_ARQUIVO vazio.'], remetente: 'x' } }) });
    render(<AbaEmails oportunidade={OPP} agora={AGORA} />);
    expect(await screen.findByText(/envio pelo Gmail está desligado/)).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Novo e-mail' })).toBeDisabled();
  });

  it('ver se respondeu atualiza a lista', async () => {
    montarGets({ emails: [ENVIADO] });
    mockPost.mockResolvedValue({ data: { verificados: 1, respondidos: 1, erros: [] } });
    render(<AbaEmails oportunidade={OPP} agora={AGORA} />);
    fireEvent.click(await screen.findByRole('button', { name: /Ver se respondeu/ }));
    expect(await screen.findByText('1 resposta nova.')).toBeInTheDocument();
    expect(mockPost).toHaveBeenCalledWith('/crm/oportunidades/o1/emails/verificar', {});
  });

  it('editor de modelos só para a gestão, e salva', async () => {
    montarGets({ cfg: config({ pode_editar: true }) });
    mockPut.mockResolvedValue({ data: { ...MODELOS[0], assunto: 'Novo assunto' } });
    render(<AbaEmails oportunidade={OPP} agora={AGORA} />);
    fireEvent.click(await screen.findByRole('button', { name: /Modelos de e-mail/ }));
    const secao = screen.getByRole('region', { name: 'Modelos de e-mail' });
    fireEvent.change(within(secao).getByLabelText('Assunto'), { target: { value: 'Novo assunto' } });
    fireEvent.click(within(secao).getByText('{{contato_primeiro_nome}}'));
    fireEvent.click(within(secao).getByRole('button', { name: /Salvar modelo/ }));
    await waitFor(() => expect(mockPut).toHaveBeenCalledWith('/crm/email/modelos/primeiro_contato', {
      nome: 'Primeiro contato', assunto: 'Novo assunto',
      corpo: 'Olá, {{contato_primeiro_nome}}{{contato_primeiro_nome}}',
    }));
    expect(await within(secao).findByText(/Modelo salvo/)).toBeInTheDocument();
  });

  it('operacional não vê o editor', async () => {
    montarGets();
    render(<AbaEmails oportunidade={OPP} agora={AGORA} />);
    await screen.findByTestId('kpi-enviados');
    expect(screen.queryByRole('button', { name: /Modelos de e-mail/ })).not.toBeInTheDocument();
  });
});
