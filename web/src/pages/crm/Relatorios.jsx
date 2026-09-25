// web/src/pages/crm/Relatorios.jsx
//
// Relatórios: tabela dinâmica sobre a base do HIPO, no estilo do Excel, e
// relatórios salvos no perfil de cada um.
//
// ── O fluxo ──────────────────────────────────────────────────────────
// 1. PERÍODO PRIMEIRO. Antes de qualquer campo, a tela pergunta o que
//    analisar (a fonte), qual data define o período (criação, desfecho,
//    prazo, data da reunião…) e qual período. Número sem "de quando" não
//    responde pergunta nenhuma — e é o período que impede a consulta da base
//    inteira.
// 2. MONTAGEM. Filtros, Linhas, Colunas e Valores, como no Excel. A tabela
//    recalcula sozinha a cada mudança (com debounce).
// 3. AÇÃO. Todo número abre os registros que o compõem, e cada registro
//    abre a oportunidade ou a conta — diretriz 2: a mesma tela mostra o
//    panorama e leva à próxima ação.
// 4. SALVAR. Com nome, no perfil. Compartilhar deixa a equipe ver e
//    duplicar; editar é só do dono.
//
// ── O recorte ────────────────────────────────────────────────────────
// A tela não filtra nada por cargo: quem recorta é a API, a partir do JWT.
// Gestão vê a base inteira; operacional vê o que é seu. Um relatório
// compartilhado pelo Franqueado mostra, para o SDR que o abre, os números
// do SDR.

import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { useSearchParams } from 'react-router-dom';
import {
  FilePlus2, Save, Copy, Trash2, Pencil, Loader2, ListOrdered, Sigma, Users, Lock, Sparkles,
} from 'lucide-react';
import api from '../../api';
import PageHeader from '../../components/ui/PageHeader';
import Card from '../../components/ui/Card';
import Button from '../../components/ui/Button';
import Badge from '../../components/ui/Badge';
import AlertMessage from '../../components/ui/AlertMessage';
import Empty from '../../components/ui/Empty';
import Modal from '../../components/ui/Modal';
import KpiInline from '../../components/ui/KpiInline';
import { Select } from '../../components/ui/Input';
import Construtor from '../../components/relatorios/Construtor';
import TabelaDinamica from '../../components/relatorios/TabelaDinamica';
import RegistrosDaCelula from '../../components/relatorios/RegistrosDaCelula';
import SalvarRelatorio from '../../components/relatorios/SalvarRelatorio';
import ListaSalvos from '../../components/relatorios/ListaSalvos';
import { REGISTROS } from '../../components/relatorios/SeletorCampo';
import {
  PRESETS, PRESET_PADRAO, resolverPeriodo, descreverPeriodo,
} from '../../components/relatorios/periodo';
import { formatarDimensao, formatarMedida } from '../../components/relatorios/pivot';
import { mensagemDeErro } from '../../components/crm/tarefaComum';

const PERSONALIZADO = 'personalizado';
const ORDENACAO_PADRAO = { por: 'rotulo', direcao: 'asc' };

// ── Configuração ─────────────────────────────────────────────────────

export function novaConfig(fonte, periodo) {
  return {
    fonte: fonte.chave,
    periodo: { ...periodo, data_ref: periodo.data_ref || fonte.data_padrao },
    linhas: [],
    colunas: [],
    valores: [{ campo: REGISTROS, agregacao: 'contagem' }],
    filtros: [],
    ordenacao: ORDENACAO_PADRAO,
    destacar: true,
  };
}

/**
 * Configuração salva -> configuração utilizável com o catálogo ATUAL.
 * Campo que saiu do catálogo é descartado e avisado, em vez de quebrar o
 * relatório inteiro com um 422.
 */
