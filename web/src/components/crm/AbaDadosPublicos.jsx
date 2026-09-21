// web/src/components/crm/AbaDadosPublicos.jsx
//
// Aba "Dados públicos" da visão 360 da conta: o que a consulta por CNPJ
// trouxe, e o que dá para FAZER com isso aqui mesmo.
//
// Decisões desta tela:
//
//   * ABRIR A ABA NÃO CONSULTA A FONTE. O que ela desenha já está no banco
//     (veio do GET /crm/contas/{id}) e os sócios vêm de uma leitura local.
//     Ir à fonte é sempre um clique explícito — em fonte paga, abrir uma
//     aba não pode custar crédito.
//
//   * DASHBOARD OPERACIONAL, e não painel de leitura (diretriz pétrea 2).
//     Cada coisa exibida leva a uma ação daqui: o CNAE sem classificação
//     traz o formulário de mapeamento; o sócio traz "onde mais ele
//     aparece"; a divergência entre o cadastro e a Receita traz o botão de
//     substituir.
//
//   * O MAPEAMENTO DO CNAE FICA ONDE O CNAE APARECE. Quem está olhando a
//     conta é quem sabe a que vertical ela pertence. Mandar essa pessoa
//     para uma tela de configuração significa que ninguém vai mapear.
//
//   * NÚMERO ESTIMADO É MARCADO COMO ESTIMADO. A fonte paga devolve
//     quadro de pessoal de base anual defasada; o número que vale para
//     precificar é o que o cliente informa. A tela diz qual é qual em vez
//     de exibir os dois como se fossem a mesma coisa.

import { useCallback, useEffect, useState } from 'react';
import {
  Landmark, RefreshCw, Users2, Building2, ShieldAlert, Search, Tag,
} from 'lucide-react';

import api from '../../api';
import Button from '../ui/Button';
import Badge from '../ui/Badge';
import Empty from '../ui/Empty';
import AlertMessage from '../ui/AlertMessage';
import Table, { Th, Tr, Td } from '../ui/Table';
import Input, { Select } from '../ui/Input';

// Rótulo dos campos nas listas de "aplicado" e "mantido". Sem isto o
// usuário leria `nao_prospectar_motivo` cru na tela.
const ROTULO_CAMPO = {
  razao_social: 'Razão social',
  nome_fantasia: 'Nome fantasia',
  cnae_codigo: 'CNAE',
  vertical_id: 'Vertical',
  porte: 'Porte',
  situacao_cadastral: 'Situação cadastral',
  data_abertura: 'Data de abertura',
  capital_social: 'Capital social',
  cep: 'CEP',
  logradouro: 'Logradouro',
  numero: 'Número',
  complemento: 'Complemento',
  bairro: 'Bairro',
  cidade: 'Cidade',
  uf: 'UF',
  telefone: 'Telefone',
  telefone_2: 'Telefone 2',
  email: 'E-mail',
  num_funcionarios: 'Nº de funcionários',
};

// Quadro I da NR-4: 1 a 4. Quanto maior, mais exigente o dimensionamento
// de SESMT e o acompanhamento — logo, mais serviço vendido.
const TOM_RISCO = { 1: 'neutral', 2: 'info', 3: 'warning', 4: 'danger' };

function rotulo(campo) {
  return ROTULO_CAMPO[campo] || campo;
}

function mensagemDeErro(err, padrao) {
  const d = err?.response?.data?.detail;
  if (typeof d === 'string') return d;
  if (Array.isArray(d) && d[0]?.msg) return d[0].msg;
  if (d?.mensagem) return d.mensagem;
  return padrao;
}

function formatarData(iso) {
  if (!iso) return '—';
  const d = new Date(iso);
  return Number.isNaN(d.getTime()) ? '—' : d.toLocaleDateString('pt-BR');
}

function formatarDataHora(iso) {
  if (!iso) return '—';
  const d = new Date(iso);
  return Number.isNaN(d.getTime())
    ? '—'
    : d.toLocaleString('pt-BR', {
      day: '2-digit', month: '2-digit', year: 'numeric',
      hour: '2-digit', minute: '2-digit',
    });
}

function formatarMoeda(v) {
  if (v === null || v === undefined || v === '') return '—';
  return Number(v).toLocaleString('pt-BR', { style: 'currency', currency: 'BRL' });
}

function Dado({ label, children, hint }) {
  return (
    <div>
      <p className="text-xs text-hipo-slate">{label}</p>
      <div className="text-sm text-hipo-ink font-medium">{children ?? '—'}</div>
      {hint && <p className="text-xs text-hipo-muted mt-0.5">{hint}</p>}
    </div>
  );
}

