// web/src/components/crm/GravadorLigacoes.jsx
//
// Gravador de ligações no Perfil (entrega 056 — Vivo Voz Negócio).
//
// O gravador é um programinha que roda na bandeja do Windows, ao lado do
// softphone da Vivo: percebe a chamada, grava microfone e saída em dois
// canais e manda para o HIPO, que transcreve e põe na oportunidade.
//
// Aqui a pessoa: baixa o instalador, gera o token de UMA máquina (que
// aparece uma vez só, para colar no instalador), vê se o gravador de cada
// máquina está ligado agora e revoga o de um computador perdido ou trocado.

import { useCallback, useEffect, useState } from 'react';
import { Copy, Check, Download, Headset, KeyRound, Trash2 } from 'lucide-react';

import api from '../../api';
import AlertMessage from '../ui/AlertMessage';
import Badge from '../ui/Badge';
import Button from '../ui/Button';
import Card from '../ui/Card';
import Input from '../ui/Input';
import { mensagemDeErro } from './contatoComum';
import { dataHoraCurta } from './ligacoes';

export const LINK_INSTALADOR = '/downloads/hipo-gravador.zip';

function TokenNovo({ token, onFechar }) {
  const [copiado, setCopiado] = useState(false);

  async function copiar() {
    try {
      await navigator.clipboard.writeText(token);
      setCopiado(true);
    } catch {
      setCopiado(false);
    }
  }

  return (
    <div className="space-y-2 rounded-lg border border-hipo-successBorder bg-hipo-successSoft p-3">
      <p className="text-sm font-medium text-hipo-success">
        Token gerado. Copie agora — ele não aparece de novo.
      </p>
      <div className="flex items-center gap-2">
        <code
          data-testid="token-gravador"
          className="flex-1 min-w-0 truncate rounded border border-hipo-border bg-hipo-card px-2 py-1.5 text-xs text-hipo-ink"
        >
          {token}
        </code>
        <Button size="sm" variant="secondary" icon={copiado ? Check : Copy} onClick={copiar}>
          {copiado ? 'Copiado' : 'Copiar'}
        </Button>
      </div>
      <ol className="list-decimal pl-5 text-xs text-hipo-slate space-y-0.5">
        <li>Baixe o instalador (botão acima) e extraia o zip.</li>
        <li>
          Na pasta extraída, clique com o botão direito em <b>instalar.ps1</b> →
          {' '}<b>Executar com o PowerShell</b>.
        </li>
        <li>Cole este token quando ele pedir. No fim, aparece um ícone verde perto do relógio.</li>
      </ol>
      <Button size="sm" variant="ghost" onClick={onFechar}>Já instalei</Button>
    </div>
  );
}

export default function GravadorLigacoes() {
  const [dados, setDados] = useState(null);
  const [erro, setErro] = useState(null);
  const [nome, setNome] = useState('Meu computador');
  const [gerando, setGerando] = useState(false);
  const [token, setToken] = useState(null);
  const [revogando, setRevogando] = useState(null);

  const carregar = useCallback(async () => {
    try {
      const r = await api.get('/crm/ligacoes/gravadores');
      setDados(r?.data || { gravadores: [], disponivel: true, problemas: [] });
      setErro(null);
    } catch (err) {
      setErro(mensagemDeErro(err, 'Não foi possível carregar os gravadores.'));
    }
  }, []);

  useEffect(() => { carregar(); }, [carregar]);

  async function gerar(e) {
    e.preventDefault();
    setGerando(true);
    setErro(null);
    try {
      const { data } = await api.post('/crm/ligacoes/gravadores', { nome: nome.trim() });
      setToken(data.token);
      carregar();
    } catch (err) {
      setErro(mensagemDeErro(err, 'Não foi possível gerar o token.'));
    } finally {
      setGerando(false);
    }
  }

  async function revogar(id) {
    setErro(null);
    try {
      await api.delete(`/crm/ligacoes/gravadores/${id}`);
      setRevogando(null);
      carregar();
    } catch (err) {
      setErro(mensagemDeErro(err, 'Não foi possível revogar.'));
    }
  }

  const gravadores = dados?.gravadores || [];

  return (
    <Card>
      <div className="flex items-center gap-2 mb-1">
        <Headset size={18} className="text-hipo-blue" />
        <h2 className="text-lg font-semibold text-hipo-ink">Gravador de ligações</h2>
      </div>
      <p className="text-sm text-hipo-slate mb-3">
        Grava as ligações do Vivo Voz Negócio feitas neste computador e manda para o HIPO, que
        transcreve e coloca cada uma na oportunidade. Ligue pelo telefone do contato dentro do HIPO
        para a gravação já cair na negociação certa. Para uma ligação pessoal, pause pelo ícone
        perto do relógio.
      </p>

      <a
        href={LINK_INSTALADOR}
        download
        className="inline-flex items-center gap-1.5 text-sm text-hipo-blue hover:underline mb-3"
      >
        <Download size={14} aria-hidden="true" />
        Baixar o instalador (Windows)
      </a>

      {erro && <AlertMessage tipo="erro" className="mb-3">{erro}</AlertMessage>}
      {dados && !dados.disponivel && (
        <AlertMessage tipo="info" className="mb-3">
          A gravação ainda está desligada no servidor ({(dados.problemas || []).join('; ')}).
          O gravador pode ser instalado; as ligações ficam guardadas na máquina até ligar.
        </AlertMessage>
      )}

      {gravadores.length > 0 && (
        <ul className="mb-3 divide-y divide-hipo-border rounded-lg border border-hipo-border">
          {gravadores.map((g) => (
            <li key={g.id} className="flex flex-wrap items-center gap-2 px-3 py-2">
              <div className="min-w-0 flex-1">
                <p className="text-sm font-medium text-hipo-ink truncate">{g.nome}</p>
                <p className="text-xs text-hipo-slate">
                  {g.maquina || 'ainda não conectou'}
                  {g.versao_agente ? ` · v${g.versao_agente}` : ''}
                  {' · '}token {g.token_prefixo}…
                </p>
              </div>
              {g.online ? (
                <Badge tone="success">Ligado agora</Badge>
              ) : (
                <Badge tone="neutral">
                  {g.ultimo_contato_em ? `Desligado · ${dataHoraCurta(g.ultimo_contato_em)}` : 'Nunca conectou'}
                </Badge>
              )}
              {revogando === g.id ? (
                <>
                  <Button size="sm" variant="danger" onClick={() => revogar(g.id)}>Revogar</Button>
                  <Button size="sm" variant="ghost" onClick={() => setRevogando(null)}>Cancelar</Button>
                </>
              ) : (
                <Button
                  size="sm"
                  variant="ghost"
                  icon={Trash2}
                  aria-label={`Revogar ${g.nome}`}
                  title="Revogar: este computador para de mandar gravações"
                  onClick={() => setRevogando(g.id)}
                />
              )}
            </li>
          ))}
        </ul>
      )}

      {token ? (
        <TokenNovo token={token} onFechar={() => setToken(null)} />
      ) : (
        <form onSubmit={gerar} className="flex flex-wrap items-end gap-2">
          <div className="flex-1 min-w-[12rem]">
            <Input
              label="Nome deste computador"
              value={nome}
              onChange={(e) => setNome(e.target.value)}
              maxLength={80}
            />
          </div>
          <Button type="submit" icon={KeyRound} loading={gerando} disabled={!nome.trim()}>
            Gerar token
          </Button>
        </form>
      )}
    </Card>
  );
}
