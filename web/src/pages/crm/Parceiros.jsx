// web/src/pages/crm/Parceiros.jsx
//
// A carteira de parceiros — a tela do EC.
//
// O parceiro é o escritório de contabilidade (ou o contador com CNPJ) que
// indica empresa para a gente. Não é entidade nova no banco: é uma `conta`
// com `eh_finder`. Aqui ela ganha dono, número e próxima ação.
//
// ── Por que esta tela existe ─────────────────────────────────────────
// Indicação é canal de aquisição, e canal sem dono morre. Antes desta tela
// dava para saber quantas oportunidades vieram de um finder, mas não quem
// era responsável por cultivar aquela relação nem há quanto tempo o parceiro
// não lembrava da gente. As duas perguntas viram, aqui, uma coluna cada.
//
// ── O que a tela mede ────────────────────────────────────────────────
// Duas taxas, com denominadores diferentes de propósito:
//
//   CONVERSÃO   — do que ele indicou e CHEGOU AO FIM, quanto virou cliente.
//                 Cancelado fica fora: é erro nosso de CRM, e punir o
//                 parceiro por isso inverteria o sentido do número.
//   CANCELAMENTO— de TUDO que ele indicou, quanto era lead errado. Essa é a
//                 qualidade da indicação, e aí o que está em aberto conta.
//
// A SITUAÇÃO (ativo / esfriando / dormente) olha a última indicação de toda
// a história, mesmo quando o período está recortado. Sem isso, um parceiro de
// três anos apareceria como "sem indicação" toda vez que alguém olhasse os
// últimos 90 dias.
//
// ── Duas leituras opostas na mesma linha ─────────────────────────────
// O FAROL mede o que NÓS fizemos pelo parceiro: quatro semanas de cadência de
// contato, verde quando alguma tarefa foi concluída naquela semana. O
// MINI-FUNIL mede o que ELE nos deu e em que pé está: o estoque aberto das
// indicações dele, por fase.
//
// Estão lado a lado de propósito. Parceiro sem indicação com quatro semanas
// verdes é problema de produto ou de mercado; parceiro sem indicação com
// quatro semanas vermelhas é abandono — e a ação é outra. Nenhuma coluna
// sozinha separa esses dois casos, e é exatamente aí que a carteira costuma
// mentir para quem a olha.
//
// ── Operacional, não relatório ───────────────────────────────────────
// Diretriz pétrea 2. O EC responsável troca no próprio select da linha; a
// passagem em massa mora no botão da barra; e abrir a linha leva ao mesmo
// drilldown da oportunidade. Se a tela só listasse, seria a mesma planilha
// que ela veio substituir.
//
// ── O drilldown é o MESMO da venda ───────────────────────────────────
// Abrir um parceiro e abrir uma oportunidade são o mesmo gesto: clicar numa
// linha para trabalhar aquele registro. Por isso a mesma casca — modal
// `full`, trilho à esquerda com o estado, abas verticais, barra única no
// rodapé — e a MESMA aba de Tarefas, componente e tudo. O que vai divergir
// com o tempo é só o conjunto de abas.

import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import {
  Handshake, UserX, Moon, Trophy, Search, X, ArrowLeftRight, CalendarX,
} from 'lucide-react';

import api from '../../api';
import Table, { Th, Tr, Td } from '../../components/ui/Table';
import Button from '../../components/ui/Button';
import Badge from '../../components/ui/Badge';
import Empty from '../../components/ui/Empty';
import Modal from '../../components/ui/Modal';
import AlertMessage from '../../components/ui/AlertMessage';
import KpiInline from '../../components/ui/KpiInline';
import FarolSemanal from '../../components/ui/FarolSemanal';
import MiniFunil from '../../components/ui/MiniFunil';
import ParceiroDetalhe from '../../components/crm/ParceiroDetalhe';
import TransferirCarteira, { SEM_EC } from '../../components/crm/TransferirCarteira';

const POR_PAGINA = 50;

const PERIODOS = [
  { valor: 'sempre', rotulo: 'Desde sempre' },
  { valor: '90d', rotulo: 'Últimos 90 dias' },
  { valor: 'ano', rotulo: 'Ano corrente' },
];

