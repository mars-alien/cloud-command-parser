"""Score the teacher (same prompt/settings as Task 1) on validation.jsonl -> results/teacher_validation.json."""
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from common.teacher import ask_teacher, load_prompt  # noqa: E402


def main():
    host = sys.argv[1] if len(sys.argv) > 1 else "http://localhost:11434"
    prompt = load_prompt(ROOT / "prompts" / "teacher_prompt.txt")
    data = ROOT / "data" / "validation.jsonl"
    rows = [json.loads(l) for l in data.read_text(encoding="utf-8").splitlines() if l.strip()]
    pred = ROOT / "results" / "teacher_predictions.jsonl"
    with open(pred, "w", encoding="utf-8", newline="\n") as f:
        for i, r in enumerate(rows, 1):
            raw = ask_teacher(r["text"], prompt, host)
            f.write(json.dumps({"id": r["id"], "prediction": raw}, ensure_ascii=False) + "\n")
            print(i, flush=True)
    proc = subprocess.run([sys.executable, str(ROOT / "tools" / "score.py"), str(pred), str(data),
                           "--out", str(ROOT / "results" / "teacher_validation.json")],
                          capture_output=True, text=True)
    (ROOT / "results" / "teacher_score.txt").write_text(proc.stdout)
    print(proc.stdout)


if __name__ == "__main__":
    main()
