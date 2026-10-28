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


# ---------------------------------------------------------------- constraints.yaml

class DtiCfg(BaseModel):
    max: float
    max_valuta: float = 0.20
    bonus_prima_locuinta: float = 0.0
    venit_minim_lunar_ron: float = 0.0


class LtvCfg(BaseModel):
    max: dict[str, float]


class VarstaCfg(BaseModel):
    max_la_scadenta: int
    min_la_acordare: int = 18


class RestructurareCfg(BaseModel):
    prelungire_maxima_luni: int
    pauza_rata_maxima_luni: int
    dti_tinta: float


class ConstraintsConfig(BaseModel):
    dti: DtiCfg
    ltv: LtvCfg
    varsta: VarstaCfg
    marja_minima_pp: float
    restructurare: RestructurareCfg


# ---------------------------------------------------------------- retention.yaml

TipInterventie = Literal["nimic", "informare", "comision", "reducere_marja", "fix_piata", "pachet", "restructurare"]
Conditie = Literal["salariu_la_alta_banca", "risc", "fara_risc"]
CHEI_PIATA = ("fixa_1_an", "fixa_3_ani", "fixa_5_ani", "fixa_toata_durata", "marja_variabila")


class InterventieCfg(BaseModel):
    id: str
    tip: TipInterventie
    eticheta: str
    cost_fix: float = 0.0
    reducere_pp: float = 0.0
    ani: int = 0
    cheie_piata: str | None = None
    efect_scor: float = 0.0
    efect_legaturi: float = 0.0
    necesita: list[Conditie] = Field(default_factory=list)

    @model_validator(mode="after")
    def _check(self) -> "InterventieCfg":
        if self.tip == "reducere_marja" and self.reducere_pp <= 0:
            raise ValueError(f"intervenția {self.id}: reducere_marja fără reducere_pp")
        if self.tip == "fix_piata" and (self.ani <= 0 or self.cheie_piata not in CHEI_PIATA):
            raise ValueError(f"intervenția {self.id}: fix_piata cere ani > 0 și cheie_piata din {CHEI_PIATA}")
        return self


class LegaturiCfg(BaseModel):
    ponderi: dict[str, float]
    produse_max: int
    vechime_max_ani: float
    nivel_scor: dict[str, float]
    activitate_min_ron: float
    min_pentru_oferta: float


class ValoareClientCfg(BaseModel):
    ani_max_produse: float
    produse_ron_pe_an: dict[str, float]


class RetentionConfig(BaseModel):
    p_tinta: float = Field(gt=0.0, lt=1.0)
    sigmoid: dict[str, float]
    B_referinta_ron: float = Field(gt=0.0)
    B_norm_max: float = 2.0
    semnale_active: dict[str, float]
    interogari_bc_min_pentru_activ: int = 2
    legaturi: LegaturiCfg
    valoare: ValoareClientCfg
    piata: dict[str, str]
    interventii: list[InterventieCfg]
    oug50: dict[str, float]

    @model_validator(mode="after")
    def _check(self) -> "RetentionConfig":
        ids = [i.id for i in self.interventii]
        dup = {i for i in ids if ids.count(i) > 1}
        if dup:
            raise ValueError(f"intervenții duplicate în retention.yaml: {sorted(dup)}")
        for k in ("a", "b", "c", "d"):
            if k not in self.sigmoid:
                raise ValueError(f"retention.yaml: sigmoid.{k} lipsește")
        for produs, cheie in self.piata.items():
            if cheie not in CHEI_PIATA:
                raise ValueError(f"retention.yaml: piata.{produs} = {cheie!r} nu e o cheie cunoscută {CHEI_PIATA}")
        if abs(sum(self.legaturi.ponderi.values()) - 1.0) > 1e-6:
            raise ValueError("retention.yaml: legaturi.ponderi trebuie să însumeze 1.0")
        return self

    def by_id(self) -> dict[str, InterventieCfg]:
        return {i.id: i for i in self.interventii}


# ---------------------------------------------------------------- checks.yaml

class VerificareCfg(BaseModel):
    id: str
    treapta: str
    externa: bool
    strat: Literal["baza", "produs", "motiv"]
    produse: list[str] = Field(default_factory=list)
    descriere: str
    necesita_consimtamant: str | None = None
    parametri: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def _check(self) -> "VerificareCfg":
        if self.strat == "produs" and not self.produse:
            raise ValueError(f"verificarea {self.id}: strat=produs fără listă de produse")
        return self


class MotivCfg(BaseModel):
    adauga: list[str] = Field(default_factory=list)
    sare: list[str] = Field(default_factory=list)
    doar: list[str] | None = None


class DocumentCfg(BaseModel):
    tip: str
    valabil: bool = False
    max_zile: int | None = None
    tipologii: list[str] | None = None
    produse: list[str] | None = None


class ChecksConfig(BaseModel):
    trepte: list[str]
    verificari: list[VerificareCfg]
    motive: dict[str, MotivCfg]
    documente_necesare: dict[str, list[DocumentCfg]]

    @model_validator(mode="after")
    def _check(self) -> "ChecksConfig":
        ids = [v.id for v in self.verificari]
        dup = {i for i in ids if ids.count(i) > 1}
        if dup:
            raise ValueError(f"verificări duplicate în checks.yaml: {sorted(dup)}")
        if len(self.trepte) != len(set(self.trepte)):
            raise ValueError("checks.yaml: trepte duplicate")
        for v in self.verificari:
            if v.treapta not in self.trepte:
                raise ValueError(f"verificarea {v.id}: treapta {v.treapta!r} nu e în {self.trepte}")
        known = set(ids)
        for motiv, m in self.motive.items():
            for vid in m.adauga + m.sare + (m.doar or []):
                if vid not in known:
                    raise ValueError(f"checks.yaml: motivul {motiv!r} referă verificarea necunoscută {vid!r}")
        return self

    def by_id(self) -> dict[str, VerificareCfg]:
        return {v.id: v for v in self.verificari}


# ---------------------------------------------------------------- agregare

MOTIVE_SPECIALE = ("risc", "blocaj")


class Config(BaseModel):
    signals: SignalsConfig
    priority: PriorityConfig
    constraints: ConstraintsConfig
    retention: RetentionConfig
    checks: ChecksConfig

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
        for sid in self.retention.semnale_active:
            if sid not in sig:
                raise ValueError(f"retention.yaml referă semnalul necunoscut {sid!r}")
        for tier in self.retention.legaturi.nivel_scor:
            if tier not in self.priority.buget_retentie_pp:
                raise ValueError(f"retention.yaml: nivelul {tier!r} nu are buget în priority.yaml")
        valid = set(sig) | set(self.priority.cereri) | set(MOTIVE_SPECIALE)
        for motiv in self.checks.motive:
            if motiv not in valid:
                raise ValueError(f"checks.yaml: motivul {motiv!r} nu e semnal, tip de cerere sau {MOTIVE_SPECIALE}")
        return self


def _load_yaml(path: Path) -> dict:
    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f)


def load_config(config_dir: Path | str = CONFIG_DIR) -> Config:
    config_dir = Path(config_dir)
    return Config(signals=SignalsConfig(**_load_yaml(config_dir / "signals.yaml")),
                  priority=PriorityConfig(**_load_yaml(config_dir / "priority.yaml")),
                  constraints=ConstraintsConfig(**_load_yaml(config_dir / "constraints.yaml")),
                  retention=RetentionConfig(**_load_yaml(config_dir / "retention.yaml")),
                  checks=ChecksConfig(**_load_yaml(config_dir / "checks.yaml")))
