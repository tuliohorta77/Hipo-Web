// web/src/components/crm/OportunidadeDetalhe.jsx
//
// Visão 360 da oportunidade — mesma estrutura da conta: identificação fixa em
// cima, resto em abas, form único com Salvar no rodapé do modal.
//
// Fase e status NÃO são campos deste form. Eles mudam por ações — mover fase,
// finalizar, reabrir, suspender — porque cada uma dispara regra de negócio e
// grava evento. Tratá-los como campo editável deixaria o usuário salvar um
// estado que o funil não permite.

import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import {
  Users, Swords, History, RotateCcw, FileText,
  PauseCircle, PlayCircle, Flag, Plus, X, Building2, Maximize2,
} from 'lucide-react';

import api from '../../api';
import AbaTarefas from './AbaTarefas';
import AbaProposta from './AbaProposta';
import Tabs from '../ui/Tabs';
import Input, { Select } from '../ui/Input';
import Button from '../ui/Button';
import Badge from '../ui/Badge';
import Empty from '../ui/Empty';
import AlertMessage from '../ui/AlertMessage';
import { AcoesDoModal } from '../ui/Modal';
import EntityPicker from '../EntityPicker';

// proxima_acao_em / proxima_acao_tipo saíram: quem responde "qual o próximo
// passo" agora é a aba Tarefas. Os campos continuavam na tela depois de o
// backend tirá-los de CAMPOS_EDITAVEIS — o usuário digitava, salvava, e o
// PATCH ignorava em silêncio.
const CAMPOS = [
  'contato_id', 'valor_mensalidade', 'temperatura', 'previsao_fechamento',
  'descricao', 'observacoes', 'origem_id', 'finder_conta_id',
];

/**
 * Campo com o rótulo na MESMA linha do controle.
 *
 * No trilho de 208px, rótulo em cima gastava duas alturas por campo sem
 * necessidade — e são só duas palavras curtas. Local de propósito: mexer no
 * Input/Select compartilhado por causa de um caso arriscaria todas as telas.
 */
function CampoInline({ id, rotulo, children }) {
  return (
    <div className="flex items-center gap-2">
      <label htmlFor={id} className="w-16 shrink-0 text-xs text-hipo-slate">
        {rotulo}
      </label>
      {children}
    </div>
  );
}

const CLASSE_INLINE =
  'flex-1 min-w-0 h-8 px-2 text-xs rounded-lg border border-hipo-border ' +
  'bg-hipo-card text-hipo-ink focus:outline-none focus:ring-2 focus:ring-hipo-blue ' +
  'disabled:bg-hipo-bg disabled:text-hipo-slate';

// Só as fases abertas: Finalizado não é escolha de seletor, é desfecho com
// status e motivo.
const FASES = [
  { valor: 'suspect', rotulo: 'Suspect' },
  { valor: 'lead', rotulo: 'Lead' },
  { valor: 'qualificacao', rotulo: 'Qualificação' },
  { valor: 'apresentacao', rotulo: 'Apresentação' },
  { valor: 'negociacao', rotulo: 'Negociação' },
];

const PAPEIS = ['EC', 'SDR', 'EV'];

const TEMPERATURAS = [0, 10, 20, 30, 40, 50, 60, 70, 80, 90];

const TOM_STATUS = {
  ativa: 'success', suspensa: 'warning', conquistado: 'success',
  perdido: 'danger', cancelado: 'neutral',
};

const ROTULO_EVENTO = {
  criacao: 'Criada', fase: 'Mudança de fase',
  status: 'Mudança de status', reabertura: 'Reaberta',
};

function mensagemDeErro(err, padrao) {
  const d = err?.response?.data?.detail;
  if (typeof d === 'string') return d;
  if (Array.isArray(d) && d[0]?.msg) return d[0].msg;
  if (d?.mensagem) return d.mensagem;
  return padrao;
}

function paraInputData(iso) {
  return iso ? String(iso).slice(0, 10) : '';
}

function formatarDataHora(iso) {
  if (!iso) return '';
  return new Date(iso).toLocaleString('pt-BR', {
    day: '2-digit', month: '2-digit', year: 'numeric',
    hour: '2-digit', minute: '2-digit',
  });
}

