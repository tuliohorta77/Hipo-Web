// web/src/components/crm/AbaSocios.jsx
//
// Quadro societário da conta — aba própria.
//
// POR QUE SAIU DE "DADOS PÚBLICOS"
//
// As duas coisas vinham da mesma consulta, mas não se usam juntas. "Dados
// públicos" é onde se consulta a Receita e se decide o que fazer com o que
// ela trouxe; aqui é onde se olha QUEM está por trás da empresa e se
// procura essa pessoa no resto da carteira. Misturadas, a lista de sócios
// ficava no fim de uma página que a pessoa já tinha parado de ler.
//
// Decisões desta aba:
//
//   * ABRIR NÃO CONSULTA FONTE EXTERNA. Lê `conta_socios`, que é local. A
//     busca por outras empresas do sócio é um clique explícito, sócio a
//     sócio — em fonte paga, abrir aba não pode custar crédito.
//
//   * "NENHUMA OUTRA EMPRESA" PRECISA DIZER ONDE PROCUROU. Quando a busca
//     externa está desligada, a resposta traz o aviso: sem isso, "nenhuma
//     outra empresa" seria lido como "não existe" em vez de "não procurei
//     fora daqui".
//
//   * SÓCIO QUE SAIU CONTINUA LISTADO, com a data de captura. A informação
//     de que alguém esteve na empresa não é apagada por uma consulta nova.

import { useCallback, useEffect, useState } from 'react';
import { Users2, Building2, Search } from 'lucide-react';

import api from '../../api';
import Button from '../ui/Button';
import Badge from '../ui/Badge';
import Empty from '../ui/Empty';
import AlertMessage from '../ui/AlertMessage';
import Table, { Th, Tr, Td } from '../ui/Table';

function mensagemDeErro(err, padrao) {
  const d = err?.response?.data?.detail;
  if (typeof d === 'string') return d;
  if (Array.isArray(d) && d[0]?.msg) return d[0].msg;
  if (d?.mensagem) return d.mensagem;
  return padrao;
}

function formatarData(iso) {
  if (!iso) return '—';
  const d = new Date(iso);
  return Number.isNaN(d.getTime()) ? '—' : d.toLocaleDateString('pt-BR');
}

function LinhaSocio({ socio, contaId }) {
  const [empresas, setEmpresas] = useState(null);
  const [avisos, setAvisos] = useState([]);
  const [buscando, setBuscando] = useState(false);
  const [erro, setErro] = useState(null);

  async function buscarEmpresas() {
    setBuscando(true);
    setErro(null);
    try {
      const { data } = await api.get('/crm/enriquecimento/socios/empresas', {
        params: {
          nome: socio.nome,
          documento: socio.documento_mascarado || undefined,
          excluir_conta_id: contaId,
        },
      });
      setEmpresas(data.empresas);
      setAvisos(data.avisos || []);
    } catch (err) {
      setErro(mensagemDeErro(err, 'Não foi possível buscar as empresas do sócio.'));
    } finally {
      setBuscando(false);
    }
  }

  return (
    <>
      <Tr>
        <Td>
          <div className="font-medium text-hipo-ink">{socio.nome}</div>
          {socio.documento_mascarado && (
            <div className="text-xs text-hipo-muted font-mono">
              {socio.documento_mascarado}
            </div>
          )}
        </Td>
        <Td>{socio.qualificacao || <span className="text-hipo-muted">—</span>}</Td>
        <Td>{socio.faixa_etaria || <span className="text-hipo-muted">—</span>}</Td>
        <Td>{formatarData(socio.entrada_em)}</Td>
        <Td align="right">
          <Button
            size="sm"
            variant="ghost"
            icon={Search}
            loading={buscando}
            onClick={buscarEmpresas}
          >
            Outras empresas
          </Button>
        </Td>
      </Tr>

      {(empresas !== null || erro) && (
        <tr>
          <td colSpan={5} className="px-4 pb-4 bg-hipo-bg/40">
            {erro && <AlertMessage tipo="erro">{erro}</AlertMessage>}
            {empresas !== null && empresas.length === 0 && (
              <p className="text-sm text-hipo-slate py-2">
                Nenhuma outra empresa deste sócio no HIPO.
              </p>
            )}
            {empresas !== null && empresas.length > 0 && (
              <ul className="py-2 space-y-1.5">
                {empresas.map((e, i) => (
                  <li
                    key={`${e.conta_id || e.razao_social}-${i}`}
                    className="flex flex-wrap items-center gap-2 text-sm"
                  >
                    <Building2 size={14} className="text-hipo-muted" />
                    <span className="text-hipo-ink">{e.razao_social}</span>
                    {e.cnpj_formatado && (
                      <span className="font-mono text-xs text-hipo-muted">
                        {e.cnpj_formatado}
                      </span>
                    )}
                    {e.qualificacao && (
                      <span className="text-xs text-hipo-slate">{e.qualificacao}</span>
                    )}
                    <Badge tone={e.confianca === 'alta' ? 'success' : 'warning'}>
                      {e.confianca === 'alta'
                        ? 'nome e documento batem'
                        : 'só o nome bate'}
                    </Badge>
                    {e.externa && <Badge tone="info">fora do HIPO</Badge>}
                  </li>
                ))}
              </ul>
            )}
            {avisos.map((a) => (
              <p key={a} className="text-xs text-hipo-muted">{a}</p>
            ))}
          </td>
        </tr>
      )}
    </>
  );
}

