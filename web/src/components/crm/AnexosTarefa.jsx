// web/src/components/crm/AnexosTarefa.jsx
//
// Anexos de uma tarefa: galeria, envio e remoção.
//
// ── Colar é o gesto principal, não o secundário ──────────────────────
// O caso que trouxe esta tela é o print do WhatsApp, e print nasce no
// Ctrl+C. Obrigar a pessoa a salvar em disco, achar a pasta e escolher o
// arquivo é atrito em cima de um gesto que já estava pronto. Por isso o
// bloco inteiro escuta `paste` e aceita arrastar-e-soltar; o botão de
// escolher arquivo continua existindo para quem já tem o arquivo salvo.
//
// ── Por que assinar a URL de cada imagem ao abrir ────────────────────
// O backend devolve a lista sem tocar no S3, e a URL vem numa segunda
// chamada. Para MINIATURA isso não é desperdício — a imagem vai ser
// exibida de qualquer jeito. Já o PDF só ganha a URL quando alguém
// clica: ele mostra ícone, não conteúdo.
//
// ── Tarefa fechada mostra, não mexe ──────────────────────────────────
// Anexo é prova do que aconteceu, e prova que pode ser trocada depois do
// fato não é prova. A mesma imutabilidade do resultado e do motivo de
// cancelamento — e o backend recusa com 422 de qualquer forma, então
// esconder os botões é honestidade, não decoração.

import { useCallback, useEffect, useRef, useState } from 'react';
import { Paperclip, Upload, X, FileText, Loader2, Maximize2 } from 'lucide-react';

import api from '../../api';
import Modal from '../ui/Modal';
import AlertMessage from '../ui/AlertMessage';
import { mensagemDeErro } from './tarefaComum';

// Espelha services/anexo.py. Duplicado de propósito: o `accept` do input
// filtra o seletor de arquivo do sistema, e um seletor que oferece o que
// o servidor vai recusar é uma promessa quebrada antes do clique.
const ACEITOS = 'image/png,image/jpeg,image/webp,image/gif,application/pdf';
const LIMITE_MB = 10;

