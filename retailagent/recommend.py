"""Recomandarea finală pentru consilier (MODEL_FINAL §4): una din cele 6 stări, oferta cu graficul ei,
documentele lipsă, explicația în română cu cifre și logul de audit.

    nu_interveni | oferta_minima | oferta_produs | restructurare | respins_escaladat | blocat

`blocat` nu e în lista din MODEL_FINAL: e starea cazurilor oprite de un task de proces (CI expirată etc.),
care nu primesc nicio decizie comercială până la rezolvare.

    python -m retailagent.recommend [--case Q0001]     # out/recommendations.json + out/audit.jsonl
"""
from __future__ import annotations

import argparse
import time
from collections import Counter
from datetime import date, timedelta
from pathlib import Path

from .checks import Mocks, load_mocks, run_all_checks
from .common import CONFIG_DIR, DATA_DIR, OUT_DIR, fmt_ron, log_event, month_key, parse_date, setup_console, shift_month, write_json
from .config_loader import Config
from .finance import grafic, luni_ramase, rata_anuitate, rata_in_luna, segmente_credit
from .queue import run_pipeline
from .retention import build_offers

STARI = ("nu_interveni", "oferta_minima", "oferta_produs", "restructurare", "respins_escaladat", "blocat")
ETICHETA = {"nu_interveni": "nu interveni", "oferta_minima": "ofertă minimă", "oferta_produs": "ofertă + produs",
            "restructurare": "restructurare", "respins_escaladat": "respins / escaladat", "blocat": "blocat (task de proces)"}
CERERI_PRODUS_NOU = ("credit_nou", "majorare_limita_card")


# ---------------------------------------------------------------- oferta + grafic

def _grafic(sold: float, segmente: list[tuple[int, float]], today: date) -> dict:
    rows = grafic(sold, segmente, shift_month(month_key(today), 1))
    return {"primele_luni": rows[:12], "nr_rate": len(rows), "dobanda_totala": round(sum(r["dobanda"] for r in rows), 2),
            "total_de_plata": round(sum(r["rata"] for r in rows), 2), "ultima_luna": rows[-1]["luna"] if rows else None}


def oferta_din_interventie(loan: dict, it: dict, today: date, market: dict, cfg: Config) -> tuple[dict, dict] | tuple[None, None]:
    """Oferta concretă (dobândă nouă, rată nouă, perioadă) + graficul, pentru intervenția aleasă."""
    luni = luni_ramase(loan, today)
    seg = segmente_credit(loan, today, market)
    # „rata veche” = ce plătește clientul azi (prima lună a scenariului „rămâi așa”). Dacă perioada fixă curentă se
    # termină înainte de scadență, rata de după (recalculată pe soldul de atunci, ca la bancă) apare separat.
    # Rata din contract, când dobânda de azi e cea din contract (altfel, rata recalculată la dobânda de azi).
    contract = loan.get("rata_lunara")
    rata_veche = (float(contract) if contract and seg[0][1] == float(loan["dobanda_curenta"])
                  else rata_in_luna(loan["sold_ramas"], seg, 1))
    stare_actuala = {}
    if len(seg) > 1:
        stare_actuala = {"rata_dupa_fixa": round(rata_in_luna(loan["sold_ramas"], seg, seg[0][0] + 1), 2),
                         "fixa_expira": loan.get("dobanda_fixa_expira_la"), "dobanda_dupa_fixa": seg[-1][1]}
    orizont = {"economie_orizont_luni": min(luni, round(cfg.retention.orizont_ani * 12))}
    d = it.get("detalii") or {}
    tip = it["tip"]
    if tip == "fix_piata":
        fix, k = d["dobanda_fixa_noua"], min(luni, d["ani"] * 12)
        post = round(market["ircc"] + loan["marja"], 2)
        seg_nou = [(k, fix)] + ([(luni - k, post)] if luni > k else [])
        oferta = {"tip": tip, "dobanda_noua": fix, "perioada": f"{d['ani']} ani", "dupa_perioada": f"IRCC + {loan['marja']:.2f} pp = {post:.2f}%"}
    elif tip in ("reducere_marja", "pachet"):
        seg_nou = [(l, max(0.0, r - (loan["marja"] - d["marja_noua"]))) for l, r in seg]
        oferta = {"tip": tip, "dobanda_noua": seg_nou[-1][1], "marja_noua": d["marja_noua"], "perioada": "toată durata rămasă"}
        if tip == "pachet":
            oferta["conditie"] = "salariul încasat la noi (cont de salariu deschis / mutat în 60 de zile)"
    elif tip == "comision":
        seg_nou = seg
        oferta = {"tip": tip, "dobanda_noua": seg[-1][1], "perioada": "—", "scutire_ron": it["cost"]}
    elif tip == "restructurare":
        C = cfg.constraints.restructurare
        if it["id"] == "ajustare_maturitate":
            luni_noi = luni + C.prelungire_maxima_luni
            seg_nou = [(luni_noi, seg[-1][1])]
            oferta = {"tip": tip, "dobanda_noua": seg[-1][1], "perioada": f"maturitate +{C.prelungire_maxima_luni} luni",
                      "luni_noi": luni_noi}
        else:
            pauza = C.pauza_rata_maxima_luni
            sold_cap = loan["sold_ramas"] * (1 + seg[-1][1] / 100 / 12) ** pauza      # dobânda se capitalizează
            seg_nou = [(luni, seg[-1][1])]
            oferta = {"tip": tip, "dobanda_noua": seg[-1][1], "perioada": f"pauză {pauza} luni, apoi {luni} rate",
                      "sold_dupa_pauza": round(sold_cap, 2)}
            g = _grafic(sold_cap, seg_nou, today + timedelta(days=30 * pauza))
            oferta.update(rata_veche=round(rata_veche, 2), rata_noua=round(g["primele_luni"][0]["rata"], 2),
                          cost_banca=it["cost"], economie_client=0.0, **stare_actuala)
            return oferta, g
    else:
        return None, None
    g = _grafic(loan["sold_ramas"], seg_nou, today)
    oferta.update(rata_veche=round(rata_veche, 2), rata_noua=round(g["primele_luni"][0]["rata"], 2),
                  cost_banca=it["cost"], economie_client=it.get("castig_client", 0.0), **orizont, **stare_actuala)
    return oferta, g


