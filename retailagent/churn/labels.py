"""Eticheta de churn: pentru fiecare candidat la retenție, a rămas sau a plecat?

    python -m retailagent.churn.labels [--data-dir data] [--out data/churn_labels.json]

Rulează fluxul complet (`pipeline.run_full`) și simulează rezultatul cu comportamentul ascuns din
`ground_truth.json` (`evaluate_final.ramane`), de două ori: fără nicio intervenție (ce s-ar întâmpla dacă banca
nu face nimic) și cu intervenția aleasă de agent. Scrie câmpurile observabile brute pe care pasul următor le
transformă în feature-uri. Agentul nu citește niciodată acest fișier.
"""
from __future__ import annotations

import argparse
import time
from collections import Counter
from pathlib import Path

from ..common import CONFIG_DIR, DATA_DIR, OUT_DIR, log_event, parse_date, read_json, setup_console, write_json, years_between
from ..evaluate_final import candidati_retentie, ramane
from ..pipeline import FullRun, run_full


def build_labels(full: FullRun, gt: list[dict]) -> list[dict]:
    cmp = {g["client_id"]: g["comportament"] for g in gt}
    etalon = {g["client_id"]: g.get("etalon", True) for g in gt}
    rows = []
    for c in candidati_retentie(full):
        case, offer = c["case"], c["offer"]
        a = full.by_case(case["case_id"])
        ci, check = a["input"], a["check"]
        cl, loan = ci.client, ci.loan
        it = next((i for i in offer["interventii"] if i["id"] == offer["interventie_aleasa"]), None)
        b_dupa = it["B_dupa"] if it else offer["B"]
        beh = cmp[case["client_id"]]
        leg = offer["legaturi"]
        rows.append({
            "client_id": case["client_id"], "case_id": case["case_id"], "loan_id": case["loan_id"], "etalon": etalon.get(case["client_id"], True),
            # observabile
            "produs": case["produs"], "tipologie": cl["tipologie_declarata"], "nivel": cl["nivel_relatie"],
            "vechime_ani": round(years_between(parse_date(cl["client_din"]), full.pf.today), 2),
            "nr_produse": len(cl.get("produse_atasate", [])), "sold": loan["sold_ramas"], "luni_ramase": offer["B_detalii"]["luni_ramase"],
            "tip_dobanda": loan["tip_dobanda"], "dobanda": loan["dobanda_curenta"], "marja": loan.get("marja"),
            "B": offer["B"], "cost_mutare": offer["B_detalii"]["cost_mutare"], "V": offer["V"],
            "legaturi": leg["scor"], **{f"legaturi_{k}": v for k, v in leg["componente"].items()},
            "semnale_active": offer["semnale_active"], "nr_semnale_active": len(offer["semnale_active"]),
            "semnale": [s["id"] for s in case["semnale"]], "plecare_scor": case["scoruri"]["plecare"], "banda": case["banda"],
            "interogari_bc": check["concluzii"].get("interogari_bc", 0), "dti_curent": check["concluzii"].get("dti_curent"),
            "salariu_la_alta_banca": bool(check["concluzii"].get("salariu_la_alta_banca")),
            "p_model_actual": offer["p"],
            # ce a făcut agentul
            "interventie_agent": offer["interventie_aleasa"], "cost_agent": offer["cost"], "B_dupa_agent": b_dupa,
            # etichete (simulate din comportamentul ascuns)
            "a_plecat_fara_interventie": not ramane(None, offer["B"], offer["B"], beh),
            "a_plecat_cu_agent": not ramane(offer["interventie_aleasa"], offer["B"], b_dupa, beh),
        })
    return rows


def rezumat(rows: list[dict]) -> dict:
    n = len(rows)
    out = {"candidati": n, "rata_plecare_fara_interventie": round(sum(r["a_plecat_fara_interventie"] for r in rows) / n, 4) if n else 0.0,
           "rata_plecare_cu_agent": round(sum(r["a_plecat_cu_agent"] for r in rows) / n, 4) if n else 0.0, "pe_nivel": {}, "pe_legaturi": {}}
    for nivel in ("standard", "gold", "platinum"):
        sub = [r for r in rows if r["nivel"] == nivel]
        if sub:
            out["pe_nivel"][nivel] = round(sum(r["a_plecat_fara_interventie"] for r in sub) / len(sub), 4)
    for nume, lo, hi in (("mici (<0.3)", 0.0, 0.3), ("medii (0.3-0.6)", 0.3, 0.6), ("mari (>=0.6)", 0.6, 1.01)):
        sub = [r for r in rows if lo <= r["legaturi"] < hi]
        if sub:
            out["pe_legaturi"][nume] = round(sum(r["a_plecat_fara_interventie"] for r in sub) / len(sub), 4)
    return out


def main(argv: list[str] | None = None) -> None:
    setup_console()
    ap = argparse.ArgumentParser(description="Eticheta de churn simulată din comportamentul ascuns (pentru antrenare).")
    ap.add_argument("--today")
    ap.add_argument("--data-dir", default=str(DATA_DIR))
    ap.add_argument("--out-dir", default=str(OUT_DIR))
    ap.add_argument("--config-dir", default=str(CONFIG_DIR))
    ap.add_argument("--out", default=None, help="implicit <data-dir>/churn_labels.json")
    a = ap.parse_args(argv)
    t0 = time.perf_counter()
    full = run_full(a.data_dir, a.out_dir, a.config_dir, a.today)
    gt = read_json(Path(a.data_dir) / "ground_truth.json")
    rows = build_labels(full, gt)
    out = Path(a.out or Path(a.data_dir) / "churn_labels.json")
    write_json(out, rows)
    r = rezumat(rows)
    dt = time.perf_counter() - t0
    print(f"Etichete de churn: {r['candidati']} candidați la retenție din {len(full.res.cases)} cazuri în {dt:.1f}s → {out}")
    print(f"  rata de plecare fără intervenție: {r['rata_plecare_fara_interventie']:.1%} · cu agentul: {r['rata_plecare_cu_agent']:.1%}")
    print("  fără intervenție, pe nivel: " + ", ".join(f"{k} {v:.0%}" for k, v in r["pe_nivel"].items()))
    print("  fără intervenție, pe legături: " + ", ".join(f"{k} {v:.0%}" for k, v in r["pe_legaturi"].items()))
    print("  intervenții ale agentului: " + ", ".join(f"{k}={v}" for k, v in Counter(x["interventie_agent"] for x in rows).most_common()))
    log_event(a.out_dir, "churn_labels", "done", candidati=r["candidati"], rata_fara=r["rata_plecare_fara_interventie"],
              rata_cu_agent=r["rata_plecare_cu_agent"], secunde=round(dt, 2))


if __name__ == "__main__":
    main()
