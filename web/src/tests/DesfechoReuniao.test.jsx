// web/src/tests/DesfechoReuniao.test.jsx
//
// A reunião vista pela TAREFA. O defeito que originou isto: a Agenda
// perguntava "o que aconteceu?" com Realizada / Cancelada / No-show, e a tela
// de Tarefas oferecia Concluir e Cancelar para a mesma reunião. Promessas:
//   1. tarefa que é reunião ou visita não oferece Concluir nem Cancelar
//   2. o desfecho tem as três respostas, com a sugestão do servidor marcada
//   3. na agenda, editar abre o formulário completo da reunião
//   4. fora da agenda, continua dando para editar e colocar na agenda
//   5. a próxima tarefa que é reunião vai para a agenda depois do fechamento
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, fireEvent, cleanup, waitFor } from '@testing-library/react';

const mockPost = vi.fn();

vi.mock('../api', () => ({
  default: { post: (...a) => mockPost(...a) },
}));

import {
  PainelReuniaoDaTarefa, SeloDesfecho, agendarProximaSeForReuniao, reuniaoDaTarefa,
} from '../components/crm/DesfechoReuniao';

const USUARIOS = [{ id: 'u1', nome: 'Jakeline Santana', cargo: 'EV' }];

function tarefa(extra = {}) {
  return {
    id: 't1', alvo: 'oportunidade', oportunidade_id: 'o1',
    status_oportunidade: 'ativa', outras_abertas: 1,
    tipo: 'reuniao', tipo_rotulo: 'Reunião', agendavel: true,
    titulo: 'Apresentar proposta', descricao: null,
    responsavel_id: 'u1', prazo: '2026-09-08T12:00:00Z',
    situacao: 'futura', reuniao_id: 'r1', reuniao_tipo_sigla: 'AP',
    desfecho_sugerido: 'no_show', desfecho_efetivo: null,
    ...extra,
  };
}

function montar(props = {}) {
  const handlers = {
    setPainel: vi.fn(),
    onRegistrarDesfecho: vi.fn().mockResolvedValue(true),
    onAbrirReuniao: vi.fn(),
    onEditar: vi.fn().mockResolvedValue(true),
    onAgendar: vi.fn(),
  };
  const utils = render(
    <PainelReuniaoDaTarefa
      tarefa={tarefa()}
      painel={null}
      usuarios={USUARIOS}
      ocupado={false}
      {...handlers}
      {...props}
    />
  );
  return { ...utils, ...handlers };
}

beforeEach(() => { mockPost.mockReset(); });
afterEach(cleanup);

describe('PainelReuniaoDaTarefa — as ações', () => {
  it('não oferece Concluir nem Cancelar: pergunta o que aconteceu', () => {
    const { setPainel } = montar();
    expect(screen.queryByText('Concluir')).not.toBeInTheDocument();
    expect(screen.queryByText('Cancelar')).not.toBeInTheDocument();
    fireEvent.click(screen.getByText('O que aconteceu?'));
    expect(setPainel).toHaveBeenCalledWith('desfecho');
  });

  it('na agenda, editar abre o formulário completo da reunião', () => {
    const { onAbrirReuniao } = montar();
    fireEvent.click(screen.getByText('Editar reunião'));
    expect(onAbrirReuniao).toHaveBeenCalledWith('r1');
    expect(screen.getByText(/na agenda · AP/)).toBeInTheDocument();
  });

  it('fora da agenda, edita a tarefa e oferece colocar na agenda', () => {
    const t = tarefa({ reuniao_id: null, reuniao_tipo_sigla: null });
    const { setPainel, onAgendar } = montar({ tarefa: t });
    expect(screen.queryByText('Editar reunião')).not.toBeInTheDocument();
    fireEvent.click(screen.getByText('Editar'));
    expect(setPainel).toHaveBeenCalledWith('editar');
    fireEvent.click(screen.getByText('Colocar na agenda'));
    expect(onAgendar).toHaveBeenCalledWith(t);
  });
});

