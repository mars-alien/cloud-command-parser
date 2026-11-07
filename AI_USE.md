# AI use

**Tool:** Claude (Anthropic chat assistant), used for planning and for drafting boilerplate.

**What it was used for**
- Explaining sequence-level knowledge distillation and how it differs from logit-based distillation.
- Drafting the first version of: the Makefile, `scripts/*.py` orchestration, Kubernetes manifests, the GitHub Actions workflow, the FastAPI service, the training loop, unit tests and the report generator.
- Working out the subnet table and NACL rule numbers.

**How the output was checked**
- Ran `ruff` and `pytest` (unit tests for the cleaner, post-processing, service endpoints, fault injection and NACL file).
- Verified the subnet table by hand (formula 2^(32-p)-2) and with Python's `ipaddress`; verified the NACL with `tools/nacl_sim.py --check` (6/6).
- Every number in the report is read from files in `results/` produced by my own runs; nothing was typed in by hand.
- Teacher replies were never edited; `clean.py` is deterministic and its output hash is recorded in `data/train.sha256`.
- Read every manifest/command before running it; fixed environment-specific problems (Windows paths, Ollama host binding) myself.
- No credentials were pasted into the AI chat; S3 keys are generated locally into the git-ignored `.secrets/` folder and `gitleaks` reports nothing.
