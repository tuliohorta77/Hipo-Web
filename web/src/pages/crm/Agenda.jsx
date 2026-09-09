// web/src/pages/crm/Agenda.jsx
//
// A semana do Executivo de Vendas: cinco colunas de dia, dezoito linhas de
// slot, e o que está marcado em cada uma.
//
// ── Por que grade e não lista ────────────────────────────────────────
// A pergunta desta tela é "onde cabe a próxima reunião", e ela se responde
// olhando o VAZIO. Uma lista de compromissos mostra o que existe; a grade
// mostra o que falta — e é o buraco entre duas reuniões que decide se o
// SDR pode oferecer quinta às 10h para o cliente que está no telefone
// agora. Foi por isso que a operação desenhou a planilha assim antes de
// existir tela nenhuma.
//
// ── Clicar no vazio é a ação principal ───────────────────────────────
// Toda célula livre é um botão. Não existe "Nova reunião" no topo pedindo
// dia e hora num formulário: o gesto natural é apontar o buraco, e o
// formulário abre com a data e a hora já preenchidas. É a diretriz do
// dashboard operacional aplicada ao caso mais literal possível — o número
// (o slot livre) É a ação.
//
// ── Fora da grade não some ───────────────────────────────────────────
// O horário específico que o SDR pode digitar (09:15) é desenhado na linha
// do slot que o contém, com a hora real no cartão. O que cai no almoço ou
// depois das 18h vai para uma faixa acima da grade. Reunião invisível é
// pior que reunião fora do lugar: quem não a vê, marca por cima.
//
// ── Os números do topo saem da MESMA resposta ────────────────────────
// Marcadas, livres e "sem convite" vêm do mesmo GET da grade, não de um
// endpoint de agregado separado que poderia discordar da lista logo
// abaixo. Mesma regra que o resumo de tarefas e o funil já seguem.

import { useCallback, useEffect, useMemo, useState } from 'react';
import {
  ChevronLeft, ChevronRight, CalendarDays, CalendarCheck, CalendarClock,
  AlertTriangle, Plus, Video, MapPin, CircleDot,
} from 'lucide-react';

import api, { getUser } from '../../api';
import Badge from '../../components/ui/Badge';
import Button from '../../components/ui/Button';
import AlertMessage from '../../components/ui/AlertMessage';
import KpiInline from '../../components/ui/KpiInline';
import ModalReuniao from '../../components/crm/ModalReuniao';
import {
  ICONE_MODALIDADE, campoLocalDoSlot, diaCurto, faixaDaSemana,
  hojeIso, horaCurta, mensagemDeErro, somarSemanas,
} from '../../components/crm/agendaComum';

const CLASSE_CAMPO =
  'h-8 text-xs rounded-lg border border-hipo-border bg-hipo-card text-hipo-ink ' +
  'focus:outline-none focus:ring-2 focus:ring-hipo-blue';

// A mesma paleta de situação de `tarefaComum`, reduzida ao que o cartão da
// agenda usa. Não importada de lá porque aqui o cartão é colorido por
// FUNDO (a grade é densa e a borda esquerda some entre as linhas), e a
// versão da linha do tempo é colorida por texto.
const TOM = {
  atrasada: 'bg-hipo-dangerSoft border-hipo-dangerBorder text-hipo-danger',
  hoje: 'bg-hipo-warningSoft border-hipo-warningBorder text-hipo-ink',
  futura: 'bg-hipo-blueSoft border-hipo-blue text-hipo-ink',
  concluida: 'bg-hipo-successSoft border-hipo-successBorder text-hipo-slate',
  cancelada: 'bg-hipo-bg border-hipo-border text-hipo-muted line-through',
};

// ── Cartão de uma reunião ────────────────────────────────────────────

function Cartao({ reuniao, onAbrir }) {
  const Icone = ICONE_MODALIDADE[reuniao.modalidade] || CircleDot;
  const semConvite = !reuniao.google_event_id && reuniao.cancelada_em === null;

  return (
    <button
      type="button"
      onClick={() => onAbrir(reuniao)}
      title={reuniao.rotulo}
      className={
        'w-full text-left px-1.5 py-1 rounded border text-[11px] leading-tight ' +
        'hover:shadow-md transition-shadow ' +
        'focus:outline-none focus-visible:ring-2 focus-visible:ring-hipo-blue ' +
        (TOM[reuniao.situacao] || TOM.futura)
      }
    >
      <span className="flex items-center gap-1">
        <Icone size={10} className="shrink-0" aria-hidden="true" />
        {/*
          A hora só aparece quando NÃO bate com a linha. Repeti-la em toda
          célula gastaria metade da largura do cartão dizendo o que a
          coluna da esquerda já diz.
        */}
        {reuniao.fora_da_grade && (
          <span className="shrink-0 font-semibold tabular-nums">
            {horaCurta(reuniao.inicio)}
          </span>
        )}
        <span className="truncate font-medium">{reuniao.rotulo}</span>
        {semConvite && (
          <AlertTriangle
            size={10}
            className="ml-auto shrink-0 text-hipo-warning"
            aria-label="convite não enviado"
          />
        )}
      </span>
    </button>
  );
}

