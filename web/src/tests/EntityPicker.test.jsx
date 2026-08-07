// web/src/tests/EntityPicker.test.jsx
//
// O EntityPicker é o componente que a especificação descreve como "uma lupa
// para procurar e um botão de mais para cadastrar novo". Os testes cobrem os
// dois caminhos e, principalmente, a promessa central do botão "+": criar
// inline devolve o registro já selecionado, sem o usuário sair do formulário.
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, fireEvent, cleanup, waitFor } from '@testing-library/react';

import EntityPicker from '../components/EntityPicker';

const ITENS = [
  { id: 'a1', nome: 'Ana Silva', email: 'ana@alfa.com' },
  { id: 'b2', nome: 'Bruno Costa', email: 'bruno@alfa.com', ja_vinculado: true },
];

const paraItem = (c) => ({
  id: c.id,
  titulo: c.nome,
  subtitulo: c.email,
  desabilitado: Boolean(c.ja_vinculado),
  motivoDesabilitado: 'já vinculado',
});

function montar(props = {}) {
  const onChange = vi.fn();
  const buscar = props.buscar || vi.fn().mockResolvedValue(ITENS);
  render(
    <EntityPicker
      label="Contato"
      value={null}
      onChange={onChange}
      buscar={buscar}
      paraItem={paraItem}
      {...props}
    />
  );
  return { onChange, buscar };
}

beforeEach(() => { vi.useRealTimers(); });
afterEach(cleanup);

describe('EntityPicker — estado inicial', () => {
  it('mostra o placeholder quando nada está selecionado', () => {
    montar({ placeholder: 'Selecione uma pessoa' });
    expect(screen.getByText('Selecione uma pessoa')).toBeInTheDocument();
  });

  it('mostra título e subtítulo do item selecionado', () => {
    montar({ value: ITENS[0] });
    expect(screen.getByText('Ana Silva')).toBeInTheDocument();
    expect(screen.getByText(/ana@alfa\.com/)).toBeInTheDocument();
  });

  it('não mostra o botão "+" quando não há como criar', () => {
    montar();
    expect(screen.queryByLabelText('Cadastrar Contato')).not.toBeInTheDocument();
  });

  it('mostra o botão "+" quando criar é fornecido', () => {
    montar({ criar: { titulo: 'Novo', campos: [], onSubmit: vi.fn() } });
    expect(screen.getByLabelText('Cadastrar Contato')).toBeInTheDocument();
  });

  it('limpa a seleção pelo botão X', () => {
    const { onChange } = montar({ value: ITENS[0] });
    fireEvent.click(screen.getByLabelText('Limpar Contato'));
    expect(onChange).toHaveBeenCalledWith(null);
  });

  it('não abre quando desabilitado', () => {
    montar({ disabled: true });
    fireEvent.click(screen.getByLabelText('Buscar Contato'));
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
  });

  it('mostra a mensagem de erro', () => {
    montar({ error: 'Campo obrigatório' });
    expect(screen.getByText('Campo obrigatório')).toBeInTheDocument();
  });
});

