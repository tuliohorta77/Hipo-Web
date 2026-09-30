// web/src/components/monitor/RperMonitor.jsx
//
// O RPeR — Reunião de Planejamento e Resultados — gerado do HIPO.
//
// Todo 1º dia útil do mês o time comercial se reúne em cima de um PPT com
// o resultado do mês fechado e o planejamento do seguinte. Esta tela faz
// duas coisas, uma por aba:
//
//   * GERAR: escolhe o mês fechado, mostra os números que vão para o PPT
//     (a mesma montagem do arquivo, sem a IA) e baixa o .pptx/.pdf pronto.
//     Ver antes de baixar é a diretriz 2: a tela é painel e ferramenta ao
//     mesmo tempo — quem vai apresentar confere o número aqui.
//   * METAS: a meta do SQUAD e a meta de CADA PESSOA, por mês. A do squad é
//     lançada à parte e não é a soma das pessoas (decisão do Tulio, 29/09):
//     férias, rampa e vaga aberta fazem as duas divergirem.
//
// Fica no Monitor porque é o mesmo assunto — meta e resultado do mês — e
// porque é de gestão, como "Metas e calendário". O backend recusa (403) a
// quem não é; aqui a tela só não oferece o botão.

import { useCallback, useEffect, useMemo, useState } from 'react';
import { Copy, Download, FileText, Sparkles } from 'lucide-react';

import api from '../../api';
import Modal from '../ui/Modal';
import Button from '../ui/Button';
import Tabs from '../ui/Tabs';
import AlertMessage from '../ui/AlertMessage';
import { mensagemDeErro } from '../crm/tarefaComum';

const MESES = [
  'janeiro', 'fevereiro', 'março', 'abril', 'maio', 'junho',
  'julho', 'agosto', 'setembro', 'outubro', 'novembro', 'dezembro',
];

const SQUADS = ['EC', 'SDR', 'EV'];

const COR_CARINHA = {
  muito_feliz: 'text-hipo-success',
  feliz: 'text-hipo-success',
  neutro: 'text-hipo-warning',
  triste: 'text-hipo-danger',
  bravo: 'text-hipo-danger',
};

const DICA_FORMATO = { moeda: 'R$', percentual: '%', inteiro: 'qtd' };

export function rotuloMes(ano, mes) {
  return `${MESES[mes - 1]}/${ano}`;
}

export function mesSeguinte(ano, mes) {
  return mes === 12 ? { ano: ano + 1, mes: 1 } : { ano, mes: mes + 1 };
}

/*
  Os últimos `quantos` meses a partir de {ano, mes}, do mais recente para o
  mais antigo. A lista é gerada aqui e não pedida ao servidor: é
  calendário, não dado.
*/
export function mesesAnteriores(ano, mes, quantos = 12) {
  const saida = [];
  let a = ano;
  let m = mes;
  for (let i = 0; i < quantos; i += 1) {
    saida.push({ ano: a, mes: m, valor: `${a}-${m}` });
    m -= 1;
    if (m === 0) { m = 12; a -= 1; }
  }
  return saida;
}

/*
  Texto do input → número para o PUT. Vazio apaga. Vírgula é decimal, como
  se digita aqui; ponto só vira milhar quando está no formato de milhar
  ("7.200", "1.234,50") — "1.5" continua sendo um e meio.
*/
export function numeroDoCampo(texto) {
  let t = (texto ?? '').trim().replace(/^R\$\s*/, '').replace(/%$/, '');
  if (t === '') return null;
  if (/^\d{1,3}(\.\d{3})+(,\d+)?$/.test(t)) t = t.replace(/\./g, '');
  const n = Number(t.replace(',', '.'));
  return Number.isNaN(n) || n < 0 ? NaN : n;
}

function textoDoValor(v) {
  return v === null || v === undefined ? '' : String(v).replace('.', ',');
}

// Blob.text() não existe em todo navegador que a equipe usa (nem no jsdom
// dos testes); o FileReader existe em todos.
function lerBlob(blob) {
  if (typeof blob.text === 'function') return blob.text();
  return new Promise((resolve, reject) => {
    const leitor = new FileReader();
    leitor.onload = () => resolve(String(leitor.result));
    leitor.onerror = reject;
    leitor.readAsText(blob);
  });
}

