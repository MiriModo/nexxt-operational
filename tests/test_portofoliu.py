"""Portofoliul realist la scară: profil, etalon neschimbat, distribuții, mock-uri, comportament, etichetă, determinism."""
from __future__ import annotations

import json
import shutil
from collections import Counter
from pathlib import Path

import pytest
import yaml

from retailagent.churn.labels import build_labels, rezumat
from retailagent.config_loader import load_config
from retailagent.evaluate import eval_detection
from retailagent.evaluate_final import cerinte_dure_final
from retailagent.generate import SCENARIOS, generate
from retailagent.pipeline import run_full
from retailagent.profil import PROFIL_PATH, load_profil

ROOT = Path(__file__).resolve().parents[1]
N = 1500
TODAY = "2026-10-28"


@pytest.fixture(scope="module")
def profil():
    return load_profil()


@pytest.fixture(scope="module")
def scale(tmp_path_factory):
    d = tmp_path_factory.mktemp("scale")
    g = generate(N, 42, TODAY, d)
    full = run_full(d, d / "out", ROOT / "config", rescan=True)
    gt = json.loads((d / "ground_truth.json").read_text(encoding="utf-8"))
    return {"dir": d, "g": g, "full": full, "gt": gt}


def _rewrite(path: Path, fn) -> None:
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    fn(data)
    path.write_text(yaml.safe_dump(data, allow_unicode=True), encoding="utf-8")


# ---------------------------------------------------------------- profil

def test_profilul_se_incarca(profil):
    assert abs(sum(profil.tipologii.values()) - 1) < 1e-6 and set(profil.credite.parametri) >= {"ipotecar", "nevoi_personale"}
    assert 0 < profil.semnale.per_client["salariu_mutat"].prob < 1 and profil.comportament.prag_baza_ron > 0
    assert any(c.cauza == "intarziere_noua" and c.efect == "venit_scadere" for c in profil.corelatii)


def test_profil_invalid_ridica_eroare(tmp_path):
    p = tmp_path / "portofoliu.yaml"
    shutil.copy(PROFIL_PATH, p)
    _rewrite(p, lambda y: y["semnale"]["per_client"]["kyc_vechi"].update(prob=1.5))
    with pytest.raises(ValueError, match="probabilitatea"):
        load_profil(p)
    shutil.copy(PROFIL_PATH, p)
    _rewrite(p, lambda y: y["tipologii"].update(SL=0.9))
    with pytest.raises(ValueError, match="însumează"):
        load_profil(p)
    shutil.copy(PROFIL_PATH, p)
    _rewrite(p, lambda y: y["corelatii"].append({"cauza": "fantoma", "efect": "kyc_vechi", "factor": 2}))
    with pytest.raises(ValueError, match="necunoscut"):
        load_profil(p)


# ---------------------------------------------------------------- etalonul rămâne identic

def test_etalonul_identic_cu_generarea_separata(scale, tmp_path):
    """Primii len(SCENARIOS) clienți din portofoliul mare sunt byte cu byte etalonul generat singur."""
    d50 = tmp_path / "etalon"
    generate(len(SCENARIOS), 42, TODAY, d50)
    for name, key in (("clients.json", "client_id"), ("loans.json", "loan_id"), ("payment_history.json", "loan_id"),
                      ("requests.json", "request_id"), ("transactions.json", "client_id")):
        a = json.loads((d50 / name).read_text(encoding="utf-8"))
        b = json.loads((scale["dir"] / name).read_text(encoding="utf-8"))
        ids = {x[key] for x in a}
        assert a == [x for x in b if x[key] in ids], name
    gt = scale["gt"]
    assert sum(1 for g in gt if g["etalon"]) == len(SCENARIOS) and all(not g["etalon"] for g in gt[len(SCENARIOS):])
    assert all(g["recomandare_asteptata"] is None and g["banda_asteptata"] is None for g in gt if not g["etalon"])


# ---------------------------------------------------------------- distribuții și detecție

def test_f1_detectie_pe_toti(scale):
    d = eval_detection(scale["full"].detections, scale["gt"], scale["full"].cfg)
    assert d["global"]["f1"] == 1.0 and d["global"]["tp"] > 300


def test_frecventa_semnalelor_in_toleranta(scale, profil):
    gt = [g for g in scale["gt"] if not g["etalon"]]
    n = len(gt)
    cnt = Counter(s for g in gt for s in g["semnale_plantate"])
    clients = {c["client_id"]: c for c in scale["full"].pf.clients}
    n_sal = sum(1 for g in gt if clients[g["client_id"]]["tipologie_declarata"] in ("salariat", "tanar_fara_istoric")
                and clients[g["client_id"]]["angajator_id"])
    # semnale per client cu probabilitate de bază (fără corelații puternice): ±40% sau ±10 apariții
    for sid, key in (("ci_expirata", "ci_expirata"), ("kyc_vechi", "kyc_vechi"), ("consimtamant_lipsa", "consimtamant_lipsa")):
        asteptat = profil.semnale.per_client[key].prob * n
        assert abs(cnt[sid] - asteptat) <= max(10, 0.4 * asteptat), (sid, cnt[sid], asteptat)
    assert cnt["salariu_mutat"] >= 10 and cnt["salariu_mutat"] <= profil.semnale.per_client["salariu_mutat"].prob * n_sal * 1.6
    assert cnt["expirare_dobanda_fixa"] >= 20 and cnt["intarziere_noua"] >= 30
    # varietate: există combinații care nu sunt în cele 50 de scenarii
    combos = {tuple(g["semnale_plantate"]) for g in gt}
    assert len(combos) > 60


