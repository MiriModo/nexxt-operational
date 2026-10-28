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
        c.headers.update(autentificare(c, "admin", "admin"))       # testele vechi rulează ca administrator
        yield c


def autentificare(c, utilizator: str, parola: str) -> dict:
    r = c.post("/api/login", json={"utilizator": utilizator, "parola": parola})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['token']}"}


def test_context_si_metrici(client):
    ctx = client.get("/api/metrici/context").json()
    assert {"azi", "clienti", "p_tinta", "total_cazuri"} <= set(ctx) and ctx["clienti"] == 50
    m = client.get("/api/metrici").json()
    assert {"cifra_vedeta", "nu_interveni", "interogari_externe", "recomandari", "cerinte_dure", "distributie"} <= set(m)


def test_cazuri_si_caz(client, pipeline):
    cazuri = client.get("/api/cazuri").json()                       # lista compactă (coada)
    assert len(cazuri) == len(pipeline["cases"])
    c = cazuri[0]
    assert {"case", "client", "loan", "check", "offer", "rec"} <= set(c) and c["compact"]
    assert c["offer"]["interventii"] == [] and c["rec"]["grafic"] is None and c["check"]["rezultate"] == []
    one = client.get(f"/api/cazuri/{c['case']['case_id']}").json()   # detaliul complet
    assert one["case"] == c["case"] and one["offer"]["interventii"] and "model" in one["offer"] and "contributii" in one["offer"]
    assert client.get("/api/cazuri?compact=false").json()[0] == one
    assert len(client.get("/api/cazuri?limit=5").json()) == 5
    assert all(x["case"]["banda"] == "P1" for x in client.get("/api/cazuri?banda=P1").json())
    assert all("C0013" in x["case"]["client_id"] for x in client.get("/api/cazuri?q=c0013").json())
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


def test_coada_paginata_si_sumar(client, pipeline):
    n = len(pipeline["cases"])
    p = client.get("/api/coada?limit=10").json()
    assert p["total"] == n and len(p["items"]) == 10 and p["items"][0]["compact"] and sum(p["pe_banda"].values()) == n
    p2 = client.get("/api/coada?limit=10&offset=10").json()
    assert p2["items"][0]["case"]["case_id"] != p["items"][0]["case"]["case_id"]
    p1 = client.get("/api/coada?banda=P1&limit=500").json()
    assert p1["total"] == p1["pe_banda"]["P1"] and all(c["case"]["banda"] == "P1" for c in p1["items"])
    t = client.get("/api/coada?sort=termen&limit=50").json()["items"]
    assert [c["case"]["deadline"] for c in t] == sorted(c["case"]["deadline"] for c in t)
    assert client.get("/api/coada?q=C0013").json()["total"] >= 1
    s = client.get("/api/cazuri/sumar").json()
    assert s["total"] == n and s["deschise"] + s["decise"] == n and len(s["primele"]) == 5
    assert s["blocate"] > 0 and s["p1"] > 0
    # „ascunde decise” folosește approvals.json scris de deciziile din testul anterior
    assert client.get("/api/coada?ascunde_decise=true&limit=1").json()["total"] == s["deschise"]


def test_verifica_si_model(client, pipeline):
    cid = pipeline["cases"][0]["case_id"]
    v = client.post(f"/api/cazuri/{cid}/verifica").json()
    assert v["case_id"] == cid and v["trepte"] and all(t["stare"] in ("executata", "oprita", "neexecutata") for t in v["trepte"])
    assert sum(len(t["rezultate"]) for t in v["trepte"]) == len(v["plan"]) and "incertitudini" in v
    assert client.post("/api/cazuri/Q9999/verifica").status_code == 404
    m = client.get("/api/model").json()
    assert m["activ"]["model"] in ("sigmoid", "antrenat")


