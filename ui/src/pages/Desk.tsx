import { Link } from "react-router-dom";
import { getDeciziiLocale } from "../api/client";
import { useBirou, useContext } from "../api/hooks";
import { CaseCard } from "../components/CaseCard";
import { decisionName } from "../components/State";
import { Figure, Loading } from "../components/ui";
import { date, dateLong, label, pct } from "../format";

/** The advisor's desk: three figures that are the day, the next cases to open, and a quiet activity card.
 *  Only cases assigned to the signed-in advisor. */
export default function Desk() {
  const b = useBirou();
  const ctx = useContext();
  const local = getDeciziiLocale();
  if (!b.data || !ctx.data) return <Loading err={b.error ? String(b.error) : null} />;
  const { coada, activitate, primele, utilizator } = b.data;
  const today = ctx.data.azi;
  const rez = activitate.rezultate;
  const first = utilizator.nume.split(" ")[0];
  const next = primele.slice(0, 3);

  return (
    <>
      <section className="day section" aria-labelledby="hello">
        <p className="date">{dateLong(today)} · my desk</p>
        <h1 id="hello" className="hl">{first}, here's your day.</h1>
        <div className="figures">
          <Figure n={coada.p1_azi} label="urgent cases due today" to="/queue?band=P1&only=due_today&sort=due" zero={coada.p1_azi === 0} />
          <Figure n={coada.de_confirmat} label="cases with something to confirm before the offer" to="/queue?only=to_confirm" zero={coada.de_confirmat === 0} />
          <Figure n={coada.deschise} label="open cases in your queue" to="/queue" />
        </div>
        {coada.peste_plafon > 0 && (
          <p className="meta" style={{ marginTop: 18 }}>
            <Link to="/queue?only=over_cap">{coada.peste_plafon} offers deferred over this month's cap</Link>: approve them explicitly or pick them up next month.
          </p>
        )}
      </section>

      <div className="desk-grid">
        <section aria-labelledby="start">
          <div className="label-row">
            <span id="start">[01] Start here</span>
            <span>/ nearest deadlines</span>
          </div>
          <div className="rows" style={{ marginTop: 16 }}>
            {next.length === 0 ? <div className="empty">Nothing open in your queue.</div> : next.map((c) => <CaseCard key={c.case.case_id} c={c} today={today} decision={local[c.case.case_id]} />)}
          </div>
          {coada.deschise > next.length && (
            <p style={{ marginTop: 16 }}>
              <Link to="/queue" className="btn secondary">
                All my cases <span className="arrow">→</span>
              </Link>
            </p>
          )}
        </section>

        <section aria-labelledby="act">
          <div className="label-row">
            <span id="act">[02] Your activity</span>
            <span>/ {activitate.decizii} decisions</span>
          </div>
          <div className="win activity" style={{ marginTop: 16 }}>
            <dl className="stats">
              <div>
                <dd>{activitate.decizii_azi}</dd>
                <dt>decisions today</dt>
              </div>
              <div>
                <dd>{activitate.decizii ? pct(activitate.override / activitate.decizii, 0) : "–"}</dd>
                <dt>recommendations changed</dt>
              </div>
              <div>
                <dd>{rez.n ? pct(rez.ramasi / rez.n, 0) : "–"}</dd>
                <dt>clients still here at 90 days</dt>
              </div>
            </dl>
            <p className="mono" style={{ margin: "18px 0 8px" }}>Last decisions</p>
            {activitate.ultimele.length === 0 ? (
              <p className="meta" style={{ margin: 0 }}>None yet. Open a case and press "Decide".</p>
            ) : (
              <div className="history">
                {activitate.ultimele.slice(0, 4).map((d, i) => (
                  <div key={i}>
                    <Link to={`/queue/${d.case_id}`} className="id">{d.case_id}</Link> · <b>{decisionName(d.decizie)}</b>
                    {d.override && <span className="tag warn" style={{ marginLeft: 6 }}>changed</span>}
                    {d.interventie_finala && d.interventie_finala !== d.interventie_agent ? ` → ${label(d.interventie_finala)}` : ""}
                    <span className="muted"> · {date(d.timestamp)}</span>
                    {d.rezultat && <span className={`tag ${d.rezultat === "ramas" ? "ok" : "bad"}`} style={{ marginLeft: 6 }}>{d.rezultat === "ramas" ? "stayed" : "left"}</span>}
                  </div>
                ))}
              </div>
            )}
          </div>
        </section>
      </div>
    </>
  );
}
