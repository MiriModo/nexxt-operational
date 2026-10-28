"""Scanner: rulează toate semnalele din config peste portofoliu → out/signals_detected.json.

    python -m retailagent.scan [--today 2026-10-28] [--data-dir data] [--out-dir out]
"""
from __future__ import annotations

import argparse
import time
from collections import Counter, defaultdict
from dataclasses import dataclass, replace
from datetime import date
from pathlib import Path

from .common import CONFIG_DIR, DATA_DIR, OUT_DIR, log_event, read_json, resolve_today, setup_console, write_json
from .config_loader import Config, load_config
from .signals import REGISTRY, Context
from .signals.inflows import Flows, Patterns, analyze


@dataclass
class Portfolio:
    today: date
    clients: list[dict]
    loans: list[dict]
    loans_by_client: dict[str, list[dict]]
    payments_by_loan: dict[str, list[dict]]
    tx_by_client: dict[str, list[dict]]
    employers: dict[str, dict]
    market: dict
    requests: list[dict]
    requests_by_client: dict[str, list[dict]]


def normalizeaza_valuta(loans: list[dict], payments: list[dict], market: dict) -> None:
    """Creditele în valută: soldul, rata, suma, limita, evaluarea și restanțele se exprimă în RON (curs din market.json),
    iar valorile originale rămân în câmpurile `*_valuta`. Toate calculele de după lucrează în RON; afișarea arată moneda."""
    curs = {"RON": 1.0, "EUR": float(market.get("curs_eur", 5.0))}
    for l in loans:
        m = l.get("moneda", "RON")
        if m == "RON" or l.get("sold_valuta") is not None:
            continue
        k = curs.get(m, 1.0)
        l["curs"] = k
        for f in ("sold_ramas", "rata_lunara", "suma_initiala", "limita"):
            if l.get(f) is not None:
                l[f"{f.split('_')[0]}_valuta"] = l[f]
                l[f] = round(l[f] * k, 2)
        if l.get("garantie") and l["garantie"].get("valoare_evaluare"):
            l["garantie"]["valoare_evaluare_valuta"] = l["garantie"]["valoare_evaluare"]
            l["garantie"]["valoare_evaluare"] = round(l["garantie"]["valoare_evaluare"] * k, 2)
    fx = {l["loan_id"]: l["curs"] for l in loans if l.get("curs")}
    for p in payments:
        if p["loan_id"] in fx and p.get("suma_restanta"):
            p["suma_restanta"] = round(p["suma_restanta"] * fx[p["loan_id"]], 2)


def load_portfolio(data_dir: Path | str = DATA_DIR, today: str | None = None) -> Portfolio:
    d = Path(data_dir)
    loans = read_json(d / "loans.json")
    requests = read_json(d / "requests.json")
    market = read_json(d / "market.json")
    payments = read_json(d / "payment_history.json")
    normalizeaza_valuta(loans, payments, market)
    by_client, pay, tx, req = defaultdict(list), defaultdict(list), defaultdict(list), defaultdict(list)
    for l in loans:
        by_client[l["client_id"]].append(l)
    for p in payments:
        pay[p["loan_id"]].append(p)
    for v in pay.values():
        v.sort(key=lambda p: p["luna"])
    for t in read_json(d / "transactions.json"):
        tx[t["client_id"]].append(t)
    for r in requests:
        req[r["client_id"]].append(r)
    return Portfolio(resolve_today(today, d), read_json(d / "clients.json"), loans, dict(by_client), dict(pay),
                     dict(tx), {e["angajator_id"]: e for e in read_json(d / "employers.json")},
                     market, requests, dict(req))


def codebitor_index(pf: Portfolio) -> dict[str, list[dict]]:
    """client_id -> creditele altora pe care e codebitor (o singură trecere prin portofoliu)."""
    out: dict[str, list[dict]] = defaultdict(list)
    for l in pf.loans:
        for c in l.get("codebitori", []):
            if c.get("client_id") and c["client_id"] != l["client_id"]:
                out[c["client_id"]].append(l)
    return dict(out)


def check_registry(cfg: Config) -> None:
    yaml_ids = {s.id for s in cfg.signals.active()}
    missing = yaml_ids - set(REGISTRY)
    if missing:
        raise SystemExit(f"Semnale din signals.yaml fără funcție @signal: {sorted(missing)}")
    for s in cfg.signals.active():
        reg = REGISTRY[s.id]
        if reg.familie != s.familie or reg.nivel != s.nivel:
            raise SystemExit(f"{s.id}: familie/nivel diferă între YAML ({s.familie}/{s.nivel}) "
                             f"și cod ({reg.familie}/{reg.nivel})")


