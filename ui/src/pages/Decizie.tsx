import { useEffect, useMemo, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { comandaApprove, getCaz, getDeciziiLocale, getSursa, postDecizie } from "../api/client";
import { useEchipa, useIstoric, useRezultat } from "../api/hooks";
import { Stare } from "../components/Stare";
import { useToast } from "../components/Toast";
import { BandaBadge, Loading } from "../components/ui";
import { eticheta, pct, ron } from "../format";
import { propunere } from "../propunere";
import type { Caz, Decizie, DecizieInput } from "../types/api";

const OPTIUNI: { id: Decizie; titlu: string; desc: string }[] = [
  { id: "aproba", titlu: "Aprobă", desc: "se execută recomandarea agentului" },
  { id: "modifica", titlu: "Modifică", desc: "altă intervenție din meniu, cu motiv" },
  { id: "respinge", titlu: "Respinge", desc: "nicio ofertă, cu motiv" },
];

export default function DeciziePage() {
  const { id = "" } = useParams();
  const nav = useNavigate();
  const toast = useToast();
  const [c, setC] = useState<Caz | null | undefined>(undefined);
  const [err, setErr] = useState<string | null>(null);
  const existent = getDeciziiLocale()[id];
  const [decizie, setDecizie] = useState<Decizie>(existent?.decizie ?? "aproba");
  const [interventie, setInterventie] = useState<string>(existent?.interventie ?? "");
  const [motiv, setMotiv] = useState(existent?.motiv ?? "");
  const [consilier, setConsilier] = useState<string>(existent?.consilier ?? "");
  const [trimit, setTrimit] = useState(false);
  const echipa = useEchipa();
  const istoric = useIstoric(id);
  const rezultat = useRezultat(id);

  useEffect(() => {
    getCaz(id).then((x) => setC(x ?? null)).catch((e) => setErr(String(e)));
  }, [id]);
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
        Cazul {id} nu există. <Link to="/cazuri">Înapoi la cazuri</Link>
      </div>
    );

  const { case: cs, client, offer, rec } = c;
  const alternative = offer.interventii.filter((i) => i.id !== offer.aleasa);

  const trimite = async () => {
    setTrimit(true);
    setErr(null);
    try {
      const r = await postDecizie(cs.case_id, input);
      toast(r.sursa === "api" ? `Decizia pentru ${cs.case_id} a fost înregistrată` : `Decizia pentru ${cs.case_id} e salvată local`);
      istoric.refetch();
      nav(`/cazuri/${cs.case_id}`);
    } catch (e) {
      setErr(String(e));
    } finally {
      setTrimit(false);
    }
  };

  return (
    <>
      <div className="actions" style={{ marginBottom: 10 }}>
        <Link to={`/cazuri/${cs.case_id}`}>← Înapoi la caz</Link>
      </div>
      <h1>
        <BandaBadge b={cs.banda} /> {client.nume} <span className="sub">{cs.case_id}</span>
      </h1>

      <div className="grid c2">
        <section className="sec">
          <h2>Agentul propune</h2>
          <p className="lead">
            <Stare r={rec.recomandare} mare lung />
          </p>
          <p style={{ margin: "0 0 8px" }}>{propunere(rec)}</p>
          {rec.oferta?.amanata_buget && <p className="small muted" style={{ margin: 0 }}>Amânată: plafonul lunar de retenție e consumat; aprobarea o face explicit.</p>}
          {existent && (
            <div className="notice warn" style={{ marginTop: 12 }}>
              Decizie existentă din {new Date(existent.la).toLocaleString("ro-RO")}: <b>{existent.decizie}</b>
              {existent.interventie ? ` → ${eticheta(existent.interventie)}` : ""}. Trimiterea o înlocuiește.
            </div>
          )}

          {istoric.data && istoric.data.length > 0 && (
            <>
              <h2 style={{ marginTop: 18 }}>Deciziile anterioare</h2>
              <div className="istoric">
                {istoric.data.map((d, i) => (
                  <div key={i} className="small" style={{ padding: "6px 0" }}>
                    <b>{d.decizie}</b>
                    {d.override && <span className="tag avertizare" style={{ marginLeft: 6 }}>override</span>}
                    {d.interventie_finala && d.interventie_finala !== d.interventie_agent ? ` → ${eticheta(d.interventie_finala)}` : ""}
                    <span className="muted">
                      {" "}· {new Date(d.timestamp).toLocaleDateString("ro-RO")}
                      {d.consilier ? ` · ${d.consilier}` : ""}
                    </span>
                    {d.motiv && <div className="muted">„{d.motiv}”</div>}
                    {d.rezultat ? (
                      <div>
                        <span className={`tag ${d.rezultat === "ramas" ? "ok" : "fail"}`}>la 90 de zile: {d.rezultat === "ramas" ? "a rămas" : "a plecat"}</span>
                      </div>
                    ) : (
                      i === 0 && (
                        <div className="actions" style={{ gap: 6, marginTop: 4 }}>
                          <span className="muted">La 90 de zile clientul:</span>
                          <button type="button" className="btn ghost sm" disabled={rezultat.isPending} onClick={() => rezultat.mutate("ramas")}>
                            a rămas
                          </button>
                          <button type="button" className="btn ghost sm" disabled={rezultat.isPending} onClick={() => rezultat.mutate("plecat")}>
                            a plecat
                          </button>
                        </div>
                      )
                    )}
                  </div>
                ))}
              </div>
            </>
          )}
        </section>

        <section className="sec">
          <h2>Decizia ta</h2>
          {OPTIUNI.map((o) => (
            <label key={o.id} className={`opt ${decizie === o.id ? "on" : ""}`}>
              <input type="radio" name="decizie" checked={decizie === o.id} onChange={() => setDecizie(o.id)} />
              <span>
                <b>{o.titlu}</b> <span className="muted">— {o.desc}</span>
              </span>
            </label>
          ))}

          {decizie === "modifica" && (
            <div className="field">
              <span>Intervenția în loc</span>
              <select value={interventie} onChange={(e) => setInterventie(e.target.value)}>
                <option value="">– alege –</option>
                {alternative.map((i) => (
                  <option key={i.id} value={i.id} disabled={!i.fezabil}>
                    {i.eticheta} · {ron(i.cost)} · plecare după {pct(i.p_dupa, 0)}
                    {!i.fezabil ? " · infezabilă" : ""}
                  </option>
                ))}
              </select>
            </div>
          )}

          <div className="field">
            <span>{decizie === "aproba" ? "Observație (opțional)" : "Motivul (obligatoriu, intră în audit)"}</span>
            {decizie === "aproba" ? (
              <input type="text" value={motiv} onChange={(e) => setMotiv(e.target.value)} />
            ) : (
              <textarea value={motiv} onChange={(e) => setMotiv(e.target.value)} placeholder="de ce te abați de la recomandare" />
            )}
          </div>

          {echipa.data && echipa.data.length > 0 && (
            <div className="field">
              <span>Consilierul care decide</span>
              <select value={consilier} onChange={(e) => setConsilier(e.target.value)}>
                <option value="">– nealocat –</option>
                {echipa.data.map((x) => (
                  <option key={x.id} value={x.id}>
                    {x.nume}
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
              {decizie === "modifica" && !interventie ? "Alege intervenția și " : ""}scrie motivul ca să poți trimite.
            </p>
          )}
          {err && (
            <div className="notice fail" role="alert" style={{ marginTop: 12 }}>
              Decizia nu a putut fi trimisă: {err}
            </div>
          )}
          {getSursa() === "static" && (
            <>
              <p className="small muted" style={{ marginTop: 12, marginBottom: 0 }}>
                Serverul nu răspunde: decizia se ține în browser. Ca să intre în audit, rulează:
              </p>
              <pre className="cmd">{comandaApprove(cs.case_id, input)}</pre>
            </>
          )}
        </section>
      </div>
    </>
  );
}
