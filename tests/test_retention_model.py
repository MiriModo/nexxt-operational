"""Modelul de retenție (M3-T1): B din grafice, legăturile cu banca, V, p sigmoid."""
from __future__ import annotations

from datetime import date

import pytest

from retailagent.retention import castig_plecare, legaturi, prob_plecare, semnale_active, valoare_client

TODAY = date(2026, 10, 28)


def client_of(pipeline, cid):
    return next(c for c in pipeline["pf"].clients if c["client_id"] == cid)


def loan_of(pipeline, cid, produs):
    return next(l for l in pipeline["pf"].loans_by_client[cid] if l["produs"] == produs)


def test_B_pozitiv_pe_ipotecar_cu_gap_si_aproape_zero_pe_card(pipeline, cfg):
    pf = pipeline["pf"]
    b = castig_plecare(loan_of(pipeline, "C0001", "ipotecar"), TODAY, pf.market, cfg)
    assert b["B"] > 50_000                                   # 400k, 22 ani, gap ~3 pp după expirare
    assert b["dobanda_la_noi"] > b["dobanda_piata"] > 0 and b["cost_mutare"] > 0
    assert b["B"] == pytest.approx(b["dobanda_la_noi"] - b["dobanda_piata"] - b["cost_mutare"], abs=1)
    card = castig_plecare(loan_of(pipeline, "C0001", "card_credit"), TODAY, pf.market, cfg)
    assert card["B"] < 500                                   # 0,9 pp pe un sold mic, un an


def test_B_nu_e_niciodata_negativ_in_model(pipeline, cfg):
    pf = pipeline["pf"]
    b = castig_plecare(loan_of(pipeline, "C0004", "nevoi_personale"), TODAY, pf.market, cfg)
    assert b["B_brut"] <= b["B"] + 1e-6 or b["B"] == 0        # B = max(0, brut)
    assert b["B"] >= 0


def test_legaturi_c0013_mai_mari_decat_c0014(pipeline, cfg):
    pf = pipeline["pf"]
    l13 = legaturi(client_of(pipeline, "C0013"), pf.tx_by_client["C0013"], True, TODAY, cfg)
    l14 = legaturi(client_of(pipeline, "C0014"), pf.tx_by_client["C0014"], True, TODAY, cfg)
    assert 0 <= l14["scor"] < cfg.retention.legaturi.min_pentru_oferta <= l13["scor"] <= 1
    assert set(l13["componente"]) == {"produse", "vechime", "nivel", "activitate"}
    assert l13["componente"]["activitate"] == 1.0 and l14["componente"]["activitate"] == 0.0
    assert l13["componente"]["nivel"] == 0.5 and l14["componente"]["nivel"] == 0.0
    # cont_salariu nu mai contează ca produs activ când salariul e la altă bancă
    assert "cont_salariu" not in l14["produse_active"]


def test_valoare_client(pipeline, cfg):
    pf = pipeline["pf"]
    v = valoare_client(loan_of(pipeline, "C0001", "ipotecar"), client_of(pipeline, "C0001"), TODAY, pf.market, cfg)
    assert v["V"] > v["venit_marja"] > 0 and v["produse"] > 0
    assert v["ani_ramasi"] == pytest.approx(22, abs=0.2)


def test_semnale_active(cfg):
    semnale = [{"id": "salariu_mutat", "scor": 1.0}, {"id": "expirare_dobanda_fixa", "scor": 0.5},
               {"id": "gap_piata_bani", "scor": 1.0}]
    n, lista = semnale_active(semnale, {"interogari_bc": 3}, cfg)
    assert n == 2 and lista == ["salariu_mutat", "interogari_bc"]
    n2, _ = semnale_active(semnale, {"interogari_bc": 0}, cfg)
    assert n2 == 1


def test_p_creste_cu_B_si_scade_cu_legaturile(cfg):
    p0 = prob_plecare(0, 0, 0.0, cfg)
    p1 = prob_plecare(15_000, 0, 0.0, cfg)
    p2 = prob_plecare(45_000, 2, 0.0, cfg)
    assert 0 < p0 < p1 < p2 < 1
    assert prob_plecare(15_000, 1, 1.0, cfg) < prob_plecare(15_000, 1, 0.0, cfg)
    assert prob_plecare(15_000, 1, 0.0, cfg, efect_scor=-0.6) < prob_plecare(15_000, 1, 0.0, cfg)
    # B_norm e plafonat: peste plafon p nu mai crește
    assert prob_plecare(10_000_000, 0, 0.0, cfg) == pytest.approx(prob_plecare(30_000, 0, 0.0, cfg))