// ── Célula ───────────────────────────────────────────────────────────

function Celula({ dia, slot, reunioes, onAbrir, onMarcar, desabilitado }) {
  if (reunioes.length > 0) {
    return (
      <div className="p-0.5 space-y-0.5 min-h-[2.25rem] border-b border-r border-hipo-border">
        {reunioes.map((r) => (
          <Cartao key={r.id} reuniao={r} onAbrir={onAbrir} />
        ))}
      </div>
    );
  }
  return (
    <button
      type="button"
      disabled={desabilitado}
      onClick={() => onMarcar(dia, slot)}
      aria-label={`Marcar reunião em ${diaCurto(dia)} às ${slot}`}
      className={
        'group min-h-[2.25rem] border-b border-r border-hipo-border ' +
        'flex items-center justify-center transition-colors ' +
        'focus:outline-none focus-visible:ring-2 focus-visible:ring-inset ' +
        'focus-visible:ring-hipo-blue ' +
        (desabilitado
          ? 'bg-hipo-bg/60 cursor-default'
          : 'hover:bg-hipo-blueSoft cursor-pointer')
      }
    >
      {!desabilitado && (
        <Plus
          size={12}
          className="text-hipo-muted opacity-0 group-hover:opacity-100 transition-opacity"
          aria-hidden="true"
        />
      )}
    </button>
  );
}

// ── Tela ─────────────────────────────────────────────────────────────

