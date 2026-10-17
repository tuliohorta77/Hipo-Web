// web/src/pages/contratos/Contratos.jsx
//
// Módulo Contratos (043): o repasse que a Controller faz para a Spectre.
//
// O cliente paga a mensalidade para a Controller; ela repassa 100% no
// primeiro mês (prêmio de venda) e 30% depois; do repasse sai o imposto; o
// que sobra é o que entra. A soma dos líquidos do mês, menos os descontos,
// é a nota que a Spectre emite para a Controller.
//
// Duas abas, uma tela:
//   Mês        — dashboard e operação juntos: KPIs, a próxima ação (lançar,
//                emitir a nota, confirmar o recebimento), a lista de
//                contratos com o lançamento do mês ou a sugestão copiada do
//                mês anterior, e o fechamento (descontos e NF).
//   Contratos  — cadastro: parâmetros de cada CNPJ e o histórico.
//
// Quem vê: Franqueado, ADM e a conta da administração (cargo Financeiro). A
// API barra o resto; a nav só mostra o item para quem tem o módulo.

import { useCallback, useEffect, useMemo, useState } from 'react';
import {
  ChevronLeft, ChevronRight, FileText, Receipt,
  Plus, Trash2, Search, Briefcase, CheckCircle2,
} from 'lucide-react';
import api from '../../api';
import Card from '../../components/ui/Card';
import Button from '../../components/ui/Button';
import Badge from '../../components/ui/Badge';
import Modal from '../../components/ui/Modal';
import AlertMessage from '../../components/ui/AlertMessage';
import Empty from '../../components/ui/Empty';
import {
  calcularRepasse, dataBr, numero, pct, reais, rotuloCompetencia,
} from '../../components/contratos/repasseCalculo';

function erroDaApi(e, padrao = 'Não foi possível concluir.') {
  const d = e?.response?.data?.detail;
  if (typeof d === 'string') return d;
  if (Array.isArray(d) && d[0]?.msg) return d[0].msg;
  return padrao;
}

function competenciaAtual() {
  const h = new Date();
  return `${h.getFullYear()}-${String(h.getMonth() + 1).padStart(2, '0')}`;
}

const CAMPO =
  'w-full h-10 px-3 rounded-lg bg-hipo-card border border-hipo-border text-sm ' +
  'text-hipo-ink outline-none focus:border-hipo-blue focus:ring-2 focus:ring-blue-100';

function Campo({ label, children, hint }) {
  return (
    <label className="block">
      <span className="block text-sm font-medium text-hipo-ink mb-1.5">{label}</span>
      {children}
      {hint && <span className="block text-xs text-hipo-slate mt-1">{hint}</span>}
    </label>
  );
}

// ── Modal de lançamento ──────────────────────────────────────────────

