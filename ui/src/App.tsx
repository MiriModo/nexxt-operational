import { useEffect, useState } from "react";
import { NavLink, Route, Routes } from "react-router-dom";
import { getContext, getSursa, onSursa, type Context } from "./api/client";
import Acasa from "./pages/Acasa";
import Dashboard from "./pages/Dashboard";
import Coada from "./pages/Coada";
import CazPage from "./pages/Caz";
import DeciziePage from "./pages/Decizie";
import Admin from "./pages/Admin";

export default function App() {
  const [ctx, setCtx] = useState<Context | null>(null);
  const [sursa, setSursa] = useState(getSursa());
  useEffect(() => {
    getContext().then(setCtx).catch(() => setCtx(null));
    return onSursa(setSursa);
  }, []);
  return (
    <>
      <a href="#continut" className="skip">
        Sari la conținut
      </a>
      <header className="top">
        <NavLink to="/" className="brand" aria-label="retailagent, pagina de start">
          retailagent<span className="dot" aria-hidden="true" />
        </NavLink>
        <nav aria-label="Principal">
          <NavLink to="/" end>
            Acasă
          </NavLink>
          <NavLink to="/cazuri">Coadă</NavLink>
          <NavLink to="/dashboard">Dashboard</NavLink>
          <NavLink to="/admin">Admin</NavLink>
        </nav>
        <span className="ctx">
          {ctx ? `${ctx.clienti} clienți în portofoliu` : ""}
          {ctx && sursa === "static" ? ", date statice (API oprit)" : ""}
          {ctx && sursa === "api" ? ", API live" : ""}
          {ctx?.model_churn ? `, model ${ctx.model_churn.nume}` : ""}
        </span>
      </header>
      <main id="continut">
        <Routes>
          <Route path="/" element={<Acasa />} />
          <Route path="/dashboard" element={<Dashboard />} />
          <Route path="/cazuri" element={<Coada />} />
          <Route path="/cazuri/:id" element={<CazPage />} />
          <Route path="/cazuri/:id/decizie" element={<DeciziePage />} />
          <Route path="/admin" element={<Admin />} />
        </Routes>
      </main>
    </>
  );
}
