"""Task 3: run the image with 1 CPU / 1 GiB, send 50 sequential requests, report peak memory.

Needs: `make up` done (SeaweedFS on localhost:8333, models/v1 present) and the image built (parser-service:1.0).
"""
import json
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from common.s3util import _creds  # noqa: E402

NAME = "parser-limits"


def sh(*a):
    return subprocess.run(list(a), capture_output=True, text=True).stdout.strip()


def mem_mib(stat):
    """'312.4MiB / 1GiB | 98%' -> 312.4"""
    first = stat.split("/")[0].strip()
    num = float("".join(c for c in first if c.isdigit() or c == "."))
    if "GiB" in first:
        return num * 1024
    if "KiB" in first:
        return num / 1024
    return num


def main():
    key, sec = _creds()
    subprocess.run(["docker", "rm", "-f", NAME], capture_output=True)
    subprocess.run(["docker", "run", "-d", "--name", NAME, "--cpus=1", "--memory=1g", "--memory-swap=1g",
                    "-p", "8000:8000", "-e", "MODEL_URI=s3://models/v1/", "-e", "MODEL_VERSION=v1",
                    "-e", "S3_ENDPOINT=http://host.docker.internal:8333", "-e", "MAX_NEW_TOKENS=64",
                    "-e", f"AWS_ACCESS_KEY_ID={key}", "-e", f"AWS_SECRET_ACCESS_KEY={sec}",
                    "parser-service:1.0"], check=True)
    out = []
    for _ in range(180):
        try:
            urllib.request.urlopen("http://localhost:8000/readyz", timeout=2)
            break
        except Exception:  # noqa: BLE001
            time.sleep(2)
    texts = [json.loads(l)["text"] for l in open(ROOT / "data/validation.jsonl", encoding="utf-8")][:50]
    peak, ok = 0.0, 0
    for i, t in enumerate(texts, 1):
        req = urllib.request.Request("http://localhost:8000/parse", data=json.dumps({"text": t}).encode(),
                                     headers={"Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=60) as r:
                ok += r.status == 200
                body = r.read().decode()
        except Exception as e:  # noqa: BLE001
            body = f"ERR {e}"
        stat = sh("docker", "stats", "--no-stream", "--format", "{{.MemUsage}} | {{.CPUPerc}}", NAME)
        peak = max(peak, mem_mib(stat))
        out.append(f"{i:02d} {body} | {stat}")
    oom = sh("docker", "inspect", "-f", "{{.State.OOMKilled}}", NAME)
    out.append(f"\n50 requests sent, {ok} returned HTTP 200; OOMKilled={oom}; peak memory {peak:.0f} MiB (limit 1024 MiB)")
    out.append(sh("docker", "stats", "--no-stream", NAME))
    size = int(sh("docker", "image", "inspect", "-f", "{{.Size}}", "parser-service:1.0") or 0)
    out.append(f"image size: {size / 1e9:.2f} GB (limit 2 GB)")
    Path(ROOT / "results" / "task3_limits.txt").write_text("\n".join(out), encoding="utf-8")
    print("\n".join(out[-4:]))
    subprocess.run(["docker", "rm", "-f", NAME], capture_output=True)


if __name__ == "__main__":
    main()
