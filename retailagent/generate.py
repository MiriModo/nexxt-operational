"""Generator de date sintetice: portofoliu retail cu semnale plantate și etalon (ground truth).

Portofoliul de bază are 50 de scenarii scrise explicit (SCENARIOS). Fiecare scenariu fixează
tipologia, nivelul relației, creditele, semnalele plantate, cererile și rezultatul așteptat în coadă
(banda + acțiunea). Restul (nume, sume, tranzacții) e aleatoriu cu seed fix, în intervale care nu
declanșează semnale neplantate. Pentru --n > 50 scenariile se repetă în blocuri de câte 50.

    python -m retailagent.generate --n 50 --seed 42
"""
from __future__ import annotations

import argparse
import random
from dataclasses import dataclass, field
from datetime import date, timedelta
from pathlib import Path

from .common import (
    DATA_DIR, DEFAULT_TODAY, add_years, last_months, log_event, month_key, setup_console, shift_month,
    write_json, OUT_DIR,
)

# ---------------------------------------------------------------- parametri de piață

MARKET = {"ircc": 5.55, "dobanda_fixa_piata_ipotecar": 4.90, "dobanda_piata_nevoi_personale": 8.90,
          "dobanda_piata_card": 22.0}

TIPOLOGIE = {"SL": "salariat", "SE": "salariat", "IND": "independent", "PEN": "pensionar",
             "ANT": "antreprenor", "DIA": "diaspora", "TAN": "tanar_fara_istoric"}


# ---------------------------------------------------------------- descrierea scenariilor

@dataclass
class L:
    """Specificația unui credit dintr-un scenariu. Câmpurile None se completează aleatoriu."""
    produs: str
    rata: str | None = None            # fixa | variabila
    exp_zile: int | None = None        # PLANTAT: zile până la expirarea dobânzii fixe
    sold: float | None = None
    ani_ramasi: float | None = None
    ani_vechime: float | None = None
    suma: float | None = None
    marja: float | None = None
    intarziere: int | None = None      # PLANTAT: zile de întârziere în ultima lună
    card_stres: bool = False           # PLANTAT
    ltv_depasit: bool = False          # PLANTAT
    asigurare: bool = False            # PLANTAT: asigurare care expiră în < 30 zile
    restructurat: bool = False         # PLANTAT


@dataclass
class R:
    """Cerere a clientului: tip, produs vizat, acum câte zile, sumă."""
    tip: str
    produs: str | None
    zile_in_urma: int
    suma: float | None = None


@dataclass
class S:
    typ: str
    tier: str
    loans: list[L]
    plant: dict = field(default_factory=dict)
    req: list[R] = field(default_factory=list)
    exp: tuple[str, str] | None = None     # (banda așteptată, acțiune așteptată); None = nu apare în coadă
    produse: int | None = None             # nr. produse atașate (non-credit)
    ani_client: float | None = None        # vechimea relației (implicit aleatoare)
    nota: str = ""


P1R = ("P1", "restructurare_preventiva")

