// web/src/components/relatorios/TabelaDinamica.jsx
//
// A grade. Todo número é clicável e abre os registros que o compõem — é a
// diretriz "dashboard operacional": o agregado leva ao item, e o item leva
// à tela onde se age sobre ele.
//
// O fundo azul proporcional ao valor (o "destaque") é o mapa de calor do
// Excel, em versão discreta: bate o olho e acha o maior sem ler número.
// Só nas células de detalhe, e só pela primeira medida de cada coluna —
// pintar total e subtotal faria o maior número ser sempre o total geral.

import { useMemo } from 'react';
import { ArrowDownWideNarrow, ArrowUpNarrowWide, ArrowDownAZ, ArrowUpAZ } from 'lucide-react';
import {
  montarGrade, formatarDimensao, formatarMedida, cabecalhosDeColuna,
} from './pivot';

const TH = 'px-3 py-2 text-[11px] font-semibold text-hipo-slate bg-hipo-bg border-b border-r border-hipo-border whitespace-nowrap';

function Valor({ c, j, formato, maximo, destacar, onAbrir, forte }) {
  const v = c.v[j];
  const alfa = destacar && typeof v === 'number' && maximo > 0 ? Math.abs(v) / maximo : 0;
  const clicavel = c.n > 0;
  return (
    <td
      className={
        'px-3 py-1.5 text-right tabular-nums border-b border-r border-hipo-border whitespace-nowrap ' +
        (forte ? 'font-semibold text-hipo-ink ' : 'text-hipo-ink ')
      }
      style={alfa ? { backgroundColor: `rgba(37, 99, 235, ${(0.04 + alfa * 0.22).toFixed(3)})` } : undefined}
    >
      {clicavel ? (
        <button
          type="button"
          onClick={() => onAbrir(c.celula)}
          className="hover:text-hipo-blue hover:underline underline-offset-2"
          title={`${c.n} registro(s) — clique para ver`}
        >
          {formatarMedida(v, formato)}
        </button>
      ) : (
        <span className="text-hipo-muted">{formatarMedida(v, formato)}</span>
      )}
    </td>
  );
}