def test_config_admin(client, tmp_path):
    # fără sesiune → 401; consilier → 403: motorul de reguli e doar al administratorului
    assert client.get("/api/config", headers={"Authorization": ""}).status_code == 401
    cons = autentificare(client, "ana.pop", "1234")
    assert client.get("/api/config", headers=cons).status_code == 403
    assert client.post("/api/rescan", headers=cons).status_code == 403
    lista = client.get("/api/config").json()
    assert {x["nume"] for x in lista} >= {"priority", "retention", "constraints", "checks", "signals", "portofoliu", "echipa"}
    r = client.get("/api/config/retention").json()
    assert "p_tinta" in r["text"]
    assert client.get("/api/config/parola").status_code == 404
    # invalid: p_tinta în afara intervalului → 400 cu mesaj; fișierul nu se schimbă
    original = r["text"]
    rau = client.put("/api/config/retention", json={"text": original.replace("p_tinta: 0.20", "p_tinta: 1.5")})
    assert rau.status_code == 400 and "respins" in rau.json()["detail"]
    assert client.get("/api/config/retention").json()["text"] == original
    assert client.put("/api/config/retention", json={"text": "p_tinta: [unclosed"}).status_code == 400
    # valid: aceeași configurație rescrisă cu un comentariu → salvat, versiunea se schimbă
    ok = client.put("/api/config/retention", json={"text": original + "\n# editat din Admin\n"}).json()
    assert ok["salvat"] and ok["versiune"]
    assert client.get("/api/config/retention").json()["text"].endswith("# editat din Admin\n")
    client.put("/api/config/retention", json={"text": original})            # restaurare
    assert client.get("/api/config/retention").json()["text"] == original
    d = client.get("/api/config/retention/diff").json()
    assert "diff" in d


def test_rescan(client):
    r = client.post("/api/rescan").json()
    assert r["cazuri"] > 0


def test_sumar_briefing(client):
    s = client.get("/api/cazuri/sumar").json()
    assert {"p1_azi", "peste_plafon", "de_confirmat", "deschise", "primele"} <= set(s)
    assert s["p1_azi"] <= s["p1"] <= s["deschise"]
    # listele briefing-ului se deschid în coadă cu `doar`
    for doar in ("de_confirmat", "peste_plafon"):            # sumarul numără doar cazurile nedecise, coada pe toate
        p = client.get(f"/api/coada?doar={doar}&limit=500").json()
        assert p["total"] >= s[doar]
        if doar == "de_confirmat":
            assert all(c["rec"]["incertitudini"] for c in p["items"])
    azi = client.get("/api/metrici/context").json()["azi"]
    p = client.get("/api/coada?doar=termen_azi&limit=500").json()
    assert all(c["case"]["deadline"] <= azi for c in p["items"])


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
    veche = ui / "public" / "data" / "queue.json"           # copie rămasă de la o versiune veche: se curăță
    veche.parent.mkdir(parents=True)
    veche.write_text("[]")
    dest = sync_ui(data, tmp_path / "out", ui)
    assert dest and (dest / "demo.json").exists() and not (dest / "queue.json").exists()
    assert json.loads((dest / "demo.json").read_text(encoding="utf-8"))["clienti"] == 50


