import type { ReactNode } from "react";
import { getSursa } from "../api/client";
import { usePropunere, useRegenereaza } from "../api/hooks";
import { label, ron } from "../format";
import type { PropunereLLM } from "../types/api";
import { useToast } from "./Toast";

/** Step 3, the AI offer agent: picks the offer among the engine's admissible options and writes the advisor's argument
 *  and the client message. Every figure in the text was checked against the computed facts on the server; without a
 *  key, or when an answer fails the checks, the text comes from the deterministic template and says so. */
export function AgentProposal({ caseId, action }: { caseId: string; action?: (p: PropunereLLM) => ReactNode }) {
  const offline = getSursa() === "static";
  const q = usePropunere(caseId, !offline);
  const again = useRegenereaza(caseId);
  const toast = useToast();
  const p = q.data;
  const busy = q.isLoading || again.isPending;
  const e = again.error ?? q.error;
  const errText = e ? (e instanceof Error ? e.message : String(e)) : null;

  const copy = async (text: string) => {
    try {
      await navigator.clipboard.writeText(text);
      toast("Client message copied");
    } catch {
      toast("Copy isn't available here; select the text instead");
    }
  };

  return (
    <div className="agent" aria-live="polite" aria-busy={busy}>
      <div className="agent-head">
        <span className="mono">AI offer agent</span>
        {p && (
          <span className={`tag ${p.sursa === "llm" ? "ok" : "warn"}`} title={p.avertisment ?? undefined}>
            {p.sursa === "llm" ? modelName(p.model) : "template"}
          </span>
        )}
        {!offline && (
          <button type="button" className="btn ghost sm" disabled={busy} onClick={() => again.mutate()}>
            {again.isPending ? "Writing…" : "Regenerate"}
          </button>
        )}
      </div>

      {offline && <p className="meta">The AI agent needs the server. Start the API and reload the page.</p>}
      {busy && (
        <div role="status">
          <p className="meta">The agent is reading the case and writing the offer…</p>
          <div className="skeleton agent-skel" />
        </div>
      )}
      {errText && !busy && (
        <div className="notice fail" role="alert">
          The AI agent didn't answer: {errText}
        </div>
      )}

      {p && !busy && (
        <>
          {p.avertisment && <p className="agent-note">{p.avertisment}</p>}
          <p className="agent-choice">
            {!p.decide ? (
              <>No offer to choose here: the agent explains the engine's decision.</>
            ) : p.acord_cu_motorul ? (
              <>
                <b>Agrees with the engine:</b> {labelOf(p, p.interventie)}
              </>
            ) : (
              <>
                <b>Chooses {labelOf(p, p.interventie)}</b> instead of {labelOf(p, p.interventie_motor)}
                {p.cost_banca != null && p.cost_motor != null && <span className="muted"> · +{ron(p.cost_banca - p.cost_motor)} for the bank</span>}
              </>
            )}
          </p>
          {p.decide && <p className="meta agent-why">{p.motiv_alegere}</p>}
          <p className="agent-arg">{p.argument}</p>
          {p.puncte_cheie.length > 0 && (
            <ul className="agent-points">
              {p.puncte_cheie.map((x) => (
                <li key={x}>{x}</li>
              ))}
            </ul>
          )}

          <div className="agent-msg">
            <div className="agent-msg-head">
              <span className="mono">Message to the client · {p.limba_client === "ro" ? "Romanian" : "English"} draft</span>
              <button type="button" className="btn secondary sm" onClick={() => copy(p.mesaj_client)}>
                Copy
              </button>
            </div>
            <p lang={p.limba_client}>{p.mesaj_client}</p>
          </div>

          {p.atentionari.length > 0 && (
            <ul className="plain agent-warn">
              {p.atentionari.map((w) => (
                <li key={w}>{w}</li>
              ))}
            </ul>
          )}
          {action?.(p)}
          <p className="meta agent-foot">
            {p.sursa === "llm"
              ? `Every figure checked against the computed facts${p.incercari > 1 ? `, after ${p.incercari} attempts` : ""} · ${(p.durata_ms / 1000).toFixed(1)} s`
              : "Written from the computed facts by the template"}{" "}
            · prompt {p.prompt_hash}
          </p>
        </>
      )}
    </div>
  );
}

/** "us.anthropic.claude-haiku-4-5-20251001-v1:0" or "claude-haiku-5-5" → "Claude Haiku 4.5" / "Claude Haiku 5.5". */
function modelName(id: string | null): string {
  const m = (id ?? "").match(/claude-(haiku|sonnet|opus|fable|mythos)-(\d+)-(\d+)/i);
  return m ? `Claude ${m[1][0].toUpperCase()}${m[1].slice(1).toLowerCase()} ${m[2]}.${m[3]}` : id ?? "model";
}

function labelOf(p: PropunereLLM, id: string | null): string {
  if (!id) return "no offer";
  return p.optiuni.find((o) => o.id === id)?.eticheta ?? label(id);
}
