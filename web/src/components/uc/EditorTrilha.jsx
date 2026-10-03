// web/src/components/uc/EditorTrilha.jsx
//
// Estúdio da UC: uma trilha inteira num modal — dados, manual da função
// (quais cargos fazem e com que prazo) e as aulas, na ordem.
//
// Cada bloco salva sozinho: mexer no prazo do EV não deveria exigir
// revisar o texto da trilha. As regras (não publicar vazia, cargo válido,
// ordem completa) são do servidor; o erro dele aparece no topo como veio.

import { useCallback, useEffect, useState } from 'react';
import {
  ArrowDown, ArrowUp, Pencil, Plus, Trash2, Eye, Archive, Send, Undo2,
} from 'lucide-react';
import api from '../../api';
import Modal from '../ui/Modal';
import Button from '../ui/Button';
import Badge from '../ui/Badge';
import Input, { Select, Textarea } from '../ui/Input';
import AlertMessage from '../ui/AlertMessage';
import { mensagemDeErro } from '../crm/tarefaComum';
import EditorAula from './EditorAula';
import { tomDoPilar } from './ucComum';

const STATUS_TOM = { rascunho: 'warning', publicada: 'success', arquivada: 'neutral' };
const STATUS_ROTULO = { rascunho: 'Rascunho', publicada: 'Publicada', arquivada: 'Arquivada' };

function linhasDeCargo(vocab, cargos) {
  const por = Object.fromEntries((cargos || []).map((c) => [c.cargo, c]));
  return (vocab?.cargos || []).map((cargo) => ({
    cargo,
    faz: !!por[cargo],
    obrigatoria: por[cargo]?.obrigatoria ?? true,
    prazo_dias: por[cargo]?.prazo_dias ?? 30,
  }));
}

