// web/src/components/crm/TranscricaoReuniao.jsx
//
// A transcrição da reunião (Google Meet), dentro da tarefa.
//
// ── Onde aparece ─────────────────────────────────────────────────────
// Nos mesmos três lugares dos anexos: o modal da tarefa (tela de
// Tarefas), a aba de tarefas da oportunidade e o formulário da reunião na
// Agenda. É a tarefa que as três telas têm na mão, e é nela que o texto
// "fica salvo" — quem abre a tarefa amanhã encontra a conversa ali.
//
// ── O resumo vem antes do texto ──────────────────────────────────────
// Quem abre a tarefa logo depois da call quer registrar o desfecho e
// agendar a próxima. Para isso servem o resumo e os próximos passos; a
// transcrição inteira é consulta, e fica fechada até alguém pedir. Uma
// hora de conversa aberta por padrão empurraria o painel de desfecho para
// fora da tela — justamente a ação que a tela existe para facilitar.
//
// ── Próximo passo é sugestão ─────────────────────────────────────────
// A lista vem da IA lendo a conversa. Ela NÃO vira tarefa sozinha: quem
// agenda a próxima continua sendo a pessoa, no painel de desfecho logo
// abaixo. A tela diz isso em uma linha.
//
// ── Some quando não tem o que dizer ──────────────────────────────────
// Reunião sem Meet (presencial, Zoom) ou servidor sem o Google ligado:
// nenhum bloco. Um "sem transcrição" em toda visita presencial ensinaria
// a ignorar o bloco na reunião em que ele importa.

import { useCallback, useEffect, useState } from 'react';
import {
  Mic, RefreshCw, ExternalLink, ChevronDown, ChevronRight, Sparkles, Loader2,
} from 'lucide-react';

import api from '../../api';
import AlertMessage from '../ui/AlertMessage';
import { mensagemDeErro } from './tarefaComum';

const COR_STATUS = {
  pronta: 'bg-hipo-successSoft text-hipo-success border-hipo-successBorder',
  aguardando: 'bg-hipo-warningSoft text-hipo-warning border-hipo-warningBorder',
  nao_iniciada: 'bg-hipo-bg text-hipo-slate border-hipo-border',
  indisponivel: 'bg-hipo-bg text-hipo-muted border-hipo-border',
};

const ROTULO_PADRAO = {
  nao_iniciada: 'Depois da reunião',
};

const BOTAO_PEQUENO =
  'inline-flex items-center gap-1 px-2 py-1 rounded-md text-xs ' +
  'border border-hipo-border bg-hipo-card text-hipo-slate ' +
  'hover:bg-hipo-blueSoft hover:text-hipo-blue hover:border-hipo-blue ' +
  'disabled:opacity-50 transition-colors ' +
  'focus:outline-none focus-visible:ring-2 focus-visible:ring-hipo-blue';

/**
 * @param tarefa  a tarefa da reunião (precisa de `id`)
 */
