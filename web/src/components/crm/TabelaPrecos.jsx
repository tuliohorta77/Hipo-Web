// web/src/components/crm/TabelaPrecos.jsx
//
// A tabela de preço por faixa de vidas, dentro da aba Proposta.
//
// Todo mundo VÊ (é o que sai no slide "Tabela de preços" e o que sugere o
// valor de cada CNPJ); só a gestão EDITA — preço é decisão comercial e a
// tabela vale para toda proposta nova de todo vendedor. Quem decide se
// pode editar é o servidor (`pode_editar`); o botão só aparece quando ele
// diz que sim.
//
// Propostas já geradas não mudam com a edição: cada uma guardou a cópia
// da tabela que usou. A tela diz isso no editor, para ninguém ter medo de
// reajustar.

import { useState } from 'react';
import { Pencil, Plus, X, Save } from 'lucide-react';

import api from '../../api';
import Button from '../ui/Button';
import AlertMessage from '../ui/AlertMessage';
import { numero } from './propostaCalculo';

function mensagemDeErro(err, padrao) {
  const d = err?.response?.data?.detail;
  if (typeof d === 'string') return d;
  if (Array.isArray(d) && d[0]?.msg) return d[0].msg;
  if (d?.mensagem) return d.mensagem;
  return padrao;
}

const CAMPO = 'h-8 px-2 text-xs rounded-lg border border-hipo-border bg-hipo-card text-hipo-ink focus:outline-none focus:ring-2 focus:ring-hipo-blue';

function paraEdicao(faixas) {
  return faixas.map((f) => ({
    vidas_ate: f.vidas_ate === null ? '' : String(f.vidas_ate),
    tipo: f.tipo,
    valor: String(f.valor),
  }));
}

export default function TabelaPrecos({ tabela, onSalva }) {
  const [editando, setEditando] = useState(false);
  const [faixas, setFaixas] = useState([]);
  const [salvando, setSalvando] = useState(false);
  const [erro, setErro] = useState(null);

  if (!tabela) return null;

  function abrir() {
    setFaixas(paraEdicao(tabela.faixas));
    setErro(null);
    setEditando(true);
  }

  function trocar(i, campo, valor) {
    setFaixas((a) => a.map((f, idx) => (idx === i ? { ...f, [campo]: valor } : f)));
  }

  async function salvar() {
    setSalvando(true);
    setErro(null);
    try {
      const { data } = await api.put('/crm/tabela-precos', {
        faixas: faixas.map((f) => ({
          vidas_ate: String(f.vidas_ate).trim() ? Number(f.vidas_ate) : null,
          tipo: f.tipo,
          valor: numero(f.valor),
        })),
      });
      setEditando(false);
      onSalva?.(data);
    } catch (err) {
      setErro(mensagemDeErro(err, 'Não foi possível salvar a tabela.'));
    } finally {
      setSalvando(false);
    }
  }

  return (
    <section
      aria-label="Tabela de preços"
      className="border border-hipo-border rounded-lg p-3 bg-hipo-card space-y-2"
    >
      <div className="flex items-center justify-between gap-2">
        <h3 className="text-sm font-semibold text-hipo-ink">Tabela de preços</h3>
        {tabela.pode_editar && !editando && (
          <Button size="sm" variant="ghost" icon={Pencil} onClick={abrir}>
            Editar
          </Button>
        )}
      </div>

      {!editando && (
        <>
          <ul className="space-y-0.5 text-xs text-hipo-slate list-disc pl-4">
            {tabela.linhas.map((l) => <li key={l}>{l}</li>)}
          </ul>
          <p className="text-[11px] text-hipo-muted">
            {tabela.padrao
              ? 'Tabela padrão do sistema (ainda não editada).'
              : `Atualizada${tabela.atualizado_por_nome ? ` por ${tabela.atualizado_por_nome}` : ''}.`}
          </p>
        </>
      )}

      {editando && (
        <div className="space-y-2">
          {erro && <AlertMessage tipo="erro">{erro}</AlertMessage>}
          <p className="text-[11px] text-hipo-muted">
            Limite em branco = faixa aberta (“acima de”), que precisa ser uma só.
            Propostas já geradas mantêm a tabela com que foram feitas.
          </p>
          <ul className="space-y-1.5">
            {faixas.map((f, i) => (
              // eslint-disable-next-line react/no-array-index-key
              <li key={i} className="flex items-center gap-1.5">
                <input
                  aria-label={`Até quantas vidas (faixa ${i + 1})`}
                  type="number"
                  min="1"
                  placeholder="acima de"
                  value={f.vidas_ate}
                  onChange={(e) => trocar(i, 'vidas_ate', e.target.value)}
                  className={`${CAMPO} w-24`}
                />
                <select
                  aria-label={`Tipo da faixa ${i + 1}`}
                  value={f.tipo}
                  onChange={(e) => trocar(i, 'tipo', e.target.value)}
                  className={`${CAMPO} w-32`}
                >
                  <option value="fixo">mensal fixo</option>
                  <option value="por_vida">por vida</option>
                </select>
                <input
                  aria-label={`Valor da faixa ${i + 1}`}
                  type="number"
                  min="0"
                  step="0.01"
                  value={f.valor}
                  onChange={(e) => trocar(i, 'valor', e.target.value)}
                  className={`${CAMPO} flex-1 min-w-0`}
                />
                <button
                  type="button"
                  aria-label={`Remover faixa ${i + 1}`}
                  onClick={() => setFaixas((a) => a.filter((_, idx) => idx !== i))}
                  className="h-8 w-8 shrink-0 inline-flex items-center justify-center rounded-lg border border-hipo-border text-hipo-slate hover:bg-hipo-bg"
                >
                  <X size={13} />
                </button>
              </li>
            ))}
          </ul>
          <div className="flex flex-wrap gap-2">
            <Button
              size="sm"
              variant="ghost"
              icon={Plus}
              onClick={() => setFaixas((a) => [...a, { vidas_ate: '', tipo: 'fixo', valor: '' }])}
            >
              Faixa
            </Button>
            <div className="flex-1" />
            <Button size="sm" variant="secondary" onClick={() => setEditando(false)}>
              Cancelar
            </Button>
            <Button size="sm" icon={Save} loading={salvando} onClick={salvar}>
              Salvar tabela
            </Button>
          </div>
        </div>
      )}
    </section>
  );
}