SCENARIOS: list[S] = [
    # 01–08 · expirarea dobânzii fixe la 15/45/75/120 zile
    S("SL", "gold", [L("ipotecar", "fixa", exp_zile=15, sold=400_000, ani_ramasi=22, marja=2.5), L("card_credit")],
      exp=("P1", "retentie_refinantare"), produse=3),
    S("SL", "standard", [L("ipotecar", "fixa", exp_zile=14, sold=260_000, ani_ramasi=20, intarziere=12)],
      exp=P1R, produse=2, nota="capcana_a"),
    S("SL", "gold", [L("ipotecar", "fixa", exp_zile=45, sold=400_000, ani_ramasi=22, marja=2.5)],
      req=[R("adeverinta_sold", "ipotecar", 9)], exp=("P1", "retentie_refinantare"), produse=3, nota="capcana_e"),
    S("SE", "standard", [L("nevoi_personale", "fixa", exp_zile=44, sold=12_000, ani_ramasi=1, suma=60_000, marja=4.0)],
      plant={"rata_alt": "nou"}, req=[R("simulare_rambursare_anticipata", "nevoi_personale", 6, 12_000)],
      exp=("P3", "monitorizare"), produse=1, nota="capcana_b"),
    S("SL", "platinum", [L("ipotecar", "fixa", exp_zile=75, sold=750_000, ani_ramasi=25, suma=900_000, marja=2.5),
                         L("card_credit")],
      plant={"rata_alt": "vechi"}, exp=("P2", "retentie_refinantare"), produse=4),
    S("IND", "standard", [L("nevoi_personale", "fixa", exp_zile=76, sold=40_000, ani_ramasi=4)],
      exp=("P3", "monitorizare"), produse=1),
    S("PEN", "standard", [L("imobiliar", "fixa", exp_zile=120, sold=150_000, ani_ramasi=12, marja=2.6)],
      exp=("P3", "monitorizare"), produse=1),
    S("SE", "gold", [L("imobiliar", "fixa", exp_zile=121, sold=220_000, ani_ramasi=18, marja=2.5)],
      exp=("P3", "monitorizare"), produse=2),
    # 09–11 · rate la alți creditori plătite din contul nostru
    S("SE", "standard", [L("card_credit")], plant={"rata_alt": "nou"}, exp=("P3", "monitorizare"), produse=1),
    S("IND", "standard", [L("nevoi_personale", "variabila")], plant={"rata_alt": "vechi"},
      exp=("P3", "monitorizare"), produse=1),
    S("ANT", "gold", [L("card_credit"), L("nevoi_personale")], plant={"rata_alt": "vechi"},
      exp=("P3", "monitorizare"), produse=2),
    # 12–15 · salariul nu mai intră (salariu_mutat + venit_disparut)
    S("SL", "standard", [L("ipotecar", "variabila")], plant={"salariu_mutat": True}, exp=P1R),
    S("SL", "gold", [L("nevoi_personale"), L("ipotecar", "variabila")], plant={"salariu_mutat": "alta_banca"},
      exp=("P1", "retentie_refinantare"), nota="salariul vine la altă bancă; ratele le acoperă din contul de acolo"),
    S("SL", "standard", [L("card_credit"), L("imobiliar", "variabila")],
      plant={"salariu_mutat": "alta_banca", "cont_nefolosit": True}, exp=("P1", "retentie_refinantare"),
      produse=1, ani_client=1.5, nota="cazul opus lui 13: salariu mutat, fără legături (standard, 1 produs, cont nefolosit)"),
    S("SL", "standard", [L("refinantare"), L("ipotecar", "fixa")], plant={"salariu_mutat": True}, exp=P1R),
    # 16 · cerere de adeverință de sold
    S("SE", "platinum", [L("ipotecar", "variabila", sold=600_000, ani_ramasi=23, suma=750_000, marja=2.6, ani_vechime=8)],
      req=[R("adeverinta_sold", "ipotecar", 20)], exp=("P1", "retentie_refinantare"), produse=4),
    # 17 · capcana d: CI expirată + cerere de refinanțare
    S("SL", "standard", [L("nevoi_personale")], plant={"ci": True}, req=[R("refinantare", "nevoi_personale", 5, 35_000)],
      exp=("P1", "task_ci_expirata"), produse=2, nota="capcana_d"),
    # 18–20 · întârzieri noi
    S("SL", "standard", [L("ipotecar", "variabila", intarziere=12), L("card_credit")], exp=P1R),
    S("SE", "standard", [L("nevoi_personale", intarziere=35), L("ipotecar", "variabila")], exp=P1R),
    S("IND", "standard", [L("nevoi_personale", intarziere=8), L("card_credit")],
      req=[R("restructurare", "nevoi_personale", 3)], exp=P1R),
    # 21–24 · venit în scădere
    S("SL", "standard", [L("refinantare"), L("ipotecar", "variabila")], plant={"venit_scadere": 0.70}, exp=P1R),
    S("SL", "gold", [L("ipotecar", "fixa"), L("card_credit")], plant={"venit_scadere": 0.50}, exp=P1R),
    S("SL", "standard", [L("ipotecar", "variabila"), L("nevoi_personale")], plant={"venit_scadere": 0.72}, exp=P1R),
    S("SL", "standard", [L("refinantare"), L("imobiliar", "variabila")], plant={"venit_scadere": 0.65}, exp=P1R),
    # 25–27 · card la limită cu plata minimă
    S("IND", "standard", [L("card_credit", card_stres=True), L("ipotecar", "variabila")], exp=P1R),
    S("SE", "standard", [L("card_credit", card_stres=True)], exp=P1R),
    S("PEN", "standard", [L("card_credit", card_stres=True), L("imobiliar", "fixa")], exp=P1R),
    # 28–29 · angajator în dificultate
    S("SL", "standard", [L("ipotecar", "variabila"), L("card_credit")], plant={"angajator": "insolventa"}, exp=P1R),
    S("SL", "gold", [L("refinantare"), L("ipotecar", "fixa")], plant={"angajator": "dizolvare"}, exp=P1R),
    # 30–31 · CI expirată
    S("PEN", "standard", [L("nevoi_personale")], plant={"ci": True}, exp=("P3", "task_ci_expirata"), produse=1),
    S("SE", "standard", [L("card_credit")], plant={"ci": True}, exp=("P3", "task_ci_expirata"), produse=1),
    # 32–33 · consimțământ lipsă
    S("IND", "standard", [L("card_credit")], plant={"consimtamant": "anaf"}, exp=("P3", "task_consimtamant_lipsa"), produse=1),
    S("SE", "standard", [L("nevoi_personale")], plant={"consimtamant": "bc"}, exp=("P3", "task_consimtamant_lipsa"), produse=1),
    # 34–35 · asigurarea garanției expiră
    S("SL", "standard", [L("ipotecar", "fixa", asigurare=True), L("card_credit")],
      exp=("P3", "task_asigurare_expirata"), produse=2),
    S("PEN", "standard", [L("imobiliar", "variabila", asigurare=True)], exp=("P3", "task_asigurare_expirata"), produse=1),
    # 36 · flag blocant (PEP)
    S("ANT", "gold", [L("card_credit")], plant={"flag": "pep"}, exp=("P3", "task_flag_blocant"), produse=2),
    # 37–38 · LTV depășit
    S("SE", "standard", [L("imobiliar", "variabila", ltv_depasit=True)], exp=P1R),
    S("IND", "standard", [L("ipotecar", "variabila", ltv_depasit=True)], exp=P1R),
    # 39–40 · KYC vechi
    S("PEN", "standard", [L("nevoi_personale")], plant={"kyc": True}, exp=("P3", "task_kyc_vechi"), produse=1),
    S("SE", "standard", [L("card_credit")], plant={"kyc": True}, exp=("P3", "task_kyc_vechi"), produse=1),
    # 41–42 · restructurare anterioară
    S("SL", "standard", [L("refinantare", restructurat=True)], exp=("P2", "monitorizare"), produse=2),
    S("IND", "standard", [L("nevoi_personale", restructurat=True)], exp=("P2", "monitorizare"), produse=1),
    # 43–44 · poprire activă
    S("SL", "standard", [L("ipotecar", "variabila"), L("card_credit")], plant={"poprire": True}, exp=P1R),
    S("ANT", "standard", [L("ipotecar", "fixa")], plant={"poprire": True}, exp=P1R),
    # 45–49 · cereri ale clienților
    S("TAN", "standard", [], req=[R("credit_nou", "nevoi_personale", 2, 30_000)], exp=("P2", "procesare_cerere"), produse=1),
    S("DIA", "gold", [L("ipotecar", "variabila")], req=[R("credit_nou", "nevoi_personale", 4, 50_000)],
      exp=("P2", "procesare_cerere"), produse=2),
    S("SL", "standard", [L("card_credit")], req=[R("majorare_limita_card", "card_credit", 1, 5_000)],
      exp=("P2", "procesare_cerere"), produse=2),
    S("PEN", "standard", [L("card_credit")], req=[R("actualizare_date", None, 3)], exp=("P3", "procesare_cerere"), produse=1),
    S("DIA", "gold", [L("ipotecar", "variabila", sold=250_000, ani_ramasi=18)],
      req=[R("simulare_rambursare_anticipata", "ipotecar", 7, 20_000)], exp=("P3", "monitorizare"), produse=2),
    # 50 · capcana c: platinum fără niciun semnal
    S("IND", "platinum", [L("ipotecar", "fixa")], exp=None, produse=4, nota="capcana_c"),
]

