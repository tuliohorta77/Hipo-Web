// web/src/tests/AulaUC.test.jsx
//
// A aula. O que estes testes seguram:
//   1. o player sai de (provedor, ref) pela tabela fechada
//   2. a trava do "Concluí": botão desabilitado com quanto falta; ao zerar,
//      habilita; o 409 do servidor aparece com o texto dele
//   3. concluir troca a tela para "Aula concluída"
//   4. modo leitura não oferece Concluí
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, fireEvent, cleanup, waitFor } from '@testing-library/react';
import { MemoryRouter, Route, Routes } from 'react-router-dom';

const mockGet = vi.fn();
const mockPost = vi.fn();
vi.mock('../api', () => ({
  default: { get: (...a) => mockGet(...a), post: (...a) => mockPost(...a) },
  getUser: () => null,
}));

import Aula from '../pages/uc/Aula';

function aula(extra = {}) {
  return {
    id: 'a1', trilha_id: 't1', trilha_titulo: 'Normas Regulamentadoras', pilar: 'tecnica',
    pilar_rotulo: 'Técnica', ordem: 1, titulo: 'NR-01: a base', resumo: 'Resumo da aula',
    conteudo_md: '## Por que começar\n\nTexto.', video_provedor: 'youtube', video_ref: 'dQw4w9WgXcQ',
    video_url: 'https://www.youtube.com/watch?v=dQw4w9WgXcQ', duracao_min: 12, versao: 1,
    status: 'publicada',
    materiais: [{ id: 'm1', nome_original: 'NR-01.pdf', tipo_mime: 'application/pdf', bytes: 398620, eh_imagem: false, criado_em: '2026-10-01T10:00:00Z' }],
    anterior: null, proxima: { id: 'a2', titulo: 'GRO e PGR' },
    aberta_em: '2026-10-01T10:00:00Z', concluida_em: null, concluiu_versao_anterior: false,
    segundos_para_liberar: 0, modo_leitura: false,
    ...extra,
  };
}

function renderizar(caminho = '/uc/aulas/a1') {
  return render(
    <MemoryRouter initialEntries={[caminho]}>
      <Routes>
        <Route path="/uc/aulas/:aulaId" element={<Aula />} />
        <Route path="/uc/trilhas/:id" element={<p>tela da trilha</p>} />
      </Routes>
    </MemoryRouter>,
  );
}

// Erro como o axios entrega: um Error com `response` pendurado.
function erroHttp(status, detail) {
  return Object.assign(new Error(`HTTP ${status}`), { response: { status, data: { detail } } });
}

beforeEach(() => { mockGet.mockReset(); mockPost.mockReset(); });
afterEach(cleanup);

describe('Aula da UC', () => {
  it('player do YouTube pela tabela fechada, texto e material', async () => {
    mockGet.mockResolvedValue({ data: aula() });
    renderizar();
    const player = await screen.findByTitle('Vídeo: NR-01: a base');
    expect(player.getAttribute('src')).toBe('https://www.youtube-nocookie.com/embed/dQw4w9WgXcQ?rel=0');
    expect(screen.getByRole('heading', { name: 'Por que começar' })).toBeInTheDocument();
    expect(screen.getByText('NR-01.pdf')).toBeInTheDocument();
    expect(screen.getByText('389 KB')).toBeInTheDocument();
  });

  it('sem vídeo, sem player', async () => {
    mockGet.mockResolvedValue({ data: aula({ video_provedor: null, video_ref: null, video_url: null }) });
    renderizar();
    await screen.findByText('Resumo da aula');
    expect(screen.queryByTitle(/Vídeo:/)).not.toBeInTheDocument();
  });

  it('trava: botão desabilitado dizendo quanto falta, e libera ao zerar', async () => {
    mockGet.mockResolvedValue({ data: aula({ segundos_para_liberar: 2 }) });
    renderizar();
    const botao = await screen.findByRole('button', { name: /Concluí/ });
    expect(botao).toBeDisabled();
    expect(screen.getByText('2 s')).toBeInTheDocument();
    // Relógio de verdade: são 2 s, e o fake timer brigaria com o findBy.
    await waitFor(
      () => expect(screen.getByRole('button', { name: /Concluí/ })).not.toBeDisabled(),
      { timeout: 4000 },
    );
  });

  it('concluir troca a tela para concluída', async () => {
    mockGet.mockResolvedValue({ data: aula() });
    mockPost.mockResolvedValue({ data: aula({ concluida_em: '2026-10-01T10:10:00Z' }) });
    renderizar();
    fireEvent.click(await screen.findByRole('button', { name: /Concluí/ }));
    expect(await screen.findByText('Aula concluída.')).toBeInTheDocument();
    expect(mockPost).toHaveBeenCalledWith('/uc/aulas/a1/concluir');
    expect(screen.queryByRole('button', { name: /Concluí/ })).not.toBeInTheDocument();
  });

  it('o 409 do servidor aparece com o texto dele', async () => {
    mockGet.mockResolvedValue({ data: aula() });
    mockPost.mockRejectedValue(erroHttp(409, 'Ainda não dá para concluir: faltam 3 min.'));
    renderizar();
    fireEvent.click(await screen.findByRole('button', { name: /Concluí/ }));
    expect(await screen.findByText('Ainda não dá para concluir: faltam 3 min.')).toBeInTheDocument();
  });

  it('aula atualizada avisa que precisa refazer', async () => {
    mockGet.mockResolvedValue({ data: aula({ concluiu_versao_anterior: true }) });
    renderizar();
    expect(await screen.findByText(/Atualizada desde que você concluiu/)).toBeInTheDocument();
  });

  it('modo leitura não oferece Concluí e mantém o usuario_id na navegação', async () => {
    mockGet.mockResolvedValue({ data: aula({ modo_leitura: true }) });
    renderizar('/uc/aulas/a1?usuario_id=u9');
    expect(await screen.findByText('Modo leitura')).toBeInTheDocument();
    expect(mockGet).toHaveBeenCalledWith('/uc/aulas/a1', { params: { usuario_id: 'u9' } });
    expect(screen.queryByRole('button', { name: /Concluí/ })).not.toBeInTheDocument();
  });
});
