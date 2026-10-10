// web/src/tests/Ligacoes.test.jsx
//
// Ligações pelo Vivo Voz Negócio (entrega 056). As promessas:
//
//   1. clicar no telefone com contexto avisa o HIPO — e sem contexto, não
//   2. o aviso nunca segura nem quebra o tel: (servidor fora não é erro)
//   3. a aba mostra os números, a lista e o aviso de gravador desligado
//   4. a ligação aberta traz resumo, próximos passos e a conversa por lado
//   5. o Perfil gera o token uma vez e lista/revoga os gravadores
//   6. a faixa de "sem vínculo" some sem nada pendente e vincula/descarta
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, fireEvent, cleanup, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';

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

import { TelefonesDoContato } from '../components/crm/contatoComum';
import AbaLigacoes from '../components/crm/AbaLigacoes';
import GravadorLigacoes from '../components/crm/GravadorLigacoes';
import LigacoesSemVinculo from '../components/crm/LigacoesSemVinculo';
import { duracaoTexto, registrarLigacao } from '../components/crm/ligacoes';

function ligacao(extra = {}) {
  return {
    id: 'l1',
    status: 'pronta',
    status_rotulo: 'Transcrita',
    origem: 'clique',
    telefone: '11995713682',
    clicada_em: '2026-10-09T17:00:00Z',
    inicio_em: '2026-10-09T17:00:05Z',
    duracao_s: 185,
    usuario_id: 'u1',
    usuario_nome: 'Kethlleen Gomes',
    contato_nome: 'Carla Souza',
    oportunidade_id: 'o1',
    vinculada: true,
    tem_audio: true,
    fala_usuario_pct: 45,
    resumo: 'Carla pediu retorno na quinta.',
    proximos_passos: ['Ligar na quinta às 10h'],
    resumo_erro: null,
    erro: null,
    criado_em: '2026-10-09T17:00:00Z',
    ...extra,
  };
}

function lista(extra = {}) {
  return {
    ligacoes: [ligacao()],
    kpis: { total: 1, gravadas: 1, minutos: 3, transcritas: 1, fala_media_pct: 45 },
    gravacao: { disponivel: true, gravador_online: true },
    ...extra,
  };
}

beforeEach(() => {
  mockGet.mockReset();
  mockPost.mockReset();
  mockDelete.mockReset();
});
afterEach(cleanup);

describe('clique em ligar', () => {
  it('avisa o HIPO com o contexto e o número', () => {
    mockPost.mockResolvedValue({ data: {} });
    render(
      <TelefonesDoContato
        contato={{ telefone: '(11) 9 9571-3682' }}
        ligacao={{ oportunidade_id: 'o1', contato_id: 'c1', tarefa_id: null }}
      />,
    );
    const link = screen.getByRole('link', { name: /9571/ });
    expect(link).toHaveAttribute('href', 'tel:11995713682');
    fireEvent.click(link);
    expect(mockPost).toHaveBeenCalledWith('/crm/ligacoes', {
      telefone: '(11) 9 9571-3682', oportunidade_id: 'o1', contato_id: 'c1',
    });
  });

  it('sem contexto, o telefone é só um tel:', () => {
    render(<TelefonesDoContato contato={{ telefone: '1122223333' }} />);
    fireEvent.click(screen.getByRole('link', { name: /1122223333/ }));
    expect(mockPost).not.toHaveBeenCalled();
  });

  it('servidor fora não vira erro', async () => {
    mockPost.mockRejectedValue(new Error('rede'));
    expect(() => registrarLigacao({ oportunidade_id: 'o1' }, '11')).not.toThrow();
    mockPost.mockImplementation(() => { throw new Error('sincrono'); });
    expect(() => registrarLigacao({ oportunidade_id: 'o1' }, '11')).not.toThrow();
  });

  it('formata a duração', () => {
    expect(duracaoTexto(185)).toBe('3:05');
    expect(duracaoTexto(3725)).toBe('1:02:05');
    expect(duracaoTexto(null)).toBe('—');
  });
});

