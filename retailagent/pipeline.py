"""Fluxul complet într-un singur loc: scan → intake → coadă → verificări → retenție → recomandare.

`run_full` e folosit de explain, approve, evaluate și demo ca să nu dubleze logica. CLI-ul (M6-T1):

    python -m retailagent.pipeline [--skip-evaluate]
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from .checks import Mocks, load_mocks, run_all_checks
from .common import CONFIG_DIR, DATA_DIR, OUT_DIR
from .config_loader import Config
from .queue import QueueResult, run_pipeline
from .recommend import build_recommendations
from .retention import build_offers
from .scan import Portfolio


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

    def by_case(self, case_id: str) -> dict:
        """Toate artefactele unui caz: case, input, trace, check, offer, rec."""
        case = next(c for c in self.res.cases if c["case_id"] == case_id)
        return {"case": case, "input": self.res.inputs[case_id], "trace": self.res.traces[case_id],
                "check": next(c for c in self.checks if c["case_id"] == case_id),
                "offer": next(o for o in self.offers if o["case_id"] == case_id),
                "rec": next(r for r in self.recs if r["case_id"] == case_id)}


def run_full(data_dir=DATA_DIR, out_dir=OUT_DIR, config_dir=CONFIG_DIR, today: str | None = None,
             cfg: Config | None = None, rescan: bool = False) -> FullRun:
    pf, cfg, res = run_pipeline(data_dir, out_dir, config_dir, today, cfg=cfg, rescan=rescan)
    mocks = load_mocks(data_dir)
    checks = run_all_checks(pf, mocks, cfg, res)
    offers = build_offers(pf, cfg, res, checks)
    recs, audit = build_recommendations(pf, cfg, res, checks, offers, mocks)
    return FullRun(pf, cfg, res, mocks, checks, offers, recs, audit)