export function normalizarConfig(cfg, fonte) {
  const existe = (k) => k === REGISTROS || fonte.campos.some((c) => c.chave === k);
  const removidos = [];
  const filtrar = (lista = []) => lista.filter((x) => {
    if (existe(x.campo)) return true;
    removidos.push(x.campo);
    return false;
  });
  const dataRefOk = fonte.campos.some((c) => c.chave === cfg.periodo?.data_ref && c.referencia);
  const config = {
    fonte: fonte.chave,
    periodo: {
      ...(cfg.periodo || { tipo: 'relativo', preset: PRESET_PADRAO }),
      data_ref: dataRefOk ? cfg.periodo.data_ref : fonte.data_padrao,
    },
    linhas: filtrar(cfg.linhas),
    colunas: filtrar(cfg.colunas),
    valores: filtrar(cfg.valores),
    filtros: filtrar(cfg.filtros),
    ordenacao: cfg.ordenacao || ORDENACAO_PADRAO,
    destacar: cfg.destacar !== false,
  };
  if (!config.valores.length) config.valores = [{ campo: REGISTROS, agregacao: 'contagem' }];
  return { config, removidos };
}

/** O corpo que a API recebe. */
export function corpoDaConsulta(config, hoje = new Date()) {
  const datas = resolverPeriodo(config.periodo, hoje);
  if (!datas || datas.inicio > datas.fim) return null;
  return {
    fonte: config.fonte,
    periodo: { data_ref: config.periodo.data_ref, inicio: datas.inicio, fim: datas.fim },
    linhas: config.linhas.map(({ campo, granularidade }) => ({ campo, granularidade: granularidade || null })),
    colunas: config.colunas.map(({ campo, granularidade }) => ({ campo, granularidade: granularidade || null })),
    valores: config.valores,
    filtros: config.filtros,
  };
}

// ── Período (fonte + data de referência + intervalo) ─────────────────

function SeletorPeriodo({ fonte, periodo, onChange, compacto = false }) {
  const datas = fonte.campos.filter((c) => c.referencia);
  const valorPreset = periodo.tipo === 'relativo' ? periodo.preset : PERSONALIZADO;
  const resolvidas = resolverPeriodo(periodo) || {};

  function trocarPreset(v) {
    if (v === PERSONALIZADO) {
      onChange({ ...periodo, tipo: 'fixo', inicio: resolvidas.inicio, fim: resolvidas.fim, preset: undefined });
    } else {
      onChange({ data_ref: periodo.data_ref, tipo: 'relativo', preset: v });
    }
  }

  return (
    <div className={`grid gap-2 ${compacto ? 'sm:grid-cols-[minmax(0,1fr)_minmax(0,1fr)_auto]' : 'sm:grid-cols-2'}`}>
      <Select
        label="Período pela data de"
        id="rel-data-ref"
        value={periodo.data_ref}
        onChange={(e) => onChange({ ...periodo, data_ref: e.target.value })}
      >
        {datas.map((c) => <option key={c.chave} value={c.chave}>{c.rotulo}</option>)}
      </Select>
      <Select
        label="Período"
        id="rel-preset"
        value={valorPreset}
        onChange={(e) => trocarPreset(e.target.value)}
      >
        {PRESETS.map((p) => <option key={p.chave} value={p.chave}>{p.rotulo}</option>)}
        <option value={PERSONALIZADO}>Personalizado…</option>
      </Select>
      {periodo.tipo === 'fixo' ? (
        <div className={`flex items-end gap-1.5 ${compacto ? '' : 'sm:col-span-2'}`}>
          <label className="text-sm flex-1">
            <span className="block font-medium text-hipo-ink mb-1.5">De</span>
            <input
              type="date"
              aria-label="Data inicial"
              value={periodo.inicio || ''}
              onChange={(e) => onChange({ ...periodo, inicio: e.target.value })}
              className="w-full h-10 px-2 rounded-lg border border-hipo-border text-sm outline-none focus:border-hipo-blue"
            />
          </label>
          <label className="text-sm flex-1">
            <span className="block font-medium text-hipo-ink mb-1.5">Até</span>
            <input
              type="date"
              aria-label="Data final"
              value={periodo.fim || ''}
              onChange={(e) => onChange({ ...periodo, fim: e.target.value })}
              className="w-full h-10 px-2 rounded-lg border border-hipo-border text-sm outline-none focus:border-hipo-blue"
            />
          </label>
        </div>
      ) : (
        compacto && (
          <p className="self-end text-xs text-hipo-slate pb-3 whitespace-nowrap">{descreverPeriodo(periodo)}</p>
        )
      )}
    </div>
  );
}