export default function EditorTrilha({ trilhaId, vocab, onFechar, onMudou }) {
  const [trilha, setTrilha] = useState(null);
  const [form, setForm] = useState(null);
  const [cargos, setCargos] = useState([]);
  const [erro, setErro] = useState('');
  const [aviso, setAviso] = useState('');
  const [ocupado, setOcupado] = useState('');
  const [aulaAberta, setAulaAberta] = useState(undefined); // undefined = fechado; null = nova

  const aplicar = useCallback((t) => {
    setTrilha(t);
    setForm({
      titulo: t.titulo, descricao: t.descricao || '', pilar: t.pilar, reforca: t.reforca || '',
    });
    setCargos(linhasDeCargo(vocab, t.cargos));
  }, [vocab]);

  const carregar = useCallback(async () => {
    try {
      const { data } = await api.get(`/uc/estudio/trilhas/${trilhaId}`);
      aplicar(data);
    } catch (e) {
      setErro(mensagemDeErro(e, 'Não foi possível abrir a trilha.'));
    }
  }, [trilhaId, aplicar]);

  useEffect(() => { if (trilhaId) carregar(); }, [trilhaId, carregar]);

  async function executar(rotulo, chamada, sucesso) {
    setErro('');
    setAviso('');
    setOcupado(rotulo);
    try {
      const { data } = await chamada();
      if (data?.aulas) aplicar(data);
      if (sucesso) setAviso(sucesso);
      onMudou?.();
    } catch (e) {
      setErro(mensagemDeErro(e, 'Não foi possível salvar.'));
    } finally {
      setOcupado('');
    }
  }

  const salvarDados = () => executar(
    'dados',
    () => api.patch(`/uc/estudio/trilhas/${trilhaId}`, { ...form, reforca: form.reforca || null }),
    'Dados da trilha salvos.',
  );

  const mudarStatus = (status, msg) => executar(
    status, () => api.patch(`/uc/estudio/trilhas/${trilhaId}`, { status }), msg,
  );

  const salvarCargos = () => executar(
    'cargos',
    () => api.put(`/uc/estudio/trilhas/${trilhaId}/cargos`, {
      cargos: cargos.filter((c) => c.faz).map((c) => ({
        cargo: c.cargo,
        obrigatoria: c.obrigatoria,
        prazo_dias: c.obrigatoria && c.prazo_dias ? Number(c.prazo_dias) : null,
      })),
    }),
    'Manual da função salvo.',
  );

  function mover(indice, delta) {
    const ids = trilha.aulas.map((a) => a.id);
    const alvo = indice + delta;
    if (alvo < 0 || alvo >= ids.length) return;
    [ids[indice], ids[alvo]] = [ids[alvo], ids[indice]];
    executar('ordem', () => api.put(`/uc/estudio/trilhas/${trilhaId}/ordem`, { aulas: ids }));
  }

  async function apagarAula(a) {
    setErro('');
    try {
      await api.delete(`/uc/estudio/aulas/${a.id}`);
      await carregar();
      onMudou?.();
    } catch (e) {
      setErro(mensagemDeErro(e, 'Não foi possível apagar a aula.'));
    }
  }

  const setCargo = (i, chave, valor) => setCargos((lista) => lista.map((c, j) => (j === i ? { ...c, [chave]: valor } : c)));

  return (
    <Modal
      aberto={!!trilhaId}
      onFechar={onFechar}
      titulo={trilha ? trilha.titulo : 'Trilha'}
      subtitulo={trilha ? `${trilha.pilar_rotulo} · ${trilha.aulas.length} aula(s) · ${trilha.concluintes} pessoa(s) já concluíram alguma aula` : undefined}
      size="full"
    >
      {!trilha || !form ? (
        erro ? <AlertMessage tipo="erro">{erro}</AlertMessage> : <p className="text-sm text-hipo-slate">Carregando…</p>
      ) : (
        <div className="space-y-6">
          {erro && <AlertMessage tipo="erro">{erro}</AlertMessage>}
          {aviso && <AlertMessage tipo="ok">{aviso}</AlertMessage>}

          {/* ── Situação ─────────────────────────────────────────── */}
          <div className="flex flex-wrap items-center gap-2">
            <Badge tone={STATUS_TOM[trilha.status]}>{STATUS_ROTULO[trilha.status]}</Badge>
            <Badge tone={tomDoPilar(trilha.pilar).badge}>{trilha.pilar_rotulo}</Badge>
            <div className="flex-1" />
            <Button size="sm" variant="ghost" icon={Eye} onClick={() => window.open(`/uc/trilhas/${trilha.id}`, '_blank')}>
              Ver como a equipe vê
            </Button>
            {trilha.status !== 'publicada' && (
              <Button size="sm" icon={Send} loading={ocupado === 'publicada'}
                onClick={() => mudarStatus('publicada', 'Trilha publicada.')}>
                Publicar
              </Button>
            )}
            {trilha.status === 'publicada' && (
              <Button size="sm" variant="secondary" icon={Undo2} loading={ocupado === 'rascunho'}
                onClick={() => mudarStatus('rascunho', 'Trilha voltou para rascunho.')}>
                Voltar a rascunho
              </Button>
            )}
            {trilha.status !== 'arquivada' && (
              <Button size="sm" variant="ghost" icon={Archive} loading={ocupado === 'arquivada'}
                onClick={() => mudarStatus('arquivada', 'Trilha arquivada.')}>
                Arquivar
              </Button>
            )}
          </div>

          {/* ── Dados ────────────────────────────────────────────── */}
          <section className="space-y-3">
            <h3 className="text-h2 text-hipo-ink">Dados</h3>
            <div className="grid gap-3 sm:grid-cols-4">
              <Input id="trilha-titulo" label="Título" className="sm:col-span-2" value={form.titulo}
                onChange={(e) => setForm({ ...form, titulo: e.target.value })} />
              <Select id="trilha-pilar" label="Pilar" value={form.pilar}
                onChange={(e) => setForm({ ...form, pilar: e.target.value })}>
                {Object.entries(vocab.pilares).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
              </Select>
              <Select id="trilha-reforca" label="Reforça (PDI)" value={form.reforca}
                onChange={(e) => setForm({ ...form, reforca: e.target.value })}>
                <option value="">Nenhuma medida</option>
                {Object.entries(vocab.reforcos).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
              </Select>
            </div>
            <Textarea id="trilha-descricao" label="Descrição" rows={2} value={form.descricao}
              onChange={(e) => setForm({ ...form, descricao: e.target.value })} />
            <Button size="sm" onClick={salvarDados} loading={ocupado === 'dados'}>Salvar dados</Button>
          </section>

          {/* ── Manual da função ─────────────────────────────────── */}
          <section className="space-y-3">
            <div>
              <h3 className="text-h2 text-hipo-ink">Manual da função</h3>
              <p className="text-sm text-hipo-slate">
                Sem nenhum cargo marcado, a trilha fica aberta a todos e sem prazo. O prazo conta da entrada
                da pessoa no cargo ou de quando a trilha virou obrigatória, o que vier depois.
              </p>
            </div>
            <div className="overflow-x-auto">
              <table className="text-sm">
                <thead>
                  <tr className="text-left text-xs text-hipo-slate">
                    <th className="pr-6 py-1 font-medium">Cargo</th>
                    <th className="pr-6 py-1 font-medium">Faz a trilha</th>
                    <th className="pr-6 py-1 font-medium">Obrigatória</th>
                    <th className="py-1 font-medium">Prazo (dias)</th>
                  </tr>
                </thead>
                <tbody>
                  {cargos.map((c, i) => (
                    <tr key={c.cargo}>
                      <td className="pr-6 py-1.5 font-medium text-hipo-ink">{c.cargo}</td>
                      <td className="pr-6 py-1.5">
                        <input type="checkbox" aria-label={`${c.cargo} faz a trilha`} checked={c.faz}
                          onChange={(e) => setCargo(i, 'faz', e.target.checked)} />
                      </td>
                      <td className="pr-6 py-1.5">
                        <input type="checkbox" aria-label={`${c.cargo} obrigatória`} checked={c.obrigatoria}
                          disabled={!c.faz} onChange={(e) => setCargo(i, 'obrigatoria', e.target.checked)} />
                      </td>
                      <td className="py-1.5">
                        <input
                          type="number" min="1" max="365" aria-label={`${c.cargo} prazo em dias`}
                          className="w-20 h-8 px-2 rounded-md border border-hipo-border bg-hipo-card disabled:opacity-50"
                          value={c.prazo_dias ?? ''} disabled={!c.faz || !c.obrigatoria}
                          onChange={(e) => setCargo(i, 'prazo_dias', e.target.value)}
                        />
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <Button size="sm" onClick={salvarCargos} loading={ocupado === 'cargos'}>Salvar manual da função</Button>
          </section>

          {/* ── Aulas ────────────────────────────────────────────── */}
          <section className="space-y-3">
            <div className="flex items-center justify-between">
              <h3 className="text-h2 text-hipo-ink">Aulas</h3>
              <Button size="sm" icon={Plus} onClick={() => setAulaAberta(null)}>Nova aula</Button>
            </div>
            {trilha.aulas.length === 0 ? (
              <p className="text-sm text-hipo-slate">Nenhuma aula ainda. A trilha só pode ser publicada com uma aula publicada.</p>
            ) : (
              <ol className="divide-y divide-hipo-border border border-hipo-border rounded-lg">
                {trilha.aulas.map((a, i) => (
                  <li key={a.id} className="flex items-center gap-3 px-3 py-2">
                    <span className="w-6 text-sm text-hipo-slate text-right">{a.ordem}.</span>
                    <div className="flex-1 min-w-0">
                      <p className="text-sm font-medium text-hipo-ink truncate">{a.titulo}</p>
                      <p className="text-xs text-hipo-slate">
                        {a.duracao_min ? `${a.duracao_min} min · ` : ''}
                        {a.video_provedor ? 'vídeo · ' : ''}
                        {a.materiais.length} material(is) · v{a.versao} · {a.concluintes} concluíram{a.tour_passos ? ` · tour de ${a.tour_passos} passos` : ''}
                      </p>
                    </div>
                    {a.status !== 'publicada' && <Badge tone="warning">Rascunho</Badge>}
                    <button type="button" aria-label={`Subir ${a.titulo}`} disabled={i === 0}
                      className="p-1 rounded text-hipo-slate hover:text-hipo-ink disabled:opacity-30" onClick={() => mover(i, -1)}>
                      <ArrowUp size={16} />
                    </button>
                    <button type="button" aria-label={`Descer ${a.titulo}`} disabled={i === trilha.aulas.length - 1}
                      className="p-1 rounded text-hipo-slate hover:text-hipo-ink disabled:opacity-30" onClick={() => mover(i, 1)}>
                      <ArrowDown size={16} />
                    </button>
                    <button type="button" aria-label={`Editar ${a.titulo}`}
                      className="p-1 rounded text-hipo-slate hover:text-hipo-blue" onClick={() => setAulaAberta(a)}>
                      <Pencil size={16} />
                    </button>
                    <button type="button" aria-label={`Apagar ${a.titulo}`}
                      className="p-1 rounded text-hipo-slate hover:text-hipo-danger" onClick={() => apagarAula(a)}>
                      <Trash2 size={16} />
                    </button>
                  </li>
                ))}
              </ol>
            )}
          </section>
        </div>
      )}

      <EditorAula
        aberto={aulaAberta !== undefined}
        trilhaId={trilhaId}
        aula={aulaAberta || null}
        onFechar={() => setAulaAberta(undefined)}
        onSalvo={() => { carregar(); onMudou?.(); }}
      />
    </Modal>
  );
}
