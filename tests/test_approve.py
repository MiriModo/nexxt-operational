"""Aprobarea consilierului (M4-T2): aprobă / modifică / respinge cu motiv, approvals.json, override în audit."""
from __future__ import annotations

import json
from datetime import datetime

import pytest

from retailagent.approve import ApprovalError, decide, main, persist
from retailagent.recommend import main as recommend_main

NOW = datetime(2026, 10, 28, 14, 30, 0)


@pytest.fixture(scope="module")
def outdir(pipeline, tmp_path_factory):
    out = tmp_path_factory.mktemp("out")
    recommend_main(["--data-dir", str(pipeline["dir"]), "--out-dir", str(out), "--top", "0"])
    return out


@pytest.fixture(scope="module")
def artefacte(outdir):
    recs = {r["case_id"]: r for r in json.loads((outdir / "recommendations.json").read_text(encoding="utf-8"))}
    offers = {o["case_id"]: o for o in json.loads((outdir / "offers.json").read_text(encoding="utf-8"))}
    return recs, offers


def caz_cu_oferta(artefacte):
    recs, offers = artefacte
    r = next(r for r in recs.values() if r["recomandare"] == "oferta_minima" and r["interventie"] == "fix_3_ani")
    return r, offers[r["case_id"]]


def test_aproba_fara_motiv(artefacte, cfg):
    r, o = caz_cu_oferta(artefacte)
    d = decide(r, o, "aproba", None, None, cfg, NOW)
    assert d["decizie"] == "aproba" and d["override"] is False and d["interventie_finala"] == "fix_3_ani"
    assert d["timestamp"] == "2026-10-28T14:30:00" and d["oferta"]["dobanda_noua"] == 4.90


def test_modifica_si_respinge_cer_motiv(artefacte, cfg):
    r, o = caz_cu_oferta(artefacte)
    with pytest.raises(ApprovalError, match="motiv"):
        decide(r, o, "modifica", "fix_1_an", None, cfg, NOW)
    with pytest.raises(ApprovalError, match="motiv"):
        decide(r, o, "respinge", None, "", cfg, NOW)
    with pytest.raises(ApprovalError):
        decide(r, o, "altceva", None, "x", cfg, NOW)


def test_modifica_cu_interventie_fezabila(artefacte, cfg):
    r, o = caz_cu_oferta(artefacte)
    d = decide(r, o, "modifica", "fix_1_an", "clientul vrea flexibilitate pe termen scurt", cfg, NOW)
    assert d["override"] is True and d["interventie_finala"] == "fix_1_an" and d["interventie_agent"] == "fix_3_ani"
    assert d["oferta"]["perioada"] == "1 ani" and d["grafic"]["nr_rate"] > 0
    assert d["motiv"] == "clientul vrea flexibilitate pe termen scurt"


def test_modifica_refuza_interventie_inexistenta_sau_infezabila(artefacte, cfg):
    r, o = caz_cu_oferta(artefacte)
    with pytest.raises(ApprovalError, match="nu există"):
        decide(r, o, "modifica", "reducere_marja_9_9", "x", cfg, NOW)
    with pytest.raises(ApprovalError, match="buget"):
        decide(r, o, "modifica", "reducere_marja_0_6", "x", cfg, NOW)      # gold: buget 0.4 pp


def test_respinge(artefacte, cfg):
    r, o = caz_cu_oferta(artefacte)
    d = decide(r, o, "respinge", None, "clientul a refuzat telefonic", cfg, NOW)
    assert d["override"] is True and d["interventie_finala"] is None and d["oferta"] is None


def test_persist_scrie_approvals_si_audit(artefacte, cfg, tmp_path):
    r, o = caz_cu_oferta(artefacte)
    d = decide(r, o, "modifica", "fix_1_an", "motiv de test", cfg, NOW)
    persist(d, tmp_path)
    persist(decide(r, o, "aproba", None, None, cfg, NOW), tmp_path)
    rows = json.loads((tmp_path / "approvals.json").read_text(encoding="utf-8"))
    assert len(rows) == 2 and rows[0]["decizie"] == "modifica" and rows[1]["decizie"] == "aproba"
    audit = [json.loads(l) for l in (tmp_path / "audit.jsonl").read_text(encoding="utf-8").splitlines()]
    assert audit[0]["tip"] == "override" and audit[0]["valoare"] == "fix_1_an" and audit[0]["motiv"] == "motiv de test"
    assert audit[1]["tip"] == "aprobare"


def test_cli(artefacte, outdir, capsys):
    r, _ = caz_cu_oferta(artefacte)
    main([r["case_id"], "--out-dir", str(outdir)])
    out = capsys.readouterr().out
    assert "APROBAT" in out and "Grafic" in out and r["case_id"] in out
    with pytest.raises(SystemExit):
        main([r["case_id"], "--out-dir", str(outdir), "--decizie", "respinge"])       # fără motiv
    rows = json.loads((outdir / "approvals.json").read_text(encoding="utf-8"))
    assert rows[-1]["case_id"] == r["case_id"] and rows[-1]["decizie"] == "aproba"
