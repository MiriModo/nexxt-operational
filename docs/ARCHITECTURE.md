# Keeper: referința tehnică

> Prezentarea pentru juriu e în [`README.md`](../README.md) (engleză). Aici e referința completă, în română:
> rulare, API, ecrane, comenzi, modelul pas cu pas, date, situații neașteptate și interpretările de validat.

Colegul virtual al consilierului de credite retail. Hackathon NEXXT · challenge Raiffeisen „AI for Operational
Efficiency". Referința de produs: [`MODEL_FINAL.md`](../MODEL_FINAL.md). Pachetul Python se numește în continuare
`retailagent`; interfața (`ui/`) e **Keeper**, în engleză, cu sistemul vizual din `Keeper_ghid_vizual_v2.pdf`
(Instrument Sans / Wix Madefor Text / Fragment Mono, tokenii și componentele din ghid; fonturile sunt împachetate în build).

Agentul găsește singur în portofoliu cazurile care trebuie lucrate, face verificările pe care le-ar face omul,
calculează **cea mai ieftină implicare a băncii care păstrează clientul** și propune o recomandare. **Consilierul
aprobă, modifică sau respinge, cu motiv.** Fiecare decizie e explicabilă în română, cu cifre și cu sursa.

Rulează local și determinist: Python 3.11+, fișiere JSON/YAML, fără bază de date (ANAF, Biroul de Credit, CRC și
garanțiile sunt mock-uri locale). Singurul apel extern, opțional, e agentul LLM de ofertare (pasul 3, doar cu o cheie
în `.env`); fără cheie, textul vine din șablonul determinist. Datele sunt 100% sintetice. Dependențe: `pyyaml`,
`pydantic`, `pytest`, `scikit-learn` (modelul de churn), `fastapi`, `uvicorn`, `httpx` (API și apelurile LLM).

```
Portofoliu ──scan semnale──┐
                           ├──► Coadă prioritizată (plecare × valoare × actiune; risc = canal separat)
Cereri clienți ────────────┘            │
                                        ▼
            Verificări alese din: produse deținute + motiv — intern → ANAF → Biroul de Credit → CRC → garanție,
            în trepte, oprire la primul pas picat; lista se afișează ÎNAINTE de rulare, cu motivul fiecărei omisiuni
                                        │
                                        ▼
          Model de retenție: cea mai ieftină intervenție din meniu cu p_după ≤ p_tinta și cost ≤ p × V
          (constrângerile BNR + plafoanele interne elimină opțiunile înainte de optimizare)
                                        │
                                        ▼
   recomandare: nu interveni | ofertă minimă | ofertă + produs | restructurare | respins/escaladat | blocat
                                        │
                                        ▼
                  consilierul aprobă / modifică / respinge cu motiv → ofertă + grafic + documente + audit
```

## Cum rulezi: trei moduri

**A. Doar Python, fără server (demo.html)** — 3 comenzi, nimic altceva de instalat:

```bash
pip install -r requirements.txt
python -m retailagent.generate            # 10.000 de clienți (60 etalon + 9.940 statistici), ~30 s; --n 60 = doar etalonul
python -m retailagent.pipeline            # tot fluxul (~3–4 min la 10.000 de clienți), evaluarea și out/demo.html
```

`data/` nu e versionat: se regenerează identic din seed. Deschide `out/demo.html` în browser (primele 200 de cazuri
din coadă; metricile pe tot portofoliul): coada, fiecare caz cu semnale / verificări / meniu de intervenții /
recomandare și butoanele de aprobare. Modelul antrenat e în `models/` (versionat); `python -m retailagent.churn.train`
îl reface.

**B. API + interfața React (dezvoltare)**:

```bash
python -m retailagent.api [--port 8000] [--reload]   # API-ul (FastAPI); nu cere `uvicorn` în PATH; rulează fluxul la pornire (~3–4 min la 10.000 de clienți)
cd ui && npm install && npm run dev                   # http://localhost:5173 (Vite proxy-ază /api → 8000; API_TARGET=http://... schimbă adresa)
```

Fără API, `npm run dev` folosește snapshot-ul static din `ui/public/data` (scris de `demo` / `pipeline`); deciziile
rămân în `localStorage`, ecranul arată comanda `approve` echivalentă, iar Admin explică de ce nu poate edita. Cu
API, deciziile intră în `out/approvals.json` + `out/audit.jsonl`.

**C. Docker (API + UI, fără Python/Node local)**:

```bash
docker compose up --build        # UI http://localhost:8080 · API http://localhost:8000/docs
RETAILAGENT_N=60 docker compose up --build   # pornire rapidă: doar etalonul
```

La prima pornire containerul `api` generează `data/` și antrenează modelul dacă lipsesc (volume: `data/`, `out/`,
`config/`, ca Admin-ul să editeze YAML-urile reale). `make demo | api | ui | test | docker` sunt scurtături pentru
aceleași comenzi (`Makefile`; pe Windows fără `make` rulează comenzile de mai sus).

### API