describe('aba Ligações', () => {
  function renderAba() {
    return render(<MemoryRouter><AbaLigacoes oportunidade={{ id: 'o1' }} /></MemoryRouter>);
  }

  it('mostra os números e a lista com o resumo', async () => {
    mockGet.mockResolvedValue({ data: lista() });
    renderAba();
    expect(await screen.findByText('Transcrita')).toBeInTheDocument();
    expect(mockGet).toHaveBeenCalledWith('/crm/ligacoes', { params: { oportunidade_id: 'o1' } });
    expect(screen.getByText('3:05')).toBeInTheDocument();
    expect(screen.getByText('45%')).toBeInTheDocument();
    expect(screen.getByText('Carla pediu retorno na quinta.')).toBeInTheDocument();
    expect(screen.queryByText(/gravador de ligações não está ligado/i)).not.toBeInTheDocument();
  });

  it('avisa quando o gravador da pessoa está desligado', async () => {
    mockGet.mockResolvedValue({ data: lista({ gravacao: { disponivel: true, gravador_online: false } }) });
    renderAba();
    expect(await screen.findByText(/gravador de ligações não está ligado/i)).toBeInTheDocument();
  });

  it('vazia explica como ligar', async () => {
    mockGet.mockResolvedValue({ data: lista({ ligacoes: [], kpis: { total: 0, gravadas: 0, minutos: 0, transcritas: 0, fala_media_pct: null } }) });
    renderAba();
    expect(await screen.findByText('Nenhuma ligação ainda')).toBeInTheDocument();
  });

  it('abrir mostra passos, conversa por lado e o áudio', async () => {
    mockGet.mockImplementation((url) => {
      if (url === '/crm/ligacoes') return Promise.resolve({ data: lista() });
      if (url === '/crm/ligacoes/l1/audio') return Promise.resolve({ data: { url: 'https://s3/x' } });
      return Promise.resolve({
        data: {
          ...ligacao(),
          pode_alterar: true,
          transcricao: [
            { inicio: '2026-10-09T17:00:06Z', participante: 'Kethlleen', canal: 0, texto: 'Bom dia, Carla?' },
            { inicio: '2026-10-09T17:00:08Z', participante: 'Carla', canal: 1, texto: 'Oi, tudo bem.' },
          ],
        },
      });
    });
    renderAba();
    fireEvent.click(await screen.findByRole('button', { expanded: false }));
    expect(await screen.findByText('Ligar na quinta às 10h')).toBeInTheDocument();
    const conversa = screen.getByTestId('conversa-ligacao');
    expect(conversa).toHaveTextContent('Bom dia, Carla?');
    expect(conversa).toHaveTextContent('Oi, tudo bem.');
    expect(screen.getByText(/falou 45% do tempo/)).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: /Ouvir/ }));
    await waitFor(() => expect(document.querySelector('audio')).toHaveAttribute('src', 'https://s3/x'));
  });
});

