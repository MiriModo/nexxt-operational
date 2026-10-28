import { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { getCaz, getDeciziiLocale } from "../api/client";
import { BandaBadge, Bar, Loading, StatusTag } from "../components/ui";
import { eticheta, num, pct, pp, ron } from "../format";
import type { Caz } from "../types/api";

export default function CazPage() {
  const { id = "" } = useParams();
  const [c, setC] = useState<Caz | null | undefined>(undefined);
  const [err, setErr] = useState<string | null>(null);
  useEffect(() => {
    getCaz(id).then((x) => setC(x ?? null)).catch((e) => setErr(String(e)));
  }, [id]);
  if (c === undefined) return <Loading err={err} />;
  if (c === null)
    return (
      <div className="notice fail">
        Cazul {id} nu există. <Link to="/cazuri">Înapoi la coadă</Link>
      </div>
    );

  const { case: cs, client, loan, check, offer, rec } = c;
  const dec = getDeciziiLocale()[cs.case_id];
  const blocat = cs.blocaje.length > 0 || rec.recomandare === "blocat";

  return (
    <>
      <div className="actions" style={{ marginBottom: 12 }}>
        <Link to="/cazuri">← Coadă</Link>
        <span style={{ flex: 1 }} />
        {dec && (
          <span className={`tag ${dec.decizie === "respinge" ? "fail" : "ok"}`}>
            decizie: {dec.decizie} {dec.interventie ? `→ ${eticheta(dec.interventie)}` : ""} ({dec.sursa})
          </span>
        )}
        <Link to={`/cazuri/${cs.case_id}/decizie`} className="btn-link">
          <button type="button" className="btn" tabIndex={-1}>
            {dec ? "Revizuiește decizia…" : "Ia decizia…"}
          </button>
        </Link>
      </div>

      <h1>
        <BandaBadge b={cs.banda} /> {cs.case_id} · {client.nume}{" "}
        <span className="sub">
          {cs.client_id}, {eticheta(cs.produs)}
          {cs.loan_id ? `, ${cs.loan_id}` : ", cerere nouă"}
        </span>
      </h1>

      {blocat && (
        <div className="notice fail" role="status">
          Caz blocat: {cs.blocaje.length ? cs.blocaje.map(eticheta).join(", ") : rec.motiv}
        </div>
      )}

      <div className="grid c3">
        <section className="panel">
          <h2>Client</h2>
          <dl className="kv">
            <dt>Nivel</dt>
            <dd>{client.nivel}</dd>
            <dt>Tipologie</dt>
            <dd>{eticheta(client.tipologie)}</dd>
            <dt>Client din</dt>
            <dd>{client.client_din}</dd>
            <dt>Produse</dt>
            <dd>{client.produse.length ? client.produse.map((p) => <span key={p} className="tag">{eticheta(p)}</span>) : "–"}</dd>
          </dl>
        </section>
        <section className="panel">
          <h2>Credit</h2>
          {loan ? (
            <dl className="kv">
              <dt>Sold</dt>
              <dd>{ron(loan.sold)}</dd>
              <dt>Rată</dt>
              <dd>{ron(loan.rata)}</dd>
              <dt>Dobândă</dt>
              <dd>
                {pp(loan.dobanda)} {loan.tip_dobanda}
              </dd>
              <dt>Fixă expiră</dt>
              <dd>{loan.expira ?? "–"}</dd>
              <dt>Scadență</dt>
              <dd>{loan.scadenta}</dd>
            </dl>
          ) : (
            <p className="muted" style={{ margin: 0 }}>
              Cerere de credit nou. Clientul nu are un credit existent pe acest caz.
            </p>
          )}
        </section>
        <section className="panel">
          <h2>Prioritizare</h2>
          <dl className="kv">
            <dt>Prioritate</dt>
            <dd>{num(cs.scoruri.prioritate, 3)}</dd>
            <dt>Plecare</dt>
            <dd>{num(cs.scoruri.plecare)}</dd>
            <dt>Valoare</dt>
            <dd>{num(cs.scoruri.valoare)}</dd>
            <dt>Risc credit</dt>
            <dd>{num(cs.scoruri.risc_credit)}</dd>
            <dt>Termen</dt>
            <dd>{cs.deadline}</dd>
            <dt>Acțiune</dt>
            <dd>{eticheta(cs.actiune_propusa)}</dd>
            <dt>Sursă</dt>
            <dd>
              {cs.sursa}
              {cs.request_id ? ` · ${cs.request_id}` : ""}
            </dd>
          </dl>
        </section>
      </div>

      <section className="panel">
        <h2>Semnale</h2>
        {cs.semnale.length === 0 && <span className="muted">Niciun semnal.</span>}
        <table>
          <tbody>
            {cs.semnale.map((s) => (
              <tr key={s.id}>
                <td style={{ width: 220 }}>
                  <b>{eticheta(s.id)}</b>
                  <div className="small muted">{eticheta(s.familie)}</div>
                </td>
                <td style={{ width: 120 }}>
                  <Bar v={s.scor} label={`scor ${num(s.scor)}`} />
                  <span className="small muted">{num(s.scor)}</span>
                </td>
                <td className="small">{s.dovada}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </section>

      <div className="grid c2">
        <section className="panel">
          <h2>Verificări</h2>
          <p className="small muted" style={{ marginTop: 0 }}>
            Motive: {check.motive.map((m) => `${m.motiv} (${m.sursa})`).join("; ") || "–"}. Interogări externe:{" "}
            {check.interogari.executate} executate, {check.interogari.evitate_vs_tot} evitate față de „rulează tot”.
            {check.oprit_la && (
              <>
                {" "}
                <b>Oprit la treapta {check.oprit_la}.</b>
              </>
            )}
          </p>
          <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th>Treaptă</th>
                <th>Verificare</th>
                <th>Status</th>
                <th>Dovadă</th>
              </tr>
            </thead>
            <tbody>
              {check.rezultate.map((r) => (
                <tr key={r.id}>
                  <td className="small muted">{r.treapta}</td>
                  <td>
                    {eticheta(r.id)}
                    {r.externa && <span className="evidence">extern</span>}
                  </td>
                  <td>
                    <StatusTag s={r.status} />
                  </td>
                  <td className="small">
                    {r.dovada}
                    {r.sursa && <span className="evidence">{r.sursa}</span>}
                  </td>
                </tr>
              ))}
              {check.omise.map((r) => (
                <tr key={`om-${r.id}`} className="infeasible">
                  <td className="small">{r.treapta}</td>
                  <td>{eticheta(r.id)}</td>
                  <td>
                    <span className="tag neexecutat">omisă</span>
                  </td>
                  <td className="small">{r.motiv}</td>
                </tr>
              ))}
            </tbody>
          </table>
          </div>
          <h2 style={{ marginTop: 16 }}>Concluzii</h2>
          <dl className="kv">
            <dt>Venit lunar</dt>
            <dd>
              {ron(check.concluzii.venit_lunar)}{" "}
              <span className="small muted">(ANAF {ron(check.concluzii.venit_lunar_anaf)})</span>
            </dd>
            <dt>DTI curent</dt>
            <dd>{pct(check.concluzii.dti_curent)}</dd>
            <dt>LTV actual</dt>
            <dd>{check.concluzii.ltv_actual != null ? pct(check.concluzii.ltv_actual) : "–"}</dd>
            <dt>Salariu la altă bancă</dt>
            <dd>{check.concluzii.salariu_la_alta_banca ? "da" : "nu"}</dd>
            <dt>Interogări BC</dt>
            <dd>{check.concluzii.interogari_bc}</dd>
          </dl>
        </section>

        <section className="panel">
          <h2>Model de retenție</h2>
          <div className="grid c3" style={{ gap: 8, marginBottom: 10 }}>
            <div>
              <div className="small muted">B · câștigul clientului dacă pleacă</div>
              <b>{ron(offer.B)}</b>
            </div>
            <div>
              <div className="small muted">p · probabilitate de plecare</div>
              <b>{pct(offer.p)}</b> <span className="small muted">țintă {pct(offer.p_tinta)}</span>
            </div>
            <div>
              <div className="small muted">V · valoarea dacă rămâne</div>
              <b>{ron(offer.V)}</b>
            </div>
          </div>
          <p className="small muted" style={{ marginTop: 0 }}>
            Dobândă rămasă la noi {ron(offer.B_detalii.dobanda_la_noi)} vs. la piață {ron(offer.B_detalii.dobanda_piata)} (
            {pp(offer.B_detalii.dobanda_pct_piata)}), diferență brută {ron(offer.B_detalii.B_brut)}, cost mutare {ron(offer.B_detalii.cost_mutare)},
            orizont {offer.B_detalii.orizont_luni} luni din {offer.B_detalii.luni_ramase} rămase.
            Legături: scor {num(offer.legaturi.scor)} ({offer.legaturi.suficiente_pentru_oferta ? "suficiente" : "insuficiente"} pentru ofertă),
            vechime {num(offer.legaturi.vechime_ani, 1)} ani, produse active {offer.legaturi.produse_active.map(eticheta).join(", ") || "niciunul"}.
          </p>
          {offer.model && (
            <p className="small muted" style={{ marginTop: 0 }}>
              p vine din modelul <b>{offer.model.nume}</b>
              {offer.model.nume === "antrenat" ? ` (${offer.model.versiune})` : ""}
              {offer.contributii && offer.contributii.length > 0 && (
                <>
                  {" "}· contribuții pe logit:{" "}
                  {offer.contributii.map(([f, v]) => `${eticheta(f)} ${v >= 0 ? "+" : ""}${num(v)}`).join(", ")}
                </>
              )}
            </p>
          )}
          <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th>Intervenție</th>
                <th className="num">Cost</th>
                <th className="num">B după</th>
                <th className="num">p după</th>
                <th>Observații</th>
              </tr>
            </thead>
            <tbody>
              {offer.interventii.map((i) => (
                <tr key={i.id} className={i.id === offer.aleasa ? "chosen" : !i.fezabil ? "infeasible" : undefined}>
                  <td>
                    {i.eticheta}
                    {i.id === offer.aleasa && <span className="evidence">aleasă</span>}
                  </td>
                  <td className="num">{ron(i.cost)}</td>
                  <td className="num">{ron(i.B_dupa)}</td>
                  <td className="num">{pct(i.p_dupa)}</td>
                  <td className="small">
                    {!i.fezabil ? i.motiv_infezabil ?? "infezabil" : i.respecta_tinta ? (i.merita ? "respectă ținta, merită" : "respectă ținta, nu merită") : "sub țintă"}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          </div>
          <p className="small" style={{ marginBottom: 0 }}>
            <b>De ce:</b> {offer.motiv_alegere}
          </p>
        </section>
      </div>

      <section className="panel">
        <h2>
          Recomandare: <span className="tag">{eticheta(rec.recomandare)}</span> {rec.eticheta}
        </h2>
        <p style={{ marginTop: 0 }}>{rec.motiv}</p>
        <div className="grid c2">
          <div>
            {rec.oferta ? (
              <dl className="kv">
                <dt>Tip</dt>
                <dd>{eticheta(rec.oferta.tip)}</dd>
                <dt>Dobândă nouă</dt>
                <dd>
                  {pp(rec.oferta.dobanda_noua)} · {rec.oferta.perioada}
                </dd>
                <dt>Rată</dt>
                <dd>
                  {ron(rec.oferta.rata_veche)} → <b>{ron(rec.oferta.rata_noua)}</b> ({rec.oferta.luni_noi} luni)
                </dd>
                <dt>Cost bancă</dt>
                <dd>{ron(rec.oferta.cost_banca)}</dd>
                <dt>Economie client</dt>
                <dd>{ron(rec.oferta.economie_client)}</dd>
              </dl>
            ) : (
              <span className="muted">Fără ofertă concretă.</span>
            )}
            {rec.documente_lipsa.length > 0 && (
              <>
                <h2 style={{ marginTop: 16 }}>Documente lipsă</h2>
                <ul className="small" style={{ margin: 0, paddingLeft: 18 }}>
                  {rec.documente_lipsa.map((d) => (
                    <li key={d.tip}>
                      <b>{eticheta(d.tip)}</b>: {d.motiv}
                    </li>
                  ))}
                </ul>
              </>
            )}
          </div>
          <div>
            {rec.grafic && (
              <>
                <div className="small muted" style={{ marginBottom: 6 }}>
                  Grafic nou: {rec.grafic.nr_rate} rate până în {rec.grafic.ultima_luna}, dobândă totală {ron(rec.grafic.dobanda_totala)}, total de plată{" "}
                  {ron(rec.grafic.total_de_plata)}
                </div>
                <div className="table-wrap">
                <table>
                  <thead>
                    <tr>
                      <th>Luna</th>
                      <th className="num">Rată</th>
                      <th className="num">Dobândă</th>
                      <th className="num">Principal</th>
                      <th className="num">Sold rămas</th>
                    </tr>
                  </thead>
                  <tbody>
                    {rec.grafic.primele_luni.map((r) => (
                      <tr key={r.nr}>
                        <td>{r.luna}</td>
                        <td className="num">{ron(r.rata, 2)}</td>
                        <td className="num">{ron(r.dobanda, 2)}</td>
                        <td className="num">{ron(r.principal, 2)}</td>
                        <td className="num">{ron(r.sold_ramas)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
                </div>
              </>
            )}
          </div>
        </div>
        <details style={{ marginTop: 12 }}>
          <summary className="small">Arată explicația completă</summary>
          <pre className="mono" style={{ whiteSpace: "pre-wrap", margin: "8px 0 0" }}>
            {rec.explicatie}
          </pre>
        </details>
      </section>
    </>
  );
}
