"""Task 7: standard load test + kubectl top sampling + cost + SLO -> results/perf_summary.json

Run with exactly two Ready replicas (python scripts/task4.py lb first leaves it that way).
"""
import csv
import json
import os
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RES = ROOT / "results"
CPU_LIMIT, MEM_LIMIT_GIB, REPLICAS = 1.0, 1.0, 2     # must match k8s/app.yaml
SLO_TARGET = 0.99


def top():
    out = subprocess.run(["kubectl", "-n", "app", "top", "pods", "--no-headers"], capture_output=True, text=True).stdout
    return out


def main():
    env = dict(os.environ, LOADTEST_HEADERS_OUT=str(RES / "loadtest_headers.json"))
    p = subprocess.Popen([sys.executable, "-m", "locust", "-f", "tools/locustfile.py", "--headless", "--users", "4",
                          "--spawn-rate", "4", "--run-time", "2m", "--host", "http://localhost:8081",
                          "--csv", "results/loadtest"], cwd=ROOT, env=env,
                         stdout=open(RES / "loadtest_locust.txt", "w"), stderr=subprocess.STDOUT)
    samples, peak = [], {}
    time.sleep(40)
    while p.poll() is None:
        t = top()
        samples.append(t)
        for line in t.splitlines():
            n, cpu, mem = line.split()[:3]
            c, m = int(cpu.rstrip("m")), int(mem.rstrip("Mi"))
            peak[n] = (max(peak.get(n, (0, 0))[0], c), max(peak.get(n, (0, 0))[1], m))
        time.sleep(15)
    (RES / "kubectl_top_pods.txt").write_text("\n---\n".join(samples))
    a = [r for r in csv.DictReader(open(RES / "loadtest_stats.csv", encoding="utf-8")) if r["Name"] == "Aggregated"][0]
    req, fail = int(a["Request Count"]), int(a["Failure Count"])
    rps = float(a["Requests/s"])
    rate = json.load(open(ROOT / "data" / "rate_card.json"))
    hourly = REPLICAS * (CPU_LIMIT * rate["vcpu_hour"] + MEM_LIMIT_GIB * rate["gib_memory_hour"])
    per_hour = rps * 3600
    budget = round((1 - SLO_TARGET) * req, 2)
    summary = {
        "requests": req, "failures": fail, "error_rate_pct": round(100 * fail / max(req, 1), 3),
        "p50_ms": float(a["50%"]), "p95_ms": float(a["95%"]), "rps": rps,
        "peak_cpu_mem_per_pod": {n: {"cpu_m": c, "mem_mi": m} for n, (c, m) in peak.items()},
        "cost": {"hourly_cost_inr": round(hourly, 4), "requests_per_hour": round(per_hour, 1),
                 "cost_per_1000_requests_inr": round(hourly / per_hour * 1000, 4) if per_hour else None,
                 "steps": f"hourly = {REPLICAS} x ({CPU_LIMIT} x {rate['vcpu_hour']} + {MEM_LIMIT_GIB} x "
                          f"{rate['gib_memory_hour']}) = {hourly:.2f} INR; req/h = {rps} x 3600 = {per_hour:.0f}; "
                          f"cost/1000 = {hourly:.2f} / {per_hour:.0f} x 1000"},
        "slo": {"objective": "99% of requests succeed (HTTP 200 within 30 s)", "window": "one 2-minute load-test run",
                "target": SLO_TARGET, "error_budget_requests": budget, "budget_used_requests": fail,
                "budget_used_pct": round(100 * fail / budget, 1) if budget else None},
    }
    (RES / "perf_summary.json").write_text(json.dumps(summary, indent=2))
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
