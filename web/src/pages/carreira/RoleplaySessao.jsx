// web/src/pages/carreira/RoleplaySessao.jsx
//
// Duas telas do Roleplay, cada uma com rota própria:
//
//   /carreira/roleplay/treino/:cenarioId  a sessão: pré-sala (briefing,
//       termo, microfone), conversa por voz com a IA e encerramento;
//   /carreira/roleplay/sessoes/:sessaoId  o resultado: duração, fala,
//       gravação e transcrição (a nota é a RP-2).
//
// Durante a conversa a transcrição NÃO aparece: ninguém lê o roteiro em
// voz alta. O áudio vai direto do navegador para o Gemini (vozRealtime);
// o HIPO entra no começo (token), em cada troca de conexão (token novo)
// e no fim (gravação + transcrição + uso).
//
// `motorAudio` e `criarVoz` são injetáveis: os testes trocam o microfone
// e o WebSocket por dublês.

import { useCallback, useEffect, useRef, useState } from 'react';
import { useNavigate, useParams, useSearchParams } from 'react-router-dom';
import {
  ArrowLeft, Clock, Headphones, Mic, PhoneOff, Repeat, Volume2,
} from 'lucide-react';
import api from '../../api';
import PageHeader from '../../components/ui/PageHeader';
import Card, { CardHeader } from '../../components/ui/Card';
import Badge from '../../components/ui/Badge';
import Button from '../../components/ui/Button';
import AlertMessage from '../../components/ui/AlertMessage';
import { mensagemDeErro } from '../../components/crm/tarefaComum';
import * as audioPadrao from '../../components/carreira/audioRoleplay';
import { anotarTurno, criarSessaoVoz, somarUso } from '../../components/carreira/vozRealtime';
import { DIFICULDADE, MOTIVO_FIM, dataHoraBr, duracaoBr } from './Roleplay';

function relogio(seg) {
  return `${String(Math.floor(seg / 60)).padStart(2, '0')}:${String(seg % 60).padStart(2, '0')}`;
}

function Barra({ rotulo, valor }) {
  return (
    <div>
      <p className="text-xs text-hipo-slate mb-1">{rotulo}</p>
      <div className="h-2 rounded-full bg-hipo-bg overflow-hidden">
        <div className="h-full bg-hipo-success transition-[width] duration-75" style={{ width: `${Math.round(valor * 100)}%` }} />
      </div>
    </div>
  );
}

