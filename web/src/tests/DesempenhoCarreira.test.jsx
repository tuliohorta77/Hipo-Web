// web/src/tests/DesempenhoCarreira.test.jsx
//
// Carreira · Desempenho. O que estes testes seguram:
//   1. abre no ponto de atenção, com quanto falta e o atalho para agir
//   2. a tabela mostra meta de hoje só no mês aberto
//   3. sem meta cadastrada, avisa onde a gestão grava
//   4. navegar de mês mexe na URL; não há próximo mês a partir do corrente
//   5. gestão escolhe a pessoa (modo leitura, sem atalhos de ação)
//   6. cargo sem squad explica, em vez de mostrar zeros
//   7. EV vê o Scorecard das reuniões: média, foco, itens e a lista que abre
//      a reunião; sem scorecard (SDR, EC) o card não aparece
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, fireEvent, cleanup, within } from '@testing-library/react';
import { MemoryRouter, Route, Routes, useLocation } from 'react-router-dom';

const mockGet = vi.fn();
vi.mock('../api', () => ({
  default: { get: (...a) => mockGet(...a) },
  getUser: () => ({ id: 'u1', nome: 'Jakeline', cargo: 'EV' }),
  getModulos: () => ['perfil', 'crm'],
}));

// O formulário da reunião tem a própria suíte (ModalReuniao.test.jsx).
vi.mock('../components/crm/ModalReuniao', () => ({
  default: ({ reuniaoId, onFechar }) => (
    <div data-testid="modal-reuniao">
      reunião {reuniaoId}
      <button type="button" onClick={onFechar}>fechar reunião</button>
    </div>
  ),
}));

import Desempenho, { mesVizinho, telaDoIndicador } from '../pages/carreira/Desempenho';
import { faixaDoItem } from '../components/carreira/ScorecardDesempenho';

function linha(extra = {}) {
  return {
    chave: 'nmrr', rotulo: 'NMRR', formato: 'moeda', natureza: 'acumulativo',
    fonte: 'Soma da mensalidade das vendas do mês.', principal: true, posicao: false,
    realizado: 450, meta_mes: 2000, meta_hoje: 1000, atingimento: 0.45, carinha: 'bravo',
    falta_mes: 1550, realizado_txt: 'R$ 450', meta_mes_txt: 'R$ 2.000',
    meta_hoje_txt: 'R$ 1.000', falta_mes_txt: 'R$ 1.550',
    ...extra,
  };
}

function resposta(extra = {}) {
  const indicadores = [
    linha(),
    linha({
      chave: 'propostas', rotulo: 'PROPOSTAS ENVIADAS', formato: 'inteiro', principal: false,
      realizado: 4, meta_mes: null, meta_hoje: null, atingimento: null, carinha: null,
      falta_mes: null, realizado_txt: '4', meta_mes_txt: '', meta_hoje_txt: '', falta_mes_txt: '',
    }),
  ];
  return {
    pessoa: { id: 'u1', nome: 'Jakeline', cargo: 'EV' },
    modo_leitura: false, pode_escolher_pessoa: false, pessoas: [],
    ano: 2026, mes: 10, rotulo: 'outubro/2026', aberto: true,
    mes_atual: { ano: 2026, mes: 10 }, squad: 'EV',
    dia_util: 10, dias_uteis: 21, tem_meta: true,
    indicadores,
    ponto_de_atencao: indicadores[0],
    funil: [
      { chave: 'reunioes_realizadas', rotulo: 'Reuniões realizadas', valor: 8, valor_txt: '8', taxa: null, taxa_txt: '', taxa_rotulo: '' },
      { chave: 'propostas', rotulo: 'Propostas', valor: 4, valor_txt: '4', taxa: 0.5, taxa_txt: '50%', taxa_rotulo: 'das reuniões viraram proposta' },
    ],
    historico: [
      { ano: 2026, mes: 9, rotulo: 'setembro', indicadores: { nmrr: { realizado_txt: 'R$ 900', atingimento: 1.0, atingimento_txt: '100%' }, propostas: { realizado_txt: '5', atingimento: null, atingimento_txt: '' } } },
      { ano: 2026, mes: 10, rotulo: 'outubro', indicadores: { nmrr: { realizado_txt: 'R$ 450', atingimento: 0.23, atingimento_txt: '23%' }, propostas: { realizado_txt: '4', atingimento: null, atingimento_txt: '' } } },
    ],
    ...extra,
  };
}

