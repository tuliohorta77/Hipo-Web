// web/src/pages/Monitor.jsx
//
// O MONITOR: o painel de parede da operação. Dez quadros com meta e
// resultado do mês corrente, cada um com uma carinha.
//
// ── Fica aberto o dia inteiro ────────────────────────────────────────
// Esta tela não é consultada, é OLHADA. Por isso ela:
//
//   * se atualiza sozinha, de minuto em minuto, sem ninguém dar F5;
//   * para de buscar quando a aba está em segundo plano e busca na hora em
//     que ela volta a aparecer — uma TV esquecida numa aba escondida não
//     precisa de uma request por minuto, e quem volta à aba precisa do dado
//     de agora, não do de vinte minutos atrás;
//   * mostra a HORA DA ÚLTIMA LEITURA. Painel parado é indistinguível de
//     painel atualizado se ele não disser quando leu — e um painel que
//     mente sem avisar é pior que nenhum painel;
//   * mantém o que está na tela quando uma leitura falha. Trocar o painel
//     por uma mensagem de erro apagaria da parede o número que a equipe
//     está olhando por causa de uma queda de rede de dois segundos: o
//     último dado bom continua, com o aviso de que ele envelheceu.
//
// ── Recorte mensal, sem seletor de período ───────────────────────────
// Do dia 1o até hoje, e vira no dia 1o sozinho. A pergunta da parede é
// "como estamos ESTE mês"; um seletor faria a TV passar novembro inteiro
// mostrando setembro sem ninguém notar.
//
// ── Meta e carinha vêm prontas do servidor ───────────────────────────
// A régua (meta proporcional aos dias úteis corridos, descontando os
// feriados da tabela) mora em services/monitor.py. A tela desenha.
//
// ── Tela cheia ───────────────────────────────────────────────────────
// A TV não precisa da barra do navegador nem da nav do HIPO. O botão pede
// tela cheia para o CONTAINER do painel (não para a página): assim os dez
// quadros crescem para ocupar a tela inteira e a fonte sobe junto. O Esc
// sai, e o estado é lido do evento `fullscreenchange` em vez de ser
// adivinhado no clique — sair pelo Esc ou pelo F11 deixaria o botão
// mentindo sobre o que ele faz.
//
// ── Tema escuro ──────────────────────────────────────────────────────
// Botão lua/sol na barra. A classe `tema-escuro` no CONTAINER redefine as
// variáveis de cor do HIPO (src/index.css) só aqui dentro: quadros, a
// lista da carinha, o formulário da reunião e Metas e calendário escurecem
// juntos, porque todos são renderizados dentro do container (ver a nota
// abaixo). A nav do HIPO, fora dele, não muda. A escolha fica gravada no
// navegador — é da TV, não da pessoa (monitorComum.lerTema).
//
// ── A carinha abre a lista ───────────────────────────────────────────
// Clicar num quadro abre o que está sendo contado nele (DetalheIndicador).
// O modal é renderizado DENTRO do container do painel, e não num portal no
// body: em tela cheia só o container aparece, e um modal fora dele abriria
// invisível atrás da TV.

import { useCallback, useEffect, useRef, useState } from 'react';
import {
  RefreshCw, Settings, AlertTriangle, Maximize2, Minimize2, Moon, Sun, Presentation,
} from 'lucide-react';

import api, { getUser } from '../api';
import Button from '../components/ui/Button';
import AlertMessage from '../components/ui/AlertMessage';
import QuadroIndicador from '../components/monitor/QuadroIndicador';
import ConfigMonitor from '../components/monitor/ConfigMonitor';
import DetalheIndicador from '../components/monitor/DetalheIndicador';
import RperMonitor from '../components/monitor/RperMonitor';
import {
  INTERVALO_MS, horaDaLeitura, lerTema, gravarTema,
} from '../components/monitor/monitorComum';
import { mensagemDeErro } from '../components/crm/tarefaComum';

// Metas e feriados são da gestão — é a régua pela qual a equipe é medida.
// O backend recusa de qualquer forma (403); aqui a tela só não oferece o
// botão a quem vai levar erro.
const CARGOS_DE_GESTAO = ['Franqueado', 'ADM'];

