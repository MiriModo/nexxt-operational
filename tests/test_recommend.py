"""Recomandarea finală (M4-T1): 6 stări, ofertă + grafic, documente lipsă, explicație, audit."""
from __future__ import annotations

import json

import pytest

from retailagent.checks import load_mocks, run_all_checks
from retailagent.recommend import STARI, build_recommendations, main
from retailagent.retention import build_offers

CHEI = {"case_id", "client_id", "loan_id", "produs", "recomandare", "interventie", "motiv", "oferta", "grafic",
        "documente_lipsa", "verificari", "explicatie", "creat_la"}


@pytest.fixture(scope="session")
def recs(pipeline, cfg):
    pf, res = pipeline["pf"], pipeline["res"]
    mocks = load_mocks(pipeline["dir"])
    checks = run_all_checks(pf, mocks, cfg, res)
    offers = build_offers(pf, cfg, res, checks)
    rows, audit = build_recommendations(pf, cfg, res, checks, offers, mocks)
    return {"rows": {r["case_id"]: r for r in rows}, "audit": audit, "checks": {c["case_id"]: c for c in checks}}


def scen(pipeline, nr):
    return pipeline["pf"].clients[nr - 1]["client_id"]


def top_case(pipeline, cid):
    return next(c for c in pipeline["cases"] if c["client_id"] == cid)


def test_schema_si_stari(recs, pipeline):
    rows = recs["rows"]
    assert set(rows) == {c["case_id"] for c in pipeline["cases"]}
    for r in rows.values():
        assert CHEI <= set(r), CHEI - set(r)
        assert r["recomandare"] in STARI
        assert r["explicatie"] and r["motiv"]
        assert r["creat_la"].endswith("T00:00:00")
    json.dumps(list(rows.values()), ensure_ascii=False)


def test_acuratetea_fata_de_etalon(recs, pipeline):
    gt = json.loads((pipeline["dir"] / "ground_truth.json").read_text(encoding="utf-8"))
    ok = tot = 0
    gresite = []
    for g in gt:
        if g["recomandare_asteptata"] is None:
            continue
        tot += 1
        got = recs["rows"][top_case(pipeline, g["client_id"])["case_id"]]["recomandare"]
        ok += got == g["recomandare_asteptata"]
        if got != g["recomandare_asteptata"]:
            gresite.append((g["client_id"], g["recomandare_asteptata"], got))
    assert ok / tot >= 0.9, gresite


def test_verificarile_picate_dau_respins(recs, pipeline):
    for nr, treapta in ((5, "garantie"), (46, "biroul_credit"), (47, "crc")):
        r = recs["rows"][top_case(pipeline, scen(pipeline, nr))["case_id"]]
        assert r["recomandare"] == "respins_escaladat"
        assert r["verificari"]["oprit_la"] == treapta and r["verificari"]["verificare_picata"]
        assert r["oferta"] is None


def test_fara_oferta_la_risc_sau_blocat(recs, pipeline, cfg):
    prag = cfg.priority.risc_credit.blocheaza_retentia_daca
    for c in pipeline["cases"]:
        r = recs["rows"][c["case_id"]]
        if c["blocaje"]:
            assert r["recomandare"] == "blocat" and r["oferta"] is None and r["interventie"] is None
        elif c["scoruri"]["risc_credit"] >= prag:
            assert r["recomandare"] in ("restructurare", "respins_escaladat")
            assert r["oferta"] is None or r["oferta"]["tip"] == "restructurare"


def test_oferta_are_grafic_si_cifre(recs, pipeline):
    r = recs["rows"][top_case(pipeline, scen(pipeline, 1))["case_id"]]          # fix 3 ani
    assert r["recomandare"] == "oferta_minima" and r["interventie"] == "fix_3_ani"
    o = r["oferta"]
    assert o["dobanda_noua"] == 4.90 and o["rata_noua"] > 0 and o["cost_banca"] > 0 and o["economie_client"] > 0
    assert o["perioada"] == "3 ani" and o["rata_noua"] < o["rata_veche"]
    # „rata veche” e ce plătește clientul azi, nu rata de după expirarea fixei (aceea apare separat)
    loan = next(l for l in pipeline["pf"].loans if l["loan_id"] == r["loan_id"])
    from retailagent.finance import luni_ramase, rata_anuitate, segmente_credit
    seg = segmente_credit(loan, pipeline["pf"].today, pipeline["pf"].market)
    azi = (loan["rata_lunara"] if seg[0][1] == loan["dobanda_curenta"]
           else rata_anuitate(loan["sold_ramas"], seg[0][1], luni_ramase(loan, pipeline["pf"].today)))
    assert o["rata_veche"] == pytest.approx(azi, abs=0.01)
    if len(seg) > 1:
        assert o["rata_dupa_fixa"] > 0 and o["fixa_expira"] == loan["dobanda_fixa_expira_la"]
    else:
        assert "rata_dupa_fixa" not in o
    assert o["economie_orizont_luni"] == 36
    g = r["grafic"]
    assert len(g["primele_luni"]) == 12 and g["nr_rate"] > 200 and g["dobanda_totala"] > 0
    assert g["primele_luni"][0]["luna"] == "2026-11"
    r13 = recs["rows"][next(c["case_id"] for c in pipeline["cases"] if c["client_id"] == scen(pipeline, 13) and c["produs"] == "ipotecar")]
    assert r13["recomandare"] == "oferta_produs" and r13["oferta"]["conditie"]


def test_documente_lipsa(recs, pipeline):
    r = recs["rows"][top_case(pipeline, scen(pipeline, 1))["case_id"]]
    lipsa = {d["tip"]: d for d in r["documente_lipsa"]}
    assert "extras_cf" in lipsa and "motiv" in lipsa["extras_cf"]                 # extrasul din dosar e mai vechi de 30 zile
    blocat = recs["rows"][top_case(pipeline, scen(pipeline, 17))["case_id"]]
    assert any(d["tip"] == "carte_identitate" for d in blocat["documente_lipsa"])
    nimic = recs["rows"][top_case(pipeline, scen(pipeline, 4))["case_id"]]
    assert nimic["documente_lipsa"] == []


def test_audit_log(recs, pipeline):
    audit = recs["audit"]
    tipuri = {a["tip"] for a in audit}
    assert {"semnal", "verificare", "decizie"} <= tipuri
    for a in audit:
        assert {"timestamp", "case_id", "client_id", "tip", "cheie", "valoare", "sursa"} <= set(a)
    q1 = [a for a in audit if a["case_id"] == pipeline["cases"][0]["case_id"]]
    assert any(a["tip"] == "decizie" and a["cheie"] == "recomandare" for a in q1)


def test_cli_scrie_fisierele(pipeline, tmp_path):
    out = tmp_path / "out"
    main(["--data-dir", str(pipeline["dir"]), "--out-dir", str(out), "--top", "1"])
    rows = json.loads((out / "recommendations.json").read_text(encoding="utf-8"))
    assert len(rows) == len(pipeline["cases"])
    lines = (out / "audit.jsonl").read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) > len(rows) and all(json.loads(l)["case_id"] for l in lines)