def client_context(pf: Portfolio, client: dict, flows: Flows, codebitor_la: list[dict] | None = None) -> Context:
    cid = client["client_id"]
    loans = pf.loans_by_client.get(cid, [])
    cod = codebitor_la if codebitor_la is not None else codebitor_index(pf).get(cid, [])
    return Context(today=pf.today, client=client, loan=None, loans=loans,
                   transactions=pf.tx_by_client.get(cid, []),
                   payments={l["loan_id"]: pf.payments_by_loan.get(l["loan_id"], []) for l in [*loans, *cod]},
                   employer=pf.employers.get(client.get("angajator_id")), market=pf.market,
                   requests=pf.requests_by_client.get(cid, []), flows=flows, codebitor_la=cod)


def client_flows(pf: Portfolio, cfg: Config, client_id: str, patterns: Patterns | None = None) -> Flows:
    patterns = patterns or Patterns(cfg.signals.tipare)
    return analyze(pf.tx_by_client.get(client_id, []), pf.today, patterns, cfg.signals.recurenta)


def run_scan(pf: Portfolio, cfg: Config) -> list[dict]:
    check_registry(cfg)
    patterns = Patterns(cfg.signals.tipare)
    active = cfg.signals.active()
    codebitori = codebitor_index(pf)
    out: list[dict] = []
    for client in pf.clients:
        base = client_context(pf, client, client_flows(pf, cfg, client["client_id"], patterns), codebitori.get(client["client_id"], []))
        targets = [None] + base.loans
        for loan in targets:
            for s in active:
                if (s.nivel == "client") != (loan is None):
                    continue
                res = REGISTRY[s.id].fn(replace(base, loan=loan, params=s.parametri))
                if res.scor > 0:
                    out.append({"client_id": client["client_id"], "loan_id": loan["loan_id"] if loan else None,
                                "id": s.id, "familie": s.familie, "scor": round(res.scor, 4),
                                "dovada": res.dovada, "detalii": res.detalii})
    return out


def main(argv: list[str] | None = None) -> None:
    setup_console()
    ap = argparse.ArgumentParser(description="Scanează portofoliul după semnale.")
    ap.add_argument("--today")
    ap.add_argument("--data-dir", default=str(DATA_DIR))
    ap.add_argument("--out-dir", default=str(OUT_DIR))
    ap.add_argument("--config-dir", default=str(CONFIG_DIR))
    a = ap.parse_args(argv)

    t0 = time.perf_counter()
    cfg = load_config(a.config_dir)
    pf = load_portfolio(a.data_dir, a.today)
    det = run_scan(pf, cfg)
    write_json(Path(a.out_dir) / "signals_detected.json", det)
    dt = time.perf_counter() - t0

    fam = {s.id: s.familie for s in cfg.signals.semnale}
    cnt = Counter(d["id"] for d in det)
    cli = {sid: len({d["client_id"] for d in det if d["id"] == sid}) for sid in cnt}
    print(f"Scanare {len(pf.clients)} clienți / {len(pf.loans)} credite, azi = {pf.today}  "
          f"→ {len(det)} detecții în {dt:.2f}s  → {a.out_dir}/signals_detected.json")
    print(f"  {'semnal':<26} {'familie':<14} {'detecții':>8} {'clienți':>8}")
    for s in cfg.signals.active():
        if s.id in cnt:
            print(f"  {s.id:<26} {fam[s.id]:<14} {cnt[s.id]:>8} {cli[s.id]:>8}")
    print("  exemple:")
    shown = set()
    for d in det:
        if d["id"] not in shown and d["id"] in ("expirare_dobanda_fixa", "gap_piata_bani", "rata_alt_creditor",
                                                 "venit_in_scadere", "card_stres", "ci_expirata"):
            shown.add(d["id"])
            print(f"    {d['client_id']} {d['loan_id'] or '-':<6} {d['id']:<24} {d['scor']:.2f}  {d['dovada']}")
    log_event(a.out_dir, "scan", "done", clienti=len(pf.clients), detectii=len(det), secunde=round(dt, 3))


if __name__ == "__main__":
    main()
