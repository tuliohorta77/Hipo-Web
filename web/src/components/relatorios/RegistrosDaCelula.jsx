// web/src/components/relatorios/RegistrosDaCelula.jsx
//
// O drilldown: os registros por trás de um número da tabela. "Abrir" leva à
// tela onde se age sobre o registro (a oportunidade no funil, a conta em
// Contas) — relatório que só mostra número e não leva a lugar nenhum é a
// tela "só de visualização" que a diretriz 2 proíbe.
//
// Abre em OUTRA ABA: quem está montando um relatório não pode perder a
// montagem (ainda não salva) por ter clicado para conferir um registro.

import { useEffect, useState } from 'react';
import { ExternalLink, Loader2 } from 'lucide-react';
import api from '../../api';
import Modal from '../ui/Modal';
import Button from '../ui/Button';
import AlertMessage from '../ui/AlertMessage';
import Empty from '../ui/Empty';
import { formatarDimensao } from './pivot';
import { mensagemDeErro } from '../crm/tarefaComum';

const PAGINA = 100;

export function destinoDe(abrir) {
  if (!abrir) return null;
  if (abrir.tipo === 'oportunidade') return `/crm/oportunidades?abrir=${abrir.id}`;
  if (abrir.tipo === 'conta') return `/crm/contas?abrir=${abrir.id}`;
  return null;
}

export default function RegistrosDaCelula({ aberto, titulo, consultaBase, celula, onFechar }) {
  const [colunas, setColunas] = useState([]);
  const [itens, setItens] = useState([]);
  const [total, setTotal] = useState(0);
  const [carregando, setCarregando] = useState(false);
  const [erro, setErro] = useState(null);

  async function buscar(deslocamento) {
    setCarregando(true);
    setErro(null);
    try {
      const { data } = await api.post('/crm/relatorios/registros', {
        ...consultaBase, celula, limite: PAGINA, deslocamento,
      });
      setColunas(data.colunas);
      setTotal(data.total);
      setItens((atual) => (deslocamento ? [...atual, ...data.itens] : data.itens));
    } catch (err) {
      setErro(mensagemDeErro(err, 'Não foi possível carregar os registros.'));
    } finally {
      setCarregando(false);
    }
  }

  useEffect(() => {
    if (!aberto) return;
    setItens([]);
    setTotal(0);
    buscar(0);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [aberto, celula, consultaBase]);

  return (
    <Modal
      aberto={aberto}
      onFechar={onFechar}
      titulo={`Registros — ${titulo}`}
      subtitulo={carregando && !itens.length ? 'Carregando…' : `${total} registro(s)`}
      size="xl"
      nivel={2}
    >
      {erro && <AlertMessage tipo="erro" className="mb-3">{erro}</AlertMessage>}
      {!carregando && !erro && itens.length === 0 && <Empty title="Nenhum registro" />}
      {itens.length > 0 && (
        <div className="overflow-x-auto border border-hipo-border rounded-lg">
          <table className="w-full text-sm">
            <thead>
              <tr>
                {colunas.map((c) => (
                  <th key={c.campo} className="text-left px-3 py-2 text-[11px] uppercase tracking-wide text-hipo-slate bg-hipo-bg border-b border-hipo-border whitespace-nowrap">
                    {c.rotulo}
                  </th>
                ))}
                <th className="bg-hipo-bg border-b border-hipo-border" />
              </tr>
            </thead>
            <tbody>
              {itens.map((item, i) => {
                const destino = destinoDe(item.abrir);
                return (
                  <tr
                    // eslint-disable-next-line react/no-array-index-key
                    key={i}
                    onClick={destino ? () => window.open(destino, '_blank', 'noopener') : undefined}
                    className={`border-b border-hipo-border last:border-b-0 ${destino ? 'cursor-pointer hover:bg-hipo-bg' : ''}`}
                  >
                    {colunas.map((c, j) => (
                      <td key={c.campo} className="px-3 py-2 text-hipo-ink whitespace-nowrap max-w-[16rem] truncate">
                        {formatarDimensao(item.valores[j], { ...c, granularidade: 'dia' })}
                      </td>
                    ))}
                    <td className="px-3 py-2 text-right">
                      {destino && (
                        <a
                          href={destino}
                          target="_blank"
                          rel="noopener noreferrer"
                          onClick={(e) => e.stopPropagation()}
                          className="inline-flex items-center gap-1 text-xs text-hipo-blue hover:underline"
                        >
                          Abrir <ExternalLink size={12} />
                        </a>
                      )}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}
      {itens.length < total && (
        <div className="flex justify-center mt-3">
          <Button variant="secondary" size="sm" loading={carregando} onClick={() => buscar(itens.length)}>
            Carregar mais ({total - itens.length} restantes)
          </Button>
        </div>
      )}
      {carregando && itens.length === 0 && (
        <div className="flex justify-center py-8 text-hipo-slate">
          <Loader2 className="animate-spin" size={20} />
        </div>
      )}
    </Modal>
  );
}
