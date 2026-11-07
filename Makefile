# Thin wrapper: every recipe is one portable command (works with GNU make on Windows: `choco install make`).
PY ?= python

.PHONY: up down infra label clean-data train train-v2 upload-model lint test build eval-all teacher-eval report package

up:            ## build + deploy the whole system from a fresh clone
	$(PY) scripts/dev.py up
down:          ## delete the cluster
	$(PY) scripts/dev.py down
infra:
	$(PY) scripts/dev.py infra
label:         ## run the two teacher workers (Ollama must be running)
	$(PY) scripts/dev.py label
clean-data:    ## shards -> data/train.jsonl + train.sha256 (+ bucket datasets/v1/)
	$(PY) worker/clean.py
train:         ## make train  |  make train SUBSET=50
	$(PY) training/train.py $(if $(SUBSET),--subset $(SUBSET),)
train-v2:
	$(PY) training/train.py --version v2
upload-model:  ## make upload-model VERSION=v1
	$(PY) scripts/dev.py upload-model --version $(or $(VERSION),v1)
build:
	docker build -t parser-service:1.0 -f service/Dockerfile .
lint:
	$(PY) -m ruff check .
test:
	$(PY) -m pytest -q
teacher-eval:
	$(PY) training/eval_teacher.py
eval-all:
	$(PY) training/evaluate.py --model EleutherAI/pythia-70m --name untrained
	$(PY) training/evaluate.py --model models_out/v1 --name student_v1
	$(PY) training/evaluate.py --model models_out/v2 --name student_v2
report:
	$(PY) scripts/build_report.py
package:
	$(PY) scripts/package_submission.py
