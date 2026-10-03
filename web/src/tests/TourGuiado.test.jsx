// web/src/tests/TourGuiado.test.jsx
//
// O tour por cima de telas falsas. O que estes testes seguram:
//   1. leva para a tela do passo e ilumina o alvo
//   2. clica no que o passo pede abrir; voltar remonta a tela (fecha o que
//      ficou aberto)
//   3. alvo que não aparece não trava: o balão explica e segue
//   4. Esc encerra, e a tecla não chega na tela
//   5. o mouse não atravessa a camada do tour
//   6. o último passo volta para a aula com ?tour=fim
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, fireEvent, cleanup, act, waitFor } from '@testing-library/react';
import { useState } from 'react';
import { MemoryRouter, Outlet, Route, Routes, useLocation } from 'react-router-dom';
import TourGuiado from '../components/uc/TourGuiado';
import { iniciarTour, lerTour } from '../components/uc/tour';

function Onde() {
  const l = useLocation();
  return <p data-testid="onde">{l.pathname}{l.search}</p>;
}

function Casca() {
  const [chave, setChave] = useState(0);
  return (
    <>
      <Onde />
      <Outlet key={chave} />
      <TourGuiado chaveTela={chave} onRemontar={() => setChave((k) => k + 1)} esperaMs={400} />
    </>
  );
}

function TelaTarefas() {
  const [aberta, setAberta] = useState(false);
  return (
    <div>
      <div data-tour="tar-area">colunas</div>
      <button type="button" data-tour="tar-cartao" onClick={() => setAberta(true)}>cartão</button>
      {aberta && <div data-tour="tar-modal-dados">janela da tarefa</div>}
    </div>
  );
}

function renderizar() {
  return render(
    <MemoryRouter initialEntries={['/uc/aulas/a1']}>
      <Routes>
        <Route element={<Casca />}>
          <Route path="/uc/aulas/:id" element={<p>tela da aula</p>} />
          <Route path="/crm/tarefas" element={<TelaTarefas />} />
          <Route path="/crm/agenda" element={<p>tela da agenda</p>} />
        </Route>
      </Routes>
    </MemoryRouter>,
  );
}

const PASSOS = [
  { rota: '/crm/tarefas', alvo: 'tar-area', titulo: 'As colunas', texto: 'Comece pela **esquerda**.' },
  { rota: '/crm/tarefas', alvo: 'tar-modal-dados', titulo: 'Dentro da tarefa', texto: 'Tipo e prazo.', clicar: ['tar-cartao'] },
  { rota: '/crm/agenda', alvo: 'nao-existe', titulo: 'A agenda', texto: 'Horário livre.' },
];

function comecar(passos = PASSOS) {
  act(() => iniciarTour({ aulaId: 'a1', aulaTitulo: 'Tarefas', passos }));
}

beforeEach(() => {
  sessionStorage.clear();
  vi.spyOn(Element.prototype, 'getBoundingClientRect').mockImplementation(function medir() {
    const visivel = this.hasAttribute?.('data-tour');
    return visivel
      ? { top: 100, left: 100, width: 200, height: 40, bottom: 140, right: 300, x: 100, y: 100 }
      : { top: 0, left: 0, width: 0, height: 0, bottom: 0, right: 0, x: 0, y: 0 };
  });
  Element.prototype.scrollIntoView = vi.fn();
});
afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
});

describe('Tour guiado', () => {
  it('sem tour não desenha nada', () => {
    renderizar();
    expect(screen.queryByTestId('tour-guiado')).toBeNull();
  });

  it('leva para a tela e ilumina o alvo', async () => {
    renderizar();
    comecar();
    await waitFor(() => expect(screen.getByTestId('onde').textContent).toBe('/crm/tarefas'));
    expect(await screen.findByTestId('tour-recorte')).toBeTruthy();
    expect(screen.getByText('Passo 1 de 3 · Tarefas')).toBeTruthy();
    expect(screen.getByText('As colunas')).toBeTruthy();
    expect(screen.getByText('esquerda').tagName).toBe('STRONG');
  });

  it('abre o cartão no passo que pede, e voltar fecha', async () => {
    renderizar();
    comecar();
    await screen.findByTestId('tour-recorte');
    fireEvent.click(screen.getByRole('button', { name: /Próximo/ }));
    expect(await screen.findByText('janela da tarefa', {}, { timeout: 2000 })).toBeTruthy();
    await waitFor(() => expect(screen.getByText('Passo 2 de 3 · Tarefas')).toBeTruthy());
    fireEvent.click(screen.getByRole('button', { name: /Voltar/ }));
    await waitFor(() => expect(screen.queryByText('janela da tarefa')).toBeNull());
    expect(screen.getByText('Passo 1 de 3 · Tarefas')).toBeTruthy();
  });

  it('alvo que não aparece não trava o tour', async () => {
    renderizar();
    act(() => iniciarTour({ aulaId: 'a1', passos: [PASSOS[2], PASSOS[0]] }));
    expect(await screen.findByText(/Isto não está aparecendo agora/, {}, { timeout: 2000 })).toBeTruthy();
    expect(screen.queryByTestId('tour-recorte')).toBeNull();
    fireEvent.click(screen.getByRole('button', { name: /Próximo/ }));
    await waitFor(() => expect(screen.getByTestId('onde').textContent).toBe('/crm/tarefas'));
  });

  it('Esc encerra e não chega na tela', async () => {
    const daTela = vi.fn();
    window.addEventListener('keydown', daTela);
    renderizar();
    comecar();
    await screen.findByTestId('tour-recorte');
    fireEvent.keyDown(document.body, { key: 'Escape' });
    window.removeEventListener('keydown', daTela);
    await waitFor(() => expect(screen.queryByTestId('tour-guiado')).toBeNull());
    expect(daTela).not.toHaveBeenCalled();
    expect(lerTour()).toBeNull();
    expect(screen.getByTestId('onde').textContent).toBe('/crm/tarefas');
  });

  it('o mouse não atravessa a camada', async () => {
    const foraDaTela = vi.fn();
    document.addEventListener('mousedown', foraDaTela);
    renderizar();
    comecar();
    await screen.findByTestId('tour-recorte');
    fireEvent.mouseDown(screen.getByTestId('tour-guiado'));
    document.removeEventListener('mousedown', foraDaTela);
    expect(foraDaTela).not.toHaveBeenCalled();
  });

  it('o último passo volta para a aula', async () => {
    renderizar();
    act(() => iniciarTour({ aulaId: 'a1', passos: [PASSOS[0]] }));
    await screen.findByTestId('tour-recorte');
    fireEvent.click(screen.getByRole('button', { name: 'Voltar para a aula' }));
    await waitFor(() => expect(screen.getByTestId('onde').textContent).toBe('/uc/aulas/a1?tour=fim'));
    expect(screen.queryByTestId('tour-guiado')).toBeNull();
  });

  it('setas andam pelos passos', async () => {
    renderizar();
    comecar();
    await screen.findByTestId('tour-recorte');
    fireEvent.keyDown(document.body, { key: 'ArrowRight' });
    await waitFor(() => expect(lerTour().indice).toBe(1));
    fireEvent.keyDown(document.body, { key: 'ArrowLeft' });
    await waitFor(() => expect(lerTour().indice).toBe(0));
  });
});
