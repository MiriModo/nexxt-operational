"""Versionarea deciziilor: ce configurație (YAML), ce model de churn și ce prompturi au produs un rezultat.

Fiecare rând de audit, fiecare recomandare și `evaluation.json` poartă versiunea, ca o decizie de ieri să poată
fi reprodusă și explicată și după ce s-au schimbat pragurile sau modelul.
"""
from __future__ import annotations

import hashlib
import subprocess
from pathlib import Path

from .common import CONFIG_DIR, read_json


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def versiune_config(config_dir: Path | str = CONFIG_DIR) -> dict:
    """Hash-ul tuturor YAML-urilor din config/ (ordonate după nume) + hash scurt per fișier."""
    d = Path(config_dir)
    fisiere = sorted(p for p in d.glob("*.yaml"))
    per = {p.name: _sha(p.read_bytes())[:12] for p in fisiere}
    total = _sha(b"".join(p.name.encode() + b"\n" + p.read_bytes() for p in fisiere))
    return {"hash": total[:12], "fisiere": per}


def versiune_model(cfg) -> dict:
    ch = cfg.retention.churn
    if ch.model != "antrenat":
        s = cfg.retention.sigmoid
        return {"model": "sigmoid", "versiune": f"a={s['a']} b={s['b']} c={s['c']} d={s['d']}", "hash": None}
    pkl = Path(ch.cale)
    if not pkl.is_absolute() and not pkl.exists():            # relativ la proiect, oriunde ar rula serverul
        pkl = Path(__file__).resolve().parents[1] / pkl
    meta_p = pkl.with_suffix(".json")
    meta = read_json(meta_p) if meta_p.exists() else {}
    return {"model": "antrenat", "versiune": meta.get("versiune"), "tip": meta.get("tip"), "antrenat_la": meta.get("antrenat_la"),
            "n": meta.get("n"), "hash": _sha(pkl.read_bytes())[:12] if pkl.exists() else None}


def versiune_cod() -> str | None:
    try:
        out = subprocess.run(["git", "rev-parse", "--short", "HEAD"], capture_output=True, text=True, timeout=5,
                             cwd=Path(__file__).resolve().parents[1])
        return out.stdout.strip() or None
    except (OSError, subprocess.SubprocessError):
        return None


def versiune_completa(cfg, config_dir: Path | str = CONFIG_DIR) -> dict:
    c, m = versiune_config(config_dir), versiune_model(cfg)
    llm = getattr(cfg, "llm", None)
    prompturi = None
    if llm is not None and llm.activat:
        from .llm import hash_prompt
        prompturi = {"llm": hash_prompt(llm), "furnizor": llm.furnizor, "model": llm.modele.get(llm.furnizor, "")}
    scurt = f"cfg:{c['hash']} model:{m['model']}:{m['hash'] or m['versiune']} prompturi:{prompturi['llm'] if prompturi else '—'}"
    return {"config": c, "model": m, "prompturi": prompturi, "cod": versiune_cod(), "scurt": scurt}
