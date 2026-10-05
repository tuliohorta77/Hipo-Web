// web/src/App.jsx
//
// Todo cargo válido tem o módulo 'crm', então /crm/oportunidades é para onde
// primeiraRotaAcessivel() manda qualquer usuário logado: o funil é a tela do
// dia a dia; Contas é cadastro de apoio.
import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom';
import Layout from './components/Layout';
import ProtectedRoute from './components/ProtectedRoute';
import Login from './pages/Login';
import Perfil from './pages/Perfil';
import Contas from './pages/crm/Contas';
import Cnaes from './pages/crm/Cnaes';
import Oportunidades from './pages/crm/Oportunidades';
import Parceiros from './pages/crm/Parceiros';
import Tarefas from './pages/crm/Tarefas';
import Agenda from './pages/crm/Agenda';
import ReuniaoAoVivo from './pages/crm/ReuniaoAoVivo';
import Relatorios from './pages/crm/Relatorios';
import Prospeccao from './pages/crm/Prospeccao';
import Monitor from './pages/Monitor';
import MinhaUC from './pages/uc/MinhaUC';
import TrilhaUC from './pages/uc/Trilha';
import AulaUC from './pages/uc/Aula';
import EstudioUC from './pages/uc/Estudio';
import DesempenhoCarreira from './pages/carreira/Desempenho';
import PdiCarreira from './pages/carreira/Pdi';
import { primeiraRotaAcessivel } from './api';

function RedirectPrimeiraRota() {
  return <Navigate to={primeiraRotaAcessivel()} replace />;
}

export default function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route path="/login" element={<Login />} />

        <Route
          path="/"
          element={
            <ProtectedRoute>
              <Layout />
            </ProtectedRoute>
          }
        >
          <Route index element={<RedirectPrimeiraRota />} />
          {/*
            Prospecção: fatia da base da Receita e "puxar para o HIPO". A
            rota existe para todo mundo; quem barra é a API (SDR e gestão), e
            a nav só mostra o item para esses cargos. Mesmo arranjo de CNAEs.
          */}
          <Route path="crm/prospeccao" element={<Prospeccao />} />
          <Route path="crm/oportunidades" element={<Oportunidades />} />
          <Route path="crm/tarefas" element={<Tarefas />} />
          <Route path="crm/agenda" element={<Agenda />} />
          {/*
            Reunião ao vivo: aberta numa aba ao lado do Meet, a partir do
            modal da reunião. O id é o da TAREFA, como o da transcrição do
            Meet — é a tarefa que as telas têm na mão.
          */}
          <Route path="crm/agenda/ao-vivo/:tarefaId" element={<ReuniaoAoVivo />} />
          <Route path="crm/contas" element={<Contas />} />
          {/*
            Relatórios: tabela dinâmica + relatórios salvos. ?r=<id> abre um
            relatório salvo direto — é o link que se manda para um colega
            quando o relatório está compartilhado.
          */}
          <Route path="crm/relatorios" element={<Relatorios />} />
          {/*
            De-para CNAE -> vertical. A rota existe para todo mundo; quem
            barra o remapeamento e a API, e a nav so mostra o item para
            gestao. Mesmo arranjo de Parceiros.
          */}
          <Route path="crm/cnaes" element={<Cnaes />} />
          {/*
            O Monitor fica fora de /crm no caminho porque não é uma tela de
            trabalho: é o painel de parede da operação inteira, e mora na
            raiz junto de Perfil. O módulo exigido pela API continua sendo
            'crm', que todo cargo válido tem.
          */}
          <Route path="monitor" element={<Monitor />} />
          {/*
            Universidade Corporativa. Módulo 'crm' na API, como o Monitor:
            todo cargo aprende. O estúdio é rota de todo mundo e quem barra é
            a API (requer_gestao_uc) — mesmo arranjo de Parceiros e CNAEs.
            ?usuario_id= em /uc, trilhas e aulas é o modo leitura da gestão.
          */}
          {/*
            Carreira: Universidade, PDI e Desempenho. /carreira é a
            Universidade (a mesma tela de /uc, que continua valendo para os
            links antigos, o tour e a conta UC).
          */}
          <Route path="carreira" element={<MinhaUC />} />
          <Route path="carreira/pdi" element={<PdiCarreira />} />
          <Route path="carreira/desempenho" element={<DesempenhoCarreira />} />
          <Route path="uc" element={<MinhaUC />} />
          <Route path="uc/estudio" element={<EstudioUC />} />
          <Route path="uc/trilhas/:trilhaId" element={<TrilhaUC />} />
          <Route path="uc/aulas/:aulaId" element={<AulaUC />} />
          {/*
            A rota existe para todo mundo; quem barra é o guard do módulo na
            API, e a nav não mostra o item para quem não tem 'parceiros'.
            Digitar a URL na mão leva a uma tela que responde 403 — que é o
            comportamento correto: a permissão vive no servidor, não aqui.
          */}
          <Route path="crm/parceiros" element={<Parceiros />} />
          <Route path="perfil" element={<Perfil />} />
        </Route>

        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    </BrowserRouter>
  );
}