function ModalLancamento({ linha, competencia, onFechar, onGravado }) {
  const { contrato, lancamento, sugestao } = linha;
  const base = lancamento || sugestao || {};
  const [porVida, setPorVida] = useState(base.valor_por_vida !== null && base.valor_por_vida !== undefined);
  const [vidas, setVidas] = useState(String(base.vidas ?? 0));
  const [valorPorVida, setValorPorVida] = useState(base.valor_por_vida != null ? String(base.valor_por_vida) : '');
  const [valorFixo, setValorFixo] = useState(
    base.valor_por_vida == null && base.valor_contrato != null ? String(base.valor_contrato)
      : (base.valor_fixo != null ? String(base.valor_fixo) : ''),
  );
  const [percentual, setPercentual] = useState(String(base.percentual_repasse ?? contrato.percentual_repasse));
  const [imposto, setImposto] = useState(String(base.imposto_percentual ?? contrato.imposto_percentual));
  const [pago, setPago] = useState(Boolean(lancamento?.pago));
  const [observacoes, setObservacoes] = useState(lancamento?.observacoes || '');
  const [salvando, setSalvando] = useState(false);
  const [erro, setErro] = useState(null);

  const previa = calcularRepasse({
    vidas,
    valorPorVida: porVida ? valorPorVida : null,
    valorFixo: porVida ? null : valorFixo,
    percentual,
    imposto,
  });

  // Lançamento NOVO: o percentual só vai para a API quando a pessoa mudou o
  // da sugestão -- assim o servidor decide o primeiro mês sozinho. Lançamento
  // que já existe manda sempre o que está gravado, para não perder ajuste.
  const percentualDaRegra = String(base.percentual_repasse ?? '');

  async function gravar() {
    setSalvando(true);
    setErro(null);
    try {
      const corpo = {
        vidas: Number.parseInt(vidas || '0', 10),
        valor_por_vida: porVida ? numero(valorPorVida) : null,
        valor_fixo: porVida ? null : numero(valorFixo),
        percentual_repasse:
          lancamento || percentual !== percentualDaRegra ? numero(percentual) : null,
        imposto_percentual: numero(imposto),
        pago,
        observacoes: observacoes.trim() || null,
      };
      await api.put(`/repasses/contratos/${contrato.id}/lancamentos/${competencia}`, corpo);
      onGravado();
    } catch (e) {
      setErro(erroDaApi(e));
    } finally {
      setSalvando(false);
    }
  }

  async function apagar() {
    setSalvando(true);
    setErro(null);
    try {
      await api.delete(`/repasses/contratos/${contrato.id}/lancamentos/${competencia}`);
      onGravado();
    } catch (e) {
      setErro(erroDaApi(e));
      setSalvando(false);
    }
  }

  return (
    <Modal
      aberto
      onFechar={onFechar}
      titulo={`${contrato.razao_social} · ${rotuloCompetencia(competencia)}`}
      subtitulo={contrato.cnpj_formatado || 'CNPJ pendente'}
      size="lg"
      footer={(
        <div className="flex items-center justify-between gap-2 w-full">
          <div>
            {lancamento && (
              <Button variant="ghost" icon={Trash2} onClick={apagar} disabled={salvando}>
                Apagar lançamento
              </Button>
            )}
          </div>
          <div className="flex gap-2">
            <Button variant="secondary" onClick={onFechar}>Cancelar</Button>
            <Button onClick={gravar} loading={salvando} data-testid="gravar-lancamento">
              Gravar
            </Button>
          </div>
        </div>
      )}
    >
      <div className="space-y-4">
        {base.primeiro_mes && (
          <AlertMessage tipo="info">
            Primeiro mês do contrato: repasse de {pct(contrato.percentual_primeiro_mes)} (prêmio de venda).
          </AlertMessage>
        )}
        <div className="flex gap-2" role="radiogroup" aria-label="Cobrança">
          <Button
            variant={porVida ? 'primary' : 'secondary'} size="sm"
            onClick={() => setPorVida(true)} role="radio" aria-checked={porVida}
          >
            Por vida
          </Button>
          <Button
            variant={!porVida ? 'primary' : 'secondary'} size="sm"
            onClick={() => setPorVida(false)} role="radio" aria-checked={!porVida}
          >
            Valor de tabela / fixo
          </Button>
        </div>
        <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
          <Campo label="Vidas cobradas">
            <input aria-label="Vidas cobradas" className={CAMPO} inputMode="numeric"
              value={vidas} onChange={(e) => setVidas(e.target.value.replace(/\D/g, ''))} />
          </Campo>
          {porVida ? (
            <Campo label="Valor por vida (R$)">
              <input aria-label="Valor por vida" className={CAMPO} inputMode="decimal"
                value={valorPorVida} onChange={(e) => setValorPorVida(e.target.value)} />
            </Campo>
          ) : (
            <Campo label="Valor do mês (R$)">
              <input aria-label="Valor do mês" className={CAMPO} inputMode="decimal"
                value={valorFixo} onChange={(e) => setValorFixo(e.target.value)} />
            </Campo>
          )}
          <Campo label="Repasse (%)" hint="100% no 1º mês, 30% depois">
            <input aria-label="Percentual de repasse" className={CAMPO} inputMode="decimal"
              value={percentual} onChange={(e) => setPercentual(e.target.value)} />
          </Campo>
          <Campo label="Imposto (%)">
            <input aria-label="Imposto" className={CAMPO} inputMode="decimal"
              value={imposto} onChange={(e) => setImposto(e.target.value)} />
          </Campo>
          <label className="flex items-center gap-2 mt-7 text-sm text-hipo-ink">
            <input type="checkbox" checked={pago} onChange={(e) => setPago(e.target.checked)} />
            Cliente pagou
          </label>
        </div>
        <Campo label="Observações">
          <textarea aria-label="Observações" rows={2} className={`${CAMPO} h-auto py-2`}
            value={observacoes} onChange={(e) => setObservacoes(e.target.value)} />
        </Campo>
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-2 rounded-lg bg-hipo-bg p-3" data-testid="previa">
          <Previa rotulo="Mensalidade do cliente" valor={previa?.valorContrato} />
          <Previa rotulo="Repasse à Spectre" valor={previa?.valorRepasse} />
          <Previa rotulo="Imposto" valor={previa?.valorImposto} />
          <Previa rotulo="Líquido Spectre" valor={previa?.valorLiquido} destaque />
        </div>
        {erro && <AlertMessage tipo="erro">{erro}</AlertMessage>}
      </div>
    </Modal>
  );
}

function Previa({ rotulo, valor, destaque }) {
  return (
    <div>
      <p className="text-xs text-hipo-slate">{rotulo}</p>
      <p className={`text-sm font-semibold ${destaque ? 'text-hipo-success' : 'text-hipo-ink'}`}>
        {valor === undefined ? '—' : reais(valor)}
      </p>
    </div>
  );
}

// ── Fechamento: descontos e nota ─────────────────────────────────────