# index (0-based) al scenariilor-capcană în blocul de 50 — folosit de teste
TRAP_INDEX = {s.nota: i for i, s in enumerate(SCENARIOS) if s.nota.startswith("capcana")}

# ---------------------------------------------------------------- vocabular

PRENUME = ["Andrei", "Maria", "Ioana", "Mihai", "Elena", "Alexandru", "Ana", "Cristian", "Gabriela", "Bogdan",
           "Raluca", "Stefan", "Diana", "Vlad", "Irina", "Radu", "Oana", "Florin", "Simona", "Catalin",
           "Adriana", "Sorin", "Laura", "Marius", "Camelia", "Dan", "Roxana", "Ionut", "Alina", "George"]
NUME = ["Popescu", "Ionescu", "Pop", "Dumitru", "Stan", "Stoica", "Gheorghe", "Matei", "Ciobanu", "Rusu",
        "Munteanu", "Constantin", "Marin", "Tudor", "Dobre", "Barbu", "Nistor", "Florea", "Ene", "Dinu",
        "Lungu", "Moldovan", "Neagu", "Cristea", "Toma", "Sandu", "Voicu", "Preda", "Oprea", "Ilie"]
FIRME = ["ALFA LOGISTIC", "DELTA SOFTWARE", "CARPATI ENERGY", "NOVA RETAIL", "DUNAREA CONSTRUCT", "ORION MEDICAL",
         "VEST AUTOMOTIVE", "BUCOVINA FOODS", "TRANSILVANIA TEXTILE", "LITORAL SERVICES", "EST AGRO",
         "PRIMA CONSULTING", "SIGMA PHARMA", "OMEGA TELECOM", "ARGES METAL", "MUNTENIA DISTRIBUTIE",
         "CRISUL TECH"]
FIRME_CLIENTI_PFA = ["ATLAS DESIGN", "BRAVO MEDIA", "CITY EVENTS", "DIGITAL HUB", "EUROPA PRINT", "FORTE STUDIO",
                     "GALAXY ADS", "HELIOS LAB", "IRIS MARKETING", "JUPITER WEB", "KAPPA DATA", "LUMEN ARCH"]
JUDETE = ["BUCURESTI", "CLUJ", "IASI", "TIMIS", "CONSTANTA", "BRASOV", "PRAHOVA", "DOLJ"]
CREDITORI = ["BCR RATA CREDIT", "BRD GROUPE SOCIETE GENERALE RATA", "BANCA TRANSILVANIA RATA CREDIT",
             "ING BANK RATA", "IFN PROVIDENT FINANCIAL", "CREDIUM IFN RATA", "CEC BANK RATA"]
UTILITATI = ["ENEL ENERGIE MUNTENIA", "ENGIE ROMANIA", "DIGI ROMANIA", "APA NOVA BUCURESTI", "ORANGE ROMANIA"]
CUMPARATURI = ["KAUFLAND", "LIDL", "MEGA IMAGE", "EMAG MARKETPLACE", "OMV PETROM", "CARREFOUR", "DEDEMAN",
               "FARMACIA TEI", "DECATHLON", "ALTEX"]
PRODUSE_NON_CREDIT = ["cont_curent", "economii", "card_debit", "asigurare_viata", "depozit", "pensie_privata"]

# ---------------------------------------------------------------- generator


# ---------------------------------------------------------------- generatorul statistic (clienții de după cele 50)

def _tri(rng: random.Random, t: list[float]) -> float:
    return rng.triangular(t[0], t[2], t[1])          # random.triangular(low, high, mode)


def _wchoice(rng: random.Random, weights: dict[str, float]) -> str:
    return rng.choices(list(weights), weights=list(weights.values()))[0]


def _hit(rng: random.Random, prob: float, drawn: set[str], efect: str, corelatii) -> bool:
    """Trage la sorți semnalul `efect` cu probabilitatea de bază înmulțită cu factorii cauzelor deja trase."""
    for c in corelatii:
        if c.efect == efect and c.cauza in drawn:
            prob *= c.factor
    return rng.random() < min(1.0, prob)


