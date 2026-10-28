import { useEffect, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { getCoada, getContext, getDeciziiLocale } from "../api/client";
import { useEchipa } from "../api/hooks";
import { useEu } from "../auth";
import { CaseCard } from "../components/CaseCard";
import { STATES, stateName } from "../components/State";
import { Loading } from "../components/ui";
import type { Banda, Caz, ParametriCoada, Recomandare } from "../types/api";

type SortKey = NonNullable<ParametriCoada["sort"]>;
type Only = NonNullable<ParametriCoada["doar"]>;
const PAGE = 60;
// URL values are English; the API keeps its own names
const ONLY: Record<string, Only> = { due_today: "termen_azi", over_cap: "peste_plafon", to_confirm: "de_confirmat" };
const ONLY_TEXT: Record<string, string> = { due_today: "due today", over_cap: "deferred over cap", to_confirm: "with something to confirm" };
const SORT: Record<string, SortKey> = { priority: "prioritate", due: "termen", client: "client" };
const GROUPS: { b: Banda; title: string }[] = [
  { b: "P1", title: "Today" },
  { b: "P2", title: "This week" },
  { b: "P3", title: "Can wait" },
];

/** The queue is filtered, sorted and paged on the server (or on the snapshot with the same semantics): PAGE at a time.
 *  Filters live in the URL, so the desk's links and "back" keep them. */
export default function Queue() {
  const [sp, setSp] = useSearchParams();
  const [items, setItems] = useState<Caz[] | null>(null);
  const [total, setTotal] = useState(0);
  const [perBand, setPerBand] = useState<Record<string, number>>({});
  const [today, setToday] = useState("");
  const [err, setErr] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [q, setQ] = useState(sp.get("q") ?? "");
  const [qApplied, setQApplied] = useState(q);
  const { eu } = useEu();
  const team = useEchipa();
  const local = getDeciziiLocale();

  const bands = new Set<Banda>((sp.get("band")?.split(",").filter(Boolean) as Banda[]) ?? []);
  if (bands.size === 0) ["P1", "P2", "P3"].forEach((b) => bands.add(b as Banda));
  const state = (sp.get("state") as Recomandare | null) ?? "";
  const advisor = sp.get("advisor") ?? "";
  const sortKey = sp.get("sort") ?? "priority";
  const hideDecided = sp.get("decided") === "hide";
  const onlyKey = sp.get("only") ?? "";
  const set = (k: string, v: string | null) => {
    const n = new URLSearchParams(sp);
    if (v) n.set(k, v);
    else n.delete(k);
    setSp(n, { replace: true });
  };

  useEffect(() => {
    getContext().then((c) => setToday(c.azi)).catch(() => undefined);
  }, []);
  useEffect(() => {
    const t = setTimeout(() => setQApplied(q), 250);
    return () => clearTimeout(t);
  }, [q]);

  const key = `${[...bands].join(",")}|${state}|${advisor}|${sortKey}|${hideDecided}|${onlyKey}|${qApplied}`;
  const params = (offset: number): ParametriCoada => ({
    benzi: [...bands], recomandari: state ? [state] : [], consilier: advisor || undefined, q: qApplied, sort: SORT[sortKey] ?? "prioritate",
    ascundeDecise: hideDecided, doar: ONLY[onlyKey], limit: PAGE, offset,
  });

  useEffect(() => {
    let live = true;
    setBusy(true);
    getCoada(params(0))
      .then((p) => {
        if (!live) return;
        setItems(p.items);
        setTotal(p.total);
        setPerBand(p.pe_banda);
      })
      .catch((e) => live && setErr(String(e)))
      .finally(() => live && setBusy(false));
    return () => {
      live = false;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [key]);

  const more = async () => {
    if (!items) return;
    setBusy(true);
    try {
      const p = await getCoada(params(items.length));
      setItems([...items, ...p.items]);
      setTotal(p.total);
    } catch (e) {
      setErr(String(e));
    } finally {
      setBusy(false);
    }
  };

  const toggleBand = (b: Banda) => {
    const s = new Set(bands);
    if (s.has(b)) s.delete(b);
    else s.add(b);
    set("band", s.size === 3 || s.size === 0 ? null : [...s].join(","));
  };

  const active: { k: string; text: string }[] = [];
  if (state) active.push({ k: "state", text: stateName(state) });
  if (advisor) active.push({ k: "advisor", text: team.data?.find((c) => c.id === advisor)?.nume ?? advisor });
  if (onlyKey) active.push({ k: "only", text: ONLY_TEXT[onlyKey] ?? onlyKey });
  if (hideDecided) active.push({ k: "decided", text: "without decided cases" });
  if (qApplied) active.push({ k: "q", text: `"${qApplied}"` });

  return (
    <>
      <div className="label-row" style={{ marginBottom: 18 }}>
        <span>{eu?.rol === "admin" ? "Queue" : "My queue"}</span>
        <span>{items ? `/ ${total} ${total === 1 ? "case" : "cases"}` : "/ loading"}</span>
      </div>

      <div className="filters" role="group" aria-label="Filters">
        <div className="segmented" role="group" aria-label="Priority band">
          {(["P1", "P2", "P3"] as Banda[]).map((b) => (
            <button key={b} type="button" className={bands.has(b) ? "on" : ""} aria-pressed={bands.has(b)} onClick={() => toggleBand(b)}>
              {b} <span className="n">{perBand[b] ?? 0}</span>
            </button>
          ))}
        </div>
        <label className="sr-only" htmlFor="state">
          State
        </label>
        <select id="state" value={state} onChange={(e) => set("state", e.target.value || null)}>
          <option value="">All states</option>
          {(Object.keys(STATES) as Recomandare[]).map((r) => (
            <option key={r} value={r}>
              {STATES[r].name}
            </option>
          ))}
        </select>
        {eu?.rol === "admin" && team.data && team.data.length > 0 && (
          <>
            <label className="sr-only" htmlFor="advisor">
              Advisor
            </label>
            <select id="advisor" value={advisor} onChange={(e) => set("advisor", e.target.value || null)}>
              <option value="">All advisors</option>
              {team.data.map((c) => (
                <option key={c.id} value={c.id}>
                  {c.nume}
                </option>
              ))}
            </select>
          </>
        )}
        <button type="button" className={`btn sm ${hideDecided ? "primary" : "secondary"}`} aria-pressed={hideDecided} onClick={() => set("decided", hideDecided ? null : "hide")}>
          Hide decided
        </button>
        <span style={{ flex: 1 }} />
        <label className="sr-only" htmlFor="sort">
          Sort by
        </label>
        <select id="sort" value={sortKey} onChange={(e) => set("sort", e.target.value === "priority" ? null : e.target.value)}>
          <option value="priority">By priority</option>
          <option value="due">By deadline</option>
          <option value="client">By client</option>
        </select>
        <label className="sr-only" htmlFor="search">
          Search
        </label>
        <input id="search" type="text" placeholder="Search client, case or reason" value={q} onChange={(e) => setQ(e.target.value)} />
      </div>

      {active.length > 0 && (
        <div className="chips" aria-label="Active filters">
          {active.map((a) => (
            <button
              key={a.k}
              type="button"
              className="chip"
              onClick={() => {
                if (a.k === "q") setQ("");
                set(a.k, null);
              }}
              aria-label={`Remove filter ${a.text}`}
            >
              {a.text} <b aria-hidden="true">×</b>
            </button>
          ))}
        </div>
      )}

      {!items && !err && (
        <div className="rows" aria-busy="true">
          {[0, 1, 2, 3, 4].map((i) => (
            <div key={i} className="skeleton" />
          ))}
        </div>
      )}
      {!items && err && <Loading err={err} />}
      {items && items.length === 0 && !busy && <div className="empty">No case matches these filters.</div>}

      {items &&
        GROUPS.filter((g) => bands.has(g.b)).map((g) => {
          const grp = items.filter((c) => c.case.banda === g.b);
          if (grp.length === 0) return null;
          return (
            <section key={g.b} className="group" aria-labelledby={`g-${g.b}`}>
              <div className="group-head">
                <h2 id={`g-${g.b}`}>{g.title}</h2>
                <span className="mono">
                  {g.b} · {grp.length}
                  {perBand[g.b] && perBand[g.b] > grp.length ? ` of ${perBand[g.b]}` : ""}
                </span>
              </div>
              <div className="rows">
                {grp.map((c) => (
                  <CaseCard key={c.case.case_id} c={c} today={today} decision={local[c.case.case_id]} />
                ))}
              </div>
            </section>
          );
        })}

      {items && items.length < total && (
        <div className="actions" style={{ justifyContent: "center", margin: "20px 0" }}>
          <button type="button" className="btn secondary" disabled={busy} onClick={more}>
            {busy ? "Loading…" : `${Math.min(PAGE, total - items.length)} more cases`}
          </button>
        </div>
      )}
    </>
  );
}
