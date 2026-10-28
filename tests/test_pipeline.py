"""O singură comandă produce toate artefactele (M6-T1)."""
from __future__ import annotations

import json
import time

from retailagent.pipeline import ARTEFACTE, main

CHEI_CAZ = ["case_id", "client_id", "loan_id", "produs", "sursa", "request_id", "semnale", "scoruri", "banda",
            "deadline", "motive_top3", "actiune_propusa", "blocaje", "creat_la"]


def test_pipeline_scrie_tot_sub_5_secunde(pipeline, tmp_path, capsys):
    out = tmp_path / "out"
    t0 = time.perf_counter()
    main(["--data-dir", str(pipeline["dir"]), "--out-dir", str(out), "--skip-evaluate", "--skip-demo"])
    dt = time.perf_counter() - t0
    assert dt < 5.0, dt
    for name in ARTEFACTE:
        assert (out / name).exists(), name
    assert not (out / "evaluation.json").exists()
    q = json.loads((out / "queue.json").read_text(encoding="utf-8"))
    assert q and all(list(c) == CHEI_CAZ for c in q)                      # schema Modulului 1 neschimbată
    recs = json.loads((out / "recommendations.json").read_text(encoding="utf-8"))
    assert len(recs) == len(q)
    assert len((out / "audit.jsonl").read_text(encoding="utf-8").splitlines()) > len(q)
    txt = capsys.readouterr().out
    for step in ("scan", "intake", "queue", "checks", "retention", "recommend"):
        assert step in txt
    assert "Flux complet" in txt


def test_pipeline_cu_evaluate(pipeline, tmp_path):
    out = tmp_path / "out"
    main(["--data-dir", str(pipeline["dir"]), "--out-dir", str(out), "--skip-demo"])
    rep = json.loads((out / "evaluation.json").read_text(encoding="utf-8"))
    assert rep["model_final"]["cerinte_dure"]["oferte_catre_risc_activ"]["incalcari"] == 0
