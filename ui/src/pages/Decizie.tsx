import { useEffect, useMemo, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { comandaApprove, getCaz, getDeciziiLocale, getSursa, postDecizie } from "../api/client";
import { useEchipa, useIstoric, useRezultat } from "../api/hooks";
import { BandaBadge, Loading } from "../components/ui";
import { eticheta, pct, ron } from "../format";
import type { Caz, Decizie, DecizieInput } from "../types/api";

const OPTIUNI: { id: Decizie; titlu: string; desc: string }[] = [
  { id: "aproba", titlu: "Aprobă", desc: "Recomandarea agentului se execută așa cum este." },
  { id: "modifica", titlu: "Modifică", desc: "Alegi altă intervenție din meniu. Motivul este obligatoriu și intră în audit." },
  { id: "respinge", titlu: "Respinge", desc: "Nu se face nicio ofertă. Motivul este obligatoriu și intră în audit." },
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
  const [consilier, setConsilier] = useState<string>(existent?.consilier ?? "");
  const [salvat, setSalvat] = useState<string | null>(null);
  const [trimit, setTrimit] = useState(false);
  const echipa = useEchipa();
  const istoric = useIstoric(id);
  const rezultat = useRezultat(id);

  useEffect(() => {
    getCaz(id).then((x) => setC(x ?? null)).catch((e) => setErr(String(e)));
  }, [id]);
  // consilierul alocat cazului (echipa.yaml) e preselectat; ofițerul poate alege altul
  useEffect(() => {
    if (!consilier && c?.consilier) setConsilier(c.consilier);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [c]);

  const input: DecizieInput = useMemo(
    () => ({
      decizie, interventie: decizie === "modifica" ? interventie || undefined : undefined, motiv: motiv.trim() || undefined, consilier: consilier || undefined,
    }),
    [decizie, interventie, motiv, consilier],
  );
  const valid = decizie === "aproba" || (motiv.trim().length > 0 && (decizie !== "modifica" || interventie));

  if (c === undefined) return <Loading err={err} />;
  if (c === null)
    return (
      <div className="notice fail">
        Cazul {id} nu există. <Link to="/cazuri">Înapoi la coadă</Link>
      </div>
    );

  const { case: cs, client, offer, rec } = c;
  const alternative = offer.interventii.filter((i) => i.id !== offer.aleasa);

  const trimite = async () => {
    setTrimit(true);
    try {
      const r = await postDecizie(cs.case_id, input);
      setSalvat(r.sursa === "api" ? "Decizia a fost înregistrată prin API." : "Decizia a fost salvată local (fără API). Rulează comanda de mai jos ca să intre în approvals.json și audit.jsonl.");
      istoric.refetch();
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
          <p style={{ marginTop: 0 }}>
            <span className="tag">{eticheta(rec.recomandare)}</span> <b>{rec.eticheta}</b>
            <br />
            <span className="small muted">{rec.motiv}</span>
          </p>
          {rec.oferta && (
            <p className="small">
              Rată {ron(rec.oferta.rata_veche)} → <b>{ron(rec.oferta.rata_noua)}</b>, cost bancă {ron(rec.oferta.cost_banca)}, economie client{" "}
              {ron(rec.oferta.economie_client)}.
            </p>
          )}
          {existent && (
            <div className="notice warn">
              Există deja o decizie {existent.sursa === "local" ? "locală" : "prin API"} din {new Date(existent.la).toLocaleString("ro-RO")}:{" "}
              <b>{existent.decizie}</b>
              {existent.interventie ? ` → ${eticheta(existent.interventie)}` : ""}. Trimiterea o înlocuiește.
            </div>
          )}

          <h2 style={{ marginTop: 16 }}>Istoricul deciziilor pe acest caz</h2>
          {getSursa() === "static" ? (
            <p className="small muted">Istoricul (approvals.json) vine prin API.</p>
          ) : !istoric.data || istoric.data.length === 0 ? (
            <p className="small muted">Nicio decizie înregistrată încă.</p>
          ) : (
            <div className="istoric">
              {istoric.data.map((d, i) => (
                <div key={i} className="small" style={{ padding: "6px 0", borderTop: i ? "1px solid var(--line, #e5e7eb)" : undefined }}>
                  <b>{d.decizie}</b>
                  {d.override && <span className="tag avertizare">override</span>}
                  {d.interventie_finala && d.interventie_finala !== d.interventie_agent ? ` → ${eticheta(d.interventie_finala)}` : ""}
                  <span className="muted">
                    {" "}· {new Date(d.timestamp).toLocaleString("ro-RO")}
                    {d.consilier ? ` · ${d.consilier}` : ""}
                    {d.versiune ? <span title={d.versiune}> · {d.versiune.split(" ")[0].replace("cfg:", "cfg ")}</span> : ""}
                  </span>
                  {d.motiv && <div className="muted">„{d.motiv}”</div>}
                  <div>
                    {d.rezultat ? (
                      <span className={`tag ${d.rezultat === "ramas" ? "ok" : "fail"}`}>la 90 de zile: {d.rezultat === "ramas" ? "a rămas" : "a plecat"}</span>
                    ) : (
                      i === 0 && (
                        <span className="actions" style={{ gap: 6, marginTop: 4 }}>
                          <span className="muted">Rezultat la 90 de zile:</span>
                          <button type="button" className="btn secondary sm" disabled={rezultat.isPending} onClick={() => rezultat.mutate("ramas")}>
                            a rămas
                          </button>
                          <button type="button" className="btn secondary sm" disabled={rezultat.isPending} onClick={() => rezultat.mutate("plecat")}>
                            a plecat
                          </button>
                        </span>
                      )
                    )}
                  </div>
                </div>
              ))}
              {rezultat.error && <div className="notice fail small">{String(rezultat.error)}</div>}
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
                    {i.eticheta} · cost {ron(i.cost)} · p după {pct(i.p_dupa)}
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

          {echipa.data && echipa.data.length > 0 && (
            <div className="field">
              <span>Consilierul care decide (intră în audit și în raportul de feedback)</span>
              <select value={consilier} onChange={(e) => setConsilier(e.target.value)}>
                <option value="">– nealocat –</option>
                {echipa.data.map((x) => (
                  <option key={x.id} value={x.id}>
                    {x.nume}
                    {x.id === c.consilier ? " (alocat cazului)" : ""}
                  </option>
                ))}
              </select>
            </div>
          )}

          <div className="actions">
            <button type="button" className="btn" disabled={!valid || trimit} onClick={trimite}>
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
              Decizia nu a putut fi trimisă ({err}). Încearcă din nou sau rulează comanda de mai jos.
            </div>
          )}

          <div className="small muted" style={{ marginTop: 12 }}>
            Comanda echivalentă:
          </div>
          <pre className="cmd">{comandaApprove(cs.case_id, input)}</pre>
        </section>
      </div>
    </>
  );
}
