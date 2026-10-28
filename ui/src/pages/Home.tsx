import { useEffect } from "react";
import { Link, Navigate, useLocation } from "react-router-dom";
import { homeFor, useEu } from "../auth";
import { Mockup } from "../components/Mockup";
import { Reveal } from "../components/Reveal";

const STEPS = [
  { n: "01", t: "Scan the portfolio", d: "Departure and risk signals from transactions, requests and external sources, every client, every morning." },
  { n: "02", t: "Build the queue", d: "One prioritised list: leaving × value × what can still be done. Risk runs on its own lane." },
  { n: "03", t: "Verify only what matters", d: "Checks chosen by products and reason, in stages, stopping at the first failure, with the evidence." },
  { n: "04", t: "Propose the cheapest keep", d: "The least the bank can do that keeps the client, within BNR limits and internal caps. You decide." },
];

/** Public landing (guide C1–C3): hero on a dot grid with the product mockup in the gradient frame, welcome,
 *  how it works, sign in. Sections reveal on scroll; the hero plays once on load. */
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
        <div className="glow" aria-hidden="true" />
        <svg className="orbit" viewBox="0 0 400 400" aria-hidden="true">
          <circle cx="200" cy="200" r="180" fill="none" stroke="#2867e4" strokeWidth="1" strokeDasharray="3 9" opacity="0.5" />
          <circle cx="200" cy="200" r="120" fill="none" stroke="#d5d5da" strokeWidth="1" strokeDasharray="2 8" />
          <circle cx="380" cy="200" r="5" fill="#2867e4" />
        </svg>
        <p className="mono hero-kicker rise" style={{ animationDelay: "0ms" }}>[00] Keeper · for retail credit advisors</p>
        <h1 id="title" className="rise hl" style={{ animationDelay: "80ms" }}>Find the case. Keep the client.</h1>
        <p className="rise" style={{ animationDelay: "160ms" }}>
          Keeper finds the clients in your portfolio who need attention today, runs the checks you would run, and proposes
          the cheapest offer that keeps them. You decide.
        </p>
        <div className="actions rise" style={{ animationDelay: "240ms" }}>
          <Link to="/signin" className="btn primary lg">
            Open the queue <span className="arrow">→</span>
          </Link>
          <a href="#how" className="btn secondary lg">
            See how it works
          </a>
        </div>
        <div className="rise" style={{ animationDelay: "340ms" }}>
          <Mockup />
        </div>
      </section>

      <section className="section" id="welcome" aria-labelledby="welcome-t">
        <Reveal>
          <div className="label-row">
            <span>[01] Welcome</span>
            <span>/ for advisors</span>
          </div>
          <div className="sec-head">
            <h2 id="welcome-t" className="hl">Your morning queue, already triaged.</h2>
            <p>
              Sign in and you get your own desk: who needs you today, what the agent proposes and why, what is still to confirm.
              Nothing is sent to a client until you approve it.
            </p>
          </div>
        </Reveal>
      </section>

      <section className="section" id="how" aria-labelledby="how-t">
        <Reveal>
          <div className="label-row">
            <span>[02] How it works</span>
            <span>/ scan → queue → verify → offer</span>
          </div>
          <div className="sec-head">
            <h2 id="how-t" className="hl">Four steps, every day, before you arrive.</h2>
            <p>Each step leaves a trace: the signal, the check, the menu it chose from. The advisor sees the result and the reason.</p>
          </div>
        </Reveal>
        <Reveal className="frame">
          <div className="stepper" aria-hidden="true">
            <span className="on">Scan</span> <span className="sep">→</span> <span>Queue</span> <span className="sep">→</span> <span>Verify</span>{" "}
            <span className="sep">→</span> <span>Offer</span>
          </div>
          <div className="steps">
            {STEPS.map((s, i) => (
              <Reveal key={s.n} className="win float" delay={120 + i * 90}>
                <span className="num">{s.n}</span>
                <h3>{s.t}</h3>
                <p>{s.d}</p>
              </Reveal>
            ))}
          </div>
        </Reveal>
      </section>

    </>
  );
}
