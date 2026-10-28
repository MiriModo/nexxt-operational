"""Verificări alese după produse deținute + motiv (MODEL_FINAL §2).

Planificarea (`plan_checks`) spune, pentru fiecare verificare din config/checks.yaml, dacă rulează și de ce,
sau de ce e omisă. Lista se afișează ÎNAINTE de rulare. Execuția în trepte (`run_checks`) e în același modul
(M2-T3): intern → anaf → biroul_credit → crc → garantie, cu oprire la primul pas picat.

    python -m retailagent.checks        # out/checks.json
"""
from __future__ import annotations

from .config_loader import Config

MOTIV_RISC = "risc"
MOTIV_BLOCAJ = "blocaj"


def motive_caz(case: dict, cereri: list[dict], cfg: Config) -> list[dict]:
    """Motivele unui caz, în ordinea: blocaj, risc, cereri, semnale. Fiecare cu sursa lui (pentru afișare)."""
    out: list[dict] = []
    if case.get("blocaje"):
        out.append({"motiv": MOTIV_BLOCAJ, "sursa": "blocaj de proces: " + ", ".join(case["blocaje"])})
    prag = cfg.priority.risc_credit.blocheaza_retentia_daca
    if case["scoruri"]["risc_credit"] >= prag:
        out.append({"motiv": MOTIV_RISC, "sursa": f"risc_credit {case['scoruri']['risc_credit']:.2f} ≥ {prag:.2f}"})
    for c in cereri:
        if c["tip"] in cfg.checks.motive:
            out.append({"motiv": c["tip"], "sursa": f"cerere {c['request_id']}"})
    for s in sorted(case["semnale"], key=lambda s: -s["scor"]):
        if s["id"] in cfg.checks.motive and all(m["motiv"] != s["id"] for m in out):
            out.append({"motiv": s["id"], "sursa": f"semnal {s['id']} ({s['scor']:.2f})"})
    return out


def plan_checks(case: dict, client: dict, loans: list[dict], cereri: list[dict], cfg: Config) -> dict:
    """Ce verificări rulează pentru acest caz și de ce; ce se omite și de ce.

    Reguli: stratul de bază rulează mereu; stratul de produs după produsele deținute de client (toate
    creditele lui, nu doar cel din caz); motivele adaugă sau sar verificări, iar `adauga` câștigă în fața
    lui `sare`; un blocaj activ lasă doar verificările din `blocaj.doar`; fără consimțământ nu se face
    nicio interogare externă care îl cere.
    """
    CH = cfg.checks
    produse = {l["produs"] for l in loans}
    motive = motive_caz(case, cereri, cfg)
    blocaj = next((m for m in motive if m["motiv"] == MOTIV_BLOCAJ), None)

    adauga: dict[str, str] = {}          # verificare -> primul motiv care o adaugă
    sare: dict[str, str] = {}
    for m in motive:
        rule = CH.motive[m["motiv"]]
        for vid in rule.adauga:
            adauga.setdefault(vid, m["motiv"])
        for vid in rule.sare:
            sare.setdefault(vid, m["motiv"])

    plan: list[dict] = []
    omise: list[dict] = []
    rulare_tot = 0                       # câte interogări externe ar face „rulează tot"
    for v in CH.verificari:
        produs_ok = not v.produse or bool(produse & set(v.produse))
        consimtamant_ok = not v.necesita_consimtamant or bool(client.get(v.necesita_consimtamant))
        if v.externa and produs_ok and consimtamant_ok:
            rulare_tot += 1
        entry = {"id": v.id, "treapta": v.treapta, "externa": v.externa}

        if blocaj:
            if v.id in (CH.motive[MOTIV_BLOCAJ].doar or []):
                plan.append({**entry, "motiv": f"singura verificare permisă cât timp cazul e {blocaj['sursa']}"})
            else:
                omise.append({**entry, "motiv": f"blocat de {', '.join(case['blocaje'])}: așteaptă rezolvarea task-ului"})
            continue
        if not produs_ok:
            omise.append({**entry, "motiv": f"clientul nu deține {' / '.join(v.produse)}"})
            continue
        if v.strat == "baza":
            motiv = "strat de bază: rulează pentru orice caz"
        elif v.strat == "produs":
            motiv = "produs deținut: " + ", ".join(sorted(produse & set(v.produse)))
        elif v.id in adauga:
            motiv = f"cerută de motivul {adauga[v.id]}"
        elif v.id in sare:
            omise.append({**entry, "motiv": f"sărită de motivul {sare[v.id]}"})
            continue
        else:
            omise.append({**entry, "motiv": "niciun motiv nu o cere"})
            continue
        if v.id in sare and v.id not in adauga and v.strat != "baza":
            omise.append({**entry, "motiv": f"sărită de motivul {sare[v.id]}"})
            continue
        if not consimtamant_ok:
            omise.append({**entry, "motiv": f"consimțământ lipsă ({v.necesita_consimtamant}): nu se interoghează"})
            continue
        plan.append({**entry, "motiv": motiv})

    ordine = {t: i for i, t in enumerate(CH.trepte)}
    plan.sort(key=lambda x: ordine[x["treapta"]])          # stabil: păstrează ordinea din YAML în treaptă
    planificate = sum(1 for x in plan if x["externa"])
    return {
        "case_id": case["case_id"], "client_id": case["client_id"], "loan_id": case.get("loan_id"),
        "motive": motive, "produse_detinute": sorted(produse), "plan": plan, "omise": omise,
        "interogari_externe": {"planificate": planificate, "rulare_tot": rulare_tot,
                               "evitate_vs_tot": rulare_tot - planificate},
    }
