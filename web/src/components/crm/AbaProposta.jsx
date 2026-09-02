// web/src/components/crm/AbaProposta.jsx
//
// A proposta comercial, dentro da oportunidade.
//
// ── O que esta aba faz ───────────────────────────────────────────────
// Preenche os dois slides variáveis do material da Controller MedSeg —
// escopo/investimento e o fechamento — e devolve o arquivo pronto. Os
// slides 1 a 4 são institucionais e ninguém edita.
//
// ── Por que os números não são todos digitáveis ──────────────────────
// Mensalidade é vidas x valor por vida; investimento é a soma com
// treinamentos e laudos. Deixar os cinco campos abertos abriria espaço
// para proposta com 50 vidas a R$ 20,00 e mensalidade de R$ 900 — e o
// cliente cobra o que está escrito no slide. Aqui o vendedor digita as
// PARCELAS; os totais aparecem calculados, do mesmo jeito que sairão no
// arquivo.
//
// ── Por que versão, e não edição ─────────────────────────────────────
// Proposta enviada não se corrige: se refaz. Cada geração vira uma versão
// nova, com quem gerou e quando, e as anteriores continuam baixáveis — é o
// que responde "o que a gente mandou primeiro" quando o cliente questiona
// o desconto duas semanas depois.

import { useCallback, useEffect, useMemo, useState } from 'react';
import {
  FileText, Plus, X, Download, FileType2, Loader2, History,
} from 'lucide-react';

import api from '../../api';
import Input from '../ui/Input';
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

export function formatarMoeda(v) {
  const n = Number(v);
  if (!Number.isFinite(n)) return 'R$ 0,00';
  return n.toLocaleString('pt-BR', { style: 'currency', currency: 'BRL' });
}

function formatarData(iso) {
  return iso ? new Date(`${String(iso).slice(0, 10)}T12:00:00`).toLocaleDateString('pt-BR') : '—';
}

// Data local em ISO. `toISOString()` converte para UTC e, das 21h à
// meia-noite em Brasília, devolve o dia SEGUINTE — a proposta sairia
// datada de amanhã para quem gera no fim do expediente. Mesma armadilha de
// fuso documentada em claude/armadilhas-deploy-e-fuso.md.
export function hojeLocalISO(base = new Date()) {
  const d = new Date(base.getTime() - base.getTimezoneOffset() * 60000);
  return d.toISOString().slice(0, 10);
}

export function somarDiasISO(iso, dias) {
  const d = new Date(`${iso}T12:00:00`);
  d.setDate(d.getDate() + dias);
  return hojeLocalISO(d);
}

// ── Uma versão na lista ──────────────────────────────────────────────

function Versao({ proposta, ocupado, pdfDisponivel, onBaixar }) {
  return (
    <li className="border border-hipo-border rounded-lg p-3 bg-hipo-card">
      <div className="flex items-start gap-2">
        <Badge tone="info">v{proposta.versao}</Badge>
        <div className="min-w-0 flex-1">
          <p className="text-sm font-medium text-hipo-ink">
            {formatarMoeda(proposta.investimento)}
            <span className="text-xs font-normal text-hipo-slate">
              {' '}· {proposta.vidas} vida{proposta.vidas === 1 ? '' : 's'} a{' '}
              {formatarMoeda(proposta.valor_por_vida)}
            </span>
          </p>
          <p className="text-xs text-hipo-slate mt-0.5">
            {formatarData(proposta.data_proposta)} · válida até{' '}
            {formatarData(proposta.validade)}
          </p>
          <p className="text-[11px] text-hipo-muted mt-0.5 truncate">
            {proposta.executivo_nome}
            {proposta.criado_por_nome
              && proposta.criado_por_nome !== proposta.executivo_nome
              && ` · gerada por ${proposta.criado_por_nome}`}
          </p>
        </div>
        <div className="flex gap-1 shrink-0">
          <Button
            size="sm"
            variant="secondary"
            icon={Download}
            disabled={ocupado}
            onClick={() => onBaixar(proposta, 'pptx')}
          >
            PPTX
          </Button>
          {/*
            O botão de PDF só aparece onde o servidor tem LibreOffice. O
            back diz se tem (pdf_disponivel) — oferecer o download e falhar
            depois do clique seria pior do que não oferecer.
          */}
          {pdfDisponivel && (
            <Button
              size="sm"
              variant="secondary"
              icon={FileType2}
              disabled={ocupado}
              onClick={() => onBaixar(proposta, 'pdf')}
            >
              PDF
            </Button>
          )}
        </div>
      </div>
    </li>
  );
}

