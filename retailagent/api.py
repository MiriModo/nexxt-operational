"""API-ul interfeței (FastAPI): strat subțire peste funcțiile pure, pe contractul din ui/src/types/api.ts.

    uvicorn retailagent.api:app --reload --port 8000          # apoi: cd ui && npm run dev (proxy /api → 8000)

    POST /api/login                  {utilizator, parola} → {token, utilizator}; apoi Authorization: Bearer <token>
    GET  /api/utilizatori            conturile pentru login (fără parole); GET /api/eu, GET /api/eu/birou (biroul consilierului)
    GET  /api/metrici/context        {azi, clienti, p_tinta, versiune, buget_portofoliu}  (public)
    GET  /api/coada, /api/cazuri     coada utilizatorului: toată pentru admin, doar cazurile alocate pentru consilier
    GET  /api/cazuri/{id}            un caz (403 dacă nu e al tău)
    GET  /api/metrici, /api/model    rezultatele agentului (admin)
    POST /api/cazuri/{id}/propunere  agentul LLM: alege oferta în constrângeri + textul (llm.genereaza); ?nou=true regenerează
    GET  /api/llm/stare              agentul LLM e activ (cheie + llm.yaml) sau pe șablon
    POST /api/cazuri/{id}/decizie    {decizie, interventie?, motiv?, propunere_id?} → approve.decide + persist; consilierul = cel autentificat
    GET  /api/decizii, /api/feedback deciziile / raportul utilizatorului (toate pentru admin)
    GET/PUT /api/config/{nume}, POST /api/rescan   motorul de reguli (admin)

Fluxul rulează o dată la pornire și stă în memorie; deciziile se scriu pe disc exact ca din CLI.
"""
from __future__ import annotations

import os
from collections import Counter
from datetime import datetime, timedelta
from pathlib import Path
from typing import Literal

import secrets
from uuid import uuid4

from fastapi import Depends, FastAPI, Header, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from .approve import ApprovalError, decide, inregistreaza_rezultat, persist
from .common import CONFIG_DIR, DATA_DIR, OUT_DIR, read_json
from .demo import build_data
from .llm import genereaza, stare_llm
from .pipeline import run_full


class DecizieInput(BaseModel):
    decizie: Literal["aproba", "modifica", "respinge"]
    interventie: str | None = None
    motiv: str | None = None
    consilier: str | None = None
    propunere_id: str | None = None        # propunerea agentului LLM pe care se bazează decizia (intră în audit)


class RezultatInput(BaseModel):
    rezultat: Literal["ramas", "plecat"]


class ConfigInput(BaseModel):
    text: str


class LoginInput(BaseModel):
    utilizator: str
    parola: str


# Conturi: consilierii (cu parola de demo) vin din config/echipa.yaml; administratorul are parola din mediu
# (RETAILAGENT_ADMIN_PAROLA; implicit `admin` pentru demo). Sesiunile stau în memorie, cu expirare.
ADMIN_PAROLA = os.environ.get("RETAILAGENT_ADMIN_PAROLA", "admin")
ADMIN = {"id": "admin", "nume": "Administrator", "rol": "admin"}
SESIUNE_ORE = 8


def compact_caz(c: dict) -> dict:
    """Aceeași formă ca un caz complet (contractul UI), dar fără listele mari — pentru coadă și pagina de start."""
    o, ch, r = c["offer"], c["check"], c["rec"]
    return {
        "case": c["case"], "client": c["client"], "loan": c["loan"], "consilier": c.get("consilier"), "versiune": c.get("versiune"),
        "check": {"motive": ch["motive"], "plan": [], "omise": [], "rezultate": [], "oprit_la": ch["oprit_la"],
                  "verificare_picata": ch["verificare_picata"], "interogari": ch["interogari"], "concluzii": ch["concluzii"]},
        "offer": {**{k: o[k] for k in ("B", "B_detalii", "p", "p_tinta", "V", "legaturi", "semnale_active", "aleasa",
                                        "motiv_alegere", "explicatie", "model")}, "interventii": [], "contributii": None},
        "rec": {**{k: r[k] for k in ("recomandare", "eticheta", "interventie", "motiv", "oferta", "documente_lipsa")},
                "incertitudini": r.get("incertitudini", []), "buget": r.get("buget"), "grafic": None, "explicatie": ""},
        "compact": True,
    }


