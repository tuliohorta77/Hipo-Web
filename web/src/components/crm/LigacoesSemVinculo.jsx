// web/src/components/crm/LigacoesSemVinculo.jsx
//
// Gravações que ainda não são de nenhuma negociação (entrega 056).
//
// Uma gravação chega sem vínculo quando ninguém clicou em "ligar" no HIPO
// antes: o cliente retornou a ligação, a pessoa discou direto no softphone.
// Ela só existe para quem ligou (e para a gestão) até alguém dizer de qual
// oportunidade é. Esta faixa fica no topo da tela de Tarefas e some quando
// não há nada pendente — não é mais uma lista para olhar, é um "falta isto".
//
// Descartar serve para a ligação pessoal que o gravador pegou: apaga o
// áudio e a transcrição.

import { useCallback, useEffect, useState } from 'react';
import { Link2, PhoneIncoming, Trash2, ChevronDown, ChevronRight } from 'lucide-react';

import api from '../../api';
import EntityPicker from '../EntityPicker';
import AlertMessage from '../ui/AlertMessage';
import Badge from '../ui/Badge';
import Button from '../ui/Button';
import LigacaoDetalhe from './LigacaoDetalhe';
import { mensagemDeErro } from './contatoComum';
import { TOM_STATUS, dataHoraCurta, duracaoTexto, quando } from './ligacoes';

async function buscarOportunidades(q) {
  const { data } = await api.get('/crm/oportunidades', { params: { q, limit: 20 } });
  return data.itens || [];
}

function Item({ lig, onFeito }) {
  const [aberto, setAberto] = useState(false);
  const [vinculando, setVinculando] = useState(false);
  const [oportunidade, setOportunidade] = useState(null);
  const [ocupado, setOcupado] = useState(false);
  const [erro, setErro] = useState(null);
  const [confirmarDescarte, setConfirmarDescarte] = useState(false);

  async function vincular() {
    if (!oportunidade) return;
    setOcupado(true);
    setErro(null);
    try {
      await api.post(`/crm/ligacoes/${lig.id}/vincular`, { oportunidade_id: oportunidade.id });
      onFeito();
    } catch (err) {
      setErro(mensagemDeErro(err, 'Não foi possível vincular.'));
    } finally {
      setOcupado(false);
    }
  }

  async function descartar() {
    setOcupado(true);
    setErro(null);
    try {
      await api.delete(`/crm/ligacoes/${lig.id}`);
      onFeito();
    } catch (err) {
      setErro(mensagemDeErro(err, 'Não foi possível descartar.'));
      setConfirmarDescarte(false);
    } finally {
      setOcupado(false);
    }
  }

  return (
    <li className="px-3 py-2 space-y-2">
      <div className="flex flex-wrap items-center gap-x-3 gap-y-1">
        <button
          type="button"
          aria-expanded={aberto}
          onClick={() => setAberto((v) => !v)}
          className="inline-flex items-center gap-1 text-sm text-hipo-ink hover:text-hipo-blue"
        >
          {aberto ? <ChevronDown size={14} aria-hidden="true" /> : <ChevronRight size={14} aria-hidden="true" />}
          {dataHoraCurta(quando(lig))}
        </button>
        <span className="text-xs tabular-nums text-hipo-slate">{duracaoTexto(lig.duracao_s)}</span>
        <Badge tone={TOM_STATUS[lig.status] || 'neutral'} className="!px-2 !py-0.5">{lig.status_rotulo}</Badge>
        {lig.resumo && !aberto && (
          <span className="text-xs text-hipo-slate truncate max-w-md">{lig.resumo}</span>
        )}
        <span className="ml-auto flex items-center gap-1.5">
          <Button size="sm" variant="secondary" icon={Link2} onClick={() => setVinculando((v) => !v)}>
            Vincular
          </Button>
          {confirmarDescarte ? (
            <>
              <Button size="sm" variant="danger" loading={ocupado} onClick={descartar}>Apagar gravação</Button>
              <Button size="sm" variant="ghost" onClick={() => setConfirmarDescarte(false)}>Cancelar</Button>
            </>
          ) : (
            <Button
              size="sm"
              variant="ghost"
              icon={Trash2}
              aria-label="Descartar gravação"
              title="Ligação pessoal ou engano: apaga o áudio e a transcrição"
              onClick={() => setConfirmarDescarte(true)}
            />
          )}
        </span>
      </div>

      {vinculando && (
        <div className="flex flex-wrap items-end gap-2">
          <div className="flex-1 min-w-[16rem]">
            <EntityPicker
              label="De qual oportunidade é esta ligação?"
              value={oportunidade}
              onChange={setOportunidade}
              buscar={buscarOportunidades}
              paraItem={(o) => ({ id: o.id, titulo: o.conta_razao_social, subtitulo: o.numero })}
              placeholder="Buscar por empresa, número ou CNPJ"
            />
          </div>
          <Button size="sm" onClick={vincular} loading={ocupado} disabled={!oportunidade}>
            Vincular
          </Button>
        </div>
      )}

      {erro && <AlertMessage tipo="erro">{erro}</AlertMessage>}
      {aberto && <LigacaoDetalhe ligacaoId={lig.id} />}
    </li>
  );
}

export default function LigacoesSemVinculo() {
  const [ligacoes, setLigacoes] = useState([]);
  const [aberta, setAberta] = useState(false);

  const carregar = useCallback(async () => {
    try {
      const { data } = await api.get('/crm/ligacoes/sem-vinculo');
      setLigacoes(data?.ligacoes || []);
    } catch {
      // Faixa acessória: falhou, some — a tela de tarefas segue inteira.
      setLigacoes([]);
    }
  }, []);

  useEffect(() => { carregar(); }, [carregar]);

  if (!ligacoes.length) return null;
  const n = ligacoes.length;

  return (
    <section
      aria-label="Ligações sem vínculo"
      className="shrink-0 rounded-lg border border-hipo-warningBorder bg-hipo-warningSoft"
    >
      <button
        type="button"
        aria-expanded={aberta}
        onClick={() => setAberta((v) => !v)}
        className="w-full flex items-center gap-2 px-3 py-2 text-left text-sm text-hipo-warning"
      >
        <PhoneIncoming size={14} aria-hidden="true" />
        <span className="font-medium">
          {n === 1 ? '1 ligação gravada sem vínculo' : `${n} ligações gravadas sem vínculo`}
        </span>
        <span className="text-xs text-hipo-slate">— diga de qual oportunidade é cada uma</span>
        {aberta
          ? <ChevronDown size={14} className="ml-auto" aria-hidden="true" />
          : <ChevronRight size={14} className="ml-auto" aria-hidden="true" />}
      </button>
      {aberta && (
        <ul className="divide-y divide-hipo-border border-t border-hipo-warningBorder bg-hipo-card rounded-b-lg max-h-[50vh] overflow-y-auto">
          {ligacoes.map((l) => <Item key={l.id} lig={l} onFeito={carregar} />)}
        </ul>
      )}
    </section>
  );
}
