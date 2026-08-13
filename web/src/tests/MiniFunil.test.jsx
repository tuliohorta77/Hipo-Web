// web/src/tests/MiniFunil.test.jsx
//
// O mini-funil da linha tem três promessas:
//   1. cinco casas SEMPRE, inclusive as zeradas — casa que some e volta
//      destrói a leitura vertical da tabela
//   2. as fases são as atuais (S/L/Q/A/N). A versão anterior deste componente
//      era código morto e ainda falava em `cadencia`, que não existe desde a
//      Sprint 0 — este arquivo existe também para isso não voltar
//   3. tudo zerado vira uma frase, não cinco caixinhas cinzas
import { describe, it, expect, afterEach } from 'vitest';
import { render, screen, cleanup } from '@testing-library/react';

import MiniFunil, { moedaCompacta } from '../components/ui/MiniFunil';

const CHEIO = {
  suspect: { qtd: 2, ticket: 3000 },
  lead: { qtd: 0, ticket: 0 },
  qualificacao: { qtd: 1, ticket: 1500 },
  apresentacao: { qtd: 0, ticket: 0 },
  negociacao: { qtd: 3, ticket: 12500 },
};

const VAZIO = {
  suspect: { qtd: 0, ticket: 0 },
  lead: { qtd: 0, ticket: 0 },
  qualificacao: { qtd: 0, ticket: 0 },
  apresentacao: { qtd: 0, ticket: 0 },
  negociacao: { qtd: 0, ticket: 0 },
};

afterEach(cleanup);

describe('MiniFunil — as cinco fases', () => {
  it('desenha as cinco letras, inclusive as fases zeradas', () => {
    render(<MiniFunil dados={CHEIO} />);
    ['S', 'L', 'Q', 'A', 'N'].forEach((letra) => {
      expect(screen.getByText(letra)).toBeInTheDocument();
    });
  });

  it('usa as fases atuais e não a extinta `cadencia`', () => {
    /*
      A versão anterior desenhava S/C/Q/A/N, com C de "Cadência" — fase que
      saiu na Sprint 0. Se alguém reintroduzir aquele vocabulário, este
      teste cai.
    */
    render(<MiniFunil dados={CHEIO} />);
    expect(screen.getByTitle(/^Lead:/)).toBeInTheDocument();
    expect(screen.queryByTitle(/Cadência/)).not.toBeInTheDocument();
  });

  it('cada casa diz a fase, a quantidade e o ticket por extenso', () => {
    render(<MiniFunil dados={CHEIO} />);
    expect(screen.getByTitle('Suspect: 2 em aberto · R$ 3.000')).toBeInTheDocument();
  });

  it('mostra a quantidade de cada fase', () => {
    render(<MiniFunil dados={CHEIO} />);
    expect(screen.getByTitle(/^Negociação:/)).toHaveTextContent('3');
  });

  it('fase vazia mostra travessão no lugar do ticket, não R$ 0', () => {
    /*
      "R$ 0" é uma afirmação sobre dinheiro; travessão é a ausência de
      negócio. Cinco "R$ 0" por linha também competem visualmente com as
      fases que têm conteúdo.
    */
    render(<MiniFunil dados={CHEIO} />);
    expect(screen.getByTitle(/^Lead:/)).toHaveTextContent('—');
  });

  it('resume o total no rótulo do grupo', () => {
    render(<MiniFunil dados={CHEIO} />);
    expect(
      screen.getByLabelText('Funil em aberto: 6 oportunidades')
    ).toBeInTheDocument();
  });
});

describe('MiniFunil — estados de vazio', () => {
  it('tudo zerado vira frase, não cinco caixinhas', () => {
    render(<MiniFunil dados={VAZIO} />);
    expect(screen.getByText('Nada em aberto')).toBeInTheDocument();
    expect(screen.queryByText('S')).not.toBeInTheDocument();
  });

  it('sem dado nenhum mostra travessão', () => {
    render(<MiniFunil dados={null} />);
    expect(screen.getByText('—')).toBeInTheDocument();
  });

  it('aceita texto de vazio próprio', () => {
    render(<MiniFunil dados={VAZIO} vazio="Nenhuma indicação viva" />);
    expect(screen.getByText('Nenhuma indicação viva')).toBeInTheDocument();
  });
});

describe('moedaCompacta', () => {
  it('abaixo de mil é o número redondo', () => {
    expect(moedaCompacta(850)).toBe('850');
  });

  it('milhares viram k com vírgula decimal brasileira', () => {
    expect(moedaCompacta(12500)).toBe('12,5k');
  });

  it('milhões viram M', () => {
    expect(moedaCompacta(2_400_000)).toBe('2,4M');
  });

  it('nulo é zero, não NaN', () => {
    expect(moedaCompacta(null)).toBe('0');
    expect(moedaCompacta(undefined)).toBe('0');
  });
});
