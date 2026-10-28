import { Link } from "react-router-dom";
import { days, label, ron } from "../format";
import type { Caz, DecizieRecord } from "../types/api";
import { State } from "./State";
import { Band } from "./ui";

const WINDOW_DAYS = 14; // the due bar: how much of the working window is left

function dueText(d: number) {
  if (d < 0) return `overdue by ${-d} ${-d === 1 ? "day" : "days"}`;
  if (d === 0) return "due today";
  if (d === 1) return "due tomorrow";
  return `due in ${d} days`;
}

/** Due bar: time left until the deadline on a 14-day window; red at ≤ 1 day, amber at ≤ 5. */
export function Due({ deadline, today }: { deadline: string; today: string }) {
  if (!today) return <span className="muted">{deadline}</span>;
  const d = days(deadline, today);
  const w = Math.max(4, Math.min(100, ((d + 1) / WINDOW_DAYS) * 100));
  return (
    <span className={`due ${d <= 1 ? "urgent" : d <= 5 ? "soon" : ""}`} title={`deadline ${deadline}`}>
      <i aria-hidden="true">
        <b style={{ width: `${w}%` }} />
      </i>
      <span>{dueText(d)}</span>
    </span>
  );
}

export function CaseCard({ c, today, decision }: { c: Caz; today: string; decision?: DecizieRecord }) {
  const { case: cs, client, loan, rec } = c;
  const toConfirm = (rec.incertitudini?.length ?? 0) > 0 || (rec.oferta?.conditii_de_confirmat?.length ?? 0) > 0;
  return (
    <Link to={`/queue/${cs.case_id}`} className="row" aria-label={`${client.nume}, case ${cs.case_id}`}>
      <div>
        <div className="row-title">
          <Band b={cs.banda} />
          <span className="name">{client.nume}</span>
          <span className="id">{cs.case_id}</span>
          {decision && <span className={`tag ${decision.decizie === "respinge" ? "bad" : "ok"}`}>decided · {decision.decizie}</span>}
          {!decision && toConfirm && <span className="tag warn">to confirm</span>}
          {!decision && rec.oferta?.amanata_buget && <span className="tag">deferred · over cap</span>}
        </div>
        <div className="row-meta">
          <span>
            {label(cs.produs)}
            {loan ? `, balance ${ron(loan.sold)}` : ""}
          </span>
          <Due deadline={cs.deadline} today={today} />
        </div>
        {cs.motive_top3[0] && <div className="row-why">{cs.motive_top3[0]}</div>}
      </div>
      <div className="row-side">
        <State r={rec.recomandare} />
        {rec.interventie && rec.interventie !== rec.recomandare && <span className="sub">{label(rec.interventie)}</span>}
      </div>
    </Link>
  );
}
