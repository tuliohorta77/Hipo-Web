// web/src/tests/FunilOportunidades.test.jsx
//
// A visão de funil tem cinco promessas que os testes precisam segurar:
//   1. cinco faixas, na ordem do funil, dimensionadas pela métrica escolhida
//   2. faixa vazia não some — ela é a informação ("esta fase está seca")
//   3. o número entre faixas é PASSAGEM (razão de estoque), não conversão,
//      e não vira Infinity quando a fase de origem está zerada
//   4. clicar na faixa abre o painel da fase, com os filtros da tela
//   5. o painel é operacional: abre, move e finaliza sem sair do funil
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, fireEvent, cleanup, within } from '@testing-library/react';

const mockGet = vi.fn();

vi.mock('../api', () => ({
  default: { get: (...a) => mockGet(...a) },
}));

import FunilOportunidades, { passagem } from '../components/crm/FunilOportunidades';

const OPP = {
  id: 'o1', numero: 'OPP-2026-00001', conta_id: 'c1',
  conta_razao_social: 'Metalurgica Alfa', contato_id: null, contato_nome: null,
  fase: 'negociacao', status: 'ativa', fase_desfecho: null, motivo_desfecho: null,
  valor_mensalidade: 2500, temperatura: 70, previsao_fechamento: '2026-09-30',
  origem_nome: null, finder_conta_id: null, finder_razao_social: null,
  envolvidos: [{ usuario_id: 'u1', nome: 'Ana Vendas', papel: 'EV' }],
  criado_em: '2026-08-01T12:00:00Z', atualizado_em: '2026-08-01T12:00:00Z',
};

const fase = (f, rotulo, quantidade, ticket) => ({
  fase: f, rotulo, quantidade, ticket,
});

const RESUMO = {
  abertas: 20, ticket_aberto: 30000, previsto_no_mes: 5000,
  paradas: 0, ganhas_mes: 2, perdidas_mes: 3,
  por_fase: [
    fase('suspect', 'Suspect', 10, 10000),
    fase('lead', 'Lead', 5, 8000),
    fase('qualificacao', 'Qualificação', 0, 0),
    fase('apresentacao', 'Apresentação', 3, 9000),
    fase('negociacao', 'Negociação', 2, 3000),
  ],
  perda_por_fase: [
    { fase: 'suspect', rotulo: 'Suspect', quantidade: 0 },
    { fase: 'lead', rotulo: 'Lead', quantidade: 4 },
    { fase: 'qualificacao', rotulo: 'Qualificação', quantidade: 0 },
    { fase: 'apresentacao', rotulo: 'Apresentação', quantidade: 0 },
    { fase: 'negociacao', rotulo: 'Negociação', quantidade: 1 },
  ],
};

function montar(props = {}) {
  const onAbrir = vi.fn();
  const onMover = vi.fn();
  const onDesfecho = vi.fn();
  const onTrocarMetrica = vi.fn();
  const utils = render(
    <FunilOportunidades
      resumo={RESUMO}
      carregando={false}
      metrica="quantidade"
      onTrocarMetrica={onTrocarMetrica}
      params={{ q: 'alfa' }}
      onAbrir={onAbrir}
      onMover={onMover}
      onDesfecho={onDesfecho}
      {...props}
    />
  );
  return { ...utils, onAbrir, onMover, onDesfecho, onTrocarMetrica };
}

beforeEach(() => {
  mockGet.mockReset();
  mockGet.mockResolvedValue({
    data: { total: 1, limit: 100, offset: 0, itens: [OPP] },
  });
});

afterEach(cleanup);

