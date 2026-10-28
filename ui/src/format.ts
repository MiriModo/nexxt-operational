export const ron = (v: number | null | undefined, d = 0) =>
  v == null
    ? "–"
    : new Intl.NumberFormat("ro-RO", { maximumFractionDigits: d, minimumFractionDigits: d }).format(v) + " lei";

export const pct = (v: number | null | undefined, d = 1) => (v == null ? "–" : (v * 100).toFixed(d) + " %");

/** Valoare deja exprimată în procente (ex. dobândă 4.9). */
export const pp = (v: number | null | undefined, d = 2) => (v == null ? "–" : v.toFixed(d) + " %");

export const num = (v: number | null | undefined, d = 2) => (v == null ? "–" : v.toFixed(d));

export const zile = (deadline: string, azi: string) =>
  Math.round((new Date(deadline).getTime() - new Date(azi).getTime()) / 86400000);

export const eticheta = (s: string | null | undefined) => (s ?? "–").replace(/_/g, " ");