const SITUACOES = [
  { valor: 'sem_indicacao', rotulo: 'Sem indicação' },
  { valor: 'ativo', rotulo: 'Ativo' },
  { valor: 'esfriando', rotulo: 'Esfriando' },
  { valor: 'dormente', rotulo: 'Dormente' },
];

const TOM_SITUACAO = {
  ativo: 'success',
  esfriando: 'warning',
  dormente: 'danger',
  sem_indicacao: 'neutral',
};

const FILTROS_VAZIOS = {
  q: '', ec_responsavel_id: '', situacao: '', sem_ec: false, sem_contato: false,
};

const CLASSE_CAMPO =
  'h-8 text-xs rounded-lg border border-hipo-border bg-hipo-card text-hipo-ink ' +
  'focus:outline-none focus:ring-2 focus:ring-hipo-blue';

function mensagemDeErro(err, padrao) {
  const d = err?.response?.data?.detail;
  if (typeof d === 'string') return d;
  if (Array.isArray(d) && d[0]?.msg) return d[0].msg;
  if (d?.mensagem) return d.mensagem;
  return padrao;
}

function formatarMoeda(v) {
  if (v === null || v === undefined) return '—';
  return Number(v).toLocaleString('pt-BR', { style: 'currency', currency: 'BRL' });
}

function formatarData(iso) {
  return iso ? new Date(iso).toLocaleDateString('pt-BR') : '—';
}

/**
 * '14/08 09:00' — a data da próxima tarefa cabe na coluna do farol sem
 * empurrar as outras. O ano fica de fora porque a próxima tarefa é sempre
 * perto; se estiver a um ano daqui, o problema não é de formatação.
 */
function dataHoraCurta(iso) {
  if (!iso) return null;
  return new Date(iso).toLocaleString('pt-BR', {
    day: '2-digit', month: '2-digit', hour: '2-digit', minute: '2-digit',
  });
}

/**
 * O prazo já passou?
 *
 * Comparação simples com o relógio, e NÃO a regra de situação de
 * services/tarefa.py (onde 'hoje' é dia de calendário e uma tarefa das 09h
 * segue sendo de hoje às 18h). Aqui a pergunta é outra: a linha só precisa
 * saber se aquela data ainda está à frente para escolher a palavra. A
 * situação de verdade, com a regra completa, vem do servidor e aparece no
 * painel — este é um rótulo de coluna, não uma segunda fonte de verdade.
 */
function vencida(iso) {
  return Boolean(iso) && new Date(iso).getTime() < Date.now();
}

/**
 * Percentual, ou travessão quando não há denominador.
 *
 * `null` e `0` são coisas diferentes: o primeiro é "nada fechou ainda", o
 * segundo é "fechou e não converteu". Mostrar 0% para quem indicou ontem
 * seria cobrar alguém que não deve nada.
 */
function percentual(v) {
  if (v === null || v === undefined) return '—';
  return `${Math.round(v * 100)}%`;
}

// ── Página ───────────────────────────────────────────────────────────

