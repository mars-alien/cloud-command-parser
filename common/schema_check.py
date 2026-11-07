"""Validate model output against data/schema.json."""
import json
from pathlib import Path


def load_schema(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def check_output(text, schema):
    """Return (ok, parsed_object_or_None)."""
    import jsonschema

    try:
        obj = json.loads(text)
        jsonschema.validate(obj, schema["json_schema"])
    except (ValueError, TypeError, jsonschema.ValidationError):
        return False, None
    return True, obj
