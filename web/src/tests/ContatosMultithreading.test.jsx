// web/src/tests/ContatosMultithreading.test.jsx
//
// Entrega 045 — ABM / multithreading:
//   1. o comitê da oportunidade (AbaContatos): farol, papel, principal, tirar
//   2. editar contato no lugar (FormContato / ContatosDaConta)
//   3. o contato obrigatório no formulário de tarefa (CampoContato)
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

import AbaContatos from '../components/crm/AbaContatos';
import ContatosDaConta from '../components/crm/ContatosDaConta';
import {
  FormContato, linkWhatsapp, tomDoComite, SeloComite,
  SinalTemperatura, explicacaoTemperatura,
} from '../components/crm/contatoComum';
import {
  CamposTarefa, corpoDaTarefa, exigeContato, formIncompleto, tarefaVazia,
} from '../components/crm/tarefaComum';

const OPP = { id: 'o1', conta_id: 'c1', contato_id: 'ct1' };

const ANA = {
  contato_id: 'ct1', nome: 'Ana Diretora', cargo: 'Diretora de RH',
  telefone: '11999990000', telefone_whatsapp: true,
  telefone_2: null, telefone_2_whatsapp: false,
  email: 'ana@alfa.com', linkedin: 'https://linkedin.com/in/ana', ativo: true,
  papel: 'decisor', papel_rotulo: 'Decisor', principal: true,
  interacoes: 2, ultima_interacao: new Date().toISOString(),
  criado_em: '2026-09-01T12:00:00Z',
};
const BIA = {
  ...ANA, contato_id: 'ct2', nome: 'Bia DP', cargo: null, telefone: null,
  telefone_whatsapp: false, email: null, linkedin: null,
  papel: null, papel_rotulo: null, principal: false, interacoes: 0, ultima_interacao: null,
};

function comite(itens, farol = {}) {
  return {
    oportunidade_id: 'o1',
    itens,
    farol: {
      nivel: 'ideal', tom: 'success', rotulo: `${itens.length} contatos`,
      dica: 'Comitê coberto.', tem_decisor: true, minimo_ideal: 2, maximo_ideal: 4,
      ...farol,
    },
  };
}

beforeEach(() => {
  [mockGet, mockPost, mockPatch, mockDelete].forEach((m) => m.mockReset());
});
afterEach(cleanup);

// ── Regras puras ─────────────────────────────────────────────────────

describe('contatoComum', () => {
  it('WhatsApp ganha o 55 quando o número não tem DDI', () => {
    expect(linkWhatsapp('(11) 99999-0000')).toBe('https://wa.me/5511999990000');
    expect(linkWhatsapp('5511999990000')).toBe('https://wa.me/5511999990000');
    expect(linkWhatsapp('')).toBeNull();
  });

  it('o tom do comitê segue a faixa do método', () => {
    expect(tomDoComite(0)).toBe('danger');
    expect(tomDoComite(1)).toBe('warning');
    expect(tomDoComite(2)).toBe('success');
    expect(tomDoComite(5)).toBe('success');
  });

  it('o selo avisa quando falta o decisor', () => {
    render(<SeloComite qtd={3} temDecisor={false} />);
    expect(screen.getByText('3 contatos · sem decisor')).toBeInTheDocument();
  });
});

describe('tarefaComum — contato obrigatório', () => {
  it('interação exige; proposta e outro não', () => {
    ['ligacao', 'reuniao', 'visita', 'whatsapp', 'email'].forEach((t) => expect(exigeContato(t)).toBe(true));
    ['proposta', 'outro'].forEach((t) => expect(exigeContato(t)).toBe(false));
  });

  it('formulário de ligação sem contato está incompleto', () => {
    const f = { ...tarefaVazia('u1'), titulo: 'FUP' };
    expect(formIncompleto(f)).toBe(true);
    expect(formIncompleto({ ...f, contato_id: 'ct1' })).toBe(false);
    expect(formIncompleto({ ...f, tipo: 'proposta' })).toBe(false);
  });

  it('a sugestão de contato entra no corpo', () => {
    const f = { ...tarefaVazia('u1', 'ct1'), titulo: 'FUP' };
    expect(corpoDaTarefa(f).contato_id).toBe('ct1');
    expect(corpoDaTarefa({ ...f, contato_id: '' }).contato_id).toBeNull();
  });
});