export default function Parceiros() {
  const [resumo, setResumo] = useState(null);
  const [lista, setLista] = useState({ total: 0, itens: [] });
  const [usuarios, setUsuarios] = useState([]);
  const [filtros, setFiltros] = useState(FILTROS_VAZIOS);
  const [busca, setBusca] = useState('');
  const [periodo, setPeriodo] = useState('sempre');
  const [pagina, setPagina] = useState(0);
  const [carregando, setCarregando] = useState(true);
  const [erro, setErro] = useState(null);
  const [kpiAtivo, setKpiAtivo] = useState(null);
  const [selecionado, setSelecionado] = useState(null);
  const [transferindo, setTransferindo] = useState(false);
  const debounce = useRef(null);
  const navigate = useNavigate();

  // Mesma armadilha das outras telas: devolver o MESMO objeto quando nada
  // mudou faz o React abortar o re-render. Sem isso, o timer dispara uma vez
  // na montagem com a busca vazia e a tela recarrega sozinha.
  useEffect(() => {
    clearTimeout(debounce.current);
    debounce.current = setTimeout(() => {
      setFiltros((f) => (f.q === busca ? f : { ...f, q: busca }));
      setPagina((p) => (p === 0 ? p : 0));
    }, 350);
    return () => clearTimeout(debounce.current);
  }, [busca]);

  useEffect(() => {
    api.get('/crm/dominio/usuarios')
      .then(({ data }) => setUsuarios(data.filter(
        (u) => ['EC', 'ADM', 'Franqueado'].includes(u.cargo)
      )))
      .catch(() => setUsuarios([]));
  }, []);

  const params = useMemo(() => {
    const p = { periodo };
    if (filtros.q) p.q = filtros.q;
    if (filtros.situacao) p.situacao = filtros.situacao;
    if (filtros.sem_contato) p.sem_contato = true;
    if (filtros.sem_ec) p.sem_ec = true;
    else if (filtros.ec_responsavel_id) p.ec_responsavel_id = filtros.ec_responsavel_id;
    return p;
  }, [
    periodo, filtros.q, filtros.situacao, filtros.sem_contato,
    filtros.sem_ec, filtros.ec_responsavel_id,
  ]);

  const carregar = useCallback(async () => {
    setCarregando(true);
    setErro(null);
    try {
      const [kpis, dados] = await Promise.all([
        api.get('/crm/parceiros/resumo', { params: { periodo } }),
        api.get('/crm/parceiros', {
          params: { ...params, limit: POR_PAGINA, offset: pagina * POR_PAGINA },
        }),
      ]);
      setResumo(kpis.data);
      setLista(dados.data);
    } catch (err) {
      setErro(mensagemDeErro(err, 'Não foi possível carregar a carteira.'));
    } finally {
      setCarregando(false);
    }
  }, [params, periodo, pagina]);

  useEffect(() => { carregar(); }, [carregar]);

  async function abrir(id) {
    setErro(null);
    try {
      const { data } = await api.get(`/crm/parceiros/${id}`, { params: { periodo } });
      setSelecionado(data);
    } catch (err) {
      setErro(mensagemDeErro(err, 'Não foi possível abrir o parceiro.'));
    }
  }

  async function salvar(parceiro, corpo) {
    setErro(null);
    try {
      const { data } = await api.patch(`/crm/parceiros/${parceiro.id}`, corpo, {
        params: { periodo },
      });
      /*
        Só mexe no painel se ele já estava aberto NESTE parceiro. Sem a
        guarda, trocar o EC pelo select da linha abria o painel do nada —
        a tela pulava embaixo do cursor de quem só queria mudar um select.

        Quando o parceiro é desmarcado, a linha some da carteira e o painel
        sobre ela tem que sumir junto.
      */
      setSelecionado((atual) => {
        if (!atual || atual.id !== data.id) return atual;
        return data.eh_finder ? data : null;
      });
      carregar();
    } catch (err) {
      setErro(mensagemDeErro(err, 'Não foi possível salvar.'));
    }
  }

  function alternarKpi(chave, parciais) {
    const base = { ...FILTROS_VAZIOS, q: filtros.q };
    if (kpiAtivo === chave) {
      setKpiAtivo(null);
      setFiltros(base);
    } else {
      setKpiAtivo(chave);
      setFiltros({ ...base, ...parciais });
    }
    setPagina(0);
  }

  function limpar() {
    setFiltros(FILTROS_VAZIOS);
    setBusca('');
    setKpiAtivo(null);
    setPagina(0);
  }

  const temFiltro =
    JSON.stringify({ ...filtros, q: '' }) !== JSON.stringify({ ...FILTROS_VAZIOS, q: '' })
    || Boolean(filtros.q);

  const dormentes = (resumo?.por_situacao || [])
    .find((s) => s.situacao === 'dormente')?.quantidade ?? 0;

  const totalPaginas = Math.max(1, Math.ceil(lista.total / POR_PAGINA));

  return (
    <div className="h-full min-h-0 flex flex-col gap-2">
      <div className="shrink-0 flex flex-wrap items-center gap-x-2 gap-y-2">
        <h1 className="sr-only">Parceiros — carteira de indicadores</h1>

        <div className="flex items-center gap-2">
          <KpiInline
            label="Parceiros"
            valor={resumo?.parceiros ?? '—'}
            icone={Handshake}
            tom="text-hipo-blue bg-hipo-blueSoft"
          />
          {/*
            Este KPI existe para ser ZERADO. Parceiro sem responsável é
            relação que ninguém está cultivando — e o clique já leva à fila.
          */}
          <KpiInline
            label="Sem EC"
            valor={resumo?.sem_ec ?? '—'}
            titulo="Parceiros sem responsável — clique para ver a fila"
            icone={UserX}
            tom="text-hipo-warning bg-hipo-warningSoft"
            ativo={kpiAtivo === 'sem_ec'}
            onClick={() => alternarKpi('sem_ec', { sem_ec: true })}
          />
          {/*
            O outro KPI que existe para ser zerado — e este, toda sexta.
            Conta só o VERMELHO da semana: nem contato feito nem tarefa
            marcada. Amarelo fica de fora porque já tem alguém com ele, e um
            KPI que cobra quem já agendou vira ruído que se aprende a ignorar.
          */}
          <KpiInline
            label="Sem contato"
            valor={resumo?.sem_contato_semana ?? '—'}
            titulo="Nesta semana: nenhuma tarefa feita nem marcada — clique para ver a fila"
            icone={CalendarX}
            tom="text-hipo-danger bg-hipo-dangerSoft"
            ativo={kpiAtivo === 'sem_contato'}
            onClick={() => alternarKpi('sem_contato', { sem_contato: true })}
          />
          <KpiInline
            label="Dormentes"
            valor={dormentes}
            titulo="Sem indicar há mais de 180 dias"
            icone={Moon}
            tom="text-hipo-warning bg-hipo-warningSoft"
            ativo={kpiAtivo === 'dormentes'}
            onClick={() => alternarKpi('dormentes', { situacao: 'dormente' })}
          />
          <KpiInline
            label="Conversão"
            valor={percentual(resumo?.taxa_conversao)}
            detalhe={resumo ? `${resumo.convertidas}/${resumo.indicacoes}` : null}
            titulo="Das indicações que chegaram ao fim. Cancelado fica fora."
            icone={Trophy}
            tom="text-hipo-success bg-hipo-successSoft"
          />
        </div>

        <div className="ml-auto flex flex-wrap items-center gap-2">
          <div className="relative">
            <Search
              size={14}
              className="absolute left-2.5 top-1/2 -translate-y-1/2 text-hipo-muted pointer-events-none"
              aria-hidden="true"
            />
            <input
              aria-label="Buscar"
              placeholder="Empresa ou CNPJ"
              value={busca}
              onChange={(e) => setBusca(e.target.value)}
              className={`${CLASSE_CAMPO} w-40 pl-7 pr-2 placeholder:text-hipo-muted`}
            />
          </div>

          <select
            aria-label="EC responsável"
            value={filtros.sem_ec ? '' : filtros.ec_responsavel_id}
            onChange={(e) => {
              setFiltros((f) => ({ ...f, ec_responsavel_id: e.target.value, sem_ec: false }));
              setKpiAtivo(null);
              setPagina(0);
            }}
            className={`${CLASSE_CAMPO} px-1 w-28`}
          >
            <option value="">Todo EC</option>
            {usuarios.map((u) => <option key={u.id} value={u.id}>{u.nome}</option>)}
          </select>

          <select
            aria-label="Situação"
            value={filtros.situacao}
            onChange={(e) => {
              setFiltros((f) => ({ ...f, situacao: e.target.value }));
              setKpiAtivo(null);
              setPagina(0);
            }}
            className={`${CLASSE_CAMPO} px-1.5`}
          >
            <option value="">Toda situação</option>
            {SITUACOES.map((s) => <option key={s.valor} value={s.valor}>{s.rotulo}</option>)}
          </select>

          <select
            aria-label="Período"
            value={periodo}
            onChange={(e) => { setPeriodo(e.target.value); setPagina(0); }}
            className={`${CLASSE_CAMPO} px-1.5`}
          >
            {PERIODOS.map((p) => <option key={p.valor} value={p.valor}>{p.rotulo}</option>)}
          </select>

          {temFiltro && (
            <button
              type="button"
              onClick={limpar}
              aria-label="Limpar filtros"
              title="Limpar filtros"
              className="h-8 w-8 inline-flex items-center justify-center rounded-lg border border-hipo-border text-hipo-slate hover:bg-hipo-bg transition-colors"
            >
              <X size={14} />
            </button>
          )}

          <Button size="sm" icon={ArrowLeftRight} onClick={() => setTransferindo(true)}>
            Transferir carteira
          </Button>
        </div>
      </div>

      {erro && (
        <div className="shrink-0"><AlertMessage tipo="erro">{erro}</AlertMessage></div>
      )}

      <div className="flex-1 min-h-0 flex gap-2">
        <div className="flex-1 min-w-0 h-full min-h-0 flex flex-col rounded-xl border border-hipo-border bg-hipo-card">
          <div className="shrink-0 flex items-baseline justify-between gap-2 px-3 py-1.5 border-b border-hipo-border">
            <h2 className="text-xs font-semibold text-hipo-ink">
              {lista.total} parceiro{lista.total === 1 ? '' : 's'}
            </h2>
            {temFiltro && <span className="text-[11px] text-hipo-slate">resultado filtrado</span>}
          </div>

          <div className="flex-1 min-h-0 p-3">
            {carregando ? (
              <p className="py-10 text-center text-sm text-hipo-slate">Carregando…</p>
            ) : lista.itens.length === 0 ? (
              <Empty
                title={temFiltro ? 'Nenhum parceiro com esses filtros' : 'Nenhum parceiro ainda'}
                description={
                  temFiltro
                    ? 'Ajuste os filtros.'
                    : 'Uma conta vira parceiro ao ser usada como indicadora de uma oportunidade — ou marcada à mão na tela de Contas.'
                }
                icon={Handshake}
                action={
                  temFiltro
                    ? <Button variant="secondary" onClick={limpar}>Limpar filtros</Button>
                    : undefined
                }
              />
            ) : (
              <div className="h-full min-h-0 flex flex-col">
                <div className="flex-1 min-h-0 overflow-auto border border-hipo-border rounded-lg">
                  <Table>
                    <thead>
                      <tr>
                        <Th>Parceiro</Th>
                        <Th>EC responsável</Th>
                        {/* O que nós fizemos por ele. */}
                        <Th>Contato</Th>
                        {/* O que ele nos deu, e em que pé está. */}
                        <Th>Em aberto</Th>
                        <Th>Situação</Th>
                        <Th align="right">Indicações</Th>
                        <Th align="right">Conversão</Th>
                        <Th align="right">Ticket ganho</Th>
                        <Th>Última</Th>
                      </tr>
                    </thead>
                    <tbody>
                      {lista.itens.map((p) => (
                        <Tr key={p.id} onClick={() => abrir(p.id)}>
                          <Td>
                            <span className="font-medium text-hipo-ink">{p.razao_social}</span>
                            <span className="block text-xs font-mono text-hipo-slate">
                              {p.cnpj_formatado}
                            </span>
                          </Td>
                          <Td>
                            {/*
                              Trocar o dono é a ação mais frequente desta
                              tela. Exigir abrir o painel para isso somaria
                              dois cliques a cada troca — e o stopPropagation
                              é o que impede o select de abrir o painel junto.
                            */}
                            <select
                              aria-label={`EC responsável por ${p.razao_social}`}
                              value={p.ec_responsavel_id || ''}
                              onClick={(e) => e.stopPropagation()}
                              onChange={(e) => {
                                e.stopPropagation();
                                salvar(p, { ec_responsavel_id: e.target.value || null });
                              }}
                              className={`${CLASSE_CAMPO} px-1 w-32`}
                            >
                              <option value="">Sem responsável</option>
                              {usuarios.map((u) => (
                                <option key={u.id} value={u.id}>{u.nome}</option>
                              ))}
                            </select>
                          </Td>
                          <Td>
                            {/*
                              Clicar no farol abre o painel — que é onde
                              estão as tarefas. O stopPropagation existe
                              porque a linha inteira já abre o painel: sem
                              ele o clique dispararia os dois handlers.
                            */}
                            <span onClick={(e) => e.stopPropagation()}>
                              <FarolSemanal
                                semanas={p.farol}
                                semanasSemContato={p.semanas_sem_contato}
                                onClick={() => abrir(p.id)}
                              />
                            </span>
                            {/*
                              Tarefa em aberto com prazo vencido NÃO é "a
                              próxima": chamá-la assim faria a linha dizer
                              "próxima 22/07" num dia 13/08 — a tela
                              anunciando futuro para uma dívida. Atrasada tem
                              palavra e cor próprias.
                            */}
                            {p.proxima_tarefa_em ? (
                              vencida(p.proxima_tarefa_em) ? (
                                <span className="block text-[10px] text-hipo-danger mt-0.5">
                                  atrasada {dataHoraCurta(p.proxima_tarefa_em)}
                                </span>
                              ) : (
                                <span className="block text-[10px] text-hipo-slate mt-0.5">
                                  próxima {dataHoraCurta(p.proxima_tarefa_em)}
                                </span>
                              )
                            ) : (
                              <span className="block text-[10px] text-hipo-muted mt-0.5">
                                nada agendado
                              </span>
                            )}
                          </Td>
                          <Td>
                            <MiniFunil dados={p.funil} />
                          </Td>
                          <Td>
                            <Badge tone={TOM_SITUACAO[p.situacao] || 'neutral'}>
                              {p.situacao_rotulo}
                            </Badge>
                          </Td>
                          <Td align="right">
                            {p.indicacoes}
                            {p.em_aberto > 0 && (
                              <span className="block text-[11px] text-hipo-slate">
                                {p.em_aberto} em aberto
                              </span>
                            )}
                          </Td>
                          <Td align="right">
                            {percentual(p.taxa_conversao)}
                            {p.canceladas > 0 && (
                              <span className="block text-[11px] text-hipo-danger">
                                {p.canceladas} cancelada{p.canceladas === 1 ? '' : 's'}
                              </span>
                            )}
                          </Td>
                          <Td align="right">{formatarMoeda(p.ticket_convertido)}</Td>
                          <Td>{formatarData(p.ultima_indicacao_em)}</Td>
                        </Tr>
                      ))}
                    </tbody>
                  </Table>
                </div>

                {totalPaginas > 1 && (
                  <div className="shrink-0 flex items-center justify-between pt-2">
                    <span className="text-xs text-hipo-slate">
                      Página {pagina + 1} de {totalPaginas}
                    </span>
                    <div className="flex gap-2">
                      <Button
                        size="sm" variant="secondary" disabled={pagina === 0}
                        onClick={() => setPagina((p) => p - 1)}
                      >
                        Anterior
                      </Button>
                      <Button
                        size="sm" variant="secondary" disabled={pagina + 1 >= totalPaginas}
                        onClick={() => setPagina((p) => p + 1)}
                      >
                        Próxima
                      </Button>
                    </div>
                  </div>
                )}
              </div>
            )}
          </div>
        </div>

      </div>

      {/*
        Modal `full` e sem padding no corpo, exatamente como a oportunidade:
        quem monta a barra do rodapé é o próprio ParceiroDetalhe, porque a
        ação de saída (Remover da carteira) precisa ficar na mesma linha de
        Fechar.

        O subtítulo é o CNPJ — o que identifica a empresa sem ambiguidade
        quando duas se chamam parecido.
      */}
      <Modal
        aberto={Boolean(selecionado)}
        onFechar={() => setSelecionado(null)}
        titulo={selecionado ? selecionado.razao_social : undefined}
        subtitulo={selecionado ? (
          <span className="font-mono text-xs">{selecionado.cnpj_formatado}</span>
        ) : undefined}
        size="full"
        bodySemPadding
      >
        {selecionado && (
          <ParceiroDetalhe
            parceiro={selecionado}
            usuarios={usuarios}
            periodo={periodo}
            onFechar={() => setSelecionado(null)}
            onAbrirNoFunil={(numero) => navigate(`/crm/oportunidades?q=${numero}`)}
            /*
              Toda ação do detalhe devolve o registro atualizado. Se ele
              deixou de ser parceiro, a linha saiu da carteira e o modal
              sobre ela tem que fechar junto.
            */
            onSalvo={(dado) => {
              setSelecionado(dado.eh_finder ? dado : null);
              carregar();
            }}
            /*
              Concluir ou agendar muda o farol e a contagem de abertas da
              LINHA. Sem este recarregamento, o quadradinho da semana
              continuaria vermelho depois de a tarefa ser concluída — e a
              tela estaria mentindo sobre o que o usuário acabou de fazer.
            */
            onRecarregar={() => { carregar(); abrir(selecionado.id); }}
          />
        )}
      </Modal>

      <TransferirCarteira
        aberto={transferindo}
        usuarios={usuarios}
        carteiras={resumo}
        onFechar={() => setTransferindo(false)}
        onConcluido={() => { setTransferindo(false); setSelecionado(null); carregar(); }}
      />
    </div>
  );
}

export { SEM_EC };