Rute: `GET /api/metrici/context` (azi, număr de clienți, modelul activ, **versiunea** config/model/cod, bugetul de
portofoliu), `GET /api/coada` (filtre pe bandă / recomandare / consilier, căutare, sortare, paginare pe server,
`ascunde_decise`), `GET /api/cazuri/sumar`, `GET /api/cazuri` (compact, `?limit`, `?banda`, `?q`),
`GET /api/cazuri/{id}` (detaliu complet), `POST /api/cazuri/{id}/decizie`, `GET /api/cazuri/{id}/decizii` (istoric),
`POST /api/cazuri/{id}/rezultat` (rămas / plecat la 90 de zile), `POST /api/cazuri/{id}/verifica` (reia doar
verificările cazului, pe trepte), `GET /api/decizii`, `GET /api/feedback`, `GET /api/echipa`, `GET /api/model`
(metrici + calibrare), `GET /api/config` · `GET/PUT /api/config/{nume}` (editare YAML cu validare pydantic, 400 cu
mesajul la eroare) · `GET /api/config/{nume}/diff`, `POST /api/rescan`, `GET /api/metrici`. OpenAPI la
`http://127.0.0.1:8000/docs`; `cd ui && npm run types` generează `src/types/openapi.d.ts` din el.
Variabile de mediu: `RETAILAGENT_DATA`, `RETAILAGENT_OUT`, `RETAILAGENT_CONFIG`, `RETAILAGENT_ADMIN_PAROLA`.

### Conturi și roluri

Pagina publică (`/`) e landing-ul Keeper (hero, welcome, how it works, sign in): alegi cine ești (consilierii din
`config/echipa.yaml` sau **Administrator**) și scrii parola. **Serverul** aplică rolul pe fiecare rută, interfața doar
reflectă:

| rol | parola | vede |
|---|---|---|
| advisor (Ana Pop, Mihai Ionescu, Ioana Dumitru, Radu Stan) | `parola` din `echipa.yaml` (demo: `1234`) | **My desk** (`/desk`: coada lui + activitatea lui) și **My queue** (`/queue`); un caz al altui consilier → 403; decizia poartă numele lui, nu unul ales |
| Administrator | `RETAILAGENT_ADMIN_PAROLA` (implicit `admin`) | tot: **Overview**, **Queue** (cu filtru pe consilier), **Reports**, **Rules engine** (`/rules`) |

Sesiunea e un token în memoria serverului (`POST /api/login` → `Authorization: Bearer`, 8 ore, `POST /api/logout`);
`GET /api/utilizatori` dă lista pentru login, fără parole. Fără server (snapshot static) login-ul e de demonstrație
(orice parolă) și filtrarea pe consilier se face în browser.

### Ecranele interfeței

Interfața e în engleză și e pentru consilier: pe fiecare ecran doar ce îi trebuie ca să decidă (cine, de ce acum, ce
propune agentul, ce costă / ce aduce, ce are de confirmat), restul într-un acordeon „How the agent got here". Cele 6
stări sunt badge-urile din ghid: **Keep** (ofertă, ofertă + produs) verde, **Restructure** (watch) amber, **Escalate**
roșu, **No action** / **Blocked** neutre. Textele produse de backend (motive, dovezi, etichetele intervențiilor,
explicația) rămân în română — traducerea lor e un pas separat.

* **My desk** (`/desk`, advisor) — „Ana, here's your day." cu cifrele mari (urgent due today, deferred over cap, to
  confirm, open) cu link direct, activitatea lui (decisions today, changed, still here at 90 days, queue by state),
  „Start here" (primele 5 după termen), ultimele decizii.
* **Overview** (`/overview`, administrator) — același briefing pe toată coada, apoi primele 5 după termen.
* **Queue** (`/queue`) — rânduri albe pe fundalul gri, segmented control pentru benzi (P1 / P2 / P3 ca etichete mono),
  select pe stare, consilier (doar admin), căutare, „Hide decided", filtre în URL afișate ca chips cu ×, bara de termen
  (fereastră de 14 zile), paginare (60 odată), schelet la încărcare.
* **Case** (`/queue/{id}`) — banda sticky cu clientul, starea, rata veche → nouă, termenul și **Decide →**; secțiuni
  cu etichete mono: [01] Why now, [02] The client, [03] What the agent proposes (dobândă, rată, economie, cost în
  display; to confirm / to request; cardul **AI offer agent** cu alegerea, argumentul și mesajul către client), [04] Checks — un rând pe verificare, pe trepte, cu
  cercurile verde / amber / roșu din ghid și **Re-check** (rulează doar verificările acelui caz și le arată pas cu
  pas). În acordeon „How the agent got here": semnalele, B / p / V, meniul ca grafic cost × p_după, explicația, versiunea.
* **Decision** (`/queue/{id}/decide`) — propunerea agentului LLM lângă cea a motorului (**Adopt the agent's choice** o
  transformă în „Change” cu motivul agentului); Approve / Change / Reject cu motiv; consilierul e cel autentificat
  (administratorul poate alege în numele cui decide), deciziile anterioare și rezultatul la 90 de zile; toast și
  întoarcere la caz.
* **Reports** (`/reports`, administrator) — cifrele mari (saved vs. uniform, no-cost cases, queries avoided, hard-rule
  breaches), costul pe strategie și distribuția ca bare în paleta de chart, bugetul lunar ca bară, **calibrarea
  modelului** cu diagonala ideală, consilierii față de agent, versiunea.
* **Rules engine** (`/rules`, administrator) — editor pentru cele 8 YAML-uri cu validare pe server la salvare, diff
  față de git, „Re-run the flow"; rutele `/api/config*` și `/api/rescan` răspund 403 pentru consilieri.

## Comenzi

