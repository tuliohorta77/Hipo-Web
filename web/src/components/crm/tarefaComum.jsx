// web/src/components/crm/tarefaComum.jsx
//
// O que as DUAS telas de tarefa compartilham: a aba dentro da oportunidade
// (linha do tempo) e a tela de gestão (quatro colunas).
//
// Existe para que a regra mais importante do módulo — concluir exige agendar
// a próxima — tenha uma implementação só. Duas cópias do mesmo formulário
// divergem no primeiro ajuste, e a que divergir vai ser a que o usuário está
// usando na hora.
//
// Aqui vive: vocabulário de tipo e situação, formatadores de data, o
// formulário de tarefa e os painéis de concluir / cancelar / editar. Cada
// tela decide onde encaixá-los e como desenhar a lista.

import { useEffect, useState } from 'react';
import {
  Check, X, Pencil, Phone, Users, MapPin, FileText,
  Mail, MessageCircle, CircleDot, AlertTriangle, CalendarPlus, CalendarCheck,
} from 'lucide-react';

import api from '../../api';
import Button from '../ui/Button';
import Input, { Select, Textarea } from '../ui/Input';
import { ROTULO_PAPEL, TelefonesDoContato } from './contatoComum';

export const TIPOS = [
  { valor: 'ligacao', rotulo: 'Ligação', Icone: Phone },
  { valor: 'reuniao', rotulo: 'Reunião', Icone: Users },
  { valor: 'visita', rotulo: 'Visita', Icone: MapPin },
  { valor: 'proposta', rotulo: 'Proposta', Icone: FileText },
  { valor: 'email', rotulo: 'E-mail', Icone: Mail },
  { valor: 'whatsapp', rotulo: 'WhatsApp', Icone: MessageCircle },
  { valor: 'outro', rotulo: 'Outro', Icone: CircleDot },
];

export const ICONE_TIPO = Object.fromEntries(TIPOS.map((t) => [t.valor, t.Icone]));

// 045: toda INTERAÇÃO tem uma pessoa do outro lado. Espelha
// TIPOS_EXIGEM_CONTATO de api/services/tarefa.py — o 422 de lá é a rede
// embaixo desta linha. Proposta e Outro podem ser trabalho interno.
export const TIPOS_EXIGEM_CONTATO = ['ligacao', 'reuniao', 'visita', 'whatsapp', 'email'];

export function exigeContato(tipo) {
  return TIPOS_EXIGEM_CONTATO.includes(tipo);
}

/**
 * O alvo de uma tarefa já existente, no formato que o seletor de contato
 * usa: a oportunidade (com a conta dela, para cadastrar gente nova) ou o
 * parceiro.
 */
export function alvoDaTarefa(tarefa) {
  if (!tarefa) return null;
  return tarefa.alvo === 'parceiro' || !tarefa.oportunidade_id
    ? { conta_id: tarefa.conta_id }
    : { oportunidade_id: tarefa.oportunidade_id, conta_id: tarefa.conta_id };
}

/** "com Fulana" + telefones clicáveis, para os cartões e a linha do tempo. */
export function ContatoDaTarefa({ tarefa }) {
  if (!tarefa.contato_id) {
    return exigeContato(tarefa.tipo) && ABERTAS.includes(tarefa.situacao)
      ? <span className="text-xs text-hipo-warning">sem contato definido</span>
      : null;
  }
  return (
    <span className="inline-flex flex-wrap items-center gap-x-2 text-xs text-hipo-slate">
      <span>com <span className="text-hipo-ink">{tarefa.contato_nome}</span></span>
      <TelefonesDoContato
        compacto
        ligacao={{ tarefa_id: tarefa.id, contato_id: tarefa.contato_id }}
        contato={{
          telefone: tarefa.contato_telefone,
          telefone_whatsapp: tarefa.contato_whatsapp,
        }}
      />
    </span>
  );
}