function Fechamento({ painel, onMudou }) {
  const f = painel.fechamento;
  const [nf, setNf] = useState(f.nf_numero || '');
  const [emitida, setEmitida] = useState(f.nf_emitida_em || '');
  const [recebido, setRecebido] = useState(f.recebido_em || '');
  const [descricao, setDescricao] = useState('');
  const [valor, setValor] = useState('');
  const [erro, setErro] = useState(null);
  const [salvando, setSalvando] = useState(false);

  useEffect(() => {
    setNf(f.nf_numero || '');
    setEmitida(f.nf_emitida_em || '');
    setRecebido(f.recebido_em || '');
  }, [f.nf_numero, f.nf_emitida_em, f.recebido_em]);

  async function gravarNota() {
    setSalvando(true);
    setErro(null);
    try {
      await api.put(`/repasses/competencias/${painel.competencia}`, {
        nf_numero: nf.trim() || null,
        nf_emitida_em: emitida || null,
        recebido_em: recebido || null,
        observacoes: f.observacoes || null,
      });
      onMudou();
    } catch (e) {
      setErro(erroDaApi(e));
    } finally {
      setSalvando(false);
    }
  }

  async function adicionarDesconto() {
    setErro(null);
    try {
      await api.post(`/repasses/competencias/${painel.competencia}/descontos`, {
        descricao: descricao.trim(), valor: numero(valor),
      });
      setDescricao('');
      setValor('');
      onMudou();
    } catch (e) {
      setErro(erroDaApi(e));
    }
  }

  async function apagarDesconto(id) {
    setErro(null);
    try {
      await api.delete(`/repasses/descontos/${id}`);
      onMudou();
    } catch (e) {
      setErro(erroDaApi(e));
    }
  }

  const t = painel.totais;
  const mini =
    'w-full h-8 px-2 rounded-md bg-hipo-card border border-hipo-border text-xs ' +
    'text-hipo-ink outline-none focus:border-hipo-blue focus:ring-2 focus:ring-blue-100';
  const rotulo = 'block text-[11px] text-hipo-slate mb-0.5';
  return (
    <Card padding="sm">
      <div className="flex items-start justify-between gap-2">
        <div className="min-w-0">
          <p className="text-sm font-semibold text-hipo-ink">Nota para a Controller</p>
          <p className="text-[11px] text-hipo-slate">
            Líquido {reais(t.valor_liquido)} − descontos {reais(t.descontos)}
          </p>
        </div>
        <span className="text-base font-bold text-hipo-success whitespace-nowrap" data-testid="valor-nf">
          {reais(t.valor_nf)}
        </span>
      </div>
      <div className="space-y-1 mt-2">
        {painel.descontos.map((d) => (
          <div key={d.id} className="flex items-center justify-between text-xs border-b border-hipo-border pb-1">
            <span className="text-hipo-ink truncate">{d.descricao}</span>
            <span className="flex items-center gap-1.5 shrink-0">
              <span className="text-hipo-danger">− {reais(d.valor)}</span>
              <button type="button" aria-label={`Apagar desconto ${d.descricao}`}
                className="text-hipo-muted hover:text-hipo-danger" onClick={() => apagarDesconto(d.id)}>
                <Trash2 size={12} />
              </button>
            </span>
          </div>
        ))}
        <div className="flex gap-1.5">
          <input aria-label="Descrição do desconto" placeholder="Desconto (ex.: pg. indevido)"
            className={mini} value={descricao} onChange={(e) => setDescricao(e.target.value)} />
          <input aria-label="Valor do desconto" placeholder="R$" inputMode="decimal"
            className={`${mini} !w-20`} value={valor} onChange={(e) => setValor(e.target.value)} />
          <Button variant="secondary" size="sm" className="!h-8 !px-2 !text-xs" icon={Plus}
            onClick={adicionarDesconto} disabled={!descricao.trim() || !numero(valor)}>
            Desconto
          </Button>
        </div>
      </div>
      <div className="grid grid-cols-2 gap-1.5 mt-2">
        <label className="col-span-2">
          <span className={rotulo}>Nº da NF</span>
          <input aria-label="Número da NF" className={mini} value={nf} onChange={(e) => setNf(e.target.value)} />
        </label>
        <label>
          <span className={rotulo}>Emitida em</span>
          <input aria-label="NF emitida em" type="date" className={mini} value={emitida}
            onChange={(e) => setEmitida(e.target.value)} />
        </label>
        <label>
          <span className={rotulo}>Recebida em</span>
          <input aria-label="Recebida em" type="date" className={mini} value={recebido}
            onChange={(e) => setRecebido(e.target.value)} />
        </label>
      </div>
      <Button onClick={gravarNota} loading={salvando} icon={FileText} size="sm"
        className="!h-8 w-full mt-2 !text-xs">
        Gravar nota
      </Button>
      {erro && <AlertMessage tipo="erro" className="mt-2">{erro}</AlertMessage>}
    </Card>
  );
}

// Total da coluna, embaixo do nome dela no cabeçalho (soma dos lançados).
function Soma({ children, destaque }) {
  return (
    <span className={
      'block text-xs font-semibold whitespace-nowrap ' +
      (destaque ? 'text-hipo-success' : 'text-hipo-ink')
    }>
      {children}
    </span>
  );
}

// ── Aba Mês ──────────────────────────────────────────────────────────

function Historico({ meses, atual }) {
  const max = Math.max(1, ...meses.map((m) => numero(m.valor_nf) || 0));
  return (
    <div className="flex items-end gap-1.5 h-16" aria-label="Nota dos últimos meses">
      {meses.map((m) => {
        const v = Math.max(0, numero(m.valor_nf) || 0);
        return (
          <div key={m.competencia} className="flex-1 flex flex-col items-center gap-1" title={`${m.rotulo}: ${reais(v)}`}>
            <div
              className={`w-full rounded-t ${m.competencia === atual ? 'bg-hipo-blue' : 'bg-hipo-blueSoft'}`}
              style={{ height: `${Math.max(2, (v / max) * 44)}px` }}
            />
            <span className="text-[10px] text-hipo-slate">{m.rotulo.split('/')[0]}</span>
          </div>
        );
      })}
    </div>
  );
}