```bash
python -m retailagent.generate [--n 10000] [--seed 42] [--profil realist|blocuri]   # data/ (implicit 10.000)
python -m retailagent.churn.labels                   # data/churn_labels.json: eticheta de churn (a_plecat) + feature-uri
python -m retailagent.churn.train                    # models/churn_v1.pkl + .json (metrici, calibrare, coeficienți)
python -m retailagent.churn.train --din-approvals                           # reantrenare pe rezultate reale (schelet)
python -m retailagent.pipeline [--skip-evaluate] [--skip-demo]   # tot fluxul → out/*.json, audit.jsonl, demo.html
python -m retailagent.explain Q0001               # explicația completă a unui caz (coadă → verificări → retenție → recomandare)
python -m retailagent.approve Q0001                                   # consilierul aprobă
python -m retailagent.approve Q0001 --decizie modifica --interventie fix_1_an --motiv "..."
python -m retailagent.approve Q0001 --decizie respinge --motiv "..." --consilier ana.pop
python -m retailagent.approve Q0001 --rezultat ramas                 # rezultatul la 90 de zile pe ultima decizie
python -m retailagent.feedback                    # out/feedback.json: override-uri, rezultate, propuneri de ajustare
python -m retailagent.evaluate [--scale 10000]    # metrici Modul 1 + „Model final" [+ scalare] → out/evaluation.json (cu versiune)
python -m retailagent.demo [--max-cazuri 200]     # pagina out/demo.html + snapshot pentru UI
python -m pytest                                  # 243 de teste

# pașii individuali (fiecare scrie fișierul lui în out/ și afișează un rezumat)
python -m retailagent.scan        # out/signals_detected.json
python -m retailagent.intake      # out/intake_cases.json
python -m retailagent.queue       # out/queue.json
python -m retailagent.checks      # out/checks.json   (--case Q0001 arată planul și rezultatele unui caz)
python -m retailagent.retention   # out/offers.json   (--case Q0001 arată meniul de intervenții)
python -m retailagent.recommend   # out/recommendations.json + out/audit.jsonl
```

Toate comenzile acceptă `--today AAAA-LL-ZZ`, `--data-dir`, `--out-dir`, `--config-dir`. Implicit azi = data din
`data/market.json` (2026-10-28). Logurile structurate (JSON lines) sunt în `out/run.log`.

## Rezultate pe etalon (cei 60 de clienți cu scenarii scrise de mână, primii din portofoliu; seed 42)

Primii 50 sunt scenariile de bază; 51–60 sunt **situațiile neașteptate** (valută, codebitor, semnale
contradictorii, cerere duplicată, fără cont, ANAF indisponibil, surse contradictorii, decedat, PEP, refinanțare
externă începută) — vezi [`REGULI.md`](REGULI.md) §5. Cifrele de mai jos sunt pe primii 50 (etalonul
istoric, neschimbat byte cu byte); cele 10 noi au toate recomandarea și incertitudinile așteptate (`tests/test_situatii.py`).

| metrică | valoare |
|---|---|
| **cifra-vedetă:** agentul vs. „aceeași reducere pentru toți" | nicio reducere uniformă nu atinge rata agentului (95%), deci nu există „aceeași rată”. Față de cea mai generoasă (0,6 pp pentru toți: 309.669 RON, 67% păstrați) agentul **costă cu 21.175 RON mai puțin (288.494 RON) și păstrează cu 29 pp mai mulți clienți**. Față de 0,2 pp pentru toți (103.948 RON, tot 67%), fiecare client păstrat în plus costă 30.758 RON |
| cazuri „nu interveni" (bani necheltuiți) | 15 / 56 cazuri active (27%) |
| interogări externe evitate prin alegerea verificărilor după motiv | 191 / 289 (66%) față de „rulează tot" |
| recomandări față de etalon | 48 / 49 (98%) |
| verificări picate corect (BC / CRC / garanție) | 3 / 3, 0 false pozitive |
| cerințe dure: oferte către risc activ · în afara limitelor · pe cazuri blocate · expirări < 30 zile nu în P1 | 0 · 0 · 0 · 0 |
| Modulul 1: F1 detecție semnale · benzi · acțiuni · ordonare · capcane | 1,00 · 100% · 100% · 708/708 · 5/5 |
| timp: scan + coadă · flux complet până la recomandare | 0,06 s · 0,65 s |

**La scară — portofoliul realist de 10.000 de clienți** (`evaluate --scale 10000`: 50 etalon + 9.950 statistici, 6.032 de cazuri):

| metrică | valoare |
|---|---|
| timp | generare ~30 s · flux complet ~3–4 min (măsurat la pornirea API-ului, 29 oct. 2026) |
| detecție semnale pe toți cei 10.000 (semnalele plantate sunt cunoscute pentru fiecare) | F1 **1,000** (4.845 TP, 0 FP, 0 FN) |
| cifra-vedetă | agent **25,8 M RON, păstrează 2.105/2.150 (98%)** · cea mai generoasă reducere uniformă (0,6 pp pentru toți): 29,0 M RON, 78% → agentul e **cu 3,19 M RON mai ieftin și păstrează cu 20 pp mai mulți clienți** (0,2 pp: 9,7 M RON, 75%; nicio reducere uniformă nu atinge 98%) |
| interogări externe evitate | 19.247 / 26.294 (73%) |
| recomandări | restructurare 1.975 · nu interveni 1.522 · blocat 1.505 · ofertă minimă 748 · respins / escaladat 252 · ofertă + produs 30 |
| cerințe dure | 0 · 0 · 0 · 0 |
| eticheta de churn (`churn.labels`, pe 1.500) | fără intervenție pleacă 30% din candidați (50% dintre cei cu legături mici, 30% dintre cei cu legături mari); cu agentul 2% |

