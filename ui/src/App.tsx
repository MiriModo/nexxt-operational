import { useEffect, useState } from "react";
import { NavLink, Route, Routes } from "react-router-dom";
import { getSursa, onSursa } from "./api/client";
import Acasa from "./pages/Acasa";
import Dashboard from "./pages/Dashboard";
import Coada from "./pages/Coada";
import CazPage from "./pages/Caz";
import DeciziePage from "./pages/Decizie";
import Admin from "./pages/Admin";

/** Antetul spune doar ce are nevoie consilierul: unde e și dacă lucrează pe date vii. Administrarea e un link discret,
 *  pe o pagină separată, cu parolă. */
export default function App() {
  const [sursa, setSursa] = useState(getSursa());
  useEffect(() => onSursa(setSursa), []);
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
          <NavLink to="/cazuri">Cazuri</NavLink>
          <NavLink to="/rezultate">Rezultate</NavLink>
        </nav>
        {sursa === "static" && <span className="ctx">date statice, serverul nu răspunde</span>}
        <NavLink to="/admin" className="admin-link">
          Administrare
        </NavLink>
      </header>
      <main id="continut">
        <Routes>
          <Route path="/" element={<Acasa />} />
          <Route path="/rezultate" element={<Dashboard />} />
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
