// web/src/pages/Login.jsx
import { useState } from 'react';
import { useNavigate, Navigate } from 'react-router-dom';
import { LogIn, AlertCircle } from 'lucide-react';
import api, { TOKEN_KEY, USER_KEY, isAuthenticated } from '../api';
import Logo from '../components/Logo';
import Input from '../components/ui/Input';
import Button from '../components/ui/Button';

export default function Login() {
  const navigate = useNavigate();
  const [email, setEmail] = useState('');
  const [senha, setSenha] = useState('');
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
      form.append('username', email);
      form.append('password', senha);

      const { data } = await api.post('/auth/login', form, {
        headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
      });

      localStorage.setItem(TOKEN_KEY, data.access_token);

      try {
        const me = await api.get('/auth/me');
        localStorage.setItem(USER_KEY, JSON.stringify(me.data));
      } catch {
        // se /me falhar, segue sem dados do user — não bloqueia o login
      }

      navigate('/pex', { replace: true });
    } catch (err) {
      const msg =
        err.response?.data?.detail ||
        err.response?.data?.message ||
        'Falha no login. Verifique e-mail e senha.';
      setErro(typeof msg === 'string' ? msg : 'Credenciais inválidas.');
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="min-h-screen bg-hipo-bg flex items-center justify-center p-4">
      <div className="w-full max-w-sm">
        {/* Brand */}
        <div className="flex flex-col items-center mb-8">
          <Logo size={48} />
          <h1 className="text-h1 text-hipo-ink mt-4">Hipo</h1>
          <p className="text-sm text-hipo-slate mt-1 text-center">
            Acesso à plataforma de operações
          </p>
        </div>

        {/* Form */}
        <form
          onSubmit={onSubmit}
          className="bg-hipo-card border border-hipo-border rounded-2xl shadow-soft p-6 space-y-4"
        >
          <Input
            label="E-mail"
            type="email"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            required
            autoFocus
            placeholder="voce@empresa.com"
          />

          <Input
            label="Senha"
            type="password"
            value={senha}
            onChange={(e) => setSenha(e.target.value)}
            required
            placeholder="••••••••"
          />

          {erro && (
            <div
              role="alert"
              className="flex items-start gap-2 px-3 py-2.5 rounded-lg bg-red-50 border border-red-100 text-hipo-danger text-sm"
            >
              <AlertCircle size={16} className="mt-0.5 shrink-0" />
              <span>{erro}</span>
            </div>
          )}

          <Button
            type="submit"
            loading={loading}
            icon={!loading ? LogIn : undefined}
            className="w-full"
          >
            {loading ? 'Entrando...' : 'Entrar'}
          </Button>
        </form>

        <p className="text-center text-xs text-hipo-muted mt-6">
          v1.0 — Acesso restrito
        </p>
      </div>
    </div>
  );
}