// ── O comitê ─────────────────────────────────────────────────────────

describe('AbaContatos', () => {
  it('mostra o farol, o papel e com quem já se falou', async () => {
    mockGet.mockResolvedValue({ data: comite([ANA, BIA]) });
    render(<AbaContatos oportunidade={OPP} />);
    expect(await screen.findByText('Ana Diretora')).toBeInTheDocument();
    expect(screen.getByLabelText('Farol de multithreading')).toHaveTextContent('2 contatos');
    expect(screen.getByText('Decisor mapeado')).toBeInTheDocument();
    expect(screen.getByText('Principal')).toBeInTheDocument();
    expect(screen.getByText(/2 interações/)).toBeInTheDocument();
    expect(screen.getByText('nenhuma interação ainda')).toBeInTheDocument();
    expect(screen.getByLabelText('WhatsApp 11999990000')).toHaveAttribute(
      'href', 'https://wa.me/5511999990000',
    );
  });

  it('comitê vazio explica o account based', async () => {
    mockGet.mockResolvedValue({
      data: comite([], { nivel: 'sem_contato', tom: 'danger', rotulo: 'Sem contato', tem_decisor: false }),
    });
    render(<AbaContatos oportunidade={OPP} />);
    expect(await screen.findByText('Ninguém da empresa nesta negociação')).toBeInTheDocument();
    expect(screen.getByText('Sem decisor')).toBeInTheDocument();
  });

  it('mudar o papel chama PATCH e redesenha com a resposta', async () => {
    mockGet.mockResolvedValue({ data: comite([ANA, BIA]) });
    mockPatch.mockResolvedValue({ data: comite([ANA, { ...BIA, papel: 'operacional' }]) });
    const onMudou = vi.fn();
    render(<AbaContatos oportunidade={OPP} onMudou={onMudou} />);
    fireEvent.change(await screen.findByLabelText('Papel de Bia DP'), {
      target: { value: 'operacional' },
    });
    await waitFor(() => expect(mockPatch).toHaveBeenCalledWith(
      '/crm/oportunidades/o1/contatos/ct2', { papel: 'operacional' },
    ));
    await waitFor(() => expect(onMudou).toHaveBeenCalled());
  });

  it('trocar o principal', async () => {
    mockGet.mockResolvedValue({ data: comite([ANA, BIA]) });
    mockPatch.mockResolvedValue({ data: comite([{ ...ANA, principal: false }, { ...BIA, principal: true }]) });
    render(<AbaContatos oportunidade={OPP} />);
    fireEvent.click(await screen.findByLabelText('Tornar Bia DP principal'));
    await waitFor(() => expect(mockPatch).toHaveBeenCalledWith(
      '/crm/oportunidades/o1/contatos/ct2', { principal: true },
    ));
  });

  it('tirar da oportunidade', async () => {
    mockGet.mockResolvedValue({ data: comite([ANA, BIA]) });
    mockDelete.mockResolvedValue({ data: comite([ANA]) });
    render(<AbaContatos oportunidade={OPP} />);
    fireEvent.click(await screen.findByLabelText('Tirar Bia DP da oportunidade'));
    await waitFor(() => expect(mockDelete).toHaveBeenCalledWith('/crm/oportunidades/o1/contatos/ct2'));
    await waitFor(() => expect(screen.queryByText('Bia DP')).not.toBeInTheDocument());
  });

  it('o erro da API aparece na tela', async () => {
    mockGet.mockResolvedValue({ data: comite([ANA, BIA]) });
    mockPatch.mockRejectedValue({ response: { data: { detail: 'Papel inválido.' } } });
    render(<AbaContatos oportunidade={OPP} />);
    fireEvent.change(await screen.findByLabelText('Papel de Bia DP'), { target: { value: 'compras' } });
    expect(await screen.findByText('Papel inválido.')).toBeInTheDocument();
  });

  it('editar abre o formulário no lugar com o cargo do vínculo', async () => {
    mockGet.mockResolvedValue({ data: comite([ANA]) });
    render(<AbaContatos oportunidade={OPP} />);
    fireEvent.click(await screen.findByLabelText('Editar Ana Diretora'));
    expect(screen.getByLabelText('Cargo nesta empresa')).toHaveValue('Diretora de RH');
    expect(screen.getByLabelText('Telefone')).toHaveValue('11999990000');
  });
});

