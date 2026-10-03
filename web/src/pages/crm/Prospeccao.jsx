// web/src/pages/crm/Prospeccao.jsx
//
// Tela do SDR: fatiar a base da Receita e puxar empresas para o CRM.
//
// AS TRÊS DIRETRIZES, AQUI
//
//   Uma tela por função — só SDR e gestão veem o item no menu, e a API
//   barra o resto (CARGOS_PROSPECCAO).
//
//   Dashboard operacional — os números do topo descrevem a fatia ("2.340
//   empresas, 180 já no CRM, 12 bloqueadas") e o botão age sobre ela. O
//   KPI "Puxáveis" e o "Todas" alternam o que a tabela mostra.
//
//   Próxima tarefa — puxar não cria só a oportunidade: cria a tarefa de
//   primeiro contato do SDR, com o prazo escolhido aqui. O placar "Seus
//   suspects abertos" fica ao lado do botão, porque puxar mais com 200
//   parados é encher a fila de tarefa que ninguém vai fazer.
//
// POR QUE O LOTE TEM TETO DE 50
//
// A base é fonte de consulta, não importação. Cada empresa que entra no CRM
// entra por escolha de alguém, com autoria — e 50 é o tamanho de uma
// escolha, não de uma carga. O teto é da API; a tela só não deixa marcar
// mais.

import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { Link } from 'react-router-dom';
import {
  Building2, UserPlus, Handshake, BadgeCheck, Ban, ListChecks, CalendarClock,
  Phone, Mail, Database, ChevronLeft, ChevronRight,
} from 'lucide-react';

import api from '../../api';
import PageHeader from '../../components/ui/PageHeader';
import Card from '../../components/ui/Card';
import Button from '../../components/ui/Button';
import Badge from '../../components/ui/Badge';
import Empty from '../../components/ui/Empty';
import AlertMessage from '../../components/ui/AlertMessage';
import KpiInline from '../../components/ui/KpiInline';
import Table, { Th, Tr, Td } from '../../components/ui/Table';
import SeletorComBusca from '../../components/crm/SeletorComBusca';

export const LIMITE_LOTE = 50;
const PAGINA = 50;

export const PUXAVEIS = ['nova', 'conta_sem_negocio'];

export const SITUACOES = {
  nova: { rotulo: 'Nova', tom: 'info' },
  conta_sem_negocio: { rotulo: 'No CRM, sem negócio', tom: 'neutral' },
  em_negociacao: { rotulo: 'Em negociação', tom: 'warning' },
  cliente: { rotulo: 'Cliente', tom: 'success' },
  bloqueada: { rotulo: 'Não prospectar', tom: 'danger' },
  inativa: { rotulo: 'Conta inativa', tom: 'neutral' },
};

const PORTES = [
  { valor: '01', rotulo: 'ME' },
  { valor: '03', rotulo: 'EPP' },
  { valor: '05', rotulo: 'Demais' },
];

const ROTULO_PORTE = {
  'MICRO EMPRESA': 'ME', 'EMPRESA DE PEQUENO PORTE': 'EPP', DEMAIS: 'Demais',
};

export const FILTROS_INICIAIS = {
  ufs: [],
  cnaes: [],
  municipios: [],
  portes: [],
  regime: '',
  idadeMin: '',
  capitalMin: '',
  secundarios: false,
  comTelefone: false,
  comEmail: false,
  soMatriz: false,
  q: '',
  todas: false,
};

// ── Funções puras (testadas em Prospeccao.test.jsx) ──────────────────

export function fatiaPronta(f) {
  return f.ufs.length > 0 && f.cnaes.length > 0;
}

