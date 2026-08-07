// web/src/tests/KanbanOportunidades.test.jsx
//
// O kanban tem quatro promessas que os testes precisam segurar:
//   1. seis colunas, na ordem do funil, com Suspect na boca
//   2. Finalizado é só leitura — soltar ali abre o desfecho, não move a fase
//   3. os totais do topo são da coluna inteira, não dos cartões visíveis
//   4. a altura é fixa e quem rola é cada coluna, por dentro
import { describe, it, expect, vi, afterEach } from 'vitest';
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

function coluna(fase, rotulo, extra = {}) {
  return {
    fase, rotulo, quantidade: 0, ticket_total: 0, itens: [],
    somente_leitura: false, ...extra,
  };
}

const COLUNAS = [
  coluna('suspect', 'Suspect'),
  coluna('lead', 'Lead', { quantidade: 2, ticket_total: 2000, itens: [item('1'), item('2')] }),
  coluna('qualificacao', 'Qualificação'),
  coluna('apresentacao', 'Apresentação'),
  coluna('negociacao', 'Negociação'),
  coluna('finalizado', 'Finalizado', { somente_leitura: true }),
];

const ROTULOS_ABERTOS = ['Suspect', 'Lead', 'Qualificação', 'Apresentação', 'Negociação'];

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
function arrastar(cartao, colunaAlvo) {
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

const regiao = (rotulo) => screen.getByRole('region', { name: `Fase ${rotulo}` });

afterEach(cleanup);

describe('Kanban — estrutura', () => {
  it('mostra as seis colunas do funil', () => {
    montar();
    for (const r of [...ROTULOS_ABERTOS, 'Finalizado']) {
      expect(regiao(r)).toBeInTheDocument();
    }
  });

  it('Suspect é a primeira coluna e Finalizado a última', () => {
    montar();
    const rotulos = screen.getAllByRole('region').map(
      (s) => s.getAttribute('aria-label')
    );
    expect(rotulos[0]).toBe('Fase Suspect');
    expect(rotulos[rotulos.length - 1]).toBe('Fase Finalizado');
  });

  it('mostra contagem e ticket somado da coluna', () => {
    montar();
    const lead = regiao('Lead');
    expect(lead).toHaveTextContent('2');
    expect(lead.textContent).toMatch(/R\$\s*2\.000,00/);
  });

  it('avisa quando há mais itens do que cartões exibidos', () => {
    montar({
      colunas: COLUNAS.map((c) =>
        c.fase === 'lead' ? { ...c, quantidade: 10, itens: [item('1')] } : c
      ),
    });
    expect(screen.getByText('+9 não exibidas')).toBeInTheDocument();
  });

  it('coluna vazia mostra o estado vazio', () => {
    montar();
    expect(regiao('Negociação')).toHaveTextContent('Vazio');
  });

  it('mostra o indicador de carregando', () => {
    montar({ carregando: true });
    expect(screen.getByText('Carregando funil…')).toBeInTheDocument();
  });
});

describe('Kanban — altura fixa', () => {
  /*
    Requisito de produto: a tela não rola. Com a página inteira rolando,
    arrastar da primeira para a última coluna exigia rolar durante o arrasto,
    e o auto-scroll do DnD nativo é irregular.
  */
  it('cada coluna ocupa a altura toda e rola por dentro', () => {
    montar();
    for (const r of [...ROTULOS_ABERTOS, 'Finalizado']) {
      const secao = regiao(r);
      expect(secao.className).toContain('h-full');
      expect(secao.querySelector('ul').className).toContain('overflow-y-auto');
    }
  });

  it('a faixa de colunas rola na horizontal, não empilha em duas linhas', () => {
    montar();
    const faixa = regiao('Suspect').parentElement;
    expect(faixa.className).toContain('overflow-x-auto');
    expect(faixa.className).not.toContain('flex-wrap');
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
      colunas: COLUNAS.map((c) =>
        c.fase === 'lead' ? { ...c, itens: [item('1', { status: 'suspensa' })] } : c
      ),
    });
    expect(screen.getByText('Suspensa')).toBeInTheDocument();
  });

  it('mostra os EVs envolvidos', () => {
    montar({
      colunas: COLUNAS.map((c) =>
        c.fase === 'lead'
          ? {
              ...c,
              itens: [item('1', {
                envolvidos: [
                  { usuario_id: 'u1', nome: 'Ana', papel: 'EV' },
                  { usuario_id: 'u2', nome: 'Bruno', papel: 'SDR' },
                ],
              })],
            }
          : c
      ),
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

  it('botão Fechar chama o desfecho, não move de fase', () => {
    const { onDesfecho, onMover } = montar();
    fireEvent.click(screen.getByLabelText('Finalizar OPP-2026-00001'));
    expect(onDesfecho).toHaveBeenCalled();
    expect(onMover).not.toHaveBeenCalled();
  });
});

describe('Kanban — coluna Finalizado', () => {
  const comFinalizada = COLUNAS.map((c) =>
    c.fase === 'finalizado'
      ? {
          ...c,
          quantidade: 1,
          ticket_total: 4000,
          itens: [item('9', { fase: 'finalizado', status: 'conquistado' })],
        }
      : c
  );

  it('mostra o status do cartão fechado', () => {
    montar({ colunas: comFinalizada });
    expect(screen.getByText('conquistado')).toBeInTheDocument();
  });

  it('cartão fechado não é arrastável nem tem seletor de fase', () => {
    /*
      Mover de fase exige reabrir, e reabrir é decisão consciente, feita na
      tela da oportunidade.
    */
    montar({ colunas: comFinalizada });
    const cartao = screen.getByText('Empresa 9').closest('li');
    expect(cartao).not.toHaveAttribute('draggable', 'true');
    expect(
      screen.queryByLabelText('Mover OPP-2026-00009 para outra fase')
    ).not.toBeInTheDocument();
    expect(screen.queryByLabelText('Finalizar OPP-2026-00009')).not.toBeInTheDocument();
  });

  it('o ticket dela é rotulado como ganho do mês', () => {
    montar({ colunas: comFinalizada });
    expect(regiao('Finalizado')).toHaveTextContent('ganho no mês');
  });

  it('soltar um cartão nela abre o desfecho e NÃO move a fase', () => {
    /*
      Fechar exige status e motivo. Mover para 'finalizado' direto criaria
      registro sem desfecho, e o backend recusa com 422.
    */
    const { onDesfecho, onMover } = montar();
    arrastar(screen.getByText('Empresa 1').closest('li'), regiao('Finalizado'));
    expect(onMover).not.toHaveBeenCalled();
    expect(onDesfecho).toHaveBeenCalledWith(expect.objectContaining({ id: '1' }));
  });
});

describe('Kanban — drag and drop', () => {
  it('arrastar para outra coluna move a oportunidade', () => {
    const { onMover } = montar();
    arrastar(screen.getByText('Empresa 1').closest('li'), regiao('Negociação'));
    expect(onMover).toHaveBeenCalledWith('1', 'negociacao');
  });

  it('arrastar para trás também move — o funil anda nos dois sentidos', () => {
    const { onMover } = montar();
    arrastar(screen.getByText('Empresa 1').closest('li'), regiao('Suspect'));
    expect(onMover).toHaveBeenCalledWith('1', 'suspect');
  });

  it('soltar na coluna de origem não faz nada', () => {
    /*
      O backend recusaria com "a oportunidade já está nesta fase" — melhor
      nem chamar do que mostrar erro para um gesto sem efeito.
    */
    const { onMover } = montar();
    arrastar(screen.getByText('Empresa 1').closest('li'), regiao('Lead'));
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

  it('o seletor oferece as cinco fases abertas e não Finalizado', () => {
    montar();
    const seletor = screen.getByLabelText('Mover OPP-2026-00001 para outra fase');
    const opcoes = [...seletor.querySelectorAll('option')].map((o) => o.value);
    expect(opcoes).toEqual([
      'suspect', 'lead', 'qualificacao', 'apresentacao', 'negociacao',
    ]);
  });
});
