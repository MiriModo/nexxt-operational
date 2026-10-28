// Strat de acces la date, organizat pe resursele API-ului (retailagent/api.py):
//   GET /api/metrici/context, GET /api/cazuri, GET /api/cazuri/{id}, POST /api/cazuri/{id}/decizie, GET /api/metrici
// Sursa: API-ul (implicit /api, proxy-at de Vite către 127.0.0.1:8000; se poate schimba cu VITE_API_URL).
// Dacă API-ul nu răspunde, cade pe snapshot-ul static public/data/demo.json (scris de `python -m retailagent.demo`),
// iar deciziile se țin în localStorage. `getSursa()` spune ce sursă e activă (pentru antet).
import type { Caz, DecizieInput, DecizieRecord, Metrici, PaginaCoada, ParametriCoada, Snapshot, Sumar } from "../types/api";

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

/** Filtrare + sortare + paginare: pe server cu API, în memorie pe snapshot (aceeași semantică). */
export async function getCoada(p: ParametriCoada = {}): Promise<PaginaCoada> {
  const limit = p.limit ?? 60;
  const offset = p.offset ?? 0;
  const qs = new URLSearchParams({ limit: String(limit), offset: String(offset), sort: p.sort ?? "prioritate" });
  if (p.benzi && p.benzi.length) qs.set("banda", p.benzi.join(","));
  if (p.q?.trim()) qs.set("q", p.q.trim());
  if (p.ascundeDecise) qs.set("ascunde_decise", "true");
  return viaApi<PaginaCoada>(`/coada?${qs}`, async () => {
    const decizii = getDeciziiLocale();
    const needle = (p.q ?? "").trim().toLowerCase();
    let rows = (await loadSnapshot()).cazuri.filter((c) => {
      if (p.benzi && p.benzi.length && !p.benzi.includes(c.case.banda)) return false;
      if (p.ascundeDecise && decizii[c.case.case_id]) return false;
      if (!needle) return true;
      return [c.case.case_id, c.case.client_id, c.client.nume, c.case.produs, c.case.actiune_propusa, c.rec.recomandare, ...c.case.motive_top3]
        .join(" ")
        .toLowerCase()
        .includes(needle);
    });
    if (p.sort === "termen") rows = [...rows].sort((a, b) => a.case.deadline.localeCompare(b.case.deadline) || b.case.scoruri.prioritate - a.case.scoruri.prioritate);
    if (p.sort === "client") rows = [...rows].sort((a, b) => a.client.nume.localeCompare(b.client.nume));
    const pe_banda: Record<string, number> = {};
    rows.forEach((c) => (pe_banda[c.case.banda] = (pe_banda[c.case.banda] ?? 0) + 1));
    return { total: rows.length, offset, limit, pe_banda, items: rows.slice(offset, offset + limit) };
  });
}

/** Contoarele paginii de start: pe toată coada cu API, pe snapshot (primele N cazuri) fără. */
export async function getSumar(): Promise<Sumar> {
  return viaApi<Sumar>("/cazuri/sumar", async () => {
    const s = await loadSnapshot();
    const decizii = getDeciziiLocale();
    const deschise = s.cazuri.filter((c) => !decizii[c.case.case_id]);
    const pe_banda: Record<string, number> = {};
    s.cazuri.forEach((c) => (pe_banda[c.case.banda] = (pe_banda[c.case.banda] ?? 0) + 1));
    return {
      total: s.cazuri.length,
      deschise: deschise.length,
      p1: deschise.filter((c) => c.case.banda === "P1").length,
      scadente_azi: deschise.filter((c) => c.case.deadline <= s.azi).length,
      blocate: deschise.filter((c) => c.case.blocaje.length > 0 || c.rec.recomandare === "blocat").length,
      decise: s.cazuri.length - deschise.length,
      pe_banda,
      primele: [...deschise]
        .sort((a, b) => a.case.deadline.localeCompare(b.case.deadline) || b.case.scoruri.prioritate - a.case.scoruri.prioritate)
        .slice(0, 5),
    };
  });
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

/** Generare exclusiv prin server; nu simulăm un LLM când API-ul lipsește. */
export async function postPropunere(caseId: string): Promise<import("../types/api").PropunereLLM> {
  const r = await fetch(`${API}/cazuri/${encodeURIComponent(caseId)}/propunere`, { method: "POST" });
  if (!r.ok) {
    const body = await r.json().catch(() => ({}));
    throw new Error(body.detail ?? "Generarea LLM necesită API-ul pornit și configurat.");
  }
  return r.json();
}
