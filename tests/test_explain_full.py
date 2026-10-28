"""Explicația completă a unui caz (M5-T1): coadă + verificări + retenție + recomandare."""
from __future__ import annotations

import pytest

from retailagent.explain import explain_full, main
from retailagent.pipeline import run_full

SECTIUNI = ("── Semnale", "── Calcul", "── De ce", "── Verificări", "── Retenție", "── Recomandare")


@pytest.fixture(scope="module")
def full(pipeline, tmp_path_factory):
    out = tmp_path_factory.mktemp("out")
    return run_full(pipeline["dir"], out)


def scen(pipeline, nr):
    return pipeline["pf"].clients[nr - 1]["client_id"]


def test_run_full_are_toate_artefactele(full, pipeline):
    n = len(pipeline["cases"])
    assert len(full.res.cases) == n == len(full.checks) == len(full.offers) == len(full.recs)
    assert full.audit and full.mocks.anaf and full.cfg.retention.p_tinta


def test_explain_full_pentru_orice_caz(full):
    for case in full.res.cases:
        txt = explain_full(case, full)
        for s in SECTIUNI:
            assert s in txt, (case["case_id"], s)
        assert case["case_id"] in txt and "Recomandare:" in txt


def test_continutul_sectiunilor(full, pipeline):
    by_client = {}
    for c in full.res.cases:
        by_client.setdefault(c["client_id"], c)
    t46 = explain_full(by_client[scen(pipeline, 46)], full)
    assert "oprit la biroul_credit" in t46 and "istoric_biroul_credit" in t46 and "RESPINS" in t46
    t13 = explain_full(next(c for c in full.res.cases if c["client_id"] == scen(pipeline, 13) and c["produs"] == "ipotecar"), full)
    assert "pachet_salariu" in t13 and "legături" in t13 and "B = " in t13 and "p = " in t13
    assert "►" in t13 and "cost" in t13 and "documente" in t13.lower()
    t17 = explain_full(by_client[scen(pipeline, 17)], full)
    assert "blocat" in t17.lower() and "singura verificare" in t17
    t4 = explain_full(by_client[scen(pipeline, 4)], full)
    assert "NU INTERVENI" in t4


def test_cli_afiseaza_explicatia_completa(pipeline, tmp_path, capsys):
    out = tmp_path / "out"
    main(["Q0001", "--data-dir", str(pipeline["dir"]), "--out-dir", str(out)])
    txt = capsys.readouterr().out
    for s in SECTIUNI:
        assert s in txt
