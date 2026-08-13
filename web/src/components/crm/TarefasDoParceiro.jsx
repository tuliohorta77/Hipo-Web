// web/src/components/crm/TarefasDoParceiro.jsx
//
// As tarefas de um parceiro, dentro do painel lateral da carteira.
//
// ── Por que existe ───────────────────────────────────────────────────
// Até a 006 a tela de Parceiros era operacional só na carteira: dava para
// trocar o EC e transferir em massa, mas não para agendar a próxima conversa.
// O resultado era a tela dizer "esse parceiro está dormente há 200 dias" sem
// oferecer nada a fazer sobre isso — diagnóstico sem remédio.
//
// ── O que muda em relação à aba da oportunidade ──────────────────────
// Uma coisa só: concluir NÃO exige agendar a próxima. A regra da oportunidade
// se apoia num estado final — um dia ela é conquistada ou perdida e a corrente
// termina. Parceria não tem estado final, e exigir a próxima ali produziria
// corrente infinita de tarefa que ninguém faz. Quem cobra cadência é o farol,
// que fica vermelho sozinho.
//
// A próxima continua sendo OFERECIDA: quem já sabe quando vai voltar a falar
// agenda no mesmo clique. O backend aceita as duas formas.
//
// ── Por que não é modal ──────────────────────────────────────────────
// O painel do parceiro já é uma superfície sobreposta. Modal dentro de modal
// empilha z-index, rouba foco e faz o Esc fechar os dois — a mesma decisão da
// aba de Tarefas da oportunidade. Criar e concluir expandem no lugar.

import { useCallback, useEffect, useState } from 'react';
import { Plus, Check, X, CalendarClock } from 'lucide-react';

import api from '../../api';
import Button from '../ui/Button';
import Input from '../ui/Input';
import Badge from '../ui/Badge';
import {
  ABERTAS,
  CamposTarefa,
  ICONE_TIPO,
  SITUACAO,
  corpoDaTarefa,
  dataCompleta,
  dataCurta,
  formIncompleto,
  mensagemDeErro,
  tarefaVazia,
} from './tarefaComum';