export default function RoleplayTreino({ motorAudio = audioPadrao, criarVoz = criarSessaoVoz }) {
  const { cenarioId } = useParams();
  const navigate = useNavigate();
  const [tela, setTela] = useState(null);
  const [erro, setErro] = useState('');
  const [aceite, setAceite] = useState(false);
  const [fase, setFase] = useState('pre'); // pre | conectando | conversa | encerrando
  const [status, setStatus] = useState('');
  const [segundos, setSegundos] = useState(0);
  const [nivelMic, setNivelMic] = useState(0);
  const [nivelIa, setNivelIa] = useState(0);
  const [reconexoes, setReconexoes] = useState(0);
  const ref = useRef({});

  useEffect(() => {
    api.get('/carreira/roleplay')
      .then(({ data }) => setTela(data))
      .catch((e) => setErro(mensagemDeErro(e, 'Não foi possível carregar o roleplay.')));
  }, []);

  // Fechar a aba no meio da conversa perde a gravação: o navegador pergunta antes.
  useEffect(() => {
    if (fase !== 'conversa') return undefined;
    const aviso = (e) => { e.preventDefault(); e.returnValue = ''; };
    window.addEventListener('beforeunload', aviso);
    return () => window.removeEventListener('beforeunload', aviso);
  }, [fase]);

  useEffect(() => () => { clearInterval(ref.current.relogio); }, []);

  const encerrar = useCallback(async (motivo = 'encerrou') => {
    const s = ref.current;
    if (s.encerrando || !s.sessaoId) return;
    s.encerrando = true;
    clearInterval(s.relogio);
    setFase('encerrando');
    setStatus('Salvando a gravação…');
    try { s.voz?.encerrar(); } catch { /* já fechada */ }
    let gravacao = null;
    try { gravacao = await s.audio?.parar(); } catch { /* sem gravação */ }
    const lat = s.latencias || [];
    const dados = {
      transcricao: s.turnos || [],
      tokens: s.uso || {},
      duracao_s: Math.round((Date.now() - s.inicio) / 1000),
      motivo_fim: motivo,
      reconexoes: s.voz?.reconexoes ?? 0,
      latencia_media_ms: lat.length ? Math.round(lat.reduce((a, b) => a + b, 0) / lat.length) : null,
    };
    const form = new FormData();
    form.append('dados', JSON.stringify(dados));
    if (gravacao && gravacao.size) form.append('audio', gravacao, 'roleplay.webm');
    try {
      await api.post(`/carreira/roleplay/sessoes/${s.sessaoId}/encerrar`, form);
      navigate(`/carreira/roleplay/sessoes/${s.sessaoId}`, { replace: true });
    } catch (e) {
      s.encerrando = false;
      setErro(mensagemDeErro(e, 'Não foi possível salvar o roleplay.') + ' Tente encerrar de novo.');
      setFase('conversa');
    }
  }, [navigate]);

  async function comecar() {
    setErro('');
    if (!motorAudio.navegadorSuporta()) {
      setErro('Este navegador não grava áudio do jeito que o roleplay precisa. Use o Chrome no computador.');
      return;
    }
    setFase('conectando');
    setStatus('Conectando…');
    try {
      if (tela.consentimento_pendente) {
        await api.post('/carreira/roleplay/consentimento');
      }
      const { data } = await api.post('/carreira/roleplay/sessoes', { cenario_id: cenarioId });
      const s = ref.current;
      Object.assign(s, {
        sessaoId: data.sessao_id, turnos: [], uso: {}, latencias: [], encerrando: false,
        fimFala: null, inicio: Date.now(),
      });
      s.audio = await motorAudio.iniciarAudio({
        onMicrofone: (b64) => s.voz?.enviarAudio(b64),
        onNivelMic: setNivelMic,
        onNivelIa: setNivelIa,
        onFimDaFala: () => { s.fimFala = performance.now(); },
      });
      s.voz = criarVoz({
        wsUrl: data.ws_url,
        token: data.token,
        modelo: data.modelo,
        obterTokenNovo: async () => (await api.post(`/carreira/roleplay/sessoes/${data.sessao_id}/token`)).data.token,
        eventos: {
          onAberto: () => { setFase('conversa'); setStatus('Em conversa'); },
          onAudio: (b64) => {
            if (s.fimFala) { s.latencias.push(performance.now() - s.fimFala); s.fimFala = null; }
            s.audio.tocar(b64);
          },
          onInterrompido: () => s.audio.interromper(),
          onTranscricao: (quem, texto) => anotarTurno(s.turnos, quem, texto, Date.now() - s.inicio),
          onUso: (u) => somarUso(s.uso, u),
          onReconectando: () => setStatus('Reconectando…'),
          onReconectado: (n) => { setReconexoes(n); setStatus('Em conversa'); },
          onFim: (motivo) => { if (motivo !== 'encerrou') encerrar(motivo); },
        },
      });
      s.voz.conectar();
      s.relogio = setInterval(() => {
        const seg = Math.floor((Date.now() - s.inicio) / 1000);
        setSegundos(seg);
        if (seg >= data.duracao_max_s) encerrar('tempo');
      }, 500);
    } catch (e) {
      const s = ref.current;
      try { await s.audio?.parar(); } catch { /* nada a parar */ }
      if (s.sessaoId) {
        // A sessão foi aberta mas o áudio/conexão falhou: fecha sem gravação.
        try {
          await api.post(`/carreira/roleplay/sessoes/${s.sessaoId}/encerrar`, (() => {
            const f = new FormData(); f.append('dados', JSON.stringify({ motivo_fim: 'queda' })); return f;
          })());
        } catch { /* fica abandonada sozinha */ }
      }
      ref.current = {};
      setFase('pre');
      setErro(e?.name === 'NotAllowedError'
        ? 'O navegador bloqueou o microfone. Libere o microfone para este site e tente de novo.'
        : mensagemDeErro(e, 'Não foi possível começar o roleplay.'));
    }
  }

  if (erro && !tela) {
    return <div className="max-w-3xl mx-auto"><AlertMessage tipo="erro">{erro}</AlertMessage></div>;
  }
  if (!tela) return <p className="text-sm text-hipo-slate p-4">Carregando…</p>;

  const cenario = tela.cenarios.find((c) => c.id === cenarioId);
  if (!cenario) {
    return (
      <div className="max-w-3xl mx-auto space-y-4">
        <AlertMessage tipo="erro">Cenário não encontrado para o seu cargo.</AlertMessage>
        <Button variant="secondary" icon={ArrowLeft} onClick={() => navigate('/carreira/roleplay')}>Voltar</Button>
      </div>
    );
  }
  const podeComecar = tela.pode_treinar && tela.disponivel && (!tela.consentimento_pendente || aceite);

  if (fase === 'pre') {
    return (
      <div className="max-w-3xl mx-auto space-y-5">
        <PageHeader
          title={cenario.titulo}
          subtitle={`${cenario.bloco_rotulo} · ${DIFICULDADE[cenario.dificuldade]} · ${cenario.duracao_alvo_min} min`}
          actions={<Button variant="ghost" icon={ArrowLeft} onClick={() => navigate('/carreira/roleplay')}>Voltar</Button>}
        />
        {erro && <AlertMessage tipo="erro">{erro}</AlertMessage>}
        {!tela.liberado && <AlertMessage tipo="aviso">{tela.motivo}</AlertMessage>}
        {tela.liberado && !tela.disponivel && <AlertMessage tipo="aviso">{tela.indisponivel_motivo}</AlertMessage>}
        <Card>
          <CardHeader title="Objetivo" />
          <p className="text-sm text-hipo-ink">{cenario.objetivo}</p>
        </Card>
        <Card>
          <CardHeader title="Antes da reunião" hint="O que o SDR passou e o que a pesquisa achou." />
          <p className="text-sm text-hipo-ink whitespace-pre-line" data-testid="briefing">{cenario.briefing}</p>
        </Card>
        {tela.consentimento_pendente && (
          <Card>
            <CardHeader title="Gravação" />
            <p className="text-sm text-hipo-slate">{tela.termo.texto}</p>
            <label className="mt-3 flex items-center gap-2 text-sm text-hipo-ink">
              <input type="checkbox" checked={aceite} onChange={(e) => setAceite(e.target.checked)} />
              Li e concordo com a gravação deste treino.
            </label>
          </Card>
        )}
        <div className="flex flex-wrap items-center gap-3">
          <Button size="lg" icon={Mic} disabled={!podeComecar} onClick={comecar}>Começar</Button>
          <span className="text-sm text-hipo-slate inline-flex items-center gap-1.5">
            <Headphones size={16} aria-hidden="true" /> Use fone de ouvido. Você começa a conversa.
          </span>
        </div>
      </div>
    );
  }

  return (
    <div className="max-w-3xl mx-auto space-y-5" data-testid="sala-roleplay">
      <PageHeader title={cenario.titulo} subtitle={cenario.bloco_rotulo} />
      {erro && <AlertMessage tipo="erro">{erro}</AlertMessage>}
      <Card>
        <div className="flex flex-wrap items-center justify-between gap-4">
          <div className="flex items-center gap-3">
            <Badge tone={status === 'Em conversa' ? 'success' : 'warning'}>{status}</Badge>
            <span className="text-kpi text-hipo-ink tabular-nums" aria-label="tempo">{relogio(segundos)}</span>
            <span className="text-xs text-hipo-slate">alvo {cenario.duracao_alvo_min} min</span>
          </div>
          <Button
            variant="danger"
            icon={PhoneOff}
            loading={fase === 'encerrando'}
            disabled={fase === 'conectando'}
            onClick={() => encerrar('encerrou')}
          >
            Encerrar
          </Button>
        </div>
        <div className="grid gap-3 sm:grid-cols-2 mt-5">
          <Barra rotulo="Seu microfone" valor={nivelMic} />
          <Barra rotulo="Cliente (IA)" valor={nivelIa} />
        </div>
        {reconexoes > 0 && (
          <p className="text-xs text-hipo-slate mt-3 inline-flex items-center gap-1">
            <Repeat size={12} aria-hidden="true" /> {reconexoes} troca(s) de conexão
          </p>
        )}
      </Card>
      <p className="text-sm text-hipo-slate">
        A transcrição aparece no resultado, depois de encerrar. Fale normalmente; você pode interromper o cliente.
      </p>
    </div>
  );
}

