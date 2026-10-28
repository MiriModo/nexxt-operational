import { useEffect, useState } from "react";
import { getSursa } from "../api/client";
import { useConfigDiff, useConfigFisier, useConfigLista, useContext, useRescan, useSalveazaConfig } from "../api/hooks";
import { useToast } from "../components/Toast";
import { Loading } from "../components/ui";

const DESCRIERI: Record<string, string> = {
  priority: "ponderi, benzi, termene, bugete pe nivel",
  retention: "p țintă, modelul de churn, meniul de intervenții, buget de portofoliu",
  constraints: "DTI, LTV, vârstă, marjă minimă, restructurare",
  checks: "verificări pe trepte, motive, documente, incertitudini critice",
  signals: "semnalele: praguri și scoruri",
  portofoliu: "profilul portofoliului generat",
  echipa: "consilierii și alocarea",
};

/** Regulile stau în YAML; aici se editează cu validare pe server (aceleași modele ca la pornire) și apoi se re-rulează fluxul. */
function Editor() {
  const lista = useConfigLista();
  const ctx = useContext();
  const toast = useToast();
  const [ales, setAles] = useState("retention");
  const fisier = useConfigFisier(ales);
  const diff = useConfigDiff(ales);
  const salveaza = useSalveazaConfig(ales);
  const rescan = useRescan();
  const [text, setText] = useState("");
  const [eroare, setEroare] = useState<string | null>(null);

  useEffect(() => {
    if (fisier.data) {
      setText(fisier.data.text);
      setEroare(null);
    }
  }, [fisier.data]);

  if (lista.isLoading) return <Loading />;
  if (lista.error) return <Loading err={String(lista.error)} />;
  if (!lista.data) return null;

  const modificat = fisier.data ? text !== fisier.data.text : false;
  const trimite = () => {
    setEroare(null);
    salveaza.mutate(text, {
      onSuccess: () => toast(`${ales}.yaml salvat. Re-rulează fluxul ca schimbarea să intre în cazuri.`),
      onError: (e) => setEroare(String(e instanceof Error ? e.message : e)),
    });
  };
  const reruleaza = () =>
    rescan.mutate(undefined, {
      onSuccess: (r) => toast(`Fluxul a fost re-rulat: ${r.cazuri} cazuri`),
      onError: (e) => toast(String(e instanceof Error ? e.message : e), "fail"),
    });

  return (
    <>
      <div className="page-head">
        <div>
          <h1>Motor de reguli</h1>
          <p className="muted" style={{ margin: 0 }}>
            O regulă, un prag sau o intervenție nouă = configurație, nu cod. Salvarea validează pe server.
            {ctx.data?.versiune ? ` Versiunea curentă: ${ctx.data.versiune.config.hash.slice(0, 6)}.` : ""}
          </p>
        </div>
        <div className="actions">
          <button type="button" className="btn secondary" disabled={rescan.isPending} onClick={reruleaza}>
            {rescan.isPending ? "Se re-rulează… (15–45 s)" : "Re-rulează fluxul"}
          </button>
        </div>
      </div>

      <div className="grid" style={{ gridTemplateColumns: "240px 1fr" }}>
        <section className="panel">
          <ul style={{ listStyle: "none", padding: 0, margin: 0 }}>
            {lista.data.map((f) => (
              <li key={f.nume} style={{ marginBottom: 8 }}>
                <button type="button" className={`chip ${f.nume === ales ? "on" : ""}`} onClick={() => setAles(f.nume)} style={{ width: "100%", justifyContent: "flex-start" }}>
                  {f.fisier}
                </button>
                <div className="small muted" style={{ padding: "2px 6px 0" }}>{DESCRIERI[f.nume]}</div>
              </li>
            ))}
          </ul>
        </section>

        <section className="panel">
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
                  {salveaza.isPending ? "Se validează…" : "Salvează"}
                </button>
                <button type="button" className="btn ghost" disabled={!modificat} onClick={() => fisier.data && setText(fisier.data.text)}>
                  Renunță
                </button>
              </div>
              {eroare && (
                <div className="notice fail" role="alert" style={{ marginTop: 10 }}>
                  {eroare}
                </div>
              )}
              <details style={{ marginTop: 12 }} onToggle={(e) => (e.currentTarget as HTMLDetailsElement).open && diff.refetch()}>
                <summary className="small muted">Diferența față de versiunea din git</summary>
                {diff.data?.git ? <pre className="diff mono">{diff.data.diff || "(identic)"}</pre> : <p className="small muted">Indisponibil (nu e repo git).</p>}
              </details>
            </>
          )}
        </section>
      </div>
    </>
  );
}

export default function Motor() {
  if (getSursa() === "static")
    return (
      <div className="notice warn">
        Motorul de reguli cere serverul pornit (<code>python -m retailagent.api</code>). Fără el, regulile se editează direct în <code>config/</code>.
      </div>
    );
  return <Editor />;
}