> **Atenție la interpretare.** Datele, etalonul și comportamentul clienților sunt generate de noi. Rata de
> rămânere din cifra-vedetă e simulată cu `ground_truth → comportament` (pragul de câștig la care clientul
> pleacă, dacă reacționează la informare, dacă acceptă să-și aducă salariul), pe care agentul **nu îl vede**.
> Scorurile arată că implementarea respectă modelul, nu că parametrii sunt validați pe date reale. Pragurile,
> ponderile și meniul trebuie calibrate cu mentorul sau pe istoric.

## Cum funcționează

### 1. Scan semnale → coadă (`config/signals.yaml`, `config/priority.yaml`)

24 de semnale în trei familii — **plecare** (expirare dobândă fixă, gap față de piață în bani, cerere adeverință
de sold / refinanțare, rate la alt creditor, salariu mutat, eligibilitate externă, vechime, sold rămas,
simulări în app), **risc de credit** (întârziere nouă, venit în scădere / dispărut, card la limită cu plata minimă,
angajator în dificultate, restructurare anterioară, poprire, LTV depășit) și **blocaj de proces** (CI expirată,
KYC vechi, consimțământ lipsă, asigurare expirată, flag blocant). Salariul, pensia, ratele la alți creditori și
popririle se deduc din tranzacții (recurență + regex), nu din etichete.

```
plecare   = Σ pondere_i × scor_i  (+ bonus simulare)
valoare   = 0.6 × venit_viitor_norm + 0.4 × produse_atașate_norm
actiune   = 1 | 0.5 | 0   (gap acoperibil din bugetul de retenție al nivelului?)
prioritate_retentie = plecare × valoare × actiune
risc_credit = max(semnale risc);   prioritate = max(risc_credit, prioritate_retentie, minim cerere)
```

P1 dacă prioritate ≥ 0,6, sau risc ≥ 0,7, sau un semnal activ (cerere de adeverință, dobândă fixă care expiră
în ≤ 30 zile, salariu mutat confirmat); P2 ≥ 0,3; altfel P3. SLA 1 / 5 / 20 zile; termen = min(SLA, expirare − 30).
Risc ≥ 0,7 → nicio ofertă de retenție, traseu de restructurare. Blocaj activ → task, cazul rămâne „blocat".

**Salariu mutat ≠ venit pierdut.** Dacă salariul nu mai intră, dar ratele sunt acoperite din transferuri proprii
de la altă bancă, `venit_disparut` nu se declanșează: clientul nu are risc de credit, doar risc de plecare
(`salariu_mutat` = 1,0 → P1). Oferta lui depinde apoi de legăturile rămase cu banca (vezi §3).

### 2. Verificări după produse deținute + motiv (`config/checks.yaml`)

18 verificări pe 6 trepte: `intern → anaf → biroul_credit → crc → garantie → eligibilitate`. Stratul de bază
rulează mereu (identitate / KYC, expuneri interne inclusiv ca codebitor, venit observat, sold cont); stratul de
produs după ce deține clientul (LTV, asigurare, utilizare card); stratul de motiv adaugă sau sare
(`adauga` câștigă în fața lui `sare`):

| motiv | adaugă | sare |
|---|---|---|
| expirare dobândă fixă / adeverință de sold / refinanțare | scenarii rămâi / refinanțezi / pleci, cost mutare, ANAF, BC, CRC, extras CF, reevaluare, DTI | — |
| simulare rambursare anticipată | comision OUG 50 (0 la variabilă), fond de urgență | BC, CRC, garanție |
| credit nou / majorare limită | eligibilitate completă pe produsul-țintă (venit minim, DTI după rata nouă, vârstă) | — |
| întârziere / venit în scădere / card stres | ANAF, capacitate de plată actuală | scenarii, cost mutare, extras CF |
| CI expirată / consimțământ lipsă (blocaj) | doar `identitate_kyc` | tot restul așteaptă |

Fluxul se oprește la prima treaptă cu o verificare picată; ce urmează rămâne „neexecutat (oprit la …)".
Fără consimțământ nu se face nicio interogare care îl cere. Pentru nerezidenți fiscali ANAF dă avertizare, nu
eșec. Metrică: interogări externe evitate față de „rulează tot".

### 3. Model de retenție (`config/retention.yaml`, `config/constraints.yaml`)

Pe graficul real de rambursare (`finance.py`), nu „gap × sold × ani":

```
B = dobândă rămasă la noi − dobândă la dobânda pieței − costul mutării       (în orizontul de decizie: orizont_ani = 3)
legături = 0.35·produse_active + 0.25·vechime + 0.20·nivel + 0.20·activitate_cont   ∈ [0, 1]
p = sigmoid(a·B_norm + b·semnale_active − c − d·legături)                   (a=3, b=0.8, c=2.5, d=1.5)
V = marjă × sold × ani_rămași + Σ produse_atașate × ani                     (valoarea clientului dacă rămâne)
```

Meniul de intervenții (12, în YAML): nu interveni · informare + simulare · scutire comision · reducere marjă
0,2 / 0,4 / 0,6 pp · nouă perioadă fixă 1 / 3 / 5 ani la dobânda pieței · pachet (salariul la noi + 0,2 pp) ·
prelungirea maturității · pauză de rată. Pentru fiecare: costul băncii (dobânda la care renunță, pe toată durata
acordată), câștigul clientului (în orizont), `B_după`, `p_după`.

