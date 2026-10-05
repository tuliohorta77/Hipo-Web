// web/src/tests/MinhaUC.test.jsx
//
// A tela de quem aprende. O que estes testes seguram:
//   1. abre no cartão "Sua próxima aula", com o motivo, e Começar leva à aula
//   2. os três pilares no topo; clicar abre o painel com as trilhas do pilar
//   3. o manual da função mostra situação e prazo; atrasada em vermelho
//   4. modo leitura (gestão vendo alguém): sem botão de agir
//   5. sem trilha nenhuma, a tela diz isso em vez de mostrar zeros
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, fireEvent, cleanup, within } from '@testing-library/react';
import { MemoryRouter, Route, Routes } from 'react-router-dom';

const mockGet = vi.fn();
vi.mock('../api', () => ({
  default: { get: (...a) => mockGet(...a) },
  getUser: () => ({ id: 'u1', nome: 'Jakeline', cargo: 'EV' }),
  getModulos: () => ['perfil', 'crm'],
}));

import MinhaUC from '../pages/uc/MinhaUC';

function trilha(extra = {}) {
  return {
    id: 't1', titulo: 'Normas Regulamentadoras', descricao: null, pilar: 'tecnica',
    pilar_rotulo: 'Técnica', obrigatoria: true, prazo: '2026-10-31',
    situacao: { codigo: 'em_dia', rotulo: 'Em dia', dias_restantes: 30 },
    aulas_total: 6, aulas_concluidas: 2, percentual: 33, proxima_aula_id: 'a3',
    ...extra,
  };
}

function painel(extra = {}) {
  return {
    usuario: { id: 'u1', nome: 'Jakeline', cargo: 'EV' },
    modo_leitura: false,
    pode_editar_conteudo: false,
    hoje: '2026-10-01',
    proxima: {
      aula_id: 'a3', aula_titulo: 'Riscos psicossociais', trilha_id: 't1',
      trilha_titulo: 'Normas Regulamentadoras', pilar: 'tecnica', pilar_rotulo: 'Técnica',
      motivo: 'em_andamento', motivo_texto: 'Continue de onde parou', prazo: '2026-10-31', duracao_min: 8,
    },
    pilares: [
      { pilar: 'tecnica', rotulo: 'Técnica', trilhas: 1, aulas_total: 6, aulas_concluidas: 2, percentual: 33 },
      { pilar: 'metodo', rotulo: 'Método', trilhas: 0, aulas_total: 0, aulas_concluidas: 0, percentual: null },
      { pilar: 'energia', rotulo: 'Energia', trilhas: 0, aulas_total: 0, aulas_concluidas: 0, percentual: null },
    ],
    manual: { trilhas_total: 1, trilhas_concluidas: 0, atrasadas: 0, trilhas: [trilha()] },
    outras: [],
    ...extra,
  };
}

function renderizar(caminho = '/uc') {
  return render(
    <MemoryRouter initialEntries={[caminho]}>
      <Routes>
        <Route path="/uc" element={<MinhaUC />} />
        <Route path="/uc/aulas/:id" element={<p>tela da aula</p>} />
        <Route path="/uc/trilhas/:id" element={<p>tela da trilha</p>} />
        <Route path="/uc/estudio" element={<p>tela do estúdio</p>} />
      </Routes>
    </MemoryRouter>,
  );
}

// Erro como o axios entrega: um Error com `response` pendurado.
function erroHttp(status, detail) {
  return Object.assign(new Error(`HTTP ${status}`), { response: { status, data: { detail } } });
}

// Chaves de propósito: hook do vitest que DEVOLVE função a trata como
// teardown, e mockReset() devolve o próprio mock — ele seria chamado depois
// do teste, com a implementação daquele teste.
beforeEach(() => { mockGet.mockReset(); });
afterEach(cleanup);

