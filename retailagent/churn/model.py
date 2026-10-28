"""Interfața `ChurnModel` și cele două implementări: `SigmoidChurn` (formula din retention.yaml, fallback) și
`TrainedChurn` (modelul antrenat din models/churn_v<N>.pkl). Alegerea: retention.yaml → churn.model.

Modelul dă doar logit-ul lui p_înainte; intervențiile rămân deplasări pe logit (`efect_scor`), iar meniul,
constrângerile și optimizarea nu se ating. `predict_logit_batch` evită apelurile unul câte unul la scară.
"""
from __future__ import annotations

import math
import warnings
from abc import ABC, abstractmethod
from pathlib import Path

from .features import FEATURE_NAMES, vector


def sigmoid(x: float) -> float:
    return 1.0 / (1.0 + math.exp(-x))


def logit(p: float) -> float:
    p = min(1 - 1e-6, max(1e-6, p))
    return math.log(p / (1 - p))


class ChurnModel(ABC):
    nume: str = "?"
    versiune: str = "—"

    @abstractmethod
    def predict_logit(self, x: dict[str, float]) -> float: ...

    def predict_logit_batch(self, xs: list[dict[str, float]]) -> list[float]:
        return [self.predict_logit(x) for x in xs]

    @abstractmethod
    def explain(self, x: dict[str, float]) -> list[tuple[str, float]]:
        """Contribuțiile (feature, delta logit) sortate după mărime, pentru `explain` și demo."""


class SigmoidChurn(ChurnModel):
    """p = sigmoid(a·B_norm + b·semnale_active − c − d·legături) — parametrii din retention.yaml → sigmoid."""
    nume = "sigmoid"

    def __init__(self, cfg):
        s = cfg.retention.sigmoid
        self.a, self.b, self.c, self.d = s["a"], s["b"], s["c"], s["d"]
        self.versiune = f"a={self.a} b={self.b} c={self.c} d={self.d}"

    def predict_logit(self, x: dict[str, float]) -> float:
        return self.a * x["B_norm"] + self.b * x["n_active"] - self.c - self.d * x["legaturi"]

    def explain(self, x: dict[str, float]) -> list[tuple[str, float]]:
        return [("B_norm", self.a * x["B_norm"]), ("n_active", self.b * x["n_active"]), ("legaturi", -self.d * x["legaturi"]),
                ("constanta", -self.c)]


class TrainedChurn(ChurnModel):
    """Model scikit-learn salvat de `churn.train` (joblib): pipeline + nume de feature-uri + medii + metadate."""
    nume = "antrenat"

    def __init__(self, bundle: dict, cale: str = ""):
        if tuple(bundle["feature_names"]) != FEATURE_NAMES:
            raise ValueError(f"modelul {cale} a fost antrenat pe altă schemă de feature-uri ({len(bundle['feature_names'])} vs {len(FEATURE_NAMES)}); reantrenează")
        self.pipeline = bundle["pipeline"]
        self.tip = bundle.get("tip", "?")
        self.medii = bundle.get("medii", {})
        self.metrici = bundle.get("metrici", {})
        self.versiune = f"{bundle.get('versiune', '?')} ({self.tip}, antrenat {bundle.get('antrenat_la', '?')[:10]}, n={bundle.get('n', '?')})"
        self.cale = cale

    @classmethod
    def load(cls, cale: Path | str) -> "TrainedChurn":
        import joblib
        return cls(joblib.load(cale), str(cale))

    def predict_logit_batch(self, xs: list[dict[str, float]]) -> list[float]:
        if not xs:
            return []
        probs = self.pipeline.predict_proba([vector(x) for x in xs])[:, 1]
        return [logit(float(p)) for p in probs]

    def predict_logit(self, x: dict[str, float]) -> float:
        return self.predict_logit_batch([x])[0]

    def explain(self, x: dict[str, float]) -> list[tuple[str, float]]:
        if self.tip == "logistic":
            scaler = self.pipeline.named_steps.get("scaler")
            clf = self.pipeline.named_steps["clf"]
            v = vector(x)
            z = (v - scaler.mean_) / scaler.scale_ if scaler is not None else v
            contrib = [(f, float(c * zi)) for f, c, zi in zip(FEATURE_NAMES, clf.coef_[0], z)]
            contrib.append(("constanta", float(clf.intercept_[0])))
        else:                                       # boosting: delta logit când feature-ul e adus la media de antrenare
            base = self.predict_logit(x)
            rows = [{**x, f: self.medii.get(f, 0.0)} for f in FEATURE_NAMES]
            contrib = [(f, base - alt) for f, alt in zip(FEATURE_NAMES, self.predict_logit_batch(rows))]
        return sorted(contrib, key=lambda t: -abs(t[1]))


_CACHE: dict[tuple, ChurnModel] = {}


def get_model(cfg) -> ChurnModel:
    """Modelul ales în retention.yaml → churn; dacă cel antrenat lipsește și fallback_sigmoid = true, sigmoidul."""
    ch = cfg.retention.churn
    key = (ch.model, ch.cale, id(cfg.retention.sigmoid))
    if key in _CACHE:
        return _CACHE[key]
    if ch.model == "antrenat":
        p = Path(ch.cale)
        if p.exists():
            m: ChurnModel = TrainedChurn.load(p)
        elif ch.fallback_sigmoid:
            warnings.warn(f"modelul antrenat {p} lipsește: se folosește sigmoidul (rulează `python -m retailagent.churn.train`)")
            m = SigmoidChurn(cfg)
        else:
            raise FileNotFoundError(f"modelul antrenat {p} lipsește și fallback_sigmoid = false")
    else:
        m = SigmoidChurn(cfg)
    _CACHE[key] = m
    return m
