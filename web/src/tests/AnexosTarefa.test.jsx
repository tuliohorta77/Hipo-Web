// web/src/tests/AnexosTarefa.test.jsx
//
// Anexo de arquivo na tarefa. O caso de uso é o print do WhatsApp, e as
// promessas que estes testes seguram são quatro:
//
//   1. colar (Ctrl+V) anexa — é o gesto principal, não o alternativo
//   2. imagem vira miniatura; PDF vira ícone
//   3. tarefa fechada mostra o anexo mas não deixa mexer
//   4. o erro do backend aparece na tela, com o texto do backend
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, fireEvent, cleanup, waitFor } from '@testing-library/react';

const mockGet = vi.fn();
const mockPost = vi.fn();
const mockDelete = vi.fn();

vi.mock('../api', () => ({
  default: {
    get: (...a) => mockGet(...a),
    post: (...a) => mockPost(...a),
    delete: (...a) => mockDelete(...a),
  },
  getUser: () => null,
}));

import AnexosTarefa from '../components/crm/AnexosTarefa';

const TAREFA_ABERTA = {
  id: 't1',
  titulo: 'Cobrar proposta',
  concluida_em: null,
  cancelada_em: null,
};

const TAREFA_FECHADA = {
  ...TAREFA_ABERTA,
  concluida_em: '2026-09-09T12:00:00Z',
};

function anexo(id, extra = {}) {
  return {
    id,
    tarefa_id: 't1',
    nome_original: `print-${id}.png`,
    tipo_mime: 'image/png',
    bytes: 204800,
    eh_imagem: true,
    enviado_por: 'u1',
    enviado_por_nome: 'Bruno Gonçalo',
    criado_em: '2026-09-09T12:00:00Z',
    ...extra,
  };
}

function respostas(lista = []) {
  return (url) => {
    if (url === '/crm/tarefas/t1/anexos') return Promise.resolve({ data: lista });
    if (url.startsWith('/crm/anexos/')) {
      const id = url.split('/')[3];
      return Promise.resolve({
        data: { url: `https://s3.exemplo/${id}?assinado`, expira_em_segundos: 300 },
      });
    }
    return Promise.resolve({ data: [] });
  };
}

function arquivoPng(nome = 'print.png') {
  return new File(['conteudo-falso'], nome, { type: 'image/png' });
}

beforeEach(() => {
  mockGet.mockReset();
  mockPost.mockReset();
  mockDelete.mockReset();
  mockGet.mockImplementation(respostas());
  mockPost.mockResolvedValue({ data: anexo('a1') });
  mockDelete.mockResolvedValue({ data: null });
});

afterEach(cleanup);

const bloco = () => screen.getByLabelText('Anexos da tarefa');

describe('AnexosTarefa — vazio', () => {
  it('convida a colar, e diz o limite', async () => {
    render(<AnexosTarefa tarefa={TAREFA_ABERTA} />);
    expect(await screen.findByText(/Cole o print aqui/)).toBeInTheDocument();
    expect(screen.getByText(/10 MB/)).toBeInTheDocument();
  });

  it('busca os anexos da tarefa certa', async () => {
    render(<AnexosTarefa tarefa={TAREFA_ABERTA} />);
    await waitFor(() =>
      expect(mockGet).toHaveBeenCalledWith('/crm/tarefas/t1/anexos')
    );
  });

  it('tarefa fechada e sem anexo não ocupa espaço na tela', async () => {
    /*
      Um bloco dizendo "sem anexos" numa tarefa que nem pode receber
      anexo é ruído puro — e a linha do tempo já é densa.
    */
    const { container } = render(<AnexosTarefa tarefa={TAREFA_FECHADA} />);
    await waitFor(() => expect(mockGet).toHaveBeenCalled());
    await waitFor(() => expect(container).toBeEmptyDOMElement());
  });
});

