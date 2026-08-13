// web/src/components/ui/FarolSemanal.jsx
//
// A trilha do farol: quatro casas, uma por semana, mais antiga à esquerda e a
// semana corrente à direita.
//
// ── O que ele mede ───────────────────────────────────────────────────
// Cadência de CONTATO. Verde = alguém concluiu uma tarefa com aquele parceiro
// naquela semana. Amarelo = tem tarefa marcada e nenhuma feita. Vermelho =
// nada. A regra mora no backend (services/parceiro.py); aqui só se desenha o
// que ele mandou — inclusive a cor, que vem pronta no payload.
//
// Isso é deliberado: recalcular a cor no navegador criaria uma segunda fonte
// de verdade que diverge no primeiro ajuste, e a que divergir seria a que o
// usuário está olhando.
//
// ── Por que a cor não vem sozinha ────────────────────────────────────
// Cor não carrega informação para quem não distingue tons — mesma decisão já
// tomada em `SITUACAO` de tarefaComum.jsx, onde cada estado tem cor E palavra.
// Aqui a semana corrente ganha anel, cada casa tem `title` com a contagem, e
// o grupo inteiro tem um `aria-label` que resume a trilha em texto. A leitura
// não depende de enxergar verde.
//
// ── Por que a semana corrente tem anel ───────────────────────────────
// Quatro quadrados idênticos não dizem qual é "agora". Sem a marca, um
// parceiro com verde na segunda casa e vermelho na quarta parece igual ao
// inverso — e são situações opostas.

const CORES = {
  verde: {
    caixa: 'bg-hipo-success',
    rotulo: 'contato feito',
  },
  amarelo: {
    caixa: 'bg-hipo-warning',
    rotulo: 'agendado, não feito',
  },
  vermelho: {
    caixa: 'bg-hipo-danger/70',
    rotulo: 'sem contato',
  },
};

/** '10/08' — dia e mês, que é o que cabe num title de 4 casas. */
function diaMes(iso) {
  if (!iso) return '';
  const [, mes, dia] = String(iso).split('-');
  return `${dia}/${mes}`;
}

function descreverSemana(semana) {
  const cor = CORES[semana.cor] || CORES.vermelho;
  const periodo = `${diaMes(semana.inicio)} a ${diaMes(semana.fim)}`;
  const partes = [semana.corrente ? 'Esta semana' : periodo, cor.rotulo];
  if (semana.concluidas > 0) {
    partes.push(`${semana.concluidas} concluída${semana.concluidas === 1 ? '' : 's'}`);
  }
  if (semana.agendadas > 0) {
    partes.push(`${semana.agendadas} em aberto`);
  }
  return partes.join(' · ');
}

/**
 * Resumo em texto da trilha inteira, para leitor de tela e para o title do
 * grupo. Uma frase é mais útil que quatro leituras soltas de cor.
 */
export function resumoDoFarol(semanas, semanasSemContato) {
  if (!semanas?.length) return 'Sem histórico de contato';
  const corrente = semanas[semanas.length - 1];
  if (corrente.cor === 'verde') return 'Contato feito esta semana';
  if (corrente.cor === 'amarelo') return 'Tarefa marcada para esta semana, ainda não feita';
  if (!semanasSemContato) return 'Sem contato esta semana';
  if (semanasSemContato >= semanas.length) {
    return `Sem contato há ${semanas.length}+ semanas`;
  }
  return `Sem contato há ${semanasSemContato} semana${semanasSemContato === 1 ? '' : 's'}`;
}

export default function FarolSemanal({ semanas, semanasSemContato = 0, onClick }) {
  if (!semanas?.length) {
    return <span className="text-[11px] text-hipo-muted">—</span>;
  }

  const resumo = resumoDoFarol(semanas, semanasSemContato);

  const trilha = (
    <span className="inline-flex items-center gap-1">
      {semanas.map((s) => {
        const cor = CORES[s.cor] || CORES.vermelho;
        return (
          <span
            key={s.inicio}
            title={descreverSemana(s)}
            className={
              `block h-4 w-4 rounded-sm ${cor.caixa} ` +
              (s.corrente ? 'ring-2 ring-offset-1 ring-hipo-ink/40 ring-offset-hipo-card' : '')
            }
          />
        );
      })}
    </span>
  );

  // Sem `onClick` é indicador; com `onClick` é botão de verdade — a diretriz
  // do dashboard operacional vale aqui também: o farol leva à ação (abrir a
  // aba de tarefas do parceiro), não só informa.
  if (!onClick) {
    return (
      <span role="img" aria-label={resumo} title={resumo}>
        {trilha}
      </span>
    );
  }

  return (
    <button
      type="button"
      onClick={onClick}
      aria-label={`${resumo}. Abrir tarefas.`}
      title={`${resumo} — clique para abrir as tarefas`}
      className="inline-flex items-center rounded p-0.5 -m-0.5 focus:outline-none focus-visible:ring-2 focus-visible:ring-hipo-blue hover:bg-hipo-bg transition-colors"
    >
      {trilha}
    </button>
  );
}
