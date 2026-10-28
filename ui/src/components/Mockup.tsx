/** The product mockup under the hero (guide A3 / C3): a white app window in the blue–peach gradient frame:
 *  scan pill, stepper, a slice of the queue, and, floating beside it, the case card with the p gauge, the score
 *  and the checks (verified / check / not allowed). Static and illustrative; the real screens are behind sign-in. */
export function Mockup() {
  const R = 46, C = 2 * Math.PI * R;
  const before = 0.62, after = 0.18;
  return (
    <div className="mock frame grad" aria-hidden="true">
      <div className="mock-win win">
        <div className="mock-top">
          <span className="mock-dots">
            <i />
            <i />
            <i />
          </span>
          <span className="tag new">Portfolio scan 36 / 40 · P1</span>
          <span className="mock-stepper">
            <b>Scan</b> → Queue → Verify → Offer
          </span>
        </div>
        <div className="mock-list">
          <div className="mock-row">
            <span className="tag p1">P1</span>
            <span className="mock-name">Elena Dumitru</span>
            <span className="mock-sig">fixed rate ends in 5 days · payoff statement requested</span>
            <span className="badge keep">Keep</span>
          </div>
          <div className="mock-row">
            <span className="tag p1">P1</span>
            <span className="mock-name">Alina Ene</span>
            <span className="mock-sig">35 days late · DTI 74 %</span>
            <span className="badge watch">Restructure</span>
          </div>
          <div className="mock-row">
            <span className="tag p2">P2</span>
            <span className="mock-name">Radu Barbu</span>
            <span className="mock-sig">salary moved to another bank</span>
            <span className="badge keep">Keep + product</span>
          </div>
          <div className="mock-row dim">
            <span className="tag p3">P3</span>
            <span className="mock-name">Mihai Sandu</span>
            <span className="mock-sig">simulation in the app</span>
            <span className="badge neutral">No action</span>
          </div>
          <div className="mock-row dim">
            <span className="tag p3">P3</span>
            <span className="mock-name">Ioana Stan</span>
            <span className="mock-sig">income down to 64 %</span>
            <span className="badge esc">Escalate</span>
          </div>
        </div>
      </div>
      <div className="mock-card win">
        <div className="mock-card-top">
          <span className="mono">Case Q2263</span>
          <span className="badge keep">Keep · fixed 3 years</span>
        </div>
        <div className="mock-gauge">
          <svg viewBox="0 0 120 120" width="112" height="112">
            <circle cx="60" cy="60" r={R} fill="none" stroke="#e7e7ea" strokeWidth="9" />
            <circle cx="60" cy="60" r={R} fill="none" stroke="#d9d9dd" strokeWidth="9" strokeDasharray={`${C * before} ${C}`} strokeLinecap="round" transform="rotate(-90 60 60)" />
            <circle className="mock-arc" cx="60" cy="60" r={R} fill="none" stroke="#2867e4" strokeWidth="9" strokeDasharray={`${C * after} ${C}`} strokeLinecap="round" transform="rotate(-90 60 60)" />
            <text x="60" y="58" textAnchor="middle" className="mock-big">18 %</text>
            <text x="60" y="74" textAnchor="middle" className="mock-small">was 62 %</text>
          </svg>
          <div className="mock-score">
            <span className="mono">chance of leaving, after</span>
            <b>4,117 → 3,058</b>
            <span>RON / month · bank cost 63,879 RON</span>
          </div>
        </div>
        <div className="checks">
          <div className="check">
            <i className="ok">✓</i>
            <span>income (ANAF)</span>
            <span className="ev">verified</span>
          </div>
          <div className="check">
            <i className="ok">✓</i>
            <span>credit bureau</span>
            <span className="ev">verified</span>
          </div>
          <div className="check wa">
            <i className="wa">!</i>
            <span>proof of income</span>
            <span className="ev">check · older than 90 days</span>
          </div>
          <div className="check no">
            <i className="no">×</i>
            <span>margin cut 0.6 pp</span>
            <span className="ev">not allowed · over tier cap</span>
          </div>
        </div>
      </div>
    </div>
  );
}
