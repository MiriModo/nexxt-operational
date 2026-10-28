import { useContext, useFeedback, useMetrici, useModel } from "../api/hooks";
import { STATES } from "../components/State";
import { Figure, Loading } from "../components/ui";
import { int, label, num, pct, ron } from "../format";
import type { Recomandare, Strategie } from "../types/api";

/** Horizontal bars without a library: label, bar, value (chart palette). */
function Bars({ rows, max }: { rows: { k: string; v: number; text: string; kind?: string }[]; max?: number }) {
  const m = max ?? Math.max(1, ...rows.map((r) => r.v));
  return (
    <div className="hbars">
      {rows.map((r) => (
        <div key={r.k} style={{ display: "contents" }}>
          <span>{r.k}</span>
          <span className="b">
            <i className={r.kind} style={{ width: `${(r.v / m) * 100}%` }} />
          </span>
          <span className="v">{r.text}</span>
        </div>
      ))}
    </div>
  );
}

const KIND: Record<Recomandare, string> = { oferta_minima: "ok", oferta_produs: "ok", nu_interveni: "", restructurare: "warn", respins_escaladat: "err", blocat: "mute" };

export default function Reports() {
  const m = useMetrici();
  const ctx = useContext();
  const model = useModel();
  const fb = useFeedback();
  if (!m.data) return <Loading err={m.error ? String(m.error) : null} />;

  const cv = m.data.cifra_vedeta;
  const strategies: [string, Strategie][] = [["the agent", cv.agent], ...Object.entries(cv.uniform).map(([k, v]) => [`${k} pp cut for everyone`, v] as [string, Strategie])];
  const breaches = Object.values(m.data.cerinte_dure).reduce((a, b) => a + b, 0);
  const v = ctx.data?.versiune;
  const b = ctx.data?.buget_portofoliu;
  const met = model.data?.antrenat?.metrici;
  const W = 440, H = 230, L = 36, R = 10, T = 10, B = 26;

  return (
    <>
      <section className="section">
        <div className="label-row">
          <span>Reports</span>
          <span>/ whole portfolio · synthetic data</span>
        </div>
        <div className="sec-head">
          <h2>What the agent is worth.</h2>
          <p>Against “the same discount for everyone”, at the same retention rate. Every figure comes from the run, with its source in the audit log.</p>
        </div>
        <div className="figures">
          <Figure n={int(Math.round(cv.economie_ron))} unit="RON" label={cv.economie_pct != null ? `saved vs. a uniform discount, ${pct(cv.economie_pct, 0)} cheaper at the same retention` : "saved vs. a uniform discount"} />
          <Figure n={pct(m.data.nu_interveni.procent, 0)} label={`cases where we spend nothing (${m.data.nu_interveni.nu_interveni} of ${m.data.nu_interveni.total})`} />
          <Figure n={pct(m.data.interogari_externe.procent, 0)} label={`external queries avoided (${int(m.data.interogari_externe.evitate)} of ${int(m.data.interogari_externe.rulare_tot)})`} />
          <Figure n={breaches} label={breaches === 0 ? "hard-rule breaches: no offers to active risk, outside limits or on blocked cases" : Object.entries(m.data.cerinte_dure).filter(([, n]) => n).map(([k, n]) => `${label(k)}: ${n}`).join(", ")} />
        </div>
      </section>

      <div className="grid c2">
        <section className="win">
          <p className="mono" style={{ marginBottom: 12 }}>[01] Cost of retention · agent vs. uniform cut</p>
          <Bars rows={strategies.map(([k, s]) => ({ k, v: s.cost, text: `${ron(s.cost)} · ${pct(s.rata_ramanere, 0)} stay`, kind: k === "the agent" ? "brand" : "" }))} />
          <p className="meta" style={{ margin: "12px 0 0" }}>{cv.concluzie}</p>
          {b && (
            <>
              <p className="mono" style={{ margin: "20px 0 4px" }}>Monthly retention budget</p>
              <div className="budget" role="img" aria-label={`used ${ron(b.cost_in_buget)} of ${ron(b.plafon_lunar_ron)}`}>
                <i style={{ width: `${Math.min(100, (b.cost_in_buget / b.plafon_lunar_ron) * 100)}%` }} />
              </div>
              <p className="meta" style={{ margin: 0 }}>
                {ron(b.cost_in_buget)} of {ron(b.plafon_lunar_ron)} · {b.in_buget} offers within budget, {b.amanate} deferred
              </p>
            </>
          )}
        </section>

        <section className="win">
          <p className="mono" style={{ marginBottom: 12 }}>[02] What the agent recommended</p>
          <Bars
            rows={Object.entries(m.data.distributie)
              .sort((a, c) => c[1] - a[1])
              .map(([k, n]) => ({ k: STATES[k as Recomandare]?.name ?? label(k), v: n, text: int(n), kind: KIND[k as Recomandare] ?? "" }))}
          />
          <p className="meta" style={{ margin: "12px 0 0" }}>
            On the hand-written benchmark: {m.data.recomandari.corecte} of {m.data.recomandari.total} recommendations as expected.
          </p>
        </section>
      </div>

      <div className="grid c2" style={{ marginTop: 16 }}>
        <section className="win">
          <p className="mono" style={{ marginBottom: 12 }}>[03] How well the model predicts leaving</p>
          {met ? (
            <>
              <p className="small" style={{ marginTop: 0 }}>
                AUC <b>{num(met.auc, 2)}</b> · Brier <b>{num(met.brier, 3)}</b> · {model.data?.antrenat?.n_test} test clients
              </p>
              <svg className="calib" viewBox={`0 0 ${W} ${H}`} role="img" aria-label="Calibration: predicted probability vs. actual leave rate">
                <line className="ax" x1={L} y1={T} x2={L} y2={H - B} />
                <line className="ax" x1={L} y1={H - B} x2={W - R} y2={H - B} />
                <line className="diag" x1={L} y1={H - B} x2={W - R} y2={T} />
                {met.bins.map((bin, i) => {
                  const n = met.bins.length;
                  const bw = (W - L - R) / n;
                  const x0 = L + i * bw;
                  const h = (p: number) => (H - T - B) * p;
                  return (
                    <g key={bin.interval}>
                      <rect className="p" x={x0 + 3} y={H - B - h(bin.p_medie)} width={bw / 2 - 4} height={h(bin.p_medie)}>
                        <title>predicted {pct(bin.p_medie, 0)}</title>
                      </rect>
                      <rect className="r" x={x0 + bw / 2 + 1} y={H - B - h(bin.rata_reala)} width={bw / 2 - 4} height={h(bin.rata_reala)}>
                        <title>actual {pct(bin.rata_reala, 0)}, n={bin.n}</title>
                      </rect>
                      <text x={x0 + bw / 2} y={H - 8} textAnchor="middle">{bin.interval.split("-")[0]}</text>
                    </g>
                  );
                })}
                <text x={L - 4} y={T + 4} textAnchor="end">100%</text>
                <text x={L - 4} y={H - B + 4} textAnchor="end">0</text>
              </svg>
              <p className="meta" style={{ margin: 0 }}>Grey: predicted; blue: how many actually left; dashed: perfect calibration.</p>
            </>
          ) : (
            <p className="meta">The trained model isn't available; the configured formula is in use.</p>
          )}
        </section>

        <section className="win">
          <p className="mono" style={{ marginBottom: 12 }}>[04] Advisors vs. the agent</p>
          {fb.data && fb.data.decizii > 0 ? (
            <>
              <p className="small" style={{ marginTop: 0 }}>
                {fb.data.decizii} decisions, {fb.data.override} changed ({pct(fb.data.rata_override, 0)}), {fb.data.rezultate_90_zile.n} with a 90-day outcome.
              </p>
              {Object.keys(fb.data.pe_interventie).length > 0 && (
                <Bars rows={Object.entries(fb.data.pe_interventie).map(([k, g]) => ({ k: label(k), v: g.rata_override ?? 0, text: `${g.override} of ${g.decizii} changed`, kind: "warn" }))} max={1} />
              )}
              {fb.data.propuneri.length > 0 && (
                <ul className="plain small" style={{ marginTop: 12 }}>
                  {fb.data.propuneri.map((p, i) => (
                    <li key={i}>{p.text}</li>
                  ))}
                </ul>
              )}
            </>
          ) : (
            <p className="meta">No decisions recorded yet. This fills in after the first decisions from a case.</p>
          )}
        </section>
      </div>

      {v && (
        <p className="meta" style={{ marginTop: 20 }} title={v.scurt}>
          Configuration version {v.config.hash.slice(0, 6)} · model {v.model.versiune ?? v.model.model} · code {v.cod ?? "—"}. Every decision carries the version it was made with.
        </p>
      )}
    </>
  );
}
