# Regulile, constrângerile și situațiile neașteptate — cu sursa fiecăreia

Tot ce e regulă, prag, meniu sau constrângere stă în `config/*.yaml` (validat cu pydantic la pornire și la salvarea
din ecranul **Admin**). Acest document spune **de unde vine fiecare regulă** și **ce face agentul când ceva nu e
cum se aștepta**. Valorile sunt sintetice / ilustrative: hackathon pe date mock, de validat cu mentorul.

Legendă pentru coloana *sursă*: **BNR** = Regulamentul BNR nr. 17/2012 privind condițiile de creditare a
persoanelor fizice (DTI, LTV, valută); **OUG 50** = OUG 50/2010 privind contractele de credit pentru consumatori
(comision de rambursare anticipată, informare); **KYC/AML** = Legea 129/2019 (identificare, PEP); **politică
internă** = plafoane și alegeri ale băncii, aici ilustrative; **model** = alegerea noastră de modelare, din
`MODEL_FINAL.md` (vezi și „Interpretări" din README).

## 1. Constrângeri de creditare (`config/constraints.yaml`)

| regulă | valoare | cheie | sursă | unde se aplică |
|---|---|---|---|---|
| Grad maxim de îndatorare (DTI) pentru credite în lei | 40 % | `dti.max` | BNR | `capacitate_plata_actuala`, eligibilitate, meniul de intervenții |
| DTI pentru credite în valută | 20 % | `dti.max_valuta` | BNR | când clientul are rate în valută (`loans.moneda = EUR`) |
| Bonus la prima locuință | +5 pp | `dti.bonus_prima_locuinta` | BNR | credit nou ipotecar |
| Venit minim pentru o ofertă nouă | 1.500 RON/lună | `dti.venit_minim_lunar_ron` | politică internă | fără ofertă comercială sub acest venit |
| LTV maxim (ipotecar / imobiliar) | 85 % | `ltv.max` | BNR | refinanțare / credit nou pe garanție, **nu** la repricing-ul creditului existent |
| Vârsta maximă la scadență | 70 de ani | `varsta.max_la_scadenta` | politică internă | prelungirea maturității nu poate depăși vârsta |
| Marja minimă după reducere | 1,5 pp | `marja_minima_pp` | politică internă | elimină reducerile care duc marja sub prag |
| Prelungire maximă la restructurare | 60 de luni | `restructurare.prelungire_maxima_luni` | politică internă | `ajustare_maturitate` |
| Pauză de rată maximă | 6 luni | `restructurare.pauza_rata_maxima_luni` | politică internă | `pauza_rata` |
| Comision de rambursare anticipată | 1 % (fixă > 1 an), 0,5 % (fixă < 1 an), 0 % (variabilă) | `retention.yaml → oug50` | OUG 50 | costul mutării la altă bancă (B) |

Constrângerile **nu sunt o etapă vizibilă**: elimină opțiunile din meniu înainte de optimizare (MODEL_FINAL §3);
intervenția infezabilă apare în ecranul Caz cu motivul („depășește bugetul de retenție 0,2 pp pentru nivelul standard").

## 2. Prioritizare și bugete (`config/priority.yaml`)

| regulă | cheie | sursă |
|---|---|---|
| Prioritate = plecare × valoare × acțiune; riscul de credit e un canal separat (nu crește prioritatea de retenție) | `ponderi_plecare`, `valoare`, `actiune`, `risc_credit` | model |
| Benzi P1 / P2 / P3 cu SLA (termen) | `benzi`, `deadline` | politică internă |
| Expirare de dobândă fixă sub 30 de zile ⇒ P1 (cerință dură) | `semnale_active` | model (cerință din MODEL_FINAL) |
| Buget de retenție pe nivel de relație (reducere maximă de marjă) | `buget_retentie_pp: {standard 0,2 · gold 0,4 · platinum 0,6}` | politică internă |
| Blocaj de proces ⇒ `blocat` (doar verificările `blocaj.doar`) | `blocaj` | model |
| Rutare: consilier / centru de retenție / colectare | `rutare` | politică internă |

## 3. Retenție (`config/retention.yaml`)

| regulă | cheie | sursă |
|---|---|---|
| p țintă: clientul e „păstrat" dacă p_după ≤ 20 % | `p_tinta` | model |
| Orizontul lui B: 3 ani (câștigul clientului dacă pleacă, pe primii 3 ani ai graficului) | `orizont_ani` | model (interpretare; vezi README) |
| Modelul de churn: sigmoid (formula din YAML) sau antrenat (`models/churn_v1.pkl`) cu fallback | `churn` | model |
| Legături cu banca: < 0,30 ⇒ doar informare / pachet; < 0,15 ⇒ doar informare | `legaturi.min_pentru_oferta`, `min_pentru_pachet` | model (regula utilizatorului: oferta depinde de legăturile rămase) |
| Meniul celor 12 intervenții, cost = ce pierde banca | `interventii` | politică internă |
| **Buget lunar de retenție pe portofoliu**: 2.000.000 RON; ofertele se ordonează după V_reținut / cost; cele peste plafon rămân recomandate, dar **amânate** | `buget_portofoliu` | politică internă |
| Refinanțare externă deja începută ⇒ semnal activ suplimentar | `semnale_active.refinantare_externa_activ` | model |

## 4. Verificări (`config/checks.yaml`)

| regulă | cheie | sursă |
|---|---|---|
| Verificările se aleg după produse deținute + motiv; lista se afișează înainte de rulare, cu motivul fiecărei omisiuni | `verificari[].strat / produse / motive` | model (MODEL_FINAL §2) |
| Trepte: intern → ANAF → Biroul de Credit → CRC → garanție → eligibilitate; oprire la prima treaptă picată | `trepte` | model |
| Sursele externe cer consimțământ și au cost: nu se interoghează dacă motivul nu le cere | `verificari[].externa / consimtamant` | KYC/AML + politică internă |
| KYC: identitate valabilă, PEP, decedat ⇒ blocat / aprobare specială | `identitate_kyc`, `flag_blocant` | KYC/AML |
| Documentele din dosar necesare per tip de recomandare | `documente` | politică internă |

## 5. Situații neașteptate — degradare controlată (`checks.yaml → incertitudini_critice`, scenariile 51–60)

Principiul: fluxul **nu se oprește** pentru că o sursă lipsește sau datele se contrazic; cazul primește o
**incertitudine** structurată (`rec.incertitudini`), oferta devine **condiționată** (`oferta.conditii_de_confirmat`),
iar dacă incertitudinea e critică pentru tipul cererii, cazul se **escaladează la om** (`respins_escaladat`).

| situație (scenariu etalon) | ce face agentul | unde |
|---|---|---|
| 51 · credit în valută (EUR) | soldul și rata se normalizează în RON la `market.curs_eur`; DTI cu pragul de 20 %; semnal `expunere_valutara` ⇒ restructurare | `scan.normalizeaza_valuta`, `constraints.dti.max_valuta` |
| 52 · codebitor pe un credit cu risc | semnalul `codebitor_cu_risc` (familia risc_credit) din `expuneri_interne`; riscul are prioritate față de retenție | `signals/risc_credit.py`, `scan.codebitor_index` |
| 53 · două credite cu semnale contradictorii (risc + plecare) | riscul câștigă: restructurare, incertitudine `semnale_contradictorii`, retenția se reia după stabilizare | `recommend.incertitudini_caz` |
| 54 · cerere duplicată (≤ 7 zile) | o singură cerere activă + lista `duplicate` pe caz; incertitudine `cerere_duplicata` | `intake` (`zile_cerere_duplicata`) |
| 55 · client fără cont curent la noi | `sold_cont` = avertizare, fluxul continuă; incertitudine `fara_cont` | `checks_run` |
| 56 · ANAF nu răspunde | status `indisponibil` (≠ fail): venitul observat din tranzacții, ofertă **condiționată** de confirmarea venitului; pentru credit nou / majorare / refinanțare ⇒ escaladare | `incertitudini_critice.anaf_indisponibil` |
| 57 · surse contradictorii (BC vs tranzacții) | DTI cu varianta prudentă (maximul); incertitudine; credit nou ⇒ escaladare | `incertitudini_critice.surse_contradictorii` |
| 58 · client decedat | `blocat`, task de proces, nicio comunicare comercială | `flag_blocant` |
| 59 · PEP cu cerere de credit nou | `respins_escaladat` cu „aprobare specială" | KYC/AML |
| 60 · refinanțare externă deja începută | BC arată credit nou la altă bancă de aceeași sumă; semnal activ suplimentar, incertitudine `refinantare_externa_in_curs` | `retention.semnale_active` |

Fiecare situație are un test în `tests/test_situatii.py`; etalonul (`python -m retailagent.generate --n 60`) le
conține pe toate și evaluarea le verifică recomandarea și incertitudinile așteptate.

## 6. Bucla de feedback și versionarea (`retailagent/feedback.py`, `retailagent/versiune.py`)

| regulă | unde |
|---|---|
| Agentul recomandă, **omul decide**: aprobă / modifică / respinge cu motiv; override-ul intră în audit cu autorul (`consilier`) | `approve.decide`, `config/echipa.yaml` |
| Rezultatul la 90 de zile (`ramas` / `plecat`) se înregistrează pe ultima decizie a cazului | `approve.inregistreaza_rezultat`, `POST /api/cazuri/{id}/rezultat` |
| Raportul de feedback: rata de override pe intervenție / nivel / produs / consilier, rămânere reală vs prezisă, **propuneri** de ajustare (sugestii, nu se aplică automat) | `python -m retailagent.feedback`, `GET /api/feedback`, Dashboard |
| Fiecare recomandare, rând de audit și evaluare poartă versiunea: hash SHA-256 al YAML-urilor + versiunea și hash-ul modelului + commit-ul de cod | `versiune_completa`, `GET /api/metrici/context` |
| Reantrenarea pe rezultate reale: `churn.train --din-approvals` | `retailagent/churn/train.py` |

## 7. Ce nu face agentul (limite asumate)

* Nu ia decizia comercială: fără aprobarea consilierului nu se comunică nicio ofertă.
* Nu interoghează surse externe fără motiv și consimțământ; nu ocolește KYC/AML.
* Nu acordă credit nou fără venit confirmat (ANAF indisponibil ⇒ escaladare).
* Nu schimbă singur pragurile: propunerile din feedback sunt sugestii pentru om, aplicate din Admin, cu validare.