def oferta_produs_nou(cerere: dict, concluzii: dict, today: date, market: dict) -> tuple[dict, dict | None]:
    produs = cerere["detalii"].get("produs_vizat") or cerere.get("produs")
    suma = cerere["detalii"].get("suma") or 0
    if produs == "card_credit":
        return {"tip": "produs_nou", "produs": produs, "suma": suma, "dobanda_noua": market["dobanda_piata_card"],
                "perioada": "revolving", "rata_noua": concluzii.get("rata_noua"), "cost_banca": 0.0, "economie_client": 0.0}, None
    if produs in ("ipotecar", "imobiliar"):
        dob, luni = float(market["dobanzi_piata"][produs]["fixa_3_ani"]), 300
    else:
        dob, luni = float(market["dobanda_piata_nevoi_personale"]), 60
    g = _grafic(suma, [(luni, dob)], today) if suma else None
    return {"tip": "produs_nou", "produs": produs, "suma": suma, "dobanda_noua": dob, "perioada": f"{luni // 12} ani",
            "rata_noua": g["primele_luni"][0]["rata"] if g else None, "cost_banca": 0.0, "economie_client": 0.0}, g


# ---------------------------------------------------------------- documente lipsă

def documente_lipsa(recomandare: str, client: dict, loan: dict | None, docs: list[dict], today: date, cfg: Config) -> list[dict]:
    out = []
    for rule in cfg.checks.documente_necesare.get(recomandare, []):
        if rule.tipologii and client.get("tipologie_declarata") not in rule.tipologii:
            continue
        if rule.produse and (loan is None or loan["produs"] not in rule.produse):
            continue
        cand = [d for d in docs if d["tip"] == rule.tip and (not rule.produse or d.get("referinta") in (None, loan["loan_id"]))]
        if not cand:
            out.append({"tip": rule.tip, "motiv": "lipsește din dosar"})
            continue
        d = max(cand, key=lambda x: x["data_emitere"])
        if rule.valabil and d.get("valabil_pana") and parse_date(d["valabil_pana"]) < today:
            out.append({"tip": rule.tip, "motiv": f"expirat la {d['valabil_pana']}"})
        elif rule.max_zile is not None and (today - parse_date(d["data_emitere"])).days > rule.max_zile:
            out.append({"tip": rule.tip, "motiv": f"emis la {d['data_emitere']}, mai vechi de {rule.max_zile} zile"})
    return out


# ---------------------------------------------------------------- decizia

