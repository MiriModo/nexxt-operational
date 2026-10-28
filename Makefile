# Comenzile uzuale. Pe Windows fără `make`: rulează comenzile de sub fiecare țintă (sunt aceleași ca în README).
PY ?= python
N ?= 10000

.PHONY: help setup data train demo api ui types test docker docker-down clean

help:
	@echo "make setup   - pip install + npm install"
	@echo "make demo    - date (daca lipsesc) + flux complet + out/demo.html + snapshot pentru UI"
	@echo "make api     - API-ul FastAPI pe :8000 (ruleaza fluxul la pornire)"
	@echo "make ui      - interfata React pe :5173 (cu API pornit separat; altfel snapshot static)"
	@echo "make types   - tipuri TypeScript din OpenAPI (API pornit)"
	@echo "make test    - suita pytest"
	@echo "make docker  - docker compose up --build (UI :8080, API :8000)"

setup:
	$(PY) -m pip install -r requirements.txt
	cd ui && npm install

data/clients.json:
	$(PY) -m retailagent.generate --n $(N)

data: data/clients.json

models/churn_v1.pkl: data/clients.json
	$(PY) -m retailagent.churn.labels
	$(PY) -m retailagent.churn.train

train: models/churn_v1.pkl

demo: data/clients.json models/churn_v1.pkl
	$(PY) -m retailagent.pipeline
	@echo "deschide out/demo.html in browser"

api: data/clients.json models/churn_v1.pkl
	$(PY) -m retailagent.api

ui:
	cd ui && npm run dev

types:
	cd ui && npm run types

test:
	$(PY) -m pytest -q -p no:anyio

docker:
	docker compose up --build

docker-down:
	docker compose down

clean:
	rm -rf out ui/dist ui/public/data .pytest_cache
