"""README-ul documentează toate comenzile și fluxul (M6-T3)."""
from __future__ import annotations

from pathlib import Path

README = (Path(__file__).resolve().parents[1] / "README.md").read_text(encoding="utf-8")
MODULE = ("generate", "scan", "intake", "queue", "checks", "retention", "recommend", "approve", "explain", "evaluate",
          "demo", "pipeline")


def test_readme_listeaza_toate_comenzile():
    for m in MODULE:
        assert f"python -m retailagent.{m}" in README, m
    assert "pip install -r requirements.txt" in README and "python -m pytest" in README


def test_readme_descrie_modelul_final():
    for s in ("B =", "p =", "V =", "p_tinta", "orizont", "legături", "aceeași reducere pentru toți", "Interpretări",
              "MODEL_FINAL.md", "demo.html", "audit.jsonl", "checks.yaml", "retention.yaml", "constraints.yaml"):
        assert s in README, s
