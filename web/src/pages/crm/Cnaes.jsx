// web/src/pages/crm/Cnaes.jsx
//
// Tela do de-para CNAE -> vertical.
//
// POR QUE VIROU TELA COM ENDEREÇO PRÓPRIO
//
// Na primeira versão isto era um botão no topo da LISTA de contas. Quem
// estava dentro da conta — que é justamente onde o problema aparece, ao ver
// "sem vertical" — não tinha como chegar aqui sem fechar tudo e voltar. Uma
// ferramenta que só existe atrás de um caminho que ninguém percorre não
// existe.
//
// Fica em /crm/cnaes, no menu, e só para gestão: classificar um código
// decide a vertical de TODAS as contas que o usam, presentes e futuras. É a
// mesma régua do bloqueio de prospecção — mexer no cadastro de uma conta é
// operação, mexer na régua que classifica a base inteira é decisão
// comercial.
//
// Quem é operacional continua podendo classificar um CNAE ainda sem
// classificação, pela aba Dados públicos da conta em que ele apareceu: lá o
// alcance é o código daquela empresa, e o trabalho não para para chamar
// alguém.

import { useCallback, useEffect, useState } from 'react';

import api from '../../api';
import PageHeader from '../../components/ui/PageHeader';
import Card from '../../components/ui/Card';
import AlertMessage from '../../components/ui/AlertMessage';
import DeParaCnaes from '../../components/crm/DeParaCnaes';

function mensagemDeErro(err, padrao) {
  const d = err?.response?.data?.detail;
  if (typeof d === 'string') return d;
  if (Array.isArray(d) && d[0]?.msg) return d[0].msg;
  if (d?.mensagem) return d.mensagem;
  return padrao;
}

export default function Cnaes() {
  const [verticais, setVerticais] = useState([]);
  const [erro, setErro] = useState(null);

  const carregarVerticais = useCallback(async () => {
    try {
      const { data } = await api.get('/crm/dominio/verticais');
      setVerticais(data);
    } catch (err) {
      setErro(mensagemDeErro(err, 'Não foi possível carregar as verticais.'));
    }
  }, []);

  useEffect(() => { carregarVerticais(); }, [carregarVerticais]);

  // O POST de domínio é idempotente: criar uma vertical que já existe
  // devolve a existente em vez de 409. Por isso dá para chamar sem checar
  // antes.
  const criarVertical = useCallback(async (nome) => {
    const { data } = await api.post('/crm/dominio/verticais', { nome });
    setVerticais((vs) => (vs.some((v) => v.id === data.id) ? vs : [...vs, data]));
    return data;
  }, []);

  return (
    <div className="space-y-6">
      <PageHeader
        title="CNAEs e verticais"
        subtitle="Classificar um CNAE vale para todas as contas que o usam"
      />

      {erro && <AlertMessage tipo="erro">{erro}</AlertMessage>}

      {/* Altura fixa para a tabela rolar por dentro, como no modal: a fila
          costuma ter centenas de linhas e o cabeçalho com os números
          precisa continuar à vista enquanto se rola. */}
      <Card padding="none">
        <div className="h-[calc(100vh-14rem)] min-h-[28rem]">
          <DeParaCnaes
            verticais={verticais}
            onCriarVertical={criarVertical}
            onMudou={carregarVerticais}
          />
        </div>
      </Card>
    </div>
  );
}