describe('gravador no Perfil', () => {
  it('lista os gravadores e gera o token uma vez', async () => {
    mockGet.mockResolvedValue({
      data: {
        disponivel: true,
        problemas: [],
        gravadores: [{
          id: 'g1', nome: 'Notebook', maquina: 'PC-SDR', versao_agente: '1.0.0',
          token_prefixo: 'hipograv_abcdef', online: true, ultimo_contato_em: '2026-10-09T17:00:00Z',
        }],
      },
    });
    mockPost.mockResolvedValue({ data: { token: 'hipograv_SEGREDO123', gravador: {} } });
    render(<GravadorLigacoes />);
    expect(await screen.findByText('Ligado agora')).toBeInTheDocument();
    expect(screen.getByRole('link', { name: /Baixar o instalador/ })).toHaveAttribute('href', '/downloads/hipo-gravador.zip');
    fireEvent.change(screen.getByLabelText(/Nome deste computador/), { target: { value: 'PC da Jake' } });
    fireEvent.click(screen.getByRole('button', { name: /Gerar token/ }));
    expect(await screen.findByTestId('token-gravador')).toHaveTextContent('hipograv_SEGREDO123');
    expect(mockPost).toHaveBeenCalledWith('/crm/ligacoes/gravadores', { nome: 'PC da Jake' });
  });

  it('revoga com confirmação', async () => {
    mockGet.mockResolvedValue({
      data: { disponivel: true, problemas: [], gravadores: [{ id: 'g1', nome: 'Velho', token_prefixo: 'hipograv_x', online: false, ultimo_contato_em: null }] },
    });
    mockDelete.mockResolvedValue({ data: { ok: true } });
    render(<GravadorLigacoes />);
    expect(await screen.findByText('Nunca conectou')).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: 'Revogar Velho' }));
    fireEvent.click(screen.getByRole('button', { name: 'Revogar' }));
    await waitFor(() => expect(mockDelete).toHaveBeenCalledWith('/crm/ligacoes/gravadores/g1'));
  });

  it('servidor sem S3 explica', async () => {
    mockGet.mockResolvedValue({ data: { disponivel: false, problemas: ['S3_BUCKET_ANEXOS não configurado'], gravadores: [] } });
    render(<GravadorLigacoes />);
    expect(await screen.findByText(/desligada no servidor/)).toBeInTheDocument();
  });
});

describe('ligações sem vínculo', () => {
  it('não aparece sem nada pendente', async () => {
    mockGet.mockResolvedValue({ data: { ligacoes: [], gravador_online: true } });
    const { container } = render(<LigacoesSemVinculo />);
    await waitFor(() => expect(mockGet).toHaveBeenCalled());
    expect(container).toBeEmptyDOMElement();
  });

  it('falha na busca também some (faixa acessória)', async () => {
    mockGet.mockRejectedValue(new Error('500'));
    const { container } = render(<LigacoesSemVinculo />);
    await waitFor(() => expect(mockGet).toHaveBeenCalled());
    expect(container).toBeEmptyDOMElement();
  });

  it('conta, abre e descarta com confirmação', async () => {
    mockGet
      .mockResolvedValueOnce({ data: { ligacoes: [ligacao({ id: 'l9', vinculada: false, oportunidade_id: null })] } })
      .mockResolvedValue({ data: { ligacoes: [] } });
    mockDelete.mockResolvedValue({ data: { ok: true } });
    render(<LigacoesSemVinculo />);
    fireEvent.click(await screen.findByRole('button', { name: /1 ligação gravada sem vínculo/ }));
    fireEvent.click(screen.getByRole('button', { name: 'Descartar gravação' }));
    fireEvent.click(screen.getByRole('button', { name: 'Apagar gravação' }));
    await waitFor(() => expect(mockDelete).toHaveBeenCalledWith('/crm/ligacoes/l9'));
    await waitFor(() => expect(screen.queryByText(/sem vínculo/)).not.toBeInTheDocument());
  });
});

describe('painel aberto acompanha a lista', () => {
  it('busca o detalhe de novo quando o status muda', async () => {
    const LigacaoDetalhe = (await import('../components/crm/LigacaoDetalhe')).default;
    mockGet.mockResolvedValue({ data: { ...ligacao({ status: 'transcrevendo', status_rotulo: 'Transcrevendo', resumo: null }), transcricao: [] } });
    const { rerender } = render(<LigacaoDetalhe ligacaoId="l1" versao="transcrevendo" />);
    await waitFor(() => expect(mockGet).toHaveBeenCalledTimes(1));
    rerender(<LigacaoDetalhe ligacaoId="l1" versao="pronta" />);
    await waitFor(() => expect(mockGet).toHaveBeenCalledTimes(2));
  });
});