function Onde() {
  const l = useLocation();
  return <p data-testid="onde">{l.pathname}{l.search}</p>;
}

function renderizar(caminho = '/carreira/desempenho') {
  return render(
    <MemoryRouter initialEntries={[caminho]}>
      <Onde />
      <Routes>
        <Route path="/carreira/desempenho" element={<Desempenho />} />
        <Route path="/crm/oportunidades" element={<p>tela de oportunidades</p>} />
      </Routes>
    </MemoryRouter>,
  );
}

beforeEach(() => { mockGet.mockReset(); });
afterEach(cleanup);

describe('regras da tela', () => {
  it('mês vizinho atravessa o ano', () => {
    expect(mesVizinho(2026, 1, -1)).toEqual({ ano: 2025, mes: 12 });
    expect(mesVizinho(2026, 12, 1)).toEqual({ ano: 2027, mes: 1 });
    expect(mesVizinho(2026, 5, 1)).toEqual({ ano: 2026, mes: 6 });
  });

  it('cada indicador sabe onde se age; desconhecido não ganha atalho', () => {
    expect(telaDoIndicador('SDR', 'agendamentos').rota).toBe('/crm/agenda');
    expect(telaDoIndicador('EC', 'contas_gestao').rota).toBe('/crm/parceiros');
    expect(telaDoIndicador('EV', 'nao_existe')).toBeNull();
  });
});

describe('Desempenho', () => {
  it('abre no ponto de atenção, com quanto falta e onde agir', async () => {
    mockGet.mockResolvedValue({ data: resposta() });
    renderizar();
    const atencao = await screen.findByTestId('ponto-de-atencao');
    expect(within(atencao).getByText(/Seu ponto de atenção: NMRR/)).toBeInTheDocument();
    expect(within(atencao).getByText('45%')).toBeInTheDocument();
    expect(within(atencao).getByText('R$ 1.550')).toBeInTheDocument();
    fireEvent.click(within(atencao).getByRole('button', { name: /Agir em Oportunidades/ }));
    expect(await screen.findByText('tela de oportunidades')).toBeInTheDocument();
    expect(mockGet).toHaveBeenCalledWith('/carreira/desempenho', { params: {} });
  });

  it('mês aberto mostra a meta de hoje e o ritmo; indicador sem meta diz isso', async () => {
    mockGet.mockResolvedValue({ data: resposta() });
    renderizar();
    expect(await screen.findByText(/dia útil 10 de 21/)).toBeInTheDocument();
    expect(screen.getByRole('columnheader', { name: 'Meta de hoje' })).toBeInTheDocument();
    const prop = screen.getByTestId('ind-propostas');
    expect(within(prop).getByText('sem meta')).toBeInTheDocument();
    // Funil e histórico.
    expect(screen.getByText('das reuniões viraram proposta')).toBeInTheDocument();
    expect(screen.getByText('100%')).toBeInTheDocument();
  });

  it('mês fechado não tem coluna de meta de hoje', async () => {
    mockGet.mockResolvedValue({ data: resposta({ aberto: false, mes: 9, rotulo: 'setembro/2026', dia_util: null }) });
    renderizar('/carreira/desempenho?ano=2026&mes=9');
    expect(await screen.findByText(/mês fechado/)).toBeInTheDocument();
    expect(screen.queryByRole('columnheader', { name: 'Meta de hoje' })).toBeNull();
    expect(mockGet).toHaveBeenCalledWith('/carreira/desempenho', { params: { ano: '2026', mes: '9' } });
  });

  it('sem meta cadastrada, avisa onde a gestão grava', async () => {
    mockGet.mockResolvedValue({ data: resposta({ tem_meta: false, ponto_de_atencao: null }) });
    renderizar();
    expect(await screen.findByText(/ainda não foi cadastrada/)).toBeInTheDocument();
    expect(screen.queryByTestId('ponto-de-atencao')).toBeNull();
  });

  it('navega de mês pela URL e não avança além do corrente', async () => {
    mockGet.mockResolvedValue({ data: resposta() });
    renderizar();
    await screen.findByTestId('mes-desempenho');
    expect(screen.getByRole('button', { name: 'Próximo mês' })).toBeDisabled();
    fireEvent.click(screen.getByRole('button', { name: 'Mês anterior' }));
    expect(screen.getByTestId('onde').textContent).toBe('/carreira/desempenho?ano=2026&mes=9');
  });

  it('voltar ao mês corrente limpa ano e mês da URL', async () => {
    mockGet.mockResolvedValue({ data: resposta({ aberto: false, ano: 2026, mes: 9, rotulo: 'setembro/2026' }) });
    renderizar('/carreira/desempenho?ano=2026&mes=9');
    await screen.findByTestId('mes-desempenho');
    fireEvent.click(screen.getByRole('button', { name: 'Próximo mês' }));
    expect(screen.getByTestId('onde').textContent).toBe('/carreira/desempenho');
  });

  it('gestão escolhe a pessoa e vê em modo leitura, sem atalhos de ação', async () => {
    mockGet.mockResolvedValue({
      data: resposta({
        modo_leitura: true, pode_escolher_pessoa: true,
        pessoa: { id: 'u9', nome: 'Kethlleen', cargo: 'SDR' },
        pessoas: [{ id: 'u9', nome: 'Kethlleen', cargo: 'SDR' }, { id: 'u8', nome: 'Aline', cargo: 'EC' }],
      }),
    });
    renderizar('/carreira/desempenho?usuario_id=u9');
    expect(await screen.findByText('Carreira · Kethlleen')).toBeInTheDocument();
    expect(screen.getByText(/Ponto de atenção: NMRR/)).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /Agir em/ })).toBeNull();
    fireEvent.change(screen.getByLabelText('Pessoa'), { target: { value: 'u8' } });
    expect(screen.getByTestId('onde').textContent).toBe('/carreira/desempenho?usuario_id=u8');
  });

  it('cargo sem squad explica, em vez de mostrar zeros', async () => {
    mockGet.mockResolvedValue({
      data: resposta({ squad: null, indicadores: [], funil: [], historico: [], ponto_de_atencao: null, tem_meta: false }),
    });
    renderizar();
    expect(await screen.findByText('Este cargo não tem metas individuais na RPeR')).toBeInTheDocument();
  });

  it('erro da API aparece com as abas', async () => {
    mockGet.mockRejectedValue(Object.assign(new Error('x'), { response: { status: 403, data: { detail: 'Só a gestão abre a UC de outra pessoa.' } } }));
    renderizar('/carreira/desempenho?usuario_id=u9');
    expect(await screen.findByText('Só a gestão abre a UC de outra pessoa.')).toBeInTheDocument();
    expect(screen.getByRole('navigation', { name: 'Carreira' })).toBeInTheDocument();
  });
});