describe('FunilOportunidades — o desenho', () => {
  it('mostra as cinco fases abertas, na ordem do funil', () => {
    montar();
    for (const r of ['Suspect', 'Lead', 'Qualificação', 'Apresentação', 'Negociação']) {
      expect(screen.getByLabelText(`Ver oportunidades em ${r}`)).toBeInTheDocument();
    }
  });

  it('a fase finalizada não entra no funil', () => {
    /*
      O funil desenha o pipeline ABERTO. Finalizado é fluxo, não estoque —
      empilhá-lo aqui inflaria a boca do funil com o que já saiu dele.
    */
    montar();
    expect(screen.queryByLabelText('Ver oportunidades em Finalizado')).not.toBeInTheDocument();
  });

  it('a largura é proporcional à maior fase', () => {
    montar();
    expect(screen.getByTestId('faixa-suspect')).toHaveAttribute('data-largura', '100');
    expect(screen.getByTestId('faixa-lead')).toHaveAttribute('data-largura', '50');
  });

  it('fase vazia mantém a largura mínima, para continuar clicável', () => {
    /*
      Zero renderizaria uma tira invisível — e uma faixa que não dá para
      clicar quebra a promessa de que o funil é operacional.
    */
    montar();
    expect(screen.getByTestId('faixa-qualificacao')).toHaveAttribute('data-largura', '8');
  });

  it('trocar para R$ redimensiona pelo valor, não pela quantidade', () => {
    montar({ metrica: 'ticket' });
    // Suspect: 10k de 10k = 100%. Apresentação: 9k de 10k = 90%, embora tenha
    // menos oportunidades que Lead.
    expect(screen.getByTestId('faixa-suspect')).toHaveAttribute('data-largura', '100');
    expect(screen.getByTestId('faixa-apresentacao')).toHaveAttribute('data-largura', '90');
  });

  it('o toggle de métrica avisa a página', () => {
    const { onTrocarMetrica } = montar();
    fireEvent.click(screen.getByRole('button', { name: 'R$' }));
    expect(onTrocarMetrica).toHaveBeenCalledWith('ticket');
  });

  it('mostra a perda histórica ao lado da fase', () => {
    montar();
    expect(screen.getByText('−4 perdidas')).toBeInTheDocument();
  });

  it('estado vazio quando não há nada aberto', () => {
    montar({
      resumo: {
        ...RESUMO,
        por_fase: RESUMO.por_fase.map((f) => ({ ...f, quantidade: 0, ticket: 0 })),
      },
    });
    expect(screen.getByText('Funil vazio')).toBeInTheDocument();
  });

  it('mostra o carregando enquanto a página busca', () => {
    montar({ carregando: true });
    expect(screen.getByText('Carregando funil…')).toBeInTheDocument();
  });
});

describe('FunilOportunidades — passagem entre fases', () => {
  it('é a razão de estoque entre a fase e a seguinte', () => {
    montar();
    // Suspect 10 -> Lead 5 = 50%.
    expect(screen.getByText('50% de passagem')).toBeInTheDocument();
  });

  it('não divide por zero quando a fase de origem está seca', () => {
    /*
      Qualificação tem 0. Sem a guarda, Apresentação/0 renderizaria
      "Infinity% de passagem" — que é pior do que não mostrar número.
    */
    montar();
    expect(screen.getAllByText('—').length).toBeGreaterThan(0);
    expect(screen.queryByText(/Infinity/)).not.toBeInTheDocument();
  });

  it('a última fase não tem seta de passagem', () => {
    montar();
    expect(screen.getAllByText(/de passagem/).length).toBe(3);
  });

  it('passagem() devolve null quando a base é zero', () => {
    expect(passagem({ quantidade: 0 }, { quantidade: 5 }, 'quantidade')).toBeNull();
    expect(passagem({ quantidade: 8 }, { quantidade: 2 }, 'quantidade')).toBe(25);
    expect(passagem({ ticket: 1000 }, { ticket: 250 }, 'ticket')).toBe(25);
  });
});

