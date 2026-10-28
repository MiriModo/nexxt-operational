# Plan de execuție — retailagent: model final (verificări + retenție + recomandare)

## Obiectiv
Platforma `retailagent` devine funcțională cap-coadă conform `MODEL_FINAL.md`: portofoliu → scan semnale →
coadă → verificări alese după produse + motiv → model de retenție (cea mai ieftină implicare) → recomandare
→ aprobare cu log de audit → explicație în română → metrici (cifra-vedetă: costul retenției cu agentul vs.
„aceeași reducere pentru toți") → demo HTML. Totul rulează local, determinist, din JSON/YAML, fără servicii
externe. După acest plan utilizatorul începe modificările pe o platformă care merge.

## Decizii și constrângeri stabilite
- **Referința** e `MODEL_FINAL.md` (28 oct 2026). Modulul 1 (scan + coadă) e gata și are 66 de teste verzi;
  schema `out/queue.json` (§5 din spec-ul Modulului 1) **nu se schimbă**. Metricile Modulului 1 trebuie să
  rămână 100% (F1 detecție, benzi, acțiuni, pairwise, 0 încălcări, 5/5 capcane).
- **Stack:** Python 3.11+, doar `pyyaml`, `pydantic`, `pytest` (vezi `requirements.txt`). Fără DB, fără
  servicii externe, fără dependențe noi. Comenzi `python -m retailagent.<modul>`. Texte pentru utilizator
  în română, cu diacritice. `setup_console()` la fiecare CLI (consola Windows).
- **Principiu YAML:** orice regulă, pondere, prag, meniu de intervenții, constrângere sau listă de
  verificări stă în `config/*.yaml`, validat cu pydantic în `config_loader.py`. Un semnal / verificare /
  intervenție nou(ă) = configurație, nu cod. Codul pur (fără I/O) e separat de CLI.
- **Determinism:** același seed → aceleași fișiere; timestamp-urile din pipeline sunt `<azi>T00:00:00`
  (doar aprobările umane folosesc ora reală).
- **B (câștigul clientului dacă pleacă)** se calculează pe graficul de rambursare (`finance.py`), nu literal:
  B = dobânda rămasă la noi (post-expirare / curentă) − dobânda rămasă la dobânda pieței − costul mutării.
  Dobânzile de piață și costurile mutării vin din `data/market.json` (`dobanzi_piata`, `costuri_mutare`).
- **Factorul `actiune` din coadă rămâne** proxy-ul ieftin existent (grilă vs buget), pentru că coada rulează
  înainte de verificări. Decizia reală o dă modelul de retenție după verificări.
- **p = sigmoid(a·B_norm + b·semnale_active − c − d·legaturi)**, parametri în `config/retention.yaml`;
  `p_tinta = 0.20`. **Legăturile cu banca** (produse active, vechime, nivel, activitate pe cont) intră în
  model: un client fără legături (`legaturi < min_pentru_oferta`) primește doar informare sau o ofertă
  condiționată de aducerea salariului (pachet); un client fidel primește reducere / perioadă fixă nouă.
  (Regula utilizatorului: „oferta se face în funcție de ce alte legături are cu banca, dacă mai e fidel.")
- **Salariu mutat ≠ risc de credit:** dacă salariul lipsește, dar ratele sunt acoperite din transferuri
  proprii, `venit_disparut` nu se declanșează și `salariu_mutat` = 1.0 (semnal activ → P1 +
  `retentie_refinantare`). Implementat deja în Modulul 1; modelul de retenție îl respectă.
- **Date:** scenariul 14 din `generate.py` devine cazul opus lui C0013: salariu mutat la altă bancă
  (`salariu_mutat: "alta_banca"`), standard, 1 produs, vechime mică (câmp nou `S.ani_client`, aplicat după
  apelul rng ca să nu schimbe fluxul aleator), cont aproape nefolosit → recomandarea așteptată
  `nu_interveni` (informare). Portofoliul rămâne la 50 de clienți; `venit_disparut` rămâne plantat la
  C0012 și C0015. Etalonul (`FINAL` din `generate_ext.py`) se actualizează în consecință.
- **Optimizarea retenției:** dintre intervențiile fezabile (constrângerile elimină înainte), cea cu cost
  minim pentru care `p_după ≤ p_tinta` **și** `cost ≤ p_înainte × V`. Dacă nu există: `informare` dacă
  `p_înainte ≥ p_tinta`, altfel `nu_interveni`. Risc de credit ≥ 0.7 → doar intervenții de restructurare.
  Blocaj activ → nicio intervenție (cazul rămâne „blocat").
- **Recomandarea** e una din: `nu_interveni` (include „doar informare") | `oferta_minima` | `oferta_produs`
  (pachet cu salariul) | `restructurare` | `respins_escaladat` (o verificare externă a picat) | `blocat`
  (task de proces; al 6-lea status, documentat). Consilierul aprobă / modifică / respinge **cu motiv**;
  override-ul intră în `out/audit.jsonl`.
- **Verificările** se aleg din strat de bază + strat produse deținute + strat motiv (adaugă / sare), din
  `config/checks.yaml`; rulează în trepte `intern → anaf → biroul_credit → crc → garantie` și se opresc la
  primul pas picat. Lista se afișează **înainte** de rulare, cu motivul fiecărei includeri și omisiuni.
  Mock-urile externe sunt `data/externe/*.json`. Metrică: interogări externe evitate față de „rulează tot".
- **Cifra-vedetă:** costul total al retenției cu agentul vs. cea mai mică reducere uniformă de marjă
  (0,2 / 0,4 / 0,6 pp pentru toți candidații la retenție) care obține cel puțin aceeași rată de rămânere.
  Rata de rămânere se simulează cu `ground_truth.comportament` (ascuns agentului): clientul pleacă dacă
  câștigul net după intervenția noastră depășește `prag_castig_plecare_ron`; `informare` îl ține doar dacă
  `reactioneaza_la_informare`; pachetul doar dacă `accepta_pachet_salariu`.
- **Demo:** pagină HTML statică `out/demo.html` generată din JSON-uri (vanilla JS, fără CDN, fără
  dependențe): metrici → coadă → caz (semnale, verificări, meniu de intervenții, recomandare, explicație,
  butoane de aprobare care afișează comanda `approve` echivalentă).
- **Performanță:** `scan → intake → queue → checks → retention → recommend` pe 50 de clienți în < 5 s.
- **Git:** repo local în `C:\dev\NEXXT`, remote `origin = https://github.com/MiriModo/nexxt-operational.git`
  (gol). `.gitignore`: `out/`, `__pycache__/`, `.pytest_cache/`, `*.zip`, `*.pdf`. Un commit per task,
  mesaj `[task-id] descriere`, apoi `git push origin main`; dacă push-ul pică (autentificare), se continuă
  cu commit-uri locale și se raportează.
- **Fără întrebări în Faza B.** Ambiguitățile se rezolvă autonom, aliniat cu MODEL_FINAL.md și cu lista de
  mai sus, și se consemnează în `vault/DECIZII.md` + README („Interpretări").
- **Teste:** `python -m pytest -q -p no:anyio` (toate verzi, inclusiv cele 66 existente). Lint/build:
  `python -m compileall -q retailagent tests`. TDD: testele taskului se scriu înainte de cod.

## Milestone 1: Fundație (calcule financiare, config, date)
- [x] M1-T1 `retailagent/finance.py` — Acceptance criteria: funcții pure `rata_anuitate`, `luni_ramase`,
  `grafic(sold, segmente, luna_start)`, `dobanda_totala(sold, segmente)`, `segmente_credit(loan, today, market)`
  (curentă până la expirarea fixei, apoi IRCC + marjă), `comision_rambursare_anticipata` (OUG 50: 0 la
  variabilă; la fixă 1% peste 1 an rămas / 0,5% sub), `dti`, `varsta_la`; teste `tests/test_finance.py`:
  anuitatea pe un caz cunoscut (±0,01), graficul stinge soldul, dobânda totală = suma coloanei din grafic,
  schimbarea de dobândă re-amortizează, comisionul 0 la variabilă.
- [x] M1-T2 `config/constraints.yaml` + `config/retention.yaml` + modele pydantic în `config_loader.py`
  (`Config` primește `constraints`, `retention`, `checks`; `load_config` le încarcă; validări: intervenții cu
  id unic, `p_tinta ∈ (0,1)`, chei de piață existente) — Acceptance criteria: `load_config()` întoarce cele
  3 config-uri noi; un YAML cu id duplicat de intervenție ridică `ValueError`; testele existente rămân verzi.
  Conținut minim: DTI 40% (+5 pp prima locuință), LTV max 0,85, vârstă max la scadență 70, marjă minimă
  1,5 pp; retenție: `p_tinta`, sigmoid a/b/c/d, `B_referinta_ron`, `semnale_active`, `legaturi`
  (ponderi, `min_pentru_oferta`), `valoare.produse_ron_pe_an`, `piata[produs] → cheie`, meniul de 12
  intervenții (nu_interveni, informare, scutire_comision, reducere 0,2/0,4/0,6, fix 1/3/5 ani,
  pachet_salariu, ajustare_maturitate, pauza_rata) cu cost/efect/necesita, `oug50`.
- [x] M1-T3 Date: scenariul 14 = caz opus (salariu mutat, fără legături), câmp `S.ani_client`, etalon
  `FINAL[14] = nu_interveni`, `FINAL[13] = oferta_produs`; `tests/test_data_ext.py` actualizat —
  Acceptance criteria: `generate` produce 50 clienți; C0014 are `salariu_mutat` = 1.0 și **nu** are
  `venit_disparut`; C0014 are `nivel_relatie = standard`, un singur produs atașat, `client_din` ≤ 2 ani;
  `venit_disparut` plantat la exact 2 clienți; toate testele existente verzi; metricile Modulului 1 rămân
  100% (`python -m retailagent.evaluate`).

## Milestone 2: Verificări după produse deținute + motiv
- [x] M2-T1 `config/checks.yaml` + model pydantic — Acceptance criteria: definește `trepte`
  (`intern, anaf, biroul_credit, crc, garantie`), lista de verificări (id, treapta, externa, strat:
  `baza | produs:<produs> | motiv`, descriere, parametri), maparea `motive` (chei = id-uri de semnale,
  tipuri de cereri, `risc`, `blocaj`) cu `adauga` / `sare`, și `documente_necesare` per tip de
  recomandare; validare: fiecare id din `adauga`/`sare` există; test de încărcare.
- [x] M2-T2 `retailagent/checks.py` — planificare — Acceptance criteria: `plan_checks(case, ctx, cfg)`
  întoarce `{motive, plan: [{id, treapta, externa, motiv_includere}], omise: [{id, motiv_omitere}]}`;
  reguli: baza mereu; strat produs după produsele deținute ale clientului; motivele adaugă/sar
  (`adauga` câștigă în fața lui `sare`); blocaj activ → doar `identitate_kyc`, restul omise cu motivul
  „blocat de <x>"; risc ≥ 0.7 → adaugă `capacitate_plata_actuala`, sare `scenarii_rata`/`cost_mutare`;
  teste pe 5 cazuri construite de mână (expirare, simulare rambursare, credit nou, întârziere, CI expirată).
- [x] M2-T3 `retailagent/checks.py` — execuție în trepte + CLI — Acceptance criteria: `run_checks(plan, ctx,
  mocks, cfg)` rulează verificările în ordinea treptelor, se oprește la prima treaptă cu `fail`, marchează
  restul `neexecutat (oprit la <treaptă>)`; fiecare verificare întoarce `{id, status: ok|avertizare|fail|
  neexecutat, dovada, detalii, sursa}`; concluzii agregate (`venit_lunar`, `dti_curent`, `ltv_actual`,
  `interogari_bc`, `salariu_la_alta_banca`, `eligibil`, `motiv_ineligibil`); contor
  `interogari_externe: {planificate, executate, evitate_vs_tot}`; `python -m retailagent.checks` scrie
  `out/checks.json` și afișează pentru fiecare caz lista planificată cu motive **înainte** de rezultate;
  pe datele generate: C0046 pică la `biroul_credit`, C0047 la `crc`, C0005 la `garantie`; C0013 primește
  `salariu_la_alta_banca = true` (ANAF arată același angajator); clienții fără consimțământ nu primesc
  interogări externe (omise cu motiv).

## Milestone 3: Model de retenție
- [x] M3-T1 `retailagent/retention.py` — B, p, V, legături — Acceptance criteria: `castig_plecare(loan, ctx,
  cfg)` = B din grafice (cu descompunerea: dobândă la noi, dobândă piață, cost mutare); `legaturi(client,
  ctx, cfg)` ∈ [0,1] cu componente; `valoare_client(loan, client, cfg)` = marjă × sold × ani + produse;
  `prob_plecare(B, semnale_active, legaturi, cfg)` cu sigmoid; teste: B > 0 pentru C0001 (gap 3 pp pe
  400k) și B ≈ 0 pentru un card; legături mai mari pentru C0013 decât pentru C0014; p crește cu B și
  scade cu legăturile.
- [x] M3-T2 `retailagent/retention.py` — meniu + constrângeri + optimizare — Acceptance criteria:
  `evalueaza_interventii(...)` întoarce pentru fiecare intervenție `{id, fezabil, motiv_infezabil, cost,
  B_dupa, p_dupa, respecta_tinta, merita (cost ≤ p×V)}`; costul reducerii de marjă și al perioadei fixe
  noi se calculează din grafice; constrângerile (marjă minimă, buget pe nivel, vârstă la scadență pentru
  prelungire, DTI pentru pachet/credit nou, LTV) elimină înainte; `alege_interventie(...)` aplică regula
  de optimizare din „Decizii”; risc → doar restructurare; legături sub prag → doar informare/pachet;
  teste: C0027 (pensionar, 86 ani la scadență) nu primește `ajustare_maturitate`; un client standard nu
  primește reducere 0,4; un client cu risc nu primește reducere.
- [x] M3-T3 CLI `python -m retailagent.retention` → `out/offers.json` — Acceptance criteria: un rând per
  caz din coadă cu `{case_id, B, p, V, legaturi, interventie_aleasa, alternative (top 3 după cost),
  explicatie}`; text de forma „Clientul ar câștiga 41.200 RON plecând; p = 68%. Oferta minimă care îl
  aduce sub 20%: … cost … față de … valoare pierdută. Alternativa …”; pe date: C0013 → `pachet_salariu`,
  C0014 → `informare`, C0004 → `nu_interveni`, cazurile cu risc → restructurare; timp < 1 s.

## Milestone 4: Recomandare, aprobare, audit
- [x] M4-T1 `retailagent/recommend.py` — Acceptance criteria: `recomanda(case, checks, offer, cfg)` →
  una din cele 6 stări (vezi Decizii) + `oferta` (dobândă nouă, rată nouă, perioadă, cost bancă, economie
  client), `grafic` (primele 12 rânduri + total), `documente_lipsa` (din `documente.json` vs
  `checks.documente_necesare`), `explicatie` în română cu cifre și sursa; `out/recommendations.json`;
  `out/audit.jsonl` cu un rând per semnal / verificare / decizie (`tip, cheie, valoare, sursa, timestamp`);
  teste: acuratețea recomandării față de `recomandare_asteptata` ≥ 90% pe cei 49 de clienți din coadă;
  `verificare_picata_asteptata` corectă pentru C0005/C0046/C0047; 0 oferte pentru risc ≥ 0.7; 0 oferte pe
  cazuri blocate.
- [x] M4-T2 `python -m retailagent.approve <case_id> [--decizie aproba|modifica|respinge]
  [--interventie id] [--motiv "..."]` — Acceptance criteria: `aproba` fără motiv merge; `modifica` /
  `respinge` fără `--motiv` ies cu eroare clară; scrie `out/approvals.json` (append, idempotent pe
  `case_id` + timestamp real) și un rând `override` / `aprobare` în `audit.jsonl`; afișează oferta,
  graficul și documentele lipsă; o intervenție inexistentă sau infezabilă e refuzată cu motiv; teste.

## Milestone 5: Explicație și evaluare
- [x] M5-T1 `explain` extins — Acceptance criteria: după secțiunile existente apar `── Verificări`
  (plan cu motive, rezultate, unde s-a oprit), `── Retenție` (B descompus, legături, p, V, tabel cu
  intervențiile: cost / p_după / fezabil / motiv), `── Recomandare` (textul final + documente lipsă);
  rulează pentru orice caz din coadă fără excepție (test existent extins).
- [x] M5-T2 `evaluate` extins — Acceptance criteria: secțiune nouă „Model final” cu: cifra-vedetă (cost
  agent vs. cost reducere uniformă la aceeași rată de rămânere, cu rata simulată din `comportament`),
  procent cazuri `nu_interveni`, interogări externe evitate (total și %), acuratețe recomandări (matrice
  de confuzie 6×6), verificări picate corect, cerințe dure noi (0 oferte către risc activ, 0 oferte în
  afara limitelor — re-verificate prin constrângeri, toate expirările < 30 zile în P1); `out/evaluation.json`
  conține secțiunea; metricile Modulului 1 neschimbate; `tests/test_evaluate_final.py`.

## Milestone 6: Pipeline, demo, documentație
- [x] M6-T1 `python -m retailagent.pipeline` (scan → intake → queue → checks → retention → recommend →
  evaluate → demo, cu `--skip-evaluate`) — Acceptance criteria: o singură comandă produce toate fișierele din
  `out/`; timp total pe 50 de clienți < 5 s fără evaluate; `explain`, `approve`, `evaluate` folosesc
  aceeași funcție `run_full()` ca să nu dubleze logica; test de integrare.
- [ ] M6-T2 `python -m retailagent.demo` → `out/demo.html` — Acceptance criteria: pagină statică
  autonomă (JSON-urile încorporate, fără rețea), cu: antet cu metricile-vedetă; tabelul cozii (bandă,
  prioritate, termen, motiv, acțiune, recomandare) cu filtre pe bandă; panou caz: semnale cu dovezi,
  verificări (planificate / omise / rezultate), meniul de intervenții cu costuri și p_după, recomandarea și
  explicația, documentele lipsă, butoane Aprobă / Modifică / Respinge care afișează comanda `approve`
  echivalentă; se deschide corect în browser (verificat cu un parser HTML în test: fără `<script src>`
  extern, dimensiune < 5 MB).
- [ ] M6-T3 README + zip final — Acceptance criteria: README descrie setup-ul în 3 comenzi, toate comenzile,
  fluxul complet, formulele (B, p, V, optimizare), tabelul de interpretări extins, structura; o persoană
  nouă rulează tot în < 5 minute; `python -m pytest` verde; arhiva `NEXXT_retailagent_<data>.zip` refăcută
  (fără `out/`? NU — cu `out/` inclus, fără cache și fără PDF); commit + push final.
