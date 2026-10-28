"""Metricile modelului final (MODEL_FINAL → Metrici), calculate pe artefactele din `pipeline.run_full`.

Cifra-vedetă: costul total al retenției cu agentul vs. „aceeași reducere pentru toți" (0,2 / 0,4 / 0,6 pp), la
aceeași rată de rămânere. Rata de rămânere se simulează cu `ground_truth → comportament`, pe care agentul nu
îl vede: clientul pleacă dacă ce mai câștigă după intervenția noastră depășește pragul lui; informarea îl ține
doar dacă reacționează la informare; pachetul doar dacă acceptă să aducă salariul.
"""
from __future__ import annotations

from collections import Counter

from .common import fmt_ron
from .recommend import STARI

UNIFORM = ("0.2", "0.4", "0.6")


# ---------------------------------------------------------------- simularea comportamentului (ascuns agentului)

def ramane(interventie: str | None, B: float, B_dupa: float, cmp: dict) -> bool:
    """Rămâne clientul după intervenție? (regulile din PLAN_EXECUTIE → Decizii)"""
    prag = cmp["prag_castig_plecare_ron"]
    if interventie in (None, "nu_interveni"):
        return B <= prag
    if interventie == "informare":
        return B <= prag or bool(cmp.get("reactioneaza_la_informare"))
    if interventie == "pachet_salariu":
        return bool(cmp.get("accepta_pachet_salariu")) or B_dupa <= prag
    return B_dupa <= prag


def candidati_retentie(full) -> list[dict]:
    """Cazurile pe care se compară politicile: nu blocate, fără risc de credit, cu un credit existent."""
    prag = full.cfg.priority.risc_credit.blocheaza_retentia_daca
    out = []
    for case in full.res.cases:
        if case["blocaje"] or case["scoruri"]["risc_credit"] >= prag or case["loan_id"] is None:
            continue
        a = full.by_case(case["case_id"])
        out.append({"case": case, "offer": a["offer"], "rec": a["rec"]})
    return out


def cifra_vedeta(full, gt: list[dict]) -> dict:
    cmp = {g["client_id"]: g["comportament"] for g in gt}
    cand = candidati_retentie(full)
    n = len(cand)

    def politica(alege):
        cost = ret = 0.0
        for c in cand:
            iid, c_cost, b_dupa = alege(c)
            cost += c_cost
            ret += ramane(iid, c["offer"]["B"], b_dupa, cmp[c["case"]["client_id"]])
        return {"cost": round(cost, 2), "retinuti": int(ret), "rata_ramanere": round(ret / n, 4) if n else 0.0,
                "cost_per_retinut": round(cost / ret, 2) if ret else None}

    def agent(c):
        o = c["offer"]
        it = next((i for i in o["interventii"] if i["id"] == o["interventie_aleasa"]), None)
        return o["interventie_aleasa"], o["cost"], (it["B_dupa"] if it else o["B"])

    def uniform(pp):
        iid = f"reducere_marja_{pp.replace('.', '_')}"

        def alege(c):
            it = next((i for i in c["offer"]["interventii"] if i["id"] == iid), None)
            if it is None or c["offer"]["B_detalii"].get("dobanda_pct_piata") is None:
                return None, 0.0, c["offer"]["B"]
            if it["cost"] == 0 and it["B_dupa"] == c["offer"]["B"]:          # produs fără marjă (card): nu se aplică
                return None, 0.0, c["offer"]["B"]
            return iid, it["cost"], it["B_dupa"]                                 # se dă tuturor, indiferent de buget
        return alege

    ag = politica(agent)
    un = {pp: politica(uniform(pp)) for pp in UNIFORM}
    aleasa = next((pp for pp in UNIFORM if un[pp]["rata_ramanere"] >= ag["rata_ramanere"]), None)
    if aleasa is not None:
        econ = un[aleasa]["cost"] - ag["cost"]
        concl = (f"la aceeași rată de rămânere ({ag['rata_ramanere']:.0%}), agentul costă {fmt_ron(ag['cost'])} RON față de "
                 f"{fmt_ron(un[aleasa]['cost'])} RON cu reducere uniformă de {aleasa} pp pentru toți → "
                 f"{'economie' if econ >= 0 else 'cost suplimentar'} {fmt_ron(abs(econ))} RON ({abs(econ) / un[aleasa]['cost']:.0%})"
                 if un[aleasa]["cost"] else f"ambele politici costă 0 RON la rata {ag['rata_ramanere']:.0%}")
    else:
        top = max(UNIFORM, key=lambda pp: un[pp]["rata_ramanere"])
        econ = un[top]["cost"] - ag["cost"]
        concl = (f"nicio reducere uniformă nu atinge rata de rămânere a agentului ({ag['rata_ramanere']:.0%}): cea mai mare "
                 f"({top} pp pentru toți) ține {un[top]['rata_ramanere']:.0%} la {fmt_ron(un[top]['cost'])} RON, agentul ține "
                 f"{ag['rata_ramanere']:.0%} la {fmt_ron(ag['cost'])} RON")
    return {"candidati": n, "agent": ag, "uniform": un, "uniform_aleasa": aleasa, "economie_ron": round(econ, 2),
            "economie_pct": round(econ / un[aleasa]["cost"], 4) if aleasa and un[aleasa]["cost"] else None, "concluzie": concl}


