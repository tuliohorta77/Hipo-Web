// web/src/pages/crm/Contas.jsx
//
// Lista de Contas — dashboard operacional (diretriz pétrea 2): os KPIs do topo
// não são decoração. Cada um é toggle e aplica na tabela abaixo exatamente o
// filtro que o compõe.
//
// Dois modais, de propósito:
//
//   * NOVA CONTA (md) — só o essencial para o registro existir: razão social,
//     CNPJ e mais dois campos. Cadastro rápido não é hora de pedir endereço.
//
//   * VISÃO 360 (full) — abre ao clicar na linha. Identificação fixa em cima,
//     resto em abas, começando por Oportunidades. É onde o cadastro se
//     completa.
//
// O "vendedor" da conta é derivado no backend a partir dos EVs das
// oportunidades ativas — não existe campo de vendedor em lugar nenhum.

import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import {
  Building2, Search, Plus, Handshake, CircleSlash, Layers, X,
} from 'lucide-react';

import api from '../../api';
import PageHeader from '../../components/ui/PageHeader';
import Card, { CardHeader } from '../../components/ui/Card';
import KpiCard from '../../components/ui/KpiCard';
import Table, { Th, Tr, Td } from '../../components/ui/Table';
import Button from '../../components/ui/Button';
import Input, { Select } from '../../components/ui/Input';
import Modal from '../../components/ui/Modal';
import Badge from '../../components/ui/Badge';
import Empty from '../../components/ui/Empty';
import AlertMessage from '../../components/ui/AlertMessage';
import ContaDetalhe from '../../components/crm/ContaDetalhe';

const POR_PAGINA = 50;

const UFS = [
  'AC', 'AL', 'AM', 'AP', 'BA', 'CE', 'DF', 'ES', 'GO', 'MA', 'MG', 'MS',
  'MT', 'PA', 'PB', 'PE', 'PI', 'PR', 'RJ', 'RN', 'RO', 'RR', 'RS', 'SC',
  'SE', 'SP', 'TO',
];

const FILTROS_VAZIOS = {
  q: '',
  vertical_id: '',
  uf: '',
  eh_finder: '',
  ativo: '',
  sem_oportunidade_ativa: false,
  sem_vertical: false,
};

// ── Helpers ──────────────────────────────────────────────────────────

export function mascararCnpj(valor) {
  const d = (valor || '').replace(/\D/g, '').slice(0, 14);
  if (d.length <= 2) return d;
  if (d.length <= 5) return `${d.slice(0, 2)}.${d.slice(2)}`;
  if (d.length <= 8) return `${d.slice(0, 2)}.${d.slice(2, 5)}.${d.slice(5)}`;
  if (d.length <= 12) return `${d.slice(0, 2)}.${d.slice(2, 5)}.${d.slice(5, 8)}/${d.slice(8)}`;
  return `${d.slice(0, 2)}.${d.slice(2, 5)}.${d.slice(5, 8)}/${d.slice(8, 12)}-${d.slice(12)}`;
}

// Validação de dígito verificador no cliente. Espelha services/cnpj.py — o
// backend continua sendo a autoridade; isto só evita a ida ao servidor para
// um erro que dá para apontar no próprio campo.
export function cnpjValido(valor) {
  const n = (valor || '').replace(/\D/g, '');
  if (n.length !== 14) return false;
  if (/^(\d)\1{13}$/.test(n)) return false;

  const dv = (base, pesos) => {
    const soma = base
      .split('')
      .reduce((acc, d, i) => acc + Number(d) * pesos[i], 0);
    const resto = soma % 11;
    return resto < 2 ? '0' : String(11 - resto);
  };

  const p1 = [5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2];
  const p2 = [6, 5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2];
  return n[12] === dv(n.slice(0, 12), p1) && n[13] === dv(n.slice(0, 13), p2);
}