export default function TranscricaoReuniao({ tarefa }) {
  const [dados, setDados] = useState(null);
  const [carregando, setCarregando] = useState(true);
  const [ocupado, setOcupado] = useState(null);   // 'buscar' | 'resumo'
  const [erro, setErro] = useState(null);
  const [aberta, setAberta] = useState(false);

  const url = `/crm/agenda/tarefas/${tarefa.id}/transcricao`;

  const carregar = useCallback(async () => {
    setCarregando(true);
    try {
      // Resposta fora do formato não pode derrubar o modal em que o bloco
      // vive — mesma cautela da galeria de anexos.
      const resposta = await api.get(url);
      const data = resposta?.data;
      setDados(data && typeof data === 'object' && data.status ? data : null);
    } catch (err) {
      // 404 = a tarefa não é reunião da agenda. Não é erro para a tela:
      // simplesmente não há o que mostrar.
      if (err?.response?.status !== 404) {
        setErro(mensagemDeErro(err, 'Não foi possível carregar a transcrição.'));
      }
      setDados(null);
    } finally {
      setCarregando(false);
    }
  }, [url]);

  useEffect(() => { carregar(); }, [carregar]);

  async function acionar(tipo) {
    setOcupado(tipo);
    setErro(null);
    try {
      const { data } = await api.post(tipo === 'buscar' ? `${url}/buscar` : `${url}/resumo`);
      setDados(data);
    } catch (err) {
      setErro(mensagemDeErro(
        err,
        tipo === 'buscar'
          ? 'Não foi possível buscar a transcrição.'
          : 'Não foi possível gerar o resumo.',
      ));
    } finally {
      setOcupado(null);
    }
  }

  if (carregando) return null;
  if (!dados) {
    return erro ? <AlertMessage tipo="erro">{erro}</AlertMessage> : null;
  }
  if (dados.status === 'sem_meet') return null;
  if (!dados.google_configurado && dados.status !== 'pronta') return null;

  const pronta = dados.status === 'pronta';
  const rotulo = dados.rotulo || ROTULO_PADRAO[dados.status] || dados.status;
  const passos = dados.proximos_passos || [];
  // O aviso de "ligue à mão" só faz sentido ANTES de a conversa acabar
  // sem texto: depois de pronta, ou de desistida, ele não muda mais nada.
  const avisoAuto = dados.transcricao_auto_erro
    && ['nao_iniciada', 'aguardando'].includes(dados.status);

  return (
    <section
      aria-label="Transcrição da reunião"
      className="rounded-lg border border-hipo-border bg-hipo-bg/40 p-2.5 space-y-2"
    >
      <div className="flex items-center gap-2 flex-wrap">
        <Mic size={13} className="shrink-0 text-hipo-slate" aria-hidden="true" />
        <span className="text-xs font-medium text-hipo-ink">Transcrição</span>
        <span
          className={
            'text-[11px] px-1.5 py-0.5 rounded border ' +
            (COR_STATUS[dados.status] || COR_STATUS.nao_iniciada)
          }
        >
          {rotulo}
        </span>

        <span className="ml-auto flex items-center gap-1.5">
          {dados.documento_url && (
            <a
              href={dados.documento_url}
              target="_blank"
              rel="noopener noreferrer"
              className={BOTAO_PEQUENO}
            >
              <ExternalLink size={12} aria-hidden="true" />
              Google Docs
            </a>
          )}
          {dados.pode_buscar && (
            <button
              type="button"
              className={BOTAO_PEQUENO}
              disabled={Boolean(ocupado)}
              onClick={() => acionar('buscar')}
            >
              {ocupado === 'buscar'
                ? <Loader2 size={12} className="animate-spin" aria-hidden="true" />
                : <RefreshCw size={12} aria-hidden="true" />}
              {ocupado === 'buscar' ? 'Buscando…' : 'Buscar agora'}
            </button>
          )}
        </span>
      </div>

      {erro && <AlertMessage tipo="erro">{erro}</AlertMessage>}

      {!pronta && dados.motivo && (
        <p className="text-xs text-hipo-muted">{dados.motivo}</p>
      )}

      {!pronta && dados.erro && (
        <AlertMessage tipo="aviso">{dados.erro}</AlertMessage>
      )}

      {avisoAuto && (
        <AlertMessage tipo="aviso">
          A transcrição automática não foi ligada nesta sala ({dados.transcricao_auto_erro}).
          Na call, ligue em Atividades → Transcrição, senão a reunião termina sem texto.
        </AlertMessage>
      )}

      {pronta && (
        <>
          {dados.resumo && (
            <div className="space-y-1.5">
              <p className="flex items-center gap-1 text-xs font-medium text-hipo-ink">
                <Sparkles size={12} className="text-hipo-blue" aria-hidden="true" />
                Resumo
              </p>
              <p className="text-sm text-hipo-slate">{dados.resumo}</p>
              {passos.length > 0 && (
                <>
                  <p className="text-xs font-medium text-hipo-ink pt-1">
                    Próximos passos combinados
                  </p>
                  <ul className="list-disc pl-5 text-sm text-hipo-slate space-y-0.5">
                    {passos.map((p, i) => <li key={i}>{p}</li>)}
                  </ul>
                </>
              )}
              <p className="text-[11px] text-hipo-muted">
                Sugestão da IA a partir da conversa — confira antes de registrar o desfecho.
              </p>
            </div>
          )}

          {dados.resumo_erro && (
            <AlertMessage tipo="aviso">
              <span>{dados.resumo_erro}</span>
              {dados.pode_resumir && dados.ia_configurada && (
                <button
                  type="button"
                  className={`${BOTAO_PEQUENO} ml-2`}
                  disabled={Boolean(ocupado)}
                  onClick={() => acionar('resumo')}
                >
                  {ocupado === 'resumo'
                    ? <Loader2 size={12} className="animate-spin" aria-hidden="true" />
                    : <Sparkles size={12} aria-hidden="true" />}
                  {ocupado === 'resumo' ? 'Gerando…' : 'Gerar resumo de novo'}
                </button>
              )}
            </AlertMessage>
          )}

          {!dados.resumo && !dados.resumo_erro && dados.ia_configurada && (
            <button
              type="button"
              className={BOTAO_PEQUENO}
              disabled={Boolean(ocupado)}
              onClick={() => acionar('resumo')}
            >
              <Sparkles size={12} aria-hidden="true" />
              {ocupado === 'resumo' ? 'Gerando…' : 'Gerar resumo'}
            </button>
          )}

          <button
            type="button"
            aria-expanded={aberta}
            onClick={() => setAberta((v) => !v)}
            className={
              'flex items-center gap-1 text-xs text-hipo-blue hover:underline ' +
              'focus:outline-none focus-visible:ring-2 focus-visible:ring-hipo-blue rounded'
            }
          >
            {aberta
              ? <ChevronDown size={12} aria-hidden="true" />
              : <ChevronRight size={12} aria-hidden="true" />}
            {aberta ? 'Esconder a conversa' : `Ver a conversa (${dados.falas} falas)`}
          </button>

          {aberta && (
            <pre
              data-testid="texto-transcricao"
              className={
                'max-h-72 overflow-y-auto whitespace-pre-wrap break-words ' +
                'rounded-md border border-hipo-border bg-hipo-card p-2 ' +
                'text-xs leading-relaxed text-hipo-ink font-sans'
              }
            >
              {dados.texto}
            </pre>
          )}
        </>
      )}
    </section>
  );
}
