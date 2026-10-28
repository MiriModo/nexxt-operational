import { useEffect, useState } from "react";
import { getCoada, getContext, getDeciziiLocale } from "../api/client";
import { useEchipa } from "../api/hooks";
import { CaseCard } from "../components/CaseCard";
import { Loading } from "../components/ui";
import { eticheta } from "../format";
import type { Banda, Caz, ParametriCoada, Recomandare } from "../types/api";

type SortKey = NonNullable<ParametriCoada["sort"]>;
const PAGINA = 60;
const RECOMANDARI: Recomandare[] = ["oferta_minima", "oferta_produs", "nu_interveni", "restructurare", "respins_escaladat", "blocat"];

const GRUPE: { b: Banda; titlu: string; desc: string }[] = [
  { b: "P1", titlu: "Acționează azi", desc: "Termen apropiat sau semnal puternic. Fiecare zi contează." },
  { b: "P2", titlu: "Săptămâna aceasta", desc: "Important, dar cu spațiu de manevră." },
  { b: "P3", titlu: "Poate aștepta", desc: "Monitorizare sau sarcini administrative." },
];

/** Coada e filtrată, sortată și paginată pe server (sau pe snapshot, cu aceeași semantică): la 10.000 de clienți
 *  sunt ~6.000 de cazuri, deci se încarcă câte PAGINA odată și se cere „încă o pagină" la nevoie. */
export default function Coada() {
  const [items, setItems] = useState<Caz[] | null>(null);
  const [total, setTotal] = useState(0);
  const [peBanda, setPeBanda] = useState<Record<string, number>>({});
  const [azi, setAzi] = useState("");
  const [err, setErr] = useState<string | null>(null);
  const [incarca, setIncarca] = useState(false);
  const [benzi, setBenzi] = useState<Set<Banda>>(new Set(["P1", "P2", "P3"]));
  const [q, setQ] = useState("");
  const [qAplicat, setQAplicat] = useState("");
  const [sort, setSort] = useState<SortKey>("prioritate");
  const [ascundeDecise, setAscundeDecise] = useState(false);
  const [recomandari, setRecomandari] = useState<Set<Recomandare>>(new Set());
  const [consilier, setConsilier] = useState("");
  const echipa = useEchipa();
  const decizii = getDeciziiLocale();

  useEffect(() => {
    getContext().then((ctx) => setAzi(ctx.azi)).catch(() => undefined);
  }, []);

  // căutarea se aplică după o scurtă pauză de tastare, ca să nu lovească serverul la fiecare literă
  useEffect(() => {
    const t = setTimeout(() => setQAplicat(q), 250);
    return () => clearTimeout(t);
  }, [q]);

  const parametri = (offset: number): ParametriCoada => ({
    benzi: [...benzi], recomandari: [...recomandari], consilier: consilier || undefined, q: qAplicat, sort, ascundeDecise, limit: PAGINA, offset,
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
  }, [benzi, recomandari, consilier, qAplicat, sort, ascundeDecise]);

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

  if (!items) return <Loading err={err} />;

  const toggle = (b: Banda) => {
    const s = new Set(benzi);
    if (s.has(b)) s.delete(b);
    else s.add(b);
    setBenzi(s);
  };
  const toggleRec = (r: Recomandare) => {
    const s = new Set(recomandari);
    if (s.has(r)) s.delete(r);
    else s.add(r);
    setRecomandari(s);
  };

  return (
    <>
      <div className="page-head">
        <div>
          <h1>Coada de cazuri</h1>
          <p className="muted" style={{ margin: 0 }}>
            {total} cazuri după filtre, afișate {items.length}. Apasă pe un caz pentru detalii, semnale și oferta propusă.
          </p>
        </div>
      </div>

      <div className="filters" role="group" aria-label="Filtre">
        {(["P1", "P2", "P3"] as Banda[]).map((b) => (
          <button key={b} type="button" className={`chip ${benzi.has(b) ? "on" : ""}`} aria-pressed={benzi.has(b)} onClick={() => toggle(b)}>
            {b} <span className="chip-n">{peBanda[b] ?? 0}</span>
          </button>
        ))}
        <button type="button" className={`chip ${ascundeDecise ? "on" : ""}`} aria-pressed={ascundeDecise} onClick={() => setAscundeDecise(!ascundeDecise)}>
          Ascunde cazurile decise
        </button>
        <span style={{ flex: 1 }} />
        <label className="sr-only" htmlFor="sort">
          Ordonează după
        </label>
        <select id="sort" value={sort} onChange={(e) => setSort(e.target.value as SortKey)} style={{ width: "auto" }}>
          <option value="prioritate">După prioritate</option>
          <option value="termen">După termen</option>
          <option value="client">După client</option>
        </select>
        <label className="sr-only" htmlFor="cauta">
          Caută în coadă
        </label>
        <input
          id="cauta"
          type="text"
          placeholder="Caută client, caz, produs sau motiv"
          value={q}
          onChange={(e) => setQ(e.target.value)}
          style={{ maxWidth: 300 }}
        />
      </div>

      <div className="filters" role="group" aria-label="Filtre pe recomandare și consilier">
        {RECOMANDARI.map((r) => (
          <button key={r} type="button" className={`chip ${recomandari.has(r) ? "on" : ""}`} aria-pressed={recomandari.has(r)} onClick={() => toggleRec(r)}>
            {eticheta(r)}
          </button>
        ))}
        <span style={{ flex: 1 }} />
        {echipa.data && echipa.data.length > 0 && (
          <>
            <label className="sr-only" htmlFor="consilier">
              Consilier
            </label>
            <select id="consilier" value={consilier} onChange={(e) => setConsilier(e.target.value)} style={{ width: "auto" }}>
              <option value="">Toți consilierii</option>
              {echipa.data.map((c) => (
                <option key={c.id} value={c.id}>
                  {c.nume}
                </option>
              ))}
            </select>
          </>
        )}
      </div>

      <p className="sr-only" role="status">
        {items.length} cazuri afișate din {total}
      </p>

      {items.length === 0 && !incarca && (
        <div className="empty">Niciun caz nu se potrivește filtrelor. Șterge căutarea sau reactivează o bandă.</div>
      )}

      {GRUPE.filter((g) => benzi.has(g.b)).map((g) => {
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
              <p className="muted small">{g.desc}</p>
            </div>
            <div className="case-list">
              {grup.map((c) => (
                <CaseCard key={c.case.case_id} c={c} azi={azi} decizie={decizii[c.case.case_id]} />
              ))}
            </div>
          </section>
        );
      })}

      {items.length < total && (
        <div className="actions" style={{ justifyContent: "center", margin: "16px 0" }}>
          <button type="button" className="btn secondary" disabled={incarca} onClick={incaOPagina}>
            {incarca ? "Se încarcă…" : `Încă ${Math.min(PAGINA, total - items.length)} cazuri (${items.length} din ${total})`}
          </button>
        </div>
      )}
    </>
  );
}
