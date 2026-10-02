// web/src/components/monitor/DetalheIndicador.jsx
//
// O clique na carinha: a lista do que está sendo contado no número do
// quadro.
//
// ── A lista é feita das MESMAS linhas do quadro ──────────────────────
// `GET /monitor/detalhe/{chave}` usa as mesmas funções que o painel usa para
// contar (routers/monitor.py). O número no topo do modal vem da mesma
// resposta da lista, e não do painel que está atrás: se a TV leu há 50
// segundos e alguém registrou um desfecho nesse meio-tempo, o modal mostra o
// número de AGORA junto com a lista de agora — os dois sempre batem entre si.
//
// ── Taxa e soma dizem como viraram número ────────────────────────────
// Em % NOSHOW a lista é o DENOMINADOR (as reuniões fechadas) e os no-shows
// vêm primeiro, marcados; em NMRR e Ticket Médio a coluna é a mensalidade.
// A frase de `resumo` ("3 no-shows em 27 reuniões fechadas") existe porque
// taxa não se confere contando linhas, e sem ela a lista parece não bater.
//
// ── Dashboard operacional: a linha leva à ação ───────────────────────
// Reunião abre o MESMO formulário da Agenda (ModalReuniao), onde se corrige
// o desfecho — que é exatamente o que se quer fazer quando um no-show está
// errado na TV. Oportunidade abre a tela de Oportunidades já buscando pelo
// número. Depois de salvar, a lista e o painel atrás recarregam.

import { useCallback, useEffect, useState } from 'react';
import { ExternalLink, ShieldCheck } from 'lucide-react';

import api, { getUser } from '../../api';
import Modal from '../ui/Modal';
import Badge from '../ui/Badge';
import Empty from '../ui/Empty';
import AlertMessage from '../ui/AlertMessage';
import Table, { Th, Tr, Td } from '../ui/Table';
import ModalReuniao from '../crm/ModalReuniao';
import { POR_DESFECHO } from '../crm/agendaComum';
import { dataCompleta, mensagemDeErro } from '../crm/tarefaComum';
import { formatar } from './monitorComum';

// Os quadros em que a lista de reuniões ganha a coluna Nota (scorecard do
// roteiro, 0 a 20): o APRE, que é de onde a média sai, e o próprio
// SCORECARD.
const COM_NOTA = ['apre', 'scorecard'];

const TOM_NOTA = (n) => {
  if (n >= 15) return 'success';
  if (n >= 10) return 'warning';
  return 'danger';
};

function SeloNota({ item }) {
  if (item.nota === null || item.nota === undefined) {
    const texto = {
      avaliando: 'avaliando…',
      erro: 'falhou',
    }[item.nota_status] || '—';
    return <span className="text-xs text-hipo-muted">{texto}</span>;
  }
  return (
    <span className="inline-flex items-center gap-1">
      <Badge tone={TOM_NOTA(item.nota)}>
        <span className="tabular-nums">{formatar(item.nota, 'inteiro')}/20</span>
      </Badge>
      {item.nota_status === 'validada' && (
        <ShieldCheck
          size={13}
          className="text-hipo-success"
          aria-label="Validada pela gestão"
        />
      )}
    </span>
  );
}

function moeda(valor) {
  if (valor === null || valor === undefined) return '—';
  return Number(valor).toLocaleString('pt-BR', { style: 'currency', currency: 'BRL' });
}

function SeloDesfecho({ item }) {
  const d = POR_DESFECHO[item.desfecho];
  if (!d) return <Badge tone="warning">{item.desfecho_rotulo || 'Sem desfecho'}</Badge>;
  const Icone = d.Icone;
  return (
    <Badge tone={d.tom}>
      {Icone && <Icone size={12} aria-hidden="true" />}
      {d.rotulo}
    </Badge>
  );
}

function linkOportunidade(numero) {
  return `/crm/oportunidades?q=${encodeURIComponent(numero)}`;
}

