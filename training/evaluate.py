"""Run a causal LM on data/validation.jsonl and score it with tools/score.py.

  python training/evaluate.py --model models_out/v1 --name student_v1
  python training/evaluate.py --model EleutherAI/pythia-70m --name untrained
"""
import argparse
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from common.postprocess import extract_prediction  # noqa: E402
from common.prompt import build_prompt  # noqa: E402


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", required=True)
    ap.add_argument("--name", required=True)
    ap.add_argument("--data", default=str(ROOT / "data" / "validation.jsonl"))
    ap.add_argument("--max-new-tokens", type=int, default=64)
    ap.add_argument("--outdir", default=str(ROOT / "results"))
    a = ap.parse_args()

    import torch
    from transformers import AutoModelForCausalLM, AutoTokenizer

    torch.set_num_threads(4)
    tok = AutoTokenizer.from_pretrained(a.model)
    tok.pad_token = tok.eos_token
    model = AutoModelForCausalLM.from_pretrained(a.model, torch_dtype=torch.float32).eval()
    rows = [json.loads(l) for l in Path(a.data).read_text(encoding="utf-8").splitlines() if l.strip()]
    out = Path(a.outdir)
    out.mkdir(exist_ok=True)
    pred_path = out / f"{a.name}_predictions.jsonl"
    with open(pred_path, "w", encoding="utf-8", newline="\n") as f:
        for r in rows:
            enc = tok(build_prompt(r["text"]), return_tensors="pt")
            with torch.no_grad():
                g = model.generate(**enc, max_new_tokens=a.max_new_tokens, do_sample=False,
                                   pad_token_id=tok.eos_token_id)
            text = tok.decode(g[0][enc["input_ids"].shape[1]:], skip_special_tokens=True)
            f.write(json.dumps({"id": r["id"], "prediction": extract_prediction(text),
                                "raw_generation": text}, ensure_ascii=False) + "\n")
    report = out / f"{a.name}_validation.json"
    proc = subprocess.run([sys.executable, str(ROOT / "tools" / "score.py"), str(pred_path), a.data,
                           "--out", str(report)], capture_output=True, text=True)
    (out / f"{a.name}_score.txt").write_text(proc.stdout)
    print(proc.stdout)


if __name__ == "__main__":
    main()
