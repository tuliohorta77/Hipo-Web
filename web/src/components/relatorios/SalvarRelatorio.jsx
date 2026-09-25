// web/src/components/relatorios/SalvarRelatorio.jsx
//
// Nome, descrição e compartilhamento de um relatório salvo.
//
// O aviso sobre o período não é enfeite: "Este mês" salvo hoje mostra o mês
// corrente em qualquer dia em que for aberto, e datas fixas nunca mudam.
// Quem salva precisa saber qual das duas coisas está guardando.

import { useEffect, useState } from 'react';
import Modal from '../ui/Modal';
import Button from '../ui/Button';
import Input, { Textarea } from '../ui/Input';
import AlertMessage from '../ui/AlertMessage';
import { rotuloPreset, dataBr } from './periodo';

export default function SalvarRelatorio({
  aberto, titulo, inicial, periodo, salvando, erro, onSalvar, onFechar,
}) {
  const [nome, setNome] = useState('');
  const [descricao, setDescricao] = useState('');
  const [compartilhado, setCompartilhado] = useState(false);
  const [erroLocal, setErroLocal] = useState(null);

  useEffect(() => {
    if (!aberto) return;
    setNome(inicial?.nome || '');
    setDescricao(inicial?.descricao || '');
    setCompartilhado(!!inicial?.compartilhado);
    setErroLocal(null);
  }, [aberto, inicial]);

  function enviar(e) {
    e.preventDefault();
    if (!nome.trim()) {
      setErroLocal('Dê um nome ao relatório.');
      return;
    }
    onSalvar({ nome: nome.trim(), descricao: descricao.trim() || null, compartilhado });
  }

  const avisoPeriodo = periodo?.tipo === 'relativo'
    ? `Período salvo como "${rotuloPreset(periodo.preset)}": as datas se atualizam sozinhas a cada abertura.`
    : periodo?.tipo === 'fixo'
      ? `Período fixo de ${dataBr(periodo.inicio)} a ${dataBr(periodo.fim)}: não muda com o tempo.`
      : null;

  return (
    <Modal aberto={aberto} onFechar={onFechar} titulo={titulo} size="md" nivel={2}>
      <form onSubmit={enviar} className="space-y-3">
        {(erroLocal || erro) && <AlertMessage tipo="erro">{erroLocal || erro}</AlertMessage>}
        <Input
          id="relatorio-nome"
          label="Nome do relatório"
          value={nome}
          maxLength={120}
          autoFocus
          onChange={(e) => setNome(e.target.value)}
          placeholder="Ex.: Funil do mês por EV"
        />
        <Textarea
          id="relatorio-descricao"
          label="Descrição (opcional)"
          value={descricao}
          maxLength={500}
          rows={2}
          onChange={(e) => setDescricao(e.target.value)}
        />
        <label className="flex items-start gap-2.5 text-sm cursor-pointer">
          <input
            type="checkbox"
            checked={compartilhado}
            onChange={(e) => setCompartilhado(e.target.checked)}
            className="mt-0.5 accent-hipo-blue"
          />
          <span>
            <span className="block text-hipo-ink font-medium">Compartilhar com a equipe</span>
            <span className="block text-xs text-hipo-slate">
              Os colegas veem e podem duplicar a montagem; só você edita. Cada um vê os dados
              que já enxerga no HIPO.
            </span>
          </span>
        </label>
        {avisoPeriodo && <p className="text-xs text-hipo-slate bg-hipo-bg rounded-lg px-3 py-2">{avisoPeriodo}</p>}
        <div className="flex justify-end gap-2 pt-1">
          <Button type="button" variant="secondary" onClick={onFechar}>Cancelar</Button>
          <Button type="submit" loading={salvando}>Salvar</Button>
        </div>
      </form>
    </Modal>
  );
}