def recomanda(case: dict, check: dict, offer: dict, client: dict, loan: dict | None, cereri: list[dict], docs: list[dict],
              today: date, market: dict, cfg: Config) -> dict:
    prag = cfg.priority.risc_credit.blocheaza_retentia_daca
    risc = case["scoruri"]["risc_credit"]
    by_id = {i["id"]: i for i in offer["interventii"]}
    ales = by_id.get(offer["interventie_aleasa"]) if offer["interventie_aleasa"] else None
    cerere_nou = next((c for c in cereri if c["tip"] in CERERI_PRODUS_NOU), None)
    oferta = g = None
    interventie = None
    incertitudini = incertitudini_caz(case, check, cereri, cfg)
    motive_caz = {c["tip"] for c in cereri} | {s["id"] for s in case["semnale"]}
    critice = [i for i in incertitudini if _critica(i["id"], motive_caz, cfg)]

    if case["blocaje"]:
        rec, motiv = "blocat", f"task de proces activ: {', '.join(case['blocaje'])}; nicio decizie comercială până la rezolvare"
        if any(s["id"] == "flag_blocant" for s in case["semnale"]):
            motiv += "; flag blocant (PEP / fraudă / decedat): nicio comunicare comercială, aprobare specială"
    elif critice:
        rec, motiv = "respins_escaladat", "escaladare la om: " + "; ".join(i["text"] for i in critice)
    elif check.get("verificare_picata"):
        picata = next(x for x in check["rezultate"] if x["id"] == check["verificare_picata"])
        rec, motiv = "respins_escaladat", f"verificarea {picata['id']} a picat ({picata['sursa'] or 'intern'}): {picata['dovada']}"
    elif risc >= prag or any(c["tip"] == "restructurare" for c in cereri):
        rec = "restructurare"
        interventie = offer["interventie_aleasa"]
        motiv = (f"risc de credit {risc:.2f} ≥ {prag:.2f}: fără ofertă de retenție" if risc >= prag
                 else "clientul a cerut restructurare")
        if ales and ales["tip"] == "restructurare" and loan:
            oferta, g = oferta_din_interventie(loan, ales, today, market, cfg)
            motiv += f"; propunere: {ales['eticheta']}"
        else:
            rec, motiv = "respins_escaladat", motiv + "; nicio restructurare fezabilă → escaladare"
    elif cerere_nou:
        if check["concluzii"].get("eligibil"):
            rec = "oferta_minima"
            oferta, g = oferta_produs_nou(cerere_nou, check["concluzii"], today, market)
            motiv = (f"cerere {cerere_nou['tip']} eligibilă: DTI după rata nouă "
                     f"{check['concluzii'].get('dti_dupa') or 0:.0%}; ofertă la grila standard")
        else:
            rec, motiv = "respins_escaladat", f"neeligibil: {check['concluzii'].get('motiv_ineligibil') or 'eligibilitatea nu a putut fi stabilită'}"
    elif ales is None or ales["tip"] in ("nimic", "informare"):
        rec = "nu_interveni"
        interventie = offer["interventie_aleasa"]
        motiv = offer["motiv_alegere"] + ("" if ales is None or ales["tip"] == "nimic" else "; doar informare + simulare")
    else:
        rec = "oferta_produs" if ales["tip"] == "pachet" else "oferta_minima"
        interventie = ales["id"]
        motiv = offer["motiv_alegere"]
        if loan:
            oferta, g = oferta_din_interventie(loan, ales, today, market, cfg)

    if oferta is not None and incertitudini:
        # degradare controlată: oferta rămâne, dar condiționată de lămurirea incertitudinilor
        oferta["conditii_de_confirmat"] = [i["text"] for i in incertitudini]
    lipsa = documente_lipsa(rec, client, loan, docs, today, cfg)
    r = {"case_id": case["case_id"], "client_id": case["client_id"], "loan_id": case["loan_id"], "produs": case["produs"],
         "recomandare": rec, "eticheta": ETICHETA[rec], "interventie": interventie, "motiv": motiv,
         "incertitudini": incertitudini,
         "oferta": oferta, "grafic": g, "documente_lipsa": lipsa,
         "verificari": {"oprit_la": check.get("oprit_la"), "verificare_picata": check.get("verificare_picata"),
                        "executate": check["interogari_externe"].get("executate", 0),
                        "evitate": check["interogari_externe"]["rulare_tot"] - check["interogari_externe"].get("executate", 0),
                        "avertizari": [x["id"] for x in check["rezultate"] if x["status"] == "avertizare"]},
         "retentie": {"B": offer["B"], "p": offer["p"], "p_dupa": offer["p_dupa"], "V": offer["V"], "cost": offer["cost"],
                      "legaturi": offer["legaturi"]["scor"]},
         "creat_la": f"{today.isoformat()}T00:00:00"}
    r["explicatie"] = explicatie(r, case, check, offer, client)
    return r


