// web/src/pages/crm/ReuniaoAoVivo.jsx
//
// Reunião ao vivo: a transcrição da call acontecendo, dentro do HIPO.
//
// ── Onde fica ────────────────────────────────────────────────────────
// Numa aba do HIPO aberta ao lado do Meet (botão "Reunião ao vivo" no
// modal da reunião). O Meet continua sendo o Meet — convite, sala e a
// transcrição de depois (entrega 020) não mudam. Esta tela só escuta.
//
// ── Prova de conceito ────────────────────────────────────────────────
// A pergunta desta entrega é uma só: o reconhecimento de voz gratuito do
// Chrome aguenta uma call de verdade em português? Por isso a tela mostra
// o estado de cada canal, os erros e, depois que a transcrição do Meet
// chega, quanto das palavras dela o ao vivo também pegou. Os cartões de
// roteiro e de objeção entram em cima disto quando a resposta for sim.
//
// ── Dashboard operacional ────────────────────────────────────────────
// A barra de cima é o painel (tempo, palavras de cada lado e a proporção
// de fala do vendedor — nas reuniões medidas em 30/09 o EV falou 65-68%);
// a ação é iniciar e encerrar dali mesmo.
//
// ── Encerrar já dá baixa ─────────────────────────────────────────────
// Os botões de fim são as respostas de "o que aconteceu?": Realizada ou
// No-show. Um clique para a transcrição, registra o desfecho pela MESMA
// rota da Agenda (POST /reunioes/{id}/desfecho) e com isso fecha a
// reunião e a tarefa na mesma transação. Quando a regra da casa exige a
// próxima tarefa (realizada, oportunidade viva, última tarefa aberta), o
// clique abre o mesmo painel de desfecho da Agenda, já com Realizada
// marcada — a regra não se pula por ter vindo de outra tela.

import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { useParams } from 'react-router-dom';
import {
  Mic, MicOff, MonitorSpeaker, Square, ExternalLink, Timer, User, Users,
  Gauge, Loader2, CloudUpload, CheckCircle2, UserX,
} from 'lucide-react';

import api from '../../api';
import PageHeader from '../../components/ui/PageHeader';
import Card from '../../components/ui/Card';
import Button from '../../components/ui/Button';
import Badge from '../../components/ui/Badge';
import AlertMessage from '../../components/ui/AlertMessage';
import KpiInline from '../../components/ui/KpiInline';
import { exigeProximaTarefa, mensagemDeErro } from '../../components/crm/tarefaComum';
import {
  DesfechoRegistrado, PainelDesfecho, agendarProximaSeForReuniao,
} from '../../components/crm/DesfechoReuniao';
import {
  CANAIS, INTERVALO_ENVIO_MS, MAX_FALAS_POR_LOTE, ROTULO_CANAL,
  criarFila, criarReconhecedor, construtorDeReconhecimento, descreverNavegador,
  diagnosticarSuporte, formatarCronometro, fraseDoErro, metricasDasFalas,
} from '../../components/crm/aoVivo';

const FUSO = 'America/Sao_Paulo';

// As situações em que a reunião ainda espera um desfecho. Mesma lista do
// ModalReuniao: fora dela a reunião já foi concluída ou cancelada.
const SITUACOES_ABERTAS = ['atrasada', 'hoje', 'futura'];

// Acima disto o vendedor está falando mais que o cliente numa conversa que
// deveria ser de descoberta. A barra fica amarela — é aviso, não regra.
const LIMITE_FALA_VENDEDOR = 60;

const ESTADO_CANAL = {
  ouvindo: { tom: 'success', texto: 'ouvindo' },
  religando: { tom: 'info', texto: 'religando' },
  parado: { tom: 'neutral', texto: 'parado' },
  falhou: { tom: 'danger', texto: 'falhou' },
  desligado: { tom: 'neutral', texto: 'sem áudio' },
};

