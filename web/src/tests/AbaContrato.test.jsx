// web/src/tests/AbaContrato.test.jsx
//
// Contrato pela Autentique dentro da oportunidade (053).
//
// O que os testes seguram:
//   1. o painel mostra quantos assinaram e DE QUEM É A VEZ (a próxima tarefa)
//   2. vindo do botão "Contrato" da proposta, abre o formulário daquela versão
//   3. o envio manda os três signatários da tela (a contratada é do servidor)
//   4. e-mail repetido ou endereço incompleto travam o envio, dizendo por quê
//   5. "Reenviar" vai para quem é a vez; cancelar exige motivo
//   6. desligado no servidor: a tela diz, e "Novo contrato" fica desabilitado
//   7. sem proposta aprovada, não há como começar
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, fireEvent, cleanup, waitFor, within } from '@testing-library/react';

const mockGet = vi.fn();
const mockPost = vi.fn();

vi.mock('../api', () => ({
  default: {
    get: (...a) => mockGet(...a),
    post: (...a) => mockPost(...a),
  },
}));

import AbaContrato, { resumoContrato, contratoAtual } from '../components/crm/AbaContrato';

const OPP = { id: 'o1', numero: 'OPP-2026-00001', conta_id: 'c1' };
const AGORA = new Date('2026-10-10T15:00:00Z');

const SITUACAO = { configurado: true, problemas: [], sandbox: false, previa_disponivel: true };
const PROPOSTAS = [
  { id: 'p2', versao: 2, aprovada_em: '2026-10-07T12:00:00Z' },
  { id: 'p1', versao: 1, aprovada_em: null },
];

function sig(ordem, papel, papel_rotulo, nome, situacao, extra = {}) {
  return {
    id: `s${ordem}`, ordem, papel, papel_rotulo, nome, email: `${nome.split(' ')[0].toLowerCase()}@x.com`,
    acao: papel.startsWith('testemunha') ? 'SIGN_AS_A_WITNESS' : 'SIGN', situacao,
    visualizado_em: null, assinado_em: null, recusado_em: null, motivo_recusa: null,
    reenviado_em: null, da_vez: false, ...extra,
  };
}

function contrato(troca = {}) {
  return {
    id: 'k1', oportunidade_id: 'o1', proposta_id: 'p2', proposta_versao: 2, versao: 1,
    status: 'enviado', sandbox: false, nome_documento: 'Contrato Controller MedSeg - NN',
    data_contrato: '2026-10-05', inicio_vigencia: '2026-10-06', dia_vencimento: 10,
    hash_original: 'a'.repeat(64), tem_assinado: false, assinado_em: null, recusado_em: null,
    cancelado_em: null, cancelado_por_nome: null, motivo_cancelamento: null,
    sincronizado_em: null, sincronizacao_erro: null, criado_por_nome: 'Jakeline',
    criado_em: '2026-10-05T12:00:00Z',
    signatarios: [
      sig(1, 'contratante', 'Contratante', 'Eladir Quadros', 'assinado',
        { assinado_em: '2026-10-07T15:00:00Z' }),
      sig(2, 'testemunha_contratante', 'Testemunha da contratante', 'Ana RH', 'visualizado',
        { da_vez: true, visualizado_em: '2026-10-08T10:00:00Z' }),
      sig(3, 'contratada', 'Contratada', 'Marcelo Canton Dick', 'pendente'),
      sig(4, 'testemunha_contratada', 'Testemunha da contratada', 'Bruno Gonçalo', 'pendente'),
    ],
    eventos: [{ id: 'e1', tipo: 'enviado', origem: 'hipo', descricao: 'Contrato v1 enviado',
      usuario_nome: 'Jakeline', criado_em: '2026-10-05T12:00:00Z' }],
    assinados: 1, total_signatarios: 4, proximo_nome: 'Ana RH', pode_cancelar: true,
    ...troca,
  };
}

