// web/src/components/uc/EditorAula.jsx
//
// Estúdio da UC: criar e editar uma aula.
//
// O vídeo entra como LINK. Quem confere e transforma em (provedor, id) é o
// servidor; a tela só mostra o player do que já foi salvo — não tenta
// adivinhar o provedor de um link que ainda não passou pela regra.
//
// "Mudança relevante" só aparece quando alguém já concluiu a aula: é a
// pergunta "essa mudança obriga quem já fez a refazer?". Sem concluinte,
// a pergunta não tem a quem se aplicar.
//
// Material de apoio e quiz só depois de salvar: precisam de uma aula que
// já existe (mesma regra dos anexos de tarefa). O quiz salva à parte
// (EditorQuiz), com o próprio botão.

import { useEffect, useRef, useState } from 'react';
import { Eye, Pencil, Trash2, Upload, FileText, Image as ImageIcon } from 'lucide-react';
import api from '../../api';
import Modal, { AcoesDoModal } from '../ui/Modal';
import Button from '../ui/Button';
import Input, { Select, Textarea } from '../ui/Input';
import AlertMessage from '../ui/AlertMessage';
import { mensagemDeErro } from '../crm/tarefaComum';
import TextoAula from './TextoAula';
import EditorQuiz from './EditorQuiz';
import { tamanhoArquivo, urlDeEmbed } from './ucComum';

function vazio() {
  return {
    titulo: '', resumo: '', conteudo_md: '', video_url: '', duracao_min: '', status: 'publicada',
  };
}

