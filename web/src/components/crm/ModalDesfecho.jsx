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
//
// ── Por que abre por cima (nivel=2 por padrão) ───────────────────────
// Este modal é aberto de DENTRO do modal da oportunidade. Com o `z-50` que
// todo modal usava, quem ficava por cima era quem estivesse por último no
// JSX — e este estava escrito antes. O usuário clicava em Finalizar e o
// formulário abria atrás: parecia que o botão não fazia nada, e só fechando
// a oportunidade dava para achá-lo.
//
// O nível é PADRÃO, não fixo. No funil a oportunidade é o modal de nível 1 e
// este é o 2. No módulo de Tarefas a oportunidade já vem empilhada sobre o
// modal da tarefa (nível 2), e ali este precisa ser o 3 — com o 2 cravado no
// código, o formulário de finalizar voltaria a abrir ATRÁS da oportunidade,
// que é exatamente o sintoma que o `nivel` existe para matar.
//
// ── Por que o registro do fechamento é obrigatório ───────────────────
// Toda tarefa concluída exige a próxima; a oportunidade finalizada é a
// exceção — e era exatamente por ali que o histórico vazava. O negócio
// fechava e o CRM não guardava O QUE fechou: qual reunião, qual ligação, o
// que o cliente disse. Ficava o status e o motivo da lista, que é
// classificação, não relato.
//
// Então finalizar exige registrar o ato do fechamento como uma tarefa JÁ
// CONCLUÍDA — data do que aconteceu, tipo, título, quem fez. Ela entra na
// linha do tempo da oportunidade e conta na produção do mês, porque foi
// trabalho feito de verdade. Não gera pendência nova: nasce fechada.
//
// Vale para os três desfechos, cancelado incluído. Cancelar é erro de
// cadastro, e saber QUEM descobriu que o lead era duplicado — e como — é o
// que evita o mesmo erro entrar de novo pela mesma porta.
//
// O backend cria a tarefa na MESMA transação do desfecho (POST /desfecho
// recebe o campo `tarefa`). Duas chamadas daqui deixariam a oportunidade
// finalizada sem registro se a segunda falhasse.

import { useCallback, useEffect, useMemo, useState } from 'react';
import { Trophy, ThumbsDown, Eraser, Plus } from 'lucide-react';

import api, { getUser } from '../../api';
import Modal from '../ui/Modal';
import Button from '../ui/Button';
import Input, { Select } from '../ui/Input';
import AlertMessage from '../ui/AlertMessage';
import { TIPOS, paraCampoLocal, paraIso } from './tarefaComum';

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

// O placeholder muda com o desfecho porque o exemplo é o que ensina o nível
// de detalhe esperado. "Reunião" genérico não diz nada seis meses depois.
const EXEMPLO_TITULO = {
  conquistado: 'ex.: Reunião — cliente aprovou a proposta das 40 vidas',
  perdido: 'ex.: Ligação — RH informou que fecharam com o concorrente',
  cancelado: 'ex.: Conferência do cadastro — CNPJ duplicado da Alfa',
};

const CLASSE_TEXTAREA =
  'w-full px-3 py-2 rounded-lg bg-hipo-card border border-hipo-border ' +
  'text-hipo-ink text-sm outline-none transition-colors resize-y ' +
  'placeholder:text-hipo-muted ' +
  'focus:border-hipo-blue focus:ring-2 focus:ring-blue-100';

function mensagemDeErro(err, padrao) {
  const d = err?.response?.data?.detail;
  if (typeof d === 'string') return d;
  if (Array.isArray(d) && d[0]?.msg) return d[0].msg;
  if (d?.mensagem) return d.mensagem;
  return padrao;
}

/*
  O registro nasce com AGORA como data, não com "amanhã 09:00" como a tarefa
  comum. São coisas diferentes: a tarefa comum é compromisso futuro e o
  padrão útil é o próximo dia útil; esta é relato do que acabou de acontecer,
  e o padrão útil é o instante em que a pessoa está finalizando.
*/
function registroVazio(responsavelPadrao = '') {
  return {
    tipo: 'reuniao',
    titulo: '',
    descricao: '',
    responsavel_id: responsavelPadrao,
    prazo: paraCampoLocal(new Date().toISOString()),
  };
}

