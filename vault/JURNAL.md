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
