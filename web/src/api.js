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

// Módulos visíveis pro cargo do usuário logado (vem do /auth/me).
//  ADM/Franqueado: tudo
//  Gerente/EP:     ['carteira', 'clientes']
//  EV:             ['clientes']
//  Hunter/Farmer:  ['carteira']
//  SDR:            ['agendamento']
export function getModulos() {
  const u = getUser();
  return Array.isArray(u?.modulos) ? u.modulos : [];
}

export function podeAcessar(modulo) {
  return getModulos().includes(modulo);
}

// Primeira rota acessível pelo cargo, na ordem de prioridade.
//   ADM/Franqueado    -> /pex         (tem 'pex')
//   Gerente / EP      -> /contadores  (tem 'carteira')
//   Hunter / Farmer   -> /contadores  (tem 'carteira')
//   EV                -> /vendas      (tem só 'clientes')
//   SDR               -> /agendamento (tem só 'agendamento')
//
// O EV é o único cargo que tem 'clientes' SEM ter 'carteira', então é o
// único que chega no if de 'clientes'. Por isso a rota dele aqui é
// /vendas: o funil de Vendas é a tela do dia-a-dia do EV. Os demais
// cargos com 'clientes' caem nos ifs anteriores (pex/carteira).
//
// O SDR tem só 'agendamento' — cai direto em /agendamento.
//
// O módulo no backend chama 'carteira', no front vira /contadores
// (renomeação visual). Backend continua respondendo em /api/carteira/*.
export function primeiraRotaAcessivel() {
  const mods = getModulos();
  if (mods.includes("pex")) return "/pex";
  if (mods.includes("carteira")) return "/contadores";
  if (mods.includes("clientes")) return "/vendas";
  if (mods.includes("agendamento")) return "/agendamento";
  if (mods.includes("po")) return "/pos";
  if (mods.includes("bd")) return "/bd-ativados";
  if (mods.includes("metas")) return "/metas";
  return "/perfil";
}

export function logout() {
  localStorage.removeItem(TOKEN_KEY);
  localStorage.removeItem(USER_KEY);
  window.location.href = "/login";
}

export default api;
