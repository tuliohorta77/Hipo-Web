// web/src/components/crm/ModelosEmail.jsx
//
// Os modelos de e-mail comercial, editados pela gestão (entrega 050).
//
// Aparece dentro da aba E-mails só para quem pode editar — mesma escolha da
// tabela de preços dentro da aba Proposta: quem ajusta o texto está olhando
// para o e-mail que ele vira. As variáveis ficam ao lado, clicáveis: clicar
// insere `{{nome}}` onde o cursor estava. Variável desconhecida é recusada
// pelo servidor na hora de salvar.

import { useRef, useState } from 'react';
import { ChevronDown, ChevronRight, Save, FileText } from 'lucide-react';

import api from '../../api';
import Input, { Textarea } from '../ui/Input';
import Button from '../ui/Button';
import AlertMessage from '../ui/AlertMessage';
import { mensagemDeErro } from './contatoComum';

function EditorModelo({ modelo, variaveis, onSalvo }) {
  const [nome, setNome] = useState(modelo.nome);
  const [assunto, setAssunto] = useState(modelo.assunto);
  const [corpo, setCorpo] = useState(modelo.corpo);
  const [salvando, setSalvando] = useState(false);
  const [erro, setErro] = useState(null);
  const [ok, setOk] = useState(false);
  // Onde o cursor estava da última vez que a pessoa mexeu no texto. Antes
  // de qualquer clique no campo, a variável vai para o FIM — o navegador
  // diz que o cursor de um textarea nunca tocado está no início, e inserir
  // lá empurraria a saudação para baixo.
  const cursor = useRef(null);

  const sujo = nome !== modelo.nome || assunto !== modelo.assunto || corpo !== modelo.corpo;

  function inserir(nomeVar) {
    const marca = `{{${nomeVar}}}`;
    const [ini, fim] = cursor.current ?? [corpo.length, corpo.length];
    setCorpo(corpo.slice(0, ini) + marca + corpo.slice(fim));
    cursor.current = [ini + marca.length, ini + marca.length];
    setOk(false);
  }

  async function salvar() {
    setSalvando(true);
    setErro(null);
    setOk(false);
    try {
      const { data } = await api.put(`/crm/email/modelos/${modelo.slug}`, { nome, assunto, corpo });
      onSalvo(data);
      setOk(true);
    } catch (err) {
      setErro(mensagemDeErro(err, 'Não foi possível salvar o modelo.'));
    } finally {
      setSalvando(false);
    }
  }

  return (
    <div className="grid grid-cols-1 lg:grid-cols-[1fr_16rem] gap-4">
      <div className="space-y-3">
        {erro && <AlertMessage tipo="erro">{erro}</AlertMessage>}
        {ok && <AlertMessage tipo="ok">Modelo salvo. Vale para os próximos rascunhos.</AlertMessage>}
        <Input label="Nome do modelo" value={nome} onChange={(e) => { setNome(e.target.value); setOk(false); }} />
        <Input label="Assunto" value={assunto} onChange={(e) => { setAssunto(e.target.value); setOk(false); }} />
        <div>
          <Textarea
            label="Texto"
            rows={12}
            value={corpo}
            onChange={(e) => { setCorpo(e.target.value); setOk(false); }}
            onSelect={(e) => { cursor.current = [e.target.selectionStart, e.target.selectionEnd]; }}
            hint="Linha em branco separa parágrafo. A assinatura do Gmail de quem envia entra sozinha no fim."
          />
        </div>
        <div className="flex items-center gap-2">
          <Button size="sm" icon={Save} onClick={salvar} disabled={!sujo} loading={salvando}>
            Salvar modelo
          </Button>
          {modelo.atualizado_por_nome && (
            <span className="text-[11px] text-hipo-muted">
              Última edição: {modelo.atualizado_por_nome}
            </span>
          )}
        </div>
      </div>
      <aside aria-label="Variáveis" className="space-y-1.5">
        <p className="text-xs font-medium text-hipo-ink">Variáveis</p>
        <p className="text-[11px] text-hipo-slate">Clique para inserir no texto.</p>
        <ul className="space-y-1">
          {variaveis.map((v) => (
            <li key={v.nome}>
              <button
                type="button"
                onClick={() => inserir(v.nome)}
                className="w-full text-left rounded-md border border-hipo-border px-2 py-1 hover:bg-hipo-bg"
                title={`Ex.: ${v.exemplo}`}
              >
                <code className="text-[11px] text-hipo-blue">{`{{${v.nome}}}`}</code>
                <span className="block text-[11px] text-hipo-slate">{v.rotulo}</span>
              </button>
            </li>
          ))}
        </ul>
      </aside>
    </div>
  );
}

export default function ModelosEmail({ modelos, variaveis, onSalvo }) {
  const [aberto, setAberto] = useState(false);
  const [slug, setSlug] = useState(modelos[0]?.slug);
  const atual = modelos.find((m) => m.slug === slug);

  return (
    <section aria-label="Modelos de e-mail" className="border-t border-hipo-border pt-4">
      <button
        type="button"
        onClick={() => setAberto((a) => !a)}
        aria-expanded={aberto}
        className="text-sm font-medium text-hipo-ink inline-flex items-center gap-1.5"
      >
        {aberto ? <ChevronDown size={14} /> : <ChevronRight size={14} />}
        <FileText size={14} aria-hidden="true" />
        Modelos de e-mail
        <span className="text-xs font-normal text-hipo-slate">(gestão)</span>
      </button>
      {aberto && atual && (
        <div className="mt-3 space-y-3">
          <div role="tablist" aria-label="Escolher modelo" className="inline-flex rounded-lg border border-hipo-border overflow-hidden">
            {modelos.map((m) => (
              <button
                key={m.slug}
                type="button"
                role="tab"
                aria-selected={m.slug === slug}
                onClick={() => setSlug(m.slug)}
                className={
                  'px-3 h-8 text-xs font-medium transition-colors '
                  + (m.slug === slug ? 'bg-hipo-blue text-white' : 'bg-hipo-card text-hipo-slate hover:bg-hipo-bg')
                }
              >
                {m.nome}
              </button>
            ))}
          </div>
          <EditorModelo key={atual.slug} modelo={atual} variaveis={variaveis} onSalvo={onSalvo} />
        </div>
      )}
    </section>
  );
}
