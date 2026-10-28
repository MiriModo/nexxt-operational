import { Link } from "react-router-dom";
import { getDeciziiLocale } from "../api/client";
import { useContext, useSumar } from "../api/hooks";
import { CaseCard } from "../components/CaseCard";
import { Loading } from "../components/ui";

function dataLunga(iso: string) {
  const d = new Date(iso + "T12:00:00");
  return new Intl.DateTimeFormat("ro-RO", { weekday: "long", day: "numeric", month: "long" }).format(d);
}

/** Briefing-ul zilei: trei liste cu link direct, nu contoare generale. */
export default function Acasa() {
  const sumar = useSumar();
  const ctx = useContext();
  const decizii = getDeciziiLocale();
  if (!sumar.data || !ctx.data) return <Loading err={sumar.error ? String(sumar.error) : null} />;
  const s = sumar.data;
  const azi = ctx.data.azi;

  const linii: { n: number; text: string; to: string }[] = [
    { n: s.p1_azi ?? s.scadente_azi, text: "cazuri urgente cu termenul azi", to: "/cazuri?banda=P1&doar=termen_azi&sort=termen" },
    { n: s.peste_plafon ?? 0, text: "oferte amânate peste plafonul lunii, de aprobat explicit", to: "/cazuri?doar=peste_plafon" },
    { n: s.de_confirmat ?? 0, text: "cazuri cu ceva de confirmat înainte de ofertă", to: "/cazuri?doar=de_confirmat" },
    { n: s.deschise, text: "cazuri deschise în total", to: "/cazuri" },
  ];

  return (
    <>
      <section className="hero" aria-labelledby="salut">
        <p className="hero-date">{dataLunga(azi)}</p>
        <h1 id="salut" className="hero-title">
          Ce ai de făcut azi<span className="dot" aria-hidden="true" />
        </h1>
        <ul className="brief">
          {linii.map((l) => (
            <li key={l.to}>
              <Link to={l.to} className={l.n === 0 ? "zero" : undefined}>
                <b>{l.n}</b> {l.text}
              </Link>
            </li>
          ))}
        </ul>
      </section>

      {s.primele.length > 0 && (
        <section className="block" aria-labelledby="incepe">
          <div className="block-head">
            <h2 id="incepe">Începe de aici</h2>
            <p className="muted">cele mai apropiate termene</p>
          </div>
          <div className="case-list">
            {s.primele.map((c) => (
              <CaseCard key={c.case.case_id} c={c} azi={azi} decizie={decizii[c.case.case_id]} />
            ))}
          </div>
        </section>
      )}
    </>
  );
}
