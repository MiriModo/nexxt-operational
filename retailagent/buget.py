"""Bugetul de retenție la nivel de portofoliu (retention.yaml → buget_portofoliu).

Optimizarea per client dă cea mai ieftină intervenție care păstrează clientul; dar banca are un plafon lunar.
Ofertele comerciale se ordonează după valoarea reținută pe leu cheltuit (p_înainte × V / cost) sau după cost și
se marchează `in_buget` până la plafon. Recomandarea nu se schimbă: cele peste plafon rămân recomandate, dar
`oferta.amanata_buget = true` (UI: „peste plafon luna asta"), ca să fie reluate luna următoare sau aprobate explicit.
"""
from __future__ import annotations

from .config_loader import Config

COMERCIALE = ("comision", "reducere_marja", "fix_piata", "pachet")


def aloca_buget(recs: list[dict], offers: list[dict], cfg: Config) -> dict:
    B = cfg.retention.buget_portofoliu
    by_offer = {o["case_id"]: o for o in offers}
    candidati = []
    for r in recs:
        o = by_offer.get(r["case_id"])
        oferta = r.get("oferta")
        if not oferta or oferta.get("tip") not in COMERCIALE or not o:
            continue
        cost = float(oferta.get("cost_banca") or 0.0)
        valoare_retinuta = o["p"] * o["V"]                       # ce am pierde fără intervenție
        scor = valoare_retinuta / cost if cost > 0 else float("inf")
        candidati.append((scor, cost, r, oferta, valoare_retinuta))
    if B.ordonare == "cost_crescator":
        candidati.sort(key=lambda t: t[1])
    else:
        candidati.sort(key=lambda t: -t[0])
    cumulat = 0.0
    in_buget = amanate = 0
    for rang, (scor, cost, r, oferta, vr) in enumerate(candidati, 1):
        incape = B.plafon_lunar_ron <= 0 or cumulat + cost <= B.plafon_lunar_ron
        if incape:
            cumulat += cost
            in_buget += 1
        else:
            amanate += 1
        oferta["in_buget"] = incape
        oferta["amanata_buget"] = not incape
        r["buget"] = {"rang": rang, "scor_v_pe_cost": round(scor, 2) if scor != float("inf") else None,
                      "valoare_retinuta": round(vr, 2), "cost": round(cost, 2), "in_buget": incape}
        if not incape:
            r["motiv"] += f"; peste plafonul lunar de retenție ({cumulat + cost:,.0f} > {B.plafon_lunar_ron:,.0f} RON) — amânată".replace(",", ".")
    return {"plafon_lunar_ron": B.plafon_lunar_ron, "ordonare": B.ordonare, "oferte": len(candidati), "in_buget": in_buget,
            "amanate": amanate, "cost_in_buget": round(cumulat, 2),
            "cost_total_oferte": round(sum(t[1] for t in candidati), 2)}
