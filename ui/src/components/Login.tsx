import { useEffect, useRef, useState, type FormEvent } from "react";
import { useNavigate } from "react-router-dom";
import { getSursa } from "../api/client";
import { useUtilizatori } from "../api/hooks";
import { useEu } from "../auth";
import { Loading } from "../components/ui";

/** "Who are you?": the advisors from echipa.yaml plus Administrator, then the password.
 *  Without the server, any password signs you in (demo mode). */
export function Login() {
  const { login } = useEu();
  const nav = useNavigate();
  const users = useUtilizatori();
  const [picked, setPicked] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const pwd = useRef<HTMLInputElement>(null);
  useEffect(() => {
    if (picked) pwd.current?.focus();
  }, [picked]);

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    if (!picked) return;
    setBusy(true);
    setError(null);
    try {
      const u = await login(picked, password);
      if (!u) setError("Wrong password.");
      else nav(u.rol === "admin" ? "/overview" : "/desk");
    } catch (err) {
      setError(String(err instanceof Error ? err.message : err));
    } finally {
      setBusy(false);
    }
  };

  if (users.isLoading) return <Loading />;
  const list = users.data ?? [];
  const offline = getSursa() === "static";
  return (
    <form className="login win" onSubmit={submit} aria-labelledby="who">
      <h2 id="who">Who are you?</h2>
      {list.map((u) => (
        <label key={u.id} className={`opt ${picked === u.id ? "on" : ""}`}>
          <input type="radio" name="user" checked={picked === u.id} onChange={() => setPicked(u.id)} />
          <span>
            <b>{u.nume}</b> <span className="muted">— {u.rol === "admin" ? "administrator" : "advisor"}</span>
          </span>
        </label>
      ))}
      <div className="field" style={{ marginTop: 14 }}>
        <span>Password</span>
        <input ref={pwd} type="password" value={password} onChange={(e) => setPassword(e.target.value)} autoComplete="current-password" disabled={!picked} />
      </div>
      {offline && <p className="meta">The server isn't responding: you'll enter demo mode, any password works.</p>}
      {error && (
        <div className="notice fail" role="alert">
          {error}
        </div>
      )}
      <button type="submit" className="btn primary" disabled={!picked || (!password && !offline) || busy}>
        {busy ? "Checking…" : "Sign in"} <span className="arrow">→</span>
      </button>
    </form>
  );
}