function quando(iso) {
  if (!iso) return '';
  const d = new Date(iso);
  const dia = d.toLocaleDateString('pt-BR', { day: '2-digit', month: '2-digit', timeZone: FUSO });
  const hora = d.toLocaleTimeString('pt-BR', { hour: '2-digit', minute: '2-digit', timeZone: FUSO });
  return `${dia} às ${hora}`;
}

function horaSegundos(iso) {
  return new Date(iso).toLocaleTimeString('pt-BR', {
    hour: '2-digit', minute: '2-digit', second: '2-digit', timeZone: FUSO,
  });
}

function pararTrilhas(streams) {
  for (const s of streams) {
    for (const t of s?.getTracks?.() || []) {
      try { t.stop(); } catch { /* já parada */ }
    }
  }
}

export default function ReuniaoAoVivo() {
  const { tarefaId } = useParams();
  const base = `/crm/agenda/tarefas/${tarefaId}/ao-vivo`;

  const [dados, setDados] = useState(null);
  const [carregando, setCarregando] = useState(true);
  const [erro, setErro] = useState(null);
  const [avisos, setAvisos] = useState([]);

  // pronto | iniciando | capturando | encerrando
  const [fase, setFase] = useState('pronto');
  const [falasLocais, setFalasLocais] = useState([]);
  const [parciais, setParciais] = useState({ vendedor: '', cliente: '' });
  const [estados, setEstados] = useState({ vendedor: 'desligado', cliente: 'desligado' });
  const [pendentes, setPendentes] = useState(0);
  const [inicio, setInicio] = useState(null);
  const [agora, setAgora] = useState(Date.now());

  // A reunião como a Agenda a vê (desfecho, situação, oportunidade) e a
  // lista de pessoas para a próxima tarefa. É o que os botões de
  // Realizada / No-show precisam para dar baixa daqui.
  const [reuniao, setReuniao] = useState(null);
  const [usuarios, setUsuarios] = useState([]);
  const [registrando, setRegistrando] = useState(false);
  const [pedindoProxima, setPedindoProxima] = useState(false);
  const [sucesso, setSucesso] = useState(null);

  const suporte = useMemo(() => diagnosticarSuporte(window), []);

  const sessaoRef = useRef(null);
  const filaRef = useRef(null);
  const recsRef = useRef({});
  const streamsRef = useRef([]);
  const intervaloRef = useRef(null);
  const enviandoRef = useRef(false);
  const fimDaListaRef = useRef(null);
  const painelProximaRef = useRef(null);

  const avisar = useCallback((texto) => {
    setAvisos((a) => (a.includes(texto) ? a : [...a, texto]));
  }, []);

  const carregar = useCallback(async () => {
    try {
      const { data } = await api.get(base);
      setDados(data && typeof data === 'object' && data.reuniao_id ? data : null);
      setErro(null);
    } catch (err) {
      setErro(mensagemDeErro(err, 'Não foi possível carregar a reunião.'));
      setDados(null);
    } finally {
      setCarregando(false);
    }
  }, [base]);

  useEffect(() => { carregar(); }, [carregar]);

  const reuniaoId = dados?.reuniao_id;
  const carregarReuniao = useCallback(async () => {
    if (!reuniaoId) return;
    try {
      const { data } = await api.get(`/crm/agenda/reunioes/${reuniaoId}`);
      setReuniao(data && typeof data === 'object' && data.id ? data : null);
    } catch {
      // Sem a reunião, os botões de desfecho só não aparecem: a captura
      // continua funcionando, e a baixa se dá pela Agenda como sempre.
      setReuniao(null);
    }
  }, [reuniaoId]);

  useEffect(() => { carregarReuniao(); }, [carregarReuniao]);

  useEffect(() => {
    api.get('/crm/dominio/usuarios')
      .then(({ data }) => setUsuarios(Array.isArray(data) ? data : []))
      .catch(() => setUsuarios([]));
  }, []);

  // Cronômetro: só anda enquanto captura.
  useEffect(() => {
    if (fase !== 'capturando') return undefined;
    const id = setInterval(() => setAgora(Date.now()), 1000);
    return () => clearInterval(id);
  }, [fase]);

  // Rolagem: a fala nova aparece embaixo, como num chat.
  useEffect(() => {
    fimDaListaRef.current?.scrollIntoView?.({ block: 'end' });
  }, [falasLocais.length, parciais.vendedor, parciais.cliente]);

  // O painel da próxima tarefa nasce no alto da página, mas quem clicou em
  // Realizada pode estar lendo a conversa lá embaixo. Sem levar a pessoa
  // até ele, o clique "não faz nada" — foi o que aconteceu no primeiro uso.
  useEffect(() => {
    if (!pedindoProxima) return;
    painelProximaRef.current?.scrollIntoView?.({ behavior: 'smooth', block: 'start' });
  }, [pedindoProxima]);

  // Fechar a aba no meio da call perderia as falas ainda não enviadas.
  useEffect(() => {
    if (fase !== 'capturando') return undefined;
    const segurar = (e) => { e.preventDefault(); e.returnValue = ''; };
    window.addEventListener('beforeunload', segurar);
    return () => window.removeEventListener('beforeunload', segurar);
  }, [fase]);

  // Sair da tela desliga tudo (sem rede: a próxima sessão encerra esta).
  useEffect(() => () => {
    clearInterval(intervaloRef.current);
    Object.values(recsRef.current).forEach((r) => { r.parar(0); });
    pararTrilhas(streamsRef.current);
  }, []);

  const enviar = useCallback(async () => {
    const fila = filaRef.current;
    const sessao = sessaoRef.current;
    if (!fila || !sessao || enviandoRef.current || !fila.temAlgo) return true;
    enviandoRef.current = true;
    const lote = fila.lote(MAX_FALAS_POR_LOTE);
    try {
      await api.post(`/crm/agenda/ao-vivo/${sessao.id}/falas`, lote);
      fila.confirmar(lote);
      return true;
    } catch (err) {
      if (err?.response?.status === 409) {
        avisar('Esta captura foi encerrada em outra aba. Inicie de novo para continuar.');
      }
      return false;
    } finally {
      setPendentes(fila.pendentes);
      enviandoRef.current = false;
    }
  }, [avisar]);

  async function iniciar() {
    setErro(null);
    setAvisos([]);
    setFase('iniciando');
    const md = navigator.mediaDevices;

    let tela;
    try {
      tela = await md.getDisplayMedia({
        video: true,
        audio: { suppressLocalAudioPlayback: false },
        preferCurrentTab: false,
        selfBrowserSurface: 'exclude',
        surfaceSwitching: 'include',
        systemAudio: 'exclude',
      });
    } catch (err) {
      setFase('pronto');
      setErro(err?.name === 'NotAllowedError'
        ? 'A escolha da aba foi cancelada. Clique em Iniciar e escolha a aba do Meet.'
        : 'Não foi possível capturar a aba do Meet.');
      return;
    }
    const trilhaAba = tela.getAudioTracks()[0];
    if (!trilhaAba) {
      pararTrilhas([tela]);
      setFase('pronto');
      setErro(
        'A aba foi compartilhada sem áudio. Clique em Iniciar de novo, escolha a aba do '
        + 'Meet e deixe marcado "Compartilhar áudio da guia".',
      );
      return;
    }

    let mic = null;
    try {
      mic = await md.getUserMedia({
        audio: { echoCancellation: true, noiseSuppression: true, autoGainControl: true },
      });
    } catch {
      avisar('Sem acesso ao microfone: só a fala do cliente será transcrita.');
    }
    const trilhaMic = mic?.getAudioTracks?.()[0] || null;
    streamsRef.current = [tela, mic].filter(Boolean);

    const trilhas = { vendedor: trilhaMic, cliente: trilhaAba };
    const canais = CANAIS.filter((c) => trilhas[c]);

    let sessao;
    try {
      const { data } = await api.post(base, { canais, navegador: descreverNavegador(navigator) });
      sessao = data;
    } catch (err) {
      pararTrilhas(streamsRef.current);
      streamsRef.current = [];
      setFase('pronto');
      setErro(mensagemDeErro(err, 'Não foi possível iniciar a captura.'));
      return;
    }
    sessaoRef.current = sessao;
    const fila = criarFila();
    filaRef.current = fila;

    const Construtor = construtorDeReconhecimento(window);
    const recs = {};
    for (const canal of canais) {
      recs[canal] = criarReconhecedor({
        canal,
        track: trilhas[canal],
        Construtor,
        aoFinal: (f) => {
          const fala = fila.adicionar(f);
          if (fala) {
            setFalasLocais((l) => [...l, { ...fala, sessao_id: sessao.id }]);
            setPendentes(fila.pendentes);
          }
        },
        aoParcial: (c, texto) => setParciais((p) => (p[c] === texto ? p : { ...p, [c]: texto })),
        aoErro: (c, codigo, fatal) => {
          fila.registrarErro(c, codigo);
          if (fatal) avisar(`${ROTULO_CANAL[c]}: ${fraseDoErro(codigo)}.`);
        },
        aoEstado: (c, estado) => setEstados((e) => ({ ...e, [c]: estado })),
      });
    }
    recsRef.current = recs;

    trilhaAba.addEventListener?.('ended', () => {
      avisar('O compartilhamento da aba do Meet foi interrompido: a fala do cliente parou de ser transcrita.');
      recs.cliente?.parar(0);
    });

    Object.values(recs).forEach((r) => r.iniciar());
    setInicio(Date.now());
    setAgora(Date.now());
    setFase('capturando');
    intervaloRef.current = setInterval(enviar, INTERVALO_ENVIO_MS);
  }

  // Para a captura e manda o que falta. Devolve false se o último lote
  // não chegou ao HIPO — quem chamou decide se segue para o desfecho.
  async function encerrar() {
    if (!sessaoRef.current) return true;
    setFase('encerrando');
    clearInterval(intervaloRef.current);
    await Promise.all(Object.values(recsRef.current).map((r) => r.parar()));
    pararTrilhas(streamsRef.current);
    streamsRef.current = [];

    const fila = filaRef.current;
    const sessao = sessaoRef.current;
    // O que não cabe no lote final vai antes, em lotes normais.
    for (let i = 0; fila && fila.pendentes > MAX_FALAS_POR_LOTE && i < 10; i += 1) {
      if (!(await enviar())) break;
    }
    let salvo = true;
    try {
      const lote = fila ? fila.lote(MAX_FALAS_POR_LOTE) : { falas: [], erros: [] };
      await api.post(`/crm/agenda/ao-vivo/${sessao.id}/encerrar`, lote);
      fila?.confirmar(lote);
    } catch (err) {
      salvo = false;
      setErro(mensagemDeErro(
        err,
        `A captura parou, mas ${fila?.pendentes || 0} fala(s) não chegaram ao HIPO.`,
      ));
    }
    setPendentes(fila?.pendentes || 0);
    setParciais({ vendedor: '', cliente: '' });
    setEstados({ vendedor: 'desligado', cliente: 'desligado' });
    recsRef.current = {};
    sessaoRef.current = null;
    setFalasLocais([]);
    setFase('pronto');
    await carregar();
    return salvo;
  }

  // ── Desfecho ──────────────────────────────────────────────────────

  async function gravarDesfecho(corpo) {
    setRegistrando(true);
    setErro(null);
    try {
      const { data } = await api.post(`/crm/agenda/reunioes/${reuniao.id}/desfecho`, corpo);
      const problema = await agendarProximaSeForReuniao(corpo.proxima, data?.proxima_id);
      if (problema) avisar(problema);
      setReuniao(data && data.id ? data : reuniao);
      setPedindoProxima(false);
      setSucesso(corpo.desfecho === 'realizada'
        ? 'Reunião registrada como realizada: a tarefa foi concluída e a agenda atualizada.'
        : 'Reunião registrada como no-show: a tarefa foi cancelada e o evento saiu da agenda.');
      await carregarReuniao();
      return true;
    } catch (err) {
      setErro(mensagemDeErro(err, 'Não foi possível registrar o desfecho da reunião.'));
      return false;
    } finally {
      setRegistrando(false);
    }
  }

  /**
   * Realizada / No-show: para a transcrição (se estiver rodando) e dá
   * baixa. Se a próxima tarefa for obrigatória, abre o painel para ela.
   */
  async function finalizar(desfecho) {
    setSucesso(null);
    if (sessaoRef.current) {
      const salvo = await encerrar();
      // Falas perdidas não impedem a baixa, mas a pessoa precisa ver o
      // aviso antes de a tela mudar de assunto.
      if (!salvo) return;
    }
    const exige = desfecho === 'realizada' && exigeProximaTarefa(
      reuniao.oportunidade_id ? 'oportunidade' : 'parceiro',
      reuniao.status_oportunidade,
      reuniao.outras_abertas,
    );
    if (exige) {
      setPedindoProxima(true);
      return;
    }
    await gravarDesfecho({ desfecho, observacao: null, proxima: null });
  }

  const capturando = fase === 'capturando';
  const ocupado = fase === 'iniciando' || fase === 'encerrando';

  // As falas das sessões anteriores (do servidor) e as desta, ainda
  // chegando. Enquanto captura, as locais são a verdade desta sessão.
  const falas = useMemo(() => {
    const salvas = dados?.falas || [];
    return [...salvas, ...falasLocais];
  }, [dados, falasLocais]);
  const metricas = useMemo(() => metricasDasFalas(falas), [falas]);
  const reuniaoAberta = Boolean(reuniao && SITUACOES_ABERTAS.includes(reuniao.situacao));
  const reuniaoFechada = Boolean(reuniao && !reuniaoAberta);

  if (carregando) {
    return (
      <div className="flex items-center gap-2 text-sm text-hipo-slate">
        <Loader2 size={16} className="animate-spin" /> Carregando a reunião…
      </div>
    );
  }
  if (!dados) {
    return <AlertMessage tipo="erro">{erro || 'Reunião não encontrada.'}</AlertMessage>;
  }

  const proporcao = metricas.proporcao_vendedor_pct;
  const bloqueio = !suporte.ok
    ? suporte.motivo
    : dados.motivo_bloqueio
      || (!dados.pode_capturar
        ? 'Só o anfitrião, um participante da reunião ou a gestão podem ligar a transcrição ao vivo.'
        : null);

  return (
    <div className="space-y-4">
      <PageHeader
        className="!mb-2"
        title="Reunião ao vivo"
        subtitle={`${dados.empresa || dados.titulo} · ${quando(dados.inicio)} · ${dados.duracao_min} min`}
        actions={(
          <>
            {dados.google_link && (
              <a
                href={dados.google_link}
                target="_blank"
                rel="noreferrer"
                className={
                  'inline-flex items-center gap-2 h-10 px-4 rounded-lg text-sm font-medium '
                  + 'bg-hipo-card text-hipo-ink border border-hipo-border hover:bg-hipo-bg'
                }
              >
                <ExternalLink size={16} /> Abrir o Meet
              </a>
            )}
            {(capturando || fase === 'encerrando') && (
              <Button
                variant="ghost" icon={Square}
                disabled={fase === 'encerrando' || registrando}
                onClick={encerrar}
                title="Para a transcrição sem registrar o desfecho da reunião."
              >
                Só parar
              </Button>
            )}
            {!capturando && fase !== 'encerrando' && !reuniaoFechada && (
              <Button
                icon={Mic}
                loading={fase === 'iniciando'}
                disabled={Boolean(bloqueio) || ocupado}
                onClick={iniciar}
              >
                Iniciar transcrição
              </Button>
            )}
            {reuniaoAberta && !pedindoProxima && (
              <>
                <Button
                  variant="secondary" icon={UserX}
                  disabled={ocupado || registrando}
                  onClick={() => finalizar('no_show')}
                  title="O cliente não apareceu: encerra a transcrição, cancela a tarefa e tira o evento da agenda."
                >
                  No-show
                </Button>
                <Button
                  variant={capturando || fase === 'encerrando' ? 'primary' : 'secondary'}
                  icon={CheckCircle2}
                  loading={registrando || fase === 'encerrando'}
                  disabled={ocupado || registrando}
                  onClick={() => finalizar('realizada')}
                  title="A reunião aconteceu: encerra a transcrição e conclui a tarefa."
                >
                  Realizada
                </Button>
              </>
            )}
          </>
        )}
      />

      <div className="flex flex-wrap gap-2" aria-label="Painel da reunião">
        <KpiInline
          label="Tempo"
          valor={inicio && (capturando || fase === 'encerrando') ? formatarCronometro(agora - inicio) : '—'}
          titulo="Tempo desde que a transcrição foi iniciada."
          icone={Timer}
          tom="bg-hipo-blueSoft text-hipo-blue"
        />
        <KpiInline
          label="Você"
          valor={metricas.palavras_vendedor}
          detalhe="palavras"
          titulo="Palavras transcritas do seu microfone."
          icone={User}
          tom="bg-hipo-blueSoft text-hipo-blue"
        />
        <KpiInline
          label="Cliente"
          valor={metricas.palavras_cliente}
          detalhe="palavras"
          titulo="Palavras transcritas do áudio da aba do Meet."
          icone={Users}
          tom="bg-hipo-successSoft text-hipo-success"
        />
        <KpiInline
          label="Sua fala"
          valor={proporcao == null ? '—' : `${proporcao}%`}
          titulo={`Parte das palavras que foram suas. Acima de ${LIMITE_FALA_VENDEDOR}%, pergunte mais e deixe o cliente falar.`}
          icone={Gauge}
          tom={proporcao != null && proporcao > LIMITE_FALA_VENDEDOR
            ? 'bg-hipo-warningSoft text-hipo-warning'
            : 'bg-hipo-successSoft text-hipo-success'}
        />
        {pendentes > 0 && (
          <KpiInline
            label="A enviar"
            valor={pendentes}
            titulo="Falas reconhecidas que ainda não chegaram ao HIPO. Saem a cada 10 segundos."
            icone={CloudUpload}
            tom="bg-hipo-warningSoft text-hipo-warning"
          />
        )}
      </div>

      {bloqueio && !capturando && <AlertMessage tipo="aviso">{bloqueio}</AlertMessage>}
      {erro && <AlertMessage tipo="erro">{erro}</AlertMessage>}
      {sucesso && <AlertMessage tipo="ok">{sucesso}</AlertMessage>}
      {avisos.map((a) => <AlertMessage key={a} tipo="aviso">{a}</AlertMessage>)}

      {pedindoProxima && reuniao && (
        <div ref={painelProximaRef} className="scroll-mt-4">
        <Card padding="sm" aria-label="Registrar a reunião" className="space-y-2">
          <AlertMessage tipo="aviso">
            Falta um passo para dar baixa: esta é a última tarefa aberta da
            oportunidade, e reunião realizada precisa da próxima tarefa.
            Preencha abaixo e clique em <strong>Registrar realizada</strong>.
          </AlertMessage>
          <PainelDesfecho
            key={reuniao.id}
            reuniao={{ ...reuniao, desfecho_sugerido: 'realizada' }}
            usuarios={usuarios}
            ocupado={registrando}
            onVoltar={() => setPedindoProxima(false)}
            onRegistrar={gravarDesfecho}
          />
        </Card>
        </div>
      )}

      <div className="grid gap-4 lg:grid-cols-3">
        <Card padding="sm" className="lg:col-span-2 flex flex-col min-h-[24rem]">
          <h2 className="text-sm font-medium text-hipo-ink mb-2">Conversa</h2>
          {falas.length === 0 && !capturando
            ? <Instrucoes />
            : (
              <ol
                aria-label="Transcrição ao vivo"
                className="flex-1 max-h-[60vh] overflow-y-auto space-y-2 pr-1"
              >
                {falas.map((f) => (
                  <li key={`${f.sessao_id}-${f.seq}`} className="flex gap-2 text-sm">
                    <span className="shrink-0 w-14 text-[11px] text-hipo-muted pt-0.5">
                      {horaSegundos(f.inicio)}
                    </span>
                    <span className={
                      'shrink-0 w-14 text-xs font-medium pt-0.5 '
                      + (f.canal === 'vendedor' ? 'text-hipo-blue' : 'text-hipo-success')
                    }
                    >
                      {ROTULO_CANAL[f.canal]}
                    </span>
                    <span className="text-hipo-ink">{f.texto}</span>
                  </li>
                ))}
                {CANAIS.filter((c) => parciais[c]).map((c) => (
                  <li key={`parcial-${c}`} className="flex gap-2 text-sm" data-testid={`parcial-${c}`}>
                    <span className="shrink-0 w-14" />
                    <span className="shrink-0 w-14 text-xs text-hipo-muted pt-0.5">{ROTULO_CANAL[c]}</span>
                    <span className="italic text-hipo-muted">{parciais[c]}</span>
                  </li>
                ))}
                <li ref={fimDaListaRef} aria-hidden="true" />
              </ol>
            )}
        </Card>

        <div className="space-y-4">
          <Card padding="sm">
            <h2 className="text-sm font-medium text-hipo-ink mb-2">Captura</h2>
            <ul className="space-y-1.5 text-sm">
              <EstadoCanal icone={estados.vendedor === 'falhou' ? MicOff : Mic}
                rotulo="Seu microfone" estado={estados.vendedor} />
              <EstadoCanal icone={MonitorSpeaker} rotulo="Aba do Meet" estado={estados.cliente} />
            </ul>
            {dados.sessoes.length > 0 && (
              <p className="mt-2 text-xs text-hipo-muted">
                {dados.sessoes.length === 1
                  ? '1 captura anterior nesta reunião.'
                  : `${dados.sessoes.length} capturas anteriores nesta reunião.`}
              </p>
            )}
          </Card>

          {reuniaoFechada && (
            <Card padding="sm" aria-label="Desfecho da reunião">
              <h2 className="text-sm font-medium text-hipo-ink">Desfecho</h2>
              <DesfechoRegistrado reuniao={reuniao} />
            </Card>
          )}

          {dados.comparacao && (
            <Card padding="sm" aria-label="Comparação com o Meet">
              <h2 className="text-sm font-medium text-hipo-ink mb-1">Comparação com o Meet</h2>
              <p className="text-2xl font-semibold text-hipo-ink">
                {dados.comparacao.cobertura_pct}%
              </p>
              <p className="text-xs text-hipo-slate">
                das {dados.comparacao.palavras_meet} palavras da transcrição do Meet
                também saíram aqui ({dados.comparacao.palavras_ao_vivo} palavras ao vivo).
              </p>
            </Card>
          )}
        </div>
      </div>
    </div>
  );
}

function EstadoCanal({ icone: Icone, rotulo, estado }) {
  const cfg = ESTADO_CANAL[estado] || ESTADO_CANAL.desligado;
  return (
    <li className="flex items-center gap-2">
      <Icone size={14} className="text-hipo-slate" aria-hidden="true" />
      <span className="text-hipo-ink">{rotulo}</span>
      <Badge tone={cfg.tom} className="ml-auto">{cfg.texto}</Badge>
    </li>
  );
}

function Instrucoes() {
  return (
    <ol className="list-decimal pl-5 space-y-1.5 text-sm text-hipo-slate">
      <li>Abra a reunião no Meet, em outra aba do Chrome.</li>
      <li>
        Volte aqui e clique em <strong className="text-hipo-ink">Iniciar transcrição</strong>.
        Na janela do Chrome, escolha a <strong className="text-hipo-ink">aba do Meet</strong> e
        deixe marcado <strong className="text-hipo-ink">Compartilhar áudio da guia</strong>.
      </li>
      <li>Permita o microfone quando o Chrome pedir.</li>
      <li>
        Deixe esta aba aberta até o fim. Ao terminar a call, clique em Encerrar — as falas
        ficam salvas na tarefa da reunião.
      </li>
    </ol>
  );
}
