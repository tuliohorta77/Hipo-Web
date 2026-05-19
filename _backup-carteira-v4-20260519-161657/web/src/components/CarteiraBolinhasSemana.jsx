// web/src/components/CarteiraBolinhasSemana.jsx
//
// Coluna vertical de bolinhas para cada semana ISO do Farmer.
// Cada coluna tem ALTURA FIXA de 3 slots (verde / laranja / cinza)
// para garantir que os labels S1, S2, S3... fiquem todos alinhados
// na mesma base, independente de quais slots estão preenchidos.
//
// Cada bolinha conta CONTADORES (CNPJs), não reuniões:
//   - verde:   contadores que tiveram pelo menos 1 reunião na semana
//   - laranja: contadores sem reunião E a semana já passou (perderam meta)
//   - cinza:   contadores ainda sem reunião na semana corrente (pendente)
//
// Props:
//   semanas: [{ key, label, com_reuniao, sem_reuniao, pendente }, ...]

const TAMANHO_BOLINHA = 30;        // px — diâmetro
const ESPACAMENTO_BOLINHA = 4;     // px — gap vertical entre bolinhas

// Altura total = 3 bolinhas + 2 gaps
const ALTURA_SLOTS = TAMANHO_BOLINHA * 3 + ESPACAMENTO_BOLINHA * 2;

function Slot({ valor, cor }) {
  // Slot ocupa sempre o mesmo espaço — invisível se valor == 0
  if (!valor || valor <= 0) {
    return (
      <div
        style={{ width: TAMANHO_BOLINHA, height: TAMANHO_BOLINHA }}
        aria-hidden="true"
      />
    );
  }
  return (
    <div
      className="rounded-full flex items-center justify-center text-white text-xs font-semibold"
      style={{
        width: TAMANHO_BOLINHA,
        height: TAMANHO_BOLINHA,
        backgroundColor: cor,
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
          `Com reunião: ${s.com_reuniao}\n` +
          `Sem reunião: ${s.sem_reuniao}\n` +
          (s.pendente ? `Pendente: ${s.pendente}` : '');

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
              <Slot valor={s.com_reuniao} cor="#16A34A" />
              <Slot valor={s.sem_reuniao} cor="#F59E0B" />
              <Slot valor={s.pendente} cor="#94A3B8" />
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
