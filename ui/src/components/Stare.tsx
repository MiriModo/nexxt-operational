import type { Recomandare } from "../types/api";

/** Limbajul vizual al celor 6 stări: aceeași culoare, același simbol și același nume în coadă, caz, decizie și rezultate.
 *  Numele e scris pentru consilier (ce are de făcut), nu pentru sistem. */
export const STARI: Record<Recomandare, { nume: string; scurt: string; simbol: string }> = {
  oferta_minima: { nume: "ofertă de retenție", scurt: "ofertă", simbol: "●" },
  oferta_produs: { nume: "ofertă cu produs atașat", scurt: "ofertă + produs", simbol: "◐" },
  nu_interveni: { nume: "nu interveni", scurt: "nu interveni", simbol: "○" },
  restructurare: { nume: "restructurare", scurt: "restructurare", simbol: "▲" },
  respins_escaladat: { nume: "escaladare la om", scurt: "escaladare", simbol: "■" },
  blocat: { nume: "blocat de proces", scurt: "blocat", simbol: "⊘" },
};

export function numeStare(r: Recomandare | string, lung = false) {
  const s = STARI[r as Recomandare];
  return s ? (lung ? s.nume : s.scurt) : String(r).replace(/_/g, " ");
}

export function Stare({ r, lung = false, mare = false }: { r: Recomandare | string; lung?: boolean; mare?: boolean }) {
  const s = STARI[r as Recomandare];
  return (
    <span className={`stare ${r} ${mare ? "mare" : ""}`}>
      <i aria-hidden="true">{s?.simbol ?? "·"}</i>
      {numeStare(r, lung)}
    </span>
  );
}