export default function EditorAula({ aberto, trilhaId, aula, onFechar, onSalvo, nivel = 2 }) {
  const editando = !!aula;
  const [form, setForm] = useState(vazio());
  const [relevante, setRelevante] = useState(false);
  const [previa, setPrevia] = useState(false);
  const [salvando, setSalvando] = useState(false);
  const [erro, setErro] = useState('');
  const [atual, setAtual] = useState(aula || null);
  const [enviando, setEnviando] = useState(false);
  const arquivoRef = useRef(null);

  useEffect(() => {
    if (!aberto) return;
    setAtual(aula || null);
    setForm(aula ? {
      titulo: aula.titulo || '',
      resumo: aula.resumo || '',
      conteudo_md: aula.conteudo_md || '',
      video_url: aula.video_url || '',
      duracao_min: aula.duracao_min ?? '',
      status: aula.status || 'publicada',
    } : vazio());
    setRelevante(false);
    setPrevia(false);
    setErro('');
  }, [aberto, aula]);

  const campo = (nome) => (e) => setForm((f) => ({ ...f, [nome]: e.target.value }));

  async function salvar() {
    setErro('');
    if (!form.titulo.trim()) { setErro('Dê um título à aula.'); return; }
    setSalvando(true);
    const corpo = {
      titulo: form.titulo,
      resumo: form.resumo,
      conteudo_md: form.conteudo_md,
      video_url: form.video_url,
      duracao_min: form.duracao_min === '' ? null : Number(form.duracao_min),
      status: form.status,
    };
    try {
      const { data } = atual
        ? await api.patch(`/uc/estudio/aulas/${atual.id}`, { ...corpo, mudanca_relevante: relevante })
        : await api.post(`/uc/estudio/trilhas/${trilhaId}/aulas`, corpo);
      setAtual(data);
      setForm((f) => ({ ...f, video_url: data.video_url || '' }));
      setRelevante(false);
      onSalvo?.(data);
    } catch (e) {
      setErro(mensagemDeErro(e, 'Não foi possível salvar a aula.'));
    } finally {
      setSalvando(false);
    }
  }

  async function enviar(arquivos) {
    if (!atual || !arquivos?.length) return;
    setEnviando(true);
    setErro('');
    try {
      // Em série: o limite por aula é contado no servidor a cada envio.
      for (const arquivo of arquivos) {
        const dados = new FormData();
        dados.append('arquivo', arquivo);
        await api.post(`/uc/estudio/aulas/${atual.id}/materiais`, dados);
      }
      const { data } = await api.get(`/uc/estudio/trilhas/${trilhaId}`);
      const nova = data.aulas.find((a) => a.id === atual.id);
      if (nova) setAtual(nova);
      onSalvo?.(nova);
    } catch (e) {
      setErro(mensagemDeErro(e, 'Não foi possível enviar o arquivo.'));
    } finally {
      setEnviando(false);
      if (arquivoRef.current) arquivoRef.current.value = '';
    }
  }

  async function removerMaterial(m) {
    setErro('');
    try {
      await api.delete(`/uc/estudio/materiais/${m.id}`);
      setAtual((a) => ({ ...a, materiais: a.materiais.filter((x) => x.id !== m.id) }));
      onSalvo?.();
    } catch (e) {
      setErro(mensagemDeErro(e, 'Não foi possível remover o material.'));
    }
  }

  const embed = atual ? urlDeEmbed(atual.video_provedor, atual.video_ref) : null;

  return (
    <Modal
      aberto={aberto}
      onFechar={onFechar}
      titulo={editando || atual ? `Aula ${atual?.ordem ?? ''}: ${atual?.titulo || form.titulo}` : 'Nova aula'}
      subtitulo={atual ? `versão ${atual.versao} · ${atual.concluintes} concluíram esta versão` : undefined}
      size="xl"
      nivel={nivel}
    >
      <AcoesDoModal>
        <Button size="sm" onClick={salvar} loading={salvando}>Salvar</Button>
      </AcoesDoModal>

      <div className="space-y-4">
        {erro && <AlertMessage tipo="erro">{erro}</AlertMessage>}

        <div className="grid gap-3 sm:grid-cols-4">
          <Input id="aula-titulo" label="Título" className="sm:col-span-3" value={form.titulo} onChange={campo('titulo')} />
          <Input
            id="aula-duracao" label="Duração (min)" type="number" min="1" max="600"
            value={form.duracao_min} onChange={campo('duracao_min')}
            hint="Libera o Concluí (ou o quiz) na metade"
          />
        </div>
        <Input id="aula-resumo" label="Resumo" value={form.resumo} onChange={campo('resumo')} />
        <div className="grid gap-3 sm:grid-cols-4">
          <Input
            id="aula-video" label="Link do vídeo" className="sm:col-span-3"
            placeholder="YouTube (não listado), Vimeo, Loom ou Google Drive"
            value={form.video_url} onChange={campo('video_url')}
            hint="Conferido ao salvar. Vídeo nunca sobe como arquivo."
          />
          <Select id="aula-status" label="Situação" value={form.status} onChange={campo('status')}>
            <option value="publicada">Publicada</option>
            <option value="rascunho">Rascunho</option>
          </Select>
        </div>

        {embed && (
          <div className="rounded-lg overflow-hidden border border-hipo-border bg-black aspect-video max-w-md">
            <iframe title="Prévia do vídeo" src={embed} className="w-full h-full" allowFullScreen />
          </div>
        )}

        <div>
          <div className="flex items-center justify-between mb-1.5">
            <label htmlFor="aula-texto" className="text-sm font-medium text-hipo-ink">Texto da aula</label>
            <Button size="sm" variant="ghost" icon={previa ? Pencil : Eye} onClick={() => setPrevia((v) => !v)}>
              {previa ? 'Editar' : 'Prévia'}
            </Button>
          </div>
          {previa ? (
            <div className="border border-hipo-border rounded-lg p-4 max-h-[50vh] overflow-y-auto">
              <TextoAula md={form.conteudo_md} />
            </div>
          ) : (
            <Textarea
              id="aula-texto"
              rows={14}
              value={form.conteudo_md}
              onChange={campo('conteudo_md')}
              textareaClassName="font-mono text-xs"
              hint="## seção · ### subseção · - item · 1. item · > destaque · **negrito**"
            />
          )}
        </div>

        {atual && atual.tour_passos > 0 && (
          <p className="text-xs text-hipo-slate bg-hipo-blueSoft rounded-lg px-3 py-2">
            Esta aula tem um tour guiado de {atual.tour_passos} passos ("Me mostra no HIPO").
            Ele vem do conteúdo carregado pelo sistema; editar a aula aqui não mexe nele.
          </p>
        )}

        {atual && atual.concluintes > 0 && (
          <label className="flex items-start gap-2 text-sm text-hipo-ink bg-hipo-warningSoft border border-hipo-warningBorder rounded-lg px-3 py-2">
            <input
              type="checkbox"
              className="mt-1"
              checked={relevante}
              onChange={(e) => setRelevante(e.target.checked)}
            />
            <span>
              <strong>Mudança relevante</strong>: quem já concluiu precisa refazer esta aula.
              Deixe desmarcado para correção de texto.
            </span>
          </label>
        )}

        <div>
          <p className="text-sm font-medium text-hipo-ink mb-1.5">Material de apoio</p>
          {!atual ? (
            <p className="text-xs text-hipo-slate">Salve a aula para anexar PDF, imagem ou documento.</p>
          ) : (
            <>
              <ul className="space-y-1.5 mb-2">
                {atual.materiais.map((m) => (
                  <li key={m.id} className="flex items-center gap-2 text-sm">
                    {m.eh_imagem ? <ImageIcon size={16} className="text-hipo-blue" /> : <FileText size={16} className="text-hipo-blue" />}
                    <span className="flex-1 truncate">{m.nome_original}</span>
                    <span className="text-xs text-hipo-slate">{tamanhoArquivo(m.bytes)}</span>
                    <button
                      type="button"
                      aria-label={`Remover ${m.nome_original}`}
                      onClick={() => removerMaterial(m)}
                      className="p-1 rounded text-hipo-slate hover:text-hipo-danger"
                    >
                      <Trash2 size={14} />
                    </button>
                  </li>
                ))}
              </ul>
              <input
                ref={arquivoRef}
                type="file"
                multiple
                className="hidden"
                data-testid="input-material"
                accept=".pdf,.png,.jpg,.jpeg,.webp,.pptx,.xlsx,.docx"
                onChange={(e) => enviar(Array.from(e.target.files || []))}
              />
              <Button
                size="sm"
                variant="secondary"
                icon={Upload}
                loading={enviando}
                onClick={() => arquivoRef.current?.click()}
              >
                Anexar arquivo
              </Button>
              <span className="text-xs text-hipo-slate ml-2">PDF, imagem, PPTX, XLSX ou DOCX até 25 MB</span>
            </>
          )}
        </div>

        {atual ? (
          <EditorQuiz
            aula={atual}
            onSalvo={(data) => { setAtual((a) => ({ ...a, quiz: data.quiz, nota_minima: data.nota_minima })); onSalvo?.(data); }}
          />
        ) : (
          <p className="text-xs text-hipo-slate">Salve a aula para escrever o quiz.</p>
        )}
      </div>
    </Modal>
  );
}