const PADRAO = {
  proposta_id: 'p2', proposta_versao: 2, aprovada: true, oportunidade_aberta: true,
  cliente_razao_social: 'NN LTDA', cliente_cnpj: '11.222.333/0001-81',
  endereco: 'Rua A, 1, Centro – Guarulhos - SP, CEP: 07000-000', pendencias_endereco: [],
  conta_id: 'c1', contratada_nome: 'Marcelo Canton Dick',
  contratada_email: 'marcelod@controllermedseg.com.br',
  data_contrato: '2026-10-10', inicio_vigencia: '2026-10-11', dia_vencimento: 10,
  contatos: [
    { id: 'k1', nome: 'Eladir Quadros', email: 'eladir@cliente.com', detalhe: 'Diretor · decisor' },
    { id: 'k2', nome: 'Ana RH', email: 'ana@cliente.com', detalhe: 'RH' },
  ],
  usuarios: [
    { id: 'u1', nome: 'Bruno Gonçalo', email: 'bruno@controllermedseg.com.br', detalhe: 'EV' },
  ],
  sugestao_contratante_id: 'k1', sugestao_testemunha_contratada_id: 'u1',
  contrato_em_aberto_id: null,
  linhas_preco: ['CNPJs até 05 funcionários registrados – R$ 180,00 mensais;'],
  grupos: [{
    raiz: '11222333', principal: true, contratante_razao_social: 'NN LTDA',
    contratante_cnpj: '11.222.333/0001-81', conta_id: 'c1',
    endereco: 'Rua A, 1, Centro – Guarulhos - SP, CEP: 07000-000', pendencias_endereco: [],
    cnpjs: [{ cnpj: '11222333000181', cnpj_formatado: '11.222.333/0001-81', razao_social: 'NN LTDA',
      vidas: 4, mensalidade: '180.00' }],
    linhas_preco: ['CNPJs até 05 funcionários registrados – R$ 180,00 mensais;'],
    contrato_em_aberto_id: null, substitui: [],
  }],
  servicos_catalogo: [
    { chave: 'ppp', texto: 'Elaboração do PPP' },
    { chave: 'cipa', texto: 'CIPA (NR-05)' },
  ],
  servicos_sugeridos: ['cipa'],
};

function montarGets({ contratos = [], situacao = SITUACAO, propostas = PROPOSTAS, padrao = PADRAO } = {}) {
  mockGet.mockImplementation((url) => {
    if (url === '/crm/contratos/situacao') return Promise.resolve({ data: situacao });
    if (url === '/crm/oportunidades/o1/contratos') return Promise.resolve({ data: contratos });
    if (url === '/crm/oportunidades/o1/propostas') return Promise.resolve({ data: propostas });
    if (url === '/crm/propostas/p2/contrato-padrao') return Promise.resolve({ data: padrao });
    return Promise.reject(new Error(`GET inesperado: ${url}`));
  });
}

beforeEach(() => {
  mockGet.mockReset();
  mockPost.mockReset();
});
afterEach(cleanup);

describe('funções puras', () => {
  it('o atual é o em andamento; senão o mais recente', () => {
    const velho = contrato({ id: 'a', status: 'cancelado' });
    const novo = contrato({ id: 'b' });
    expect(contratoAtual([velho, novo]).id).toBe('b');
    expect(contratoAtual([contrato({ id: 'c', status: 'assinado' }), velho]).id).toBe('c');
    expect(contratoAtual([])).toBe(null);
  });

  it('resumo: quem é a vez e há quanto tempo está parado', () => {
    const r = resumoContrato(contrato(), AGORA);
    expect(r.assinados).toBe(1);
    expect(r.vez.nome).toBe('Ana RH');
    // Parado desde a última assinatura (07/10), não desde o envio.
    expect(r.paradoDias).toBe(3);
  });
});

describe('painel', () => {
  it('mostra assinaturas e de quem é a vez', async () => {
    montarGets({ contratos: [contrato()] });
    render(<AbaContrato oportunidade={OPP} agora={AGORA} />);
    expect(await screen.findByTestId('kpi-assinaturas')).toHaveTextContent('1 de 4');
    expect(screen.getByTestId('kpi-vez')).toHaveTextContent('Ana RH');
    expect(screen.getByTestId('kpi-vez')).toHaveTextContent('parado há 3 dias');
    // 055: com um em andamento ainda dá para abrir o formulário — a outra
    // empresa da proposta pode ir; a mesma é barrada no formulário.
    expect(screen.getByRole('button', { name: /Novo contrato/ })).not.toBeDisabled();
  });

  it('desligado no servidor: avisa e não deixa começar', async () => {
    montarGets({ situacao: { ...SITUACAO, configurado: false,
      problemas: ['AUTENTIQUE_API_TOKEN não configurado no .env'] } });
    render(<AbaContrato oportunidade={OPP} agora={AGORA} />);
    expect(await screen.findByText(/AUTENTIQUE_API_TOKEN/)).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /Novo contrato/ })).toBeDisabled();
  });

  it('sem proposta aprovada: explica o caminho', async () => {
    montarGets({ propostas: [{ id: 'p1', versao: 1, aprovada_em: null }] });
    render(<AbaContrato oportunidade={OPP} agora={AGORA} />);
    expect(await screen.findByText(/versão APROVADA da proposta/)).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /Novo contrato/ })).toBeDisabled();
  });
});

