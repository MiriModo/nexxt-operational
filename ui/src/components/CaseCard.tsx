import { Link } from "react-router-dom";
import { eticheta, ron, zile } from "../format";
import type { Caz, DecizieRecord } from "../types/api";
import { Stare } from "./Stare";
import { BandaBadge } from "./ui";

const FEREASTRA_ZILE = 14; // bara de termen: cât din fereastra de lucru a mai rămas

function termen(z: number) {
  if (z < 0) return `depășit cu ${-z} ${-z === 1 ? "zi" : "zile"}`;
  if (z === 0) return "azi";
  if (z === 1) return "mâine";
  return `în ${z} zile`;
}

/** Bara de termen: cât timp mai e până la termen, pe o fereastră de 14 zile; roșu la ≤ 1 zi, coral la ≤ 5. */
export function Sla({ deadline, azi }: { deadline: string; azi: string }) {
  if (!azi) return <span className="muted">{deadline}</span>;
  const z = zile(deadline, azi);
  const w = Math.max(4, Math.min(100, ((z + 1) / FEREASTRA_ZILE) * 100));
  return (
    <span className={`sla ${z <= 1 ? "urgent" : z <= 5 ? "curand" : ""}`} title={`termen ${deadline}`}>
      <i aria-hidden="true">
        <b style={{ width: `${w}%` }} />
      </i>
      <span>termen {termen(z)}</span>
    </span>
  );
}

export function CaseCard({ c, azi, decizie }: { c: Caz; azi: string; decizie?: DecizieRecord }) {
  const { case: cs, client, loan, rec } = c;
  const deConfirmat = (rec.incertitudini?.length ?? 0) > 0 || (rec.oferta?.conditii_de_confirmat?.length ?? 0) > 0;

  return (
    <Link to={`/cazuri/${cs.case_id}`} className="case-card" aria-label={`${client.nume}, cazul ${cs.case_id}`}>
      <div className="cc-band">
        <BandaBadge b={cs.banda} />
      </div>
      <div className="cc-main">
        <div className="cc-title">
          <span className="cc-name">{client.nume}</span>
          <span className="cc-id">{cs.case_id}</span>
          {decizie && <span className={`tag ${decizie.decizie === "respinge" ? "fail" : "ok"}`}>decis: {decizie.decizie}</span>}
          {!decizie && deConfirmat && <span className="tag inc">de confirmat</span>}
          {!decizie && rec.oferta?.amanata_buget && <span className="tag">amânată, peste plafon</span>}
        </div>
        <div className="cc-meta">
          {eticheta(cs.produs)}
          {loan ? `, sold ${ron(loan.sold)}` : ""}
          {" · "}
          <Sla deadline={cs.deadline} azi={azi} />
        </div>
        {cs.motive_top3[0] && <div className="cc-motiv">{cs.motive_top3[0]}</div>}
      </div>
      <div className="cc-side">
        <div className="cc-rec">
          <Stare r={rec.recomandare} />
          {rec.interventie && rec.interventie !== rec.recomandare && <span className="cc-rec-sub">{eticheta(rec.interventie)}</span>}
        </div>
      </div>
    </Link>
  );
}
