"""Încărcarea și validarea configurației YAML (pydantic). Erorile de config opresc rularea cu mesaj clar."""
from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Literal

import yaml
from pydantic import BaseModel, Field, model_validator

from .common import CONFIG_DIR

Familie = Literal["plecare", "risc_credit", "blocaj_proces"]


class SignalCfg(BaseModel):
    id: str
    familie: Familie
    nivel: Literal["client", "credit"]
    descriere: str
    inputs: list[str]
    regula: str
    dovada: str
    motiv: str
    actiune_sugerata: str
    declansator: bool = True
    evaluat: bool = True
    sursa_cerere: bool = False
    activat: bool = True
    parametri: dict[str, Any] = Field(default_factory=dict)


class SignalsConfig(BaseModel):
    versiune: int
    tipare: dict[str, list[str]]
    recurenta: dict[str, int]
    semnale: list[SignalCfg]

    @model_validator(mode="after")
    def _check(self) -> "SignalsConfig":
        ids = [s.id for s in self.semnale]
        dup = {i for i in ids if ids.count(i) > 1}
        if dup:
            raise ValueError(f"semnale duplicate în signals.yaml: {sorted(dup)}")
        for key in ("pensie", "dividende", "firma", "creditor", "poprire"):
            if key not in self.tipare:
                raise ValueError(f"lipsește tipare.{key}")
        for key, pats in self.tipare.items():
            for p in pats:
                try:
                    re.compile(p)
                except re.error as e:
                    raise ValueError(f"regex invalid în tipare.{key}: {p!r} ({e})") from e
        return self

    def by_id(self) -> dict[str, SignalCfg]:
        return {s.id: s for s in self.semnale}

    def active(self) -> list[SignalCfg]:
        return [s for s in self.semnale if s.activat]


class BandCfg(BaseModel):
    prioritate_min: float
    sau_risc_credit_min: float | None = None
    sau_semnal_activ: bool = False
    sla_zile: int


class ValoareCfg(BaseModel):
    venit_viitor: float
    produse_atasate: float
    produse_max: int = 4


class ActiuneCfg(BaseModel):
    oferta_in_grila: float
    partial: float
    imposibil: float


class GrilaCfg(BaseModel):
    spread_peste_piata_pp: dict[str, float]
    multiplicator_partial: float = 2.0


class RiscCfg(BaseModel):
    agregare: Literal["max"]
    blocheaza_retentia_daca: float


class BlocajCfg(BaseModel):
    activ_de_la: float
    ordine: list[str]


class CerereCfg(BaseModel):
    actiune: str | None
    prioritate_min: float = 0.0


class RutareCfg(BaseModel):
    retentie_min: float
    retentie_la_semnal_activ: bool = False
    informare_expirare_min: float
    actiune_implicita: str


class DeadlineCfg(BaseModel):
    informare_inainte_de_expirare_zile: int


class PriorityConfig(BaseModel):
    ponderi_plecare: dict[str, float]
    bonus_plecare: dict[str, float] = Field(default_factory=dict)
    valoare: ValoareCfg
    actiune: ActiuneCfg
    grila_retentie: GrilaCfg
    risc_credit: RiscCfg
    buget_retentie_pp: dict[str, float]
    benzi: dict[str, BandCfg]
    semnale_active: dict[str, float] = Field(default_factory=dict)
    blocaj: BlocajCfg
    cereri: dict[str, CerereCfg]
    rutare: RutareCfg
    deadline: DeadlineCfg

    @model_validator(mode="after")
    def _check(self) -> "PriorityConfig":
        if list(self.benzi) != sorted(self.benzi):
            raise ValueError("benzile trebuie listate în ordinea P1, P2, P3 ...")
        mins = [b.prioritate_min for b in self.benzi.values()]
        if mins != sorted(mins, reverse=True):
            raise ValueError("benzi: prioritate_min trebuie să scadă de la P1 la ultima bandă")
        return self


class Config(BaseModel):
    signals: SignalsConfig
    priority: PriorityConfig

    @model_validator(mode="after")
    def _cross(self) -> "Config":
        sig = self.signals.by_id()
        for sid in list(self.priority.ponderi_plecare) + list(self.priority.bonus_plecare):
            if sid not in sig:
                raise ValueError(f"priority.yaml referă semnalul necunoscut {sid!r}")
            if sig[sid].familie != "plecare":
                raise ValueError(f"{sid!r} are pondere de plecare dar familia e {sig[sid].familie}")
        for sid in list(self.priority.semnale_active) + self.priority.blocaj.ordine:
            if sid not in sig:
                raise ValueError(f"priority.yaml referă semnalul necunoscut {sid!r}")
        return self


def _load_yaml(path: Path) -> dict:
    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f)


def load_config(config_dir: Path | str = CONFIG_DIR) -> Config:
    config_dir = Path(config_dir)
    return Config(signals=SignalsConfig(**_load_yaml(config_dir / "signals.yaml")),
                  priority=PriorityConfig(**_load_yaml(config_dir / "priority.yaml")))
