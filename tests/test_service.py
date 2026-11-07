import pytest
from fastapi.testclient import TestClient

import service.app as appmod

GOOD = '{"intent": "weather_query", "date": null, "time": null, "place": "london"}'


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setenv("MODEL_VERSION", "v1")
    monkeypatch.delenv("FAULT_INJECT", raising=False)
    monkeypatch.setattr(appmod, "load_model", lambda: (lambda text: " " + GOOD + "\nCommand: x"))
    appmod.STATE.update(ready=False, generate=None, error=None)
    with TestClient(appmod.app) as c:
        for _ in range(100):
            if appmod.STATE["ready"]:
                break
            import time
            time.sleep(0.02)
        yield c


def test_health_ready_and_headers(client):
    assert client.get("/healthz").status_code == 200
    assert client.get("/readyz").status_code == 200
    r = client.post("/parse", json={"text": "what is the weather in london"})
    assert r.status_code == 200
    assert r.json() == {"intent": "weather_query", "date": None, "time": None, "place": "london"}
    assert r.headers["X-Model-Version"] == "v1"
    assert r.headers["X-Served-By"]


def test_not_ready_returns_503(monkeypatch):
    import threading
    gate = threading.Event()
    monkeypatch.setattr(appmod, "load_model", lambda: (gate.wait(5), (lambda t: GOOD))[1])
    appmod.STATE.update(ready=False, generate=None, error=None)
    with TestClient(appmod.app) as c:
        assert c.get("/healthz").status_code == 200
        assert c.get("/readyz").status_code == 503
        gate.set()


def test_fault_injection_gives_500(client, monkeypatch):
    monkeypatch.setenv("FAULT_INJECT", "1")
    r = client.post("/parse", json={"text": "anything"})
    assert r.status_code == 500
    assert r.json() == {"error": "invalid_model_output"}


def test_invalid_model_output_never_200(client):
    appmod.STATE["generate"] = lambda text: '{"intent": "nope", "date": null, "time": null, "place": null}'
    r = client.post("/parse", json={"text": "x"})
    assert r.status_code == 500 and r.json() == {"error": "invalid_model_output"}