export default function Agenda() {
  /*
    Abre na agenda de QUEM ENTROU, como a tela de Tarefas.

    Aberta em "todos", a grade da equipe inteira empilha cinco reuniões no
    mesmo slot e nenhum buraco é confiável — a tela deixaria de responder
    "onde cabe a próxima". Ver a agenda dos outros continua a um clique no
    mesmo seletor, e é assim que o SDR marca para o EV.
  */
  const usuarioLogado = useMemo(() => getUser(), []);
  const padraoAnfitriao = usuarioLogado?.id ? String(usuarioLogado.id) : '';

  const [semana, setSemana] = useState(null);
  const [inicio, setInicio] = useState(hojeIso);
  const [anfitriao, setAnfitriao] = useState(padraoAnfitriao);
  const [usuarios, setUsuarios] = useState([]);
  const [carregando, setCarregando] = useState(true);
  const [erro, setErro] = useState(null);

  // O modal serve criar e editar. `novo` guarda o slot clicado; `aberta`, a
  // reunião clicada. Nunca os dois ao mesmo tempo.
  const [aberta, setAberta] = useState(null);
  const [novo, setNovo] = useState(null);

  const params = useMemo(() => {
    const p = { inicio };
    if (anfitriao) p.anfitriao_id = anfitriao;
    return p;
  }, [inicio, anfitriao]);

  const carregar = useCallback(async () => {
    setCarregando(true);
    setErro(null);
    try {
      const { data } = await api.get('/crm/agenda/semana', { params });
      setSemana(data);
    } catch (err) {
      setErro(mensagemDeErro(err, 'Não foi possível carregar a agenda.'));
    } finally {
      setCarregando(false);
    }
  }, [params]);

  useEffect(() => { carregar(); }, [carregar]);

  useEffect(() => {
    api.get('/crm/dominio/usuarios')
      .then(({ data }) => setUsuarios(data))
      .catch(() => setUsuarios([]));
  }, []);

  /*
    O usuário logado é garantido na lista mesmo que a chamada de domínio
    falhe. Sem isso o filtro estaria aplicado com o seletor mostrando a
    opção errada — a tela mentiria sobre o próprio recorte. Mesmo cuidado
    da tela de Tarefas.
  */
  const opcoesAnfitriao = useMemo(() => {
    const lista = usuarios.map((u) => ({
      id: String(u.id),
      nome: String(u.id) === padraoAnfitriao ? `${u.nome} (você)` : u.nome,
    }));
    if (padraoAnfitriao && !lista.some((u) => u.id === padraoAnfitriao)) {
      lista.unshift({
        id: padraoAnfitriao,
        nome: `${usuarioLogado?.nome || 'Você'} (você)`,
      });
    }
    return lista;
  }, [usuarios, padraoAnfitriao, usuarioLogado]);

  /*
    Índice (dia, slot) -> reuniões, montado uma vez por carga.

    Procurar linearmente dentro de cada uma das 90 células faria 90 varridas
    da lista a cada render — e a grade re-renderiza a cada hover de célula.
  */
  const porSlot = useMemo(() => {
    const mapa = new Map();
    const foraDaGrade = [];
    for (const dia of semana?.dias || []) {
      for (const r of dia.reunioes) {
        if (!r.slot) { foraDaGrade.push({ ...r, dia: dia.data }); continue; }
        const chave = `${dia.data}|${r.slot}`;
        if (!mapa.has(chave)) mapa.set(chave, []);
        mapa.get(chave).push(r);
      }
    }
    return { mapa, foraDaGrade };
  }, [semana]);

  const fechar = useCallback(() => { setAberta(null); setNovo(null); }, []);
  const aoSalvar = useCallback(() => { carregar(); }, [carregar]);

  function marcar(dia, slot) {
    setAberta(null);
    setNovo({ inicio: campoLocalDoSlot(dia, slot) });
  }

  const dias = semana?.dias || [];
  const slots = semana?.slots || [];

  return (
    <div className="h-full min-h-0 flex flex-col gap-2">

      {/* ── Barra única: navegação, contadores, filtro ── */}
      <div className="shrink-0 flex flex-wrap items-center gap-x-2 gap-y-2">
        <h1 className="sr-only">Agenda de reuniões</h1>

        <div className="flex items-center gap-1">
          <button
            type="button"
            aria-label="Semana anterior"
            onClick={() => setInicio((i) => somarSemanas(i, -1))}
            className="h-8 w-8 inline-flex items-center justify-center rounded-lg border border-hipo-border text-hipo-slate hover:bg-hipo-bg"
          >
            <ChevronLeft size={15} />
          </button>
          <button
            type="button"
            aria-label="Próxima semana"
            onClick={() => setInicio((i) => somarSemanas(i, 1))}
            className="h-8 w-8 inline-flex items-center justify-center rounded-lg border border-hipo-border text-hipo-slate hover:bg-hipo-bg"
          >
            <ChevronRight size={15} />
          </button>
          <Button
            size="sm" variant="secondary"
            onClick={() => setInicio(hojeIso())}
          >
            Hoje
          </Button>
          <span className="ml-2 text-sm font-semibold text-hipo-ink tabular-nums">
            {semana ? faixaDaSemana(semana.inicio, semana.fim) : '—'}
          </span>
        </div>

        <div className="flex items-center gap-2">
          <KpiInline
            label="Marcadas"
            valor={semana?.total ?? '—'}
            titulo="Reuniões marcadas nesta semana, sem contar as canceladas."
            icone={CalendarDays}
            tom="bg-hipo-blueSoft text-hipo-blue"
          />
          {/*
            "Livres" só existe com uma agenda escolhida: somar os slots
            vagos de cinco pessoas produziria um número que não responde à
            pergunta de ninguém. O backend devolve null, e a tela some com
            o KPI em vez de mostrar um traço sem explicação.
          */}
          {semana?.livres !== null && semana?.livres !== undefined && (
            <KpiInline
              label="Slots livres"
              valor={semana.livres}
              titulo="Horários vagos na grade desta semana, descontando feriados."
              icone={CalendarClock}
              tom="bg-hipo-successSoft text-hipo-success"
            />
          )}
          {semana?.concluidas > 0 && (
            <KpiInline
              label="Realizadas"
              valor={semana.concluidas}
              titulo="Reuniões já concluídas nesta semana."
              icone={CalendarCheck}
              tom="bg-hipo-successSoft text-hipo-success"
            />
          )}
          {/*
            O contador que impede o convite perdido de passar despercebido.
            Fica no topo, e não escondido no detalhe de cada cartão: uma
            reunião cujo convite não saiu é uma reunião que não vai
            acontecer.
          */}
          {semana?.nao_sincronizadas > 0 && (
            <Badge tone="warning">
              {semana.nao_sincronizadas} sem convite
            </Badge>
          )}
        </div>

        <div className="ml-auto flex items-center gap-2">
          <select
            aria-label="Agenda de"
            value={anfitriao}
            onChange={(e) => setAnfitriao(e.target.value)}
            className={`${CLASSE_CAMPO} px-1.5 max-w-[12rem]`}
          >
            <option value="">Toda a equipe</option>
            {opcoesAnfitriao.map((u) => (
              <option key={u.id} value={u.id}>{u.nome}</option>
            ))}
          </select>
        </div>
      </div>

      {erro && (
        <div className="shrink-0"><AlertMessage tipo="erro">{erro}</AlertMessage></div>
      )}

      {semana && !semana.google_configurado && (
        <div className="shrink-0">
          <AlertMessage tipo="aviso">
            A integração com o Google Calendar não está configurada neste
            servidor: as reuniões são marcadas normalmente, mas os convites
            não são enviados.
          </AlertMessage>
        </div>
      )}

      {/* ── Fora da grade ── */}
      {porSlot.foraDaGrade.length > 0 && (
        <div className="shrink-0 flex flex-wrap items-center gap-1.5 px-2 py-1.5 rounded-lg border border-dashed border-hipo-border bg-hipo-bg/50">
          <span className="text-[11px] text-hipo-slate shrink-0">
            Fora da grade:
          </span>
          {porSlot.foraDaGrade.map((r) => (
            <span key={r.id} className="inline-flex items-center gap-1">
              <span className="text-[11px] text-hipo-muted tabular-nums">
                {diaCurto(r.dia)}
              </span>
              <span className="w-48">
                <Cartao reuniao={r} onAbrir={setAberta} />
              </span>
            </span>
          ))}
        </div>
      )}

      {/* ── A grade ── */}
      <div className="flex-1 min-h-0 flex flex-col border border-hipo-border rounded-xl overflow-hidden bg-hipo-card">
        {carregando && !semana ? (
          <p className="py-16 text-center text-sm text-hipo-slate">
            Carregando a agenda…
          </p>
        ) : (
          <>
            {/* Cabeçalho dos dias. Fora do container que rola, para não
                sumir quando a grade desce até as 17h30. */}
            <div
              className="shrink-0 grid border-b border-hipo-border bg-hipo-bg/60"
              style={{ gridTemplateColumns: '3.5rem repeat(5, minmax(0, 1fr))' }}
            >
              <div className="border-r border-hipo-border" />
              {dias.map((d) => (
                <div
                  key={d.data}
                  className={
                    'px-2 py-1.5 border-r border-hipo-border text-center ' +
                    (d.nao_util ? 'bg-hipo-warningSoft' : '')
                  }
                >
                  <span className="block text-xs font-semibold text-hipo-ink">
                    {d.dia_semana}
                  </span>
                  <span className="block text-[11px] text-hipo-slate tabular-nums">
                    {diaCurto(d.data)}
                  </span>
                  {/*
                    Feriado PINTA, não bloqueia: o calendário de dias não
                    úteis é mantido à mão e pode estar desatualizado.
                    Recusar com base nele transformaria uma tabela
                    esquecida em erro para o usuário.
                  */}
                  {d.nao_util && (
                    <span
                      className="block text-[10px] text-hipo-warning truncate"
                      title={d.motivo || 'Dia não útil'}
                    >
                      {d.motivo || 'não útil'}
                    </span>
                  )}
                </div>
              ))}
            </div>

            {/* O scroll da tela mora aqui. `min-h-0` não é decoração: sem
                ele o flex-item usa a altura do conteúdo como mínimo e a
                grade cresce para fora do container em vez de rolar. */}
            <div className="flex-1 min-h-0 overflow-y-auto">
              <div
                className="grid"
                style={{ gridTemplateColumns: '3.5rem repeat(5, minmax(0, 1fr))' }}
              >
                {slots.map((slot, i) => {
                  // O intervalo do almoço é um SALTO entre slots, não uma
                  // linha vazia: uma faixa de células cinzas gastaria a
                  // altura de três reuniões dizendo que ninguém trabalha ali.
                  const anterior = slots[i - 1];
                  const depoisDoAlmoco = anterior === '11:30' && slot === '13:00';
                  return (
                    <div key={slot} className="contents">
                      {depoisDoAlmoco && (
                        <div className="col-span-6 h-3 bg-hipo-bg border-y border-hipo-border" />
                      )}
                      <div className="px-1 py-1 border-b border-r border-hipo-border text-[11px] text-hipo-slate text-right tabular-nums">
                        {slot}
                      </div>
                      {dias.map((d) => (
                        <Celula
                          key={`${d.data}-${slot}`}
                          dia={d.data}
                          slot={slot}
                          reunioes={porSlot.mapa.get(`${d.data}|${slot}`) || []}
                          onAbrir={(r) => { setNovo(null); setAberta(r); }}
                          onMarcar={marcar}
                          // Sem anfitrião escolhido não dá para marcar
                          // clicando: a célula vazia é vazia para QUEM?
                          // Cinco agendas sobrepostas não têm buraco comum,
                          // e o clique criaria a reunião no dono errado.
                          desabilitado={!anfitriao}
                        />
                      ))}
                    </div>
                  );
                })}
              </div>
            </div>
          </>
        )}
      </div>

      {!anfitriao && semana && (
        <p className="shrink-0 text-xs text-hipo-slate">
          Vendo a semana de toda a equipe. Escolha uma pessoa para marcar
          reuniões clicando nos horários livres.
        </p>
      )}

      <ModalReuniao
        aberto={Boolean(aberta || novo)}
        onFechar={fechar}
        onSalvo={aoSalvar}
        reuniao={aberta}
        slotInicial={novo?.inicio || ''}
        anfitriaoInicial={anfitriao}
        usuarios={usuarios}
      />
    </div>
  );
}
