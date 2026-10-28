"""Explicația completă a unui caz: semnale cu dovezi, formula cu numerele înlocuite, de ce banda,
de ce acțiunea și ce ar schimba rezultatul (scenarii „ce-ar fi dacă” recalculate cu aceeași funcție).

    python -m retailagent.explain Q0001
"""
from __future__ import annotations

import argparse
from dataclasses import replace
from pathlib import Path

from .common import CONFIG_DIR, DATA_DIR, OUT_DIR, fmt_ron, read_json, setup_console
from .config_loader import Config
from .queue import CaseInput, Trace, score_case
from .recommend import ETICHETA

ACT_TXT = {"oferta_in_grila": "ofertă în grilă", "partial": "parțial", "imposibil": "imposibil"}


def _rezultat(ci: CaseInput, cfg: Config) -> tuple[str, str, float]:
    c, _ = score_case(ci, cfg)
    return c["banda"], c["actiune_propusa"], c["scoruri"]["prioritate"]


def what_ifs(case: dict, ci: CaseInput, tr: Trace, cfg: Config) -> list[str]:
    out: list[str] = []
    P = cfg.priority
    banda, act = case["banda"], case["actiune_propusa"]
    pr, risc = case["scoruri"]["prioritate"], case["scoruri"]["risc_credit"]

    # 1. distanța față de pragurile benzilor
    names = list(P.benzi)
    i = names.index(banda)
    if i > 0:
        sus = names[i - 1]
        out.append(f"{sus} ar necesita prioritate ≥ {P.benzi[sus].prioritate_min:.2f} "
                   f"(acum {pr:.2f}, lipsesc {P.benzi[sus].prioritate_min - pr:.2f})")
    if i < len(names) - 1 and tr.banda_motiv.startswith("prioritate"):
        out.append(f"sub {P.benzi[banda].prioritate_min:.2f} cazul ar coborî în {names[i + 1]}")

    # 2. bugetul de retenție al nivelului clientului = 0
    if ci.loan is not None:
        tier = ci.client["nivel_relatie"]
        cfg0 = cfg.model_copy(deep=True)
        cfg0.priority.buget_retentie_pp[tier] = 0.0
        b2, a2, p2 = _rezultat(ci, cfg0)
        if (b2, a2) != (banda, act):
            out.append(f"dacă buget_retentie_pp[{tier}] = 0 → acțiune {a2}, {b2} (prioritate {p2:.2f})")
        else:
            out.append(f"buget_retentie_pp[{tier}] = 0 nu schimbă banda sau acțiunea")

    # 3. fără fiecare semnal declanșator, pe rând
    sig_cfg = cfg.signals.by_id()
    seen = set()
    for s in sorted(ci.semnale, key=lambda s: -s["scor"]):
        if s["id"] in seen or not sig_cfg[s["id"]].declansator:
            continue
        seen.add(s["id"])
        fara = replace(ci, semnale=[x for x in ci.semnale if x["id"] != s["id"]])
        b2, a2, p2 = _rezultat(fara, cfg)
        if (b2, a2) != (banda, act):
            verb = "după rezolvarea" if s["familie"] == "blocaj_proces" else "fără"
            out.append(f"{verb} {s['id']} → {b2}, acțiune {a2} (prioritate {p2:.2f})")

    # 4. pragul de blocare a retenției
    if act == "restructurare_preventiva" and case["scoruri"]["prioritate_retentie"] > 0:
        out.append(f"retenția e blocată cât timp risc_credit ≥ {P.risc_credit.blocheaza_retentia_daca:.2f} "
                   f"(acum {risc:.2f}); prioritate_retentie ar fi {case['scoruri']['prioritate_retentie']:.2f}")
    return out


