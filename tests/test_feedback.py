"""Bucla de feedback (M7): versionare, consilier + rezultat la 90 de zile, raportul de feedback, rutele API."""
from __future__ import annotations

import json
import shutil
from datetime import datetime
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from retailagent.api import create_app
from retailagent.approve import ApprovalError, decide, inregistreaza_rezultat, persist
from retailagent.config_loader import load_config
from retailagent.feedback import raport_feedback
from retailagent.pipeline import run_full
from retailagent.versiune import versiune_completa, versiune_config

ROOT = Path(__file__).resolve().parents[1]
NOW = datetime(2026, 10, 28, 15, 0, 0)


@pytest.fixture(scope="module")
def full(pipeline, tmp_path_factory):
    return run_full(pipeline["dir"], tmp_path_factory.mktemp("fb_out"), ROOT / "config", rescan=True)


def test_versiunea_se_schimba_cu_yaml(tmp_path, cfg):
    v1 = versiune_config(ROOT / "config")
    d = tmp_path / "config"
    shutil.copytree(ROOT / "config", d)
    assert versiune_config(d)["hash"] == v1["hash"]
    (d / "retention.yaml").write_text((d / "retention.yaml").read_text(encoding="utf-8") + "\n# modificat\n", encoding="utf-8")
    v2 = versiune_config(d)
    assert v2["hash"] != v1["hash"] and v2["fisiere"]["retention.yaml"] != v1["fisiere"]["retention.yaml"]
    assert v2["fisiere"]["priority.yaml"] == v1["fisiere"]["priority.yaml"]
    vc = versiune_completa(cfg)
    assert vc["scurt"].startswith("cfg:") and vc["model"]["model"] in ("sigmoid", "antrenat") and "prompturi" in vc


def test_versiunea_si_consilierul_sunt_pe_recomandari_si_audit(full):
    assert all(r["versiune"] and r["consilier"] for r in full.recs)
    assert all(a.get("versiune") for a in full.audit)
    ids = {c.id for c in full.cfg.echipa.consilieri}
    assert {r["consilier"] for r in full.recs} <= ids and len({r["consilier"] for r in full.recs}) > 1
    # alocarea e deterministă pe client
    assert all(full.cfg.echipa.pentru(r["client_id"]) == r["consilier"] for r in full.recs)


def test_decizie_cu_consilier_si_rezultat(full, tmp_path):
    cfg = full.cfg
    r = next(r for r in full.recs if r["recomandare"] == "oferta_minima" and r["interventie"] == "fix_3_ani")
    o = next(o for o in full.offers if o["case_id"] == r["case_id"])
    d = decide(r, o, "aproba", None, None, cfg, NOW, full.pf and ROOT / "data")
    assert d["consilier"] == cfg.echipa.pentru(r["client_id"]) and d["rezultat"] is None and d["versiune"] == r["versiune"]
    d2 = decide(r, o, "modifica", "fix_1_an", "client vrea 1 an", cfg, NOW, ROOT / "data", consilier=cfg.echipa.consilieri[1].id)
    assert d2["consilier"] == cfg.echipa.consilieri[1].id
    with pytest.raises(ApprovalError, match="echipa"):
        decide(r, o, "aproba", None, None, cfg, NOW, ROOT / "data", consilier="nimeni")
    with pytest.raises(ApprovalError, match="nicio decizie"):
        inregistreaza_rezultat(r["case_id"], "ramas", NOW, tmp_path)
    persist(d2, tmp_path)
    with pytest.raises(ApprovalError, match="rezultatul"):
        inregistreaza_rezultat(r["case_id"], "poate", NOW, tmp_path)
    rez = inregistreaza_rezultat(r["case_id"], "ramas", NOW, tmp_path)
    assert rez["rezultat"] == "ramas" and rez["rezultat_la"] and rez["interventie_finala"] == "fix_1_an"
    audit = [json.loads(l) for l in (tmp_path / "audit.jsonl").read_text(encoding="utf-8").splitlines()]
    assert audit[-1]["tip"] == "rezultat" and audit[-1]["valoare"] == "ramas" and audit[-1]["consilier"] == d2["consilier"]


