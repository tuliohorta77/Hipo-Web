// web/src/components/uc/TextoAula.jsx
//
// O texto da aula, escrito em um markdown pequeno pela gestão no estúdio.
//
// Sem biblioteca e sem dangerouslySetInnerHTML: cada linha vira elemento
// React, então um "<script>" digitado no estúdio aparece como texto, não
// executa. O subconjunto é o que uma apostila precisa:
//
//   ## Seção          ### Subseção
//   - item            1. item numerado
//   > destaque        (vira a caixa "Na conversa com o cliente")
//   **negrito**       parágrafo = linhas seguidas; linha em branco separa

function inline(texto, chaveBase) {
  const partes = String(texto).split(/(\*\*[^*]+\*\*)/g);
  return partes.map((p, i) => {
    if (p.startsWith('**') && p.endsWith('**') && p.length > 4) {
      return <strong key={`${chaveBase}-${i}`} className="font-semibold text-hipo-ink">{p.slice(2, -2)}</strong>;
    }
    return p;
  });
}

export function blocos(md) {
  const linhas = String(md || '').replace(/\r\n/g, '\n').split('\n');
  const saida = [];
  let atual = null;

  const fechar = () => {
    if (atual) saida.push(atual);
    atual = null;
  };

  for (const bruta of linhas) {
    const linha = bruta.trimEnd();
    if (!linha.trim()) { fechar(); continue; }

    let m;
    if ((m = linha.match(/^###\s+(.*)$/))) { fechar(); saida.push({ tipo: 'h3', texto: m[1] }); continue; }
    if ((m = linha.match(/^##\s+(.*)$/))) { fechar(); saida.push({ tipo: 'h2', texto: m[1] }); continue; }
    if ((m = linha.match(/^\s*[-*]\s+(.*)$/))) {
      if (atual?.tipo !== 'ul') { fechar(); atual = { tipo: 'ul', itens: [] }; }
      atual.itens.push(m[1]); continue;
    }
    if ((m = linha.match(/^\s*\d+[.)]\s+(.*)$/))) {
      if (atual?.tipo !== 'ol') { fechar(); atual = { tipo: 'ol', itens: [] }; }
      atual.itens.push(m[1]); continue;
    }
    if ((m = linha.match(/^>\s?(.*)$/))) {
      if (atual?.tipo !== 'quote') { fechar(); atual = { tipo: 'quote', linhas: [] }; }
      atual.linhas.push(m[1]); continue;
    }
    if (atual?.tipo !== 'p') { fechar(); atual = { tipo: 'p', linhas: [] }; }
    atual.linhas.push(linha.trim());
  }
  fechar();
  return saida;
}

export default function TextoAula({ md }) {
  const lista = blocos(md);
  if (lista.length === 0) return null;
  return (
    <div className="space-y-3 text-sm leading-relaxed text-hipo-slate" data-testid="texto-aula">
      {lista.map((b, i) => {
        const k = `b${i}`;
        switch (b.tipo) {
          case 'h2':
            return <h2 key={k} className="text-h2 text-hipo-ink pt-3">{inline(b.texto, k)}</h2>;
          case 'h3':
            return <h3 key={k} className="text-base font-semibold text-hipo-ink pt-2">{inline(b.texto, k)}</h3>;
          case 'ul':
            return (
              <ul key={k} className="list-disc pl-5 space-y-1">
                {b.itens.map((t, j) => <li key={j}>{inline(t, `${k}-${j}`)}</li>)}
              </ul>
            );
          case 'ol':
            return (
              <ol key={k} className="list-decimal pl-5 space-y-1">
                {b.itens.map((t, j) => <li key={j}>{inline(t, `${k}-${j}`)}</li>)}
              </ol>
            );
          case 'quote':
            return (
              <blockquote
                key={k}
                className="border-l-4 border-hipo-blue bg-hipo-blueSoft/60 rounded-r-lg px-4 py-3 text-hipo-ink"
              >
                {inline(b.linhas.join(' '), k)}
              </blockquote>
            );
          default:
            return <p key={k}>{inline(b.linhas.join(' '), k)}</p>;
        }
      })}
    </div>
  );
}