def explain_case(case: dict, ci: CaseInput, tr: Trace, cfg: Config) -> str:
    P = cfg.priority
    s = case["scoruri"]
    cl = ci.client
    L: list[str] = []
    w = L.append
    w(f"═══ {case['case_id']} · {cl['nume']} ({cl['client_id']}, {cl['nivel_relatie']}, {cl['tipologie_declarata']})")
    cred = f"{case['loan_id']} · {case['produs']}" if case["loan_id"] else f"fără credit existent · {case['produs'] or '—'}"
    if ci.loan:
        ln = ci.loan
        cred += (f" · sold {fmt_ron(ln['sold_ramas'])} RON · {ln['tip_dobanda']} {ln['dobanda_curenta']:.2f}%"
                 + (f" (fixă până la {ln['dobanda_fixa_expira_la']})" if ln.get("dobanda_fixa_expira_la") else ""))
    w(f"    {cred}")
    w(f"    Banda {case['banda']} · acțiune: {case['actiune_propusa']} · termen: {case['deadline']} · sursă: {case['sursa']}"
      + (f" · cerere {case['request_id']}" if case["request_id"] else ""))
    if case["blocaje"]:
        w(f"    ⛔ BLOCAT de: {', '.join(case['blocaje'])} — nicio ofertă până la rezolvare")

    w("\n── Semnale (cu dovada)")
    for x in case["semnale"]:
        w(f"  [{x['familie']:<13}] {x['id']:<26} {x['scor']:.2f}  {x['dovada']}")

    w("\n── Calcul")
    if tr.contributii_plecare:
        terms = " + ".join(f"{wt:.2f}×{sc:.2f}" if wt else f"bonus {ct:.2f}" for _, wt, sc, ct in tr.contributii_plecare)
        names = ", ".join(cid for cid, *_ in tr.contributii_plecare)
        w(f"  plecare   = {terms} = {s['plecare']:.2f}   ({names})")
    else:
        w(f"  plecare   = 0 (niciun semnal de plecare)")
    w(f"  valoare   = {P.valoare.venit_viitor:.1f} × venit_viitor_norm {tr.venit_norm:.2f} "
      f"({fmt_ron(tr.venit_viitor)} / {fmt_ron(ci.venit_max)} RON max portofoliu) + {P.valoare.produse_atasate:.1f} × "
      f"produse {tr.produse_norm:.2f} ({len(cl.get('produse_atasate', []))}/{P.valoare.produse_max}) = {s['valoare']:.2f}")
    if ci.loan is not None:
        w(f"  actiune   = {s['actiune']:.1f} ({ACT_TXT[tr.actiune_eticheta]}: gap față de piață {tr.gap_pp:.2f} pp; "
          f"grila băncii e cu {tr.necesar_pp:.2f} pp peste piață; buget {cl['nivel_relatie']} = {tr.buget_pp:.2f} pp)")
    else:
        w("  actiune   = 0.0 (fără credit existent — nu există ofertă de retenție)")
    w(f"  prioritate_retentie = {s['plecare']:.2f} × {s['valoare']:.2f} × {s['actiune']:.1f} = {s['prioritate_retentie']:.2f}")
    w(f"  risc_credit = max(semnale risc) = {s['risc_credit']:.2f}" + (f"  ({tr.risc_sursa})" if tr.risc_sursa else ""))
    pr_txt = f"max({s['risc_credit']:.2f}, {s['prioritate_retentie']:.2f})"
    if tr.prioritate_min_cerere:
        pr_txt = f"max({pr_txt}, minim cerere {tr.prioritate_min_cerere:.2f})"
    w(f"  prioritate  = {pr_txt} = {s['prioritate']:.2f}")

    w("\n── De ce")
    w(f"  banda {case['banda']}: {tr.banda_motiv or 'niciun prag atins — banda implicită'}")
    w(f"  acțiunea {case['actiune_propusa']}: {tr.actiune_motiv}")
    w(f"  termenul {case['deadline']}: {tr.deadline_motiv}")
    w("  motive principale:")
    for m in case["motive_top3"]:
        w(f"    • {m}")

    w("\n── Ce ar schimba rezultatul")
    for m in what_ifs(case, ci, tr, cfg):
        w(f"  → {m}")
    return "\n".join(L)


# ================================================================ explicația completă (verificări + retenție + recomandare)

MARK = {"ok": "✔", "avertizare": "⚠", "fail": "✘", "neexecutat": "·"}


def explain_checks(check: dict) -> list[str]:
    L = ["\n── Verificări (alese după produse deținute + motiv)"]
    L.append("  motive: " + ", ".join(f"{m['motiv']} ({m['sursa']})" for m in check["motive"]) + "; produse deținute: "
             + (", ".join(check["produse_detinute"]) or "—"))
    L.append("  planificate, cu motivul includerii:")
    for x in check["plan"]:
        L.append(f"    [{x['treapta']:<13}] {x['id']:<30} {'extern' if x['externa'] else 'intern':<6} ← {x['motiv']}")
    if check["omise"]:
        L.append("  omise, cu motivul omiterii:")
        for x in check["omise"]:
            L.append(f"    [{x['treapta']:<13}] {x['id']:<30} {'extern' if x['externa'] else 'intern':<6} ✗ {x['motiv']}")
    L.append("  rezultate:")
    for x in check["rezultate"]:
        L.append(f"    {MARK[x['status']]} {x['id']:<30} {x['dovada']}" + (f"  [{x['sursa']}]" if x.get("sursa") and x["sursa"] != "intern" else ""))
    ie = check["interogari_externe"]
    L.append(f"  interogări externe: {ie.get('executate', 0)} executate din {ie['rulare_tot']} posibile → "
             f"{ie['rulare_tot'] - ie.get('executate', 0)} evitate"
             + (f"; oprit la {check['oprit_la']} ({check['verificare_picata']})" if check["oprit_la"] else ""))
    return L


