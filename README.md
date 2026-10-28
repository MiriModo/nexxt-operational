# retailagent — colegul virtual al consilierului de credite retail

Hackathon NEXXT · challenge Raiffeisen „AI for Operational Efficiency". Referința de produs: [`MODEL_FINAL.md`](MODEL_FINAL.md).

Agentul găsește singur în portofoliu cazurile care trebuie lucrate, face verificările pe care le-ar face omul,
calculează **cea mai ieftină implicare a băncii care păstrează clientul** și propune o recomandare. **Consilierul
aprobă, modifică sau respinge, cu motiv.** Fiecare decizie e explicabilă în română, cu cifre și cu sursa.

Rulează local și determinist: Python 3.11+, fișiere JSON/YAML, fără bază de date, fără servicii externe (ANAF,
Biroul de Credit, CRC și garanțiile sunt mock-uri locale). Datele sunt 100% sintetice.

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

## Setup în 3 comenzi

```bash
pip install -r requirements.txt
python -m retailagent.generate --n 50 --seed 42
python -m retailagent.pipeline
```

A treia comandă rulează tot fluxul (sub o secundă pe 50 de clienți), evaluarea și generează `out/demo.html`.
Deschide `out/demo.html` în browser: coada, fiecare caz cu semnale / verificări / meniu de intervenții /
recomandare și butoanele de aprobare.

## Comenzi

