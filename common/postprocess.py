"""Turn raw generated text into the prediction string (shared by evaluate.py and the service)."""
import json


def extract_prediction(generated: str) -> str:
    s = (generated or "").strip()
    if not s:
        return ""

    for start in range(len(s)):
        if s[start] not in "{[":
            continue
        try:
            _, end = json.JSONDecoder().raw_decode(s[start:])
            return s[start:start + end]
        except ValueError:
            continue

    return s
