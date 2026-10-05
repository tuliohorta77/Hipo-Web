// web/src/pages/uc/Aula.jsx
//
// Uma aula da UC: vídeo, texto, material de apoio e o botão "Concluí".
//
// A TRAVA DO "CONCLUÍ". A aula libera depois de metade da duração estimada,
// contada da primeira abertura. O relógio que vale é o do SERVIDOR — a API
// devolve quantos segundos faltam e recusa (409) o concluir adiantado. A
// contagem regressiva aqui é só conforto: sem ela o botão ficaria
// desabilitado sem explicar até quando.
//
// AULA COM QUIZ (`quiz` não nulo) não tem "Concluí": conclui pela
// aprovação no QuizAula, que só abre depois da mesma trava de tempo.
//
// O VÍDEO entra por urlDeEmbed(provedor, ref), que monta o endereço a partir
// de uma tabela fechada. Nenhum texto da API vira src de iframe direto.
//
// O TOUR GUIADO. Aula de uso do HIPO traz passos (`tour`). "Me mostra no
// HIPO" abre a tela real e o TourGuiado (montado no Layout) destaca cada
// elemento; no fim volta para cá com ?tour=fim. Conta sem o módulo 'crm'
// (cargo UC) não abre as telas do CRM, então não vê o botão.

import { useCallback, useEffect, useState } from 'react';
import { useNavigate, useParams, useSearchParams } from 'react-router-dom';
import {
  ArrowLeft, ArrowRight, CheckCircle2, ExternalLink, FileText, Image as ImageIcon, RefreshCw, Clock,
  MousePointerClick,
} from 'lucide-react';
import api, { getModulos } from '../../api';
import PageHeader from '../../components/ui/PageHeader';
import Card, { CardHeader } from '../../components/ui/Card';
import Badge from '../../components/ui/Badge';
import Button from '../../components/ui/Button';
import AlertMessage from '../../components/ui/AlertMessage';
import { mensagemDeErro } from '../../components/crm/tarefaComum';
import TextoAula from '../../components/uc/TextoAula';
import QuizAula from '../../components/uc/QuizAula';
import { iniciarTour } from '../../components/uc/tour';
import {
  tamanhoArquivo, tempoRestante, tomDoPilar, urlDeEmbed,
} from '../../components/uc/ucComum';

