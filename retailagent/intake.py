"""Intake: cererile clienților (data/requests.json) → cazuri cu sursa = client_request.

Fiecare cerere e legată de creditul vizat (detalii.loan_id sau detalii.produs_vizat). Cererile pentru
produse noi (credit_nou) sau fără produs (actualizare_date) rămân fără loan_id. Situațiile neașteptate
(client necunoscut, tip necunoscut, produs inexistent) nu opresc rularea: sunt marcate și logate.

    python -m retailagent.intake
"""
from __future__ import annotations

import argparse
from pathlib import Path

from .common import CONFIG_DIR, DATA_DIR, OUT_DIR, log_event, parse_date, setup_console, write_json
from .config_loader import Config, load_config
from .scan import Portfolio, load_portfolio


def match_loan(req: dict, loans: list[dict]) -> dict | None:
    det = req.get("detalii") or {}
    if det.get("loan_id"):
        return next((l for l in loans if l["loan_id"] == det["loan_id"]), None)
    produs = det.get("produs_vizat")
    if req["tip"] == "credit_nou" or produs is None:
        return None
    cand = [l for l in loans if l["produs"] == produs]
    return max(cand, key=lambda l: (l["sold_ramas"], l["loan_id"])) if cand else None


def run_intake(pf: Portfolio, cfg: Config, out_dir: Path | str | None = None) -> list[dict]:
    known = {c["client_id"] for c in pf.clients}
    cases = []
    for r in sorted(pf.requests, key=lambda r: r["request_id"]):
        avertizari = []
        if r["client_id"] not in known:
            if out_dir:
                log_event(out_dir, "intake", "client_necunoscut", request_id=r["request_id"], client_id=r["client_id"])
            continue
        rule = cfg.priority.cereri.get(r["tip"])
        if rule is None:
            avertizari.append(f"tip de cerere necunoscut: {r['tip']}")
        if parse_date(r["data"]) > pf.today:
            avertizari.append("cerere datată în viitor")
        loan = match_loan(r, pf.loans_by_client.get(r["client_id"], []))
        produs = (r.get("detalii") or {}).get("produs_vizat")
        if loan is None and produs and r["tip"] != "credit_nou":
            avertizari.append(f"clientul nu are un credit {produs} — caz nou fără credit")
        cases.append({
            "request_id": r["request_id"], "client_id": r["client_id"],
            "loan_id": loan["loan_id"] if loan else None, "produs": loan["produs"] if loan else produs,
            "tip": r["tip"], "data": r["data"], "detalii": r.get("detalii") or {}, "sursa": "client_request",
            "actiune_cerere": rule.actiune if rule else "procesare_cerere",
            "prioritate_min": rule.prioritate_min if rule else 0.0,
            "avertizari": avertizari,
        })
        if avertizari and out_dir:
            log_event(out_dir, "intake", "avertizare", request_id=r["request_id"], avertizari=avertizari)
    return cases


def main(argv: list[str] | None = None) -> None:
    setup_console()
    ap = argparse.ArgumentParser(description="Transformă cererile clienților în cazuri.")
    ap.add_argument("--today")
    ap.add_argument("--data-dir", default=str(DATA_DIR))
    ap.add_argument("--out-dir", default=str(OUT_DIR))
    ap.add_argument("--config-dir", default=str(CONFIG_DIR))
    a = ap.parse_args(argv)
    cfg = load_config(a.config_dir)
    pf = load_portfolio(a.data_dir, a.today)
    cases = run_intake(pf, cfg, a.out_dir)
    write_json(Path(a.out_dir) / "intake_cases.json", cases)
    print(f"Intake: {len(pf.requests)} cereri → {len(cases)} cazuri → {a.out_dir}/intake_cases.json")
    print(f"  {'cerere':<6} {'client':<6} {'credit':<6} {'produs':<16} {'tip':<31} {'acțiune cerere':<17} {'prio min':>8}")
    for c in cases:
        print(f"  {c['request_id']:<6} {c['client_id']:<6} {c['loan_id'] or '—':<6} {c['produs'] or '—':<16} "
              f"{c['tip']:<31} {c['actiune_cerere'] or '(semnal)':<17} {c['prioritate_min']:>8.2f}"
              + (f"  ⚠ {'; '.join(c['avertizari'])}" if c["avertizari"] else ""))
    log_event(a.out_dir, "intake", "done", cereri=len(pf.requests), cazuri=len(cases))


if __name__ == "__main__":
    main()
