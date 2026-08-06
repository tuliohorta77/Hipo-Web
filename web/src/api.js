// web/src/api.js
// Cliente axios central com injeção automática de token e tratamento de 401.
import axios from "axios";

export const TOKEN_KEY = "hipo_token";
export const USER_KEY = "hipo_user";

const api = axios.create({
  baseURL: "/api",
});

api.interceptors.request.use((cfg) => {
  const token = localStorage.getItem(TOKEN_KEY);
  if (token) {
    cfg.headers = cfg.headers || {};
    cfg.headers.Authorization = `Bearer ${token}`;
  }
  return cfg;
});

api.interceptors.response.use(
  (r) => r,
  (err) => {
    if (err.response?.status === 401) {
      localStorage.removeItem(TOKEN_KEY);
      localStorage.removeItem(USER_KEY);
      if (!window.location.pathname.startsWith("/login")) {
        window.location.href = "/login";
      }
    }
    return Promise.reject(err);
  }
);

export function isAuthenticated() {
  return !!localStorage.getItem(TOKEN_KEY);
}

export function getUser() {
  const raw = localStorage.getItem(USER_KEY);
  try {
    return raw ? JSON.parse(raw) : null;
  } catch {
    return null;
  }
}

// Módulos visíveis pro cargo do usuário logado (vêm do /auth/me e ficam
// gravados no localStorage no login).
//
// Sprint 0:
//   Franqueado / ADM        -> ['perfil', 'usuarios']
//   EC / SDR / EV / EP      -> ['perfil']
//   cargo extinto ou vazio  -> []
//
// ATENÇÃO: mudança de permissão no backend só reflete depois de relogin.
// Ctrl+Shift+R recarrega os assets mas não zera o localStorage — só
// logout/login força um /auth/me novo.
export function getModulos() {
  const u = getUser();
  return Array.isArray(u?.modulos) ? u.modulos : [];
}

export function podeAcessar(modulo) {
  return getModulos().includes(modulo);
}

// Rotas candidatas para o redirect inicial, em ordem de prioridade.
// Cada entrada é [módulo, rota]. A Sprint 1 acrescenta ['crm', '/crm/contas']
// no topo da lista.
const ROTAS_INICIAIS = [];

// Primeira rota acessível pelo cargo. Sem nenhum módulo operacional
// disponível (estado da Sprint 0), todo cargo cai em /perfil — que é
// visível para qualquer usuário autenticado.
export function primeiraRotaAcessivel() {
  const mods = getModulos();
  const encontrada = ROTAS_INICIAIS.find(([modulo]) => mods.includes(modulo));
  return encontrada ? encontrada[1] : "/perfil";
}

export function logout() {
  localStorage.removeItem(TOKEN_KEY);
  localStorage.removeItem(USER_KEY);
  window.location.href = "/login";
}

export default api;
