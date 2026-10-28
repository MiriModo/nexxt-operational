import { useContext, useFeedback, useMetrici, useModel } from "../api/hooks";
import { Kpi, Loading } from "../components/ui";
import { eticheta, num, pct, ron } from "../format";
import type { Strategie } from "../types/api";

export default function Dashboard() {
  const m = useMetrici();
  const ctx = useContext();
  const model = useModel();
  const fb = useFeedback();
  if (!m.data) return <Loading err={m.error ? String(m.error) : null} />;

  const cv = m.data.cifra_vedeta;
  const strategii: [string, Strategie][] = [
    ["agent", cv.agent],
    ...Object.entries(cv.uniform).map(([k, v]) => [`uniform ${k}`, v] as [string, Strategie]),
  ];
  const cerinteOk = Object.values(m.data.cerinte_dure).every((v) => v === 0);
  const v = ctx.data?.versiune;
  const b = ctx.data?.buget_portofoliu;
  const antrenat = model.data?.antrenat;
  const metrici = antrenat?.metrici;

  return (
    <>
      <h1>Dashboard</h1>
      <div className="grid c4">
        <Kpi l="Economie față de politica uniformă" v={ron(cv.economie_ron)} s={cv.economie_pct != null ? pct(cv.economie_pct) : `${cv.candidati} candidați`} />
        <Kpi l="Cazuri „nu interveni”" v={pct(m.data.nu_interveni.procent)} s={`${m.data.nu_interveni.nu_interveni} din ${m.data.nu_interveni.total}`} />
        <Kpi l="Interogări externe evitate" v={pct(m.data.interogari_externe.procent)} s={`${m.data.interogari_externe.executate} executate din ${m.data.interogari_externe.rulare_tot} posibile`} />
        <Kpi l="Acuratețea recomandărilor" v={pct(m.data.recomandari.acuratete)} s={`${m.data.recomandari.corecte} din ${m.data.recomandari.total} față de etalon`} />
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
          <p className="small muted" style={{ marginBottom: 0 }}>{cv.concluzie}</p>
          {b && (
            <>
              <h2 style={{ marginTop: 16 }}>Buget de retenție pe portofoliu</h2>
              <p className="small" style={{ margin: 0 }}>
                Plafon lunar {ron(b.plafon_lunar_ron)}: <b>{b.in_buget}</b> din {b.oferte} oferte în buget ({ron(b.cost_in_buget)} din {ron(b.cost_total_oferte)}),{" "}
                {b.amanate} amânate („peste plafon luna asta”). Ordonare: {eticheta(b.ordonare)}.
              </p>
            </>
          )}
        </section>

        <section className="panel">
          <h2>Distribuția recomandărilor</h2>
          <table>
            <tbody>
              {Object.entries(m.data.distributie).map(([k, v]) => (
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
              {Object.entries(m.data.cerinte_dure).map(([k, v]) => (
                <tr key={k}>
                  <td>{eticheta(k)}</td>
                  <td className="num">{v}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </section>
      </div>

      <div className="grid c2">
        <section className="panel">
          <h2>Modelul de churn</h2>
          {model.data ? (
            <>
              <p className="small" style={{ marginTop: 0 }}>
                Activ: <b>{model.data.activ.model}</b> {model.data.activ.versiune ?? ""}
                {model.data.activ.hash ? <span className="evidence">hash {model.data.activ.hash}</span> : null}
              </p>
              {metrici ? (
                <>
                  <div className="grid c3" style={{ gap: 8 }}>
                    <div>
                      <div className="small muted">AUC</div>
                      <b>{num(metrici.auc, 3)}</b>
                    </div>
                    <div>
                      <div className="small muted">Brier (mai mic = mai bine calibrat)</div>
                      <b>{num(metrici.brier, 3)}</b>
                    </div>
                    <div>
                      <div className="small muted">ECE</div>
                      <b>{num(metrici.ece, 3)}</b>
                    </div>
                  </div>
                  <div className="small muted" style={{ marginTop: 8 }}>
                    Calibrare pe test ({antrenat?.n_test} rânduri): gri = probabilitatea prezisă, verde = rata reală de plecare, pe 10 intervale.
                  </div>
                  <div className="calib" role="img" aria-label="Curba de calibrare a modelului de churn">
                    {metrici.bins.map((bin) => (
                      <div key={bin.interval} title={`${bin.interval}: prezis ${pct(bin.p_medie)}, real ${pct(bin.rata_reala)}, n=${bin.n}`}>
                        <div style={{ display: "flex", gap: 2, alignItems: "flex-end", height: "100%", width: "100%" }}>
                          <div className="b p" style={{ height: `${bin.p_medie * 100}%` }} />
                          <div className="b r" style={{ height: `${bin.rata_reala * 100}%` }} />
                        </div>
                        <span className="lbl">{bin.interval.split("-")[0]}</span>
                      </div>
                    ))}
                  </div>
                  {antrenat?.coeficienti && (
                    <p className="small" style={{ marginBottom: 0 }}>
                      Coeficienți principali: {Object.entries(antrenat.coeficienti).slice(0, 6).map(([f, c]) => `${eticheta(f)} ${c >= 0 ? "+" : ""}${num(c)}`).join(", ")}
                    </p>
                  )}
                  <p className="small muted" style={{ marginBottom: 0 }}>
                    Antrenat pe {antrenat?.n} rânduri sintetice ({antrenat?.antrenat_la?.slice(0, 10)}); valoarea reală vine din rezultatele la 90 de zile.
                  </p>
                </>
              ) : (
                <p className="small muted">Modelul antrenat nu e disponibil (rulează <code>python -m retailagent.churn.train</code>); se folosește sigmoidul.</p>
              )}
            </>
          ) : (
            <p className="small muted">Metadatele modelului vin prin API.</p>
          )}
        </section>

        <section className="panel">
          <h2>Feedback: agent vs. consilier vs. rezultat</h2>
          {fb.data ? (
            fb.data.decizii === 0 ? (
              <p className="small muted">Nicio decizie înregistrată încă. Deciziile luate din ecranul „Decizie” apar aici.</p>
            ) : (
              <>
                <p className="small" style={{ marginTop: 0 }}>
                  <b>{fb.data.decizii}</b> decizii, <b>{fb.data.override}</b> override-uri ({pct(fb.data.rata_override)}),{" "}
                  {fb.data.rezultate_90_zile.n} rezultate la 90 de zile.
                </p>
                {Object.keys(fb.data.pe_interventie).length > 0 && (
                  <table>
                    <thead>
                      <tr>
                        <th>Intervenția agentului</th>
                        <th className="num">Decizii</th>
                        <th className="num">Override</th>
                      </tr>
                    </thead>
                    <tbody>
                      {Object.entries(fb.data.pe_interventie).map(([k, g]) => (
                        <tr key={k}>
                          <td>{eticheta(k)}</td>
                          <td className="num">{g.decizii}</td>
                          <td className="num">{g.override} ({pct(g.rata_override, 0)})</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                )}
                {Object.keys(fb.data.rezultate_90_zile.pe_interventie).length > 0 && (
                  <>
                    <h2 style={{ marginTop: 12 }}>Rămânere reală vs. prezisă</h2>
                    <table>
                      <tbody>
                        {Object.entries(fb.data.rezultate_90_zile.pe_interventie).map(([k, g]) => (
                          <tr key={k}>
                            <td>{eticheta(k)}</td>
                            <td className="num">real {pct(g.rata_ramanere_reala, 0)}</td>
                            <td className="num">prezis {g.rata_ramanere_prezisa != null ? pct(g.rata_ramanere_prezisa, 0) : "–"}</td>
                            <td className="num">n={g.n}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </>
                )}
                <h2 style={{ marginTop: 12 }}>Propuneri</h2>
                <ul className="small" style={{ margin: 0, paddingLeft: 18 }}>
                  {fb.data.propuneri.map((p, i) => (
                    <li key={i}>{p.text}</li>
                  ))}
                </ul>
              </>
            )
          ) : (
            <p className="small muted">Feedback-ul vine prin API.</p>
          )}
        </section>
      </div>

      {v && (
        <section className="panel">
          <h2>Versiune</h2>
          <p className="small mono" style={{ margin: 0 }}>
            config {v.config.hash} · model {v.model.model}
            {v.model.hash ? ` ${v.model.hash}` : ""} · cod {v.cod ?? "—"} · prompturi {v.prompturi ? "da" : "—"}
          </p>
          <p className="small muted" style={{ marginBottom: 0 }}>
            Fiecare recomandare și fiecare rând de audit poartă această versiune, ca o decizie de ieri să poată fi reprodusă după ce se schimbă pragurile sau modelul.
          </p>
        </section>
      )}
    </>
  );
}
