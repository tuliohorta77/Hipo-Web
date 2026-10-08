// web/src/components/crm/AbaProposta.jsx
//
// A proposta comercial, dentro da oportunidade.
//
// ── O que esta aba faz ───────────────────────────────────────────────
// Preenche os slides variáveis do material da Controller MedSeg e devolve
// o arquivo pronto. Os slides 1 a 4 são institucionais e ninguém edita.
//
// ── Vários CNPJs (042) ───────────────────────────────────────────────
// Cliente com vários CNPJs é UMA negociação. A lista "CNPJs da proposta"
// mostra o CNPJ principal da oportunidade e os adicionais; adicionar um
// CNPJ aqui o VINCULA à oportunidade na hora (é isso que faz a conta da
// filial mostrar que está nesta negociação). Cada CNPJ tem suas vidas e
// sua mensalidade; a mensalidade da proposta é a soma.
//
// Duas modalidades:
//   * Tabela por faixa — o valor de cada CNPJ vem da tabela de preços
//     (até 5 vidas R$ 180, ...) e pode ser negociado; a tela mostra o
//     desconto contra a tabela. A TABELA NÃO VAI PARA O CLIENTE (051): no
//     arquivo, cada CNPJ mostra a faixa ("16 a 20 vidas"), e o rodapé o
//     valor por vida excedente que o EV escolheu aqui.
//   * Valor por vida — vidas x valor por vida, derivado (não se digita).
//
// O arquivo sai consolidado (todos os CNPJs, no estilo do material
// "VARIOS CNPJs") ou só de um CNPJ, pela lista da versão.
//
// ── Ver e aprovar (051) ──────────────────────────────────────────────
// Gerar abre o visualizador (VisualizadorProposta): o EV vê o PDF que o
// cliente vai receber e aprova. Só versão aprovada vai anexada na aba
// E-mails — o vendedor não precisa mais baixar e abrir no PC.
//
// ── Por que versão, e não edição ─────────────────────────────────────
// Proposta enviada não se corrige: se refaz. Cada geração vira uma versão
// nova, com quem gerou e quando, e as anteriores continuam baixáveis — é o
// que responde "o que a gente mandou primeiro" quando o cliente questiona
// o desconto duas semanas depois.

import { useCallback, useEffect, useMemo, useState } from 'react';
import {
  FileText, Plus, X, Download, FileType2, Loader2, History, Building2,
  ChevronDown, ChevronRight, Send, Eye, FileSignature,
} from 'lucide-react';

import api from '../../api';
import Input from '../ui/Input';
import Button from '../ui/Button';
import Badge from '../ui/Badge';
import Empty from '../ui/Empty';
import AlertMessage from '../ui/AlertMessage';
import EntityPicker from '../EntityPicker';
import TabelaPrecos from './TabelaPrecos';
import VisualizadorProposta from './VisualizadorProposta';
import {
  numero, valorTabela, descontoPercentual, mensalidadeDaLinha,
} from './propostaCalculo';

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

