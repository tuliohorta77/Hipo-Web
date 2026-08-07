// web/src/tests/ModalDesfecho.test.jsx
//
// A distinção Perdido × Cancelado é a decisão mais fácil de errar do sistema:
// perdido entra na taxa de conversão, cancelado fica fora de todo denominador.
// Por isso a tela explica a consequência de cada opção, e o teste segura esse
// texto — se alguém "limpar" o modal removendo as explicações, quebra aqui.
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, fireEvent, cleanup, waitFor } from '@testing-library/react';

const mockGet = vi.fn();
const mockPost = vi.fn();

vi.mock('../api', () => ({
  default: { get: (...a) => mockGet(...a), post: (...a) => mockPost(...a) },
}));

import ModalDesfecho from '../components/crm/ModalDesfecho';

const OPP = { id: 'o1', numero: 'OPP-2026-00001', conta_razao_social: 'Alfa LTDA' };

function montar(props = {}) {
  const onFechar = vi.fn();
  const onConcluido = vi.fn();
  render(
    <ModalDesfecho
      oportunidade={OPP}
      onFechar={onFechar}
      onConcluido={onConcluido}
      {...props}
    />
  );
  return { onFechar, onConcluido };
}

beforeEach(() => {
  mockGet.mockReset();
  mockPost.mockReset();
  mockGet.mockImplementation((url) => {
    if (url === '/crm/dominio/motivos/perda') {
      return Promise.resolve({ data: [{ id: 1, nome: 'Preço', slug: 'preco' }] });
    }
    if (url === '/crm/dominio/motivos/cancelamento') {
      return Promise.resolve({ data: [{ id: 9, nome: 'Lead errado', slug: 'lead-errado' }] });
    }
    return Promise.resolve({ data: [] });
  });
});

afterEach(cleanup);

describe('ModalDesfecho — as três opções', () => {
  it('mostra conquistado, perdido e cancelado', () => {
    montar();
    expect(screen.getByText('Conquistado')).toBeInTheDocument();
    expect(screen.getByText('Perdido')).toBeInTheDocument();
    expect(screen.getByText('Cancelado')).toBeInTheDocument();
  });

  it('explica que perdido entra na conversão', () => {
    montar();
    expect(screen.getByText(/Entra na taxa de conversão/)).toBeInTheDocument();
  });

  it('explica que cancelado fica fora dos relatórios', () => {
    montar();
    expect(screen.getByText(/Fica fora dos relatórios de conversão/)).toBeInTheDocument();
  });

  it('identifica a oportunidade no subtítulo', () => {
    montar();
    expect(screen.getByText(/OPP-2026-00001 · Alfa LTDA/)).toBeInTheDocument();
  });

  it('não abre sem oportunidade', () => {
    montar({ oportunidade: null });
    expect(screen.queryByText('Conquistado')).not.toBeInTheDocument();
  });
});

