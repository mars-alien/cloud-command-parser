"""Task 4 experiments. Each runs the standard Locust command through the Ingress while acting on the cluster.

  python scripts/task4.py rolling      # v1 -> v2 under load, then rollout undo
  python scripts/task4.py recovery     # delete one Pod under load
  python scripts/task4.py coldstart    # delete all Pods x3, log evidence + median time-to-Ready
  python scripts/task4.py lb           # 2 ready replicas, standard 2m load test, per-replica counts
  python scripts/task4.py hpa          # apply HPA, scale down to 1, load -> 2, stop load -> 1
  python scripts/task4.py endpoints    # show Service has no ready endpoints while a new Pod is loading
"""
import json
import statistics
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RES = ROOT / "results"
RES.mkdir(exist_ok=True)
HOST = "http://localhost:8081"


def k(*args, capture=True, check=True):
    r = subprocess.run(["kubectl", *args], capture_output=capture, text=True, cwd=ROOT, check=check)
    return r.stdout if capture else None


def log(name, text):
    with open(RES / name, "a", encoding="utf-8") as f:
        f.write(f"[{datetime.now().isoformat(timespec='seconds')}] {text}\n")
    print(text, flush=True)


def locust(prefix, run_time="2m", users=4):
    env = dict(**__import__("os").environ, LOADTEST_HEADERS_OUT=str(RES / f"{prefix}_headers.json"))
    cmd = [sys.executable, "-m", "locust", "-f", "tools/locustfile.py", "--headless", "--users", str(users),
           "--spawn-rate", str(users), "--run-time", run_time, "--host", HOST, "--csv", f"results/{prefix}"]
    return subprocess.Popen(cmd, cwd=ROOT, env=env, stdout=open(RES / f"{prefix}_locust.txt", "w"),
                            stderr=subprocess.STDOUT)


def pods():
    j = json.loads(k("-n", "app", "get", "pods", "-l", "app=parser", "-o", "json"))["items"]
    return [p for p in j if not p["metadata"].get("deletionTimestamp")]


def ready_count():
    return sum(1 for p in pods() for c in p["status"].get("conditions", [])
               if c["type"] == "Ready" and c["status"] == "True")


def wait_ready(n, timeout=600):
    t = time.time()
    while time.time() - t < timeout:
        if ready_count() >= n and len(pods()) == n:
            return True
        time.sleep(2)
    return False


def summary(prefix):
    import csv
    rows = list(csv.DictReader(open(RES / f"{prefix}_stats.csv", encoding="utf-8")))
    a = [r for r in rows if r["Name"] == "Aggregated"][0]
    req, fail = int(a["Request Count"]), int(a["Failure Count"])
    log(f"{prefix}.log", f"requests={req} failures={fail} ({100 * fail / max(req, 1):.2f}%) "
                         f"p50={a['50%']}ms p95={a['95%']}ms rps={a['Requests/s']}")


def rolling():
    p = locust("rolling", "5m")
    time.sleep(30)
    log("rolling.log", "set MODEL_VERSION=v2, MODEL_URI=s3://models/v2/")
    k("-n", "app", "set", "env", "deploy/parser", "MODEL_VERSION=v2", "MODEL_URI=s3://models/v2/")
    k("-n", "app", "rollout", "status", "deploy/parser", "--timeout=600s", capture=False)
    time.sleep(30)
    log("rolling.log", "rollout undo")
    k("-n", "app", "rollout", "undo", "deploy/parser")
    k("-n", "app", "rollout", "status", "deploy/parser", "--timeout=600s", capture=False)
    p.wait()
    summary("rolling")
    hdr = json.load(open(RES / "rolling_headers.json"))
    log("rolling.log", f"headers: {hdr}")
    out = subprocess.run(["curl", "-s", "-i", "-X", "POST", f"{HOST}/parse", "-H", "Content-Type: application/json",
                          "-d", '{"text": "what is the weather in london"}'], capture_output=True, text=True).stdout
    log("rolling.log", "after rollback:\n" + out)


def recovery():
    p = locust("recovery", "3m")
    time.sleep(30)
    victim = pods()[0]["metadata"]["name"]
    log("recovery.log", f"replicas before: {len(pods())}; deleting {victim}")
    k("-n", "app", "delete", "pod", victim, "--wait=false")
    ok = wait_ready(2)
    log("recovery.log", f"replica count restored to 2 ready: {ok}")
    p.wait()
    summary("recovery")


def coldstart():
    times = []
    for i in range(3):
        k("-n", "app", "delete", "pod", "-l", "app=parser", "--wait=true")
        time.sleep(3)
        wait_ready(2, 900)
        for p in pods():
            created = datetime.fromisoformat(p["metadata"]["creationTimestamp"].replace("Z", "+00:00"))
            ready = [c for c in p["status"]["conditions"] if c["type"] == "Ready"][0]["lastTransitionTime"]
            dt = (datetime.fromisoformat(ready.replace("Z", "+00:00")) - created).total_seconds()
            times.append(dt)
            log("coldstart.log", f"run {i + 1} pod {p['metadata']['name']}: {dt:.0f}s to Ready")
            log("coldstart.log", "pod log: " + k("-n", "app", "logs", p["metadata"]["name"]).strip().replace("\n", " | "))
    log("coldstart.log", f"median time-to-Ready over {len(times)} pods (3 runs): {statistics.median(times):.1f}s")


def lb():
    k("-n", "app", "delete", "hpa", "parser", "--ignore-not-found")
    k("-n", "app", "scale", "deploy/parser", "--replicas=2")
    wait_ready(2)
    locust("lb", "2m").wait()
    summary("lb")
    hdr = json.load(open(RES / "lb_headers.json"))["per_replica"]
    tot = sum(hdr.values())
    log("lb.log", "per replica: " + ", ".join(f"{n}: {c} ({100 * c / tot:.1f}%)" for n, c in hdr.items()))


def hpa():
    k("apply", "-f", "k8s/hpa.yaml")
    log("hpa.log", "HPA applied; waiting for scale down to 1 replica")
    t = time.time()
    while time.time() - t < 600 and len(pods()) > 1:
        time.sleep(10)
    log("hpa.log", f"replicas now {len(pods())}")
    p = locust("hpa", "4m", users=4)
    while p.poll() is None:
        log("hpa.log", "HPA: " + " ".join(k("-n", "app", "get", "hpa", "parser", "--no-headers").split()))
        time.sleep(15)
    summary("hpa")
    for _ in range(12):
        log("hpa.log", "after load: " + " ".join(k("-n", "app", "get", "hpa", "parser", "--no-headers").split()))
        time.sleep(15)


def endpoints():
    k("-n", "app", "scale", "deploy/parser", "--replicas=0")
    time.sleep(5)
    k("-n", "app", "scale", "deploy/parser", "--replicas=1")
    for _ in range(20):
        log("endpoints.log", "pods: " + " ".join(k("-n", "app", "get", "pods", "--no-headers").split()) +
            " | endpoints: " + " ".join(k("-n", "app", "get", "endpoints", "parser", "--no-headers").split()))
        time.sleep(3)


if __name__ == "__main__":
    globals()[sys.argv[1]]()
