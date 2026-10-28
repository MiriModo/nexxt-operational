import { Link } from "react-router-dom";
import { getDeciziiLocale } from "../api/client";
import { useBirou, useContext } from "../api/hooks";
import { CaseCard } from "../components/CaseCard";
import { STATES } from "../components/State";
import { Figure, Loading } from "../components/ui";
import { date, dateLong, label, pct } from "../format";
import type { Recomandare } from "../types/api";

/** The advisor's desk: their queue as a briefing with direct links, and their activity. Only cases assigned to them. */
export default function Desk() {
  const b = useBirou();
  const ctx = useContext();
  const local = getDeciziiLocale();
  if (!b.data || !ctx.data) return <Loading err={b.error ? String(b.error) : null} />;
  const { coada, activitate, primele, utilizator } = b.data;
  const today = ctx.data.azi;
  const rez = activitate.rezultate;
  const first = utilizator.nume.split(" ")[0];

  return (
    <>
      <section className="day section" aria-labelledby="hello">
        <p className="date">{dateLong(today)} · my desk</p>
        <h1 id="hello">{first}, here's your day.</h1>
        <div className="figures">
          <Figure n={coada.p1_azi} label="urgent cases due today" to="/queue?band=P1&only=due_today&sort=due" zero={coada.p1_azi === 0} />
          <Figure n={coada.peste_plafon} label="offers deferred over this month's cap, to approve explicitly" to="/queue?only=over_cap" zero={coada.peste_plafon === 0} />
          <Figure n={coada.de_confirmat} label="cases with something to confirm before the offer" to="/queue?only=to_confirm" zero={coada.de_confirmat === 0} />
          <Figure n={coada.deschise} label="open cases in your queue" to="/queue" />
        </div>
      </section>

      <section className="section">
        <div className="label-row">
          <span>[01] Your activity</span>
          <span>/ {activitate.decizii} decisions in total</span>
        </div>
        <div className="figures compact" style={{ marginTop: 24 }}>
          <Figure n={activitate.decizii_azi} label="decisions today" />
          <Figure n={activitate.decizii ? pct(activitate.override / activitate.decizii, 0) : "–"} label={`recommendations changed (${activitate.override} of ${activitate.decizii})`} />
          <Figure n={rez.n ? pct(rez.ramasi / rez.n, 0) : "–"} label={rez.n ? `clients still here at 90 days (${rez.ramasi} stayed, ${rez.plecati} left)` : "clients still here at 90 days — no results yet"} />
          <Figure
            n={coada.total}
            label={(Object.keys(STATES) as Recomandare[])
              .filter((r) => coada.distributie[r])
              .map((r) => `${coada.distributie[r]} ${STATES[r].short.toLowerCase()}`)
              .join(" · ")}
          />
        </div>
      </section>

      <div className="grid c2">
        <section className="section" aria-labelledby="start">
          <div className="label-row">
            <span id="start">[02] Start here</span>
            <span>/ nearest deadlines</span>
          </div>
          <div className="rows" style={{ marginTop: 16 }}>
            {primele.length === 0 ? <div className="empty">Nothing open in your queue.</div> : primele.map((c) => <CaseCard key={c.case.case_id} c={c} today={today} decision={local[c.case.case_id]} />)}
          </div>
        </section>
        <section className="section" aria-labelledby="last">
          <div className="label-row">
            <span id="last">[03] Your last decisions</span>
            <span>/ latest first</span>
          </div>
          {activitate.ultimele.length === 0 ? (
            <p className="meta" style={{ marginTop: 16 }}>No decisions yet. Open a case and press "Decide".</p>
          ) : (
            <div className="win history" style={{ marginTop: 16 }}>
              {activitate.ultimele.map((d, i) => (
                <div key={i}>
                  <Link to={`/queue/${d.case_id}`} className="id">{d.case_id}</Link> · <b>{d.decizie}</b>
                  {d.override && <span className="tag warn" style={{ marginLeft: 6 }}>changed</span>}
                  {d.interventie_finala && d.interventie_finala !== d.interventie_agent ? ` → ${label(d.interventie_finala)}` : ""}
                  <span className="muted"> · {date(d.timestamp)}</span>
                  {d.rezultat && <span className={`tag ${d.rezultat === "ramas" ? "ok" : "bad"}`} style={{ marginLeft: 6 }}>{d.rezultat === "ramas" ? "stayed" : "left"}</span>}
                </div>
              ))}
            </div>
          )}
        </section>
      </div>
    </>
  );
}
