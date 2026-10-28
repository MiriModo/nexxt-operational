import { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { getCaz, getDeciziiLocale } from "../api/client";
import { useVerifica } from "../api/hooks";
import { Sla } from "../components/CaseCard";
import { Stare, numeStare } from "../components/Stare";
import { BandaBadge, Loading } from "../components/ui";
import { eticheta, num, pct, pp, ron } from "../format";
import { propunere } from "../propunere";
import type { Caz, CheckInfo, OfferInfo, Reverificare, VerificareRezultat } from "../types/api";

const ORDINE_TREPTE = ["intern", "anaf", "biroul_credit", "crc", "garantie", "eligibilitate"];
const NUME_TREAPTA: Record<string, string> = {
  intern: "la noi", anaf: "ANAF", biroul_credit: "Biroul de Credit", crc: "CRC", garantie: "garanție", eligibilitate: "eligibilitate",
};
const SIMBOL: Record<string, string> = { ok: "✓", avertizare: "!", fail: "✕", indisponibil: "?", neexecutat: "–" };
type Treapta = Reverificare["trepte"][number];

function grupeazaTrepte(check: CheckInfo): Treapta[] {
  return ORDINE_TREPTE.map((t) => ({ treapta: t, rezultate: check.rezultate.filter((r) => r.treapta === t) }))
    .filter((t) => t.rezultate.length)
    .map((t) => ({
      ...t,
      stare: check.oprit_la === t.treapta ? "oprita" : t.rezultate.every((r) => r.status === "neexecutat") ? "neexecutata" : "executata",
    }));
}

function Rand({ r, activa }: { r: VerificareRezultat; activa?: boolean }) {
  return (
    <div className={`check ${r.status} ${activa ? "activa" : ""}`}>
      <span className="st" aria-label={r.status}>
        {SIMBOL[r.status] ?? "·"}
      </span>
      <span>{eticheta(r.id)}</span>
      <span className="ev">
        {r.dovada}
        {r.incertitudine ? ` — ${r.incertitudine}` : ""}
      </span>
    </div>
  );
}

/** Verificările, un rând pe verificare, grupate pe trepte. La „Reverifică” treptele apar una câte una, ca să se vadă
 *  că fluxul se oprește la prima picată și nu mai întreabă sursele de după ea. Cele omise nu se afișează. */
function Verificari({ check, caseId }: { check: CheckInfo; caseId: string }) {
  const verifica = useVerifica(caseId);
  const [trepte, setTrepte] = useState<Treapta[]>(() => grupeazaTrepte(check));
  const [vizibile, setVizibile] = useState<number>(Infinity);
  useEffect(() => {
    if (vizibile === Infinity) return;
    if (vizibile >= trepte.length) {
      setVizibile(Infinity);
      return;
    }
    const t = setTimeout(() => setVizibile(vizibile + 1), 450);
    return () => clearTimeout(t);
  }, [vizibile, trepte.length]);
  const inCurs = verifica.isPending || vizibile !== Infinity;
  const reverifica = () =>
    verifica.mutate(undefined, {
      onSuccess: (r) => {
        setTrepte(r.trepte);
        setVizibile(0);
      },
    });
  const venit = check.concluzii.venit_lunar;

  return (
    <section className="sec" aria-labelledby="verif">
      <div className="actions" style={{ justifyContent: "space-between", marginBottom: 6 }}>
        <h2 id="verif" style={{ margin: 0 }}>
          Verificări
          {check.oprit_la ? ` · oprite la ${NUME_TREAPTA[check.oprit_la] ?? check.oprit_la}` : ""}
          {venit ? ` · venit ${ron(venit)}/lună` : ""}
          {check.concluzii.dti_curent ? `, DTI ${pct(check.concluzii.dti_curent, 0)}` : ""}
        </h2>
        <button type="button" className="btn ghost sm" disabled={inCurs} onClick={reverifica}>
          {inCurs ? "Se verifică…" : "Reverifică"}
        </button>
      </div>
      {verifica.error && <div className="notice fail">{String(verifica.error)}</div>}
      <div className="checks">
        {trepte.map((t, i) => {
          if (vizibile !== Infinity && i > vizibile) return null;
          const activa = vizibile !== Infinity && i === vizibile;
          return (
            <div key={t.treapta}>
              <div className="treapta-h">
                {NUME_TREAPTA[t.treapta] ?? t.treapta}
                {t.stare === "oprita" ? " · oprit aici" : t.stare === "neexecutata" ? " · nu a mai fost nevoie" : ""}
              </div>
              {t.rezultate.map((r) => (
                <Rand key={r.id} r={r} activa={activa} />
              ))}
            </div>
          );
        })}
      </div>
    </section>
  );
}

/** Meniul de intervenții ca grafic cost × p după: punctul ales plin, infezabilele gri, linia țintei punctată. */
function MeniuGrafic({ offer }: { offer: OfferInfo }) {
  const W = 560, H = 230, L = 46, R = 16, T = 14, B = 30;
  const maxCost = Math.max(1, ...offer.interventii.map((i) => i.cost));
  const x = (c: number) => L + (c / maxCost) * (W - L - R);
  const y = (p: number) => T + (1 - Math.max(0, Math.min(1, p))) * (H - T - B);
  const aleasa = offer.interventii.find((i) => i.id === offer.aleasa);
  return (
    <svg className="menu-chart" viewBox={`0 0 ${W} ${H}`} role="img" aria-label="Intervențiile din meniu după cost și probabilitatea de plecare după">
      <line className="ax" x1={L} y1={T} x2={L} y2={H - B} />
      <line className="ax" x1={L} y1={H - B} x2={W - R} y2={H - B} />
      <line className="tinta" x1={L} y1={y(offer.p_tinta)} x2={W - R} y2={y(offer.p_tinta)} />
      <text x={W - R} y={y(offer.p_tinta) - 4} textAnchor="end">
        ținta {pct(offer.p_tinta, 0)}
      </text>
      <text x={L - 6} y={T + 4} textAnchor="end">100 %</text>
      <text x={L - 6} y={H - B + 4} textAnchor="end">0 %</text>
      <text x={L} y={H - 8}>0 lei</text>
      <text x={W - R} y={H - 8} textAnchor="end">{ron(maxCost)}</text>
      <text x={8} y={T + 4} transform={`rotate(-90 8 ${T + 4})`} textAnchor="end">plecare după</text>
      {offer.interventii.map((i) => (
        <circle key={i.id} className={`pt ${i.id === offer.aleasa ? "ales" : ""} ${!i.fezabil ? "infezabil" : ""}`} cx={x(i.cost)} cy={y(i.p_dupa)} r={i.id === offer.aleasa ? 7 : 4.5}>
          <title>
            {i.eticheta}: cost {ron(i.cost)}, plecare după {pct(i.p_dupa, 0)}
            {!i.fezabil ? ` — ${i.motiv_infezabil ?? "infezabil"}` : ""}
          </title>
        </circle>
      ))}
      {aleasa && (
        <text className="lbl" x={Math.min(x(aleasa.cost) + 10, W - R - 120)} y={y(aleasa.p_dupa) - 10}>
          {aleasa.eticheta}
        </text>
      )}
    </svg>
  );
}

export default function CazPage() {
  const { id = "" } = useParams();
  const [c, setC] = useState<Caz | null | undefined>(undefined);
  const [err, setErr] = useState<string | null>(null);
  const [azi, setAzi] = useState("");
  useEffect(() => {
    getCaz(id).then((x) => setC(x ?? null)).catch((e) => setErr(String(e)));
    import("../api/client").then((m) => m.getContext().then((ctx) => setAzi(ctx.azi)).catch(() => undefined));
  }, [id]);
  if (c === undefined) return <Loading err={err} />;
  if (c === null)
    return (
      <div className="notice fail">
        Cazul {id} nu există. <Link to="/cazuri">Înapoi la cazuri</Link>
      </div>
    );

  const { case: cs, client, loan, check, offer, rec } = c;
  const dec = getDeciziiLocale()[cs.case_id];
  const of = rec.oferta;
  const deConfirmat = [
    ...(of?.conditii_de_confirmat ?? []),
    ...(rec.incertitudini ?? []).filter((i) => !(of?.conditii_de_confirmat ?? []).some((cc) => cc.includes(i.text.slice(0, 20)))).map((i) => i.text),
  ];
  const blocat = cs.blocaje.length > 0 || rec.recomandare === "blocat";

  return (
    <>
      <div className="actions" style={{ marginBottom: 10 }}>
        <Link to="/cazuri">← Cazuri</Link>
      </div>

      <div className="strip">
        <BandaBadge b={cs.banda} />
        <div className="who">
          <b>{client.nume}</b>
          <span>
            {cs.case_id} · {eticheta(cs.produs)}
            {loan ? ` · sold ${ron(loan.sold)}` : " · cerere nouă"}
          </span>
        </div>
        <div className="what">
          <Stare r={rec.recomandare} mare lung />
          {rec.interventie && rec.interventie !== rec.recomandare && <span>{eticheta(rec.interventie)}</span>}
        </div>
        {of && (
          <div className="num">
            <b>
              {ron(of.rata_veche)} → {ron(of.rata_noua)}
            </b>
            <span>rata lunară · cost bancă {ron(of.cost_banca)}</span>
          </div>
        )}
        <div className="num">
          <Sla deadline={cs.deadline} azi={azi} />
        </div>
        <div className="go">
          {dec && <span className={`tag ${dec.decizie === "respinge" ? "fail" : "ok"}`}>decis: {dec.decizie}</span>}
          <Link to={`/cazuri/${cs.case_id}/decizie`} className="btn-link">
            <button type="button" className="btn" tabIndex={-1}>
              {dec ? "Revizuiește decizia" : "Ia decizia"}
            </button>
          </Link>
        </div>
      </div>

      {blocat && (
        <div className="notice fail" role="status">
          Caz blocat: {cs.blocaje.length ? cs.blocaje.map(eticheta).join(", ") : rec.motiv}. Nu se comunică nimic clientului până se rezolvă.
        </div>
      )}

      <div className="grid c2">
        <div>
          <section className="sec" aria-labelledby="dece">
            <h2 id="dece">De ce acum</h2>
            <ul className="plain">
              {cs.motive_top3.map((m) => (
                <li key={m}>{m}</li>
              ))}
            </ul>
          </section>

          <section className="sec" aria-labelledby="cine">
            <h2 id="cine">Clientul</h2>
            <dl className="kv">
              <dt>Relația</dt>
              <dd>
                {client.nivel}, client din {client.client_din.slice(0, 4)}
                {offer.legaturi.produse_active.length ? `, ${offer.legaturi.produse_active.map(eticheta).join(", ")}` : ", fără alte produse"}
              </dd>
              {loan && (
                <>
                  <dt>Creditul</dt>
                  <dd>
                    rată {ron(loan.rata)}, dobândă {pp(loan.dobanda)} {loan.tip_dobanda}
                    {loan.expira ? `, fixă până la ${loan.expira}` : ""}
                    {loan.moneda && loan.moneda !== "RON" ? ` (în ${loan.moneda}, sold afișat în lei)` : ""}
                  </dd>
                </>
              )}
              {cs.request_id && (
                <>
                  <dt>Cererea</dt>
                  <dd>{cs.request_id}</dd>
                </>
              )}
            </dl>
          </section>
        </div>

        <section className="sec" aria-labelledby="propune">
          <h2 id="propune">Ce propune agentul</h2>
          <p className="lead">{propunere(rec)}</p>
          {of && (
            <dl className="offer">
              <div>
                <dd>{pp(of.dobanda_noua)}</dd>
                <dt>dobândă nouă, {of.perioada}</dt>
              </div>
              <div>
                <dd>
                  <s>{ron(of.rata_veche)}</s>
                  {ron(of.rata_noua)}
                </dd>
                <dt>rata lunară</dt>
              </div>
              <div>
                <dd>{ron(of.economie_client)}</dd>
                <dt>economia clientului</dt>
              </div>
              <div>
                <dd>{ron(of.cost_banca)}</dd>
                <dt>costul băncii</dt>
              </div>
            </dl>
          )}
          {of?.amanata_buget && (
            <p className="small" style={{ margin: "10px 0 0" }}>
              Amânată: plafonul lunar de retenție e consumat. O poți aproba explicit sau o reiei luna viitoare.
            </p>
          )}
          {(deConfirmat.length > 0 || rec.documente_lipsa.length > 0) && (
            <div className="todo">
              <ul className="plain">
                {deConfirmat.map((t) => (
                  <li key={t}>de confirmat: {t}</li>
                ))}
                {rec.documente_lipsa.map((d) => (
                  <li key={d.tip}>
                    de cerut: {eticheta(d.tip)} ({d.motiv})
                  </li>
                ))}
              </ul>
            </div>
          )}
          {rec.llm && (
            <>
              <p className="small muted" style={{ margin: "12px 0 4px" }}>Textul pentru client</p>
              <pre className="mono" style={{ whiteSpace: "pre-wrap", margin: 0, fontFamily: "inherit", fontSize: 13 }}>
                {rec.llm.text_client}
              </pre>
            </>
          )}
        </section>
      </div>

      <Verificari check={check} caseId={cs.case_id} />

      <details className="more">
        <summary>Cum a ajuns agentul aici</summary>
        <div className="grid c2">
          <div>
            <h2 className="small muted" style={{ fontWeight: 600 }}>Semnalele</h2>
            <ul className="plain small">
              {cs.semnale.map((s) => (
                <li key={s.id}>
                  <b>{eticheta(s.id)}</b> {num(s.scor, 1)} — {s.dovada}
                </li>
              ))}
            </ul>
            <p className="small" style={{ marginTop: 10 }}>
              Dacă pleacă, clientul câștigă <b>{ron(offer.B)}</b> în 3 ani; probabilitatea de plecare acum <b>{pct(offer.p, 0)}</b> (ținta{" "}
              {pct(offer.p_tinta, 0)}); dacă rămâne, valorează <b>{ron(offer.V)}</b>. {offer.motiv_alegere}
            </p>
            <p className="small muted">{rec.motiv}</p>
            {rec.grafic && (
              <p className="small muted">
                Graficul nou: {rec.grafic.nr_rate} rate până în {rec.grafic.ultima_luna}, dobândă totală {ron(rec.grafic.dobanda_totala)}.
              </p>
            )}
          </div>
          <div>
            <h2 className="small muted" style={{ fontWeight: 600 }}>Meniul de intervenții</h2>
            <MeniuGrafic offer={offer} />
            <p className="small muted" style={{ margin: "4px 0 0" }}>
              Aleasă: <b>{numeStare(rec.recomandare)}</b>
              {offer.aleasa ? ` · ${offer.interventii.find((i) => i.id === offer.aleasa)?.eticheta ?? eticheta(offer.aleasa)}` : ""}. Punctele gri deschis
              sunt infezabile (limite BNR / plafoane interne); treci cu mouse-ul pentru motiv.
            </p>
          </div>
        </div>
        <details style={{ marginTop: 8 }}>
          <summary className="small muted">Explicația completă, text</summary>
          <pre className="mono" style={{ whiteSpace: "pre-wrap", margin: "8px 0 0" }}>
            {rec.explicatie}
          </pre>
        </details>
        <p className="small muted mono" style={{ marginBottom: 0 }}>
          {c.consilier ? `consilier ${c.consilier} · ` : ""}
          {c.versiune ? <span title={c.versiune}>versiune {c.versiune.split(" ")[0].replace("cfg:", "cfg ")}</span> : null}
          {offer.model ? ` · p din modelul ${offer.model.nume}` : ""}
        </p>
      </details>
    </>
  );
}
