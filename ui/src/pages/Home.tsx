import { useEffect } from "react";
import { Navigate, useLocation } from "react-router-dom";
import { homeFor, useEu } from "../auth";
import { Login } from "../components/Login";

const STEPS = [
  { n: "01", t: "Scan the portfolio", d: "Departure and risk signals from transactions, requests and external sources — every client, every morning." },
  { n: "02", t: "Build the queue", d: "One prioritised list: leaving × value × what can still be done. Risk runs on its own lane." },
  { n: "03", t: "Verify only what matters", d: "Checks chosen by products and reason, in stages, stopping at the first failure — with the evidence." },
  { n: "04", t: "Propose the cheapest keep", d: "The least the bank can do that keeps the client, within BNR limits and internal caps. You decide." },
];

/** Public landing (guide C1–C2): hero on a dot grid, welcome, how it works, sign in. */
export default function Home() {
  const { eu } = useEu();
  const loc = useLocation();
  useEffect(() => {
    if (loc.hash) document.querySelector(loc.hash)?.scrollIntoView({ behavior: "smooth", block: "start" });
  }, [loc.hash]);
  if (eu) return <Navigate to={homeFor(eu)} replace />;

  return (
    <>
      <section className="hero section" aria-labelledby="title">
        <div className="dots" aria-hidden="true" />
        <h1 id="title">Find the case. Keep the client.</h1>
        <p>
          Keeper finds the clients in your portfolio who need attention today, runs the checks you would run, and proposes
          the cheapest offer that keeps them. You decide.
        </p>
        <div className="actions">
          <a href="#signin" className="btn primary lg">
            Open the queue <span className="arrow">→</span>
          </a>
          <a href="#how" className="btn secondary lg">
            See how it works
          </a>
        </div>
        <p className="proof">
          Built for the retail credit advisor: one queue, one proposal per case, every number with its source.<sup>[1]</sup>
        </p>
      </section>

      <section className="section" id="welcome" aria-labelledby="welcome-t">
        <div className="label-row">
          <span>[01] Welcome</span>
          <span>/ for advisors</span>
        </div>
        <div className="sec-head">
          <h2 id="welcome-t">Your morning queue, already triaged.</h2>
          <p>
            Sign in and you get your own desk: who needs you today, what the agent proposes and why, what is still to confirm.
            Nothing is sent to a client until you approve it.
          </p>
        </div>
      </section>

      <section className="section" id="how" aria-labelledby="how-t">
        <div className="label-row">
          <span>[02] How it works</span>
          <span>/ scan → queue → verify → offer</span>
        </div>
        <div className="sec-head">
          <h2 id="how-t">Four steps, every day, before you arrive.</h2>
          <p>Each step leaves a trace: the signal, the check, the menu it chose from. The advisor sees the result and the reason.</p>
        </div>
        <div className="frame">
          <div className="stepper" aria-hidden="true">
            <span className="on">Scan</span> <span className="sep">→</span> <span>Queue</span> <span className="sep">→</span> <span>Verify</span>{" "}
            <span className="sep">→</span> <span>Offer</span>
          </div>
          <div className="steps">
            {STEPS.map((s) => (
              <div key={s.n} className="win">
                <span className="num">{s.n}</span>
                <h3>{s.t}</h3>
                <p>{s.d}</p>
              </div>
            ))}
          </div>
        </div>
      </section>

      <section className="section" id="signin" aria-labelledby="signin-t" style={{ scrollMarginTop: 80 }}>
        <div className="label-row">
          <span>[03] Sign in</span>
          <span>/ advisors · administrator</span>
        </div>
        <div className="sec-head">
          <h2 id="signin-t">Who are you today?</h2>
          <p>Advisors see only their own queue. The administrator sees everything and tunes the rules engine.</p>
        </div>
        <div className="frame">
          <Login />
        </div>
      </section>
    </>
  );
}
