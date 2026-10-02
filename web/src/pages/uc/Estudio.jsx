// web/src/pages/uc/Estudio.jsx
//
// Universidade Corporativa — estúdio da gestão.
//
// Duas abas:
//   Trilhas — o conteúdo, agrupado por pilar. Cada trilha abre o editor
//             (dados, manual da função, aulas).
//   Time    — uma linha por pessoa: manual em dia, atrasadas, andamento e a
//             próxima aula. Clicar abre a UC da pessoa em modo leitura —
//             gestão vê a tela da função subordinada, sem agir por ela.
//
// A rota existe para todo mundo; quem barra é a API (requer_gestao_uc). Um
// operacional que digitar a URL vê o aviso do servidor, não uma tela vazia.

import { useCallback, useEffect, useState } from 'react';
import { useNavigate, useSearchParams } from 'react-router-dom';
import { ArrowLeft, Plus, Users } from 'lucide-react';
import api from '../../api';
import PageHeader from '../../components/ui/PageHeader';
import Card from '../../components/ui/Card';
import Badge from '../../components/ui/Badge';
import Button from '../../components/ui/Button';
import Tabs from '../../components/ui/Tabs';
import Modal from '../../components/ui/Modal';
import Input, { Select, Textarea } from '../../components/ui/Input';
import AlertMessage from '../../components/ui/AlertMessage';
import Empty from '../../components/ui/Empty';
import { mensagemDeErro } from '../../components/crm/tarefaComum';
import EditorTrilha from '../../components/uc/EditorTrilha';
import { tomDoPilar } from '../../components/uc/ucComum';

const STATUS_TOM = { rascunho: 'warning', publicada: 'success', arquivada: 'neutral' };
const STATUS_ROTULO = { rascunho: 'Rascunho', publicada: 'Publicada', arquivada: 'Arquivada' };

