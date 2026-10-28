import { useEffect, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { getCoada, getContext, getDeciziiLocale } from "../api/client";
import { useEchipa } from "../api/hooks";
import { useEu } from "../auth";
import { CaseCard } from "../components/CaseCard";
import { STARI, numeStare } from "../components/Stare";
import { Loading } from "../components/ui";
import type { Banda, Caz, ParametriCoada, Recomandare } from "../types/api";

type SortKey = NonNullable<ParametriCoada["sort"]>;
type Doar = NonNullable<ParametriCoada["doar"]>;
const PAGINA = 60;
const DOAR_TEXT: Record<Doar, string> = { termen_azi: "termen azi", peste_plafon: "amânate peste plafon", de_confirmat: "cu ceva de confirmat" };
const GRUPE: { b: Banda; titlu: string }[] = [
  { b: "P1", titlu: "Azi" },
  { b: "P2", titlu: "Săptămâna aceasta" },
  { b: "P3", titlu: "Poate aștepta" },
];

/** Coada e filtrată, sortată și paginată pe server (sau pe snapshot, cu aceeași semantică): câte PAGINA odată.
 *  Filtrele vin și din URL (listele briefing-ului de pe Acasă). */
export default function Coada() {
  const [sp, setSp] = useSearchParams();
  const [items, setItems] = useState<Caz[] | null>(null);
  const [total, setTotal] = useState(0);
  const [peBanda, setPeBanda] = useState<Record<string, number>>({});
  const [azi, setAzi] = useState("");
  const [err, setErr] = useState<string | null>(null);
  const [incarca, setIncarca] = useState(false);
  const [q, setQ] = useState(sp.get("q") ?? "");
  const [qAplicat, setQAplicat] = useState(q);
  const { eu } = useEu();
  const echipa = useEchipa();
  const decizii = getDeciziiLocale();

  // filtrele stau în URL: linkurile din briefing și „înapoi” le păstrează
  const benzi = new Set<Banda>((sp.get("banda")?.split(",").filter(Boolean) as Banda[]) ?? []);
  if (benzi.size === 0) ["P1", "P2", "P3"].forEach((b) => benzi.add(b as Banda));
  const rec = (sp.get("rec") as Recomandare | null) ?? "";
  const consilier = sp.get("consilier") ?? "";
  const sort = (sp.get("sort") as SortKey | null) ?? "prioritate";
  const ascundeDecise = sp.get("decise") === "nu";
  const doar = (sp.get("doar") as Doar | null) ?? undefined;
  const seteaza = (k: string, v: string | null) => {
    const n = new URLSearchParams(sp);
    if (v) n.set(k, v);
    else n.delete(k);
    setSp(n, { replace: true });
  };

  useEffect(() => {
    getContext().then((ctx) => setAzi(ctx.azi)).catch(() => undefined);
  }, []);
  useEffect(() => {
    const t = setTimeout(() => setQAplicat(q), 250);
    return () => clearTimeout(t);
  }, [q]);

  const cheie = `${[...benzi].join(",")}|${rec}|${consilier}|${sort}|${ascundeDecise}|${doar ?? ""}|${qAplicat}`;
  const parametri = (offset: number): ParametriCoada => ({
    benzi: [...benzi], recomandari: rec ? [rec] : [], consilier: consilier || undefined, q: qAplicat, sort, ascundeDecise, doar, limit: PAGINA, offset,
  });

  useEffect(() => {
    let activ = true;
    setIncarca(true);
    getCoada(parametri(0))
      .then((p) => {
        if (!activ) return;
        setItems(p.items);
        setTotal(p.total);
        setPeBanda(p.pe_banda);
      })
      .catch((e) => activ && setErr(String(e)))
      .finally(() => activ && setIncarca(false));
    return () => {
      activ = false;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [cheie]);

  const incaOPagina = async () => {
    if (!items) return;
    setIncarca(true);
    try {
      const p = await getCoada(parametri(items.length));
      setItems([...items, ...p.items]);
      setTotal(p.total);
    } catch (e) {
      setErr(String(e));
    } finally {
      setIncarca(false);
    }
  };

  const toggleBanda = (b: Banda) => {
    const s = new Set(benzi);
    if (s.has(b)) s.delete(b);
    else s.add(b);
    seteaza("banda", s.size === 3 || s.size === 0 ? null : [...s].join(","));
  };

  const active: { k: string; text: string }[] = [];
  if (rec) active.push({ k: "rec", text: numeStare(rec) });
  if (consilier) active.push({ k: "consilier", text: echipa.data?.find((c) => c.id === consilier)?.nume ?? consilier });
  if (doar) active.push({ k: "doar", text: DOAR_TEXT[doar] });
  if (ascundeDecise) active.push({ k: "decise", text: "fără cazurile decise" });
  if (qAplicat) active.push({ k: "q", text: `„${qAplicat}”` });

  return (
    <>
      <div className="page-head">
        <div>
          <h1>{eu?.rol === "admin" ? "Cazuri" : "Cazurile mele"}</h1>
          <p className="muted" style={{ margin: 0 }}>
            {items ? `${total} ${total === 1 ? "caz" : "cazuri"}` : "se încarcă"}
          </p>
        </div>
      </div>

      <div className="filters" role="group" aria-label="Filtre">
        {(["P1", "P2", "P3"] as Banda[]).map((b) => (
          <button key={b} type="button" className={`chip ${benzi.has(b) ? "on" : ""}`} aria-pressed={benzi.has(b)} onClick={() => toggleBanda(b)}>
            {b} <span className="chip-n">{peBanda[b] ?? 0}</span>
          </button>
        ))}
        <label className="sr-only" htmlFor="rec">
          Recomandare
        </label>
        <select id="rec" value={rec} onChange={(e) => seteaza("rec", e.target.value || null)} style={{ width: "auto" }}>
          <option value="">Toate recomandările</option>
          {(Object.keys(STARI) as Recomandare[]).map((r) => (
            <option key={r} value={r}>
              {STARI[r].nume}
            </option>
          ))}
        </select>
        {eu?.rol === "admin" && echipa.data && echipa.data.length > 0 && (
          <>
            <label className="sr-only" htmlFor="consilier">
              Consilier
            </label>
            <select id="consilier" value={consilier} onChange={(e) => seteaza("consilier", e.target.value || null)} style={{ width: "auto" }}>
              <option value="">Toți consilierii</option>
              {echipa.data.map((c) => (
                <option key={c.id} value={c.id}>
                  {c.nume}
                </option>
              ))}
            </select>
          </>
        )}
        <button type="button" className={`chip ${ascundeDecise ? "on" : ""}`} aria-pressed={ascundeDecise} onClick={() => seteaza("decise", ascundeDecise ? null : "nu")}>
          Ascunde decise
        </button>
        <span style={{ flex: 1 }} />
        <label className="sr-only" htmlFor="sort">
          Ordonează după
        </label>
        <select id="sort" value={sort} onChange={(e) => seteaza("sort", e.target.value === "prioritate" ? null : e.target.value)} style={{ width: "auto" }}>
          <option value="prioritate">După prioritate</option>
          <option value="termen">După termen</option>
          <option value="client">După client</option>
        </select>
        <label className="sr-only" htmlFor="cauta">
          Caută
        </label>
        <input id="cauta" type="text" placeholder="Caută client, caz sau motiv" value={q} onChange={(e) => setQ(e.target.value)} style={{ maxWidth: 260 }} />
      </div>

      {active.length > 0 && (
        <div className="active-filters" aria-label="Filtre active">
          {active.map((a) => (
            <button
              key={a.k}
              type="button"
              className="flt"
              onClick={() => {
                if (a.k === "q") setQ("");
                seteaza(a.k, null);
              }}
              aria-label={`Scoate filtrul ${a.text}`}
            >
              {a.text} <b aria-hidden="true">×</b>
            </button>
          ))}
        </div>
      )}

      {!items && !err && (
        <div className="case-list" aria-busy="true">
          {[0, 1, 2, 3, 4].map((i) => (
            <div key={i} className="skeleton" />
          ))}
        </div>
      )}
      {!items && err && <Loading err={err} />}

      {items && items.length === 0 && !incarca && <div className="empty">Niciun caz pentru filtrele alese.</div>}

      {items &&
        GRUPE.filter((g) => benzi.has(g.b)).map((g) => {
          const grup = items.filter((c) => c.case.banda === g.b);
          if (grup.length === 0) return null;
          return (
            <section key={g.b} className="queue-group" aria-labelledby={`g-${g.b}`}>
              <div className="group-head">
                <h2 id={`g-${g.b}`}>
                  {g.titlu} <span className="group-band">{g.b}</span>
                </h2>
                <span className="group-count">
                  {grup.length}
                  {peBanda[g.b] && peBanda[g.b] > grup.length ? ` din ${peBanda[g.b]}` : ""}
                </span>
              </div>
              <div className="case-list">
                {grup.map((c) => (
                  <CaseCard key={c.case.case_id} c={c} azi={azi} decizie={decizii[c.case.case_id]} />
                ))}
              </div>
            </section>
          );
        })}

      {items && items.length < total && (
        <div className="actions" style={{ justifyContent: "center", margin: "16px 0" }}>
          <button type="button" className="btn secondary" disabled={incarca} onClick={incaOPagina}>
            {incarca ? "Se încarcă…" : `Încă ${Math.min(PAGINA, total - items.length)} cazuri`}
          </button>
        </div>
      )}
    </>
  );
}