export default function ModalDesfecho({
  oportunidade, onFechar, onConcluido,
  // Ver a nota sobre empilhamento no topo do arquivo.
  nivel = 2,
}) {
  const usuarioLogado = useMemo(() => getUser(), []);
  const responsavelPadrao = usuarioLogado?.id ? String(usuarioLogado.id) : '';

  const [status, setStatus] = useState(null);
  const [motivoId, setMotivoId] = useState('');
  const [motivos, setMotivos] = useState([]);
  const [novoMotivo, setNovoMotivo] = useState('');
  const [criandoMotivo, setCriandoMotivo] = useState(false);
  const [observacoes, setObservacoes] = useState('');
  const [registro, setRegistro] = useState(() => registroVazio(responsavelPadrao));
  const [usuarios, setUsuarios] = useState([]);
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
    setRegistro(registroVazio(responsavelPadrao));
    setErro(null);
  }, [aberto, oportunidade?.id, responsavelPadrao]);

  /*
    A lista de usuários só é buscada com o modal aberto. Buscar na montagem
    faria toda tela que monta este componente — e ele fica montado o tempo
    todo, escondido, em Oportunidades — pagar uma chamada que ninguém pediu.
  */
  useEffect(() => {
    if (!aberto) return;
    let vivo = true;
    api.get('/crm/dominio/usuarios')
      .then(({ data }) => { if (vivo) setUsuarios(data); })
      .catch(() => { if (vivo) setUsuarios([]); });
    return () => { vivo = false; };
  }, [aberto]);

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

  // O título é o único campo do registro sem padrão razoável: tipo, data e
  // responsável já vêm preenchidos, e inventar um título ("Fechamento") seria
  // gravar ruído com cara de informação.
  const registroIncompleto = !registro.titulo.trim() || !registro.prazo;

  async function confirmar() {
    if (!escolha) return;
    if (escolha.tipoMotivo && !motivoId) {
      setErro('Informe o motivo.');
      return;
    }
    if (registroIncompleto) {
      setErro('Descreva o que aconteceu no fechamento.');
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
          tarefa: {
            tipo: registro.tipo,
            titulo: registro.titulo.trim(),
            descricao: registro.descricao.trim() || null,
            // Sem responsável escolhido o backend usa quem está finalizando.
            responsavel_id: registro.responsavel_id || null,
            prazo: paraIso(registro.prazo),
          },
        }
      );
      onConcluido(data);
    } catch (err) {
      setErro(mensagemDeErro(err, 'Não foi possível finalizar a oportunidade.'));
    } finally {
      setSalvando(false);
    }
  }

  const setCampo = (campo) => (e) =>
    setRegistro((r) => ({ ...r, [campo]: e.target.value }));

  return (
    <Modal
      aberto={aberto}
      onFechar={onFechar}
      titulo="Finalizar oportunidade"
      subtitulo={oportunidade
        ? `${oportunidade.numero} · ${oportunidade.conta_razao_social}`
        : undefined}
      size="lg"
      nivel={nivel}
      footer={
        <div className="flex justify-end gap-2">
          <Button variant="ghost" onClick={onFechar}>Cancelar</Button>
          <Button
            onClick={confirmar}
            loading={salvando}
            disabled={!status || registroIncompleto}
          >
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

        {/*
          A observação vai para o campo de observações da OPORTUNIDADE — é
          nota do registro comercial. O detalhe do registro logo abaixo vai
          para a tarefa. Ficam separados porque respondem a perguntas
          diferentes seis meses depois: "o que ficou anotado neste negócio"
          e "o que aconteceu naquele dia".
        */}
        {status && (
          <Input
            label="Observação (opcional)"
            placeholder="O que aconteceu…"
            value={observacoes}
            onChange={(e) => setObservacoes(e.target.value)}
          />
        )}

        {/*
          ── Registro do fechamento ──
          Aparece junto com a escolha do desfecho, não depois: é parte da
          mesma decisão. Escondê-lo atrás de um "adicionar registro" faria
          dele um passo opcional aos olhos de quem usa, e ele não é.
        */}
        {status && (
          <div className="space-y-3 border-t border-hipo-border pt-4">
            <div>
              <h3 className="text-sm font-semibold text-hipo-ink">
                Registro do fechamento *
              </h3>
              <p className="text-xs text-hipo-slate mt-0.5">
                O que aconteceu para o negócio chegar aqui. Entra na linha do
                tempo da oportunidade já como tarefa concluída — o motivo
                acima classifica, este campo conta a história.
              </p>
            </div>

            <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
              <div className="md:col-span-2">
                <Input
                  id="desfecho-titulo"
                  label="O que aconteceu *"
                  placeholder={EXEMPLO_TITULO[status]}
                  value={registro.titulo}
                  onChange={setCampo('titulo')}
                  inputClassName="text-base"
                />
              </div>

              <Select
                id="desfecho-tipo"
                label="Tipo"
                value={registro.tipo}
                onChange={setCampo('tipo')}
              >
                {TIPOS.map((t) => (
                  <option key={t.valor} value={t.valor}>{t.rotulo}</option>
                ))}
              </Select>

              <Input
                id="desfecho-prazo"
                label="Quando"
                type="datetime-local"
                value={registro.prazo}
                onChange={setCampo('prazo')}
              />

              <div className="md:col-span-2">
                <Select
                  id="desfecho-responsavel"
                  label="Quem fez"
                  value={registro.responsavel_id}
                  onChange={setCampo('responsavel_id')}
                >
                  {/*
                    O campo já vem com quem está finalizando. A opção vazia
                    é a saída para sessão sem usuário gravado no
                    localStorage — aí o backend usa o autenticado.
                  */}
                  <option value="">— quem está finalizando —</option>
                  {usuarios.map((u) => (
                    <option key={u.id} value={u.id}>{u.nome}</option>
                  ))}
                </Select>
              </div>

              <div className="md:col-span-2">
                <label
                  htmlFor="desfecho-detalhe"
                  className="block text-sm font-medium text-hipo-ink mb-1.5"
                >
                  Detalhe (opcional)
                </label>
                <textarea
                  id="desfecho-detalhe"
                  rows={3}
                  value={registro.descricao}
                  onChange={setCampo('descricao')}
                  placeholder="Quem participou, o que ficou combinado, o que levou à decisão"
                  className={CLASSE_TEXTAREA}
                />
              </div>
            </div>
          </div>
        )}
      </div>
    </Modal>
  );
}
