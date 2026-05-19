// web/src/pages/Login.jsx
import { useState } from "react";
import { useNavigate, Navigate } from "react-router-dom";
import { LogIn, AlertCircle } from "lucide-react";
import api, { TOKEN_KEY, USER_KEY, isAuthenticated } from "../api";

export default function Login() {
  const navigate = useNavigate();
  const [email, setEmail] = useState("");
  const [senha, setSenha] = useState("");
  const [loading, setLoading] = useState(false);
  const [erro, setErro] = useState(null);

  // Se já autenticado, manda pra raiz
  if (isAuthenticated()) {
    return <Navigate to="/pex" replace />;
  }

  async function onSubmit(e) {
    e.preventDefault();
    setLoading(true);
    setErro(null);

    try {
      // OAuth2PasswordRequestForm exige application/x-www-form-urlencoded
      // com campos `username` e `password`.
      const form = new URLSearchParams();
      form.append("username", email);
      form.append("password", senha);

      const { data } = await api.post("/auth/login", form, {
        headers: { "Content-Type": "application/x-www-form-urlencoded" },
      });

      localStorage.setItem(TOKEN_KEY, data.access_token);

      // Busca dados do usuário (já com token aplicado pelo interceptor)
      try {
        const me = await api.get("/auth/me");
        localStorage.setItem(USER_KEY, JSON.stringify(me.data));
      } catch {
        // se /me falhar, segue sem dados do user — não bloqueia o login
      }

      navigate("/pex", { replace: true });
    } catch (err) {
      const msg =
        err.response?.data?.detail ||
        err.response?.data?.message ||
        "Falha no login. Verifique e-mail e senha.";
      setErro(typeof msg === "string" ? msg : "Credenciais inválidas.");
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="min-h-screen bg-slate-950 text-slate-100 font-mono flex items-center justify-center p-4">
      <div className="w-full max-w-sm">
        {/* Logo */}
        <div className="flex flex-col items-center mb-8">
          <div className="w-12 h-12 rounded-xl bg-gradient-to-br from-cyan-500 to-blue-600 flex items-center justify-center text-lg font-bold mb-3">
            H
          </div>
          <span className="text-cyan-400 font-bold tracking-widest text-sm">
            HIPO
          </span>
          <p className="text-xs text-slate-500 mt-1">
            Hipotálamo Inteligente de Processos e Operações
          </p>
        </div>

        {/* Form */}
        <form
          onSubmit={onSubmit}
          className="bg-slate-900 border border-slate-800 rounded-xl p-6 space-y-4"
        >
          <div>
            <label className="block text-xs text-slate-500 tracking-wider mb-1.5">
              E-MAIL
            </label>
            <input
              type="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              required
              autoFocus
              className="w-full bg-slate-950 border border-slate-800 focus:border-cyan-500 rounded-lg px-3 py-2 text-sm outline-none transition-colors"
              placeholder="voce@empresa.com"
            />
          </div>

          <div>
            <label className="block text-xs text-slate-500 tracking-wider mb-1.5">
              SENHA
            </label>
            <input
              type="password"
              value={senha}
              onChange={(e) => setSenha(e.target.value)}
              required
              className="w-full bg-slate-950 border border-slate-800 focus:border-cyan-500 rounded-lg px-3 py-2 text-sm outline-none transition-colors"
              placeholder="••••••••"
            />
          </div>

          {erro && (
            <div className="flex items-start gap-2 px-3 py-2 rounded-lg bg-red-500/10 border border-red-500/30 text-red-400 text-xs">
              <AlertCircle size={14} className="mt-0.5 shrink-0" />
              <span>{erro}</span>
            </div>
          )}

          <button
            type="submit"
            disabled={loading}
            className={`w-full flex items-center justify-center gap-2 py-2.5 rounded-lg text-sm font-bold tracking-wider transition-all ${
              loading
                ? "bg-slate-800 text-slate-500 cursor-not-allowed"
                : "bg-cyan-600 hover:bg-cyan-500 text-white"
            }`}
          >
            <LogIn size={15} />
            {loading ? "ENTRANDO..." : "ENTRAR"}
          </button>
        </form>

        <p className="text-center text-xs text-slate-600 mt-4">
          v1.0 — Acesso restrito
        </p>
      </div>
    </div>
  );
}