describe('envio', () => {
  it('vindo da proposta: abre o formulário com as sugestões e envia', async () => {
    montarGets();
    const onPresetUsado = vi.fn();
    mockPost.mockResolvedValue({ data: contrato({ assinados: 0 }) });
    render(<AbaContrato oportunidade={OPP} agora={AGORA}
      preset={{ proposta_id: 'p2' }} onPresetUsado={onPresetUsado} />);

    const form = await screen.findByRole('region', { name: 'Novo contrato' });
    expect(onPresetUsado).toHaveBeenCalled();
    await waitFor(() => expect(within(form).getByLabelText('Nome', { selector: '#contratante-nome' }))
      .toHaveValue('Eladir Quadros'));
    expect(within(form).getByText('Marcelo Canton Dick')).toBeInTheDocument();
    expect(within(form).getByText(/R\$ 180,00 mensais/)).toBeInTheDocument();

    const enviar = within(form).getByRole('button', { name: /Enviar para assinatura/ });
    // Falta a testemunha da contratante.
    expect(enviar).toBeDisabled();
    fireEvent.change(form.querySelector('#test-contratante-origem'), { target: { value: 'k2' } });
    expect(enviar).not.toBeDisabled();
    fireEvent.click(enviar);

    await waitFor(() => expect(mockPost).toHaveBeenCalled());
    const [url, corpo] = mockPost.mock.calls[0];
    expect(url).toBe('/crm/propostas/p2/contratos');
    expect(corpo.signatarios).toEqual([
      { papel: 'contratante', nome: 'Eladir Quadros', email: 'eladir@cliente.com', contato_id: 'k1' },
      { papel: 'testemunha_contratante', nome: 'Ana RH', email: 'ana@cliente.com', contato_id: 'k2' },
      { papel: 'testemunha_contratada', nome: 'Bruno Gonçalo',
        email: 'bruno@controllermedseg.com.br', usuario_id: 'u1' },
    ]);
    expect(corpo.dia_vencimento).toBe(10);
    expect(corpo.raiz_cnpj).toBe('11222333');
    expect(corpo.servicos).toEqual(['cipa']);
    expect(corpo.servicos_livres).toEqual([]);
    expect(await screen.findByText(/Contrato enviado/)).toBeInTheDocument();
  });

  it('e-mail repetido trava e diz por quê', async () => {
    montarGets();
    render(<AbaContrato oportunidade={OPP} agora={AGORA} preset={{ proposta_id: 'p2' }} />);
    const form = await screen.findByRole('region', { name: 'Novo contrato' });
    await waitFor(() => expect(form.querySelector('#contratante-nome')).toHaveValue('Eladir Quadros'));
    fireEvent.change(form.querySelector('#test-contratante-origem'), { target: { value: 'k1' } });
    expect(within(form).getByRole('status')).toHaveTextContent(/pessoa diferente/);
    expect(within(form).getByRole('button', { name: /Enviar para assinatura/ })).toBeDisabled();
  });

  it('endereço incompleto trava o envio e a prévia', async () => {
    montarGets({ padrao: { ...PADRAO, grupos: [{ ...PADRAO.grupos[0],
      pendencias_endereco: ['número', 'CEP'] }] } });
    render(<AbaContrato oportunidade={OPP} agora={AGORA} preset={{ proposta_id: 'p2' }} />);
    const form = await screen.findByRole('region', { name: 'Novo contrato' });
    expect(await within(form).findByText(/falta: número, CEP/)).toBeInTheDocument();
    expect(within(form).getByRole('button', { name: /Prévia do PDF/ })).toBeDisabled();
    expect(within(form).getByRole('button', { name: /Enviar para assinatura/ })).toBeDisabled();
  });
});

