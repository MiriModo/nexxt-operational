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
from collections import Counter
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


def compact_caz(c: dict) -> dict:
    """Aceeași formă ca un caz complet (contractul UI), dar fără listele mari — pentru coadă și pagina de start."""
    o, ch, r = c["offer"], c["check"], c["rec"]
    return {
        "case": c["case"], "client": c["client"], "loan": c["loan"],
        "check": {"motive": ch["motive"], "plan": [], "omise": [], "rezultate": [], "oprit_la": ch["oprit_la"],
                  "verificare_picata": ch["verificare_picata"], "interogari": ch["interogari"], "concluzii": ch["concluzii"]},
        "offer": {**{k: o[k] for k in ("B", "B_detalii", "p", "p_tinta", "V", "legaturi", "semnale_active", "aleasa",
                                        "motiv_alegere", "explicatie", "model")}, "interventii": [], "contributii": None},
        "rec": {**{k: r[k] for k in ("recomandare", "eticheta", "interventie", "motiv", "oferta", "documente_lipsa")},
                "grafic": None, "explicatie": ""},
        "compact": True,
    }


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
    """Fluxul se rulează la pornirea serverului (lifespan), nu la import: `import retailagent.api` nu citește date."""
    from contextlib import asynccontextmanager

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        app.state.stare = Stare(data_dir, out_dir, config_dir)
        yield

    app = FastAPI(title="retailagent API", version="1.0", lifespan=lifespan)
    app.add_middleware(CORSMiddleware, allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
                       allow_methods=["*"], allow_headers=["*"])

    class _Lazy:
        """Acces la starea încărcată în lifespan (TestClient o pornește cu `with TestClient(app)`)."""
        def __getattr__(self, name):
            return getattr(app.state.stare, name)

    stare = _Lazy()

    @app.get("/api/metrici/context")
    def context():
        d = stare.data
        return {"azi": d["azi"], "clienti": d["clienti"], "p_tinta": d["p_tinta"], "model_churn": d.get("model_churn"),
                "total_cazuri": d["total_cazuri"]}

    @app.get("/api/cazuri")
    def cazuri(limit: int = 500, compact: bool = True, banda: str | None = None, q: str | None = None):
        """Coada, în ordinea priorității. Implicit compactă (fără verificări detaliate, meniu, grafic): la 10.000 de
        clienți lista completă ar avea ~60 MB; detaliul unui caz vine din GET /api/cazuri/{id}."""
        rows = stare.data["cazuri"]
        if banda:
            rows = [c for c in rows if c["case"]["banda"] == banda]
        if q:
            ql = q.lower()
            rows = [c for c in rows if ql in f"{c['case']['case_id']} {c['case']['client_id']} {c['client']['nume']} "
                                           f"{c['case']['produs']} {c['rec']['recomandare']}".lower()]
        if limit:
            rows = rows[:limit]
        return [compact_caz(c) for c in rows] if compact else rows

    def _decise() -> dict[str, dict]:
        p = stare.out_dir / "approvals.json"
        out: dict[str, dict] = {}
        for d in (read_json(p) if p.exists() else []):
            out[d["case_id"]] = d                                   # ultima decizie per caz
        return out

    @app.get("/api/coada")
    def coada(limit: int = 60, offset: int = 0, banda: str | None = None, q: str | None = None,
              sort: str = "prioritate", ascunde_decise: bool = False):
        """Pagina de coadă: filtre + sortare + paginare pe server (UI-ul nu încarcă toate cazurile)."""
        rows = stare.data["cazuri"]
        benzi = set(banda.split(",")) if banda else None
        decise = _decise() if ascunde_decise else {}
        if benzi:
            rows = [c for c in rows if c["case"]["banda"] in benzi]
        if ascunde_decise:
            rows = [c for c in rows if c["case"]["case_id"] not in decise]
        if q:
            ql = q.lower()
            rows = [c for c in rows if ql in " ".join([c["case"]["case_id"], c["case"]["client_id"], c["client"]["nume"], c["case"]["produs"] or "",
                                                       c["case"]["actiune_propusa"], c["rec"]["recomandare"], *c["case"]["motive_top3"]]).lower()]
        if sort == "termen":
            rows = sorted(rows, key=lambda c: (c["case"]["deadline"], -c["case"]["scoruri"]["prioritate"]))
        elif sort == "client":
            rows = sorted(rows, key=lambda c: c["client"]["nume"])
        return {"total": len(rows), "offset": offset, "limit": limit,
                "pe_banda": dict(Counter(c["case"]["banda"] for c in rows)),
                "items": [compact_caz(c) for c in rows[offset:offset + limit]]}

    @app.get("/api/cazuri/sumar")
    def sumar():
        """Contoarele paginii de start, pe toată coada: deschise, cu termen azi, blocate, decise, primele 5."""
        rows = stare.data["cazuri"]
        azi = stare.data["azi"]
        decise = _decise()
        deschise = [c for c in rows if c["case"]["case_id"] not in decise]
        primele = sorted(deschise, key=lambda c: (c["case"]["deadline"], -c["case"]["scoruri"]["prioritate"]))[:5]
        return {"total": len(rows), "deschise": len(deschise), "p1": sum(1 for c in deschise if c["case"]["banda"] == "P1"),
                "scadente_azi": sum(1 for c in deschise if c["case"]["deadline"] <= azi),
                "blocate": sum(1 for c in deschise if c["case"]["blocaje"] or c["rec"]["recomandare"] == "blocat"),
                "decise": len(rows) - len(deschise), "pe_banda": dict(Counter(c["case"]["banda"] for c in rows)),
                "primele": [compact_caz(c) for c in primele]}

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
