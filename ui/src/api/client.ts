// Strat de acces la date, organizat pe resursele API-ului (retailagent/api.py):
//   GET /api/metrici/context, GET /api/cazuri, GET /api/cazuri/{id}, POST /api/cazuri/{id}/decizie, GET /api/metrici
// Sursa: API-ul (implicit /api, proxy-at de Vite către 127.0.0.1:8000; se poate schimba cu VITE_API_URL).
// Dacă API-ul nu răspunde, cade pe snapshot-ul static public/data/demo.json (scris de `python -m retailagent.demo`),
// iar deciziile se țin în localStorage. `getSursa()` spune ce sursă e activă (pentru antet).
import type {
  Birou, BugetPortofoliu, Caz, ConfigFisier, Consilier, DecizieInput, DecizieRecord, DecizieServer, Feedback, Metrici, ModelInfo,
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

// ---- sesiunea: tokenul și utilizatorul stau în sessionStorage; fiecare apel către API poartă Authorization: Bearer
const SES_KEY = "retailagent.sesiune";
export type Rol = "consilier" | "admin";
export interface Utilizator { id: string; nume: string; rol: Rol }
type Sesiune = { token: string; utilizator: Utilizator };
const deconectari = new Set<() => void>();

function citesteSesiune(): Sesiune | null {
  try {
    const raw = sessionStorage.getItem(SES_KEY);
    return raw ? (JSON.parse(raw) as Sesiune) : null;
  } catch {
    return null;
  }
}
export const getEu = (): Utilizator | null => citesteSesiune()?.utilizator ?? null;
export function setSesiune(s: Sesiune | null) {
  try {
    if (s) sessionStorage.setItem(SES_KEY, JSON.stringify(s));
    else sessionStorage.removeItem(SES_KEY);
  } catch {
    /* fără sessionStorage: sesiunea ține doar cât pagina */
  }
}
/** Se apelează la 401 (sesiune expirată) sau la „Ieși”: App trimite la pagina publică. */
export function deconecteaza() {
  setSesiune(null);
  deconectari.forEach((fn) => fn());
}
export function onDeconectare(fn: () => void): () => void {
  deconectari.add(fn);
  return () => deconectari.delete(fn);
}

export class EroareHttp extends Error {
  constructor(public status: number, mesaj: string) {
    super(mesaj);
  }
}
/** fetch cu antetul de autentificare; 401 deconectează, 403 / 400 devin erori cu mesajul serverului. */
async function req(path: string, init: RequestInit = {}): Promise<Response> {
  const tok = citesteSesiune()?.token;
  const headers: Record<string, string> = { ...((init.headers as Record<string, string>) ?? {}) };
  if (tok) headers.Authorization = `Bearer ${tok}`;
  const r = await fetch(`${API}${path}`, { ...init, headers });
  if (r.status === 401) {
    deconecteaza();
    throw new EroareHttp(401, "sesiunea a expirat, intră din nou în cont");
  }
  if (r.status === 403 || r.status === 400) throw new EroareHttp(r.status, ((await r.json()) as { detail?: string }).detail ?? `${path}: ${r.status}`);
  return r;
}

/** Încearcă API-ul; la eroare de rețea sau 5xx cade pe snapshot (404 rămâne 404: cazul chiar nu există;
 *  401 / 403 / 400 sunt răspunsuri, nu căderi, și se propagă). */
async function viaApi<T>(path: string, fallback: () => Promise<T>): Promise<T> {
  if (sursa === "static") return fallback();
  try {
    const r = await req(path);
    if (r.status === 404) {
      setSursa("api");
      return undefined as T;
    }
    if (!r.ok) throw new Error(`${path}: ${r.status}`);
    setSursa("api");
    return (await r.json()) as T;
  } catch (e) {
    if (e instanceof EroareHttp) throw e;
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
      const r = await req(`/cazuri/${id}/verifica`, { method: "POST" });
      if (r.ok) {
        setSursa("api");
        return (await r.json()) as Reverificare;
      }
      if (r.status === 404) throw new Error(`cazul ${id} nu există`);
    } catch (e) {
      if (e instanceof EroareHttp || (e instanceof Error && e.message.startsWith("cazul"))) throw e;
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
  const r = await req(`/cazuri/${id}/rezultat`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ rezultat }) });
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

// ---- conturi: cu API, parola se verifică pe server; fără API (snapshot), login-ul e de demo (orice parolă)
function numeDinId(id: string) {
  return id.split(".").map((p) => p.charAt(0).toUpperCase() + p.slice(1)).join(" ");
}
export async function getUtilizatori(): Promise<Utilizator[]> {
  return viaApi<Utilizator[]>("/utilizatori", async () => {
    const ids = [...new Set((await loadSnapshot()).cazuri.map((c) => c.consilier).filter((x): x is string => !!x))].sort();
    return [...ids.map((id) => ({ id, nume: numeDinId(id), rol: "consilier" as Rol })), { id: "admin", nume: "Administrator", rol: "admin" as Rol }];
  });
}
/** Întoarce utilizatorul la succes, null la parolă greșită. */
export async function login(utilizator: string, parola: string): Promise<Utilizator | null> {
  if (sursa !== "static") {
    try {
      const r = await fetch(`${API}/login`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ utilizator, parola }) });
      if (r.status === 401) return null;
      if (!r.ok) throw new Error(`login: ${r.status}`);
      setSursa("api");
      const s = (await r.json()) as Sesiune;
      setSesiune(s);
      return s.utilizator;
    } catch {
      setSursa("static");
    }
  }
  const u = (await getUtilizatori()).find((x) => x.id === utilizator);
  if (!u) return null;
  setSesiune({ token: "", utilizator: u });
  return u;
}
export async function logout(): Promise<void> {
  if (sursa === "api") {
    try {
      await req("/logout", { method: "POST" });
    } catch {
      /* sesiunea se închide oricum local */
    }
  }
  deconecteaza();
}

