import { useEffect, useState } from "react";
import { getSursa } from "../api/client";
import { useConfigDiff, useConfigFisier, useConfigLista, useContext, useRescan, useSalveazaConfig } from "../api/hooks";
import { Loading } from "../components/ui";

const DESCRIERI: Record<string, string> = {
  priority: "ponderi, benzi, SLA, buget de retenție pe nivel, rutare",
  retention: "p țintă, orizont, model de churn, legături, meniul de intervenții, buget de portofoliu",
  constraints: "DTI, LTV, vârstă, marjă minimă, restructurare (BNR + politica internă)",
  checks: "verificări pe trepte, motive, documente necesare, incertitudini critice",
  signals: "cele 24 de semnale: praguri, scoruri, regex-uri",
  portofoliu: "profilul statistic al portofoliului generat",
  echipa: "consilierii și alocarea cazurilor",
};

/** Tot ce e regulă, prag, meniu sau constrângere stă în YAML: aici se editează cu validare pe server (aceleași modele
 *  pydantic ca la pornire) și apoi se re-rulează fluxul. Fără API, ecranul explică de ce nu poate edita. */
export default function Admin() {
  const lista = useConfigLista();
  const ctx = useContext();
  const [ales, setAles] = useState("retention");
  const fisier = useConfigFisier(ales);
  const diff = useConfigDiff(ales);
  const salveaza = useSalveazaConfig(ales);
  const rescan = useRescan();
  const [text, setText] = useState("");
  const [mesaj, setMesaj] = useState<{ ok: boolean; text: string } | null>(null);

  useEffect(() => {
    if (fisier.data) {
      setText(fisier.data.text);
      setMesaj(null);
    }
  }, [fisier.data]);

  if (lista.isLoading) return <Loading />;
  if (getSursa() === "static" || !lista.data?.length)
    return (
      <>
        <h1>Admin</h1>
        <div className="notice warn">
          Editarea configurației cere API-ul pornit (<code>python -m retailagent.api</code>). Fără el, interfața arată doar
          snapshot-ul static; YAML-urile rămân editabile direct în <code>config/</code>, urmate de <code>python -m retailagent.pipeline</code>.
        </div>
      </>
    );

  const modificat = fisier.data ? text !== fisier.data.text : false;
  const trimite = () => {
    setMesaj(null);
    salveaza.mutate(text, {
      onSuccess: (r) => setMesaj({ ok: true, text: `Salvat (versiune config ${r.versiune}). ${r.nota}.` }),
      onError: (e) => setMesaj({ ok: false, text: String(e instanceof Error ? e.message : e) }),
    });
  };
  const reruleaza = () =>
    rescan.mutate(undefined, {
      onSuccess: (r) => setMesaj({ ok: true, text: `Fluxul a fost re-rulat: ${r.cazuri} cazuri în coadă (azi ${r.azi}).` }),
      onError: (e) => setMesaj({ ok: false, text: String(e instanceof Error ? e.message : e) }),
    });

  return (
    <>
      <div className="page-head">
        <div>
          <h1>Admin · configurație</h1>
          <p className="muted" style={{ margin: 0 }}>
            Un semnal, o verificare, o intervenție sau un prag nou = configurație, nu cod. Salvarea validează pe server; apoi re-rulezi fluxul.
            {ctx.data?.versiune ? ` Versiune curentă: ${ctx.data.versiune.scurt}` : ""}
          </p>
        </div>
      </div>

      <div className="grid c3" style={{ gridTemplateColumns: "260px 1fr 1fr" }}>
        <section className="panel">
          <h2>Fișiere</h2>
          <ul style={{ listStyle: "none", padding: 0, margin: 0 }}>
            {lista.data.map((f) => (
              <li key={f.nume} style={{ marginBottom: 6 }}>
                <button type="button" className={`chip ${f.nume === ales ? "on" : ""}`} onClick={() => setAles(f.nume)} style={{ width: "100%", textAlign: "left" }}>
                  {f.fisier} <span className="chip-n">{f.hash ?? "—"}</span>
                </button>
                <div className="small muted" style={{ padding: "2px 6px 0" }}>{DESCRIERI[f.nume]}</div>
              </li>
            ))}
          </ul>
          <div className="actions" style={{ marginTop: 12 }}>
            <button type="button" className="btn" disabled={rescan.isPending} onClick={reruleaza}>
              {rescan.isPending ? "Se re-rulează… (15–45 s)" : "Re-rulează fluxul"}
            </button>
          </div>
          <p className="small muted">Re-rularea reface coada, verificările, retenția și recomandările cu configurația de pe disc.</p>
        </section>

        <section className="panel" style={{ gridColumn: "span 2" }}>
          <h2>
            {ales}.yaml {modificat && <span className="tag avertizare">modificat, nesalvat</span>}
          </h2>
          {fisier.isLoading ? (
            <Loading />
          ) : (
            <>
              <textarea className="editor" value={text} onChange={(e) => setText(e.target.value)} spellCheck={false} aria-label={`Conținutul ${ales}.yaml`} />
              <div className="actions" style={{ marginTop: 10 }}>
                <button type="button" className="btn" disabled={!modificat || salveaza.isPending} onClick={trimite}>
                  {salveaza.isPending ? "Se validează…" : "Salvează (cu validare)"}
                </button>
                <button type="button" className="btn ghost" disabled={!modificat} onClick={() => fisier.data && setText(fisier.data.text)}>
                  Renunță la modificări
                </button>
              </div>
              {mesaj && (
                <div className={`notice ${mesaj.ok ? "ok" : "fail"}`} role={mesaj.ok ? "status" : "alert"} style={{ marginTop: 10 }}>
                  {mesaj.text}
                </div>
              )}
              <details style={{ marginTop: 12 }} onToggle={(e) => (e.currentTarget as HTMLDetailsElement).open && diff.refetch()}>
                <summary className="small">Diferența față de versiunea din git</summary>
                {diff.data?.git ? (
                  <pre className="diff mono">{diff.data.diff || "(identic cu versiunea din git)"}</pre>
                ) : (
                  <p className="small muted">Proiectul nu e într-un repo git accesibil serverului.</p>
                )}
              </details>
            </>
          )}
        </section>
      </div>
    </>
  );
}
