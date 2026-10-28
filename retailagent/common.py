"""Utilitare comune: căi implicite, I/O JSON, calendar, formatare în română, logging structurat."""
from __future__ import annotations

import json
import sys
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any

DATA_DIR = Path("data")
OUT_DIR = Path("out")
CONFIG_DIR = Path("config")
DEFAULT_TODAY = "2026-10-28"


def setup_console() -> None:
    """Consola Windows nu e UTF-8 implicit; diacriticele trebuie să apară corect."""
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8")
        except (AttributeError, ValueError):
            pass


# ---------------------------------------------------------------- I/O

def read_json(path: Path | str) -> Any:
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def write_json(path: Path | str, obj: Any) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=2)


def log_event(out_dir: Path | str, step: str, event: str, **fields: Any) -> None:
    """Logging structurat (JSON lines) în out/run.log."""
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    rec = {"ts": datetime.now().isoformat(timespec="seconds"), "step": step, "event": event, **fields}
    with open(out_dir / "run.log", "a", encoding="utf-8") as f:
        f.write(json.dumps(rec, ensure_ascii=False) + "\n")


# ---------------------------------------------------------------- calendar

def parse_date(s: str | date | None) -> date | None:
    if s is None or s == "":
        return None
    if isinstance(s, date):
        return s
    return date.fromisoformat(s[:10])


def resolve_today(arg: str | None, data_dir: Path | str = DATA_DIR) -> date:
    """`--today` explicit > data din market.json > valoarea implicită."""
    if arg:
        return date.fromisoformat(arg)
    market = Path(data_dir) / "market.json"
    if market.exists():
        return date.fromisoformat(read_json(market)["data"])
    return date.fromisoformat(DEFAULT_TODAY)


def month_key(d: date) -> str:
    return f"{d.year:04d}-{d.month:02d}"


def shift_month(key: str, k: int) -> str:
    y, m = int(key[:4]), int(key[5:7])
    idx = y * 12 + (m - 1) + k
    return f"{idx // 12:04d}-{idx % 12 + 1:02d}"


def last_months(end_key: str, n: int) -> list[str]:
    """Ultimele n luni, în ordine cronologică, terminând cu end_key inclusiv."""
    return [shift_month(end_key, -i) for i in range(n - 1, -1, -1)]


def add_years(d: date, years: float) -> date:
    return d + timedelta(days=round(years * 365.25))


def years_between(a: date, b: date) -> float:
    return (b - a).days / 365.25


# ---------------------------------------------------------------- formatare

def fmt_ron(x: float) -> str:
    """41200.4 -> '41.200' (separator de mii românesc)."""
    return f"{round(x):,}".replace(",", ".")


def fmt_num(x: float, nd: int = 2) -> str:
    return f"{x:.{nd}f}"


def plural(n: float, singular: str, plural_: str) -> str:
    """plural(1, 'an', 'ani') -> '1 an'; plural(22, 'an', 'ani') -> '22 ani'."""
    n = round(n)
    return f"{n} {singular if n == 1 else plural_}"


def fmt_date(d: date | None) -> str:
    return d.isoformat() if d else "—"