export default function Monitor() {
  const [painel, setPainel] = useState(null);
  const [erro, setErro] = useState(null);
  const [buscando, setBuscando] = useState(false);
  const [config, setConfig] = useState(false);
  // O RPeR (PPT da reunião do 1º dia útil) — gestão, como as metas.
  const [rper, setRper] = useState(false);
  const [cheia, setCheia] = useState(false);
  // A chave do quadro cuja lista está aberta, ou null.
  const [detalhe, setDetalhe] = useState(null);
  const [tema, setTema] = useState(lerTema);
  const escuro = tema === 'escuro';
  const container = useRef(null);
  const usuario = getUser();
  const podeConfigurar = CARGOS_DE_GESTAO.includes(usuario?.cargo);

  /*
    `montado` em ref, e não em estado: a resposta de uma busca que estava no
    ar quando o usuário saiu da tela chegaria depois do unmount e o React
    avisaria sobre atualizar componente desmontado — numa tela que busca a
    cada minuto, isso acontece todo dia.
  */
  const montado = useRef(true);
  // O `true` no corpo do efeito não é redundante: o StrictMode do React 18
  // (ligado em main.jsx) monta, DESMONTA e monta de novo em desenvolvimento.
  // Só com o cleanup, o ref ficava `false` para sempre e o painel parava em
  // "Carregando painel…" no `npm run dev` — em produção não acontecia.
  useEffect(() => {
    montado.current = true;
    return () => { montado.current = false; };
  }, []);

  const carregar = useCallback(async () => {
    setBuscando(true);
    try {
      const { data } = await api.get('/monitor/painel');
      if (!montado.current) return;
      setPainel(data);
      setErro(null);
    } catch (err) {
      if (!montado.current) return;
      // O painel que está na tela FICA. Só aparece o aviso de que ele
      // envelheceu — ver a nota no topo do arquivo.
      setErro(mensagemDeErro(err, 'Não foi possível atualizar o painel.'));
    } finally {
      if (montado.current) setBuscando(false);
    }
  }, []);

  useEffect(() => { carregar(); }, [carregar]);

  // O navegador é a fonte da verdade do estado de tela cheia.
  useEffect(() => {
    function sincronizar() {
      setCheia(Boolean(document.fullscreenElement));
    }
    document.addEventListener('fullscreenchange', sincronizar);
    return () => document.removeEventListener('fullscreenchange', sincronizar);
  }, []);

  /*
    Pedir tela cheia só funciona dentro de um gesto do usuário, e pode ser
    recusado (política do navegador, iframe sem permissão). O `catch` existe
    para a recusa não derrubar a tela: o painel continua onde está.
  */
  async function alternarTelaCheia() {
    try {
      if (document.fullscreenElement) {
        await document.exitFullscreen?.();
        return;
      }
      const alvo = container.current;
      if (!alvo?.requestFullscreen) {
        setErro('Este navegador não permite tela cheia nesta página.');
        return;
      }
      await alvo.requestFullscreen();
    } catch {
      setErro('O navegador recusou a tela cheia.');
    }
  }

  /*
    O relógio da tela. `document.hidden` é consultado no disparo, e não só
    no agendamento: a aba pode ter ido para o fundo entre dois tiques.

    `visibilitychange` busca na hora em que a aba volta — sem isso, quem
    reabre a TV veria o dado de até um minuto atrás por até um minuto.
  */
  useEffect(() => {
    const id = setInterval(() => {
      if (!document.hidden) carregar();
    }, INTERVALO_MS);

    function aoVoltar() {
      if (!document.hidden) carregar();
    }
    document.addEventListener('visibilitychange', aoVoltar);

    return () => {
      clearInterval(id);
      document.removeEventListener('visibilitychange', aoVoltar);
    };
  }, [carregar]);

  function alternarTema() {
    const novo = escuro ? 'claro' : 'escuro';
    setTema(novo);
    gravarTema(novo);
  }

  const hora = horaDaLeitura(painel?.atualizado_em);

  return (
    <div
      ref={container}
      data-testid="monitor"
      data-tema={tema}
      className={
        'min-h-0 flex flex-col gap-2 '
        + (escuro ? 'tema-escuro ' : '')
        // Em tela cheia o container passa a ser a tela: sem fundo e sem
        // respiro próprios, os quadros ficariam colados na moldura preta.
        + (cheia
          ? 'h-full bg-hipo-bg p-4 overflow-hidden'
          // Fora da tela cheia, o escuro cobre também o respiro que o
          // Layout dá em volta da página (px-3 lg:px-5 py-3): sem isso
          // ficaria uma moldura clara em volta do painel escuro. A altura
          // soma os dois respiros (0,75rem em cima e embaixo).
          : (escuro
            ? 'bg-hipo-bg -mx-3 lg:-mx-5 -my-3 px-3 lg:px-5 py-3 h-[calc(100%+1.5rem)]'
            : 'h-full'))
      }
    >

      {/* ── Barra: o mês, o ritmo e a hora da leitura ── */}
      <div data-tour="mon-barra" className="shrink-0 flex flex-wrap items-center gap-x-4 gap-y-2 px-1">
        <h1 className="text-lg font-semibold text-hipo-ink">Monitor</h1>

        {painel && (
          <>
            <span className="text-sm text-hipo-slate capitalize">{painel.rotulo}</span>
            {/*
              O ritmo do mês em texto, não só na barra de cada quadro: é o
              denominador de toda carinha da tela, e quem olha precisa saber
              em que altura do mês está.
            */}
            <span className="text-xs text-hipo-slate">
              dia útil {painel.dia_util_atual} de {painel.dias_uteis}
              {' · '}
              {Math.round(painel.progresso * 100)}% do mês
            </span>
          </>
        )}

        <div className="ml-auto flex items-center gap-2">
          {hora && (
            <span
              className="text-xs text-hipo-muted tabular-nums"
              aria-label={`Atualizado às ${hora}`}
            >
              {erro && (
                <AlertTriangle
                  size={12}
                  className="inline mr-1 text-hipo-warning"
                  aria-hidden="true"
                />
              )}
              {hora}
            </span>
          )}
          <Button
            size="sm" variant="ghost" icon={escuro ? Sun : Moon}
            aria-label={escuro ? 'Usar tema claro' : 'Usar tema escuro'}
            aria-pressed={escuro}
            onClick={alternarTema}
          >
            {escuro ? 'Claro' : 'Escuro'}
          </Button>
          <Button
            size="sm" variant="ghost" icon={cheia ? Minimize2 : Maximize2}
            aria-label={cheia ? 'Sair da tela cheia' : 'Tela cheia'}
            onClick={alternarTelaCheia}
          >
            {cheia ? 'Sair' : 'Tela cheia'}
          </Button>
          <Button
            size="sm" variant="ghost" icon={RefreshCw}
            loading={buscando}
            aria-label="Atualizar agora"
            onClick={carregar}
          >
            Atualizar
          </Button>
          {podeConfigurar && (
            <Button
              size="sm" variant="secondary" icon={Presentation}
              onClick={() => setRper(true)}
            >
              RPeR
            </Button>
          )}
          {podeConfigurar && (
            <Button
              size="sm" variant="secondary" icon={Settings}
              onClick={() => setConfig(true)}
            >
              Metas e calendário
            </Button>
          )}
        </div>
      </div>

      {/*
        O aviso de leitura velha aparece ACIMA dos quadros e não no lugar
        deles: o número da parede continua valendo, só ficou mais antigo do
        que deveria.
      */}
      {erro && painel && (
        <div className="shrink-0">
          <AlertMessage tipo="aviso">
            {erro} Mostrando a última leitura{hora ? ` das ${hora}` : ''}.
          </AlertMessage>
        </div>
      )}
      {erro && !painel && (
        <div className="shrink-0"><AlertMessage tipo="erro">{erro}</AlertMessage></div>
      )}

      {/*
        Grade de 5 colunas em duas linhas, como a planilha que a operação já
        lê. Em tela estreita cai para 2 colunas: a TV é larga, mas a mesma
        tela abre no celular de quem está fora.
      */}
      <div className="flex-1 min-h-0 overflow-y-auto">
        {!painel ? (
          <p className="py-16 text-center text-sm text-hipo-slate">Carregando painel…</p>
        ) : (
          <div data-tour="mon-quadros" className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-5 gap-2 auto-rows-fr h-full">
            {painel.indicadores.map((i) => (
              <QuadroIndicador
                key={i.chave}
                indicador={i}
                grande={cheia}
                onAbrir={(ind) => setDetalhe(ind.chave)}
              />
            ))}
          </div>
        )}
      </div>

      {painel && detalhe && (
        <DetalheIndicador
          aberto
          chave={detalhe}
          ano={painel.ano}
          mes={painel.mes}
          onFechar={() => setDetalhe(null)}
          onMudou={carregar}
        />
      )}

      {podeConfigurar && rper && (
        <RperMonitor aberto={rper} onFechar={() => setRper(false)} />
      )}

      {podeConfigurar && painel && (
        <ConfigMonitor
          aberto={config}
          onFechar={() => setConfig(false)}
          ano={painel.ano}
          mes={painel.mes}
          onSalvo={carregar}
        />
      )}
    </div>
  );
}
