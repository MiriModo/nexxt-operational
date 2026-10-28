import { getDeciziiLocale } from "../api/client";
import { useContext, useSumar } from "../api/hooks";
import { CaseCard } from "../components/CaseCard";
import { Figure, Loading } from "../components/ui";
import { dateLong } from "../format";

/** The administrator's overview: the same briefing, on the whole queue. */
export default function Overview() {
  const sumar = useSumar();
  const ctx = useContext();
  const local = getDeciziiLocale();
  if (!sumar.data || !ctx.data) return <Loading err={sumar.error ? String(sumar.error) : null} />;
  const s = sumar.data;
  const today = ctx.data.azi;
  return (
    <>
      <section className="day section" aria-labelledby="hello">
        <p className="date">{dateLong(today)} · whole portfolio · {ctx.data.clienti.toLocaleString("en-US")} clients</p>
        <h1 id="hello" className="hl">What the queue holds today.</h1>
        <div className="figures">
          <Figure n={s.p1_azi ?? s.scadente_azi} label="urgent cases due today" to="/queue?band=P1&only=due_today&sort=due" />
          <Figure n={s.peste_plafon ?? 0} label="offers deferred over this month's cap" to="/queue?only=over_cap" />
          <Figure n={s.de_confirmat ?? 0} label="cases with something to confirm" to="/queue?only=to_confirm" />
          <Figure n={s.deschise} label="open cases in total" to="/queue" />
        </div>
      </section>
      {s.primele.length > 0 && (
        <section className="section" aria-labelledby="start">
          <div className="label-row">
            <span id="start">[01] Start here</span>
            <span>/ nearest deadlines</span>
          </div>
          <div className="rows" style={{ marginTop: 16 }}>
            {s.primele.map((c) => (
              <CaseCard key={c.case.case_id} c={c} today={today} decision={local[c.case.case_id]} />
            ))}
          </div>
        </section>
      )}
    </>
  );
}
