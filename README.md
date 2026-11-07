# Knowledge Distillation and Local-Cloud Deployment of a Command-Parsing LM

**CS3081 Cloud Computing - Mini Project** | Royal Sachan | Roll no. 230101021

| | |
|---|---|
| GitHub repository | https://github.com/mars-alien/cloud-command-parser |
| Model assets (GitHub Releases) | https://github.com/mars-alien/cloud-command-parser/releases (`model-v1`, `model-v2`) |
| CI runs | https://github.com/mars-alien/cloud-command-parser/actions |
| Report / evidence / AI use | `report/report.pdf` / `results/` / `AI_USE.md` |

## What this project does

A tiny voice-assistant command parser: one English command in, one JSON object out
(`{"intent", "date", "time", "place"}`, 8 intents). A large teacher model labels the data, a 70M-parameter student learns from those labels (sequence-level knowledge distillation), and the student is served from a local Kubernetes cluster.

```
commands_pool.jsonl (3,000, SLURP)
        |  SeaweedFS (bucket: datasets)
        v
 2 parallel k8s workers  --->  Ollama + phi3.5 teacher (temp 0, seed 42)
        |  datasets/teacher/shard-{0,1}.jsonl
        v
 worker/clean.py  -->  datasets/v1/train.jsonl + train.sha256
        v
 training/train.py (Pythia-70M, CPU)  -->  models/v1, models/v2 (bucket) + GitHub Releases
        v
 FastAPI service (Docker, CPU torch) <-- downloads weights from SeaweedFS at start-up
        v
 k3d / Kubernetes: Deployment (2 replicas) + Service + Traefik Ingress + HPA (1-2)
```

## Repository layout

| Path | Contents |
|---|---|
| `cluster/k3d.yaml` | k3d cluster config (Ingress and S3 ports) |
| `k8s/` | namespaces, SeaweedFS, worker Job, app Deployment/Service/Ingress, HPA |
| `prompts/teacher_prompt.txt` | teacher prompt |
| `worker/` | labelling worker, `clean.py`, worker Dockerfile |
| `training/` | `train.py`, `config.yaml`, `evaluate.py`, `eval_teacher.py`, `loss.csv` |
| `service/` | FastAPI app, `requirements.txt`, Dockerfile |
| `common/` | shared code (prompt format, post-processing, schema check, S3, teacher client) |
| `network/` | `subnets.md`, `nacl.json`, sample packets |
| `scripts/` | `dev.py` (cluster/deploy), `task4.py`, `perf.py`, `docker_limits.py`, `build_report.py`, `package_submission.py` |
| `tests/`, `.github/workflows/ci.yml` | unit tests, CI pipeline |
| `data/`, `tools/` | course kit (validation set, schema, rate card, `score.py`, Locust file, NACL simulator) |
| `results/` | logs, score reports, Locust output, command output (evidence) |

## Prerequisites (Windows 10/11, VS Code, PowerShell)

Docker Desktop (WSL2 backend, running), Python 3.11, Git, then:

```powershell
winget install Kubernetes.kubectl
winget install k3d.k3d              # or: choco install k3d
winget install Ollama.Ollama
winget install GitHub.cli           # for releases
choco install make                  # optional; otherwise run the python commands from the Makefile
python -m venv .venv ; .\.venv\Scripts\Activate.ps1
pip install -r requirements-dev.txt
```

Let the worker Pods reach Ollama on the laptop: `setx OLLAMA_HOST 0.0.0.0`, quit and restart Ollama, then `ollama pull phi3.5`.

## Quick start (fresh clone)

Needs the GitHub Releases `model-v1` and `model-v2` to exist.

```powershell
make up        # cluster + SeaweedFS + buckets + data/models restore + image build + deploy
curl.exe -X POST http://localhost:8081/parse -H "Content-Type: application/json" -d "{\"text\": \"what is the weather in london\"}"
make down      # delete the cluster
```

Expected answer: `{"intent":"weather_query","date":null,"time":null,"place":"london"}` with headers `X-Model-Version` and `X-Served-By`.

