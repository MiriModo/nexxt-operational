// Strat de acces la date, organizat pe resursele API-ului (retailagent/api.py):
//   GET /api/metrici/context, GET /api/cazuri, GET /api/cazuri/{id}, POST /api/cazuri/{id}/decizie, GET /api/metrici
// Sursa: API-ul (implicit /api, proxy-at de Vite către 127.0.0.1:8000; se poate schimba cu VITE_API_URL).
// Dacă API-ul nu răspunde, cade pe snapshot-ul static public/data/demo.json (scris de `python -m retailagent.demo`),
// iar deciziile se țin în localStorage. `getSursa()` spune ce sursă e activă (pentru antet).
import type {
  BugetPortofoliu, Caz, ConfigFisier, Consilier, DecizieInput, DecizieRecord, DecizieServer, Feedback, Metrici, ModelInfo,
  PaginaCoada, ParametriCoada, Reverificare, Snapshot, Sumar, Versiune,
} from "../types/api";

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
  total_cazuri?: number;
  versiune?: Versiune | null;
  buget_portofoliu?: BugetPortofoliu | null;
}

export async function getContext(): Promise<Context> {
  return viaApi<Context>("/metrici/context", async () => {
    const s = await loadSnapshot();
    return { azi: s.azi, clienti: s.clienti, p_tinta: s.p_tinta, model_churn: s.model_churn, total_cazuri: s.total_cazuri };
  });
}

/** Reia verificările unui caz (doar cu API); fără API, regrupează pe trepte ce e deja în snapshot. */
export async function postVerifica(id: string): Promise<Reverificare> {
  if (sursa !== "static") {
    try {
      const r = await fetch(`${API}/cazuri/${id}/verifica`, { method: "POST" });
      if (r.ok) {
        setSursa("api");
        return (await r.json()) as Reverificare;
      }
      if (r.status === 404) throw new Error(`cazul ${id} nu există`);
    } catch (e) {
      if (e instanceof Error && e.message.startsWith("cazul")) throw e;
      setSursa("static");
    }
  }
  const c = await getCaz(id);
  if (!c) throw new Error(`cazul ${id} nu există`);
  const ordine = ["intern", "anaf", "biroul_credit", "crc", "garantie", "eligibilitate"];
  const trepte = ordine
    .map((t) => ({ treapta: t, rezultate: c.check.rezultate.filter((r) => r.treapta === t) }))
    .filter((t) => t.rezultate.length)
    .map((t) => ({
      ...t,
      stare: (c.check.oprit_la === t.treapta ? "oprita" : t.rezultate.every((r) => r.status === "neexecutat") ? "neexecutata" : "executata") as
        | "executata"
        | "oprita"
        | "neexecutata",
    }));
  return {
    case_id: id, motive: c.check.motive, plan: c.check.plan, omise: c.check.omise, trepte, oprit_la: c.check.oprit_la,
    verificare_picata: c.check.verificare_picata, incertitudini: c.rec.incertitudini ?? [], concluzii: c.check.concluzii as Record<string, unknown>,
    interogari_externe: c.check.interogari,
  };
}

export async function getIstoric(id: string): Promise<DecizieServer[]> {
  return viaApi<DecizieServer[]>(`/cazuri/${id}/decizii`, async () => {
    const d = getDeciziiLocale()[id];
    return d
      ? [{ timestamp: d.la, case_id: id, client_id: "", consilier: d.consilier ?? null, decizie: d.decizie, override: d.decizie !== "aproba",
           recomandare_agent: "nu_interveni", interventie_agent: null, interventie_finala: d.interventie ?? null, motiv: d.motiv ?? null,
           rezultat: null, rezultat_la: null }]
      : [];
  });
}

export async function postRezultat(id: string, rezultat: "ramas" | "plecat"): Promise<DecizieServer> {
  const r = await fetch(`${API}/cazuri/${id}/rezultat`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ rezultat }) });
  if (r.status === 400) throw new Error(((await r.json()) as { detail?: string }).detail ?? "rezultat refuzat");
  if (!r.ok) throw new Error(`rezultat: ${r.status} (rezultatul la 90 de zile se înregistrează doar prin API)`);
  return (await r.json()) as DecizieServer;
}

export async function getEchipa(): Promise<Consilier[]> {
  return viaApi<{ consilieri: Consilier[] }>("/echipa", async () => ({ consilieri: [] })).then((r) => r.consilieri);
}

export async function getFeedback(): Promise<Feedback | null> {
  return viaApi<Feedback | null>("/feedback", async () => null);
}

export async function getModel(): Promise<ModelInfo | null> {
  return viaApi<ModelInfo | null>("/model", async () => null);
}

export async function getConfigLista(): Promise<ConfigFisier[]> {
  return viaApi<ConfigFisier[]>("/config", async () => []);
}

export async function getConfig(nume: string): Promise<{ nume: string; text: string }> {
  const r = await fetch(`${API}/config/${nume}`);
  if (!r.ok) throw new Error(`config ${nume}: ${r.status}`);
  return (await r.json()) as { nume: string; text: string };
}

export async function putConfig(nume: string, text: string): Promise<{ salvat: boolean; versiune: string; nota: string }> {
  const r = await fetch(`${API}/config/${nume}`, { method: "PUT", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ text }) });
  if (r.status === 400) throw new Error(((await r.json()) as { detail?: string }).detail ?? "configurație respinsă");
  if (!r.ok) throw new Error(`config ${nume}: ${r.status}`);
  return (await r.json()) as { salvat: boolean; versiune: string; nota: string };
}

export async function getConfigDiff(nume: string): Promise<{ diff: string; git: boolean }> {
  const r = await fetch(`${API}/config/${nume}/diff`);
  if (!r.ok) throw new Error(`diff ${nume}: ${r.status}`);
  return (await r.json()) as { diff: string; git: boolean };
}

export async function postRescan(): Promise<{ cazuri: number; azi: string }> {
  const r = await fetch(`${API}/rescan`, { method: "POST" });
  if (!r.ok) throw new Error(`rescan: ${r.status}`);
  return (await r.json()) as { cazuri: number; azi: string };
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
  if (p.recomandari && p.recomandari.length) qs.set("recomandare", p.recomandari.join(","));
  if (p.consilier) qs.set("consilier", p.consilier);
  if (p.q?.trim()) qs.set("q", p.q.trim());
  if (p.ascundeDecise) qs.set("ascunde_decise", "true");
  return viaApi<PaginaCoada>(`/coada?${qs}`, async () => {
    const decizii = getDeciziiLocale();
    const needle = (p.q ?? "").trim().toLowerCase();
    let rows = (await loadSnapshot()).cazuri.filter((c) => {
      if (p.benzi && p.benzi.length && !p.benzi.includes(c.case.banda)) return false;
      if (p.recomandari && p.recomandari.length && !p.recomandari.includes(c.rec.recomandare)) return false;
      if (p.consilier && c.consilier !== p.consilier) return false;
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
  if (d.consilier) p.push(`--consilier ${d.consilier}`);
  return p.join(" ");
}
