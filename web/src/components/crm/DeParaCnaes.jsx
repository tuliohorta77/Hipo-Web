// web/src/components/crm/DeParaCnaes.jsx
//
// De-para CNAE -> vertical (e grau de risco da NR-4).
//
// POR QUE ESTA TELA EXISTE
//
// Mapear o CNAE dentro de cada conta resolve uma conta por vez. Com 1.751
// contas e algumas centenas de CNAEs distintos, isso nunca termina. Aqui a
// pergunta é outra: "qual código classifica mais contas de uma vez?" — e a
// lista já vem ordenada por isso.
//
// Decisões desta tela:
//
//   * A LISTA JÁ VEM CLASSIFICADA (015). Todo CNAE nasce com a vertical
//     derivada da seção da CNAE 2.0 — a hierarquia oficial do IBGE. O
//     trabalho aqui deixou de ser "preencher do zero" e passou a ser
//     CONFERIR: a linha mostra a sugestão, e quem discorda troca.
//
//   * ORDENADA POR TRABALHO, não por código. O primeiro da lista é o CNAE
//     com mais contas ESPERANDO vertical. Ordem alfabética aqui seria uma
//     tabela; ordem por impacto é uma fila.
//
//   * MAPEAR APLICA NAS CONTAS QUE JÁ EXISTEM. É o ponto inteiro: um clique
//     classifica as 40 contas daquele código. Só as que estão SEM vertical —
//     conta classificada por gente nunca é tocada, que é a mesma regra do
//     enriquecimento.
//
//   * DASHBOARD OPERACIONAL (diretriz pétrea 2): os números do topo não são
//     decoração. "Contas esperando" é o tamanho do problema, e ele cai a
//     cada linha resolvida, na mesma tela, sem recarregar.
//
//   * REMAPEAR É DE GESTÃO. O backend recusa com 403 para os demais; aqui a
//     linha já mapeada nasce em modo leitura para quem não é gestão, com o
//     motivo à vista, em vez de deixar tentar e falhar.

import { useCallback, useEffect, useMemo, useState } from 'react';
import { Tag, Search, Check, ShieldAlert, RefreshCw } from 'lucide-react';

import api, { getUser } from '../../api';
import Button from '../ui/Button';
import Badge from '../ui/Badge';
import Empty from '../ui/Empty';
import AlertMessage from '../ui/AlertMessage';
import Table, { Th, Tr, Td } from '../ui/Table';
import Input, { Select } from '../ui/Input';

const TOM_RISCO = { 1: 'neutral', 2: 'info', 3: 'warning', 4: 'danger' };

function mensagemDeErro(err, padrao) {
  const d = err?.response?.data?.detail;
  if (typeof d === 'string') return d;
  if (Array.isArray(d) && d[0]?.msg) return d[0].msg;
  if (d?.mensagem) return d.mensagem;
  return padrao;
}

function Numero({ label, valor, tom = 'ink' }) {
  const cor = tom === 'alerta' ? 'text-hipo-warning' : 'text-hipo-ink';
  return (
    <div>
      <p className="text-xs text-hipo-slate">{label}</p>
      <p className={`text-2xl font-semibold ${cor}`}>{valor ?? '—'}</p>
    </div>
  );
}

// ── Uma linha do de-para ─────────────────────────────────────────────

