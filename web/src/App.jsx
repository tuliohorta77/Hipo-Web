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
import Oportunidades from './pages/crm/Oportunidades';
import Parceiros from './pages/crm/Parceiros';
import Tarefas from './pages/crm/Tarefas';
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
          <Route path="crm/oportunidades" element={<Oportunidades />} />
          <Route path="crm/tarefas" element={<Tarefas />} />
          <Route path="crm/contas" element={<Contas />} />
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
