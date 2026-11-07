# Handwritten reflection - draft to copy by hand (about 3 pages). Edit to match what actually happened to you.
Name: Royal Sachan   Roll no.: 230101021   GitHub: https://github.com/mars-alien/cloud-command-parser

## What I learnt
Sequence-level distillation: the student is trained with ordinary cross-entropy on the text the teacher generated. It is simple and works across
different tokenizers, unlike logit-based KD, which needs aligned vocabularies and stored logits. I learnt how a small CPU-only fine-tune is set up
(masking the prompt, EOS, fixed seeds), and how the same artefact moves through object storage, a container, Kubernetes and CI.
On the cloud side: Pods vs Deployments, readiness vs liveness (the Service has no endpoints until /readyz is 200), requests vs limits, why HPA
percentage is relative to the request, rolling updates with maxUnavailable 0, stateless NACLs and subnet maths.

## Challenges and how I solved them
1. Labelling 3,000 commands on CPU took [__] hours. Workers flush every 20 records and resume, so a restart did not lose work.
2. Making Pods reach Ollama on Windows: Ollama listened on localhost only; set OLLAMA_HOST=0.0.0.0 and used host.docker.internal.
3. Teacher replies were not always clean ([__] rejected): I did not edit them; clean.py rejects them by the four rules, and writes bytes so the checksum is the same on Windows.
4. Memory/CPU limits: [describe peak memory __ MiB, any OOM or throttling you saw].
5. Rolling update without errors: needed readiness probes, maxUnavailable 0 and a preStop sleep so Traefik stops sending traffic first. [__ failures]
6. [Any Windows/Docker/k3d problem you really hit and fixed.]

## Findings
Student v1: JSON validity [__]%, full-frame [__]% vs teacher [__]% and untrained [__]%. p50 [__] ms, p95 [__] ms, [__] req/s,
error rate [__]%. Cost [__] INR per 1,000 requests. Cold start median [__] s (dominated by model download + torch import).
Load balancing split [__]/[__]. HPA scaled 1 -> 2 after [__] s of load.

## What could be better
More training data and filtering for teacher agreement; logit KD with a same-tokenizer teacher; quantised/ONNX inference for latency;
a multi-node cluster for real fault tolerance; sealed secrets and TLS; keep the model in a PVC cache to cut cold start.
