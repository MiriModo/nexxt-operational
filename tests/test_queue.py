"""Cazurile-capcană din §8, cerințele dure din §7 și criteriile de acceptare din §10."""
from __future__ import annotations

import json

from retailagent.evaluate import eval_detection, eval_queue
from retailagent.explain import explain_case
from retailagent.generate import TRAP_INDEX, generate
from retailagent.intake import run_intake
from retailagent.queue import build_queue

from .conftest import TODAY


def cid(trap: str) -> str:
    return f"C{TRAP_INDEX[trap] + 1:04d}"


def cases_of(pipeline, client_id):
    return [c for c in pipeline["cases"] if c["client_id"] == client_id]


# ---------------------------------------------------------------- cele 5 capcane

def test_capcana_a_expirare_plus_intarziere_merge_la_restructurare(pipeline):
    cs = cases_of(pipeline, cid("capcana_a"))
    assert cs
    for c in cs:
        assert any(s["id"] == "expirare_dobanda_fixa" and s["scor"] == 1.0 for s in c["semnale"])
        assert any(s["id"] == "intarziere_noua" for s in c["semnale"])
        assert c["actiune_propusa"] == "restructurare_preventiva"
        assert c["banda"] == "P1"


def test_capcana_b_plecare_mare_sold_mic_ramane_P3(pipeline):
    cs = cases_of(pipeline, cid("capcana_b"))
    assert cs
    for c in cs:
        assert c["scoruri"]["plecare"] >= 0.4
        assert c["banda"] == "P3"


def test_capcana_c_platinum_fara_semnale_nu_apare(pipeline):
    client = next(c for c in pipeline["pf"].clients if c["client_id"] == cid("capcana_c"))
    assert client["nivel_relatie"] == "platinum"
    assert cases_of(pipeline, cid("capcana_c")) == []


def test_capcana_d_ci_expirata_plus_refinantare_P1_blocat(pipeline):
    cs = cases_of(pipeline, cid("capcana_d"))
    assert len(cs) == 1
    c = cs[0]
    assert c["banda"] == "P1"
    assert c["blocaje"] == ["ci_expirata"]
    assert c["actiune_propusa"] == "task_ci_expirata"
    assert c["request_id"] is not None


def test_capcana_e_cerere_se_ataseaza_fara_dublura(pipeline):
    client = cid("capcana_e")
    req = next(r for r in pipeline["pf"].requests if r["client_id"] == client and r["tip"] == "adeverinta_sold")
    cs = cases_of(pipeline, client)
    assert len(cs) == 1                                   # un singur credit → un singur caz
    assert cs[0]["request_id"] == req["request_id"]
    assert any(s["id"] == "expirare_dobanda_fixa" for s in cs[0]["semnale"])   # era deja în coadă din scanare


# ---------------------------------------------------------------- cerințe dure + metrici

def test_cerinte_dure_zero_incalcari(pipeline, cfg):
    gt = json.loads((pipeline["dir"] / "ground_truth.json").read_text(encoding="utf-8"))
    q = eval_queue(pipeline["cases"], gt, pipeline["pf"], cfg)
    assert all(v["incalcari"] == 0 for v in q["cerinte_dure"].values()), q["cerinte_dure"]


def test_f1_detectie_peste_prag(pipeline, cfg):
    gt = json.loads((pipeline["dir"] / "ground_truth.json").read_text(encoding="utf-8"))
    assert eval_detection(pipeline["det"], gt, cfg)["global"]["f1"] >= 0.9


def test_schema_caz_stabila(pipeline):
    keys = ["case_id", "client_id", "loan_id", "produs", "sursa", "request_id", "semnale", "scoruri", "banda",
            "deadline", "motive_top3", "actiune_propusa", "blocaje", "creat_la"]
    for c in pipeline["cases"]:
        assert list(c) == keys
        assert set(c["scoruri"]) == {"plecare", "valoare", "actiune", "prioritate_retentie", "risc_credit", "prioritate"}
        assert 1 <= len(c["motive_top3"]) <= 3
        assert c["sursa"] in ("scan", "client_request")


def test_ordinea_cozii(pipeline, cfg):
    rank = {b: i for i, b in enumerate(cfg.priority.benzi)}
    keys = [(rank[c["banda"]], -c["scoruri"]["prioritate"], c["deadline"]) for c in pipeline["cases"]]
    assert keys == sorted(keys)


# ---------------------------------------------------------------- criteriile de acceptare §10

def test_config_buget_zero_trece_standard_pe_informare(pipeline, cfg):
    """§10.4: buget_retentie_pp.standard = 0 → cazurile standard cu gap mare trec pe informare_client, fără cod nou."""
    pf, det = pipeline["pf"], pipeline["det"]
    cfg0 = cfg.model_copy(deep=True)
    cfg0.priority.buget_retentie_pp["standard"] = 0.0
    before = {(c["client_id"], c["loan_id"]): c for c in pipeline["cases"]}
    after = build_queue(pf, cfg0, det, run_intake(pf, cfg0)).cases

    tier = {c["client_id"]: c["nivel_relatie"] for c in pf.clients}
    schimbate = [c for c in after if c["actiune_propusa"] == "informare_client"]
    assert schimbate, "niciun caz nu a trecut pe informare_client"
    for c in schimbate:
        assert tier[c["client_id"]] == "standard"
        assert before[(c["client_id"], c["loan_id"])]["actiune_propusa"] != "informare_client"
    assert cid("capcana_b") in {c["client_id"] for c in schimbate}


def test_determinism(tmp_path, cfg, pipeline):
    """Același seed → aceleași date și aceeași coadă."""
    generate(50, 42, TODAY.isoformat(), tmp_path)
    for name in ("clients.json", "loans.json", "transactions.json", "requests.json", "ground_truth.json"):
        assert (tmp_path / name).read_bytes() == (pipeline["dir"] / name).read_bytes(), name


def test_explain_lizibil_pentru_orice_caz(pipeline, cfg):
    res = pipeline["res"]
    for c in res.cases:
        txt = explain_case(c, res.inputs[c["case_id"]], res.traces[c["case_id"]], cfg)
        assert c["case_id"] in txt and "prioritate_retentie =" in txt and "De ce" in txt
