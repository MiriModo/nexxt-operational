"""Antrenarea modelului de churn pe `churn_labels.json`.

    python -m retailagent.churn.train --labels out/scale_10000/churn_labels.json [--versiune v1] [--tip auto|logistic|boosting]
    python -m retailagent.churn.train --din-approvals          # schelet: eticheta din rezultatele reale (approvals.json → rezultat)

Split pe clienți (nu pe cazuri), ca un client cu două credite să nu fie și în antrenare, și în test. Metrici:
AUC (discriminare) și, mai important, Brier + curba de calibrare — p intră în `cost ≤ p × V`, deci o
probabilitate corect calibrată valorează mai mult decât o ordonare bună. Artefact: models/churn_<v>.pkl
(joblib) + models/churn_<v>.json (feature-uri, versiune, metrici, data, seed).
"""
from __future__ import annotations

import argparse
import json
import time
from datetime import datetime
from pathlib import Path

from ..common import DATA_DIR, OUT_DIR, log_event, read_json, setup_console, write_json
from .features import FEATURE_NAMES, SCHEMA_VERSIUNE, vector

MODELS_DIR = Path("models")


def _calibrare(p: list[float], y: list[int], bins: int = 10) -> dict:
    rows = []
    ece = 0.0
    n = len(p)
    for i in range(bins):
        lo, hi = i / bins, (i + 1) / bins
        idx = [k for k in range(n) if lo <= p[k] < hi or (i == bins - 1 and p[k] == 1.0)]
        if not idx:
            continue
        pm = sum(p[k] for k in idx) / len(idx)
        rr = sum(y[k] for k in idx) / len(idx)
        ece += abs(pm - rr) * len(idx) / n
        rows.append({"interval": f"{lo:.1f}-{hi:.1f}", "n": len(idx), "p_medie": round(pm, 3), "rata_reala": round(rr, 3)})
    return {"ece": round(ece, 4), "bins": rows}


def _metrici(model, X, y) -> dict:
    from sklearn.metrics import brier_score_loss, log_loss, roc_auc_score
    p = [float(v) for v in model.predict_proba(X)[:, 1]]
    out = {"auc": round(float(roc_auc_score(y, p)), 4) if len(set(y)) > 1 else None,
           "brier": round(float(brier_score_loss(y, p)), 4), "log_loss": round(float(log_loss(y, p, labels=[0, 1])), 4),
           "rata_pozitiva": round(sum(y) / len(y), 4), "n": len(y)}
    out.update(_calibrare(p, y))
    return out


def train(labels_path: Path | str, out_dir: Path | str = MODELS_DIR, versiune: str = "v1", tip: str = "auto",
          seed: int = 42, eticheta: str = "a_plecat_fara_interventie") -> dict:
    import joblib
    from sklearn.ensemble import HistGradientBoostingClassifier
    from sklearn.linear_model import LogisticRegression
    from sklearn.model_selection import GroupShuffleSplit
    from sklearn.pipeline import Pipeline
    from sklearn.preprocessing import StandardScaler

    rows = [r for r in read_json(labels_path) if r.get("features")]
    if len(rows) < 100:
        raise SystemExit(f"prea puține rânduri cu feature-uri ({len(rows)}); rulează `churn.labels` pe un portofoliu mai mare")
    X = [vector(r["features"]) for r in rows]
    y = [int(bool(r[eticheta])) for r in rows]
    groups = [r["client_id"] for r in rows]
    tr, te = next(GroupShuffleSplit(n_splits=1, test_size=0.2, random_state=seed).split(X, y, groups))
    Xtr, ytr = [X[i] for i in tr], [y[i] for i in tr]
    Xte, yte = [X[i] for i in te], [y[i] for i in te]

    candidati = {}
    if tip in ("auto", "logistic"):
        candidati["logistic"] = Pipeline([("scaler", StandardScaler()),
                                          ("clf", LogisticRegression(C=1.0, max_iter=2000, random_state=seed))])
    if tip in ("auto", "boosting"):
        candidati["boosting"] = Pipeline([("clf", HistGradientBoostingClassifier(max_depth=4, learning_rate=0.05, max_iter=300,
                                                                                 l2_regularization=1.0, random_state=seed))])
    rezultate = {}
    for nume, pipe in candidati.items():
        t0 = time.perf_counter()
        pipe.fit(Xtr, ytr)
        rezultate[nume] = {"model": pipe, "test": _metrici(pipe, Xte, yte), "antrenare": _metrici(pipe, Xtr, ytr),
                           "secunde": round(time.perf_counter() - t0, 2)}
    ales = min(rezultate, key=lambda k: rezultate[k]["test"]["brier"])          # calibrarea decide
    best = rezultate[ales]
    medii = {f: float(sum(x[i] for x in Xtr) / len(Xtr)) for i, f in enumerate(FEATURE_NAMES)}
    bundle = {"pipeline": best["model"], "tip": ales, "feature_names": list(FEATURE_NAMES), "schema_versiune": SCHEMA_VERSIUNE,
              "versiune": versiune, "medii": medii, "metrici": best["test"], "antrenat_la": datetime.now().isoformat(timespec="seconds"),
              "n": len(rows), "eticheta": eticheta, "seed": seed, "sursa": str(labels_path)}
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    joblib.dump(bundle, out / f"churn_{versiune}.pkl")
    meta = {k: v for k, v in bundle.items() if k != "pipeline"}
    meta["candidati"] = {k: {"test": v["test"], "antrenare": v["antrenare"], "secunde": v["secunde"]} for k, v in rezultate.items()}
    meta["n_antrenare"], meta["n_test"] = len(tr), len(te)
    if ales == "logistic":
        clf = best["model"].named_steps["clf"]
        meta["coeficienti"] = {f: round(float(c), 4) for f, c in sorted(zip(FEATURE_NAMES, clf.coef_[0]), key=lambda t: -abs(t[1]))}
    write_json(out / f"churn_{versiune}.json", meta)
    return meta


