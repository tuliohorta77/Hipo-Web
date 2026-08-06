// web/src/App.jsx
//
// Sprint 1: entra o CRM. /crm/contas é a primeira tela operacional do
// produto novo — todo cargo válido tem o módulo 'crm', então é para onde
// primeiraRotaAcessivel() manda qualquer usuário logado.
import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom';
import Layout from './components/Layout';
import ProtectedRoute from './components/ProtectedRoute';
import Login from './pages/Login';
import Perfil from './pages/Perfil';
import Contas from './pages/crm/Contas';
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
          <Route path="crm/contas" element={<Contas />} />
          <Route path="perfil" element={<Perfil />} />
        </Route>

        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    </BrowserRouter>
  );
}
