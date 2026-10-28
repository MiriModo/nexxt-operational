import { useEffect, useRef, useState } from "react";
import { Navigate } from "react-router-dom";
import { useEu } from "../auth";
import { Login } from "../components/Login";

/** Pagina publică: ce face agentul, în trei rânduri, și un singur buton. Login-ul apare sub, la apăsare. */
export default function Home() {
  const { eu } = useEu();
  const [arataLogin, setArataLogin] = useState(false);
  const ancora = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (arataLogin) ancora.current?.scrollIntoView({ behavior: "smooth", block: "start" });
  }, [arataLogin]);
  if (eu) return <Navigate to={eu.rol === "admin" ? "/acasa" : "/biroul-meu"} replace />;

  return (
    <>
      <section className="hero home" aria-labelledby="titlu">
        <h1 id="titlu" className="hero-title">
          Colegul virtual al consilierului de credite<span className="dot" aria-hidden="true" />
        </h1>
        <p className="hero-sub">
          Găsește în portofoliu clienții care trebuie lucrați azi, face verificările pe care le-ai face tu și propune cea mai ieftină
          ofertă care îi păstrează. Tu decizi.
        </p>
        <ul className="home-list">
          <li>Semnalele de plecare și de risc, din tranzacții, cereri și surse externe, într-o singură coadă pe priorități.</li>
          <li>Verificări doar unde e nevoie, în trepte, cu oprire la prima picată și cu dovada fiecăreia.</li>
          <li>O propunere pe caz, cu rata nouă, ce economisește clientul și ce costă banca, gata de aprobat sau de schimbat cu motiv.</li>
        </ul>
        <div className="hero-actions">
          <button type="button" className="btn" onClick={() => setArataLogin(true)} aria-expanded={arataLogin} aria-controls="login">
            Intră în cont
          </button>
        </div>
      </section>
      <div ref={ancora} id="login" style={{ scrollMarginTop: 72 }}>
        {arataLogin && <Login />}
      </div>
    </>
  );
}