function formatarPct(n) {
  return `${String(n).replace('.', ',')}%`;
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

const CAMPO = 'h-8 px-2 text-xs rounded-lg border border-hipo-border bg-hipo-card text-hipo-ink focus:outline-none focus:ring-2 focus:ring-hipo-blue';

// Vidas sugeridas para um CNPJ que entra na lista: a da última proposta,
// senão a que o CLIENTE declarou no cadastro. Estimativa de fonte paga
// nunca precifica (ver claude/econodata-quadro-de-pessoal-confiabilidade.md).
function vidasSugeridas(cnpj, ultimos) {
  const anterior = ultimos.find((i) => i.conta_id === cnpj.conta_id);
  if (anterior) return String(anterior.vidas);
  if (cnpj.num_funcionarios_origem === 'declarado' && cnpj.num_funcionarios > 0) {
    return String(cnpj.num_funcionarios);
  }
  return '';
}

// Junta a lista de CNPJs da oportunidade com o que já estava digitado:
// vincular ou desvincular um CNPJ não pode apagar as vidas dos outros.
function mesclarLinhas(cnpjs, atuais, ultimos) {
  return cnpjs.map((c) => {
    const ja = atuais.find((l) => l.conta_id === c.conta_id);
    if (ja) return { ...ja, cnpj: c };
    const anterior = ultimos.find((i) => i.conta_id === c.conta_id);
    return {
      conta_id: c.conta_id,
      cnpj: c,
      // Na primeira abertura entra quem estava na última proposta (ou
      // todos, se não houve proposta). CNPJ que entra depois, entra marcado.
      incluir: ultimos.length === 0 || Boolean(anterior) || atuais.length > 0,
      vidas: vidasSugeridas(c, ultimos),
      valor: anterior && anterior.valor_tabela !== null
        && Number(anterior.mensalidade) !== Number(anterior.valor_tabela)
        ? String(anterior.mensalidade)
        : '',
    };
  });
}

// ── Seletor de modalidade ────────────────────────────────────────────

function Modalidade({ valor, onChange }) {
  const opcoes = [
    { id: 'tabela', rotulo: 'Tabela por faixa' },
    { id: 'por_vida', rotulo: 'Valor por vida' },
  ];
  return (
    <div role="radiogroup" aria-label="Modalidade de preço" className="inline-flex rounded-lg border border-hipo-border overflow-hidden">
      {opcoes.map((o) => (
        <button
          key={o.id}
          type="button"
          role="radio"
          aria-checked={valor === o.id}
          onClick={() => onChange(o.id)}
          className={
            'px-3 h-8 text-xs font-medium transition-colors '
            + (valor === o.id
              ? 'bg-hipo-blue text-white'
              : 'bg-hipo-card text-hipo-slate hover:bg-hipo-bg')
          }
        >
          {o.rotulo}
        </button>
      ))}
    </div>
  );
}

// ── Uma linha de CNPJ ────────────────────────────────────────────────

function LinhaCnpj({
  linha, modalidade, valorPorVida, faixas, ocupado, onTrocar, onRemover,
}) {
  const { cnpj } = linha;
  const vidas = Number(linha.vidas);
  const tabela = modalidade === 'tabela' ? valorTabela(vidas, faixas) : null;
  const mensal = mensalidadeDaLinha({
    modalidade, vidas: linha.vidas, valorNegociado: linha.valor, valorPorVida, faixas,
  });
  const desconto = modalidade === 'tabela' ? descontoPercentual(mensal, tabela) : null;
  const rotulo = cnpj.nome_fantasia || cnpj.razao_social;

  return (
    <li
      className={
        'border border-hipo-border rounded-lg p-2.5 '
        + (linha.incluir ? 'bg-hipo-card' : 'bg-hipo-bg/40 opacity-70')
      }
      data-testid={`linha-${cnpj.conta_id}`}
    >
      <div className="flex items-start gap-2">
        <input
          type="checkbox"
          className="mt-1"
          aria-label={`Incluir ${rotulo} na proposta`}
          checked={linha.incluir}
          onChange={(e) => onTrocar({ incluir: e.target.checked })}
        />
        <div className="min-w-0 flex-1">
          <div className="flex items-center gap-1.5 min-w-0">
            <span className="text-sm font-medium text-hipo-ink truncate" title={cnpj.razao_social}>
              {cnpj.razao_social}
            </span>
            {cnpj.principal && <Badge tone="info">Principal</Badge>}
          </div>
          <p className="text-[11px] text-hipo-slate font-mono">{cnpj.cnpj_formatado}</p>
        </div>
        {!cnpj.principal && (
          <button
            type="button"
            disabled={ocupado}
            onClick={onRemover}
            aria-label={`Tirar ${rotulo} da oportunidade`}
            title="Tirar este CNPJ da oportunidade"
            className="h-7 w-7 shrink-0 inline-flex items-center justify-center rounded-lg border border-hipo-border text-hipo-slate hover:bg-hipo-bg disabled:opacity-50"
          >
            <X size={12} />
          </button>
        )}
      </div>

      {linha.incluir && (
        <div className="mt-2 flex flex-wrap items-end gap-2 pl-6">
          <label className="text-[11px] text-hipo-slate">
            Vidas
            <input
              aria-label={`Vidas de ${rotulo}`}
              type="number"
              min="1"
              value={linha.vidas}
              onChange={(e) => onTrocar({ vidas: e.target.value })}
              className={`${CAMPO} block w-20 mt-0.5`}
            />
          </label>

          {modalidade === 'tabela' ? (
            <label className="text-[11px] text-hipo-slate">
              Mensalidade (R$)
              <input
                aria-label={`Mensalidade de ${rotulo}`}
                type="number"
                min="0"
                step="0.01"
                placeholder={tabela !== null ? String(tabela.toFixed(2)) : 'tabela'}
                value={linha.valor}
                onChange={(e) => onTrocar({ valor: e.target.value })}
                className={`${CAMPO} block w-28 mt-0.5`}
              />
            </label>
          ) : null}

          <div className="text-xs text-hipo-ink pb-1.5 min-w-0">
            <span className="font-semibold" data-testid={`mensal-${cnpj.conta_id}`}>
              {mensal === null ? '—' : formatarMoeda(mensal)}
            </span>
            {modalidade === 'tabela' && tabela !== null && (
              <span className="text-hipo-muted"> · tabela {formatarMoeda(tabela)}</span>
            )}
            {desconto !== null && (
              <Badge tone="warning" className="ml-1.5">
                −{formatarPct(desconto)}
              </Badge>
            )}
            {modalidade === 'tabela' && mensal !== null && tabela !== null && mensal > tabela && (
              <Badge tone="neutral" className="ml-1.5">acima da tabela</Badge>
            )}
          </div>
        </div>
      )}
    </li>
  );
}

// ── Uma versão na lista ──────────────────────────────────────────────

function BotoesArquivo({
  ocupado, pdfDisponivel, aprovada, onBaixar, onEnviar, onVer, onContrato,
}) {
  return (
    <div className="flex flex-wrap justify-end gap-1 shrink-0">
      {/*
        051: "Ver" abre o visualizador do HIPO — conferir não exige mais
        baixar e abrir no PC. É lá que o EV aprova.
      */}
      {onVer && (
        <Button size="sm" variant={aprovada ? 'secondary' : 'primary'} icon={Eye}
          disabled={ocupado} onClick={onVer}>
          {aprovada ? 'Ver' : 'Ver e aprovar'}
        </Button>
      )}
      {/*
        050: a proposta vai por e-mail em PDF, da caixa do vendedor. Mesma
        regra do botão de PDF: sem LibreOffice no servidor, não há anexo, e
        o botão não aparece. 051: e só depois do ok do EV.
      */}
      {onEnviar && pdfDisponivel && aprovada && (
        <Button size="sm" variant="secondary" icon={Send} disabled={ocupado}
          onClick={onEnviar} aria-label="Enviar por e-mail">
          E-mail
        </Button>
      )}
      {/*
        053: o contrato para assinatura eletrônica nasce de uma versão
        aprovada. Só na proposta consolidada: o contrato é um só, com todos
        os CNPJs.
      */}
      {onContrato && aprovada && (
        <Button size="sm" variant="secondary" icon={FileSignature} disabled={ocupado}
          onClick={onContrato} aria-label="Enviar contrato para assinatura">
          Contrato
        </Button>
      )}
      <Button size="sm" variant="secondary" icon={Download} disabled={ocupado}
        onClick={() => onBaixar('pptx')}>
        PPTX
      </Button>
      {/*
        O botão de PDF só aparece onde o servidor tem LibreOffice. O back
        diz se tem (pdf_disponivel) — oferecer o download e falhar depois
        do clique seria pior do que não oferecer.
      */}
      {pdfDisponivel && (
        <Button size="sm" variant="secondary" icon={FileType2} disabled={ocupado}
          onClick={() => onBaixar('pdf')}>
          PDF
        </Button>
      )}
    </div>
  );
}

function Versao({ proposta, ocupado, pdfDisponivel, onBaixar, onEnviar, onVer, onContrato }) {
  const [aberta, setAberta] = useState(false);
  const itens = proposta.itens || [];
  const varios = itens.length > 1;

  return (
    <li className="border border-hipo-border rounded-lg p-3 bg-hipo-card">
      <div className="flex items-start gap-2">
        <div className="flex flex-col items-start gap-1 shrink-0">
          <Badge tone="info">v{proposta.versao}</Badge>
        </div>
        <div className="min-w-0 flex-1">
          <p className="text-sm font-medium text-hipo-ink">
            {formatarMoeda(proposta.investimento)}
            <span className="text-xs font-normal text-hipo-slate">
              {' '}· {proposta.vidas} vida{proposta.vidas === 1 ? '' : 's'}
              {proposta.modalidade === 'por_vida' && proposta.valor_por_vida
                ? <> a {formatarMoeda(proposta.valor_por_vida)}</>
                : null}
              {varios ? <> · {itens.length} CNPJs</> : null}
            </span>
          </p>
          <p className="text-xs text-hipo-slate mt-0.5">
            {proposta.modalidade === 'tabela' ? 'Tabela por faixa' : 'Valor por vida'}
            {' · '}{formatarData(proposta.data_proposta)} · válida até{' '}
            {formatarData(proposta.validade)}
          </p>
          <p className="text-[11px] text-hipo-muted mt-0.5 truncate">
            {proposta.executivo_nome}
            {proposta.criado_por_nome
              && proposta.criado_por_nome !== proposta.executivo_nome
              && ` · gerada por ${proposta.criado_por_nome}`}
          </p>
          <p className="mt-1">
            {proposta.aprovada_em ? (
              <Badge tone="success">
                Aprovada{proposta.aprovada_por_nome ? ` por ${proposta.aprovada_por_nome}` : ''}
              </Badge>
            ) : (
              <Badge tone="warning">Aguardando aprovação</Badge>
            )}
          </p>
        </div>
        <BotoesArquivo
          ocupado={ocupado}
          pdfDisponivel={pdfDisponivel}
          aprovada={Boolean(proposta.aprovada_em)}
          onBaixar={(formato) => onBaixar(proposta, formato)}
          onEnviar={onEnviar ? () => onEnviar(proposta) : undefined}
          onVer={onVer ? () => onVer(proposta) : undefined}
          onContrato={onContrato ? () => onContrato(proposta) : undefined}
        />
      </div>

      {varios && (
        <div className="mt-2 border-t border-hipo-border pt-2">
          <button
            type="button"
            onClick={() => setAberta((a) => !a)}
            aria-expanded={aberta}
            className="text-xs text-hipo-blue inline-flex items-center gap-1 hover:underline"
          >
            {aberta ? <ChevronDown size={12} /> : <ChevronRight size={12} />}
            Proposta por CNPJ
          </button>
          {aberta && (
            <ul className="mt-2 space-y-1.5" aria-label={`CNPJs da versão ${proposta.versao}`}>
              {itens.map((i) => (
                <li key={i.id || i.cnpj} className="flex items-center gap-2">
                  <div className="min-w-0 flex-1">
                    <p className="text-xs text-hipo-ink truncate" title={i.razao_social}>
                      {i.razao_social}
                    </p>
                    <p className="text-[11px] text-hipo-slate">
                      {i.cnpj_formatado} · {i.vidas} vida{i.vidas === 1 ? '' : 's'} ·{' '}
                      {formatarMoeda(i.mensalidade)}
                      {i.desconto_percentual !== null && i.desconto_percentual !== undefined && (
                        <> · −{formatarPct(i.desconto_percentual)}</>
                      )}
                    </p>
                  </div>
                  {i.id && (
                    <BotoesArquivo
                      ocupado={ocupado}
                      pdfDisponivel={pdfDisponivel}
                      aprovada={Boolean(proposta.aprovada_em)}
                      onBaixar={(formato) => onBaixar(proposta, formato, i)}
                      onEnviar={onEnviar ? () => onEnviar(proposta, i) : undefined}
                      onVer={onVer ? () => onVer(proposta, i) : undefined}
                    />
                  )}
                </li>
              ))}
            </ul>
          )}
        </div>
      )}
    </li>
  );
}

// ── Aba ──────────────────────────────────────────────────────────────

export default function AbaProposta({
  oportunidade, onGerada, onCnpjsMudaram, onEnviarPorEmail, onEnviarContrato,
}) {
  const [padrao, setPadrao] = useState(null);
  const [versoes, setVersoes] = useState([]);
  const [carregando, setCarregando] = useState(true);
  const [gerando, setGerando] = useState(false);
  const [baixando, setBaixando] = useState(null);
  const [vinculando, setVinculando] = useState(false);
  const [erro, setErro] = useState(null);
  const [chavePicker, setChavePicker] = useState(0);

  const [modalidade, setModalidade] = useState('tabela');
  const [linhas, setLinhas] = useState([]);
  const [tabela, setTabela] = useState(null);
  const [valorVida, setValorVida] = useState('');
  const [excedente, setExcedente] = useState('');
  const [visualizando, setVisualizando] = useState(null);
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
      const d = p.data;
      setPadrao(d);
      setVersoes(lista.data);
      setTabela(d.tabela || null);

      const hoje = hojeLocalISO();
      setCidade(d.cidade);
      setDataProposta(hoje);
      setValidade(somarDiasISO(hoje, d.dias_validade));
      setEscopo(d.escopo_padrao);
      setModalidade(d.modalidade || 'tabela');
      // A última proposta é o ponto de partida do "ajustar o desconto":
      // muda um valor, o resto continua igual.
      if (d.valor_por_vida != null) setValorVida(String(d.valor_por_vida));
      // 051: o excedente da última proposta, ou a sugestão da tabela.
      if (d.valor_vida_excedente != null) setExcedente(String(d.valor_vida_excedente));

      const ultimos = d.ultimos_itens || [];
      const cnpjs = d.cnpjs || [];
      const iniciais = mesclarLinhas(cnpjs, [], ultimos);
      // Proposta antiga de um CNPJ só, sem itens: as vidas dela vão para o
      // principal, como antes da 042.
      if (!ultimos.length && d.vidas != null && iniciais[0] && !iniciais[0].vidas) {
        iniciais[0] = { ...iniciais[0], vidas: String(d.vidas) };
      }
      setLinhas(iniciais);
    } catch (err) {
      setErro(mensagemDeErro(err, 'Não foi possível carregar a proposta.'));
    } finally {
      setCarregando(false);
    }
  }, [oportunidade.id]);

  useEffect(() => { carregar(); }, [carregar]);

  const faixas = tabela?.faixas || [];
  const incluidas = linhas.filter((l) => l.incluir);

  // Os mesmos cálculos do backend, para o vendedor ver o total ANTES de
  // gerar. O servidor recalcula na hora de gravar.
  const totais = useMemo(() => {
    let mensal = 0;
    let vidas = 0;
    let completo = incluidas.length > 0;
    for (const l of incluidas) {
      const m = mensalidadeDaLinha({
        modalidade, vidas: l.vidas, valorNegociado: l.valor, valorPorVida: valorVida, faixas,
      });
      if (m === null) completo = false;
      mensal += m || 0;
      vidas += Number(l.vidas) || 0;
    }
    const extra = (n) => (Number.isFinite(numero(n)) ? numero(n) : 0);
    return {
      mensal, vidas, completo, investimento: mensal + extra(treinamentos) + extra(laudos),
    };
  }, [incluidas, modalidade, valorVida, faixas, treinamentos, laudos]);

  function trocarLinha(contaId, mudanca) {
    setLinhas((atual) => atual.map((l) => (l.conta_id === contaId ? { ...l, ...mudanca } : l)));
  }

  function trocarItem(i, texto) {
    setEscopo((atual) => atual.map((item, idx) => (idx === i ? texto : item)));
  }

  function removerItem(i) {
    setEscopo((atual) => atual.filter((_, idx) => idx !== i));
  }

  // Vincular é imediato: a conta passa a mostrar a oportunidade mesmo que
  // ninguém gere proposta hoje.
  async function vincular(conta) {
    if (!conta) return;
    setVinculando(true);
    setErro(null);
    try {
      const { data } = await api.post(
        `/crm/oportunidades/${oportunidade.id}/cnpjs`,
        { conta_id: conta.id },
      );
      setLinhas((atual) => mesclarLinhas(data, atual, padrao?.ultimos_itens || []));
      onCnpjsMudaram?.(data);
    } catch (err) {
      setErro(mensagemDeErro(err, 'Não foi possível adicionar o CNPJ.'));
    } finally {
      setVinculando(false);
      setChavePicker((k) => k + 1);
    }
  }

  async function desvincular(linha) {
    setVinculando(true);
    setErro(null);
    try {
      const { data } = await api.delete(
        `/crm/oportunidades/${oportunidade.id}/cnpjs/${linha.conta_id}`,
      );
      setLinhas((atual) => mesclarLinhas(data, atual, padrao?.ultimos_itens || []));
      onCnpjsMudaram?.(data);
    } catch (err) {
      setErro(mensagemDeErro(err, 'Não foi possível tirar o CNPJ.'));
    } finally {
      setVinculando(false);
    }
  }

  async function gerar() {
    setGerando(true);
    setErro(null);
    try {
      const corpo = {
        modalidade,
        itens: incluidas.map((l) => {
          const item = { conta_id: l.conta_id, vidas: Number(l.vidas) };
          const negociado = numero(l.valor);
          if (modalidade === 'tabela' && Number.isFinite(negociado)) item.mensalidade = negociado;
          return item;
        }),
        treinamentos: numero(treinamentos) || 0,
        laudos: numero(laudos) || 0,
        escopo: escopo.map((i) => i.trim()).filter(Boolean),
        data_proposta: dataProposta,
        validade,
        cidade: cidade.trim(),
      };
      if (modalidade === 'por_vida') corpo.valor_por_vida = numero(valorVida);
      else corpo.valor_vida_excedente = numero(excedente);

      const { data } = await api.post(
        `/crm/oportunidades/${oportunidade.id}/propostas`, corpo,
      );
      setVersoes((atual) => [data, ...atual]);
      // A mensalidade da oportunidade muda junto no backend; avisar o pai
      // é o que mantém o cartão do funil e o trilho coerentes com o que
      // acabou de ser gerado.
      onGerada?.(data);
      // 051: em vez de baixar, abre o visualizador — o EV confere aqui e
      // aprova, sem sair do HIPO.
      setVisualizando({ proposta: data, item: null });
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
    sabe o número da oportunidade, a versão e o CNPJ.
  */
  async function baixar(proposta, formato, item = null) {
    setBaixando(`${proposta.id}-${item?.id || 'todos'}-${formato}`);
    setErro(null);
    try {
      const params = { formato };
      if (item) params.item = item.id;
      const resp = await api.get(`/crm/propostas/${proposta.id}/arquivo`, {
        params,
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
  const jaNaLista = new Set(linhas.map((l) => l.conta_id));

  const podeGerar = servidorGera
    && incluidas.length > 0
    && incluidas.every((l) => Number(l.vidas) >= 1)
    && (modalidade !== 'por_vida' || numero(valorVida) > 0)
    && (modalidade !== 'tabela' || numero(excedente) > 0)
    && totais.completo && totais.mensal > 0
    && escopo.some((i) => i.trim())
    && dataProposta && validade && validade >= dataProposta;

  return (
    <div className="space-y-6">
      {erro && <AlertMessage tipo="erro">{erro}</AlertMessage>}

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">

        {/* ── Formulário ── */}
        <div className="space-y-4">
          <div className="flex flex-wrap items-start justify-between gap-2">
            <div>
              <h3 className="text-sm font-semibold text-hipo-ink">Nova proposta</h3>
              <p className="text-xs text-hipo-slate mt-0.5">
                Cliente e contato do executivo saem do cadastro — não se digitam aqui.
              </p>
            </div>
            <Modalidade valor={modalidade} onChange={setModalidade} />
          </div>

          {modalidade === 'por_vida' && (
            <div className="max-w-[12rem]">
              <Input
                label="Valor por vida (R$)"
                type="number"
                min="0"
                step="0.01"
                value={valorVida}
                onChange={(e) => setValorVida(e.target.value)}
              />
            </div>
          )}

          {/*
            051: na modalidade tabela, o que cada vida acima do plano
            acrescenta. Sai no rodapé da proposta ("Para cada vida adicional,
            será acrescido o valor de R$ 15,00 mensais"). A tabela de preço
            em si não vai para o cliente.
          */}
          {modalidade === 'tabela' && (
            <div className="max-w-[16rem]">
              <Input
                label="Valor por vida excedente (R$)"
                type="number"
                min="0"
                step="0.01"
                value={excedente}
                onChange={(e) => setExcedente(e.target.value)}
                hint={tabela?.excedente_padrao
                  ? `Tabela: ${formatarMoeda(tabela.excedente_padrao)} por vida acima do plano`
                  : 'Por vida acima do plano escolhido'}
              />
            </div>
          )}

          {/* ── CNPJs ── */}
          <section aria-label="CNPJs da proposta" className="space-y-2">
            <div className="flex items-center justify-between">
              <h4 className="text-sm font-medium text-hipo-ink flex items-center gap-1.5">
                <Building2 size={14} aria-hidden="true" />
                CNPJs da proposta
                <span className="text-xs font-normal text-hipo-slate">
                  ({incluidas.length} de {linhas.length})
                </span>
              </h4>
            </div>
            <ul className="space-y-1.5">
              {linhas.map((l) => (
                <LinhaCnpj
                  key={l.conta_id}
                  linha={l}
                  modalidade={modalidade}
                  valorPorVida={valorVida}
                  faixas={faixas}
                  ocupado={vinculando}
                  onTrocar={(m) => trocarLinha(l.conta_id, m)}
                  onRemover={() => desvincular(l)}
                />
              ))}
            </ul>
            <EntityPicker
              key={chavePicker}
              label="Adicionar CNPJ do mesmo cliente"
              value={null}
              onChange={vincular}
              disabled={vinculando}
              buscar={async (q) => {
                const { data } = await api.get('/crm/contas/busca', { params: { q } });
                return data;
              }}
              paraItem={(c) => {
                let motivo;
                if (jaNaLista.has(c.id)) motivo = 'já na proposta';
                else if (c.ativo === false) motivo = 'desativada';
                else if (c.nao_prospectar) motivo = 'bloqueada';
                return {
                  id: c.id,
                  titulo: c.razao_social,
                  subtitulo: c.cnpj_formatado,
                  desabilitado: Boolean(motivo),
                  motivoDesabilitado: motivo,
                };
              }}
              criar={{
                titulo: 'Cadastrar CNPJ novo',
                campos: [
                  { nome: 'cnpj', label: 'CNPJ', obrigatorio: true },
                  { nome: 'razao_social', label: 'Razão social', obrigatorio: true },
                ],
                onSubmit: async (dados) => {
                  const { data } = await api.post('/crm/contas', dados);
                  return data;
                },
              }}
              placeholder="Buscar por razão social ou CNPJ…"
              hint="O CNPJ passa a fazer parte desta oportunidade — a conta dele mostra o vínculo."
            />
          </section>

          <div className="grid grid-cols-2 gap-3">
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
              <dt className="text-hipo-slate">
                Mensalidade
                <span className="text-xs"> · {totais.vidas} vida{totais.vidas === 1 ? '' : 's'}</span>
              </dt>
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
            {incluidas.length > 1 && (
              <p className="text-[11px] text-hipo-muted mt-1">
                Na proposta consolidada, cada CNPJ entra como uma linha depois do escopo.
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
            Gerar cria a versão {(versoes[0]?.versao ?? 0) + 1} e abre a proposta
            para você conferir e aprovar. Só proposta aprovada vai por e-mail.
          </p>
        </div>

        {/* ── Versões e tabela ── */}
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
                  onEnviar={onEnviarPorEmail}
                  onContrato={onEnviarContrato}
                  onVer={(prop, item) => setVisualizando({ proposta: prop, item: item || null })}
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

          {modalidade === 'tabela' && (
            <TabelaPrecos tabela={tabela} onSalva={setTabela} />
          )}
        </div>
      </div>

      <VisualizadorProposta
        proposta={visualizando?.proposta || null}
        itemInicial={visualizando?.item || null}
        pdfDisponivel={padrao?.pdf_disponivel}
        onFechar={() => setVisualizando(null)}
        onBaixar={baixar}
        onAprovada={(aprovada) => {
          setVersoes((atual) => atual.map((v) => (v.id === aprovada.id ? aprovada : v)));
          setVisualizando((v) => (v ? { ...v, proposta: aprovada } : v));
        }}
      />
    </div>
  );
}