# ---------------------------------------------------------------- celelalte metrici

def procent_nu_interveni(full) -> dict:
    activi = [r for r in full.recs if r["recomandare"] != "blocat"]
    nu = sum(1 for r in activi if r["recomandare"] == "nu_interveni")
    return {"nu_interveni": nu, "altele": len(activi) - nu, "total": len(activi), "procent": round(nu / len(activi), 4) if activi else 0.0,
            "bani_necheltuiti_fata_de_informare_pentru_toti": None}


def interogari_evitate(full) -> dict:
    tot = sum(c["interogari_externe"]["rulare_tot"] for c in full.checks)
    ex = sum(c["interogari_externe"].get("executate", 0) for c in full.checks)
    return {"rulare_tot": tot, "executate": ex, "evitate": tot - ex, "procent": round((tot - ex) / tot, 4) if tot else 0.0}


def _top_rec(full) -> dict[str, dict]:
    top: dict[str, dict] = {}
    for r in full.recs:
        top.setdefault(r["client_id"], r)
    return top


def eval_recomandari(full, gt: list[dict]) -> dict:
    labels = list(STARI) + ["—"]
    conf = {e: {p: 0 for p in labels} for e in labels}
    top = _top_rec(full)
    ok = tot = 0
    gresite = []
    for g in gt:
        exp = g.get("recomandare_asteptata") or "—"
        got = top[g["client_id"]]["recomandare"] if g["client_id"] in top else "—"
        conf[exp][got] += 1
        if exp != "—":
            tot += 1
            ok += exp == got
            if exp != got:
                gresite.append({"client_id": g["client_id"], "asteptat": exp, "obtinut": got})
    return {"acuratete": round(ok / tot, 4) if tot else 1.0, "corecte": ok, "total": tot, "matrice_confuzie": conf, "gresite": gresite}


def eval_verificari(full, gt: list[dict]) -> dict:
    oprit = {}
    for c in full.checks:
        if c["oprit_la"] and c["oprit_la"] != "intern":
            oprit.setdefault(c["client_id"], c["oprit_la"])
    ast = [g for g in gt if g.get("verificare_picata_asteptata")]
    corecte = sum(1 for g in ast if oprit.get(g["client_id"]) == g["verificare_picata_asteptata"])
    fp = [cid for cid in oprit if not any(g["client_id"] == cid and g.get("verificare_picata_asteptata") for g in gt)]
    return {"asteptate": len(ast), "corecte": corecte, "false_pozitive": len(fp), "false_pozitive_clienti": fp}


