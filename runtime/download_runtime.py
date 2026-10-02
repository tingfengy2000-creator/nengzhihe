"""Download the pinned public runner and model, retaining provenance."""
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import hashlib
import json
import urllib.request
import time

ROOT = Path(__file__).resolve().parent
MODEL_REVISION = "bc640142c66e1fdd12af0bd68f40445458f3869b"
FILES = {
    "llama-b11146-bin-win-cuda-13.4-x64.zip": "https://github.com/ggml-org/llama.cpp/releases/download/b11146/llama-b11146-bin-win-cuda-13.4-x64.zip",
    "cudart-llama-bin-win-cuda-13.4-x64.zip": "https://github.com/ggml-org/llama.cpp/releases/download/b11146/cudart-llama-bin-win-cuda-13.4-x64.zip",
    "Qwen3-4B-Q4_K_M.gguf": f"https://huggingface.co/Qwen/Qwen3-4B-GGUF/resolve/{MODEL_REVISION}/Qwen3-4B-Q4_K_M.gguf",
    "MODEL_LICENSE.txt": f"https://huggingface.co/Qwen/Qwen3-4B-GGUF/resolve/{MODEL_REVISION}/LICENSE",
    "MODEL_CARD.md": f"https://huggingface.co/Qwen/Qwen3-4B-GGUF/resolve/{MODEL_REVISION}/README.md",
    "RUNNER_LICENSE.txt": "https://raw.githubusercontent.com/ggml-org/llama.cpp/b11146/LICENSE",
}

def download(item):
    name, url = item
    path = ROOT / name
    started = time.perf_counter()
    req = urllib.request.Request(url, headers={"User-Agent": "Nengzhihe-Reproducible-Pilot/0.1"})
    digest = hashlib.sha256()
    with urllib.request.urlopen(req, timeout=90) as response, path.with_suffix(path.suffix + ".part").open("wb") as handle:
        expected = response.headers.get("Content-Length")
        size = 0
        while chunk := response.read(4 * 1024 * 1024):
            handle.write(chunk)
            digest.update(chunk)
            size += len(chunk)
    if expected and size != int(expected):
        raise RuntimeError(f"{name}: size mismatch {size} != {expected}")
    path.with_suffix(path.suffix + ".part").replace(path)
    result = {"name": name, "source": url, "bytes": size, "sha256": digest.hexdigest(), "download_seconds": round(time.perf_counter() - started, 3)}
    print(json.dumps(result), flush=True)
    return result

if __name__ == "__main__":
    with ThreadPoolExecutor(max_workers=3) as pool:
        results = list(pool.map(download, FILES.items()))
    (ROOT / "download_manifest.json").write_text(json.dumps(results, indent=2), encoding="utf-8")