export default function TabelaDinamica({ resultado, ordenacao, onOrdenar, destacar = true, onAbrirCelula }) {
  const grade = useMemo(() => montarGrade(resultado, ordenacao), [resultado, ordenacao]);
  const L = resultado.linhas.length;
  const C = resultado.colunas.length;
  const M = resultado.valores.length;
  const fileiras = useMemo(() => cabecalhosDeColuna(grade.colunas, C), [grade.colunas, C]);
  const alturaCab = C + 1;
  const colsRotulo = Math.max(L, 1);

  function alternarOrdem(por) {
    if (ordenacao.por === por) {
      onOrdenar({ por, direcao: ordenacao.direcao === 'asc' ? 'desc' : 'asc' });
    } else {
      onOrdenar({ por, direcao: por === 'valor' ? 'desc' : 'asc' });
    }
  }

  const IconeRotulo = ordenacao.por === 'rotulo' && ordenacao.direcao === 'desc' ? ArrowUpAZ : ArrowDownAZ;
  const IconeValor = ordenacao.por === 'valor' && ordenacao.direcao === 'asc' ? ArrowUpNarrowWide : ArrowDownWideNarrow;

  return (
    <div className="overflow-auto max-h-[70vh] border border-hipo-border rounded-lg" data-testid="tabela-dinamica">
      <table className="text-xs border-separate border-spacing-0 min-w-full">
        <thead className="sticky top-0 z-10">
          {Array.from({ length: alturaCab }).map((_, fila) => (
            <tr key={fila}>
              {fila === 0 && (
                L > 0 ? resultado.linhas.map((d, i) => (
                  <th key={d.campo + i} rowSpan={alturaCab} className={`${TH} text-left align-bottom`}>
                    <span className="inline-flex items-center gap-1">
                      {d.rotulo}
                      {i === 0 && (
                        <>
                          <button
                            type="button"
                            onClick={() => alternarOrdem('rotulo')}
                            aria-label="Ordenar pelo nome"
                            className={`p-0.5 rounded ${ordenacao.por === 'rotulo' ? 'text-hipo-blue' : 'text-hipo-muted'} hover:text-hipo-blue`}
                          >
                            <IconeRotulo size={12} />
                          </button>
                          <button
                            type="button"
                            onClick={() => alternarOrdem('valor')}
                            aria-label="Ordenar pelo valor"
                            className={`p-0.5 rounded ${ordenacao.por === 'valor' ? 'text-hipo-blue' : 'text-hipo-muted'} hover:text-hipo-blue`}
                          >
                            <IconeValor size={12} />
                          </button>
                        </>
                      )}
                    </span>
                  </th>
                )) : (
                  <th rowSpan={alturaCab} className={`${TH} text-left`}>&nbsp;</th>
                )
              )}

              {/* Campos de coluna: uma fileira por campo, valores agrupados. */}
              {fila < C && fileiras[fila].map((h) => (
                <th key={h.prefixo} colSpan={h.span * M} className={`${TH} text-center`}>
                  <span className="block text-[10px] font-normal text-hipo-muted">{resultado.colunas[fila].rotulo}</span>
                  {formatarDimensao(h.valor, resultado.colunas[fila])}
                </th>
              ))}
              {fila === 0 && C > 0 && (
                <th colSpan={M} rowSpan={C} className={`${TH} text-center align-bottom bg-hipo-blueSoft/60`}>Total</th>
              )}

              {/* Última fileira: o nome de cada medida. */}
              {fila === alturaCab - 1 && (
                <>
                  {(C > 0 ? [...grade.colunas, null] : [null]).flatMap((col, ci) => (
                    resultado.valores.map((m, j) => (
                      <th
                        key={`${ci}-${j}`}
                        className={`${TH} text-right font-medium ${col === null && C > 0 ? 'bg-hipo-blueSoft/60' : ''}`}
                      >
                        {m.rotulo}
                      </th>
                    ))
                  ))}
                </>
              )}
            </tr>
          ))}
        </thead>
        <tbody>
          {grade.linhas.map((linha) => {
            const chaveReact = `${linha.tipo}-${JSON.stringify(linha.chave)}`;
            const forte = linha.tipo !== 'detalhe';
            const fundo = linha.tipo === 'total'
              ? 'bg-hipo-blueSoft/60'
              : linha.tipo === 'subtotal' ? 'bg-hipo-bg' : '';
            return (
              <tr key={chaveReact} className={fundo} data-tipo={linha.tipo}>
                {linha.tipo === 'detalhe' && resultado.linhas.map((d, i) => (
                  <td
                    key={i}
                    className={
                      'px-3 py-1.5 border-b border-r border-hipo-border whitespace-nowrap max-w-[18rem] truncate ' +
                      (linha.chave[i] === null ? 'italic text-hipo-muted' : 'text-hipo-ink')
                    }
                    title={formatarDimensao(linha.chave[i], d)}
                  >
                    {linha.mostrar[i] ? formatarDimensao(linha.chave[i], d) : ''}
                  </td>
                ))}
                {linha.tipo === 'subtotal' && (
                  <>
                    {Array.from({ length: linha.nivel - 1 }).map((_, i) => (
                      <td key={i} className="border-b border-r border-hipo-border" />
                    ))}
                    <td
                      colSpan={colsRotulo - linha.nivel + 1}
                      className="px-3 py-1.5 font-semibold text-hipo-ink border-b border-r border-hipo-border whitespace-nowrap"
                    >
                      Total de {formatarDimensao(linha.chave[linha.nivel - 1], resultado.linhas[linha.nivel - 1])}
                    </td>
                  </>
                )}
                {linha.tipo === 'total' && (
                  <td colSpan={colsRotulo} className="px-3 py-1.5 font-semibold text-hipo-ink border-b border-r border-hipo-border">
                    Total geral
                  </td>
                )}

                {C > 0 && linha.celulas.map((c, ci) => (
                  resultado.valores.map((m, j) => (
                    <Valor
                      key={`${ci}-${j}`}
                      c={c}
                      j={j}
                      formato={m.formato}
                      maximo={grade.maximos[j]}
                      destacar={destacar && linha.tipo === 'detalhe'}
                      forte={forte}
                      onAbrir={onAbrirCelula}
                    />
                  ))
                ))}
                {resultado.valores.map((m, j) => (
                  <Valor
                    key={`t-${j}`}
                    c={linha.total}
                    j={j}
                    formato={m.formato}
                    maximo={grade.maximos[j]}
                    destacar={destacar && C === 0 && linha.tipo === 'detalhe'}
                    forte={forte || C > 0}
                    onAbrir={onAbrirCelula}
                  />
                ))}
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}
