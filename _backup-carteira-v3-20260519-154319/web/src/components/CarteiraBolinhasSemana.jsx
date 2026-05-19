// web/src/components/CarteiraBolinhasSemana.jsx
//
// Coluna vertical de bolinhas para uma única semana ISO do Farmer.
// Cada bolinha conta CONTADORES (CNPJs), não reuniões:
//   - verde:   contadores que tiveram pelo menos 1 reunião na semana
//   - laranja: contadores sem reunião E a semana já passou (perderam meta)
//   - cinza:   contadores ainda sem reunião na semana corrente (pendente)
//
// Props:
//   semanas: [{ key, label, com_reuniao, sem_reuniao, pendente }, ...]

function Bolinha({ valor, cor }) {
  // Bolinhas com 0 contadores são omitidas pra não poluir
  if (valor <= 0) return null;
  return (
    <div
      className="w-8 h-8 rounded-full flex items-center justify-center text-white text-xs font-semibold"
      style={{ backgroundColor: cor }}
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
    <div className="flex items-start justify-center gap-3">
      {semanas.map((s) => {
        const titulo =
          `${s.label} (${s.key})\n` +
          `Com reunião: ${s.com_reuniao}\n` +
          `Sem reunião: ${s.sem_reuniao}\n` +
          (s.pendente ? `Pendente: ${s.pendente}` : "");

        return (
          <div
            key={s.key}
            className="flex flex-col gap-1 items-center"
            title={titulo}
          >
            <Bolinha valor={s.com_reuniao} cor="#16A34A" />
            <Bolinha valor={s.sem_reuniao} cor="#F59E0B" />
            <Bolinha valor={s.pendente} cor="#94A3B8" />
            <span className="text-[10px] text-hipo-muted mt-0.5 font-medium">
              {s.label}
            </span>
          </div>
        );
      })}
    </div>
  );
}
