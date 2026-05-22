// web/src/tests/Bastoes.test.jsx
//
// Testes da página de aprovação de bastões.
// v1.2.0 etapa 4: página busca /carteira/bastoes/todos (não mais /pendentes).
//
// Cobre:
//   - render básico (titulo + estado vazio se fila vazia)
//   - render com 1 bastão pendente (mostra Hunter, Farmer, contador, botões)
//   - clica em Aprovar → chama PATCH /aprovar
//   - clica em Rejeitar → abre modal, valida motivo, confirma chama PATCH /rejeitar
//   - aba Aprovados mostra os bastões aprovados de verdade
//   - KPIs refletem a contagem por status
//
// Notas:
//   - "Rejeitar bastão" aparece em 2 lugares no modal (titulo + botao).
//     Usamos getByRole pra distinguir: heading vs button.

import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { MemoryRouter } from 'react-router-dom';
import Bastoes from '../pages/Bastoes';

// ── Mocks ─────────────────────────────────────────────────────

const mockGet   = vi.fn();
const mockPatch = vi.fn();

vi.mock('../api', () => ({
  default: {
    get:   (...args) => mockGet(...args),
    patch: (...args) => mockPatch(...args),
  },
}));

function renderWith() {
  return render(
    <MemoryRouter>
      <Bastoes />
    </MemoryRouter>
  );
}

// Fixtures
const PENDENTE = {
  id: 'bast-1',
  hunter_nome: 'Patrick Hunter',
  farmer_nome: 'Aline Farmer',
  cnpj_contador: '11.111.111/0001-11',
  contabilidade: 'Contab Teste',
  cidade_uf: 'Sao Paulo/SP',
  data_parceria: '2026-05-01',
  leads_iniciais: 2,
  criado_em: '2026-05-21T10:00:00Z',
  status: 'PENDENTE',
  observacoes: null,
};

const APROVADO = {
  id: 'bast-2',
  hunter_nome: 'Marta Santos',
  farmer_nome: 'Joao Farmer',
  cnpj_contador: '22.222.222/0001-22',
  contabilidade: 'Contab Aprovada',
  cidade_uf: 'Guarulhos/SP',
  data_parceria: '2026-04-10',
  leads_iniciais: 3,
  criado_em: '2026-04-10T09:00:00Z',
  status: 'APROVADO',
  validado_por_nome: 'Tulio Horta',
  validado_em: '2026-04-12T14:00:00Z',
  observacoes: null,
};