// ── Aba ──────────────────────────────────────────────────────────────

export default function AbaProposta({ oportunidade, onGerada }) {
  const [padrao, setPadrao] = useState(null);
  const [versoes, setVersoes] = useState([]);
  const [carregando, setCarregando] = useState(true);
  const [gerando, setGerando] = useState(false);
  const [baixando, setBaixando] = useState(null);
  const [erro, setErro] = useState(null);

  const [vidas, setVidas] = useState('');
  const [valorVida, setValorVida] = useState('');
  const [treinamentos, setTreinamentos] = useState('0');
  const [laudos, setLaudos] = useState('0');
  const [escopo, setEscopo] = useState([]);
  const [dataProposta, setDataProposta] = useState(hojeLocalISO());
  const [validade, setValidade] = useState('');
  const [cidade, setCidade] = useState('');

  const carregar = useCallback(async () => {
    setCarregando(true);
    setErro(null);
    try {
      const [p, lista] = await Promise.all([
        api.get(`/crm/oportunidades/${oportunidade.id}/proposta-padrao`),
        api.get(`/crm/oportunidades/${oportunidade.id}/propostas`),
      ]);
      setPadrao(p.data);
      setVersoes(lista.data);

      const hoje = hojeLocalISO();
      setCidade(p.data.cidade);
      setDataProposta(hoje);
      setValidade(somarDiasISO(hoje, p.data.dias_validade));
      setEscopo(p.data.escopo_padrao);
      // A última proposta é o ponto de partida do "ajustar o desconto":
      // muda um valor, o resto continua igual.
      if (p.data.vidas != null) setVidas(String(p.data.vidas));
      if (p.data.valor_por_vida != null) setValorVida(String(p.data.valor_por_vida));
    } catch (err) {
      setErro(mensagemDeErro(err, 'Não foi possível carregar a proposta.'));
    } finally {
      setCarregando(false);
    }
  }, [oportunidade.id]);

  useEffect(() => { carregar(); }, [carregar]);

  // Os mesmos cálculos do backend, para o vendedor ver o total ANTES de
  // gerar. O servidor recalcula na hora de gravar — este número é para o
  // olho, não é o que vai para o arquivo.
  const totais = useMemo(() => {
    const n = (v) => {
      const x = Number(String(v).replace(',', '.'));
      return Number.isFinite(x) ? x : 0;
    };
    const mensal = n(vidas) * n(valorVida);
    return { mensal, investimento: mensal + n(treinamentos) + n(laudos) };
  }, [vidas, valorVida, treinamentos, laudos]);

  function trocarItem(i, texto) {
    setEscopo((atual) => atual.map((item, idx) => (idx === i ? texto : item)));
  }

  function removerItem(i) {
    setEscopo((atual) => atual.filter((_, idx) => idx !== i));
  }

  async function gerar() {
    setGerando(true);
    setErro(null);
    try {
      const { data } = await api.post(
        `/crm/oportunidades/${oportunidade.id}/propostas`,
        {
          vidas: Number(vidas),
          valor_por_vida: Number(String(valorVida).replace(',', '.')),
          treinamentos: Number(String(treinamentos).replace(',', '.')) || 0,
          laudos: Number(String(laudos).replace(',', '.')) || 0,
          escopo: escopo.map((i) => i.trim()).filter(Boolean),
          data_proposta: dataProposta,
          validade,
          cidade: cidade.trim(),
        },
      );
      setVersoes((atual) => [data, ...atual]);
      // A mensalidade da oportunidade muda junto no backend; avisar o pai
      // é o que mantém o cartão do funil e o trilho coerentes com o que
      // acabou de ser gerado.
      onGerada?.(data);
      await baixar(data, 'pptx');
    } catch (err) {
      setErro(mensagemDeErro(err, 'Não foi possível gerar a proposta.'));
    } finally {
      setGerando(false);
    }
  }

  /*
    Download com blob, e não <a href> direto: a rota exige o Bearer do
    axios, e uma âncora comum sairia sem o cabeçalho e voltaria 401. O
    nome do arquivo vem do Content-Disposition do servidor, que é quem
    sabe o número da oportunidade e a versão.
  */
  async function baixar(proposta, formato) {
    setBaixando(`${proposta.id}-${formato}`);
    setErro(null);
    try {
      const resp = await api.get(`/crm/propostas/${proposta.id}/arquivo`, {
        params: { formato },
        responseType: 'blob',
      });
      const disposicao = resp.headers?.['content-disposition'] || '';
      const achado = /filename="?([^";]+)"?/.exec(disposicao);
      const url = URL.createObjectURL(resp.data);
      const link = document.createElement('a');
      link.href = url;
      link.download = achado ? achado[1] : `proposta-v${proposta.versao}.${formato}`;
      document.body.appendChild(link);
      link.click();
      link.remove();
      URL.revokeObjectURL(url);
    } catch (err) {
      // Um erro em blob chega como Blob, não como JSON — sem esta leitura,
      // a mensagem do servidor (ex.: LibreOffice ausente) viraria
      // "[object Blob]" na tela.
      let mensagem = 'Não foi possível baixar o arquivo.';
      const corpo = err?.response?.data;
      if (corpo instanceof Blob) {
        try {
          const texto = await corpo.text();
          mensagem = JSON.parse(texto).detail || mensagem;
        } catch { /* mantém o padrão */ }
      } else {
        mensagem = mensagemDeErro(err, mensagem);
      }
      setErro(mensagem);
    } finally {
      setBaixando(null);
    }
  }

  if (carregando) {
    return <p className="py-10 text-center text-sm text-hipo-slate">Carregando proposta…</p>;
  }

  // `geracao_disponivel` vem do servidor: sem python-pptx lá, gerar
  // gravaria a versão no banco e falharia no download — versão fantasma que
  // ninguém consegue baixar.
  const servidorGera = padrao?.geracao_disponivel !== false;

  const podeGerar = servidorGera
    && Number(vidas) >= 1
    && Number(String(valorVida).replace(',', '.')) > 0
    && escopo.some((i) => i.trim())
    && dataProposta && validade && validade >= dataProposta;

  return (
    <div className="space-y-6">
      {erro && <AlertMessage tipo="erro">{erro}</AlertMessage>}

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">

        {/* ── Formulário ── */}
        <div className="space-y-4">
          <div>
            <h3 className="text-sm font-semibold text-hipo-ink">Nova proposta</h3>
            <p className="text-xs text-hipo-slate mt-0.5">
              Cliente e contato do executivo saem do cadastro — não se digitam aqui.
            </p>
          </div>

          <div className="grid grid-cols-2 gap-3">
            <Input
              label="Qtde. de vidas"
              type="number"
              min="1"
              value={vidas}
              onChange={(e) => setVidas(e.target.value)}
            />
            <Input
              label="Valor por vida (R$)"
              type="number"
              min="0"
              step="0.01"
              value={valorVida}
              onChange={(e) => setValorVida(e.target.value)}
            />
            <Input
              label="Treinamentos (R$)"
              type="number"
              min="0"
              step="0.01"
              value={treinamentos}
              onChange={(e) => setTreinamentos(e.target.value)}
            />
            <Input
              label="Laudos / outros (R$)"
              type="number"
              min="0"
              step="0.01"
              value={laudos}
              onChange={(e) => setLaudos(e.target.value)}
            />
          </div>

          {/*
            Os totais aparecem como texto, não como campo: são derivados, e
            um input com valor calculado convida a digitar por cima.
          */}
          <dl className="rounded-lg border border-hipo-border bg-hipo-bg/40 px-3 py-2 text-sm">
            <div className="flex justify-between">
              <dt className="text-hipo-slate">Mensalidade</dt>
              <dd className="font-medium text-hipo-ink" data-testid="calc-mensalidade">
                {formatarMoeda(totais.mensal)}
              </dd>
            </div>
            <div className="flex justify-between mt-1 pt-1 border-t border-hipo-border">
              <dt className="font-medium text-hipo-ink">Investimento</dt>
              <dd className="font-semibold text-hipo-blue" data-testid="calc-investimento">
                {formatarMoeda(totais.investimento)}
              </dd>
            </div>
          </dl>

          <div className="grid grid-cols-2 gap-3">
            <Input
              label="Data da proposta"
              type="date"
              value={dataProposta}
              onChange={(e) => {
                setDataProposta(e.target.value);
                // A validade acompanha a data quando o usuário troca o dia
                // da proposta: manter o vencimento antigo produziria
                // proposta que nasce vencida.
                if (padrao) setValidade(somarDiasISO(e.target.value, padrao.dias_validade));
              }}
            />
            <Input
              label="Válida até"
              type="date"
              min={dataProposta}
              value={validade}
              onChange={(e) => setValidade(e.target.value)}
              hint={`Padrão: ${padrao?.dias_validade ?? 10} dias`}
            />
          </div>

          <Input
            label="Cidade"
            value={cidade}
            onChange={(e) => setCidade(e.target.value)}
            hint="Sai antes da data no slide de fechamento"
          />

          {/* ── Escopo ── */}
          <div>
            <div className="flex items-center justify-between mb-1.5">
              <label className="text-sm font-medium text-hipo-ink">
                Escopo da proposta
              </label>
              <Button
                size="sm"
                variant="ghost"
                icon={Plus}
                onClick={() => setEscopo((a) => [...a, ''])}
              >
                Item
              </Button>
            </div>
            <ul className="space-y-1.5">
              {escopo.map((item, i) => (
                // eslint-disable-next-line react/no-array-index-key
                <li key={i} className="flex items-center gap-1.5">
                  <input
                    aria-label={`Item ${i + 1} do escopo`}
                    value={item}
                    onChange={(e) => trocarItem(i, e.target.value)}
                    className="flex-1 min-w-0 h-8 px-2 text-xs rounded-lg border border-hipo-border bg-hipo-card text-hipo-ink focus:outline-none focus:ring-2 focus:ring-hipo-blue"
                  />
                  <button
                    type="button"
                    onClick={() => removerItem(i)}
                    aria-label={`Remover item ${i + 1}`}
                    className="h-8 w-8 shrink-0 inline-flex items-center justify-center rounded-lg border border-hipo-border text-hipo-slate hover:bg-hipo-bg transition-colors"
                  >
                    <X size={13} />
                  </button>
                </li>
              ))}
            </ul>
            {escopo.length === 0 && (
              <p className="text-xs text-hipo-muted mt-1">
                Sem itens — a proposta precisa de pelo menos um.
              </p>
            )}
          </div>

          {!servidorGera && (
            <AlertMessage tipo="erro">
              O servidor está sem a biblioteca que monta o arquivo
              (python-pptx), então a proposta não pode ser gerada agora.
              Avise quem cuida da infraestrutura.
            </AlertMessage>
          )}

          <Button
            onClick={gerar}
            disabled={!podeGerar || gerando}
            loading={gerando}
            icon={gerando ? Loader2 : FileText}
          >
            {gerando ? 'Gerando…' : 'Gerar proposta'}
          </Button>
          <p className="text-xs text-hipo-muted">
            Gerar cria a versão {(versoes[0]?.versao ?? 0) + 1} e baixa o PPTX.
          </p>
        </div>

        {/* ── Versões ── */}
        <div className="space-y-3">
          <h3 className="text-sm font-semibold text-hipo-ink flex items-center gap-1.5">
            <History size={14} aria-hidden="true" />
            Versões geradas
          </h3>

          {versoes.length === 0 ? (
            <Empty
              title="Nenhuma proposta gerada"
              description="A primeira versão aparece aqui assim que você gerar."
              icon={FileText}
            />
          ) : (
            <ul className="space-y-2" aria-label="Versões da proposta">
              {versoes.map((p) => (
                <Versao
                  key={p.id}
                  proposta={p}
                  ocupado={Boolean(baixando)}
                  pdfDisponivel={padrao?.pdf_disponivel}
                  onBaixar={baixar}
                />
              ))}
            </ul>
          )}

          {padrao && !padrao.pdf_disponivel && (
            <p className="text-xs text-hipo-muted">
              O PDF não está disponível neste servidor. Baixe o PPTX e exporte
              pelo PowerPoint.
            </p>
          )}
          {padrao && !padrao.executivo_telefone && (
            <AlertMessage tipo="aviso">
              Seu telefone não está no cadastro, então o slide sai com um
              travessão no lugar. Preencha em Perfil.
            </AlertMessage>
          )}
        </div>
      </div>
    </div>
  );
}
