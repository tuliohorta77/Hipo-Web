// web/src/App.jsx
import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom';
import Layout from './components/Layout';
import ProtectedRoute from './components/ProtectedRoute';
import Login from './pages/Login';
import POsDashboard from './pages/POs';
import PEXDashboard from './pages/PEX';
import BDAtivadosDashboard from './pages/BDAtivados';
import Metas from './pages/Metas';
import Carteira from './pages/Carteira';
import Perfil from './pages/Perfil';
import { primeiraRotaAcessivel } from './api';

// Componente pequeno pro <Route index>: usa a primeira rota acessível
// pelo cargo do usuário logado. ADM/Franqueado vai pra /pex, Hunter/Farmer
// vai pra /carteira.
function RedirectPrimeiraRota() {
  return <Navigate to={primeiraRotaAcessivel()} replace />;
}

export default function App() {
  return (
    <BrowserRouter>
      <Routes>
        {/* Rota pública */}
        <Route path="/login" element={<Login />} />

        {/* Rotas protegidas */}
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
          <Route path="carteira"     element={<Carteira />} />
          <Route path="metas"        element={<Metas />} />
          <Route path="perfil"       element={<Perfil />} />
        </Route>

        {/* Fallback */}
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    </BrowserRouter>
  );
}