async function mensagemDeBlob(err, padrao) {
  // Erro em blob chega como Blob, não como JSON — mesma armadilha do
  // download da proposta (AbaProposta.jsx).
  const corpo = err?.response?.data;
  if (corpo instanceof Blob) {
    try {
      return JSON.parse(await lerBlob(corpo)).detail || padrao;
    } catch {
      return padrao;
    }
  }
  return mensagemDeErro(err, padrao);
}

// ── Aba Gerar ────────────────────────────────────────────────────────

function AbaGerar({ status }) {
  const opcoes = useMemo(
    () => {
      if (!status) return [];
      // O mês CORRENTE entra no topo como prévia parcial: a reunião é no
      // 1º dia útil, mas a gestão quer ver o PPT antes do mês fechar. O
      // padrão continua sendo o mês fechado (segundo item).
      const atual = mesSeguinte(status.ano, status.mes);
      return mesesAnteriores(atual.ano, atual.mes, 13).map((o, i) => (
        i === 0 ? { ...o, parcial: true } : o
      ));
    },
    [status],
  );
  const [escolhido, setEscolhido] = useState(null);
  const [previa, setPrevia] = useState(null);
  const [carregando, setCarregando] = useState(false);
  const [baixando, setBaixando] = useState(null);
  const [usarIa, setUsarIa] = useState(true);
  const [erro, setErro] = useState(null);
  const [aviso, setAviso] = useState(null);
  const [squad, setSquad] = useState('EC');

  useEffect(() => {
    if (opcoes.length && !escolhido) setEscolhido(opcoes[1] || opcoes[0]);
  }, [opcoes, escolhido]);

  useEffect(() => {
    if (!escolhido) return;
    let vivo = true;
    setCarregando(true);
    setErro(null);
    api.get('/rper/previa', { params: { ano: escolhido.ano, mes: escolhido.mes } })
      .then(({ data }) => { if (vivo) setPrevia(data); })
      .catch((err) => {
        if (vivo) setErro(mensagemDeErro(err, 'Não foi possível montar a prévia.'));
      })
      .finally(() => { if (vivo) setCarregando(false); });
    return () => { vivo = false; };
  }, [escolhido]);

  async function baixar(formato) {
    setBaixando(formato);
    setErro(null);
    setAviso(null);
    try {
      const resp = await api.get('/rper/arquivo', {
        params: {
          ano: escolhido.ano, mes: escolhido.mes, formato, ia: usarIa && status?.ia_configurada,
        },
        responseType: 'blob',
      });
      const disposicao = resp.headers?.['content-disposition'] || '';
      const achado = /filename="?([^";]+)"?/.exec(disposicao);
      const url = URL.createObjectURL(resp.data);
      const link = document.createElement('a');
      link.href = url;
      link.download = achado ? achado[1] : `RPeR.${formato}`;
      document.body.appendChild(link);
      link.click();
      link.remove();
      URL.revokeObjectURL(url);
      const descartados = Number(resp.headers?.['x-rper-textos-descartados'] || 0);
      if (usarIa && status?.ia_configurada && resp.headers?.['x-rper-ia'] === '0') {
        setAviso('A IA não respondeu: os textos saíram no formato padrão.');
      } else if (descartados > 0) {
        setAviso(
          `${descartados} ${descartados === 1 ? 'texto da IA citava' : 'textos da IA citavam'} `
          + 'número que não está nos dados e saiu no formato padrão.',
        );
      }
    } catch (err) {
      setErro(await mensagemDeBlob(err, 'Não foi possível gerar o RPeR.'));
    } finally {
      setBaixando(null);
    }
  }

  const bloco = previa?.squads?.find((s) => s.squad === squad);

  return (
    <div className="space-y-4">
      {erro && <AlertMessage tipo="erro">{erro}</AlertMessage>}
      {aviso && <AlertMessage tipo="aviso">{aviso}</AlertMessage>}

      <div className="flex flex-wrap items-end gap-3">
        <label className="text-sm text-hipo-ink" htmlFor="rper-mes">
          <span className="block font-medium mb-1.5">Mês dos resultados</span>
          <select
            id="rper-mes"
            className="h-10 px-3 rounded-lg bg-hipo-card border border-hipo-border text-sm"
            value={escolhido?.valor || ''}
            onChange={(e) => setEscolhido(opcoes.find((o) => o.valor === e.target.value))}
          >
            {opcoes.map((o) => (
              <option key={o.valor} value={o.valor}>
                {rotuloMes(o.ano, o.mes)}{o.parcial ? ' (parcial, até hoje)' : ''}
              </option>
            ))}
          </select>
        </label>
        {escolhido && (
          <p className="text-xs text-hipo-slate pb-2.5">
            RPeR de {(() => {
              const s = mesSeguinte(escolhido.ano, escolhido.mes);
              return rotuloMes(s.ano, s.mes);
            })()}: resultados de {rotuloMes(escolhido.ano, escolhido.mes)} e
            planejamento do mês seguinte.
            {escolhido.parcial && (
              <strong className="block text-hipo-warning">
                Mês ainda aberto: os números vão até hoje e mudam até o fim do mês.
              </strong>
            )}
          </p>
        )}
      </div>

      <div className="flex flex-wrap items-center gap-2">
        <Button
          icon={Download}
          loading={baixando === 'pptx'}
          disabled={!escolhido || !status?.pptx_disponivel || Boolean(baixando)}
          onClick={() => baixar('pptx')}
        >
          Baixar PPTX
        </Button>
        <Button
          variant="secondary"
          icon={FileText}
          loading={baixando === 'pdf'}
          disabled={!escolhido || !status?.pdf_disponivel || Boolean(baixando)}
          title={status?.pdf_disponivel ? undefined : 'LibreOffice não está instalado no servidor.'}
          onClick={() => baixar('pdf')}
        >
          Baixar PDF
        </Button>
        <label className="ml-2 inline-flex items-center gap-2 text-sm text-hipo-ink">
          <input
            type="checkbox"
            checked={usarIa && Boolean(status?.ia_configurada)}
            disabled={!status?.ia_configurada}
            onChange={(e) => setUsarIa(e.target.checked)}
          />
          <Sparkles size={14} className="text-hipo-blue" aria-hidden="true" />
          Textos de leitura pela IA
        </label>
        {status && !status.ia_configurada && (
          <span className="text-xs text-hipo-slate">
            (sem chave da IA no servidor: textos no formato padrão)
          </span>
        )}
      </div>
      {baixando && (
        <p className="text-xs text-hipo-slate">
          Montando o arquivo{usarIa && status?.ia_configurada ? ' e escrevendo os textos' : ''}…
          pode levar até um minuto.
        </p>
      )}

      {/* ── Prévia: o que vai para o PPT ── */}
      <section aria-label="Prévia do RPeR" className="border-t border-hipo-border pt-3 space-y-3">
        <Tabs
          items={SQUADS.map((s) => ({ key: s, label: s }))}
          value={squad}
          onChange={setSquad}
        />
        {carregando && !previa && (
          <p className="py-6 text-center text-sm text-hipo-slate">Montando a prévia…</p>
        )}
        {bloco && (
          <div className="overflow-x-auto">
            <table className="w-full text-sm" aria-label={`Prévia ${bloco.squad}`}>
              <thead>
                <tr className="text-xs text-hipo-slate border-b border-hipo-border">
                  <th className="text-left font-medium py-1.5 pr-2">Indicador</th>
                  <th className="text-right font-medium px-2">Meta</th>
                  <th className="text-right font-medium px-2">Squad</th>
                  <th className="text-right font-medium px-2">Ating.</th>
                  {bloco.pessoas.map((p) => (
                    <th key={p.id} className="text-right font-medium px-2">
                      {p.nome.split(' ')[0]}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {bloco.total.map((l, k) => (
                  <tr key={l.chave} className="border-b border-hipo-border/60">
                    <td className="py-1.5 pr-2 text-hipo-ink">
                      {l.rotulo}
                      {l.posicao && (
                        <span className="ml-1 text-[10px] text-hipo-muted" title="Posição no momento da geração">
                          posição
                        </span>
                      )}
                    </td>
                    <td className="text-right px-2 tabular-nums text-hipo-slate">{l.meta_txt || '—'}</td>
                    <td className="text-right px-2 tabular-nums font-semibold text-hipo-ink">{l.realizado_txt}</td>
                    <td className={`text-right px-2 tabular-nums font-medium ${COR_CARINHA[l.carinha] || 'text-hipo-muted'}`}>
                      {l.atingimento_txt || '—'}
                    </td>
                    {bloco.pessoas.map((p) => (
                      <td key={p.id} className="text-right px-2 tabular-nums text-hipo-ink">
                        {p.indicadores[k].realizado_txt}
                      </td>
                    ))}
                  </tr>
                ))}
              </tbody>
            </table>
            {bloco.pessoas.length === 0 && (
              <p className="mt-2 text-xs text-hipo-slate">
                Ninguém ativo com o cargo {bloco.squad}: o PPT sai com o bloco zerado.
              </p>
            )}
          </div>
        )}
      </section>
    </div>
  );
}

// ── Aba Metas ────────────────────────────────────────────────────────

function AbaMetas({ status }) {
  // Metas abrem no mês do planejamento: o seguinte ao mês fechado.
  const inicial = useMemo(
    () => (status ? mesSeguinte(status.ano, status.mes) : null),
    [status],
  );
  const opcoes = useMemo(() => {
    if (!inicial) return [];
    const prox = mesSeguinte(inicial.ano, inicial.mes);
    return mesesAnteriores(prox.ano, prox.mes, 8);
  }, [inicial]);
  const [alvo, setAlvo] = useState(null);
  const [dados, setDados] = useState(null);
  const [campos, setCampos] = useState({});
  const [squad, setSquad] = useState('EC');
  const [ocupado, setOcupado] = useState(false);
  const [erro, setErro] = useState(null);
  const [salvo, setSalvo] = useState(false);

  useEffect(() => {
    if (inicial && !alvo) setAlvo({ ...inicial, valor: `${inicial.ano}-${inicial.mes}` });
  }, [inicial, alvo]);

  // Chave de campo: squad|usuario (ou "squad")|indicador.
  const aplicar = useCallback((data) => {
    setDados(data);
    const novos = {};
    data.squads.forEach((s) => {
      Object.entries(s.squad_metas).forEach(([ind, v]) => {
        novos[`${s.squad}|squad|${ind}`] = textoDoValor(v);
      });
      s.pessoas.forEach((p) => {
        Object.entries(p.metas).forEach(([ind, v]) => {
          novos[`${s.squad}|${p.id}|${ind}`] = textoDoValor(v);
        });
      });
    });
    setCampos(novos);
  }, []);

  useEffect(() => {
    if (!alvo) return;
    let vivo = true;
    setErro(null);
    setSalvo(false);
    api.get('/rper/metas', { params: { ano: alvo.ano, mes: alvo.mes } })
      .then(({ data }) => { if (vivo) aplicar(data); })
      .catch((err) => {
        if (vivo) setErro(mensagemDeErro(err, 'Não foi possível carregar as metas.'));
      });
    return () => { vivo = false; };
  }, [alvo, aplicar]);

  const invalidos = Object.values(campos).some((t) => Number.isNaN(numeroDoCampo(t)));

  async function salvar() {
    setOcupado(true);
    setErro(null);
    setSalvo(false);
    try {
      const metas = Object.entries(campos).map(([chave, texto]) => {
        const [sq, dono, indicador] = chave.split('|');
        return {
          squad: sq,
          usuario_id: dono === 'squad' ? null : dono,
          indicador,
          valor: numeroDoCampo(texto),
        };
      });
      const { data } = await api.put('/rper/metas', { ano: alvo.ano, mes: alvo.mes, metas });
      aplicar(data);
      setSalvo(true);
    } catch (err) {
      setErro(mensagemDeErro(err, 'Não foi possível salvar as metas.'));
    } finally {
      setOcupado(false);
    }
  }

  async function copiar() {
    setOcupado(true);
    setErro(null);
    try {
      const { data } = await api.post('/rper/metas/copiar', null, {
        params: { ano: alvo.ano, mes: alvo.mes },
      });
      aplicar(data);
    } catch (err) {
      setErro(mensagemDeErro(err, 'Não foi possível copiar as metas do mês anterior.'));
    } finally {
      setOcupado(false);
    }
  }

  const bloco = dados?.squads?.find((s) => s.squad === squad);

  function campo(chave, rotulo) {
    const texto = campos[chave] ?? '';
    return (
      <input
        aria-label={rotulo}
        inputMode="decimal"
        placeholder="—"
        value={texto}
        onChange={(e) => setCampos((c) => ({ ...c, [chave]: e.target.value }))}
        className={
          'w-24 h-8 px-2 rounded-md bg-hipo-card border text-right text-sm tabular-nums '
          + (Number.isNaN(numeroDoCampo(texto)) ? 'border-hipo-danger' : 'border-hipo-border')
        }
      />
    );
  }

  return (
    <div className="space-y-4">
      {erro && <AlertMessage tipo="erro">{erro}</AlertMessage>}
      {salvo && <AlertMessage tipo="ok">Metas salvas.</AlertMessage>}

      <div className="flex flex-wrap items-end gap-3">
        <label className="text-sm text-hipo-ink" htmlFor="rper-metas-mes">
          <span className="block font-medium mb-1.5">Mês da meta</span>
          <select
            id="rper-metas-mes"
            className="h-10 px-3 rounded-lg bg-hipo-card border border-hipo-border text-sm"
            value={alvo?.valor || ''}
            onChange={(e) => setAlvo(opcoes.find((o) => o.valor === e.target.value))}
          >
            {opcoes.map((o) => (
              <option key={o.valor} value={o.valor}>{rotuloMes(o.ano, o.mes)}</option>
            ))}
          </select>
        </label>
        <Button variant="secondary" size="sm" icon={Copy} loading={ocupado} onClick={copiar}
          disabled={!alvo}
        >
          Copiar do mês anterior
        </Button>
        <p className="text-xs text-hipo-slate pb-2">
          A meta do squad é lançada à parte — não é a soma das pessoas.
          Campo vazio = sem meta.
        </p>
      </div>

      <Tabs items={SQUADS.map((s) => ({ key: s, label: s }))} value={squad} onChange={setSquad} />

      {bloco && (
        <div className="overflow-x-auto">
          <table className="w-full text-sm" aria-label={`Metas ${bloco.squad}`}>
            <thead>
              <tr className="text-xs text-hipo-slate border-b border-hipo-border">
                <th className="text-left font-medium py-1.5 pr-2">Indicador</th>
                <th className="text-right font-medium px-2">Squad</th>
                {bloco.pessoas.map((p) => (
                  <th key={p.id} className="text-right font-medium px-2">{p.nome.split(' ')[0]}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {bloco.indicadores.map((ind) => (
                <tr key={ind.chave} className="border-b border-hipo-border/60">
                  <td className="py-1 pr-2 text-hipo-ink" title={ind.fonte}>
                    {ind.rotulo}
                    <span className="ml-1 text-[10px] text-hipo-muted">{DICA_FORMATO[ind.formato]}</span>
                  </td>
                  <td className="text-right px-2 py-1">
                    {campo(`${bloco.squad}|squad|${ind.chave}`, `${ind.rotulo} — squad`)}
                  </td>
                  {bloco.pessoas.map((p) => (
                    <td key={p.id} className="text-right px-2 py-1">
                      {campo(`${bloco.squad}|${p.id}|${ind.chave}`, `${ind.rotulo} — ${p.nome}`)}
                    </td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      <div className="flex justify-end">
        <Button loading={ocupado} disabled={invalidos || !dados} onClick={salvar}>
          Salvar metas
        </Button>
      </div>
    </div>
  );
}

// ── O modal ──────────────────────────────────────────────────────────

export default function RperMonitor({ aberto, onFechar }) {
  const [aba, setAba] = useState('gerar');
  const [status, setStatus] = useState(null);
  const [erro, setErro] = useState(null);

  useEffect(() => {
    if (!aberto) return;
    let vivo = true;
    api.get('/rper/status')
      .then(({ data }) => { if (vivo) setStatus(data); })
      .catch((err) => {
        if (vivo) setErro(mensagemDeErro(err, 'Não foi possível consultar o RPeR.'));
      });
    return () => { vivo = false; };
  }, [aberto]);

  return (
    <Modal
      aberto={aberto}
      onFechar={onFechar}
      titulo="RPeR — Reunião de Planejamento e Resultados"
      subtitulo={status ? `Resultados de ${status.rotulo_fechado} · planejamento de ${status.rotulo_novo}` : undefined}
      size="xl"
    >
      <div className="space-y-4">
        {erro && <AlertMessage tipo="erro">{erro}</AlertMessage>}
        <Tabs
          items={[{ key: 'gerar', label: 'Gerar PPT' }, { key: 'metas', label: 'Metas por squad e pessoa' }]}
          value={aba}
          onChange={setAba}
        />
        {aba === 'gerar' ? <AbaGerar status={status} /> : <AbaMetas status={status} />}
      </div>
    </Modal>
  );
}