describe('ModalDesfecho — motivo', () => {
  it('conquistado não pede motivo', async () => {
    montar();
    fireEvent.click(screen.getByText('Conquistado'));
    await waitFor(() => {
      expect(screen.queryByLabelText('Motivo *')).not.toBeInTheDocument();
    });
  });

  it('perdido carrega os motivos de perda', async () => {
    montar();
    fireEvent.click(screen.getByText('Perdido'));
    expect(await screen.findByLabelText('Motivo *')).toBeInTheDocument();
    await waitFor(() =>
      expect(mockGet).toHaveBeenCalledWith('/crm/dominio/motivos/perda')
    );
  });

  it('cancelado carrega a OUTRA lista de motivos', async () => {
    /*
      As duas listas são separadas de propósito: misturar motivo comercial
      com erro de cadastro tornaria o relatório inútil.
    */
    montar();
    fireEvent.click(screen.getByText('Cancelado'));
    await waitFor(() =>
      expect(mockGet).toHaveBeenCalledWith('/crm/dominio/motivos/cancelamento')
    );
  });

  it('trocar de perdido para cancelado troca a lista', async () => {
    montar();
    fireEvent.click(screen.getByText('Perdido'));
    await waitFor(() => expect(mockGet).toHaveBeenCalledWith('/crm/dominio/motivos/perda'));
    fireEvent.click(screen.getByText('Cancelado'));
    await waitFor(() =>
      expect(mockGet).toHaveBeenCalledWith('/crm/dominio/motivos/cancelamento')
    );
  });

  it('perdido sem motivo não envia', async () => {
    montar();
    fireEvent.click(screen.getByText('Perdido'));
    await screen.findByLabelText('Motivo *');
    fireEvent.click(screen.getByText('Finalizar'));
    expect(await screen.findByText('Informe o motivo.')).toBeInTheDocument();
    expect(mockPost).not.toHaveBeenCalled();
  });

  it('cria motivo novo pelo próprio modal', async () => {
    mockPost.mockResolvedValue({ data: { id: 7, nome: 'Sem verba', slug: 'sem-verba' } });
    montar();
    fireEvent.click(screen.getByText('Perdido'));
    await screen.findByLabelText('Motivo *');
    fireEvent.change(screen.getByLabelText('Criar motivo'), {
      target: { value: 'Sem verba' },
    });
    fireEvent.click(screen.getByText('Adicionar'));
    await waitFor(() =>
      expect(mockPost).toHaveBeenCalledWith('/crm/dominio/motivos/perda', { nome: 'Sem verba' })
    );
  });
});

describe('ModalDesfecho — envio', () => {
  it('o botão começa desabilitado', () => {
    montar();
    expect(screen.getByText('Finalizar').closest('button')).toBeDisabled();
  });

  it('conquistado envia sem motivo', async () => {
    mockPost.mockResolvedValue({ data: { ...OPP, status: 'conquistado' } });
    const { onConcluido } = montar();
    fireEvent.click(screen.getByText('Conquistado'));
    fireEvent.click(screen.getByText('Finalizar'));

    await waitFor(() => expect(mockPost).toHaveBeenCalled());
    const [url, corpo] = mockPost.mock.calls[0];
    expect(url).toBe('/crm/oportunidades/o1/desfecho');
    expect(corpo.status).toBe('conquistado');
    expect(corpo.motivo_desfecho_id).toBeNull();
    await waitFor(() => expect(onConcluido).toHaveBeenCalled());
  });

  it('perdido envia o motivo escolhido', async () => {
    mockPost.mockResolvedValue({ data: { ...OPP, status: 'perdido' } });
    montar();
    fireEvent.click(screen.getByText('Perdido'));
    const select = await screen.findByLabelText('Motivo *');
    fireEvent.change(select, { target: { value: '1' } });
    fireEvent.click(screen.getByText('Finalizar'));

    await waitFor(() => expect(mockPost).toHaveBeenCalled());
    expect(mockPost.mock.calls[0][1].motivo_desfecho_id).toBe(1);
  });

  it('envia a observação quando preenchida', async () => {
    mockPost.mockResolvedValue({ data: OPP });
    montar();
    fireEvent.click(screen.getByText('Conquistado'));
    fireEvent.change(await screen.findByLabelText('Observação (opcional)'), {
      target: { value: 'Assinou dia 10' },
    });
    fireEvent.click(screen.getByText('Finalizar'));
    await waitFor(() =>
      expect(mockPost.mock.calls[0][1].observacoes).toBe('Assinou dia 10')
    );
  });

  it('mostra o erro devolvido pela API', async () => {
    mockPost.mockRejectedValue({
      response: { data: { detail: 'Esta oportunidade já está finalizada.' } },
    });
    montar();
    fireEvent.click(screen.getByText('Conquistado'));
    fireEvent.click(screen.getByText('Finalizar'));
    expect(await screen.findByText('Esta oportunidade já está finalizada.')).toBeInTheDocument();
  });
});