def incertitudini_caz(case: dict, check: dict, cereri: list[dict], cfg: Config) -> list[dict]:
    """Situațiile neașteptate ale cazului: din verificări (surse indisponibile / contradictorii, refinanțare externă,
    fără cont) + reguli pe caz (cerere duplicată, semnale contradictorii). Fiecare are id (checks.yaml) și text."""
    out = [dict(i) for i in check.get("incertitudini") or []]
    prag = cfg.priority.risc_credit.blocheaza_retentia_daca
    for c in cereri:
        if c.get("duplicate"):
            out.append({"id": "cerere_duplicata", "text": f"cerere duplicată: {', '.join(c['duplicate'])} repetă {c['request_id']} "
                                                           f"(se tratează o singură dată)"})
    plecare_tare = [s["id"] for s in case["semnale"] if s["familie"] == "plecare" and s["scor"] >= 0.8
                    and s["id"] in cfg.priority.semnale_active]
    if case["scoruri"]["risc_credit"] >= prag and plecare_tare:
        out.append({"id": "semnale_contradictorii", "text": f"semnale contradictorii: risc de credit {case['scoruri']['risc_credit']:.2f} "
                                                             f"și semnal activ de plecare ({', '.join(plecare_tare)}); riscul are prioritate, "
                                                             "retenția se reia după stabilizare"})
    return out


def _critica(iid: str, motive: set[str], cfg: Config) -> bool:
    reguli = cfg.checks.incertitudini_critice
    if iid not in reguli:
        return False
    return not reguli[iid] or bool(motive & set(reguli[iid]))


def explicatie(r: dict, case: dict, check: dict, offer: dict, client: dict) -> str:
    L = [f"Recomandare: {ETICHETA[r['recomandare']].upper()} — {r['motiv']}."]
    if r.get("incertitudini"):
        L.append("Incertitudini (de lămurit cu clientul / sursele): " + "; ".join(i["text"] for i in r["incertitudini"]) + ".")
    top = case["motive_top3"][:2]
    if top:
        L.append("De ce e în coadă: " + "; ".join(top) + f" (banda {case['banda']}).")
    ex = check["interogari_externe"]
    v = r["verificari"]
    L.append(f"Verificări: {len(check['plan'])} planificate după produse + motiv, {ex.get('executate', 0)} interogări externe "
             f"din {ex['rulare_tot']} posibile" + (f"; oprit la {v['oprit_la']} ({v['verificare_picata']})" if v["oprit_la"] else "")
             + (f"; avertizări: {', '.join(v['avertizari'])}" if v["avertizari"] else "") + ".")
    c = check["concluzii"]
    cifre = []
    if c.get("venit_lunar"):
        cifre.append(f"venit {fmt_ron(c['venit_lunar'])} RON/lună" + (" (ANAF)" if c.get("venit_lunar_anaf") else ""))
    if c.get("dti_curent") is not None:
        cifre.append(f"DTI {c['dti_curent']:.0%}")
    if c.get("ltv_actual") is not None:
        cifre.append(f"LTV actual {c['ltv_actual']:.2f}")
    if cifre:
        L.append("Cifre: " + ", ".join(cifre) + ".")
    if r["recomandare"] in ("nu_interveni", "oferta_minima", "oferta_produs") and offer["interventie_aleasa"]:
        L.append(offer["explicatie"])
    o = r["oferta"]
    if o and o.get("rata_noua"):
        if o.get("rata_veche"):
            sens = "scade" if o["rata_noua"] <= o["rata_veche"] else "crește"
            L.append(f"Oferta: dobândă {o['dobanda_noua']:.2f}% ({o['perioada']}), rata {sens} de la {fmt_ron(o['rata_veche'])} "
                     f"(azi) la {fmt_ron(o['rata_noua'])} RON/lună; cost pentru bancă {fmt_ron(o['cost_banca'])} RON."
                     + (f" Fără ofertă, după {o['fixa_expira']} rata ar fi {fmt_ron(o['rata_dupa_fixa'])} RON/lună."
                        if o.get("rata_dupa_fixa") else "")
                     + (f" Condiție: {o['conditie']}." if o.get("conditie") else ""))
        else:
            L.append(f"Oferta: {o.get('produs')} {fmt_ron(o.get('suma') or 0)} RON la {o['dobanda_noua']:.2f}%, rată {fmt_ron(o['rata_noua'])} RON/lună.")
    if r["documente_lipsa"]:
        L.append("Documente de adus: " + "; ".join(f"{d['tip']} ({d['motiv']})" for d in r["documente_lipsa"]) + ".")
    return " ".join(L)