// ── Mapeamento do CNAE ───────────────────────────────────────────────

// Dois modos, e a diferença importa:
//
//   * SEM CLASSIFICAÇÃO — ninguém passou por este CNAE. O bloco pede a
//     decisão, e o botão só habilita quando há o que gravar.
//
//   * SUGERIDO (015) — a vertical veio da seção da CNAE 2.0. O select já
//     abre com ela escolhida, e confirmar sem mudar nada é ação válida:
//     marca o CNAE como decidido por gente e tira ele da fila do de-para.
//
// Antes da 015 o bloco só aparecia quando `vertical_id` era nulo. Como
// agora todo CNAE nasce com vertical, essa condição passou a ser sempre
// falsa — e no dia da carga o bloco sumiu de todas as contas de uma vez.
// É por isso que quem manda aqui é a PROCEDÊNCIA, não a presença.
function MapearCnae({ conta, verticais, onCriarVertical, onMapeado }) {
  const sugerido = conta.cnae_mapeamento_origem === 'derivado';
  const sugestaoId = sugerido && conta.cnae_vertical_id
    ? String(conta.cnae_vertical_id)
    : '';

  const [verticalId, setVerticalId] = useState(sugestaoId);
  const [grau, setGrau] = useState(
    conta.cnae_grau_risco ? String(conta.cnae_grau_risco) : ''
  );
  const [novaVertical, setNovaVertical] = useState('');
  const [salvando, setSalvando] = useState(false);
  const [erro, setErro] = useState(null);

  const mudou = verticalId !== sugestaoId
    || grau !== (conta.cnae_grau_risco ? String(conta.cnae_grau_risco) : '')
    || Boolean(novaVertical.trim());

  async function salvar() {
    if (!verticalId && !grau && !novaVertical.trim()) {
      setErro('Escolha a vertical, o grau de risco, ou os dois.');
      return;
    }
    setSalvando(true);
    setErro(null);
    try {
      let idVertical = verticalId ? Number(verticalId) : null;
      const nome = novaVertical.trim();
      if (!idVertical && nome) {
        const criada = await onCriarVertical(nome);
        idVertical = criada.id;
      }
      const { data } = await api.patch(
        `/crm/enriquecimento/cnaes/${conta.cnae_codigo}`,
        {
          vertical_id: idVertical,
          grau_risco: grau ? Number(grau) : null,
          // Sem isto, classificar aqui só valeria para consultas futuras —
          // e o texto logo acima promete que vale para todas as contas do
          // código. Promessa na tela e efeito no banco têm que bater.
          aplicar_em_contas: true,
        },
      );
      await onMapeado(data);
    } catch (err) {
      setErro(mensagemDeErro(err, 'Não foi possível mapear o CNAE.'));
    } finally {
      setSalvando(false);
    }
  }

  return (
    <div
      className={
        'rounded-lg border p-4 space-y-3 '
        + (sugerido
          ? 'border-hipo-blueSoft bg-hipo-blueSoft/40'
          : 'border-hipo-warningBorder bg-hipo-warningSoft')
      }
    >
      <div className="flex items-start gap-2">
        <Tag
          size={16}
          className={
            'shrink-0 mt-0.5 '
            + (sugerido ? 'text-hipo-blue' : 'text-hipo-warning')
          }
        />
        <div className="text-sm text-hipo-ink">
          {sugerido ? (
            <>
              <strong>
                Vertical sugerida
                {conta.cnae_vertical_nome ? `: ${conta.cnae_vertical_nome}` : ''}
                .
              </strong>
              <p className="text-hipo-slate">
                Veio da seção da CNAE 2.0, a classificação oficial do IBGE —
                ninguém conferiu ainda. Confirmar ou trocar vale para{' '}
                <em>todas</em> as contas com o CNAE{' '}
                <span className="font-mono">{conta.cnae_codigo}</span>.
              </p>
            </>
          ) : (
            <>
              <strong>Este CNAE ainda não foi classificado.</strong>
              <p className="text-hipo-slate">
                Classificar aqui vale para <em>todas</em> as contas com o CNAE{' '}
                <span className="font-mono">{conta.cnae_codigo}</span> —
                inclusive as que forem cadastradas depois.
              </p>
            </>
          )}
        </div>
      </div>

      {erro && <AlertMessage tipo="erro">{erro}</AlertMessage>}

      <div className="grid grid-cols-1 md:grid-cols-4 gap-3 items-end">
        <Select
          label="Vertical"
          value={verticalId}
          onChange={(e) => setVerticalId(e.target.value)}
        >
          <option value="">— escolher —</option>
          {verticais.map((v) => (
            <option key={v.id} value={v.id}>{v.nome}</option>
          ))}
        </Select>
        <Input
          label="ou criar vertical"
          id="inp-nova-vertical-cnae"
          placeholder="nome da nova"
          value={novaVertical}
          onChange={(e) => setNovaVertical(e.target.value)}
        />
        <Select
          label="Grau de risco (NR-4)"
          value={grau}
          onChange={(e) => setGrau(e.target.value)}
        >
          <option value="">— não sei —</option>
          <option value="1">1</option>
          <option value="2">2</option>
          <option value="3">3</option>
          <option value="4">4</option>
        </Select>
        <Button
          onClick={salvar}
          loading={salvando}
          variant={sugerido && !mudou ? 'secondary' : 'primary'}
        >
          {sugerido && !mudou ? 'Confirmar vertical' : 'Classificar CNAE'}
        </Button>
      </div>
    </div>
  );
}

