// web/src/App.jsx
//
// Sprint 0 (limpeza do legado): as telas de PEX, POs, BD Ativados,
// Contadores, Clientes, Vendas, Agendamento, Bastões e Metas saíram junto
// com as tabelas que consumiam. Restam Login e Perfil.
//
// A Sprint 1 adiciona /crm/contas; a Sprint 4, /crm/oportunidades.
import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom';
import Layout from './components/Layout';
import ProtectedRoute from './components/ProtectedRoute';
import Login from './pages/Login';
import Perfil from './pages/Perfil';
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
          <Route path="perfil" element={<Perfil />} />
        </Route>

        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    </BrowserRouter>
  );
}
