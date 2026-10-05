// web/src/pages/carreira/Pdi.jsx
//
// Carreira · PDI (plano de desenvolvimento individual). Modelo misto:
//   * o HIPO sugere ações (Desempenho abaixo de 70% da meta; trilha
//     obrigatória atrasada ou vencendo; quiz final reprovado 2+ vezes);
//   * a gestão confirma (ajustando), descarta ou cria uma ação;
//   * o colaborador marca como feita.
//
// As três diretrizes:
//   1. uma tela por função: cada um vê o próprio PDI; a gestão escolhe a
//      pessoa e monta o dela;
//   2. dashboard operacional: abertas, atrasadas e feitas no mês no topo,
//      e cada ação tem a ação dela (feita, editar, abrir trilha);
//   3. próxima tarefa: a tela abre na ação de prazo mais curto.
//
// As REGRAS (sugestão, prazo, quem pode o quê) são do servidor.

import { useCallback, useEffect, useState } from 'react';
import { useNavigate, useSearchParams } from 'react-router-dom';
import {
  CheckCircle2, ClipboardList, GraduationCap, Lightbulb, Pencil, Plus, RotateCcw, Target, X,
} from 'lucide-react';
import api from '../../api';
import PageHeader from '../../components/ui/PageHeader';
import Card, { CardHeader } from '../../components/ui/Card';
import Badge from '../../components/ui/Badge';
import Button from '../../components/ui/Button';
import AlertMessage from '../../components/ui/AlertMessage';
import Empty from '../../components/ui/Empty';
import Modal from '../../components/ui/Modal';
import Input, { Select, Textarea } from '../../components/ui/Input';
import { mensagemDeErro } from '../../components/crm/tarefaComum';
import AbasCarreira from '../../components/carreira/AbasCarreira';

export const TOM_SITUACAO = {
  atrasada: 'danger', vence_logo: 'warning', em_dia: 'neutral', concluida: 'success', cancelada: 'neutral',
};

export function dataBr(iso) {
  if (!iso) return '';
  const [a, m, d] = String(iso).slice(0, 10).split('-');
  return `${d}/${m}/${a}`;
}

function textoPrazo(acao) {
  const s = acao.situacao;
  if (s.codigo === 'atrasada') return `venceu em ${dataBr(acao.prazo)}`;
  if (s.codigo === 'vence_logo') return s.dias_restantes === 0 ? 'vence hoje' : `vence em ${s.dias_restantes} dia(s)`;
  return `até ${dataBr(acao.prazo)}`;
}

function FormAcao({ aberto, inicial, trilhas, onFechar, onSalvar }) {
  const [form, setForm] = useState(inicial);
  const [salvando, setSalvando] = useState(false);
  const [erro, setErro] = useState('');

  useEffect(() => { setForm(inicial); setErro(''); }, [inicial]);
  if (!form) return null;
  const campo = (nome) => (e) => setForm((f) => ({ ...f, [nome]: e.target.value }));

  async function salvar() {
    setErro('');
    if (!form.objetivo.trim()) { setErro('Escreva o objetivo.'); return; }
    if (!form.o_que_fazer.trim()) { setErro('Escreva o que fazer.'); return; }
    if (!form.prazo) { setErro('Defina o prazo.'); return; }
    setSalvando(true);
    try {
      await onSalvar(form);
    } catch (e) {
      setErro(mensagemDeErro(e, 'Não foi possível salvar a ação.'));
    } finally {
      setSalvando(false);
    }
  }

  return (
    <Modal
      aberto={aberto}
      onFechar={onFechar}
      titulo={form.id ? 'Editar ação' : form.chave_origem ? 'Confirmar sugestão' : 'Nova ação'}
      subtitulo={form.origem_rotulo ? `Sugestão do HIPO · ${form.origem_rotulo}` : undefined}
      size="lg"
      footer={(
        <div className="flex justify-end gap-2">
          <Button variant="secondary" onClick={onFechar}>Cancelar</Button>
          <Button onClick={salvar} loading={salvando}>{form.id ? 'Salvar' : 'Criar ação'}</Button>
        </div>
      )}
    >
      <div className="space-y-4">
        {erro && <AlertMessage tipo="erro">{erro}</AlertMessage>}
        <Input id="pdi-objetivo" label="Objetivo" value={form.objetivo} onChange={campo('objetivo')} maxLength={200} />
        <Textarea id="pdi-fazer" label="O que fazer" rows={4} value={form.o_que_fazer} onChange={campo('o_que_fazer')} />
        <div className="grid gap-3 sm:grid-cols-3">
          <Select id="pdi-trilha" label="Trilha de reforço (opcional)" className="sm:col-span-2"
            value={form.trilha_id || ''} onChange={campo('trilha_id')}>
            <option value="">Nenhuma</option>
            {trilhas.map((t) => <option key={t.id} value={t.id}>{t.pilar_rotulo} · {t.titulo}</option>)}
          </Select>
          <Input id="pdi-prazo" label="Prazo" type="date" value={form.prazo} onChange={campo('prazo')} />
        </div>
      </div>
    </Modal>
  );
}