## Full workflow (how the evidence in `results/` was produced)

| Task | Commands |
|---|---|
| **1** Storage + labelling | `make infra` -> `make label` (hours; follow with `kubectl -n pipeline logs -f -l job-name=teacher-labelling --prefix`) -> `make clean-data` |
| **2** Distillation | `make train SUBSET=50` (smoke test) -> `make train` -> `make train-v2` -> `make upload-model VERSION=v1` / `v2` -> `make teacher-eval` -> `make eval-all` -> `gh release create model-v1 dist/model-v1.zip` / `model-v2 dist/model-v2.zip` |
| **3** Container | `make build` -> `python scripts/docker_limits.py` (50 requests at 1 CPU / 1 GiB, peak memory) -> `python scripts/docker_limits.py fault` (expects HTTP 500 `invalid_model_output`) |
| **4** Kubernetes | `python scripts/dev.py app` -> `python scripts/task4.py` with `endpoints`, `rolling`, `recovery`, `coldstart`, `lb`, `hpa` |
| **5** Network | `python tools/nacl_sim.py network/nacl.json network/packets_sample.jsonl --check` (working in `network/subnets.md`) |
| **6** CI/CD | push; Actions -> `ci` -> Run workflow with `model=baseline` (fails at the quality gate); save the run URL in `results/ci_failed_run.txt` |
| **7** Performance | `python scripts/task4.py lb` -> `python scripts/perf.py` -> `make report` |

No `make`? Every target is one Python command; see the `Makefile`.

Checksums: `Get-FileHash dist\model-v1.zip -Algorithm SHA256` must equal `models_out/v1/model.sha256`; `data/train.sha256` is the hash of `data/train.jsonl`.

## Testing and CI

`make lint` (ruff) and `make test` (pytest: cleaner, post-processing, service endpoints, fault injection, NACL file). GitHub Actions runs lint -> unit tests -> model evaluation (downloads `model-v1.zip` from the Release, runs `score.py` on `validation.jsonl`) -> quality gate (`score.py --min-validity 95`), plus a `gitleaks` secret scan.

## Design notes

- **Reproducible data:** shards are split by `line_number % SHARD_COUNT`; `clean.py` is deterministic and writes LF-only bytes, so the SHA-256 is identical on Windows and Linux. Teacher replies are stored exactly as generated.
- **No secrets in Git:** S3 keys are generated at `make up` into the git-ignored `.secrets/` folder and injected as Kubernetes Secrets.
- **No weights in Git or in the image:** the service downloads `MODEL_URI` from SeaweedFS at start-up; `/readyz` returns 503 until the model is loaded.
- **Single-node limitation:** the cluster runs on one laptop, so it shows self-healing and rolling updates but not fault tolerance across machines.

## Troubleshooting (Windows)

| Problem | Fix |
|---|---|
| `make` is not recognized | `choco install make`, reopen the terminal, or run the Python commands directly |
| Pods cannot reach Ollama | set `OLLAMA_HOST=0.0.0.0` and restart Ollama; check the Ollama URL in `k8s/worker-job.yaml` |
| `SeaweedFS S3 not reachable on localhost:8333` | wait for the pod (`kubectl -n data get pods`), confirm port 8333 is free and Docker Desktop is running |
| Port 8080/8081 already in use | change the host port in `cluster/k3d.yaml`, recreate the cluster, and use the same port in `scripts/task4.py` and `scripts/perf.py` |
| Labelling is slow | CPU-only Ollama is slow; the workers resume from saved progress, so a restart loses nothing |

## Submission checklist

1. `report/report.pdf` (`make report`, at most 8 pages) and `results/` evidence.
2. Scanned handwritten reflection at `reflection/230101021.pdf`.
3. Model files only as GitHub Release assets (never committed).
4. Tag the final commit: `git tag final` then `git push --tags`.
5. `make package` -> `submission/230101021.zip` (report, reflection, source, this README).
