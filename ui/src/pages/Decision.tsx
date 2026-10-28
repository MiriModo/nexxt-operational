import { useEffect, useMemo, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { comandaApprove, getCaz, getDeciziiLocale, getSursa, postDecizie } from "../api/client";
import { useEchipa, useIstoric, useRezultat } from "../api/hooks";
import { useEu } from "../auth";
import { State, decisionName } from "../components/State";
import { useToast } from "../components/Toast";
import { Band, Loading } from "../components/ui";
import { date, label, pct, ron } from "../format";
import { proposal } from "../proposal";
import type { Caz, Decizie, DecizieInput } from "../types/api";

const OPTIONS: { id: Decizie; title: string; desc: string }[] = [
  { id: "aproba", title: "Approve", desc: "the agent's recommendation goes ahead" },
  { id: "modifica", title: "Change", desc: "another intervention from the menu, with a reason" },
  { id: "respinge", title: "Reject", desc: "no offer, with a reason" },
];

export default function Decision() {
  const { id = "" } = useParams();
  const nav = useNavigate();
  const toast = useToast();
  const [c, setC] = useState<Caz | null | undefined>(undefined);
  const [err, setErr] = useState<string | null>(null);
  const existing = getDeciziiLocale()[id];
  const [decision, setDecision] = useState<Decizie>(existing?.decizie ?? "aproba");
  const [intervention, setIntervention] = useState<string>(existing?.interventie ?? "");
  const [reason, setReason] = useState(existing?.motiv ?? "");
  const [advisor, setAdvisor] = useState<string>(existing?.consilier ?? "");
  const [busy, setBusy] = useState(false);
  const { eu } = useEu();
  const team = useEchipa();
  const history = useIstoric(id);
  const outcome = useRezultat(id);

  useEffect(() => {
    getCaz(id).then((x) => setC(x ?? null)).catch((e) => setErr(String(e)));
  }, [id]);
  useEffect(() => {
    if (!advisor && c?.consilier) setAdvisor(c.consilier);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [c]);

  const input: DecizieInput = useMemo(
    () => ({ decizie: decision, interventie: decision === "modifica" ? intervention || undefined : undefined, motiv: reason.trim() || undefined, consilier: advisor || undefined }),
    [decision, intervention, reason, advisor],
  );
  const valid = decision === "aproba" || (reason.trim().length > 0 && (decision !== "modifica" || intervention));

  if (c === undefined) return <Loading err={err} />;
  if (c === null)
    return (
      <div className="notice fail">
        Case {id} doesn't exist. <Link to="/queue">Back to the queue</Link>
      </div>
    );

  const { case: cs, client, offer, rec } = c;
  const alternatives = offer.interventii.filter((i) => i.id !== offer.aleasa);

  const send = async () => {
    setBusy(true);
    setErr(null);
    try {
      const r = await postDecizie(cs.case_id, input);
      toast(r.sursa === "api" ? `Decision for ${cs.case_id} recorded` : `Decision for ${cs.case_id} saved locally`);
      history.refetch();
      nav(`/queue/${cs.case_id}`);
    } catch (e) {
      setErr(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  };

  return (
    <>
      <div className="label-row" style={{ marginBottom: 18 }}>
        <Link to={`/queue/${cs.case_id}`}>← Back to the case</Link>
        <span>decision · {cs.case_id}</span>
      </div>
      <h1 style={{ marginBottom: 22, display: "flex", gap: 12, alignItems: "center" }}>
        <Band b={cs.banda} /> {client.nume}
      </h1>

      <div className="grid c2">
        <section className="sec">
          <div className="sec-label">
            <span>[01] The agent proposes</span>
          </div>
          <p style={{ marginBottom: 10 }}>
            <State r={rec.recomandare} lg long />
          </p>
          <p className="lead" style={{ color: "var(--foreground)", fontSize: 15.5 }}>{proposal(rec)}</p>
          {rec.oferta?.amanata_buget && <p className="meta">Deferred: this month's retention cap is used up; approving it does so explicitly.</p>}
          {existing && (
            <div className="notice warn" style={{ marginTop: 12 }}>
              Existing decision from {date(existing.la)}: <b>{decisionName(existing.decizie)}</b>
              {existing.interventie ? ` → ${label(existing.interventie)}` : ""}. Sending replaces it.
            </div>
          )}

          {history.data && history.data.length > 0 && (
            <>
              <div className="sec-label" style={{ marginTop: 22 }}>
                <span>[02] Earlier decisions</span>
              </div>
              <div className="history">
                {history.data.map((d, i) => (
                  <div key={i}>
                    <b>{decisionName(d.decizie)}</b>
                    {d.override && <span className="tag warn" style={{ marginLeft: 6 }}>changed</span>}
                    {d.interventie_finala && d.interventie_finala !== d.interventie_agent ? ` → ${label(d.interventie_finala)}` : ""}
                    <span className="muted">
                      {" "}· {date(d.timestamp)}
                      {d.consilier ? ` · ${d.consilier}` : ""}
                    </span>
                    {d.motiv && <div className="muted">“{d.motiv}”</div>}
                    {d.rezultat ? (
                      <div>
                        <span className={`tag ${d.rezultat === "ramas" ? "ok" : "bad"}`}>at 90 days: {d.rezultat === "ramas" ? "stayed" : "left"}</span>
                      </div>
                    ) : (
                      i === 0 && (
                        <div className="actions" style={{ gap: 8, marginTop: 6 }}>
                          <span className="muted">At 90 days the client:</span>
                          <button type="button" className="btn secondary sm" disabled={outcome.isPending} onClick={() => outcome.mutate("ramas")}>
                            stayed
                          </button>
                          <button type="button" className="btn secondary sm" disabled={outcome.isPending} onClick={() => outcome.mutate("plecat")}>
                            left
                          </button>
                        </div>
                      )
                    )}
                  </div>
                ))}
              </div>
            </>
          )}
        </section>

        <section className="sec">
          <div className="sec-label">
            <span>[03] Your decision</span>
          </div>
          {OPTIONS.map((o) => (
            <label key={o.id} className={`opt ${decision === o.id ? "on" : ""}`}>
              <input type="radio" name="decision" checked={decision === o.id} onChange={() => setDecision(o.id)} />
              <span>
                <b>{o.title}</b> <span className="muted">— {o.desc}</span>
              </span>
            </label>
          ))}

          {decision === "modifica" && (
            <div className="field">
              <span>Intervention instead</span>
              <select value={intervention} onChange={(e) => setIntervention(e.target.value)} style={{ width: "100%" }}>
                <option value="">– choose –</option>
                {alternatives.map((i) => (
                  <option key={i.id} value={i.id} disabled={!i.fezabil}>
                    {i.eticheta} · {ron(i.cost)} · p after {pct(i.p_dupa, 0)}
                    {!i.fezabil ? " · infeasible" : ""}
                  </option>
                ))}
              </select>
            </div>
          )}

          <div className="field">
            <span>{decision === "aproba" ? "Note (optional)" : "Reason (required, goes to the audit log)"}</span>
            {decision === "aproba" ? (
              <input type="text" value={reason} onChange={(e) => setReason(e.target.value)} />
            ) : (
              <textarea value={reason} onChange={(e) => setReason(e.target.value)} placeholder="why you're departing from the recommendation" />
            )}
          </div>

          {eu?.rol !== "admin" && <p className="meta">You decide as {eu?.nume}; the audit log carries your name.</p>}
          {eu?.rol === "admin" && team.data && team.data.length > 0 && (
            <div className="field">
              <span>Deciding on behalf of</span>
              <select value={advisor} onChange={(e) => setAdvisor(e.target.value)} style={{ width: "100%" }}>
                <option value="">– unassigned –</option>
                {team.data.map((x) => (
                  <option key={x.id} value={x.id}>
                    {x.nume}
                  </option>
                ))}
              </select>
            </div>
          )}

          <div className="actions">
            <button type="button" className="btn primary" disabled={!valid || busy} onClick={send}>
              {busy ? "Sending…" : "Send the decision"} <span className="arrow">→</span>
            </button>
            <button type="button" className="btn ghost" onClick={() => nav(`/queue/${cs.case_id}`)}>
              Cancel
            </button>
          </div>
          {!valid && (
            <p className="meta" style={{ margin: "10px 0 0" }}>
              {decision === "modifica" && !intervention ? "Pick the intervention and " : ""}write the reason to send.
            </p>
          )}
          {err && (
            <div className="notice fail" role="alert" style={{ marginTop: 12 }}>
              The decision couldn't be sent: {err}
            </div>
          )}
          {getSursa() === "static" && (
            <>
              <p className="meta" style={{ marginTop: 12, marginBottom: 0 }}>The server isn't responding: the decision stays in this browser. To put it in the audit log, run:</p>
              <pre className="cmd">{comandaApprove(cs.case_id, input)}</pre>
            </>
          )}
        </section>
      </div>
    </>
  );
}
