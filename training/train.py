"""Sequence-level distillation: fine-tune Pythia-70M on teacher JSON replies (CPU).

  python training/train.py                     # v1 (config.yaml)
  python training/train.py --version v2
  python training/train.py --subset 50        # smoke test, first 50 records only
"""
import argparse
import csv
import json
import os
import random
import sys
import time
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from common.prompt import build_example, build_prompt  # noqa: E402
from training.model_packaging import package  # noqa: E402

KEYS = ("intent", "date", "time", "place")


def canonical(raw):
    """Same JSON, fixed key order and ', ' / ': ' separators (deterministic; no content change)."""
    obj = json.loads(raw)
    return json.dumps({k: obj[k] for k in KEYS}, ensure_ascii=False)


def load_records(path, limit):
    recs = [json.loads(l) for l in Path(path).read_text(encoding="utf-8").splitlines() if l.strip()]
    return recs[:limit]


def encode(tok, rec, max_len):
    prompt_ids = tok(build_prompt(rec["text"]))["input_ids"]
    full_ids = tok(build_example(rec["text"], canonical(rec["teacher_raw"])))["input_ids"] + [tok.eos_token_id]
    full_ids = full_ids[:max_len]
    labels = [-100] * len(prompt_ids) + full_ids[len(prompt_ids):]
    return full_ids, labels[:len(full_ids)]


def collate(batch, pad_id):
    n = max(len(i) for i, _ in batch)
    ids = [i + [pad_id] * (n - len(i)) for i, _ in batch]
    lab = [l + [-100] * (n - len(l)) for _, l in batch]
    att = [[1] * len(i) + [0] * (n - len(i)) for i, _ in batch]
    return ids, att, lab


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", default=str(ROOT / "training" / "config.yaml"))
    ap.add_argument("--version", default="v1")
    ap.add_argument("--subset", type=int, default=None)
    a = ap.parse_args()

    import numpy as np
    import torch
    from transformers import AutoModelForCausalLM, AutoTokenizer

    cfg = yaml.safe_load(Path(a.config).read_text())
    cfg.update(cfg["versions"].get(a.version, {}))
    seed = cfg["seed"]
    random.seed(seed)
    np.random.seed(seed)
    torch.manual_seed(seed)
    torch.set_num_threads(os.cpu_count() or 4)

    limit = a.subset or cfg["max_train_examples"]
    tag = f"subset{a.subset}" if a.subset else a.version
    records = load_records(ROOT / cfg["train_path"], limit)
    print(f"training {tag}: {len(records)} records, seed={seed}, epochs={cfg['epochs']}", flush=True)

    tok = AutoTokenizer.from_pretrained(cfg["base_model"])
    tok.pad_token = tok.eos_token
    model = AutoModelForCausalLM.from_pretrained(cfg["base_model"], torch_dtype=torch.float32)
    model.config.pad_token_id = tok.eos_token_id
    data = [encode(tok, r, cfg["max_seq_length"]) for r in records]

    bs = cfg["batch_size"]
    steps_per_epoch = (len(data) + bs - 1) // bs
    total = steps_per_epoch * cfg["epochs"]
    opt = torch.optim.AdamW(model.parameters(), lr=cfg["learning_rate"], weight_decay=cfg["weight_decay"])
    warm = max(1, int(total * cfg["warmup_ratio"]))
    sched = torch.optim.lr_scheduler.LambdaLR(
        opt, lambda s: (s + 1) / warm if s < warm else max(0.0, (total - s) / max(1, total - warm)))
    gen = torch.Generator().manual_seed(seed)

    losses, step, t0 = [], 0, time.time()
    model.train()
    for epoch in range(1, cfg["epochs"] + 1):
        order = torch.randperm(len(data), generator=gen).tolist()
        tot, n = 0.0, 0
        for i in range(0, len(order), bs):
            ids, att, lab = collate([data[j] for j in order[i:i + bs]], tok.eos_token_id)
            out = model(input_ids=torch.tensor(ids), attention_mask=torch.tensor(att), labels=torch.tensor(lab))
            out.loss.backward()
            torch.nn.utils.clip_grad_norm_(model.parameters(), 1.0)
            opt.step()
            sched.step()
            opt.zero_grad()
            tot, n, step = tot + out.loss.item(), n + 1, step + 1
        losses.append(tot / n)
        print(f"epoch {epoch}/{cfg['epochs']} loss {losses[-1]:.4f} ({time.time() - t0:.0f}s)", flush=True)

    loss_name = "loss.csv" if a.version == "v1" and a.subset is None else f"loss_{tag}.csv"
    loss_file = ROOT / "training" / loss_name
    with open(loss_file, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["epoch", "train_loss"])
        for e, l in enumerate(losses, 1):
            w.writerow([e, f"{l:.6f}"])

    out_dir = ROOT / "models_out" / tag
    out_dir.mkdir(parents=True, exist_ok=True)
    model.save_pretrained(out_dir, safe_serialization=True)
    tok.save_pretrained(out_dir)
    (out_dir / "version.json").write_text(json.dumps(
        {"model_version": tag, "base_model": cfg["base_model"], "seed": seed, "epochs": cfg["epochs"],
         "learning_rate": cfg["learning_rate"], "batch_size": bs, "train_records": len(records),
         "final_loss": losses[-1]}, indent=2))
    digest = package(out_dir, ROOT / "dist" / f"model-{tag}.zip")
    print(f"saved {out_dir}; model-{tag}.zip sha256 {digest}")


if __name__ == "__main__":
    main()