describe('FunilOportunidades — o painel da fase', () => {
  it('clicar na faixa busca as oportunidades daquela fase, com os filtros da tela', async () => {
    montar();
    fireEvent.click(screen.getByLabelText('Ver oportunidades em Negociação'));
    expect(await screen.findByText('OPP-2026-00001')).toBeInTheDocument();
    expect(mockGet).toHaveBeenCalledWith('/crm/oportunidades', {
      params: {
        q: 'alfa',
        fase: 'negociacao',
        apenas_abertas: true,
        ordenar_por: 'temperatura',
        desc: true,
        limit: 100,
      },
    });
  });

  it('abrir o cartão devolve o id para a página', async () => {
    const { onAbrir } = montar();
    fireEvent.click(screen.getByLabelText('Ver oportunidades em Negociação'));
    fireEvent.click(await screen.findByText('Metalurgica Alfa'));
    expect(onAbrir).toHaveBeenCalledWith('o1');
  });

  it('mover de fase pelo painel chama a página', async () => {
    const { onMover } = montar();
    fireEvent.click(screen.getByLabelText('Ver oportunidades em Negociação'));
    const seletor = await screen.findByLabelText('Mover OPP-2026-00001 para outra fase');
    fireEvent.change(seletor, { target: { value: 'lead' } });
    expect(onMover).toHaveBeenCalledWith('o1', 'lead');
  });

  it('o seletor do cartão oferece só as cinco fases abertas', async () => {
    montar();
    fireEvent.click(screen.getByLabelText('Ver oportunidades em Negociação'));
    const seletor = await screen.findByLabelText('Mover OPP-2026-00001 para outra fase');
    const opcoes = [...seletor.querySelectorAll('option')].map((o) => o.value);
    expect(opcoes).toEqual([
      'suspect', 'lead', 'qualificacao', 'apresentacao', 'negociacao',
    ]);
  });

  it('finalizar pelo painel abre o desfecho na página', async () => {
    const { onDesfecho } = montar();
    fireEvent.click(screen.getByLabelText('Ver oportunidades em Negociação'));
    fireEvent.click(await screen.findByLabelText('Finalizar OPP-2026-00001'));
    expect(onDesfecho).toHaveBeenCalledWith(expect.objectContaining({ id: 'o1' }));
  });

  it('clicar de novo na mesma faixa fecha o painel', async () => {
    montar();
    const faixa = screen.getByLabelText('Ver oportunidades em Negociação');
    fireEvent.click(faixa);
    await screen.findByText('OPP-2026-00001');
    fireEvent.click(faixa);
    expect(screen.queryByText('OPP-2026-00001')).not.toBeInTheDocument();
  });

  it('o botão X fecha o painel', async () => {
    montar();
    fireEvent.click(screen.getByLabelText('Ver oportunidades em Negociação'));
    await screen.findByText('OPP-2026-00001');
    fireEvent.click(screen.getByLabelText('Fechar painel da fase'));
    expect(screen.queryByText('OPP-2026-00001')).not.toBeInTheDocument();
  });

  it('o cabeçalho do painel traz os totais da fase', async () => {
    montar();
    fireEvent.click(screen.getByLabelText('Ver oportunidades em Apresentação'));
    const painel = within(await screen.findByLabelText('Oportunidades em Apresentação'));
    expect(painel.getByText(/3 em aberto/)).toBeInTheDocument();
  });

  it('falha na busca não derruba o funil', async () => {
    mockGet.mockRejectedValue(new Error('offline'));
    montar();
    fireEvent.click(screen.getByLabelText('Ver oportunidades em Negociação'));
    expect(
      await screen.findByText('Não foi possível carregar as oportunidades desta fase.')
    ).toBeInTheDocument();
    // O desenho continua de pé.
    expect(screen.getByTestId('faixa-suspect')).toBeInTheDocument();
  });

  it('avisa quando há mais oportunidades do que as carregadas', async () => {
    mockGet.mockResolvedValue({
      data: { total: 40, limit: 100, offset: 0, itens: [OPP] },
    });
    montar();
    fireEvent.click(screen.getByLabelText('Ver oportunidades em Negociação'));
    expect(await screen.findByText('+39 não exibidas')).toBeInTheDocument();
  });
});
