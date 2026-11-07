"""Teacher access (Ollama + phi3.5, temperature 0, seed 42). Shared by the worker and eval_teacher.py."""
import json
import time
from urllib.error import HTTPError
import urllib.request

MODEL = "phi3.5"
OPTIONS = {"temperature": 0, "seed": 42, "num_predict": 100}


def load_prompt(path):
    return open(path, encoding="utf-8").read()


def ask_teacher(text, prompt_template, host="http://localhost:11434", retries=3, timeout=1800):
    body = {
        "model": MODEL,
        "prompt": prompt_template.replace("{command}", text),
        "stream": False,
        "format": "json",
        "keep_alive": "24h",
        "options": OPTIONS,
    }
    req = urllib.request.Request(f"{host}/api/generate", data=json.dumps(body).encode(),
                                 headers={"Content-Type": "application/json"})
    last = None
    for attempt in range(retries):
        try:
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return json.loads(r.read())["response"]
        except HTTPError as e:
            detail = e.read().decode("utf-8", errors="replace").strip()
            last = RuntimeError(f"HTTP {e.code}: {detail or e.reason}")
            time.sleep(2 * (attempt + 1))
        except Exception as e:  # noqa: BLE001
            last = e
            time.sleep(2 * (attempt + 1))
    raise RuntimeError(f"teacher failed: {last}")