/** Filtros da tela -> query string da API. Vazio não vai. */
export function montarParams(f) {
  const p = {
    uf: f.ufs,
    cnae: f.cnaes.map((c) => c.valor),
  };
  if (f.municipios.length) p.municipio = f.municipios.map((m) => m.valor);
  if (f.portes.length) p.porte = f.portes;
  if (f.regime) p.regime = f.regime;
  if (f.idadeMin !== '' && Number(f.idadeMin) > 0) p.idade_min = Number(f.idadeMin);
  if (f.capitalMin !== '' && Number(f.capitalMin) > 0) p.capital_min = Number(f.capitalMin);
  if (f.secundarios) p.secundarios = true;
  if (f.comTelefone) p.com_telefone = true;
  if (f.comEmail) p.com_email = true;
  if (f.soMatriz) p.so_matriz = true;
  if (f.q.trim()) p.q = f.q.trim();
  p.situacao = f.todas ? 'todas' : 'puxaveis';
  return p;
}

/**
 * O que foi digitado vira prefixo de CNAE quando é só número de 2 a 7
 * dígitos. "41" pega a divisão inteira; "4120400" é a subclasse exata.
 */
export function opcaoCnaeLivre(texto) {
  const d = (texto || '').replace(/[.\-/\s]/g, '');
  if (!/^\d{2,7}$/.test(d)) return null;
  if (d.length === 7) return { valor: d, rotulo: d };
  return { valor: d, rotulo: `${d} (todos que começam assim)` };
}

/** Prazo do primeiro contato: hoje = agora; outro dia = 9h local. */
export function prazoParaApi(dataIso, hoje) {
  if (!dataIso || dataIso === hoje) return null;
  return new Date(`${dataIso}T09:00:00`).toISOString();
}

export function hojeLocal(agora = new Date()) {
  const z = (n) => String(n).padStart(2, '0');
  return `${agora.getFullYear()}-${z(agora.getMonth() + 1)}-${z(agora.getDate())}`;
}

function mensagemDeErro(err, padrao) {
  const d = err?.response?.data?.detail;
  if (typeof d === 'string') return d;
  if (Array.isArray(d) && d[0]?.msg) return d[0].msg;
  if (d?.mensagem) return d.mensagem;
  return padrao;
}

const moeda = new Intl.NumberFormat('pt-BR', {
  style: 'currency', currency: 'BRL', maximumFractionDigits: 0,
});
const inteiro = new Intl.NumberFormat('pt-BR');

function anos(dataIso) {
  if (!dataIso) return '—';
  const d = new Date(`${dataIso}T00:00:00`);
  const a = Math.floor((Date.now() - d.getTime()) / (365.25 * 24 * 3600 * 1000));
  return a < 1 ? 'menos de 1 ano' : `${a} ${a === 1 ? 'ano' : 'anos'}`;
}

// ── Tela ─────────────────────────────────────────────────────────────

