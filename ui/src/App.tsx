import { useEffect, useState } from "react";
import { Navigate, NavLink, Route, Routes, useNavigate } from "react-router-dom";
import { getSursa, onSursa } from "./api/client";
import { Protejat, useEu } from "./auth";
import Acasa from "./pages/Acasa";
import Birou from "./pages/Birou";
import CazPage from "./pages/Caz";
import Coada from "./pages/Coada";
import Dashboard from "./pages/Dashboard";
import DeciziePage from "./pages/Decizie";
import Home from "./pages/Home";
import Motor from "./pages/Motor";

/** Antetul arată doar ce are nevoie cine e logat: consilierul își vede biroul și cazurile, administratorul vede tot. */
export default function App() {
  const { eu, logout } = useEu();
  const nav = useNavigate();
  const [sursa, setSursa] = useState(getSursa());
  useEffect(() => onSursa(setSursa), []);
  const iesi = async () => {
    await logout();
    nav("/");
  };
  return (
    <>
      <a href="#continut" className="skip">
        Sari la conținut
      </a>
      <header className="top">
        <NavLink to={eu ? (eu.rol === "admin" ? "/acasa" : "/biroul-meu") : "/"} className="brand" aria-label="retailagent, pagina de start">
          retailagent<span className="dot" aria-hidden="true" />
        </NavLink>
        {eu?.rol === "consilier" && (
          <nav aria-label="Principal">
            <NavLink to="/biroul-meu">Biroul meu</NavLink>
            <NavLink to="/cazuri">Cazurile mele</NavLink>
          </nav>
        )}
        {eu?.rol === "admin" && (
          <nav aria-label="Principal">
            <NavLink to="/acasa">Acasă</NavLink>
            <NavLink to="/cazuri">Cazuri</NavLink>
            <NavLink to="/rezultate">Rezultate</NavLink>
            <NavLink to="/motor">Motor de reguli</NavLink>
          </nav>
        )}
        {sursa === "static" && <span className="ctx">date statice, serverul nu răspunde</span>}
        {eu ? (
          <span className="cine">
            {eu.nume}
            <button type="button" className="btn ghost sm" onClick={iesi}>
              Ieși
            </button>
          </span>
        ) : (
          <NavLink to="/" className="admin-link">
            Intră în cont
          </NavLink>
        )}
      </header>
      <main id="continut">
        <Routes>
          <Route path="/" element={<Home />} />
          <Route path="/biroul-meu" element={<Protejat rol="consilier"><Birou /></Protejat>} />
          <Route path="/acasa" element={<Protejat rol="admin"><Acasa /></Protejat>} />
          <Route path="/cazuri" element={<Protejat><Coada /></Protejat>} />
          <Route path="/cazuri/:id" element={<Protejat><CazPage /></Protejat>} />
          <Route path="/cazuri/:id/decizie" element={<Protejat><DeciziePage /></Protejat>} />
          <Route path="/rezultate" element={<Protejat rol="admin"><Dashboard /></Protejat>} />
          <Route path="/motor" element={<Protejat rol="admin"><Motor /></Protejat>} />
          <Route path="/dashboard" element={<Navigate to="/rezultate" replace />} />
          <Route path="/admin" element={<Navigate to="/motor" replace />} />
        </Routes>
      </main>
    </>
  );
}
