// web/src/pages/uc/MinhaUC.jsx
//
// Universidade Corporativa — a tela de quem aprende.
//
// Segue as três diretrizes da casa:
//   1. uma tela por função: cada pessoa vê o manual do PRÓPRIO cargo;
//   2. dashboard operacional: os três pilares no topo, e cada um abre um
//      painel com as trilhas que compõem o número e o botão para seguir;
//   3. próxima tarefa: a tela abre num cartão "Sua próxima aula", não numa
//      lista de cursos.
//
// A gestão abre a UC de qualquer pessoa com ?usuario_id= (vindo da aba Time
// do estúdio). A tela é a mesma, em modo leitura: sem botão de começar.

import { useCallback, useEffect, useState } from 'react';
import { useNavigate, useSearchParams } from 'react-router-dom';
import {
  BookOpen, Compass, Zap, PlayCircle, GraduationCap, PenSquare, ArrowLeft, Clock,
} from 'lucide-react';
import api from '../../api';
import PageHeader from '../../components/ui/PageHeader';
import Card, { CardHeader } from '../../components/ui/Card';
import Badge from '../../components/ui/Badge';
import Button from '../../components/ui/Button';
import AlertMessage from '../../components/ui/AlertMessage';
import Empty from '../../components/ui/Empty';
import Modal from '../../components/ui/Modal';
import { mensagemDeErro } from '../../components/crm/tarefaComum';
import {
  SITUACAO_TOM, dataCurta, textoPrazo, tomDoPilar,
} from '../../components/uc/ucComum';

const ICONE_PILAR = { tecnica: BookOpen, metodo: Compass, energia: Zap };

function Barra({ percentual, pilar }) {
  const p = percentual ?? 0;
  return (
    <div className="h-1.5 rounded-full bg-hipo-bg overflow-hidden" aria-hidden="true">
      <div className={`h-full rounded-full ${tomDoPilar(pilar).barra}`} style={{ width: `${p}%` }} />
    </div>
  );
}

function CartaoPilar({ pilar, onAbrir }) {
  const Icone = ICONE_PILAR[pilar.pilar] || BookOpen;
  const vazio = pilar.trilhas === 0;
  return (
    <button
      type="button"
      onClick={() => onAbrir(pilar)}
      className="text-left bg-hipo-card border border-hipo-border rounded-xl shadow-soft p-5 hover:border-hipo-blue transition-colors"
      aria-label={`Pilar ${pilar.rotulo}`}
    >
      <div className="flex items-start justify-between mb-3">
        <p className="text-sm font-medium text-hipo-slate">{pilar.rotulo}</p>
        <div className={`w-9 h-9 rounded-lg flex items-center justify-center ${tomDoPilar(pilar.pilar).icone}`}>
          <Icone size={18} />
        </div>
      </div>
      <p className="text-kpi text-hipo-ink">{vazio || pilar.percentual === null ? '—' : `${pilar.percentual}%`}</p>
      <p className="text-xs text-hipo-slate mt-1 mb-2">
        {vazio
          ? 'Nenhuma trilha publicada ainda'
          : `${pilar.aulas_concluidas} de ${pilar.aulas_total} aulas · ${pilar.trilhas} trilha${pilar.trilhas === 1 ? '' : 's'}`}
      </p>
      <Barra percentual={pilar.percentual} pilar={pilar.pilar} />
    </button>
  );
}