// Cada situação tem um tom e uma palavra. A palavra não é redundância: cor
// sozinha não carrega informação para quem não distingue tons.
export const SITUACAO = {
  atrasada: {
    palavra: 'Atrasado',
    ponto: 'border-hipo-danger bg-hipo-card',
    texto: 'text-hipo-danger',
    icone: 'text-hipo-danger',
    tom: 'danger',
  },
  hoje: {
    palavra: 'Hoje',
    ponto: 'border-hipo-warning bg-hipo-warningSoft',
    texto: 'text-hipo-warning',
    icone: 'text-hipo-warning',
    tom: 'warning',
  },
  futura: {
    palavra: 'Agendado',
    ponto: 'border-hipo-blue bg-hipo-blueSoft',
    texto: 'text-hipo-blue',
    icone: 'text-hipo-blue',
    tom: 'info',
  },
  concluida: {
    palavra: 'concluído',
    ponto: 'border-hipo-success bg-hipo-success',
    texto: 'text-hipo-success',
    icone: 'text-white',
    tom: 'success',
  },
  cancelada: {
    palavra: 'cancelado',
    ponto: 'border-hipo-border bg-hipo-bg',
    texto: 'text-hipo-muted',
    icone: 'text-hipo-muted',
    tom: 'neutral',
  },
};

export const ABERTAS = ['atrasada', 'hoje', 'futura'];
export const STATUS_ABERTOS = ['ativa', 'suspensa'];

/**
 * Concluir esta tarefa obriga a agendar a próxima?
 *
 * Espelha `services/tarefa.exige_proxima` do backend — e existe como função
 * única justamente porque NÃO espelhava: a tela de gestão calculava só
 * `STATUS_ABERTOS.includes(status_oportunidade)`, e em tarefa de parceiro
 * esse campo chega nulo. Resultado: o formulário da próxima nem aparecia, a
 * tela ainda dizia "oportunidade finalizada", e o backend recusava a
 * conclusão com 422. A pessoa ficava sem saída — era preciso abrir o
 * parceiro pelo módulo de Parceiros para conseguir concluir.
 *
 * A regra, agora num lugar só:
 *
 *   sobra OUTRA tarefa aberta   -> não exige. A regra é do ALVO — a
 *                                  oportunidade nunca fica sem próximo
 *                                  passo —, e com outra aberta ela não
 *                                  ficou. Ganha das duas linhas abaixo.
 *   parceiro                    -> exige. Parceria não tem estado final que
 *                                  dispense; sem próximo contato marcado a
 *                                  relação some da agenda.
 *   oportunidade viva           -> exige (ativa ou suspensa).
 *   oportunidade finalizada     -> não exige. Acabou, não há próximo passo.
 *
 * `outrasAbertas` vem pronto do servidor (`tarefa.outras_abertas`), pelo
 * mesmo motivo de `alvo`: é a MESMA conta que o backend refaz, travada, no
 * momento de gravar. Contar aqui exigiria a lista inteira de tarefas do
 * alvo em toda tela que conclui — e a que divergisse seria a que a pessoa
 * está olhando.
 *
 * O default 0 é para o servidor antigo: sem o campo, a tela volta a cobrar
 * a próxima sempre, que é o comportamento ESTRITO. Falhar para o lado que
 * pede demais é chato; para o lado que dispensa seria deixar a
 * oportunidade parar em silêncio.
 */
export function exigeProximaTarefa(alvo, statusOportunidade, outrasAbertas = 0) {
  if (outrasAbertas > 0) return false;
  if (alvo === 'parceiro') return true;
  return STATUS_ABERTOS.includes(statusOportunidade);
}

// ── A ponte para a agenda ────────────────────────────────────────────
//
// Só reunião e visita entram na grade. Ligação, e-mail e WhatsApp não têm
// hora marcada para o cliente, não geram convite e não ocupam slot — pôr
// qualquer tarefa na agenda encheria a grade de itens que não são
// compromissos e destruiria a única coisa que ela promete: mostrar onde
// cabe a próxima reunião.
//
// Espelha a validação do backend (`criar_de_tarefa`), e o 422 de lá é a
// rede embaixo desta linha.
export const TIPOS_AGENDAVEIS = ['reuniao', 'visita'];

