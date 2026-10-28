"""Metricile modelului final (M5-T2): cifra-vedetă, % nu interveni, interogări evitate, acuratețe, cerințe dure."""
from __future__ import annotations

import json

import pytest

from retailagent.evaluate import main as evaluate_main
from retailagent.evaluate_final import (candidati_retentie, cerinte_dure_final, cifra_vedeta, eval_recomandari,
                                        eval_verificari, interogari_evitate, procent_nu_interveni, ramane)
from retailagent.pipeline import run_full
from retailagent.recommend import STARI


@pytest.fixture(scope="module")
def full(pipeline, tmp_path_factory):
    return run_full(pipeline["dir"], tmp_path_factory.mktemp("out"))


@pytest.fixture(scope="module")
def gt(pipeline):
    return json.loads((pipeline["dir"] / "ground_truth.json").read_text(encoding="utf-8"))


def test_simularea_comportamentului():
    cmp = {"prag_castig_plecare_ron": 10_000, "reactioneaza_la_informare": False, "accepta_pachet_salariu": True}
    assert ramane("nu_interveni", 5_000, 5_000, cmp) and not ramane("nu_interveni", 20_000, 20_000, cmp)
    assert not ramane("informare", 20_000, 20_000, cmp)
    assert ramane("informare", 20_000, 20_000, {**cmp, "reactioneaza_la_informare": True})
    assert ramane("pachet_salariu", 20_000, 19_000, cmp) and not ramane("pachet_salariu", 20_000, 19_000, {**cmp, "accepta_pachet_salariu": False})
    assert ramane("fix_3_ani", 20_000, 0, cmp) and not ramane("reducere_marja_0_2", 20_000, 15_000, cmp)


def test_cifra_vedeta(full, gt):
    cand = candidati_retentie(full)
    assert cand and all(not c["case"]["blocaje"] and c["case"]["scoruri"]["risc_credit"] < 0.7 for c in cand)
    h = cifra_vedeta(full, gt)
    assert set(h) >= {"candidati", "agent", "uniform", "uniform_aleasa", "economie_ron", "economie_pct", "concluzie"}
    a = h["agent"]
    assert a["cost"] == pytest.approx(sum(c["offer"]["cost"] for c in cand), abs=1)
    assert 0 <= a["rata_ramanere"] <= 1 and a["retinuti"] <= h["candidati"]
    assert set(h["uniform"]) == {"0.2", "0.4", "0.6"}
    for u in h["uniform"].values():
        assert u["cost"] >= 0 and 0 <= u["rata_ramanere"] <= 1
    if h["uniform_aleasa"] is not None:
        assert h["uniform"][h["uniform_aleasa"]]["rata_ramanere"] >= a["rata_ramanere"]
        assert h["economie_ron"] == pytest.approx(h["uniform"][h["uniform_aleasa"]]["cost"] - a["cost"], abs=1)
    assert "RON" in h["concluzie"]


def test_procent_si_interogari(full):
    p = procent_nu_interveni(full)
    assert 0 < p["procent"] < 1 and p["nu_interveni"] + p["altele"] == p["total"]
    q = interogari_evitate(full)
    assert q["executate"] < q["rulare_tot"] and q["evitate"] == q["rulare_tot"] - q["executate"] and 0 < q["procent"] < 1


def test_acuratete_recomandari_si_verificari(full, gt):
    r = eval_recomandari(full, gt)
    assert r["acuratete"] >= 0.9 and r["total"] == 49
    labels = list(STARI) + ["—"]
    assert set(r["matrice_confuzie"]) == set(labels)
    assert sum(sum(row.values()) for row in r["matrice_confuzie"].values()) == 50
    v = eval_verificari(full, gt)
    assert v["asteptate"] == 3 and v["corecte"] == 3 and v["false_pozitive"] == 0


def test_cerinte_dure_final(full):
    h = cerinte_dure_final(full)
    assert set(h) == {"oferte_catre_risc_activ", "oferte_in_afara_limitelor", "oferte_pe_cazuri_blocate", "expirare_sub_30_zile_nu_P1"}
    assert all(v["incalcari"] == 0 for v in h.values()), h


def test_evaluate_main_scrie_sectiunea(pipeline, tmp_path, capsys):
    out = tmp_path / "out"
    evaluate_main(["--data-dir", str(pipeline["dir"]), "--out-dir", str(out)])
    rep = json.loads((out / "evaluation.json").read_text(encoding="utf-8"))
    assert "model_final" in rep and "cifra_vedeta" in rep["model_final"]
    assert rep["detectie"]["global"]["f1"] == 1.0 and rep["benzi"]["acuratete"] == 1.0        # Modulul 1 neschimbat
    txt = capsys.readouterr().out
    assert "Model final" in txt and "Cifra-vedetă" in txt