function LinhaCnae({ cnae, verticais, ehGestao, onSalvo, onCriarVertical }) {
  const [verticalId, setVerticalId] = useState(
    cnae.vertical_id ? String(cnae.vertical_id) : ''
  );
  const [grau, setGrau] = useState(
    cnae.grau_risco ? String(cnae.grau_risco) : ''
  );
  const [salvando, setSalvando] = useState(false);
  const [erro, setErro] = useState(null);

  // 'humano' = alguém decidiu; 'derivado' = veio da seção da CNAE 2.0.
  // Só o primeiro é de gestão: corrigir uma sugestão é trabalho de quem
  // está com a conta na frente.
  const decididoPorGente = cnae.mapeamento_origem === 'humano';
  const sugerido = cnae.mapeamento_origem === 'derivado';
  const bloqueado = decididoPorGente && !ehGestao;

  const mudou =
    verticalId !== (cnae.vertical_id ? String(cnae.vertical_id) : '')
    || grau !== (cnae.grau_risco ? String(cnae.grau_risco) : '');

  async function salvar() {
    setSalvando(true);
    setErro(null);
    try {
      const { data } = await api.patch(
        `/crm/enriquecimento/cnaes/${cnae.codigo}`,
        {
          vertical_id: verticalId ? Number(verticalId) : null,
          grau_risco: grau ? Number(grau) : null,
          aplicar_em_contas: true,
        },
      );
      // A confirmação sobe para o topo da tela, e não fica nesta linha, por
      // um motivo simples: com o filtro "só os não classificados" ligado, a
      // linha SOME da lista assim que é classificada. Mensagem presa a ela
      // desapareceria junto com o próprio resultado.
      onSalvo(data);
    } catch (err) {
      setErro(mensagemDeErro(err, 'Não foi possível mapear este CNAE.'));
    } finally {
      setSalvando(false);
    }
  }

  return (
    <>
      <Tr>
        <Td className="font-mono text-sm align-top">{cnae.codigo}</Td>
        <Td className="align-top">
          <div className="text-hipo-ink">{cnae.descricao}</div>
          {(decididoPorGente || sugerido) && (
            <div className="mt-1 flex flex-wrap items-center gap-1.5">
              <Badge tone={sugerido ? 'info' : 'success'}>
                {sugerido ? <Tag size={12} /> : <Check size={12} />}
                {cnae.vertical_nome || 'sem vertical'}
                {sugerido && ' (sugerido)'}
              </Badge>
              {cnae.grau_risco && (
                <Badge tone={TOM_RISCO[cnae.grau_risco] || 'neutral'}>
                  <ShieldAlert size={12} />
                  grau {cnae.grau_risco}
                </Badge>
              )}
            </div>
          )}
        </Td>
        <Td align="right" className="align-top">
          <div className="text-hipo-ink">{cnae.qtd_contas}</div>
          {cnae.qtd_contas_sem_vertical > 0 && (
            <div className="text-xs text-hipo-warning">
              {cnae.qtd_contas_sem_vertical} sem vertical
            </div>
          )}
        </Td>
        <Td className="align-top">
          {bloqueado ? (
            <span className="text-xs text-hipo-muted">
              definido por alguém — só gestão altera
            </span>
          ) : (
            <Select
              label=""
              aria-label={`Vertical do CNAE ${cnae.codigo}`}
              value={verticalId}
              onChange={(e) => setVerticalId(e.target.value)}
            >
              <option value="">— sem vertical —</option>
              {verticais.map((v) => (
                <option key={v.id} value={v.id}>{v.nome}</option>
              ))}
            </Select>
          )}
        </Td>
        <Td className="align-top">
          {!bloqueado && (
            <Select
              label=""
              aria-label={`Grau de risco do CNAE ${cnae.codigo}`}
              value={grau}
              onChange={(e) => setGrau(e.target.value)}
            >
              <option value="">—</option>
              <option value="1">1</option>
              <option value="2">2</option>
              <option value="3">3</option>
              <option value="4">4</option>
            </Select>
          )}
        </Td>
        <Td align="right" className="align-top">
          {!bloqueado && (
            <Button
              size="sm"
              variant={mudou ? 'primary' : 'secondary'}
              // Confirmar uma sugestão sem mudar nada é uma ação de
              // verdade: marca o CNAE como decidido por gente e tira ele
              // da fila. Por isso o botão não exige alteração quando a
              // linha é apenas sugerida.
              disabled={!mudou && !sugerido}
              loading={salvando}
              onClick={salvar}
            >
              {/* "Confirmar" só faz sentido quando existe uma sugestão na
                  frente para concordar. CNAE sem nada sugerido — o caso
                  legado, anterior à 015 — continua sendo "Aplicar", que é
                  o que o botão realmente faz ali. */}
              {sugerido && !mudou ? 'Confirmar' : 'Aplicar'}
            </Button>
          )}
        </Td>
      </Tr>

      {erro && (
        <tr>
          <td colSpan={6} className="px-5 pb-3 bg-hipo-bg/40">
            <AlertMessage tipo="erro">{erro}</AlertMessage>
          </td>
        </tr>
      )}
    </>
  );
}

// ── Tela ─────────────────────────────────────────────────────────────