export function ResultadoRoleplay() {
  const { sessaoId } = useParams();
  const [params] = useSearchParams();
  const navigate = useNavigate();
  const [s, setS] = useState(null);
  const [erro, setErro] = useState('');
  const [audioUrl, setAudioUrl] = useState('');
  const usuarioId = params.get('usuario_id');
  const voltar = `/carreira/roleplay${usuarioId ? `?usuario_id=${encodeURIComponent(usuarioId)}` : ''}`;

  useEffect(() => {
    api.get(`/carreira/roleplay/sessoes/${sessaoId}`)
      .then(({ data }) => setS(data))
      .catch((e) => setErro(mensagemDeErro(e, 'Não foi possível abrir o roleplay.')));
  }, [sessaoId]);

  async function ouvir() {
    try {
      const { data } = await api.get(`/carreira/roleplay/sessoes/${sessaoId}/audio`);
      setAudioUrl(data.url);
    } catch (e) {
      setErro(mensagemDeErro(e, 'Não foi possível abrir a gravação.'));
    }
  }

  if (erro && !s) return <div className="max-w-3xl mx-auto"><AlertMessage tipo="erro">{erro}</AlertMessage></div>;
  if (!s) return <p className="text-sm text-hipo-slate p-4">Carregando…</p>;

  return (
    <div className="max-w-3xl mx-auto space-y-5">
      <PageHeader
        title={s.cenario_titulo}
        subtitle={`${s.bloco_rotulo || 'Roleplay'} · ${dataHoraBr(s.iniciada_em)}${s.modo_leitura ? ' · modo leitura' : ''}`}
        actions={<Button variant="secondary" icon={ArrowLeft} onClick={() => navigate(voltar)}>Roleplay</Button>}
      />
      {erro && <AlertMessage tipo="erro">{erro}</AlertMessage>}
      <Card>
        <div className="flex flex-wrap gap-x-6 gap-y-2 text-sm">
          <span className="inline-flex items-center gap-1.5"><Clock size={14} aria-hidden="true" /> {duracaoBr(s.duracao_s)}</span>
          <span>Sua fala: <b>{s.fala_executivo_pct ?? '—'}{s.fala_executivo_pct !== null ? '%' : ''}</b></span>
          <Badge tone={s.motivo_fim === 'encerrou' ? 'success' : 'warning'}>
            {s.status === 'abandonada' ? 'Não encerrado' : MOTIVO_FIM[s.motivo_fim] || 'Encerrado'}
          </Badge>
          {!s.conta_media && <Badge>Fora da média</Badge>}
        </div>
        <p className="text-sm text-hipo-slate mt-3">
          A nota contra o Roteiro de Vendas (itens de 0 a 2, com o trecho da sua fala) chega na próxima versão.
          A gravação e a transcrição já ficam guardadas para isso.
        </p>
        {s.tem_audio && (
          <div className="mt-4">
            {audioUrl
              ? <audio controls src={audioUrl} className="w-full" data-testid="player-roleplay" />
              : <Button variant="secondary" icon={Volume2} onClick={ouvir}>Ouvir gravação</Button>}
          </div>
        )}
      </Card>
      <Card padding="none">
        <div className="px-5 pt-5"><CardHeader title="Transcrição" /></div>
        {s.transcricao?.length ? (
          <ol className="px-5 pb-5 space-y-2">
            {s.transcricao.map((t, i) => (
              <li key={i} className="text-sm">
                <span className={`font-semibold ${t.quem === 'cliente' ? 'text-hipo-warning' : 'text-hipo-blue'}`}>
                  {t.quem === 'cliente' ? 'Cliente' : (s.modo_leitura ? 'Executivo' : 'Você')}
                </span>
                <span className="text-xs text-hipo-slate"> · {relogio(Math.floor((t.t_ms || 0) / 1000))}</span>
                <span className="text-hipo-ink"> — {t.texto}</span>
              </li>
            ))}
          </ol>
        ) : (
          <p className="px-5 pb-5 text-sm text-hipo-slate">Sem transcrição.</p>
        )}
      </Card>
    </div>
  );
}