def din_approvals(out_dir: Path | str = OUT_DIR, data_dir: Path | str = DATA_DIR) -> dict:
    """Schelet pentru reantrenarea pe rezultate reale: approvals.json → `rezultat` ∈ {ramas, plecat} la 90 de zile."""
    p = Path(out_dir) / "approvals.json"
    rows = read_json(p) if p.exists() else []
    etichetate = [r for r in rows if r.get("rezultat") in ("ramas", "plecat")]
    labels_p = Path(data_dir) / "churn_labels.json"
    by_case = {r["case_id"]: r for r in read_json(labels_p)} if labels_p.exists() else {}
    unite = [{**by_case[r["case_id"]], "a_plecat_real": r["rezultat"] == "plecat", "interventie_finala": r["interventie_finala"]}
             for r in etichetate if r["case_id"] in by_case]
    return {"aprobari": len(rows), "cu_rezultat": len(etichetate), "cu_feature_uri": len(unite), "minim_necesar": 200,
            "randuri": unite}


def main(argv: list[str] | None = None) -> None:
    setup_console()
    ap = argparse.ArgumentParser(description="Antrenează modelul de churn pe churn_labels.json.")
    ap.add_argument("--labels", default=str(DATA_DIR / "churn_labels.json"))
    ap.add_argument("--out-dir", default=str(MODELS_DIR))
    ap.add_argument("--versiune", default="v1")
    ap.add_argument("--tip", choices=["auto", "logistic", "boosting"], default="auto")
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--din-approvals", action="store_true", help="eticheta din rezultatele reale (approvals.json → rezultat)")
    a = ap.parse_args(argv)

    if a.din_approvals:
        r = din_approvals()
        print(f"Aprobări: {r['aprobari']} · cu rezultat la 90 de zile: {r['cu_rezultat']} · cu feature-uri: {r['cu_feature_uri']} "
              f"(minim pentru antrenare: {r['minim_necesar']})")
        if r["cu_feature_uri"] < r["minim_necesar"]:
            print("  Prea puține rezultate reale: se antrenează în continuare pe eticheta simulată. Când consilierii înregistrează "
                  "`rezultat` în approvals.json, această comandă devine sursa de reantrenare.")
            return
        tmp = Path(a.out_dir) / "labels_din_approvals.json"
        write_json(tmp, [{**x, "a_plecat_fara_interventie": x["a_plecat_real"]} for x in r["randuri"]])
        a.labels = str(tmp)

    meta = train(a.labels, a.out_dir, a.versiune, a.tip, a.seed)
    m = meta["metrici"]
    print(f"Model de churn {meta['versiune']} ({meta['tip']}): {meta['n']} rânduri, {meta['n_antrenare']} antrenare / {meta['n_test']} test, "
          f"eticheta {meta['eticheta']} → {a.out_dir}/churn_{meta['versiune']}.pkl")
    for k, v in meta["candidati"].items():
        mark = "►" if k == meta["tip"] else " "
        print(f"  {mark} {k:<9} test: AUC {v['test']['auc']} · Brier {v['test']['brier']} · ECE {v['test']['ece']} · log-loss {v['test']['log_loss']}"
              f"   (antrenare: AUC {v['antrenare']['auc']} · Brier {v['antrenare']['brier']}) · {v['secunde']}s")
    print("  calibrare (test): " + " · ".join(f"{b['interval']}: p {b['p_medie']:.2f} vs real {b['rata_reala']:.2f} (n={b['n']})" for b in m["bins"]))
    if "coeficienti" in meta:
        print("  coeficienți (top): " + ", ".join(f"{f} {c:+.2f}" for f, c in list(meta["coeficienti"].items())[:8]))
    print("  Atenție: eticheta e simulată din comportamentul sintetic — modelul învață regulile generatorului. Valoarea reală "
          "apare când eticheta vine din rezultatele consilierilor (--din-approvals).")
    log_event(OUT_DIR, "churn_train", "done", versiune=meta["versiune"], tip=meta["tip"], auc=m["auc"], brier=m["brier"], n=meta["n"])


if __name__ == "__main__":
    main()
