// web/src/components/crm/GuiaRoteiro.jsx
//
// O "Guia do roteiro": o script resumido do scorecard, para o vendedor ter
// ao lado durante a call (pedido do Tulio, 07/10/2026).
//
// ── De onde vem o texto ──────────────────────────────────────────────
// De GET /crm/agenda/roteiro/guia, montado em services/roteiro_scorecard.py
// AO LADO dos 10 itens que a IA usa para dar a nota. É de propósito: o
// vendedor lê aqui exatamente aquilo em que vai ser avaliado, e o texto
// não tem como divergir da avaliação. Nada fica escrito no front.
//
// ── Três abas, na ordem da reunião ───────────────────────────────────
//   Roteiro    — as 6 etapas com o tempo, e em cada uma os itens do
//                scorecard: o que fazer, falas de exemplo, o que evitar e o
//                que vale 2 pontos. Cada item tem um "feito" para marcar
//                durante a call; a marca vive só neste modal (é rascunho
//                de quem está falando, não registro — o registro é o
//                scorecard que sai da transcrição).
//   Três 10    — produto, você e Controller: o sinal de que está baixo e
//                como subir; as perguntas de calibração; o limite do looping.
//   Fechamento — a técnica de cada situação com a frase pronta, e a
//                pergunta final.
//
// Os três 10 e as técnicas são os da trilha "06 · Fechamento" da UC.

import { useEffect, useMemo, useState } from 'react';
import {
  CheckCircle2, Circle, Clock, Gauge, MessageSquareQuote, OctagonX, Target,
} from 'lucide-react';

import api from '../../api';
import Modal from '../ui/Modal';
import Tabs from '../ui/Tabs';
import AlertMessage from '../ui/AlertMessage';
import { mensagemDeErro } from './agendaComum';

const ABAS = [
  { key: 'guia-roteiro', label: 'Roteiro' },
  { key: 'guia-tres-dez', label: 'Três 10' },
  { key: 'guia-fechamento', label: 'Fechamento' },
];

const TITULO_CERTEZA = {
  Produto: '10 no produto',
  'Você': '10 em você',
  Controller: '10 na Controller',
};

function Fala({ children }) {
  return (
    <li className="flex gap-1.5 text-sm text-hipo-ink">
      <MessageSquareQuote size={14} className="mt-0.5 shrink-0 text-hipo-blue" aria-hidden="true" />
      <span>“{children}”</span>
    </li>
  );
}

function ItemDoRoteiro({ item, feito, onAlternar }) {
  return (
    <li
      className={
        'rounded-lg border p-3 transition-colors ' +
        (feito
          ? 'border-hipo-successBorder bg-hipo-successSoft/60'
          : 'border-hipo-border bg-hipo-card')
      }
    >
      <div className="flex items-start gap-2">
        <button
          type="button"
          onClick={onAlternar}
          aria-pressed={feito}
          aria-label={`Marcar item ${item.item} como feito`}
          className={
            'mt-0.5 shrink-0 rounded-full focus:outline-none ' +
            'focus-visible:ring-2 focus-visible:ring-hipo-blue ' +
            (feito ? 'text-hipo-success' : 'text-hipo-muted hover:text-hipo-blue')
          }
        >
          {feito ? <CheckCircle2 size={18} /> : <Circle size={18} />}
        </button>
        <div className="min-w-0 flex-1 space-y-2">
          <p className="text-sm font-semibold text-hipo-ink">
            <span className="tabular-nums text-hipo-muted">{item.item}.</span> {item.nome}
          </p>
          <p className="text-sm text-hipo-ink">{item.fazer}</p>
          <ul className="space-y-1">
            {item.exemplos.map((ex) => <Fala key={ex}>{ex}</Fala>)}
          </ul>
          <p className="flex gap-1.5 text-xs text-hipo-danger">
            <OctagonX size={13} className="mt-0.5 shrink-0" aria-hidden="true" />
            <span><strong>Evite:</strong> {item.evitar}</span>
          </p>
          <p className="flex gap-1.5 text-xs text-hipo-slate">
            <Target size={13} className="mt-0.5 shrink-0 text-hipo-success" aria-hidden="true" />
            <span><strong>Vale 2:</strong> {item.vale_2}</span>
          </p>
        </div>
      </div>
    </li>
  );
}

function AbaRoteiro({ guia, feitos, alternar }) {
  return (
    <div className="space-y-4">
      {guia.etapas.map((etapa) => (
        <section key={etapa.nome} aria-label={etapa.nome}>
          <h3 className="mb-2 flex items-center gap-2 text-xs font-semibold uppercase tracking-wide text-hipo-slate">
            {etapa.nome}
            {etapa.minutos ? (
              <span className="inline-flex items-center gap-1 font-normal normal-case text-hipo-muted">
                <Clock size={11} aria-hidden="true" /> {etapa.minutos} min
              </span>
            ) : null}
          </h3>
          <ul className="space-y-2">
            {etapa.itens.map((item) => (
              <ItemDoRoteiro
                key={item.item}
                item={item}
                feito={feitos.has(item.item)}
                onAlternar={() => alternar(item.item)}
              />
            ))}
          </ul>
        </section>
      ))}
    </div>
  );
}

