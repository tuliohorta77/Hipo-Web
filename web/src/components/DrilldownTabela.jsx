// web/src/components/DrilldownTabela.jsx
//
// Tabela completa de grupos de um colaborador (formato da tela antiga:
// timeline + atrasadas + futuras + leads + funil).
//
// Extraído de Contadores.jsx (v1.2.0 etapa 5.0) pra ser reutilizável —
// usado tanto na aba Hunter/Farmer de Contadores quanto na sub-aba
// Relacionamento (BastaoLista), que mostra a visão Farmer dos contadores
// que o Hunter passou via bastão.
//
// Props:
//   - aba: 'EC_HUNTER' | 'EC_FARMER'  (Farmer mostra coluna Leads/mês)
//   - grupos: list de grupos já filtrados
//   - totalSemFiltro: total de grupos antes do filtro (pro título)
//   - filtros: { busca_grupo, tarefa_atrasada, sem_tarefa_futura }
//   - onFiltros: (novoFiltros) => void
//   - onAbrirGrupo: (grupo) => void  (abre o drawer de detalhe)
//   - funilPorGrupo: { [id_grupo]: dadosFunil }

import { Search, ChevronRight } from 'lucide-react';
import Table, { Th, Tr, Td } from './ui/Table';
import Badge from './ui/Badge';
import CarteiraTimeline from './CarteiraTimeline';
import MiniFunil from './ui/MiniFunil';

export default function DrilldownTabela({
  aba,
  grupos,
  totalSemFiltro,
  filtros,
  onFiltros,
  onAbrirGrupo,
  funilPorGrupo,
}) {
  const ehFarmer = aba === 'EC_FARMER';
  const titulo =
    grupos.length === totalSemFiltro
      ? `${totalSemFiltro} grupo(s)`
      : `${grupos.length} de ${totalSemFiltro} grupo(s)`;

  return (
    <div className="bg-hipo-card border border-hipo-border rounded-lg overflow-hidden">
      {/* Filtros locais (mesma UX da tela antiga) */}
      <div className="px-4 py-3 border-b border-hipo-border bg-hipo-bg flex flex-wrap items-center gap-3">
        <span className="text-xs text-hipo-slate font-medium">{titulo}</span>

        <div className="relative flex-1 min-w-[200px]">
          <Search
            size={14}
            className="absolute left-3 top-1/2 -translate-y-1/2 text-hipo-muted"
          />
          <input
            value={filtros.busca_grupo}
            onChange={(e) =>
              onFiltros({ ...filtros, busca_grupo: e.target.value })
            }
            placeholder="Buscar grupo ou contabilidade..."
            onClick={(e) => e.stopPropagation()}
            className="w-full h-9 bg-hipo-card border border-hipo-border rounded-md pl-9 pr-3 text-sm text-hipo-ink placeholder:text-hipo-muted outline-none focus:border-hipo-blue focus:ring-2 focus:ring-hipo-blueSoft"
          />
        </div>

        <label
          className="flex items-center gap-2 text-xs text-hipo-slate cursor-pointer hover:text-hipo-ink"
          onClick={(e) => e.stopPropagation()}
        >
          <input
            type="checkbox"
            checked={filtros.tarefa_atrasada}
            onChange={(e) =>
              onFiltros({ ...filtros, tarefa_atrasada: e.target.checked })
            }
            className="w-4 h-4 accent-hipo-blue cursor-pointer"
          />
          Tarefa atrasada
        </label>
        <label
          className="flex items-center gap-2 text-xs text-hipo-slate cursor-pointer hover:text-hipo-ink"
          onClick={(e) => e.stopPropagation()}
        >
          <input
            type="checkbox"
            checked={filtros.sem_tarefa_futura}
            onChange={(e) =>
              onFiltros({ ...filtros, sem_tarefa_futura: e.target.checked })
            }
            className="w-4 h-4 accent-hipo-blue cursor-pointer"
          />
          Sem tarefa futura
        </label>
      </div>

      {grupos.length === 0 ? (
        <p className="text-sm text-hipo-slate text-center py-6">
          Nenhum grupo nesse filtro.
        </p>
      ) : (
        <Table className="[&_th]:!py-2 [&_th]:!text-[11px] [&_th]:!tracking-wide [&_td]:!py-1.5 [&_td]:!text-[13px]">
          <thead>
            <tr>
              <Th className="w-6"></Th>
              <Th>Grupo</Th>
              <Th align="center">CNPJs</Th>
              <Th>Execução</Th>
              <Th align="center">Atrasadas</Th>
              <Th align="center">Futuras</Th>
              {ehFarmer && <Th align="center">Leads/mês</Th>}
              <Th align="left">Funil</Th>
            </tr>
          </thead>
          <tbody>
            {grupos.map((g) => (
              <Tr key={g.id_grupo} onClick={() => onAbrirGrupo(g)}>
                <Td className="text-hipo-muted">
                  <ChevronRight size={14} />
                </Td>
                <Td>
                  <div className="flex flex-col">
                    <span className="font-semibold text-hipo-ink">
                      {g.nome_grupo || '—'}
                      {g.colaboradores_multiplos && (
                        <Badge tone="warning" className="ml-2">
                          ⚠ Múlt
                        </Badge>
                      )}
                    </span>
                    <span className="text-xs text-hipo-slate mt-0.5">
                      {g.contabilidade_principal} · {g.cidade_uf}
                      {g.parceria && (
                        <span
                          className={`ml-2 ${
                            g.parceria === 'Parceiro'
                              ? 'text-hipo-success font-medium'
                              : 'text-hipo-slate'
                          }`}
                        >
                          {g.parceria === 'Parceiro' ? '● parceiro' : '○ não parceiro'}
                        </span>
                      )}
                    </span>
                  </div>
                </Td>
                <Td align="center">{g.qtd_cnpj}</Td>
                <Td>
                  <CarteiraTimeline cells={g.timeline} compact />
                </Td>
                <Td
                  align="center"
                  className={
                    g.tarefas_atrasadas > 0
                      ? 'text-hipo-danger font-semibold'
                      : 'text-hipo-muted'
                  }
                >
                  {g.tarefas_atrasadas}
                </Td>
                <Td
                  align="center"
                  className={
                    g.tarefas_futuras > 0
                      ? 'text-hipo-blue font-medium'
                      : 'text-hipo-muted'
                  }
                >
                  {g.tarefas_futuras}
                </Td>
                {ehFarmer && (
                  <Td align="center" className="text-hipo-blue font-semibold">
                    {g.leads_no_mes || 0}
                  </Td>
                )}
                <Td onClick={(e) => e.stopPropagation()}>
                  <MiniFunil dados={funilPorGrupo[g.id_grupo]} vazio="—" />
                </Td>
              </Tr>
            ))}
          </tbody>
        </Table>
      )}
    </div>
  );
}
