import { useContext, useFeedback, useMetrici, useModel } from "../api/hooks";
import { STATES } from "../components/State";
import { Loading } from "../components/ui";
import { int, label, num, pct, ron, ronShort } from "../format";
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

/** One KPI card: mono label, big number with a grey unit, one line of context. */
function Stat({ label: l, n, unit, note, tone }: { label: string; n: string | number; unit?: string; note: string; tone?: "good" }) {
  return (
    <div className={`win stat ${tone ?? ""}`}>
      <p className="mono">{l}</p>
      <b>
        {n}
        {unit && <small>{unit}</small>}
      </b>
      <span>{note}</span>
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
  const uniform = Object.entries(cv.uniform).map(([k, v]) => [`${k} pp cut for everyone`, v] as [string, Strategie]);
  const strategies: [string, Strategie][] = [["the agent", cv.agent], ...uniform];
  const comp = cv.comparator ?? cv.uniform_aleasa ?? "0.6";
  const cu = cv.uniform[comp];
  const breaches = Object.values(m.data.cerinte_dure).reduce((a, b) => a + b, 0);
  const v = ctx.data?.versiune;
  const b = ctx.data?.buget_portofoliu;
  const met = model.data?.antrenat?.metrici;
  const saved = ronShort(Math.abs(cv.economie_ron ?? 0));
  const gap = cv.diferenta_retentie_pp ?? (cu ? (cv.agent.rata_ramanere - cu.rata_ramanere) * 100 : 0);
  // the headline never claims "same retention" unless a uniform cut really reaches the agent's rate
  const headline = cv.aceeasi_rata
    ? { label: "Saved at the same retention", note: `vs. ${comp} pp for everyone, ${pct(cu?.rata_ramanere, 0)} kept by both` }
    : cv.domina
      ? { label: `Cheaper than ${comp} pp for everyone`, note: `and keeps ${num(gap, 0)} pp more clients (${pct(cv.agent.rata_ramanere, 0)} vs ${pct(cu?.rata_ramanere, 0)})` }
      : { label: `Extra cost vs. ${comp} pp for everyone`, note: `for ${num(gap, 0)} pp more clients kept (${pct(cv.agent.rata_ramanere, 0)} vs ${pct(cu?.rata_ramanere, 0)})` };
  const W = 440, H = 230, L = 36, R = 10, T = 10, B = 26;

  return (
    <>
      <section className="section reports-head">
        <div className="label-row">
          <span>Reports</span>
          <span>/ whole portfolio · synthetic data</span>
        </div>
        <h1 className="hl">What the agent is worth.</h1>
      </section>

      <div className="stats">
        <Stat label={headline.label} n={saved.n} unit={saved.unit} note={headline.note} tone={cv.aceeasi_rata || cv.domina ? "good" : undefined} />
        <Stat label="No-cost cases" n={pct(m.data.nu_interveni.procent, 0)} note={`${int(m.data.nu_interveni.nu_interveni)} of ${int(m.data.nu_interveni.total)} cases need no offer`} />
        <Stat label="External queries avoided" n={pct(m.data.interogari_externe.procent, 0)} note={`${int(m.data.interogari_externe.evitate)} of ${int(m.data.interogari_externe.rulare_tot)}`} />
        <Stat
          label="Hard-rule breaches"
          n={breaches}
          note={breaches === 0 ? "no offers to active risk, outside limits or on blocked cases" : Object.entries(m.data.cerinte_dure).filter(([, n]) => n).map(([k, n]) => `${label(k)}: ${n}`).join(", ")}
          tone={breaches === 0 ? "good" : undefined}
        />
      </div>

      <div className="report-grid">
        <section className="win accent">
          <p className="mono card-title">[01] Cost of retention · agent vs. uniform cut</p>
          <Bars rows={strategies.map(([k, s]) => ({ k, v: s.cost, text: `${ron(s.cost)} · ${pct(s.rata_ramanere, 0)} stay`, kind: k === "the agent" ? "grad" : "" }))} />
          {cu && (
            <p className="meta card-note">
              The agent keeps {pct(cv.agent.rata_ramanere, 0)} of clients for {ron(cv.agent.cost)}.{" "}
              {cv.aceeasi_rata
                ? `A ${comp} pp cut for everyone keeps the same share for ${ron(cu.cost)}.`
                : `No uniform cut reaches that: the most generous (${comp} pp for everyone) keeps ${pct(cu.rata_ramanere, 0)} for ${ron(cu.cost)}.`}
              {cv.cost_per_client_in_plus != null &&
                ` Against ${cv.uniform_ieftina} pp for everyone, each extra client kept costs ${ron(cv.cost_per_client_in_plus)}.`}
            </p>
          )}
          {b && (
            <div className="budget-block">
              <p className="mono">Monthly retention budget</p>
              <div className="budget" role="img" aria-label={`used ${ron(b.cost_in_buget)} of ${ron(b.plafon_lunar_ron)}`}>
                <i style={{ width: `${Math.min(100, (b.cost_in_buget / b.plafon_lunar_ron) * 100)}%` }} />
              </div>
              <p className="meta">
                {ron(b.cost_in_buget)} of {ron(b.plafon_lunar_ron)} · {b.in_buget} offers within budget, {b.amanate} deferred
              </p>
            </div>
          )}
        </section>

        <section className="win accent">
          <p className="mono card-title">[02] What the agent recommended</p>
          <Bars
            rows={Object.entries(m.data.distributie)
              .sort((a, c) => c[1] - a[1])
              .map(([k, n]) => ({ k: STATES[k as Recomandare]?.name ?? label(k), v: n, text: int(n), kind: KIND[k as Recomandare] ?? "" }))}
          />
          <p className="meta card-note">
            On the hand-written benchmark: {m.data.recomandari.corecte} of {m.data.recomandari.total} recommendations as expected.
          </p>
        </section>

        <section className="win accent">
          <p className="mono card-title">[03] How well the model predicts leaving</p>
          {met ? (
            <>
              <p className="small" style={{ margin: "0 0 8px" }}>
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
              <p className="meta card-note">
                <span className="key p" /> predicted <span className="key r" /> actually left · dashed: perfect calibration
              </p>
            </>
          ) : (
            <p className="meta">The trained model isn't available; the configured formula is in use.</p>
          )}
        </section>

        <section className="win accent">
          <p className="mono card-title">[04] Advisors vs. the agent</p>
          {fb.data && fb.data.decizii > 0 ? (
            <>
              <div className="mini-stats">
                <div>
                  <b>{fb.data.decizii}</b>
                  <span>decisions</span>
                </div>
                <div>
                  <b>{pct(fb.data.rata_override, 0)}</b>
                  <span>changed by the advisor</span>
                </div>
                <div>
                  <b>{fb.data.rezultate_90_zile.n}</b>
                  <span>with a 90-day outcome</span>
                </div>
              </div>
              {Object.keys(fb.data.pe_interventie).length > 0 && (
                <>
                  <p className="mono" style={{ margin: "18px 0 10px" }}>Changed, by intervention</p>
                  <Bars rows={Object.entries(fb.data.pe_interventie).map(([k, g]) => ({ k: label(k), v: g.rata_override ?? 0, text: `${g.override} of ${g.decizii}`, kind: "warn" }))} max={1} />
                </>
              )}
            </>
          ) : (
            <p className="meta">No decisions recorded yet. This fills in after the first decisions from a case.</p>
          )}
        </section>
      </div>

      {v && (
        <p className="meta" style={{ marginTop: 24 }} title={v.scurt}>
          Configuration {v.config.hash.slice(0, 6)} · model {v.model.versiune ?? v.model.model} · code {v.cod ?? "n/a"} · every decision carries the version it was made with.
        </p>
      )}
    </>
  );
}
