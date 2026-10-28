from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest

from retailagent.config_loader import load_config
from retailagent.generate import generate
from retailagent.intake import run_intake
from retailagent.queue import build_queue
from retailagent.scan import load_portfolio, run_scan

ROOT = Path(__file__).resolve().parents[1]
TODAY = date(2026, 10, 28)


@pytest.fixture(scope="session")
def cfg():
    return load_config(ROOT / "config")


@pytest.fixture(scope="session")
def pipeline(cfg, tmp_path_factory):
    """Portofoliul standard (50 clienți, seed 42) trecut prin scan → intake → coadă."""
    d = tmp_path_factory.mktemp("data")
    generate(50, 42, TODAY.isoformat(), d)
    pf = load_portfolio(d)
    det = run_scan(pf, cfg)
    res = build_queue(pf, cfg, det, run_intake(pf, cfg))
    return {"dir": d, "pf": pf, "det": det, "res": res, "cases": res.cases}