# ---------------------------------------------------------------- audit

def audit_rows(case: dict, check: dict, offer: dict, r: dict, today: date) -> list[dict]:
    ts = f"{today.isoformat()}T00:00:00"
    base = {"timestamp": ts, "case_id": case["case_id"], "client_id": case["client_id"]}
    rows = [{**base, "tip": "semnal", "cheie": s["id"], "valoare": s["scor"], "sursa": s["dovada"]} for s in case["semnale"]]
    rows += [{**base, "tip": "verificare", "cheie": x["id"], "valoare": x["status"], "sursa": x.get("sursa") or "intern",
              "dovada": x["dovada"]} for x in check["rezultate"]]
    rows.append({**base, "tip": "retentie", "cheie": "interventie", "valoare": offer["interventie_aleasa"],
                 "sursa": f"B={offer['B']} p={offer['p']} V={offer['V']} cost={offer['cost']}"})
    rows.append({**base, "tip": "decizie", "cheie": "recomandare", "valoare": r["recomandare"], "sursa": "agent", "motiv": r["motiv"]})
    return rows


# ---------------------------------------------------------------- pe portofoliu + CLI

def build_recommendations(pf, cfg: Config, res, checks: list[dict], offers: list[dict], mocks: Mocks,
                          versiune: str | None = None) -> tuple[list[dict], list[dict]]:
    from .versiune import versiune_completa
    by_check = {c["case_id"]: c for c in checks}
    by_offer = {o["case_id"]: o for o in offers}
    versiune = versiune or versiune_completa(cfg)["scurt"]
    rows, audit = [], []
    for case in res.cases:
        ci = res.inputs[case["case_id"]]
        check, offer = by_check[case["case_id"]], by_offer[case["case_id"]]
        r = recomanda(case, check, offer, ci.client, ci.loan, ci.cereri, mocks.documente.get(case["client_id"], []),
                      pf.today, pf.market, cfg)
        r["consilier"] = cfg.echipa.pentru(case["client_id"])
        r["versiune"] = versiune
        rows.append(r)
        audit += [{**a, "versiune": versiune} for a in audit_rows(case, check, offer, r, pf.today)]
    return rows, audit


def print_rec(r: dict) -> None:
    print(f"\n═══ {r['case_id']} · {r['client_id']} · {r['loan_id'] or 'fără credit'} · {r['produs']}")
    print(f"  {r['explicatie']}")


def main(argv: list[str] | None = None) -> None:
    setup_console()
    ap = argparse.ArgumentParser(description="Recomandarea finală: stare, ofertă, grafic, documente, explicație, audit.")
    ap.add_argument("--today")
    ap.add_argument("--data-dir", default=str(DATA_DIR))
    ap.add_argument("--out-dir", default=str(OUT_DIR))
    ap.add_argument("--config-dir", default=str(CONFIG_DIR))
    ap.add_argument("--case")
    ap.add_argument("--top", type=int, default=5)
    a = ap.parse_args(argv)

    t0 = time.perf_counter()
    pf, cfg, res = run_pipeline(a.data_dir, a.out_dir, a.config_dir, a.today)
    mocks = load_mocks(a.data_dir)
    checks = run_all_checks(pf, mocks, cfg, res)
    offers = build_offers(pf, cfg, res, checks)
    rows, audit = build_recommendations(pf, cfg, res, checks, offers, mocks)
    out = Path(a.out_dir)
    write_json(out / "offers.json", offers)
    write_json(out / "recommendations.json", rows)
    out.mkdir(parents=True, exist_ok=True)
    import json
    with open(out / "audit.jsonl", "w", encoding="utf-8") as f:
        for row in audit:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
    dt = time.perf_counter() - t0

    for r in ([r for r in rows if r["case_id"] == a.case] if a.case else rows[:a.top]):
        print_rec(r)
    cnt = Counter(r["recomandare"] for r in rows)
    print(f"\nRecomandări: {len(rows)} cazuri în {dt:.2f}s → {a.out_dir}/recommendations.json, {a.out_dir}/audit.jsonl ({len(audit)} rânduri)")
    print("  " + ", ".join(f"{k}={v}" for k, v in cnt.most_common()))
    print(f"  documente lipsă: {sum(len(r['documente_lipsa']) for r in rows)} pe {sum(1 for r in rows if r['documente_lipsa'])} cazuri")
    log_event(a.out_dir, "recommend", "done", cazuri=len(rows), recomandari=dict(cnt), audit=len(audit), secunde=round(dt, 3))


if __name__ == "__main__":
    main()