function CartaoAcao({ acao, dados, onConcluir, onReabrir, onEditar, onCancelar, navigate }) {
  const aberta = acao.status === 'aberta';
  return (
    <li className="px-5 py-4 flex flex-col sm:flex-row sm:items-start gap-3" data-testid={`acao-${acao.id}`}>
      <div className="flex-1 min-w-0">
        <div className="flex flex-wrap items-center gap-2 mb-1">
          <Badge tone={TOM_SITUACAO[acao.situacao.codigo]}>{acao.situacao.rotulo}</Badge>
          <Badge tone="info">{acao.origem_rotulo}</Badge>
          {aberta && <span className="text-xs text-hipo-slate">{textoPrazo(acao)}</span>}
          {acao.concluida_automatica && <span className="text-xs text-hipo-slate">concluída pela trilha</span>}
        </div>
        <p className="font-medium text-hipo-ink">{acao.objetivo}</p>
        <p className="text-sm text-hipo-slate whitespace-pre-line mt-0.5">{acao.o_que_fazer}</p>
        {acao.nota_conclusao && <p className="text-xs text-hipo-slate mt-1">Nota: {acao.nota_conclusao}</p>}
        {acao.trilha && (
          <button
            type="button"
            className="mt-1.5 inline-flex items-center gap-1 text-xs text-hipo-blue hover:underline"
            onClick={() => navigate(`/uc/trilhas/${acao.trilha.id}${dados.modo_leitura ? `?usuario_id=${dados.pessoa.id}` : ''}`)}
          >
            <GraduationCap size={12} /> {acao.trilha.titulo}
          </button>
        )}
      </div>
      <div className="flex flex-wrap gap-2 shrink-0">
        {aberta && dados.pode_concluir && (
          <Button size="sm" icon={CheckCircle2} onClick={() => onConcluir(acao)}>Feita</Button>
        )}
        {acao.status === 'concluida' && dados.pode_concluir && !acao.concluida_automatica && (
          <Button size="sm" variant="ghost" icon={RotateCcw} onClick={() => onReabrir(acao)}>Desfazer</Button>
        )}
        {aberta && dados.pode_gerir && (
          <>
            <Button size="sm" variant="secondary" icon={Pencil} onClick={() => onEditar(acao)} aria-label={`Editar ${acao.objetivo}`}>
              Editar
            </Button>
            <Button size="sm" variant="ghost" icon={X} onClick={() => onCancelar(acao)} aria-label={`Cancelar ${acao.objetivo}`}>
              Cancelar
            </Button>
          </>
        )}
      </div>
    </li>
  );
}

function Numero({ rotulo, valor, tom }) {
  return (
    <Card padding="md">
      <p className="text-xs text-hipo-slate">{rotulo}</p>
      <p className={`text-2xl font-semibold tabular-nums ${tom || 'text-hipo-ink'}`}>{valor}</p>
    </Card>
  );
}

