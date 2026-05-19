// web/src/components/ui/Table.jsx
// Tabela do Hipo: cabeçalho em cinza muito claro, linhas com borda fina,
// padding generoso, hover sutil. Conforme Manual §6.
//
// Uso:
//   <Table>
//     <thead>
//       <tr><Th>Coluna A</Th><Th>Coluna B</Th></tr>
//     </thead>
//     <tbody>
//       <Tr onClick={...}>
//         <Td>x</Td>
//         <Td>y</Td>
//       </Tr>
//     </tbody>
//   </Table>

export default function Table({ children, className = '' }) {
  return (
    <div className="overflow-x-auto -mx-1">
      <table className={`w-full text-sm ${className}`}>{children}</table>
    </div>
  );
}

export function Th({ children, className = '', align = 'left', ...rest }) {
  return (
    <th
      className={
        `text-${align} font-medium text-hipo-slate bg-hipo-bg ` +
        `px-4 py-3 border-y border-hipo-border first:pl-5 last:pr-5 ` +
        `text-xs uppercase tracking-wide ${className}`
      }
      {...rest}
    >
      {children}
    </th>
  );
}

export function Tr({ children, className = '', onClick, ...rest }) {
  const clickable = !!onClick;
  return (
    <tr
      onClick={onClick}
      className={
        `border-b border-hipo-border last:border-b-0 ` +
        (clickable ? 'hover:bg-hipo-bg cursor-pointer transition-colors ' : '') +
        className
      }
      {...rest}
    >
      {children}
    </tr>
  );
}

export function Td({ children, className = '', align = 'left', ...rest }) {
  return (
    <td
      className={`text-${align} px-4 py-3.5 text-hipo-ink first:pl-5 last:pr-5 ${className}`}
      {...rest}
    >
      {children}
    </td>
  );
}