/**
 * Esta tarefa pode virar uma reunião na grade?
 *
 * Não basta o tipo: tarefa fechada é histórico imutável, e uma que já está
 * na agenda tem `reuniao_id` preenchido — oferecer "agendar" nas duas
 * levaria o usuário até um botão que devolve erro.
 */
export function podeEntrarNaAgenda(tarefa) {
  return (
    TIPOS_AGENDAVEIS.includes(tarefa.tipo)
    && !tarefa.reuniao_id
    && ABERTAS.includes(tarefa.situacao)
  );
}

export function mensagemDeErro(err, padrao) {
  const d = err?.response?.data?.detail;
  if (typeof d === 'string') return d;
  if (Array.isArray(d) && d[0]?.msg) return d[0].msg;
  if (d?.mensagem) return d.mensagem;
  return padrao;
}

// ── Datas ────────────────────────────────────────────────────────────

/** ISO (UTC) -> valor de <input type="datetime-local"> no fuso local. */
export function paraCampoLocal(iso) {
  const d = iso ? new Date(iso) : new Date();
  const local = new Date(d.getTime() - d.getTimezoneOffset() * 60000);
  return local.toISOString().slice(0, 16);
}

/** Amanhã 09:00, no fuso do usuário. Default de qualquer tarefa nova. */
export function amanhaDeManha() {
  const d = new Date();
  d.setDate(d.getDate() + 1);
  d.setHours(9, 0, 0, 0);
  return paraCampoLocal(d.toISOString());
}

export function paraIso(valorDoCampo) {
  return valorDoCampo ? new Date(valorDoCampo).toISOString() : null;
}

/**
 * '15/mar'.
 *
 * Montado à mão porque `toLocaleDateString('pt-BR', {month:'short'})` devolve
 * "15 de mar." — o "de" quebra a coluna em duas linhas e desalinha os pontos
 * da linha do tempo.
 */
const MESES = ['jan', 'fev', 'mar', 'abr', 'mai', 'jun',
               'jul', 'ago', 'set', 'out', 'nov', 'dez'];

export function dataCurta(iso) {
  const d = new Date(iso);
  return `${String(d.getDate()).padStart(2, '0')}/${MESES[d.getMonth()]}`;
}

export function dataCompleta(iso) {
  if (!iso) return '—';
  return new Date(iso).toLocaleString('pt-BR', {
    day: '2-digit', month: '2-digit', year: 'numeric',
    hour: '2-digit', minute: '2-digit',
  });
}

// ── Formulário ───────────────────────────────────────────────────────

/**
 * `contatoPadrao`: com quem a conversa provavelmente vai ser — na próxima
 * tarefa, a mesma pessoa da que está fechando; na nova, o principal da
 * oportunidade. É sugestão: o campo continua trocável.
 */
export function tarefaVazia(usuarioPadrao = '', contatoPadrao = '') {
  return {
    tipo: 'ligacao',
    titulo: '',
    descricao: '',
    responsavel_id: usuarioPadrao,
    prazo: amanhaDeManha(),
    contato_id: contatoPadrao || '',
  };
}

export function corpoDaTarefa(form) {
  return {
    tipo: form.tipo,
    titulo: form.titulo.trim(),
    descricao: form.descricao.trim() || null,
    responsavel_id: form.responsavel_id,
    prazo: paraIso(form.prazo),
    contato_id: form.contato_id || null,
  };
}

export function formIncompleto(form) {
  return (
    !form.titulo.trim() || !form.responsavel_id || !form.prazo
    || (exigeContato(form.tipo) && !form.contato_id)
  );
}

export function formDaTarefa(tarefa) {
  return {
    tipo: tarefa.tipo,
    titulo: tarefa.titulo,
    descricao: tarefa.descricao || '',
    responsavel_id: tarefa.responsavel_id,
    prazo: paraCampoLocal(tarefa.prazo),
    contato_id: tarefa.contato_id || '',
  };
}

// ── Com quem (045) ───────────────────────────────────────────────────

const NOVO = '__novo__';

