"""Execuția verificărilor în trepte, cu mock-urile externe (M2-T3), pe portofoliul generat."""
from __future__ import annotations

import json

import pytest

from retailagent.checks import load_mocks, run_all_checks

STATUSURI = {"ok", "avertizare", "fail", "neexecutat"}


@pytest.fixture(scope="session")
def checks(pipeline, cfg):
    mocks = load_mocks(pipeline["dir"])
    return {r["case_id"]: r for r in run_all_checks(pipeline["pf"], mocks, cfg, pipeline["res"])}


def scen(pipeline, nr):
    return pipeline["pf"].clients[nr - 1]["client_id"]


def of_client(checks, cid):
    return [r for r in checks.values() if r["client_id"] == cid]


def test_fiecare_caz_are_plan_si_rezultate(pipeline, checks):
    assert set(checks) == {c["case_id"] for c in pipeline["cases"]}
    for r in checks.values():
        assert {x["id"] for x in r["rezultate"]} == {x["id"] for x in r["plan"]}
        assert all(x["status"] in STATUSURI for x in r["rezultate"])
        assert all(x["dovada"] for x in r["rezultate"] if x["status"] != "neexecutat")
        ie = r["interogari_externe"]
        assert ie["executate"] <= ie["planificate"] <= ie["rulare_tot"]
        assert r["oprit_la"] is None or r["oprit_la"] in cfg_trepte(pipeline)


def cfg_trepte(pipeline):
    return ["intern", "anaf", "biroul_credit", "crc", "garantie", "eligibilitate"]


def test_oprirea_la_primul_pas_picat(pipeline, checks):
    ordine = ["intern", "anaf", "biroul_credit", "crc", "garantie", "eligibilitate"]
    for nr, treapta in ((46, "biroul_credit"), (47, "crc"), (5, "garantie")):
        rs = of_client(checks, scen(pipeline, nr))
        assert rs, nr
        assert any(r["oprit_la"] == treapta for r in rs), (nr, [r["oprit_la"] for r in rs])
        for r in rs:
            assert r["oprit_la"] in (None, treapta), (nr, r["oprit_la"])     # un caz fără motiv de CF nu o cere
            if r["oprit_la"] is None:
                continue
            assert r["verificare_picata"] is not None
            picata = next(x for x in r["rezultate"] if x["id"] == r["verificare_picata"])
            assert picata["status"] == "fail" and picata["sursa"]
            # tot ce e după treapta picată e neexecutat, tot ce e înainte e executat
            for x in r["rezultate"]:
                if ordine.index(x["treapta"]) > ordine.index(treapta):
                    assert x["status"] == "neexecutat" and "oprit la" in x["dovada"]
                elif ordine.index(x["treapta"]) < ordine.index(treapta):
                    assert x["status"] != "neexecutat"


def test_clientii_curati_nu_se_opresc(pipeline, checks):
    for nr in (1, 3, 8, 13, 16, 45):
        for r in of_client(checks, scen(pipeline, nr)):
            assert r["oprit_la"] is None, (nr, r["verificare_picata"])


def test_salariu_la_alta_banca_din_anaf(pipeline, checks):
    for nr, asteptat in ((13, True), (14, True), (12, False), (15, False), (1, False)):
        for r in of_client(checks, scen(pipeline, nr)):
            assert r["concluzii"]["salariu_la_alta_banca"] is asteptat, nr
    # ANAF arată venitul pentru C0013 deși la noi nu mai intră
    r = of_client(checks, scen(pipeline, 13))[0]
    assert r["concluzii"]["venit_lunar_anaf"] > 5_000
    assert sum(list(r["concluzii"]["venit_pe_luna"].values())[-2:]) == 0       # la noi nu a mai intrat nimic


def test_blocatii_nu_primesc_interogari_externe(pipeline, checks):
    for nr in (17, 30, 32, 33, 36, 39):
        for r in of_client(checks, scen(pipeline, nr)):
            assert r["interogari_externe"]["executate"] == 0
            assert [x["id"] for x in r["plan"]] == ["identitate_kyc"]


def test_concluzii_venit_dti_ltv(pipeline, checks):
    r = of_client(checks, scen(pipeline, 1))[0]           # salariat gold, ipotecar + card
    c = r["concluzii"]
    assert c["venit_lunar"] > 0 and 0 < c["dti_curent"] < 1
    assert c["ltv_dosar"] is not None and c["ltv_actual"] is not None
    assert c["interogari_bc"] >= 0
    assert c["cost_mutare"] > 0 and c["scenarii"]["dobanda_ramai"] > c["scenarii"]["dobanda_piata"]


def test_interogari_evitate_la_nivel_de_portofoliu(checks):
    tot = sum(r["interogari_externe"]["rulare_tot"] for r in checks.values())
    executate = sum(r["interogari_externe"]["executate"] for r in checks.values())
    assert 0 < executate < tot


def test_checks_json_este_serializabil(checks):
    json.dumps(list(checks.values()), ensure_ascii=False)
