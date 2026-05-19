// web/src/pages/Metas.jsx
import { useEffect, useMemo, useState } from 'react';
import { Save, Calendar, Target, Info, CheckCircle2 } from 'lucide-react';
import api, { getUser } from '../api';
import Card from '../components/ui/Card';
import PageHeader from '../components/ui/PageHeader';
import Button from '../components/ui/Button';
import Input, { Select } from '../components/ui/Input';
import AlertMessage from '../components/ui/AlertMessage';

const PILARES = [
  { codigo: 'RESULTADO',   label: 'Pilar Resultado',   pts: 60 },
  { codigo: 'GESTAO',      label: 'Pilar Gestão',      pts: 20 },
  { codigo: 'ENGAJAMENTO', label: 'Pilar Engajamento', pts: 20 },
];

function mesRefAtual() {
  const d = new Date();
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}`;
}

function nomeMes(ref) {
  const [y, m] = ref.split('-');
  const meses = [
    'jan', 'fev', 'mar', 'abr', 'mai', 'jun',
    'jul', 'ago', 'set', 'out', 'nov', 'dez',
  ];
  return `${meses[parseInt(m, 10) - 1]}/${y.slice(2)}`;
}

function gerarOpcoesMes() {
  const opts = [];
  const hoje = new Date();
  for (let delta = -6; delta <= 6; delta++) {
    const d = new Date(hoje.getFullYear(), hoje.getMonth() + delta, 1);
    const ref = `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}`;
    opts.push({ ref, label: nomeMes(ref) });
  }
  return opts;
}

// ─────────── Componentes auxiliares ───────────

function Section({ title, hint, children }) {
  return (
    <Card className="mb-4">
      <div className="mb-4">
        <h3 className="text-h2 text-hipo-ink">{title}</h3>
        {hint && <p className="text-sm text-hipo-slate mt-0.5">{hint}</p>}
      </div>
      {children}
    </Card>
  );
}

function IndicadorRow({ ind, valor, cluster, onChange, readOnly }) {
  const metaPorCluster = ind.meta_por_cluster?.[cluster];
  const placeholder = metaPorCluster ? `Auto: ${metaPorCluster}` : '';
  return (
    <div className="flex items-center gap-4 py-3 border-b border-hipo-border last:border-0">
      <div className="flex-1 min-w-0">
        <p className="text-sm font-medium text-hipo-ink">{ind.nome}</p>
        <p className="text-xs text-hipo-slate mt-0.5">
          {ind.pts} pts · {ind.meta_label}
          {metaPorCluster != null && (
            <span className="ml-2 text-hipo-blue font-medium">
              → {cluster}: {metaPorCluster}
            </span>
          )}
        </p>
      </div>
      <Input
        type="number"
        step="any"
        value={valor ?? ''}
        onChange={(e) => onChange(e.target.value)}
        placeholder={placeholder}
        disabled={readOnly}
        inputClassName="w-32 text-right"
        className="shrink-0"
      />
    </div>
  );
}

export default function Metas() {
  const user = getUser();
  const isAdm = (user?.cargo || '').toUpperCase() === 'ADM';

  const [mesRef, setMesRef] = useState(mesRefAtual());
  const [catalogo, setCatalogo] = useState({ clusters: [], indicadores: [] });
  const [meta, setMeta] = useState(null);
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [msg, setMsg] = useState(null);

  useEffect(() => {
    api.get('/metas/catalogo').then(({ data }) => setCatalogo(data));
  }, []);

  useEffect(() => {
    setLoading(true);
    setMsg(null);
    api
      .get(`/metas/${mesRef}`)
      .then(({ data }) => setMeta(data))
      .catch(() => setMeta(null))
      .finally(() => setLoading(false));
  }, [mesRef]);

  const indicadoresEditaveis = useMemo(
    () => catalogo.indicadores.filter((i) => i.meta_editavel),
    [catalogo]
  );

  const metasMap = useMemo(() => {
    const m = {};
    if (meta?.indicadores) {
      for (const ind of meta.indicadores) m[ind.codigo] = ind.meta_valor;
    }
    return m;
  }, [meta]);

  const big3 = useMemo(() => {
    const arr = (meta?.big3 || []).slice();
    while (arr.length < 3) {
      arr.push({ ordem: arr.length + 1, descricao: '', atingiu: false });
    }
    return arr.sort((a, b) => a.ordem - b.ordem);
  }, [meta]);

  const setCab = (key, value) => setMeta((prev) => ({ ...prev, [key]: value }));
  const setMetaInd = (codigo, value) => {
    setMeta((prev) => {
      const inds = (prev?.indicadores || []).filter((i) => i.codigo !== codigo);
      const novo = value === '' || value === null ? null : Number(value);
      if (novo !== null && !isNaN(novo))
        inds.push({ codigo, meta_valor: novo });
      return { ...prev, indicadores: inds };
    });
  };
  const setBig3Campo = (ordem, key, value) => {
    setMeta((prev) => {
      const arr = (prev?.big3 || []).slice();
      const idx = arr.findIndex((b) => b.ordem === ordem);
      if (idx === -1) {
        arr.push({ ordem, descricao: '', atingiu: false, [key]: value });
      } else {
        arr[idx] = { ...arr[idx], [key]: value };
      }
      return { ...prev, big3: arr.sort((a, b) => a.ordem - b.ordem) };
    });
  };

  async function salvar() {
    if (!isAdm) return;
    setSaving(true);
    setMsg(null);
    try {
      const big3Final = [1, 2, 3].map((ord) => {
        const existente = (meta.big3 || []).find((b) => b.ordem === ord);
        return existente || { ordem: ord, descricao: '', atingiu: false };
      });
      const payload = {
        mes_ref: mesRef,
        cluster_unidade: meta.cluster_unidade || 'BASE',
        dias_uteis: Number(meta.dias_uteis) || 22,
        ecs_ativos_m3: Number(meta.ecs_ativos_m3) || 0,
        evs_ativos: Number(meta.evs_ativos) || 0,
        carteira_total_contadores: Number(meta.carteira_total_contadores) || 0,
        apps_ativos: Number(meta.apps_ativos) || 0,
        headcount_recomendado:
          meta.headcount_recomendado != null && meta.headcount_recomendado !== ''
            ? Number(meta.headcount_recomendado)
            : null,
        indicadores: (meta.indicadores || []).filter(
          (i) => i.meta_valor != null
        ),
        big3: big3Final,
      };
      await api.post(`/metas/${mesRef}`, payload);
      setMsg({ tipo: 'ok', texto: 'Metas salvas com sucesso.' });
      const { data } = await api.get(`/metas/${mesRef}`);
      setMeta(data);
    } catch (err) {
      setMsg({
        tipo: 'erro',
        texto: `Erro: ${err.response?.data?.detail || err.message}`,
      });
    } finally {
      setSaving(false);
    }
  }

  const opcoesMes = gerarOpcoesMes();

  return (
    <>
      <PageHeader
        title="Metas PEX"
        subtitle="Cadastro mensal de metas — configuração da unidade e indicadores variáveis."
        actions={
          <>
            <Select
              value={mesRef}
              onChange={(e) => setMesRef(e.target.value)}
              selectClassName="w-32"
            >
              {opcoesMes.map((o) => (
                <option key={o.ref} value={o.ref}>
                  {o.label}
                </option>
              ))}
            </Select>
            {isAdm && (
              <Button
                onClick={salvar}
                disabled={saving || loading || !meta}
                loading={saving}
                icon={!saving ? Save : undefined}
              >
                {saving ? 'Salvando...' : 'Salvar'}
              </Button>
            )}
          </>
        }
      />

      {!isAdm && (
        <AlertMessage tipo="aviso" className="mb-4">
          Apenas usuários ADM podem editar metas. Você está em modo somente
          leitura.
        </AlertMessage>
      )}

      {meta?.pre_populado && !meta.existente && (
        <AlertMessage tipo="info" className="mb-4">
          Mês ainda não cadastrado. Valores pré-populados a partir do último mês
          existente. Clique em <strong>Salvar</strong> para confirmar.
        </AlertMessage>
      )}

      {meta?.existente && meta?.atualizado_em && (
        <div className="mb-4 flex items-center gap-2 text-sm text-hipo-slate">
          <Calendar size={14} />
          Última atualização:{' '}
          {new Date(meta.atualizado_em).toLocaleString('pt-BR')}
        </div>
      )}

      {msg && (
        <AlertMessage tipo={msg.tipo} className="mb-4">
          {msg.texto}
        </AlertMessage>
      )}

      {loading ? (
        <Card>
          <div className="text-center py-10 text-sm text-hipo-slate">
            Carregando...
          </div>
        </Card>
      ) : (
        <>
          <Section
            title="Configuração da unidade"
            hint="Dados globais usados como denominador nos cálculos"
          >
            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
              <Select
                label="Cluster"
                value={meta?.cluster_unidade || 'BASE'}
                onChange={(e) => setCab('cluster_unidade', e.target.value)}
                disabled={!isAdm}
              >
                {(catalogo.clusters || []).map((c) => (
                  <option key={c} value={c}>
                    {c.replace('_', ' ')}
                  </option>
                ))}
              </Select>
              <Input
                label="Dias úteis"
                type="number"
                value={meta?.dias_uteis ?? ''}
                onChange={(e) => setCab('dias_uteis', e.target.value)}
                disabled={!isAdm}
              />
              <Input
                label="ECs ativos M3"
                type="number"
                value={meta?.ecs_ativos_m3 ?? ''}
                onChange={(e) => setCab('ecs_ativos_m3', e.target.value)}
                disabled={!isAdm}
              />
              <Input
                label="EVs ativos"
                type="number"
                value={meta?.evs_ativos ?? ''}
                onChange={(e) => setCab('evs_ativos', e.target.value)}
                disabled={!isAdm}
              />
              <Input
                label="Carteira contadores"
                type="number"
                value={meta?.carteira_total_contadores ?? ''}
                onChange={(e) =>
                  setCab('carteira_total_contadores', e.target.value)
                }
                disabled={!isAdm}
              />
              <Input
                label="Apps ativos (SoW)"
                type="number"
                value={meta?.apps_ativos ?? ''}
                onChange={(e) => setCab('apps_ativos', e.target.value)}
                disabled={!isAdm}
              />
              <Input
                label="Headcount alvo"
                type="number"
                value={meta?.headcount_recomendado ?? ''}
                onChange={(e) =>
                  setCab('headcount_recomendado', e.target.value)
                }
                disabled={!isAdm}
              />
            </div>
          </Section>

          {PILARES.map(({ codigo, label, pts }) => {
            const inds = indicadoresEditaveis.filter((i) => i.pilar === codigo);
            if (inds.length === 0 && codigo !== 'ENGAJAMENTO') return null;
            return (
              <Section
                key={codigo}
                title={label}
                hint={`${pts} pontos no total`}
              >
                {inds.length > 0 ? (
                  <div>
                    {inds.map((ind) => (
                      <IndicadorRow
                        key={ind.codigo}
                        ind={ind}
                        valor={metasMap[ind.codigo]}
                        cluster={meta?.cluster_unidade}
                        onChange={(v) => setMetaInd(ind.codigo, v)}
                        readOnly={!isAdm}
                      />
                    ))}
                  </div>
                ) : (
                  <p className="text-sm text-hipo-slate italic">
                    Sem metas numéricas editáveis neste pilar (todas
                    universais).
                  </p>
                )}

                {codigo === 'ENGAJAMENTO' && (
                  <div className="mt-6 pt-6 border-t border-hipo-border">
                    <div className="mb-3">
                      <p className="text-sm font-semibold text-hipo-ink">
                        Big 3 — Ações mensais
                      </p>
                      <p className="text-xs text-hipo-slate mt-0.5">
                        2 pts por ação atingida (máx 6 pts)
                      </p>
                    </div>
                    <div className="space-y-2">
                      {big3.map((acao) => (
                        <div
                          key={acao.ordem}
                          className="flex items-center gap-3"
                        >
                          <span className="text-xs font-semibold text-hipo-muted w-14 shrink-0">
                            Ação {acao.ordem}
                          </span>
                          <Input
                            type="text"
                            placeholder="Descrição da ação..."
                            value={acao.descricao || ''}
                            onChange={(e) =>
                              setBig3Campo(
                                acao.ordem,
                                'descricao',
                                e.target.value
                              )
                            }
                            disabled={!isAdm}
                            className="flex-1"
                          />
                          <label className="flex items-center gap-2 text-sm text-hipo-slate cursor-pointer whitespace-nowrap shrink-0">
                            <input
                              type="checkbox"
                              checked={!!acao.atingiu}
                              onChange={(e) =>
                                setBig3Campo(
                                  acao.ordem,
                                  'atingiu',
                                  e.target.checked
                                )
                              }
                              disabled={!isAdm}
                              className="w-4 h-4 accent-hipo-blue cursor-pointer"
                            />
                            Atingiu
                          </label>
                        </div>
                      ))}
                    </div>
                  </div>
                )}
              </Section>
            );
          })}
        </>
      )}
    </>
  );
}
