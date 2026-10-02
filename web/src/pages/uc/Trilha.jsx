// web/src/pages/uc/Trilha.jsx
//
// Uma trilha da UC: o andamento e as aulas, na ordem. Cada linha é uma
// ação ("Abrir"), não só um item de lista. A gestão vê rascunho aqui antes
// de publicar, com o selo de rascunho em cada aula que ainda não vale.

import { useEffect, useState } from 'react';
import { useNavigate, useParams, useSearchParams } from 'react-router-dom';
import { ArrowLeft, CheckCircle2, Circle, RefreshCw, PlayCircle, Paperclip, Clock } from 'lucide-react';
import api from '../../api';
import PageHeader from '../../components/ui/PageHeader';
import Card from '../../components/ui/Card';
import Badge from '../../components/ui/Badge';
import Button from '../../components/ui/Button';
import AlertMessage from '../../components/ui/AlertMessage';
import { mensagemDeErro } from '../../components/crm/tarefaComum';
import {
  ESTADO_AULA, SITUACAO_TOM, textoPrazo, tomDoPilar,
} from '../../components/uc/ucComum';

const ICONE_ESTADO = { concluida: CheckCircle2, atualizada: RefreshCw, pendente: Circle };

export default function Trilha() {
  const { trilhaId } = useParams();
  const [params] = useSearchParams();
  const usuarioId = params.get('usuario_id');
  const sufixo = usuarioId ? `?usuario_id=${usuarioId}` : '';
  const navigate = useNavigate();
  const [trilha, setTrilha] = useState(null);
  const [erro, setErro] = useState('');

  useEffect(() => {
    let vivo = true;
    api.get(`/uc/trilhas/${trilhaId}`, { params: usuarioId ? { usuario_id: usuarioId } : undefined })
      .then(({ data }) => { if (vivo) setTrilha(data); })
      .catch((e) => { if (vivo) setErro(mensagemDeErro(e, 'Não foi possível abrir a trilha.')); });
    return () => { vivo = false; };
  }, [trilhaId, usuarioId]);

  const voltar = (
    <Button variant="ghost" icon={ArrowLeft} onClick={() => navigate(`/uc${sufixo}`)}>
      Universidade
    </Button>
  );

  if (erro) {
    return (
      <div className="max-w-4xl mx-auto">
        <PageHeader title="Trilha" actions={voltar} />
        <AlertMessage tipo="erro">{erro}</AlertMessage>
      </div>
    );
  }
  if (!trilha) return <p className="text-sm text-hipo-slate p-4">Carregando…</p>;

  const proxima = trilha.aulas.find((a) => a.estado !== 'concluida' && a.status === 'publicada');
  const prazo = textoPrazo(trilha.situacao, trilha.prazo);

  return (
    <div className="max-w-4xl mx-auto space-y-4">
      <PageHeader title={trilha.titulo} subtitle={trilha.descricao} actions={voltar} />

      <Card>
        <div className="flex flex-wrap items-center gap-2 mb-3">
          <Badge tone={tomDoPilar(trilha.pilar).badge}>{trilha.pilar_rotulo}</Badge>
          {trilha.status !== 'publicada' && <Badge tone="warning">Rascunho</Badge>}
          {trilha.obrigatoria && (
            <Badge tone={SITUACAO_TOM[trilha.situacao.codigo]}>{trilha.situacao.rotulo}</Badge>
          )}
          {prazo && <span className="text-xs text-hipo-slate">{prazo}</span>}
        </div>
        <div className="flex items-center gap-3">
          <div className="flex-1 h-2 rounded-full bg-hipo-bg overflow-hidden">
            <div
              className={`h-full rounded-full ${tomDoPilar(trilha.pilar).barra}`}
              style={{ width: `${trilha.percentual ?? 0}%` }}
            />
          </div>
          <span className="text-sm font-semibold text-hipo-ink">{trilha.percentual ?? 0}%</span>
          {proxima && !usuarioId && (
            <Button size="sm" icon={PlayCircle} onClick={() => navigate(`/uc/aulas/${proxima.id}`)}>
              {trilha.aulas.some((a) => a.estado === 'concluida') ? 'Continuar' : 'Começar'}
            </Button>
          )}
        </div>
      </Card>

      <Card padding="none">
        <ol className="divide-y divide-hipo-border">
          {trilha.aulas.map((a) => {
            const est = ESTADO_AULA[a.estado];
            const Icone = ICONE_ESTADO[a.estado];
            return (
              <li key={a.id}>
                <button
                  type="button"
                  onClick={() => navigate(`/uc/aulas/${a.id}${sufixo}`)}
                  className="w-full text-left px-5 py-4 flex items-start gap-3 hover:bg-hipo-bg transition-colors"
                >
                  <Icone
                    size={20}
                    className={`mt-0.5 shrink-0 ${a.estado === 'concluida' ? 'text-hipo-success' : a.estado === 'atualizada' ? 'text-hipo-warning' : 'text-hipo-muted'}`}
                  />
                  <div className="flex-1 min-w-0">
                    <p className="font-medium text-hipo-ink">{a.ordem}. {a.titulo}</p>
                    {a.resumo && <p className="text-sm text-hipo-slate mt-0.5">{a.resumo}</p>}
                    <div className="flex flex-wrap items-center gap-3 mt-1.5 text-xs text-hipo-slate">
                      {a.duracao_min && <span className="inline-flex items-center gap-1"><Clock size={12} /> {a.duracao_min} min</span>}
                      {a.tem_video && <span className="inline-flex items-center gap-1"><PlayCircle size={12} /> vídeo</span>}
                      {a.materiais > 0 && (
                        <span className="inline-flex items-center gap-1"><Paperclip size={12} /> {a.materiais} material{a.materiais === 1 ? '' : 'is'}</span>
                      )}
                    </div>
                  </div>
                  <div className="flex flex-col items-end gap-1 shrink-0">
                    <Badge tone={est.tom}>{est.rotulo}</Badge>
                    {a.status !== 'publicada' && <Badge tone="warning">Rascunho</Badge>}
                  </div>
                </button>
              </li>
            );
          })}
        </ol>
      </Card>
    </div>
  );
}
