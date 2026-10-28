# Jurnal per task

## M0 — bootstrap (2026-10-28)
- git init, remote origin, .gitignore, vault inițializat; baseline 66 teste verzi, compileall OK.

## M1-T1 — finance.py (done)
- `rata_anuitate`, `luni_ramase`, `grafic`, `dobanda_totala`, `segmente_credit`, `comision_rambursare_anticipata`,
  `dti`, `varsta_la`; generator comun `_iter_scenariu` (re-amortizare la fiecare schimbare de dobândă).
- 7 teste în `tests/test_finance.py` (anuitate pe caz cunoscut, grafic stinge soldul, re-amortizare, OUG 50).
- Lecție: în heredoc-uri bash, `\N` din `C:\dev\NEXXT` sparge string-urile Python → scripturile se scriu în fișier.

## M1-T2 — constraints.yaml + retention.yaml + modele pydantic (done)
- `ConstraintsConfig` (dti, ltv, varsta, marja_minima_pp, restructurare), `RetentionConfig` (p_tinta, sigmoid a/b/c/d,
  B_referinta, semnale_active, legaturi, valoare, piata, 12 intervenții, oug50), `Config` are acum 4 config-uri.
- Validări: id-uri duplicate, p_tinta ∈ (0,1), chei de piață din `CHEI_PIATA`, tip intervenție din enum,
  ponderile legăturilor însumează 1, semnalele referite există, nivelurile au buget în priority.yaml.
- 5 teste în `tests/test_config_final.py` (copie a config-ului în tmp + rescriere YAML pentru cazurile negative).
- `checks.yaml` se adaugă la M2-T1 (câmp nou în `Config`, cu același tipar).

## M1-T3 — scenariul 14 = cazul opus lui C0013 (done)
- `S.ani_client` (vechimea relației, aplicată după apelul rng ca fluxul aleator să rămână identic),
  `plant.cont_nefolosit` (ieșirile din ultimele 2 luni se filtrează în `tx()`, tot fără să atingă rng),
  scenariul 14: salariu mutat la altă bancă, standard, 1 produs, 1,5 ani vechime → GT `nu_interveni`.
- ANAF pentru C0014 arată salariul în continuare (`anaf: salariu_continua`); `venit_disparut` plantat la 2 clienți.
- Metricile Modulului 1 rămân 100% (verificat cu `evaluate`); suita completă verde.
- Lecție: orice plantare nouă în generator trebuie să nu schimbe numărul de apeluri rng, altfel se mută
  valorile tuturor clienților următori.

## M2-T1 — checks.yaml + ChecksConfig (done)
- 18 verificări pe 5 trepte (intern, anaf, biroul_credit, crc, garantie), straturi baza / produs / motiv,
  `necesita_consimtamant` pentru ANAF și BC, `parametri` per verificare.
- `motive`: chei = semnale + tipuri de cereri + `risc` + `blocaj` (validat încrucișat în `Config`);
  `blocaj.doar = [identitate_kyc]`; `adauga` câștigă în fața lui `sare` (regula se aplică în M2-T2).
- `documente_necesare` per tip de recomandare (valabil / max_zile / tipologii / produse).
- 4 teste noi în `tests/test_config_final.py`.

## M2-T2 — checks.py: plan_checks (done)
- `motive_caz` (blocaj, risc, cereri, semnale — în această ordine) și `plan_checks(case, client, loans, cereri, cfg)`
  → `{motive, produse_detinute, plan[{id, treapta, externa, motiv}], omise[...], interogari_externe{planificate,
  rulare_tot, evitate_vs_tot}}`. Produsele deținute = toate creditele clientului, nu doar cel din caz.
- Baseline „rulează tot" = toate verificările externe aplicabile (produs + consimțământ).
- 6 teste în `tests/test_checks_plan.py` (expirare, simulare, credit nou, risc + adauga>sare, blocaj, consimțământ).
