# Knowledge distillation + local-cloud deployment of a command-parsing LM (CS3081 mini project)

Royal Sachan, roll no. 230101021

- GitHub repository: https://github.com/mars-alien/cloud-command-parser
- Releases (model assets): https://github.com/mars-alien/cloud-command-parser/releases (`model-v1`, `model-v2`)
- CI runs: https://github.com/mars-alien/cloud-command-parser/actions
- Report: `report/report.pdf` - Evidence: `results/` - AI use: `AI_USE.md`

Pipeline: SLURP commands -> phi3.5 teacher (Ollama, 2 parallel k8s workers) -> `worker/clean.py` -> fine-tune Pythia-70M
(sequence-level KD) -> weights in SeaweedFS -> FastAPI service in Docker -> k3d/Kubernetes (Deployment, Ingress, HPA).

## Prerequisites (Windows 10/11, VS Code, PowerShell)
Docker Desktop (WSL2 backend, running), Python 3.11, Git, then:
```powershell
winget install Kubernetes.kubectl
winget install k3d.k3d          # or: choco install k3d
winget install Ollama.Ollama
winget install GitHub.cli       # for releases
choco install make              # optional; without it run the python commands shown in the Makefile
python -m venv .venv ; .\.venv\Scripts\Activate.ps1
pip install -r requirements-dev.txt
```
Let worker Pods reach Ollama on Windows: run `setx OLLAMA_HOST 0.0.0.0`, then quit and restart Ollama. The worker connects through `host.docker.internal`; pull the teacher model with `ollama pull phi3.5`.

## Build, deploy, test, tear down
Fresh clone (needs the GitHub Releases to exist): `make up` -> `curl.exe -X POST http://localhost:8081/parse -H "Content-Type: application/json" -d "{\"text\": \"what is the weather in london\"}"` -> `make down`.

## Full workflow in order (what produced the evidence in `results/`)
| Task | Commands |
|---|---|
| 1 | `make infra` ; `make label` (hours; follow with `kubectl -n pipeline logs -f -l job-name=teacher-labelling --prefix`) ; `make clean-data` |
| 2 | `make train SUBSET=50` ; `make train` ; `make train-v2` ; `make upload-model VERSION=v1` ; `make upload-model VERSION=v2` ; `make teacher-eval` ; `make eval-all` ; `gh release create model-v1 dist/model-v1.zip` ; `gh release create model-v2 dist/model-v2.zip` |
| 3 | `make build` ; `python scripts/docker_limits.py` ; fault test: `docker run --rm -p 8000:8000 -e FAULT_INJECT=1 ...` (see AI/report) |
| 4 | `python scripts/dev.py app` ; `python scripts/task4.py endpoints` / `rolling` / `recovery` / `coldstart` / `lb` / `hpa` |
| 5 | `python tools/nacl_sim.py network/nacl.json network/packets_sample.jsonl --check` (table in `network/subnets.md`) |
| 6 | push; Actions -> ci -> Run workflow with `model=baseline` (fails at the gate); put the run URL in `results/ci_failed_run.txt` |
| 7 | `python scripts/task4.py lb` then `python scripts/perf.py` ; `make report` |

Check release checksum: `Get-FileHash dist\model-v1.zip -Algorithm SHA256` must equal `models_out/v1/model.sha256`.
Submission zip: put the scanned handwritten reflection at `reflection/230101021.pdf`, then `make package` -> `submission/230101021.zip`.
