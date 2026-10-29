// Number and date formatting for the English interface. Amounts are RON (the data is a Romanian portfolio).
export const ron = (v: number | null | undefined, d = 0) =>
  v == null ? "–" : new Intl.NumberFormat("en-US", { maximumFractionDigits: d, minimumFractionDigits: d }).format(v) + " RON";

export const pct = (v: number | null | undefined, d = 1) => (v == null ? "–" : (v * 100).toFixed(d) + " %");

/** Value already in percent (e.g. interest 4.9). */
export const pp = (v: number | null | undefined, d = 2) => (v == null ? "–" : v.toFixed(d) + " %");

export const num = (v: number | null | undefined, d = 2) => (v == null ? "–" : v.toFixed(d));

export const int = (v: number | null | undefined) => (v == null ? "–" : new Intl.NumberFormat("en-US").format(v));

export const days = (deadline: string, today: string) =>
  Math.round((new Date(deadline).getTime() - new Date(today).getTime()) / 86400000);

export const date = (iso: string) => new Intl.DateTimeFormat("en-GB", { day: "numeric", month: "short", year: "numeric" }).format(new Date(iso));

/** "2028-01-03" → "January 2028". */
export const monthYear = (iso: string) =>
  new Intl.DateTimeFormat("en-GB", { month: "long", year: "numeric" }).format(new Date(iso.length === 10 ? iso + "T12:00:00" : iso));
export const dateLong = (iso: string) =>
  new Intl.DateTimeFormat("en-GB", { weekday: "long", day: "numeric", month: "long" }).format(new Date(iso.length === 10 ? iso + "T12:00:00" : iso));

/** Backend ids (snake_case) shown as words. The backend's own sentences stay as produced. */
export const label = (s: string | null | undefined) => (s ?? "–").replace(/_/g, " ");

/** Compact amount for big figures: 3,188,389 → { n: "3.19", unit: "M RON" }. */
export const ronShort = (v: number | null | undefined): { n: string; unit: string } => {
  if (v == null) return { n: "–", unit: "" };
  const a = Math.abs(v);
  if (a >= 1e6) return { n: (v / 1e6).toFixed(2), unit: "M RON" };
  if (a >= 1e4) return { n: (v / 1e3).toFixed(1), unit: "k RON" };
  return { n: new Intl.NumberFormat("en-US").format(Math.round(v)), unit: "RON" };
};
