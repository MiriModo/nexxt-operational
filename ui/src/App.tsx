import { useEffect, useState } from "react";
import { Navigate, NavLink, Route, Routes, useLocation, useNavigate } from "react-router-dom";
import { getSursa, onSursa } from "./api/client";
import { Protected, homeFor, useEu } from "./auth";
import { Brand } from "./components/Brand";
import Case from "./pages/Case";
import Decision from "./pages/Decision";
import Desk from "./pages/Desk";
import Home from "./pages/Home";
import Overview from "./pages/Overview";
import Queue from "./pages/Queue";
import Reports from "./pages/Reports";
import RulesEngine from "./pages/RulesEngine";

/** Fixed header (guide B3): transparent, frosted on scroll; the nav depends on who is signed in. */
export default function App() {
  const { eu, logout } = useEu();
  const nav = useNavigate();
  const loc = useLocation();
  const [source, setSource] = useState(getSursa());
  const [scrolled, setScrolled] = useState(false);
  const [open, setOpen] = useState(false);
  useEffect(() => onSursa(setSource), []);
  useEffect(() => {
    const onScroll = () => setScrolled(window.scrollY > 8);
    onScroll();
    window.addEventListener("scroll", onScroll, { passive: true });
    return () => window.removeEventListener("scroll", onScroll);
  }, []);
  useEffect(() => setOpen(false), [loc.pathname]);
  const signOut = async () => {
    await logout();
    nav("/");
  };
  const landing = !eu && loc.pathname === "/";

  return (
    <>
      <a href="#content" className="skip">
        Skip to content
      </a>
      <header className={`hdr ${scrolled || open ? "scrolled" : ""} ${open ? "open" : ""}`}>
        <div className="container hdr-in">
          <Brand to={homeFor(eu)} />
          {eu?.rol === "consilier" && (
            <nav className="nav" aria-label="Main">
              <NavLink to="/desk">My desk</NavLink>
              <NavLink to="/queue">My queue</NavLink>
            </nav>
          )}
          {eu?.rol === "admin" && (
            <nav className="nav" aria-label="Main">
              <NavLink to="/overview">Overview</NavLink>
              <NavLink to="/queue">Queue</NavLink>
              <NavLink to="/reports">Reports</NavLink>
              <NavLink to="/rules">Rules engine</NavLink>
            </nav>
          )}
          {!eu && landing && (
            <nav className="nav" aria-label="Main">
              <a href="#how">How it works</a>
              <a href="#signin">Sign in</a>
            </nav>
          )}
          <div className="cta">
            {source === "static" && <span className="who">static data · server offline</span>}
            {eu ? (
              <>
                <span className="who">{eu.nume}</span>
                <button type="button" className="btn ghost" onClick={signOut}>
                  Sign out
                </button>
              </>
            ) : (
              <a href="#signin" className="btn primary" onClick={(e) => { if (loc.pathname !== "/") { e.preventDefault(); nav("/#signin"); } }}>
                Open the queue <span className="arrow">→</span>
              </a>
            )}
            <button type="button" className="btn ghost menu-btn" aria-expanded={open} onClick={() => setOpen(!open)}>
              Menu
            </button>
          </div>
        </div>
      </header>
      <main id="content" className={`container ${landing ? "landing" : ""}`}>
        <Routes>
          <Route path="/" element={<Home />} />
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
