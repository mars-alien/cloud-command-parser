"""Task 3: run the image with 1 CPU / 1 GiB, send 50 sequential requests, report peak memory.

Needs: `make up` done (SeaweedFS on localhost:8333, models/v1 present) and the image built (parser-service:1.0).
"""
import argparse
import http.client
import json
import subprocess
import sys
import time
import urllib.error
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


def wait_ready(timeout=360):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            with urllib.request.urlopen("http://localhost:8000/readyz", timeout=2) as response:
                if response.status == 200:
                    return
        except (http.client.HTTPException, OSError, urllib.error.HTTPError, urllib.error.URLError):
            time.sleep(2)
    logs = sh("docker", "logs", NAME)
    raise RuntimeError(f"service did not become ready within {timeout}s:\n{logs}")


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("mode", choices=("limits", "fault"), nargs="?", default="limits")
    mode = ap.parse_args().mode

    key, sec = _creds()
    subprocess.run(["docker", "rm", "-f", NAME], capture_output=True)
    cmd = ["docker", "run", "-d", "--name", NAME, "--cpus=1", "--memory=1g", "--memory-swap=1g",
           "-p", "8000:8000", "-e", "MODEL_URI=s3://models/v1/", "-e", "MODEL_VERSION=v1",
           "-e", "S3_ENDPOINT=http://host.docker.internal:8333", "-e", "MAX_NEW_TOKENS=64",
           "-e", f"AWS_ACCESS_KEY_ID={key}", "-e", f"AWS_SECRET_ACCESS_KEY={sec}"]
    if mode == "fault":
        cmd += ["-e", "FAULT_INJECT=1"]
    cmd.append("parser-service:1.0")

    try:
        subprocess.run(cmd, check=True)
        wait_ready()
        texts = [json.loads(l)["text"] for l in open(ROOT / "data/validation.jsonl", encoding="utf-8")][:50]
        if mode == "fault":
            req = urllib.request.Request("http://localhost:8000/parse", data=json.dumps({"text": texts[0]}).encode(),
                                         headers={"Content-Type": "application/json"})
            try:
                with urllib.request.urlopen(req, timeout=60) as r:
                    status, body = r.status, r.read().decode()
            except urllib.error.HTTPError as e:
                status, body = e.code, e.read().decode()
            if status != 500 or json.loads(body) != {"error": "invalid_model_output"}:
                raise RuntimeError(f"fault injection check failed: HTTP {status}, body={body}")
            report = f"fault injection returned expected HTTP {status}: {body}"
            report_path = ROOT / "results" / "task3_fault.txt"
        else:
            peak, ok, out = 0.0, 0, []
            for i, text in enumerate(texts, 1):
                req = urllib.request.Request("http://localhost:8000/parse", data=json.dumps({"text": text}).encode(),
                                             headers={"Content-Type": "application/json"})
                try:
                    with urllib.request.urlopen(req, timeout=60) as r:
                        ok += r.status == 200
                        body = r.read().decode()
                except urllib.error.HTTPError as e:
                    body = f"ERR HTTP {e.code}: {e.read().decode()}"
                stat = sh("docker", "stats", "--no-stream", "--format", "{{.MemUsage}} | {{.CPUPerc}}", NAME)
                peak = max(peak, mem_mib(stat))
                out.append(f"{i:02d} {body} | {stat}")
            oom = sh("docker", "inspect", "-f", "{{.State.OOMKilled}}", NAME)
            out.append(f"\n{len(texts)} requests sent, {ok} returned HTTP 200; OOMKilled={oom}; "
                       f"peak memory {peak:.0f} MiB (limit 1024 MiB)")
            out.append(sh("docker", "stats", "--no-stream", NAME))
            size = int(sh("docker", "image", "inspect", "-f", "{{.Size}}", "parser-service:1.0") or 0)
            out.append(f"image size: {size / 1e9:.2f} GB (limit 2 GB)")
            report = "\n".join(out)
            report_path = ROOT / "results" / "task3_limits.txt"
        report_path.write_text(report, encoding="utf-8")
        print(report if mode == "fault" else "\n".join(out[-4:]))
    finally:
        subprocess.run(["docker", "rm", "-f", NAME], capture_output=True)


if __name__ == "__main__":
    main()