function scorecard(extra = {}) {
  const nomes = ['Preparação', 'Contrato de abertura', 'Perguntas de Situação', 'Perguntas de Problema',
    'Perguntas de Implicação', 'Resumo de confirmação', 'GPCT: prazo, decisor e consequência',
    'Apresentação ligada às dores', 'Objeções com LAER', 'Próximo passo com data'];
  const itens = nomes.map((nome, i) => {
    const media = i === 4 ? 0.5 : 1.5;
    return { item: i + 1, nome, etapa: 'x', media, media_txt: media.toFixed(1).replace('.', ','), fracao: media / 2 };
  });
  return {
    media: 13.5, media_txt: '13,5', nota_maxima: 20, avaliadas: 2, realizadas: 3, sem_nota: 1,
    meta: 15, meta_txt: '15,0', meta_padrao: true, atingimento: 0.9, carinha: 'neutro', faixa: 'media',
    itens, item_fraco: itens[4],
    foco: { texto: 'Fazer duas perguntas de implicação antes de apresentar.', reuniao_id: 'r2', empresa: 'Metalúrgica Alfa', data: '2026-10-06T13:00:00Z' },
    reunioes: [
      { reuniao_id: 'r3', data: '2026-10-07T13:00:00Z', empresa: 'Padaria Beta', oportunidade_numero: 'OPP-3', nota: null, nota_status: 'avaliando', faixa: null },
      { reuniao_id: 'r2', data: '2026-10-06T13:00:00Z', empresa: 'Metalúrgica Alfa', oportunidade_numero: 'OPP-2', nota: 16, nota_status: 'validada', faixa: 'boa' },
      { reuniao_id: 'r1', data: '2026-10-02T13:00:00Z', empresa: 'Gráfica Gama', oportunidade_numero: 'OPP-1', nota: 11, nota_status: 'ia', faixa: 'media' },
    ],
    historico: [
      { ano: 2026, mes: 9, rotulo: 'setembro', media: 12, media_txt: '12,0', avaliadas: 4, faixa: 'media' },
      { ano: 2026, mes: 10, rotulo: 'outubro', media: 13.5, media_txt: '13,5', avaliadas: 2, faixa: 'media' },
    ],
    ...extra,
  };
}

