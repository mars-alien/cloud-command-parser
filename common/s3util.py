"""Small S3 helpers (SeaweedFS). Credentials: env vars, else the git-ignored .secrets/s3.env."""
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SECRETS = ROOT / ".secrets" / "s3.env"


def _creds():
    key = os.environ.get("AWS_ACCESS_KEY_ID")
    sec = os.environ.get("AWS_SECRET_ACCESS_KEY")
    if (not key or not sec) and SECRETS.exists():
        vals = dict(l.strip().split("=", 1) for l in SECRETS.read_text().splitlines() if "=" in l)
        key, sec = vals.get("AWS_ACCESS_KEY_ID"), vals.get("AWS_SECRET_ACCESS_KEY")
    return key, sec


def client(endpoint=None):
    import boto3
    from botocore.config import Config

    key, sec = _creds()
    return boto3.client(
        "s3",
        endpoint_url=endpoint or os.environ.get("S3_ENDPOINT", "http://localhost:8333"),
        aws_access_key_id=key,
        aws_secret_access_key=sec,
        region_name="us-east-1",
        config=Config(s3={"addressing_style": "path"}, retries={"max_attempts": 5}),
    )


def parse_uri(uri):
    assert uri.startswith("s3://"), uri
    bucket, _, prefix = uri[5:].partition("/")
    return bucket, prefix


def ensure_bucket(c, name):
    names = [b["Name"] for b in c.list_buckets().get("Buckets", [])]
    if name not in names:
        c.create_bucket(Bucket=name)


def put_bytes(c, bucket, key, data):
    c.put_object(Bucket=bucket, Key=key, Body=data)


def get_bytes(c, bucket, key):
    return c.get_object(Bucket=bucket, Key=key)["Body"].read()


def exists(c, bucket, key):
    try:
        c.head_object(Bucket=bucket, Key=key)
        return True
    except Exception:
        return False


def list_keys(c, bucket, prefix=""):
    keys, token = [], None
    while True:
        kw = {"Bucket": bucket, "Prefix": prefix}
        if token:
            kw["ContinuationToken"] = token
        r = c.list_objects_v2(**kw)
        keys += [o["Key"] for o in r.get("Contents", [])]
        if not r.get("IsTruncated"):
            return keys
        token = r["NextContinuationToken"]


def download_prefix(c, uri, dest):
    bucket, prefix = parse_uri(uri)
    dest = Path(dest)
    dest.mkdir(parents=True, exist_ok=True)
    n = 0
    for key in list_keys(c, bucket, prefix):
        name = key[len(prefix):].lstrip("/")
        if not name or name.endswith(".zip"):
            continue
        (dest / name).write_bytes(get_bytes(c, bucket, key))
        n += 1
    return n
