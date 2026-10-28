import { Link } from "react-router-dom";
import { getDeciziiLocale } from "../api/client";
import { useBirou, useContext } from "../api/hooks";
import { CaseCard } from "../components/CaseCard";
import { STARI } from "../components/Stare";
import { Kpi, Loading } from "../components/ui";
import { eticheta, pct } from "../format";
import type { Recomandare } from "../types/api";

function dataLunga(iso: string) {
  const d = new Date(iso + "T12:00:00");
  return new Intl.DateTimeFormat("ro-RO", { weekday: "long", day: "numeric", month: "long" }).format(d);
}

/** Biroul consilierului: coada lui (briefing cu link direct) și activitatea lui. Doar cazurile alocate lui. */
export default function Birou() {
  const b = useBirou();
  const ctx = useContext();
  const decizii = getDeciziiLocale();
  if (!b.data || !ctx.data) return <Loading err={b.error ? String(b.error) : null} />;
  const { coada, activitate, primele, utilizator } = b.data;
  const azi = ctx.data.azi;
  const linii = [
    { n: coada.p1_azi, text: "cazuri urgente cu termenul azi", to: "/cazuri?banda=P1&doar=termen_azi&sort=termen" },
    { n: coada.peste_plafon, text: "oferte amânate peste plafonul lunii, de aprobat explicit", to: "/cazuri?doar=peste_plafon" },
    { n: coada.de_confirmat, text: "cazuri cu ceva de confirmat înainte de ofertă", to: "/cazuri?doar=de_confirmat" },
    { n: coada.deschise, text: "cazuri deschise în coada ta", to: "/cazuri" },
  ];
  const rez = activitate.rezultate;

  return (
    <>
      <section className="hero" aria-labelledby="salut">
        <p className="hero-date">{dataLunga(azi)}</p>
        <h1 id="salut" className="hero-title">
          {utilizator.nume.split(" ")[0]}, ce ai de făcut azi<span className="dot" aria-hidden="true" />
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

      <div className="grid c4">
        <Kpi l="Decizii luate azi" v={activitate.decizii_azi} s={`${activitate.decizii} în total`} />
        <Kpi l="Recomandări schimbate" v={activitate.decizii ? pct(activitate.override / activitate.decizii, 0) : "–"} s={`${activitate.override} din ${activitate.decizii}`} />
        <Kpi l="Clienți rămași la 90 de zile" v={rez.n ? pct(rez.ramasi / rez.n, 0) : "–"} s={rez.n ? `${rez.ramasi} rămași, ${rez.plecati} plecați` : "încă fără rezultate"} />
        <Kpi
          l="Coada ta"
          v={coada.total}
          s={(Object.keys(STARI) as Recomandare[])
            .filter((r) => coada.distributie[r])
            .map((r) => `${coada.distributie[r]} ${STARI[r].scurt}`)
            .join(" · ")}
        />
      </div>

      <div className="grid c2">
        <section className="block" aria-labelledby="incepe">
          <div className="block-head">
            <h2 id="incepe">Începe de aici</h2>
            <p className="muted">cele mai apropiate termene</p>
          </div>
          {primele.length === 0 ? (
            <div className="empty">Nimic deschis în coada ta.</div>
          ) : (
            <div className="case-list">
              {primele.map((c) => (
                <CaseCard key={c.case.case_id} c={c} azi={azi} decizie={decizii[c.case.case_id]} />
              ))}
            </div>
          )}
        </section>
        <section className="block" aria-labelledby="ultimele">
          <div className="block-head">
            <h2 id="ultimele">Ultimele tale decizii</h2>
          </div>
          {activitate.ultimele.length === 0 ? (
            <p className="muted small">Nicio decizie încă. Deschide un caz și apasă „Ia decizia”.</p>
          ) : (
            <div className="istoric panel">
              {activitate.ultimele.map((d, i) => (
                <div key={i} className="small" style={{ padding: "6px 0" }}>
                  <Link to={`/cazuri/${d.case_id}`}>{d.case_id}</Link> · <b>{d.decizie}</b>
                  {d.override && <span className="tag avertizare" style={{ marginLeft: 6 }}>schimbată</span>}
                  {d.interventie_finala && d.interventie_finala !== d.interventie_agent ? ` → ${eticheta(d.interventie_finala)}` : ""}
                  <span className="muted"> · {new Date(d.timestamp).toLocaleDateString("ro-RO")}</span>
                  {d.rezultat && <span className={`tag ${d.rezultat === "ramas" ? "ok" : "fail"}`} style={{ marginLeft: 6 }}>{d.rezultat === "ramas" ? "a rămas" : "a plecat"}</span>}
                </div>
              ))}
            </div>
          )}
        </section>
      </div>
    </>
  );
}
