import type { Recomandare } from "../types/api";

/** The six agent states as Keeper badges (guide D3): Keep / Watch / Escalate pills, neutral for no action and blocked.
 *  Same colour and wording in the queue, the case, the decision and the reports. */
export const STATES: Record<Recomandare, { name: string; short: string; badge: "keep" | "watch" | "esc" | "neutral" }> = {
  oferta_minima: { name: "Keep — retention offer", short: "Keep", badge: "keep" },
  oferta_produs: { name: "Keep — offer with a product", short: "Keep + product", badge: "keep" },
  nu_interveni: { name: "No action needed", short: "No action", badge: "neutral" },
  restructurare: { name: "Watch — restructure", short: "Restructure", badge: "watch" },
  respins_escaladat: { name: "Escalate to a person", short: "Escalate", badge: "esc" },
  blocat: { name: "Blocked by a process task", short: "Blocked", badge: "neutral" },
};

export function stateName(r: Recomandare | string, long = false) {
  const s = STATES[r as Recomandare];
  return s ? (long ? s.name : s.short) : String(r).replace(/_/g, " ");
}

export function State({ r, long = false, lg = false }: { r: Recomandare | string; long?: boolean; lg?: boolean }) {
  const s = STATES[r as Recomandare];
  return <span className={`badge ${s?.badge ?? "neutral"} ${lg ? "lg" : ""}`}>{stateName(r, long)}</span>;
}