/** Biroul consilierului: coada lui + activitatea lui. Fără API: calculat din snapshot + deciziile locale. */
export async function getBirou(): Promise<Birou> {
  return viaApi<Birou>("/eu/birou", async () => {
    const eu = getEu();
    const s = await loadSnapshot();
    const rows = s.cazuri.filter((c) => !eu || eu.rol === "admin" || c.consilier === eu.id);
    const decizii = Object.values(getDeciziiLocale()).filter((d) => !eu || eu.rol === "admin" || d.consilier === eu.id);
    const decise = new Set(decizii.map((d) => d.case_id));
    const deschise = rows.filter((c) => !decise.has(c.case.case_id));
    const conteaza = (f: (c: Caz) => boolean) => deschise.filter(f).length;
    const distributie: Record<string, number> = {};
    rows.forEach((c) => (distributie[c.rec.recomandare] = (distributie[c.rec.recomandare] ?? 0) + 1));
    const pe_banda: Record<string, number> = {};
    deschise.forEach((c) => (pe_banda[c.case.banda] = (pe_banda[c.case.banda] ?? 0) + 1));
    const azi = new Date().toISOString().slice(0, 10);
    return {
      utilizator: eu ?? { id: "", nume: "", rol: "consilier" },
      coada: {
        total: rows.length, deschise: deschise.length,
        p1_azi: conteaza((c) => c.case.banda === "P1" && c.case.deadline <= s.azi),
        peste_plafon: conteaza((c) => !!c.rec.oferta?.amanata_buget),
        de_confirmat: conteaza((c) => !!c.rec.incertitudini?.length),
        pe_banda, distributie,
      },
      activitate: {
        decizii: decizii.length, decizii_azi: decizii.filter((d) => d.la.slice(0, 10) === azi).length,
        override: decizii.filter((d) => d.decizie !== "aproba").length,
        rezultate: { n: 0, ramasi: 0, plecati: 0 },
        ultimele: decizii.slice(-5).reverse().map((d) => ({
          timestamp: d.la, case_id: d.case_id, client_id: "", consilier: d.consilier ?? null, decizie: d.decizie, override: d.decizie !== "aproba",
          recomandare_agent: "nu_interveni" as const, interventie_agent: null, interventie_finala: d.interventie ?? null, motiv: d.motiv ?? null,
          rezultat: null, rezultat_la: null,
        })),
      },
      primele: [...deschise].sort((a, b) => a.case.deadline.localeCompare(b.case.deadline) || b.case.scoruri.prioritate - a.case.scoruri.prioritate).slice(0, 5),
    };
  });
}

// ---- motorul de reguli (admin): aceleași apeluri, autentificate; serverul răspunde 403 pentru consilier
async function cereJson<T>(path: string, init: RequestInit = {}): Promise<T> {
  const r = await req(path, init);
  if (!r.ok) throw new Error(`${path}: ${r.status}`);
  return (await r.json()) as T;
}
export const getConfigLista = () => cereJson<ConfigFisier[]>("/config");
export const getConfig = (nume: string) => cereJson<{ nume: string; text: string }>(`/config/${nume}`);
export const putConfig = (nume: string, text: string) =>
  cereJson<{ salvat: boolean; versiune: string; nota: string }>(`/config/${nume}`, {
    method: "PUT", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ text }),
  });
export const getConfigDiff = (nume: string) => cereJson<{ diff: string; git: boolean }>(`/config/${nume}/diff`);
export const postRescan = () => cereJson<{ cazuri: number; azi: string }>("/rescan", { method: "POST" });

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
  if (p.doar) qs.set("doar", p.doar);
  return viaApi<PaginaCoada>(`/coada?${qs}`, async () => {
    const decizii = getDeciziiLocale();
    const needle = (p.q ?? "").trim().toLowerCase();
    const snap = await loadSnapshot();
    const eu = getEu();
    let rows = snap.cazuri.filter((c) => {
      if (eu && eu.rol !== "admin" && c.consilier !== eu.id) return false;
      if (p.benzi && p.benzi.length && !p.benzi.includes(c.case.banda)) return false;
      if (p.doar === "termen_azi" && c.case.deadline > snap.azi) return false;
      if (p.doar === "peste_plafon" && !c.rec.oferta?.amanata_buget) return false;
      if (p.doar === "de_confirmat" && !c.rec.incertitudini?.length) return false;
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
    const snap = await loadSnapshot();
    const eu = getEu();
    const s = { ...snap, cazuri: snap.cazuri.filter((c) => !eu || eu.rol === "admin" || c.consilier === eu.id) };
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
      const r = await req(`/cazuri/${caseId}/decizie`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(d),
      });
      if (!r.ok) throw new Error(`decizie: ${r.status}`);
      setSursa("api");
      const srv = (await r.json()) as { consilier?: string | null };
      const rec: DecizieRecord = { ...d, consilier: srv.consilier ?? d.consilier, case_id: caseId, la: new Date().toISOString(), sursa: "api" };
      salveazaLocal(rec); // ecranele citesc starea deciziilor din localStorage; API-ul a scris approvals.json + audit
      return rec;
    } catch (e) {
      if (e instanceof EroareHttp) throw e;                       // refuz de validare / drepturi, nu cădere
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
