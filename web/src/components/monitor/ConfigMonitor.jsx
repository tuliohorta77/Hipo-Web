// web/src/components/monitor/ConfigMonitor.jsx
//
// As duas coisas que o Monitor precisa que alguém mantenha: as METAS do mês
// e os DIAS SEM EXPEDIENTE do ano.
//
// ── Por que as duas juntas ───────────────────────────────────────────
// Elas são o mesmo assunto: a régua do painel. A meta diz quanto se espera
// no mês; o feriado diz em quantos dias. Meta de 276 leads num mês com três
// feriados cobra mais por dia do que num mês cheio — e é isso que o painel
// mostra na carinha. Separar em duas telas faria alguém ajustar a meta sem
// lembrar do calendário.
//
// ── Por que um Salvar para todas as metas ────────────────────────────
// Quem abre isto ajusta várias e salva uma vez. Um PUT por campo deixaria o
// mês metade novo e metade velho se a rede caísse no meio; aqui vai tudo
// numa chamada e o servidor grava em transação.
//
// Campo em branco APAGA a meta daquele indicador — é como se tira a
// cobrança sem deixar zero, que significa "meta zero" e continua com
// carinha.

import { useCallback, useEffect, useState } from 'react';
import { CalendarOff, Copy, Plus, Trash2 } from 'lucide-react';

import api from '../../api';
import Modal from '../ui/Modal';
import Button from '../ui/Button';
import Input from '../ui/Input';
import AlertMessage from '../ui/AlertMessage';
import { mensagemDeErro } from '../crm/tarefaComum';

const DICA_FORMATO = {
  moeda: 'em reais',
  percentual: 'em %',
  inteiro: 'quantidade',
};

function dataCurta(iso) {
  const [ano, mes, dia] = iso.split('-');
  return `${dia}/${mes}/${ano}`;
}