function TabelaReunioes({ itens, chave, onAbrirReuniao }) {
  // Em AGEND MÊS a data que conta é a da MARCAÇÃO; a da reunião vira coluna
  // de apoio. Nos outros quadros é o contrário, e a coluna extra sobra.
  const pelaMarcacao = chave === 'agendamentos_mes';
  const comNota = COM_NOTA.includes(chave);
  return (
    <Table>
      <thead>
        <tr>
          <Th>{pelaMarcacao ? 'Marcada em' : 'Reunião'}</Th>
          {pelaMarcacao && <Th>Reunião</Th>}
          <Th>Empresa</Th>
          <Th>Anfitrião</Th>
          <Th>Agendado por</Th>
          <Th>Desfecho</Th>
          {comNota && <Th>Nota</Th>}
        </tr>
      </thead>
      <tbody>
        {itens.map((i, n) => (
          <Tr
            key={`${i.reuniao_id}-${n}`}
            onClick={() => onAbrirReuniao(i.reuniao_id)}
            // No % NOSHOW (denominador) e no SCORECARD (reunião ainda sem
            // nota), a linha que não entra na conta fica em segundo plano.
            className={i.conta ? '' : 'opacity-60'}
            aria-label={`Abrir reunião com ${i.empresa || 'empresa sem nome'}`}
          >
            <Td className="whitespace-nowrap tabular-nums">
              {i.tipo_sigla && (
                <span className="mr-1.5 text-xs font-semibold text-hipo-blue">{i.tipo_sigla}</span>
              )}
              {dataCompleta(i.data)}
            </Td>
            {pelaMarcacao && (
              <Td className="whitespace-nowrap tabular-nums text-hipo-slate">
                {dataCompleta(i.reuniao_inicio)}
              </Td>
            )}
            <Td>
              <span className="block truncate max-w-[18rem]">{i.empresa || '—'}</span>
              {i.oportunidade_numero && (
                <span className="text-xs text-hipo-slate">{i.oportunidade_numero}</span>
              )}
              {!i.oportunidade_numero && i.conta_id && (
                <span className="text-xs text-hipo-slate">parceiro</span>
              )}
            </Td>
            <Td className="text-hipo-slate">{i.pessoa || '—'}</Td>
            <Td className="text-hipo-slate">{i.agendado_por_nome || '—'}</Td>
            <Td><SeloDesfecho item={i} /></Td>
            {comNota && <Td className="whitespace-nowrap"><SeloNota item={i} /></Td>}
          </Tr>
        ))}
      </tbody>
    </Table>
  );
}

function TabelaOportunidades({ itens, comValor, semLink = false }) {
  return (
    <Table>
      <thead>
        <tr>
          <Th>Quando</Th>
          <Th>Empresa</Th>
          <Th>Oportunidade</Th>
          <Th>Registrado por</Th>
          {comValor && <Th align="right">Mensalidade</Th>}
        </tr>
      </thead>
      <tbody>
        {itens.map((i, n) => (
          <Tr key={`${i.oportunidade_id}-${n}`}>
            <Td className="whitespace-nowrap tabular-nums">{dataCompleta(i.data)}</Td>
            <Td><span className="block truncate max-w-[20rem]">{i.empresa || '—'}</span></Td>
            <Td>
              {i.oportunidade_numero && semLink ? (
                i.oportunidade_numero
              ) : i.oportunidade_numero ? (
                <a
                  href={linkOportunidade(i.oportunidade_numero)}
                  className="inline-flex items-center gap-1 text-hipo-blue hover:underline"
                >
                  {i.oportunidade_numero}
                  <ExternalLink size={12} aria-hidden="true" />
                </a>
              ) : '—'}
            </Td>
            <Td className="text-hipo-slate">{i.pessoa || '—'}</Td>
            {comValor && (
              <Td align="right" className="tabular-nums">{moeda(i.valor)}</Td>
            )}
          </Tr>
        ))}
      </tbody>
    </Table>
  );
}

