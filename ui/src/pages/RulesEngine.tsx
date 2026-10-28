import { useEffect, useState } from "react";
import { getSursa } from "../api/client";
import { useConfigDiff, useConfigFisier, useConfigLista, useContext, useRescan, useSalveazaConfig } from "../api/hooks";
import { useToast } from "../components/Toast";
import { Loading } from "../components/ui";

const ABOUT: Record<string, string> = {
  priority: "weights, bands, deadlines, per-tier budgets",
  retention: "target p, churn model, intervention menu, portfolio budget",
  constraints: "DTI, LTV, age, minimum margin, restructuring",
  checks: "staged checks, reasons, documents, critical uncertainties",
  signals: "the signals: thresholds and scores",
  portofoliu: "profile of the generated portfolio",
  echipa: "advisors and case allocation",
};

/** The rules live in YAML; here they're edited with server-side validation (same models as at start-up), then the flow
 *  is re-run. The route is admin-only; the role comes from the session. */
export default function RulesEngine() {
  const list = useConfigLista();
  const ctx = useContext();
  const toast = useToast();
  const [picked, setPicked] = useState("retention");
  const file = useConfigFisier(picked);
  const diff = useConfigDiff(picked);
  const save = useSalveazaConfig(picked);
  const rerun = useRescan();
  const [text, setText] = useState("");
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (file.data) {
      setText(file.data.text);
      setError(null);
    }
  }, [file.data]);

  if (getSursa() === "static")
    return (
      <div className="notice warn">
        The rules engine needs the server running (<code>python -m retailagent.api</code>). Without it, edit the YAML files in <code>config/</code> directly.
      </div>
    );
  if (list.isLoading) return <Loading />;
  if (list.error) return <Loading err={String(list.error)} />;
  if (!list.data) return null;

  const dirty = file.data ? text !== file.data.text : false;
  const submit = () => {
    setError(null);
    save.mutate(text, {
      onSuccess: () => toast(`${picked}.yaml saved. Re-run the flow so the change reaches the cases.`),
      onError: (e) => setError(String(e instanceof Error ? e.message : e)),
    });
  };
  const run = () =>
    rerun.mutate(undefined, {
      onSuccess: (r) => toast(`Flow re-run: ${r.cazuri} cases`),
      onError: (e) => toast(String(e instanceof Error ? e.message : e), "fail"),
    });

  return (
    <>
      <section className="section" style={{ marginBottom: 24 }}>
        <div className="label-row">
          <span>Rules engine</span>
          <span>/ config{ctx.data?.versiune ? ` · version ${ctx.data.versiune.config.hash.slice(0, 6)}` : ""}</span>
        </div>
        <div className="sec-head" style={{ padding: "28px 0 8px" }}>
          <h2 className="hl" style={{ fontSize: 34 }}>A rule, a threshold or a new intervention is configuration, not code.</h2>
          <div>
            <p>Saving validates on the server with the same models used at start-up. Then re-run the flow.</p>
            <button type="button" className="btn primary" disabled={rerun.isPending} onClick={run} style={{ marginTop: 12 }}>
              {rerun.isPending ? "Re-running… (15–45 s)" : "Re-run the flow"} <span className="arrow">→</span>
            </button>
          </div>
        </div>
      </section>

      <div className="frame">
        <div className="grid" style={{ gridTemplateColumns: "240px 1fr", alignItems: "start" }}>
          <ul className="files win" style={{ padding: 10 }}>
            {list.data.map((f) => (
              <li key={f.nume}>
                <button type="button" className={f.nume === picked ? "on" : ""} onClick={() => setPicked(f.nume)}>
                  {f.fisier}
                </button>
                <div className="desc">{ABOUT[f.nume]}</div>
              </li>
            ))}
          </ul>
          <section className="win" style={{ margin: 0 }}>
            <div className="sec-label">
              <span>{picked}.yaml</span>
              {dirty && <span className="tag warn">modified, unsaved</span>}
            </div>
            {file.isLoading ? (
              <Loading />
            ) : (
              <>
                <textarea className="editor" value={text} onChange={(e) => setText(e.target.value)} spellCheck={false} aria-label={`Contents of ${picked}.yaml`} />
                <div className="actions" style={{ marginTop: 12 }}>
                  <button type="button" className="btn primary" disabled={!dirty || save.isPending} onClick={submit}>
                    {save.isPending ? "Validating…" : "Save"}
                  </button>
                  <button type="button" className="btn ghost" disabled={!dirty} onClick={() => file.data && setText(file.data.text)}>
                    Discard
                  </button>
                </div>
                {error && (
                  <div className="notice fail" role="alert" style={{ marginTop: 12 }}>
                    {error}
                  </div>
                )}
                <details style={{ marginTop: 14 }} onToggle={(e) => (e.currentTarget as HTMLDetailsElement).open && diff.refetch()}>
                  <summary className="meta" style={{ cursor: "pointer" }}>Difference from the git version</summary>
                  {diff.data?.git ? <pre className="diff">{diff.data.diff || "(identical)"}</pre> : <p className="meta">Unavailable (not a git repo).</p>}
                </details>
              </>
            )}
          </section>
        </div>
      </div>
    </>
  );
}