**Constrângerile elimină înainte de optimizare:** bugetul de retenție pe nivel (0,2 / 0,4 / 0,6 pp), marja
minimă 1,5 pp, vârsta maximă la noua scadență (70), DTI 40 % (+5 pp prima locuință), LTV 0,85, produsul fără
marjă / fără dobândă de piață pentru perioada cerută, risc activ (doar restructurare), **legături insuficiente**
(sub 0,30: doar informare sau pachet condiționat de salariu; sub 0,15: doar informare).

**Optimizare:** intervenția cu cost minim pentru care `p_după ≤ p_tinta` (20 %) **și** `cost ≤ p_înainte × V`.
Dacă nu există: informare (dacă p ≥ țintă) sau nu interveni.

Exemplu (C0013, salariu mutat la altă bancă, client gold de 12 ani): *„Clientul ar câștiga 21.130 RON plecând
(în 3 ani); p = 83 %. Oferta minimă care îl aduce sub 20 %: pachet: salariul la noi + reducere marjă 0,2 pp,
cost 6.950 RON față de 100.673 RON valoare pierdută; p scade la 14 %. Alternativa fixă 3 ani (4,90 %):
29.226 RON, p 7 %."* Cazul opus, C0014 (salariu mutat, standard, un produs, cont nefolosit): doar informare.

### 4. Recomandare și aprobare

`recommend` alege starea în ordinea: blocat → verificare picată (respins / escaladat) → risc sau cerere de
restructurare → cerere de produs nou (eligibil → ofertă la grila standard) → nu interveni / ofertă minimă /
ofertă + produs. Produce oferta concretă (dobândă nouă, rată nouă, perioadă), graficul de rambursare, documentele
lipsă din dosar (reguli în `checks.yaml → documente_necesare`), explicația în română și `out/audit.jsonl`
(semnal / verificare / retenție / decizie, cu valoare, sursă și timestamp).

`approve` validează decizia consilierului: `modifica` și `respinge` cer motiv; intervenția aleasă de om trebuie
să existe în meniu și să fie fezabilă (altfel refuz cu motivul constrângerii); override-ul intră în audit.

### 5. Agentul LLM de ofertare (`config/llm.yaml`, `retailagent/llm.py`)

Pasul 3 din roadmap: **decide oferta în constrângeri și scrie textul în limbaj uman**. Constrângerile rămân la motor;
modelul alege doar dintre opțiunile pe care motorul le-a declarat admisibile și scrie doar cu cifrele calculate.

1. **Opțiunile admisibile** (`optiuni_admisibile`): în cazurile de retenție (ofertă minimă / ofertă + produs), intervențiile
   fezabile (DTI, LTV, vârstă, marjă minimă, buget pe nivel) care aduc p sub țintă și costă ≤ p×V, plafonate la
   `cost_max_fata_de_motor` × costul alegerii motorului (implicit 2×). Pentru fiecare se calculează oferta concretă, la
   fel ca la decizia „modifică”. Cazurile blocate, escaladate, cu risc de credit sau fără nevoie de ofertă nu primesc
   opțiuni: agentul doar explică decizia motorului.
2. **Contextul** (`context_agent`): doar fapte calculate și etichete din config. Fără nume, fără dovezile semnalelor
   (text liber din date, unde pot apărea comercianți sau bănci), deci fără injecție de prompt.
3. **Apelul**: tool forțat cu schemă strictă; `interventie` e un enum din opțiunile admisibile. Furnizorul implicit din
   `llm.yaml` e Anthropic (`claude-haiku-5-5`); la demo rulăm pe Amazon Bedrock cu Claude Haiku 4.5
   (`.env`: `RETAILAGENT_LLM_PROVIDER=bedrock`, `BEDROCK_MODEL_ID`). Opțional, OpenAI.
4. **Validarea** (`valideaza`): fiecare număr din text trebuie să existe în fapte; mesajul către client poate cita doar
   creditul și oferta aleasă (nu costul băncii, p, V sau scoruri) și trebuie să spună rata sau dobânda nouă; termenii
   interziși (bănci concurente, „garantat”, „gratuit”, cashback) resping textul. Un răspuns respins primește o
   reîncercare cu motivul respingerii, apoi agentul cade pe **șablonul determinist** (aceleași câmpuri, marcat
   `sablon`).
5. **Decizia rămâne a consilierului.** Dacă agentul alege altă opțiune decât motorul, interfața arată diferența de
   cost; adoptarea ei e un „modifică” cu motivul agentului. `propunere_id` intră în decizie doar dacă propunerea
   corespunde intervenției finale (serverul verifică), iar propunerea întreagă intră în `approvals.json` și
   `audit.jsonl`. Hash-ul promptului intră în `versiune.prompturi`.

Cheia **nu** stă în repo: `ANTHROPIC_API_KEY` (sau `AWS_BEARER_TOKEN_BEDROCK` / `OPENAI_API_KEY`) în mediu sau în
`.env` din rădăcină (vezi `.env.example`; `.env` e ignorat de git și de Docker). Fără cheie, totul funcționează pe
șablon. Verificare rapidă: `python -m retailagent.llm --verifica` (starea + un apel de probă pe un caz sintetic).

## Portofoliul realist la scară (`config/portofoliu.yaml`, `retailagent/profil.py`)

Pentru `--n > 50` generatorul nu mai repetă cele 50 de scenarii în blocuri: primii 50 rămân scenariile de mână
(etalonul, identic byte cu byte), iar restul se construiesc **statistic** din profilul YAML. Conceptul, pe scurt:

