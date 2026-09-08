// web/src/tests/ModalDesfecho.test.jsx
//
// A distinção Perdido × Cancelado é a decisão mais fácil de errar do sistema:
// perdido entra na taxa de conversão, cancelado fica fora de todo denominador.
// Por isso a tela explica a consequência de cada opção, e o teste segura esse
// texto — se alguém "limpar" o modal removendo as explicações, quebra aqui.
//
// A segunda regra que este arquivo segura é a do REGISTRO DO FECHAMENTO: não
// se finaliza uma oportunidade sem contar o que aconteceu. É a única exceção
// da regra "toda tarefa concluída exige a próxima", e era por ela que o
// histórico do negócio vazava no momento em que ele mais importa.
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, fireEvent, cleanup, waitFor } from '@testing-library/react';

const mockGet = vi.fn();
const mockPost = vi.fn();

vi.mock('../api', () => ({
  default: { get: (...a) => mockGet(...a), post: (...a) => mockPost(...a) },
  getUser: () => USUARIO_LOGADO,
}));

import ModalDesfecho from '../components/crm/ModalDesfecho';

const USUARIO_LOGADO = { id: 'u-logado', nome: 'Aline Martins' };
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

/** Escolhe o desfecho e preenche o registro — o caminho feliz completo. */
async function escolherEPreencher(rotulo, titulo = 'Reunião de fechamento') {
  fireEvent.click(screen.getByText(rotulo));
  fireEvent.change(await screen.findByLabelText('O que aconteceu *'), {
    target: { value: titulo },
  });
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
    if (url === '/crm/dominio/usuarios') {
      return Promise.resolve({ data: [
        { id: 'u-logado', nome: 'Aline Martins' },
        { id: 'u-2', nome: 'Bruno Gonçalo' },
      ] });
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
    await escolherEPreencher('Perdido');
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

describe('ModalDesfecho — registro do fechamento obrigatório', () => {
  it('o formulário do registro só aparece depois de escolher o desfecho', async () => {
    montar();
    expect(screen.queryByLabelText('O que aconteceu *')).not.toBeInTheDocument();
    fireEvent.click(screen.getByText('Conquistado'));
    expect(await screen.findByLabelText('O que aconteceu *')).toBeInTheDocument();
  });

  it('escolher o desfecho não basta: sem o registro o botão continua travado', async () => {
    montar();
    fireEvent.click(screen.getByText('Conquistado'));
    await screen.findByLabelText('O que aconteceu *');
    expect(screen.getByText('Finalizar').closest('button')).toBeDisabled();
  });

  it('com o registro preenchido o botão libera', async () => {
    montar();
    await escolherEPreencher('Conquistado');
    await waitFor(() =>
      expect(screen.getByText('Finalizar').closest('button')).not.toBeDisabled()
    );
  });

  it('título só de espaço não conta como registro', async () => {
    montar();
    await escolherEPreencher('Conquistado', '   ');
    expect(screen.getByText('Finalizar').closest('button')).toBeDisabled();
  });

  it('envia o registro junto do desfecho, numa chamada só', async () => {
    /*
      Uma chamada, não duas: o backend cria a tarefa na mesma transação. Duas
      chamadas daqui deixariam a oportunidade finalizada sem registro se a
      segunda falhasse — que é exatamente o buraco que a regra tapa.
    */
    mockPost.mockResolvedValue({ data: { ...OPP, status: 'conquistado' } });
    montar();
    await escolherEPreencher('Conquistado', 'Reunião — cliente aprovou as 40 vidas');
    fireEvent.click(screen.getByText('Finalizar'));

    await waitFor(() => expect(mockPost).toHaveBeenCalled());
    expect(mockPost).toHaveBeenCalledTimes(1);
    const [url, corpo] = mockPost.mock.calls[0];
    expect(url).toBe('/crm/oportunidades/o1/desfecho');
    expect(corpo.tarefa.titulo).toBe('Reunião — cliente aprovou as 40 vidas');
    expect(corpo.tarefa.tipo).toBe('reuniao');
    expect(corpo.tarefa.prazo).toBeTruthy();
  });

  it('cancelado também exige o registro', async () => {
    /*
      Cancelar é erro nosso de cadastro. Saber quem descobriu — e como — é o
      que impede o mesmo erro de entrar de novo pela mesma porta.
    */
    montar();
    fireEvent.click(screen.getByText('Cancelado'));
    expect(await screen.findByLabelText('O que aconteceu *')).toBeInTheDocument();
    expect(screen.getByText('Finalizar').closest('button')).toBeDisabled();
  });

  it('o registro já vem no nome de quem está finalizando', async () => {
    /*
      Quem fecha o negócio é quase sempre quem esteve na reunião. Obrigar a
      escolher no seletor seria atrito no momento em que a pessoa só quer
      registrar que ganhou.
    */
    mockPost.mockResolvedValue({ data: OPP });
    montar();
    await escolherEPreencher('Conquistado');
    fireEvent.click(screen.getByText('Finalizar'));
    await waitFor(() => expect(mockPost).toHaveBeenCalled());
    expect(mockPost.mock.calls[0][1].tarefa.responsavel_id).toBe('u-logado');
  });

  it('permite atribuir o registro a outra pessoa', async () => {
    mockPost.mockResolvedValue({ data: OPP });
    montar();
    await escolherEPreencher('Conquistado');
    fireEvent.change(await screen.findByLabelText('Quem fez'), {
      target: { value: 'u-2' },
    });
    fireEvent.click(screen.getByText('Finalizar'));
    await waitFor(() => expect(mockPost).toHaveBeenCalled());
    expect(mockPost.mock.calls[0][1].tarefa.responsavel_id).toBe('u-2');
  });

  it('o detalhe do registro vai separado da observação da oportunidade', async () => {
    mockPost.mockResolvedValue({ data: OPP });
    montar();
    await escolherEPreencher('Conquistado');
    fireEvent.change(screen.getByLabelText('Detalhe (opcional)'), {
      target: { value: 'RH e diretoria presentes' },
    });
    fireEvent.change(screen.getByLabelText('Observação (opcional)'), {
      target: { value: 'Assinou dia 10' },
    });
    fireEvent.click(screen.getByText('Finalizar'));

    await waitFor(() => expect(mockPost).toHaveBeenCalled());
    const corpo = mockPost.mock.calls[0][1];
    expect(corpo.tarefa.descricao).toBe('RH e diretoria presentes');
    expect(corpo.observacoes).toBe('Assinou dia 10');
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
    await escolherEPreencher('Conquistado');
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
    await escolherEPreencher('Perdido');
    const select = await screen.findByLabelText('Motivo *');
    fireEvent.change(select, { target: { value: '1' } });
    fireEvent.click(screen.getByText('Finalizar'));

    await waitFor(() => expect(mockPost).toHaveBeenCalled());
    expect(mockPost.mock.calls[0][1].motivo_desfecho_id).toBe(1);
  });

  it('envia a observação quando preenchida', async () => {
    mockPost.mockResolvedValue({ data: OPP });
    montar();
    await escolherEPreencher('Conquistado');
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
    await escolherEPreencher('Conquistado');
    fireEvent.click(screen.getByText('Finalizar'));
    expect(await screen.findByText('Esta oportunidade já está finalizada.')).toBeInTheDocument();
  });
});
