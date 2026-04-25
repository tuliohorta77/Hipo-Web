// web/src/App.jsx
import { BrowserRouter, Routes, Route, Navigate } from "react-router-dom";
import Layout from "./components/Layout";
import ProtectedRoute from "./components/ProtectedRoute";
import Login from "./pages/Login";
import POsDashboard from "./pages/POs";
import PEXDashboard from "./pages/PEX";
import BDAtivadosDashboard from "./pages/BDAtivados";

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
          <Route index element={<Navigate to="/pex" replace />} />
          <Route path="pex" element={<PEXDashboard />} />
          <Route path="pos" element={<POsDashboard />} />
          <Route path="bd-ativados" element={<BDAtivadosDashboard />} />
        </Route>

        {/* Fallback */}
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    </BrowserRouter>
  );
}
