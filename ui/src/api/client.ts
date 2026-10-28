// Strat de acces la date, organizat pe resursele API-ului (retailagent/api.py):
//   GET /api/metrici/context, GET /api/cazuri, GET /api/cazuri/{id}, POST /api/cazuri/{id}/decizie, GET /api/metrici
// Sursa: API-ul (implicit /api, proxy-at de Vite către 127.0.0.1:8000; se poate schimba cu VITE_API_URL).
// Dacă API-ul nu răspunde, cade pe snapshot-ul static public/data/demo.json (scris de `python -m retailagent.demo`),
// iar deciziile se țin în localStorage. `getSursa()` spune ce sursă e activă (pentru antet).
import type { Caz, DecizieInput, DecizieRecord, Metrici, Snapshot } from "../types/api";

const API = (import.meta.env.VITE_API_URL as string | undefined) ?? "/api";
const LS_KEY = "retailagent.decizii";

type Sursa = "api" | "static" | "necunoscuta";
let sursa: Sursa = "necunoscuta";
const ascultatori = new Set<(s: Sursa) => void>();

export function getSursa(): Sursa {
  return sursa;
}
export function onSursa(fn: (s: Sursa) => void): () => void {
  ascultatori.add(fn);
  return () => ascultatori.delete(fn);
}
function setSursa(s: Sursa) {
  if (s !== sursa) {
    sursa = s;
    ascultatori.forEach((fn) => fn(s));
  }
}

let snapshot: Promise<Snapshot> | null = null;
function loadSnapshot(): Promise<Snapshot> {
  if (!snapshot) {
    snapshot = fetch("/data/demo.json").then((r) => {
      if (!r.ok) throw new Error(`demo.json: ${r.status}`);
      return r.json() as Promise<Snapshot>;
    });
  }
  return snapshot;
}

/** Încearcă API-ul; la eroare de rețea sau 5xx cade pe snapshot (404 rămâne 404: cazul chiar nu există). */
async function viaApi<T>(path: string, fallback: () => Promise<T>): Promise<T> {
  if (sursa === "static") return fallback();
  try {
    const r = await fetch(`${API}${path}`);
    if (r.status === 404) {
      setSursa("api");
      return undefined as T;
    }
    if (!r.ok) throw new Error(`${path}: ${r.status}`);
    setSursa("api");
    return (await r.json()) as T;
  } catch {
    setSursa("static");
    return fallback();
  }
}

export interface Context {
  azi: string;
  clienti: number;
  p_tinta: number;
  model_churn?: { nume: string; versiune: string } | null;
}

export async function getContext(): Promise<Context> {
  return viaApi<Context>("/metrici/context", async () => {
    const s = await loadSnapshot();
    return { azi: s.azi, clienti: s.clienti, p_tinta: s.p_tinta, model_churn: s.model_churn };
  });
}

export async function getCazuri(): Promise<Caz[]> {
  return viaApi<Caz[]>("/cazuri", async () => (await loadSnapshot()).cazuri);
}

export async function getCaz(id: string): Promise<Caz | undefined> {
  return viaApi<Caz | undefined>(`/cazuri/${id}`, async () => (await loadSnapshot()).cazuri.find((c) => c.case.case_id === id));
}

export async function getMetrici(): Promise<Metrici> {
  return viaApi<Metrici>("/metrici", async () => (await loadSnapshot()).metrici);
}

export function getDeciziiLocale(): Record<string, DecizieRecord> {
  try {
    return JSON.parse(localStorage.getItem(LS_KEY) ?? "{}") as Record<string, DecizieRecord>;
  } catch {
    return {};
  }
}

function salveazaLocal(rec: DecizieRecord) {
  const all = getDeciziiLocale();
  all[rec.case_id] = rec;
  try {
    localStorage.setItem(LS_KEY, JSON.stringify(all));
  } catch {
    /* fără persistență: decizia rămâne doar în sesiune */
  }
}

export async function postDecizie(caseId: string, d: DecizieInput): Promise<DecizieRecord> {
  if (sursa !== "static") {
    try {
      const r = await fetch(`${API}/cazuri/${caseId}/decizie`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(d),
      });
      if (r.status === 400) {
        const body = (await r.json()) as { detail?: string };
        throw new Error(body.detail ?? "decizie refuzată");
      }
      if (!r.ok) throw new Error(`decizie: ${r.status}`);
      setSursa("api");
      const rec: DecizieRecord = { ...d, case_id: caseId, la: new Date().toISOString(), sursa: "api" };
      salveazaLocal(rec); // ecranele citesc starea deciziilor din localStorage; API-ul a scris approvals.json + audit
      return rec;
    } catch (e) {
      if (e instanceof Error && !/^decizie: 5|fetch/i.test(e.message) && sursa === "api") throw e; // refuz de validare, nu cădere
      setSursa("static");
    }
  }
  const rec: DecizieRecord = { ...d, case_id: caseId, la: new Date().toISOString(), sursa: "local" };
  salveazaLocal(rec);
  return rec;
}

/** Comanda CLI echivalentă, cu aceeași semantică precum `python -m retailagent.approve`. */
export function comandaApprove(caseId: string, d: DecizieInput): string {
  const p = [`python -m retailagent.approve ${caseId} --decizie ${d.decizie}`];
  if (d.decizie === "modifica" && d.interventie) p.push(`--interventie ${d.interventie}`);
  if (d.motiv) p.push(`--motiv "${d.motiv.replace(/"/g, "'")}"`);
  return p.join(" ");
}