describe('Bastoes — pagina de aprovacao', () => {
  beforeEach(() => {
    mockGet.mockReset();
    mockPatch.mockReset();
  });

  it('renderiza titulo e KPIs zerados quando lista vazia', async () => {
    mockGet.mockResolvedValue({ data: [] });
    renderWith();

    expect(await screen.findByRole('heading', { name: 'Bastões' })).toBeInTheDocument();
    expect(screen.getByText('Fila de aprovação de passagens Hunter → Farmer.')).toBeInTheDocument();

    // Estado vazio na aba Pendentes (default)
    expect(await screen.findByText('Nenhum bastão pendentes')).toBeInTheDocument();
  });

  it('busca o endpoint /todos', async () => {
    mockGet.mockResolvedValue({ data: [] });
    renderWith();

    await waitFor(() => {
      expect(mockGet).toHaveBeenCalledWith('/carteira/bastoes/todos');
    });
  });

  it('renderiza 1 bastao pendente com Hunter, Farmer, contador e botoes', async () => {
    mockGet.mockResolvedValue({ data: [PENDENTE] });
    renderWith();

    expect(await screen.findByText('Patrick Hunter')).toBeInTheDocument();
    expect(screen.getByText('Aline Farmer')).toBeInTheDocument();
    expect(screen.getByText('Contab Teste')).toBeInTheDocument();
    expect(screen.getByText('11.111.111/0001-11')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /Aprovar/i })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /^Rejeitar$/i })).toBeInTheDocument();
  });

  it('clica em Aprovar -> chama PATCH /aprovar', async () => {
    mockGet.mockResolvedValue({ data: [PENDENTE] });
    mockPatch.mockResolvedValue({ data: { ...PENDENTE, status: 'APROVADO' } });
    renderWith();

    const aprovarBtn = await screen.findByRole('button', { name: /Aprovar/i });
    fireEvent.click(aprovarBtn);

    await waitFor(() => {
      expect(mockPatch).toHaveBeenCalledWith('/carteira/bastoes/bast-1/aprovar');
    });
  });

  it('clica em Rejeitar -> abre modal com titulo Rejeitar bastao', async () => {
    mockGet.mockResolvedValue({ data: [PENDENTE] });
    renderWith();

    const rejeitarBtn = await screen.findByRole('button', { name: /^Rejeitar$/i });
    fireEvent.click(rejeitarBtn);

    expect(
      await screen.findByRole('heading', { name: 'Rejeitar bastão' })
    ).toBeInTheDocument();
    expect(
      screen.getByText(/Patrick Hunter.*Aline Farmer/)
    ).toBeInTheDocument();
  });

  it('modal de rejeicao valida motivo vazio', async () => {
    mockGet.mockResolvedValue({ data: [PENDENTE] });
    renderWith();

    fireEvent.click(await screen.findByRole('button', { name: /^Rejeitar$/i }));
    await screen.findByRole('heading', { name: 'Rejeitar bastão' });

    const btnConfirmar = screen.getByRole('button', { name: 'Rejeitar bastão' });
    fireEvent.click(btnConfirmar);

    expect(await screen.findByText(/Informe o motivo/)).toBeInTheDocument();
    expect(mockPatch).not.toHaveBeenCalled();
  });

  it('modal de rejeicao com motivo valido -> chama PATCH /rejeitar', async () => {
    mockGet.mockResolvedValue({ data: [PENDENTE] });
    mockPatch.mockResolvedValue({ data: { ...PENDENTE, status: 'REJEITADO' } });
    renderWith();

    fireEvent.click(await screen.findByRole('button', { name: /^Rejeitar$/i }));
    await screen.findByRole('heading', { name: 'Rejeitar bastão' });

    const textarea = screen.getByPlaceholderText(/Ex: Termo de parceria/);
    fireEvent.change(textarea, {
      target: { value: 'Termo nao assinado pelo socio.' },
    });

    fireEvent.click(screen.getByRole('button', { name: 'Rejeitar bastão' }));

    await waitFor(() => {
      expect(mockPatch).toHaveBeenCalledWith(
        '/carteira/bastoes/bast-1/rejeitar',
        { motivo: 'Termo nao assinado pelo socio.' }
      );
    });
  });

  it('aba Aprovados mostra os bastoes aprovados de verdade', async () => {
    mockGet.mockResolvedValue({ data: [PENDENTE, APROVADO] });
    renderWith();

    // Espera carregar — aba Pendentes (default) mostra o PENDENTE
    await screen.findByText('Patrick Hunter');

    // Clica na aba Aprovados
    fireEvent.click(screen.getByRole('button', { name: /Aprovados/i }));

    // Agora aparece o bastão APROVADO (Marta Santos) e quem aprovou
    expect(await screen.findByText('Marta Santos')).toBeInTheDocument();
    expect(screen.getByText('Contab Aprovada')).toBeInTheDocument();
    expect(screen.getByText('Tulio Horta')).toBeInTheDocument();
  });

  it('KPI de Aprovados reflete a contagem', async () => {
    mockGet.mockResolvedValue({ data: [PENDENTE, APROVADO] });
    renderWith();

    await screen.findByText('Patrick Hunter');

    // "Aprovados" aparece em 2 lugares: KpiCard (dentro de <p>) e aba (<span>).
    // Pegamos so o do KpiCard filtrando pela tag P.
    const labels = screen.getAllByText('Aprovados');
    const labelKpi = labels.find((el) => el.tagName === 'P');
    expect(labelKpi).toBeDefined();
    const kpiCard = labelKpi.closest('div').parentElement;
    expect(kpiCard).toHaveTextContent('1');
  });

  it('exibe erro de carregamento quando GET falha', async () => {
    mockGet.mockRejectedValue({
      response: { data: { detail: 'Erro X' } },
      message: 'Network Error',
    });
    renderWith();

    expect(await screen.findByText(/Erro X/)).toBeInTheDocument();
  });
});
