import { BrowserRouter, Routes, Route, Navigate } from "react-router-dom";
import Layout from "./components/Layout";
import POsDashboard from "./pages/POs";
import PEXDashboard from "./pages/PEX";
import BDAtivadosDashboard from "./pages/BDAtivados";

export default function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route path="/" element={<Layout />}>
          <Route index element={<Navigate to="/pex" replace />} />
          <Route path="pex" element={<PEXDashboard />} />
          <Route path="pos" element={<POsDashboard />} />
          <Route path="bd-ativados" element={<BDAtivadosDashboard />} />
        </Route>
      </Routes>
    </BrowserRouter>
  );
}