function LinhaTrilha({ trilha, leitura, onAbrir }) {
  const sit = trilha.situacao;
  const prazo = textoPrazo(sit, trilha.prazo);
  const concluida = sit.codigo === 'concluida';
  return (
    <li className="py-3 flex flex-col sm:flex-row sm:items-center gap-3">
      <div className="flex-1 min-w-0">
        <div className="flex flex-wrap items-center gap-2">
          <button
            type="button"
            onClick={() => onAbrir(trilha)}
            className="font-medium text-hipo-ink hover:text-hipo-blue text-left"
          >
            {trilha.titulo}
          </button>
          <Badge tone={tomDoPilar(trilha.pilar).badge}>{trilha.pilar_rotulo}</Badge>
          {trilha.obrigatoria && <Badge tone={SITUACAO_TOM[sit.codigo]}>{sit.rotulo}</Badge>}
        </div>
        <div className="flex items-center gap-3 mt-2">
          <div className="flex-1 max-w-xs"><Barra percentual={trilha.percentual} pilar={trilha.pilar} /></div>
          <span className="text-xs text-hipo-slate whitespace-nowrap">
            {trilha.aulas_concluidas}/{trilha.aulas_total} aulas
          </span>
          {prazo && (
            <span className={`text-xs whitespace-nowrap ${sit.codigo === 'atrasada' ? 'text-hipo-danger' : 'text-hipo-slate'}`}>
              {prazo}
            </span>
          )}
        </div>
      </div>
      {!leitura && (
        <Button
          size="sm"
          variant={concluida ? 'secondary' : 'primary'}
          onClick={() => onAbrir(trilha, !concluida)}
        >
          {concluida ? 'Revisar' : trilha.aulas_concluidas > 0 ? 'Continuar' : 'Começar'}
        </Button>
      )}
    </li>
  );
}

