"""Command-parser inference service (FastAPI). Port 8000.

Env: MODEL_URI (s3://models/v1/), MODEL_VERSION, S3_ENDPOINT, MAX_NEW_TOKENS, FAULT_INJECT (test hook).
S3 credentials come from AWS_ACCESS_KEY_ID / AWS_SECRET_ACCESS_KEY (a Kubernetes Secret).
"""
import os
import socket
import threading
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from common import s3util
from common.postprocess import extract_prediction
from common.prompt import build_prompt
from common.schema_check import check_output, load_schema

SCHEMA = load_schema(os.environ.get("SCHEMA_PATH", str(Path(__file__).resolve().parent.parent / "data" / "schema.json")))
STATE = {"ready": False, "generate": None, "error": None}
_lock = threading.Lock()


def load_model():
    """Download model + tokenizer from object storage and return generate(text)->raw text."""
    import torch
    from transformers import AutoModelForCausalLM, AutoTokenizer

    torch.set_num_threads(int(os.environ.get("OMP_NUM_THREADS", "1")))
    dest = Path("/tmp/model")
    n = s3util.download_prefix(s3util.client(os.environ["S3_ENDPOINT"]), os.environ["MODEL_URI"], dest)
    print(f"downloaded {n} model files from {os.environ['MODEL_URI']} (version {os.environ.get('MODEL_VERSION')})",
          flush=True)
    tok = AutoTokenizer.from_pretrained(dest)
    tok.pad_token = tok.eos_token
    model = AutoModelForCausalLM.from_pretrained(dest, torch_dtype=torch.float32, low_cpu_mem_usage=True).eval()
    max_new = int(os.environ.get("MAX_NEW_TOKENS", "64"))

    def generate(text):
        enc = tok(build_prompt(text), return_tensors="pt")
        with torch.no_grad():
            g = model.generate(**enc, max_new_tokens=max_new, do_sample=False, pad_token_id=tok.eos_token_id)
        return tok.decode(g[0][enc["input_ids"].shape[1]:], skip_special_tokens=True)

    return generate


def _loader():
    try:
        STATE["generate"] = load_model()
        STATE["ready"] = True
        print("model loaded, ready", flush=True)
    except Exception as e:  # noqa: BLE001
        STATE["error"] = repr(e)
        print("MODEL LOAD FAILED:", e, flush=True)


@asynccontextmanager
async def lifespan(app):
    threading.Thread(target=_loader, daemon=True).start()  # /healthz is up while this runs
    yield


app = FastAPI(lifespan=lifespan)


class ParseIn(BaseModel):
    text: str


def _headers():
    return {"X-Model-Version": os.environ.get("MODEL_VERSION", "unknown"),
            "X-Served-By": os.environ.get("POD_NAME") or socket.gethostname()}


@app.get("/healthz")
def healthz():
    return {"status": "alive"}


@app.get("/readyz")
def readyz():
    if STATE["ready"]:
        return {"status": "ready"}
    return JSONResponse({"status": "loading"}, status_code=503)


@app.post("/parse")
def parse(body: ParseIn):
    if not STATE["ready"]:
        return JSONResponse({"error": "model_not_ready"}, status_code=503, headers=_headers())
    with _lock:
        raw = STATE["generate"](body.text)
    pred = extract_prediction(raw)
    if os.environ.get("FAULT_INJECT") == "1":
        pred = "not json"
    ok, obj = check_output(pred, SCHEMA)
    if not ok:
        return JSONResponse({"error": "invalid_model_output"}, status_code=500, headers=_headers())
    return JSONResponse(obj, status_code=200, headers=_headers())
