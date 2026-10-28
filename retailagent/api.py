"""API-ul interfeței (FastAPI): strat subțire peste funcțiile pure, pe contractul din ui/src/types/api.ts.

    uvicorn retailagent.api:app --reload --port 8000          # apoi: cd ui && npm run dev (proxy /api → 8000)

    GET  /api/metrici/context        {azi, clienti, p_tinta}
    GET  /api/cazuri                 toate cazurile din coadă (snapshot-ul per caz, ca în demo.html)
    GET  /api/cazuri/{id}            un caz
    GET  /api/metrici                cifra-vedetă, nu interveni, interogări evitate, acuratețe, cerințe dure
    POST /api/cazuri/{id}/decizie    {decizie, interventie?, motiv?} → approve.decide + persist (approvals.json, audit.jsonl)
    GET  /api/decizii                deciziile înregistrate (approvals.json)
    POST /api/rescan                 reface fluxul complet (după ce s-au schimbat datele sau YAML-urile)

Fluxul rulează o dată la pornire și stă în memorie; deciziile se scriu pe disc exact ca din CLI.
"""
from __future__ import annotations

import os
from datetime import datetime
from pathlib import Path
from typing import Literal

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from .approve import ApprovalError, decide, persist
from .common import CONFIG_DIR, DATA_DIR, OUT_DIR, read_json
from .demo import build_data
from .pipeline import run_full


class DecizieInput(BaseModel):
    decizie: Literal["aproba", "modifica", "respinge"]
    interventie: str | None = None
    motiv: str | None = None


class Stare:
    def __init__(self, data_dir, out_dir, config_dir):
        self.data_dir, self.out_dir, self.config_dir = Path(data_dir), Path(out_dir), Path(config_dir)
        self.refresh()

    def refresh(self) -> None:
        self.full = run_full(self.data_dir, self.out_dir, self.config_dir, rescan=True)
        gt = read_json(self.data_dir / "ground_truth.json")
        self.data = build_data(self.full, gt, None)
        self.cazuri = {c["case"]["case_id"]: c for c in self.data["cazuri"]}
        self.recs = {r["case_id"]: r for r in self.full.recs}
        self.offers = {o["case_id"]: o for o in self.full.offers}


def create_app(data_dir=DATA_DIR, out_dir=OUT_DIR, config_dir=CONFIG_DIR) -> FastAPI:
    app = FastAPI(title="retailagent API", version="1.0")
    app.add_middleware(CORSMiddleware, allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
                       allow_methods=["*"], allow_headers=["*"])
    stare = Stare(data_dir, out_dir, config_dir)
    app.state.stare = stare

    @app.get("/api/metrici/context")
    def context():
        d = stare.data
        return {"azi": d["azi"], "clienti": d["clienti"], "p_tinta": d["p_tinta"], "model_churn": d.get("model_churn"),
                "total_cazuri": d["total_cazuri"]}

    @app.get("/api/cazuri")
    def cazuri():
        return stare.data["cazuri"]

    @app.get("/api/cazuri/{case_id}")
    def caz(case_id: str):
        c = stare.cazuri.get(case_id)
        if c is None:
            raise HTTPException(404, f"cazul {case_id} nu există")
        return c

    @app.get("/api/metrici")
    def metrici():
        return stare.data["metrici"]

    @app.post("/api/cazuri/{case_id}/decizie")
    def decizie(case_id: str, d: DecizieInput):
        if case_id not in stare.recs:
            raise HTTPException(404, f"cazul {case_id} nu există")
        try:
            rec = decide(stare.recs[case_id], stare.offers[case_id], d.decizie, d.interventie, d.motiv, stare.full.cfg,
                         datetime.now(), stare.data_dir)
        except ApprovalError as e:
            raise HTTPException(400, str(e)) from e
        persist(rec, stare.out_dir)
        return {"decizie": d.decizie, "interventie": rec["interventie_finala"], "motiv": rec["motiv"], "case_id": case_id,
                "la": rec["timestamp"], "sursa": "api", "override": rec["override"], "oferta": rec["oferta"],
                "documente_lipsa": rec["documente_lipsa"]}

    @app.get("/api/decizii")
    def decizii():
        p = stare.out_dir / "approvals.json"
        return read_json(p) if p.exists() else []

    @app.post("/api/rescan")
    def rescan():
        stare.refresh()
        return {"cazuri": stare.data["total_cazuri"], "azi": stare.data["azi"]}

    return app


ROOT = Path(__file__).resolve().parents[1]


def _resolve(p: str | Path) -> Path:
    """Căile implicite (data/, out/, config/) sunt relative la rădăcina proiectului, oriunde ar fi pornit uvicorn."""
    p = Path(p)
    return p if p.is_absolute() or p.exists() else ROOT / p


app = create_app(_resolve(os.environ.get("RETAILAGENT_DATA", DATA_DIR)), _resolve(os.environ.get("RETAILAGENT_OUT", OUT_DIR)),
                 _resolve(os.environ.get("RETAILAGENT_CONFIG", CONFIG_DIR)))
