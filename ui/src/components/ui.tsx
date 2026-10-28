import type { ReactNode } from "react";
import type { Banda } from "../types/api";

const BAND_TITLE: Record<string, string> = { P1: "priority 1 — act today", P2: "priority 2 — this week", P3: "priority 3 — can wait" };

export function Band({ b }: { b: Banda | string }) {
  return (
    <span className={`tag ${b.toLowerCase()}`} title={BAND_TITLE[b]} aria-label={`Band ${b}, ${BAND_TITLE[b] ?? ""}`}>
      {b}
    </span>
  );
}

/** A big figure with a grey unit and a caption (guide A4). Optional link. */
export function Figure({ n, unit, label, to, zero }: { n: ReactNode; unit?: string; label: string; to?: string; zero?: boolean }) {
  const inner = (
    <>
      <b>
        {n}
        {unit && <small>{unit}</small>}
      </b>
      <span>{label}</span>
    </>
  );
  const cls = `figure ${to ? "link" : ""} ${zero ? "zero" : ""}`;
  return to ? (
    <a href={to} className={cls}>
      {inner}
    </a>
  ) : (
    <div className={cls}>{inner}</div>
  );
}

export function Loading({ err }: { err?: string | null }) {
  if (err)
    return (
      <div className="notice fail" role="alert">
        Couldn't load the data ({err}). Check that the server is running and reload.
      </div>
    );
  return (
    <div className="muted" role="status">
      Loading…
    </div>
  );
}