export default function AbaSocios({ conta }) {
  const [socios, setSocios] = useState(null);
  const [erro, setErro] = useState(null);

  const carregar = useCallback(async () => {
    try {
      const { data } = await api.get(
        `/crm/enriquecimento/contas/${conta.id}/socios`
      );
      setSocios(data);
    } catch (err) {
      setErro(mensagemDeErro(err, 'Não foi possível carregar o quadro societário.'));
      setSocios([]);
    }
  }, [conta.id]);

  useEffect(() => { carregar(); }, [carregar]);

  return (
    <div className="space-y-4">
      {erro && <AlertMessage tipo="erro">{erro}</AlertMessage>}

      {socios === null ? (
        <p className="py-10 text-center text-sm text-hipo-slate">Carregando…</p>
      ) : socios.length === 0 ? (
        // A mensagem muda conforme JÁ houve consulta ou não. Depois de
        // consultar, "sem sócios" quase sempre significa empresário
        // individual ou MEI — esses não têm quadro societário na Receita, e
        // dizer só "sem sócios registrados" faria parecer defeito do
        // sistema num dado que simplesmente não existe.
        <Empty
          title={
            conta.enriquecida_em
              ? 'A Receita não tem quadro societário para este CNPJ'
              : 'Sem sócios registrados'
          }
          description={
            conta.enriquecida_em
              ? 'É o caso de empresário individual e MEI: a empresa é a própria pessoa, então não há sociedade a publicar. Para os demais tipos, o quadro vem na consulta.'
              : 'O quadro societário vem junto com a consulta por CNPJ, na aba Dados públicos.'
          }
          icon={Users2}
        />
      ) : (
        <>
          <p className="text-sm text-hipo-slate">
            {socios.length === 1
              ? '1 sócio registrado.'
              : `${socios.length} sócios registrados.`}{' '}
            &quot;Outras empresas&quot; procura a mesma pessoa no resto da
            carteira — é assim que se descobre que o cliente novo é sócio de
            um que você já atende.
          </p>
          <div className="border border-hipo-border rounded-lg overflow-hidden">
            <Table>
              <thead>
                <tr>
                  <Th>Sócio</Th>
                  <Th>Qualificação</Th>
                  <Th>Faixa etária</Th>
                  <Th>Entrada</Th>
                  <Th align="right">Ações</Th>
                </tr>
              </thead>
              <tbody>
                {socios.map((s) => (
                  <LinhaSocio key={s.id} socio={s} contaId={conta.id} />
                ))}
              </tbody>
            </Table>
          </div>
        </>
      )}
    </div>
  );
}