function mensagemDeErro(err, padrao) {
  const d = err?.response?.data?.detail;
  if (typeof d === 'string') return d;
  if (Array.isArray(d) && d[0]?.msg) return d[0].msg;
  if (d?.mensagem) return d.mensagem;
  return padrao;
}

function KpiBotao({ onClick, ativo, children }) {
  return (
    <button
      type="button"
      onClick={onClick}
      aria-pressed={ativo}
      className={
        'text-left w-full rounded-xl transition-shadow focus:outline-none ' +
        'focus-visible:ring-2 focus-visible:ring-hipo-blue ' +
        (ativo ? 'ring-2 ring-hipo-blue' : 'hover:shadow-md')
      }
    >
      {children}
    </button>
  );
}

// ── Modal de criação ─────────────────────────────────────────────────

const FORM_NOVO = {
  razao_social: '', nome_fantasia: '', cnpj: '', vertical_id: '',
  num_funcionarios: '',
};

function FormNovaConta({ aberto, onFechar, onCriada, onAbrirExistente, verticais }) {
  const [form, setForm] = useState(FORM_NOVO);
  const [erros, setErros] = useState({});
  const [erroGeral, setErroGeral] = useState(null);
  const [conflito, setConflito] = useState(null);
  const [salvando, setSalvando] = useState(false);

  useEffect(() => {
    if (!aberto) return;
    setForm(FORM_NOVO);
    setErros({});
    setErroGeral(null);
    setConflito(null);
  }, [aberto]);

  function set(campo, valor) {
    setForm((f) => ({ ...f, [campo]: valor }));
    setErros((e) => ({ ...e, [campo]: undefined }));
  }

  async function salvar() {
    const e = {};
    if (!form.razao_social.trim()) e.razao_social = 'Informe a razão social.';
    if (!cnpjValido(form.cnpj)) e.cnpj = 'CNPJ inválido.';
    setErros(e);
    if (Object.keys(e).length) return;

    setSalvando(true);
    setErroGeral(null);
    setConflito(null);
    try {
      const { data } = await api.post('/crm/contas', {
        razao_social: form.razao_social,
        nome_fantasia: form.nome_fantasia || null,
        cnpj: form.cnpj.replace(/\D/g, ''),
        vertical_id: form.vertical_id ? Number(form.vertical_id) : null,
        num_funcionarios: form.num_funcionarios === '' ? null : Number(form.num_funcionarios),
      });
      onCriada(data);
    } catch (err) {
      const d = err?.response?.data?.detail;
      // 409 traz a conta existente: em vez de só barrar, oferecemos abrir.
      if (err?.response?.status === 409 && d?.conta_id) setConflito(d);
      else setErroGeral(mensagemDeErro(err, 'Não foi possível criar a conta.'));
    } finally {
      setSalvando(false);
    }
  }

  return (
    <Modal
      aberto={aberto}
      onFechar={onFechar}
      titulo="Nova conta"
      subtitulo="O restante do cadastro você completa na tela da conta"
      size="md"
      footer={
        <div className="flex justify-end gap-2">
          <Button variant="ghost" onClick={onFechar}>Cancelar</Button>
          <Button onClick={salvar} loading={salvando}>Criar conta</Button>
        </div>
      }
    >
      <div className="space-y-4">
        {erroGeral && <AlertMessage tipo="erro">{erroGeral}</AlertMessage>}

        {conflito && (
          <AlertMessage tipo="aviso">
            <div className="space-y-2">
              <p>
                {conflito.mensagem} Já existe a conta{' '}
                <strong>{conflito.razao_social}</strong>
                {conflito.ativo === false && ' (desativada)'}.
              </p>
              <Button
                size="sm"
                variant="secondary"
                onClick={() => onAbrirExistente(conflito.conta_id)}
              >
                Abrir a conta existente
              </Button>
            </div>
          </AlertMessage>
        )}

        <Input
          label="Razão social *"
          value={form.razao_social}
          error={erros.razao_social}
          onChange={(e) => set('razao_social', e.target.value)}
        />
        <Input
          label="CNPJ *"
          value={form.cnpj}
          error={erros.cnpj}
          placeholder="00.000.000/0000-00"
          onChange={(e) => set('cnpj', mascararCnpj(e.target.value))}
        />
        <Input
          label="Nome fantasia"
          value={form.nome_fantasia}
          onChange={(e) => set('nome_fantasia', e.target.value)}
        />
        <div className="grid grid-cols-2 gap-4">
          <Select
            label="Vertical"
            value={form.vertical_id}
            onChange={(e) => set('vertical_id', e.target.value)}
          >
            <option value="">— sem vertical —</option>
            {verticais.map((v) => <option key={v.id} value={v.id}>{v.nome}</option>)}
          </Select>
          <Input
            label="Nº de funcionários"
            type="number"
            min="0"
            value={form.num_funcionarios}
            onChange={(e) => set('num_funcionarios', e.target.value)}
          />
        </div>
      </div>
    </Modal>
  );
}

