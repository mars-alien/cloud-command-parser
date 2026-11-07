"""Clean the teacher shards -> datasets/v1/train.jsonl + train.sha256 (deterministic).

Usage:  python worker/clean.py              # read shards from object storage, write bucket + data/
        python worker/clean.py --offline    # read data/teacher/shard-*.jsonl, write data/ only
"""
import argparse
import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

SCHEMA = json.loads((ROOT / "data" / "schema.json").read_text(encoding="utf-8"))
KEYS = set(SCHEMA["keys"])
INTENTS = set(SCHEMA["intents"])


def classify(rec):
    """Return None if the record is good, else reason 'a'|'b'|'c'|'d'."""
    try:
        obj = json.loads(rec["teacher_raw"])
    except (ValueError, TypeError):
        return "a"
    if not isinstance(obj, dict) or set(obj.keys()) != KEYS:
        return "b"
    if obj["intent"] not in INTENTS:
        return "c"
    text = rec["text"].lower()
    for k in ("date", "time", "place"):
        v = obj[k]
        if v is None:
            continue
        if not isinstance(v, str) or not v.strip() or v.strip().lower() not in text:
            return "d"
    return None


def clean(records):
    counts = {"input": len(records), "a_invalid_json": 0, "b_bad_keys": 0, "c_bad_intent": 0,
              "d_bad_slot": 0, "duplicates": 0, "kept": 0}
    names = {"a": "a_invalid_json", "b": "b_bad_keys", "c": "c_bad_intent", "d": "d_bad_slot"}
    good = []
    for r in sorted(records, key=lambda r: r["id"]):
        why = classify(r)
        if why:
            counts[names[why]] += 1
        else:
            good.append(r)
    seen, kept = set(), []
    for r in good:  # id order => smallest id kept
        if r["text"] in seen:
            counts["duplicates"] += 1
            continue
        seen.add(r["text"])
        kept.append(r)
    counts["kept"] = len(kept)
    assert counts["input"] == sum(v for k, v in counts.items() if k != "input")
    body = "".join(json.dumps({"id": r["id"], "text": r["text"], "teacher_raw": r["teacher_raw"]},
                              ensure_ascii=False) + "\n" for r in kept).encode("utf-8")
    return body, counts


def read_shards_local(d):
    recs = []
    for p in sorted(Path(d).glob("shard-*.jsonl")):
        recs += [json.loads(l) for l in p.read_text(encoding="utf-8").splitlines() if l.strip()]
    return recs


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--offline", action="store_true")
    ap.add_argument("--shards-dir", default=str(ROOT / "data" / "teacher"))
    a = ap.parse_args()
    c = None
    if a.offline:
        records = read_shards_local(a.shards_dir)
    else:
        from common import s3util
        c = s3util.client()
        records = []
        for key in sorted(s3util.list_keys(c, "datasets", "teacher/")):
            body = s3util.get_bytes(c, "datasets", key)
            records += [json.loads(l) for l in body.decode("utf-8").splitlines() if l.strip()]
            (ROOT / "data" / "teacher").mkdir(exist_ok=True)
            (ROOT / "data" / "teacher" / Path(key).name).write_bytes(body)
    body, counts = clean(records)
    digest = hashlib.sha256(body).hexdigest()
    (ROOT / "data" / "train.jsonl").write_bytes(body)  # bytes: no CRLF on Windows
    (ROOT / "data" / "train.sha256").write_text(f"{digest}  train.jsonl\n", encoding="utf-8", newline="\n")
    (ROOT / "results").mkdir(exist_ok=True)
    (ROOT / "results" / "clean_counts.json").write_text(json.dumps(counts, indent=2) + "\n")
    if c is not None:
        s3util.put_bytes(c, "datasets", "v1/train.jsonl", body)
        s3util.put_bytes(c, "datasets", "v1/train.sha256", f"{digest}  train.jsonl\n".encode())
    print(json.dumps(counts, indent=2))
    print("sha256", digest)


if __name__ == "__main__":
    main()
