#!/bin/sh
# Pornirea API-ului în container: date → model → flux (în api) → servire.
set -e
cd /app

N="${RETAILAGENT_N:-10000}"
if [ ! -f data/clients.json ]; then
  echo "[entrypoint] data/ lipsește: generez portofoliul (--n $N, seed 42)…"
  python -m retailagent.generate --n "$N"
fi
if [ ! -f models/churn_v1.pkl ]; then
  echo "[entrypoint] models/churn_v1.pkl lipsește: etichete + antrenare…"
  python -m retailagent.churn.labels
  python -m retailagent.churn.train
fi
echo "[entrypoint] pornesc API-ul (fluxul rulează la pornire, ~45 s pe 10.000 de clienți)"
exec python -m retailagent.api --host 0.0.0.0 --port 8000