// ── Página ───────────────────────────────────────────────────────────

export default function Contas() {
  const [resumo, setResumo] = useState(null);
  const [dados, setDados] = useState({ total: 0, itens: [] });
  const [verticais, setVerticais] = useState([]);
  const [filtros, setFiltros] = useState(FILTROS_VAZIOS);
  const [busca, setBusca] = useState('');
  const [pagina, setPagina] = useState(0);
  const [carregando, setCarregando] = useState(true);
  const [erro, setErro] = useState(null);
  const [novaAberta, setNovaAberta] = useState(false);
  const [detalhe, setDetalhe] = useState(null);
  const [abrindo, setAbrindo] = useState(false);
  const [kpiAtivo, setKpiAtivo] = useState(null);
  const [acaoSalvar, setAcaoSalvar] = useState(null);
  const debounce = useRef(null);

  // Busca com debounce: sem isso, cada tecla vira uma request.
  // O `f.q === busca ? f : ...` nao e microtuning: devolver o MESMO objeto faz
  // o React abortar o re-render. Sem isso, o timer dispara uma vez na montagem
  // com a busca vazia, cria um `filtros` novo por identidade, o useMemo de
  // `params` recalcula, o useCallback de `carregar` troca e a tela busca tudo
  // de novo — piscando o estado de carregando e desmontando o conteudo que ja
  // estava na tela.
  useEffect(() => {
    clearTimeout(debounce.current);
    debounce.current = setTimeout(() => {
      setFiltros((f) => (f.q === busca ? f : { ...f, q: busca }));
      setPagina((p) => (p === 0 ? p : 0));
    }, 350);
    return () => clearTimeout(debounce.current);
  }, [busca]);

  const params = useMemo(() => {
    const p = { limit: POR_PAGINA, offset: pagina * POR_PAGINA };
    if (filtros.q) p.q = filtros.q;
    if (filtros.vertical_id) p.vertical_id = filtros.vertical_id;
    if (filtros.uf) p.uf = filtros.uf;
    if (filtros.eh_finder !== '') p.eh_finder = filtros.eh_finder;
    if (filtros.ativo !== '') p.ativo = filtros.ativo;
    if (filtros.sem_oportunidade_ativa) p.sem_oportunidade_ativa = true;
    if (filtros.sem_vertical) p.sem_vertical = true;
    return p;
  }, [filtros, pagina]);

  const carregar = useCallback(async () => {
    setCarregando(true);
    setErro(null);
    try {
      const [lista, kpis, verts] = await Promise.all([
        api.get('/crm/contas', { params }),
        api.get('/crm/contas/resumo'),
        api.get('/crm/dominio/verticais'),
      ]);
      setDados(lista.data);
      setResumo(kpis.data);
      setVerticais(verts.data);
    } catch (err) {
      setErro(mensagemDeErro(err, 'Não foi possível carregar as contas.'));
    } finally {
      setCarregando(false);
    }
  }, [params]);

  useEffect(() => { carregar(); }, [carregar]);

  const carregarDetalhe = useCallback(async (id) => {
    const { data } = await api.get(`/crm/contas/${id}`);
    return data;
  }, []);

  // A listagem devolve o resumo da conta; a visão 360 precisa do detalhe
  // (com contatos e oportunidades). Por isso abrir busca o registro completo.
  async function abrirConta(id) {
    setAbrindo(true);
    setErro(null);
    try {
      setDetalhe(await carregarDetalhe(id));
      setNovaAberta(false);
    } catch (err) {
      setErro(mensagemDeErro(err, 'Não foi possível abrir a conta.'));
    } finally {
      setAbrindo(false);
    }
  }

  // Estas três são passadas como prop para o ContaDetalhe. Mantê-las
  // estáveis não é otimização: prop nova a cada render do pai realimenta os
  // efeitos do filho e já produziu loop de renderização aqui.
  const recarregarDetalhe = useCallback(async () => {
    if (!detalhe) return;
    try {
      setDetalhe(await carregarDetalhe(detalhe.id));
      carregar();
    } catch (err) {
      setErro(mensagemDeErro(err, 'Não foi possível recarregar a conta.'));
    }
  }, [detalhe, carregarDetalhe, carregar]);

  const criarVertical = useCallback(async (nome) => {
    const { data } = await api.post('/crm/dominio/verticais', { nome });
    setVerticais((vs) => (vs.some((v) => v.id === data.id) ? vs : [...vs, data]));
    return data;
  }, []);

  const aoSalvarConta = useCallback((atualizada) => {
    setDetalhe(atualizada);
    carregar();
  }, [carregar]);

  function aplicar(parciais) {
    setFiltros((f) => ({ ...f, ...parciais }));
    setPagina(0);
  }

  // KPI é toggle: clicar de novo no mesmo cartão desfaz o filtro. Sem isso, a
  // única forma de voltar seria o "Limpar filtros", que também apaga a busca
  // e os selects — mais do que o usuário pediu.
  function alternarKpi(chave, parciais) {
    const base = {
      ...FILTROS_VAZIOS,
      q: filtros.q,
      vertical_id: filtros.vertical_id,
      uf: filtros.uf,
    };
    if (kpiAtivo === chave) {
      setKpiAtivo(null);
      setFiltros(base);
    } else {
      setKpiAtivo(chave);
      setFiltros({ ...base, ...parciais });
    }
    setPagina(0);
  }

  function limpar() {
    setFiltros(FILTROS_VAZIOS);
    setBusca('');
    setKpiAtivo(null);
    setPagina(0);
  }

  const temFiltro =
    JSON.stringify({ ...filtros, q: '' }) !== JSON.stringify({ ...FILTROS_VAZIOS, q: '' })
    || Boolean(filtros.q);

  const totalPaginas = Math.max(1, Math.ceil(dados.total / POR_PAGINA));

  return (
    <div className="space-y-6">
      <PageHeader
        title="Contas"
        subtitle="Empresas-cliente da operação"
        actions={
          <Button icon={Plus} onClick={() => setNovaAberta(true)}>Nova conta</Button>
        }
      />

      {erro && <AlertMessage tipo="erro">{erro}</AlertMessage>}

      {/* KPIs clicáveis: cada um aplica o filtro que o compõe. */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
        <KpiBotao
          ativo={kpiAtivo === 'ativas'}
          onClick={() => alternarKpi('ativas', { ativo: 'true' })}
        >
          <KpiCard
            label="Contas ativas"
            value={resumo?.ativas ?? '—'}
            hint={resumo ? `${resumo.total} no total` : undefined}
            icon={Building2}
            tone="blue"
          />
        </KpiBotao>

        <KpiBotao
          ativo={kpiAtivo === 'sem-oportunidade'}
          onClick={() => alternarKpi('sem-oportunidade', { sem_oportunidade_ativa: true })}
        >
          <KpiCard
            label="Sem oportunidade aberta"
            value={resumo?.sem_oportunidade_ativa ?? '—'}
            hint="carteira parada"
            icon={CircleSlash}
            tone="amber"
          />
        </KpiBotao>

        <KpiBotao
          ativo={kpiAtivo === 'finders'}
          onClick={() => alternarKpi('finders', { eh_finder: 'true' })}
        >
          <KpiCard
            label="Parceiros indicadores"
            value={resumo?.finders ?? '—'}
            hint="finders"
            icon={Handshake}
            tone="emerald"
          />
        </KpiBotao>

        <KpiBotao
          ativo={kpiAtivo === 'sem-vertical'}
          onClick={() => alternarKpi('sem-vertical', { sem_vertical: true })}
        >
          <KpiCard
            label="Sem vertical"
            value={resumo?.sem_vertical ?? '—'}
            hint="cadastro incompleto"
            icon={Layers}
            tone="violet"
          />
        </KpiBotao>
      </div>

      <Card padding="none">
        <CardHeader
          title={`${dados.total} conta${dados.total === 1 ? '' : 's'}`}
          hint={temFiltro ? 'resultado filtrado' : undefined}
          right={
            temFiltro ? (
              <Button size="sm" variant="ghost" icon={X} onClick={limpar}>
                Limpar filtros
              </Button>
            ) : null
          }
          className="px-5 pt-5"
        />

        <div className="px-5 py-4 grid grid-cols-1 md:grid-cols-4 gap-3">
          <Input
            label="Buscar"
            icon={Search}
            placeholder="Razão social, fantasia ou CNPJ"
            value={busca}
            onChange={(e) => setBusca(e.target.value)}
            className="md:col-span-2"
          />
          <Select
            label="Vertical"
            value={filtros.vertical_id}
            onChange={(e) => aplicar({ vertical_id: e.target.value })}
          >
            <option value="">Todas</option>
            {verticais.map((v) => <option key={v.id} value={v.id}>{v.nome}</option>)}
          </Select>
          <Select
            label="UF"
            value={filtros.uf}
            onChange={(e) => aplicar({ uf: e.target.value })}
          >
            <option value="">Todas</option>
            {UFS.map((uf) => <option key={uf} value={uf}>{uf}</option>)}
          </Select>
        </div>

        {carregando || abrindo ? (
          <p className="px-5 py-10 text-center text-sm text-hipo-slate">Carregando…</p>
        ) : dados.itens.length === 0 ? (
          <Empty
            title={temFiltro ? 'Nenhuma conta com esses filtros' : 'Nenhuma conta cadastrada'}
            description={
              temFiltro
                ? 'Ajuste os filtros ou limpe a busca.'
                : 'Cadastre a primeira empresa-cliente para começar.'
            }
            icon={Building2}
            action={
              temFiltro ? (
                <Button variant="secondary" onClick={limpar}>Limpar filtros</Button>
              ) : (
                <Button icon={Plus} onClick={() => setNovaAberta(true)}>Nova conta</Button>
              )
            }
          />
        ) : (
          <>
            <Table>
              <thead>
                <tr>
                  <Th>Razão social</Th>
                  <Th>CNPJ</Th>
                  <Th>Vertical</Th>
                  <Th>Cidade/UF</Th>
                  <Th>Vendedor</Th>
                  <Th align="right">Oport. ativas</Th>
                  <Th>Situação</Th>
                </tr>
              </thead>
              <tbody>
                {dados.itens.map((c) => (
                  <Tr key={c.id} onClick={() => abrirConta(c.id)}>
                    <Td>
                      <div className="font-medium text-hipo-ink">{c.razao_social}</div>
                      {c.nome_fantasia && (
                        <div className="text-xs text-hipo-slate">{c.nome_fantasia}</div>
                      )}
                    </Td>
                    <Td className="font-mono text-sm">{c.cnpj_formatado}</Td>
                    <Td>{c.vertical_nome || <span className="text-hipo-muted">—</span>}</Td>
                    <Td>
                      {c.cidade ? `${c.cidade}${c.uf ? `/${c.uf}` : ''}`
                        : <span className="text-hipo-muted">—</span>}
                    </Td>
                    <Td>
                      {c.vendedores.length > 0
                        ? c.vendedores.join(', ')
                        : <span className="text-hipo-muted">—</span>}
                    </Td>
                    <Td align="right">{c.qtd_oportunidades_ativas}</Td>
                    <Td>
                      <div className="flex gap-1.5">
                        {c.eh_finder && <Badge tone="info">Finder</Badge>}
                        <Badge tone={c.ativo ? 'success' : 'neutral'}>
                          {c.ativo ? 'Ativa' : 'Inativa'}
                        </Badge>
                      </div>
                    </Td>
                  </Tr>
                ))}
              </tbody>
            </Table>

            {totalPaginas > 1 && (
              <div className="flex items-center justify-between px-5 py-4 border-t border-hipo-border">
                <span className="text-sm text-hipo-slate">
                  Página {pagina + 1} de {totalPaginas}
                </span>
                <div className="flex gap-2">
                  <Button
                    size="sm"
                    variant="secondary"
                    disabled={pagina === 0}
                    onClick={() => setPagina((p) => p - 1)}
                  >
                    Anterior
                  </Button>
                  <Button
                    size="sm"
                    variant="secondary"
                    disabled={pagina + 1 >= totalPaginas}
                    onClick={() => setPagina((p) => p + 1)}
                  >
                    Próxima
                  </Button>
                </div>
              </div>
            )}
          </>
        )}
      </Card>

      <FormNovaConta
        aberto={novaAberta}
        verticais={verticais}
        onFechar={() => setNovaAberta(false)}
        onCriada={(conta) => { setNovaAberta(false); setDetalhe(conta); carregar(); }}
        onAbrirExistente={(id) => { setNovaAberta(false); abrirConta(id); }}
      />

      <Modal
        aberto={Boolean(detalhe)}
        onFechar={() => { setDetalhe(null); setAcaoSalvar(null); }}
        titulo={detalhe?.razao_social}
        subtitulo={detalhe ? `CNPJ ${detalhe.cnpj_formatado}` : undefined}
        size="full"
        bodySemPadding
        acoes={
          // `acoes`, não `footer`: as saídas da tela ficam na linha do
          // título, ao lado do X. Aqui é o PAI quem monta os botões porque é
          // ele quem tem o estado do salvamento, que chega do ContaDetalhe
          // pelo canal registrarSalvar.
          <div className="flex items-center gap-2" aria-label="Ações da conta">
            <span className="text-xs text-hipo-slate mr-1">
              {acaoSalvar?.sujo ? 'Alterações não salvas' : 'Tudo salvo'}
            </span>
            <Button size="sm" variant="ghost"
              onClick={() => { setDetalhe(null); setAcaoSalvar(null); }}>
              Fechar
            </Button>
            <Button
              size="sm"
              onClick={() => acaoSalvar?.salvar()}
              disabled={!acaoSalvar?.sujo}
              loading={acaoSalvar?.salvando}
            >
              Salvar
            </Button>
          </div>
        }
      >
        {detalhe && (
          <ContaDetalhe
            conta={detalhe}
            verticais={verticais}
            onCriarVertical={criarVertical}
            onRecarregar={recarregarDetalhe}
            onSalvo={aoSalvarConta}
            registrarSalvar={setAcaoSalvar}
          />
        )}
      </Modal>
    </div>
  );
}
