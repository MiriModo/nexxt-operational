import { useEffect, useRef, useState, type FormEvent } from "react";
import { useNavigate } from "react-router-dom";
import { getSursa } from "../api/client";
import { useUtilizatori } from "../api/hooks";
import { useEu } from "../auth";
import { Loading } from "../components/ui";

/** „Cine ești?”: numele din echipa.yaml + Administrator, apoi parola. Fără server, orice parolă intră (demo). */
export function Login() {
  const { login } = useEu();
  const nav = useNavigate();
  const utilizatori = useUtilizatori();
  const [ales, setAles] = useState("");
  const [parola, setParola] = useState("");
  const [eroare, setEroare] = useState<string | null>(null);
  const [verific, setVerific] = useState(false);
  const campParola = useRef<HTMLInputElement>(null);
  useEffect(() => {
    if (ales) campParola.current?.focus();
  }, [ales]);

  const trimite = async (e: FormEvent) => {
    e.preventDefault();
    if (!ales) return;
    setVerific(true);
    setEroare(null);
    try {
      const u = await login(ales, parola);
      if (!u) setEroare("Parolă greșită.");
      else nav(u.rol === "admin" ? "/acasa" : "/biroul-meu");
    } catch (err) {
      setEroare(String(err instanceof Error ? err.message : err));
    } finally {
      setVerific(false);
    }
  };

  if (utilizatori.isLoading) return <Loading />;
  const lista = utilizatori.data ?? [];
  return (
    <form className="login panel" onSubmit={trimite} aria-labelledby="cine">
      <h2 id="cine" style={{ fontSize: 17 }}>Cine ești?</h2>
      {lista.map((u) => (
        <label key={u.id} className={`opt ${ales === u.id ? "on" : ""}`}>
          <input type="radio" name="utilizator" checked={ales === u.id} onChange={() => setAles(u.id)} />
          <span>
            <b>{u.nume}</b> <span className="muted">— {u.rol === "admin" ? "administrator" : "consilier"}</span>
          </span>
        </label>
      ))}
      <div className="field" style={{ marginTop: 12 }}>
        <span>Parola</span>
        <input ref={campParola} type="password" value={parola} onChange={(e) => setParola(e.target.value)} autoComplete="current-password" disabled={!ales} />
      </div>
      {getSursa() === "static" && <p className="small muted">Serverul nu răspunde: intri în modul de demonstrație, cu orice parolă.</p>}
      {eroare && (
        <div className="notice fail" role="alert">
          {eroare}
        </div>
      )}
      <button type="submit" className="btn" disabled={!ales || (!parola && getSursa() !== "static") || verific}>
        {verific ? "Se verifică…" : "Intră"}
      </button>
    </form>
  );
}