export default function ConfigMonitor({ aberto, onFechar, ano, mes, onSalvo }) {
  const [metas, setMetas] = useState([]);
  const [rotulo, setRotulo] = useState('');
  const [feriados, setFeriados] = useState([]);
  const [novoFeriado, setNovoFeriado] = useState({ data: '', motivo: '' });
  const [carregando, setCarregando] = useState(true);
  const [ocupado, setOcupado] = useState(false);
  const [erro, setErro] = useState(null);

  const anoDosFeriados = ano;

  const carregar = useCallback(async () => {
    setCarregando(true);
    setErro(null);
    try {
      const [m, f] = await Promise.all([
        api.get('/monitor/metas', { params: { ano, mes } }),
        api.get('/monitor/feriados', { params: { ano: anoDosFeriados } }),
      ]);
      setRotulo(m.data.rotulo);
      setMetas(m.data.metas.map((x) => ({
        ...x,
        // String no estado, número só na hora de enviar: input controlado
        // com número trava o usuário no meio de "1.5" e apaga o que ele
        // acabou de digitar.
        texto: x.valor === null || x.valor === undefined ? '' : String(x.valor),
      })));
      setFeriados(f.data);
    } catch (err) {
      setErro(mensagemDeErro(err, 'Não foi possível carregar metas e feriados.'));
    } finally {
      setCarregando(false);
    }
  }, [ano, mes, anoDosFeriados]);

  useEffect(() => { if (aberto) carregar(); }, [aberto, carregar]);

  const mutar = useCallback(async (fn, padrao) => {
    setOcupado(true);
    setErro(null);
    try {
      await fn();
      onSalvo?.();
      return true;
    } catch (err) {
      setErro(mensagemDeErro(err, padrao));
      return false;
    } finally {
      setOcupado(false);
    }
  }, [onSalvo]);

  function salvarMetas() {
    const corpo = {
      ano,
      mes,
      metas: metas.map((m) => ({
        indicador: m.indicador,
        // Vazio apaga; vírgula aceita, porque é como se digita número aqui.
        valor: m.texto.trim() === ''
          ? null
          : Number(m.texto.replace(',', '.')),
      })),
    };
    return mutar(
      () => api.put('/monitor/metas', corpo).then(({ data }) => {
        setMetas(data.metas.map((x) => ({
          ...x, texto: x.valor === null ? '' : String(x.valor),
        })));
      }),
      'Não foi possível salvar as metas.',
    );
  }

  function copiarDoMesAnterior() {
    return mutar(
      () => api.post('/monitor/metas/copiar', null, { params: { ano, mes } })
        .then(({ data }) => {
          setMetas(data.metas.map((x) => ({
            ...x, texto: x.valor === null ? '' : String(x.valor),
          })));
        }),
      'Não foi possível copiar as metas do mês anterior.',
    );
  }

  function adicionarFeriado() {
    if (!novoFeriado.data || !novoFeriado.motivo.trim()) return undefined;
    return mutar(
      () => api.post('/monitor/feriados', {
        data: novoFeriado.data, motivo: novoFeriado.motivo.trim(),
      }).then(() => {
        setNovoFeriado({ data: '', motivo: '' });
        return carregar();
      }),
      'Não foi possível marcar o dia.',
    );
  }

  function carregarNacionais() {
    return mutar(
      () => api.post('/monitor/feriados/nacionais', null, { params: { ano: anoDosFeriados } })
        .then(({ data }) => setFeriados(data)),
      'Não foi possível carregar os feriados nacionais.',
    );
  }

  function apagarFeriado(id) {
    return mutar(
      () => api.delete(`/monitor/feriados/${id}`).then(() => carregar()),
      'Não foi possível remover o dia.',
    );
  }

  const invalida = metas.some(
    (m) => m.texto.trim() !== '' && Number.isNaN(Number(m.texto.replace(',', '.')))
  );

  return (
    <Modal
      aberto={aberto}
      onFechar={onFechar}
      titulo="Metas e calendário"
      subtitulo={rotulo ? `Metas de ${rotulo}` : undefined}
      size="lg"
    >
      <div className="space-y-5">
        {erro && <AlertMessage tipo="erro">{erro}</AlertMessage>}

        {carregando ? (
          <p className="py-8 text-center text-sm text-hipo-slate">Carregando…</p>
        ) : (
          <>
            {/* ── Metas do mês ── */}
            <section aria-label="Metas do mês" className="space-y-3">
              <div className="flex flex-wrap items-center justify-between gap-2">
                <p className="text-xs text-hipo-slate">
                  A meta é do mês inteiro. O painel cobra a parte dela que cabe
                  nos dias úteis já corridos.
                </p>
                <Button
                  size="sm" variant="secondary" icon={Copy}
                  loading={ocupado} onClick={copiarDoMesAnterior}
                >
                  Copiar do mês anterior
                </Button>
              </div>

              <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                {metas.map((m) => (
                  <Input
                    key={m.indicador}
                    id={`meta-${m.indicador}`}
                    label={`${m.sigla} — ${m.rotulo}`}
                    hint={DICA_FORMATO[m.formato]}
                    inputMode="decimal"
                    value={m.texto}
                    placeholder="sem meta"
                    onChange={(e) => setMetas((atual) => atual.map((x) => (
                      x.indicador === m.indicador ? { ...x, texto: e.target.value } : x
                    )))}
                  />
                ))}
              </div>

              <div className="flex justify-end">
                <Button loading={ocupado} disabled={invalida} onClick={salvarMetas}>
                  Salvar metas
                </Button>
              </div>
            </section>

            {/* ── Calendário ── */}
            <section
              aria-label="Dias sem expediente"
              className="space-y-3 border-t border-hipo-border pt-4"
            >
              <div className="flex flex-wrap items-center justify-between gap-2">
                <p className="flex items-center gap-1.5 text-sm font-medium text-hipo-ink">
                  <CalendarOff size={14} className="text-hipo-blue" />
                  Dias sem expediente em {anoDosFeriados}
                </p>
                <Button
                  size="sm" variant="secondary"
                  loading={ocupado} onClick={carregarNacionais}
                >
                  Carregar feriados nacionais
                </Button>
              </div>

              <div className="flex flex-wrap items-end gap-2">
                <Input
                  id="feriado-data"
                  label="Data"
                  type="date"
                  value={novoFeriado.data}
                  onChange={(e) => setNovoFeriado((f) => ({ ...f, data: e.target.value }))}
                />
                <div className="flex-1 min-w-[12rem]">
                  <Input
                    id="feriado-motivo"
                    label="Motivo"
                    placeholder="ex.: Aniversário da cidade"
                    value={novoFeriado.motivo}
                    onChange={(e) => setNovoFeriado((f) => ({ ...f, motivo: e.target.value }))}
                  />
                </div>
                <Button
                  icon={Plus}
                  loading={ocupado}
                  disabled={!novoFeriado.data || !novoFeriado.motivo.trim()}
                  onClick={adicionarFeriado}
                >
                  Marcar
                </Button>
              </div>

              {feriados.length === 0 ? (
                <p className="text-xs text-hipo-slate">
                  Nenhum dia marcado — o painel conta só sábado e domingo como
                  não úteis.
                </p>
              ) : (
                <ul className="divide-y divide-hipo-border border border-hipo-border rounded-lg">
                  {feriados.map((f) => (
                    <li key={f.id} className="flex items-center gap-2 px-3 py-1.5 text-sm">
                      <span className="font-mono tabular-nums text-hipo-ink">
                        {dataCurta(f.data)}
                      </span>
                      <span className="truncate text-hipo-slate">{f.motivo}</span>
                      <button
                        type="button"
                        onClick={() => apagarFeriado(f.id)}
                        aria-label={`Remover ${dataCurta(f.data)}`}
                        className="ml-auto shrink-0 text-hipo-slate hover:text-hipo-danger"
                      >
                        <Trash2 size={14} />
                      </button>
                    </li>
                  ))}
                </ul>
              )}
            </section>
          </>
        )}

        <div className="flex justify-end">
          <Button variant="ghost" onClick={onFechar}>Fechar</Button>
        </div>
      </div>
    </Modal>
  );
}