export default function Prospeccao() {
  const [base, setBase] = useState(null);
  const [filtros, setFiltros] = useState(FILTROS_INICIAIS);
  const [ordem, setOrdem] = useState('capital');
  const [offset, setOffset] = useState(0);
  const [resumo, setResumo] = useState(null);
  const [lista, setLista] = useState({ itens: [], total: 0 });
  const [carregando, setCarregando] = useState(false);
  const [erro, setErro] = useState(null);
  const [selecao, setSelecao] = useState(() => new Map());
  const [prazo, setPrazo] = useState(hojeLocal());
  const [puxando, setPuxando] = useState(false);
  const [resultado, setResultado] = useState(null);
  const pedido = useRef(0);

  useEffect(() => {
    let vivo = true;
    api.get('/crm/prospeccao/base')
      .then(({ data }) => {
        if (!vivo) return;
        setBase(data);
        // Com uma UF só na base, ela já vem marcada: é um clique a menos
        // num campo que não tem escolha.
        if (data.carregada && data.ufs.length === 1) {
          setFiltros((f) => ({ ...f, ufs: data.ufs }));
        }
      })
      .catch((err) => vivo && setErro(mensagemDeErro(err, 'Não foi possível ler a base.')));
    return () => { vivo = false; };
  }, []);

  const params = useMemo(() => montarParams(filtros), [filtros]);
  const pronta = fatiaPronta(filtros);

  const carregar = useCallback(async () => {
    if (!pronta) return;
    const meu = ++pedido.current;
    setCarregando(true);
    setErro(null);
    try {
      const [r1, r2] = await Promise.all([
        api.get('/crm/prospeccao/resumo', { params }),
        api.get('/crm/prospeccao', { params: { ...params, ordem, limit: PAGINA, offset } }),
      ]);
      if (meu !== pedido.current) return;
      setResumo(r1.data);
      setLista(r2.data);
    } catch (err) {
      if (meu === pedido.current) setErro(mensagemDeErro(err, 'Não foi possível consultar a fatia.'));
    } finally {
      if (meu === pedido.current) setCarregando(false);
    }
  }, [pronta, params, ordem, offset]);

  // Debounce: o campo de busca dispara a cada tecla.
  useEffect(() => {
    if (!pronta) {
      setResumo(null);
      setLista({ itens: [], total: 0 });
      return undefined;
    }
    const id = setTimeout(carregar, 300);
    return () => clearTimeout(id);
  }, [carregar, pronta]);

  function mudar(campo, valor) {
    setFiltros((f) => ({ ...f, [campo]: valor }));
    setOffset(0);
  }

  const buscarCnaes = useCallback(async (q) => {
    const { data } = await api.get('/crm/prospeccao/cnaes', { params: { q } });
    return data.map((c) => ({ valor: c.codigo, rotulo: c.codigo, detalhe: c.descricao }));
  }, []);

  const buscarMunicipios = useCallback(async (q) => {
    const { data } = await api.get('/crm/prospeccao/municipios', {
      params: { uf: filtros.ufs, q },
    });
    return data.map((m) => ({ valor: m.codigo, rotulo: m.nome, detalhe: m.uf }));
  }, [filtros.ufs]);

  // ── Seleção ──
  const selecionaveis = lista.itens.filter((i) => PUXAVEIS.includes(i.situacao));
  const todosDaPaginaMarcados =
    selecionaveis.length > 0 && selecionaveis.every((i) => selecao.has(i.cnpj));

  function alternar(item) {
    setSelecao((atual) => {
      const nova = new Map(atual);
      if (nova.has(item.cnpj)) nova.delete(item.cnpj);
      else if (nova.size < LIMITE_LOTE) nova.set(item.cnpj, item.razao_social);
      return nova;
    });
  }

  function alternarPagina() {
    setSelecao((atual) => {
      const nova = new Map(atual);
      if (todosDaPaginaMarcados) {
        selecionaveis.forEach((i) => nova.delete(i.cnpj));
      } else {
        for (const i of selecionaveis) {
          if (nova.size >= LIMITE_LOTE) break;
          nova.set(i.cnpj, i.razao_social);
        }
      }
      return nova;
    });
  }

  async function puxar() {
    setPuxando(true);
    setResultado(null);
    setErro(null);
    try {
      const { data } = await api.post('/crm/prospeccao/puxar', {
        cnpjs: [...selecao.keys()],
        prazo: prazoParaApi(prazo, hojeLocal()),
      });
      setResultado(data);
      setSelecao(new Map());
      await carregar();
    } catch (err) {
      setErro(mensagemDeErro(err, 'Não foi possível puxar as empresas.'));
    } finally {
      setPuxando(false);
    }
  }

  // ── Render ──
  if (base && !base.carregada) {
    return (
      <div className="space-y-6">
        <PageHeader title="Prospecção" />
        <Card>
          <Empty
            icon={Database}
            title="A base da Receita ainda não foi carregada"
            description="A carga é feita pela gestão uma vez por mês, com o script carregar_base_receita. Depois dela, esta tela fatia as empresas ativas por CNAE e cidade."
          />
        </Card>
      </div>
    );
  }

  const subtitulo = base?.carregada
    ? `Base da Receita de ${base.referencia} (${base.ufs.join(', ')}), ${inteiro.format(base.estabelecimentos || 0)} empresas ativas`
    : 'Carregando a base…';

  return (
    <div className="space-y-4 pb-24">
      <PageHeader title="Prospecção" subtitle={subtitulo} />

      {/* ── Recorte ── */}
      <Card padding="sm">
        <div data-tour="pro-recorte" className="grid gap-3 lg:grid-cols-[auto_minmax(0,2fr)_minmax(0,1.3fr)]">
          <div>
            <span className="block text-xs font-medium text-hipo-slate mb-1">UF</span>
            <div className="flex flex-wrap gap-1.5" role="group" aria-label="UF">
              {(base?.ufs || []).map((uf) => {
                const ativo = filtros.ufs.includes(uf);
                return (
                  <button
                    key={uf}
                    type="button"
                    aria-pressed={ativo}
                    onClick={() => mudar('ufs', ativo ? filtros.ufs.filter((u) => u !== uf) : [...filtros.ufs, uf])}
                    className={
                      'h-10 px-3 rounded-lg border text-sm font-medium ' +
                      (ativo ? 'bg-hipo-blue text-white border-hipo-blue' : 'bg-hipo-card border-hipo-border text-hipo-ink hover:bg-hipo-bg')
                    }
                  >
                    {uf}
                  </button>
                );
              })}
            </div>
          </div>
          <SeletorComBusca
            rotulo="CNAE"
            placeholder="Código (41, 4120400) ou atividade"
            selecionados={filtros.cnaes}
            onMudar={(v) => mudar('cnaes', v)}
            buscar={buscarCnaes}
            opcaoLivre={opcaoCnaeLivre}
          />
          <SeletorComBusca
            rotulo="Cidade"
            placeholder="Todas as cidades da UF"
            selecionados={filtros.municipios}
            onMudar={(v) => mudar('municipios', v)}
            buscar={buscarMunicipios}
            desabilitado={!filtros.ufs.length}
          />
        </div>

        <div className="mt-3 flex flex-wrap items-end gap-x-4 gap-y-3">
          <div>
            <span className="block text-xs font-medium text-hipo-slate mb-1">Porte</span>
            <div data-tour="pro-porte" className="flex gap-1" role="group" aria-label="Porte">
              {PORTES.map((p) => {
                const ativo = filtros.portes.includes(p.valor);
                return (
                  <button
                    key={p.valor}
                    type="button"
                    aria-pressed={ativo}
                    onClick={() => mudar('portes', ativo ? filtros.portes.filter((x) => x !== p.valor) : [...filtros.portes, p.valor])}
                    className={
                      'h-9 px-2.5 rounded-md border text-xs font-medium ' +
                      (ativo ? 'bg-hipo-blueSoft text-hipo-blueDark border-hipo-blue' : 'bg-hipo-card border-hipo-border text-hipo-slate hover:bg-hipo-bg')
                    }
                  >
                    {p.rotulo}
                  </button>
                );
              })}
            </div>
          </div>

          <label className="block">
            <span className="block text-xs font-medium text-hipo-slate mb-1">Regime</span>
            <select
              value={filtros.regime}
              onChange={(e) => mudar('regime', e.target.value)}
              className="h-9 px-2 rounded-md border border-hipo-border bg-hipo-card text-sm text-hipo-ink"
            >
              <option value="">Qualquer</option>
              <option value="nao_simples">Fora do Simples</option>
              <option value="simples">Optante do Simples</option>
            </select>
          </label>

          <label className="block w-28">
            <span className="block text-xs font-medium text-hipo-slate mb-1">Aberta há (anos)</span>
            <input
              type="number" min="0" max="100" inputMode="numeric"
              value={filtros.idadeMin}
              onChange={(e) => mudar('idadeMin', e.target.value)}
              placeholder="0"
              className="h-9 w-full px-2 rounded-md border border-hipo-border bg-hipo-card text-sm"
            />
          </label>

          <label className="block w-36">
            <span className="block text-xs font-medium text-hipo-slate mb-1">Capital mínimo (R$)</span>
            <input
              type="number" min="0" step="10000" inputMode="numeric"
              value={filtros.capitalMin}
              onChange={(e) => mudar('capitalMin', e.target.value)}
              placeholder="0"
              className="h-9 w-full px-2 rounded-md border border-hipo-border bg-hipo-card text-sm"
            />
          </label>

          <label className="block flex-1 min-w-[12rem]">
            <span className="block text-xs font-medium text-hipo-slate mb-1">Buscar na fatia</span>
            <input
              value={filtros.q}
              onChange={(e) => mudar('q', e.target.value)}
              placeholder="Nome ou CNPJ"
              className="h-9 w-full px-2 rounded-md border border-hipo-border bg-hipo-card text-sm"
            />
          </label>
        </div>

        <div data-tour="pro-opcoes" className="mt-3 flex flex-wrap gap-x-5 gap-y-2 text-sm text-hipo-ink">
          {[
            ['secundarios', 'Incluir CNAE secundário'],
            ['comTelefone', 'Com telefone'],
            ['comEmail', 'Com e-mail'],
            ['soMatriz', 'Só matriz'],
          ].map(([campo, rotulo]) => (
            <label key={campo} className="inline-flex items-center gap-2 cursor-pointer">
              <input
                type="checkbox"
                checked={filtros[campo]}
                onChange={(e) => mudar(campo, e.target.checked)}
                className="w-4 h-4 accent-[rgb(var(--hipo-blue))]"
              />
              {rotulo}
            </label>
          ))}
        </div>
      </Card>

      {erro && <AlertMessage tipo="erro">{erro}</AlertMessage>}

      {resultado && <ResultadoPuxada resultado={resultado} onFechar={() => setResultado(null)} />}

      {!pronta ? (
        <Card>
          <Empty
            icon={Building2}
            title="Escolha a UF e ao menos um CNAE"
            description="Digite um código (41 pega a divisão inteira de construção) ou parte da atividade. A cidade é opcional."
          />
        </Card>
      ) : (
        <>
          {/* ── O que é a fatia ── */}
          {resumo && (
            <div data-tour="pro-resumo" className="flex flex-wrap gap-2" aria-label="Resumo da fatia">
              <KpiInline label="Na fatia" valor={inteiro.format(resumo.total)}
                icone={Building2} tom="bg-hipo-bg text-hipo-slate" />
              <KpiInline label="Puxáveis" valor={inteiro.format(resumo.puxaveis)}
                detalhe={resumo.conta_sem_negocio ? `${inteiro.format(resumo.conta_sem_negocio)} já no CRM` : null}
                icone={UserPlus} tom="bg-hipo-blueSoft text-hipo-blue"
                ativo={!filtros.todas} onClick={() => mudar('todas', false)}
                titulo="Mostrar só as empresas que podem ser puxadas" />
              <KpiInline label="Em negociação" valor={inteiro.format(resumo.em_negociacao)}
                icone={Handshake} tom="bg-hipo-warningSoft text-hipo-warning"
                ativo={filtros.todas} onClick={() => mudar('todas', true)}
                titulo="Mostrar a fatia inteira, com a situação de cada empresa" />
              <KpiInline label="Clientes" valor={inteiro.format(resumo.clientes)}
                icone={BadgeCheck} tom="bg-hipo-successSoft text-hipo-success" />
              <KpiInline label="Não prospectar" valor={inteiro.format(resumo.bloqueadas + resumo.inativas)}
                icone={Ban} tom="bg-hipo-dangerSoft text-hipo-danger" />
              <div className="flex-1" />
              <KpiInline label="Seus suspects abertos" valor={inteiro.format(resumo.meus_suspects_abertos)}
                detalhe={`${inteiro.format(resumo.minhas_puxadas_no_mes)} no mês`}
                icone={ListChecks}
                tom={resumo.meus_suspects_abertos >= 100 ? 'bg-hipo-warningSoft text-hipo-warning' : 'bg-hipo-bg text-hipo-slate'}
                titulo="Oportunidades puxadas da base por você que ainda estão em Suspect" />
            </div>
          )}

          {/* ── A lista ── */}
          <Card padding="none">
            <div className="flex flex-wrap items-center justify-between gap-2 px-5 py-3 border-b border-hipo-border">
              <p className="text-sm text-hipo-slate">
                {carregando ? 'Consultando…' : `${inteiro.format(lista.total)} ${filtros.todas ? 'na fatia' : 'puxáveis'}`}
              </p>
              <label className="text-sm text-hipo-slate inline-flex items-center gap-2">
                Ordenar por
                <select
                  value={ordem}
                  onChange={(e) => { setOrdem(e.target.value); setOffset(0); }}
                  className="h-8 px-2 rounded-md border border-hipo-border bg-hipo-card text-sm text-hipo-ink"
                >
                  <option value="capital">Maior capital</option>
                  <option value="abertura">Mais antigas</option>
                  <option value="razao">Nome</option>
                </select>
              </label>
            </div>

            {lista.itens.length === 0 && !carregando ? (
              <Empty
                title="Nenhuma empresa nesta fatia"
                description={filtros.todas ? 'Afrouxe algum filtro.' : 'Todas já estão no CRM. Marque "Em negociação" para ver a fatia inteira.'}
              />
            ) : (
              <Table>
                <thead>
                  <tr>
                    <Th className="w-10">
                      <input
                        type="checkbox"
                        aria-label="Selecionar a página"
                        checked={todosDaPaginaMarcados}
                        disabled={!selecionaveis.length}
                        onChange={alternarPagina}
                        className="w-4 h-4"
                      />
                    </Th>
                    <Th>Empresa</Th>
                    <Th>CNAE</Th>
                    <Th>Onde</Th>
                    <Th>Porte</Th>
                    <Th align="right">Capital</Th>
                    <Th>Aberta há</Th>
                    <Th>Contato</Th>
                    <Th>Situação</Th>
                  </tr>
                </thead>
                <tbody>
                  {lista.itens.map((i) => {
                    const puxavel = PUXAVEIS.includes(i.situacao);
                    const marcado = selecao.has(i.cnpj);
                    const sit = SITUACOES[i.situacao] || { rotulo: i.situacao, tom: 'neutral' };
                    return (
                      <Tr key={i.cnpj} className={marcado ? 'bg-hipo-blueSoft/40' : ''}>
                        <Td>
                          <input
                            type="checkbox"
                            aria-label={`Selecionar ${i.razao_social}`}
                            checked={marcado}
                            disabled={!puxavel || (!marcado && selecao.size >= LIMITE_LOTE)}
                            onChange={() => alternar(i)}
                            className="w-4 h-4"
                          />
                        </Td>
                        <Td>
                          <p className="font-medium text-hipo-ink">{i.nome_fantasia || i.razao_social}</p>
                          <p className="text-xs text-hipo-slate">
                            {i.nome_fantasia ? `${i.razao_social}, ` : ''}{i.cnpj_formatado}{i.matriz ? '' : ' (filial)'}
                          </p>
                        </Td>
                        <Td>
                          <p className="text-hipo-ink">{i.cnae_principal}</p>
                          <p className="text-xs text-hipo-slate max-w-[16rem] truncate" title={i.cnae_descricao || ''}>
                            {i.cnae_descricao || '—'}
                          </p>
                        </Td>
                        <Td>
                          <p className="text-hipo-ink">{i.municipio || '—'}</p>
                          <p className="text-xs text-hipo-slate">{i.bairro || ''}</p>
                        </Td>
                        <Td>
                          <p className="text-hipo-ink">{ROTULO_PORTE[i.porte] || '—'}</p>
                          <p className="text-xs text-hipo-slate">
                            {i.simples === true ? 'Simples' : i.simples === false ? 'Fora do Simples' : ''}
                          </p>
                        </Td>
                        <Td align="right" className="tabular-nums">
                          {i.capital_social != null ? moeda.format(Number(i.capital_social)) : '—'}
                        </Td>
                        <Td>{anos(i.data_abertura)}</Td>
                        <Td>
                          <span className="inline-flex gap-1.5 text-hipo-slate">
                            {i.telefone && <Phone size={14} aria-label="Tem telefone" />}
                            {i.email && <Mail size={14} aria-label="Tem e-mail" />}
                            {!i.telefone && !i.email && '—'}
                          </span>
                        </Td>
                        <Td><Badge tone={sit.tom}>{sit.rotulo}</Badge></Td>
                      </Tr>
                    );
                  })}
                </tbody>
              </Table>
            )}

            {lista.total > PAGINA && (
              <div className="flex items-center justify-end gap-2 px-5 py-3 border-t border-hipo-border text-sm text-hipo-slate">
                {offset + 1}–{Math.min(offset + PAGINA, lista.total)} de {inteiro.format(lista.total)}
                <Button variant="secondary" size="sm" icon={ChevronLeft}
                  disabled={offset === 0} onClick={() => setOffset(Math.max(0, offset - PAGINA))}
                  aria-label="Página anterior" />
                <Button variant="secondary" size="sm" icon={ChevronRight}
                  disabled={offset + PAGINA >= lista.total} onClick={() => setOffset(offset + PAGINA)}
                  aria-label="Próxima página" />
              </div>
            )}
          </Card>
        </>
      )}

      {/* ── Ação ── */}
      {selecao.size > 0 && (
        <div data-tour="pro-barra-acao" className="fixed bottom-0 inset-x-0 z-40 bg-hipo-card border-t border-hipo-border shadow-soft">
          <div className="max-w-7xl mx-auto px-4 py-3 flex flex-wrap items-center gap-3">
            <p className="text-sm text-hipo-ink">
              <strong>{selecao.size}</strong> {selecao.size === 1 ? 'empresa selecionada' : 'empresas selecionadas'}
              <span className="text-hipo-slate"> (até {LIMITE_LOTE} por vez)</span>
            </p>
            <button type="button" className="text-sm text-hipo-slate underline" onClick={() => setSelecao(new Map())}>
              Limpar
            </button>
            <div className="flex-1" />
            <label className="inline-flex items-center gap-2 text-sm text-hipo-slate">
              <CalendarClock size={15} aria-hidden="true" />
              Primeiro contato em
              <input
                type="date"
                value={prazo}
                min={hojeLocal()}
                onChange={(e) => setPrazo(e.target.value)}
                aria-label="Data do primeiro contato"
                className="h-9 px-2 rounded-md border border-hipo-border bg-hipo-card text-sm text-hipo-ink"
              />
            </label>
            <Button icon={UserPlus} loading={puxando} onClick={puxar}>
              Puxar para o HIPO
            </Button>
          </div>
        </div>
      )}
    </div>
  );
}