describe('AnexosTarefa — colar', () => {
  it('Ctrl+V com imagem no clipboard anexa', async () => {
    /*
      O gesto principal. Print nasce no Ctrl+C: obrigar a salvar em disco
      antes é atrito em cima de um gesto que já estava pronto.
    */
    render(<AnexosTarefa tarefa={TAREFA_ABERTA} />);
    await screen.findByText(/Cole o print aqui/);

    fireEvent.paste(bloco(), { clipboardData: { files: [arquivoPng()] } });

    await waitFor(() => expect(mockPost).toHaveBeenCalled());
    const [url, corpo] = mockPost.mock.calls[0];
    expect(url).toBe('/crm/tarefas/t1/anexos');
    expect(corpo).toBeInstanceOf(FormData);
    expect(corpo.get('arquivo')).toBeInstanceOf(File);
  });

  it('colar TEXTO não anexa nada', async () => {
    /*
      O bloco fica na mesma tela do campo "O que aconteceu". Colar texto
      por perto não pode virar upload de nada.
    */
    render(<AnexosTarefa tarefa={TAREFA_ABERTA} />);
    await screen.findByText(/Cole o print aqui/);

    fireEvent.paste(bloco(), { clipboardData: { files: [] } });

    await new Promise((r) => setTimeout(r, 50));
    expect(mockPost).not.toHaveBeenCalled();
  });

  it('tarefa fechada ignora o colar', async () => {
    mockGet.mockImplementation(respostas([anexo('a1')]));
    render(<AnexosTarefa tarefa={TAREFA_FECHADA} />);
    await screen.findByLabelText('Abrir print-a1.png');

    fireEvent.paste(bloco(), { clipboardData: { files: [arquivoPng()] } });

    await new Promise((r) => setTimeout(r, 50));
    expect(mockPost).not.toHaveBeenCalled();
  });

  it('arrastar e soltar também anexa', async () => {
    render(<AnexosTarefa tarefa={TAREFA_ABERTA} />);
    await screen.findByText(/Cole o print aqui/);

    fireEvent.drop(bloco(), { dataTransfer: { files: [arquivoPng()] } });

    await waitFor(() => expect(mockPost).toHaveBeenCalled());
  });

  it('vários arquivos vão em série, não em paralelo', async () => {
    /*
      O limite de 10 por tarefa é contado no servidor a cada POST. Dez
      uploads simultâneos leriam a mesma contagem antes de qualquer um
      gravar — e passariam todos.
    */
    const ordem = [];
    mockPost.mockImplementation(() => {
      ordem.push('inicio');
      return new Promise((r) => setTimeout(() => { ordem.push('fim'); r({ data: {} }); }, 10));
    });

    render(<AnexosTarefa tarefa={TAREFA_ABERTA} />);
    await screen.findByText(/Cole o print aqui/);

    fireEvent.paste(bloco(), {
      clipboardData: { files: [arquivoPng('a.png'), arquivoPng('b.png')] },
    });

    await waitFor(() => expect(mockPost).toHaveBeenCalledTimes(2));
    expect(ordem).toEqual(['inicio', 'fim', 'inicio', 'fim']);
  });
});

