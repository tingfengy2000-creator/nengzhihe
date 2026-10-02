"""Verify official checksums before extracting or executing any downloaded file."""
import hashlib
import json
from pathlib import Path
import zipfile

ROOT = Path(__file__).resolve().parent
EXPECTED = {
    "Qwen3-4B-Q4_K_M.gguf": "7485fe6f11af29433bc51cab58009521f205840f5b4ae3a32fa7f92e8534fdf5",
    "llama-b11146-bin-win-cuda-13.4-x64.zip": "b1866c0ce76bc7bfb0c24b33e9a37e9669f1be18539b12c74ce361f81c41f047",
    "cudart-llama-bin-win-cuda-13.4-x64.zip": "738f8c251ac22b70c3ae6f83a10cf222725df0395246a2cf58f32bdb85fbe668",
}

if __name__ == "__main__":
    checks = []
    for name, expected in EXPECTED.items():
        path = ROOT / name
        with path.open("rb") as stream:
            actual = hashlib.file_digest(stream, "sha256").hexdigest()
        record = {"name": name, "expected_sha256": expected, "actual_sha256": actual, "matches": actual == expected, "bytes": path.stat().st_size}
        checks.append(record)
        print(json.dumps(record), flush=True)
        if actual != expected:
            raise RuntimeError(f"Official checksum mismatch for {name}")
    target = ROOT / "llama"
    target.mkdir(exist_ok=True)
    for name in EXPECTED:
        if not name.endswith(".zip"):
            continue
        with zipfile.ZipFile(ROOT / name) as archive:
            for entry in archive.infolist():
                resolved = (target / entry.filename).resolve()
                if not resolved.is_relative_to(target.resolve()):
                    raise RuntimeError("Unsafe archive member")
            archive.extractall(target)
    (ROOT / "checksum_verification.json").write_text(json.dumps(checks, indent=2), encoding="utf-8")
