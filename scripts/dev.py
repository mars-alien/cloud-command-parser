"""Project orchestration (works from PowerShell/cmd/Git Bash on Windows). Usage: python scripts/dev.py <cmd>

  infra         k3d cluster + SeaweedFS + buckets + commands_pool upload
  label         build worker image, run 2 parallel teacher workers (needs Ollama running), wait
  upload-model  --version v1|v2   upload models_out/<v>/ to bucket models/<v>/ (+ model.sha256)
  up            infra + restore committed data/models + build images + deploy app   (fresh-clone entry point)
  down          delete the cluster
"""
import argparse
import json
import secrets
import subprocess
import sys
import time
import urllib.request
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
CLUSTER = "parser-cluster"
GITHUB_REPO = "mars-alien/cloud-command-parser"   # <-- change if your repo name differs
SECRETS = ROOT / ".secrets"


def run(cmd, check=True, input=None, capture=False):
    print("$", " ".join(map(str, cmd)), flush=True)
    return subprocess.run(cmd, check=check, input=input, text=True, cwd=ROOT,
                          capture_output=capture)


def kubectl(*a, **kw):
    return run(["kubectl", *a], **kw)


def apply_secret(ns, name, **kw):
    """kw: literal key=value pairs or key=Path (file)."""
    args = ["kubectl", "-n", ns, "create", "secret", "generic", name, "--dry-run=client", "-o", "yaml"]
    for k, v in kw.items():
        args.append(f"--from-file={k}={v}" if isinstance(v, Path) else f"--from-literal={k}={v}")
    manifest = run(args, capture=True).stdout
    kubectl("apply", "-f", "-", input=manifest)


def make_secrets():
    SECRETS.mkdir(exist_ok=True)
    env = SECRETS / "s3.env"
    if not env.exists():
        key, sec = "AK" + secrets.token_hex(8).upper(), secrets.token_hex(20)
        env.write_text(f"AWS_ACCESS_KEY_ID={key}\nAWS_SECRET_ACCESS_KEY={sec}\n")
        (SECRETS / "s3.json").write_text(json.dumps({"identities": [{
            "name": "admin", "credentials": [{"accessKey": key, "secretKey": sec}],
            "actions": ["Admin", "Read", "Write", "List", "Tagging"]}]}))
    vals = dict(l.split("=", 1) for l in env.read_text().splitlines())
    return vals


def cluster_exists():
    out = run(["k3d", "cluster", "list", "-o", "json"], capture=True).stdout
    return any(c["name"] == CLUSTER for c in json.loads(out))


def infra():
    for tool in ("docker", "k3d", "kubectl"):
        args = [tool, "version"]
        if tool == "kubectl":
            args.append("--client")
        if subprocess.run(args, capture_output=True).returncode != 0:
            sys.exit(f"{tool} not found / not working - see README prerequisites")
    if not cluster_exists():
        run(["k3d", "cluster", "create", "--config", "cluster/k3d.yaml"])
    kubectl("apply", "-f", "k8s/namespaces.yaml")
    vals = make_secrets()
    apply_secret("data", "seaweedfs-s3-config", **{"s3.json": SECRETS / "s3.json"})
    apply_secret("pipeline", "s3-credentials", **vals)
    apply_secret("app", "s3-credentials", **vals)
    kubectl("apply", "-f", "k8s/seaweedfs.yaml")
    kubectl("-n", "data", "rollout", "status", "deploy/seaweedfs", "--timeout=300s")
    from common import s3util
    c = s3util.client("http://localhost:8333")
    for _ in range(60):
        try:
            c.list_buckets()
            break
        except Exception:  # noqa: BLE001
            time.sleep(3)
    else:
        sys.exit("SeaweedFS S3 not reachable on localhost:8333")
    for b in ("datasets", "models"):
        s3util.ensure_bucket(c, b)
    if not s3util.exists(c, "datasets", "commands_pool.jsonl"):
        s3util.put_bytes(c, "datasets", "commands_pool.jsonl", (ROOT / "data/commands_pool.jsonl").read_bytes())
    print("infra ready")


def build_image(tag, dockerfile):
    run(["docker", "build", "-t", tag, "-f", dockerfile, "."])
    run(["k3d", "image", "import", tag, "-c", CLUSTER])


def label():
    build_image("parser-worker:1.0", "worker/Dockerfile")
    kubectl("-n", "pipeline", "delete", "job", "teacher-labelling", "--ignore-not-found")
    kubectl("apply", "-f", "k8s/worker-job.yaml")
    print("Workers started. Follow with: kubectl -n pipeline logs -f -l job-name=teacher-labelling --prefix")
    kubectl("-n", "pipeline", "wait", "--for=condition=complete", "job/teacher-labelling", "--timeout=24h")


def upload_model(version):
    from common import s3util
    c = s3util.client("http://localhost:8333")
    d = ROOT / "models_out" / version
    for p in sorted(d.iterdir()):
        s3util.put_bytes(c, "models", f"{version}/{p.name}", p.read_bytes())
    print("uploaded", [p.name for p in d.iterdir()], "to models/", version)


def restore():
    """Fresh clone: put committed datasets + model release assets into the buckets."""
    from common import s3util
    c = s3util.client("http://localhost:8333")
    for p in sorted((ROOT / "data" / "teacher").glob("shard-*.jsonl")):
        if not s3util.exists(c, "datasets", f"teacher/{p.name}"):
            s3util.put_bytes(c, "datasets", f"teacher/{p.name}", p.read_bytes())
    for name in ("train.jsonl", "train.sha256"):
        if (ROOT / "data" / name).exists() and not s3util.exists(c, "datasets", f"v1/{name}"):
            s3util.put_bytes(c, "datasets", f"v1/{name}", (ROOT / "data" / name).read_bytes())
    for v in ("v1", "v2"):
        if s3util.exists(c, "models", f"{v}/model.sha256"):
            continue
        z = ROOT / "dist" / f"model-{v}.zip"
        if not z.exists():
            z.parent.mkdir(exist_ok=True)
            url = f"https://github.com/{GITHUB_REPO}/releases/download/model-{v}/model-{v}.zip"
            print("downloading", url)
            urllib.request.urlretrieve(url, z)
        with zipfile.ZipFile(z) as zf:
            for n in zf.namelist():
                s3util.put_bytes(c, "models", f"{v}/{n}", zf.read(n))
        import hashlib
        digest = hashlib.sha256(z.read_bytes()).hexdigest()
        s3util.put_bytes(c, "models", f"{v}/model.sha256", f"{digest}  {z.name}\n".encode())


def app():
    build_image("parser-service:1.0", "service/Dockerfile")
    kubectl("apply", "-f", "k8s/app.yaml")
    kubectl("-n", "app", "rollout", "status", "deploy/parser", "--timeout=600s")
    print("Deployed. Try: curl -X POST http://localhost:8081/parse -H \"Content-Type: application/json\" "
          "-d \"{\\\"text\\\": \\\"what is the weather in london\\\"}\"")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["infra", "label", "upload-model", "up", "down", "app", "restore"])
    ap.add_argument("--version", default="v1")
    a = ap.parse_args()
    if a.cmd == "infra":
        infra()
    elif a.cmd == "label":
        label()
    elif a.cmd == "upload-model":
        upload_model(a.version)
    elif a.cmd == "restore":
        restore()
    elif a.cmd == "app":
        app()
    elif a.cmd == "up":
        infra()
        restore()
        app()
    elif a.cmd == "down":
        run(["k3d", "cluster", "delete", CLUSTER], check=False)


if __name__ == "__main__":
    main()