function ResultadoPuxada({ resultado, onFechar }) {
  const { puxadas, puladas, enriquecimento_em_segundo_plano: emSegundo } = resultado;
  const tipo = puxadas.length ? (puladas.length ? 'aviso' : 'ok') : 'aviso';
  return (
    <AlertMessage tipo={tipo}>
      <div className="flex flex-wrap items-start justify-between gap-2">
        <div className="space-y-1">
          <p className="font-semibold">
            {puxadas.length
              ? `${puxadas.length} ${puxadas.length === 1 ? 'empresa puxada' : 'empresas puxadas'} para o funil, com tarefa de primeiro contato para você.`
              : 'Nenhuma empresa foi puxada.'}
          </p>
          {emSegundo > 0 && (
            <p>Sócios e CNAEs secundários chegam da Receita em alguns instantes.</p>
          )}
          {puladas.length > 0 && (
            <details>
              <summary className="cursor-pointer">
                {puladas.length} {puladas.length === 1 ? 'ficou de fora' : 'ficaram de fora'}
              </summary>
              <ul className="mt-1 list-disc pl-5">
                {puladas.map((p) => (
                  <li key={`${p.cnpj}-${p.motivo}`}>
                    {p.razao_social || p.cnpj}: {p.mensagem}
                  </li>
                ))}
              </ul>
            </details>
          )}
          {puxadas.length > 0 && (
            <p>
              <Link to="/crm/tarefas" className="underline font-medium">Ir para minhas tarefas</Link>
            </p>
          )}
        </div>
        <button type="button" onClick={onFechar} className="text-sm underline">Fechar</button>
      </div>
    </AlertMessage>
  );
}
