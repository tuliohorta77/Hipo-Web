// web/src/components/crm/ContaDetalhe.jsx
//
// Visão 360 da conta: bloco fixo com a identificação em cima, o resto em abas.
//
// Decisões desta tela:
//
//   * Form ÚNICO. As abas organizam visualmente, mas endereço, telefones e
//     observações fazem parte do mesmo registro — separar em vários "salvar"
//     faria o usuário salvar três vezes para corrigir um cadastro.
//     O botão fica no rodapé, sempre visível, e só habilita quando há mudança.
//
//   * Contatos e Histórico ficam FORA do form: vincular um contato é uma ação
//     imediata, não um campo em edição. Por isso essas abas não sujam o form
//     nem dependem do Salvar.
//
//   * O CNPJ é somente leitura. Trocar o CNPJ de uma conta é trocar de
//     empresa, não editar — o backend também não aceita no PATCH.
//
//   * O vendedor é derivado das oportunidades ativas, então não é campo:
//     é informação exibida.

import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import {
  Briefcase, Users, MapPin, Phone, FileText, History,
  Plus, UserCircle, TrendingUp,
} from 'lucide-react';

import api from '../../api';
import Tabs from '../ui/Tabs';
import Input, { Select } from '../ui/Input';
import Button from '../ui/Button';
import Badge from '../ui/Badge';
import Empty from '../ui/Empty';
import AlertMessage from '../ui/AlertMessage';
import Table, { Th, Tr, Td } from '../ui/Table';
import ContatosDaConta from './ContatosDaConta';

const UFS = [
  'AC', 'AL', 'AM', 'AP', 'BA', 'CE', 'DF', 'ES', 'GO', 'MA', 'MG', 'MS',
  'MT', 'PA', 'PB', 'PE', 'PI', 'PR', 'RJ', 'RN', 'RO', 'RR', 'RS', 'SC',
  'SE', 'SP', 'TO',
];

// Campos que o PATCH aceita. Espelha CAMPOS_EDITAVEIS do router — se
// divergir, o front manda campo que o backend ignora em silêncio.
const CAMPOS = [
  'razao_social', 'nome_fantasia', 'vertical_id', 'num_funcionarios',
  'cep', 'logradouro', 'numero', 'complemento', 'bairro', 'cidade', 'uf',
  'telefone', 'telefone_2', 'email', 'observacoes', 'eh_finder', 'ativo',
];

const FASES = {
  lead: 'Lead',
  qualificacao: 'Qualificação',
  apresentacao: 'Apresentação',
  negociacao: 'Negociação',
  finalizado: 'Finalizado',
};

const TOM_STATUS = {
  ativa: 'success',
  suspensa: 'warning',
  conquistado: 'success',
  perdido: 'danger',
  cancelado: 'neutral',
};

const ROTULO_EVENTO = {
  conta_criada: 'Conta cadastrada',
  contato_vinculado: 'Contato vinculado',
  contato_desvinculado: 'Contato desvinculado',
  oportunidade_criacao: 'Oportunidade criada',
  oportunidade_fase: 'Mudança de fase',
  oportunidade_status: 'Mudança de status',
  oportunidade_reabertura: 'Oportunidade reaberta',
};

function mensagemDeErro(err, padrao) {
  const d = err?.response?.data?.detail;
  if (typeof d === 'string') return d;
  if (Array.isArray(d) && d[0]?.msg) return d[0].msg;
  if (d?.mensagem) return d.mensagem;
  return padrao;
}

function formatarMoeda(v) {
  if (v === null || v === undefined) return '—';
  return Number(v).toLocaleString('pt-BR', { style: 'currency', currency: 'BRL' });
}

function formatarData(iso) {
  if (!iso) return '—';
  return new Date(iso).toLocaleDateString('pt-BR');
}

function formatarDataHora(iso) {
  if (!iso) return '';
  return new Date(iso).toLocaleString('pt-BR', {
    day: '2-digit', month: '2-digit', year: 'numeric',
    hour: '2-digit', minute: '2-digit',
  });
}