* **Distribuție în loc de valoare fixă.** Nu „soldul e 400.000", ci „soldul unui ipotecar e între 80.000 și 900.000,
  cel mai des în jur de 250.000" (triunghiular). La fel vechimea, marja, durata, numărul de produse. Fiecare client
  e unic, portofoliul arată plauzibil.
* **Semnalele apar cu o probabilitate, corelat.** „12% din creditele cu dobândă fixă expiră în 120 de zile; 4,5%
  au întârzieri; cine are întârzieri are de 3 ori mai des venit în scădere." Apar combinații pe care nu le-am scris
  de mână — exact ce trebuie să învețe un model. Corelațiile se aplică în ordinea trasării (per credit, apoi per client).
* **Comportamentul ascuns are structură.** Pragul la care clientul pleacă depinde de vechime, produse, nivel și
  activitatea pe cont, plus zgomot lognormal: `prag = prag_baza × (1 + 0,8·vechime/10 + 0,9·produse/4 + 0,7·nivel + 0,4·activ) × e^N(0, 0,45)`.
  Agentul nu îl vede. `python -m retailagent.churn.labels` simulează pentru fiecare candidat la retenție dacă a
  rămas sau a plecat — fără intervenție și cu intervenția agentului — și scrie `churn_labels.json`, setul de
  antrenare pentru modelul de churn (pasul următor).
* **Mock-urile externe** (ANAF, BC, CRC, garanție) se generează cu aceleași reguli de consistență; eșecurile
  (întârziere ≥ 90 zile la un IFN, garant cu restanțe, litigiu în CF) apar cu probabilități mici din profil.
* **Seed-ul.** Tot ce e „la sorți" pleacă din seed 42; RNG-ul clienților statistici e separat de cel al etalonului.
  Aceeași comandă → aceleași 10.000 de clienți (test de determinism).
* **Etalonul în metrici.** `ground_truth.json` marchează `etalon: true/false`. Benzile, acțiunile, ordonarea,
  recomandările și verificările picate se evaluează doar pe etalon; F1 de detecție pe toți.

`--profil blocuri` păstrează comportamentul vechi (repetarea blocurilor); `--profil-file` ia alt profil.

## Modelul de churn antrenat (`retailagent/churn/`, `models/`)

`p_plecare` poate veni din două surse, alese în `retention.yaml → churn.model`: **`antrenat`** (`models/churn_v1.pkl`,
implicit — platforma pornește pe modelul antrenat) sau **`sigmoid`** (formula cu parametri scriși de noi, fallback). Tot restul — meniul, constrângerile,
optimizarea — e identic; modelul dă doar `p_înainte`, iar intervențiile rămân deplasări pe logit. Cu `sigmoid`
rezultatele sunt identice cu cele de dinainte (test de aur).

Conceptul, pe scurt:

* **Ce învață.** Din 10.000 de clienți sintetici, pentru fiecare candidat la retenție: a plecat sau nu *dacă banca
  nu făcea nimic* (`a_plecat_fara_interventie`, simulat din comportamentul ascuns). Modelul învață legătura
  dintre ce vede agentul (B, legături, semnale active, nivel, vechime, produs, sold, DTI…) și plecare.
* **O singură funcție `features()`** (`churn/features.py`), folosită identic la antrenare (`churn.labels` o scrie
  în `churn_labels.json`) și la inferență (`retention_menu`). 33 de coloane, ordine fixă, versiune de schemă;
  un model antrenat pe altă schemă e refuzat la încărcare.
* **De ce split pe clienți.** Un client cu două credite are două rânduri; dacă unul e în antrenare și altul în
  test, scorul e umflat. `GroupShuffleSplit` pe `client_id`, 80/20.
* **De ce calibrare, nu doar AUC.** p intră în `cost ≤ p × V`: un model care ordonează bine dar spune 90% când
  realitatea e 60% cheltuie bani degeaba. Se antrenează regresie logistică și gradient boosting; câștigă cel cu
  **Brier** mai mic pe test; se raportează și ECE + curba de calibrare pe 10 intervale.
* **Explicabilitate.** Logistic: contribuția fiecărui feature pe logit (coeficient × valoare standardizată);
  boosting: delta logit când feature-ul e adus la media de antrenare. Apar în `explain` și în demo.
* **Circularitatea.** Eticheta e simulată din regulile noastre de generare, deci modelul învață generatorul
  (AUC 0,98 pe sintetic nu înseamnă nimic despre realitate). Valoarea apare când eticheta vine din
  rezultatele consilierilor: `churn.train --din-approvals` citește `rezultat ∈ {ramas, plecat}` din
  `approvals.json` și reantrenează când sunt cel puțin 200 de rezultate reale.

Rezultat (`models/churn_v1.json`, 2.147 rânduri, 1.719 / 428): **logistic**, AUC 0,98, Brier 0,045, ECE 0,024;
coeficienți principali: `B_norm +2,36`, `B_log +2,23`, `produs_nevoi_personale −0,74`, `sold_log +0,55`,
`activ_salariu_mutat +0,25`, `legaturi −0,24`. `evaluate` tipărește secțiunea „sigmoid vs antrenat" (cifra-vedetă,
p mediu, distribuția intervențiilor) când `models/churn_v1.pkl` există.

## Date (`retailagent/generate.py`, `retailagent/generate_ext.py`)

