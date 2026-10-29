import { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { EroareHttp, getCaz, getContext, getDeciziiLocale } from "../api/client";
import { useVerifica } from "../api/hooks";
import { Due } from "../components/CaseCard";
import { CATEGORIES, categoryName } from "../components/Categories";
import { AgentProposal } from "../components/AgentProposal";
import { State, decisionName } from "../components/State";
import { Band, Loading } from "../components/ui";
import { label, num, pct, pp, ron } from "../format";
import { proposal } from "../proposal";
import type { Caz, CheckInfo, Cheltuieli, OfferInfo, Reverificare, VerificareRezultat } from "../types/api";

const STAGES = ["intern", "anaf", "biroul_credit", "crc", "garantie", "eligibilitate"];
const STAGE_NAME: Record<string, string> = {
  intern: "in-house", anaf: "tax authority (ANAF)", biroul_credit: "credit bureau", crc: "central credit register (CRC)", garantie: "collateral", eligibilitate: "eligibility",
};
const ICON: Record<string, { cls: string; ch: string }> = {
  ok: { cls: "ok", ch: "✓" }, avertizare: { cls: "wa", ch: "!" }, fail: { cls: "no", ch: "×" }, indisponibil: { cls: "wa", ch: "?" }, neexecutat: { cls: "skip", ch: "–" },
};
const PROBLEM = new Set(["avertizare", "fail", "indisponibil"]);
type Stage = Reverificare["trepte"][number];

function groupStages(check: CheckInfo): Stage[] {
  return STAGES.map((t) => ({ treapta: t, rezultate: check.rezultate.filter((r) => r.treapta === t) }))
    .filter((t) => t.rezultate.length)
    .map((t) => ({
      ...t,
      stare: check.oprit_la === t.treapta ? "oprita" : t.rezultate.every((r) => r.status === "neexecutat") ? "neexecutata" : "executata",
    }));
}

function Row({ r, live }: { r: VerificareRezultat; live?: boolean }) {
  const ic = ICON[r.status] ?? ICON.neexecutat;
  return (
    <div className={`check ${ic.cls} ${live ? "live" : ""}`}>
      <i className={ic.cls} aria-label={r.status}>
        {ic.ch}
      </i>
      <span>{label(r.id)}</span>
      <span className="ev">
        {r.dovada}
        {r.incertitudine ? ` · ${r.incertitudine}` : ""}
      </span>
    </div>
  );
}

/** Checks: one summary line, then only the rows that need a look (warnings, failures, unavailable sources).
 *  The full list, by stage, sits under "Show all checks"; "Re-check" replays it stage by stage there. */
function Checks({ check, caseId }: { check: CheckInfo; caseId: string }) {
  const verify = useVerifica(caseId);
  const [stages, setStages] = useState<Stage[]>(() => groupStages(check));
  const [visible, setVisible] = useState<number>(Infinity);
  const [open, setOpen] = useState(false);
  useEffect(() => {
    if (visible === Infinity) return;
    if (visible >= stages.length) {
      setVisible(Infinity);
      return;
    }
    const t = setTimeout(() => setVisible(visible + 1), 450);
    return () => clearTimeout(t);
  }, [visible, stages.length]);
  const running = verify.isPending || visible !== Infinity;
  const recheck = () =>
    verify.mutate(undefined, {
      onSuccess: (r) => {
        setStages(r.trepte);
        setOpen(true);
        setVisible(0);
      },
    });
  const rows = stages.flatMap((s) => s.rezultate);
  const passed = rows.filter((r) => r.status === "ok").length;
  const problems = rows.filter((r) => PROBLEM.has(r.status));
  const skipped = rows.filter((r) => r.status === "neexecutat").length;
  const income = check.concluzii.venit_lunar;
  const facts = [income ? `income ${ron(income)}/month` : "", check.concluzii.dti_curent ? `DTI ${pct(check.concluzii.dti_curent, 0)}` : ""].filter(Boolean).join(", ");

  return (
    <section className="sec" aria-labelledby="checks">
      <div className="sec-label">
        <span id="checks">[03] Checks</span>
        <button type="button" className="btn secondary sm" disabled={running} onClick={recheck}>
          {running ? "Checking…" : "Re-check"}
        </button>
      </div>
      <p className="summary">
        <b>{passed} passed</b>
        {problems.length > 0 && (
          <>
            {" · "}
            <b className="warn">{problems.length} to review</b>
          </>
        )}
        {skipped > 0 && ` · ${skipped} not needed (stopped at ${STAGE_NAME[check.oprit_la ?? ""] ?? check.oprit_la})`}
        {facts ? ` · ${facts}` : ""}
      </p>
      {verify.error && <div className="notice fail">{String(verify.error)}</div>}
      {problems.length > 0 && (
        <div className="checks">
          {problems.map((r) => (
            <Row key={r.id} r={r} />
          ))}
        </div>
      )}
      <details className="more" open={open} onToggle={(e) => setOpen((e.currentTarget as HTMLDetailsElement).open)}>
        <summary>Show all checks</summary>
        <div className="checks">
          {stages.map((t, i) => {
            if (visible !== Infinity && i > visible) return null;
            const live = visible !== Infinity && i === visible;
            return (
              <div key={t.treapta}>
                <div className="stage">
                  {STAGE_NAME[t.treapta] ?? t.treapta}
                  {t.stare === "oprita" ? " · stopped here" : t.stare === "neexecutata" ? " · not needed" : ""}
                </div>
                {t.rezultate.map((r) => (
                  <Row key={r.id} r={r} live={live} />
                ))}
              </div>
            );
          })}
        </div>
      </details>
    </section>
  );
}

/** Spending over the last months by payment category (as in the bank's app): top categories as bars, then what
 *  goes to other banks and to the client's own accounts. */
function Spending({ s }: { s: Cheltuieli }) {
  const top = s.categorii.slice(0, 6);
  const rest = s.categorii.slice(6).reduce((a, c) => a + c.suma, 0);
  const rows = [...top.map((c) => ({ k: categoryName(c.categorie), v: c.suma, text: `${ron(c.suma)} · ${pct(c.procent, 0)}`, kind: CATEGORIES[c.categorie]?.kind ?? "" }))];
  if (rest > 0) rows.push({ k: "Other", v: rest, text: `${ron(rest)} · ${pct(rest / s.total_out, 0)}`, kind: "mute" });
  const max = Math.max(1, ...rows.map((r) => r.v));
  return (
    <div className="spending">
      <p className="mono" style={{ margin: "18px 0 8px" }}>
        Spending, last {s.luni} months · {ron(s.total_out)}
      </p>
      <div className="hbars">
        {rows.map((r) => (
          <div key={r.k} style={{ display: "contents" }}>
            <span>{r.k}</span>
            <span className="b">
              <i className={r.kind} style={{ width: `${(r.v / max) * 100}%` }} />
            </span>
            <span className="v">{r.text}</span>
          </div>
        ))}
      </div>
      <p className="meta" style={{ margin: "8px 0 0" }}>
        income {ron(s.venit_lunar)}/month
        {s.loan_payments > 0 ? ` · ${ron(s.loan_payments)} to other banks` : ""}
        {s.internal_transfers > 0 ? ` · ${ron(s.internal_transfers)} to own accounts` : ""}
      </p>
    </div>
  );
}

/** The intervention menu as a cost × p-after chart: chosen point in brand blue, infeasible ones grey, target dashed. */
function MenuChart({ offer }: { offer: OfferInfo }) {
  const W = 560, H = 230, L = 46, R = 16, T = 14, B = 30;
  const maxCost = Math.max(1, ...offer.interventii.map((i) => i.cost));
  const x = (c: number) => L + (c / maxCost) * (W - L - R);
  const y = (p: number) => T + (1 - Math.max(0, Math.min(1, p))) * (H - T - B);
  const chosen = offer.interventii.find((i) => i.id === offer.aleasa);
  return (
    <svg className="menu-chart" viewBox={`0 0 ${W} ${H}`} role="img" aria-label="Menu interventions by cost and probability of leaving afterwards">
      <line className="ax" x1={L} y1={T} x2={L} y2={H - B} />
      <line className="ax" x1={L} y1={H - B} x2={W - R} y2={H - B} />
      <line className="target" x1={L} y1={y(offer.p_tinta)} x2={W - R} y2={y(offer.p_tinta)} />
      <text x={W - R} y={y(offer.p_tinta) - 4} textAnchor="end">TARGET {pct(offer.p_tinta, 0)}</text>
      <text x={L - 6} y={T + 4} textAnchor="end">100%</text>
      <text x={L - 6} y={H - B + 4} textAnchor="end">0%</text>
      <text x={L} y={H - 8}>0 RON</text>
      <text x={W - R} y={H - 8} textAnchor="end">{ron(maxCost)}</text>
      <text x={8} y={T + 4} transform={`rotate(-90 8 ${T + 4})`} textAnchor="end">P LEAVE AFTER</text>
      {offer.interventii.map((i) => (
        <circle key={i.id} className={`pt ${i.id === offer.aleasa ? "chosen" : ""} ${!i.fezabil ? "infeasible" : ""}`} cx={x(i.cost)} cy={y(i.p_dupa)} r={i.id === offer.aleasa ? 7 : 4.5}>
          <title>
            {i.eticheta}: cost {ron(i.cost)}, p after {pct(i.p_dupa, 0)}
            {!i.fezabil ? ` · ${i.motiv_infezabil ?? "infeasible"}` : ""}
          </title>
        </circle>
      ))}
      {chosen && (
        <text className="lbl" x={Math.min(x(chosen.cost) + 10, W - R - 140)} y={y(chosen.p_dupa) - 10}>
          {chosen.eticheta}
        </text>
      )}
    </svg>
  );
}

export default function Case() {
  const { id = "" } = useParams();
  const [c, setC] = useState<Caz | null | undefined>(undefined);
  const [err, setErr] = useState<{ status?: number; text: string } | null>(null);
  const [today, setToday] = useState("");
  useEffect(() => {
    getCaz(id)
      .then((x) => setC(x ?? null))
      .catch((e) => setErr({ status: e instanceof EroareHttp ? e.status : undefined, text: e instanceof Error ? e.message : String(e) }));
    getContext().then((ctx) => setToday(ctx.azi)).catch(() => undefined);
  }, [id]);
  if (err?.status === 403)
    return (
      <div className="notice warn">
        Case {id} isn't in your queue. <Link to="/queue">Back to your queue</Link>
      </div>
    );
  if (c === undefined) return <Loading err={err?.text} />;
  if (c === null)
    return (
      <div className="notice fail">
        Case {id} doesn't exist. <Link to="/queue">Back to the queue</Link>
      </div>
    );

  const { case: cs, client, loan, check, offer, rec } = c;
  const dec = getDeciziiLocale()[cs.case_id];
  const of = rec.oferta;
  const toConfirm = [
    ...(of?.conditii_de_confirmat ?? []),
    ...(rec.incertitudini ?? []).filter((i) => !(of?.conditii_de_confirmat ?? []).some((cc) => cc.includes(i.text.slice(0, 20)))).map((i) => i.text),
  ];
  const blocked = cs.blocaje.length > 0 || rec.recomandare === "blocat";
  const products = offer.legaturi.produse_active.map(label).join(", ");
  const relationship = [`${client.nivel} client since ${client.client_din.slice(0, 4)}`, products ? `also ${products}` : "no other products", cs.request_id ? `request ${cs.request_id}` : ""]
    .filter(Boolean)
    .join(" · ");

  return (
    <>
      <div className="label-row" style={{ marginBottom: 16 }}>
        <Link to="/queue">← Queue</Link>
        <span>
          case {cs.case_id} · {cs.client_id}
        </span>
      </div>

      <div className="strip">
        <Band b={cs.banda} />
        <div className="who">
          <b>{client.nume}</b>
          <span>
            {label(cs.produs)}
            {loan
              ? ` · balance ${ron(loan.sold)} · ${ron(loan.rata)}/month at ${pp(loan.dobanda)}${loan.tip_dobanda === "fixa" ? " fixed" : ""}${loan.expira ? ` until ${loan.expira}` : ""}${loan.moneda && loan.moneda !== "RON" ? ` (${loan.moneda}, shown in RON)` : ""}`
              : " · new request"}
          </span>
        </div>
        <div className="cell">
          <State r={rec.recomandare} lg />
          {rec.interventie && rec.interventie !== rec.recomandare && <span>{label(rec.interventie)}</span>}
        </div>
        <div className="cell">
          <Due deadline={cs.deadline} today={today} />
        </div>
        <div className="go">
          {dec && <span className={`tag ${dec.decizie === "respinge" ? "bad" : "ok"}`}>decided · {decisionName(dec.decizie)}</span>}
          <Link to={`/queue/${cs.case_id}/decide`} className="btn primary">
            {dec ? "Revisit the decision" : "Decide"} <span className="arrow">→</span>
          </Link>
        </div>
      </div>

      {blocked && (
        <div className="notice fail" role="status">
          Blocked: {cs.blocaje.length ? cs.blocaje.map(label).join(", ") : rec.motiv}. Nothing goes to the client until it's resolved.
        </div>
      )}

      <div className="grid c2 case-grid">
        <section className="sec" aria-labelledby="why">
          <div className="sec-label">
            <span id="why">[01] Why now</span>
          </div>
          <ul className="plain why">
            {cs.motive_top3.map((m) => (
              <li key={m}>{m}</li>
            ))}
          </ul>
          <p className="meta" style={{ marginTop: 12 }}>{relationship}</p>
          {c.cheltuieli && c.cheltuieli.categorii.length > 0 && <Spending s={c.cheltuieli} />}
        </section>

        <section className="sec" aria-labelledby="prop">
          <div className="sec-label">
            <span id="prop">[02] What the agent proposes</span>
          </div>
          <p className="lead">{proposal(rec)}</p>
          {of && (
            <dl className="offer">
              <div>
                <dd>{pp(of.dobanda_noua)}</dd>
                <dt>new rate, {of.perioada.replace(/ ani$/, " years").replace(/ an$/, " year")}</dt>
              </div>
              <div>
                <dd>
                  {of.rata_veche > 0 && <s>{ron(of.rata_veche)}</s>}
                  {ron(of.rata_noua)}
                </dd>
                <dt>monthly payment</dt>
              </div>
              <div>
                <dd>{ron(of.cost_banca)}</dd>
                <dt>it costs the bank</dt>
              </div>
            </dl>
          )}
          {of?.amanata_buget && (
            <p className="small" style={{ margin: "12px 0 0" }}>
              Deferred: this month's retention cap is used up. Approve it explicitly or pick it up next month.
            </p>
          )}
          {(toConfirm.length > 0 || rec.documente_lipsa.length > 0) && (
            <div className="todo">
              <ul className="plain">
                {toConfirm.map((t) => (
                  <li key={t}>to confirm: {t}</li>
                ))}
                {rec.documente_lipsa.map((d) => (
                  <li key={d.tip}>
                    to request: {label(d.tip)} ({d.motiv})
                  </li>
                ))}
              </ul>
            </div>
          )}
          <AgentProposal caseId={cs.case_id} />
        </section>
      </div>

      <Checks check={check} caseId={cs.case_id} />

      <details className="more">
        <summary>How the agent got here</summary>
        <div className="grid c2">
          <div>
            <p className="mono" style={{ marginBottom: 8 }}>Signals</p>
            <ul className="plain small">
              {cs.semnale.map((s) => (
                <li key={s.id}>
                  <b>{label(s.id)}</b> {num(s.scor, 1)} · {s.dovada}
                </li>
              ))}
            </ul>
          </div>
          <div>
            <p className="mono" style={{ marginBottom: 8 }}>Intervention menu</p>
            <MenuChart offer={offer} />
            <p className="meta" style={{ margin: "6px 0 0" }}>
              {offer.motiv_alegere} Light grey points are infeasible (BNR limits / internal caps); hover for the reason.
            </p>
          </div>
        </div>
        <details style={{ marginTop: 10 }}>
          <summary className="meta" style={{ cursor: "pointer" }}>Full explanation, as text</summary>
          <pre className="text" style={{ marginTop: 8, fontFamily: "var(--font-mono)", fontSize: 12 }}>
            {rec.explicatie}
          </pre>
        </details>
      </details>
    </>
  );
}
