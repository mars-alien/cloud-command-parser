import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def test_nacl_sample_packets_all_correct():
    r = subprocess.run([sys.executable, "tools/nacl_sim.py", "network/nacl.json", "network/packets_sample.jsonl",
                        "--check"], cwd=ROOT, capture_output=True, text=True)
    assert "6 / 6" in r.stdout


def test_deny_rule_is_lowest_numbered_inbound():
    import json
    n = json.loads((ROOT / "network" / "nacl.json").read_text())
    first = min(n["inbound"], key=lambda r: r["rule"])
    assert first["action"] == "deny" and first["cidr"] == "198.51.100.0/24"
