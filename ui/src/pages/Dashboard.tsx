import { useEffect, useState } from "react";
import { getMetrici } from "../api/client";
import { Kpi, Loading } from "../components/ui";
import { eticheta, pct, ron } from "../format";
import type { Metrici, Strategie } from "../types/api";

export default function Dashboard() {
  const [m, setM] = useState<Metrici | null>(null);
  const [err, setErr] = useState<string | null>(null);
  useEffect(() => {
    getMetrici().then(setM).catch((e) => setErr(String(e)));
  }, []);
  if (!m) return <Loading err={err} />;

  const cv = m.cifra_vedeta;
  const strategii: [string, Strategie][] = [
    ["agent", cv.agent],
    ...Object.entries(cv.uniform).map(([k, v]) => [`uniform ${k}`, v] as [string, Strategie]),
  ];
  const cerinteOk = Object.values(m.cerinte_dure).every((v) => v === 0);

  return (
    <>
      <h1>Dashboard</h1>
      <div className="grid c4">
        <Kpi
          l="Economie față de politica uniformă"
          v={ron(cv.economie_ron)}
          s={cv.economie_pct != null ? pct(cv.economie_pct) : `${cv.candidati} candidați`}
        />
        <Kpi
          l="Cazuri „nu interveni”"
          v={pct(m.nu_interveni.procent)}
          s={`${m.nu_interveni.nu_interveni} din ${m.nu_interveni.total}`}
        />
        <Kpi
          l="Interogări externe evitate"
          v={pct(m.interogari_externe.procent)}
          s={`${m.interogari_externe.executate} executate din ${m.interogari_externe.rulare_tot} posibile`}
        />
        <Kpi
          l="Acuratețea recomandărilor"
          v={pct(m.recomandari.acuratete)}
          s={`${m.recomandari.corecte} din ${m.recomandari.total} față de etalon`}
        />
      </div>

      <div className="grid c2">
        <section className="panel">
          <h2>Agent vs. politică uniformă</h2>
          <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th>Strategie</th>
                <th className="num">Cost</th>
                <th className="num">Reținuți</th>
                <th className="num">Rată rămânere</th>
                <th className="num">Cost / reținut</th>
              </tr>
            </thead>
            <tbody>
              {strategii.map(([k, s]) => (
                <tr key={k} className={k === "agent" ? "chosen" : undefined}>
                  <td>{k}</td>
                  <td className="num">{ron(s.cost)}</td>
                  <td className="num">{s.retinuti}</td>
                  <td className="num">{pct(s.rata_ramanere)}</td>
                  <td className="num">{ron(s.cost_per_retinut)}</td>
                </tr>
              ))}
            </tbody>
          </table>
          </div>
          <p className="small muted" style={{ marginBottom: 0 }}>
            {cv.concluzie}
          </p>
        </section>

        <section className="panel">
          <h2>Distribuția recomandărilor</h2>
          <table>
            <tbody>
              {Object.entries(m.distributie).map(([k, v]) => (
                <tr key={k}>
                  <td>{eticheta(k)}</td>
                  <td className="num">{v}</td>
                </tr>
              ))}
            </tbody>
          </table>
          <h2 style={{ marginTop: 16 }}>Cerințe dure</h2>
          <div className={`notice ${cerinteOk ? "ok" : "fail"}`}>
            {cerinteOk ? "Nicio încălcare a cerințelor dure." : "Există încălcări ale cerințelor dure, vezi detaliile de mai jos."}
          </div>
          <table>
            <tbody>
              {Object.entries(m.cerinte_dure).map(([k, v]) => (
                <tr key={k}>
                  <td>{eticheta(k)}</td>
                  <td className="num">{v}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </section>
      </div>
    </>
  );
}