export default function MinhaUC() {
  const navigate = useNavigate();
  const [params] = useSearchParams();
  const usuarioId = params.get('usuario_id');

  const [dados, setDados] = useState(null);
  const [erro, setErro] = useState('');
  const [pilarAberto, setPilarAberto] = useState(null);

  const carregar = useCallback(async () => {
    setErro('');
    try {
      const { data } = await api.get('/uc/painel', {
        params: usuarioId ? { usuario_id: usuarioId } : undefined,
      });
      setDados(data);
    } catch (e) {
      setErro(mensagemDeErro(e, 'Não foi possível carregar a Universidade.'));
    }
  }, [usuarioId]);

  useEffect(() => { carregar(); }, [carregar]);

  const sufixo = usuarioId ? `?usuario_id=${usuarioId}` : '';
  const leitura = !!dados?.modo_leitura;

  function abrirTrilha(trilha, irDireto = false) {
    setPilarAberto(null);
    if (irDireto && trilha.proxima_aula_id) {
      navigate(`/uc/aulas/${trilha.proxima_aula_id}${sufixo}`);
    } else {
      navigate(`/uc/trilhas/${trilha.id}${sufixo}`);
    }
  }

  if (erro && !dados) {
    return (
      <div className="max-w-6xl mx-auto">
        <PageHeader title="Universidade" />
        <AlertMessage tipo="erro">{erro}</AlertMessage>
      </div>
    );
  }
  if (!dados) {
    return <p className="text-sm text-hipo-slate p-4">Carregando…</p>;
  }

  const { proxima, pilares, manual, outras } = dados;
  const todas = [...manual.trilhas, ...outras];
  const doPilar = pilarAberto ? todas.filter((t) => t.pilar === pilarAberto.pilar) : [];
  const nada = todas.length === 0;

  return (
    <div className="max-w-6xl mx-auto space-y-5">
      <PageHeader
        title={leitura ? `Universidade · ${dados.usuario.nome}` : 'Universidade'}
        subtitle={
          leitura
            ? `${dados.usuario.cargo || 'sem cargo'} · modo leitura`
            : 'Técnica, Método e Energia: o que saber, como fazer e quanto fazer.'
        }
        actions={
          dados.pode_editar_conteudo && (
            leitura ? (
              <Button variant="secondary" icon={ArrowLeft} onClick={() => navigate('/uc/estudio?aba=time')}>
                Voltar ao time
              </Button>
            ) : (
              <Button variant="secondary" icon={PenSquare} onClick={() => navigate('/uc/estudio')}>
                Estúdio
              </Button>
            )
          )
        }
      />

      {erro && <AlertMessage tipo="erro">{erro}</AlertMessage>}

      <div className="grid gap-4 grid-cols-1 lg:grid-cols-5">
        <Card data-tour="uc-proxima" className="lg:col-span-2" padding="md">
          <p className="text-xs font-semibold uppercase tracking-wide text-hipo-slate mb-3">
            {leitura ? 'Próxima aula da pessoa' : 'Sua próxima aula'}
          </p>
          {proxima ? (
            <div data-testid="proxima-aula">
              <div className="flex flex-wrap items-center gap-2 mb-2">
                <Badge tone={tomDoPilar(proxima.pilar).badge}>{proxima.pilar_rotulo}</Badge>
                <Badge tone={proxima.motivo === 'atrasada' ? 'danger' : proxima.motivo === 'vence_logo' ? 'warning' : 'neutral'}>
                  {proxima.motivo_texto}
                </Badge>
              </div>
              <p className="text-h2 text-hipo-ink">{proxima.aula_titulo}</p>
              <p className="text-sm text-hipo-slate mt-1">{proxima.trilha_titulo}</p>
              <div className="flex flex-wrap items-center gap-3 mt-2 text-xs text-hipo-slate">
                {proxima.duracao_min && (
                  <span className="inline-flex items-center gap-1"><Clock size={12} /> {proxima.duracao_min} min</span>
                )}
                {proxima.prazo && <span>prazo da trilha: {dataCurta(proxima.prazo)}</span>}
              </div>
              {!leitura && (
                <Button
                  className="mt-4"
                  icon={PlayCircle}
                  onClick={() => navigate(`/uc/aulas/${proxima.aula_id}`)}
                >
                  Começar
                </Button>
              )}
            </div>
          ) : (
            <Empty
              icon={GraduationCap}
              title={nada ? 'Nenhuma trilha para o seu cargo ainda' : 'Tudo em dia'}
              description={nada ? 'Quando a gestão publicar, ela aparece aqui.' : 'Não há aula pendente agora.'}
              className="py-6"
            />
          )}
        </Card>
        {pilares.map((p) => (
          <CartaoPilar key={p.pilar} pilar={p} onAbrir={setPilarAberto} />
        ))}
      </div>

      <div className="grid gap-4 grid-cols-1 lg:grid-cols-3">
        <Card data-tour="uc-manual" className="lg:col-span-2">
          <CardHeader
            title="Manual da função"
            hint={
              manual.trilhas_total
                ? `${manual.trilhas_concluidas} de ${manual.trilhas_total} trilhas obrigatórias concluídas`
                  + (manual.atrasadas ? ` · ${manual.atrasadas} atrasada${manual.atrasadas === 1 ? '' : 's'}` : '')
                : 'Trilhas obrigatórias do cargo'
            }
          />
          {manual.trilhas.length ? (
            <ul className="divide-y divide-hipo-border">
              {manual.trilhas.map((t) => (
                <LinhaTrilha key={t.id} trilha={t} leitura={leitura} onAbrir={abrirTrilha} />
              ))}
            </ul>
          ) : (
            <Empty title="Sem trilha obrigatória" description="O cargo ainda não tem manual publicado." className="py-6" />
          )}
        </Card>
        <Card>
          <CardHeader title="Outras trilhas" hint="Abertas ao seu cargo, sem prazo" />
          {outras.length ? (
            <ul className="divide-y divide-hipo-border">
              {outras.map((t) => (
                <LinhaTrilha key={t.id} trilha={t} leitura={leitura} onAbrir={abrirTrilha} />
              ))}
            </ul>
          ) : (
            <p className="text-sm text-hipo-slate">Nenhuma por enquanto.</p>
          )}
        </Card>
      </div>

      <Modal
        aberto={!!pilarAberto}
        onFechar={() => setPilarAberto(null)}
        titulo={pilarAberto ? `Pilar ${pilarAberto.rotulo}` : ''}
        subtitulo={pilarAberto && pilarAberto.trilhas
          ? `${pilarAberto.aulas_concluidas} de ${pilarAberto.aulas_total} aulas concluídas`
          : undefined}
        size="lg"
      >
        {doPilar.length ? (
          <ul className="divide-y divide-hipo-border">
            {doPilar.map((t) => (
              <LinhaTrilha key={t.id} trilha={t} leitura={leitura} onAbrir={abrirTrilha} />
            ))}
          </ul>
        ) : (
          <Empty title="Nenhuma trilha neste pilar ainda" className="py-6" />
        )}
        <p className="text-xs text-hipo-muted mt-4">
          A nota mensal do pilar, com Método e Energia medidos na operação, chega nas próximas entregas da UC.
        </p>
      </Modal>
    </div>
  );
}
