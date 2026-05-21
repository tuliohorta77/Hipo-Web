// web/src/tests/Bastoes.test.jsx
//
// Testes da página de aprovação de bastões.
// Cobre:
//   - render básico (titulo + estado vazio se fila vazia)
//   - render com 1 bastão pendente (mostra Hunter, Farmer, contador, botões)
//   - clica em Aprovar → chama PATCH /aprovar
//   - clica em Rejeitar → abre modal, valida motivo, confirma chama PATCH /rejeitar
//   - tab Aprovados/Rejeitados/Removidos → mostra aviso de "ver no Hunter"
//
// Notas:
//   - "Rejeitar bastão" aparece em 2 lugares no modal (titulo + botao).
//     Usamos getByRole pra distinguir: heading vs button.
//   - Usamos findBy* para esperas (mais robusto que await waitFor + getBy).
//
// Mock do api: vi.mock('../api', () => ({ default: { get, patch }, ... })).

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

// Fixture: 1 bastão pendente
const PENDENTE_BASE = {
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


describe('Bastoes — pagina de aprovacao', () => {
  beforeEach(() => {
    mockGet.mockReset();
    mockPatch.mockReset();
  });

  it('renderiza titulo e KPI de pendentes zerado quando lista vazia', async () => {
    mockGet.mockResolvedValue({ data: [] });
    renderWith();

    expect(await screen.findByRole('heading', { name: 'Bastões' })).toBeInTheDocument();
    expect(screen.getByText('Fila de aprovação de passagens Hunter → Farmer.')).toBeInTheDocument();

    // Estado vazio na aba Pendentes
    expect(await screen.findByText('Nenhum bastão pendente')).toBeInTheDocument();
  });

  it('renderiza 1 bastao pendente com Hunter, Farmer, contador e botoes', async () => {
    mockGet.mockResolvedValue({ data: [PENDENTE_BASE] });
    renderWith();

    expect(await screen.findByText('Patrick Hunter')).toBeInTheDocument();
    expect(screen.getByText('Aline Farmer')).toBeInTheDocument();
    expect(screen.getByText('Contab Teste')).toBeInTheDocument();
    expect(screen.getByText('11.111.111/0001-11')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /Aprovar/i })).toBeInTheDocument();
    // Só existe 1 botão "Rejeitar" antes de abrir o modal
    expect(screen.getByRole('button', { name: /^Rejeitar$/i })).toBeInTheDocument();
  });

  it('clica em Aprovar -> chama PATCH /aprovar', async () => {
    mockGet.mockResolvedValue({ data: [PENDENTE_BASE] });
    mockPatch.mockResolvedValue({ data: { ...PENDENTE_BASE, status: 'APROVADO' } });
    renderWith();

    const aprovarBtn = await screen.findByRole('button', { name: /Aprovar/i });
    fireEvent.click(aprovarBtn);

    await waitFor(() => {
      expect(mockPatch).toHaveBeenCalledWith('/carteira/bastoes/bast-1/aprovar');
    });
  });

  it('clica em Rejeitar -> abre modal com titulo Rejeitar bastao', async () => {
    mockGet.mockResolvedValue({ data: [PENDENTE_BASE] });
    renderWith();

    const rejeitarBtn = await screen.findByRole('button', { name: /^Rejeitar$/i });
    fireEvent.click(rejeitarBtn);

    // Titulo do modal (h2) — distingue do botão que tem o mesmo texto
    expect(
      await screen.findByRole('heading', { name: 'Rejeitar bastão' })
    ).toBeInTheDocument();

    // Subtitulo do modal mostra hunter -> farmer (pode haver caracteres no meio,
    // como o ID/contabilidade entre parenteses)
    expect(
      screen.getByText(/Patrick Hunter.*Aline Farmer/)
    ).toBeInTheDocument();
  });

  it('modal de rejeicao valida motivo vazio', async () => {
    mockGet.mockResolvedValue({ data: [PENDENTE_BASE] });
    renderWith();

    fireEvent.click(await screen.findByRole('button', { name: /^Rejeitar$/i }));

    // Espera modal abrir (h2)
    await screen.findByRole('heading', { name: 'Rejeitar bastão' });

    // Clica no BOTAO "Rejeitar bastão" do modal sem preencher motivo
    const btnConfirmar = screen.getByRole('button', { name: 'Rejeitar bastão' });
    fireEvent.click(btnConfirmar);

    // Aparece erro de validação
    expect(await screen.findByText(/Informe o motivo/)).toBeInTheDocument();
    // E patch NAO foi chamado
    expect(mockPatch).not.toHaveBeenCalled();
  });

  it('modal de rejeicao com motivo valido -> chama PATCH /rejeitar', async () => {
    mockGet.mockResolvedValue({ data: [PENDENTE_BASE] });
    mockPatch.mockResolvedValue({ data: { ...PENDENTE_BASE, status: 'REJEITADO' } });
    renderWith();

    fireEvent.click(await screen.findByRole('button', { name: /^Rejeitar$/i }));

    await screen.findByRole('heading', { name: 'Rejeitar bastão' });

    const textarea = screen.getByPlaceholderText(/Ex: Termo de parceria/);
    fireEvent.change(textarea, {
      target: { value: 'Termo nao assinado pelo socio.' },
    });

    // Clica no BOTAO do modal (não no título)
    fireEvent.click(screen.getByRole('button', { name: 'Rejeitar bastão' }));

    await waitFor(() => {
      expect(mockPatch).toHaveBeenCalledWith(
        '/carteira/bastoes/bast-1/rejeitar',
        { motivo: 'Termo nao assinado pelo socio.' }
      );
    });
  });

  it('aba Aprovados mostra aviso de scope futuro', async () => {
    mockGet.mockResolvedValue({ data: [] });
    renderWith();

    await screen.findByRole('heading', { name: 'Bastões' });

    fireEvent.click(screen.getByRole('button', { name: /Aprovados/i }));

    expect(
      await screen.findByText(/disponível no drilldown do Hunter/)
    ).toBeInTheDocument();
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