function tamanhoLegivel(bytes) {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${Math.round(bytes / 1024)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

/**
 * @param tarefa       a tarefa dona (precisa de id, concluida_em, cancelada_em)
 * @param onMudou      avisa o pai — a contagem de anexos pode aparecer fora daqui
 * @param nivelLightbox nível do modal da imagem ampliada. Ver a nota abaixo.
 */
export default function AnexosTarefa({ tarefa, onMudou, nivelLightbox = 2 }) {
  const [itens, setItens] = useState([]);
  const [urls, setUrls] = useState({});      // anexo_id -> url assinada
  const [carregando, setCarregando] = useState(true);
  const [enviando, setEnviando] = useState(false);
  const [erro, setErro] = useState(null);
  const [arrastando, setArrastando] = useState(false);
  const [ampliado, setAmpliado] = useState(null);
  const inputRef = useRef(null);

  // A mesma regra do backend (services/anexo.pode_alterar). Repetida aqui
  // para a tela não oferecer o que o 422 vai recusar.
  const podeAlterar = !tarefa.concluida_em && !tarefa.cancelada_em;

  const carregar = useCallback(async () => {
    setCarregando(true);
    try {
      const { data } = await api.get(`/crm/tarefas/${tarefa.id}/anexos`);
      setItens(data);

      // Só as imagens: o PDF mostra ícone e só precisa de URL no clique.
      const imagens = data.filter((a) => a.eh_imagem);
      const assinadas = await Promise.all(
        imagens.map((a) =>
          api.get(`/crm/anexos/${a.id}/url`)
            .then(({ data: d }) => [a.id, d.url])
            // Uma URL que falha não pode derrubar a galeria inteira: a
            // miniatura quebrada é melhor que a lista sumir.
            .catch(() => [a.id, null])
        )
      );
      setUrls(Object.fromEntries(assinadas.filter(([, u]) => u)));
    } catch (err) {
      setErro(mensagemDeErro(err, 'Não foi possível carregar os anexos.'));
    } finally {
      setCarregando(false);
    }
  }, [tarefa.id]);

  useEffect(() => { carregar(); }, [carregar]);

  const enviar = useCallback(async (arquivos) => {
    const lista = Array.from(arquivos || []).filter(Boolean);
    if (lista.length === 0) return;

    setEnviando(true);
    setErro(null);
    try {
      // Em série, e não em paralelo: o limite de 10 por tarefa é contado
      // no servidor a cada POST. Dez uploads simultâneos leriam a mesma
      // contagem antes de qualquer um gravar, e passariam todos.
      for (const arquivo of lista) {
        const corpo = new FormData();
        corpo.append('arquivo', arquivo);
        // Sem Content-Type explícito: o navegador precisa montar o
        // boundary do multipart sozinho. Definir 'multipart/form-data' na
        // mão produz um header sem boundary e o servidor devolve 422 sem
        // dizer por quê.
        await api.post(`/crm/tarefas/${tarefa.id}/anexos`, corpo);
      }
      await carregar();
      onMudou?.();
    } catch (err) {
      setErro(mensagemDeErro(err, 'Não foi possível enviar o arquivo.'));
    } finally {
      setEnviando(false);
    }
  }, [tarefa.id, carregar, onMudou]);

  const remover = useCallback(async (anexo) => {
    setErro(null);
    try {
      await api.delete(`/crm/anexos/${anexo.id}`);
      await carregar();
      onMudou?.();
    } catch (err) {
      setErro(mensagemDeErro(err, 'Não foi possível remover o anexo.'));
    }
  }, [carregar, onMudou]);

  /*
    O paste escuta no BLOCO, não na window. Escutando na window, colar
    dentro do campo "O que aconteceu" — que fica na mesma tela — anexaria
    a imagem sem ninguém pedir, e um Ctrl+V de texto num campo vizinho
    passaria por aqui à toa.
  */
  const aoColar = useCallback((e) => {
    if (!podeAlterar) return;
    const arquivos = Array.from(e.clipboardData?.files || []);
    if (arquivos.length === 0) return;
    e.preventDefault();
    enviar(arquivos);
  }, [podeAlterar, enviar]);

  const aoSoltar = useCallback((e) => {
    e.preventDefault();
    setArrastando(false);
    if (!podeAlterar) return;
    enviar(e.dataTransfer?.files);
  }, [podeAlterar, enviar]);

  async function abrirAmpliado(anexo) {
    if (anexo.eh_imagem && urls[anexo.id]) {
      setAmpliado({ ...anexo, url: urls[anexo.id] });
      return;
    }
    // PDF (ou imagem cuja URL falhou): pede a URL agora e abre em aba
    // nova. PDF dentro de modal é pior que o leitor do navegador.
    try {
      const { data } = await api.get(`/crm/anexos/${anexo.id}/url`);
      window.open(data.url, '_blank', 'noopener,noreferrer');
    } catch (err) {
      setErro(mensagemDeErro(err, 'Não foi possível abrir o arquivo.'));
    }
  }

  const vazio = itens.length === 0;

  // Some inteiro quando não há nada e nada pode ser feito: numa tarefa
  // fechada sem anexo, um bloco vazio dizendo "sem anexos" é ruído puro.
  if (!podeAlterar && vazio && !carregando) return null;

  return (
    <div
      onPaste={aoColar}
      onDrop={aoSoltar}
      onDragOver={(e) => { e.preventDefault(); if (podeAlterar) setArrastando(true); }}
      onDragLeave={() => setArrastando(false)}
      /*
        tabIndex torna o bloco focável, e é isso que faz o Ctrl+V chegar
        aqui: sem foco, o evento de colar vai para o body e o handler
        nunca dispara. O outline fica com o :focus-visible do foco real.
      */
      tabIndex={podeAlterar ? 0 : -1}
      aria-label="Anexos da tarefa"
      className={
        'rounded-lg border p-2.5 space-y-2 transition-colors ' +
        'focus:outline-none focus-visible:ring-2 focus-visible:ring-hipo-blue ' +
        (arrastando
          ? 'border-hipo-blue bg-hipo-blueSoft border-dashed'
          : 'border-hipo-border bg-hipo-bg/40')
      }
    >
      <div className="flex items-center gap-2">
        <Paperclip size={13} className="shrink-0 text-hipo-slate" aria-hidden="true" />
        <span className="text-xs font-medium text-hipo-ink">
          Anexos{itens.length > 0 ? ` (${itens.length})` : ''}
        </span>

        {podeAlterar && (
          <>
            <input
              ref={inputRef}
              type="file"
              accept={ACEITOS}
              multiple
              className="hidden"
              aria-label="Escolher arquivo para anexar"
              onChange={(e) => {
                enviar(e.target.files);
                // Zerar permite reenviar o MESMO arquivo depois de
                // remover: sem isso o onChange não dispara na segunda vez,
                // porque o valor do input não mudou.
                e.target.value = '';
              }}
            />
            <button
              type="button"
              onClick={() => inputRef.current?.click()}
              disabled={enviando}
              className={
                'ml-auto inline-flex items-center gap-1 px-2 py-1 rounded-md text-xs ' +
                'border border-hipo-border bg-hipo-card text-hipo-slate ' +
                'hover:bg-hipo-blueSoft hover:text-hipo-blue hover:border-hipo-blue ' +
                'disabled:opacity-50 transition-colors ' +
                'focus:outline-none focus-visible:ring-2 focus-visible:ring-hipo-blue'
              }
            >
              {enviando
                ? <Loader2 size={12} className="animate-spin" aria-hidden="true" />
                : <Upload size={12} aria-hidden="true" />}
              {enviando ? 'Enviando…' : 'Anexar'}
            </button>
          </>
        )}
      </div>

      {erro && <AlertMessage tipo="erro">{erro}</AlertMessage>}

      {carregando ? (
        <p className="text-xs text-hipo-muted">Carregando anexos…</p>
      ) : vazio ? (
        podeAlterar && (
          <p className="text-xs text-hipo-muted">
            Cole o print aqui (Ctrl+V), arraste o arquivo, ou use o botão.
            Até {LIMITE_MB} MB — imagem ou PDF.
          </p>
        )
      ) : (
        <ul className="flex flex-wrap gap-2">
          {itens.map((a) => (
            <li key={a.id} className="relative group">
              <button
                type="button"
                onClick={() => abrirAmpliado(a)}
                title={`${a.nome_original} — ${tamanhoLegivel(a.bytes)}`}
                aria-label={`Abrir ${a.nome_original}`}
                className={
                  'block w-20 h-20 rounded-md border border-hipo-border overflow-hidden ' +
                  'bg-hipo-card hover:border-hipo-blue transition-colors ' +
                  'focus:outline-none focus-visible:ring-2 focus-visible:ring-hipo-blue'
                }
              >
                {a.eh_imagem && urls[a.id] ? (
                  <img
                    src={urls[a.id]}
                    alt={a.nome_original}
                    className="w-full h-full object-cover"
                  />
                ) : (
                  <span className="w-full h-full flex flex-col items-center justify-center gap-1 text-hipo-slate">
                    <FileText size={20} aria-hidden="true" />
                    <span className="text-[10px] px-1 truncate max-w-full">
                      {a.eh_imagem ? 'imagem' : 'PDF'}
                    </span>
                  </span>
                )}
              </button>

              {podeAlterar && (
                <button
                  type="button"
                  onClick={() => remover(a)}
                  aria-label={`Remover ${a.nome_original}`}
                  title="Remover"
                  className={
                    'absolute -top-1.5 -right-1.5 w-5 h-5 rounded-full ' +
                    'bg-hipo-card border border-hipo-border text-hipo-slate ' +
                    'flex items-center justify-center ' +
                    'opacity-0 group-hover:opacity-100 focus:opacity-100 ' +
                    'hover:bg-hipo-dangerSoft hover:text-hipo-danger hover:border-hipo-danger ' +
                    'transition-opacity ' +
                    'focus:outline-none focus-visible:ring-2 focus-visible:ring-hipo-blue'
                  }
                >
                  <X size={11} />
                </button>
              )}
            </li>
          ))}
        </ul>
      )}

      {/*
        ── Imagem ampliada ──
        O nível vem por PROP, com padrão 2. Este componente aparece em
        contextos de profundidade diferente: no módulo de Tarefas o modal
        da tarefa é nível 1, mas dentro do drilldown da oportunidade ele
        já está no 2. Nível cravado aqui faria o lightbox abrir ATRÁS —
        exatamente a dívida que o ModalDesfecho cobrou na 011.
      */}
      <Modal
        aberto={Boolean(ampliado)}
        onFechar={() => setAmpliado(null)}
        titulo={ampliado?.nome_original}
        subtitulo={ampliado ? tamanhoLegivel(ampliado.bytes) : undefined}
        size="xl"
        nivel={nivelLightbox}
        acoes={
          ampliado ? (
            <a
              href={ampliado.url}
              target="_blank"
              rel="noopener noreferrer"
              className={
                'inline-flex items-center gap-1 px-2 py-1 rounded-md text-xs ' +
                'border border-hipo-border text-hipo-slate hover:text-hipo-blue ' +
                'hover:border-hipo-blue transition-colors'
              }
            >
              <Maximize2 size={12} aria-hidden="true" />
              Abrir em nova aba
            </a>
          ) : undefined
        }
      >
        {ampliado && (
          <div className="flex items-center justify-center">
            <img
              src={ampliado.url}
              alt={ampliado.nome_original}
              className="max-w-full max-h-[70vh] object-contain"
            />
          </div>
        )}
      </Modal>
    </div>
  );
}
