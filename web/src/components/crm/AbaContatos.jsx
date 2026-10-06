// web/src/components/crm/AbaContatos.jsx
//
// O COMITÊ da oportunidade (entrega 045 — ABM / multithreading).
//
// A venda de medicina ocupacional passa por várias pessoas da mesma empresa:
// diretoria, RH, DP, Compras, SESMT, médico do trabalho. Depender de UMA é
// o jeito mais comum de perder negócio em silêncio. Esta aba é, ao mesmo
// tempo, o painel (farol de quantas pessoas estão envolvidas, se o decisor
// está mapeado, com quem já se falou) e a ferramenta (incluir, classificar
// o papel, trocar o principal, editar telefone, tirar da lista).
//
// O principal é o espelho de `oportunidades.contato_id` — o que a busca, a
// proposta e os relatórios mostram como "o contato".

import { useCallback, useEffect, useState } from 'react';
import { Star, Trash2, Pencil, UserPlus, Users, Mail } from 'lucide-react';

import api from '../../api';
import EntityPicker from '../EntityPicker';
import Button from '../ui/Button';
import Badge from '../ui/Badge';
import Empty from '../ui/Empty';
import AlertMessage from '../ui/AlertMessage';
import { Select } from '../ui/Input';
import {
  FormContato, LinkLinkedin, PAPEIS, TelefonesDoContato, mensagemDeErro,
} from './contatoComum';

function quando(iso) {
  if (!iso) return null;
  const dias = Math.floor((Date.now() - new Date(iso).getTime()) / 86400000);
  if (dias <= 0) return 'hoje';
  if (dias === 1) return 'ontem';
  return `há ${dias} dias`;
}

function Farol({ farol, qtd }) {
  if (!farol) return null;
  const pct = Math.min(qtd / farol.maximo_ideal, 1) * 100;
  const cor = {
    danger: 'bg-hipo-danger', warning: 'bg-hipo-warning', success: 'bg-hipo-success',
  }[farol.tom] || 'bg-hipo-slate';
  return (
    <section
      aria-label="Farol de multithreading"
      className="rounded-lg border border-hipo-border bg-hipo-card px-4 py-3 space-y-2"
    >
      <div className="flex flex-wrap items-center gap-2">
        <Users size={16} className="text-hipo-slate" aria-hidden="true" />
        <span className="text-sm font-medium text-hipo-ink">Comitê da conta</span>
        <Badge tone={farol.tom}>{farol.rotulo}</Badge>
        <Badge tone={farol.tem_decisor ? 'success' : 'neutral'}>
          {farol.tem_decisor ? 'Decisor mapeado' : 'Sem decisor'}
        </Badge>
        <span className="ml-auto text-xs text-hipo-slate">
          Ideal: {farol.minimo_ideal} a {farol.maximo_ideal} contatos
        </span>
      </div>
      <div className="h-1.5 rounded-full bg-hipo-bg overflow-hidden" aria-hidden="true">
        <div className={`h-full ${cor}`} style={{ width: `${pct}%` }} />
      </div>
      <p className="text-xs text-hipo-slate">{farol.dica}</p>
    </section>
  );
}