describe('AnexosTarefa — galeria', () => {
  it('imagem vira miniatura com a URL assinada', async () => {
    mockGet.mockImplementation(respostas([anexo('a1')]));
    render(<AnexosTarefa tarefa={TAREFA_ABERTA} />);

    const img = await screen.findByAltText('print-a1.png');
    expect(img.getAttribute('src')).toContain('assinado');
  });

  it('PDF não gasta uma assinatura à toa', async () => {
    /*
      PDF mostra ícone, não conteúdo. Assinar a URL de quem não vai ser
      exibido é trabalho jogado fora — e cada assinatura tem validade
      curta correndo desde a emissão.
    */
    mockGet.mockImplementation(respostas([
      anexo('p1', { eh_imagem: false, tipo_mime: 'application/pdf', nome_original: 'contrato.pdf' }),
    ]));
    render(<AnexosTarefa tarefa={TAREFA_ABERTA} />);

    await screen.findByLabelText('Abrir contrato.pdf');
    expect(mockGet.mock.calls.some(([u]) => u.startsWith('/crm/anexos/'))).toBe(false);
  });

  it('mostra a contagem', async () => {
    mockGet.mockImplementation(respostas([anexo('a1'), anexo('a2')]));
    render(<AnexosTarefa tarefa={TAREFA_ABERTA} />);
    expect(await screen.findByText('Anexos (2)')).toBeInTheDocument();
  });

  it('uma URL que falha não derruba a galeria', async () => {
    /*
      Miniatura quebrada é ruim; a lista inteira sumir é pior.
    */
    mockGet.mockImplementation((url) => {
      if (url === '/crm/tarefas/t1/anexos') return Promise.resolve({ data: [anexo('a1')] });
      if (url.startsWith('/crm/anexos/')) return Promise.reject(new Error('500'));
      return Promise.resolve({ data: [] });
    });
    render(<AnexosTarefa tarefa={TAREFA_ABERTA} />);

    expect(await screen.findByLabelText('Abrir print-a1.png')).toBeInTheDocument();
  });
});

describe('AnexosTarefa — remover', () => {
  it('tarefa aberta oferece remover', async () => {
    mockGet.mockImplementation(respostas([anexo('a1')]));
    render(<AnexosTarefa tarefa={TAREFA_ABERTA} />);

    fireEvent.click(await screen.findByLabelText('Remover print-a1.png'));
    await waitFor(() => expect(mockDelete).toHaveBeenCalledWith('/crm/anexos/a1'));
  });

  it('tarefa fechada NÃO oferece remover', async () => {
    /*
      Anexo é prova do que aconteceu, e prova que pode ser trocada depois
      do fato não é prova. Mesma imutabilidade do resultado. O backend
      recusa com 422 de qualquer jeito — esconder o botão é honestidade.
    */
    mockGet.mockImplementation(respostas([anexo('a1')]));
    render(<AnexosTarefa tarefa={TAREFA_FECHADA} />);

    await screen.findByLabelText('Abrir print-a1.png');
    expect(screen.queryByLabelText('Remover print-a1.png')).not.toBeInTheDocument();
    expect(screen.queryByText('Anexar')).not.toBeInTheDocument();
  });

  it('avisa o pai quando a lista muda', async () => {
    const onMudou = vi.fn();
    mockGet.mockImplementation(respostas([anexo('a1')]));
    render(<AnexosTarefa tarefa={TAREFA_ABERTA} onMudou={onMudou} />);

    fireEvent.click(await screen.findByLabelText('Remover print-a1.png'));
    await waitFor(() => expect(onMudou).toHaveBeenCalled());
  });
});

describe('AnexosTarefa — erro', () => {
  it('o texto do backend aparece na tela', async () => {
    /*
      A recusa de HEIC explica o que fazer no iPhone. Trocar isso por
      "erro ao enviar" jogaria fora a única parte útil da resposta.
    */
    mockPost.mockRejectedValue({
      response: {
        data: {
          detail: 'Formato HEIC (foto de iPhone) não é exibível no navegador.',
        },
      },
    });
    render(<AnexosTarefa tarefa={TAREFA_ABERTA} />);
    await screen.findByText(/Cole o print aqui/);

    fireEvent.paste(bloco(), { clipboardData: { files: [arquivoPng()] } });

    expect(await screen.findByText(/HEIC/)).toBeInTheDocument();
  });

  it('falha ao listar não deixa a tela muda', async () => {
    mockGet.mockImplementation((url) => {
      if (url === '/crm/tarefas/t1/anexos') {
        return Promise.reject({ response: { data: { detail: 'Anexos indisponíveis' } } });
      }
      return Promise.resolve({ data: [] });
    });
    render(<AnexosTarefa tarefa={TAREFA_ABERTA} />);
    expect(await screen.findByText('Anexos indisponíveis')).toBeInTheDocument();
  });
});
