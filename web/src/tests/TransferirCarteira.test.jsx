// web/src/tests/TransferirCarteira.test.jsx
//
// A passagem de carteira em massa é a resposta para "o EC saiu, e agora?".
// Três coisas precisam ficar de pé:
//   1. os três movimentos cabem no mesmo formulário (sai / órfãos / devolve)
//   2. a CONTAGEM aparece antes de executar — sem ela é apertar e torcer
//   3. os casos impossíveis travam o botão em vez de virar erro da API
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, fireEvent, cleanup, waitFor, within } from '@testing-library/react';

const mockPost = vi.fn();

vi.mock('../api', () => ({
  default: { post: (...a) => mockPost(...a) },
}));

import TransferirCarteira, { SEM_EC } from '../components/crm/TransferirCarteira';

const USUARIOS = [
  { id: 'u1', nome: 'Ana EC', cargo: 'EC' },
  { id: 'u2', nome: 'Bruno EC', cargo: 'EC' },
];

const CARTEIRAS = {
  sem_ec: 3,
  por_ec: [
    { usuario_id: 'u1', nome: 'Ana EC', parceiros: 5, indicacoes: 20, convertidas: 8 },
    { usuario_id: 'u2', nome: 'Bruno EC', parceiros: 0, indicacoes: 0, convertidas: 0 },
  ],
};

function montar(props = {}) {
  const onFechar = vi.fn();
  const onConcluido = vi.fn();
  render(
    <TransferirCarteira
      aberto
      usuarios={USUARIOS}
      carteiras={CARTEIRAS}
      onFechar={onFechar}
      onConcluido={onConcluido}
      {...props}
    />
  );
  return { onFechar, onConcluido };
}

const botaoTransferir = () => screen.getByRole('button', { name: /^Transferir/ });

beforeEach(() => {
  mockPost.mockReset();
  mockPost.mockResolvedValue({ data: { transferidos: 3, conta_ids: ['a', 'b', 'c'] } });
});

afterEach(cleanup);

describe('TransferirCarteira — a prévia', () => {
  it('abre em "sem responsável" e conta os órfãos', () => {
    /*
      O padrão é a fila de órfãos porque é o caso que se repete: parceiro
      novo entra sem dono toda semana; EC sai uma vez por ano.
    */
    montar();
    const previa = within(screen.getByTestId('previa-transferencia'));
    expect(previa.getByText('3 parceiros')).toBeInTheDocument();
    expect(previa.getByText(/sem responsável/)).toBeInTheDocument();
  });

  it('trocar a origem troca a contagem', () => {
    montar();
    fireEvent.change(screen.getByLabelText('De'), { target: { value: 'u1' } });
    expect(within(screen.getByTestId('previa-transferencia')).getByText('5 parceiros'))
      .toBeInTheDocument();
  });

  it('a contagem também aparece no botão', () => {
    /* "Transferir 5" é uma promessa verificável; "Transferir" é um salto de
       fé. */
    montar();
    fireEvent.change(screen.getByLabelText('De'), { target: { value: 'u1' } });
    expect(screen.getByRole('button', { name: 'Transferir 5' })).toBeInTheDocument();
  });

  it('singular quando é um só', () => {
    montar({ carteiras: { sem_ec: 1, por_ec: [] } });
    expect(screen.getByText('1 parceiro')).toBeInTheDocument();
  });
});

describe('TransferirCarteira — o que trava o botão', () => {
  it('sem destino escolhido', () => {
    montar();
    expect(botaoTransferir()).toBeDisabled();
  });

  it('origem e destino iguais', () => {
    montar();
    fireEvent.change(screen.getByLabelText('De'), { target: { value: 'u1' } });
    fireEvent.change(screen.getByLabelText('Para'), { target: { value: 'u1' } });
    expect(botaoTransferir()).toBeDisabled();
    expect(screen.getByText('Origem e destino são a mesma pessoa.')).toBeInTheDocument();
  });

  it('carteira de origem vazia', () => {
    montar();
    fireEvent.change(screen.getByLabelText('De'), { target: { value: 'u2' } });
    fireEvent.change(screen.getByLabelText('Para'), { target: { value: 'u1' } });
    expect(botaoTransferir()).toBeDisabled();
    expect(screen.getByText(/não tem parceiro nenhum/)).toBeInTheDocument();
  });

  it('nenhum órfão para distribuir', () => {
    montar({ carteiras: { sem_ec: 0, por_ec: [] } });
    fireEvent.change(screen.getByLabelText('Para'), { target: { value: 'u1' } });
    expect(botaoTransferir()).toBeDisabled();
    expect(screen.getByText('Nenhum parceiro está sem responsável.')).toBeInTheDocument();
  });
});

describe('TransferirCarteira — os três movimentos', () => {
  it('distribuir os órfãos manda de=null', async () => {
    const { onConcluido } = montar();
    fireEvent.change(screen.getByLabelText('Para'), { target: { value: 'u1' } });
    fireEvent.click(botaoTransferir());
    await waitFor(() =>
      expect(mockPost).toHaveBeenCalledWith(
        '/crm/parceiros/carteira/transferir',
        { de_usuario_id: null, para_usuario_id: 'u1' }
      )
    );
    await waitFor(() => expect(onConcluido).toHaveBeenCalled());
  });

  it('alguém saiu: de=quem sai, para=quem assume', async () => {
    montar();
    fireEvent.change(screen.getByLabelText('De'), { target: { value: 'u1' } });
    fireEvent.change(screen.getByLabelText('Para'), { target: { value: 'u2' } });
    fireEvent.click(botaoTransferir());
    await waitFor(() =>
      expect(mockPost).toHaveBeenCalledWith(
        '/crm/parceiros/carteira/transferir',
        { de_usuario_id: 'u1', para_usuario_id: 'u2' }
      )
    );
  });

  it('devolver à fila manda para=null', async () => {
    montar();
    fireEvent.change(screen.getByLabelText('De'), { target: { value: 'u1' } });
    fireEvent.change(screen.getByLabelText('Para'), { target: { value: SEM_EC } });
    fireEvent.click(botaoTransferir());
    await waitFor(() =>
      expect(mockPost).toHaveBeenCalledWith(
        '/crm/parceiros/carteira/transferir',
        { de_usuario_id: 'u1', para_usuario_id: null }
      )
    );
  });

  it('"sem responsável" nas duas pontas não vira string vazia', () => {
    /*
      SEM_EC é um sentinela, não ''. String vazia colidiria com "não escolhi
      nada", e os dois significam coisas diferentes: um é um destino válido,
      o outro é formulário incompleto.
    */
    expect(SEM_EC).not.toBe('');
    montar();
    const opcoes = [...screen.getByLabelText('Para').querySelectorAll('option')]
      .map((o) => o.value);
    expect(opcoes).toEqual(['', SEM_EC, 'u1', 'u2']);
  });
});

describe('TransferirCarteira — erro', () => {
  it('mostra a mensagem da API e não fecha', async () => {
    mockPost.mockRejectedValue({
      response: { data: { detail: 'Origem e destino são a mesma pessoa.' } },
    });
    const { onConcluido } = montar();
    fireEvent.change(screen.getByLabelText('Para'), { target: { value: 'u1' } });
    fireEvent.click(botaoTransferir());
    expect(await screen.findByText('Origem e destino são a mesma pessoa.')).toBeInTheDocument();
    expect(onConcluido).not.toHaveBeenCalled();
  });
});
