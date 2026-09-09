// web/src/components/crm/ProdutividadeAgenda.jsx
//
// As duas perguntas que a operação fecha todo dia:
//
//   "quantos agendamentos por dia, por SDR"
//   "quantas reuniões por dia, por EV — e com que resultado"
//
// ── Por que dois quadros e não um ────────────────────────────────────
// Os dois eixos de data são DIFERENTES, e é isso que os torna comparáveis.
// O SDR é medido pelo dia em que MARCOU; o EV, pelo dia em que a reunião
// ACONTECEU. Uma reunião que o SDR marcou segunda para quinta conta no dia
// do SDR na segunda e no dia do EV na quinta. Numa tabela só, as duas
// colunas teriam o mesmo cabeçalho de data querendo dizer coisas
// diferentes — e alguém somaria as duas.
//
// ── Por que modal e não tela ─────────────────────────────────────────
// O relatório responde à pergunta de quem está OLHANDO a agenda: "como foi
// a semana". Numa tela própria, ele viraria um destino separado que
// ninguém visita — e a decisão de olhar o número deixaria de acontecer no
// momento em que ela é natural, que é com a grade na frente.
//
// ── O que a tela NÃO faz ─────────────────────────────────────────────
// Nada aqui adivinha desfecho. Reunião que passou e ninguém marcou aparece
// na coluna "pendentes", separada, e fica fora das duas taxas. Foi a
// decisão do produto: virar no-show sozinha depois de N horas fecharia o
// número mais rápido ao preço de inventar um resultado que ninguém
// afirmou.

import { useCallback, useEffect, useMemo, useState } from 'react';
import { CalendarRange, TrendingUp, UserX } from 'lucide-react';

import api from '../../api';
import Modal from '../ui/Modal';
import Badge from '../ui/Badge';
import AlertMessage from '../ui/AlertMessage';
import Empty from '../ui/Empty';
import Table, { Th, Td, Tr } from '../ui/Table';
import { diaCurto, mensagemDeErro } from './agendaComum';

/**
 * Percentual, ou um traço quando não há denominador.
 *
 * `null` não é zero: uma semana sem nenhuma reunião fechada tem taxa
 * INDEFINIDA, e escrever "0%" ali diria que ninguém realizou nada — a
 * mesma frase que descreve uma semana ruim de verdade.
 */
function taxa(v) {
  if (v === null || v === undefined) return '—';
  return `${Math.round(v * 100)}%`;
}

function Numero({ valor, tom = 'text-hipo-ink' }) {
  // Zero em cinza claro: numa tabela de cinco dias por pessoa, a maioria
  // das células é zero, e todas em preto escondem as que têm número.
  return (
    <span className={`tabular-nums ${valor ? tom : 'text-hipo-muted'}`}>
      {valor}
    </span>
  );
}