def test_conturi_si_roluri(client):
    u = client.get("/api/utilizatori", headers={"Authorization": ""}).json()          # public, fără parole
    assert [x["id"] for x in u][-1] == "admin" and all("parola" not in x for x in u) and len(u) == 5
    assert client.post("/api/login", json={"utilizator": "ana.pop", "parola": "nu"}).status_code == 401
    assert client.post("/api/login", json={"utilizator": "nimeni", "parola": "1234"}).status_code == 401
    assert client.get("/api/coada", headers={"Authorization": "Bearer fals"}).status_code == 401
    ana = autentificare(client, "ana.pop", "1234")
    assert client.get("/api/eu", headers=ana).json() == {"id": "ana.pop", "nume": "Ana Pop", "rol": "consilier"}
    # consilierul vede doar cazurile lui, administratorul pe toate
    toate = client.get("/api/coada?limit=500").json()
    ale_anei = client.get("/api/coada?limit=500", headers=ana).json()
    assert 0 < ale_anei["total"] < toate["total"] and all(c["consilier"] == "ana.pop" for c in ale_anei["items"])
    assert client.get("/api/cazuri/sumar", headers=ana).json()["total"] == ale_anei["total"]
    strain = next(c["case"]["case_id"] for c in toate["items"] if c["consilier"] != "ana.pop")
    assert client.get(f"/api/cazuri/{strain}", headers=ana).status_code == 403
    assert client.post(f"/api/cazuri/{strain}/verifica", headers=ana).status_code == 403
    assert client.get("/api/metrici", headers=ana).status_code == 403
    assert "parola" not in client.get("/api/echipa", headers=ana).json()["consilieri"][0]
    # decizia poartă consilierul autentificat, chiar dacă body-ul spune altceva
    al_ei = ale_anei["items"][0]["case"]["case_id"]
    r = client.post(f"/api/cazuri/{al_ei}/decizie", json={"decizie": "aproba", "consilier": "radu.stan"}, headers=ana).json()
    assert r["consilier"] == "ana.pop"
    assert all(d["consilier"] == "ana.pop" for d in client.get("/api/decizii", headers=ana).json())
    b = client.get("/api/eu/birou", headers=ana).json()
    assert b["utilizator"]["id"] == "ana.pop" and b["coada"]["total"] == ale_anei["total"] and b["activitate"]["decizii"] >= 1
    assert {"p1_azi", "peste_plafon", "de_confirmat", "distributie"} <= set(b["coada"]) and len(b["primele"]) <= 5
    assert client.get("/api/feedback", headers=ana).json()["decizii"] == b["activitate"]["decizii"]
    # logout invalidează tokenul
    client.post("/api/logout", headers=ana)
    assert client.get("/api/eu", headers=ana).status_code == 401


def test_propunere_llm_si_audit(client, monkeypatch):
    rows = client.get('/api/cazuri?compact=false').json()
    c = next(c for c in rows if c['rec']['recomandare'] == 'oferta_minima')
    cid = c['case']['case_id']
    from retailagent import llm
    monkeypatch.setattr('retailagent.api.genereaza', lambda _: {
        'interventie': c['rec']['interventie'], 'titlu': 'Propunere', 'motiv': 'Motiv',
        'indicii': ['Semnal'], 'mesaj_client': 'Mesaj', 'atentionari': [], 'model': 'test'})
    p = client.post(f'/api/cazuri/{cid}/propunere').json()
    assert p['case_id'] == cid
    assert client.post('/api/cazuri/Q9999/propunere').status_code == 404
    assert client.post(f'/api/cazuri/{cid}/decizie', json={
        'decizie': 'respinge', 'motiv': 'x', 'propunere_id': p['id']}).status_code == 400
    assert client.post(f'/api/cazuri/{cid}/decizie', json={
        'decizie': 'aproba', 'propunere_id': p['id']}).status_code == 200
    assert client.get('/api/decizii').json()[-1]['propunere_llm']['id'] == p['id']
    assert p['id'] in (client.out / 'audit.jsonl').read_text()
    monkeypatch.setattr('retailagent.api.genereaza', llm.genereaza)
    monkeypatch.setattr('retailagent.llm.configurare', lambda: {'RETAILAGENT_LLM_PROVIDER': 'bedrock'})
    assert client.post(f'/api/cazuri/{cid}/propunere').status_code == 503


