import { useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { getCazuri, getContext, getDeciziiLocale, type Context } from "../api/client";
import { CaseCard } from "../components/CaseCard";
import { Loading } from "../components/ui";
import type { Caz } from "../types/api";

function dataLunga(iso: string) {
  const d = new Date(iso + "T12:00:00");
  return new Intl.DateTimeFormat("ro-RO", { weekday: "long", day: "numeric", month: "long" }).format(d);
}

function plural(n: number, unu: string, multe: string) {
  return n === 1 ? `${n} ${unu}` : `${n} ${multe}`;
}

export default function Acasa() {
  const [cazuri, setCazuri] = useState<Caz[] | null>(null);
  const [ctx, setCtx] = useState<Context | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const decizii = getDeciziiLocale();

  useEffect(() => {
    Promise.all([getCazuri(), getContext()])
      .then(([c, x]) => {
        setCazuri(c);
        setCtx(x);
      })
      .catch((e) => setErr(String(e)));
  }, []);

  const azi = ctx?.azi ?? "";
  const stare = useMemo(() => {
    if (!cazuri || !azi) return null;
    const deschise = cazuri.filter((c) => !decizii[c.case.case_id]);
    const p1 = deschise.filter((c) => c.case.banda === "P1");
    const scadenteAzi = deschise.filter((c) => c.case.deadline <= azi);
    const blocate = deschise.filter((c) => c.case.blocaje.length > 0 || c.rec.recomandare === "blocat");
    const decise = cazuri.length - deschise.length;
    const primele = [...deschise]
      .sort((a, b) => {
        if (a.case.deadline !== b.case.deadline) return a.case.deadline.localeCompare(b.case.deadline);
        return b.case.scoruri.prioritate - a.case.scoruri.prioritate;
      })
      .slice(0, 5);
    return { deschise, p1, scadenteAzi, blocate, decise, primele };
  }, [cazuri, azi, decizii]);

  if (!cazuri || !ctx || !stare) return <Loading err={err} />;

  const rezumat =
    stare.deschise.length === 0
      ? "Nu mai e nimic deschis în coadă. Poți închide ziua liniștit."
      : `${plural(stare.p1.length, "caz cere", "cazuri cer")} atenție azi` +
        (stare.scadenteAzi.length ? `, ${plural(stare.scadenteAzi.length, "are", "au")} termenul azi sau depășit` : "") +
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
            <dd>{stare.deschise.length}</dd>
          </div>
          <div>
            <dt>cu termen azi sau depășit</dt>
            <dd>{stare.scadenteAzi.length}</dd>
          </div>
          <div>
            <dt>blocate de verificări</dt>
            <dd>{stare.blocate.length}</dd>
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
              Toate cele {stare.deschise.length} cazuri deschise
            </Link>
          </p>
        </section>
      )}
    </>
  );
}