/**
 * O seletor do contato da tarefa: as pessoas do comitê primeiro (o
 * principal com estrela), depois o resto da empresa — e "cadastrar novo"
 * no fim, porque quem descobriu agora o nome do RH não pode ficar travado
 * pela obrigação de escolher alguém que ainda não existe no sistema.
 */
export function CampoContato({ alvo, valor, onChange, obrigatorio, idBase, prefixo = '' }) {
  const [opcoes, setOpcoes] = useState([]);
  const [novo, setNovo] = useState(null);
  const [erro, setErro] = useState(null);
  const [salvando, setSalvando] = useState(false);
  const oppId = alvo?.oportunidade_id || null;
  const contaId = alvo?.conta_id || null;

  useEffect(() => {
    if (!oppId && !contaId) { setOpcoes([]); return; }
    let vivo = true;
    // Dentro de uma promise: erro de rede OU de chamada (cliente sem `get`
    // num teste, por exemplo) vira lista vazia, nunca tela branca.
    Promise.resolve()
      .then(() => api.get('/crm/contatos/por-alvo', {
        params: oppId ? { oportunidade_id: oppId } : { conta_id: contaId },
      }))
      .then(({ data }) => { if (vivo) setOpcoes(Array.isArray(data) ? data : []); })
      .catch(() => { if (vivo) setOpcoes([]); });
    return () => { vivo = false; };
  }, [oppId, contaId]);

  async function cadastrar() {
    setSalvando(true);
    setErro(null);
    try {
      const { data } = await api.post('/crm/contatos', {
        nome: novo.nome.trim(),
        cargo: novo.cargo.trim() || null,
        telefone: novo.telefone.trim() || null,
        telefone_whatsapp: novo.whatsapp,
        conta_id: contaId,
      });
      setOpcoes((o) => [...o, { ...data, no_comite: false, principal: false, cargo: novo.cargo }]);
      onChange(data.id);
      setNovo(null);
    } catch (err) {
      setErro(mensagemDeErro(err, 'Não foi possível cadastrar o contato.'));
    } finally {
      setSalvando(false);
    }
  }

  const rotulo = (c) => [
    c.principal ? '★ ' : '',
    c.nome,
    c.cargo ? ` · ${c.cargo}` : '',
    c.papel ? ` · ${ROTULO_PAPEL[c.papel] || c.papel}` : '',
  ].join('');

  const doComite = opcoes.filter((c) => c.no_comite);
  const daEmpresa = opcoes.filter((c) => !c.no_comite);
  const id = `${idBase}-contato`;

  return (
    <div className="md:col-span-2 space-y-2">
      <Select
        id={id}
        label={`${prefixo}Contato${obrigatorio ? ' (obrigatório)' : ''}`}
        value={novo ? NOVO : (valor || '')}
        onChange={(e) => {
          if (e.target.value === NOVO) {
            setNovo({ nome: '', cargo: '', telefone: '', whatsapp: false });
          } else {
            setNovo(null);
            onChange(e.target.value);
          }
        }}
      >
        <option value="">{obrigatorio ? '— com quem vai ser? —' : '— sem contato —'}</option>
        {doComite.length > 0 && (
          <optgroup label="Nesta oportunidade">
            {doComite.map((c) => <option key={c.id} value={c.id}>{rotulo(c)}</option>)}
          </optgroup>
        )}
        {daEmpresa.length > 0 && (
          <optgroup label={oppId ? 'Outras pessoas da empresa' : 'Contatos do parceiro'}>
            {daEmpresa.map((c) => <option key={c.id} value={c.id}>{rotulo(c)}</option>)}
          </optgroup>
        )}
        {contaId && <option value={NOVO}>+ Cadastrar novo contato…</option>}
      </Select>

      {obrigatorio && !valor && !novo && opcoes.length === 0 && (
        <p className="text-xs text-hipo-warning">
          Esta empresa ainda não tem contato. Cadastre a pessoa com quem vai
          ser a conversa — é assim que a conta deixa de depender de um nome só.
        </p>
      )}

      {novo && (
        <div className="grid grid-cols-1 md:grid-cols-3 gap-2 border-l-2 border-hipo-blue pl-3">
          <Input
            id={`${id}-novo-nome`} label="Nome" value={novo.nome}
            onChange={(e) => setNovo((n) => ({ ...n, nome: e.target.value }))}
          />
          <Input
            id={`${id}-novo-cargo`} label="Cargo" value={novo.cargo}
            onChange={(e) => setNovo((n) => ({ ...n, cargo: e.target.value }))}
          />
          <div>
            <Input
              id={`${id}-novo-telefone`} label="Telefone" value={novo.telefone}
              onChange={(e) => setNovo((n) => ({ ...n, telefone: e.target.value }))}
            />
            <label className="inline-flex items-center gap-1.5 text-xs text-hipo-slate mt-1">
              <input
                type="checkbox" checked={novo.whatsapp}
                onChange={(e) => setNovo((n) => ({ ...n, whatsapp: e.target.checked }))}
              />
              É WhatsApp
            </label>
          </div>
          {erro && <p className="md:col-span-3 text-xs text-hipo-danger">{erro}</p>}
          <div className="md:col-span-3 flex justify-end gap-2">
            <Button size="sm" variant="ghost" onClick={() => setNovo(null)}>Voltar</Button>
            <Button size="sm" loading={salvando} disabled={!novo.nome.trim()} onClick={cadastrar}>
              Cadastrar e usar
            </Button>
          </div>
        </div>
      )}
    </div>
  );
}

