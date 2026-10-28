"""Registrul de semnale.

Fiecare semnal e o funcție pură `(Context) -> SignalResult`, înregistrată cu decoratorul `@signal`.
Pragurile și treptele vin din `ctx.params` (secțiunea `parametri` din config/signals.yaml).

    @signal("expirare_dobanda_fixa", familie="plecare", nivel="credit")
    def expirare_dobanda_fixa(ctx: Context) -> SignalResult: ...
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Any, Callable

from .inflows import Flows


@dataclass(frozen=True)
class SignalResult:
    scor: float
    dovada: str = ""
    detalii: dict[str, Any] = field(default_factory=dict)


ZERO = SignalResult(0.0)


@dataclass(frozen=True)
class Context:
    today: date
    client: dict
    loan: dict | None                    # None pentru semnalele de nivel client
    loans: list[dict]                    # toate creditele clientului
    transactions: list[dict]
    payments: dict[str, list[dict]]      # loan_id -> istoric sortat cronologic
    employer: dict | None
    market: dict
    requests: list[dict]                 # cererile clientului
    flows: Flows                         # încasări/plăți recurente deduse din tranzacții
    params: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class SignalDef:
    id: str
    familie: str
    nivel: str
    fn: Callable[[Context], SignalResult]


REGISTRY: dict[str, SignalDef] = {}


def signal(id: str, familie: str, nivel: str = "client"):
    def deco(fn: Callable[[Context], SignalResult]):
        if id in REGISTRY:
            raise ValueError(f"semnal înregistrat de două ori: {id}")
        REGISTRY[id] = SignalDef(id, familie, nivel, fn)
        return fn
    return deco


def step_score(value: float, trepte: list[list[float]], descending: bool = False) -> float:
    """Trepte [[prag, scor], ...]: prima treaptă cu value ≤ prag (sau ≥ prag dacă descending) câștigă."""
    for prag, scor in trepte:
        if (value >= prag) if descending else (value <= prag):
            return float(scor)
    return 0.0


# înregistrarea efectivă a semnalelor (importurile populează REGISTRY)
from . import plecare, risc_credit, blocaj_proces  # noqa: E402,F401