// ── Editar contato ───────────────────────────────────────────────────

describe('FormContato', () => {
  const CONTATO = {
    id: 'ct1', nome: 'Ana', telefone: '1111', telefone_whatsapp: false,
    telefone_2: null, email: null, linkedin: null, cargo: 'RH',
  };

  it('troca o telefone com PATCH no mesmo contato, sem recriar', async () => {
    mockPatch.mockResolvedValue({ data: {} });
    const onSalvo = vi.fn();
    render(<FormContato contato={CONTATO} contaId="c1" cargoAtual="RH" onSalvo={onSalvo} />);
    fireEvent.change(screen.getByLabelText('Telefone'), { target: { value: '11 98888-7777' } });
    fireEvent.click(screen.getAllByLabelText('É WhatsApp')[0]);
    fireEvent.change(screen.getByLabelText('2º telefone'), { target: { value: '11 3333-4444' } });
    fireEvent.click(screen.getByText('Salvar contato'));
    await waitFor(() => expect(onSalvo).toHaveBeenCalled());
    expect(mockPatch).toHaveBeenCalledTimes(1);
    expect(mockPatch).toHaveBeenCalledWith('/crm/contatos/ct1', expect.objectContaining({
      telefone: '11 98888-7777', telefone_whatsapp: true, telefone_2: '11 3333-4444',
    }));
  });

  it('cargo alterado vai para o vínculo com a conta', async () => {
    mockPatch.mockResolvedValue({ data: {} });
    render(<FormContato contato={CONTATO} contaId="c1" cargoAtual="RH" onSalvo={() => {}} />);
    fireEvent.change(screen.getByLabelText('Cargo nesta empresa'), { target: { value: 'Gerente de RH' } });
    fireEvent.click(screen.getByText('Salvar contato'));
    await waitFor(() => expect(mockPatch).toHaveBeenCalledWith(
      '/crm/contatos/ct1/vinculos/c1', { cargo: 'Gerente de RH' },
    ));
  });

  it('aceita dois e-mails no mesmo campo e avisa como separar', async () => {
    mockPatch.mockResolvedValue({ data: {} });
    render(<FormContato contato={CONTATO} contaId="c1" cargoAtual="RH" onSalvo={() => {}} />);
    const campo = screen.getByLabelText('E-mail');
    expect(campo).toHaveAttribute('type', 'text');
    expect(screen.getByText(/Separe com ponto e vírgula/)).toBeInTheDocument();
    fireEvent.change(campo, { target: { value: 'ana@x.com; financeiro@x.com' } });
    fireEvent.click(screen.getByText('Salvar contato'));
    await waitFor(() => expect(mockPatch).toHaveBeenCalledWith(
      '/crm/contatos/ct1', expect.objectContaining({ email: 'ana@x.com; financeiro@x.com' }),
    ));
  });

  it('mostra o erro do servidor (LinkedIn inválido)', async () => {
    mockPatch.mockRejectedValue({ response: { data: { detail: [{ msg: 'Informe o endereço do perfil no LinkedIn' }] } } });
    render(<FormContato contato={CONTATO} onSalvo={() => {}} />);
    fireEvent.change(screen.getByLabelText('LinkedIn'), { target: { value: 'meusite.com' } });
    fireEvent.click(screen.getByText('Salvar contato'));
    expect(await screen.findByText(/perfil no LinkedIn/)).toBeInTheDocument();
  });
});

describe('ContatosDaConta — editar', () => {
  it('o botão Editar troca a linha pelo formulário', () => {
    render(
      <ContatosDaConta
        contaId="c1"
        onMudou={() => {}}
        contatos={[{ id: 'ct1', nome: 'Ana', cargo: 'RH', principal: true, telefone: '1111' }]}
      />,
    );
    fireEvent.click(screen.getByLabelText('Editar Ana'));
    expect(screen.getByText('Salvar contato')).toBeInTheDocument();
    expect(screen.getByLabelText('Nome')).toHaveValue('Ana');
  });
});

// ── O campo de contato da tarefa ─────────────────────────────────────

