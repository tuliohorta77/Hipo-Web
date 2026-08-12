// web/src/components/crm/TransferirCarteira.jsx
//
// Passagem de carteira em massa.
//
// Esta tela existe por causa de uma conta de padaria: desligar um EC com 40
// parceiros, um clique por parceiro, são 40 cliques — e o que acontece na
// prática é que ninguém faz. A carteira passa a apontar para quem não
// trabalha mais aqui, e o filtro "parceiros do EC" vira ficção.
//
// Três movimentos cabem no mesmo formulário, e é de propósito:
//
//   * ALGUÉM SAIU        — de: quem sai      → para: quem assume
//   * DISTRIBUIR ÓRFÃOS  — de: "sem EC"      → para: quem assume
//   * DEVOLVER À FILA    — de: alguém        → para: "sem EC"
//
// O "sem EC" nas duas pontas é o que junta os três num só. Separar em telas
// diferentes obrigaria a decidir antes de entender o que se quer fazer.
//
// A confirmação mostra a CONTAGEM antes de executar. Sem isso, "transferir
// tudo do Fulano" é um botão que ninguém aperta com confiança.

import { useEffect, useMemo, useState } from 'react';
import { ArrowRight, Users } from 'lucide-react';

import api from '../../api';
import Modal from '../ui/Modal';
import Button from '../ui/Button';
import AlertMessage from '../ui/AlertMessage';
import { Select } from '../ui/Input';

// Valor do <option> que representa "sem responsável". String vazia colidiria
// com "não escolhi nada", e os dois significam coisas diferentes aqui.
export const SEM_EC = '__sem_ec__';

function mensagemDeErro(err, padrao) {
  const d = err?.response?.data?.detail;
  if (typeof d === 'string') return d;
  if (Array.isArray(d) && d[0]?.msg) return d[0].msg;
  if (d?.mensagem) return d.mensagem;
  return padrao;
}

/** Converte o valor do select no que a API espera. */
function paraId(valor) {
  return valor === SEM_EC ? null : valor;
}

export default function TransferirCarteira({
  aberto, usuarios, carteiras, onFechar, onConcluido,
}) {
  const [de, setDe] = useState(SEM_EC);
  const [para, setPara] = useState('');
  const [erro, setErro] = useState(null);
  const [salvando, setSalvando] = useState(false);

  useEffect(() => {
    if (!aberto) return;
    setDe(SEM_EC);
    setPara('');
    setErro(null);
  }, [aberto]);

  // Quantos parceiros a origem tem hoje. Vem do resumo que a página já
  // carregou — pedir de novo à API só para contar seria uma chamada a mais
  // para responder o que já está na tela.
  const quantidade = useMemo(() => {
    if (de === SEM_EC) return carteiras?.sem_ec ?? 0;
    return (carteiras?.por_ec || []).find((c) => c.usuario_id === de)?.parceiros ?? 0;
  }, [de, carteiras]);

  const mesmaPessoa = de !== SEM_EC && de === para;
  const nadaAMover = quantidade === 0;
  const semDestino = para === '';

  async function transferir() {
    setSalvando(true);
    setErro(null);
    try {
      const { data } = await api.post('/crm/parceiros/carteira/transferir', {
        de_usuario_id: paraId(de),
        para_usuario_id: paraId(para),
      });
      onConcluido(data);
    } catch (err) {
      setErro(mensagemDeErro(err, 'Não foi possível transferir a carteira.'));
    } finally {
      setSalvando(false);
    }
  }

  const nomeDe = de === SEM_EC
    ? 'sem responsável'
    : usuarios.find((u) => u.id === de)?.nome || '—';
  const nomePara = para === SEM_EC
    ? 'sem responsável'
    : usuarios.find((u) => u.id === para)?.nome || '—';

  return (
    <Modal
      aberto={aberto}
      onFechar={onFechar}
      titulo="Transferir carteira"
      subtitulo="Move todos os parceiros de uma vez"
      size="md"
      footer={
        <div className="flex justify-end gap-2">
          <Button variant="ghost" onClick={onFechar}>Cancelar</Button>
          <Button
            onClick={transferir}
            loading={salvando}
            disabled={mesmaPessoa || nadaAMover || semDestino}
          >
            Transferir {quantidade > 0 ? quantidade : ''}
          </Button>
        </div>
      }
    >
      <div className="space-y-4">
        {erro && <AlertMessage tipo="erro">{erro}</AlertMessage>}

        <div className="grid grid-cols-2 gap-4">
          <Select label="De" value={de} onChange={(e) => setDe(e.target.value)}>
            <option value={SEM_EC}>Sem responsável</option>
            {usuarios.map((u) => (
              <option key={u.id} value={u.id}>{u.nome}</option>
            ))}
          </Select>
          <Select label="Para" value={para} onChange={(e) => setPara(e.target.value)}>
            <option value="">Escolha…</option>
            <option value={SEM_EC}>Sem responsável</option>
            {usuarios.map((u) => (
              <option key={u.id} value={u.id}>{u.nome}</option>
            ))}
          </Select>
        </div>

        {/*
          A contagem é a informação principal deste modal, não um detalhe:
          é o que separa "transferir a carteira" de "apertar e torcer".
        */}
        <div
          data-testid="previa-transferencia"
          className="flex items-center gap-3 rounded-lg border border-hipo-border bg-hipo-bg px-3 py-2.5"
        >
          <span className="w-8 h-8 shrink-0 rounded-lg bg-hipo-blueSoft text-hipo-blue grid place-items-center">
            <Users size={15} />
          </span>
          <div className="min-w-0 text-sm">
            <p className="font-semibold text-hipo-ink">
              {quantidade} parceiro{quantidade === 1 ? '' : 's'}
            </p>
            <p className="flex items-center gap-1.5 text-xs text-hipo-slate truncate">
              {nomeDe}
              <ArrowRight size={12} aria-hidden="true" />
              {semDestino ? '…' : nomePara}
            </p>
          </div>
        </div>

        {mesmaPessoa && (
          <AlertMessage tipo="aviso">Origem e destino são a mesma pessoa.</AlertMessage>
        )}
        {nadaAMover && !mesmaPessoa && (
          <AlertMessage tipo="info">
            {de === SEM_EC
              ? 'Nenhum parceiro está sem responsável.'
              : `${nomeDe} não tem parceiro nenhum na carteira.`}
          </AlertMessage>
        )}

        <p className="text-xs text-hipo-slate">
          Cada parceiro transferido registra um evento próprio no histórico,
          com autor e data.
        </p>
      </div>
    </Modal>
  );
}