// ── Sócios ───────────────────────────────────────────────────────────

function LinhaSocio({ socio, contaId }) {
  const [empresas, setEmpresas] = useState(null);
  const [avisos, setAvisos] = useState([]);
  const [buscando, setBuscando] = useState(false);
  const [erro, setErro] = useState(null);

  async function buscarEmpresas() {
    setBuscando(true);
    setErro(null);
    try {
      const { data } = await api.get('/crm/enriquecimento/socios/empresas', {
        params: {
          nome: socio.nome,
          documento: socio.documento_mascarado || undefined,
          excluir_conta_id: contaId,
        },
      });
      setEmpresas(data.empresas);
      setAvisos(data.avisos || []);
    } catch (err) {
      setErro(mensagemDeErro(err, 'Não foi possível buscar as empresas do sócio.'));
    } finally {
      setBuscando(false);
    }
  }

  return (
    <>
      <Tr>
        <Td>
          <div className="font-medium text-hipo-ink">{socio.nome}</div>
          {socio.documento_mascarado && (
            <div className="text-xs text-hipo-muted font-mono">
              {socio.documento_mascarado}
            </div>
          )}
        </Td>
        <Td>{socio.qualificacao || <span className="text-hipo-muted">—</span>}</Td>
        <Td>{socio.faixa_etaria || <span className="text-hipo-muted">—</span>}</Td>
        <Td>{formatarData(socio.entrada_em)}</Td>
        <Td align="right">
          <Button
            size="sm"
            variant="ghost"
            icon={Search}
            loading={buscando}
            onClick={buscarEmpresas}
          >
            Outras empresas
          </Button>
        </Td>
      </Tr>

      {(empresas !== null || erro) && (
        <tr>
          <td colSpan={5} className="px-4 pb-4 bg-hipo-bg/40">
            {erro && <AlertMessage tipo="erro">{erro}</AlertMessage>}
            {empresas !== null && empresas.length === 0 && (
              <p className="text-sm text-hipo-slate py-2">
                Nenhuma outra empresa deste sócio no HIPO.
              </p>
            )}
            {empresas !== null && empresas.length > 0 && (
              <ul className="py-2 space-y-1.5">
                {empresas.map((e, i) => (
                  <li
                    key={`${e.conta_id || e.razao_social}-${i}`}
                    className="flex flex-wrap items-center gap-2 text-sm"
                  >
                    <Building2 size={14} className="text-hipo-muted" />
                    <span className="text-hipo-ink">{e.razao_social}</span>
                    {e.cnpj_formatado && (
                      <span className="font-mono text-xs text-hipo-muted">
                        {e.cnpj_formatado}
                      </span>
                    )}
                    {e.qualificacao && (
                      <span className="text-xs text-hipo-slate">{e.qualificacao}</span>
                    )}
                    <Badge tone={e.confianca === 'alta' ? 'success' : 'warning'}>
                      {e.confianca === 'alta'
                        ? 'nome e documento batem'
                        : 'só o nome bate'}
                    </Badge>
                    {e.externa && <Badge tone="info">fora do HIPO</Badge>}
                  </li>
                ))}
              </ul>
            )}
            {avisos.map((a) => (
              <p key={a} className="text-xs text-hipo-muted">{a}</p>
            ))}
          </td>
        </tr>
      )}
    </>
  );
}

// ── Componente principal ─────────────────────────────────────────────

