import { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { EroareHttp, getCaz, getContext, getDeciziiLocale } from "../api/client";
import { useVerifica } from "../api/hooks";
import { Due } from "../components/CaseCard";
import { State, decisionName, stateName } from "../components/State";
import { Band, Loading } from "../components/ui";
import { label, num, pct, pp, ron } from "../format";
import { proposal } from "../proposal";
import type { Caz, CheckInfo, OfferInfo, Reverificare, VerificareRezultat } from "../types/api";

const STAGES = ["intern", "anaf", "biroul_credit", "crc", "garantie", "eligibilitate"];
const STAGE_NAME: Record<string, string> = {
  intern: "in-house", anaf: "tax authority (ANAF)", biroul_credit: "credit bureau", crc: "central credit register (CRC)", garantie: "collateral", eligibilitate: "eligibility",
};
const ICON: Record<string, { cls: string; ch: string }> = {
  ok: { cls: "ok", ch: "✓" }, avertizare: { cls: "wa", ch: "!" }, fail: { cls: "no", ch: "×" }, indisponibil: { cls: "wa", ch: "?" }, neexecutat: { cls: "skip", ch: "–" },
};
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

/** Checks, one row each, grouped by stage (guide D3). "Re-check" replays them stage by stage so you can see the flow
 *  stop at the first failure and skip the external sources after it. Skipped checks are not shown. */
function Checks({ check, caseId }: { check: CheckInfo; caseId: string }) {
  const verify = useVerifica(caseId);
  const [stages, setStages] = useState<Stage[]>(() => groupStages(check));
  const [visible, setVisible] = useState<number>(Infinity);
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
        setVisible(0);
      },
    });
  const income = check.concluzii.venit_lunar;
  return (
    <section className="sec" aria-labelledby="checks">
      <div className="sec-label">
        <span id="checks">
          [04] Checks
          {check.oprit_la ? ` · stopped at ${STAGE_NAME[check.oprit_la] ?? check.oprit_la}` : ""}
          {income ? ` · income ${ron(income)}/month` : ""}
          {check.concluzii.dti_curent ? `, DTI ${pct(check.concluzii.dti_curent, 0)}` : ""}
        </span>
        <button type="button" className="btn secondary sm" disabled={running} onClick={recheck}>
          {running ? "Checking…" : "Re-check"}
        </button>
      </div>
      {verify.error && <div className="notice fail">{String(verify.error)}</div>}
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
    </section>
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
            {loan ? ` · balance ${ron(loan.sold)}` : " · new request"}
          </span>
        </div>
        <div className="cell">
          <State r={rec.recomandare} lg />
          {rec.interventie && rec.interventie !== rec.recomandare && <span>{label(rec.interventie)}</span>}
        </div>
        {of && (
          <div className="cell">
            <b>
              {ron(of.rata_veche)} → {ron(of.rata_noua)}
            </b>
            <span>monthly payment · bank cost {ron(of.cost_banca)}</span>
          </div>
        )}
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

      <div className="grid c2">
        <div>
          <section className="sec" aria-labelledby="why">
            <div className="sec-label">
              <span id="why">[01] Why now</span>
            </div>
            <ul className="plain">
              {cs.motive_top3.map((m) => (
                <li key={m}>{m}</li>
              ))}
            </ul>
          </section>
          <section className="sec" aria-labelledby="who">
            <div className="sec-label">
              <span id="who">[02] The client</span>
            </div>
            <dl className="kv">
              <dt>Relationship</dt>
              <dd>
                {client.nivel}, client since {client.client_din.slice(0, 4)}
                {offer.legaturi.produse_active.length ? `, ${offer.legaturi.produse_active.map(label).join(", ")}` : ", no other products"}
              </dd>
              {loan && (
                <>
                  <dt>The loan</dt>
                  <dd>
                    payment {ron(loan.rata)}, rate {pp(loan.dobanda)} {loan.tip_dobanda === "fixa" ? "fixed" : loan.tip_dobanda}
                    {loan.expira ? `, fixed until ${loan.expira}` : ""}
                    {loan.moneda && loan.moneda !== "RON" ? ` (in ${loan.moneda}, balance shown in RON)` : ""}
                  </dd>
                </>
              )}
              {cs.request_id && (
                <>
                  <dt>Request</dt>
                  <dd className="id">{cs.request_id}</dd>
                </>
              )}
            </dl>
          </section>
        </div>

        <section className="sec" aria-labelledby="prop">
          <div className="sec-label">
            <span id="prop">[03] What the agent proposes</span>
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
                  <s>{ron(of.rata_veche)}</s>
                  {ron(of.rata_noua)}
                </dd>
                <dt>monthly payment</dt>
              </div>
              {of.economie_client > 0 && (
                <div>
                  <dd>{ron(of.economie_client)}</dd>
                  <dt>the client saves</dt>
                </div>
              )}
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
          {rec.llm && (
            <>
              <p className="mono" style={{ margin: "14px 0 6px" }}>Text for the client</p>
              <pre className="text">{rec.llm.text_client}</pre>
            </>
          )}
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
            <p className="small" style={{ marginTop: 12 }}>
              If the client leaves, they gain <b>{ron(offer.B)}</b> over 3 years; probability of leaving now <b>{pct(offer.p, 0)}</b> (target{" "}
              {pct(offer.p_tinta, 0)}); if they stay, they're worth <b>{ron(offer.V)}</b>. {offer.motiv_alegere}
            </p>
            <p className="meta">{rec.motiv}</p>
            {rec.grafic && (
              <p className="meta">
                New schedule: {rec.grafic.nr_rate} payments until {rec.grafic.ultima_luna}, total interest {ron(rec.grafic.dobanda_totala)}.
              </p>
            )}
          </div>
          <div>
            <p className="mono" style={{ marginBottom: 8 }}>Intervention menu</p>
            <MenuChart offer={offer} />
            <p className="meta" style={{ margin: "6px 0 0" }}>
              Chosen: <b>{stateName(rec.recomandare)}</b>
              {offer.aleasa ? ` · ${offer.interventii.find((i) => i.id === offer.aleasa)?.eticheta ?? label(offer.aleasa)}` : ""}. Light grey points are infeasible
              (BNR limits / internal caps); hover for the reason.
            </p>
          </div>
        </div>
        <details style={{ marginTop: 10 }}>
          <summary className="meta" style={{ cursor: "pointer" }}>Full explanation, as text</summary>
          <pre className="text" style={{ marginTop: 8, fontFamily: "var(--font-mono)", fontSize: 12 }}>
            {rec.explicatie}
          </pre>
        </details>
        <p className="meta mono" style={{ marginBottom: 0, textTransform: "none", letterSpacing: 0.2 }}>
          {c.consilier ? `advisor ${c.consilier} · ` : ""}
          {c.versiune ? <span title={c.versiune}>version {c.versiune.split(" ")[0].replace("cfg:", "cfg ")}</span> : null}
          {offer.model ? ` · p from the ${offer.model.nume === "antrenat" ? "trained" : "sigmoid"} model` : ""}
        </p>
      </details>
    </>
  );
}
