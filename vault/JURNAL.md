# Jurnal per task

## M0 — bootstrap (2026-10-28)
- git init, remote origin, .gitignore, vault inițializat; baseline 66 teste verzi, compileall OK.

## M1-T1 — finance.py (done)
- `rata_anuitate`, `luni_ramase`, `grafic`, `dobanda_totala`, `segmente_credit`, `comision_rambursare_anticipata`,
  `dti`, `varsta_la`; generator comun `_iter_scenariu` (re-amortizare la fiecare schimbare de dobândă).
- 7 teste în `tests/test_finance.py` (anuitate pe caz cunoscut, grafic stinge soldul, re-amortizare, OUG 50).
- Lecție: în heredoc-uri bash, `\N` din `C:\dev\NEXXT` sparge string-urile Python → scripturile se scriu în fișier.