function Campo({ children, className = '' }) {
  return <div className={className}>{children}</div>;
}

function Textarea({ label, value, onChange, rows = 6, placeholder, id }) {
  // O htmlFor/id não é detalhe de teste: sem ele o label não anuncia o campo
  // para leitor de tela nem foca o textarea ao ser clicado.
  const campoId = id || (label ? `ta-${label.toLowerCase().replace(/\s+/g, '-')}` : undefined);
  return (
    <div>
      {label && (
        <label
          htmlFor={campoId}
          className="block text-sm font-medium text-hipo-ink mb-1.5"
        >
          {label}
        </label>
      )}
      <textarea
        id={campoId}
        rows={rows}
        value={value || ''}
        placeholder={placeholder}
        onChange={onChange}
        className="w-full px-3 py-2 rounded-lg border border-hipo-border bg-hipo-card text-sm text-hipo-ink placeholder:text-hipo-muted focus:outline-none focus:ring-2 focus:ring-hipo-blue resize-y"
      />
    </div>
  );
}

// ── Abas ─────────────────────────────────────────────────────────────

function AbaOportunidades({ oportunidades }) {
  if (!oportunidades || oportunidades.length === 0) {
    return (
      <Empty
        title="Nenhuma oportunidade nesta conta"
        description="As oportunidades aparecem aqui assim que o módulo entrar no ar."
        icon={Briefcase}
      />
    );
  }

  const ativas = oportunidades.filter((o) => o.status === 'ativa');
  const totalAtivo = ativas.reduce((s, o) => s + Number(o.valor_mensalidade || 0), 0);

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap gap-6 px-1">
        <div>
          <p className="text-xs text-hipo-slate">Oportunidades</p>
          <p className="text-lg font-semibold text-hipo-ink">{oportunidades.length}</p>
        </div>
        <div>
          <p className="text-xs text-hipo-slate">Ativas</p>
          <p className="text-lg font-semibold text-hipo-ink">{ativas.length}</p>
        </div>
        <div>
          <p className="text-xs text-hipo-slate">Mensalidade em aberto</p>
          <p className="text-lg font-semibold text-hipo-ink">{formatarMoeda(totalAtivo)}</p>
        </div>
      </div>

      <div className="border border-hipo-border rounded-lg overflow-hidden">
        <Table>
          <thead>
            <tr>
              <Th>Número</Th>
              <Th>Fase</Th>
              <Th>Status</Th>
              <Th align="right">Mensalidade</Th>
              <Th align="right">Temp.</Th>
              <Th>Previsão</Th>
            </tr>
          </thead>
          <tbody>
            {oportunidades.map((o) => (
              <Tr key={o.id}>
                <Td className="font-mono text-sm">{o.numero}</Td>
                <Td>{FASES[o.fase] || o.fase}</Td>
                <Td>
                  <Badge tone={TOM_STATUS[o.status] || 'neutral'}>{o.status}</Badge>
                </Td>
                <Td align="right">{formatarMoeda(o.valor_mensalidade)}</Td>
                <Td align="right">
                  {o.temperatura === null || o.temperatura === undefined
                    ? <span className="text-hipo-muted">—</span>
                    : o.temperatura}
                </Td>
                <Td>{formatarData(o.previsao_fechamento)}</Td>
              </Tr>
            ))}
          </tbody>
        </Table>
      </div>
    </div>
  );
}

