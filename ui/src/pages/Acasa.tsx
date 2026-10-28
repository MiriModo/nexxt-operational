import { useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { getContext, getDeciziiLocale, getSumar, type Context } from "../api/client";
import { CaseCard } from "../components/CaseCard";
import { Loading } from "../components/ui";
import type { Sumar } from "../types/api";

function dataLunga(iso: string) {
  const d = new Date(iso + "T12:00:00");
  return new Intl.DateTimeFormat("ro-RO", { weekday: "long", day: "numeric", month: "long" }).format(d);
}

function plural(n: number, unu: string, multe: string) {
  return n === 1 ? `${n} ${unu}` : `${n} ${multe}`;
}

export default function Acasa() {
  // contoarele vin din GET /api/cazuri/sumar (toată coada), nu din încărcarea tuturor cazurilor
  const [sumar, setSumar] = useState<Sumar | null>(null);
  const [ctx, setCtx] = useState<Context | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const decizii = getDeciziiLocale();

  useEffect(() => {
    Promise.all([getSumar(), getContext()])
      .then(([s, x]) => {
        setSumar(s);
        setCtx(x);
      })
      .catch((e) => setErr(String(e)));
  }, []);

  const azi = ctx?.azi ?? "";
  const stare = useMemo(() => {
    if (!sumar) return null;
    return { deschise: sumar.deschise, p1: sumar.p1, scadenteAzi: sumar.scadente_azi, blocate: sumar.blocate, decise: sumar.decise, primele: sumar.primele };
  }, [sumar]);

  if (!sumar || !ctx || !stare) return <Loading err={err} />;

  const rezumat =
    stare.deschise === 0
      ? "Nu mai e nimic deschis în coadă. Poți închide ziua liniștit."
      : `${plural(stare.p1, "caz cere", "cazuri cer")} atenție azi` +
        (stare.scadenteAzi ? `, ${plural(stare.scadenteAzi, "are", "au")} termenul azi sau depășit` : "") +
        ".";

  return (
    <>
      <section className="hero" aria-labelledby="salut">
        <p className="hero-date">{dataLunga(ctx.azi)}</p>
        <h1 id="salut" className="hero-title">
          Haide să lucrăm și&nbsp;astăzi<span className="dot" aria-hidden="true" />
        </h1>
        <p className="hero-sub">{rezumat}</p>
        <div className="hero-actions">
          <Link to="/cazuri" className="btn">
            Deschide coada
          </Link>
          <Link to="/dashboard" className="btn secondary on-dark">
            Vezi rezultatele agentului
          </Link>
        </div>
        <dl className="hero-stats">
          <div>
            <dt>cazuri deschise</dt>
            <dd>{stare.deschise}</dd>
          </div>
          <div>
            <dt>cu termen azi sau depășit</dt>
            <dd>{stare.scadenteAzi}</dd>
          </div>
          <div>
            <dt>blocate de verificări</dt>
            <dd>{stare.blocate}</dd>
          </div>
          <div>
            <dt>decise deja</dt>
            <dd>{stare.decise}</dd>
          </div>
        </dl>
      </section>

      {stare.primele.length > 0 && (
        <section className="block" aria-labelledby="incepe">
          <div className="block-head">
            <h2 id="incepe">Începe de aici</h2>
            <p className="muted">Cele mai apropiate termene, în ordinea priorității. Apasă pe un caz pentru detalii.</p>
          </div>
          <div className="case-list">
            {stare.primele.map((c) => (
              <CaseCard key={c.case.case_id} c={c} azi={azi} decizie={decizii[c.case.case_id]} />
            ))}
          </div>
          <p style={{ marginTop: 14 }}>
            <Link to="/cazuri" className="link">
              Toate cele {stare.deschise} cazuri deschise
            </Link>
          </p>
        </section>
      )}
    </>
  );
}
