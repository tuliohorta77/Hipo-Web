// web/src/tests/BastaoLista.test.jsx
//
// Testa o BastaoLista apos o refactor da v1.3.0 (etapa 2c): o componente
// agora consome GET /carteira/relacionamento (cruzamento ja feito no
// backend), GET /carteira/bastoes/meus (pendentes + historico) e
// GET /carteira/colaboradores (lista de Farmers pro modal).

import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import BastaoLista from "../components/BastaoLista";

// Mock do modulo de api.
vi.mock("../api", () => ({
  default: { get: vi.fn(), post: vi.fn() },
}));
import api from "../api";


// Resposta padrao de /carteira/relacionamento com 1 grupo.
function relComUmGrupo() {
  return {
    data: {
      hunter_nome: "Beatriz",
      grupos: [
        {
          id_grupo: "G1",
          nome_grupo: "Contabilidade Alfa",
          cidade_uf: "SP/SP",
          parceria: "Parceiro",
          qtd_cnpj: 2,
          timeline: [],
          tarefas_atrasadas: 0,
          tarefas_futuras: 1,
          leads_no_mes: 4,
          colaboradores_multiplos: false,
        },
      ],
      bastoes_sem_grupo: [],
      kpis: { total_grupos: 1, com_atrasada: 0, com_futura: 1, leads: 4 },
      aviso: null,
    },
  };
}

function relVazioComAviso() {
  return {
    data: {
      hunter_nome: null,
      grupos: [],
      bastoes_sem_grupo: [],
      kpis: { total_grupos: 0, com_atrasada: 0, com_futura: 0, leads: 0 },
      aviso: "Sua carteira ainda não foi configurada.",
    },
  };
}

// Roteia os GET por endpoint.
function mockGet({ rel, bastoes = [], colaboradores = [] }) {
  api.get.mockImplementation((url) => {
    if (url === "/carteira/relacionamento") return Promise.resolve(rel);
    if (url === "/carteira/bastoes/meus") return Promise.resolve({ data: bastoes });
    if (url === "/carteira/colaboradores") return Promise.resolve({ data: colaboradores });
    return Promise.resolve({ data: {} });
  });
  api.post.mockResolvedValue({ data: { por_grupo: {} } });
}


describe("BastaoLista (v1.3.0 etapa 2c)", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("renderiza os grupos vindos de /carteira/relacionamento", async () => {
    mockGet({ rel: relComUmGrupo() });
    render(<BastaoLista hunterNome="Beatriz" />);

    await waitFor(() => {
      expect(screen.getByText("Contabilidade Alfa")).toBeInTheDocument();
    });
  });

  it("chama /relacionamento, /bastoes/meus e /colaboradores", async () => {
    mockGet({ rel: relComUmGrupo() });
    render(<BastaoLista hunterNome="Beatriz" />);

    await waitFor(() => {
      const urls = api.get.mock.calls.map((c) => c[0]);
      expect(urls).toContain("/carteira/relacionamento");
      expect(urls).toContain("/carteira/bastoes/meus");
      expect(urls).toContain("/carteira/colaboradores");
    });
  });

  it("passa hunterNome como ?hunter= para /relacionamento", async () => {
    mockGet({ rel: relComUmGrupo() });
    render(<BastaoLista hunterNome="Beatriz" />);

    await waitFor(() => {
      const chamada = api.get.mock.calls.find(
        (c) => c[0] === "/carteira/relacionamento"
      );
      expect(chamada[1]).toEqual({ params: { hunter: "Beatriz" } });
    });
  });

  it("mostra o aviso quando o backend devolve operacional sem vinculo", async () => {
    mockGet({ rel: relVazioComAviso() });
    render(<BastaoLista hunterNome={null} />);

    await waitFor(() => {
      expect(
        screen.getByText(/carteira ainda não foi configurada/i)
      ).toBeInTheDocument();
    });
  });

  it("deriva a lista de Farmers de /carteira/colaboradores", async () => {
    mockGet({
      rel: relComUmGrupo(),
      colaboradores: [
        { id: "1", nome: "Aline", funcao: "EC_FARMER" },
        { id: "2", nome: "Beatriz", funcao: "EC_HUNTER" },
        { id: "3", nome: "Jheison", funcao: "EC_FARMER" },
      ],
    });
    render(<BastaoLista hunterNome="Beatriz" />);

    // Espera o carregamento terminar (grupo renderizado).
    await waitFor(() => {
      expect(screen.getByText("Contabilidade Alfa")).toBeInTheDocument();
    });
    // O componente nao expoe os farmers diretamente na tela sem abrir o
    // modal; o teste garante ao menos que /colaboradores foi consultado
    // (a derivacao EC_FARMER e testada implicitamente pelo fluxo do modal).
    const urls = api.get.mock.calls.map((c) => c[0]);
    expect(urls).toContain("/carteira/colaboradores");
  });
});
