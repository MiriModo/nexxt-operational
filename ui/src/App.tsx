import { useEffect, useState } from "react";
import { Navigate, Route, Routes, useLocation } from "react-router-dom";
import { getSursa, onSursa } from "./api/client";
import { Protected, useEu } from "./auth";
import { Header } from "./components/Header";
import Case from "./pages/Case";
import Decision from "./pages/Decision";
import Desk from "./pages/Desk";
import Home from "./pages/Home";
import Overview from "./pages/Overview";
import Queue from "./pages/Queue";
import Reports from "./pages/Reports";
import RulesEngine from "./pages/RulesEngine";
import SignIn from "./pages/SignIn";

export default function App() {
  const { eu } = useEu();
  const loc = useLocation();
  const [source, setSource] = useState(getSursa());
  useEffect(() => onSursa(setSource), []);
  const landing = !eu && loc.pathname === "/";

  return (
    <>
      <a href="#content" className="skip">
        Skip to content
      </a>
      <Header offline={source === "static"} />
      <main id="content" className={`container ${landing ? "landing" : ""}`}>
        <Routes>
          <Route path="/" element={<Home />} />
          <Route path="/signin" element={<SignIn />} />
          <Route path="/desk" element={<Protected role="consilier"><Desk /></Protected>} />
          <Route path="/overview" element={<Protected role="admin"><Overview /></Protected>} />
          <Route path="/queue" element={<Protected><Queue /></Protected>} />
          <Route path="/queue/:id" element={<Protected><Case /></Protected>} />
          <Route path="/queue/:id/decide" element={<Protected><Decision /></Protected>} />
          <Route path="/reports" element={<Protected role="admin"><Reports /></Protected>} />
          <Route path="/rules" element={<Protected role="admin"><RulesEngine /></Protected>} />
          <Route path="/biroul-meu" element={<Navigate to="/desk" replace />} />
          <Route path="/acasa" element={<Navigate to="/overview" replace />} />
          <Route path="/cazuri" element={<Navigate to="/queue" replace />} />
          <Route path="/cazuri/:id" element={<CaseRedirect />} />
          <Route path="/rezultate" element={<Navigate to="/reports" replace />} />
          <Route path="/dashboard" element={<Navigate to="/reports" replace />} />
          <Route path="/motor" element={<Navigate to="/rules" replace />} />
          <Route path="/admin" element={<Navigate to="/rules" replace />} />
        </Routes>
      </main>
    </>
  );
}

function CaseRedirect() {
  const loc = useLocation();
  return <Navigate to={loc.pathname.replace(/^\/cazuri/, "/queue").replace(/\/decizie$/, "/decide")} replace />;
}
