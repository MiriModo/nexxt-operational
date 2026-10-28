import { Link } from "react-router-dom";
import { eticheta, ron, zile } from "../format";
import type { Caz, DecizieRecord } from "../types/api";
import { BandaBadge } from "./ui";

function termen(deadline: string, azi: string) {
  if (!azi) return deadline;
  const z = zile(deadline, azi);
  if (z < 0) return `termen depășit cu ${-z} ${-z === 1 ? "zi" : "zile"}`;
  if (z === 0) return "termen azi";
  if (z === 1) return "termen mâine";
  return `termen în ${z} zile`;
}

export function CaseCard({ c, azi, decizie }: { c: Caz; azi: string; decizie?: DecizieRecord }) {
  const { case: cs, client, loan, rec } = c;
  const z = azi ? zile(cs.deadline, azi) : 99;
  const urgent = z <= 1;
  const blocat = cs.blocaje.length > 0 || rec.recomandare === "blocat";

  return (
    <Link to={`/cazuri/${cs.case_id}`} className="case-card" aria-label={`Cazul ${cs.case_id}, ${client.nume}, vezi detaliile`}>
      <div className="cc-band">
        <BandaBadge b={cs.banda} />
      </div>
      <div className="cc-main">
        <div className="cc-title">
          <span className="cc-name">{client.nume}</span>
          <span className="cc-id">{cs.case_id}</span>
          {decizie && <span className={`tag ${decizie.decizie === "respinge" ? "fail" : "ok"}`}>{decizie.decizie}</span>}
          {blocat && !decizie && <span className="tag fail">blocat</span>}
          {rec.incertitudini && rec.incertitudini.length > 0 && (
            <span className="tag inc" title={rec.incertitudini.map((i) => i.text).join("; ")}>
              {rec.incertitudini.length === 1 ? "1 incertitudine" : `${rec.incertitudini.length} incertitudini`}
            </span>
          )}
          {rec.oferta?.amanata_buget && <span className="tag buget">peste plafon</span>}
        </div>
        <div className="cc-meta">
          {eticheta(cs.produs)}
          {loan ? `, sold ${ron(loan.sold)}${loan.moneda && loan.moneda !== "RON" ? ` (${loan.moneda})` : ""}` : ""},{" "}
          <span className={urgent ? "cc-urgent" : undefined}>{termen(cs.deadline, azi)}</span>
          {c.consilier ? ` · ${c.consilier}` : ""}
        </div>
        {cs.motive_top3[0] && <div className="cc-motiv">{cs.motive_top3[0]}</div>}
      </div>
      <div className="cc-side">
        <div className="cc-rec">
          <span className="cc-rec-main">{eticheta(rec.recomandare)}</span>
          {rec.interventie && rec.interventie !== rec.recomandare && <span className="cc-rec-sub">{eticheta(rec.interventie)}</span>}
        </div>
        <span className="btn secondary sm cc-cta" aria-hidden="true">
          Vezi detaliile
        </span>
      </div>
    </Link>
  );
}
