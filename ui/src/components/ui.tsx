import type { Banda, StatusVerificare } from "../types/api";

const BANDA_LABEL: Record<string, string> = {
  P1: "prioritate 1, acționează azi",
  P2: "prioritate 2, săptămâna aceasta",
  P3: "prioritate 3, poate aștepta",
};

export function BandaBadge({ b }: { b: Banda | string }) {
  return (
    <span className={`badge ${b}`} title={BANDA_LABEL[b]} aria-label={`Banda ${b}, ${BANDA_LABEL[b] ?? ""}`}>
      {b}
    </span>
  );
}

export function StatusTag({ s }: { s: StatusVerificare | string }) {
  return <span className={`tag ${s}`}>{s}</span>;
}

export function Kpi({ l, v, s }: { l: string; v: string | number; s?: string }) {
  return (
    <div className="panel kpi">
      <div className="l">{l}</div>
      <div className="v">{v}</div>
      {s && <div className="s">{s}</div>}
    </div>
  );
}

export function Bar({ v, max = 1, label }: { v: number; max?: number; label?: string }) {
  const w = Math.max(0, Math.min(100, (v / max) * 100));
  return (
    <div className="bar" role="img" aria-label={label ?? `${Math.round(w)} %`}>
      <i style={{ width: `${w}%` }} />
    </div>
  );
}

export function Loading({ err }: { err?: string | null }) {
  if (err)
    return (
      <div className="notice fail" role="alert">
        Datele nu s-au putut încărca ({err}). Verifică dacă serverul rulează și reîncarcă pagina.
      </div>
    );
  return (
    <div className="muted" role="status">
      Se încarcă…
    </div>
  );
}
