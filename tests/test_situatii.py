"""Situații neașteptate (roadmap pasul 6): scenariile etalon 51–60, tratate explicit — degradare controlată,
marcare incertitudine, escaladare la om; plus bugetul de retenție la nivel de portofoliu."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from retailagent.buget import aloca_buget
from retailagent.evaluate import eval_detection
from retailagent.evaluate_final import cerinte_dure_final, eval_situatii
from retailagent.generate import SCENARIOS, SITUATII, generate
from retailagent.intake import run_intake
from retailagent.pipeline import run_full
from retailagent.recommend import _critica

ROOT = Path(__file__).resolve().parents[1]
TODAY = "2026-10-28"


@pytest.fixture(scope="module")
def etalon(tmp_path_factory):
    d = tmp_path_factory.mktemp("etalon60")
    generate(len(SCENARIOS), 42, TODAY, d)
    full = run_full(d, d / "out", ROOT / "config", rescan=True)
    gt = json.loads((d / "ground_truth.json").read_text(encoding="utf-8"))
    top = {}
    for c in full.res.cases:
        top.setdefault(c["client_id"], c)
    recs = {r["case_id"]: r for r in full.recs}
    checks = {c["case_id"]: c for c in full.checks}
    return {"dir": d, "full": full, "gt": gt, "top": top, "recs": recs, "checks": checks}


def caz(etalon, nume):
    cid = f"C{SITUATII[nume] + 1:04d}"
    c = etalon["top"][cid]
    return cid, c, etalon["recs"][c["case_id"]], etalon["checks"][c["case_id"]]


def inc(rec):
    return {i["id"] for i in rec["incertitudini"]}


def test_etalonul_are_60_de_scenarii_si_detectia_ramane_perfecta(etalon):
    assert len(SCENARIOS) == 60 and len(SITUATII) == 10
    d = eval_detection(etalon["full"].detections, etalon["gt"], etalon["full"].cfg)["global"]
    assert d["f1"] == 1.0 and d["fp"] == 0 and d["fn"] == 0
    s = eval_situatii(etalon["full"], etalon["gt"])
    assert s["corecte"] == s["asteptate"] >= 6, s["gresite"]
    assert all(v["incalcari"] == 0 for v in cerinte_dure_final(etalon["full"]).values())


def test_51_credit_in_valuta(etalon):
    cid, c, r, ch = caz(etalon, "situatie_valuta")
    loan = next(l for l in etalon["full"].pf.loans if l["client_id"] == cid)
    assert loan["moneda"] == "EUR" and loan["sold_valuta"] == 120_000 and loan["sold_ramas"] == pytest.approx(120_000 * 4.97)
    assert any(s["id"] == "expunere_valutara" for s in c["semnale"]) and r["recomandare"] == "restructurare"
    assert ch["concluzii"]["dti_valuta"] > 0.20 and "valut" in next(x["dovada"] for x in ch["rezultate"] if x["id"] == "capacitate_plata_actuala")


def test_52_codebitor_cu_risc(etalon):
    cid, c, r, ch = caz(etalon, "situatie_codebitor")
    s = next(s for s in c["semnale"] if s["id"] == "codebitor_cu_risc")
    assert "C0018" in s["dovada"] and r["recomandare"] == "restructurare"
    assert "solidar" in next(x["dovada"] for x in ch["rezultate"] if x["id"] == "expuneri_interne")


def test_53_semnale_contradictorii(etalon):
    cid, c, r, _ = caz(etalon, "situatie_contradictorii")
    assert r["recomandare"] == "restructurare" and "semnale_contradictorii" in inc(r)
    assert c["scoruri"]["risc_credit"] >= 0.7 and any(s["id"] == "expirare_dobanda_fixa" and s["scor"] == 1.0 for s in c["semnale"])


def test_54_cerere_duplicata(etalon):
    cid, c, r, _ = caz(etalon, "situatie_cerere_duplicata")
    cazuri = [x for x in etalon["full"].res.cases if x["client_id"] == cid]
    assert len(cazuri) == 1 and "cerere_duplicata" in inc(r)
    intake = run_intake(etalon["full"].pf, etalon["full"].cfg)
    ale = [x for x in intake if x["client_id"] == cid]
    assert len(ale) == 1 and len(ale[0]["duplicate"]) == 1 and ale[0]["request_id"] > ale[0]["duplicate"][0]   # rămâne cea mai recentă
    assert r["oferta"] and r["oferta"]["conditii_de_confirmat"]


def test_55_fara_cont(etalon):
    cid, c, r, ch = caz(etalon, "situatie_fara_cont")
    sc = next(x for x in ch["rezultate"] if x["id"] == "sold_cont")
    assert sc["status"] == "avertizare" and sc["incertitudine"] == "fara_cont" and ch["oprit_la"] is None
    assert "fara_cont" in inc(r) and r["recomandare"] in ("oferta_minima", "nu_interveni")


def test_56_anaf_indisponibil(etalon):
    cid, c, r, ch = caz(etalon, "situatie_fara_anaf")
    va = next(x for x in ch["rezultate"] if x["id"] == "venit_anaf")
    assert va["status"] == "indisponibil" and ch["oprit_la"] is None                         # nu oprește fluxul
    assert ch["interogari_externe"]["executate"] < ch["interogari_externe"]["planificate"]   # o sursă n-a răspuns
    assert "anaf_indisponibil" in inc(r) and r["recomandare"] == "oferta_minima"
    assert any("ANAF" in t for t in r["oferta"]["conditii_de_confirmat"])                    # ofertă condiționată


def test_56b_anaf_indisponibil_e_critic_la_credit_nou(etalon):
    cfg = etalon["full"].cfg
    assert _critica("anaf_indisponibil", {"credit_nou"}, cfg) and not _critica("anaf_indisponibil", {"expirare_dobanda_fixa"}, cfg)
    assert not _critica("fara_cont", {"credit_nou"}, cfg)


def test_57_surse_contradictorii(etalon):
    cid, c, r, ch = caz(etalon, "situatie_surse_contradictorii")
    assert "surse_contradictorii" in inc(r)
    bc = next(x for x in ch["rezultate"] if x["id"] == "istoric_biroul_credit")
    assert bc["status"] == "avertizare" and "UniCredit" in bc["dovada"]
    assert ch["concluzii"]["rate_alti_creditori"] >= 910.0                                    # DTI prudent: ratele din BC


def test_58_59_decedat_si_pep(etalon):
    for nume in ("situatie_decedat", "situatie_pep"):
        cid, c, r, ch = caz(etalon, nume)
        assert r["recomandare"] == "blocat" and c["actiune_propusa"] == "task_flag_blocant" and r["oferta"] is None
        assert "aprobare specială" in r["motiv"]
        assert [x["id"] for x in ch["plan"]] == ["identitate_kyc"] and ch["interogari_externe"]["executate"] == 0


def test_60_refinantare_externa_in_curs(etalon):
    cid, c, r, ch = caz(etalon, "situatie_refinantare_externa")
    assert ch["concluzii"]["refinantare_externa_in_curs"] is True and "refinantare_externa_in_curs" in inc(r)
    offer = next(o for o in etalon["full"].offers if o["case_id"] == c["case_id"])
    assert "refinantare_externa_in_curs" in offer["semnale_active"]                         # intră în p
    assert r["recomandare"] == "oferta_minima" and r["oferta"]["conditii_de_confirmat"]


def test_bugetul_de_portofoliu(etalon):
    full = etalon["full"]
    b = full.buget
    assert b["oferte"] >= 5 and b["in_buget"] == b["oferte"] and b["amanate"] == 0           # plafonul implicit încape tot
    cfg = full.cfg.model_copy(deep=True)
    cfg.retention.buget_portofoliu.plafon_lunar_ron = 50_000
    recs = [json.loads(json.dumps(r)) for r in full.recs]
    b2 = aloca_buget(recs, full.offers, cfg)
    assert b2["amanate"] >= 1 and b2["cost_in_buget"] <= 50_000
    amanate = [r for r in recs if r.get("buget") and not r["buget"]["in_buget"]]
    assert amanate and all(r["oferta"]["amanata_buget"] and "plafon" in r["motiv"] for r in amanate)
    ranguri = [r["buget"]["rang"] for r in recs if r.get("buget")]
    assert sorted(ranguri) == list(range(1, len(ranguri) + 1))