export default function Pdi() {
  const navigate = useNavigate();
  const [params, setParams] = useSearchParams();
  const usuarioId = params.get('usuario_id');

  const [dados, setDados] = useState(null);
  const [erro, setErro] = useState('');
  const [aviso, setAviso] = useState('');
  const [form, setForm] = useState(null);

  const carregar = useCallback(async () => {
    setErro('');
    try {
      const { data } = await api.get('/carreira/pdi', { params: usuarioId ? { usuario_id: usuarioId } : {} });
      setDados(data);
    } catch (e) {
      setErro(mensagemDeErro(e, 'Não foi possível carregar o PDI.'));
    }
  }, [usuarioId]);

  useEffect(() => { carregar(); }, [carregar]);

  async function agir(promessa) {
    setAviso('');
    try {
      const { data } = await promessa;
      setDados(data);
    } catch (e) {
      setAviso(mensagemDeErro(e, 'Não foi possível concluir a ação.'));
    }
  }

  const patch = (acao, corpo) => agir(api.patch(`/carreira/pdi/acoes/${acao.id}`, corpo));

  async function salvarForm(f) {
    const corpo = {
      objetivo: f.objetivo, o_que_fazer: f.o_que_fazer, prazo: f.prazo, trilha_id: f.trilha_id || null,
    };
    const { data } = f.id
      ? await api.patch(`/carreira/pdi/acoes/${f.id}`, corpo)
      : await api.post('/carreira/pdi/acoes', {
        ...corpo, usuario_id: dados.pessoa.id, chave_origem: f.chave_origem || null,
      });
    setDados(data);
    setForm(null);
  }

  const cabecalho = (
    <>
      <PageHeader
        title={dados?.modo_leitura ? `Carreira · ${dados.pessoa.nome}` : 'Carreira'}
        subtitle={dados?.modo_leitura
          ? `${dados.pessoa.cargo || 'sem cargo'} · PDI`
          : 'Seu plano de desenvolvimento: o que fazer, até quando.'}
      />
      <AbasCarreira ativa="PDI" />
    </>
  );

  if (erro && !dados) {
    return <div className="max-w-6xl mx-auto space-y-4">{cabecalho}<AlertMessage tipo="erro">{erro}</AlertMessage></div>;
  }
  if (!dados) {
    return <div className="max-w-6xl mx-auto space-y-4">{cabecalho}<p className="text-sm text-hipo-slate p-4">Carregando…</p></div>;
  }

  const prox = dados.proxima;
  const props = {
    dados, navigate,
    onConcluir: (a) => patch(a, { status: 'concluida' }),
    onReabrir: (a) => patch(a, { status: 'aberta' }),
    onCancelar: (a) => patch(a, { status: 'cancelada' }),
    onEditar: (a) => setForm({
      id: a.id, objetivo: a.objetivo, o_que_fazer: a.o_que_fazer, prazo: String(a.prazo).slice(0, 10),
      trilha_id: a.trilha?.id || '',
    }),
  };

  return (
    <div className="max-w-6xl mx-auto space-y-5">
      {cabecalho}

      {dados.pode_gerir && (
        <div className="flex flex-wrap items-center gap-3">
          <label className="text-sm text-hipo-slate inline-flex items-center gap-2">
            Pessoa
            <select
              aria-label="Pessoa"
              className="h-9 rounded-lg border border-hipo-border bg-hipo-card px-2 text-sm text-hipo-ink"
              value={usuarioId || ''}
              onChange={(e) => {
                const p = new URLSearchParams(params);
                if (e.target.value) p.set('usuario_id', e.target.value); else p.delete('usuario_id');
                setParams(p);
              }}
            >
              <option value="">Eu</option>
              {dados.pessoas.map((p) => <option key={p.id} value={p.id}>{p.nome} · {p.cargo}</option>)}
            </select>
          </label>
          <Button
            className="ml-auto"
            icon={Plus}
            onClick={() => setForm({ objetivo: '', o_que_fazer: '', prazo: '', trilha_id: '' })}
          >
            Nova ação
          </Button>
        </div>
      )}

      {aviso && <AlertMessage tipo="erro">{aviso}</AlertMessage>}

      <Card padding="md" data-testid="pdi-proxima">
        <p className="text-xs font-semibold uppercase tracking-wide text-hipo-slate mb-2">
          {dados.modo_leitura ? 'Próxima ação da pessoa' : 'Sua próxima ação'}
        </p>
        {prox ? (
          <div className="flex flex-col sm:flex-row sm:items-center gap-3">
            <Target size={22} className="text-hipo-blue shrink-0" aria-hidden="true" />
            <div className="flex-1 min-w-0">
              <p className="text-h2 text-hipo-ink">{prox.objetivo}</p>
              <p className="text-sm text-hipo-slate mt-1 whitespace-pre-line">{prox.o_que_fazer}</p>
              <div className="flex flex-wrap items-center gap-2 mt-2">
                <Badge tone={TOM_SITUACAO[prox.situacao.codigo]}>{prox.situacao.rotulo}</Badge>
                <span className="text-xs text-hipo-slate">{textoPrazo(prox)}</span>
              </div>
            </div>
            <div className="flex gap-2">
              {prox.trilha && (
                <Button variant="secondary" icon={GraduationCap}
                  onClick={() => navigate(`/uc/trilhas/${prox.trilha.id}${dados.modo_leitura ? `?usuario_id=${dados.pessoa.id}` : ''}`)}>
                  Abrir trilha
                </Button>
              )}
              {dados.pode_concluir && (
                <Button icon={CheckCircle2} onClick={() => props.onConcluir(prox)}>Feita</Button>
              )}
            </div>
          </div>
        ) : (
          <Empty
            icon={ClipboardList}
            title="Nenhuma ação aberta"
            description={dados.pode_gerir
              ? 'Confirme uma sugestão do HIPO abaixo ou crie uma ação.'
              : 'Quando a gestão montar o seu PDI, a próxima ação aparece aqui.'}
            className="py-4"
          />
        )}
      </Card>

      <div className="grid gap-4 grid-cols-3">
        <Numero rotulo="Abertas" valor={dados.resumo.abertas} />
        <Numero rotulo="Atrasadas" valor={dados.resumo.atrasadas} tom={dados.resumo.atrasadas ? 'text-hipo-danger' : undefined} />
        <Numero rotulo="Feitas no mês" valor={dados.resumo.feitas_no_mes} tom="text-hipo-success" />
      </div>

      {dados.pode_gerir && (
        <Card padding="none" data-testid="pdi-sugestoes">
          <div className="px-5 pt-4">
            <CardHeader title="Sugestões do HIPO" hint="Do Desempenho e da Universidade. Confirme ajustando, ou descarte." />
          </div>
          {dados.sugestoes.length === 0 ? (
            <p className="px-5 pb-4 text-sm text-hipo-slate">Nada a sugerir agora.</p>
          ) : (
            <ul className="divide-y divide-hipo-border">
              {dados.sugestoes.map((s) => (
                <li key={s.chave} className="px-5 py-4 flex flex-col sm:flex-row sm:items-start gap-3">
                  <Lightbulb size={18} className="text-hipo-warning shrink-0 mt-0.5" aria-hidden="true" />
                  <div className="flex-1 min-w-0">
                    <Badge tone="info">{s.origem_rotulo}</Badge>
                    <p className="font-medium text-hipo-ink mt-1">{s.objetivo}</p>
                    <p className="text-sm text-hipo-slate">{s.o_que_fazer}</p>
                  </div>
                  <div className="flex gap-2 shrink-0">
                    <Button size="sm" onClick={() => setForm({
                      objetivo: s.objetivo, o_que_fazer: s.o_que_fazer, prazo: String(s.prazo).slice(0, 10),
                      trilha_id: s.trilha_id || '', chave_origem: s.chave, origem_rotulo: s.origem_rotulo,
                    })}>
                      Confirmar
                    </Button>
                    <Button size="sm" variant="ghost"
                      onClick={() => agir(api.post('/carreira/pdi/sugestoes/descartar', { usuario_id: dados.pessoa.id, chave: s.chave }))}>
                      Descartar
                    </Button>
                  </div>
                </li>
              ))}
            </ul>
          )}
        </Card>
      )}

      {!dados.pode_gerir && dados.sugestoes_pendentes > 0 && (
        <AlertMessage tipo="info">
          O HIPO tem {dados.sugestoes_pendentes} sugestão(ões) para o seu PDI. A gestão revisa com você e confirma.
        </AlertMessage>
      )}

      <Card padding="none">
        <div className="px-5 pt-4"><CardHeader title="Ações abertas" hint="Por prazo." /></div>
        {dados.acoes_abertas.length === 0 ? (
          <p className="px-5 pb-4 text-sm text-hipo-slate">Nenhuma.</p>
        ) : (
          <ul className="divide-y divide-hipo-border">
            {dados.acoes_abertas.map((a) => <CartaoAcao key={a.id} acao={a} {...props} />)}
          </ul>
        )}
      </Card>

      {dados.acoes_feitas.length > 0 && (
        <Card padding="none">
          <div className="px-5 pt-4"><CardHeader title="Feitas e canceladas" hint="As 20 mais recentes." /></div>
          <ul className="divide-y divide-hipo-border">
            {dados.acoes_feitas.map((a) => <CartaoAcao key={a.id} acao={a} {...props} />)}
          </ul>
        </Card>
      )}

      <FormAcao
        aberto={!!form}
        inicial={form}
        trilhas={dados.trilhas}
        onFechar={() => setForm(null)}
        onSalvar={salvarForm}
      />
    </div>
  );
}