export default function Aula() {
  const { aulaId } = useParams();
  const [params, setParams] = useSearchParams();
  const usuarioId = params.get('usuario_id');
  const voltouDoTour = params.get('tour') === 'fim';
  const podeTour = getModulos().includes('crm');
  const sufixo = usuarioId ? `?usuario_id=${usuarioId}` : '';
  const navigate = useNavigate();

  const [aula, setAula] = useState(null);
  const [erro, setErro] = useState('');
  const [falta, setFalta] = useState(0);
  const [concluindo, setConcluindo] = useState(false);
  const [erroConcluir, setErroConcluir] = useState('');

  const carregar = useCallback(async () => {
    setErro('');
    try {
      const { data } = await api.get(`/uc/aulas/${aulaId}`, {
        params: usuarioId ? { usuario_id: usuarioId } : undefined,
      });
      setAula(data);
      setFalta(data.segundos_para_liberar || 0);
    } catch (e) {
      setErro(mensagemDeErro(e, 'Não foi possível abrir a aula.'));
    }
  }, [aulaId, usuarioId]);

  useEffect(() => { setAula(null); setErroConcluir(''); carregar(); }, [carregar]);

  // Contagem regressiva local, só enquanto há o que contar.
  useEffect(() => {
    if (falta <= 0) return undefined;
    const t = setInterval(() => setFalta((s) => Math.max(0, s - 1)), 1000);
    return () => clearInterval(t);
  }, [falta > 0]); // eslint-disable-line react-hooks/exhaustive-deps

  async function concluir() {
    setConcluindo(true);
    setErroConcluir('');
    try {
      const { data } = await api.post(`/uc/aulas/${aulaId}/concluir`);
      setAula(data);
      setFalta(0);
    } catch (e) {
      setErroConcluir(mensagemDeErro(e, 'Não foi possível concluir a aula.'));
      if (e?.response?.status === 409) carregar();
    } finally {
      setConcluindo(false);
    }
  }

  async function abrirMaterial(m) {
    // Aba aberta ANTES do await: depois dele o navegador já não considera
    // o clique, e o bloqueador de pop-up engole a janela.
    const aba = window.open('', '_blank');
    try {
      const { data } = await api.get(`/uc/materiais/${m.id}/url`);
      if (aba) aba.location.href = data.url;
      else window.location.href = data.url;
    } catch (e) {
      if (aba) aba.close();
      setErro(mensagemDeErro(e, 'Não foi possível abrir o material.'));
    }
  }

  const voltar = (
    <Button
      variant="ghost"
      icon={ArrowLeft}
      onClick={() => navigate(aula ? `/uc/trilhas/${aula.trilha_id}${sufixo}` : `/uc${sufixo}`)}
    >
      {aula ? 'Trilha' : 'Universidade'}
    </Button>
  );

  if (erro && !aula) {
    return (
      <div className="max-w-4xl mx-auto">
        <PageHeader title="Aula" actions={voltar} />
        <AlertMessage tipo="erro">{erro}</AlertMessage>
      </div>
    );
  }
  if (!aula) return <p className="text-sm text-hipo-slate p-4">Carregando…</p>;

  const embed = urlDeEmbed(aula.video_provedor, aula.video_ref);
  const passos = aula.tour || [];

  function mostrarNoHipo() {
    iniciarTour({ aulaId: aula.id, aulaTitulo: aula.titulo, passos });
  }

  function fecharAvisoTour() {
    const p = new URLSearchParams(params);
    p.delete('tour');
    setParams(p, { replace: true });
  }
  const concluida = !!aula.concluida_em;
  const temQuiz = !!aula.quiz;

  return (
    <div className="max-w-4xl mx-auto space-y-4">
      <PageHeader
        title={`${aula.ordem}. ${aula.titulo}`}
        subtitle={aula.trilha_titulo}
        actions={voltar}
      />

      <div className="flex flex-wrap items-center gap-2">
        <Badge tone={tomDoPilar(aula.pilar).badge}>{aula.pilar_rotulo}</Badge>
        {aula.duracao_min && (
          <Badge tone="neutral"><Clock size={12} /> {aula.duracao_min} min</Badge>
        )}
        {concluida && <Badge tone="success"><CheckCircle2 size={12} /> Concluída</Badge>}
        {!concluida && aula.concluiu_versao_anterior && (
          <Badge tone="warning"><RefreshCw size={12} /> Atualizada desde que você concluiu</Badge>
        )}
        {aula.status !== 'publicada' && <Badge tone="warning">Rascunho</Badge>}
        {aula.modo_leitura && <Badge tone="info">Modo leitura</Badge>}
      </div>

      {erro && <AlertMessage tipo="erro">{erro}</AlertMessage>}

      {embed && (
        <div className="rounded-xl overflow-hidden border border-hipo-border bg-black aspect-video">
          <iframe
            title={`Vídeo: ${aula.titulo}`}
            src={embed}
            className="w-full h-full"
            allow="autoplay; fullscreen; picture-in-picture"
            allowFullScreen
            referrerPolicy="strict-origin-when-cross-origin"
          />
        </div>
      )}
      {embed && aula.video_url && (
        <a
          href={aula.video_url}
          target="_blank"
          rel="noreferrer"
          className="inline-flex items-center gap-1 text-xs text-hipo-blue hover:underline"
        >
          Abrir o vídeo no site <ExternalLink size={12} />
        </a>
      )}

      {aula.resumo && <p className="text-sm text-hipo-ink">{aula.resumo}</p>}

      {aula.conteudo_md && (
        <Card>
          <TextoAula md={aula.conteudo_md} />
        </Card>
      )}

      {passos.length > 0 && (
        <Card data-tour="uc-tour">
          <CardHeader
            title="Veja na prática"
            hint={`${passos.length} passos na tela real do HIPO`}
          />
          {voltouDoTour && (
            <AlertMessage tipo="ok" className="mb-3">
              <span className="flex flex-wrap items-center gap-2">
                Tour concluído. Agora faça você mesmo: abra a tela e repita os passos no seu dia a dia.
                <button type="button" onClick={fecharAvisoTour} className="underline text-xs">ok</button>
              </span>
            </AlertMessage>
          )}
          <ol className="list-decimal pl-5 space-y-1 text-sm text-hipo-ink mb-3">
            {passos.map((p, i) => <li key={i}>{p.titulo}</li>)}
          </ol>
          {podeTour ? (
            <div className="flex flex-col sm:flex-row sm:items-center gap-2">
              <Button icon={MousePointerClick} onClick={mostrarNoHipo}>Me mostra no HIPO</Button>
              <p className="text-xs text-hipo-slate">
                O tour só mostra: nada é criado nem alterado. Use as setas ou Enter para
                avançar e Esc para sair.
              </p>
            </div>
          ) : (
            <p className="text-xs text-hipo-slate">
              O tour abre as telas do CRM, que esta conta não acessa.
            </p>
          )}
        </Card>
      )}

      {aula.materiais.length > 0 && (
        <Card>
          <CardHeader title="Material de apoio" />
          <ul className="space-y-2">
            {aula.materiais.map((m) => (
              <li key={m.id}>
                <button
                  type="button"
                  onClick={() => abrirMaterial(m)}
                  className="w-full flex items-center gap-3 px-3 py-2 rounded-lg border border-hipo-border hover:bg-hipo-bg text-left"
                >
                  {m.eh_imagem ? <ImageIcon size={18} className="text-hipo-blue" /> : <FileText size={18} className="text-hipo-blue" />}
                  <span className="flex-1 text-sm text-hipo-ink truncate">{m.nome_original}</span>
                  <span className="text-xs text-hipo-slate">{tamanhoArquivo(m.bytes)}</span>
                </button>
              </li>
            ))}
          </ul>
        </Card>
      )}

      {temQuiz && (
        <QuizAula
          aula={aula}
          faltaAula={falta}
          onAtualizar={(data) => { setAula(data); setFalta(data.segundos_para_liberar || 0); }}
          onRecarregar={carregar}
        />
      )}

      <Card>
        <div className="flex flex-col sm:flex-row sm:items-center gap-3">
          <div className="flex-1">
            {aula.modo_leitura ? (
              <p className="text-sm text-hipo-slate">
                {concluida ? 'A pessoa concluiu esta aula.' : 'A pessoa ainda não concluiu esta aula.'}
              </p>
            ) : concluida ? (
              <p className="text-sm text-hipo-success font-medium">Aula concluída.</p>
            ) : temQuiz ? (
              <p className="text-sm text-hipo-slate">A aula conclui quando você for aprovado no quiz.</p>
            ) : falta > 0 ? (
              <p className="text-sm text-hipo-slate">
                O botão libera em <strong className="text-hipo-ink">{tempoRestante(falta)}</strong>.
                Aproveite para ler o texto e o material.
              </p>
            ) : (
              <p className="text-sm text-hipo-slate">Terminou? Marque a aula como concluída.</p>
            )}
            {erroConcluir && <AlertMessage tipo="erro" className="mt-2">{erroConcluir}</AlertMessage>}
          </div>
          <div className="flex items-center gap-2">
            {aula.anterior && (
              <Button variant="secondary" icon={ArrowLeft} onClick={() => navigate(`/uc/aulas/${aula.anterior.id}${sufixo}`)}>
                Anterior
              </Button>
            )}
            {!aula.modo_leitura && !concluida && !temQuiz && aula.status === 'publicada' && (
              <Button icon={CheckCircle2} onClick={concluir} loading={concluindo} disabled={falta > 0}>
                Concluí
              </Button>
            )}
            {aula.proxima && (
              <Button
                variant={concluida || aula.modo_leitura ? 'primary' : 'secondary'}
                iconRight={ArrowRight}
                onClick={() => navigate(`/uc/aulas/${aula.proxima.id}${sufixo}`)}
              >
                Próxima
              </Button>
            )}
          </div>
        </div>
      </Card>
    </div>
  );
}
