# ENV — comenzi de mediu (sursa canonică pentru GATE, PAS 3)

- Director: `C:\dev\NEXXT` (Windows 11, Python 3.12.10, Git Bash)
- Dependențe: `pip install -r requirements.txt` (pyyaml, pydantic, pytest)
- **Teste:** `python -m pytest -q -p no:anyio` — baseline la bootstrap: **66 passed**
- **Build/lint:** `python -m compileall -q retailagent tests`
- **Regresie Modul 1:** `PYTHONIOENCODING=utf-8 python -m retailagent.evaluate` → F1 1.00, benzi 100%, acțiuni 100%, 708/708, 0 încălcări, 5/5 capcane
- Regenerare date: `python -m retailagent.generate --n 50 --seed 42`
- Lanț Modul 1: `python -m retailagent.scan && python -m retailagent.queue`
- Consola Windows: prefixează cu `PYTHONIOENCODING=utf-8` când afișezi diacritice din Python.
- Git: `origin = https://github.com/MiriModo/nexxt-operational.git`, branch `main`, 1 commit per task + push.
