"""Verificări alese după produse deținute + motiv (MODEL_FINAL §2).

Planificarea (`plan_checks`) spune, pentru fiecare verificare din config/checks.yaml, dacă rulează și de ce,
sau de ce e omisă. Lista se afișează ÎNAINTE de rulare. Execuția în trepte e în `checks_run.py`
(intern → anaf → biroul_credit → crc → garantie, cu oprire la primul pas picat); aici e și CLI-ul.

    python -m retailagent.checks [--case Q0001] [--top 5]       # out/checks.json
"""
from __future__ import annotations

import argparse
import time
from pathlib import Path

from .checks_run import CHECKS, CheckContext, Mocks, load_mocks, run_checks  # noqa: F401 (re-export)
from .common import CONFIG_DIR, DATA_DIR, OUT_DIR, log_event, setup_console, write_json
from .config_loader import Config
from .queue import QueueResult, run_pipeline
from .scan import Portfolio, client_flows

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


# ---------------------------------------------------------------- rulare pe portofoliu + CLI

def codebitor_index(pf: Portfolio) -> dict[str, list[dict]]:
    """client_id -> creditele altora pe care e codebitor (calculat o singură dată pe portofoliu)."""
    out: dict[str, list[dict]] = {}
    for l in pf.loans:
        for c in l.get("codebitori", []):
            if c.get("client_id") and c["client_id"] != l["client_id"]:
                out.setdefault(c["client_id"], []).append(l)
    return out


def build_context(pf: Portfolio, mocks: Mocks, cfg: Config, case: dict, cereri: list[dict], motive: list[str],
                  clients_by_id: dict[str, dict] | None = None, codebitori: dict[str, list[dict]] | None = None) -> CheckContext:
    cid = case["client_id"]
    client = (clients_by_id or {}).get(cid) or next(c for c in pf.clients if c["client_id"] == cid)
    loans = pf.loans_by_client.get(cid, [])
    loan = next((l for l in loans if l["loan_id"] == case["loan_id"]), None)
    codebitor_la = (codebitori if codebitori is not None else codebitor_index(pf)).get(cid, [])
    return CheckContext(pf.today, client, loan, loans, codebitor_la, cereri, motive, pf.market,
                        client_flows(pf, cfg, cid), pf.tx_by_client.get(cid, []),
                        {l["loan_id"]: pf.payments_by_loan.get(l["loan_id"], []) for l in loans}, mocks, cfg)


def check_registry(cfg: Config) -> None:
    missing = {v.id for v in cfg.checks.verificari} - set(CHECKS)
    if missing:
        raise SystemExit(f"Verificări din checks.yaml fără funcție @check: {sorted(missing)}")


def run_all_checks(pf: Portfolio, mocks: Mocks, cfg: Config, res: QueueResult) -> list[dict]:
    check_registry(cfg)
    clients_by_id = {c["client_id"]: c for c in pf.clients}
    codebitori = codebitor_index(pf)
    out = []
    for case in res.cases:
        ci = res.inputs[case["case_id"]]
        plan = plan_checks(case, ci.client, pf.loans_by_client.get(case["client_id"], []), ci.cereri, cfg)
        ctx = build_context(pf, mocks, cfg, case, ci.cereri, [m["motiv"] for m in plan["motive"]], clients_by_id, codebitori)
        out.append(run_checks(plan, ctx))
    return out


def print_plan(r: dict) -> None:
    print(f"\n═══ {r['case_id']} · {r['client_id']} · {r['loan_id'] or 'fără credit'} · motive: "
          + ", ".join(m["motiv"] for m in r["motive"]))
    print("  planificate (înainte de rulare):")
    for x in r["plan"]:
        print(f"    [{x['treapta']:<13}] {x['id']:<30} {'extern' if x['externa'] else 'intern':<6}  ← {x['motiv']}")
    if r["omise"]:
        print("  omise:")
        for x in r["omise"]:
            print(f"    [{x['treapta']:<13}] {x['id']:<30} {'extern' if x['externa'] else 'intern':<6}  ✗ {x['motiv']}")
    print("  rezultate:")
    for x in r["rezultate"]:
        mark = {"ok": "✔", "avertizare": "⚠", "fail": "✘", "neexecutat": "·"}[x["status"]]
        print(f"    {mark} {x['id']:<30} {x['dovada']}")
    ie = r["interogari_externe"]
    print(f"  interogări externe: {ie['executate']} executate din {ie['rulare_tot']} posibile → {ie['rulare_tot'] - ie['executate']} evitate"
          + (f"   OPRIT la {r['oprit_la']} ({r['verificare_picata']})" if r["oprit_la"] else ""))


def main(argv: list[str] | None = None) -> None:
    setup_console()
    ap = argparse.ArgumentParser(description="Verificări alese după produse deținute + motiv, rulate în trepte.")
    ap.add_argument("--today")
    ap.add_argument("--data-dir", default=str(DATA_DIR))
    ap.add_argument("--out-dir", default=str(OUT_DIR))
    ap.add_argument("--config-dir", default=str(CONFIG_DIR))
    ap.add_argument("--case", help="afișează doar acest caz")
    ap.add_argument("--top", type=int, default=5, help="câte cazuri se afișează detaliat")
    a = ap.parse_args(argv)

    t0 = time.perf_counter()
    pf, cfg, res = run_pipeline(a.data_dir, a.out_dir, a.config_dir, a.today)
    results = run_all_checks(pf, load_mocks(a.data_dir), cfg, res)
    write_json(Path(a.out_dir) / "checks.json", results)
    dt = time.perf_counter() - t0

    for r in ([r for r in results if r["case_id"] == a.case] if a.case else results[:a.top]):
        print_plan(r)
    tot = sum(r["interogari_externe"]["rulare_tot"] for r in results)
    ex = sum(r["interogari_externe"]["executate"] for r in results)
    oprite = [r for r in results if r["oprit_la"]]
    print(f"\nVerificări: {len(results)} cazuri în {dt:.2f}s → {a.out_dir}/checks.json")
    print(f"  interogări externe: {ex} executate din {tot} („rulează tot”) → {tot - ex} evitate ({(tot - ex) / tot:.0%})")
    print(f"  oprite la o verificare picată: {len(oprite)}  " + ", ".join(f"{r['case_id']}={r['verificare_picata']}" for r in oprite))
    log_event(a.out_dir, "checks", "done", cazuri=len(results), interogari_executate=ex, interogari_posibile=tot, secunde=round(dt, 3))


if __name__ == "__main__":
    main()
