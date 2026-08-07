// web/src/components/crm/ContatosDaConta.jsx
//
// Lista de contatos vinculados a uma conta, dentro do formulário da conta.
//
// Contatos não têm tela própria: a pessoa só faz sentido no contexto da
// empresa (diretriz "uma tela por função" — ninguém tem a função de gerir
// contatos soltos). Vincular, criar, promover a principal e desvincular
// acontecem todos aqui.

import { useCallback, useEffect, useState } from 'react';
import { Star, Trash2, UserPlus, Mail, Phone } from 'lucide-react';

import api from '../../api';
import EntityPicker from '../EntityPicker';
import Button from '../ui/Button';
import Badge from '../ui/Badge';
import Empty from '../ui/Empty';
import AlertMessage from '../ui/AlertMessage';

function mensagemDeErro(err, padrao) {
  const d = err?.response?.data?.detail;
  if (typeof d === 'string') return d;
  if (Array.isArray(d) && d[0]?.msg) return d[0].msg;
  if (d?.mensagem) return d.mensagem;
  return padrao;
}

export default function ContatosDaConta({ contaId, contatos, onMudou }) {
  const [erro, setErro] = useState(null);
  const [ocupado, setOcupado] = useState(null);
  const [chaveReset, setChaveReset] = useState(0);

  useEffect(() => { setErro(null); }, [contaId]);

  const buscar = useCallback(
    async (q) => {
      const { data } = await api.get('/crm/contatos/busca', {
        params: { q, conta_id: contaId },
      });
      return data;
    },
    [contaId]
  );

  // Sugere possíveis duplicatas antes de criar. Diferente do CNPJ, aqui é
  // aviso: e-mail e telefone corporativos são legitimamente compartilhados.
  const checarDuplicata = useCallback(async (dados) => {
    if (!dados.email && !dados.telefone) return [];
    const { data } = await api.get('/crm/contatos/duplicatas', {
      params: { email: dados.email || undefined, telefone: dados.telefone || undefined },
    });
    return data.map((d) => ({
      id: d.id,
      texto: `${d.nome}${d.contas.length ? ` (${d.contas.join(', ')})` : ''} — mesmo ${d.motivo}`,
    }));
  }, []);

  async function acao(chave, fn, mensagemErro) {
    setOcupado(chave);
    setErro(null);
    try {
      await fn();
      onMudou();
    } catch (err) {
      setErro(mensagemDeErro(err, mensagemErro));
    } finally {
      setOcupado(null);
    }
  }

  async function vincular(contato) {
    if (!contato) return;
    await acao(
      'vincular',
      () => api.post(`/crm/contatos/${contato.id}/vinculos`, { conta_id: contaId }),
      'Não foi possível vincular o contato.'
    );
    setChaveReset((k) => k + 1);
  }

  async function criarEVincular(dados) {
    const { data } = await api.post('/crm/contatos', { ...dados, conta_id: contaId });
    onMudou();
    setChaveReset((k) => k + 1);
    return data;
  }

  return (
    <div className="space-y-3">
      {erro && <AlertMessage tipo="erro">{erro}</AlertMessage>}

      <EntityPicker
        key={chaveReset}
        label="Adicionar contato"
        value={null}
        onChange={vincular}
        buscar={buscar}
        limparAvisoDuplicata={checarDuplicata}
        placeholder="Buscar pessoa já cadastrada…"
        paraItem={(c) => ({
          id: c.id,
          titulo: c.nome,
          subtitulo: [c.email, c.telefone].filter(Boolean).join(' · ') || undefined,
          desabilitado: c.ja_vinculado,
          motivoDesabilitado: 'já vinculado',
        })}
        criar={{
          titulo: 'Cadastrar novo contato',
          campos: [
            { nome: 'nome', label: 'Nome', obrigatorio: true },
            { nome: 'email', label: 'E-mail', tipo: 'email' },
            { nome: 'telefone', label: 'Telefone' },
            { nome: 'data_nascimento', label: 'Nascimento', tipo: 'date' },
            { nome: 'cargo', label: 'Cargo nesta empresa' },
          ],
          onSubmit: criarEVincular,
        }}
      />

      {contatos.length === 0 ? (
        <Empty
          title="Nenhum contato nesta conta"
          description="Busque uma pessoa já cadastrada ou cadastre uma nova."
          icon={UserPlus}
        />
      ) : (
        <ul className="divide-y divide-hipo-border border border-hipo-border rounded-lg">
          {contatos.map((c) => (
            <li key={c.id} className="flex items-center gap-3 px-3 py-2.5">
              <div className="min-w-0 flex-1">
                <div className="flex items-center gap-2">
                  <span className="text-sm font-medium text-hipo-ink truncate">{c.nome}</span>
                  {c.principal && <Badge tone="info">Principal</Badge>}
                </div>
                <div className="flex flex-wrap gap-x-3 text-xs text-hipo-slate">
                  {c.cargo && <span>{c.cargo}</span>}
                  {c.email && (
                    <span className="inline-flex items-center gap-1">
                      <Mail size={11} />{c.email}
                    </span>
                  )}
                  {c.telefone && (
                    <span className="inline-flex items-center gap-1">
                      <Phone size={11} />{c.telefone}
                    </span>
                  )}
                </div>
              </div>

              {!c.principal && (
                <Button
                  size="sm"
                  variant="ghost"
                  icon={Star}
                  loading={ocupado === `principal-${c.id}`}
                  onClick={() =>
                    acao(
                      `principal-${c.id}`,
                      () => api.patch(`/crm/contatos/${c.id}/vinculos/${contaId}`, {
                        principal: true,
                      }),
                      'Não foi possível definir o contato principal.'
                    )
                  }
                >
                  Tornar principal
                </Button>
              )}

              <Button
                size="sm"
                variant="ghost"
                icon={Trash2}
                aria-label={`Desvincular ${c.nome}`}
                loading={ocupado === `remover-${c.id}`}
                onClick={() =>
                  acao(
                    `remover-${c.id}`,
                    () => api.delete(`/crm/contatos/${c.id}/vinculos/${contaId}`),
                    'Não foi possível desvincular o contato.'
                  )
                }
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
