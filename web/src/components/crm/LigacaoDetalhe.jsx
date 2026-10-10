// web/src/components/crm/LigacaoDetalhe.jsx
//
// Uma ligação aberta (entrega 056): o resumo e os próximos passos que a IA
// tirou da conversa, a conversa inteira (cada lado com a sua cor — o
// gravador grava em dois canais, então "quem falou" é exato) e o áudio.
//
// Busca o próprio detalhe. Enquanto a ligação está em andamento (subindo,
// transcrevendo), oferece "Atualizar" — a mesma passada do timer.

import { useCallback, useEffect, useState } from 'react';
import { Headphones, Loader2, RefreshCw, Sparkles } from 'lucide-react';

import api from '../../api';
import AlertMessage from '../ui/AlertMessage';
import { mensagemDeErro } from './contatoComum';
import { EM_ANDAMENTO, dataHoraCurta } from './ligacoes';

const BOTAO_PEQUENO =
  'inline-flex items-center gap-1 px-2 py-1 rounded-md text-xs ' +
  'border border-hipo-border bg-hipo-card text-hipo-slate ' +
  'hover:bg-hipo-blueSoft hover:text-hipo-blue hover:border-hipo-blue ' +
  'disabled:opacity-50 transition-colors ' +
  'focus:outline-none focus-visible:ring-2 focus-visible:ring-hipo-blue';

function hora(iso) {
  if (!iso) return '';
  return new Date(iso).toLocaleTimeString('pt-BR', {
    timeZone: 'America/Sao_Paulo', hour: '2-digit', minute: '2-digit', second: '2-digit',
  });
}

