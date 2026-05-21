// web/src/App.jsx
import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom';
import Layout from './components/Layout';
import ProtectedRoute from './components/ProtectedRoute';
import Login from './pages/Login';
import POsDashboard from './pages/POs';
import PEXDashboard from './pages/PEX';
import BDAtivadosDashboard from './pages/BDAtivados';
import Metas from './pages/Metas';
import Contadores from './pages/Contadores';
import Clientes from './pages/Clientes';
import Bastoes from './pages/Bastoes';
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
          <Route path="pex"          element={<PEXDashboard />} />
          <Route path="pos"          element={<POsDashboard />} />
          <Route path="bd-ativados"  element={<BDAtivadosDashboard />} />
          <Route path="contadores"   element={<Contadores />} />
          <Route path="clientes"     element={<Clientes />} />
          <Route path="bastoes"      element={<Bastoes />} />
          <Route path="metas"        element={<Metas />} />
          <Route path="perfil"       element={<Perfil />} />

          {/* Compat: /carteira redireciona pra /contadores */}
          <Route path="carteira" element={<Navigate to="/contadores" replace />} />
        </Route>

        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    </BrowserRouter>
  );
}
