import { Navigate } from "react-router-dom";
import { homeFor, useEu } from "../auth";
import { Login } from "../components/Login";
import { Reveal } from "../components/Reveal";

/** Sign-in page (opened from the menu bar): who are you, then the password. */
export default function SignIn() {
  const { eu } = useEu();
  if (eu) return <Navigate to={homeFor(eu)} replace />;
  return (
    <section className="section signin" aria-labelledby="signin-t">
      <Reveal>
        <div className="label-row">
          <span>[00] Sign in</span>
          <span>/ advisors · administrator</span>
        </div>
        <div className="sec-head">
          <h2 id="signin-t" className="hl">Who are you today?</h2>
          <p>Advisors see only their own queue. The administrator sees everything and tunes the rules engine.</p>
        </div>
      </Reveal>
      <Reveal className="frame" delay={100}>
        <Login />
      </Reveal>
    </section>
  );
}
