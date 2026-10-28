import { useContext, useFeedback, useMetrici, useModel } from "../api/hooks";
import { STARI } from "../components/Stare";
import { Kpi, Loading } from "../components/ui";
import { eticheta, num, pct, ron } from "../format";
import type { Recomandare, Strategie } from "../types/api";

/** Bare orizontale fără librărie: eticheta, bara, valoarea. */
function Bare({ rows, max }: { rows: { k: string; v: number; text: string; fel?: string }[]; max?: number }) {
  const m = max ?? Math.max(1, ...rows.map((r) => r.v));
  return (
    <div className="hbars">
      {rows.map((r) => (
        <div key={r.k} style={{ display: "contents" }}>
          <span>{r.k}</span>
          <span className="b">
            <i className={r.fel} style={{ width: `${(r.v / m) * 100}%` }} />
          </span>
          <span className="v">{r.text}</span>
        </div>
      ))}
    </div>
  );
}

const FEL: Record<Recomandare, string> = { oferta_minima: "ok", oferta_produs: "ok", nu_interveni: "", restructurare: "warn", respins_escaladat: "err", blocat: "mute" };

export default function Dashboard() {
  const m = useMetrici();
  const ctx = useContext();
  const model = useModel();
  const fb = useFeedback();
  if (!m.data) return <Loading err={m.error ? String(m.error) : null} />;

  const cv = m.data.cifra_vedeta;
  const strategii: [string, Strategie][] = [["agentul", cv.agent], ...Object.entries(cv.uniform).map(([k, v]) => [`reducere ${k} pp pentru toți`, v] as [string, Strategie])];
  const incalcari = Object.values(m.data.cerinte_dure).reduce((a, b) => a + b, 0);
  const v = ctx.data?.versiune;
  const b = ctx.data?.buget_portofoliu;
  const metrici = model.data?.antrenat?.metrici;
  const W = 420, H = 230, L = 36, R = 10, T = 10, B = 26;

  return (
    <>
      <h1>Rezultatele agentului</h1>
      <div className="grid c4">
        <Kpi l="Economie față de „aceeași reducere pentru toți”" v={ron(cv.economie_ron)} s={cv.economie_pct != null ? `${pct(cv.economie_pct, 0)} mai ieftin, la aceeași rată de rămânere` : ""} />
        <Kpi l="Cazuri unde nu cheltuim nimic" v={pct(m.data.nu_interveni.procent, 0)} s={`${m.data.nu_interveni.nu_interveni} din ${m.data.nu_interveni.total}`} />
        <Kpi l="Interogări externe evitate" v={pct(m.data.interogari_externe.procent, 0)} s={`${m.data.interogari_externe.evitate} din ${m.data.interogari_externe.rulare_tot}`} />
        <Kpi l="Cerințe dure" v={incalcari === 0 ? "0 încălcări" : `${incalcari} încălcări`} s={incalcari === 0 ? "fără oferte către risc, în afara limitelor sau pe cazuri blocate" : Object.entries(m.data.cerinte_dure).filter(([, n]) => n).map(([k, n]) => `${eticheta(k)}: ${n}`).join(", ")} />
      </div>

      <div className="grid c2">
        <section className="panel">
          <h2>Costul retenției: agentul față de o reducere uniformă</h2>
          <Bare rows={strategii.map(([k, s]) => ({ k, v: s.cost, text: `${ron(s.cost)} · rămân ${pct(s.rata_ramanere, 0)}`, fel: k === "agentul" ? "ok" : "" }))} />
          <p className="small muted" style={{ margin: "10px 0 0" }}>{cv.concluzie}</p>
          {b && (
            <>
              <h2 style={{ marginTop: 18 }}>Bugetul lunar de retenție</h2>
              <div className="budget" role="img" aria-label={`folosit ${ron(b.cost_in_buget)} din ${ron(b.plafon_lunar_ron)}`}>
                <i style={{ width: `${Math.min(100, (b.cost_in_buget / b.plafon_lunar_ron) * 100)}%` }} />
              </div>
              <p className="small muted" style={{ margin: 0 }}>
                {ron(b.cost_in_buget)} din {ron(b.plafon_lunar_ron)} · {b.in_buget} oferte în buget, {b.amanate} amânate
              </p>
            </>
          )}
        </section>

        <section className="panel">
          <h2>Ce a recomandat agentul</h2>
          <Bare
            rows={Object.entries(m.data.distributie)
              .sort((a, c) => c[1] - a[1])
              .map(([k, n]) => ({ k: STARI[k as Recomandare]?.nume ?? eticheta(k), v: n, text: String(n), fel: FEL[k as Recomandare] ?? "" }))}
          />
          <p className="small muted" style={{ margin: "10px 0 0" }}>
            Pe etalonul scris de mână: {m.data.recomandari.corecte} din {m.data.recomandari.total} recomandări la fel ca așteptarea.
          </p>
        </section>
      </div>

      <div className="grid c2">
        <section className="panel">
          <h2>Cât de bine prezice modelul plecarea</h2>
          {metrici ? (
            <>
              <p className="small" style={{ marginTop: 0 }}>
                AUC <b>{num(metrici.auc, 2)}</b> · Brier <b>{num(metrici.brier, 3)}</b> · {model.data?.antrenat?.n_test} clienți de test
              </p>
              <svg className="calib" viewBox={`0 0 ${W} ${H}`} role="img" aria-label="Calibrare: probabilitatea prezisă față de rata reală de plecare">
                <line className="ax" x1={L} y1={T} x2={L} y2={H - B} />
                <line className="ax" x1={L} y1={H - B} x2={W - R} y2={H - B} />
                <line className="diag" x1={L} y1={H - B} x2={W - R} y2={T} />
                {metrici.bins.map((bin, i) => {
                  const n = metrici.bins.length;
                  const bw = (W - L - R) / n;
                  const x0 = L + i * bw;
                  const h = (p: number) => (H - T - B) * p;
                  return (
                    <g key={bin.interval}>
                      <rect className="p" x={x0 + 3} y={H - B - h(bin.p_medie)} width={bw / 2 - 4} height={h(bin.p_medie)}>
                        <title>prezis {pct(bin.p_medie, 0)}</title>
                      </rect>
                      <rect className="r" x={x0 + bw / 2 + 1} y={H - B - h(bin.rata_reala)} width={bw / 2 - 4} height={h(bin.rata_reala)}>
                        <title>real {pct(bin.rata_reala, 0)}, n={bin.n}</title>
                      </rect>
                      <text x={x0 + bw / 2} y={H - 8} textAnchor="middle">{bin.interval.split("-")[0]}</text>
                    </g>
                  );
                })}
                <text x={L - 4} y={T + 4} textAnchor="end">100 %</text>
                <text x={L - 4} y={H - B + 4} textAnchor="end">0</text>
              </svg>
              <p className="small muted" style={{ margin: 0 }}>
                Gri: cât a prezis; verde: cât au plecat de fapt; linia punctată: calibrarea perfectă.
              </p>
            </>
          ) : (
            <p className="small muted">Modelul antrenat nu e disponibil; se folosește formula din configurație.</p>
          )}
        </section>

        <section className="panel">
          <h2>Consilierii față de agent</h2>
          {fb.data && fb.data.decizii > 0 ? (
            <>
              <p className="small" style={{ marginTop: 0 }}>
                {fb.data.decizii} decizii, {fb.data.override} schimbate ({pct(fb.data.rata_override, 0)}), {fb.data.rezultate_90_zile.n} cu rezultat la 90 de zile.
              </p>
              {Object.keys(fb.data.pe_interventie).length > 0 && (
                <Bare rows={Object.entries(fb.data.pe_interventie).map(([k, g]) => ({ k: eticheta(k), v: g.rata_override ?? 0, text: `${g.override} din ${g.decizii} schimbate`, fel: "warn" }))} max={1} />
              )}
              {fb.data.propuneri.length > 0 && (
                <ul className="plain small" style={{ marginTop: 10 }}>
                  {fb.data.propuneri.map((p, i) => (
                    <li key={i}>{p.text}</li>
                  ))}
                </ul>
              )}
            </>
          ) : (
            <p className="small muted">Nicio decizie înregistrată încă. Apare aici după primele decizii din ecranul cazului.</p>
          )}
        </section>
      </div>

      {v && (
        <p className="small muted" title={v.scurt}>
          Versiunea configurației {v.config.hash.slice(0, 6)} · model {v.model.versiune ?? v.model.model} · cod {v.cod ?? "—"}. Fiecare decizie poartă versiunea cu care a fost luată.
        </p>
      )}
    </>
  );
}
