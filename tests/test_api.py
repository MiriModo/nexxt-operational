"""API-ul interfeței (FastAPI) pe contractul din ui/src/types/api.ts + sincronizarea snapshot-ului în ui/public/data."""
from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from retailagent.api import create_app
from retailagent.demo import build_data, sync_ui
from retailagent.pipeline import run_full

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="module")
def client(pipeline, tmp_path_factory):
    out = tmp_path_factory.mktemp("api_out")
    app = create_app(pipeline["dir"], out, ROOT / "config")
    with TestClient(app) as c:
        c.out = out
        yield c


def test_context_si_metrici(client):
    ctx = client.get("/api/metrici/context").json()
    assert {"azi", "clienti", "p_tinta", "total_cazuri"} <= set(ctx) and ctx["clienti"] == 50
    m = client.get("/api/metrici").json()
    assert {"cifra_vedeta", "nu_interveni", "interogari_externe", "recomandari", "cerinte_dure", "distributie"} <= set(m)


def test_cazuri_si_caz(client, pipeline):
    cazuri = client.get("/api/cazuri").json()
    assert len(cazuri) == len(pipeline["cases"])
    c = cazuri[0]
    assert {"case", "client", "loan", "check", "offer", "rec"} <= set(c)
    assert "model" in c["offer"] and "contributii" in c["offer"]
    one = client.get(f"/api/cazuri/{c['case']['case_id']}").json()
    assert one == c
    assert client.get("/api/cazuri/Q9999").status_code == 404


def test_decizie_aproba_si_override(client):
    cazuri = client.get("/api/cazuri").json()
    cu_oferta = next(c for c in cazuri if c["rec"]["recomandare"] == "oferta_minima" and c["rec"]["interventie"] == "fix_3_ani")
    cid = cu_oferta["case"]["case_id"]
    r = client.post(f"/api/cazuri/{cid}/decizie", json={"decizie": "aproba"})
    assert r.status_code == 200 and r.json()["sursa"] == "api" and r.json()["override"] is False
    r = client.post(f"/api/cazuri/{cid}/decizie", json={"decizie": "respinge"})
    assert r.status_code == 400 and "motiv" in r.json()["detail"]
    r = client.post(f"/api/cazuri/{cid}/decizie", json={"decizie": "modifica", "interventie": "reducere_marja_0_6", "motiv": "x"})
    assert r.status_code == 400 and "buget" in r.json()["detail"]
    r = client.post(f"/api/cazuri/{cid}/decizie", json={"decizie": "modifica", "interventie": "fix_1_an", "motiv": "clientul vrea 1 an"})
    assert r.status_code == 200 and r.json()["interventie"] == "fix_1_an" and r.json()["oferta"]["perioada"] == "1 ani"
    assert client.post("/api/cazuri/Q9999/decizie", json={"decizie": "aproba"}).status_code == 404
    dec = client.get("/api/decizii").json()
    assert len(dec) == 2 and dec[-1]["decizie"] == "modifica"
    audit = (client.out / "audit.jsonl").read_text(encoding="utf-8").splitlines()
    assert any('"override"' in l for l in audit)


def test_rescan(client):
    r = client.post("/api/rescan").json()
    assert r["cazuri"] > 0


def test_sync_ui_scrie_snapshotul(pipeline, tmp_path):
    full = run_full(pipeline["dir"], tmp_path / "out", ROOT / "config", rescan=True)
    gt = json.loads((pipeline["dir"] / "ground_truth.json").read_text(encoding="utf-8"))
    data = build_data(full, gt, 10)
    assert data["total_cazuri"] == len(full.res.cases) and len(data["cazuri"]) == 10 and data["model_churn"]
    assert sync_ui(data, tmp_path / "out", tmp_path / "nu_e_ui") is None
    ui = tmp_path / "ui"
    ui.mkdir()
    (ui / "package.json").write_text("{}")
    (tmp_path / "out").mkdir(exist_ok=True)
    (tmp_path / "out" / "queue.json").write_text("[]")
    dest = sync_ui(data, tmp_path / "out", ui)
    assert dest and (dest / "demo.json").exists() and (dest / "queue.json").exists()
    assert json.loads((dest / "demo.json").read_text(encoding="utf-8"))["clienti"] == 50