class Stare:
    def __init__(self, data_dir, out_dir, config_dir):
        self.data_dir, self.out_dir, self.config_dir = Path(data_dir), Path(out_dir), Path(config_dir)
        self.sesiuni: dict[str, dict] = {}                      # token → {id, nume, rol, expira}
        self.refresh()

    def refresh(self) -> None:
        self.propuneri: dict[str, dict] = {}                    # id → propunerea LLM; expiră la reîncărcarea fluxului
        self.propunere_caz: dict[str, str] = {}                 # case_id → id-ul ultimei propuneri (cache)
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

    # ---- conturi și roluri: serverul filtrează după cine ești, interfața doar reflectă
    def utilizatori_cunoscuti() -> list[dict]:
        cons = [{"id": c.id, "nume": c.nume, "rol": "consilier"} for c in stare.full.cfg.echipa.consilieri]
        return [*cons, ADMIN]

    def utilizator_curent(authorization: str | None = Header(default=None)) -> dict:
        tok = authorization.removeprefix("Bearer ").strip() if authorization else ""
        s = stare.sesiuni.get(tok)
        if not s or s["expira"] < datetime.now():
            stare.sesiuni.pop(tok, None)
            raise HTTPException(401, "nu ești autentificat sau sesiunea a expirat")
        return s

    def doar_admin(eu: dict = Depends(utilizator_curent)) -> dict:
        if eu["rol"] != "admin":
            raise HTTPException(403, "doar administratorul poate face asta")
        return eu

    def ale_mele(rows: list[dict], eu: dict) -> list[dict]:
        """Cazurile pe care le vede utilizatorul: toate pentru admin, doar cele alocate lui pentru consilier."""
        return rows if eu["rol"] == "admin" else [c for c in rows if c.get("consilier") == eu["id"]]

    def al_meu(case_id: str, eu: dict) -> dict:
        c = stare.cazuri.get(case_id)
        if c is None:
            raise HTTPException(404, f"cazul {case_id} nu există")
        if eu["rol"] != "admin" and c.get("consilier") != eu["id"]:
            raise HTTPException(403, f"cazul {case_id} nu e în coada ta")
        return c

    def aprobarile(eu: dict) -> list[dict]:
        p = stare.out_dir / "approvals.json"
        rows = read_json(p) if p.exists() else []
        return rows if eu["rol"] == "admin" else [d for d in rows if d.get("consilier") == eu["id"]]

    @app.get("/api/utilizatori")
    def utilizatori():
        """Lista de conturi pentru ecranul de login (fără parole)."""
        return utilizatori_cunoscuti()

    @app.post("/api/login")
    def login(body: LoginInput):
        u = next((x for x in utilizatori_cunoscuti() if x["id"] == body.utilizator), None)
        if u is None:
            raise HTTPException(401, "utilizator necunoscut")
        if u["rol"] == "admin":
            asteptata = ADMIN_PAROLA
        else:
            asteptata = next(c.parola for c in stare.full.cfg.echipa.consilieri if c.id == u["id"]) or ""
        if not asteptata or not secrets.compare_digest(body.parola, asteptata):
            raise HTTPException(401, "parolă greșită")
        tok = secrets.token_urlsafe(24)
        stare.sesiuni[tok] = {**u, "expira": datetime.now() + timedelta(hours=SESIUNE_ORE)}
        return {"token": tok, "utilizator": u}

    @app.post("/api/logout")
    def logout(authorization: str | None = Header(default=None)):
        stare.sesiuni.pop(authorization.removeprefix("Bearer ").strip() if authorization else "", None)
        return {"ok": True}

    @app.get("/api/eu")
    def eu_(eu: dict = Depends(utilizator_curent)):
        return {k: eu[k] for k in ("id", "nume", "rol")}

    @app.get("/api/eu/birou")
    def birou(eu: dict = Depends(utilizator_curent)):
        """Biroul consilierului: briefing-ul cozii lui + activitatea lui (decizii, override, rezultate la 90 de zile)."""
        rows = ale_mele(stare.data["cazuri"], eu)
        azi = stare.data["azi"]
        decise = {d["case_id"]: d for d in aprobarile(eu)}
        deschise = [c for c in rows if c["case"]["case_id"] not in decise]
        primele = sorted(deschise, key=lambda c: (c["case"]["deadline"], -c["case"]["scoruri"]["prioritate"]))[:5]
        dec = aprobarile(eu)
        cu_rez = [d for d in dec if d.get("rezultat")]
        return {
            "utilizator": {k: eu[k] for k in ("id", "nume", "rol")},
            "coada": {"total": len(rows), "deschise": len(deschise),
                      "p1_azi": sum(1 for c in deschise if c["case"]["banda"] == "P1" and c["case"]["deadline"] <= azi),
                      "peste_plafon": sum(1 for c in deschise if (c["rec"].get("oferta") or {}).get("amanata_buget")),
                      "de_confirmat": sum(1 for c in deschise if c["rec"].get("incertitudini")),
                      "pe_banda": dict(Counter(c["case"]["banda"] for c in deschise)),
                      "distributie": dict(Counter(c["rec"]["recomandare"] for c in rows))},
            "activitate": {"decizii": len(dec), "decizii_azi": sum(1 for d in dec if d["timestamp"][:10] == datetime.now().strftime("%Y-%m-%d")),
                           "override": sum(1 for d in dec if d.get("override")),
                           "rezultate": {"n": len(cu_rez), "ramasi": sum(1 for d in cu_rez if d["rezultat"] == "ramas"),
                                         "plecati": sum(1 for d in cu_rez if d["rezultat"] == "plecat")},
                           "ultimele": dec[-5:][::-1]},
            "primele": [compact_caz(c) for c in primele],
        }

    @app.get("/api/metrici/context")
    def context():
        d = stare.data
        from .versiune import versiune_completa
        return {"azi": d["azi"], "clienti": d["clienti"], "p_tinta": d["p_tinta"], "model_churn": d.get("model_churn"),
                "total_cazuri": d["total_cazuri"], "versiune": versiune_completa(stare.full.cfg, stare.config_dir),
                "buget_portofoliu": stare.full.buget}

    @app.get("/api/cazuri")
    def cazuri(limit: int = 500, compact: bool = True, banda: str | None = None, q: str | None = None,
               eu: dict = Depends(utilizator_curent)):
        """Coada, în ordinea priorității. Implicit compactă (fără verificări detaliate, meniu, grafic): la 10.000 de
        clienți lista completă ar avea ~60 MB; detaliul unui caz vine din GET /api/cazuri/{id}."""
        rows = ale_mele(stare.data["cazuri"], eu)
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
              sort: str = "prioritate", ascunde_decise: bool = False, recomandare: str | None = None,
              consilier: str | None = None, doar: str | None = None, eu: dict = Depends(utilizator_curent)):
        """Pagina de coadă: filtre + sortare + paginare pe server (UI-ul nu încarcă toate cazurile).
        `doar` = una din listele briefing-ului: termen_azi | peste_plafon | de_confirmat."""
        rows = ale_mele(stare.data["cazuri"], eu)
        benzi = set(banda.split(",")) if banda else None
        decise = _decise() if ascunde_decise else {}
        if benzi:
            rows = [c for c in rows if c["case"]["banda"] in benzi]
        if doar == "termen_azi":
            azi = stare.data["azi"]
            rows = [c for c in rows if c["case"]["deadline"] <= azi]
        elif doar == "peste_plafon":
            rows = [c for c in rows if (c["rec"].get("oferta") or {}).get("amanata_buget")]
        elif doar == "de_confirmat":
            rows = [c for c in rows if c["rec"].get("incertitudini")]
        if recomandare:
            rec_set = set(recomandare.split(","))
            rows = [c for c in rows if c["rec"]["recomandare"] in rec_set]
        if consilier:
            rows = [c for c in rows if c.get("consilier") == consilier]
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
    def sumar(eu: dict = Depends(utilizator_curent)):
        """Contoarele paginii de start (briefing-ul), pe coada utilizatorului: deschise, P1 cu termen azi,
        oferte amânate peste plafon, cazuri cu ceva de confirmat, blocate, decise, primele 5."""
        rows = ale_mele(stare.data["cazuri"], eu)
        azi = stare.data["azi"]
        decise = _decise()
        deschise = [c for c in rows if c["case"]["case_id"] not in decise]
        primele = sorted(deschise, key=lambda c: (c["case"]["deadline"], -c["case"]["scoruri"]["prioritate"]))[:5]
        return {"total": len(rows), "deschise": len(deschise), "p1": sum(1 for c in deschise if c["case"]["banda"] == "P1"),
                "scadente_azi": sum(1 for c in deschise if c["case"]["deadline"] <= azi),
                "p1_azi": sum(1 for c in deschise if c["case"]["banda"] == "P1" and c["case"]["deadline"] <= azi),
                "peste_plafon": sum(1 for c in deschise if (c["rec"].get("oferta") or {}).get("amanata_buget")),
                "de_confirmat": sum(1 for c in deschise if c["rec"].get("incertitudini")),
                "blocate": sum(1 for c in deschise if c["case"]["blocaje"] or c["rec"]["recomandare"] == "blocat"),
                "decise": len(rows) - len(deschise), "pe_banda": dict(Counter(c["case"]["banda"] for c in rows)),
                "primele": [compact_caz(c) for c in primele]}

    @app.get("/api/cazuri/{case_id}")
    def caz(case_id: str, eu: dict = Depends(utilizator_curent)):
        return al_meu(case_id, eu)

    @app.get("/api/metrici", dependencies=[Depends(doar_admin)])
    def metrici():
        return stare.data["metrici"]

    @app.get("/api/llm/stare")
    def llm_stare(eu: dict = Depends(utilizator_curent)):
        """Agentul LLM e activ (cheie + llm.yaml) sau lucrează pe șablon; nu expune niciodată cheia."""
        return stare_llm(stare.full.cfg.llm)

    @app.post("/api/cazuri/{case_id}/propunere")
    def propunere(case_id: str, nou: bool = False, eu: dict = Depends(utilizator_curent)):
        """Agentul LLM (pasul 3): alege oferta dintre opțiunile admisibile ale motorului și scrie argumentul pentru
        consilier + mesajul pentru client, validate față de faptele calculate. Fără cheie sau la eroare: șablonul.
        Propunerea se păstrează per caz până la reîncărcarea fluxului; `?nou=true` cere una nouă."""
        c = al_meu(case_id, eu)
        vechi = stare.propunere_caz.get(case_id)
        if vechi and not nou and vechi in stare.propuneri:
            return stare.propuneri[vechi]
        result = genereaza(c, stare.offers.get(case_id), stare.full.pf, stare.full.cfg)
        result = {**result, "id": str(uuid4()), "case_id": case_id, "generat_la": datetime.now().isoformat(timespec="seconds")}
        stare.propuneri[result["id"]] = result
        stare.propunere_caz[case_id] = result["id"]
        return result

    @app.post("/api/cazuri/{case_id}/decizie")
    def decizie(case_id: str, d: DecizieInput, eu: dict = Depends(utilizator_curent)):
        """Decizia poartă consilierul autentificat; doar administratorul poate decide în numele altcuiva."""
        al_meu(case_id, eu)
        suggestion = None
        if d.propunere_id:
            suggestion = stare.propuneri.get(d.propunere_id)
            if suggestion is None or suggestion["case_id"] != case_id:
                raise HTTPException(400, "Propunerea LLM a expirat. Generează din nou.")
            final = d.interventie if d.decizie == "modifica" else stare.recs[case_id]["interventie"]
            if d.decizie == "respinge" or suggestion["interventie"] != final:
                raise HTTPException(400, "Propunerea LLM nu corespunde intervenției alese.")
        consilier = d.consilier if eu["rol"] == "admin" else eu["id"]
        try:
            rec = decide(stare.recs[case_id], stare.offers[case_id], d.decizie, d.interventie, d.motiv, stare.full.cfg,
                         datetime.now(), stare.data_dir, consilier)
        except ApprovalError as e:
            raise HTTPException(400, str(e)) from e
        if suggestion:
            rec["propunere_llm"] = suggestion
        persist(rec, stare.out_dir)
        return {"decizie": d.decizie, "interventie": rec["interventie_finala"], "motiv": rec["motiv"], "case_id": case_id,
                "la": rec["timestamp"], "sursa": "api", "override": rec["override"], "oferta": rec["oferta"],
                "documente_lipsa": rec["documente_lipsa"], "consilier": rec["consilier"], "versiune": rec.get("versiune")}

    @app.get("/api/decizii")
    def decizii(eu: dict = Depends(utilizator_curent)):
        return aprobarile(eu)

    @app.get("/api/cazuri/{case_id}/decizii")
    def decizii_caz(case_id: str, eu: dict = Depends(utilizator_curent)):
        """Istoricul deciziilor (aprobări, override-uri, rezultate) ale unui caz, cronologic."""
        al_meu(case_id, eu)
        p = stare.out_dir / "approvals.json"
        return [d for d in (read_json(p) if p.exists() else []) if d["case_id"] == case_id]

    @app.post("/api/cazuri/{case_id}/rezultat")
    def rezultat(case_id: str, r: RezultatInput, eu: dict = Depends(utilizator_curent)):
        al_meu(case_id, eu)
        try:
            return inregistreaza_rezultat(case_id, r.rezultat, datetime.now(), stare.out_dir)
        except ApprovalError as e:
            raise HTTPException(400, str(e)) from e

    @app.get("/api/feedback")
    def feedback(eu: dict = Depends(utilizator_curent)):
        """Raportul de feedback: pe toate deciziile pentru admin, doar pe ale lui pentru consilier."""
        from .feedback import raport_feedback
        return raport_feedback(aprobarile(eu), stare.full.recs, stare.full.offers)

    @app.get("/api/echipa")
    def echipa(eu: dict = Depends(utilizator_curent)):
        return {"consilieri": [c.model_dump(exclude={"parola"}) for c in stare.full.cfg.echipa.consilieri],
                "alocare": stare.full.cfg.echipa.alocare}

    @app.post("/api/cazuri/{case_id}/verifica")
    def verifica(case_id: str, eu: dict = Depends(utilizator_curent)):
        """Reia doar verificările acestui caz (plan după produse + motiv, apoi treptele în ordine) și întoarce rezultatele
        treaptă cu treaptă — UI-ul le afișează „în timp real"."""
        from .checks import build_context, plan_checks, run_checks
        al_meu(case_id, eu)
        case = next((c for c in stare.full.res.cases if c["case_id"] == case_id), None)
        if case is None:
            raise HTTPException(404, f"cazul {case_id} nu există")
        full = stare.full
        ci = full.res.inputs[case_id]
        plan = plan_checks(case, ci.client, full.pf.loans_by_client.get(case["client_id"], []), ci.cereri, full.cfg)
        ctx = build_context(full.pf, full.mocks, full.cfg, case, ci.cereri, [m["motiv"] for m in plan["motive"]])
        r = run_checks(plan, ctx)
        trepte = []
        for t in full.cfg.checks.trepte:
            rez = [x for x in r["rezultate"] if x["treapta"] == t]
            if not rez:
                continue
            stare_t = "oprita" if r["oprit_la"] == t else ("neexecutata" if all(x["status"] == "neexecutat" for x in rez) else "executata")
            trepte.append({"treapta": t, "stare": stare_t, "rezultate": rez})
        return {"case_id": case_id, "motive": r["motive"], "plan": r["plan"], "omise": r["omise"], "trepte": trepte,
                "oprit_la": r["oprit_la"], "verificare_picata": r["verificare_picata"], "incertitudini": r["incertitudini"],
                "concluzii": r["concluzii"], "interogari_externe": r["interogari_externe"]}

    @app.get("/api/model", dependencies=[Depends(doar_admin)])
    def model():
        """Metadatele modelului de churn (metrici, calibrare, coeficienți) pentru Dashboard."""
        from .versiune import versiune_model
        ch = stare.full.cfg.retention.churn
        meta_p = _resolve(ch.cale).with_suffix(".json")
        meta = read_json(meta_p) if meta_p.exists() else {}
        return {"activ": versiune_model(stare.full.cfg), "antrenat": meta}

    # ---- motorul de reguli (administrator): editare YAML cu validare pe server, apoi re-rulare
    EDITABILE = ("priority", "retention", "constraints", "checks", "signals", "portofoliu", "echipa", "llm")
    admin = doar_admin

    @app.get("/api/config", dependencies=[Depends(admin)])
    def config_lista():
        from .versiune import versiune_config
        v = versiune_config(stare.config_dir)
        return [{"nume": n, "fisier": f"{n}.yaml", "hash": v["fisiere"].get(f"{n}.yaml"),
                 "exista": (stare.config_dir / f"{n}.yaml").exists()} for n in EDITABILE]

    @app.get("/api/config/{nume}", dependencies=[Depends(admin)])
    def config_citeste(nume: str):
        if nume not in EDITABILE:
            raise HTTPException(404, f"configurația {nume!r} nu e editabilă: {EDITABILE}")
        p = stare.config_dir / f"{nume}.yaml"
        if not p.exists():
            raise HTTPException(404, f"{p} lipsește")
        return {"nume": nume, "text": p.read_text(encoding="utf-8")}

    @app.put("/api/config/{nume}", dependencies=[Depends(admin)])
    def config_scrie(nume: str, body: ConfigInput):
        """Validează noul YAML cu aceleași modele pydantic ca la încărcare (pe o copie), apoi îl scrie. 400 = invalid."""
        import shutil
        import tempfile

        import yaml
        from .config_loader import load_config
        from .profil import load_profil
        if nume not in EDITABILE:
            raise HTTPException(404, f"configurația {nume!r} nu e editabilă")
        try:
            yaml.safe_load(body.text)
        except yaml.YAMLError as e:
            raise HTTPException(400, f"YAML invalid: {e}") from e
        with tempfile.TemporaryDirectory() as tmp:
            d = Path(tmp) / "config"
            shutil.copytree(stare.config_dir, d)
            (d / f"{nume}.yaml").write_text(body.text, encoding="utf-8")
            try:
                if nume == "portofoliu":
                    load_profil(d / "portofoliu.yaml")
                else:
                    load_config(d)
            except Exception as e:                      # pydantic / ValueError: mesajul e explicația pentru om
                raise HTTPException(400, f"configurație respinsă: {e}") from e
        (stare.config_dir / f"{nume}.yaml").write_text(body.text, encoding="utf-8")
        from .versiune import versiune_config
        return {"nume": nume, "salvat": True, "versiune": versiune_config(stare.config_dir)["hash"],
                "nota": "rulează POST /api/rescan ca schimbarea să intre în coadă"}

    @app.get("/api/config/{nume}/diff", dependencies=[Depends(admin)])
    def config_diff(nume: str):
        """Diferența față de versiunea din git (dacă proiectul e într-un repo)."""
        import subprocess
        if nume not in EDITABILE:
            raise HTTPException(404, f"configurația {nume!r} nu e editabilă")
        p = stare.config_dir / f"{nume}.yaml"
        try:
            out = subprocess.run(["git", "diff", "--", str(p)], capture_output=True, text=True, timeout=10, cwd=ROOT)
            return {"nume": nume, "diff": out.stdout, "git": out.returncode == 0}
        except (OSError, subprocess.SubprocessError):
            return {"nume": nume, "diff": "", "git": False}

    @app.post("/api/rescan", dependencies=[Depends(admin)])
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


def main(argv: list[str] | None = None) -> None:
    """`python -m retailagent.api [--port 8000] [--reload]` — pornește serverul fără să depindă de `uvicorn` în PATH."""
    import argparse

    import uvicorn

    from .common import setup_console
    setup_console()
    ap = argparse.ArgumentParser(description="API-ul interfeței retailagent (FastAPI + uvicorn).")
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=8000)
    ap.add_argument("--reload", action="store_true", help="repornește la modificări de cod (dezvoltare)")
    a = ap.parse_args(argv)
    print(f"retailagent API → http://{a.host}:{a.port}/docs  (încarcă fluxul la pornire: ~15–45 s pe 10.000 de clienți)")
    uvicorn.run("retailagent.api:app", host=a.host, port=a.port, reload=a.reload, app_dir=str(ROOT))


if __name__ == "__main__":
    main()