// ── Início: fonte e período antes de tudo ────────────────────────────

function Inicio({ catalogo, onComecar }) {
  const [fonteChave, setFonteChave] = useState(catalogo.fontes[0].chave);
  const fonte = catalogo.fontes.find((f) => f.chave === fonteChave);
  const [periodo, setPeriodo] = useState({ tipo: 'relativo', preset: PRESET_PADRAO, data_ref: fonte.data_padrao });
  const datas = resolverPeriodo(periodo);
  const valido = datas && datas.inicio <= datas.fim;

  function escolherFonte(f) {
    setFonteChave(f.chave);
    setPeriodo((p) => ({ ...p, data_ref: f.data_padrao }));
  }

  return (
    <Card>
      <h2 className="text-h2 text-hipo-ink mb-1">Novo relatório</h2>
      <p className="text-sm text-hipo-slate mb-4">
        Escolha o que analisar e o período. Depois, monte a tabela arrastando os campos.
      </p>

      <h3 className="text-xs font-semibold uppercase tracking-wide text-hipo-muted mb-2">1. O que você quer analisar?</h3>
      <div className="grid gap-2 sm:grid-cols-2 xl:grid-cols-4 mb-5" role="radiogroup" aria-label="Fonte de dados">
        {catalogo.fontes.map((f) => (
          <button
            key={f.chave}
            type="button"
            role="radio"
            aria-checked={f.chave === fonteChave}
            onClick={() => escolherFonte(f)}
            className={
              'text-left px-3 py-2.5 rounded-lg border transition-colors ' +
              (f.chave === fonteChave
                ? 'border-hipo-blue bg-hipo-blueSoft ring-1 ring-hipo-blue'
                : 'border-hipo-border hover:bg-hipo-bg')
            }
          >
            <span className="block text-sm font-semibold text-hipo-ink">{f.rotulo}</span>
            <span className="block text-xs text-hipo-slate mt-0.5">{f.descricao}</span>
          </button>
        ))}
      </div>

      <h3 className="text-xs font-semibold uppercase tracking-wide text-hipo-muted mb-2">2. De qual período?</h3>
      <SeletorPeriodo fonte={fonte} periodo={periodo} onChange={setPeriodo} />
      {datas && (
        <p className={`text-xs mt-2 ${valido ? 'text-hipo-slate' : 'text-hipo-danger'}`}>
          {valido ? descreverPeriodo(periodo) : 'A data inicial é depois da final.'}
        </p>
      )}

      <div className="flex justify-end mt-5">
        <Button icon={Sparkles} disabled={!valido} onClick={() => onComecar(novaConfig(fonte, periodo))}>
          Montar relatório
        </Button>
      </div>
    </Card>
  );
}

// ── Página ───────────────────────────────────────────────────────────