function AbaTresDez({ tresDez }) {
  return (
    <div className="space-y-4">
      <p className="text-sm text-hipo-slate">
        O cliente só fecha seguro das três coisas. Basta uma baixa para o
        “sim” virar “vou pensar”.
      </p>
      <div className="rounded-lg border border-hipo-blue/40 bg-hipo-blueSoft p-3 space-y-1">
        <p className="flex items-center gap-1.5 text-xs font-semibold uppercase tracking-wide text-hipo-blue">
          <Gauge size={13} aria-hidden="true" /> Meça antes de pedir
        </p>
        <ul className="space-y-1">
          <Fala>{tresDez.pergunta_calibracao}</Fala>
          <Fala>{tresDez.pergunta_o_que_falta}</Fala>
        </ul>
      </div>
      <ul className="grid grid-cols-1 gap-2 md:grid-cols-3">
        {tresDez.certezas.map((c) => (
          <li key={c.nome} className="rounded-lg border border-hipo-border bg-hipo-card p-3 space-y-2">
            <p className="text-sm font-semibold text-hipo-ink">{TITULO_CERTEZA[c.nome] || `10 em ${c.nome}`}</p>
            <p className="text-xs text-hipo-danger"><strong>Está baixo quando:</strong> {c.sinal_baixo}</p>
            <p className="text-xs text-hipo-ink"><strong>Como subir:</strong> {c.como_subir}</p>
          </li>
        ))}
      </ul>
      <p className="text-xs text-hipo-slate">
        <strong>Looping:</strong> acolha, explore (LAER), volte à certeza baixa,
        meça de novo e peça com outra técnica. No máximo {tresDez.looping_maximo}{' '}
        voltas; depois, feche um próximo passo com data.
      </p>
    </div>
  );
}

function AbaFechamento({ fechamentos, perguntaFinal }) {
  return (
    <div className="space-y-3">
      <p className="text-sm text-hipo-slate">
        Abra sempre com o resumo de valor, peça com a técnica da situação e
        fique em silêncio. Convite de calendário ainda na reunião.
      </p>
      <ul className="space-y-2">
        {fechamentos.map((f) => (
          <li key={f.tecnica} className="rounded-lg border border-hipo-border bg-hipo-card p-3 space-y-1">
            <p className="text-xs text-hipo-slate">{f.situacao}</p>
            <p className="text-sm font-semibold text-hipo-ink">{f.tecnica}</p>
            <ul><Fala>{f.frase}</Fala></ul>
          </li>
        ))}
      </ul>
      <div className="rounded-lg border border-hipo-successBorder bg-hipo-successSoft p-3">
        <p className="text-xs font-semibold uppercase tracking-wide text-hipo-success">Antes de desligar</p>
        <ul className="mt-1"><Fala>{perguntaFinal}</Fala></ul>
      </div>
    </div>
  );
}

export default function GuiaRoteiro({ aberto, onFechar, nivel = 2 }) {
  const [guia, setGuia] = useState(null);
  const [erro, setErro] = useState(null);
  const [aba, setAba] = useState(ABAS[0].key);
  const [feitos, setFeitos] = useState(() => new Set());

  useEffect(() => {
    if (!aberto || guia) return undefined;
    let vivo = true;
    setErro(null);
    api.get('/crm/agenda/roteiro/guia')
      .then(({ data }) => { if (vivo) setGuia(data); })
      .catch((err) => {
        if (vivo) setErro(mensagemDeErro(err, 'Não foi possível abrir o guia do roteiro.'));
      });
    return () => { vivo = false; };
  }, [aberto, guia]);

  const totalItens = useMemo(
    () => (guia ? guia.etapas.reduce((n, e) => n + e.itens.length, 0) : 0),
    [guia],
  );

  function alternar(numero) {
    setFeitos((atual) => {
      const novo = new Set(atual);
      if (novo.has(numero)) novo.delete(numero); else novo.add(numero);
      return novo;
    });
  }

  return (
    <Modal
      aberto={aberto}
      onFechar={onFechar}
      nivel={nivel}
      size="lg"
      titulo="Guia do roteiro"
      subtitulo={guia ? (
        <span className="flex flex-wrap items-center gap-x-3 gap-y-1">
          <span>{guia.duracao_min} min</span>
          <span>fale até {guia.meta_fala_pct.toLocaleString('pt-BR')}% do tempo</span>
          <span className="tabular-nums" aria-live="polite">
            {feitos.size}/{totalItens} itens feitos
          </span>
        </span>
      ) : undefined}
    >
      {erro && <AlertMessage tipo="erro">{erro}</AlertMessage>}
      {!erro && !guia && (
        <p className="py-8 text-center text-sm text-hipo-slate">Carregando o guia…</p>
      )}
      {guia && (
        <div className="space-y-4">
          <Tabs items={ABAS} value={aba} onChange={setAba} />
          {aba === 'guia-roteiro' && (
            <AbaRoteiro guia={guia} feitos={feitos} alternar={alternar} />
          )}
          {aba === 'guia-tres-dez' && <AbaTresDez tresDez={guia.tres_dez} />}
          {aba === 'guia-fechamento' && (
            <AbaFechamento fechamentos={guia.fechamentos} perguntaFinal={guia.pergunta_final} />
          )}
        </div>
      )}
    </Modal>
  );
}