/**
 * O que se escreve na tarefa tem tamanho de campo à altura.
 *
 * O título vinha num input de 40px e o detalhe, num input de UMA linha —
 * do mesmo tamanho de um campo de CEP. Quem escreve "Ligar para o RH da
 * Metalurgica confirmando as 40 vidas do PCMSO e a data dos exames"
 * enxergava um terço do que digitou e perdia a noção do que já tinha
 * escrito. O campo comunica quanto se espera que seja escrito, e um campo
 * apertado ensina a escrever pouco.
 *
 * Título continua em uma linha só — é rótulo, e rótulo que vira parágrafo
 * quebra a lista e a linha do tempo. Mas ganhou altura e fonte maiores. O
 * detalhe virou textarea de 4 linhas, redimensionável na vertical.
 */
/*
 * A classe do textarea morava aqui, copiada. Virou o componente
 * `Textarea` em ui/Input.jsx quando o terceiro campo de texto livre
 * precisou dela — três cópias do mesmo visual divergem no primeiro
 * ajuste de paleta, e a que diverge é sempre a que o usuário está vendo.
 */

export function CamposTarefa({
  valor, onChange, usuarios, prefixo = '', idBase = 'tarefa',
  // 045: { oportunidade_id?, conta_id } — de onde vêm os contatos possíveis.
  // Sem alvo o campo não aparece (o servidor continua cobrando).
  alvo = null,
  // Diz, quando o tipo é reunião ou visita, que ela vai para a agenda. É o
  // caso da PRÓXIMA tarefa marcada ao fechar outra. Quem já explica isso do
  // seu jeito (a criação na aba) ou não agenda ao salvar (a edição) desliga.
  avisoAgenda = true,
}) {
  const set = (campo) => (e) => onChange({ ...valor, [campo]: e.target.value });

  /*
    Ids explícitos, e não os que o Input deriva do rótulo.

    O Input monta `inp-${label}` minúsculo com espaços virando hífen. Com o
    prefixo "Próxima: " isso produz `inp-próxima:-título` — legal em HTML5,
    mas os dois-pontos quebram `document.querySelector('#...')` sem escape.
    Ninguém tropeça nisso no dia a dia, e é justamente por isso que dói
    quando alguém tropeça: um seletor que falha por causa de pontuação no
    rótulo é caça ao fantasma.

    Como bônus, dois formulários abertos ao mesmo tempo (o de editar uma
    tarefa e o da próxima de outra) deixam de brigar pelo mesmo id.
  */
  const campoId = (nome) => `${idBase}-${nome}`;

  return (
    <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
      {/*
        Título em primeiro e ocupando a linha toda: é o que a pessoa veio
        escrever. Tipo, prazo e responsável são classificação, e vêm depois.
      */}
      <div className="md:col-span-2">
        <Input
          id={campoId('titulo')}
          label={`${prefixo}Título`}
          placeholder="ex.: Ligar para o RH confirmando as 40 vidas do PCMSO"
          value={valor.titulo}
          onChange={set('titulo')}
          inputClassName="text-base"
        />
      </div>

      <Select
        id={campoId('tipo')}
        label={`${prefixo}Tipo`}
        value={valor.tipo}
        onChange={set('tipo')}
      >
        {TIPOS.map((t) => <option key={t.valor} value={t.valor}>{t.rotulo}</option>)}
      </Select>

      <Input
        id={campoId('prazo')}
        label={`${prefixo}Prazo`}
        type="datetime-local"
        value={valor.prazo}
        onChange={set('prazo')}
      />

      <Select
        id={campoId('responsavel')}
        label={`${prefixo}Responsável`}
        value={valor.responsavel_id}
        onChange={set('responsavel_id')}
      >
        <option value="">— selecione —</option>
        {usuarios.map((u) => <option key={u.id} value={u.id}>{u.nome}</option>)}
      </Select>

      {alvo && (
        <CampoContato
          alvo={alvo}
          valor={valor.contato_id}
          onChange={(contatoId) => onChange({ ...valor, contato_id: contatoId })}
          obrigatorio={exigeContato(valor.tipo)}
          idBase={idBase}
          prefixo={prefixo}
        />
      )}

      {avisoAgenda && TIPOS_AGENDAVEIS.includes(valor.tipo) && (
        <p className="md:col-span-2 text-xs text-hipo-slate">
          Reunião e visita entram na agenda ao salvar — o horário precisa estar
          livre para o responsável, em dia útil.
        </p>
      )}

      <div className="md:col-span-2">
        <Textarea
          id={campoId('detalhe')}
          label={`${prefixo}Detalhe (opcional)`}
          rows={4}
          value={valor.descricao}
          onChange={set('descricao')}
          placeholder="Contexto, combinados, o que precisa levar"
        />
      </div>
    </div>
  );
}

