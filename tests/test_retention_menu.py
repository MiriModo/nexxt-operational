"""Meniul de intervenții, constrângerile și optimizarea (M3-T2), pe portofoliul generat."""
from __future__ import annotations

import pytest

from retailagent.checks import load_mocks, run_all_checks
from retailagent.retention_menu import evalueaza_caz


@pytest.fixture(scope="session")
def evaluari(pipeline, cfg):
    pf, res = pipeline["pf"], pipeline["res"]
    checks = {r["case_id"]: r for r in run_all_checks(pf, load_mocks(pipeline["dir"]), cfg, res)}
    return {c["case_id"]: evalueaza_caz(pf, cfg, c, res.inputs[c["case_id"]], checks[c["case_id"]]) for c in res.cases}


def scen(pipeline, nr):
    return pipeline["pf"].clients[nr - 1]["client_id"]


def of_client(evaluari, cid, produs=None):
    return [e for e in evaluari.values() if e["client_id"] == cid and (produs is None or e["produs"] == produs)]


def by_id(e):
    return {i["id"]: i for i in e["interventii"]}


def test_structura_evaluarii(evaluari, cfg):
    ids = {i.id for i in cfg.retention.interventii}
    for e in evaluari.values():
        assert set(by_id(e)) == ids
        for i in e["interventii"]:
            assert set(i) >= {"id", "fezabil", "motiv_infezabil", "cost", "B_dupa", "p_dupa", "respecta_tinta", "merita"}
            assert i["cost"] >= 0 and 0 <= i["p_dupa"] <= 1
            assert i["fezabil"] or i["motiv_infezabil"]
        assert 0 <= e["p_inainte"] <= 1 and e["V"] >= 0 and e["B"]["B"] >= 0
        assert e["aleasa"] is None or e["aleasa"] in ids


def test_pensionarul_nu_primeste_prelungire_de_maturitate(evaluari, pipeline):
    e = of_client(evaluari, scen(pipeline, 27), "imobiliar")[0]            # 86 de ani la scadență
    i = by_id(e)
    assert not i["ajustare_maturitate"]["fezabil"] and "vârst" in i["ajustare_maturitate"]["motiv_infezabil"]
    assert i["pauza_rata"]["fezabil"]
    assert e["aleasa"] == "pauza_rata"


def test_clientul_standard_nu_primeste_reducere_peste_buget(evaluari, pipeline, cfg):
    e = of_client(evaluari, scen(pipeline, 1))[0]                           # gold → buget 0.4
    i = by_id(e)
    assert i["reducere_marja_0_2"]["fezabil"] and i["reducere_marja_0_4"]["fezabil"]
    assert not i["reducere_marja_0_6"]["fezabil"] and "buget" in i["reducere_marja_0_6"]["motiv_infezabil"]
    e2 = next(x for x in evaluari.values() if x["nivel_relatie"] == "standard" and x["risc_credit"] < 0.7
              and x["produs"] in ("ipotecar", "imobiliar") and not x["blocat"])
    assert not by_id(e2)["reducere_marja_0_4"]["fezabil"]


def test_riscul_blocheaza_retentia(evaluari, pipeline):
    e = of_client(evaluari, scen(pipeline, 2))[0]                           # capcana a: expirare + întârziere
    i = by_id(e)
    for iid in ("reducere_marja_0_2", "fix_3_ani", "informare", "scutire_comision"):
        assert not i[iid]["fezabil"] and "risc" in i[iid]["motiv_infezabil"]
    assert e["aleasa"] in ("ajustare_maturitate", "pauza_rata")


def test_blocajul_nu_da_nicio_interventie(evaluari, pipeline):
    e = of_client(evaluari, scen(pipeline, 17))[0]
    assert e["blocat"] and e["aleasa"] is None and "blocat" in e["motiv_alegere"]


def test_legaturile_decid_oferta(evaluari, pipeline):
    e13 = of_client(evaluari, scen(pipeline, 13), "ipotecar")[0]
    e14 = of_client(evaluari, scen(pipeline, 14), "imobiliar")[0]
    assert e13["legaturi"]["suficiente_pentru_oferta"] and not e14["legaturi"]["suficiente_pentru_oferta"]
    i14 = by_id(e14)
    assert not i14["reducere_marja_0_2"]["fezabil"] and "legături" in i14["reducere_marja_0_2"]["motiv_infezabil"]
    assert not i14["pachet_salariu"]["fezabil"] and "nicio legătură" in i14["pachet_salariu"]["motiv_infezabil"]
    assert i14["informare"]["fezabil"] and e14["aleasa"] == "informare"
    assert by_id(e13)["pachet_salariu"]["fezabil"]
    assert e13["aleasa"] == "pachet_salariu"                                 # legături + salariul adus înapoi


def test_optimizarea_alege_costul_minim_care_atinge_tinta(evaluari, cfg):
    for e in evaluari.values():
        if e["blocat"] or e["risc_credit"] >= cfg.priority.risc_credit.blocheaza_retentia_daca or e["aleasa"] is None:
            continue
        a = by_id(e)[e["aleasa"]]
        if a["id"] in ("nu_interveni", "informare") and not a["respecta_tinta"]:
            continue                                                         # „nu există → nu interveni / informare"
        assert a["fezabil"] and a["respecta_tinta"] and a["merita"]
        mai_ieftine = [i for i in e["interventii"] if i["fezabil"] and i["respecta_tinta"] and i["merita"] and i["cost"] < a["cost"]]
        assert mai_ieftine == [], (e["case_id"], [i["id"] for i in mai_ieftine])


def test_costurile_vin_din_grafice(evaluari, pipeline):
    e = of_client(evaluari, scen(pipeline, 1))[0]                           # 400k, 22 ani
    i = by_id(e)
    assert i["reducere_marja_0_2"]["cost"] < i["reducere_marja_0_4"]["cost"]
    assert 5_000 < i["reducere_marja_0_2"]["cost"] < 15_000               # ≈ 0,2 pp pe sold descrescător ≈ 9k
    assert i["fix_1_an"]["cost"] < i["fix_3_ani"]["cost"] < i["fix_5_ani"]["cost"]
    assert i["reducere_marja_0_2"]["B_dupa"] == pytest.approx(e["B"]["B"] - i["reducere_marja_0_2"]["castig_client"], abs=1)
    assert i["reducere_marja_0_2"]["castig_client"] < i["reducere_marja_0_2"]["cost"]   # câștigul e pe 3 ani, costul pe 22
    assert i["fix_3_ani"]["B_dupa"] < 2_000                                           # fixa de 3 ani închide gap-ul în orizont
    assert i["pachet_salariu"]["motiv_infezabil"]                            # salariul e deja la noi
