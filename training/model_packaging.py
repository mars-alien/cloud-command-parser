"""Deterministic zip of a model dir + SHA-256 (the GitHub Release asset)."""
import hashlib
import zipfile
from pathlib import Path


def package(model_dir, zip_path):
    model_dir, zip_path = Path(model_dir), Path(zip_path)
    zip_path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as z:
        for p in sorted(model_dir.iterdir()):
            if p.is_file() and p.name != "model.sha256":
                info = zipfile.ZipInfo(p.name, date_time=(2020, 1, 1, 0, 0, 0))
                info.compress_type = zipfile.ZIP_DEFLATED
                z.writestr(info, p.read_bytes())
    digest = hashlib.sha256(zip_path.read_bytes()).hexdigest()
    (model_dir / "model.sha256").write_text(f"{digest}  {zip_path.name}\n", encoding="utf-8", newline="\n")
    return digest