describe('MinhaUC', () => {
  it('abre no cartão da próxima aula, e Começar leva até ela', async () => {
    mockGet.mockResolvedValue({ data: painel() });
    renderizar();
    const cartao = await screen.findByTestId('proxima-aula');
    expect(within(cartao).getByText('Riscos psicossociais')).toBeInTheDocument();
    expect(within(cartao).getByText('Continue de onde parou')).toBeInTheDocument();
    fireEvent.click(within(cartao).getByRole('button', { name: /Começar/ }));
    expect(await screen.findByText('tela da aula')).toBeInTheDocument();
  });

  it('os três pilares; pilar sem trilha mostra traço, não zero', async () => {
    mockGet.mockResolvedValue({ data: painel() });
    renderizar();
    const tecnica = await screen.findByRole('button', { name: 'Pilar Técnica' });
    expect(within(tecnica).getByText('33%')).toBeInTheDocument();
    const metodo = screen.getByRole('button', { name: 'Pilar Método' });
    expect(within(metodo).getByText('—')).toBeInTheDocument();
    expect(within(metodo).getByText('Nenhuma trilha publicada ainda')).toBeInTheDocument();
  });

  it('clicar no pilar abre as trilhas dele', async () => {
    mockGet.mockResolvedValue({ data: painel() });
    renderizar();
    fireEvent.click(await screen.findByRole('button', { name: 'Pilar Técnica' }));
    const dialogo = await screen.findByRole('dialog');
    expect(within(dialogo).getByText('Normas Regulamentadoras')).toBeInTheDocument();
    fireEvent.click(within(dialogo).getByRole('button', { name: 'Continuar' }));
    expect(await screen.findByText('tela da aula')).toBeInTheDocument();
  });

  it('manual da função: atrasada aparece com o prazo vencido', async () => {
    mockGet.mockResolvedValue({
      data: painel({
        manual: {
          trilhas_total: 1, trilhas_concluidas: 0, atrasadas: 1,
          trilhas: [trilha({ situacao: { codigo: 'atrasada', rotulo: 'Atrasada', dias_restantes: -2 }, prazo: '2026-09-29' })],
        },
      }),
    });
    renderizar();
    expect(await screen.findByText('Atrasada')).toBeInTheDocument();
    expect(screen.getByText(/1 atrasada/)).toBeInTheDocument();
    expect(screen.getByText('venceu há 2 dias (29/09/2026)')).toBeInTheDocument();
  });

  it('modo leitura: mesma tela, sem botão de agir, com volta ao time', async () => {
    mockGet.mockResolvedValue({
      data: painel({ modo_leitura: true, pode_editar_conteudo: true }),
    });
    renderizar('/uc?usuario_id=u9');
    expect(await screen.findByText('Carreira · Jakeline')).toBeInTheDocument();
    expect(mockGet).toHaveBeenCalledWith('/uc/painel', { params: { usuario_id: 'u9' } });
    expect(screen.queryByRole('button', { name: /Começar/ })).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Continuar' })).not.toBeInTheDocument();
    expect(screen.getByRole('button', { name: /Voltar ao time/ })).toBeInTheDocument();
    // As abas da Carreira levam o modo leitura junto.
    const abas = screen.getByRole('navigation', { name: 'Carreira' });
    expect(within(abas).getByText('Desempenho').closest('a').getAttribute('href'))
      .toBe('/carreira/desempenho?usuario_id=u9');
  });

  it('gestão vê o botão do estúdio; operacional não', async () => {
    mockGet.mockResolvedValue({ data: painel({ pode_editar_conteudo: true }) });
    renderizar();
    fireEvent.click(await screen.findByRole('button', { name: /Estúdio/ }));
    expect(await screen.findByText('tela do estúdio')).toBeInTheDocument();
    cleanup();
    mockGet.mockResolvedValue({ data: painel() });
    renderizar();
    await screen.findByTestId('proxima-aula');
    expect(screen.queryByRole('button', { name: /Estúdio/ })).not.toBeInTheDocument();
  });

  it('sem trilha nenhuma, diz isso', async () => {
    mockGet.mockResolvedValue({
      data: painel({ proxima: null, manual: { trilhas_total: 0, trilhas_concluidas: 0, atrasadas: 0, trilhas: [] } }),
    });
    renderizar();
    expect(await screen.findByText('Nenhuma trilha para o seu cargo ainda')).toBeInTheDocument();
  });

  it('aulas feitas: a próxima é o quiz final da trilha', async () => {
    mockGet.mockResolvedValue({
      data: painel({
        proxima: {
          tipo: 'quiz', aula_id: null, aula_titulo: 'Quiz final da trilha', trilha_id: 't1',
          trilha_titulo: 'Normas Regulamentadoras', pilar: 'tecnica', pilar_rotulo: 'Técnica',
          motivo: 'quiz_final', motivo_texto: 'Falta o quiz final da trilha', prazo: null, duracao_min: null,
        },
      }),
    });
    render(
      <MemoryRouter initialEntries={['/uc']}>
        <Routes>
          <Route path="/uc" element={<MinhaUC />} />
          <Route path="/uc/trilhas/:id/quiz" element={<p>tela do quiz</p>} />
        </Routes>
      </MemoryRouter>,
    );
    fireEvent.click(await screen.findByRole('button', { name: /Fazer o quiz/ }));
    expect(await screen.findByText('tela do quiz')).toBeInTheDocument();
  });

  it('erro da API aparece com o texto do servidor', async () => {
    mockGet.mockRejectedValue(erroHttp(403, 'Só a gestão abre a UC de outra pessoa.'));
    renderizar('/uc?usuario_id=u9');
    expect(await screen.findByText('Só a gestão abre a UC de outra pessoa.')).toBeInTheDocument();
  });
});
