"""Fluxul complet într-un singur loc: scan → intake → coadă → verificări → retenție → recomandare.

`run_full` e folosit de explain, approve, evaluate și demo ca să nu dubleze logica. CLI-ul (M6-T1):

    python -m retailagent.pipeline [--skip-evaluate]
"""
from __future__ import annotations

import argparse
import json
import time
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path

from .buget import aloca_buget
from .checks import Mocks, load_mocks, run_all_checks
from .common import CONFIG_DIR, DATA_DIR, OUT_DIR, fmt_ron, log_event, setup_console, write_json
from .config_loader import Config, load_config
from .intake import run_intake
from .queue import QueueResult, build_queue, load_or_scan
from .recommend import build_recommendations
from .retention import build_offers
from .scan import Portfolio, load_portfolio, run_scan


@dataclass
class FullRun:
    pf: Portfolio
    cfg: Config
    res: QueueResult
    mocks: Mocks
    checks: list[dict]
    offers: list[dict]
    recs: list[dict]
    audit: list[dict]
    detections: list[dict] = field(default_factory=list)
    intake: list[dict] = field(default_factory=list)
    buget: dict = field(default_factory=dict)

    def by_case(self, case_id: str) -> dict:
        """Toate artefactele unui caz: case, input, trace, check, offer, rec."""
        case = next(c for c in self.res.cases if c["case_id"] == case_id)
        return {"case": case, "input": self.res.inputs[case_id], "trace": self.res.traces[case_id],
                "check": next(c for c in self.checks if c["case_id"] == case_id),
                "offer": next(o for o in self.offers if o["case_id"] == case_id),
                "rec": next(r for r in self.recs if r["case_id"] == case_id)}


def run_full(data_dir=DATA_DIR, out_dir=OUT_DIR, config_dir=CONFIG_DIR, today: str | None = None,
             cfg: Config | None = None, rescan: bool = False, timings: dict | None = None) -> FullRun:
    t = time.perf_counter()

    def lap(name: str) -> None:
        nonlocal t
        if timings is not None:
            timings[name] = round(time.perf_counter() - t, 3)
        t = time.perf_counter()

    cfg = cfg or load_config(config_dir)
    pf = load_portfolio(data_dir, today)
    det = run_scan(pf, cfg) if rescan else load_or_scan(pf, cfg, Path(out_dir))
    lap("scan")
    intake = run_intake(pf, cfg)
    lap("intake")
    res = build_queue(pf, cfg, det, intake)
    lap("queue")
    mocks = load_mocks(data_dir)
    checks = run_all_checks(pf, mocks, cfg, res)
    lap("checks")
    offers = build_offers(pf, cfg, res, checks)
    lap("retention")
    recs, audit = build_recommendations(pf, cfg, res, checks, offers, mocks)
    lap("recommend")
    buget = aloca_buget(recs, offers, cfg)          # plafonul lunar pe portofoliu: marchează ofertele peste plafon
    full = FullRun(pf, cfg, res, mocks, checks, offers, recs, audit)
    full.detections, full.intake, full.buget = det, intake, buget
    return full


ARTEFACTE = ("signals_detected.json", "intake_cases.json", "queue.json", "checks.json", "offers.json",
             "recommendations.json", "audit.jsonl")


def write_artifacts(full: FullRun, out_dir: Path) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    write_json(out_dir / "signals_detected.json", full.detections)
    write_json(out_dir / "intake_cases.json", full.intake)
    write_json(out_dir / "queue.json", full.res.cases)
    write_json(out_dir / "checks.json", full.checks)
    write_json(out_dir / "offers.json", full.offers)
    write_json(out_dir / "recommendations.json", full.recs)
    with open(out_dir / "audit.jsonl", "w", encoding="utf-8") as f:
        for row in full.audit:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")


def main(argv: list[str] | None = None) -> None:
    setup_console()
    ap = argparse.ArgumentParser(description="Fluxul complet: scan → intake → coadă → verificări → retenție → recomandare [→ evaluate → demo].")
    ap.add_argument("--today")
    ap.add_argument("--data-dir", default=str(DATA_DIR))
    ap.add_argument("--out-dir", default=str(OUT_DIR))
    ap.add_argument("--config-dir", default=str(CONFIG_DIR))
    ap.add_argument("--skip-evaluate", action="store_true")
    ap.add_argument("--skip-demo", action="store_true")
    a = ap.parse_args(argv)

    out = Path(a.out_dir)
    timings: dict[str, float] = {}
    t0 = time.perf_counter()
    full = run_full(a.data_dir, out, a.config_dir, a.today, rescan=True, timings=timings)
    write_artifacts(full, out)
    timings["scriere"] = round(time.perf_counter() - t0 - sum(timings.values()), 3)
    total = time.perf_counter() - t0

    cnt = Counter(r["recomandare"] for r in full.recs)
    bands = Counter(c["banda"] for c in full.res.cases)
    ex = sum(c["interogari_externe"].get("executate", 0) for c in full.checks)
    tot = sum(c["interogari_externe"]["rulare_tot"] for c in full.checks)
    cost = sum(o["cost"] for o in full.offers if o["interventie_aleasa"])
    print(f"Flux complet pe {len(full.pf.clients)} clienți, azi = {full.pf.today} → {out}/")
    print(f"  scan        {timings['scan']:>6.2f}s  {len(full.detections)} detecții")
    print(f"  intake      {timings['intake']:>6.2f}s  {len(full.intake)} cereri → cazuri")
    print(f"  queue       {timings['queue']:>6.2f}s  {len(full.res.cases)} cazuri · " + "  ".join(f"{b}={bands.get(b, 0)}" for b in full.cfg.priority.benzi))
    print(f"  checks      {timings['checks']:>6.2f}s  {ex} interogări externe din {tot} ({(tot - ex) / tot:.0%} evitate)")
    print(f"  retention   {timings['retention']:>6.2f}s  cost total propus {fmt_ron(cost)} RON")
    print(f"  recommend   {timings['recommend']:>6.2f}s  " + ", ".join(f"{k}={v}" for k, v in cnt.most_common()))
    print(f"  total       {total:>6.2f}s  → {', '.join(ARTEFACTE)}")
    log_event(out, "pipeline", "done", clienti=len(full.pf.clients), cazuri=len(full.res.cases), secunde=round(total, 3), pasi=timings)

    if not a.skip_evaluate:
        from .evaluate import main as evaluate_main
        print()
        evaluate_main(["--data-dir", a.data_dir, "--out-dir", a.out_dir, "--config-dir", a.config_dir])
    if not a.skip_demo:
        try:
            from .demo import main as demo_main
        except ImportError:
            print("\n(demo: modulul retailagent.demo nu există încă)")
        else:
            print()
            demo_main(["--data-dir", a.data_dir, "--out-dir", a.out_dir, "--config-dir", a.config_dir])


if __name__ == "__main__":
    main()