export default function AbaContatos({ oportunidade, onMudou }) {
  const oppId = oportunidade.id;
  const [dados, setDados] = useState(null);
  const [erro, setErro] = useState(null);
  const [ocupado, setOcupado] = useState(null);
  const [editando, setEditando] = useState(null);
  const [papelNovo, setPapelNovo] = useState('');
  const [chaveReset, setChaveReset] = useState(0);

  const carregar = useCallback(async () => {
    try {
      const { data } = await api.get(`/crm/oportunidades/${oppId}/contatos`);
      setDados(data);
    } catch (err) {
      setErro(mensagemDeErro(err, 'Não foi possível carregar os contatos.'));
      setDados({ itens: [], farol: null });
    }
  }, [oppId]);

  useEffect(() => { carregar(); }, [carregar]);

  async function acao(chave, fn, padrao) {
    setOcupado(chave);
    setErro(null);
    try {
      const resp = await fn();
      if (resp?.data?.itens) setDados(resp.data);
      else await carregar();
      onMudou?.();
      return true;
    } catch (err) {
      setErro(mensagemDeErro(err, padrao));
      return false;
    } finally {
      setOcupado(null);
    }
  }

  const buscar = useCallback(async (q) => {
    const { data } = await api.get('/crm/contatos/por-alvo', {
      params: { oportunidade_id: oppId },
    });
    const termo = q.trim().toLowerCase();
    return (data || []).filter((c) => (
      !termo
      || c.nome.toLowerCase().includes(termo)
      || (c.email || '').toLowerCase().includes(termo)
      || (c.telefone || '').includes(termo)
    ));
  }, [oppId]);

  async function incluir(contato) {
    if (!contato) return;
    await acao(
      'incluir',
      () => api.post(`/crm/oportunidades/${oppId}/contatos`, {
        contato_id: contato.id, papel: papelNovo || null,
      }),
      'Não foi possível incluir o contato.',
    );
    setPapelNovo('');
    setChaveReset((k) => k + 1);
  }

  // Só CRIA (já vinculado à conta). Quem põe no comitê é o `incluir`: o
  // EntityPicker chama `onChange` com o registro criado, e fazer as duas
  // coisas aqui faria a inclusão rodar duas vezes (a segunda, 409).
  async function criarNaConta(novo) {
    const { data } = await api.post('/crm/contatos', {
      ...novo, cargo: novo.cargo || null, conta_id: oportunidade.conta_id,
    });
    return data;
  }

  if (!dados) return <p className="text-sm text-hipo-slate">Carregando contatos…</p>;
  const ativos = dados.itens.filter((c) => c.ativo);

  return (
    <div className="space-y-4">
      {erro && <AlertMessage tipo="erro">{erro}</AlertMessage>}
      <Farol farol={dados.farol} qtd={ativos.length} />

      {/* Incluir: alguém da empresa (ou de um CNPJ adicional) ou uma pessoa nova. */}
      <div className="grid grid-cols-1 md:grid-cols-[1fr_220px] gap-3 items-end">
        <EntityPicker
          key={chaveReset}
          label="Incluir pessoa no comitê"
          value={null}
          onChange={incluir}
          buscar={buscar}
          placeholder="Buscar contato da empresa…"
          paraItem={(c) => ({
            id: c.id,
            titulo: c.nome,
            subtitulo: [c.cargo, c.email, c.telefone].filter(Boolean).join(' · ') || undefined,
            desabilitado: c.no_comite,
            motivoDesabilitado: 'já está aqui',
          })}
          criar={{
            titulo: 'Cadastrar pessoa nova',
            campos: [
              { nome: 'nome', label: 'Nome', obrigatorio: true },
              { nome: 'cargo', label: 'Cargo nesta empresa' },
              { nome: 'telefone', label: 'Telefone' },
              { nome: 'email', label: 'E-mail', tipo: 'email' },
            ],
            onSubmit: criarNaConta,
          }}
        />
        <Select
          id="comite-papel-novo"
          label="Papel de quem entra"
          value={papelNovo}
          onChange={(e) => setPapelNovo(e.target.value)}
        >
          <option value="">— classificar depois —</option>
          {PAPEIS.map((p) => <option key={p.valor} value={p.valor}>{p.rotulo}</option>)}
        </Select>
      </div>

      {dados.itens.length === 0 ? (
        <Empty
          title="Ninguém da empresa nesta negociação"
          description="Account Based: mapeie quem decide, quem usa o serviço e quem compra. O ideal é ter de 2 a 4 pessoas envolvidas."
          icon={UserPlus}
        />
      ) : (
        <ul className="divide-y divide-hipo-border border border-hipo-border rounded-lg">
          {dados.itens.map((c) => (editando === c.contato_id ? (
            <li key={c.contato_id} className="px-3 py-2.5">
              <FormContato
                contato={{ ...c, id: c.contato_id }}
                contaId={oportunidade.conta_id}
                cargoAtual={c.cargo}
                onCancelar={() => setEditando(null)}
                onSalvo={() => { setEditando(null); carregar(); onMudou?.(); }}
              />
            </li>
          ) : (
            <li key={c.contato_id} className="flex flex-wrap items-center gap-3 px-3 py-2.5">
              <div className="min-w-0 flex-1">
                <div className="flex flex-wrap items-center gap-2">
                  <span className={`text-sm font-medium truncate ${c.ativo ? 'text-hipo-ink' : 'text-hipo-muted line-through'}`}>
                    {c.nome}
                  </span>
                  {c.principal && <Badge tone="info">Principal</Badge>}
                  {!c.ativo && <Badge tone="neutral">inativo</Badge>}
                  {c.cargo && <span className="text-xs text-hipo-slate">{c.cargo}</span>}
                </div>
                <div className="flex flex-wrap items-center gap-x-3 gap-y-1 text-xs text-hipo-slate mt-0.5">
                  <TelefonesDoContato contato={c} compacto />
                  {c.email && (
                    <a href={`mailto:${c.email}`} className="inline-flex items-center gap-1 hover:text-hipo-blue">
                      <Mail size={11} aria-hidden="true" />{c.email}
                    </a>
                  )}
                  <LinkLinkedin url={c.linkedin} />
                  <span>
                    {c.interacoes
                      ? `${c.interacoes} interaç${c.interacoes === 1 ? 'ão' : 'ões'} · última ${quando(c.ultima_interacao)}`
                      : 'nenhuma interação ainda'}
                  </span>
                </div>
              </div>

              <select
                aria-label={`Papel de ${c.nome}`}
                value={c.papel || ''}
                disabled={ocupado === `papel-${c.contato_id}`}
                onChange={(e) => acao(
                  `papel-${c.contato_id}`,
                  () => api.patch(`/crm/oportunidades/${oppId}/contatos/${c.contato_id}`, {
                    papel: e.target.value || null,
                  }),
                  'Não foi possível mudar o papel.',
                )}
                className="h-9 px-2 text-sm rounded-lg border border-hipo-border bg-hipo-card text-hipo-ink"
              >
                <option value="">— papel —</option>
                {PAPEIS.map((p) => <option key={p.valor} value={p.valor}>{p.rotulo}</option>)}
              </select>

              {!c.principal && c.ativo && (
                <Button
                  size="sm" variant="ghost" icon={Star}
                  aria-label={`Tornar ${c.nome} principal`}
                  loading={ocupado === `principal-${c.contato_id}`}
                  onClick={() => acao(
                    `principal-${c.contato_id}`,
                    () => api.patch(`/crm/oportunidades/${oppId}/contatos/${c.contato_id}`, {
                      principal: true,
                    }),
                    'Não foi possível trocar o principal.',
                  )}
                >
                  Tornar principal
                </Button>
              )}
              <Button
                size="sm" variant="ghost" icon={Pencil}
                aria-label={`Editar ${c.nome}`}
                onClick={() => setEditando(c.contato_id)}
              >
                Editar
              </Button>
              <Button
                size="sm" variant="ghost" icon={Trash2}
                aria-label={`Tirar ${c.nome} da oportunidade`}
                loading={ocupado === `remover-${c.contato_id}`}
                onClick={() => acao(
                  `remover-${c.contato_id}`,
                  () => api.delete(`/crm/oportunidades/${oppId}/contatos/${c.contato_id}`),
                  'Não foi possível tirar o contato.',
                )}
              >
                Tirar
              </Button>
            </li>
          )))}
        </ul>
      )}
    </div>
  );
}