// ── Painéis de ação ──────────────────────────────────────────────────

/*
  A saída para quem NÃO tem próximo passo depende do alvo, e o texto tem que
  dizer a verdade sobre a tela em que a pessoa está.

  A oportunidade manda finalizar, e existe um botão Finalizar ali. Parceria
  não se finaliza — mandar "finalize a parceria" seria pedir uma ação que a
  tela não oferece, que é pior do que não explicar. As saídas reais do
  parceiro são cancelar a tarefa ou tirá-lo da carteira, e as duas existem
  na tela.

  `tarefa.alvo` vem pronto do servidor. Inferir de campo nulo aqui seria a
  segunda fonte de verdade que o backend já evitou ao mandar o campo.
  Espelha `_SEM_PROXIMA` de api/services/tarefa.py.
*/
const SAIDA_SEM_PROXIMA = {
  oportunidade:
    'Toda tarefa concluída exige a próxima. Se não há próximo passo, '
    + 'finalize a oportunidade.',
  parceiro:
    'Toda tarefa concluída exige a próxima. Se não há próximo passo, '
    + 'cancele a tarefa em vez de concluir, ou tire o parceiro da carteira.',
};

/**
 * Concluir, cancelar e editar — os três painéis, num componente só.
 *
 * `exigeProxima` é uma FUNÇÃO `(tarefa) => bool`, e não um booleano.
 *
 * Virou função quando a regra passou a depender de duas coisas que moram em
 * lugares diferentes: o STATUS DA OPORTUNIDADE, que só a tela tem com
 * frescor (a aba acabou de recebê-lo, a tela de gestão o traz no cartão), e
 * QUANTAS OUTRAS TAREFAS DO ALVO ESTÃO ABERTAS, que vem em cada tarefa. Um
 * booleano calculado uma vez para a lista inteira obrigaria cada chamador a
 * refazer metade da regra na hora de aplicá-la — e regra pela metade em dois
 * lugares foi exatamente o que quebrou a conclusão de tarefa de parceiro.
 *
 * O backend recusa com 422 de qualquer forma; aqui a tela só evita levar o
 * usuário até o botão achando que vai passar.
 */
