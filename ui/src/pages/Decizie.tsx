import { useEffect, useMemo, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { getCaz, getDeciziiLocale, postDecizie, postPropunere } from "../api/client";
import { BandaBadge, Loading } from "../components/ui";
import { eticheta, ron } from "../format";
import type { Caz, Decizie, DecizieInput, PropunereLLM } from "../types/api";

const OPTIUNI: { id: Decizie; titlu: string; desc: string }[] = [
  { id: "aproba", titlu: "Aprobă", desc: "Confirmi oferta recomandată." },
  { id: "modifica", titlu: "Modifică", desc: "Alegi o altă ofertă și explici motivul." },
  { id: "respinge", titlu: "Respinge", desc: "Nu faci o ofertă și explici motivul." },
];

export default function DeciziePage() {
  const { id = "" } = useParams();
  const nav = useNavigate();
  const [c, setC] = useState<Caz | null | undefined>(undefined);
  const [err, setErr] = useState<string | null>(null);
  const existent = getDeciziiLocale()[id];
  const [decizie, setDecizie] = useState<Decizie>(existent?.decizie ?? "aproba");
  const [interventie, setInterventie] = useState<string>(existent?.interventie ?? "");
  const [motiv, setMotiv] = useState(existent?.motiv ?? "");
  const [salvat, setSalvat] = useState<string | null>(null);
  const [trimit, setTrimit] = useState(false);
  const [propunere, setPropunere] = useState<PropunereLLM | null>(null);
  const [generare, setGenerare] = useState(false);
  const [eroareLLM, setEroareLLM] = useState<string | null>(null);
  const [incercare, setIncercare] = useState(0);

  useEffect(() => {
    let activ = true;
    const previous = getDeciziiLocale()[id];
    setC(undefined); setErr(null); setSalvat(null);
    setDecizie(previous?.decizie ?? "aproba");
    setInterventie(previous?.interventie ?? ""); setMotiv(previous?.motiv ?? "");
    getCaz(id).then(x => { if (activ) setC(x ?? null); })
      .catch(e => { if (activ) setErr(String(e)); });
    return () => { activ = false; };
  }, [id]);

  useEffect(() => {
    let activ = true;
    setPropunere(null); setEroareLLM(null);
    if (!c || c.case.case_id !== id) { setGenerare(false); return; }
    setGenerare(true);
    postPropunere(id).then(x => { if (activ) setPropunere(x); })
      .catch(e => { if (activ) setEroareLLM(e instanceof Error ? e.message : String(e)); })
      .finally(() => { if (activ) setGenerare(false); });
    return () => { activ = false; };
  }, [id, c, incercare]);

  const recomandata = propunere?.interventie ?? c?.rec.interventie;
  const input: DecizieInput = useMemo(() => {
    const finala = decizie === "modifica" ? interventie : recomandata;
    const faraOfertaAI = !!propunere && propunere.interventie === null && !!c?.rec.oferta;
    const overrideAI = decizie === "aproba" && finala !== c?.rec.interventie;
    return {
      decizie: decizie === "aproba" && faraOfertaAI ? "respinge" : overrideAI ? "modifica" : decizie,
      interventie: decizie === "modifica" || overrideAI ? finala || undefined : undefined,
      motiv: motiv.trim() || (overrideAI || (decizie === "aproba" && faraOfertaAI) ? propunere?.motiv : undefined),
      propunere_id: propunere?.interventie && decizie !== "respinge" && finala === propunere.interventie ? propunere.id : undefined,
    };
  }, [decizie, interventie, motiv, propunere, c, recomandata]);
  const valid = decizie === "aproba" || (motiv.trim().length > 0 && (decizie !== "modifica" || interventie));

  if (c === undefined) return <Loading err={err} />;
  if (c === null)
    return (
      <div className="notice fail">
        Cazul {id} nu există. <Link to="/cazuri">Înapoi la coadă</Link>
      </div>
    );

  const { case: cs, client, offer, rec } = c;
  const alternative = offer.interventii.filter((i) => i.id !== recomandata);

  const trimite = async () => {
    setTrimit(true); setErr(null);
    try {
      const r = await postDecizie(cs.case_id, input);
      setSalvat(r.sursa === "api" ? "Decizia a fost înregistrată." : "Decizia este salvată doar în acest browser. Serverul nu a putut fi contactat.");
    } catch (e) {
      setErr(String(e));
    } finally {
      setTrimit(false);
    }
  };

  return (
    <>
      <div className="actions" style={{ marginBottom: 12 }}>
        <Link to={`/cazuri/${cs.case_id}`}>← Înapoi la caz</Link>
      </div>
      <h1>
        <BandaBadge b={cs.banda} /> Decizie pentru {cs.case_id} · {client.nume}
      </h1>

      <div className="grid c2">
        <section className="panel">
          <h2>Recomandarea agentului</h2>
          <div aria-live="polite" aria-busy={generare}>
            {generare && <p className="small muted" role="status">Se pregătește recomandarea…</p>}
            {eroareLLM && <div className="notice warn" role="alert">
              <p>Recomandarea AI nu este disponibilă. Poți folosi recomandarea existentă.</p>
              <button type="button" className="btn ghost" disabled={trimit} onClick={() => setIncercare(x => x + 1)}>Încearcă din nou</button>
              <details className="small"><summary>Detalii eroare</summary><p>{eroareLLM}</p></details>
            </div>}
            <h3>{propunere?.titlu ?? rec.eticheta}</h3>
            <p>{propunere?.motiv ?? rec.motiv}</p>
            {propunere && <>
              <div style={{ borderLeft: "3px solid var(--border, #ddd)", paddingLeft: 16, marginTop: 20 }}>
                <span className="small muted">Mesaj pentru client · propunere</span>
                <p style={{ whiteSpace: "pre-wrap", marginBottom: 0 }}>{propunere.mesaj_client}</p>
              </div>
              {propunere.atentionari.map((x, i) => <p className="notice warn small" key={i}>{x}</p>)}
            </>}
            {(propunere ? propunere.interventie : rec.oferta) && <p className="small muted" style={{ marginTop: 20 }}>
              {propunere?.interventie && <><b>{eticheta(propunere.interventie)}</b> · </>}
              {(!propunere?.interventie || propunere.interventie === rec.interventie) && rec.oferta
                ? <>Rată {ron(rec.oferta.rata_veche)} → <b>{ron(rec.oferta.rata_noua)}</b> · Economie client {ron(rec.oferta.economie_client)} · Cost bancă {ron(rec.oferta.cost_banca)}</>
                : <>Cost bancă {ron(offer.interventii.find(i => i.id === propunere?.interventie)?.cost ?? 0)}</>}
            </p>}
          </div>
          {existent && (
            <div className="notice warn">
              Există deja o decizie {existent.sursa === "local" ? "locală" : "prin API"} din {new Date(existent.la).toLocaleString("ro-RO")}:{" "}
              <b>{existent.decizie}</b>
              {existent.interventie ? ` → ${eticheta(existent.interventie)}` : ""}. Trimiterea o înlocuiește.
            </div>
          )}
        </section>

        <section className="panel">
          <h2>Decizia ofițerului</h2>
          {OPTIUNI.map((o) => (
            <label key={o.id} className={`opt ${decizie === o.id ? "on" : ""}`}>
              <input type="radio" name="decizie" checked={decizie === o.id} onChange={() => setDecizie(o.id)} />
              <span>
                <b>{o.titlu}</b>
                <br />
                <span className="small muted">{o.desc}</span>
              </span>
            </label>
          ))}

          {decizie === "modifica" && (
            <div className="field">
              <span>Intervenția aleasă în loc</span>
              <select value={interventie} onChange={(e) => setInterventie(e.target.value)}>
                <option value="">– alege –</option>
                {alternative.map((i) => (
                  <option key={i.id} value={i.id} disabled={!i.fezabil}>
                    {i.eticheta} · cost {ron(i.cost)}
                    {!i.fezabil ? ` · infezabil: ${i.motiv_infezabil ?? ""}` : ""}
                  </option>
                ))}
              </select>
            </div>
          )}

          {decizie !== "aproba" && (
            <div className="field">
              <span>Motiv (obligatoriu, intră în audit)</span>
              <textarea value={motiv} onChange={(e) => setMotiv(e.target.value)} placeholder="de ce te abați de la recomandare" />
            </div>
          )}
          {decizie === "aproba" && (
            <div className="field">
              <span>Observație (opțional)</span>
              <input type="text" value={motiv} onChange={(e) => setMotiv(e.target.value)} />
            </div>
          )}

          <div className="actions">
            <button type="button" className="btn" disabled={!valid || trimit || generare} onClick={trimite}>
              {trimit ? "Se trimite…" : "Trimite decizia"}
            </button>
            <button type="button" className="btn ghost" onClick={() => nav(`/cazuri/${cs.case_id}`)}>
              Renunță
            </button>
          </div>
          {!valid && (
            <p className="small muted" style={{ margin: "8px 0 0" }}>
              {decizie === "modifica" && !interventie ? "Alege intervenția înlocuitoare și " : ""}
              scrie motivul ca să poți trimite.
            </p>
          )}

          {salvat && (
            <div className="notice ok" role="status" style={{ marginTop: 12 }}>
              {salvat}
            </div>
          )}
          {err && (
            <div className="notice fail" role="alert" style={{ marginTop: 12 }}>
              Decizia nu a putut fi trimisă ({err}). Încearcă din nou.
            </div>
          )}

        </section>
      </div>
    </>
  );
}