describe('EntityPicker — busca pela lupa', () => {
  it('abre o painel de busca', () => {
    montar();
    fireEvent.click(screen.getByLabelText('Buscar Contato'));
    expect(screen.getByRole('dialog')).toBeInTheDocument();
    expect(screen.getByPlaceholderText('Digite para buscar…')).toBeInTheDocument();
  });

  it('não busca com o campo vazio', () => {
    const { buscar } = montar();
    fireEvent.click(screen.getByLabelText('Buscar Contato'));
    expect(buscar).not.toHaveBeenCalled();
    expect(screen.getByText('Digite ao menos uma letra.')).toBeInTheDocument();
  });

  it('busca e lista os resultados', async () => {
    const { buscar } = montar();
    fireEvent.click(screen.getByLabelText('Buscar Contato'));
    fireEvent.change(screen.getByPlaceholderText('Digite para buscar…'), {
      target: { value: 'ana' },
    });
    expect(await screen.findByText('Ana Silva')).toBeInTheDocument();
    expect(buscar).toHaveBeenCalledWith('ana');
  });

  it('seleciona um item e fecha o painel', async () => {
    const { onChange } = montar();
    fireEvent.click(screen.getByLabelText('Buscar Contato'));
    fireEvent.change(screen.getByPlaceholderText('Digite para buscar…'), {
      target: { value: 'ana' },
    });
    fireEvent.click(await screen.findByText('Ana Silva'));

    expect(onChange).toHaveBeenCalledWith(ITENS[0]);
    await waitFor(() => expect(screen.queryByRole('dialog')).not.toBeInTheDocument());
  });

  it('desabilita item já vinculado e não o seleciona', async () => {
    const { onChange } = montar();
    fireEvent.click(screen.getByLabelText('Buscar Contato'));
    fireEvent.change(screen.getByPlaceholderText('Digite para buscar…'), {
      target: { value: 'a' },
    });
    const bruno = await screen.findByText('Bruno Costa');
    expect(screen.getByText('já vinculado')).toBeInTheDocument();
    fireEvent.click(bruno);
    expect(onChange).not.toHaveBeenCalled();
  });

  it('avisa quando não encontra nada', async () => {
    montar({ buscar: vi.fn().mockResolvedValue([]) });
    fireEvent.click(screen.getByLabelText('Buscar Contato'));
    fireEvent.change(screen.getByPlaceholderText('Digite para buscar…'), {
      target: { value: 'zzz' },
    });
    expect(await screen.findByText('Nada encontrado.')).toBeInTheDocument();
  });

  it('mostra erro quando a busca falha', async () => {
    montar({ buscar: vi.fn().mockRejectedValue(new Error('boom')) });
    fireEvent.click(screen.getByLabelText('Buscar Contato'));
    fireEvent.change(screen.getByPlaceholderText('Digite para buscar…'), {
      target: { value: 'ana' },
    });
    expect(await screen.findByText('Não foi possível buscar.')).toBeInTheDocument();
  });

  it('fecha com Esc', async () => {
    montar();
    fireEvent.click(screen.getByLabelText('Buscar Contato'));
    expect(screen.getByRole('dialog')).toBeInTheDocument();
    fireEvent.keyDown(document, { key: 'Escape' });
    await waitFor(() => expect(screen.queryByRole('dialog')).not.toBeInTheDocument());
  });
});

describe('EntityPicker — criar inline', () => {
  const CRIAR = {
    titulo: 'Cadastrar novo contato',
    campos: [
      { nome: 'nome', label: 'Nome', obrigatorio: true },
      { nome: 'email', label: 'E-mail' },
    ],
    onSubmit: vi.fn(),
  };

  beforeEach(() => { CRIAR.onSubmit.mockReset(); });

  it('abre direto no formulário pelo botão "+"', () => {
    montar({ criar: CRIAR });
    fireEvent.click(screen.getByLabelText('Cadastrar Contato'));
    expect(screen.getByText('Cadastrar novo contato')).toBeInTheDocument();
    expect(screen.getByLabelText('Nome *')).toBeInTheDocument();
  });

  it('exige os campos obrigatórios', async () => {
    montar({ criar: CRIAR });
    fireEvent.click(screen.getByLabelText('Cadastrar Contato'));
    fireEvent.click(screen.getByText('Criar'));
    expect(await screen.findByText('Preencha: Nome.')).toBeInTheDocument();
    expect(CRIAR.onSubmit).not.toHaveBeenCalled();
  });

  it('cria e devolve o registro já selecionado', async () => {
    const novo = { id: 'z9', nome: 'Carla Nova', email: 'carla@alfa.com' };
    CRIAR.onSubmit.mockResolvedValue(novo);
    const { onChange } = montar({ criar: CRIAR });

    fireEvent.click(screen.getByLabelText('Cadastrar Contato'));
    fireEvent.change(screen.getByLabelText('Nome *'), { target: { value: 'Carla Nova' } });
    fireEvent.click(screen.getByText('Criar'));

    await waitFor(() => expect(onChange).toHaveBeenCalledWith(novo));
    expect(CRIAR.onSubmit).toHaveBeenCalledWith({ nome: 'Carla Nova' });
    await waitFor(() => expect(screen.queryByRole('dialog')).not.toBeInTheDocument());
  });

  it('mostra erro quando a criação falha', async () => {
    CRIAR.onSubmit.mockRejectedValue({ response: { data: { detail: 'Nome já existe' } } });
    montar({ criar: CRIAR });
    fireEvent.click(screen.getByLabelText('Cadastrar Contato'));
    fireEvent.change(screen.getByLabelText('Nome *'), { target: { value: 'X' } });
    fireEvent.click(screen.getByText('Criar'));
    expect(await screen.findByText('Nome já existe')).toBeInTheDocument();
  });

  it('volta para a busca pelo botão Voltar', async () => {
    montar({ criar: CRIAR });
    fireEvent.click(screen.getByLabelText('Cadastrar Contato'));
    fireEvent.click(screen.getByText('Voltar'));
    expect(await screen.findByPlaceholderText('Digite para buscar…')).toBeInTheDocument();
  });
});

