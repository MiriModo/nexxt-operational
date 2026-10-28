"""Configurația modelului final (M1-T2): constraints.yaml + retention.yaml, validate cu pydantic."""
from __future__ import annotations

import shutil
from pathlib import Path

import pytest
import yaml

from retailagent.config_loader import load_config

ROOT = Path(__file__).resolve().parents[1]


def test_load_config_intoarce_configurile_noi(cfg):
    c, r = cfg.constraints, cfg.retention
    assert c.dti.max == 0.40 and c.dti.bonus_prima_locuinta == 0.05
    assert c.ltv.max["ipotecar"] == 0.85
    assert c.varsta.max_la_scadenta == 70
    assert c.marja_minima_pp == 1.5
    assert 0 < r.p_tinta < 1
    assert set(r.sigmoid) >= {"a", "b", "c", "d"}
    assert r.legaturi.min_pentru_oferta > 0
    ids = [i.id for i in r.interventii]
    assert len(ids) == len(set(ids)) and len(ids) >= 12
    assert {"nu_interveni", "informare", "reducere_marja_0_2", "fix_3_ani", "pachet_salariu", "ajustare_maturitate",
            "pauza_rata"} <= set(ids)
    assert r.by_id()["pachet_salariu"].necesita == ["salariu_la_alta_banca"]
    assert r.by_id()["reducere_marja_0_4"].reducere_pp == 0.4
    assert r.piata["ipotecar"] == "fixa_3_ani" and r.piata["nevoi_personale"] == "fixa_toata_durata"
    assert r.oug50["fixa_peste_1_an_pct"] == 1.0


def _copy_config(tmp_path: Path) -> Path:
    d = tmp_path / "config"
    shutil.copytree(ROOT / "config", d)
    return d


def _rewrite(path: Path, fn) -> None:
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    fn(data)
    path.write_text(yaml.safe_dump(data, allow_unicode=True), encoding="utf-8")


def test_interventie_duplicata_ridica_eroare(tmp_path):
    d = _copy_config(tmp_path)
    _rewrite(d / "retention.yaml", lambda y: y["interventii"].append(dict(y["interventii"][1])))
    with pytest.raises(ValueError, match="duplicat"):
        load_config(d)


def test_p_tinta_in_afara_intervalului_ridica_eroare(tmp_path):
    d = _copy_config(tmp_path)
    _rewrite(d / "retention.yaml", lambda y: y.update(p_tinta=1.5))
    with pytest.raises(ValueError):
        load_config(d)


def test_cheie_de_piata_necunoscuta_ridica_eroare(tmp_path):
    d = _copy_config(tmp_path)
    _rewrite(d / "retention.yaml", lambda y: y["piata"].update(ipotecar="fixa_7_ani"))
    with pytest.raises(ValueError, match="piata"):
        load_config(d)


def test_tip_interventie_necunoscut_ridica_eroare(tmp_path):
    d = _copy_config(tmp_path)
    _rewrite(d / "retention.yaml", lambda y: y["interventii"][0].update(tip="magie"))
    with pytest.raises(ValueError):
        load_config(d)