def test_variabilitate_fata_de_blocuri(scale):
    loans = [l for l in scale["full"].pf.loans if l["client_id"] > "C0050" and l["produs"] == "ipotecar"]
    solduri = {l["sold_ramas"] for l in loans}
    assert len(solduri) > len(loans) * 0.9                                   # practic toate diferite
    vech = {c["client_din"] for c in scale["full"].pf.clients if c["client_id"] > "C0050"}
    assert len(vech) > 100                                                    # vechimea are granularitate de 0,1 ani


# ---------------------------------------------------------------- mock-uri consistente pe clienții statistici

def test_mockuri_consistente_la_scara(scale):
    d = scale["dir"]
    bc = {b["client_id"]: b for b in json.loads((d / "externe" / "biroul_credit.json").read_text(encoding="utf-8"))}
    crc = json.loads((d / "externe" / "crc.json").read_text(encoding="utf-8"))
    gar = {g["loan_id"]: g for g in json.loads((d / "externe" / "garantii.json").read_text(encoding="utf-8"))}
    tx = json.loads((d / "transactions.json").read_text(encoding="utf-8"))
    rate = {}
    for t in tx:
        if t["tip_etichetat"] == "rata_alt_creditor" and t["client_id"] > "C0050":
            rate.setdefault(t["client_id"], t["suma"])
    assert len(rate) > 50
    for cid, suma in rate.items():
        assert any(c["stare"] == "activ" and c["rata_lunara"] == suma for c in bc[cid]["credite"]), cid
    for row in crc:
        assert all(e["sold"] >= row["prag_raportare_ron"] for e in row["expuneri"])
    for l in scale["full"].pf.loans:
        if l["garantie"] and l["sold_ramas"] > l["garantie"]["valoare_evaluare"]:
            assert gar[l["loan_id"]]["reevaluare"]["valoare"] <= l["garantie"]["valoare_evaluare"]
    picate = Counter(c["oprit_la"] for c in scale["full"].checks if c["oprit_la"] not in (None, "intern"))
    assert picate["biroul_credit"] >= 3 and picate["crc"] >= 2 and picate["garantie"] >= 1       # eșecuri plantate din profil
    assert sum(picate.values()) >= 6


# ---------------------------------------------------------------- comportament cu structură + etichetă

def test_comportamentul_are_structura(scale):
    gt = {g["client_id"]: g for g in scale["gt"]}
    clients = scale["full"].pf.clients
    prag = lambda cs: sum(gt[c["client_id"]]["comportament"]["prag_castig_plecare_ron"] for c in cs) / len(cs)
    by_tier = {t: [c for c in clients if c["nivel_relatie"] == t] for t in ("standard", "gold", "platinum")}
    assert prag(by_tier["standard"]) < prag(by_tier["gold"]) < prag(by_tier["platinum"])
    vechi = [c for c in clients if c["client_din"] < "2018-01-01"]
    noi = [c for c in clients if c["client_din"] > "2024-01-01"]
    assert prag(vechi) > prag(noi)
    # zgomot: clienți cu același nivel și vechime similară au praguri diferite
    sub = [gt[c["client_id"]]["comportament"]["prag_castig_plecare_ron"] for c in by_tier["standard"] if "2021-01-01" < c["client_din"] < "2021-12-31"]
    assert len(set(sub)) > 5


def test_eticheta_de_churn(scale):
    rows = build_labels(scale["full"], scale["gt"])
    r = rezumat(rows)
    assert r["candidati"] > 200 and 0.05 <= r["rata_plecare_fara_interventie"] <= 0.45
    assert r["rata_plecare_cu_agent"] < r["rata_plecare_fara_interventie"]
    assert r["pe_legaturi"]["mici (<0.3)"] > r["pe_legaturi"]["mari (>=0.6)"]
    # eticheta nu e o funcție deterministă a observabilelor: la B similar apar ambele etichete
    mid = [x for x in rows if 8_000 <= x["B"] <= 20_000]
    assert {x["a_plecat_fara_interventie"] for x in mid} == {True, False}
    assert all({"B", "legaturi", "nivel", "vechime_ani", "interventie_agent", "a_plecat_cu_agent"} <= set(x) for x in rows)


# ---------------------------------------------------------------- determinism + invarianți la scară

def test_determinism_la_scara(scale, tmp_path):
    d2 = tmp_path / "again"
    generate(N, 42, TODAY, d2)
    for name in ("clients.json", "loans.json", "transactions.json", "ground_truth.json", "externe/anaf.json"):
        assert (d2 / name).read_bytes() == (scale["dir"] / name).read_bytes(), name
    full2 = run_full(d2, d2 / "out", ROOT / "config", rescan=True)
    assert full2.res.cases == scale["full"].res.cases
    assert [r["recomandare"] for r in full2.recs] == [r["recomandare"] for r in scale["full"].recs]


def test_invarianti_la_scara(scale):
    h = cerinte_dure_final(scale["full"])
    assert all(v["incalcari"] == 0 for v in h.values()), {k: v["incalcari"] for k, v in h.items()}
