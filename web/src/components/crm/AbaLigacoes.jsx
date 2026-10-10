// web/src/components/crm/AbaLigacoes.jsx
//
// Aba Ligações da oportunidade (entrega 056 — Vivo Voz Negócio).
//
// Painel e ferramenta ao mesmo tempo (diretriz 2): em cima, quantas
// ligações, quantos minutos gravados, quantas transcritas e quanto quem
// ligou falou; embaixo, cada ligação, que abre com o resumo, a conversa e o
// áudio. Ligar continua sendo pelo telefone do contato (aba Contatos ou a
// tarefa): o clique avisa o HIPO e a gravação cai aqui sozinha.
//
// Enquanto alguma ligação está em andamento (subindo, transcrevendo), a
// aba se atualiza a cada 20 s — quem desligou e abriu a aba vê a
// transcrição chegar sem apertar nada.

import { useCallback, useEffect, useMemo, useState } from 'react';
import { Link } from 'react-router-dom';
import {
  PhoneCall, Clock, FileText, Mic, ChevronDown, ChevronRight, Phone,
} from 'lucide-react';

import api from '../../api';
import AlertMessage from '../ui/AlertMessage';
import Badge from '../ui/Badge';
import Empty from '../ui/Empty';
import KpiInline from '../ui/KpiInline';
import LigacaoDetalhe from './LigacaoDetalhe';
import { mensagemDeErro } from './contatoComum';
import {
  EM_ANDAMENTO, TOM_STATUS, dataHoraCurta, duracaoTexto, quando,
} from './ligacoes';

const ATUALIZAR_MS = 20000;

function LinhaLigacao({ lig, aberta, onAlternar, onMudou }) {
  return (
    <li className="px-3 py-2.5">
      <button
        type="button"
        aria-expanded={aberta}
        onClick={onAlternar}
        className="w-full flex flex-wrap items-center gap-x-3 gap-y-1 text-left focus:outline-none focus-visible:ring-2 focus-visible:ring-hipo-blue rounded"
      >
        {aberta
          ? <ChevronDown size={14} className="text-hipo-slate shrink-0" aria-hidden="true" />
          : <ChevronRight size={14} className="text-hipo-slate shrink-0" aria-hidden="true" />}
        <span className="text-sm font-medium text-hipo-ink">{dataHoraCurta(quando(lig))}</span>
        <span className="text-xs text-hipo-slate">{lig.usuario_nome}</span>
        {lig.contato_nome && (
          <span className="text-xs text-hipo-slate">→ {lig.contato_nome}</span>
        )}
        {lig.telefone && (
          <span className="inline-flex items-center gap-1 text-xs text-hipo-muted">
            <Phone size={10} aria-hidden="true" />{lig.telefone}
          </span>
        )}
        <span className="ml-auto flex items-center gap-2">
          <span className="text-xs tabular-nums text-hipo-slate">{duracaoTexto(lig.duracao_s)}</span>
          <Badge tone={TOM_STATUS[lig.status] || 'neutral'} className="!px-2 !py-0.5">
            {lig.status_rotulo}
          </Badge>
        </span>
      </button>
      {!aberta && lig.resumo && (
        <p className="mt-1 ml-6 text-xs text-hipo-slate line-clamp-2">{lig.resumo}</p>
      )}
      {aberta && (
        <div className="mt-2 ml-6">
          <LigacaoDetalhe ligacaoId={lig.id} versao={lig.status} onMudou={onMudou} />
        </div>
      )}
    </li>
  );
}

export default function AbaLigacoes({ oportunidade, contaId }) {
  const filtro = useMemo(
    () => (oportunidade ? { oportunidade_id: oportunidade.id } : { conta_id: contaId }),
    [oportunidade, contaId],
  );
  const [dados, setDados] = useState(null);
  const [erro, setErro] = useState(null);
  const [aberta, setAberta] = useState(null);

  const carregar = useCallback(async () => {
    try {
      const { data } = await api.get('/crm/ligacoes', { params: filtro });
      setDados(data);
      setErro(null);
    } catch (err) {
      setErro(mensagemDeErro(err, 'Não foi possível carregar as ligações.'));
    }
  }, [filtro]);

  useEffect(() => { carregar(); }, [carregar]);

  const andando = (dados?.ligacoes || []).some((l) => EM_ANDAMENTO.includes(l.status));
  useEffect(() => {
    if (!andando) return undefined;
    const t = setInterval(carregar, ATUALIZAR_MS);
    return () => clearInterval(t);
  }, [andando, carregar]);

  if (!dados) {
    return erro
      ? <AlertMessage tipo="erro">{erro}</AlertMessage>
      : <p className="text-sm text-hipo-muted">Carregando…</p>;
  }

  const { ligacoes, kpis, gravacao } = dados;

  return (
    <div className="space-y-3">
      <div className="flex flex-wrap items-center gap-2">
        <KpiInline
          label="Ligações"
          valor={kpis.total}
          titulo="Cliques em ligar pelo HIPO e gravações vinculadas a esta negociação."
          icone={PhoneCall}
          tom="bg-hipo-blueSoft text-hipo-blue"
        />
        <KpiInline
          label="Gravadas"
          valor={kpis.gravadas}
          detalhe={`${kpis.minutos} min`}
          icone={Clock}
          tom="bg-hipo-bg text-hipo-slate"
        />
        <KpiInline
          label="Transcritas"
          valor={kpis.transcritas}
          icone={FileText}
          tom="bg-hipo-successSoft text-hipo-success"
        />
        <KpiInline
          label="Fala de quem ligou"
          valor={kpis.fala_media_pct === null ? '—' : `${kpis.fala_media_pct}%`}
          titulo="Média do tempo de fala de quem ligou. Acima de 60% costuma ser pouca pergunta."
          icone={Mic}
          tom={kpis.fala_media_pct > 60 ? 'bg-hipo-warningSoft text-hipo-warning' : 'bg-hipo-bg text-hipo-slate'}
        />
      </div>

      {erro && <AlertMessage tipo="erro">{erro}</AlertMessage>}

      {!gravacao.disponivel && (
        <AlertMessage tipo="info">
          A gravação de ligações está desligada no servidor. Os cliques em ligar continuam registrados.
        </AlertMessage>
      )}
      {gravacao.disponivel && !gravacao.gravador_online && (
        <AlertMessage tipo="aviso">
          Seu gravador de ligações não está ligado. As ligações feitas agora não serão gravadas nem
          transcritas. Veja em <Link to="/perfil" className="underline">Perfil → Gravador de ligações</Link>.
        </AlertMessage>
      )}

      {ligacoes.length === 0 ? (
        <Empty
          icon={PhoneCall}
          title="Nenhuma ligação ainda"
          description="Clique no telefone de um contato (aba Contatos ou na tarefa) para ligar pelo Vivo Voz Negócio. A ligação aparece aqui gravada, transcrita e resumida."
        />
      ) : (
        <ul className="divide-y divide-hipo-border rounded-lg border border-hipo-border bg-hipo-card">
          {ligacoes.map((l) => (
            <LinhaLigacao
              key={l.id}
              lig={l}
              aberta={aberta === l.id}
              onAlternar={() => setAberta((a) => (a === l.id ? null : l.id))}
              onMudou={carregar}
            />
          ))}
        </ul>
      )}
    </div>
  );
}