describe('ações', () => {
  it('reenviar vai para quem é a vez', async () => {
    montarGets({ contratos: [contrato()] });
    mockPost.mockResolvedValue({ data: contrato() });
    render(<AbaContrato oportunidade={OPP} agora={AGORA} />);
    fireEvent.click(await screen.findByRole('button', { name: /Reenviar para Ana/ }));
    await waitFor(() => expect(mockPost).toHaveBeenCalledWith('/crm/contratos/k1/reenviar', {}));
  });

  it('cancelar exige motivo', async () => {
    montarGets({ contratos: [contrato()] });
    mockPost.mockResolvedValue({ data: contrato({ status: 'cancelado', pode_cancelar: false,
      cancelado_em: '2026-10-10T12:00:00Z', motivo_cancelamento: 'refazer' }) });
    render(<AbaContrato oportunidade={OPP} agora={AGORA} />);
    fireEvent.click(await screen.findByRole('button', { name: /^Cancelar$/ }));
    const confirmar = screen.getByRole('button', { name: 'Cancelar contrato' });
    expect(confirmar).toBeDisabled();
    fireEvent.change(screen.getByLabelText('Por que cancelar?'), { target: { value: 'refazer' } });
    fireEvent.click(confirmar);
    await waitFor(() => expect(mockPost).toHaveBeenCalledWith(
      '/crm/contratos/k1/cancelar', { motivo: 'refazer' }));
    expect(await screen.findByTestId('kpi-situacao')).toHaveTextContent('Cancelado');
  });

  it('assinado: oferece o PDF assinado e não cancela', async () => {
    montarGets({ contratos: [contrato({
      status: 'assinado', pode_cancelar: false, assinados: 4, proximo_nome: null,
      signatarios: contrato().signatarios.map((s) => ({ ...s, situacao: 'assinado', da_vez: false })),
    })] });
    render(<AbaContrato oportunidade={OPP} agora={AGORA} />);
    expect(await screen.findByRole('button', { name: /Contrato assinado/ })).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /^Cancelar$/ })).not.toBeInTheDocument();
    expect(screen.getByTestId('kpi-assinaturas')).toHaveTextContent('4 de 4');
  });
});


describe('aviso ao faturamento (054)', () => {
  const assinado = (troca = {}) => contrato({
    status: 'assinado', pode_cancelar: false, pode_reenviar_aviso: true, assinados: 4,
    proximo_nome: null,
    signatarios: contrato().signatarios.map((s) => ({ ...s, situacao: 'assinado', da_vez: false })),
    ...troca,
  });
  const DEST = { ...SITUACAO, aviso_destinatarios: ['faturamento@x.com', 'adm@x.com'] };

  it('mostra para quem foi', async () => {
    montarGets({ situacao: DEST, contratos: [assinado({
      aviso_enviado_em: '2026-10-08T21:00:00Z', aviso_remetente: 'bruno@x.com',
      aviso_para: ['faturamento@x.com', 'adm@x.com'],
    })] });
    render(<AbaContrato oportunidade={OPP} agora={AGORA} />);
    const status = await screen.findByTestId('aviso-status');
    expect(status).toHaveTextContent('bruno@x.com');
    expect(status).toHaveTextContent('faturamento@x.com, adm@x.com');
    expect(screen.getByRole('button', { name: 'Reenviar aviso' })).toBeInTheDocument();
  });

  it('falha aparece e o botão tenta de novo', async () => {
    montarGets({ situacao: DEST, contratos: [assinado({ aviso_erro: 'Gmail fora do ar' })] });
    mockPost.mockResolvedValue({ data: assinado({ aviso_enviado_em: '2026-10-08T21:00:00Z',
      aviso_remetente: 'bruno@x.com', aviso_para: ['faturamento@x.com'] }) });
    render(<AbaContrato oportunidade={OPP} agora={AGORA} />);
    expect(await screen.findByTestId('aviso-status')).toHaveTextContent('Gmail fora do ar');
    fireEvent.click(screen.getByRole('button', { name: 'Enviar aviso' }));
    await waitFor(() => expect(mockPost).toHaveBeenCalledWith('/crm/contratos/k1/aviso', {}));
    await waitFor(() => expect(screen.getByTestId('aviso-status')).toHaveTextContent('Aviso enviado'));
  });

  it('sem destinatários: diz que está desligado e não oferece o botão', async () => {
    montarGets({ contratos: [assinado()] });
    render(<AbaContrato oportunidade={OPP} agora={AGORA} />);
    expect(await screen.findByTestId('aviso-status')).toHaveTextContent('desligado');
    expect(screen.queryByRole('button', { name: /aviso/ })).not.toBeInTheDocument();
  });
});


