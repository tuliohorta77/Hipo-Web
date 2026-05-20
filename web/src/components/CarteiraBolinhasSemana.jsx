// web/src/components/CarteiraBolinhasSemana.jsx
//
// Coluna vertical de bolinhas para cada semana ISO do Farmer.
// Cada coluna tem ALTURA FIXA de 3 slots (cumpridas / atrasadas / pendentes)
// para garantir que os labels S1, S2, S3... fiquem todos alinhados
// na mesma base, independente de quais slots estão preenchidos.
//
// Cada bolinha conta CONTADORES (CNPJs), não reuniões:
//   - success: contadores que tiveram pelo menos 1 reunião na semana
//   - warning: contadores sem reunião E a semana já passou (perderam meta)
//   - neutral: contadores ainda sem reunião na semana corrente (pendente)
//
// Manual de Marca §6: "badges suaves, sem saturação excessiva".
// Em vez de bolinhas sólidas saturadas, usamos fundo pastel + texto
// semântico e borda discreta. A leitura visual continua imediata.
//
// Props:
//   semanas: [{ key, label, com_reuniao, sem_reuniao, pendente }, ...]

const TAMANHO_BOLINHA = 30;        // px — diâmetro
const ESPACAMENTO_BOLINHA = 4;     // px — gap vertical entre bolinhas
// Altura total = 3 bolinhas + 2 gaps
const ALTURA_SLOTS = TAMANHO_BOLINHA * 3 + ESPACAMENTO_BOLINHA * 2;

// Cada variante traz fundo soft + texto semântico + borda contrastante.
// Visualmente, é o mesmo padrão do CarteiraTimeline (consistência entre
// os 2 componentes de status do módulo Contadores).
const VARIANTES = {
  success: 'bg-hipo-successSoft text-hipo-success border-hipo-successBorder',
  warning: 'bg-hipo-warningSoft text-hipo-warning border-hipo-warningBorder',
  neutral: 'bg-hipo-bg          text-hipo-muted   border-hipo-border',
};

function Slot({ valor, variante }) {
  // Slot ocupa sempre o mesmo espaço — invisível se valor == 0
  if (!valor || valor <= 0) {
    return (
      <div
        style={{ width: TAMANHO_BOLINHA, height: TAMANHO_BOLINHA }}
        aria-hidden="true"
      />
    );
  }
  const classes = VARIANTES[variante] || VARIANTES.neutral;
  return (
    <div
      className={`rounded-full flex items-center justify-center text-xs font-semibold border ${classes}`}
      style={{
        width: TAMANHO_BOLINHA,
        height: TAMANHO_BOLINHA,
      }}
    >
      {valor}
    </div>
  );
}

export default function CarteiraBolinhasSemana({ semanas = [] }) {
  if (!semanas.length) {
    return <span className="text-hipo-muted text-xs">—</span>;
  }
  return (
    <div className="flex items-end justify-center gap-3">
      {semanas.map((s) => {
        const titulo =
          `${s.label} (${s.key})\n` +
          `Grupos com reunião: ${s.com_reuniao}\n` +
          `Grupos sem reunião: ${s.sem_reuniao}\n` +
          (s.pendente ? `Grupos pendentes: ${s.pendente}` : '');
        return (
          <div
            key={s.key}
            className="flex flex-col items-center"
            title={titulo}
          >
            {/* Container de altura fixa garante alinhamento dos labels */}
            <div
              className="flex flex-col items-center"
              style={{
                height: ALTURA_SLOTS,
                gap: ESPACAMENTO_BOLINHA,
                justifyContent: 'flex-end',
              }}
            >
              <Slot valor={s.com_reuniao} variante="success" />
              <Slot valor={s.sem_reuniao} variante="warning" />
              <Slot valor={s.pendente}    variante="neutral" />
            </div>
            <span className="text-[11px] text-hipo-muted mt-1.5 font-medium">
              {s.label}
            </span>
          </div>
        );
      })}
    </div>
  );
}