describe('EntityPicker — aviso de duplicata', () => {
  const CRIAR = {
    titulo: 'Cadastrar novo contato',
    campos: [
      { nome: 'nome', label: 'Nome', obrigatorio: true },
      { nome: 'email', label: 'E-mail' },
    ],
    onSubmit: vi.fn(),
  };

  beforeEach(() => { CRIAR.onSubmit.mockReset(); });

  it('sugere duplicatas e segura a criação na primeira tentativa', async () => {
    const checar = vi.fn().mockResolvedValue([
      { id: 'd1', texto: 'Ana Silva (Alfa LTDA) — mesmo email' },
    ]);
    montar({ criar: CRIAR, limparAvisoDuplicata: checar });

    fireEvent.click(screen.getByLabelText('Cadastrar Contato'));
    fireEvent.change(screen.getByLabelText('Nome *'), { target: { value: 'Ana' } });
    fireEvent.change(screen.getByLabelText('E-mail'), { target: { value: 'ana@alfa.com' } });
    fireEvent.click(screen.getByText('Criar'));

    expect(await screen.findByText(/Ana Silva \(Alfa LTDA\)/)).toBeInTheDocument();
    expect(CRIAR.onSubmit).not.toHaveBeenCalled();
  });

  it('cria mesmo assim na segunda tentativa — duplicata avisa, não bloqueia', async () => {
    const checar = vi.fn().mockResolvedValue([
      { id: 'd1', texto: 'Ana Silva — mesmo email' },
    ]);
    const novo = { id: 'z9', nome: 'Ana' };
    CRIAR.onSubmit.mockResolvedValue(novo);
    const { onChange } = montar({ criar: CRIAR, limparAvisoDuplicata: checar });

    fireEvent.click(screen.getByLabelText('Cadastrar Contato'));
    fireEvent.change(screen.getByLabelText('Nome *'), { target: { value: 'Ana' } });
    fireEvent.click(screen.getByText('Criar'));
    await screen.findByText(/Ana Silva/);

    fireEvent.click(screen.getByText('Criar'));
    await waitFor(() => expect(onChange).toHaveBeenCalledWith(novo));
  });

  it('cria direto quando não há duplicata', async () => {
    const checar = vi.fn().mockResolvedValue([]);
    const novo = { id: 'z9', nome: 'Zeca' };
    CRIAR.onSubmit.mockResolvedValue(novo);
    const { onChange } = montar({ criar: CRIAR, limparAvisoDuplicata: checar });

    fireEvent.click(screen.getByLabelText('Cadastrar Contato'));
    fireEvent.change(screen.getByLabelText('Nome *'), { target: { value: 'Zeca' } });
    fireEvent.click(screen.getByText('Criar'));

    await waitFor(() => expect(onChange).toHaveBeenCalledWith(novo));
  });
});