function AbaMes({ abas }) {
  const [competencia, setCompetencia] = useState(competenciaAtual());
  const [painel, setPainel] = useState(null);
  const [erro, setErro] = useState(null);
  const [editando, setEditando] = useState(null);
  const [lancandoLote, setLancandoLote] = useState(false);
  const [filtro, setFiltro] = useState('todos');

  const carregar = useCallback(async () => {
    setErro(null);
    try {
      const { data } = await api.get('/repasses/painel', { params: { competencia } });
      setPainel(data);
    } catch (e) {
      setErro(erroDaApi(e, 'Não foi possível carregar o mês.'));
    }
  }, [competencia]);

  useEffect(() => { carregar(); }, [carregar]);

  async function lancarSugestoes() {
    setLancandoLote(true);
    setErro(null);
    try {
      await api.post(`/repasses/competencias/${competencia}/lancar-sugestoes`, {});
      await carregar();
    } catch (e) {
      setErro(erroDaApi(e));
    } finally {
      setLancandoLote(false);
    }
  }

  const linhas = useMemo(() => {
    if (!painel) return [];
    if (filtro === 'pendentes') return painel.linhas.filter((l) => !l.lancamento);
    if (filtro === 'nao_pagos') return painel.linhas.filter((l) => l.lancamento && !l.lancamento.pago);
    return painel.linhas;
  }, [painel, filtro]);

  if (erro && !painel) return <div className="space-y-2">{abas}<AlertMessage tipo="erro">{erro}</AlertMessage></div>;
  if (!painel) return <div className="space-y-2">{abas}<p className="text-sm text-hipo-slate">Carregando…</p></div>;

  const passo = painel.proximo_passo;
  // Somas do cabeçalho: o que está na lista, lançado OU sugerido -- o mês
  // previsto. A nota (lateral) segue contando só o que já foi lançado.
  const soma = (campo) => linhas.reduce((acc, l) => acc + (numero((l.lancamento || l.sugestao)?.[campo]) || 0), 0);
  const t = {
    vidas: soma('vidas'),
    valor_contrato: soma('valor_contrato'),
    valor_repasse: soma('valor_repasse'),
    valor_imposto: soma('valor_imposto'),
    valor_liquido: soma('valor_liquido'),
  };

  // Tudo que não é a lista cabe numa faixa de ~40px: mês, quatro KPIs de
  // barra e a próxima ação. A lista ganha o resto da altura e rola sozinha,
  // com o cabeçalho preso -- a tela inteira cabe num notebook sem rolar.
  return (
    <div className="h-full min-h-0 flex flex-col gap-2">
      <div className="flex flex-wrap items-center gap-2 shrink-0">
        {abas}
        <div className="flex items-center">
          <Button variant="ghost" size="sm" aria-label="Mês anterior" className="!h-8 !px-2"
            onClick={() => setCompetencia(painel.anterior)}>
            <ChevronLeft size={16} />
          </Button>
          <span className="text-sm font-semibold text-hipo-ink w-20 text-center" data-testid="competencia">
            {painel.rotulo}
          </span>
          <Button variant="ghost" size="sm" aria-label="Mês seguinte" className="!h-8 !px-2"
            onClick={() => setCompetencia(painel.seguinte)}>
            <ChevronRight size={16} />
          </Button>
        </div>
        <div className="flex items-center gap-1.5">
          {[
            ['todos', `Todos (${painel.linhas.length})`],
            ['pendentes', `Pendentes (${painel.pendentes})`],
            ['nao_pagos', 'Cliente não pagou'],
          ].map(([chave, rotulo]) => (
            <button key={chave} type="button" onClick={() => setFiltro(chave)}
              className={
                'px-2.5 h-7 rounded-full text-xs font-medium border ' +
                (filtro === chave
                  ? 'bg-hipo-blue text-white border-hipo-blue'
                  : 'bg-hipo-card text-hipo-slate border-hipo-border hover:text-hipo-ink')
              }>
              {rotulo}
            </button>
          ))}
        </div>
        <div className="flex-1" />
        <div
          className={
            'h-9 flex items-center gap-2 pl-3 pr-1 rounded-lg border text-xs ' +
            (passo.acao === 'fechado'
              ? 'bg-hipo-successSoft border-hipo-successBorder text-hipo-success'
              : 'bg-hipo-blueSoft border-hipo-blueSoft text-hipo-blueDark')
          }
          data-testid="proximo-passo"
        >
          {passo.acao === 'fechado' ? <CheckCircle2 size={14} /> : <Receipt size={14} />}
          <span>{passo.texto}</span>
          {passo.acao === 'lancar' && (
            <Button size="sm" className="!h-7" onClick={lancarSugestoes} loading={lancandoLote}>
              Confirmar sugestões ({painel.pendentes})
            </Button>
          )}
        </div>
      </div>

      {erro && <AlertMessage tipo="erro">{erro}</AlertMessage>}

      <div className="flex-1 min-h-0 grid grid-cols-1 xl:grid-cols-[minmax(0,1fr)_300px] gap-3">
        <Card padding="none" className="!p-0 min-h-0 flex flex-col overflow-hidden">
          {linhas.length === 0 ? (
            <Empty title="Nada por aqui" description="Nenhum contrato neste recorte do mês." />
          ) : (
            <div className="flex-1 min-h-0 overflow-auto">
              <table className="w-full text-[13px]">
                <thead className="sticky top-0 bg-hipo-card z-10">
                  <tr className="text-left text-[11px] text-hipo-slate border-b border-hipo-border align-bottom">
                    <th className="px-3 py-1.5 font-medium">
                      Contrato
                      <Soma>{linhas.length} contratos · {painel.lancados} lançados</Soma>
                    </th>
                    <th className="px-2 py-1.5 font-medium text-right">
                      Vidas<Soma>{t.vidas}</Soma>
                    </th>
                    <th className="px-2 py-1.5 font-medium text-right" title="O que o cliente paga à Controller">
                      Mensalidade<Soma>{reais(t.valor_contrato)}</Soma>
                    </th>
                    <th className="px-2 py-1.5 font-medium text-right" title="100% no primeiro mês, 30% depois">
                      % repasse<Soma>&nbsp;</Soma>
                    </th>
                    <th className="px-2 py-1.5 font-medium text-right" title="Mensalidade × % repasse">
                      Repasse<Soma>{reais(t.valor_repasse)}</Soma>
                    </th>
                    <th className="px-2 py-1.5 font-medium text-right">
                      Imposto<Soma>{reais(t.valor_imposto)}</Soma>
                    </th>
                    <th className="px-2 py-1.5 font-medium text-right" title="Repasse − imposto: o que entra na Spectre">
                      Líquido Spectre<Soma destaque>{reais(t.valor_liquido)}</Soma>
                    </th>
                    <th className="px-3 py-1.5 font-medium text-right text-[10px] text-hipo-muted font-normal">
                      somas com sugestões · itálico = não lançado
                    </th>
                  </tr>
                </thead>
                <tbody>
                  {linhas.map((linha) => {
                    const { contrato: c, lancamento: l, sugestao: s } = linha;
                    const v = l || s;
                    const tom = l ? 'text-hipo-ink' : 'text-hipo-muted italic';
                    return (
                      <tr key={c.id} className="border-b border-hipo-border hover:bg-hipo-bg"
                        data-testid={`linha-${c.id}`}>
                        <td className="px-3 py-1 max-w-[280px]">
                          <p className="font-medium text-hipo-ink truncate leading-tight" title={c.razao_social}>{c.razao_social}</p>
                          <p className="text-[11px] text-hipo-slate truncate leading-tight">
                            {c.cnpj_formatado || 'CNPJ pendente'}
                            {c.oportunidade_numero ? ` · ${c.oportunidade_numero}` : ''}
                            {c.grupo ? ` · ${c.grupo}` : ''}
                          </p>
                        </td>
                        <td className={`px-2 py-1 text-right ${tom}`}>{v?.vidas ?? '—'}</td>
                        <td className={`px-2 py-1 text-right whitespace-nowrap ${tom}`}>{reais(v?.valor_contrato)}</td>
                        <td className={`px-2 py-1 text-right whitespace-nowrap ${tom}`}>
                          {v?.primeiro_mes && (
                            <span className="mr-1 px-1.5 py-0.5 rounded-full bg-hipo-blueSoft text-hipo-blue text-[10px] font-medium not-italic">
                              1º mês
                            </span>
                          )}
                          {pct(v?.percentual_repasse)}
                        </td>
                        <td className={`px-2 py-1 text-right whitespace-nowrap ${tom}`}>{reais(v?.valor_repasse)}</td>
                        <td className={`px-2 py-1 text-right whitespace-nowrap ${tom}`}>{reais(v?.valor_imposto)}</td>
                        <td className={`px-2 py-1 text-right whitespace-nowrap font-semibold ${l ? 'text-hipo-success' : 'text-hipo-muted italic'}`}>
                          {reais(v?.valor_liquido)}
                        </td>
                        <td className="px-3 py-1 text-right whitespace-nowrap">
                          {l && (
                            <span className={
                              'mr-1.5 px-1.5 py-0.5 rounded-full text-[10px] font-medium ' +
                              (l.pago ? 'bg-hipo-successSoft text-hipo-success' : 'bg-hipo-warningSoft text-hipo-warning')
                            }>
                              {l.pago ? 'pago' : 'não pago'}
                            </span>
                          )}
                          <Button size="sm" variant={l ? 'secondary' : 'primary'} className="!h-7 !px-2.5 !text-xs"
                            onClick={() => setEditando(linha)}>
                            {l ? 'Editar' : 'Lançar'}
                          </Button>
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          )}
        </Card>

        <div className="min-h-0 overflow-y-auto space-y-3">
          <Fechamento painel={painel} onMudou={carregar} />
          <Card padding="sm">
            <p className="text-xs font-semibold text-hipo-ink mb-2">Nota dos últimos meses</p>
            <Historico meses={painel.historico} atual={painel.competencia} />
          </Card>
        </div>
      </div>

      {editando && (
        <ModalLancamento
          linha={editando}
          competencia={painel.competencia}
          onFechar={() => setEditando(null)}
          onGravado={() => { setEditando(null); carregar(); }}
        />
      )}
    </div>
  );
}

// ── Aba Contratos ────────────────────────────────────────────────────

const CONTRATO_VAZIO = {
  razao_social: '', cnpj: '', data_venda: '', modalidade: 'por_vida', vidas: '',
  valor_por_vida: '', valor_fixo: '', percentual_repasse: '30',
  percentual_primeiro_mes: '100', imposto_percentual: '14.33',
  primeira_competencia: '', grupo: '', observacoes: '', status: 'ativo', encerrado_em: '',
};

function paraFormulario(c) {
  const s = (v) => (v === null || v === undefined ? '' : String(v));
  return {
    razao_social: s(c.razao_social), cnpj: s(c.cnpj_formatado || c.cnpj),
    data_venda: s(c.data_venda), modalidade: c.modalidade, vidas: s(c.vidas),
    valor_por_vida: s(c.valor_por_vida), valor_fixo: s(c.valor_fixo),
    percentual_repasse: s(c.percentual_repasse),
    percentual_primeiro_mes: s(c.percentual_primeiro_mes),
    imposto_percentual: s(c.imposto_percentual),
    primeira_competencia: s(c.primeira_competencia), grupo: s(c.grupo),
    observacoes: s(c.observacoes), status: c.status, encerrado_em: s(c.encerrado_em),
  };
}

function paraApi(f, novo) {
  const corpo = {
    razao_social: f.razao_social.trim(),
    cnpj: f.cnpj.trim() || null,
    data_venda: f.data_venda || null,
    modalidade: f.modalidade,
    vidas: f.vidas === '' ? null : Number.parseInt(f.vidas, 10),
    valor_por_vida: f.modalidade === 'por_vida' ? numero(f.valor_por_vida) : null,
    valor_fixo: f.modalidade === 'valor_fixo' ? numero(f.valor_fixo) : null,
    percentual_repasse: numero(f.percentual_repasse),
    percentual_primeiro_mes: numero(f.percentual_primeiro_mes),
    imposto_percentual: numero(f.imposto_percentual),
    primeira_competencia: f.primeira_competencia || null,
    grupo: f.grupo.trim() || null,
    observacoes: f.observacoes.trim() || null,
  };
  if (!novo) {
    corpo.status = f.status;
    corpo.encerrado_em = f.status === 'encerrado' ? (f.encerrado_em || null) : null;
  }
  return corpo;
}

function FormularioContrato({ form, setForm, novo }) {
  const set = (k) => (e) => setForm((f) => ({ ...f, [k]: e.target.value }));
  return (
    <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
      <Campo label="Razão social">
        <input aria-label="Razão social" className={CAMPO} value={form.razao_social} onChange={set('razao_social')} />
      </Campo>
      <Campo label="CNPJ" hint="Pode ficar em branco até ser identificado.">
        <input aria-label="CNPJ" className={CAMPO} value={form.cnpj} onChange={set('cnpj')} />
      </Campo>
      <Campo label="Data da venda">
        <input aria-label="Data da venda" type="date" className={CAMPO} value={form.data_venda} onChange={set('data_venda')} />
      </Campo>
      <Campo label="Grupo / observação curta">
        <input aria-label="Grupo" className={CAMPO} value={form.grupo} onChange={set('grupo')} />
      </Campo>
      <Campo label="Cobrança">
        <select aria-label="Cobrança" className={CAMPO} value={form.modalidade} onChange={set('modalidade')}>
          <option value="por_vida">Por vida</option>
          <option value="valor_fixo">Valor de tabela / fixo</option>
        </select>
      </Campo>
      <div className="grid grid-cols-2 gap-3">
        <Campo label="Vidas">
          <input aria-label="Vidas do contrato" className={CAMPO} inputMode="numeric" value={form.vidas} onChange={set('vidas')} />
        </Campo>
        {form.modalidade === 'por_vida' ? (
          <Campo label="Valor por vida">
            <input aria-label="Valor por vida do contrato" className={CAMPO} inputMode="decimal"
              value={form.valor_por_vida} onChange={set('valor_por_vida')} />
          </Campo>
        ) : (
          <Campo label="Valor fixo">
            <input aria-label="Valor fixo do contrato" className={CAMPO} inputMode="decimal"
              value={form.valor_fixo} onChange={set('valor_fixo')} />
          </Campo>
        )}
      </div>
      <div className="grid grid-cols-3 gap-3 sm:col-span-2">
        <Campo label="Repasse (%)">
          <input aria-label="Repasse recorrente" className={CAMPO} value={form.percentual_repasse} onChange={set('percentual_repasse')} />
        </Campo>
        <Campo label="1º mês (%)">
          <input aria-label="Repasse do primeiro mês" className={CAMPO} value={form.percentual_primeiro_mes} onChange={set('percentual_primeiro_mes')} />
        </Campo>
        <Campo label="Imposto (%)">
          <input aria-label="Imposto do contrato" className={CAMPO} value={form.imposto_percentual} onChange={set('imposto_percentual')} />
        </Campo>
      </div>
      <Campo label="Mês do prêmio (1º mês)" hint="Em branco: o primeiro lançamento define.">
        <input aria-label="Primeira competência" type="month" className={CAMPO}
          value={form.primeira_competencia} onChange={set('primeira_competencia')} />
      </Campo>
      {!novo && (
        <div className="grid grid-cols-2 gap-3">
          <Campo label="Situação">
            <select aria-label="Situação" className={CAMPO} value={form.status} onChange={set('status')}>
              <option value="ativo">Ativo</option>
              <option value="encerrado">Encerrado</option>
            </select>
          </Campo>
          {form.status === 'encerrado' && (
            <Campo label="Encerrado em">
              <input aria-label="Encerrado em" type="date" className={CAMPO}
                value={form.encerrado_em} onChange={set('encerrado_em')} />
            </Campo>
          )}
        </div>
      )}
      <div className="sm:col-span-2">
        <Campo label="Observações">
          <textarea aria-label="Observações do contrato" rows={2} className={`${CAMPO} h-auto py-2`}
            value={form.observacoes} onChange={set('observacoes')} />
        </Campo>
      </div>
    </div>
  );
}

function ModalContrato({ contratoId, onFechar, onMudou }) {
  const novo = !contratoId;
  const [form, setForm] = useState(CONTRATO_VAZIO);
  const [detalhe, setDetalhe] = useState(null);
  const [erro, setErro] = useState(null);
  const [salvando, setSalvando] = useState(false);

  useEffect(() => {
    if (novo) return;
    api.get(`/repasses/contratos/${contratoId}`)
      .then(({ data }) => { setDetalhe(data); setForm(paraFormulario(data)); })
      .catch((e) => setErro(erroDaApi(e, 'Não foi possível abrir o contrato.')));
  }, [contratoId, novo]);

  async function gravar() {
    setSalvando(true);
    setErro(null);
    try {
      if (novo) await api.post('/repasses/contratos', paraApi(form, true));
      else await api.patch(`/repasses/contratos/${contratoId}`, paraApi(form, false));
      onMudou();
    } catch (e) {
      setErro(erroDaApi(e));
    } finally {
      setSalvando(false);
    }
  }

  return (
    <Modal
      aberto
      onFechar={onFechar}
      titulo={novo ? 'Novo contrato' : (detalhe?.razao_social || 'Contrato')}
      subtitulo={detalhe?.oportunidade_numero ? `Oportunidade ${detalhe.oportunidade_numero}` : undefined}
      size="xl"
      footer={(
        <div className="flex justify-end gap-2 w-full">
          <Button variant="secondary" onClick={onFechar}>Fechar</Button>
          <Button onClick={gravar} loading={salvando} data-testid="gravar-contrato">Gravar</Button>
        </div>
      )}
    >
      <div className="space-y-5">
        <FormularioContrato form={form} setForm={setForm} novo={novo} />
        {erro && <AlertMessage tipo="erro">{erro}</AlertMessage>}
        {detalhe && (
          <div>
            <h3 className="text-h2 text-hipo-ink mb-2">Lançamentos</h3>
            {detalhe.lancamentos.length === 0 ? (
              <p className="text-sm text-hipo-slate">Nenhum lançamento ainda.</p>
            ) : (
              <table className="w-full text-sm">
                <thead>
                  <tr className="text-left text-xs text-hipo-slate border-b border-hipo-border">
                    <th className="py-1 font-medium">Mês</th>
                    <th className="py-1 font-medium text-right">Vidas</th>
                    <th className="py-1 font-medium text-right">Mensalidade</th>
                    <th className="py-1 font-medium text-right">% repasse</th>
                    <th className="py-1 font-medium text-right">Repasse</th>
                    <th className="py-1 font-medium text-right">Líquido Spectre</th>
                    <th className="py-1 font-medium text-right">Pago</th>
                  </tr>
                </thead>
                <tbody>
                  {detalhe.lancamentos.map((l) => (
                    <tr key={l.id} className="border-b border-hipo-border">
                      <td className="py-1">{rotuloCompetencia(l.competencia)}</td>
                      <td className="py-1 text-right">{l.vidas}</td>
                      <td className="py-1 text-right">{reais(l.valor_contrato)}</td>
                      <td className="py-1 text-right">{pct(l.percentual_repasse)}</td>
                      <td className="py-1 text-right">{reais(l.valor_repasse)}</td>
                      <td className="py-1 text-right font-semibold">{reais(l.valor_liquido)}</td>
                      <td className="py-1 text-right">{l.pago ? 'sim' : 'não'}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </div>
        )}
      </div>
    </Modal>
  );
}

function ModalDaOportunidade({ onFechar, onMudou }) {
  const [q, setQ] = useState('');
  const [lista, setLista] = useState(null);
  const [erro, setErro] = useState(null);
  const [gerando, setGerando] = useState(null);

  const buscar = useCallback(async () => {
    setErro(null);
    try {
      const { data } = await api.get('/repasses/oportunidades', { params: q.trim() ? { q: q.trim() } : {} });
      setLista(data);
    } catch (e) {
      setErro(erroDaApi(e));
    }
  }, [q]);

  useEffect(() => { buscar(); }, []); // eslint-disable-line react-hooks/exhaustive-deps

  async function gerar(id) {
    setGerando(id);
    setErro(null);
    try {
      await api.post('/repasses/contratos/da-oportunidade', { oportunidade_id: id });
      onMudou();
    } catch (e) {
      setErro(erroDaApi(e));
      setGerando(null);
    }
  }

  return (
    <Modal aberto onFechar={onFechar} titulo="Contratos a partir da oportunidade"
      subtitulo="Oportunidades conquistadas com CNPJ ainda sem contrato" size="lg">
      <div className="space-y-3">
        <div className="flex gap-2">
          <input aria-label="Buscar oportunidade" placeholder="Número ou razão social" className={CAMPO}
            value={q} onChange={(e) => setQ(e.target.value)}
            onKeyDown={(e) => { if (e.key === 'Enter') buscar(); }} />
          <Button variant="secondary" icon={Search} onClick={buscar}>Buscar</Button>
        </div>
        {erro && <AlertMessage tipo="erro">{erro}</AlertMessage>}
        {lista && lista.length === 0 && (
          <Empty title="Nada pendente" description="Toda oportunidade conquistada já tem contrato." />
        )}
        {lista?.map((o) => (
          <div key={o.id} className="border border-hipo-border rounded-lg p-3">
            <div className="flex items-start justify-between gap-3">
              <div>
                <p className="font-medium text-hipo-ink">{o.numero} · {o.razao_social}</p>
                <p className="text-xs text-hipo-slate">Conquistada em {dataBr(o.data_conquista)}</p>
              </div>
              <Button size="sm" onClick={() => gerar(o.id)} loading={gerando === o.id}>
                Gerar {o.cnpjs_sem_contrato.length} contrato{o.cnpjs_sem_contrato.length > 1 ? 's' : ''}
              </Button>
            </div>
            <ul className="mt-2 text-xs text-hipo-slate space-y-0.5">
              {o.cnpjs_sem_contrato.map((i) => (
                <li key={i.cnpj}>
                  {i.cnpj_formatado} · {i.razao_social}
                  {i.vidas != null ? ` · ${i.vidas} vidas` : ''} · {reais(i.mensalidade)}
                </li>
              ))}
            </ul>
          </div>
        ))}
      </div>
    </Modal>
  );
}

function AbaContratos({ abas }) {
  const [lista, setLista] = useState(null);
  const [q, setQ] = useState('');
  const [status, setStatus] = useState('ativo');
  const [erro, setErro] = useState(null);
  const [aberto, setAberto] = useState(null); // null | 'novo' | 'oportunidade' | id

  const carregar = useCallback(async () => {
    setErro(null);
    try {
      const params = {};
      if (status) params.status = status;
      if (q.trim()) params.q = q.trim();
      const { data } = await api.get('/repasses/contratos', { params });
      setLista(data);
    } catch (e) {
      setErro(erroDaApi(e, 'Não foi possível carregar os contratos.'));
    }
  }, [q, status]);

  useEffect(() => { carregar(); }, [status]); // eslint-disable-line react-hooks/exhaustive-deps

  function fecharEAtualizar() {
    setAberto(null);
    carregar();
  }

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center gap-2">
        {abas}
        <input aria-label="Buscar contrato" placeholder="Razão social, CNPJ, grupo ou oportunidade"
          className={`${CAMPO} max-w-sm`} value={q} onChange={(e) => setQ(e.target.value)}
          onKeyDown={(e) => { if (e.key === 'Enter') carregar(); }} />
        <select aria-label="Filtrar situação" className={`${CAMPO} w-40`} value={status}
          onChange={(e) => setStatus(e.target.value)}>
          <option value="ativo">Ativos</option>
          <option value="encerrado">Encerrados</option>
          <option value="">Todos</option>
        </select>
        <Button variant="secondary" icon={Search} onClick={carregar}>Buscar</Button>
        <div className="flex-1" />
        <Button variant="secondary" icon={Briefcase} onClick={() => setAberto('oportunidade')}>
          Da oportunidade
        </Button>
        <Button icon={Plus} onClick={() => setAberto('novo')}>Novo contrato</Button>
      </div>

      {erro && <AlertMessage tipo="erro">{erro}</AlertMessage>}

      <Card padding="none" className="!p-0 overflow-hidden">
        {!lista ? (
          <p className="p-4 text-sm text-hipo-slate">Carregando…</p>
        ) : lista.length === 0 ? (
          <Empty title="Nenhum contrato" description="Cadastre um contrato ou gere a partir de uma oportunidade conquistada." />
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="text-left text-xs text-hipo-slate border-b border-hipo-border">
                  <th className="px-4 py-2 font-medium">Contrato</th>
                  <th className="px-2 py-2 font-medium">Oportunidade</th>
                  <th className="px-2 py-2 font-medium">Venda</th>
                  <th className="px-2 py-2 font-medium">Cobrança</th>
                  <th className="px-2 py-2 font-medium text-right">Repasse</th>
                  <th className="px-2 py-2 font-medium">Último mês</th>
                  <th className="px-4 py-2 font-medium">Situação</th>
                </tr>
              </thead>
              <tbody>
                {lista.map((c) => (
                  <tr key={c.id} className="border-b border-hipo-border hover:bg-hipo-bg cursor-pointer"
                    onClick={() => setAberto(c.id)} data-testid={`contrato-${c.id}`}>
                    <td className="px-4 py-2">
                      <p className="font-medium text-hipo-ink">{c.razao_social}</p>
                      <p className="text-xs text-hipo-slate">
                        {c.cnpj_formatado || <span className="text-hipo-warning">CNPJ pendente</span>}
                        {c.grupo ? ` · ${c.grupo}` : ''}
                      </p>
                    </td>
                    <td className="px-2 py-2 text-hipo-slate">{c.oportunidade_numero || '—'}</td>
                    <td className="px-2 py-2 text-hipo-slate">{dataBr(c.data_venda)}</td>
                    <td className="px-2 py-2 text-hipo-slate">
                      {c.modalidade === 'por_vida'
                        ? `${c.vidas ?? '—'} vidas × ${reais(c.valor_por_vida)}`
                        : `${reais(c.valor_fixo)} fixo`}
                    </td>
                    <td className="px-2 py-2 text-right text-hipo-slate">
                      {pct(c.percentual_repasse)} <span className="text-xs">(1º: {pct(c.percentual_primeiro_mes)})</span>
                    </td>
                    <td className="px-2 py-2 text-hipo-slate">
                      {c.ultima_competencia
                        ? `${rotuloCompetencia(c.ultima_competencia)} · ${reais(c.ultimo_valor_liquido)}`
                        : '—'}
                    </td>
                    <td className="px-4 py-2">
                      {c.status === 'ativo'
                        ? <Badge tone="success">ativo</Badge>
                        : <Badge tone="neutral">encerrado</Badge>}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Card>

      {aberto === 'oportunidade' && (
        <ModalDaOportunidade onFechar={() => setAberto(null)} onMudou={fecharEAtualizar} />
      )}
      {aberto && aberto !== 'oportunidade' && (
        <ModalContrato
          contratoId={aberto === 'novo' ? null : aberto}
          onFechar={() => setAberto(null)}
          onMudou={fecharEAtualizar}
        />
      )}
    </div>
  );
}

// ── Página ───────────────────────────────────────────────────────────

// As abas moram na mesma linha do mês, dos filtros e da próxima ação: cada
// aba recebe o seletor e o põe no começo da própria barra.
function SeletorAba({ aba, setAba }) {
  const itens = [['mes', 'Mês'], ['contratos', 'Contratos']];
  return (
    <div role="tablist" className="flex items-center p-0.5 rounded-lg bg-hipo-bg border border-hipo-border mr-1">
      {itens.map(([chave, rotulo]) => (
        <button key={chave} type="button" role="tab" aria-selected={aba === chave}
          data-testid={`tab-${chave}`} onClick={() => setAba(chave)}
          className={
            'px-3 h-7 rounded-md text-xs font-medium transition-colors ' +
            (aba === chave ? 'bg-hipo-card text-hipo-blue shadow-sm' : 'text-hipo-slate hover:text-hipo-ink')
          }>
          {rotulo}
        </button>
      ))}
    </div>
  );
}

export default function Contratos() {
  const [aba, setAba] = useState('mes');
  const abas = <SeletorAba aba={aba} setAba={setAba} />;
  return (
    <div className="h-full min-h-0">
      {aba === 'mes'
        ? <AbaMes abas={abas} />
        : <div className="h-full overflow-y-auto"><AbaContratos abas={abas} /></div>}
    </div>
  );
}