export default function DeParaCnaes({ verticais, onCriarVertical, onMudou }) {
  const [cnaes, setCnaes] = useState(null);
  const [resumo, setResumo] = useState(null);
  const [busca, setBusca] = useState('');
  const [soNaoMapeados, setSoNaoMapeados] = useState(true);
  const [erro, setErro] = useState(null);
  const [carregando, setCarregando] = useState(true);
  const [novaVertical, setNovaVertical] = useState('');
  const [criando, setCriando] = useState(false);
  const [feito, setFeito] = useState(null);

  const ehGestao = useMemo(
    () => ['Franqueado', 'ADM'].includes(getUser()?.cargo),
    []
  );

  const carregar = useCallback(async () => {
    setCarregando(true);
    setErro(null);
    try {
      const params = { limit: 300 };
      if (soNaoMapeados) params.apenas_nao_mapeados = true;
      if (busca.trim()) params.q = busca.trim();
      const [lista, kpis] = await Promise.all([
        api.get('/crm/enriquecimento/cnaes', { params }),
        api.get('/crm/enriquecimento/resumo'),
      ]);
      setCnaes(lista.data);
      setResumo(kpis.data);
    } catch (err) {
      setErro(mensagemDeErro(err, 'Não foi possível carregar os CNAEs.'));
      setCnaes([]);
    } finally {
      setCarregando(false);
    }
  }, [soNaoMapeados, busca]);

  useEffect(() => { carregar(); }, [carregar]);

  async function criarVertical() {
    const nome = novaVertical.trim();
    if (!nome) return;
    setCriando(true);
    try {
      await onCriarVertical(nome);
      setNovaVertical('');
    } catch (err) {
      setErro(mensagemDeErro(err, 'Não foi possível criar a vertical.'));
    } finally {
      setCriando(false);
    }
  }

  // Recarrega a lista e os números depois de cada mapeamento: o "contas
  // esperando" do topo é o placar do trabalho, e placar que não se move não
  // serve para nada.
  async function aoSalvar(resultado) {
    setFeito(resultado);
    await carregar();
    onMudou?.();
  }

  return (
    <div className="flex flex-col h-full min-h-0">
      <div className="shrink-0 px-5 pt-4 pb-4 border-b border-hipo-border bg-hipo-bg/40 space-y-4">
        {erro && <AlertMessage tipo="erro">{erro}</AlertMessage>}

        {feito && (
          <AlertMessage tipo="ok">
            {feito.contas_atualizadas > 0
              ? `${feito.codigo}: ${feito.contas_atualizadas} conta(s) classificada(s) como ${feito.vertical_nome}.`
              : `${feito.codigo} classificado. Nenhuma conta sem vertical usava este CNAE.`}
          </AlertMessage>
        )}

        <div className="flex flex-wrap gap-8">
          <Numero label="CNAEs conhecidos" valor={resumo?.cnaes_conhecidos} />
          <Numero
            label="A conferir"
            valor={resumo?.cnaes_a_confirmar}
            tom="alerta"
          />
          <Numero
            label="Contas com vertical sugerida"
            valor={resumo?.contas_com_vertical_sugerida}
          />
          <Numero
            label="Contas sem vertical"
            valor={resumo?.contas_sem_vertical}
            tom="alerta"
          />
        </div>

        <p className="text-sm text-hipo-slate">
          A vertical já vem preenchida a partir da <strong>seção da CNAE
          2.0</strong>, a classificação oficial do IBGE. O que está aqui é
          sugestão: conferir ou trocar vale para <strong>todas</strong> as
          contas daquele código — as que já existem e as que vierem depois.
          Conta com vertical definida por alguém nunca é alterada.
        </p>

        <div className="grid grid-cols-1 md:grid-cols-12 gap-3 items-end">
          <div className="md:col-span-5">
            <Input
              label="Buscar"
              id="inp-buscar-cnae"
              icon={Search}
              placeholder="Código ou atividade"
              value={busca}
              onChange={(e) => setBusca(e.target.value)}
            />
          </div>
          <div className="md:col-span-3 flex items-center h-10">
            <label className="flex items-center gap-2 text-sm text-hipo-ink">
              <input
                type="checkbox"
                checked={soNaoMapeados}
                onChange={(e) => setSoNaoMapeados(e.target.checked)}
                className="rounded border-hipo-border"
              />
              Só os que faltam conferir
            </label>
          </div>
          <div className="md:col-span-3">
            <Input
              label="Criar vertical"
              id="inp-nova-vertical-depara"
              placeholder="nome da nova"
              value={novaVertical}
              onChange={(e) => setNovaVertical(e.target.value)}
            />
          </div>
          <div className="md:col-span-1">
            <Button
              variant="secondary"
              loading={criando}
              disabled={!novaVertical.trim()}
              onClick={criarVertical}
            >
              Criar
            </Button>
          </div>
        </div>
      </div>

      <div className="flex-1 min-h-0 overflow-y-auto">
        {carregando ? (
          <p className="px-5 py-10 text-center text-sm text-hipo-slate">Carregando…</p>
        ) : cnaes.length === 0 ? (
          <Empty
            title={
              soNaoMapeados
                ? 'Nenhum CNAE esperando conferência'
                : 'Nenhum CNAE encontrado'
            }
            description={
              soNaoMapeados
                ? 'Todos os CNAEs conhecidos já passaram por alguém.'
                : 'Os CNAEs aparecem aqui conforme as contas são consultadas por CNPJ.'
            }
            icon={Tag}
            action={
              soNaoMapeados ? (
                <Button
                  variant="secondary"
                  icon={RefreshCw}
                  onClick={() => setSoNaoMapeados(false)}
                >
                  Ver todos
                </Button>
              ) : undefined
            }
          />
        ) : (
          <Table>
            <thead>
              <tr>
                <Th>CNAE</Th>
                <Th>Atividade</Th>
                <Th align="right">Contas</Th>
                <Th>Vertical</Th>
                <Th>Risco</Th>
                <Th align="right">Ação</Th>
              </tr>
            </thead>
            <tbody>
              {cnaes.map((c) => (
                <LinhaCnae
                  key={c.codigo}
                  cnae={c}
                  verticais={verticais}
                  ehGestao={ehGestao}
                  onSalvo={aoSalvar}
                  onCriarVertical={onCriarVertical}
                />
              ))}
            </tbody>
          </Table>
        )}
      </div>
    </div>
  );
}
