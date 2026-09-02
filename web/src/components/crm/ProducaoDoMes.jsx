// web/src/components/crm/ProducaoDoMes.jsx
//
// "Quantas reuniões tivemos em agosto?"
//
// A informação existia desde a Sprint 5 — toda tarefa tem tipo, prazo e
// concluída_em — mas só era alcançável tarefa a tarefa, dentro do drilldown
// de cada oportunidade. Dado que só existe no detalhe não é dado de gestão.
//
// ── Por que três colunas e não uma ───────────────────────────────────
// Realizadas, agendadas e canceladas usam DATAS DIFERENTES de propósito:
// quando foi feita, quando estava marcada, quando foi desmarcada. Uma
// reunião marcada para 28/08 e feita em 02/09 é de agosto na agenda e de
// setembro na produção. Somar as três daria um número sem significado; o que
// interessa é a distância entre as duas primeiras.
//
// ── Por que um modal e não uma faixa na tela ─────────────────────────
// A tela de Tarefas é um kanban de quatro colunas, e a regra de layout das
// telas operacionais é que tudo que não é o conteúdo cabe em ~25% da altura.
// Uma segunda linha de KPIs empurraria as colunas para baixo da dobra. O
// número do mês fica numa pílula de 40px na barra que já existe, e o detalhe
// abre por cima quando alguém pergunta.
//
// ── O drilldown é a razão do componente existir ──────────────────────
// Clicar em "12 reuniões" abre exatamente aquelas doze. É a diretriz do
// dashboard operacional: o número leva ao item, não termina em si mesmo. O
// recorte é o MESMO dos dois lados (services/tarefa.py:janela_utc), então a
// lista não pode divergir da contagem.
//
// Sem ações na lista: tarefa concluída é histórico imutável.

import { useCallback, useEffect, useMemo, useState } from 'react';
import { ChevronLeft, ChevronRight, CircleDot, Inbox } from 'lucide-react';

import api from '../../api';
import Modal from '../ui/Modal';
import Badge from '../ui/Badge';
import AlertMessage from '../ui/AlertMessage';
import Table, { Th, Tr, Td } from '../ui/Table';
import { ICONE_TIPO, dataCompleta, mensagemDeErro } from './tarefaComum';

const MESES = [
  'janeiro', 'fevereiro', 'março', 'abril', 'maio', 'junho',
  'julho', 'agosto', 'setembro', 'outubro', 'novembro', 'dezembro',
];

const MESES_CURTOS = [
  'jan', 'fev', 'mar', 'abr', 'mai', 'jun',
  'jul', 'ago', 'set', 'out', 'nov', 'dez',
];

/*
  Datas montadas campo a campo, nunca por toISOString(). O ISO converte para
  UTC antes de formatar: 01/08 00:00 em Brasília vira "2026-07-31" e o mês
  inteiro sai deslocado em um dia. O backend já faz a conversão de fuso — o
  que ele espera aqui é o dia de calendário, cru.
*/
function diaIso(d) {
  const mes = String(d.getMonth() + 1).padStart(2, '0');
  const dia = String(d.getDate()).padStart(2, '0');
  return `${d.getFullYear()}-${mes}-${dia}`;
}

// Dia 0 do mês seguinte é o último dia deste — e acerta fevereiro bissexto
// sem tabela de dias.
export function limitesDoMes(ano, mes) {
  return {
    de: diaIso(new Date(ano, mes, 1)),
    ate: diaIso(new Date(ano, mes + 1, 0)),
  };
}

export function rotuloDoMes(ano, mes) {
  return `${MESES[mes]} de ${ano}`;
}

export function rotuloCurto(ano, mes) {
  const agora = new Date();
  const esteAno = ano === agora.getFullYear();
  return esteAno ? MESES_CURTOS[mes] : `${MESES_CURTOS[mes]}/${String(ano).slice(2)}`;
}

// ── Uma linha de tipo ────────────────────────────────────────────────

function LinhaTipo({ linha, aberta, onAbrir }) {
  const Icone = ICONE_TIPO[linha.tipo] || CircleDot;
  const vazia = linha.realizadas === 0;

  return (
    <Tr
      onClick={vazia ? undefined : () => onAbrir(linha)}
      aria-expanded={vazia ? undefined : aberta}
      className={aberta ? 'bg-hipo-blueSoft' : ''}
    >
      <Td>
        <span className="flex items-center gap-2">
          <Icone
            size={14}
            className={vazia ? 'text-hipo-muted' : 'text-hipo-blue'}
            aria-hidden="true"
          />
          <span className={vazia ? 'text-hipo-muted' : ''}>{linha.rotulo}</span>
        </span>
      </Td>
      <Td align="right" className="tabular-nums font-semibold">
        {/*
          Zero em cinza, não em preto. A linha existe para dizer que ninguém
          fez nenhuma visita em agosto — e isso é informação —, mas ela não
          pode competir visualmente com os números que têm conteúdo.
        */}
        <span className={vazia ? 'text-hipo-muted font-normal' : 'text-hipo-ink'}>
          {linha.realizadas}
        </span>
      </Td>
      <Td align="right" className="tabular-nums text-hipo-slate">{linha.agendadas}</Td>
      <Td align="right" className="tabular-nums text-hipo-slate">{linha.canceladas}</Td>
    </Tr>
  );
}