describe('Scorecard das reuniões (EV)', () => {
  it('faixa do item: 1,5+ boa, 1+ média, abaixo baixa', () => {
    expect(faixaDoItem(2)).toBe('boa');
    expect(faixaDoItem(1)).toBe('media');
    expect(faixaDoItem(0.5)).toBe('baixa');
    expect(faixaDoItem(null)).toBeNull();
  });

  it('mostra a média contra a meta, o foco e os itens', async () => {
    mockGet.mockResolvedValue({ data: resposta({ scorecard: scorecard() }) });
    renderizar();
    const card = await screen.findByTestId('scorecard');
    expect(within(card).getByTestId('scorecard-media').textContent).toBe('13,5');
    expect(within(card).getByText(/padrão do roteiro/)).toBeInTheDocument();
    expect(within(card).getByText(/2 de 3 reuniões realizadas avaliadas/)).toBeInTheDocument();
    const foco = within(card).getByTestId('scorecard-foco');
    expect(within(foco).getByText('Seu foco')).toBeInTheDocument();
    expect(within(foco).getByText('Perguntas de Implicação')).toBeInTheDocument();
    expect(within(foco).getByText(/Fazer duas perguntas de implicação/)).toBeInTheDocument();
    expect(within(card).getByTestId('item-5')).toHaveTextContent('0,5');
    // Nota de cada reunião e o selo de validada.
    expect(within(card).getByText('16/20')).toBeInTheDocument();
    expect(within(card).getByLabelText('Validada pela gestão')).toBeInTheDocument();
    expect(within(card).getByText('avaliando…')).toBeInTheDocument();
    // Histórico.
    expect(within(card).getByText('12,0')).toBeInTheDocument();
  });

  it('clicar na reunião abre o formulário com o scorecard completo', async () => {
    mockGet.mockResolvedValue({ data: resposta({ scorecard: scorecard() }) });
    renderizar();
    const card = await screen.findByTestId('scorecard');
    fireEvent.click(within(card).getByRole('button', { name: 'Abrir reunião com Gráfica Gama' }));
    expect(screen.getByTestId('modal-reuniao')).toHaveTextContent('reunião r1');
    expect(mockGet).toHaveBeenCalledWith('/crm/dominio/usuarios');
    fireEvent.click(screen.getByRole('button', { name: 'fechar reunião' }));
    expect(screen.queryByTestId('modal-reuniao')).toBeNull();
  });

  it('sem reunião avaliada não inventa nota', async () => {
    mockGet.mockResolvedValue({
      data: resposta({
        scorecard: scorecard({
          media: null, media_txt: '—', avaliadas: 0, realizadas: 2, sem_nota: 2,
          atingimento: null, carinha: null, faixa: null, item_fraco: null, foco: null,
        }),
      }),
    });
    renderizar();
    const card = await screen.findByTestId('scorecard');
    expect(within(card).getByText(/Nenhuma reunião avaliada ainda/)).toBeInTheDocument();
    expect(within(card).queryByTestId('scorecard-foco')).toBeNull();
    expect(within(card).queryByTestId('item-1')).toBeNull();
  });

  it('quem não é EV não tem o card', async () => {
    mockGet.mockResolvedValue({ data: resposta({ scorecard: null }) });
    renderizar();
    await screen.findByTestId('mes-desempenho');
    expect(screen.queryByTestId('scorecard')).toBeNull();
  });

  it('gestão em modo leitura vê o foco da pessoa', async () => {
    mockGet.mockResolvedValue({
      data: resposta({ modo_leitura: true, pode_escolher_pessoa: true, scorecard: scorecard() }),
    });
    renderizar('/carreira/desempenho?usuario_id=u1');
    const card = await screen.findByTestId('scorecard');
    expect(within(card).getByText('Foco')).toBeInTheDocument();
  });
});