def cerinte_dure_final(full) -> dict:
    cfg = full.cfg
    prag = cfg.priority.risc_credit.blocheaza_retentia_daca
    P, C = cfg.priority, cfg.constraints
    cases = {c["case_id"]: c for c in full.res.cases}
    offers = {o["case_id"]: o for o in full.offers}
    loans = {l["loan_id"]: l for l in full.pf.loans}
    clients = {c["client_id"]: c for c in full.pf.clients}
    risc, limite, blocate = [], [], []
    for r in full.recs:
        case = cases[r["case_id"]]
        oferta_comerciala = r["oferta"] is not None and r["oferta"].get("tip") not in ("restructurare", "produs_nou")
        if oferta_comerciala and case["scoruri"]["risc_credit"] >= prag:
            risc.append(r["case_id"])
        if case["blocaje"] and (r["oferta"] is not None or r["interventie"]):
            blocate.append(r["case_id"])
        if r["interventie"] and r["loan_id"]:
            it = next(i for i in offers[r["case_id"]]["interventii"] if i["id"] == r["interventie"])
            loan, client = loans[r["loan_id"]], clients[r["client_id"]]
            cfg_it = cfg.retention.by_id()[r["interventie"]]
            buget = P.buget_retentie_pp.get(client["nivel_relatie"], 0.0)
            if not it["fezabil"]:
                limite.append(r["case_id"])
            elif cfg_it.reducere_pp and loan.get("marja") is not None and (
                    cfg_it.reducere_pp > buget + 1e-9 or loan["marja"] - cfg_it.reducere_pp < C.marja_minima_pp - 1e-9):
                limite.append(r["case_id"])
    exp30 = []
    from datetime import timedelta
    from .common import parse_date
    for c in full.res.cases:
        l = loans.get(c["loan_id"])
        exp = parse_date(l.get("dobanda_fixa_expira_la")) if l else None
        if exp and l["tip_dobanda"] == "fixa" and full.pf.today <= exp < full.pf.today + timedelta(days=30) and c["banda"] != list(P.benzi)[0]:
            exp30.append(c["case_id"])
    return {k: {"incalcari": len(v), "cazuri": v} for k, v in
            (("oferte_catre_risc_activ", risc), ("oferte_in_afara_limitelor", limite),
             ("oferte_pe_cazuri_blocate", blocate), ("expirare_sub_30_zile_nu_P1", exp30))}


def raport_model_final(full, gt: list[dict]) -> dict:
    return {"cifra_vedeta": cifra_vedeta(full, gt), "nu_interveni": procent_nu_interveni(full),
            "interogari_externe": interogari_evitate(full), "recomandari": eval_recomandari(full, gt),
            "verificari_picate": eval_verificari(full, gt), "cerinte_dure": cerinte_dure_final(full),
            "distributie_recomandari": dict(Counter(r["recomandare"] for r in full.recs))}


def print_model_final(m: dict) -> None:
    h = m["cifra_vedeta"]
    print("\n═══ Model final")
    print(f"  Cifra-vedetă (pe {h['candidati']} candidați la retenție, rata de rămânere simulată din comportamentul ascuns):")
    a = h["agent"]
    print(f"    agent:              cost {fmt_ron(a['cost']):>10} RON · rămân {a['retinuti']:>2}/{h['candidati']} ({a['rata_ramanere']:.0%})"
          + (f" · {fmt_ron(a['cost_per_retinut'])} RON / client reținut" if a["cost_per_retinut"] else ""))
    for pp, u in h["uniform"].items():
        mark = "◄" if pp == h["uniform_aleasa"] else " "
        print(f"  {mark} uniform {pp} pp:     cost {fmt_ron(u['cost']):>10} RON · rămân {u['retinuti']:>2}/{h['candidati']} ({u['rata_ramanere']:.0%})"
              + (f" · {fmt_ron(u['cost_per_retinut'])} RON / client reținut" if u["cost_per_retinut"] else ""))
    print(f"    → {h['concluzie']}")
    n = m["nu_interveni"]
    print(f"  „Nu interveni\": {n['nu_interveni']}/{n['total']} cazuri active ({n['procent']:.0%}) — bani necheltuiți")
    q = m["interogari_externe"]
    print(f"  Interogări externe evitate: {q['evitate']}/{q['rulare_tot']} ({q['procent']:.0%}) față de „rulează tot\"")
    r = m["recomandari"]
    print(f"  Recomandări vs etalon: {r['corecte']}/{r['total']} ({r['acuratete']:.0%})"
          + (f" · diferențe: " + ", ".join(f"{g['client_id']} {g['asteptat']}→{g['obtinut']}" for g in r["gresite"]) if r["gresite"] else ""))
    labels = list(r["matrice_confuzie"])
    print("    așteptat \\ obținut   " + " ".join(f"{l[:6]:>6}" for l in labels))
    for e, row in r["matrice_confuzie"].items():
        print(f"    {e:<20} " + " ".join(f"{row[l]:>6}" for l in labels))
    v = m["verificari_picate"]
    print(f"  Verificări picate corect: {v['corecte']}/{v['asteptate']} · false pozitive: {v['false_pozitive']}")
    print("  Cerințe dure:")
    for k, x in m["cerinte_dure"].items():
        print(f"    {k:<32} încălcări: {x['incalcari']}" + (f"  {x['cazuri']}" if x["cazuri"] else ""))