describe('PainelReuniaoDaTarefa — o desfecho', () => {
  it('as três respostas, com a sugestão do servidor já marcada', () => {
    montar({ painel: 'desfecho' });
    const opcoes = screen.getAllByRole('radio');
    expect(opcoes.map((o) => o.textContent)).toEqual([
      expect.stringContaining('Realizada'),
      expect.stringContaining('Cancelada'),
      expect.stringContaining('No-show'),
    ]);
    expect(screen.getByRole('radio', { checked: true })).toHaveTextContent('No-show');
  });

  it('registrar manda o desfecho escolhido', async () => {
    const { onRegistrarDesfecho, setPainel } = montar({ painel: 'desfecho' });
    fireEvent.click(screen.getByRole('radio', { name: /Cancelada/ }));
    fireEvent.click(screen.getByText('Registrar cancelada'));
    await waitFor(() => expect(onRegistrarDesfecho).toHaveBeenCalled());
    const [t, corpo] = onRegistrarDesfecho.mock.calls[0];
    expect(t.id).toBe('t1');
    expect(corpo).toMatchObject({ desfecho: 'cancelada', proxima: null });
    await waitFor(() => expect(setPainel).toHaveBeenCalledWith(null));
  });

  it('realizada na última tarefa aberta exige a próxima', () => {
    montar({ painel: 'desfecho', tarefa: tarefa({ outras_abertas: 0 }) });
    fireEvent.click(screen.getByRole('radio', { name: /Realizada/ }));
    expect(screen.getByText('Registrar realizada').closest('button')).toBeDisabled();
    expect(screen.getByLabelText('Próxima: Título')).toBeInTheDocument();
  });

  it('parceiro sem outra tarefa aberta também exige a próxima', () => {
    montar({
      painel: 'desfecho',
      tarefa: tarefa({ oportunidade_id: null, status_oportunidade: null, outras_abertas: 0 }),
    });
    fireEvent.click(screen.getByRole('radio', { name: /Realizada/ }));
    expect(screen.getByLabelText('Próxima: Título')).toBeInTheDocument();
  });

  it('voltar fecha o painel sem registrar', () => {
    const { setPainel, onRegistrarDesfecho } = montar({ painel: 'desfecho' });
    fireEvent.click(screen.getByText('Voltar'));
    expect(setPainel).toHaveBeenCalledWith(null);
    expect(onRegistrarDesfecho).not.toHaveBeenCalled();
  });
});

describe('reuniaoDaTarefa', () => {
  it('traduz prazo e responsável para o vocabulário da agenda', () => {
    expect(reuniaoDaTarefa(tarefa())).toMatchObject({
      inicio: '2026-09-08T12:00:00Z', anfitriao_id: 'u1',
      desfecho_sugerido: 'no_show', status_oportunidade: 'ativa',
    });
  });
});

describe('SeloDesfecho', () => {
  it('no-show aparece como no-show, não como cancelado', () => {
    render(<SeloDesfecho tarefa={tarefa({ desfecho_efetivo: 'no_show' })} />);
    expect(screen.getByText('No-show')).toBeInTheDocument();
  });

  it('sem desfecho, não desenha nada', () => {
    const { container } = render(<SeloDesfecho tarefa={tarefa()} />);
    expect(container).toBeEmptyDOMElement();
  });
});

describe('agendarProximaSeForReuniao', () => {
  it('põe na agenda a próxima que é reunião', async () => {
    mockPost.mockResolvedValue({ data: {} });
    const r = await agendarProximaSeForReuniao({ tipo: 'visita' }, 'p1');
    expect(r).toBeNull();
    expect(mockPost).toHaveBeenCalledWith(
      '/crm/agenda/reunioes/de-tarefa/p1', { modalidade: 'presencial' },
    );
  });

  it('ligação não vai para a agenda', async () => {
    expect(await agendarProximaSeForReuniao({ tipo: 'ligacao' }, 'p1')).toBeNull();
    expect(mockPost).not.toHaveBeenCalled();
  });

  it('se não couber na agenda, devolve o aviso em vez de estourar', async () => {
    mockPost.mockRejectedValue({ response: { data: { detail: 'Esse horário já está ocupado.' } } });
    const r = await agendarProximaSeForReuniao({ tipo: 'reuniao' }, 'p1');
    expect(r).toMatch(/não entrou na agenda: Esse horário já está ocupado/);
  });
});