function AbaHistorico({ contaId }) {
  const [eventos, setEventos] = useState(null);
  const [erro, setErro] = useState(null);

  useEffect(() => {
    let vivo = true;
    setEventos(null);
    setErro(null);
    api.get(`/crm/contas/${contaId}/historico`)
      .then(({ data }) => { if (vivo) setEventos(data); })
      .catch((err) => {
        if (vivo) setErro(mensagemDeErro(err, 'Não foi possível carregar o histórico.'));
      });
    return () => { vivo = false; };
  }, [contaId]);

  if (erro) return <AlertMessage tipo="erro">{erro}</AlertMessage>;
  if (eventos === null) {
    return <p className="py-8 text-center text-sm text-hipo-slate">Carregando…</p>;
  }
  if (eventos.length === 0) {
    return <Empty title="Sem histórico" description="Nada registrado nesta conta ainda." icon={History} />;
  }

  return (
    <ol className="relative border-l border-hipo-border ml-2 space-y-4 py-1">
      {eventos.map((e, i) => (
        <li key={`${e.tipo}-${e.quando}-${i}`} className="ml-5">
          <span className="absolute -left-1.5 w-3 h-3 rounded-full bg-hipo-blueSoft border-2 border-hipo-blue" />
          <div className="flex flex-wrap items-baseline gap-x-2">
            <span className="text-sm font-medium text-hipo-ink">
              {ROTULO_EVENTO[e.tipo] || e.tipo}
            </span>
            <span className="text-xs text-hipo-slate">{formatarDataHora(e.quando)}</span>
          </div>
          <p className="text-sm text-hipo-slate">
            {e.titulo}
            {e.detalhe && <span className="text-hipo-muted"> · {e.detalhe}</span>}
          </p>
          {e.usuario && <p className="text-xs text-hipo-muted">por {e.usuario}</p>}
        </li>
      ))}
    </ol>
  );
}

// ── Componente principal ─────────────────────────────────────────────

