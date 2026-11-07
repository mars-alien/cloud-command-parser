import json

from common.postprocess import extract_prediction
from worker.clean import clean, classify


def rec(i, text, raw):
    return {"id": i, "text": text, "teacher_raw": raw}


def good(**kw):
    d = {"intent": "weather_query", "date": None, "time": None, "place": "london"}
    d.update(kw)
    return json.dumps(d)


def test_extract_first_json_object_only():
    assert extract_prediction('{"a": 1} trailing junk\nmore') == '{"a": 1}'
    assert extract_prediction('Command: what is the weather in london\nJSON: {"a": 1} trailing junk') == '{"a": 1}'
    assert extract_prediction('prefix before json\n{"a": 1}\nCommand: x') == '{"a": 1}'
    assert extract_prediction("not json at all") == "not json at all"
    assert extract_prediction("   ") == ""


def test_classify_reasons():
    t = "what is the weather in london"
    assert classify(rec("1", t, "oops")) == "a"
    assert classify(rec("1", t, '{"intent": "weather_query"}')) == "b"
    assert classify(rec("1", t, good(intent="play_music"))) == "c"
    assert classify(rec("1", t, good(place="paris"))) == "d"
    assert classify(rec("1", t, good())) is None


def test_clean_counts_dedupe_and_order():
    t = "what is the weather in london"
    records = [
        rec("C3", t, good()),                      # duplicate of C1 -> dropped, C1 kept
        rec("C1", t, good()),
        rec("C2", "other command", "bad"),         # (a)
        rec("C4", "x", good(place="nowhere")),     # (d)
    ]
    body, counts = clean(records)
    assert counts == {"input": 4, "a_invalid_json": 1, "b_bad_keys": 0, "c_bad_intent": 0,
                      "d_bad_slot": 1, "duplicates": 1, "kept": 1}
    lines = body.decode().splitlines()
    assert json.loads(lines[0])["id"] == "C1"
    assert b"\r" not in body


def test_clean_is_deterministic():
    t = "what is the weather in london"
    r = [rec("C1", t, good())]
    assert clean(r)[0] == clean(list(reversed(r)))[0]
