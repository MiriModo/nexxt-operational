"""CLI-ul modelului de retenție (M3-T3): out/offers.json + textul pentru consilier."""
from __future__ import annotations

import json
import time

import pytest

from retailagent.checks import load_mocks, run_all_checks
from retailagent.retention import build_offers, explicatie_oferta, main

CHEI = {"case_id", "client_id", "loan_id", "produs", "B", "p", "V", "legaturi", "semnale_active", "interventie_aleasa",
        "eticheta", "cost", "p_dupa", "alternative", "motiv_alegere", "explicatie", "interventii"}


@pytest.fixture(scope="session")
def offers(pipeline, cfg):
    pf, res = pipeline["pf"], pipeline["res"]
    checks = run_all_checks(pf, load_mocks(pipeline["dir"]), cfg, res)
    t0 = time.perf_counter()
    rows = build_offers(pf, cfg, res, checks)
    assert time.perf_counter() - t0 < 1.0
    return {r["case_id"]: r for r in rows}


def scen(pipeline, nr):
    return pipeline["pf"].clients[nr - 1]["client_id"]


def of_client(offers, cid, produs=None):
    return [o for o in offers.values() if o["client_id"] == cid and (produs is None or o["produs"] == produs)]


def test_un_rand_per_caz_cu_cheile_cerute(offers, pipeline):
    assert set(offers) == {c["case_id"] for c in pipeline["cases"]}
    for o in offers.values():
        assert CHEI <= set(o), CHEI - set(o)
        assert isinstance(o["alternative"], list) and len(o["alternative"]) <= 3
        assert o["explicatie"] and "RON" in o["explicatie"] or o["interventie_aleasa"] is None
    json.dumps(list(offers.values()), ensure_ascii=False)


def test_alegerile_pe_date(offers, pipeline, cfg):
    assert of_client(offers, scen(pipeline, 13), "ipotecar")[0]["interventie_aleasa"] == "pachet_salariu"
    assert of_client(offers, scen(pipeline, 14), "imobiliar")[0]["interventie_aleasa"] == "informare"
    assert of_client(offers, scen(pipeline, 4))[0]["interventie_aleasa"] == "nu_interveni"
    assert of_client(offers, scen(pipeline, 1), "ipotecar")[0]["interventie_aleasa"] == "fix_3_ani"
    prag = cfg.priority.risc_credit.blocheaza_retentia_daca
    risc = [o for c in pipeline["cases"] if c["scoruri"]["risc_credit"] >= prag and not c["blocaje"]
            for o in [offers[c["case_id"]]]]
    assert risc and all(o["interventie_aleasa"] in ("ajustare_maturitate", "pauza_rata") for o in risc)
    blocate = [offers[c["case_id"]] for c in pipeline["cases"] if c["blocaje"]]
    assert blocate and all(o["interventie_aleasa"] is None for o in blocate)


def test_textul_pentru_consilier(offers, pipeline):
    o = of_client(offers, scen(pipeline, 1), "ipotecar")[0]
    t = o["explicatie"]
    assert t.startswith("Clientul ar câștiga") and "RON plecând" in t and "p = " in t
    assert "Oferta minimă" in t and "sub 20%" in t and "cost" in t and "valoare" in t
    assert "Alternativ" in t and "Recomandare:" in t
    assert explicatie_oferta(o) == t
    # restructurare
    r = of_client(offers, scen(pipeline, 2))[0]
    assert "risc de credit" in r["explicatie"].lower() and "restructurare" in r["explicatie"].lower()
    # nu interveni
    n = of_client(offers, scen(pipeline, 4))[0]
    assert "nu interveni" in n["explicatie"].lower()
    # blocat
    b = of_client(offers, scen(pipeline, 17))[0]
    assert "blocat" in b["explicatie"].lower()


def test_cli_scrie_offers_json(pipeline, tmp_path):
    out = tmp_path / "out"
    main(["--data-dir", str(pipeline["dir"]), "--out-dir", str(out), "--top", "2"])
    rows = json.loads((out / "offers.json").read_text(encoding="utf-8"))
    assert len(rows) == len(pipeline["cases"])