describe('CamposTarefa — contato', () => {
  const OPCOES = [
    { id: 'ct1', nome: 'Ana', cargo: 'RH', no_comite: true, principal: true, papel: 'decisor' },
    { id: 'ct3', nome: 'Caio', cargo: null, no_comite: false, principal: false, papel: null },
  ];

  function Campos({ valor, onChange }) {
    return (
      <CamposTarefa
        valor={valor}
        onChange={onChange}
        usuarios={[]}
        alvo={{ oportunidade_id: 'o1', conta_id: 'c1' }}
      />
    );
  }

  it('lista o comitê primeiro e marca o obrigatório na ligação', async () => {
    mockGet.mockResolvedValue({ data: OPCOES });
    render(<Campos valor={tarefaVazia('u1')} onChange={() => {}} />);
    const campo = screen.getByLabelText('Contato (obrigatório)');
    expect(await screen.findByText('★ Ana · RH · Decisor')).toBeInTheDocument();
    expect(campo.querySelector('optgroup[label="Nesta oportunidade"]')).not.toBeNull();
    expect(mockGet).toHaveBeenCalledWith('/crm/contatos/por-alvo', { params: { oportunidade_id: 'o1' } });
  });

  it('proposta não exige', async () => {
    mockGet.mockResolvedValue({ data: OPCOES });
    render(<Campos valor={{ ...tarefaVazia('u1'), tipo: 'proposta' }} onChange={() => {}} />);
    expect(screen.getByLabelText('Contato')).toBeInTheDocument();
  });

  it('cadastrar novo cria na conta e já escolhe', async () => {
    mockGet.mockResolvedValue({ data: [] });
    mockPost.mockResolvedValue({ data: { id: 'ct9', nome: 'Davi' } });
    const onChange = vi.fn();
    render(<Campos valor={tarefaVazia('u1')} onChange={onChange} />);
    expect(await screen.findByText(/ainda não tem contato/)).toBeInTheDocument();
    fireEvent.change(screen.getByLabelText('Contato (obrigatório)'), { target: { value: '__novo__' } });
    fireEvent.change(screen.getByLabelText('Nome'), { target: { value: 'Davi' } });
    fireEvent.click(screen.getByText('Cadastrar e usar'));
    await waitFor(() => expect(mockPost).toHaveBeenCalledWith('/crm/contatos', expect.objectContaining({
      nome: 'Davi', conta_id: 'c1',
    })));
    await waitFor(() => expect(onChange).toHaveBeenCalledWith(expect.objectContaining({ contato_id: 'ct9' })));
  });
});

// ── Temperatura do contato (046) ─────────────────────────────────────

describe('SinalTemperatura', () => {
  it('mostra a palavra e, ao clicar, o porquê', () => {
    render(<SinalTemperatura contato={{
      temperatura: 'quente', temperatura_rotulo: 'Quente',
      interacoes_60d: 3, dias_desde_ultima_conversa: 2,
    }} />);
    const botao = screen.getByRole('button', { name: /Contato quente/ });
    expect(botao).toHaveTextContent('Quente');
    expect(screen.queryByText(/últimos 60 dias/)).not.toBeInTheDocument();
    fireEvent.click(botao);
    expect(screen.getByText('3 conversas concluídas nos últimos 60 dias · última há 2 dias')).toBeInTheDocument();
  });

  it('frio sem histórico explica que nunca houve conversa', () => {
    expect(explicacaoTemperatura({ interacoes_60d: 0, dias_desde_ultima_conversa: null }))
      .toBe('nenhuma conversa concluída nos últimos 60 dias · nunca houve conversa concluída');
    expect(explicacaoTemperatura({ interacoes_60d: 1, dias_desde_ultima_conversa: 1 }))
      .toBe('1 conversa concluída nos últimos 60 dias · última ontem');
  });

  it('aparece no comitê da oportunidade', async () => {
    mockGet.mockResolvedValue({ data: comite([{ ...ANA, temperatura: 'morno', temperatura_rotulo: 'Morno' }]) });
    render(<AbaContatos oportunidade={OPP} />);
    expect(await screen.findByRole('button', { name: /Contato morno/ })).toBeInTheDocument();
  });

  it('aparece na ficha da conta', () => {
    render(
      <ContatosDaConta
        contaId="c1" onMudou={() => {}}
        contatos={[{ id: 'ct1', nome: 'Ana', principal: true, temperatura: 'frio', temperatura_rotulo: 'Frio' }]}
      />,
    );
    expect(screen.getByRole('button', { name: /Contato frio/ })).toBeInTheDocument();
  });
});
