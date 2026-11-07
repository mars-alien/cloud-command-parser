"""Teacher-labelling worker. Env: SHARD_INDEX, SHARD_COUNT (+ S3_ENDPOINT, OLLAMA_URL)."""
import json
import os
import sys

from common import s3util
from common.teacher import ask_teacher, load_prompt

FLUSH_EVERY = 20


def my_lines(lines, index, count):
    """Commands whose line number (from 0) % count == index."""
    return [line for n, line in enumerate(lines) if n % count == index]


def main():
    index = int(os.environ["SHARD_INDEX"])
    count = int(os.environ["SHARD_COUNT"])
    ollama = os.environ.get("OLLAMA_URL", "http://host.docker.internal:11434")
    prompt = load_prompt(os.environ.get("PROMPT_PATH", "prompts/teacher_prompt.txt"))
    c = s3util.client()
    pool = s3util.get_bytes(c, "datasets", "commands_pool.jsonl").decode("utf-8").splitlines()
    mine = my_lines(pool, index, count)
    out_key = f"teacher/shard-{index}.jsonl"

    done = {}
    if s3util.exists(c, "datasets", out_key):  # resume after a restart
        for line in s3util.get_bytes(c, "datasets", out_key).decode("utf-8").splitlines():
            if line.strip():
                r = json.loads(line)
                done[r["id"]] = r
    print(f"shard {index}/{count}: {len(mine)} commands, {len(done)} already done", flush=True)

    def flush():
        body = "".join(json.dumps(done[k], ensure_ascii=False) + "\n" for k in sorted(done)).encode("utf-8")
        s3util.put_bytes(c, "datasets", out_key, body)

    for line in mine:
        rec = json.loads(line)
        if rec["id"] in done:
            continue
        try:
            raw = ask_teacher(rec["text"], prompt, ollama)
        except RuntimeError as e:
            print("ERROR", rec["id"], e, file=sys.stderr, flush=True)
            raise
        done[rec["id"]] = {"id": rec["id"], "text": rec["text"], "teacher_raw": raw}
        if len(done) % FLUSH_EVERY == 0:
            flush()
            print(f"shard {index}: {len(done)}/{len(mine)}", flush=True)
    flush()
    print(f"shard {index}: finished {len(done)}/{len(mine)}", flush=True)


if __name__ == "__main__":
    main()