// ── Aba: envolvidos e concorrentes ───────────────────────────────────

function AbaEnvolvidos({ oportunidade, onMudou, setErro }) {
  const [usuarios, setUsuarios] = useState([]);
  const [novoUsuario, setNovoUsuario] = useState('');
  const [novoPapel, setNovoPapel] = useState('EV');
  const [ocupado, setOcupado] = useState(false);

  useEffect(() => {
    api.get('/crm/dominio/usuarios')
      .then(({ data }) => setUsuarios(data))
      .catch((err) => setErro(mensagemDeErro(err, 'Não foi possível carregar os usuários.')));
  }, [setErro]);

  const envolvidos = oportunidade.envolvidos || [];

  async function salvarLista(lista) {
    setOcupado(true);
    setErro(null);
    try {
      await api.put(`/crm/oportunidades/${oportunidade.id}/envolvidos`, lista);
      onMudou();
    } catch (err) {
      setErro(mensagemDeErro(err, 'Não foi possível atualizar os envolvidos.'));
    } finally {
      setOcupado(false);
    }
  }

  function adicionar() {
    if (!novoUsuario) return;
    const ja = envolvidos.some(
      (e) => e.usuario_id === novoUsuario && e.papel === novoPapel
    );
    if (ja) {
      setErro('Essa pessoa já está com esse papel.');
      return;
    }
    salvarLista([
      ...envolvidos.map((e) => ({ usuario_id: e.usuario_id, papel: e.papel })),
      { usuario_id: novoUsuario, papel: novoPapel },
    ]);
    setNovoUsuario('');
  }

  function remover(alvo) {
    salvarLista(
      envolvidos
        .filter((e) => !(e.usuario_id === alvo.usuario_id && e.papel === alvo.papel))
        .map((e) => ({ usuario_id: e.usuario_id, papel: e.papel }))
    );
  }

  return (
    <div className="space-y-4 max-w-3xl">
      <div className="flex gap-2 items-end">
        <Select
          label="Pessoa"
          className="flex-1"
          value={novoUsuario}
          onChange={(e) => setNovoUsuario(e.target.value)}
        >
          <option value="">— selecione —</option>
          {usuarios.map((u) => (
            <option key={u.id} value={u.id}>
              {u.nome}{u.cargo ? ` (${u.cargo})` : ''}
            </option>
          ))}
        </Select>
        <Select
          label="Papel"
          value={novoPapel}
          onChange={(e) => setNovoPapel(e.target.value)}
        >
          {PAPEIS.map((p) => <option key={p} value={p}>{p}</option>)}
        </Select>
        <Button icon={Plus} loading={ocupado} disabled={!novoUsuario} onClick={adicionar}>
          Adicionar
        </Button>
      </div>

      {envolvidos.length === 0 ? (
        <Empty
          title="Ninguém vinculado"
          description="A mesma pessoa pode entrar com mais de um papel — quem prospectou como SDR e tocou como EV, por exemplo."
          icon={Users}
        />
      ) : (
        <ul className="divide-y divide-hipo-border border border-hipo-border rounded-lg">
          {envolvidos.map((e) => (
            <li key={`${e.usuario_id}-${e.papel}`} className="flex items-center gap-3 px-3 py-2.5">
              <Badge tone="info">{e.papel}</Badge>
              <span className="flex-1 text-sm text-hipo-ink truncate">{e.nome}</span>
              <Button
                size="sm"
                variant="ghost"
                icon={X}
                aria-label={`Remover ${e.nome} como ${e.papel}`}
                onClick={() => remover(e)}
              >
                Remover
              </Button>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

function AbaConcorrentes({ oportunidade, onMudou, setErro }) {
  const [lista, setLista] = useState([]);
  const [selecionado, setSelecionado] = useState('');
  const [novo, setNovo] = useState('');
  const [ocupado, setOcupado] = useState(false);

  const carregar = useCallback(() => {
    api.get('/crm/dominio/concorrentes')
      .then(({ data }) => setLista(data))
      .catch((err) => setErro(mensagemDeErro(err, 'Não foi possível carregar os concorrentes.')));
  }, [setErro]);

  useEffect(() => { carregar(); }, [carregar]);

  const atuais = oportunidade.concorrentes || [];

  async function salvar(ids) {
    setOcupado(true);
    setErro(null);
    try {
      await api.put(`/crm/oportunidades/${oportunidade.id}/concorrentes`, ids);
      onMudou();
    } catch (err) {
      setErro(mensagemDeErro(err, 'Não foi possível atualizar os concorrentes.'));
    } finally {
      setOcupado(false);
    }
  }

  async function adicionar() {
    let id = selecionado ? Number(selecionado) : null;
    if (!id && novo.trim()) {
      try {
        const { data } = await api.post('/crm/dominio/concorrentes', { nome: novo.trim() });
        id = data.id;
        setNovo('');
        carregar();
      } catch (err) {
        setErro(mensagemDeErro(err, 'Não foi possível criar o concorrente.'));
        return;
      }
    }
    if (!id || atuais.some((c) => c.id === id)) return;
    salvar([...atuais.map((c) => c.id), id]);
    setSelecionado('');
  }

  return (
    <div className="space-y-4 max-w-3xl">
      <div className="flex gap-2 items-end">
        <Select
          label="Concorrente"
          className="flex-1"
          value={selecionado}
          onChange={(e) => setSelecionado(e.target.value)}
        >
          <option value="">— selecione —</option>
          {lista.map((c) => <option key={c.id} value={c.id}>{c.nome}</option>)}
        </Select>
        <Input
          label="Ou criar"
          placeholder="nome do concorrente"
          className="flex-1"
          value={novo}
          onChange={(e) => setNovo(e.target.value)}
        />
        <Button
          icon={Plus}
          loading={ocupado}
          disabled={!selecionado && !novo.trim()}
          onClick={adicionar}
        >
          Adicionar
        </Button>
      </div>

      {atuais.length === 0 ? (
        <Empty title="Nenhum concorrente registrado" icon={Swords} />
      ) : (
        <ul className="flex flex-wrap gap-2">
          {atuais.map((c) => (
            <li key={c.id}>
              <button
                type="button"
                onClick={() => salvar(atuais.filter((x) => x.id !== c.id).map((x) => x.id))}
                className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full border border-hipo-border text-sm text-hipo-ink hover:bg-hipo-dangerSoft hover:border-hipo-dangerBorder"
                aria-label={`Remover ${c.nome}`}
              >
                {c.nome}<X size={12} />
              </button>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

function AbaHistorico({ oportunidadeId }) {
  const [eventos, setEventos] = useState(null);
  const [erro, setErro] = useState(null);

  useEffect(() => {
    let vivo = true;
    setEventos(null);
    api.get(`/crm/oportunidades/${oportunidadeId}/eventos`)
      .then(({ data }) => { if (vivo) setEventos(data); })
      .catch((err) => {
        if (vivo) setErro(mensagemDeErro(err, 'Não foi possível carregar o histórico.'));
      });
    return () => { vivo = false; };
  }, [oportunidadeId]);

  if (erro) return <AlertMessage tipo="erro">{erro}</AlertMessage>;
  if (eventos === null) {
    return <p className="py-8 text-center text-sm text-hipo-slate">Carregando…</p>;
  }
  if (eventos.length === 0) {
    return <Empty title="Sem histórico" icon={History} />;
  }

  return (
    <ol className="relative border-l border-hipo-border ml-2 space-y-4 py-1">
      {eventos.map((e, i) => (
        <li key={`${e.tipo}-${e.criado_em}-${i}`} className="ml-5">
          <span className="absolute -left-1.5 w-3 h-3 rounded-full bg-hipo-blueSoft border-2 border-hipo-blue" />
          <div className="flex flex-wrap items-baseline gap-x-2">
            <span className="text-sm font-medium text-hipo-ink">
              {ROTULO_EVENTO[e.tipo] || e.tipo}
            </span>
            <span className="text-xs text-hipo-slate">{formatarDataHora(e.criado_em)}</span>
          </div>
          <p className="text-sm text-hipo-slate">
            {e.de ? `${e.de} → ${e.para}` : e.para}
          </p>
          {e.usuario && <p className="text-xs text-hipo-muted">por {e.usuario}</p>}
        </li>
      ))}
    </ol>
  );
}

// ── Componente principal ─────────────────────────────────────────────

export default function OportunidadeDetalhe({
  oportunidade,
  onRecarregar,
  onSalvo,
  onDesfecho,
  onFechar,
  // Drilldown da empresa: quem monta o modal da conta é a página, porque é
  // ela que já tem o modal da oportunidade e sabe empilhar um sobre o outro.
  // Opcional — sem o handler, o botão simplesmente não aparece.
  onAbrirConta,
}) {
  const [form, setForm] = useState({});
  const [aba, setAba] = useState('dados');
  const [erro, setErro] = useState(null);
  const [salvando, setSalvando] = useState(false);
  const [acaoEmCurso, setAcaoEmCurso] = useState(null);
  const [contatos, setContatos] = useState([]);
  const [origens, setOrigens] = useState([]);
  const idCarregado = useRef(null);

  const finalizada = ['perdido', 'cancelado', 'conquistado'].includes(oportunidade.status);

  useEffect(() => {
    if (idCarregado.current === oportunidade.id) return;
    idCarregado.current = oportunidade.id;
    setForm({
      contato_id: oportunidade.contato_id || '',
      valor_mensalidade: oportunidade.valor_mensalidade ?? '',
      temperatura: oportunidade.temperatura ?? '',
      previsao_fechamento: paraInputData(oportunidade.previsao_fechamento),
      descricao: oportunidade.descricao || '',
      observacoes: oportunidade.observacoes || '',
      origem_id: oportunidade.origem_id ?? '',
      finder_conta_id: oportunidade.finder_conta_id || '',
    });
    setAba('dados');
    setErro(null);
  }, [oportunidade]);

  useEffect(() => {
    api.get(`/crm/contatos`, { params: { conta_id: oportunidade.conta_id, limit: 100 } })
      // `|| []` não é paranoia: uma resposta sem `itens` deixava o map de
      // baixo estourar e a tela inteira virava branco. Erro de dado não pode
      // derrubar a tela.
      .then(({ data }) => setContatos(data.itens || []))
      .catch(() => setContatos([]));
    api.get('/crm/dominio/origens')
      .then(({ data }) => setOrigens(data))
      .catch(() => setOrigens([]));
  }, [oportunidade.conta_id]);

  const sujo = useMemo(() => {
    const original = {
      contato_id: oportunidade.contato_id || '',
      valor_mensalidade: oportunidade.valor_mensalidade ?? '',
      temperatura: oportunidade.temperatura ?? '',
      previsao_fechamento: paraInputData(oportunidade.previsao_fechamento),
      descricao: oportunidade.descricao || '',
      observacoes: oportunidade.observacoes || '',
      origem_id: oportunidade.origem_id ?? '',
      finder_conta_id: oportunidade.finder_conta_id || '',
    };
    return CAMPOS.some((c) => String(form[c] ?? '') !== String(original[c] ?? ''));
  }, [form, oportunidade]);

  function set(campo, valor) {
    setForm((f) => ({ ...f, [campo]: valor }));
  }

  const salvar = useCallback(async () => {
    setSalvando(true);
    setErro(null);
    const corpo = {};
    for (const c of CAMPOS) {
      let v = form[c];
      if (v === '' || v === null || v === undefined) v = null;
      else if (c === 'origem_id' || c === 'temperatura') v = Number(v);
      corpo[c] = v;
    }
    try {
      const { data } = await api.patch(`/crm/oportunidades/${oportunidade.id}`, corpo);
      onSalvo(data);
    } catch (err) {
      setErro(mensagemDeErro(err, 'Não foi possível salvar a oportunidade.'));
    } finally {
      setSalvando(false);
    }
  }, [form, oportunidade.id, onSalvo]);

  async function acao(chave, fn) {
    setAcaoEmCurso(chave);
    setErro(null);
    try {
      const { data } = await fn();
      onSalvo(data);
    } catch (err) {
      setErro(mensagemDeErro(err, 'Não foi possível concluir a ação.'));
    } finally {
      setAcaoEmCurso(null);
    }
  }

  const abas = [
    { key: 'dados', label: 'Dados' },
    // Tarefas logo depois de Dados: é a aba que responde "e agora?", que é a
    // pergunta que traz o vendedor a esta tela. O badge conta as abertas e
    // vem do detalhe, não de uma segunda chamada — precisa estar certo antes
    // de alguém clicar.
    { key: 'tarefas', label: 'Tarefas', badge: oportunidade.tarefas_abertas || undefined },
    { key: 'proposta', label: 'Proposta' },
    { key: 'envolvidos', label: 'Envolvidos', badge: oportunidade.envolvidos?.length || undefined },
    { key: 'concorrentes', label: 'Concorrentes', badge: oportunidade.concorrentes?.length || undefined },
    { key: 'historico', label: 'Histórico' },
  ];

  return (
    /*
      ── Trilho à esquerda, conteúdo à direita ──
      A faixa de abas horizontal comia ~44px da altura do modal, mais os
      ~110px do bloco de fase/temperatura/mensalidade que ficava acima dela.
      Altura é o recurso escasso aqui — largura sobra. Movendo estado e
      navegação para uma coluna de 13rem, o conteúdo da aba passa a ter a
      altura inteira do modal.
    */
    <div className="flex h-full min-h-0">

      {/* ── Trilho: estado, navegação e ações ── */}
      <aside className="shrink-0 w-52 border-r border-hipo-border bg-hipo-bg/40 flex flex-col min-h-0">
        <div className="px-3 pt-3 pb-3 space-y-2">
          {/*
            A empresa, no topo do trilho e clicável.

            O título do modal já diz o nome, mas dizer não é o mesmo que
            levar: quem está na negociação e precisa do cadastro — mudar a
            vertical, corrigir o endereço, ver os contatos, ver as OUTRAS
            oportunidades da mesma empresa — tinha que fechar tudo, ir para
            Contas e buscar de novo pela razão social.

            Abre a visão 360 da conta EM CIMA desta, e editável. Empilhar em
            vez de navegar é o que preserva o que já estava aqui: fase,
            aba selecionada e qualquer campo em edição continuam intactos
            quando o drilldown fecha.
          */}
          {onAbrirConta && (
            <button
              type="button"
              onClick={() => onAbrirConta(oportunidade.conta_id)}
              title={`Abrir a conta: ${oportunidade.conta_razao_social}`}
              aria-label={`Abrir a conta ${oportunidade.conta_razao_social}`}
              className={
                'w-full flex items-center gap-1.5 px-2 py-1.5 rounded-lg text-xs ' +
                'border border-hipo-border bg-hipo-card text-hipo-ink text-left ' +
                'hover:bg-hipo-blueSoft hover:border-hipo-blue transition-colors ' +
                'focus:outline-none focus-visible:ring-2 focus-visible:ring-hipo-blue'
              }
            >
              <Building2 size={13} className="shrink-0 text-hipo-blue" aria-hidden="true" />
              <span className="truncate font-medium">{oportunidade.conta_razao_social}</span>
              <Maximize2 size={12} className="ml-auto shrink-0 text-hipo-slate" aria-hidden="true" />
            </button>
          )}

          {/*
            Fase é ação, não campo: mudar dispara regra e grava evento. Por
            isso o select chama o endpoint na hora, sem passar pelo Salvar.
          */}
          <CampoInline id="opp-fase" rotulo="Fase">
            <select
              id="opp-fase"
              aria-label="Fase"
              className={CLASSE_INLINE}
              value={oportunidade.fase}
              disabled={finalizada || Boolean(acaoEmCurso)}
              onChange={(e) => acao('fase', () =>
                api.patch(`/crm/oportunidades/${oportunidade.id}/fase`, { fase: e.target.value })
              )}
            >
              {FASES.map((f) => <option key={f.valor} value={f.valor}>{f.rotulo}</option>)}
              {finalizada && <option value="finalizado">Finalizado</option>}
            </select>
          </CampoInline>

          <CampoInline id="opp-temperatura" rotulo="Temp.">
            <select
              id="opp-temperatura"
              aria-label="Temperatura"
              className={CLASSE_INLINE}
              value={form.temperatura ?? ''}
              disabled={oportunidade.status !== 'ativa'}
              onChange={(e) => set('temperatura', e.target.value)}
            >
              {oportunidade.status !== 'ativa' && <option value="">—</option>}
              {TEMPERATURAS.map((t) => <option key={t} value={t}>{t}</option>)}
            </select>
          </CampoInline>
        </div>

        {/* Navegação. Rola sozinha se um dia houver abas demais. */}
        <div className="flex-1 min-h-0 overflow-y-auto px-2 py-2 border-t border-hipo-border">
          <Tabs items={abas} value={aba} onChange={setAba} orientacao="vertical" />
        </div>

      </aside>

      {/* ── Conteúdo da aba ── */}
      <div className="flex-1 min-w-0 flex flex-col min-h-0">
        {erro && (
          <div className="shrink-0 px-5 pt-4">
            <AlertMessage tipo="erro">{erro}</AlertMessage>
          </div>
        )}

      <div className="px-5 py-5 flex-1 min-h-0 overflow-y-auto">
        {aba === 'dados' && (
          // Três colunas e sem max-w: com dois campos a menos (a próxima ação
          // virou a tabela `tarefas`), tudo cabe na altura do modal sem rolar.
          <div className="grid grid-cols-1 md:grid-cols-3 gap-x-4 gap-y-3">
            <Select
              label="Contato"
              value={form.contato_id || ''}
              onChange={(e) => set('contato_id', e.target.value)}
            >
              <option value="">— sem contato —</option>
              {contatos.map((c) => <option key={c.id} value={c.id}>{c.nome}</option>)}
            </Select>
            <Select
              label="Origem"
              value={form.origem_id ?? ''}
              onChange={(e) => set('origem_id', e.target.value)}
            >
              <option value="">— sem origem —</option>
              {origens.map((o) => <option key={o.id} value={o.id}>{o.nome}</option>)}
            </Select>

            <Input
              label="Previsão de fechamento"
              type="date"
              value={form.previsao_fechamento || ''}
              onChange={(e) => set('previsao_fechamento', e.target.value)}
            />
            <div>
              <EntityPicker
                label="Finder (parceiro que indicou)"
                value={form.finder_conta_id
                  ? { id: form.finder_conta_id, razao_social: oportunidade.finder_razao_social }
                  : null}
                onChange={(c) => set('finder_conta_id', c ? c.id : '')}
                buscar={async (q) => {
                  const { data } = await api.get('/crm/contas/busca', {
                    params: { q, apenas_finders: false },
                  });
                  return data.filter((c) => c.id !== oportunidade.conta_id);
                }}
                paraItem={(c) => ({
                  id: c.id,
                  titulo: c.razao_social,
                  subtitulo: c.cnpj_formatado,
                  badge: c.eh_finder ? { texto: 'finder', tone: 'info' } : undefined,
                })}
                placeholder="Nenhum"
              />
            </div>

            <Input
              label="Descrição"
              className="md:col-span-3"
              value={form.descricao || ''}
              onChange={(e) => set('descricao', e.target.value)}
            />
            <div className="md:col-span-3">
              <label
                htmlFor="opp-observacoes"
                className="block text-sm font-medium text-hipo-ink mb-1.5"
              >
                Observações
              </label>
              <textarea
                id="opp-observacoes"
                rows={3}
                value={form.observacoes || ''}
                onChange={(e) => set('observacoes', e.target.value)}
                className="w-full px-3 py-2 rounded-lg border border-hipo-border bg-hipo-card text-sm text-hipo-ink focus:outline-none focus:ring-2 focus:ring-hipo-blue resize-y"
              />
            </div>
          </div>
        )}

        {aba === 'envolvidos' && (
          <AbaEnvolvidos
            oportunidade={oportunidade}
            onMudou={onRecarregar}
            setErro={setErro}
          />
        )}

        {aba === 'concorrentes' && (
          <AbaConcorrentes
            oportunidade={oportunidade}
            onMudou={onRecarregar}
            setErro={setErro}
          />
        )}

        {aba === 'tarefas' && (
          <AbaTarefas oportunidade={oportunidade} onMudou={onRecarregar} />
        )}

        {/*
          Proposta ainda não existe como modelo. Vidas, valor por vida e o
          versionamento (v1, v2, v3) dependem do catálogo e da precificação,
          que estão em aberto. Aba criada vazia de propósito: reservar o lugar
          é barato, adivinhar o modelo de dados é caro.
        */}
        {aba === 'proposta' && (
          <div className="space-y-5">
            {/*
              A mensalidade continua digitável aqui para as oportunidades
              que ainda não têm proposta gerada — negociação que começou no
              telefone tem valor antes de ter documento. Gerar uma proposta
              sobrescreve este campo com vidas x valor por vida: o funil não
              pode somar um ticket diferente do que foi enviado ao cliente.
            */}
            <div className="max-w-md">
              <Input
                label="Mensalidade (R$)"
                type="number"
                min="0"
                step="0.01"
                value={form.valor_mensalidade ?? ''}
                onChange={(e) => set('valor_mensalidade', e.target.value)}
                hint="Gerar uma proposta recalcula este valor a partir das vidas."
              />
            </div>

            <div className="border-t border-hipo-border pt-5">
              <AbaProposta
                oportunidade={oportunidade}
                onGerada={(proposta) => {
                  // O backend já gravou a mensalidade nova. Refletir no
                  // form evita o campo acima mostrar o valor velho até
                  // alguém recarregar — e um "Alterações não salvas"
                  // fantasma se o usuário tocar em qualquer outro campo.
                  set('valor_mensalidade', String(proposta.mensalidade));
                  onRecarregar?.();
                }}
              />
            </div>
          </div>
        )}

        {aba === 'historico' && <AbaHistorico oportunidadeId={oportunidade.id} />}
        </div>

        {/*
          Uma barra só, no CABEÇALHO. Suspender e Finalizar são saídas desta
          tela, igual a Fechar e Salvar — separá-las em cantos diferentes
          obrigava o olho a procurar onde estava cada ação.

          Ficavam no rodapé até aqui. Num modal de 92vh isso põe o Salvar a
          uma tela de distância do campo que se acabou de editar; em cima,
          ao lado do X, as saídas da tela ficam todas no mesmo canto.

          O JSX segue no fim do componente porque é aqui que ele se lê — o
          portal do <AcoesDoModal> é que o coloca lá em cima. Consequência
          boa: os botões continuam vizinhos do estado que usam (`sujo`,
          `salvando`, `acaoEmCurso`), sem canal nenhum com o pai.
        */}
        <AcoesDoModal>
        <div
          aria-label="Ações da oportunidade"
          className="flex flex-wrap items-center gap-2"
        >
          <span className="text-xs text-hipo-slate mr-1">
            {sujo ? 'Alterações não salvas' : 'Tudo salvo'}
          </span>

          <div className="flex flex-wrap items-center gap-2">
            {finalizada ? (
              <Button
                size="sm"
                variant="secondary"
                icon={RotateCcw}
                loading={acaoEmCurso === 'reabrir'}
                onClick={() => acao('reabrir', () =>
                  api.post(`/crm/oportunidades/${oportunidade.id}/reabrir`, {})
                )}
              >
                Reabrir
              </Button>
            ) : (
              <>
                <Button
                  size="sm"
                  variant="secondary"
                  icon={oportunidade.status === 'ativa' ? PauseCircle : PlayCircle}
                  loading={acaoEmCurso === 'status'}
                  onClick={() => acao('status', () =>
                    api.patch(`/crm/oportunidades/${oportunidade.id}/status`, {
                      status: oportunidade.status === 'ativa' ? 'suspensa' : 'ativa',
                      temperatura: oportunidade.temperatura ?? 50,
                    })
                  )}
                >
                  {oportunidade.status === 'ativa' ? 'Suspender' : 'Reativar'}
                </Button>
                <Button size="sm" variant="secondary" icon={Flag}
                  onClick={() => onDesfecho(oportunidade)}>
                  Finalizar
                </Button>
              </>
            )}

            <Button size="sm" variant="ghost" onClick={onFechar}>Fechar</Button>
            <Button size="sm" onClick={salvar} disabled={!sujo} loading={salvando}>
              Salvar
            </Button>
          </div>
        </div>
        </AcoesDoModal>
      </div>
    </div>
  );
}