describe('empresas, filiais e substituição (055)', () => {
  const G2 = {
    raiz: '99888777', principal: false, contratante_razao_social: 'OUTRA LTDA',
    contratante_cnpj: '99.888.777/0001-19', conta_id: 'c9', endereco: 'Rua B, 2',
    pendencias_endereco: [], cnpjs: [{ cnpj: '99888777000119', cnpj_formatado: '99.888.777/0001-19',
      razao_social: 'OUTRA LTDA', vidas: 3, mensalidade: '180.00' }],
    linhas_preco: ['Linha da outra empresa;'], contrato_em_aberto_id: null, substitui: [],
  };

  it('duas raízes: escolhe a empresa e manda a raiz certa', async () => {
    montarGets({ padrao: { ...PADRAO, grupos: [{ ...PADRAO.grupos[0], contrato_em_aberto_id: 'k1' }, G2] } });
    mockPost.mockResolvedValue({ data: contrato() });
    render(<AbaContrato oportunidade={OPP} agora={AGORA} preset={{ proposta_id: 'p2' }} />);
    const form = await screen.findByRole('region', { name: 'Novo contrato' });
    // Já abre na empresa que não tem contrato em andamento.
    expect(await within(form).findByText('Linha da outra empresa;')).toBeInTheDocument();
    expect(within(form).getByRole('radio', { name: /OUTRA LTDA/ })).toBeChecked();
    fireEvent.click(within(form).getByRole('radio', { name: /NN LTDA/ }));
    expect(within(form).getByRole('status')).toHaveTextContent(/já há um contrato de NN LTDA/i);
    fireEvent.click(within(form).getByRole('radio', { name: /OUTRA LTDA/ }));
    fireEvent.change(form.querySelector('#test-contratante-origem'), { target: { value: 'k2' } });
    fireEvent.click(within(form).getByRole('button', { name: /Enviar para assinatura/ }));
    await waitFor(() => expect(mockPost).toHaveBeenCalled());
    expect(mockPost.mock.calls[0][1].raiz_cnpj).toBe('99888777');
  });

  it('matriz e filiais: lista o Anexo 1 e avisa a substituição', async () => {
    const grupo = { ...PADRAO.grupos[0],
      cnpjs: [...PADRAO.grupos[0].cnpjs, { cnpj: '11222333000262', cnpj_formatado: '11.222.333/0002-62',
        razao_social: 'NN FILIAL', vidas: 2, mensalidade: '180.00' }],
      substitui: [{ id: 'k0', versao: 1, data_contrato: '2026-05-10' }] };
    montarGets({ padrao: { ...PADRAO, grupos: [grupo] } });
    render(<AbaContrato oportunidade={OPP} agora={AGORA} preset={{ proposta_id: 'p2' }} />);
    const form = await screen.findByRole('region', { name: 'Novo contrato' });
    expect(await within(form).findByLabelText('CNPJs do contrato')).toHaveTextContent('NN FILIAL');
    expect(within(form).getByText(/substitui o contrato v1 de 10\/05\/2026/)).toBeInTheDocument();
  });

  it('serviços: vem marcado o sugerido e as linhas livres vão separadas', async () => {
    montarGets();
    mockPost.mockResolvedValue({ data: contrato() });
    render(<AbaContrato oportunidade={OPP} agora={AGORA} preset={{ proposta_id: 'p2' }} />);
    const form = await screen.findByRole('region', { name: 'Novo contrato' });
    await waitFor(() => expect(within(form).getByLabelText('CIPA (NR-05)')).toBeChecked());
    fireEvent.click(within(form).getByLabelText('Elaboração do PPP'));
    fireEvent.click(within(form).getByLabelText('CIPA (NR-05)'));
    fireEvent.change(within(form).getByLabelText('Outros serviços (um por linha)'),
      { target: { value: 'Treinamento NR-35\n\n  Treinamento NR-10 ' } });
    fireEvent.change(form.querySelector('#test-contratante-origem'), { target: { value: 'k2' } });
    fireEvent.click(within(form).getByRole('button', { name: /Enviar para assinatura/ }));
    await waitFor(() => expect(mockPost).toHaveBeenCalled());
    const corpo = mockPost.mock.calls[0][1];
    expect(corpo.servicos).toEqual(['ppp']);
    expect(corpo.servicos_livres).toEqual(['Treinamento NR-35', 'Treinamento NR-10']);
  });

  it('dois contratos vigentes aparecem; o substituído vai para o histórico', async () => {
    montarGets({ contratos: [
      contrato({ id: 'a', contratante_razao_social: 'NN LTDA' }),
      contrato({ id: 'b', versao: 2, status: 'assinado', contratante_razao_social: 'OUTRA LTDA',
        assinados: 4, proximo_nome: null,
        signatarios: contrato().signatarios.map((x) => ({ ...x, situacao: 'assinado', da_vez: false })) }),
      contrato({ id: 'c', versao: 0, status: 'substituido', substituido_por_versao: 2 }),
    ] });
    render(<AbaContrato oportunidade={OPP} agora={AGORA} />);
    expect(await screen.findByTestId('kpi-empresas')).toHaveTextContent('2');
    const empresas = screen.getAllByTestId('contrato-empresa').map((e) => e.textContent);
    expect(empresas).toEqual(['NN LTDA', 'OUTRA LTDA']);
    expect(screen.getByRole('button', { name: /Versões anteriores \(1\)/ })).toBeInTheDocument();
  });
});
