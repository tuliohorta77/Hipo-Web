// web/src/tests/KanbanOportunidades.test.jsx
//
// O kanban tem duas promessas que os testes precisam segurar:
//   1. a coluna Finalizado NÃO existe — fechar exige status e motivo
//   2. os totais do topo são da coluna inteira, não dos cartões visíveis
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, fireEvent, cleanup } from '@testing-library/react';

import KanbanOportunidades from '../components/crm/KanbanOportunidades';

function item(id, extra = {}) {
  return {
    id,
    numero: `OPP-2026-0000${id}`,
    conta_razao_social: `Empresa ${id}`,
    fase: 'lead',
    status: 'ativa',
    valor_mensalidade: 1000,
    temperatura: 50,
    previsao_fechamento: '2026-09-30',
    envolvidos: [],
    ...extra,
  };
}

const COLUNAS = [
  { fase: 'lead', rotulo: 'Lead', quantidade: 2, ticket_total: 2000, itens: [item('1'), item('2')] },
  { fase: 'qualificacao', rotulo: 'Qualificação', quantidade: 0, ticket_total: 0, itens: [] },
  { fase: 'apresentacao', rotulo: 'Apresentação', quantidade: 0, ticket_total: 0, itens: [] },
  { fase: 'negociacao', rotulo: 'Negociação', quantidade: 0, ticket_total: 0, itens: [] },
];

function montar(props = {}) {
  const onAbrir = vi.fn();
  const onMover = vi.fn();
  const onDesfecho = vi.fn();
  render(
    <KanbanOportunidades
      colunas={COLUNAS}
      carregando={false}
      onAbrir={onAbrir}
      onMover={onMover}
      onDesfecho={onDesfecho}
      {...props}
    />
  );
  return { onAbrir, onMover, onDesfecho };
}

/** Simula um drag-and-drop nativo entre colunas. */
function arrastar(cartao, colunaAlvo, id) {
  const dados = new Map();
  const dataTransfer = {
    setData: (k, v) => dados.set(k, v),
    getData: (k) => dados.get(k),
    effectAllowed: '',
  };
  fireEvent.dragStart(cartao, { dataTransfer });
  fireEvent.dragOver(colunaAlvo, { dataTransfer });
  fireEvent.drop(colunaAlvo, { dataTransfer });
}

afterEach(cleanup);

describe('Kanban — estrutura', () => {
  it('mostra as quatro colunas abertas', () => {
    montar();
    for (const r of ['Lead', 'Qualificação', 'Apresentação', 'Negociação']) {
      expect(screen.getByRole('region', { name: `Fase ${r}` })).toBeInTheDocument();
    }
  });

  it('não tem coluna Finalizado', () => {
    /*
      Fechar exige status e motivo. Uma coluna Finalizado permitiria soltar um
      cartão lá e criar registro sem desfecho — o backend recusa isso com 422.
    */
    montar();
    expect(screen.queryByRole('region', { name: /Finalizado/ })).not.toBeInTheDocument();
  });

  it('mostra contagem e ticket somado da coluna', () => {
    montar();
    const lead = screen.getByRole('region', { name: 'Fase Lead' });
    expect(lead).toHaveTextContent('2');
    expect(lead.textContent).toMatch(/R\$\s*2\.000,00/);
  });

  it('avisa quando há mais itens do que cartões exibidos', () => {
    montar({
      colunas: [
        { ...COLUNAS[0], quantidade: 10, itens: [item('1')] },
        ...COLUNAS.slice(1),
      ],
    });
    expect(screen.getByText('+9 não exibidas')).toBeInTheDocument();
  });

  it('coluna vazia mostra o estado vazio', () => {
    montar();
    const vazia = screen.getByRole('region', { name: 'Fase Negociação' });
    expect(vazia).toHaveTextContent('Vazio');
  });

  it('mostra o indicador de carregando', () => {
    montar({ carregando: true });
    expect(screen.getByText('Carregando funil…')).toBeInTheDocument();
  });
});

describe('Kanban — cartão', () => {
  it('mostra empresa, número e valor', () => {
    montar();
    expect(screen.getByText('Empresa 1')).toBeInTheDocument();
    expect(screen.getByText('OPP-2026-00001')).toBeInTheDocument();
  });

  it('marca oportunidade suspensa', () => {
    montar({
      colunas: [{ ...COLUNAS[0], itens: [item('1', { status: 'suspensa' })] }, ...COLUNAS.slice(1)],
    });
    expect(screen.getByText('Suspensa')).toBeInTheDocument();
  });

  it('mostra os EVs envolvidos', () => {
    montar({
      colunas: [
        {
          ...COLUNAS[0],
          itens: [item('1', {
            envolvidos: [
              { usuario_id: 'u1', nome: 'Ana', papel: 'EV' },
              { usuario_id: 'u2', nome: 'Bruno', papel: 'SDR' },
            ],
          })],
        },
        ...COLUNAS.slice(1),
      ],
    });
    // Só EV aparece no cartão — é quem responde pelo negócio.
    expect(screen.getByText('Ana')).toBeInTheDocument();
    expect(screen.queryByText('Bruno')).not.toBeInTheDocument();
  });

  it('clicar no cartão abre a oportunidade', () => {
    const { onAbrir } = montar();
    fireEvent.click(screen.getByText('Empresa 1'));
    expect(onAbrir).toHaveBeenCalledWith('1');
  });

  it('botão Finalizar chama o desfecho, não move de fase', () => {
    const { onDesfecho, onMover } = montar();
    fireEvent.click(screen.getByLabelText('Finalizar OPP-2026-00001'));
    expect(onDesfecho).toHaveBeenCalled();
    expect(onMover).not.toHaveBeenCalled();
  });
});

describe('Kanban — drag and drop', () => {
  it('arrastar para outra coluna move a oportunidade', () => {
    const { onMover } = montar();
    const cartao = screen.getByText('Empresa 1').closest('li');
    const alvo = screen.getByRole('region', { name: 'Fase Negociação' });
    arrastar(cartao, alvo, '1');
    expect(onMover).toHaveBeenCalledWith('1', 'negociacao');
  });

  it('soltar na coluna de origem não faz nada', () => {
    /*
      O backend recusaria com "a oportunidade já está nesta fase" — melhor
      nem chamar do que mostrar erro para um gesto sem efeito.
    */
    const { onMover } = montar();
    const cartao = screen.getByText('Empresa 1').closest('li');
    const mesma = screen.getByRole('region', { name: 'Fase Lead' });
    arrastar(cartao, mesma, '1');
    expect(onMover).not.toHaveBeenCalled();
  });
});

describe('Kanban — acessibilidade', () => {
  it('cada cartão tem seletor de fase, alternativa ao arrastar', () => {
    /*
      Drag-and-drop nativo não funciona por teclado. O select faz a mesma
      coisa e é operável por quem não usa mouse.
    */
    const { onMover } = montar();
    const seletor = screen.getByLabelText('Mover OPP-2026-00001 para outra fase');
    fireEvent.change(seletor, { target: { value: 'apresentacao' } });
    expect(onMover).toHaveBeenCalledWith('1', 'apresentacao');
  });

  it('o seletor não oferece a fase Finalizado', () => {
    montar();
    const seletor = screen.getByLabelText('Mover OPP-2026-00001 para outra fase');
    const opcoes = [...seletor.querySelectorAll('option')].map((o) => o.value);
    expect(opcoes).toEqual(['lead', 'qualificacao', 'apresentacao', 'negociacao']);
  });
});