// ── O modal ──────────────────────────────────────────────────────────

export default function ProducaoDoMes({ aberto, onFechar, filtros = {} }) {
  const hoje = useMemo(() => new Date(), []);
  const [ano, setAno] = useState(hoje.getFullYear());
  const [mes, setMes] = useState(hoje.getMonth());

  const [resumo, setResumo] = useState(null);
  const [carregando, setCarregando] = useState(false);
  const [erro, setErro] = useState(null);

  const [tipoAberto, setTipoAberto] = useState(null);
  const [itens, setItens] = useState([]);
  const [carregandoItens, setCarregandoItens] = useState(false);

  const { responsavel_id: responsavelId, q } = filtros;

  const periodo = useMemo(() => limitesDoMes(ano, mes), [ano, mes]);

  const params = useMemo(() => {
    const p = { ...periodo };
    if (responsavelId) p.responsavel_id = responsavelId;
    if (q) p.q = q;
    return p;
  }, [periodo, responsavelId, q]);

  useEffect(() => {
    if (!aberto) return undefined;
    let vivo = true;
    setCarregando(true);
    setErro(null);
    api.get('/crm/tarefas/resumo', { params })
      .then(({ data }) => { if (vivo) setResumo(data); })
      .catch((err) => {
        if (vivo) setErro(mensagemDeErro(err, 'Não foi possível carregar a produção do mês.'));
      })
      .finally(() => { if (vivo) setCarregando(false); });
    return () => { vivo = false; };
  }, [aberto, params]);

  // Trocar de mês fecha o drilldown: a lista aberta é de um mês que não está
  // mais na tela, e uma lista que sobrevive ao filtro que a gerou é a forma
  // mais barata de mostrar dado errado com cara de certo.
  useEffect(() => { setTipoAberto(null); setItens([]); }, [params]);

  const abrirTipo = useCallback(async (linha) => {
    if (tipoAberto === linha.tipo) {
      setTipoAberto(null);
      setItens([]);
      return;
    }
    setTipoAberto(linha.tipo);
    setItens([]);
    setCarregandoItens(true);
    try {
      const { data } = await api.get('/crm/tarefas', {
        params: {
          ...params,
          tipo: linha.tipo,
          // 'conclusao' é o que faz esta lista ser as MESMAS tarefas que a
          // coluna Realizadas contou. Com o default ('prazo') viriam as
          // marcadas para o mês, que é outro conjunto.
          base: 'conclusao',
          situacao: ['concluida'],
          ordenar: 'cronologico',
        },
      });
      setItens(data.itens || []);
    } catch (err) {
      setErro(mensagemDeErro(err, 'Não foi possível abrir a lista.'));
    } finally {
      setCarregandoItens(false);
    }
  }, [params, tipoAberto]);

  const andar = (passo) => {
    const d = new Date(ano, mes + passo, 1);
    setAno(d.getFullYear());
    setMes(d.getMonth());
  };

  // Não deixa navegar para o futuro: mês que ainda não aconteceu só pode
  // devolver zero, e zero sem causa parece defeito.
  const noMesCorrente = ano === hoje.getFullYear() && mes === hoje.getMonth();

  const temFiltro = Boolean(responsavelId || q);
  const linhaTipoAberta = resumo?.por_tipo?.find((t) => t.tipo === tipoAberto);

  return (
    <Modal
      aberto={aberto}
      onFechar={onFechar}
      titulo="Produção do mês"
      subtitulo={
        temFiltro
          ? 'Com os filtros da tela aplicados.'
          : 'Tarefas realizadas, agendadas e canceladas no período.'
      }
      size="lg"
    >
      <div className="space-y-4">

        {/* ── Navegação de mês ── */}
        <div className="flex items-center justify-center gap-2">
          <button
            type="button"
            onClick={() => andar(-1)}
            aria-label="Mês anterior"
            className="h-8 w-8 inline-flex items-center justify-center rounded-lg border border-hipo-border text-hipo-slate hover:bg-hipo-bg transition-colors"
          >
            <ChevronLeft size={16} />
          </button>
          <span className="min-w-[10rem] text-center text-sm font-semibold text-hipo-ink">
            {rotuloDoMes(ano, mes)}
          </span>
          <button
            type="button"
            onClick={() => andar(1)}
            disabled={noMesCorrente}
            aria-label="Mês seguinte"
            className="h-8 w-8 inline-flex items-center justify-center rounded-lg border border-hipo-border text-hipo-slate hover:bg-hipo-bg transition-colors disabled:opacity-40 disabled:cursor-not-allowed"
          >
            <ChevronRight size={16} />
          </button>
        </div>

        {erro && <AlertMessage tipo="erro">{erro}</AlertMessage>}

        {carregando && !resumo ? (
          <p className="py-10 text-center text-sm text-hipo-slate">Carregando…</p>
        ) : resumo && (
          <>
            {/* ── Os três números ── */}
            <div className="grid grid-cols-3 gap-2">
              {[
                { rotulo: 'Realizadas', valor: resumo.realizadas, forte: true,
                  dica: 'Concluídas dentro do mês.' },
                { rotulo: 'Agendadas', valor: resumo.agendadas, forte: false,
                  dica: 'Com prazo dentro do mês, feitas ou não.' },
                { rotulo: 'Canceladas', valor: resumo.canceladas, forte: false,
                  dica: 'Desmarcadas dentro do mês.' },
              ].map((n) => (
                <div
                  key={n.rotulo}
                  title={n.dica}
                  className="rounded-lg border border-hipo-border bg-hipo-bg/40 px-3 py-2"
                >
                  <p className="text-[10px] uppercase tracking-wide text-hipo-slate">
                    {n.rotulo}
                  </p>
                  <p className={
                    'tabular-nums leading-tight ' +
                    (n.forte
                      ? 'text-2xl font-semibold text-hipo-ink'
                      : 'text-2xl font-normal text-hipo-slate')
                  }>
                    {n.valor}
                  </p>
                </div>
              ))}
            </div>

            {/* ── Por tipo ── */}
            <div>
              <h3 className="text-xs font-semibold text-hipo-slate uppercase tracking-wide mb-1.5">
                Por tipo
              </h3>
              <Table>
                <thead>
                  <tr>
                    <Th>Tipo</Th>
                    <Th align="right">Realizadas</Th>
                    <Th align="right">Agendadas</Th>
                    <Th align="right">Canceladas</Th>
                  </tr>
                </thead>
                <tbody>
                  {resumo.por_tipo.map((linha) => (
                    <LinhaTipo
                      key={linha.tipo}
                      linha={linha}
                      aberta={tipoAberto === linha.tipo}
                      onAbrir={abrirTipo}
                    />
                  ))}
                </tbody>
              </Table>
              <p className="mt-1.5 text-[11px] text-hipo-muted">
                Clique num tipo para ver as tarefas realizadas.
              </p>
            </div>

            {/* ── Drilldown ── */}
            {tipoAberto && (
              <section
                aria-label={`Realizadas — ${linhaTipoAberta?.rotulo || tipoAberto}`}
                className="rounded-lg border border-hipo-border bg-hipo-bg/40 p-3"
              >
                <h3 className="text-xs font-semibold text-hipo-ink mb-2">
                  {linhaTipoAberta?.rotulo} — realizadas em {rotuloDoMes(ano, mes)}
                  <Badge tone="success" className="ml-2">{itens.length}</Badge>
                </h3>
                {carregandoItens ? (
                  <p className="py-4 text-center text-xs text-hipo-slate">Carregando…</p>
                ) : itens.length === 0 ? (
                  <p className="py-4 text-center text-xs text-hipo-muted">
                    Nada para mostrar.
                  </p>
                ) : (
                  <ul className="space-y-1.5 max-h-56 overflow-y-auto pr-0.5">
                    {itens.map((t) => (
                      <li
                        key={t.id}
                        className="rounded-md border border-hipo-border bg-hipo-card px-2.5 py-2"
                      >
                        <p className="text-sm text-hipo-ink">{t.titulo}</p>
                        <p className="text-xs text-hipo-slate truncate">
                          {t.conta_razao_social}
                        </p>
                        <p className="text-[11px] text-hipo-muted flex items-center gap-2">
                          <span>{dataCompleta(t.concluida_em || t.prazo)}</span>
                          {t.responsavel_nome && (
                            <span className="ml-auto truncate">{t.responsavel_nome}</span>
                          )}
                        </p>
                      </li>
                    ))}
                  </ul>
                )}
              </section>
            )}

            {/* ── Por responsável ── */}
            <div>
              <h3 className="text-xs font-semibold text-hipo-slate uppercase tracking-wide mb-1.5">
                Por responsável
              </h3>
              {resumo.por_responsavel.length === 0 ? (
                <p className="flex items-center gap-2 py-3 text-xs text-hipo-muted">
                  <Inbox size={14} aria-hidden="true" />
                  Ninguém registrou tarefa neste período.
                </p>
              ) : (
                <Table>
                  <thead>
                    <tr>
                      <Th>Responsável</Th>
                      <Th align="right">Realizadas</Th>
                      <Th align="right">Agendadas</Th>
                    </tr>
                  </thead>
                  <tbody>
                    {resumo.por_responsavel.map((p) => (
                      <Tr key={p.usuario_id}>
                        <Td>{p.nome || '—'}</Td>
                        <Td align="right" className="tabular-nums font-semibold">
                          {p.realizadas}
                        </Td>
                        <Td align="right" className="tabular-nums text-hipo-slate">
                          {p.agendadas}
                        </Td>
                      </Tr>
                    ))}
                  </tbody>
                </Table>
              )}
            </div>
          </>
        )}
      </div>
    </Modal>
  );
}