def test_raportul_de_feedback(full):
    cfg = full.cfg
    recs = [r for r in full.recs if r["interventie"] in ("fix_3_ani", "pachet_salariu", "nu_interveni")][:8]
    approvals = []
    for i, r in enumerate(recs):
        o = next(o for o in full.offers if o["case_id"] == r["case_id"])
        if r["interventie"] == "fix_3_ani":
            d = decide(r, o, "modifica", "fix_1_an", "clientul preferă flexibilitate pe termen scurt", cfg, NOW, ROOT / "data")
        else:
            d = decide(r, o, "aproba", None, None, cfg, NOW, ROOT / "data")
        d["rezultat"] = "ramas" if i % 3 else "plecat"
        approvals.append(d)
    f = raport_feedback(approvals, full.recs, full.offers)
    assert f["decizii"] == len(recs) and f["override"] == sum(1 for r in recs if r["interventie"] == "fix_3_ani")
    assert f["pe_interventie"]["fix_3_ani"]["rata_override"] == 1.0
    assert f["inlocuiri"][0]["agent"] == "fix_3_ani" and f["inlocuiri"][0]["final"] == "fix_1_an"
    assert "flexibilitate" in dict(f["cuvinte_cheie"])
    assert f["rezultate_90_zile"]["n"] == len(recs) and "fix_1_an" in f["rezultate_90_zile"]["pe_interventie"]
    assert any(p["tip"] == "override_frecvent" and p["interventie"] == "fix_3_ani" for p in f["propuneri"])
    assert any(p["tip"] == "date" for p in f["propuneri"])
    assert set(f["pe_consilier"]) <= {c.id for c in cfg.echipa.consilieri}


def test_rutele_api_de_feedback(pipeline, tmp_path):
    with TestClient(create_app(pipeline["dir"], tmp_path / "out", ROOT / "config")) as c:
        tok = c.post("/api/login", json={"utilizator": "admin", "parola": "admin"}).json()["token"]
        c.headers.update({"Authorization": f"Bearer {tok}"})           # rutele cer sesiune; adminul vede tot
        ctx = c.get("/api/metrici/context").json()
        assert ctx["versiune"]["scurt"].startswith("cfg:") and "buget_portofoliu" in ctx
        echipa = c.get("/api/echipa").json()["consilieri"]
        assert len(echipa) >= 2
        caz = next(x for x in c.get("/api/cazuri?compact=false").json() if x["rec"]["recomandare"] == "oferta_minima")
        cid = caz["case"]["case_id"]
        assert caz["consilier"] in {e["id"] for e in echipa}
        assert c.post(f"/api/cazuri/{cid}/rezultat", json={"rezultat": "ramas"}).status_code == 400          # fără decizie
        r = c.post(f"/api/cazuri/{cid}/decizie", json={"decizie": "aproba", "consilier": echipa[1]["id"]}).json()
        assert r["consilier"] == echipa[1]["id"] and r["versiune"]
        assert c.post(f"/api/cazuri/{cid}/decizie", json={"decizie": "aproba", "consilier": "x"}).status_code == 400
        rez = c.post(f"/api/cazuri/{cid}/rezultat", json={"rezultat": "plecat"}).json()
        assert rez["rezultat"] == "plecat"
        ist = c.get(f"/api/cazuri/{cid}/decizii").json()
        assert len(ist) == 1 and ist[0]["rezultat"] == "plecat"
        fb = c.get("/api/feedback").json()
        assert fb["decizii"] == 1 and fb["rezultate_90_zile"]["n"] == 1
        assert c.get(f"/api/coada?consilier={echipa[1]['id']}&limit=5").json()["total"] > 0
        assert all(x["rec"]["recomandare"] == "blocat" for x in c.get("/api/coada?recomandare=blocat&limit=5").json()["items"])
