// web/src/tests/GuiaRoteiro.test.jsx
//
// O Guia do roteiro (07/10/2026): o script resumido do scorecard aberto de
// dentro da reunião. O que estes testes seguram:
//   1. o texto vem do servidor (o mesmo módulo dos 10 itens da avaliação)
//   2. as etapas aparecem na ordem, com o tempo, e cada item com as falas
//   3. "feito" marca e desmarca, e o contador acompanha
//   4. as abas Três 10 e Fechamento mostram as perguntas e as frases
//   5. falha da API vira mensagem, não tela branca
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, fireEvent, cleanup } from '@testing-library/react';

const mockGet = vi.fn();

vi.mock('../api', () => ({
  default: { get: (...a) => mockGet(...a) },
}));

import GuiaRoteiro from '../components/crm/GuiaRoteiro';

const GUIA = {
  versao_roteiro: '2026-09-30',
  duracao_min: 45,
  meta_fala_pct: 40,
  nota_maxima: 20,
  etapas: [
    {
      nome: '1. Abertura', minutos: 5,
      itens: [{
        item: 2, nome: 'Contrato de abertura',
        vale_2: 'Tempo, pauta e o combinado.',
        fazer: 'Combine tempo, pauta e o próximo passo.',
        exemplos: ['Combinamos 45 minutos. Pode ser?'],
        evitar: 'Abrir compartilhando a tela.',
      }],
    },
    {
      nome: '6. Fechamento', minutos: 3,
      itens: [{
        item: 10, nome: 'Próximo passo com data',
        vale_2: 'Dia e hora aceitos.',
        fazer: 'Termine com dia e hora.',
        exemplos: ['Quinta às 10h ou sexta às 15h?'],
        evitar: 'Te mando por e-mail.',
      }],
    },
  ],
  tres_dez: {
    certezas: [
      { nome: 'Produto', sinal_baixo: 'Isso a gente já tem.', como_subir: 'Volte à dor.' },
      { nome: 'Você', sinal_baixo: 'Câmera fechada.', como_subir: 'Resumo.' },
      { nome: 'Controller', sinal_baixo: 'Nunca ouvi falar.', como_subir: 'Caso do setor.' },
    ],
    pergunta_calibracao: 'De 0 a 10, quanto isso resolve?',
    pergunta_o_que_falta: 'O que faltaria para ser um 10?',
    looping_maximo: 2,
  },
  fechamentos: [
    { situacao: 'Decisor ausente', tecnica: 'Reunião com o decisor', frase: 'Vamos marcar 20 minutos?' },
  ],
  pergunta_final: 'Tem alguma coisa que possa impedir a gente de avançar?',
};

beforeEach(() => {
  mockGet.mockReset();
  mockGet.mockResolvedValue({ data: GUIA });
});

afterEach(cleanup);

async function abrir() {
  render(<GuiaRoteiro aberto onFechar={vi.fn()} />);
  await screen.findByText('Contrato de abertura');
}

describe('GuiaRoteiro', () => {
  it('busca o guia no servidor', async () => {
    await abrir();
    expect(mockGet).toHaveBeenCalledWith('/crm/agenda/roteiro/guia');
  });

  it('mostra as etapas com o tempo e as falas de cada item', async () => {
    await abrir();
    expect(screen.getByRole('region', { name: '1. Abertura' })).toBeInTheDocument();
    expect(screen.getByText('5 min')).toBeInTheDocument();
    expect(screen.getByText('“Combinamos 45 minutos. Pode ser?”')).toBeInTheDocument();
    expect(screen.getByText('Abrir compartilhando a tela.')).toBeInTheDocument();
    expect(screen.getByText('Dia e hora aceitos.')).toBeInTheDocument();
  });

  it('marca e desmarca o item como feito, e o contador acompanha', async () => {
    await abrir();
    expect(screen.getByText('0/2 itens feitos')).toBeInTheDocument();
    const botao = screen.getByRole('button', { name: 'Marcar item 2 como feito' });
    fireEvent.click(botao);
    expect(botao).toHaveAttribute('aria-pressed', 'true');
    expect(screen.getByText('1/2 itens feitos')).toBeInTheDocument();
    fireEvent.click(botao);
    expect(screen.getByText('0/2 itens feitos')).toBeInTheDocument();
  });

  it('aba Três 10 mostra as certezas e as perguntas de calibração', async () => {
    await abrir();
    fireEvent.click(screen.getByTestId('tab-guia-tres-dez'));
    expect(screen.getByText('10 no produto')).toBeInTheDocument();
    expect(screen.getByText('10 em você')).toBeInTheDocument();
    expect(screen.getByText('10 na Controller')).toBeInTheDocument();
    expect(screen.getByText('“De 0 a 10, quanto isso resolve?”')).toBeInTheDocument();
    expect(screen.getByText(/No máximo 2/)).toBeInTheDocument();
  });

  it('aba Fechamento mostra a técnica, a frase e a pergunta final', async () => {
    await abrir();
    fireEvent.click(screen.getByTestId('tab-guia-fechamento'));
    expect(screen.getByText('Reunião com o decisor')).toBeInTheDocument();
    expect(screen.getByText('“Vamos marcar 20 minutos?”')).toBeInTheDocument();
    expect(
      screen.getByText('“Tem alguma coisa que possa impedir a gente de avançar?”'),
    ).toBeInTheDocument();
  });

  it('falha da API vira mensagem', async () => {
    mockGet.mockRejectedValue({ response: { data: { detail: 'Sem permissão.' } } });
    render(<GuiaRoteiro aberto onFechar={vi.fn()} />);
    expect(await screen.findByText('Sem permissão.')).toBeInTheDocument();
  });

  it('fechado não busca nada', () => {
    render(<GuiaRoteiro aberto={false} onFechar={vi.fn()} />);
    expect(mockGet).not.toHaveBeenCalled();
  });
});