export function PainelAcoesTarefa({
  tarefa, painel, setPainel, usuarios, exigeProxima, ocupado,
  onConcluir, onCancelar, onEditar,
  // Opcional: sem o handler, o botão não aparece. É o que permite à aba
  // dentro da oportunidade oferecer a agenda e à tela de gestão fazer o
  // mesmo, sem nenhuma das duas precisar saber da outra.
  onAgendar,
}) {
  const exigeProximaAqui = exigeProxima(tarefa);
  const [resultado, setResultado] = useState('');
  const [motivo, setMotivo] = useState('');
  const [proxima, setProxima] = useState(
    () => tarefaVazia(tarefa.responsavel_id, tarefa.contato_id),
  );
  const alvo = alvoDaTarefa(tarefa);
  const [edicao, setEdicao] = useState(() => formDaTarefa(tarefa));

  if (!painel) {
    return (
      <div data-tour="tar-acoes" className="flex flex-wrap items-center gap-2">
        <Button
          size="sm" icon={Check}
          aria-label={`Concluir ${tarefa.titulo}`}
          onClick={() => {
            setResultado('');
            setProxima(tarefaVazia(tarefa.responsavel_id, tarefa.contato_id));
            setPainel('concluir');
          }}
        >
          Concluir
        </Button>
        <Button
          size="sm" variant="ghost" icon={Pencil}
          aria-label={`Editar ${tarefa.titulo}`}
          onClick={() => { setEdicao(formDaTarefa(tarefa)); setPainel('editar'); }}
        >
          Editar
        </Button>
        <Button
          size="sm" variant="ghost" icon={X}
          aria-label={`Cancelar ${tarefa.titulo}`}
          onClick={() => { setMotivo(''); setPainel('cancelar'); }}
        >
          Cancelar
        </Button>

        {/*
          "Colocar na agenda" REAPROVEITA esta tarefa em vez de criar uma
          reunião nova. É o caminho de quem agendou o próximo passo aqui e
          só depois percebeu que aquilo tem hora marcada com o cliente —
          criar uma segunda tarefa diria a mesma coisa duas vezes na linha
          do tempo e contaria duas reuniões na produção do mês.

          Nunca abre modal: esta barra vive dentro da aba da oportunidade,
          que já está dentro de um modal. O horário e o dono já estão na
          tarefa; o que falta (tipo, convidados) se ajusta depois, pela
          agenda.
        */}
        {onAgendar && podeEntrarNaAgenda(tarefa) && (
          <Button
            size="sm" variant="ghost" icon={CalendarPlus}
            loading={ocupado}
            aria-label={`Colocar ${tarefa.titulo} na agenda`}
            onClick={() => onAgendar(tarefa)}
          >
            Colocar na agenda
          </Button>
        )}

        {tarefa.reuniao_id && (
          <span className="inline-flex items-center gap-1 text-xs text-hipo-success">
            <CalendarCheck size={13} aria-hidden="true" />
            na agenda
          </span>
        )}
      </div>
    );
  }

  if (painel === 'concluir') {
    return (
      <div className="space-y-3 border-l-2 border-hipo-border pl-3">
        {/*
          Textarea, não input de uma linha: este é o RELATO do que
          aconteceu — vai inteiro para a linha do tempo da negociação e é
          o que alguém vai ler seis meses depois para entender o negócio.
          Num campo de 40px o texto rolava para a direita e sumia, e quem
          escrevia perdia de vista o começo da própria frase.

          Id explícito por causa dos parênteses do rótulo (ver a nota no
          componente Textarea).
        */}
        <Textarea
          id={`resultado-${tarefa.id}`}
          label="O que aconteceu (opcional)"
          rows={3}
          placeholder="Atendeu, pediu proposta para 15 vidas"
          value={resultado}
          onChange={(e) => setResultado(e.target.value)}
        />

        {exigeProximaAqui ? (
          <div className="space-y-2">
            <div className="flex items-center gap-2 text-xs text-hipo-slate">
              <AlertTriangle size={13} className="text-hipo-warning" />
              <span>{SAIDA_SEM_PROXIMA[tarefa.alvo] || SAIDA_SEM_PROXIMA.oportunidade}</span>
            </div>
            <CamposTarefa
              valor={proxima}
              onChange={setProxima}
              usuarios={usuarios}
              prefixo="Próxima: "
              idBase={`proxima-${tarefa.id}`}
              alvo={alvo}
            />
          </div>
        ) : (
          /*
            DIZER QUAL DAS DUAS DISPENSAS SE APLICOU.

            Sem isso, o formulário às vezes pede a próxima e às vezes não, e
            a diferença fica invisível — o usuário conclui que é bug e para
            de confiar na regra. Cada frase nomeia o motivo, e o de sobrar
            outra tarefa aberta vem primeiro porque é o novo.
          */
          <p className="text-xs text-hipo-slate">
            {tarefa.outras_abertas > 0
              ? `Esta ${tarefa.alvo === 'parceiro' ? 'parceria' : 'oportunidade'} `
                + `já tem ${tarefa.outras_abertas === 1
                  ? 'outra tarefa em aberto'
                  : `outras ${tarefa.outras_abertas} tarefas em aberto`}`
                + ' — não é preciso agendar a próxima.'
              : 'Oportunidade finalizada — não é preciso agendar a próxima.'}
          </p>
        )}


        <div className="flex justify-end gap-2">
          <Button size="sm" variant="ghost" onClick={() => setPainel(null)}>
            Voltar
          </Button>
          <Button
            size="sm"
            loading={ocupado}
            disabled={exigeProximaAqui && formIncompleto(proxima)}
            onClick={() => onConcluir(tarefa, resultado, exigeProximaAqui ? proxima : null)
              .then((ok) => ok && setPainel(null))}
          >
            Concluir tarefa
          </Button>
        </div>
      </div>
    );
  }

  if (painel === 'cancelar') {
    return (
      <div className="space-y-3 border-l-2 border-hipo-border pl-3">
        {/*
          Pelo mesmo motivo do resultado, e com uma linha a menos: motivo
          de cancelamento costuma ser curto ("agendei duplicado"), mas
          quando não é — "o contato saiu da empresa e o novo RH pediu para
          retomar em janeiro" — não pode sumir para a direita.
        */}
        <Textarea
          id={`motivo-${tarefa.id}`}
          label="Motivo do cancelamento (opcional)"
          rows={2}
          placeholder="Agendei duplicado"
          value={motivo}
          onChange={(e) => setMotivo(e.target.value)}
        />
        <div className="flex justify-end gap-2">
          <Button size="sm" variant="ghost" onClick={() => setPainel(null)}>
            Voltar
          </Button>
          <Button
            size="sm" variant="secondary" loading={ocupado}
            onClick={() => onCancelar(tarefa, motivo).then((ok) => ok && setPainel(null))}
          >
            Cancelar tarefa
          </Button>
        </div>
      </div>
    );
  }

  return (
    <div className="space-y-3 border-l-2 border-hipo-border pl-3">
      <CamposTarefa
        valor={edicao}
        onChange={setEdicao}
        usuarios={usuarios}
        idBase={`edicao-${tarefa.id}`}
        avisoAgenda={false}
        alvo={alvo}
      />
      <div className="flex justify-end gap-2">
        <Button size="sm" variant="ghost" onClick={() => setPainel(null)}>
          Voltar
        </Button>
        <Button
          size="sm" loading={ocupado} disabled={formIncompleto(edicao)}
          onClick={() => onEditar(tarefa, edicao).then((ok) => ok && setPainel(null))}
        >
          Salvar tarefa
        </Button>
      </div>
    </div>
  );
}