def test_propunere_respecta_accesul(client, monkeypatch):
    ana = autentificare(client, "ana.pop", "1234")
    rows = client.get('/api/coada?limit=500').json()['items']
    foreign = next(c['case']['case_id'] for c in rows if c['consilier'] != 'ana.pop')
    own = next(c['case']['case_id'] for c in rows if c['consilier'] == 'ana.pop')
    calls = []
    def generate(c):
        calls.append(c['case']['case_id'])
        return {'interventie': None, 'titlu': 'Titlu', 'motiv': 'Motiv', 'indicii': [],
                'mesaj_client': 'Mesaj', 'atentionari': [], 'model': 'test'}
    monkeypatch.setattr('retailagent.api.genereaza', generate)
    assert client.post(f'/api/cazuri/{own}/propunere', headers={'Authorization': ''}).status_code == 401
    assert client.post(f'/api/cazuri/{foreign}/propunere', headers=ana).status_code == 403
    assert calls == []
    assert client.post(f'/api/cazuri/{own}/propunere', headers=ana).status_code == 200
    assert calls == [own]


def test_partner_benefit_validated_and_saved(client, monkeypatch):
    from datetime import date
    from functools import partial
    from retailagent.loyalty import recommend_benefits
    from retailagent.cheltuieli import luni_recente
    rows = client.get('/api/cazuri?compact=false').json()
    from copy import deepcopy
    c = deepcopy(next(c for c in rows if c['rec']['recomandare'] == 'oferta_minima'))
    # Construct a clean, eligible server-side fixture without mutating other tests.
    c['case']['scoruri']['risc_credit'] = 0
    c['case']['blocaje'] = []
    c['rec']['documente_lipsa'] = []
    c['rec']['incertitudini'] = []
    c['check']['verificare_picata'] = None
    state = client.app.state.stare
    monkeypatch.setitem(state.cazuri, c['case']['case_id'], c)
    months = sorted(luni_recente(state.full.pf.today, 3))
    tx = [{'directie': 'out', 'data': months[n % 3] + '-01', 'suma': 100,
           'categorie': 'appliances_it'} for n in range(5)]
    monkeypatch.setitem(state.full.pf.tx_by_client, c['case']['client_id'], tx)
    monkeypatch.setattr('retailagent.api.recommend_benefits', partial(recommend_benefits, pricing_date=date(2026, 10, 29)))
    c = client.get(f"/api/cazuri/{c['case']['case_id']}").json()

    cid = c['case']['case_id']
    benefit = c['loyalty']['offers'][0]
    assert client.post(f'/api/cazuri/{cid}/decizie', json={
        'decizie': 'aproba', 'loyalty_offer_id': 'invented'}).status_code == 400
    assert client.post(f'/api/cazuri/{cid}/decizie', json={
        'decizie': 'respinge', 'motiv': 'No', 'loyalty_offer_id': benefit['id']}).status_code == 400
    r = client.post(f'/api/cazuri/{cid}/decizie', json={
        'decizie': 'aproba', 'loyalty_offer_id': benefit['id']})
    assert r.status_code == 200
    saved = client.get('/api/decizii').json()[-1]
    assert saved['loyalty_benefit'] == benefit
    assert benefit['id'] in (client.out / 'audit.jsonl').read_text()
    # A price change/expiry invalidates both the attached catalogue and generated copy.
    monkeypatch.setattr('retailagent.api.genereaza', lambda _: {
        'interventie': c['rec']['interventie'], 'titlu': 'Title', 'motiv': 'Reason',
        'indicii': [], 'mesaj_client': 'Message', 'atentionari': [], 'model': 'test'})
    proposal = client.post(f'/api/cazuri/{cid}/propunere').json()
    monkeypatch.setattr('retailagent.api.recommend_benefits', partial(recommend_benefits, pricing_date=date(2026, 11, 1)))
    assert client.post(f'/api/cazuri/{cid}/decizie', json={
        'decizie': 'aproba', 'loyalty_offer_id': benefit['id']}).status_code == 400
    assert client.post(f'/api/cazuri/{cid}/decizie', json={
        'decizie': 'aproba', 'propunere_id': proposal['id']}).status_code == 400
