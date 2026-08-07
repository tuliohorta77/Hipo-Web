// web/src/components/crm/ModalDesfecho.jsx
//
// Fechar uma oportunidade. É o modal que o botão "Finalizar" do cartão abre,
// e o mesmo que apareceria ao arrastar para uma coluna Finalizado — por isso
// essa coluna não existe no kanban.
//
// A distinção entre Perdido e Cancelado é a decisão mais importante desta
// tela, e a mais fácil de errar. O texto de cada opção explica a consequência
// no relatório, porque quem escolhe no dia a dia não vai lembrar da regra:
//   Perdido   -> o cliente recusou. ENTRA na taxa de conversão.
//   Cancelado -> erro nosso de CRM. FICA FORA de todo denominador.

import { useCallback, useEffect, useState } from 'react';
import { Trophy, ThumbsDown, Eraser, Plus } from 'lucide-react';

import api from '../../api';
import Modal from '../ui/Modal';
import Button from '../ui/Button';
import Input, { Select } from '../ui/Input';
import AlertMessage from '../ui/AlertMessage';

const OPCOES = [
  {
    status: 'conquistado',
    rotulo: 'Conquistado',
    Icone: Trophy,
    tom: 'border-hipo-successBorder bg-hipo-successSoft text-hipo-success',
    explicacao: 'O cliente fechou. Entra como ganho na conversão.',
    tipoMotivo: null,
  },
  {
    status: 'perdido',
    rotulo: 'Perdido',
    Icone: ThumbsDown,
    tom: 'border-hipo-dangerBorder bg-hipo-dangerSoft text-hipo-danger',
    explicacao: 'O cliente recusou nossos serviços. Entra na taxa de conversão.',
    tipoMotivo: 'perda',
  },
  {
    status: 'cancelado',
    rotulo: 'Cancelado',
    Icone: Eraser,
    tom: 'border-hipo-border bg-hipo-bg text-hipo-slate',
    explicacao: 'Erro nosso de cadastro — lead errado, duplicata, empresa inexistente. Fica fora dos relatórios de conversão.',
    tipoMotivo: 'cancelamento',
  },
];

function mensagemDeErro(err, padrao) {
  const d = err?.response?.data?.detail;
  if (typeof d === 'string') return d;
  if (Array.isArray(d) && d[0]?.msg) return d[0].msg;
  if (d?.mensagem) return d.mensagem;
  return padrao;
}

export default function ModalDesfecho({ oportunidade, onFechar, onConcluido }) {
  const [status, setStatus] = useState(null);
  const [motivoId, setMotivoId] = useState('');
  const [motivos, setMotivos] = useState([]);
  const [novoMotivo, setNovoMotivo] = useState('');
  const [criandoMotivo, setCriandoMotivo] = useState(false);
  const [observacoes, setObservacoes] = useState('');
  const [erro, setErro] = useState(null);
  const [salvando, setSalvando] = useState(false);

  const aberto = Boolean(oportunidade);
  const escolha = OPCOES.find((o) => o.status === status);

  useEffect(() => {
    if (!aberto) return;
    setStatus(null);
    setMotivoId('');
    setNovoMotivo('');
    setObservacoes('');
    setErro(null);
  }, [aberto, oportunidade?.id]);

  const carregarMotivos = useCallback(async (tipo) => {
    if (!tipo) { setMotivos([]); return; }
    try {
      const { data } = await api.get(`/crm/dominio/motivos/${tipo}`);
      setMotivos(data);
    } catch (err) {
      setErro(mensagemDeErro(err, 'Não foi possível carregar os motivos.'));
    }
  }, []);

  useEffect(() => {
    setMotivoId('');
    carregarMotivos(escolha?.tipoMotivo);
  }, [escolha?.tipoMotivo, carregarMotivos]);

  async function criarMotivo() {
    const nome = novoMotivo.trim();
    if (!nome || !escolha?.tipoMotivo) return;
    setCriandoMotivo(true);
    try {
      const { data } = await api.post(
        `/crm/dominio/motivos/${escolha.tipoMotivo}`, { nome }
      );
      setMotivos((ms) => (ms.some((m) => m.id === data.id) ? ms : [...ms, data]));
      setMotivoId(String(data.id));
      setNovoMotivo('');
    } catch (err) {
      setErro(mensagemDeErro(err, 'Não foi possível criar o motivo.'));
    } finally {
      setCriandoMotivo(false);
    }
  }

  async function confirmar() {
    if (!escolha) return;
    if (escolha.tipoMotivo && !motivoId) {
      setErro('Informe o motivo.');
      return;
    }
    setSalvando(true);
    setErro(null);
    try {
      const { data } = await api.post(
        `/crm/oportunidades/${oportunidade.id}/desfecho`,
        {
          status: escolha.status,
          motivo_desfecho_id: motivoId ? Number(motivoId) : null,
          observacoes: observacoes.trim() || null,
        }
      );
      onConcluido(data);
    } catch (err) {
      setErro(mensagemDeErro(err, 'Não foi possível finalizar a oportunidade.'));
    } finally {
      setSalvando(false);
    }
  }

  return (
    <Modal
      aberto={aberto}
      onFechar={onFechar}
      titulo="Finalizar oportunidade"
      subtitulo={oportunidade
        ? `${oportunidade.numero} · ${oportunidade.conta_razao_social}`
        : undefined}
      size="md"
      footer={
        <div className="flex justify-end gap-2">
          <Button variant="ghost" onClick={onFechar}>Cancelar</Button>
          <Button onClick={confirmar} loading={salvando} disabled={!status}>
            Finalizar
          </Button>
        </div>
      }
    >
      <div className="space-y-4">
        {erro && <AlertMessage tipo="erro">{erro}</AlertMessage>}

        <div className="space-y-2">
          {OPCOES.map(({ status: s, rotulo, Icone, tom, explicacao }) => (
            <button
              key={s}
              type="button"
              onClick={() => setStatus(s)}
              aria-pressed={status === s}
              className={
                'w-full text-left p-3 rounded-lg border transition-all ' +
                (status === s ? `${tom} ring-2 ring-offset-1` : 'border-hipo-border hover:bg-hipo-bg')
              }
            >
              <span className="flex items-center gap-2 font-medium">
                <Icone size={16} />{rotulo}
              </span>
              <span className="block mt-0.5 text-xs opacity-90">{explicacao}</span>
            </button>
          ))}
        </div>

        {escolha?.tipoMotivo && (
          <div className="space-y-2">
            <Select
              label="Motivo *"
              value={motivoId}
              onChange={(e) => setMotivoId(e.target.value)}
            >
              <option value="">— selecione —</option>
              {motivos.map((m) => <option key={m.id} value={m.id}>{m.nome}</option>)}
            </Select>
            <div className="flex gap-2 items-end">
              <Input
                label="Criar motivo"
                placeholder={escolha.status === 'perdido' ? 'ex.: Preço' : 'ex.: Lead errado'}
                className="flex-1"
                value={novoMotivo}
                onChange={(e) => setNovoMotivo(e.target.value)}
              />
              <Button
                variant="secondary"
                icon={Plus}
                loading={criandoMotivo}
                disabled={!novoMotivo.trim()}
                onClick={criarMotivo}
              >
                Adicionar
              </Button>
            </div>
          </div>
        )}

        {status && (
          <Input
            label="Observação (opcional)"
            placeholder="O que aconteceu…"
            value={observacoes}
            onChange={(e) => setObservacoes(e.target.value)}
          />
        )}
      </div>
    </Modal>
  );
}