export default function Relatorios() {
  const [searchParams, setSearchParams] = useSearchParams();
  const idNaUrl = searchParams.get('r');

  const [catalogo, setCatalogo] = useState(null);
  const [salvos, setSalvos] = useState([]);
  const [erro, setErro] = useState(null);
  const [aviso, setAviso] = useState(null);

  const [config, setConfig] = useState(null);
  const [atual, setAtual] = useState(null);       // relatório salvo aberto
  const [snapshot, setSnapshot] = useState(null); // config como estava salva

  const [resultado, setResultado] = useState(null);
  const [consultando, setConsultando] = useState(false);
  const [erroConsulta, setErroConsulta] = useState(null);
  const pedido = useRef(0);

  const [drill, setDrill] = useState(null);
  const [modalSalvar, setModalSalvar] = useState(null); // 'novo' | 'copia' | 'editar'
  const [salvando, setSalvando] = useState(false);
  const [erroSalvar, setErroSalvar] = useState(null);
  const [confirmarExcluir, setConfirmarExcluir] = useState(false);
  const [descartar, setDescartar] = useState(null); // ação pendente

  const fonte = useMemo(
    () => (catalogo && config ? catalogo.fontes.find((f) => f.chave === config.fonte) : null),
    [catalogo, config],
  );

  // ── Carga inicial ──
  const carregarSalvos = useCallback(async () => {
    try {
      const { data } = await api.get('/crm/relatorios/salvos');
      setSalvos(data);
      return data;
    } catch (err) {
      setErro(mensagemDeErro(err, 'Não foi possível carregar os relatórios salvos.'));
      return [];
    }
  }, []);

  useEffect(() => {
    (async () => {
      try {
        const { data } = await api.get('/crm/relatorios/catalogo');
        setCatalogo(data);
      } catch (err) {
        setErro(mensagemDeErro(err, 'Não foi possível carregar o catálogo de campos.'));
      }
    })();
    carregarSalvos();
  }, [carregarSalvos]);

  // ── Abrir relatório salvo ──
  const abrirSalvo = useCallback((r) => {
    if (!catalogo) return;
    const f = catalogo.fontes.find((x) => x.chave === r.fonte);
    if (!f) {
      setErro(`O relatório "${r.nome}" usa uma fonte de dados que não existe mais.`);
      return;
    }
    const { config: cfg, removidos } = normalizarConfig(r.config, f);
    setConfig(cfg);
    setAtual(r);
    setSnapshot(JSON.stringify(cfg));
    setResultado(null);
    setErro(null);
    setAviso(removidos.length
      ? `Alguns campos deste relatório não existem mais e foram retirados: ${removidos.join(', ')}.`
      : null);
    if (searchParams.get('r') !== r.id) setSearchParams({ r: r.id }, { replace: true });
  }, [catalogo, searchParams, setSearchParams]);

  // ?r=<id> abre direto (link compartilhado).
  useEffect(() => {
    if (!catalogo || !idNaUrl || atual?.id === idNaUrl) return;
    const r = salvos.find((x) => x.id === idNaUrl);
    if (r) abrirSalvo(r);
  }, [catalogo, salvos, idNaUrl, atual, abrirSalvo]);

  // ── Consulta (recalcula sozinha) ──
  const chaveConsulta = config ? JSON.stringify(corpoDaConsulta(config)) : null;
  const consultaBase = useMemo(() => (chaveConsulta ? JSON.parse(chaveConsulta) : null), [chaveConsulta]);

  useEffect(() => {
    if (!consultaBase) return undefined;
    const meu = ++pedido.current;
    const t = setTimeout(async () => {
      setConsultando(true);
      try {
        const { data } = await api.post('/crm/relatorios/consulta', consultaBase);
        if (meu !== pedido.current) return;
        setResultado(data);
        setErroConsulta(null);
      } catch (err) {
        if (meu !== pedido.current) return;
        setErroConsulta(mensagemDeErro(err, 'Não foi possível calcular o relatório.'));
      } finally {
        if (meu === pedido.current) setConsultando(false);
      }
    }, 300);
    return () => clearTimeout(t);
  }, [consultaBase]);

  // ── Estado de edição ──
  const sujo = config
    ? (atual ? JSON.stringify(config) !== snapshot
      : config.linhas.length + config.colunas.length + config.filtros.length > 0)
    : false;

  function protegerAlteracoes(acao) {
    if (sujo) setDescartar(() => acao);
    else acao();
  }

  function novo() {
    protegerAlteracoes(() => {
      setConfig(null);
      setAtual(null);
      setSnapshot(null);
      setResultado(null);
      setAviso(null);
      setErroConsulta(null);
      setSearchParams({}, { replace: true });
    });
  }

  function trocarFonte(chave) {
    const f = catalogo.fontes.find((x) => x.chave === chave);
    // Campos são de cada fonte: trocar a fonte recomeça a montagem, mas
    // mantém o período (o intervalo), que continua fazendo sentido.
    setConfig(novaConfig(f, { ...config.periodo, data_ref: f.data_padrao }));
  }

  // ── Salvar ──
  async function salvar(meta) {
    setSalvando(true);
    setErroSalvar(null);
    try {
      const corpo = { ...meta, config };
      const { data } = modalSalvar === 'editar' || (!modalSalvar && atual?.eh_meu)
        ? await api.put(`/crm/relatorios/salvos/${atual.id}`, corpo)
        : await api.post('/crm/relatorios/salvos', corpo);
      setAtual(data);
      setSnapshot(JSON.stringify(config));
      setModalSalvar(null);
      setAviso(`Relatório "${data.nome}" salvo.`);
      setSearchParams({ r: data.id }, { replace: true });
      carregarSalvos();
    } catch (err) {
      const msg = mensagemDeErro(err, 'Não foi possível salvar o relatório.');
      if (modalSalvar) setErroSalvar(msg); else setErro(msg);
    } finally {
      setSalvando(false);
    }
  }

  function clicarSalvar() {
    if (atual?.eh_meu) {
      salvar({ nome: atual.nome, descricao: atual.descricao, compartilhado: atual.compartilhado });
    } else {
      setErroSalvar(null);
      setModalSalvar(atual ? 'copia' : 'novo');
    }
  }

  async function duplicar() {
    try {
      const { data } = await api.post(`/crm/relatorios/salvos/${atual.id}/duplicar`, {});
      const lista = await carregarSalvos();
      abrirSalvo(lista.find((x) => x.id === data.id) || data);
      setAviso(`Cópia "${data.nome}" criada no seu perfil.`);
    } catch (err) {
      setErro(mensagemDeErro(err, 'Não foi possível duplicar o relatório.'));
    }
  }

  async function excluir() {
    try {
      await api.delete(`/crm/relatorios/salvos/${atual.id}`);
      setConfirmarExcluir(false);
      setAviso(`Relatório "${atual.nome}" excluído.`);
      setConfig(null);
      setAtual(null);
      setSnapshot(null);
      setResultado(null);
      setSearchParams({}, { replace: true });
      carregarSalvos();
    } catch (err) {
      setConfirmarExcluir(false);
      setErro(mensagemDeErro(err, 'Não foi possível excluir o relatório.'));
    }
  }

  // ── Drilldown ──
  function abrirCelula(celula) {
    const partes = celula.map((c) => {
      const dim = [...(resultado?.linhas || []), ...(resultado?.colunas || [])]
        .find((d) => d.campo === c.campo && (d.granularidade || null) === (c.granularidade || null));
      return dim ? `${dim.rotulo}: ${formatarDimensao(c.valor, dim)}` : c.valor;
    });
    setDrill({ celula, titulo: partes.length ? partes.join(' · ') : 'todos do período' });
  }

  const totalGeral = resultado
    ? resultado.celulas.find((c) => c.g.every(Boolean)) || null
    : null;

  // ── Render ──
  const acoes = config && (
    <>
      <Button variant="secondary" icon={FilePlus2} onClick={novo} aria-label="Novo relatório">
        <span className="hidden sm:inline">Novo</span>
      </Button>
      {atual?.eh_meu && (
        <Button variant="ghost" icon={Pencil} aria-label="Renomear ou compartilhar" onClick={() => { setErroSalvar(null); setModalSalvar('editar'); }}>
          <span className="hidden md:inline">Renomear / compartilhar</span>
        </Button>
      )}
      {atual && !atual.eh_meu && (
        <Button variant="secondary" icon={Copy} onClick={duplicar}>
          Duplicar <span className="hidden sm:inline">para mim</span>
        </Button>
      )}
      {atual?.eh_meu && (
        <Button variant="secondary" icon={Copy} aria-label="Salvar como novo relatório" onClick={() => { setErroSalvar(null); setModalSalvar('copia'); }}>
          <span className="hidden md:inline">Salvar como…</span>
        </Button>
      )}
      <Button icon={Save} loading={salvando && !modalSalvar} onClick={clicarSalvar} disabled={atual?.eh_meu && !sujo}>
        {atual && !atual.eh_meu ? 'Salvar uma cópia' : 'Salvar'}
      </Button>
      {atual?.eh_meu && (
        <Button variant="ghost" icon={Trash2} onClick={() => setConfirmarExcluir(true)} aria-label="Excluir relatório" className="text-hipo-danger" />
      )}
    </>
  );

  const titulo = atual ? atual.nome : 'Relatórios';
  const subtitulo = atual ? (
    <span className="inline-flex flex-wrap items-center gap-1.5">
      {atual.descricao && <span>{atual.descricao}</span>}
      {atual.compartilhado && atual.eh_meu && <Badge tone="info"><Users size={11} /> Compartilhado</Badge>}
      {!atual.eh_meu && <Badge tone="neutral"><Lock size={11} /> De {atual.dono_nome} — só leitura</Badge>}
      {sujo && <Badge tone="warning">Alterações não salvas</Badge>}
    </span>
  ) : 'Monte tabelas dinâmicas com os dados do HIPO e salve no seu perfil.';

  return (
    <div className="max-w-[1600px] mx-auto pb-6">
      <PageHeader title={titulo} subtitle={subtitulo} actions={acoes} />

      {erro && <AlertMessage tipo="erro" className="mb-4">{erro}</AlertMessage>}
      {aviso && <AlertMessage tipo="info" className="mb-4">{aviso}</AlertMessage>}

      <div className="grid grid-cols-[minmax(0,1fr)] gap-4 lg:grid-cols-[16rem_minmax(0,1fr)]">
        <aside>
          <Card padding="sm">
            <ListaSalvos
              salvos={salvos}
              ativoId={atual?.id}
              onAbrir={(r) => protegerAlteracoes(() => abrirSalvo(r))}
            />
          </Card>
        </aside>

        <div className="min-w-0 space-y-4">
          {!catalogo && !erro && (
            <Card><div className="flex justify-center py-10 text-hipo-slate"><Loader2 className="animate-spin" /></div></Card>
          )}

          {catalogo && !config && <Inicio catalogo={catalogo} onComecar={(c) => { setConfig(c); setAviso(null); }} />}

          {catalogo && config && fonte && (
            <>
              <Card padding="sm">
                <div className="grid gap-2 lg:grid-cols-[14rem_minmax(0,1fr)] mb-3">
                  <Select
                    label="Fonte de dados"
                    id="rel-fonte"
                    value={config.fonte}
                    onChange={(e) => trocarFonte(e.target.value)}
                  >
                    {catalogo.fontes.map((f) => <option key={f.chave} value={f.chave}>{f.rotulo}</option>)}
                  </Select>
                  <SeletorPeriodo
                    compacto
                    fonte={fonte}
                    periodo={config.periodo}
                    onChange={(p) => setConfig({ ...config, periodo: p })}
                  />
                </div>
                <Construtor
                  catalogo={catalogo}
                  fonte={fonte}
                  config={config}
                  consultaBase={consultaBase}
                  onChange={setConfig}
                />
              </Card>

              {!consultaBase && (
                <AlertMessage tipo="aviso">Informe um período válido: a data inicial não pode ser depois da final.</AlertMessage>
              )}
              {erroConsulta && <AlertMessage tipo="erro">{erroConsulta}</AlertMessage>}

              {resultado && (
                <Card padding="sm">
                  <div className="flex flex-wrap items-center gap-2 mb-3">
                    <KpiInline
                      label={`Quantidade de ${fonte.rotulo_registro}`}
                      valor={formatarMedida(resultado.total_registros, 'inteiro')}
                      icone={ListOrdered}
                      tom="bg-hipo-blueSoft text-hipo-blue"
                      titulo="Ver todos os registros do período"
                      onClick={() => abrirCelula([])}
                    />
                    {totalGeral && resultado.valores.map((m, j) => (
                      m.campo === REGISTROS ? null : (
                        <KpiInline
                          key={`${m.campo}-${m.agregacao}`}
                          label={m.rotulo}
                          valor={formatarMedida(totalGeral.v[j], m.formato)}
                          icone={Sigma}
                          titulo={m.rotulo}
                          tom="bg-hipo-bg text-hipo-slate"
                        />
                      )
                    ))}
                    <span className="ml-auto flex items-center gap-3 text-xs text-hipo-slate">
                      {consultando && <Loader2 size={14} className="animate-spin" aria-label="Calculando" />}
                      <span>
                        {resultado.periodo.data_ref_rotulo}: {descreverPeriodo(config.periodo)}
                      </span>
                      <label className="inline-flex items-center gap-1.5 cursor-pointer">
                        <input
                          type="checkbox"
                          checked={config.destacar}
                          onChange={(e) => setConfig({ ...config, destacar: e.target.checked })}
                          className="accent-hipo-blue"
                        />
                        Destacar maiores
                      </label>
                    </span>
                  </div>

                  {resultado.total_registros === 0 ? (
                    <Empty
                      title="Nenhum registro no período"
                      description="Amplie o período, troque a data de referência ou revise os filtros."
                    />
                  ) : (
                    <TabelaDinamica
                      resultado={resultado}
                      ordenacao={config.ordenacao}
                      onOrdenar={(o) => setConfig({ ...config, ordenacao: o })}
                      destacar={config.destacar}
                      onAbrirCelula={abrirCelula}
                    />
                  )}
                  {resultado.linhas.length === 0 && resultado.colunas.length === 0 && resultado.total_registros > 0 && (
                    <p className="text-xs text-hipo-slate mt-2">
                      Dica: adicione um campo em <strong>Linhas</strong> (ex.: Fase, Responsável) para quebrar o total.
                    </p>
                  )}
                </Card>
              )}
            </>
          )}
        </div>
      </div>

      <RegistrosDaCelula
        aberto={!!drill}
        titulo={drill?.titulo}
        celula={drill?.celula}
        consultaBase={consultaBase}
        onFechar={() => setDrill(null)}
      />

      <SalvarRelatorio
        aberto={!!modalSalvar}
        titulo={{ novo: 'Salvar relatório', copia: 'Salvar como novo relatório', editar: 'Nome e compartilhamento' }[modalSalvar] || ''}
        inicial={modalSalvar === 'editar' ? atual
          : modalSalvar === 'copia' ? { nome: `${atual?.nome} (cópia)`, descricao: atual?.descricao } : null}
        periodo={config?.periodo}
        salvando={salvando}
        erro={erroSalvar}
        onSalvar={salvar}
        onFechar={() => setModalSalvar(null)}
      />

      <Modal
        aberto={confirmarExcluir}
        onFechar={() => setConfirmarExcluir(false)}
        titulo="Excluir relatório?"
        size="sm"
        nivel={2}
        footer={(
          <div className="flex justify-end gap-2">
            <Button variant="secondary" onClick={() => setConfirmarExcluir(false)}>Cancelar</Button>
            <Button variant="danger" onClick={excluir}>Excluir</Button>
          </div>
        )}
      >
        <p className="text-sm text-hipo-ink">
          "{atual?.nome}" sai do seu perfil
          {atual?.compartilhado ? ' e deixa de aparecer para a equipe' : ''}. Os dados não são afetados.
        </p>
      </Modal>

      <Modal
        aberto={!!descartar}
        onFechar={() => setDescartar(null)}
        titulo="Descartar alterações?"
        size="sm"
        nivel={2}
        footer={(
          <div className="flex justify-end gap-2">
            <Button variant="secondary" onClick={() => setDescartar(null)}>Continuar editando</Button>
            <Button variant="danger" onClick={() => { const a = descartar; setDescartar(null); a(); }}>Descartar</Button>
          </div>
        )}
      >
        <p className="text-sm text-hipo-ink">A montagem atual tem alterações que não foram salvas.</p>
      </Modal>
    </div>
  );
}
