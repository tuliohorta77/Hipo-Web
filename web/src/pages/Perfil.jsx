// web/src/pages/Perfil.jsx
//
// Página de perfil do usuário logado. Exibe dados básicos (nome, email,
// cargo, módulos) e permite trocar a senha.
//
// Acessível a todos os usuários logados.

import { useState } from 'react';
import { KeyRound, AlertCircle, CheckCircle2, User, Phone } from 'lucide-react';
import api, { getUser, USER_KEY } from '../api';

import Card from '../components/ui/Card';
import PageHeader from '../components/ui/PageHeader';
import Button from '../components/ui/Button';
import Input from '../components/ui/Input';
import Badge from '../components/ui/Badge';

// Rótulos amigáveis pros módulos
const MODULOS_LABEL = {
  pex: 'PEX',
  po: 'POs',
  bd: 'BD Ativados',
  metas: 'Metas',
  carteira: 'Carteira',
  usuarios: 'Usuários',
};

export default function Perfil() {
  const user = getUser() || {};
  const [senhaAtual, setSenhaAtual] = useState('');
  const [novaSenha, setNovaSenha] = useState('');
  const [confirmacao, setConfirmacao] = useState('');
  const [loading, setLoading] = useState(false);
  const [msg, setMsg] = useState(null);

  // Telefone tem estado e mensagem PRÓPRIOS. Compartilhar `msg` com a troca
  // de senha faria "Telefone salvo" aparecer dentro do formulário de senha,
  // e o usuário procuraria o que tinha dado errado ali.
  const [telefone, setTelefone] = useState(user.telefone || '');
  const [salvandoTelefone, setSalvandoTelefone] = useState(false);
  const [msgTelefone, setMsgTelefone] = useState(null);

  /*
    Grava e ATUALIZA O localStorage no mesmo passo.

    O front lê o usuário do `hipo_user`, gravado no login. Sem reescrever
    ali, o telefone novo sumiria da tela no próximo F5 e voltaria só depois
    de logout/login — a mesma armadilha que já mordeu as permissões.
  */
  async function salvarTelefone(e) {
    e.preventDefault();
    setSalvandoTelefone(true);
    setMsgTelefone(null);
    try {
      const { data } = await api.put('/auth/perfil', { telefone: telefone.trim() || null });
      setTelefone(data.telefone || '');
      try {
        const atual = JSON.parse(localStorage.getItem(USER_KEY) || '{}');
        localStorage.setItem(USER_KEY, JSON.stringify({ ...atual, telefone: data.telefone }));
      } catch {
        /* localStorage indisponível não pode derrubar o salvamento */
      }
      setMsgTelefone({ tipo: 'ok', texto: 'Telefone salvo.' });
    } catch (err) {
      const detail = err.response?.data?.detail;
      setMsgTelefone({
        tipo: 'erro',
        texto: typeof detail === 'string' ? detail : 'Não foi possível salvar o telefone.',
      });
    } finally {
      setSalvandoTelefone(false);
    }
  }

  function validarLocalmente() {
    if (!senhaAtual) return 'Informe a senha atual.';
    if (!novaSenha) return 'Informe a nova senha.';
    if (novaSenha.length < 6) return 'A nova senha precisa ter pelo menos 6 caracteres.';
    if (novaSenha !== confirmacao) return 'A confirmação não bate com a nova senha.';
    if (novaSenha === senhaAtual) return 'A nova senha não pode ser igual à atual.';
    return null;
  }

  async function onSubmit(e) {
    e.preventDefault();
    setMsg(null);

    const erroLocal = validarLocalmente();
    if (erroLocal) {
      setMsg({ tipo: 'erro', texto: erroLocal });
      return;
    }

    setLoading(true);
    try {
      await api.put('/auth/senha', {
        senha_atual: senhaAtual,
        nova_senha: novaSenha,
      });
      setMsg({ tipo: 'ok', texto: 'Senha alterada com sucesso.' });
      setSenhaAtual('');
      setNovaSenha('');
      setConfirmacao('');
    } catch (err) {
      const detail = err.response?.data?.detail;
      const texto =
        typeof detail === 'string'
          ? detail
          : Array.isArray(detail)
          ? detail.map((d) => d.msg).join(' • ')
          : err.message;
      setMsg({ tipo: 'erro', texto: `Erro: ${texto}` });
    } finally {
      setLoading(false);
    }
  }

  const initials = (user.nome || user.email || 'U')
    .split(' ')
    .slice(0, 2)
    .map((p) => p.charAt(0).toUpperCase())
    .join('');

  return (
    <>
      <PageHeader
        title="Perfil"
        subtitle="Seus dados e troca de senha."
      />

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* Coluna 1: dados do usuário */}
        <Card>
          <div className="flex items-center gap-4 mb-4">
            <div className="w-14 h-14 rounded-full bg-hipo-blueSoft text-hipo-blue flex items-center justify-center text-lg font-semibold">
              {initials}
            </div>
            <div>
              <h2 className="text-lg font-semibold text-hipo-ink">
                {user.nome || '—'}
              </h2>
              <p className="text-sm text-hipo-slate">{user.email || '—'}</p>
            </div>
          </div>

          <div className="space-y-3 pt-4 border-t border-hipo-border">
            <div>
              <p className="text-xs text-hipo-slate uppercase tracking-wider mb-1">
                Cargo
              </p>
              <Badge tone="info">{user.cargo || 'sem cargo'}</Badge>
            </div>

            <div>
              <p className="text-xs text-hipo-slate uppercase tracking-wider mb-1.5">
                Módulos acessíveis
              </p>
              <div className="flex flex-wrap gap-1.5">
                {(user.modulos || []).length === 0 ? (
                  <span className="text-sm text-hipo-muted">nenhum</span>
                ) : (
                  user.modulos.map((m) => (
                    <Badge key={m} tone="success">
                      {MODULOS_LABEL[m] || m}
                    </Badge>
                  ))
                )}
              </div>
            </div>
          </div>
        </Card>

        {/* Telefone: sai na proposta comercial, ao lado de nome e e-mail. */}
        <Card>
          <div className="flex items-center gap-2 mb-1">
            <Phone size={18} className="text-hipo-blue" />
            <h2 className="text-lg font-semibold text-hipo-ink">Contato</h2>
          </div>
          <p className="text-sm text-hipo-slate mb-4">
            Seu telefone sai no slide de fechamento das propostas que você
            gerar, junto do nome e do e-mail. Sem ele, o slide mostra um
            travessão e o cliente liga para a recepção.
          </p>

          <form onSubmit={salvarTelefone} className="space-y-4">
            <Input
              label="Telefone"
              value={telefone}
              onChange={(e) => setTelefone(e.target.value)}
              placeholder="+55 (11) 9 0000-0000"
              hint="Formato livre — sai na proposta exatamente como digitado."
            />

            {msgTelefone && (
              <div
                role="alert"
                className={
                  'flex items-start gap-2 px-3 py-2.5 rounded-lg text-sm '
                  + (msgTelefone.tipo === 'ok'
                    ? 'bg-hipo-successSoft text-hipo-success'
                    : 'bg-hipo-dangerSoft text-hipo-danger')
                }
              >
                {msgTelefone.tipo === 'ok'
                  ? <CheckCircle2 size={16} className="mt-0.5 shrink-0" />
                  : <AlertCircle size={16} className="mt-0.5 shrink-0" />}
                <span>{msgTelefone.texto}</span>
              </div>
            )}

            <Button type="submit" loading={salvandoTelefone}>
              Salvar telefone
            </Button>
          </form>
        </Card>

        {/* Coluna 2: troca de senha */}
        <Card>
          <div className="flex items-center gap-2 mb-4">
            <KeyRound size={18} className="text-hipo-blue" />
            <h2 className="text-lg font-semibold text-hipo-ink">Trocar senha</h2>
          </div>

          <form onSubmit={onSubmit} className="space-y-4">
            <Input
              label="Senha atual"
              type="password"
              value={senhaAtual}
              onChange={(e) => setSenhaAtual(e.target.value)}
              autoComplete="current-password"
              required
            />

            <Input
              label="Nova senha (mín. 6 caracteres)"
              type="password"
              value={novaSenha}
              onChange={(e) => setNovaSenha(e.target.value)}
              autoComplete="new-password"
              required
              minLength={6}
            />

            <Input
              label="Confirmar nova senha"
              type="password"
              value={confirmacao}
              onChange={(e) => setConfirmacao(e.target.value)}
              autoComplete="new-password"
              required
              minLength={6}
            />

            {msg && (
              <div
                role="alert"
                className={
                  'flex items-start gap-2 px-3 py-2.5 rounded-lg text-sm ' +
                  (msg.tipo === 'ok'
                    ? 'bg-emerald-50 border border-emerald-100 text-emerald-700'
                    : 'bg-red-50 border border-red-100 text-hipo-danger')
                }
              >
                {msg.tipo === 'ok' ? (
                  <CheckCircle2 size={16} className="mt-0.5 shrink-0" />
                ) : (
                  <AlertCircle size={16} className="mt-0.5 shrink-0" />
                )}
                <span>{msg.texto}</span>
              </div>
            )}

            <Button
              type="submit"
              loading={loading}
              icon={!loading ? KeyRound : undefined}
              className="w-full"
            >
              {loading ? 'Alterando...' : 'Alterar senha'}
            </Button>
          </form>
        </Card>
      </div>
    </>
  );
}