function NovaTrilha({ aberto, vocab, onFechar, onCriada }) {
  const [form, setForm] = useState({ titulo: '', pilar: 'tecnica', descricao: '', reforca: '' });
  const [erro, setErro] = useState('');
  const [salvando, setSalvando] = useState(false);

  useEffect(() => {
    if (aberto) { setForm({ titulo: '', pilar: 'tecnica', descricao: '', reforca: '' }); setErro(''); }
  }, [aberto]);

  async function criar() {
    if (!form.titulo.trim()) { setErro('Dê um título à trilha.'); return; }
    setSalvando(true);
    setErro('');
    try {
      const { data } = await api.post('/uc/estudio/trilhas', { ...form, reforca: form.reforca || null });
      onCriada(data);
    } catch (e) {
      setErro(mensagemDeErro(e, 'Não foi possível criar a trilha.'));
    } finally {
      setSalvando(false);
    }
  }

  return (
    <Modal
      aberto={aberto}
      onFechar={onFechar}
      titulo="Nova trilha"
      subtitulo="Nasce em rascunho. Publique depois de criar as aulas."
      footer={(
        <div className="flex justify-end gap-2">
          <Button variant="secondary" onClick={onFechar}>Cancelar</Button>
          <Button onClick={criar} loading={salvando}>Criar trilha</Button>
        </div>
      )}
    >
      <div className="space-y-3">
        {erro && <AlertMessage tipo="erro">{erro}</AlertMessage>}
        <Input id="nova-titulo" label="Título" value={form.titulo}
          onChange={(e) => setForm({ ...form, titulo: e.target.value })} />
        <div className="grid gap-3 sm:grid-cols-2">
          <Select id="nova-pilar" label="Pilar" value={form.pilar}
            onChange={(e) => setForm({ ...form, pilar: e.target.value })}>
            {Object.entries(vocab?.pilares || {}).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
          </Select>
          <Select id="nova-reforca" label="Reforça (PDI)" value={form.reforca}
            onChange={(e) => setForm({ ...form, reforca: e.target.value })}>
            <option value="">Nenhuma medida</option>
            {Object.entries(vocab?.reforcos || {}).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
          </Select>
        </div>
        <Textarea id="nova-descricao" label="Descrição" rows={2} value={form.descricao}
          onChange={(e) => setForm({ ...form, descricao: e.target.value })} />
      </div>
    </Modal>
  );
}

function AbaTrilhas({ vocab, trilhas, onAbrir }) {
  if (!trilhas.length) {
    return <Empty title="Nenhuma trilha ainda" description="Crie a primeira com o botão Nova trilha." />;
  }
  return (
    <div className="grid gap-4 lg:grid-cols-3">
      {Object.entries(vocab.pilares).map(([pilar, rotulo]) => {
        const lista = trilhas.filter((t) => t.pilar === pilar);
        return (
          <Card key={pilar} padding="sm">
            <div className="flex items-center gap-2 mb-3">
              <span className={`w-2.5 h-2.5 rounded-full ${tomDoPilar(pilar).barra}`} />
              <h3 className="text-h2 text-hipo-ink">{rotulo}</h3>
              <span className="text-xs text-hipo-slate">{lista.length}</span>
            </div>
            {lista.length === 0 ? (
              <p className="text-sm text-hipo-slate">Nenhuma trilha neste pilar.</p>
            ) : (
              <ul className="space-y-2">
                {lista.map((t) => (
                  <li key={t.id}>
                    <button
                      type="button"
                      onClick={() => onAbrir(t.id)}
                      className="w-full text-left border border-hipo-border rounded-lg px-3 py-2 hover:border-hipo-blue transition-colors"
                    >
                      <div className="flex items-start justify-between gap-2">
                        <span className="text-sm font-medium text-hipo-ink">{t.titulo}</span>
                        <Badge tone={STATUS_TOM[t.status]}>{STATUS_ROTULO[t.status]}</Badge>
                      </div>
                      <p className="text-xs text-hipo-slate mt-1">
                        {t.aulas_publicadas}/{t.aulas_total} aulas publicadas · {t.concluintes} pessoa(s) em andamento
                      </p>
                      <p className="text-xs text-hipo-slate mt-0.5">
                        {t.cargos.length
                          ? t.cargos.map((c) => `${c.cargo}${c.obrigatoria ? '*' : ''}`).join(' · ')
                          : 'Aberta a todos'}
                      </p>
                    </button>
                  </li>
                ))}
              </ul>
            )}
          </Card>
        );
      })}
      <p className="text-xs text-hipo-muted lg:col-span-3">* obrigatória para o cargo (manual da função)</p>
    </div>
  );
}

function AbaTime({ linhas, onAbrir }) {
  if (!linhas.length) return <Empty icon={Users} title="Ninguém no time ainda" />;
  return (
    <Card padding="none">
      <div className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead>
            <tr className="text-left text-xs text-hipo-slate border-b border-hipo-border">
              <th className="px-4 py-3 font-medium">Pessoa</th>
              <th className="px-4 py-3 font-medium">Cargo</th>
              <th className="px-4 py-3 font-medium">Manual da função</th>
              <th className="px-4 py-3 font-medium">Aulas</th>
              <th className="px-4 py-3 font-medium">Próxima aula</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-hipo-border">
            {linhas.map((p) => (
              <tr
                key={p.id}
                className="hover:bg-hipo-bg cursor-pointer"
                onClick={() => onAbrir(p)}
                data-testid={`time-${p.id}`}
              >
                <td className="px-4 py-3 font-medium text-hipo-ink">{p.nome}</td>
                <td className="px-4 py-3 text-hipo-slate">{p.cargo}</td>
                <td className="px-4 py-3">
                  {p.obrigatorias ? (
                    <span className="inline-flex items-center gap-2">
                      {p.obrigatorias_concluidas}/{p.obrigatorias}
                      {p.atrasadas > 0 && <Badge tone="danger">{p.atrasadas} atrasada{p.atrasadas === 1 ? '' : 's'}</Badge>}
                    </span>
                  ) : <span className="text-hipo-muted">—</span>}
                </td>
                <td className="px-4 py-3">{p.percentual === null ? '—' : `${p.percentual}%`}</td>
                <td className="px-4 py-3 text-hipo-slate">
                  {p.aulas_total === 0 ? 'Sem trilha para o cargo' : (p.proxima_aula || 'Tudo em dia')}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </Card>
  );
}

export default function Estudio() {
  const navigate = useNavigate();
  const [params, setParams] = useSearchParams();
  const aba = params.get('aba') === 'time' ? 'time' : 'trilhas';

  const [vocab, setVocab] = useState(null);
  const [trilhas, setTrilhas] = useState([]);
  const [time, setTime] = useState([]);
  const [erro, setErro] = useState('');
  const [nova, setNova] = useState(false);
  const [aberta, setAberta] = useState(null);

  const carregar = useCallback(async () => {
    setErro('');
    try {
      const [v, t, p] = await Promise.all([
        api.get('/uc/estudio/vocabulario'),
        api.get('/uc/estudio/trilhas'),
        api.get('/uc/estudio/time'),
      ]);
      setVocab(v.data);
      setTrilhas(t.data);
      setTime(p.data);
    } catch (e) {
      setErro(mensagemDeErro(e, 'Não foi possível carregar o estúdio.'));
    }
  }, []);

  useEffect(() => { carregar(); }, [carregar]);

  return (
    <div className="max-w-6xl mx-auto space-y-4">
      <PageHeader
        title="Estúdio da Universidade"
        subtitle="Conteúdo por pilar, manual de cada função e o andamento do time."
        actions={(
          <>
            <Button variant="ghost" icon={ArrowLeft} onClick={() => navigate('/uc')}>Minha UC</Button>
            {vocab && <Button icon={Plus} onClick={() => setNova(true)}>Nova trilha</Button>}
          </>
        )}
      />

      {erro && <AlertMessage tipo="erro">{erro}</AlertMessage>}

      {vocab && (
        <>
          <Tabs
            items={[
              { key: 'trilhas', label: 'Trilhas' },
              { key: 'time', label: 'Time' },
            ]}
            value={aba}
            onChange={(k) => setParams(k === 'time' ? { aba: 'time' } : {})}
          />
          {aba === 'trilhas' ? (
            <AbaTrilhas vocab={vocab} trilhas={trilhas} onAbrir={setAberta} />
          ) : (
            <AbaTime linhas={time} onAbrir={(p) => navigate(`/uc?usuario_id=${p.id}`)} />
          )}
        </>
      )}

      <NovaTrilha
        aberto={nova}
        vocab={vocab}
        onFechar={() => setNova(false)}
        onCriada={(t) => { setNova(false); carregar(); setAberta(t.id); }}
      />

      {aberta && vocab && (
        <EditorTrilha
          trilhaId={aberta}
          vocab={vocab}
          onFechar={() => setAberta(null)}
          onMudou={carregar}
        />
      )}
    </div>
  );
}