def explain_retention(offer: dict, cfg: Config) -> list[str]:
    R = cfg.retention
    b, leg = offer["B_detalii"], offer["legaturi"]
    L = ["\n── Retenție (cea mai ieftină implicare care păstrează clientul)"]
    L.append(f"  B = dobândă la noi {fmt_ron(b['dobanda_la_noi'])} − dobândă piață {fmt_ron(b['dobanda_piata'])} "
             f"({b['dobanda_pct_piata'] if b['dobanda_pct_piata'] is not None else '—'}%) − cost mutare {fmt_ron(b['cost_mutare'])} "
             f"= {fmt_ron(offer['B'])} RON (orizont {b.get('orizont_luni', 0)} luni)")
    c = leg["componente"]
    L.append(f"  legături = {leg['scor']:.2f} (produse {c['produse']:.2f} · vechime {c['vechime']:.2f} ({leg['vechime_ani']} ani) · "
             f"nivel {c['nivel']:.2f} · activitate {c['activitate']:.0f}) → {'suficiente' if leg['suficiente_pentru_oferta'] else 'insuficiente'} pentru ofertă")
    L.append(f"  semnale active: {', '.join(offer['semnale_active']) or '—'}")
    s = R.sigmoid
    L.append(f"  p = sigmoid({s['a']}·B_norm + {s['b']}·active − {s['c']} − {s['d']}·legături) = {offer['p']:.0%}   (țintă ≤ {offer['p_tinta']:.0%})")
    L.append(f"  V = {fmt_ron(offer['V'])} RON (marjă {fmt_ron(offer['valoare']['venit_marja'])} + produse {fmt_ron(offer['valoare']['produse'])}) "
             f"→ p × V = {fmt_ron(offer['p'] * offer['V'])} RON")
    L.append(f"  {'':2}{'intervenție':<22} {'fezabil':<7} {'cost':>9} {'B după':>9} {'p după':>6} {'țintă':<5} {'merită':<6} motiv")
    for i in offer["interventii"]:
        mark = "►" if i["id"] == offer["interventie_aleasa"] else " "
        L.append(f"  {mark} {i['id']:<22} {'da' if i['fezabil'] else 'nu':<7} {fmt_ron(i['cost']):>9} {fmt_ron(i['B_dupa']):>9} "
                 f"{i['p_dupa']:>6.0%} {'da' if i['respecta_tinta'] else 'nu':<5} {'da' if i['merita'] else 'nu':<6} "
                 f"{'' if i['fezabil'] else i['motiv_infezabil']}"[:170])
    L.append(f"  aleasă: {offer['interventie_aleasa'] or '—'} — {offer['motiv_alegere']}")
    return L


def explain_recommendation(rec: dict) -> list[str]:
    L = [f"\n── Recomandare: {ETICHETA[rec['recomandare']].upper()}"]
    L.append(f"  motiv: {rec['motiv']}")
    o = rec["oferta"]
    if o:
        L.append("  ofertă: " + ", ".join(f"{k} {v}" for k, v in o.items() if v is not None and k not in ("tip",)))
    if rec["grafic"]:
        g = rec["grafic"]
        L.append(f"  grafic: {g['nr_rate']} rate, prima {fmt_ron(g['primele_luni'][0]['rata'])} RON ({g['primele_luni'][0]['luna']}), "
                 f"dobândă totală {fmt_ron(g['dobanda_totala'])} RON")
    if rec["documente_lipsa"]:
        L.append("  documente de adus: " + "; ".join(f"{d['tip']} ({d['motiv']})" for d in rec["documente_lipsa"]))
    else:
        L.append("  documente: dosarul e complet pentru această recomandare")
    L.append(f"  text pentru consilier: {rec['explicatie']}")
    return L


def explain_full(case: dict, full) -> str:
    a = full.by_case(case["case_id"])
    txt = explain_case(a["case"], a["input"], a["trace"], full.cfg)
    L = explain_checks(a["check"]) + explain_retention(a["offer"], full.cfg) + explain_recommendation(a["rec"])
    return txt + "\n" + "\n".join(L)


def main(argv: list[str] | None = None) -> None:
    setup_console()
    ap = argparse.ArgumentParser(description="Explică un caz din coadă: semnale, calcul, verificări, retenție, recomandare.")
    ap.add_argument("case_id")
    ap.add_argument("--today")
    ap.add_argument("--data-dir", default=str(DATA_DIR))
    ap.add_argument("--out-dir", default=str(OUT_DIR))
    ap.add_argument("--config-dir", default=str(CONFIG_DIR))
    ap.add_argument("--scurt", action="store_true", help="doar partea de coadă (fără verificări / retenție / recomandare)")
    a = ap.parse_args(argv)

    from .pipeline import run_full
    full = run_full(a.data_dir, a.out_dir, a.config_dir, a.today)
    res = full.res
    # cazul e identificat după conținut (client, credit, cerere) ca să fie robust la o coadă regenerată
    qpath = Path(a.out_dir) / "queue.json"
    target = None
    if qpath.exists():
        target = next((c for c in read_json(qpath) if c["case_id"] == a.case_id), None)
    key = (lambda c: (c["client_id"], c["loan_id"], c["request_id"]))
    case = next((c for c in res.cases if target and key(c) == key(target)), None)         or next((c for c in res.cases if c["case_id"] == a.case_id), None)
    if case is None:
        raise SystemExit(f"Cazul {a.case_id} nu există în coadă ({len(res.cases)} cazuri).")
    if a.scurt:
        print(explain_case(case, res.inputs[case["case_id"]], res.traces[case["case_id"]], full.cfg))
    else:
        print(explain_full(case, full))


if __name__ == "__main__":
    main()