def sample_scenario(rng: random.Random, profil, today: date) -> tuple[S, dict]:
    """Un client statistic: tipologie → nivel → credite → semnale (cu corelații) → cereri. Întoarce (S, plante externe).

    Produce aceleași obiecte S/L/R ca scenariile de mână, deci construcția creditelor, a plăților și a
    tranzacțiilor e identică; `planted_signals(S)` dă etalonul de semnale și pentru clienții statistici.
    """
    P = profil
    typ = _wchoice(rng, P.tipologii)
    v = P.vechime_client_ani
    vechime = rng.uniform(0.3, 1.5) if typ == "TAN" else _tri(rng, [v.min, v.mod, v.max])
    bonus = P.niveluri_bonus_vechime * max(0.0, vechime - 5)
    w = {"standard": max(0.01, P.niveluri["standard"] - 1.5 * bonus), "gold": P.niveluri["gold"] + bonus,
         "platinum": P.niveluri["platinum"] + bonus / 2}
    tier = _wchoice(rng, w)

    SC, drawn = P.semnale.per_credit, set()
    nr = rng.choices([0, 1, 2, 3], weights=P.credite.nr_credite[typ])[0]
    loans: list[L] = []
    for _ in range(nr):
        weights = dict(P.credite.produse[typ])
        if any(l.produs in ("ipotecar", "imobiliar") for l in loans):
            weights["ipotecar"] = weights["imobiliar"] = 0.0
        if any(l.produs == "card_credit" for l in loans):
            weights["card_credit"] = 0.0
        if sum(weights.values()) <= 0:
            break
        produs = _wchoice(rng, weights)
        if produs == "card_credit":
            spec = L("card_credit")
            if _hit(rng, SC["card_stres"].prob, drawn, "card_stres", P.corelatii):
                spec.card_stres = True
                drawn.add("card_stres")
        else:
            pp = P.credite.parametri[produs]
            rata = "fixa" if rng.random() < pp.fixa_prob else "variabila"
            spec = L(produs, rata, sold=round(_tri(rng, pp.sold), -2), ani_ramasi=round(_tri(rng, pp.ani_ramasi), 1),
                     ani_vechime=round(_tri(rng, pp.ani_vechime), 1), marja=round(_tri(rng, pp.marja), 2))
            secured = produs in ("ipotecar", "imobiliar")
            if secured and rata == "fixa" and _hit(rng, SC["expirare_dobanda_fixa"].prob, drawn, "expirare_dobanda_fixa", P.corelatii):
                spec.exp_zile = rng.randint(*SC["expirare_dobanda_fixa"].get("zile", [1, 120]))
                drawn.add("expirare_dobanda_fixa")
            if secured and _hit(rng, SC["ltv_depasit"].prob, drawn, "ltv_depasit", P.corelatii):
                spec.ltv_depasit = True
                drawn.add("ltv_depasit")
            if secured and _hit(rng, SC["asigurare_expirata"].prob, drawn, "asigurare_expirata", P.corelatii):
                spec.asigurare = True
                drawn.add("asigurare_expirata")
            if _hit(rng, SC["restructurare_anterioara"].prob, drawn, "restructurare_anterioara", P.corelatii):
                spec.restructurat = True
                drawn.add("restructurare_anterioara")
        i_cfg = SC["intarziere_noua"]
        if _hit(rng, i_cfg.prob, drawn, "intarziere_noua", P.corelatii):
            grav = rng.random() < i_cfg.get("prob_grav", 0.3)
            spec.intarziere = rng.randint(*(i_cfg.get("zile_grav", [32, 60]) if grav else i_cfg.get("zile", [3, 25])))
            drawn.add("intarziere_noua")
        loans.append(spec)

    PC, plant = P.semnale.per_client, {}
    if loans and _hit(rng, PC["rata_alt_creditor"].prob, drawn, "rata_alt_creditor", P.corelatii):
        plant["rata_alt"] = "nou" if rng.random() < PC["rata_alt_creditor"].get("prob_nou", 0.5) else "vechi"
        drawn.add("rata_alt_creditor")
    # salariu mutat / venit în scădere au nevoie de istoric de salariu: doar SL (tinerii au doar 4 luni de încasări)
    if typ == "SL" and loans and _hit(rng, PC["salariu_mutat"].prob, drawn, "salariu_mutat", P.corelatii):
        alta = rng.random() < PC["salariu_mutat"].get("prob_alta_banca", 0.5)
        plant["salariu_mutat"] = "alta_banca" if alta else True
        drawn.add("salariu_mutat")
        if alta and _hit(rng, PC["cont_nefolosit"].prob, drawn, "cont_nefolosit", P.corelatii):
            plant["cont_nefolosit"] = True
            plant.pop("rata_alt", None)                    # ieșirile din ultimele 2 luni dispar: rata n-ar mai fi vizibilă
    if typ == "SL" and "salariu_mutat" not in drawn and loans \
            and _hit(rng, PC["venit_scadere"].prob, drawn, "venit_scadere", P.corelatii):
        plant["venit_scadere"] = round(rng.uniform(*PC["venit_scadere"].get("factor", [0.5, 0.75])), 2)
        drawn.add("venit_scadere")
    if _hit(rng, PC["ci_expirata"].prob, drawn, "ci_expirata", P.corelatii):
        plant["ci"] = True
    if _hit(rng, PC["consimtamant_lipsa"].prob, drawn, "consimtamant_lipsa", P.corelatii):
        plant["consimtamant"] = rng.choice(["anaf", "bc"])
    if _hit(rng, PC["kyc_vechi"].prob, drawn, "kyc_vechi", P.corelatii):
        plant["kyc"] = True
    if _hit(rng, PC["flag_blocant"].prob, drawn, "flag_blocant", P.corelatii):
        plant["flag"] = "pep"
    if loans and not plant.get("cont_nefolosit") and _hit(rng, PC["poprire_activa"].prob, drawn, "poprire_activa", P.corelatii):
        plant["poprire"] = True
        drawn.add("poprire_activa")

    req: list[R] = []
    produse_detinute = {l.produs for l in loans}
    for tip, c in P.cereri.items():
        if rng.random() >= c.prob:
            continue
        if tip == "credit_nou":
            produs = rng.choice(c.produse)
        elif tip == "actualizare_date":
            produs = None
        else:
            cand = [p for p in c.produse if p in produse_detinute]
            if not cand:
                continue
            produs = rng.choice(cand)
        suma = round(rng.uniform(*c.suma), -2) if c.suma else None
        req.append(R(tip, produs, rng.randint(1, 20), suma))
        break                                              # o singură cerere per client

    pa = P.produse_atasate
    nprod = rng.randint(int(pa.min), int(pa.max))
    E = P.externe
    plante_ext = {}
    if plant.get("salariu_mutat") == "alta_banca":
        plante_ext["anaf"] = "salariu_continua"
    if rng.random() < E.bc_negativ:
        plante_ext["bc"] = "negativ"
    if rng.random() < E.crc_garant_restante:
        plante_ext["crc"] = "garant_restante"
    if any(l.produs in ("ipotecar", "imobiliar") for l in loans) and rng.random() < E.cf_litigiu:
        plante_ext["cf"] = "litigiu"
    sc = S(typ, tier, loans, plant=plant, req=req, exp=None, produse=nprod, ani_client=round(vechime, 1), nota="statistic")
    return sc, plante_ext