export default function ProdutividadeAgenda({
  aberto, onFechar, de, ate, nivel = 2,
}) {
  const [dados, setDados] = useState(null);
  const [carregando, setCarregando] = useState(false);
  const [erro, setErro] = useState(null);

  const carregar = useCallback(async () => {
    if (!aberto || !de || !ate) return;
    setCarregando(true);
    setErro(null);
    try {
      const { data } = await api.get('/crm/agenda/produtividade', {
        params: { de, ate },
      });
      setDados(data);
    } catch (err) {
      setErro(mensagemDeErro(err, 'Não foi possível carregar a produtividade.'));
    } finally {
      setCarregando(false);
    }
  }, [aberto, de, ate]);

  useEffect(() => { carregar(); }, [carregar]);

  /*
    `|| []` não é paranoia: uma resposta truncada — proxy no meio, resposta
    de erro com corpo JSON, uma versão do servidor mais antiga que esta
    tela — deixava o `.length` estourar e o modal inteiro virava branco,
    dentro da Agenda, levando a grade junto. Foi assim na Sprint 4, com
    `itens`. Lista vazia é uma tela honesta; tela branca não é.
  */
  const dias = useMemo(() => dados?.dias || [], [dados]);
  const porSdr = dados?.por_sdr || [];
  const porEv = dados?.por_ev || [];

  return (
    <Modal
      aberto={aberto}
      onFechar={onFechar}
      nivel={nivel}
      size="xl"
      titulo="Produtividade da agenda"
      subtitulo={
        dados
          ? `${diaCurto(dados.de)} a ${diaCurto(dados.ate)}`
          : undefined
      }
    >
      <div className="space-y-5">
        {erro && <AlertMessage tipo="erro">{erro}</AlertMessage>}

        {carregando && !dados && (
          <p className="py-12 text-center text-sm text-hipo-slate">
            Carregando os números…
          </p>
        )}

        {dados && (
          <>
            {/* ── O resumo ── */}
            <div className="flex flex-wrap items-center gap-2">
              <Badge tone="info">
                <CalendarRange size={12} aria-hidden="true" />
                {dados.agendamentos} agendamentos
              </Badge>
              <Badge tone="success">
                {dados.realizadas} realizadas
              </Badge>
              <Badge tone="neutral">
                {dados.canceladas} canceladas
              </Badge>
              <Badge tone="danger">
                <UserX size={12} aria-hidden="true" />
                {dados.no_show} no-show
              </Badge>
              {dados.pendentes > 0 && (
                <Badge tone="warning">
                  {dados.pendentes} sem desfecho
                </Badge>
              )}

              {/*
                As taxas ficam à direita e fora dos contadores: são o
                RESULTADO da semana, não mais um número dela. Ambas saem do
                mesmo denominador — só as reuniões que já têm desfecho —
                para que "realização + no-show + cancelamento" feche em
                100% e ninguém procure o resto.
              */}
              <span className="ml-auto flex items-center gap-3 text-xs">
                <span className="inline-flex items-center gap-1 text-hipo-slate">
                  <TrendingUp size={13} className="text-hipo-success" />
                  realização{' '}
                  <strong className="text-hipo-ink tabular-nums">
                    {taxa(dados.taxa_realizacao)}
                  </strong>
                </span>
                <span className="inline-flex items-center gap-1 text-hipo-slate">
                  no-show{' '}
                  <strong className="text-hipo-ink tabular-nums">
                    {taxa(dados.taxa_no_show)}
                  </strong>
                </span>
              </span>
            </div>

            {dados.pendentes > 0 && (
              <AlertMessage tipo="aviso">
                {dados.pendentes} {dados.pendentes === 1 ? 'reunião' : 'reuniões'}
                {' '}já {dados.pendentes === 1 ? 'passou' : 'passaram'} sem
                ninguém registrar o que aconteceu. Elas ficam de fora das
                taxas até alguém responder — o sistema não inventa desfecho.
              </AlertMessage>
            )}

            {/* ── SDR: quantos marcou por dia ── */}
            <section>
              <h3 className="text-sm font-semibold text-hipo-ink mb-1">
                Agendamentos por SDR
              </h3>
              <p className="text-xs text-hipo-slate mb-2">
                Contados no dia em que a reunião foi MARCADA — é o dia em que
                o trabalho foi feito, não o dia em que ela acontece.
              </p>
              {porSdr.length === 0 ? (
                <Empty title="Nenhum agendamento nesta janela." />
              ) : (
                <Table>
                  <thead>
                    <tr>
                      <Th>Quem marcou</Th>
                      {dias.map((d) => <Th key={d} align="center">{diaCurto(d)}</Th>)}
                      <Th align="right">Total</Th>
                    </tr>
                  </thead>
                  <tbody>
                    {porSdr.map((p) => (
                      <Tr key={p.usuario_id || 'sem-dono'}>
                        <Td>{p.nome || <span className="text-hipo-muted">sem dono</span>}</Td>
                        {p.por_dia.map((d) => (
                          <Td key={d.dia} className="text-center">
                            <Numero valor={d.agendamentos} />
                          </Td>
                        ))}
                        <Td className="text-right font-semibold tabular-nums">
                          {p.total}
                        </Td>
                      </Tr>
                    ))}
                  </tbody>
                </Table>
              )}
            </section>

            {/* ── EV: quantas teve e com que resultado ── */}
            <section>
              <h3 className="text-sm font-semibold text-hipo-ink mb-1">
                Reuniões por EV
              </h3>
              <p className="text-xs text-hipo-slate mb-2">
                Contadas no dia em que a reunião ACONTECEU. O total por dia
                traz o desfecho embaixo — realizadas · canceladas · no-show —
                e o <span className="text-hipo-warning">+N</span> em amarelo
                é o que ainda ninguém respondeu.
              </p>
              {porEv.length === 0 ? (
                <Empty title="Nenhuma reunião nesta janela." />
              ) : (
                <Table>
                  <thead>
                    <tr>
                      <Th>Anfitrião</Th>
                      {dias.map((d) => <Th key={d} align="center">{diaCurto(d)}</Th>)}
                      <Th align="center">Realiz.</Th>
                      <Th align="center">Canc.</Th>
                      <Th align="center">No-show</Th>
                      <Th align="center">Pend.</Th>
                      <Th align="right">Total</Th>
                    </tr>
                  </thead>
                  <tbody>
                    {porEv.map((p) => (
                      <Tr key={p.usuario_id || 'sem-dono'}>
                        <Td>{p.nome || <span className="text-hipo-muted">sem dono</span>}</Td>
                        {p.por_dia.map((d) => (
                          <Td key={d.dia} className="text-center">
                            <Numero valor={d.total} />
                            {/*
                              O detalhe do dia embaixo do total, em miúdo:
                              sem ele, "3 reuniões na terça" não diz se a
                              terça foi boa. Some quando o dia é vazio,
                              para não encher a tabela de "0·0·0".

                              O "+N" em amarelo é o que ainda não foi
                              respondido, e ele PRECISA aparecer aqui: sem
                              ele, um dia com uma reunião só, ainda
                              pendente, mostrava "1" em cima e "0·0·0"
                              embaixo — e quem lê procura a reunião que
                              sumiu numa outra coluna da tabela.
                            */}
                            {d.total > 0 && (
                              <span className="block text-[10px] tabular-nums">
                                <span className="text-hipo-slate">
                                  {d.realizadas}·{d.canceladas}·{d.no_show}
                                </span>
                                {d.pendentes > 0 && (
                                  <span className="text-hipo-warning"> +{d.pendentes}</span>
                                )}
                              </span>
                            )}
                          </Td>
                        ))}
                        <Td className="text-center">
                          <Numero valor={p.realizadas} tom="text-hipo-success" />
                        </Td>
                        <Td className="text-center">
                          <Numero valor={p.canceladas} />
                        </Td>
                        <Td className="text-center">
                          <Numero valor={p.no_show} tom="text-hipo-danger" />
                        </Td>
                        <Td className="text-center">
                          <Numero valor={p.pendentes} tom="text-hipo-warning" />
                        </Td>
                        <Td className="text-right font-semibold tabular-nums">
                          {p.total}
                        </Td>
                      </Tr>
                    ))}
                  </tbody>
                </Table>
              )}
            </section>
          </>
        )}
      </div>
    </Modal>
  );
}
