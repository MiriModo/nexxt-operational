"""Profilul statistic al portofoliului realist (config/portofoliu.yaml), validat cu pydantic.

Separat de `config_loader.Config`: generatorul nu depinde de restul configurației, iar restul aplicației nu
depinde de profil. `load_profil(path)` întoarce `ProfilPortofoliu`.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, Field, model_validator

from .common import CONFIG_DIR

PROFIL_PATH = CONFIG_DIR / "portofoliu.yaml"
PRODUSE = ("ipotecar", "imobiliar", "nevoi_personale", "card_credit", "refinantare")
TIPOLOGII = ("SL", "SE", "IND", "PEN", "ANT", "DIA", "TAN")

Prob = float  # 0..1
Tri = list[float]  # [min, mod, max]


def _check_prob(name: str, p: float) -> None:
    if not 0.0 <= p <= 1.0:
        raise ValueError(f"{name}: probabilitatea {p} nu e în [0, 1]")


def _check_weights(name: str, w: dict[str, float] | list[float]) -> None:
    vals = list(w.values()) if isinstance(w, dict) else w
    if any(v < 0 for v in vals):
        raise ValueError(f"{name}: ponderi negative")
    if abs(sum(vals) - 1.0) > 1e-6:
        raise ValueError(f"{name}: ponderile însumează {sum(vals):.4f}, nu 1")


def _check_tri(name: str, t: list[float]) -> None:
    if len(t) != 3 or not (t[0] <= t[1] <= t[2]):
        raise ValueError(f"{name}: distribuția triunghiulară trebuie să fie [min, mod, max] crescător, nu {t}")


class Interval(BaseModel):
    min: float
    mod: float | None = None
    max: float

    @model_validator(mode="after")
    def _check(self) -> "Interval":
        if self.mod is None:
            self.mod = (self.min + self.max) / 2
        if not self.min <= self.mod <= self.max:
            raise ValueError(f"intervalul [{self.min}, {self.mod}, {self.max}] nu e crescător")
        return self


class ParametriProdus(BaseModel):
    sold: Tri
    ani_ramasi: Tri
    ani_vechime: Tri
    marja: Tri
    fixa_prob: Prob

    @model_validator(mode="after")
    def _check(self) -> "ParametriProdus":
        for k in ("sold", "ani_ramasi", "ani_vechime", "marja"):
            _check_tri(k, getattr(self, k))
        _check_prob("fixa_prob", self.fixa_prob)
        return self


class CrediteCfg(BaseModel):
    nr_credite: dict[str, list[float]]
    produse: dict[str, dict[str, float]]
    parametri: dict[str, ParametriProdus]

    @model_validator(mode="after")
    def _check(self) -> "CrediteCfg":
        for t in TIPOLOGII:
            if t not in self.nr_credite or t not in self.produse:
                raise ValueError(f"credite: lipsește tipologia {t}")
            _check_weights(f"nr_credite.{t}", self.nr_credite[t])
            _check_weights(f"produse.{t}", self.produse[t])
            for p in self.produse[t]:
                if p not in PRODUSE:
                    raise ValueError(f"produse.{t}: produs necunoscut {p!r}")
        for p in ("ipotecar", "imobiliar", "nevoi_personale", "refinantare"):
            if p not in self.parametri:
                raise ValueError(f"credite.parametri: lipsește {p}")
        return self


class SemnalCfg(BaseModel):
    prob: Prob
    extra: dict[str, Any] = Field(default_factory=dict)

    model_config = {"extra": "allow"}

    @model_validator(mode="after")
    def _check(self) -> "SemnalCfg":
        _check_prob("prob", self.prob)
        for k, v in (self.model_extra or {}).items():
            if k.startswith("prob") and isinstance(v, (int, float)):
                _check_prob(k, float(v))
        return self

    def get(self, key: str, default: Any = None) -> Any:
        return (self.model_extra or {}).get(key, default)


class SemnaleCfg(BaseModel):
    per_credit: dict[str, SemnalCfg]
    per_client: dict[str, SemnalCfg]


class CorelatieCfg(BaseModel):
    cauza: str
    efect: str
    factor: float = Field(gt=0.0)


class CerereCfg(BaseModel):
    prob: Prob
    produse: list[str] = Field(default_factory=list)
    suma: list[float] | None = None

    @model_validator(mode="after")
    def _check(self) -> "CerereCfg":
        _check_prob("prob", self.prob)
        if self.suma is not None and (len(self.suma) != 2 or self.suma[0] > self.suma[1]):
            raise ValueError(f"suma trebuie să fie [min, max], nu {self.suma}")
        return self


class ExterneCfg(BaseModel):
    bc_negativ: Prob
    crc_garant_restante: Prob
    cf_litigiu: Prob
    codebitor_prob: Prob

    @model_validator(mode="after")
    def _check(self) -> "ExterneCfg":
        for k in ("bc_negativ", "crc_garant_restante", "cf_litigiu", "codebitor_prob"):
            _check_prob(k, getattr(self, k))
        return self


class TranzactiiCfg(BaseModel):
    cumparaturi_pe_luna: list[int]
    nr_utilitati: int = Field(ge=0, le=5)
    prob_chirie_in: Prob
    prob_chirie_out: Prob
    # cât din plățile „altele” rămân pe comerciantul tras (`pastreaza`) sau devin restaurante / divertisment /
    # transport / servicii / cash / călătorii; lipsă = ponderile implicite din generate.py
    categorii: dict[str, Prob] | None = None

    @model_validator(mode="after")
    def _categorii(self) -> "TranzactiiCfg":
        if self.categorii is not None:
            permise = {"pastreaza", "restaurants", "entertainment", "transport", "services", "cash", "travel"}
            rele = set(self.categorii) - permise
            if rele:
                raise ValueError(f"tranzactii.categorii: chei necunoscute {sorted(rele)}; permise {sorted(permise)}")
            if abs(sum(self.categorii.values()) - 1.0) > 1e-6:
                raise ValueError("tranzactii.categorii: ponderile trebuie să însumeze 1.0")
        return self


class AngajatoriCfg(BaseModel):
    bazin: int = Field(ge=1)
    prob_insolventa: Prob
    prob_dizolvare: Prob
    prob_client_al_bancii: Prob


class ComportamentCfg(BaseModel):
    prag_baza_ron: float = Field(gt=0)
    c_vechime: float = 0.0
    c_produse: float = 0.0
    c_nivel: float = 0.0
    c_activitate: float = 0.0
    zgomot_sigma: float = Field(ge=0.0)
    prob_reactie_informare: Prob
    prob_accepta_pachet: Prob


class ProfilPortofoliu(BaseModel):
    tipologii: dict[str, float]
    niveluri: dict[str, float]
    niveluri_bonus_vechime: float = 0.0
    vechime_client_ani: Interval
    produse_atasate: Interval
    credite: CrediteCfg
    semnale: SemnaleCfg
    corelatii: list[CorelatieCfg] = Field(default_factory=list)
    cereri: dict[str, CerereCfg]
    externe: ExterneCfg
    tranzactii: TranzactiiCfg
    angajatori: AngajatoriCfg
    comportament: ComportamentCfg

    @model_validator(mode="after")
    def _check(self) -> "ProfilPortofoliu":
        _check_weights("tipologii", self.tipologii)
        if set(self.tipologii) != set(TIPOLOGII):
            raise ValueError(f"tipologii: trebuie exact {TIPOLOGII}")
        _check_weights("niveluri", self.niveluri)
        if set(self.niveluri) != {"standard", "gold", "platinum"}:
            raise ValueError("niveluri: trebuie standard / gold / platinum")
        toate = set(self.semnale.per_credit) | set(self.semnale.per_client)
        for c in self.corelatii:
            if c.cauza not in toate or c.efect not in toate:
                raise ValueError(f"corelatii: {c.cauza} → {c.efect} referă un semnal necunoscut")
        for t, p in (("prob_insolventa", self.angajatori.prob_insolventa), ("prob_dizolvare", self.angajatori.prob_dizolvare)):
            _check_prob(f"angajatori.{t}", p)
        return self


def load_profil(path: Path | str = PROFIL_PATH) -> ProfilPortofoliu:
    with open(path, encoding="utf-8") as f:
        return ProfilPortofoliu(**yaml.safe_load(f))