export default function TarefasDoParceiro({
  parceiroId, usuarios, usuarioAtualId, onMudou,
}) {
  const [tarefas, setTarefas] = useState([]);
  const [carregando, setCarregando] = useState(true);
  const [erro, setErro] = useState(null);
  const [criando, setCriando] = useState(false);
  const [form, setForm] = useState(() => tarefaVazia(usuarioAtualId));
  const [ocupado, setOcupado] = useState(false);
  // Qual tarefa está com painel aberto e qual painel: 'concluir' | 'cancelar'.
  const [acao, setAcao] = useState(null);
  const [resultado, setResultado] = useState('');
  const [motivo, setMotivo] = useState('');
  const [proxima, setProxima] = useState(null);

  const carregar = useCallback(async () => {
    setCarregando(true);
    try {
      const { data } = await api.get('/crm/tarefas', {
        params: { conta_id: parceiroId, ordenar: 'urgencia' },
      });
      setTarefas(data.itens || []);
    } catch (err) {
      setErro(mensagemDeErro(err, 'Não foi possível carregar as tarefas.'));
    } finally {
      setCarregando(false);
    }
  }, [parceiroId]);

  useEffect(() => { carregar(); }, [carregar]);

  // Trocar de parceiro tem que fechar tudo que estava aberto. Sem isto, o
  // painel de concluir da tarefa anterior continuaria montado sobre a lista
  // do parceiro novo.
  useEffect(() => {
    setAcao(null);
    setCriando(false);
    setErro(null);
  }, [parceiroId]);

  function encerrar() {
    setAcao(null);
    setCriando(false);
    setProxima(null);
    setResultado('');
    setMotivo('');
  }

  async function executar(promessa, padrao) {
    setOcupado(true);
    setErro(null);
    try {
      await promessa;
      encerrar();
      await carregar();
      // O farol e a contagem de abertas mudaram: quem manda recarregar a
      // linha é a tela, não este componente. Sem o aviso, o quadradinho da
      // semana continuaria vermelho depois de a tarefa ser concluída.
      onMudou?.();
      return true;
    } catch (err) {
      setErro(mensagemDeErro(err, padrao));
      return false;
    } finally {
      setOcupado(false);
    }
  }

  const criar = () => executar(
    api.post('/crm/tarefas', { conta_id: parceiroId, ...corpoDaTarefa(form) }),
    'Não foi possível criar a tarefa.',
  );

  const concluir = (tarefa) => executar(
    api.post(`/crm/tarefas/${tarefa.id}/concluir`, {
      resultado: resultado.trim() || null,
      proxima: proxima ? corpoDaTarefa(proxima) : null,
    }),
    'Não foi possível concluir a tarefa.',
  );

  const cancelar = (tarefa) => executar(
    api.post(`/crm/tarefas/${tarefa.id}/cancelar`, { motivo: motivo.trim() || null }),
    'Não foi possível cancelar a tarefa.',
  );

  const abertas = tarefas.filter((t) => ABERTAS.includes(t.situacao));
  const fechadas = tarefas.filter((t) => !ABERTAS.includes(t.situacao));

  return (
    <section aria-label="Tarefas do parceiro">
      <div className="flex items-center justify-between gap-2 mb-1.5">
        <h4 className="text-xs font-semibold text-hipo-ink">
          Tarefas {abertas.length > 0 && (
            <span className="text-hipo-slate font-normal">({abertas.length} em aberto)</span>
          )}
        </h4>
        {!criando && (
          <Button
            size="sm"
            variant="ghost"
            icon={Plus}
            onClick={() => { encerrar(); setForm(tarefaVazia(usuarioAtualId)); setCriando(true); }}
          >
            Nova
          </Button>
        )}
      </div>

      {erro && <p className="mb-2 text-[11px] text-hipo-danger">{erro}</p>}

      {criando && (
        <div className="mb-3 space-y-2 rounded-lg border border-hipo-border bg-hipo-card p-2">
          <CamposTarefa valor={form} onChange={setForm} usuarios={usuarios} />
          <div className="flex justify-end gap-2">
            <Button size="sm" variant="ghost" onClick={encerrar}>Voltar</Button>
            <Button
              size="sm"
              loading={ocupado}
              disabled={formIncompleto(form)}
              onClick={criar}
            >
              Agendar
            </Button>
          </div>
        </div>
      )}

      {carregando ? (
        <p className="py-3 text-center text-xs text-hipo-slate">Carregando…</p>
      ) : tarefas.length === 0 ? (
        <p className="py-3 text-center text-[11px] text-hipo-muted">
          Nenhuma tarefa ainda. Agende a próxima conversa com este parceiro.
        </p>
      ) : (
        <ul className="space-y-1.5">
          {[...abertas, ...fechadas].map((t) => {
            const tom = SITUACAO[t.situacao] || SITUACAO.cancelada;
            const Icone = ICONE_TIPO[t.tipo] || CalendarClock;
            const aberta = ABERTAS.includes(t.situacao);
            const painel = acao?.id === t.id ? acao.painel : null;

            return (
              <li
                key={t.id}
                className="rounded-lg border border-hipo-border bg-hipo-card p-2"
              >
                <div className="flex items-start gap-2">
                  <Icone size={13} className={`mt-0.5 shrink-0 ${tom.icone}`} />
                  <div className="min-w-0 flex-1">
                    <span className="block text-xs text-hipo-ink">{t.titulo}</span>
                    <span className="flex items-center gap-1.5 mt-0.5">
                      <Badge tone={tom.tom}>{tom.palavra}</Badge>
                      <span className="text-[10px] text-hipo-slate">
                        {dataCurta(t.prazo)}
                      </span>
                      {t.responsavel_nome && (
                        <span className="text-[10px] text-hipo-muted truncate">
                          {t.responsavel_nome}
                        </span>
                      )}
                    </span>
                    {t.resultado && (
                      <span className="block mt-1 text-[10px] text-hipo-slate">
                        {t.resultado}
                      </span>
                    )}
                  </div>
                </div>

                {aberta && !painel && (
                  <div className="mt-1.5 flex gap-1.5">
                    <Button
                      size="sm"
                      icon={Check}
                      aria-label={`Concluir ${t.titulo}`}
                      onClick={() => {
                        setResultado('');
                        setProxima(null);
                        setAcao({ id: t.id, painel: 'concluir' });
                      }}
                    >
                      Concluir
                    </Button>
                    <Button
                      size="sm"
                      variant="ghost"
                      icon={X}
                      aria-label={`Cancelar ${t.titulo}`}
                      onClick={() => { setMotivo(''); setAcao({ id: t.id, painel: 'cancelar' }); }}
                    >
                      Cancelar
                    </Button>
                  </div>
                )}

                {painel === 'concluir' && (
                  <div className="mt-2 space-y-2 border-l-2 border-hipo-border pl-2">
                    <Input
                      label="O que aconteceu (opcional)"
                      placeholder="Passou dois contatos para a semana que vem"
                      value={resultado}
                      onChange={(e) => setResultado(e.target.value)}
                    />
                    {/*
                      Oferecida, não exigida. Parceria não tem estado final —
                      ver o cabeçalho deste arquivo.
                    */}
                    {proxima ? (
                      <div className="space-y-2">
                        <CamposTarefa
                          valor={proxima}
                          onChange={setProxima}
                          usuarios={usuarios}
                          prefixo="Próxima: "
                        />
                        <button
                          type="button"
                          onClick={() => setProxima(null)}
                          className="text-[11px] text-hipo-slate underline"
                        >
                          Não agendar agora
                        </button>
                      </div>
                    ) : (
                      <button
                        type="button"
                        onClick={() => setProxima(tarefaVazia(t.responsavel_id))}
                        className="text-[11px] text-hipo-blue underline"
                      >
                        Agendar a próxima conversa
                      </button>
                    )}
                    <div className="flex justify-end gap-2">
                      <Button size="sm" variant="ghost" onClick={encerrar}>Voltar</Button>
                      <Button
                        size="sm"
                        loading={ocupado}
                        disabled={Boolean(proxima) && formIncompleto(proxima)}
                        onClick={() => concluir(t)}
                      >
                        Concluir tarefa
                      </Button>
                    </div>
                  </div>
                )}

                {painel === 'cancelar' && (
                  <div className="mt-2 space-y-2 border-l-2 border-hipo-border pl-2">
                    <Input
                      label="Motivo (opcional)"
                      placeholder="Agendei duplicado"
                      value={motivo}
                      onChange={(e) => setMotivo(e.target.value)}
                    />
                    <div className="flex justify-end gap-2">
                      <Button size="sm" variant="ghost" onClick={encerrar}>Voltar</Button>
                      <Button
                        size="sm"
                        variant="secondary"
                        loading={ocupado}
                        onClick={() => cancelar(t)}
                      >
                        Cancelar tarefa
                      </Button>
                    </div>
                  </div>
                )}

                {!aberta && t.concluida_em && (
                  <span className="block mt-1 text-[10px] text-hipo-muted">
                    {dataCompleta(t.concluida_em)}
                  </span>
                )}
              </li>
            );
          })}
        </ul>
      )}
    </section>
  );
}