// `versao`: o status que a LISTA conhece. A aba se atualiza sozinha enquanto
// há ligação em andamento; quando o status muda lá, o painel aberto busca o
// detalhe de novo — senão a etiqueta diria "Transcrita" e o painel seguiria
// mostrando "Transcrevendo", sem a conversa.
export default function LigacaoDetalhe({ ligacaoId, versao, onMudou }) {
  const [dados, setDados] = useState(null);
  const [erro, setErro] = useState(null);
  const [ocupado, setOcupado] = useState(null);
  const [audio, setAudio] = useState(null);

  const carregar = useCallback(async () => {
    try {
      const { data } = await api.get(`/crm/ligacoes/${ligacaoId}`);
      setDados(data);
      setErro(null);
    } catch (err) {
      setErro(mensagemDeErro(err, 'Não foi possível abrir a ligação.'));
    }
  }, [ligacaoId]);

  useEffect(() => { carregar(); }, [carregar, versao]);

  async function acionar(acao) {
    setOcupado(acao);
    setErro(null);
    try {
      const { data } = await api.post(`/crm/ligacoes/${ligacaoId}/${acao}`);
      setDados((d) => ({ ...d, ...data }));
      onMudou?.(data);
    } catch (err) {
      setErro(mensagemDeErro(err, 'Não foi possível concluir a ação.'));
    } finally {
      setOcupado(null);
    }
  }

  async function ouvir() {
    setOcupado('audio');
    setErro(null);
    try {
      const { data } = await api.get(`/crm/ligacoes/${ligacaoId}/audio`);
      setAudio(data.url);
    } catch (err) {
      setErro(mensagemDeErro(err, 'Não foi possível abrir o áudio.'));
    } finally {
      setOcupado(null);
    }
  }

  if (!dados) {
    return erro
      ? <AlertMessage tipo="erro">{erro}</AlertMessage>
      : <p className="text-xs text-hipo-muted">Carregando…</p>;
  }

  const pronta = dados.status === 'pronta';
  const andando = EM_ANDAMENTO.includes(dados.status);
  const passos = dados.proximos_passos || [];
  const conversa = dados.transcricao || [];

  return (
    <div className="space-y-2.5" data-testid="ligacao-detalhe">
      <div className="flex flex-wrap items-center gap-1.5">
        {dados.tem_audio && !audio && (
          <button type="button" className={BOTAO_PEQUENO} onClick={ouvir} disabled={Boolean(ocupado)}>
            {ocupado === 'audio'
              ? <Loader2 size={12} className="animate-spin" aria-hidden="true" />
              : <Headphones size={12} aria-hidden="true" />}
            Ouvir
          </button>
        )}
        {andando && (
          <button type="button" className={BOTAO_PEQUENO} onClick={() => acionar('atualizar')} disabled={Boolean(ocupado)}>
            {ocupado === 'atualizar'
              ? <Loader2 size={12} className="animate-spin" aria-hidden="true" />
              : <RefreshCw size={12} aria-hidden="true" />}
            Atualizar
          </button>
        )}
        {dados.audio_removido_em && (
          <span className="text-[11px] text-hipo-muted">
            Áudio apagado em {dataHoraCurta(dados.audio_removido_em)} (prazo de guarda); a transcrição fica.
          </span>
        )}
      </div>

      {audio && (
        <audio controls autoPlay src={audio} className="w-full h-9" />
      )}

      {erro && <AlertMessage tipo="erro">{erro}</AlertMessage>}
      {dados.erro && <AlertMessage tipo="aviso">{dados.erro}</AlertMessage>}

      {dados.status === 'discando' && (
        <p className="text-xs text-hipo-muted">
          A gravação chega alguns segundos depois de desligar, se o gravador estiver ligado nesta máquina.
        </p>
      )}
      {dados.status === 'sem_gravacao' && (
        <p className="text-xs text-hipo-muted">
          O clique foi registrado, mas nenhuma gravação chegou — o gravador estava desligado ou a ligação
          não foi feita pelo Vivo Voz Negócio neste computador.
        </p>
      )}
      {dados.status === 'sem_fala' && (
        <p className="text-xs text-hipo-muted">A gravação não tem conversa (só chamou, ou caiu na caixa postal muda).</p>
      )}

      {pronta && dados.resumo && (
        <div className="space-y-1.5">
          <p className="flex items-center gap-1 text-xs font-medium text-hipo-ink">
            <Sparkles size={12} className="text-hipo-blue" aria-hidden="true" />
            Resumo
          </p>
          <p className="text-sm text-hipo-slate">{dados.resumo}</p>
          {passos.length > 0 && (
            <>
              <p className="text-xs font-medium text-hipo-ink pt-1">Próximos passos combinados</p>
              <ul className="list-disc pl-5 text-sm text-hipo-slate space-y-0.5">
                {passos.map((p, i) => <li key={i}>{p}</li>)}
              </ul>
            </>
          )}
          <p className="text-[11px] text-hipo-muted">
            Sugestão da IA a partir da conversa — confira antes de registrar o resultado da tarefa.
          </p>
        </div>
      )}

      {pronta && dados.resumo_erro && (
        <AlertMessage tipo="aviso">
          <span>{dados.resumo_erro}</span>
          {dados.pode_alterar && (
            <button
              type="button"
              className={`${BOTAO_PEQUENO} ml-2`}
              disabled={Boolean(ocupado)}
              onClick={() => acionar('resumo')}
            >
              <Sparkles size={12} aria-hidden="true" />
              {ocupado === 'resumo' ? 'Gerando…' : 'Gerar resumo de novo'}
            </button>
          )}
        </AlertMessage>
      )}

      {pronta && conversa.length > 0 && (
        <div>
          <p className="text-xs font-medium text-hipo-ink mb-1">
            Conversa
            {dados.fala_usuario_pct !== null && dados.fala_usuario_pct !== undefined && (
              <span className="ml-2 font-normal text-hipo-slate">
                quem ligou falou {dados.fala_usuario_pct}% do tempo
              </span>
            )}
          </p>
          <ol
            data-testid="conversa-ligacao"
            className="max-h-72 overflow-y-auto rounded-md border border-hipo-border bg-hipo-card p-2 space-y-1.5"
          >
            {conversa.map((f, i) => (
              <li key={i} className={`text-xs leading-relaxed ${f.canal === 0 ? 'pr-8' : 'pl-8 text-right'}`}>
                <span className={`font-medium ${f.canal === 0 ? 'text-hipo-blue' : 'text-hipo-success'}`}>
                  {f.participante}
                </span>
                <span className="ml-1 text-[10px] text-hipo-muted">{hora(f.inicio)}</span>
                <span className="block text-hipo-ink">{f.texto}</span>
              </li>
            ))}
          </ol>
        </div>
      )}
    </div>
  );
}
