// web/src/api.js
// Cliente axios central com injeção automática de token e tratamento de 401.
import axios from "axios";

export const TOKEN_KEY = "hipo_token";
export const USER_KEY = "hipo_user";

const api = axios.create({
  baseURL: "/api",
});

// Injeta Bearer em toda request
api.interceptors.request.use((cfg) => {
  const token = localStorage.getItem(TOKEN_KEY);
  if (token) {
    cfg.headers = cfg.headers || {};
    cfg.headers.Authorization = `Bearer ${token}`;
  }
  return cfg;
});

// Em 401, limpa sessão e redireciona pra /login
api.interceptors.response.use(
  (r) => r,
  (err) => {
    if (err.response?.status === 401) {
      localStorage.removeItem(TOKEN_KEY);
      localStorage.removeItem(USER_KEY);
      // evita loop se já está em /login
      if (!window.location.pathname.startsWith("/login")) {
        window.location.href = "/login";
      }
    }
    return Promise.reject(err);
  }
);

// Helpers de auth
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

// Retorna os módulos visíveis pro cargo do usuário logado.
// Cargo Hunter/Farmer/EP/Gerente retornam ['carteira'], ADM/Franqueado tudo.
export function getModulos() {
  const u = getUser();
  return Array.isArray(u?.modulos) ? u.modulos : [];
}

// Verifica se o usuário tem acesso ao módulo.
export function podeAcessar(modulo) {
  return getModulos().includes(modulo);
}

// Devolve o path da primeira rota que o usuário pode acessar.
// Usado no Login e no redirect do "/" → primeira aba disponível.
// Ordem de preferência: pex → carteira → po → bd → metas.
// Cargo Hunter/Farmer cai direto em /carteira; ADM cai em /pex.
export function primeiraRotaAcessivel() {
  const mods = getModulos();
  if (mods.includes("pex")) return "/pex";
  if (mods.includes("carteira")) return "/carteira";
  if (mods.includes("po")) return "/pos";
  if (mods.includes("bd")) return "/bd-ativados";
  if (mods.includes("metas")) return "/metas";
  return "/perfil"; // sem módulos: pelo menos perfil
}

export function logout() {
  localStorage.removeItem(TOKEN_KEY);
  localStorage.removeItem(USER_KEY);
  window.location.href = "/login";
}

export default api;