50 de scenarii explicite cu semnale plantate și etalon: `ground_truth.json` conține semnalele plantate, banda și
acțiunea așteptată, recomandarea așteptată, verificarea care trebuie să pice și `comportament` (ascuns
agentului, folosit doar de `evaluate`). Fișiere: `clients`, `loans` (cu `prima_locuinta`, `codebitori`),
`payment_history`, `transactions`, `employers`, `requests`, `market` (IRCC, dobânzi de piață pe perioade fixe,
costurile mutării), `conturi`, `documente`, `externe/{anaf, biroul_credit, crc, garantii}`. Mock-urile spun
aceeași poveste ca portofoliul (rata la alt creditor apare în BC cu aceeași sumă, expunerile ≥ 20.000 RON în CRC,
LTV-ul depășit e confirmat de reevaluare). Situații plantate: C0005 litigiu în CF, C0046 întârziere de 95 de
zile la un IFN, C0047 garant pe un credit cu restanțe, C0013 / C0014 salariu mutat cu / fără legături, C0027
pensionar care ar avea 86 de ani la o prelungire. Pentru `--n > 50` vezi „Portofoliul realist la scară".

Fiecare tranzacție poartă și o **categorie de plată**, ca în aplicația băncii (`categorie`: groceries, restaurants,
appliances_it, shopping, home_diy, transport, health, entertainment, services, travel, utilities_bills, housing,
loan_payments, cash, legal, internal_transfers, other; la intrări income_salary / income_pension / income_rent /
income_dividends / internal_transfers / transfers_in). Categoria se deduce din comerciant (`generate.categoria`) și
nu consumă din RNG-ul principal: sumele, datele și semnalele rămân identice; pentru o parte din plățile „altele" se
schimbă doar comerciantul (ponderi în `portofoliu.yaml → tranzactii.categorii`). `retailagent/cheltuieli.py` face
profilul pe ultimele 3 luni (`cheltuieli` în `GET /api/cazuri/{id}`), afișat pe pagina cazului ca „Spending, last 3 months".

## Cum adaugi ceva nou (configurație, nu cod)

* **Semnal:** intrare în `signals.yaml` + funcție `@signal(id, familie, nivel)` în `retailagent/signals/` +
  pondere în `priority.yaml` + 2 teste. Scanner-ul verifică la pornire că fiecare semnal din YAML are funcție.
* **Verificare:** intrare în `checks.yaml` (treaptă, strat, produse, consimțământ) + funcție `@check(id)` în
  `checks_run.py`; adaugi id-ul la motivele care o cer.
* **Intervenție:** intrare în `retention.yaml → interventii` (tip, cost, reducere / ani, efect, condiții).
  Tipurile existente nu cer cod nou. Un buget nou pe nivel: `priority.yaml → buget_retentie_pp`.
* **Constrângere / prag:** `constraints.yaml`, `retention.yaml` (p_tinta, orizont, sigmoid, legături).
* **Consilier:** `echipa.yaml`; alocarea e deterministă (hash pe `client_id`).
* **Incertitudine critică** (ce tip de cerere se escaladează când o sursă lipsește): `checks.yaml → incertitudini_critice`.
* Din interfață: **Admin** editează oricare YAML cu validare și re-rulează fluxul.

Sursa fiecărei reguli (BNR, OUG 50, KYC/AML, politică internă, model) e în [`REGULI.md`](REGULI.md).

## Situații neașteptate: degradare controlată, nu oprire

