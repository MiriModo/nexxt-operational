"""Modelul de churn (planul 2): feature-uri, interfață, test de aur cu sigmoidul, antrenare, model antrenat, fallback."""
from __future__ import annotations

import json
import warnings
from pathlib import Path

import pytest

from retailagent.churn.features import FEATURE_NAMES, features, vector
from retailagent.churn.labels import build_labels
from retailagent.churn.model import SigmoidChurn, TrainedChurn, get_model, sigmoid
from retailagent.churn.train import train
from retailagent.evaluate_final import cerinte_dure_final, cifra_vedeta
from retailagent.generate import generate
from retailagent.pipeline import run_full
from retailagent.retention import prob_plecare

ROOT = Path(__file__).resolve().parents[1]
TODAY = "2026-10-28"


@pytest.fixture(scope="module")
def antrenat(tmp_path_factory):
    """Portofoliu de 1.500 → etichete → model antrenat în tmp (nu atinge models/ din repo)."""
    d = tmp_path_factory.mktemp("churn")
    generate(1500, 42, TODAY, d)
    full = run_full(d, d / "out", ROOT / "config", rescan=True)
    gt = json.loads((d / "ground_truth.json").read_text(encoding="utf-8"))
    rows = build_labels(full, gt)
    (d / "churn_labels.json").write_text(json.dumps(rows, ensure_ascii=False), encoding="utf-8")
    meta = train(d / "churn_labels.json", d / "models", "test", "auto", 42)
    return {"dir": d, "full": full, "gt": gt, "rows": rows, "meta": meta, "cale": d / "models" / "churn_test.pkl"}


def test_features_au_ordinea_fixa(pipeline, cfg):
    full = run_full(pipeline["dir"], pipeline["dir"] / "out_f", ROOT / "config")
    o = next(o for o in full.offers if o["loan_id"])
    x = o["features"]
    assert tuple(x) == FEATURE_NAMES and len(vector(x)) == len(FEATURE_NAMES)
    assert all(isinstance(v, float) for v in x.values())
    assert 0 <= x["B_norm"] <= cfg.retention.B_norm_max and 0 <= x["legaturi"] <= 1
    # același client, aceleași intrări → același vector (determinism) și fără câmpuri din comportament
    ci = full.res.inputs[o["case_id"]]
    check = next(c for c in full.checks if c["case_id"] == o["case_id"])
    again = features(o["B"], o["legaturi"], o["semnale_active"], ci.client, ci.loan, check["concluzii"], full.pf.today, cfg, o["B_detalii"]["luni_ramase"])
    assert again == x and "prag" not in " ".join(x)


def test_sigmoid_churn_reproduce_formula(cfg):
    m = SigmoidChurn(cfg)
    for B, n, leg in ((0, 0, 0.0), (15_000, 1, 0.5), (60_000, 2, 1.0)):
        x = {"B_norm": min(B / cfg.retention.B_referinta_ron, cfg.retention.B_norm_max), "n_active": n, "legaturi": leg}
        assert sigmoid(m.predict_logit(x)) == pytest.approx(prob_plecare(B, n, leg, cfg))
    assert get_model(cfg).nume == "sigmoid"


def test_etichetele_contin_feature_urile(antrenat):
    rows = antrenat["rows"]
    assert all(r.get("features") and tuple(r["features"]) == FEATURE_NAMES for r in rows)


def test_antrenarea_produce_model_calibrat(antrenat):
    meta, cale = antrenat["meta"], antrenat["cale"]
    assert cale.exists() and (cale.parent / "churn_test.json").exists()
    m = meta["metrici"]
    assert m["auc"] >= 0.7 and m["brier"] <= 0.22 and m["ece"] <= 0.12, m
    assert meta["n_antrenare"] + meta["n_test"] == meta["n"] and meta["tip"] in ("logistic", "boosting")
    assert set(meta["candidati"]) == {"logistic", "boosting"}
    # split pe clienți: niciun client în ambele părți (verificat prin GroupShuffleSplit → n_test ≈ 20%)
    assert 0.12 <= meta["n_test"] / meta["n"] <= 0.28


def test_modelul_antrenat_prezice_si_explica(antrenat, cfg):
    m = TrainedChurn.load(antrenat["cale"])
    rows = antrenat["rows"]
    xs = [r["features"] for r in rows[:50]]
    lg = m.predict_logit_batch(xs)
    assert len(lg) == 50 and all(0 < sigmoid(v) < 1 for v in lg)
    assert m.predict_logit(xs[0]) == pytest.approx(lg[0])
    contrib = m.explain(xs[0])
    assert contrib and all(isinstance(c[1], float) for c in contrib)
    # B mai mare → p mai mare (monotonie pe feature-ul principal), în medie
    sus = [{**x, "B_norm": 2.0, "B_log": 0.9} for x in xs]
    jos = [{**x, "B_norm": 0.0, "B_log": 0.0} for x in xs]
    assert sum(m.predict_logit_batch(sus)) > sum(m.predict_logit_batch(jos))


def test_fluxul_cu_modelul_antrenat(antrenat, cfg):
    c = cfg.model_copy(deep=True)
    c.retention.churn.model = "antrenat"
    c.retention.churn.cale = str(antrenat["cale"])
    d = antrenat["dir"]
    full = run_full(d, d / "out2", ROOT / "config", cfg=c, rescan=True)
    assert full.offers[0]["model_churn"]["nume"] == "antrenat"
    assert all(v["incalcari"] == 0 for v in cerinte_dure_final(full).values())
    h = cifra_vedeta(full, antrenat["gt"])
    assert 0 <= h["agent"]["rata_ramanere"] <= 1 and h["agent"]["cost"] >= 0
    # același meniu și aceleași constrângeri: fezabilitatea nu depinde de model
    sig = antrenat["full"].offers
    for a, b in zip(sig, full.offers):
        assert [i["fezabil"] for i in a["interventii"]] == [i["fezabil"] for i in b["interventii"]]


def test_fallback_cand_modelul_lipseste(cfg):
    c = cfg.model_copy(deep=True)
    c.retention.churn.model = "antrenat"
    c.retention.churn.cale = "models/nu_exista.pkl"
    with warnings.catch_warnings(record=True) as w:
        warnings.simplefilter("always")
        assert get_model(c).nume == "sigmoid" and any("lipsește" in str(x.message) for x in w)
    c.retention.churn.fallback_sigmoid = False
    c.retention.churn.cale = "models/nu_exista_2.pkl"
    with pytest.raises(FileNotFoundError):
        get_model(c)


def test_schema_diferita_e_refuzata(antrenat):
    import joblib
    b = joblib.load(antrenat["cale"])
    b["feature_names"] = b["feature_names"][:-1]
    with pytest.raises(ValueError, match="schem"):
        TrainedChurn(b, "x")
