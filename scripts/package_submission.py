"""Build submission/<roll>.zip: report, handwritten reflection, source tree, README.md (links) at the top level."""
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ROLL = "230101021"
SKIP_DIRS = {".git", ".secrets", "models_out", "dist", "submission", "__pycache__", ".venv", ".pytest_cache", ".ruff_cache"}
SKIP_SUFFIX = {".safetensors", ".bin", ".pt", ".pyc"}


def main():
    refl = ROOT / "reflection" / f"{ROLL}.pdf"
    for need in (ROOT / "report" / "report.pdf", refl, ROOT / "README.md"):
        if not need.exists():
            print("MISSING:", need.relative_to(ROOT))
    out = ROOT / "submission"
    out.mkdir(exist_ok=True)
    z = out / f"{ROLL}.zip"
    with zipfile.ZipFile(z, "w", zipfile.ZIP_DEFLATED) as zf:
        for p in sorted(ROOT.rglob("*")):
            rel = p.relative_to(ROOT)
            if p.is_dir() or set(rel.parts) & SKIP_DIRS or p.suffix in SKIP_SUFFIX:
                continue
            zf.write(p, rel.as_posix())
        if refl.exists():
            zf.write(refl, f"{ROLL}.pdf")   # also at top level, exactly <roll_number>.pdf
    print("wrote", z)
    sys.exit(0)


if __name__ == "__main__":
    main()