Zece scenarii din etalon (51–60) acoperă ce se întâmplă când datele nu sunt cum se așteaptă. Principiul: fluxul
continuă, cazul poartă o **incertitudine** structurată (`rec.incertitudini`, vizibilă în coadă și în caz), oferta
devine **condiționată** (`oferta.conditii_de_confirmat`), iar dacă incertitudinea e critică pentru tipul cererii
(`checks.yaml → incertitudini_critice`) cazul se **escaladează la om**. Status nou de verificare: `indisponibil`
(sursa nu a răspuns) ≠ `fail`. Creditele în EUR se normalizează în RON (`market.curs_eur`) și primesc DTI 20 %;
codebitorii cu risc, cererile duplicate (≤ 7 zile) și refinanțările externe începute au semnale / reguli proprii.
**Bugetul lunar de retenție pe portofoliu** (`retention.yaml → buget_portofoliu`, 2 M RON) ordonează ofertele
după V_reținut / cost; cele peste plafon rămân recomandate, dar amânate („peste plafon luna asta").

## Bucla de feedback și versionarea

Fiecare decizie a consilierului poartă autorul (`consilier`), iar la 90 de zile se înregistrează rezultatul
(`ramas` / `plecat`). `python -m retailagent.feedback` (și Dashboard-ul) raportează rata de override pe
intervenție / nivel / produs / consilier, motivele frecvente, rămânerea reală vs. prezisă pe intervenție și
**propuneri** de ajustare (ex. „pachet_salariu e înlocuit des cu fix_3_ani → revizuiește efect_scor") — sugestii
pentru om, nu modificări automate. Fiecare recomandare, rând de audit și evaluare poartă **versiunea**: hash
SHA-256 al YAML-urilor + versiunea / hash-ul modelului + commit-ul de cod, ca o decizie de ieri să poată fi
reprodusă după ce se schimbă pragurile. `churn.train --din-approvals` reantrenează pe rezultatele reale.

## Interpretări ale modelului (de validat cu mentorul)

| subiect | ce am ales | de ce |
|---|---|---|
| orizontul lui B | 3 ani (`orizont_ani`), nu toată durata | pe 22 de ani B ≈ 200.000 RON, p ≈ 97 % pentru toți și nicio ofertă nu atingea ținta; exemplul din MODEL_FINAL (41.200 RON, „fix 3 ani") e consistent cu ~3 ani |
| costul intervenției | pe toată durata acordată (reducerea de marjă: până la scadență; fixa: perioada ei) | ce pierde efectiv banca; câștigul clientului se numără doar în orizont |
| legăturile cu banca | gate pentru ofertă: < 0,30 doar informare / pachet; < 0,15 doar informare | regula utilizatorului: oferta depinde de legăturile rămase, de fidelitate |
| pachetul cu salariul | `efect_scor −2,5` (ancoraj) + legături +0,4 | a muta din nou și salariul, și creditul e costisitor pentru client; parametru de calibrat |
| treapta `eligibilitate` | a 6-a, internă, după sursele externe | DTI și eligibilitatea au nevoie de venitul confirmat (ANAF) și de ratele din BC; altfel fluxul se oprea înainte de BC |
| `blocat` ca a 6-a stare | cazurile cu task de proces nu primesc decizie comercială | MODEL_FINAL le ține „blocate" până la rezolvare |
| nerezident fiscal | ANAF → avertizare; venitul din transferuri proprii + documente | ANAF nu vede venitul din străinătate |
| `actiune` din coadă | proxy-ul cu grilă vs buget rămâne | coada rulează înainte de verificări; decizia reală o dă modelul de retenție |
| rata de rămânere | simulată din `comportament` (prag de câștig, informare, pachet) | altfel comparația agent vs uniform ar folosi propriul model al agentului |
| etalonul recalibrat | C0007, C0008 → nu interveni; C0016 → ofertă minimă; C0049 lăsat ca diferență | reflectă intenția scenariilor după calibrare; C0049 (diaspora, variabil cu gap 3 pp) e de discutat |
| `gap_piata_bani` (Modul 1) | formula literală, plafonată la 30.000 RON | supraestimează economia, dar nu schimbă clasamentul |
| semnal activ pentru P1 | adeverință, expirare ≤ 30 zile, salariu mutat confirmat | cerința „expirare < 30 zile ⇒ P1" trebuie garantată |
| sursă externă indisponibilă | status `indisponibil`, fluxul continuă cu ce se vede, oferta e condiționată; credit nou ⇒ escaladare | o sursă căzută nu trebuie să blocheze retenția, dar nici să dea credit nou fără venit confirmat |
| semnale contradictorii (risc + plecare) | riscul de credit câștigă; retenția se reia după stabilizare | nu oferi reducere unui client care nu-și plătește rata |
| buget de portofoliu | plafon lunar, ordonare V_reținut / cost, ofertele peste plafon rămân recomandate, dar amânate | decizia comercială rămâne vizibilă; omul poate aproba explicit peste plafon |
| credit în valută | normalizare în RON la cursul din `market.json`, DTI 20 % | BNR; cursul e o fotografie, nu o prognoză |
| consilier | alocare deterministă (hash pe client) | același client ajunge mereu la același om; feedback-ul se poate raporta pe consilier |

## Structura

```
retailagent/
  generate.py, generate_ext.py   # date sintetice + etalon (60 scenarii explicite, 51–60 situații neașteptate; --n > 60 = profil statistic)
  profil.py                      # profilul portofoliului realist (pydantic)
  churn/                         # features (o singură funcție), model (SigmoidChurn / TrainedChurn), labels, train
  common.py, config_loader.py    # utilitare; validare pydantic a YAML-urilor + verificări încrucișate
  signals/                       # registru, inflows (deducerea încasărilor), plecare, risc_credit, blocaj_proces
  scan.py, intake.py, queue.py   # Modulul 1: semnale → cazuri → coadă (schema queue.json stabilă)
  finance.py                     # anuitate, grafic, dobândă pe scenarii / orizont, OUG 50, DTI, cost mutare
  checks.py, checks_run.py       # plan după produse + motiv; execuție în trepte cu mock-uri; CLI
  retention.py, retention_menu.py# B, legături, V, p; meniu, constrângeri, optimizare; CLI
  recommend.py, approve.py       # cele 6 stări, ofertă, grafic, documente, audit, incertitudini; aprobarea consilierului + rezultat la 90 zile
  buget.py                       # bugetul lunar de retenție pe portofoliu (ordonare V_reținut / cost, marcaje in_buget / amânată)
  feedback.py, versiune.py       # raportul agent vs. consilier vs. rezultat; hash config + versiune model + commit
  llm.py                         # pasul 3: agentul LLM de ofertare (opțiuni admisibile, context, validare, șablon, furnizori)
  explain.py, evaluate.py, evaluate_final.py, demo.py, pipeline.py
  api.py                         # FastAPI pe contractul din ui/src/types/api.ts (snapshot comun cu demo.py → build_data)
models/                          # churn_v1.pkl (joblib) + churn_v1.json (feature-uri, metrici, calibrare, coeficienți)
ui/                              # React (Vite + TS + React Query): Acasă, Coadă, Caz, Decizie, Dashboard, Admin; public/data e generat
config/                          # signals, priority, checks, constraints, retention, portofoliu, echipa, llm
docs/REGULI.md                   # fiecare regulă cu sursa (BNR / OUG 50 / KYC-AML / politică internă / model) + situațiile neașteptate
data/                            # portofoliul + externe/ (mock-uri)         out/   # artefactele rulării
tests/                           # 243 de teste (… + situații neașteptate, feedback, API)
Dockerfile.api, ui/Dockerfile, docker-compose.yml, Makefile
vault/                           # jurnalul deciziilor și al taskurilor (autobot)
```
