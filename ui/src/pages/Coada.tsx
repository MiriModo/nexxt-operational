import { useEffect, useMemo, useState } from "react";
import { getCazuri, getContext, getDeciziiLocale } from "../api/client";
import { CaseCard } from "../components/CaseCard";
import { Loading } from "../components/ui";
import type { Banda, Caz } from "../types/api";

type SortKey = "prioritate" | "termen" | "client";

const GRUPE: { b: Banda; titlu: string; desc: string }[] = [
  { b: "P1", titlu: "Acționează azi", desc: "Termen apropiat sau semnal puternic. Fiecare zi contează." },
  { b: "P2", titlu: "Săptămâna aceasta", desc: "Important, dar cu spațiu de manevră." },
  { b: "P3", titlu: "Poate aștepta", desc: "Monitorizare sau sarcini administrative." },
];

export default function Coada() {
  const [cazuri, setCazuri] = useState<Caz[] | null>(null);
  const [azi, setAzi] = useState("");
  const [err, setErr] = useState<string | null>(null);
  const [benzi, setBenzi] = useState<Set<Banda>>(new Set(["P1", "P2", "P3"]));
  const [q, setQ] = useState("");
  const [sort, setSort] = useState<SortKey>("prioritate");
  const [ascundeDecise, setAscundeDecise] = useState(false);
  const decizii = getDeciziiLocale();

  useEffect(() => {
    Promise.all([getCazuri(), getContext()])
      .then(([c, ctx]) => {
        setCazuri(c);
        setAzi(ctx.azi);
      })
      .catch((e) => setErr(String(e)));
  }, []);

  const vizibile = useMemo(() => {
    if (!cazuri) return [];
    const needle = q.trim().toLowerCase();
    const f = cazuri.filter((c) => {
      if (!benzi.has(c.case.banda)) return false;
      if (ascundeDecise && decizii[c.case.case_id]) return false;
      if (!needle) return true;
      const hay = [c.case.case_id, c.case.client_id, c.client.nume, c.case.produs, c.case.actiune_propusa, c.rec.recomandare, ...c.case.motive_top3]
        .join(" ")
        .toLowerCase();
      return hay.includes(needle);
    });
    f.sort((a, b) => {
      switch (sort) {
        case "prioritate":
          return b.case.scoruri.prioritate - a.case.scoruri.prioritate || a.case.deadline.localeCompare(b.case.deadline);
        case "termen":
          return a.case.deadline.localeCompare(b.case.deadline) || b.case.scoruri.prioritate - a.case.scoruri.prioritate;
        case "client":
          return a.client.nume.localeCompare(b.client.nume);
      }
    });
    return f;
  }, [cazuri, benzi, q, sort, ascundeDecise, decizii]);

  if (!cazuri) return <Loading err={err} />;

  const count = (b: Banda) => cazuri.filter((c) => c.case.banda === b).length;
  const toggle = (b: Banda) => {
    const s = new Set(benzi);
    if (s.has(b)) s.delete(b);
    else s.add(b);
    setBenzi(s);
  };
  const deschise = cazuri.filter((c) => !decizii[c.case.case_id]).length;

  return (
    <>
      <div className="page-head">
        <div>
          <h1>Coada de cazuri</h1>
          <p className="muted" style={{ margin: 0 }}>
            {deschise} deschise din {cazuri.length}. Apasă pe un caz pentru detalii, semnale și oferta propusă.
          </p>
        </div>
      </div>

      <div className="filters" role="group" aria-label="Filtre">
        {(["P1", "P2", "P3"] as Banda[]).map((b) => (
          <button key={b} type="button" className={`chip ${benzi.has(b) ? "on" : ""}`} aria-pressed={benzi.has(b)} onClick={() => toggle(b)}>
            {b} <span className="chip-n">{count(b)}</span>
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

      <p className="sr-only" role="status">
        {vizibile.length} cazuri afișate
      </p>

      {vizibile.length === 0 && (
        <div className="empty">
          Niciun caz nu se potrivește filtrelor. Șterge căutarea sau reactivează o bandă.
        </div>
      )}

      {GRUPE.filter((g) => benzi.has(g.b)).map((g) => {
        const items = vizibile.filter((c) => c.case.banda === g.b);
        if (items.length === 0) return null;
        return (
          <section key={g.b} className="queue-group" aria-labelledby={`g-${g.b}`}>
            <div className="group-head">
              <h2 id={`g-${g.b}`}>
                {g.titlu} <span className="group-band">{g.b}</span>
              </h2>
              <span className="group-count">{items.length}</span>
              <p className="muted small">{g.desc}</p>
            </div>
            <div className="case-list">
              {items.map((c) => (
                <CaseCard key={c.case.case_id} c={c} azi={azi} decizie={decizii[c.case.case_id]} />
              ))}
            </div>
          </section>
        );
      })}
    </>
  );
}