export default function ContaDetalhe({
  conta,
  verticais,
  onCriarVertical,
  onSalvo,
  onRecarregar,
  registrarSalvar,
}) {
  const [form, setForm] = useState({});
  const [aba, setAba] = useState('oportunidades');
  const [erro, setErro] = useState(null);
  const [salvando, setSalvando] = useState(false);
  const [novaVertical, setNovaVertical] = useState('');
  const [criandoVertical, setCriandoVertical] = useState(false);
  const idCarregado = useRef(null);

  // Recarrega o form quando troca de conta. Comparar por id (e não pelo
  // objeto) evita descartar o que o usuário digitou quando o pai recarrega
  // a conta por causa de uma ação de contato.
  useEffect(() => {
    if (idCarregado.current === conta.id) return;
    idCarregado.current = conta.id;
    setForm(Object.fromEntries(CAMPOS.map((c) => [c, conta[c] ?? (c === 'eh_finder' || c === 'ativo' ? false : '')])));
    setAba('oportunidades');
    setErro(null);
  }, [conta]);

  const sujo = useMemo(
    () => CAMPOS.some((c) => {
      const atual = form[c];
      const original = conta[c] ?? (typeof atual === 'boolean' ? false : '');
      return String(atual ?? '') !== String(original ?? '');
    }),
    [form, conta]
  );

  function set(campo, valor) {
    setForm((f) => ({ ...f, [campo]: valor }));
  }

  const salvar = useCallback(async () => {
    setSalvando(true);
    setErro(null);
    const corpo = {};
    for (const c of CAMPOS) {
      let v = form[c];
      if (c === 'vertical_id') v = v === '' || v === null ? null : Number(v);
      else if (c === 'num_funcionarios') v = v === '' || v === null ? null : Number(v);
      else if (typeof v === 'string') v = v.trim() === '' ? null : v;
      corpo[c] = v;
    }
    try {
      const { data } = await api.patch(`/crm/contas/${conta.id}`, corpo);
      onSalvo(data);
    } catch (err) {
      setErro(mensagemDeErro(err, 'Não foi possível salvar a conta.'));
    } finally {
      setSalvando(false);
    }
  }, [form, conta.id, onSalvo]);

  // O rodapé com o botão Salvar vive no Modal (pai), então ele precisa de
  // acesso ao estado daqui.
  //
  // CUIDADO — este efeito já causou loop infinito de renderização:
  // publicar `salvar` como dependência criava o ciclo
  //   efeito -> setState no pai -> pai re-renderiza -> nova prop onSalvo
  //   -> novo useCallback salvar -> efeito de novo -> ...
  //
  // A ref mantém a função sempre atual sem entrar nas dependências, então o
  // efeito só dispara quando `sujo` ou `salvando` mudam de verdade.
  const salvarRef = useRef(salvar);
  salvarRef.current = salvar;

  useEffect(() => {
    registrarSalvar?.({
      salvar: () => salvarRef.current(),
      sujo,
      salvando,
    });
  }, [registrarSalvar, sujo, salvando]);

  async function criarVertical() {
    const nome = novaVertical.trim();
    if (!nome) return;
    setCriandoVertical(true);
    try {
      const nova = await onCriarVertical(nome);
      set('vertical_id', String(nova.id));
      setNovaVertical('');
    } catch (err) {
      setErro(mensagemDeErro(err, 'Não foi possível criar a vertical.'));
    } finally {
      setCriandoVertical(false);
    }
  }

  const abas = [
    { key: 'oportunidades', label: 'Oportunidades', badge: conta.oportunidades?.length || undefined },
    { key: 'contatos', label: 'Contatos', badge: conta.contatos?.length || undefined },
    { key: 'endereco', label: 'Endereço' },
    { key: 'telefones', label: 'Telefones e e-mail' },
    { key: 'observacoes', label: 'Observações' },
    { key: 'historico', label: 'Histórico' },
  ];

  const ICONE_ABA = {
    oportunidades: Briefcase, contatos: Users, endereco: MapPin,
    telefones: Phone, observacoes: FileText, historico: History,
  };

  return (
    <div className="flex flex-col h-full min-h-0">
      {/* ── Bloco fixo: identificação (não rola) ── */}
      <div className="shrink-0 px-5 pt-4 pb-4 border-b border-hipo-border bg-hipo-bg/40">
        {erro && <div className="mb-3"><AlertMessage tipo="erro">{erro}</AlertMessage></div>}

        <div className="grid grid-cols-1 md:grid-cols-12 gap-3">
          <Campo className="md:col-span-5">
            <Input
              label="Razão social"
              value={form.razao_social || ''}
              onChange={(e) => set('razao_social', e.target.value)}
            />
          </Campo>
          <Campo className="md:col-span-3">
            <Input
              label="CNPJ"
              value={conta.cnpj_formatado}
              disabled
              hint="Não editável"
            />
          </Campo>
          <Campo className="md:col-span-4">
            <Input
              label="Nome fantasia"
              value={form.nome_fantasia || ''}
              onChange={(e) => set('nome_fantasia', e.target.value)}
            />
          </Campo>

          <Campo className="md:col-span-4">
            <div className="flex gap-2 items-end">
              <Select
                label="Vertical"
                className="flex-1"
                value={form.vertical_id ?? ''}
                onChange={(e) => set('vertical_id', e.target.value)}
              >
                <option value="">— sem vertical —</option>
                {verticais.map((v) => (
                  <option key={v.id} value={v.id}>{v.nome}</option>
                ))}
              </Select>
              <Input
                label="Criar"
                placeholder="nova vertical"
                className="flex-1"
                value={novaVertical}
                onChange={(e) => setNovaVertical(e.target.value)}
              />
              <Button
                variant="secondary"
                icon={Plus}
                loading={criandoVertical}
                disabled={!novaVertical.trim()}
                onClick={criarVertical}
                aria-label="Adicionar vertical"
              />
            </div>
          </Campo>

          <Campo className="md:col-span-2">
            <Input
              label="Nº funcionários"
              type="number"
              min="0"
              value={form.num_funcionarios ?? ''}
              onChange={(e) => set('num_funcionarios', e.target.value)}
            />
          </Campo>

          <Campo className="md:col-span-3">
            <label className="block text-sm font-medium text-hipo-ink mb-1.5">Vendedor</label>
            <div className="h-10 px-3 flex items-center gap-2 rounded-lg border border-hipo-border bg-hipo-bg text-sm">
              <UserCircle size={15} className="text-hipo-muted shrink-0" />
              <span className="truncate text-hipo-slate">
                {conta.vendedores?.length ? conta.vendedores.join(', ') : 'sem oportunidade ativa'}
              </span>
            </div>
          </Campo>

          <Campo className="md:col-span-3">
            <label className="block text-sm font-medium text-hipo-ink mb-1.5">Situação</label>
            <div className="h-10 flex items-center gap-4">
              <label className="flex items-center gap-2 text-sm text-hipo-ink">
                <input
                  type="checkbox"
                  checked={Boolean(form.ativo)}
                  onChange={(e) => set('ativo', e.target.checked)}
                  className="rounded border-hipo-border"
                />
                Ativa
              </label>
              <label className="flex items-center gap-2 text-sm text-hipo-ink">
                <input
                  type="checkbox"
                  checked={Boolean(form.eh_finder)}
                  onChange={(e) => set('eh_finder', e.target.checked)}
                  className="rounded border-hipo-border"
                />
                Finder
              </label>
            </div>
          </Campo>
        </div>
      </div>

      {/* ── Abas ── */}
      <Tabs
        items={abas}
        value={aba}
        onChange={setAba}
        className="shrink-0 px-5 bg-hipo-bg/40"
      />

      {/* Só esta área rola. A altura do modal é fixa, então trocar de aba
          não muda o tamanho da janela — o conteúdo curto deixa espaço vazio
          e o longo ganha barra de rolagem própria. */}
      <div className="px-5 py-5 flex-1 min-h-0 overflow-y-auto">
        {aba === 'oportunidades' && (
          <AbaOportunidades oportunidades={conta.oportunidades} />
        )}

        {aba === 'contatos' && (
          <ContatosDaConta
            contaId={conta.id}
            contatos={conta.contatos || []}
            onMudou={onRecarregar}
          />
        )}

        {aba === 'endereco' && (
          <div className="grid grid-cols-1 md:grid-cols-6 gap-4 max-w-4xl">
            <Input
              label="CEP"
              className="md:col-span-2"
              placeholder="00000000"
              value={form.cep || ''}
              onChange={(e) => set('cep', e.target.value.replace(/\D/g, '').slice(0, 8))}
            />
            <Input
              label="Logradouro"
              className="md:col-span-4"
              value={form.logradouro || ''}
              onChange={(e) => set('logradouro', e.target.value)}
            />
            <Input
              label="Número"
              className="md:col-span-1"
              value={form.numero || ''}
              onChange={(e) => set('numero', e.target.value)}
            />
            <Input
              label="Complemento"
              className="md:col-span-2"
              value={form.complemento || ''}
              onChange={(e) => set('complemento', e.target.value)}
            />
            <Input
              label="Bairro"
              className="md:col-span-3"
              value={form.bairro || ''}
              onChange={(e) => set('bairro', e.target.value)}
            />
            <Input
              label="Cidade"
              className="md:col-span-4"
              value={form.cidade || ''}
              onChange={(e) => set('cidade', e.target.value)}
            />
            <Select
              label="UF"
              className="md:col-span-2"
              value={form.uf || ''}
              onChange={(e) => set('uf', e.target.value)}
            >
              <option value="">—</option>
              {UFS.map((uf) => <option key={uf} value={uf}>{uf}</option>)}
            </Select>
          </div>
        )}

        {aba === 'telefones' && (
          <div className="grid grid-cols-1 md:grid-cols-3 gap-4 max-w-3xl">
            <Input
              label="Telefone"
              value={form.telefone || ''}
              onChange={(e) => set('telefone', e.target.value)}
            />
            <Input
              label="Telefone 2"
              value={form.telefone_2 || ''}
              onChange={(e) => set('telefone_2', e.target.value)}
            />
            <Input
              label="E-mail"
              type="email"
              value={form.email || ''}
              onChange={(e) => set('email', e.target.value)}
            />
          </div>
        )}

        {aba === 'observacoes' && (
          <div className="max-w-3xl">
            <Textarea
              label="Observações"
              rows={10}
              placeholder="Anotações sobre esta conta…"
              value={form.observacoes}
              onChange={(e) => set('observacoes', e.target.value)}
            />
          </div>
        )}

        {aba === 'historico' && <AbaHistorico contaId={conta.id} />}
      </div>
    </div>
  );
}