export default function DetalheIndicador({
  aberto, chave, ano, mes, onFechar, onMudou,
}) {
  const [detalhe, setDetalhe] = useState(null);
  const [erro, setErro] = useState(null);
  const [carregando, setCarregando] = useState(false);
  const [reuniaoAberta, setReuniaoAberta] = useState(null);
  const [usuarios, setUsuarios] = useState([]);

  const carregar = useCallback(async () => {
    if (!chave) return;
    setCarregando(true);
    try {
      const { data } = await api.get(`/monitor/detalhe/${chave}`, { params: { ano, mes } });
      setDetalhe(data);
      setErro(null);
    } catch (err) {
      setErro(mensagemDeErro(err, 'Não foi possível abrir a lista deste quadro.'));
    } finally {
      setCarregando(false);
    }
  }, [chave, ano, mes]);

  useEffect(() => {
    if (!aberto) { setDetalhe(null); setErro(null); return; }
    carregar();
  }, [aberto, carregar]);

  // A lista de usuários só é necessária para o formulário da reunião —
  // buscar no clique, e não ao abrir a lista, poupa uma request a cada
  // olhada na TV.
  // Conta de TV (cargo Monitor): só o painel. A lista abre, mas a linha não
  // leva ao formulário da reunião nem à oportunidade — a API barraria (403).
  const somenteLeitura = getUser()?.cargo === 'Monitor';

  function abrirReuniao(id) {
    if (!id || somenteLeitura) return;
    if (usuarios.length === 0) {
      api.get('/crm/dominio/usuarios')
        .then(({ data }) => setUsuarios(Array.isArray(data) ? data : []))
        .catch(() => setUsuarios([]));
    }
    setReuniaoAberta(id);
  }

  function aoMudar() {
    carregar();
    onMudou?.();
  }

  const itens = detalhe?.itens || [];
  const titulo = detalhe ? `${detalhe.sigla} — ${detalhe.rotulo}` : 'Carregando…';
  const subtitulo = detalhe
    ? `${detalhe.rotulo_mes.charAt(0).toUpperCase()}${detalhe.rotulo_mes.slice(1)} · até hoje`
    : undefined;
  const comValor = ['nmrr', 'ticket_medio', 'contratos'].includes(chave);

  return (
    <>
      <Modal
        aberto={aberto}
        onFechar={onFechar}
        titulo={titulo}
        subtitulo={subtitulo}
        size="xl"
      >
        <div className="space-y-4">
          {erro && <AlertMessage tipo="erro">{erro}</AlertMessage>}

          {detalhe && (
            <div className="flex flex-wrap items-baseline gap-x-4 gap-y-1">
              <span className="text-3xl font-bold tabular-nums text-hipo-ink">
                {formatar(detalhe.resultado, detalhe.formato)}
              </span>
              <span className="text-sm text-hipo-slate">{detalhe.resumo}</span>
              {chave === 'noshow' && itens.length > 0 && (
                <span className="text-xs text-hipo-muted">
                  No-shows primeiro; as demais são o denominador.
                </span>
              )}
              {chave === 'scorecard' && itens.length > 0 && (
                <span className="text-xs text-hipo-muted">
                  Pior nota primeiro; as sem nota ficam fora da média. Clique para ver o scorecard.
                </span>
              )}
            </div>
          )}
          {detalhe && (
            <p className="text-xs text-hipo-muted">{detalhe.fonte}</p>
          )}

          {!detalhe && carregando && (
            <p className="py-10 text-center text-sm text-hipo-slate">Carregando lista…</p>
          )}

          {detalhe && itens.length === 0 && (
            <Empty
              title="Nada contando neste número"
              description={
                detalhe.tipo === 'nenhum'
                  ? detalhe.resumo
                  : 'Nenhum registro entra neste quadro no mês até agora.'
              }
            />
          )}

          {detalhe && itens.length > 0 && detalhe.tipo === 'reunioes' && (
            <TabelaReunioes itens={itens} chave={chave} onAbrirReuniao={abrirReuniao} />
          )}
          {detalhe && itens.length > 0 && detalhe.tipo === 'oportunidades' && (
            <TabelaOportunidades itens={itens} comValor={comValor} semLink={somenteLeitura} />
          )}
        </div>
      </Modal>

      {/* Montado só quando abre: o formulário busca tipos e contatos ao montar. */}
      {reuniaoAberta && (
        <ModalReuniao
          aberto
          nivel={2}
          reuniaoId={reuniaoAberta}
          usuarios={usuarios}
          onFechar={() => { setReuniaoAberta(null); aoMudar(); }}
          onSalvo={aoMudar}
        />
      )}
    </>
  );
}