class Generator:
    def __init__(self, n: int, seed: int, today: date, profil=None, mod: str = "blocuri"):
        self.n = n
        self.seed = seed
        self.rng = random.Random(seed)
        self.today = today
        self.profil, self.mod = profil, mod
        self.tx_profile = None                      # None = zgomotul tranzacțiilor ca la cele 50 de scenarii
        self.plante_ext: dict[str, dict] = {}       # client_id -> plante pentru mock-urile externe (clienți statistici)
        self.cur_month = month_key(today)
        self.tx_months = last_months(self.cur_month, 12)                  # tranzacții: 12 luni, inclusiv luna curentă
        self.ph_months = last_months(shift_month(self.cur_month, -1), 24)  # istoric plăți: 24 luni închise
        self.clients, self.loans, self.payments, self.transactions = [], [], [], []
        self.employers, self.requests, self.ground_truth = [], [], []
        self._loan_seq = self._req_seq = 0
        self._luni_fara_iesiri: set[str] = set()

    # ---------------- helpers
    def d(self, days: int) -> date:
        return self.today + timedelta(days=days)

    def person(self) -> str:
        return f"{self.rng.choice(PRENUME)} {self.rng.choice(NUME)}"

    def day_in_month(self, mkey: str, day: int) -> str | None:
        day = max(1, min(28, day))
        if mkey == self.cur_month and day > self.today.day:
            return None
        return f"{mkey}-{day:02d}"

    def tx(self, cid: str, mkey: str, day: int, suma: float, directie: str, cine: str, tip: str) -> None:
        dt = self.day_in_month(mkey, day)
        if dt and directie == "out" and mkey in self._luni_fara_iesiri:
            return                                    # contul nu mai e folosit (plantat): ieșirile dispar
        if dt:
            self.transactions.append({"client_id": cid, "data": dt, "suma": round(suma, 2), "directie": directie,
                                      "platitor_beneficiar": cine, "tip_etichetat": tip})

    @staticmethod
    def annuity(sold: float, rate_pct: float, months: int) -> float:
        r = rate_pct / 100 / 12
        months = max(1, months)
        return sold / months if r == 0 else sold * r / (1 - (1 + r) ** -months)

    # ---------------- angajatori
    def make_employers(self, block: int) -> dict[str, dict]:
        emps = {}
        for i, name in enumerate(FIRME):
            eid = f"F{block * len(FIRME) + i + 1:04d}"
            suffix = "SA" if i % 4 == 2 else "SRL"
            emps[name] = {"angajator_id": eid, "nume": f"{name} {suffix}", "client_al_bancii": self.rng.random() < 0.6,
                          "status": "activ", "trend_plati_salarii_3l": round(self.rng.uniform(-0.10, 0.15), 2)}
        self.employers.extend(emps.values())
        return emps

    def make_employer_pool(self) -> list[dict]:
        """Bazinul de angajatori pentru clienții statistici: nume cu SRL/SA (regex-ul `firma`), câțiva în dificultate."""
        A, rng = self.profil.angajatori, self.rng
        tipuri = ["TRADING", "LOGISTIC", "SERVICES", "TECH", "CONSTRUCT", "MEDICAL", "AGRO", "SOFTWARE", "RETAIL", "ENERGY"]
        pool, seen = [], set()
        start = len(self.employers)
        while len(pool) < A.bazin:
            name = f"{rng.choice(NUME).upper()} {rng.choice(tipuri)}"
            if name in seen:
                continue
            seen.add(name)
            r = rng.random()
            status = "insolventa" if r < A.prob_insolventa else ("dizolvare" if r < A.prob_insolventa + A.prob_dizolvare else "activ")
            pool.append({"angajator_id": f"F{start + len(pool) + 1:04d}",
                         "nume": f"{name} {'SA' if len(pool) % 5 == 4 else 'SRL'}",
                         "client_al_bancii": rng.random() < A.prob_client_al_bancii, "status": status,
                         "trend_plati_salarii_3l": -0.35 if status != "activ" else round(rng.uniform(-0.10, 0.15), 2)})
        self.employers.extend(pool)
        return pool

    # ---------------- credite
    def make_loan(self, cid: str, spec: L, tier: str) -> dict:
        rng, ircc = self.rng, MARKET["ircc"]
        self._loan_seq += 1
        lid = f"L{self._loan_seq:04d}"
        p = spec.produs
        loan = {"loan_id": lid, "client_id": cid, "produs": p, "moneda": "RON", "suma_initiala": None,
                "sold_ramas": None, "data_acordare": None, "data_scadenta": None, "rata_lunara": None,
                "tip_dobanda": None, "dobanda_curenta": None, "dobanda_fixa_expira_la": None, "indice": None,
                "marja": None, "restructurat_anterior": False, "restructurari": [], "garantie": None,
                "codebitori": [], "limita": None, "utilizare_limita": None}

        if p == "card_credit":
            limita = rng.choice([5_000, 8_000, 10_000, 15_000, 20_000, 30_000])
            util = round(rng.uniform(0.93, 0.98), 2) if spec.card_stres else round(rng.uniform(0.05, 0.65), 2)
            vech = rng.uniform(1, 6)
            loan.update(suma_initiala=limita, sold_ramas=round(limita * util, 2), limita=limita, utilizare_limita=util,
                        data_acordare=add_years(self.today, -vech).isoformat(),
                        data_scadenta=add_years(self.today, rng.uniform(1, 4)).isoformat(),
                        tip_dobanda="fixa", dobanda_curenta=22.9,
                        rata_lunara=round(max(50, limita * util * 0.05), 2))
            return loan

        secured = p in ("ipotecar", "imobiliar")
        rata = spec.rata or ("variabila" if secured and rng.random() < 0.5 else "fixa")
        if spec.exp_zile is not None:                       # dobândă fixă inițială care expiră curând
            exp = self.d(spec.exp_zile)
            vech = spec.ani_vechime or (5 - spec.exp_zile / 365.25)
        else:
            vech = spec.ani_vechime or (rng.uniform(2, 9) if secured else rng.uniform(1, 4))
            exp = None
        ani_ramasi = spec.ani_ramasi or (rng.uniform(10, 27) if secured else rng.uniform(2, 6))
        if spec.sold:
            sold = spec.sold
        elif secured:
            sold = rng.uniform(150_000, 420_000)
        elif p == "refinantare":
            sold = rng.uniform(45_000, 140_000)
        else:
            sold = rng.uniform(15_000, 80_000)
        frac = (ani_ramasi / (ani_ramasi + vech)) ** 0.8
        suma = spec.suma or round(sold / max(0.15, frac), -3)
        sold = round(sold, -2)
        marja = spec.marja or (round(rng.uniform(2.2, 3.0), 2) if secured else round(rng.uniform(4.0, 6.0), 2))

        if rata == "variabila":
            dob = round(ircc + marja, 2)
        elif secured:
            dob = round(rng.uniform(5.0, 6.2), 2) if spec.exp_zile is None else round(rng.uniform(5.0, 5.6), 2)
            if exp is None:   # fixă pe perioadă inițială care expiră departe (> 1 an)
                exp = self.d(rng.randint(400, 1800))
        else:
            dob = round(rng.uniform(9.5, 12.5), 2)
            # nevoi personale / refinanțări: fixă pe toată durata, cu excepția celor plantate
        grant = add_years(self.today, -vech)
        loan.update(suma_initiala=suma, sold_ramas=sold, data_acordare=grant.isoformat(),
                    data_scadenta=add_years(self.today, ani_ramasi).isoformat(),
                    rata_lunara=round(self.annuity(sold, dob, round(ani_ramasi * 12)), 2),
                    tip_dobanda=rata, dobanda_curenta=dob,
                    dobanda_fixa_expira_la=exp.isoformat() if exp else None,
                    indice="IRCC", marja=marja)
        if secured:
            val = round(suma / rng.uniform(0.65, 0.82), -3)
            data_eval = grant - timedelta(days=15)
            if spec.ltv_depasit:
                val = round(sold / 1.12, -3)
                data_eval = date(2022, 4, 15)
            asig = self.d(rng.randint(12, 20)) if spec.asigurare else self.d(rng.randint(60, 330))
            loan["garantie"] = {"tip": "imobil", "valoare_evaluare": val, "data_evaluare": data_eval.isoformat(),
                                "asigurare_expira_la": asig.isoformat()}
        if spec.restructurat:
            loan["restructurat_anterior"] = True
            loan["restructurari"] = [{"data": add_years(self.today, -3.5).isoformat(), "tip": "prelungire_perioada"}]
        return loan

    def make_payments(self, loan: dict, spec: L) -> None:
        grant_m = loan["data_acordare"][:7]
        months = [m for m in self.ph_months if m > grant_m]
        for i, m in enumerate(months):
            zile, rest, minima = 0, 0, False
            if spec.intarziere and i == len(months) - 1:
                zile, rest = spec.intarziere, loan["rata_lunara"]
            elif spec.intarziere and spec.intarziere > 30 and i == len(months) - 2:
                zile, rest = 5, 0
            if spec.card_stres and i >= len(months) - 2:
                minima = True
            self.payments.append({"loan_id": loan["loan_id"], "luna": m, "zile_intarziere": zile,
                                  "suma_restanta": round(rest, 2), "plata_minima_card": minima,
                                  "rambursare_anticipata": 0})

    # ---------------- tranzacții
    def make_transactions(self, cid: str, sc: S, nume: str, employer: dict | None, total_rate: float) -> None:
        rng, months = self.rng, self.tx_months
        typ, plant = sc.typ, sc.plant
        n = len(months)

        if typ in ("SL", "TAN") and employer:
            base = max(rng.uniform(5_000, 14_000), total_rate / 0.35)
            day = rng.randint(6, 16)
            start = n - 4 if typ == "TAN" else 0
            for i in range(start, n):
                if plant.get("salariu_mutat") and i >= n - 2:
                    continue
                amt = base * rng.uniform(0.98, 1.03)
                if plant.get("venit_scadere") and i >= n - 3:
                    amt = base * plant["venit_scadere"]
                self.tx(cid, months[i], day + rng.randint(-2, 2), amt, "in", employer["nume"], "salariu")
            if plant.get("salariu_mutat") == "alta_banca":   # salariul vine acum la altă bancă, de unde acoperă ratele
                for i in range(n - 2, n):
                    self.tx(cid, months[i], day + 3, round(max(total_rate * 1.3, base * 0.4), 2), "in",
                            f"TRANSFER {nume.upper()}", "transfer_propriu")
        elif typ == "PEN":
            amt, day, jud = rng.uniform(2_200, 4_800), rng.randint(8, 12), rng.choice(JUDETE)
            for m in months:
                self.tx(cid, m, day + rng.randint(-1, 1), amt, "in", f"CASA JUDETEANA DE PENSII {jud}", "pensie")
        elif typ == "SE":
            for m in months:
                self.tx(cid, m, rng.randint(3, 25), rng.uniform(2_500, 7_000), "in", f"TRANSFER {nume.upper()}", "extern")
        elif typ == "IND":
            payers = FIRME_CLIENTI_PFA[:]
            rng.shuffle(payers)
            seq = payers * 2
            for i, m in enumerate(months):
                for p in seq[2 * i:2 * i + 2]:
                    self.tx(cid, m, rng.randint(1, 27), rng.uniform(2_000, 9_000), "in", f"{p} SRL", "extern")
        elif typ == "ANT":
            firma = f"{rng.choice(NUME).upper()} INVEST SRL"
            for i, m in enumerate(months):
                if i % 3 == 2:
                    self.tx(cid, m, rng.randint(10, 20), rng.uniform(15_000, 40_000), "in", f"{firma} - DIVIDENDE", "dividende")
                self.tx(cid, m, rng.randint(1, 27), rng.uniform(1_000, 4_000), "in", f"TRANSFER {nume.upper()}", "extern")
        elif typ == "DIA":
            for m in months:
                self.tx(cid, m, rng.randint(1, 27), rng.uniform(800, 2_500), "in", f"SEPA TRANSFER {nume.upper()} DE", "extern")

        tp = self.tx_profile                       # zgomotul extrasului: valorile celor 50 sau cele din profil
        if typ not in ("TAN",) and rng.random() < (tp.prob_chirie_in if tp else 0.2):
            chirias, amt = self.person().upper(), rng.choice([1_500, 2_000, 2_500])
            for m in months:
                self.tx(cid, m, rng.randint(1, 5), amt, "in", f"CHIRIE {chirias}", "chirie_in")

        # ieșiri
        util = rng.sample(UTILITATI, tp.nr_utilitati if tp else 2)
        lo, hi = tp.cumparaturi_pe_luna if tp else (3, 6)
        for m in months:
            for u in util:
                self.tx(cid, m, rng.randint(15, 25), rng.uniform(80, 450), "out", u, "utilitati")
            for _ in range(rng.randint(lo, hi)):
                self.tx(cid, m, rng.randint(1, 28), rng.uniform(30, 900), "out", rng.choice(CUMPARATURI), "altele")
        if typ in ("SE", "TAN") and rng.random() < (tp.prob_chirie_out if tp else 0.5):
            proprietar, amt = self.person().upper(), rng.choice([1_800, 2_200, 2_800])
            for m in months:
                self.tx(cid, m, rng.randint(1, 5), amt, "out", f"{proprietar} CHIRIE", "chirie_out")

        if plant.get("rata_alt"):
            creditor, amt = rng.choice(CREDITORI), round(rng.uniform(450, 2_400), 2)
            k = 3 if plant["rata_alt"] == "nou" else 8
            day = rng.randint(10, 20)
            for m in months[-k:]:
                self.tx(cid, m, day + rng.randint(-1, 1), amt, "out", creditor, "rata_alt_creditor")
        if plant.get("poprire"):
            bej = f"BEJ {rng.choice(NUME).upper()} POPRIRE DOSAR {rng.randint(100, 999)}/2026"
            for m in months[-2:]:
                self.tx(cid, m, rng.randint(5, 15), rng.uniform(600, 1_500), "out", bej, "poprire")

    # ---------------- client
    def make_client(self, idx: int, sc: S, employers: dict[str, dict], free_emps: list[dict],
                    employer_fix: dict | None = None, etalon: bool = True) -> None:
        rng = self.rng
        cid = f"C{idx:04d}"
        nume = self.person()
        varsta = {"PEN": rng.randint(63, 75), "TAN": rng.randint(20, 24)}.get(sc.typ, rng.randint(28, 58))
        nastere = date(self.today.year - varsta, rng.randint(1, 12), rng.randint(1, 28))
        plant = sc.plant

        employer = None
        if employer_fix is not None:
            employer = employer_fix
        elif sc.typ in ("SL", "SE", "TAN"):
            if plant.get("angajator"):
                employer = employers[FIRME[-2] if plant["angajator"] == "insolventa" else FIRME[-1]]
                employer.update(status=plant["angajator"], trend_plati_salarii_3l=-0.35)
            else:
                employer = rng.choice(free_emps)

        produse = []
        if sc.typ in ("SL", "TAN"):
            produse.append("cont_salariu")
        nprod = sc.produse if sc.produse is not None else rng.randint(1, 2)
        extra = [p for p in PRODUSE_NON_CREDIT if p not in produse]
        rng.shuffle(extra)
        produse = (produse + extra)[:max(nprod, len(produse))]

        vechime = rng.uniform(3, 15) if sc.typ != "TAN" else 0.5      # rng se apelează mereu (flux stabil)
        if sc.ani_client is not None:
            vechime = sc.ani_client
        client = {
            "client_id": cid, "nume": nume, "data_nasterii": nastere.isoformat(),
            "ci_expira_la": (self.d(-40) if plant.get("ci") else self.d(rng.randint(200, 3000))).isoformat(),
            "kyc_actualizat_la": (add_years(self.today, -2.6) if plant.get("kyc") else self.d(-rng.randint(30, 600))).isoformat(),
            "nivel_relatie": sc.tier,
            "client_din": add_years(self.today, -vechime).isoformat(),
            "consimtamant_anaf": plant.get("consimtamant") != "anaf",
            "consimtamant_biroul_credit": plant.get("consimtamant") != "bc",
            "flag_pep": plant.get("flag") == "pep", "flag_frauda_interna": False, "flag_decedat": False,
            "angajator_id": employer["angajator_id"] if employer else None,
            "produse_atasate": produse, "tipologie_declarata": TIPOLOGIE[sc.typ],
        }
        self.clients.append(client)

        total_rate = 0.0
        for spec in sc.loans:
            loan = self.make_loan(cid, spec, sc.tier)
            self.loans.append(loan)
            self.make_payments(loan, spec)
            total_rate += loan["rata_lunara"]

        self._luni_fara_iesiri = set(self.tx_months[-2:]) if plant.get("cont_nefolosit") else set()
        self.make_transactions(cid, sc, nume, employer, total_rate)
        self._luni_fara_iesiri = set()

        for rq in sc.req:
            self._req_seq += 1
            det = {"produs_vizat": rq.produs}
            if rq.suma:
                det["suma"] = rq.suma
            self.requests.append({"request_id": f"R{self._req_seq:04d}", "client_id": cid,
                                  "data": self.d(-rq.zile_in_urma).isoformat(), "tip": rq.tip, "detalii": det})

        self.ground_truth.append({"client_id": cid, "etalon": etalon, "semnale_plantate": planted_signals(sc),
                                  "banda_asteptata": sc.exp[0] if sc.exp else None,
                                  "actiune_asteptata": sc.exp[1] if sc.exp else None})

    def run(self) -> None:
        employers = {}
        n_etalon = self.n if self.mod == "blocuri" else min(self.n, len(SCENARIOS))
        for idx in range(1, n_etalon + 1):
            pos = (idx - 1) % len(SCENARIOS)
            if pos == 0:
                employers = self.make_employers((idx - 1) // len(SCENARIOS))
                planted_names = {FIRME[-2], FIRME[-1]}
                free = [e for k, e in employers.items() if k not in planted_names]
            self.make_client(idx, SCENARIOS[pos], employers, free)
        if self.n <= n_etalon:
            return
        # clienții statistici: RNG separat (cei 50 rămân identici byte cu byte), zgomot din profil, bazin de angajatori
        self.rng = random.Random(self.seed * 7919 + 1)
        self.tx_profile = self.profil.tranzactii
        pool = self.make_employer_pool()
        for idx in range(n_etalon + 1, self.n + 1):
            sc, plante_ext = sample_scenario(self.rng, self.profil, self.today)
            employer = None
            if sc.typ in ("SL", "SE", "TAN"):
                employer = self.rng.choice(pool)
                if employer["status"] != "activ":
                    sc.plant["angajator"] = employer["status"]
            self.make_client(idx, sc, {}, [], employer_fix=employer, etalon=False)
            self.plante_ext[f"C{idx:04d}"] = plante_ext

    def write(self, out: Path, extra_market: dict | None = None) -> None:
        write_json(out / "clients.json", self.clients)
        write_json(out / "loans.json", self.loans)
        write_json(out / "payment_history.json", self.payments)
        write_json(out / "transactions.json", self.transactions)
        write_json(out / "employers.json", self.employers)
        write_json(out / "requests.json", self.requests)
        write_json(out / "market.json", {"data": self.today.isoformat(), **MARKET, **(extra_market or {})})
        write_json(out / "ground_truth.json", self.ground_truth)


def planted_signals(sc: S) -> list[str]:
    """Etalonul de semnale pentru un scenariu (ce TREBUIE să găsească scanner-ul)."""
    out: list[str] = []
    for l in sc.loans:
        if l.exp_zile is not None:
            out.append("expirare_dobanda_fixa")
        if l.intarziere:
            out.append("intarziere_noua")
        if l.card_stres:
            out.append("card_stres")
        if l.ltv_depasit:
            out.append("ltv_depasit")
        if l.asigurare:
            out.append("asigurare_expirata")
        if l.restructurat:
            out.append("restructurare_anterioara")
    p = sc.plant
    if p.get("rata_alt"):
        out.append("rata_alt_creditor")
    if p.get("salariu_mutat"):
        out.append("salariu_mutat")
        if p["salariu_mutat"] is True:            # venitul chiar a dispărut, nu doar s-a mutat
            out.append("venit_disparut")
    if p.get("venit_scadere"):
        out.append("venit_in_scadere")
    if p.get("angajator"):
        out.append("angajator_in_dificultate")
    for key, sig in (("ci", "ci_expirata"), ("consimtamant", "consimtamant_lipsa"), ("flag", "flag_blocant"),
                     ("kyc", "kyc_vechi"), ("poprire", "poprire_activa")):
        if p.get(key):
            out.append(sig)
    for r in sc.req:
        if r.tip in ("adeverinta_sold", "refinantare"):
            out.append("cerere_adeverinta_sold")
        if r.tip == "simulare_rambursare_anticipata":
            out.append("simulare_in_app")
    return sorted(set(out))


def generate(n: int = 50, seed: int = 42, today: str = DEFAULT_TODAY, out: Path | str = DATA_DIR,
             mod: str | None = None, profil_file: Path | str | None = None) -> Generator:
    """mod: 'realist' (implicit pentru n > 50: primii 50 = etalon, restul din config/portofoliu.yaml) sau 'blocuri'."""
    from .generate_ext import extend
    from .profil import PROFIL_PATH, load_profil
    mod = mod or ("realist" if n > len(SCENARIOS) else "blocuri")
    profil = load_profil(profil_file or PROFIL_PATH) if mod == "realist" else None
    g = Generator(n, seed, date.fromisoformat(today), profil, mod)
    g.run()
    g.ext = extend(g, seed)              # date pentru modelul final: verificări, retenție, recomandare
    g.write(Path(out), g.ext.market())
    g.ext.write(Path(out))
    return g


def main(argv: list[str] | None = None) -> None:
    setup_console()
    ap = argparse.ArgumentParser(description="Generează portofoliul sintetic + ground truth.")
    ap.add_argument("--n", type=int, default=10000, help="implicit 10.000: 50 etalon + 9.950 statistici (--n 50 = doar etalonul)")
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--today", default=DEFAULT_TODAY)
    ap.add_argument("--out", default=str(DATA_DIR))
    ap.add_argument("--log-dir", default=str(OUT_DIR))
    ap.add_argument("--profil", choices=["realist", "blocuri"], default=None,
                    help="realist (implicit pentru n > 50): primii 50 = scenariile etalon, restul din profilul statistic")
    ap.add_argument("--profil-file", default=None, help="implicit config/portofoliu.yaml")
    a = ap.parse_args(argv)
    g = generate(a.n, a.seed, a.today, a.out, a.profil, a.profil_file)

    from collections import Counter
    prod = Counter(l["produs"] for l in g.loans)
    tip = Counter(c["tipologie_declarata"] for c in g.clients)
    sig = Counter(s for gt in g.ground_truth for s in gt["semnale_plantate"])
    print(f"Generat în {a.out}/  (seed={a.seed}, azi={a.today}, mod={g.mod}"
          + (f": {min(a.n, len(SCENARIOS))} etalon + {max(0, a.n - len(SCENARIOS))} statistici" if g.mod == "realist" else "") + ")")
    print(f"  clienți: {len(g.clients)}  credite: {len(g.loans)}  istoric plăți: {len(g.payments)}  "
          f"tranzacții: {len(g.transactions)}  cereri: {len(g.requests)}  angajatori: {len(g.employers)}")
    print("  tipologii: " + ", ".join(f"{k}={v}" for k, v in tip.most_common()))
    print("  produse:   " + ", ".join(f"{k}={v}" for k, v in prod.most_common()))
    print("  semnale plantate (clienți):")
    for k, v in sorted(sig.items()):
        print(f"    {k:<26} {v}")
    exp = Counter(gt["banda_asteptata"] or "—" for gt in g.ground_truth)
    print("  benzi așteptate: " + ", ".join(f"{k}={v}" for k, v in sorted(exp.items())))
    e = g.ext
    rec = Counter(gt["recomandare_asteptata"] or "—" for gt in g.ground_truth)
    fail = Counter(gt["verificare_picata_asteptata"] for gt in g.ground_truth if gt["verificare_picata_asteptata"])
    print("  model final:")
    print(f"    conturi: {len(e.conturi)}  documente: {sum(len(d['documente']) for d in e.documente)}  "
          f"garanții: {len(e.garantii)}  codebitori: {sum(len(l['codebitori']) for l in g.loans)}")
    print(f"    externe: anaf={len(e.anaf)}  biroul_credit={len(e.bc)} "
          f"(credite externe: {sum(len(b['credite']) for b in e.bc)})  "
          f"crc={len(e.crc)} (expuneri: {sum(len(x['expuneri']) for x in e.crc)})")
    print("    recomandări așteptate: " + ", ".join(f"{k}={v}" for k, v in sorted(rec.items())))
    print("    verificări care trebuie să pice: " + ", ".join(f"{k}={v}" for k, v in sorted(fail.items())))
    log_event(a.log_dir, "generate", "done", n=a.n, seed=a.seed, clienti=len(g.clients), credite=len(g.loans),
              tranzactii=len(g.transactions))


if __name__ == "__main__":
    main()