```bash
python -m retailagent.generate --n 50 --seed 42   # data/*.json, data/externe/*.json, ground_truth.json
python -m retailagent.generate --n 10000 --seed 42 --out out/scale_10000   # portofoliu realist: 50 etalon + 9.950 statistici
python -m retailagent.churn.labels --data-dir out/scale_10000             # eticheta de churn (a_plecat) pentru antrenare
python -m retailagent.pipeline [--skip-evaluate] [--skip-demo]   # tot fluxul → out/*.json, audit.jsonl, demo.html
python -m retailagent.explain Q0001               # explicația completă a unui caz (coadă → verificări → retenție → recomandare)
python -m retailagent.approve Q0001                                   # consilierul aprobă
python -m retailagent.approve Q0001 --decizie modifica --interventie fix_1_an --motiv "..."
python -m retailagent.approve Q0001 --decizie respinge --motiv "..."
python -m retailagent.evaluate [--scale 10000]    # metrici Modul 1 + „Model final" [+ scalare] → out/evaluation.json
python -m retailagent.demo [--max-cazuri 200]     # doar pagina out/demo.html
python -m pytest                                  # 159 teste

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

## Rezultate pe setul sintetic (50 clienți, seed 42)

| metrică | valoare |
|---|---|
| **cifra-vedetă:** cost retenție agent vs. „aceeași reducere pentru toți", la aceeași rată de rămânere | agent **288.544 RON**, reține 20/21 candidați (95%) · uniform 0,6 pp pentru toți: 309.669 RON, reține doar 67% (0,2 pp: 103.948 RON, 67%) |
| cazuri „nu interveni" (bani necheltuiți) | 15 / 56 cazuri active (27%) |
| interogări externe evitate prin alegerea verificărilor după motiv | 191 / 289 (66%) față de „rulează tot" |
| recomandări față de etalon | 48 / 49 (98%) |
| verificări picate corect (BC / CRC / garanție) | 3 / 3, 0 false pozitive |
| cerințe dure: oferte către risc activ · în afara limitelor · pe cazuri blocate · expirări < 30 zile nu în P1 | 0 · 0 · 0 · 0 |
| Modulul 1: F1 detecție semnale · benzi · acțiuni · ordonare · capcane | 1,00 · 100% · 100% · 708/708 · 5/5 |
| timp: scan + coadă · flux complet până la recomandare | 0,06 s · 0,65 s |

**La scară — portofoliul realist de 10.000 de clienți** (`evaluate --scale 10000`: 50 etalon + 9.950 statistici, 6.024 cazuri):

| metrică | valoare |
|---|---|
| timp | generare 31 s · flux complet 38,5 s (scan 11,4 · coadă 1,1 · verificări 5,9 · retenție 16,9 · recomandare 3,3) |
| detecție semnale pe toți cei 10.000 (semnalele plantate sunt cunoscute pentru fiecare) | F1 **1,000** (4.845 TP, 0 FP, 0 FN) |
| cifra-vedetă | agent 27,1 M RON, reține 2.105/2.147 candidați (98%) · uniform 0,6 pp: 28,9 M RON, 79% · 0,2 pp: 9,7 M RON, 75% |
| interogări externe evitate | 19.236 / 26.260 (73%) |
| recomandări | restructurare 1.972 · blocat 1.503 · nu interveni 1.476 · ofertă minimă 782 · respins 253 · ofertă + produs 38 |
| cerințe dure | 0 · 0 · 0 · 0 |
| eticheta de churn (`churn.labels`, pe 1.500) | fără intervenție pleacă 30% din candidați (50% dintre cei cu legături mici, 30% dintre cei cu legături mari); cu agentul 2% |

> **Atenție la interpretare.** Datele, etalonul și comportamentul clienților sunt generate de noi. Rata de
> rămânere din cifra-vedetă e simulată cu `ground_truth → comportament` (pragul de câștig la care clientul
> pleacă, dacă reacționează la informare, dacă acceptă să-și aducă salariul), pe care agentul **nu îl vede**.
> Scorurile arată că implementarea respectă modelul, nu că parametrii sunt validați pe date reale. Pragurile,
> ponderile și meniul trebuie calibrate cu mentorul sau pe istoric.

## Cum funcționează

### 1. Scan semnale → coadă (`config/signals.yaml`, `config/priority.yaml`)

22 de semnale în trei familii — **plecare** (expirare dobândă fixă, gap față de piață în bani, cerere adeverință
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

## Cum adaugi ceva nou (configurație, nu cod)

* **Semnal:** intrare în `signals.yaml` + funcție `@signal(id, familie, nivel)` în `retailagent/signals/` +
  pondere în `priority.yaml` + 2 teste. Scanner-ul verifică la pornire că fiecare semnal din YAML are funcție.
* **Verificare:** intrare în `checks.yaml` (treaptă, strat, produse, consimțământ) + funcție `@check(id)` în
  `checks_run.py`; adaugi id-ul la motivele care o cer.
* **Intervenție:** intrare în `retention.yaml → interventii` (tip, cost, reducere / ani, efect, condiții).
  Tipurile existente nu cer cod nou. Un buget nou pe nivel: `priority.yaml → buget_retentie_pp`.
* **Constrângere / prag:** `constraints.yaml`, `retention.yaml` (p_tinta, orizont, sigmoid, legături).

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

## Structura

```
retailagent/
  generate.py, generate_ext.py   # date sintetice + etalon (50 scenarii explicite; --n > 50 = profil statistic)
  profil.py, churn/labels.py     # profilul portofoliului realist (pydantic); eticheta de churn simulată
  common.py, config_loader.py    # utilitare; validare pydantic a celor 5 YAML-uri + verificări încrucișate
  signals/                       # registru, inflows (deducerea încasărilor), plecare, risc_credit, blocaj_proces
  scan.py, intake.py, queue.py   # Modulul 1: semnale → cazuri → coadă (schema queue.json stabilă)
  finance.py                     # anuitate, grafic, dobândă pe scenarii / orizont, OUG 50, DTI, cost mutare
  checks.py, checks_run.py       # plan după produse + motiv; execuție în trepte cu mock-uri; CLI
  retention.py, retention_menu.py# B, legături, V, p; meniu, constrângeri, optimizare; CLI
  recommend.py, approve.py       # cele 6 stări, ofertă, grafic, documente, audit; aprobarea consilierului
  explain.py, evaluate.py, evaluate_final.py, demo.py, pipeline.py
config/                          # signals, priority, checks, constraints, retention, portofoliu
data/                            # portofoliul + externe/ (mock-uri)         out/   # artefactele rulării
tests/                           # 159 teste (semnale, coadă, date, config, finance, verificări, retenție, recomandare, aprobare, explain, evaluate, pipeline, demo, portofoliu la scară)
vault/                           # jurnalul deciziilor și al taskurilor (autobot)
```