export default function AbaDadosPublicos({
  conta, verticais, onCriarVertical, onRecarregar,
}) {
  const [socios, setSocios] = useState(null);
  const [erro, setErro] = useState(null);
  const [buscando, setBuscando] = useState(false);
  const [resultado, setResultado] = useState(null);

  const carregarSocios = useCallback(async () => {
    try {
      const { data } = await api.get(
        `/crm/enriquecimento/contas/${conta.id}/socios`
      );
      setSocios(data);
    } catch (err) {
      setErro(mensagemDeErro(err, 'Não foi possível carregar o quadro societário.'));
      setSocios([]);
    }
  }, [conta.id]);

  useEffect(() => { carregarSocios(); }, [carregarSocios]);

  // `sobrescrever` só verdadeiro quando o usuário pede explicitamente, pelo
  // botão que aparece junto da divergência.
  async function consultar({ sobrescrever = false } = {}) {
    setBuscando(true);
    setErro(null);
    try {
      const { data } = await api.post(
        `/crm/enriquecimento/contas/${conta.id}/aplicar`,
        { forcar: true, sobrescrever },
      );
      setResultado(data);
      await carregarSocios();
      await onRecarregar?.();
    } catch (err) {
      setErro(mensagemDeErro(err, 'Não foi possível consultar os dados públicos.'));
    } finally {
      setBuscando(false);
    }
  }

  const nuncaConsultada = !conta.enriquecida_em;

  // O bloco aparece enquanto NINGUÉM decidiu este CNAE — seja porque está
  // vazio, seja porque a vertical é só uma sugestão da seção da CNAE 2.0.
  // Decisão humana ('humano') tira o bloco daqui: remapear vale para a
  // base inteira e é de gestão, na tela do de-para.
  //
  // Reparar que a condição olha a PROCEDÊNCIA e não a presença da
  // vertical: depois da 015 todo CNAE nasce classificado, então
  // `!vertical_id` seria sempre falso e o bloco nunca mais apareceria.
  const cnaeAConferir = Boolean(conta.cnae_codigo)
    && conta.cnae_mapeamento_origem !== 'humano';

  if (nuncaConsultada && socios !== null && socios.length === 0) {
    return (
      <div className="space-y-4">
        {erro && <AlertMessage tipo="erro">{erro}</AlertMessage>}
        <Empty
          title="Esta conta nunca foi consultada"
          description={
            'Buscar na Receita preenche endereço, CNAE, porte e quadro '
            + 'societário — sem tocar no que já estiver preenchido aqui.'
          }
          icon={Landmark}
          action={
            <Button icon={RefreshCw} loading={buscando} onClick={() => consultar()}>
              Buscar dados públicos
            </Button>
          }
        />
      </div>
    );
  }

  return (
    <div className="space-y-5">
      {erro && <AlertMessage tipo="erro">{erro}</AlertMessage>}

      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="text-xs text-hipo-slate">
          {conta.enriquecida_em ? (
            <>
              Última consulta em {formatarDataHora(conta.enriquecida_em)}
              {conta.enriquecida_fonte && ` · fonte: ${conta.enriquecida_fonte}`}
            </>
          ) : 'Nunca consultada.'}
        </div>
        <Button
          size="sm"
          variant="secondary"
          icon={RefreshCw}
          loading={buscando}
          onClick={() => consultar()}
        >
          Atualizar dados públicos
        </Button>
      </div>

      {conta.situacao_cadastral
        && !['ATIVA', 'Ativa'].includes(conta.situacao_cadastral) && (
        <AlertMessage tipo="aviso">
          <strong>Situação cadastral: {conta.situacao_cadastral}.</strong>{' '}
          Empresa fora de operação segundo a Receita — confira antes de
          prospectar.
        </AlertMessage>
      )}

      {resultado && (
        <div className="space-y-2">
          {Object.keys(resultado.aplicados || {}).length > 0 && (
            <AlertMessage tipo="ok">
              Preenchidos:{' '}
              {Object.keys(resultado.aplicados).map(rotulo).join(', ')}.
            </AlertMessage>
          )}
          {(resultado.mantidos || []).length > 0 && (
            <AlertMessage tipo="aviso">
              <div className="space-y-2">
                <p>
                  Estes campos já tinham valor e <strong>não</strong> foram
                  alterados:
                </p>
                <ul className="space-y-1">
                  {resultado.mantidos.map((m) => (
                    <li key={m.campo} className="text-sm">
                      <span className="font-medium">{rotulo(m.campo)}</span>:{' '}
                      aqui <span className="font-mono">{m.atual}</span> ·
                      na fonte <span className="font-mono">{m.sugerido}</span>
                      {m.motivo === 'número declarado pelo cliente' && (
                        <Badge tone="success" className="ml-2">
                          declarado pelo cliente
                        </Badge>
                      )}
                    </li>
                  ))}
                </ul>
                {resultado.mantidos.some(
                  (m) => m.motivo !== 'número declarado pelo cliente'
                ) && (
                  <Button
                    size="sm"
                    variant="secondary"
                    loading={buscando}
                    onClick={() => consultar({ sobrescrever: true })}
                  >
                    Usar os dados da fonte
                  </Button>
                )}
              </div>
            </AlertMessage>
          )}
          {(resultado.avisos || []).map((a) => (
            <p key={a} className="text-xs text-hipo-muted">{a}</p>
          ))}
        </div>
      )}

      {/* Identificação econômica */}
      <div className="rounded-lg border border-hipo-border p-4 space-y-4">
        <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
          <Dado label="CNAE principal">
            {conta.cnae_codigo ? (
              <span className="font-mono">{conta.cnae_codigo}</span>
            ) : null}
          </Dado>
          <div className="md:col-span-2">
            <Dado label="Atividade">{conta.cnae_descricao}</Dado>
          </div>
          <Dado label="Grau de risco (NR-4)">
            {conta.cnae_grau_risco ? (
              <Badge tone={TOM_RISCO[conta.cnae_grau_risco] || 'neutral'}>
                <ShieldAlert size={12} />
                grau {conta.cnae_grau_risco}
              </Badge>
            ) : null}
          </Dado>

          <Dado label="Porte">{conta.porte}</Dado>
          <Dado label="Situação cadastral">{conta.situacao_cadastral}</Dado>
          <Dado label="Abertura">{formatarData(conta.data_abertura)}</Dado>
          <Dado label="Capital social">{formatarMoeda(conta.capital_social)}</Dado>

          <Dado
            label="Nº de funcionários"
            hint={
              conta.num_funcionarios_origem === 'estimado'
                ? 'estimativa da fonte — confirme com o cliente antes de precificar'
                : conta.num_funcionarios_origem === 'declarado'
                  ? 'informado pelo cliente'
                  : undefined
            }
          >
            {conta.num_funcionarios ?? null}
            {conta.num_funcionarios_origem === 'estimado' && (
              <Badge tone="warning" className="ml-2">estimado</Badge>
            )}
          </Dado>
        </div>

        {cnaeAConferir && (
          <MapearCnae
            key={`${conta.cnae_codigo}:${conta.cnae_mapeamento_origem || ''}`}
            conta={conta}
            verticais={verticais}
            onCriarVertical={onCriarVertical}
            onMapeado={async () => { await onRecarregar?.(); }}
          />
        )}
      </div>

      {/* Quadro societário */}
      <div>
        <h3 className="text-sm font-semibold text-hipo-ink mb-2 flex items-center gap-2">
          <Users2 size={15} className="text-hipo-muted" />
          Quadro societário
        </h3>

        {socios === null ? (
          <p className="py-6 text-center text-sm text-hipo-slate">Carregando…</p>
        ) : socios.length === 0 ? (
          // A mensagem muda conforme JÁ houve consulta ou não. Depois de
          // consultar, "sem sócios" quase sempre significa empresário
          // individual ou MEI — esses não têm quadro societário na Receita,
          // e dizer só "sem sócios registrados" faria parecer defeito do
          // sistema num dado que simplesmente não existe.
          <Empty
            title={
              conta.enriquecida_em
                ? 'A Receita não tem quadro societário para este CNPJ'
                : 'Sem sócios registrados'
            }
            description={
              conta.enriquecida_em
                ? 'É o caso de empresário individual e MEI: a empresa é a própria pessoa, então não há sociedade a publicar. Para os demais tipos, o quadro vem na consulta.'
                : 'O quadro societário vem junto com a consulta por CNPJ.'
            }
            icon={Users2}
          />
        ) : (
          <div className="border border-hipo-border rounded-lg overflow-hidden">
            <Table>
              <thead>
                <tr>
                  <Th>Sócio</Th>
                  <Th>Qualificação</Th>
                  <Th>Faixa etária</Th>
                  <Th>Entrada</Th>
                  <Th align="right">Ações</Th>
                </tr>
              </thead>
              <tbody>
                {socios.map((s) => (
                  <LinhaSocio key={s.id} socio={s} contaId={conta.id} />
                ))}
              </tbody>
            </Table>
          </div>
        )}
      </div>
    </div>
  );
}
