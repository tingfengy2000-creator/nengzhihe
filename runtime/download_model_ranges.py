"""Resume the pinned model in verified HTTP ranges on a slow connection."""
from concurrent.futures import ThreadPoolExecutor, as_completed
import hashlib
import json
from pathlib import Path
import time
import urllib.request
import argparse

ROOT = Path(__file__).resolve().parent
URL = "https://huggingface.co/Qwen/Qwen3-4B-GGUF/resolve/bc640142c66e1fdd12af0bd68f40445458f3869b/Qwen3-4B-Q4_K_M.gguf"
TOTAL = 2497280256
CHUNK = 8 * 1024 * 1024
PARTS = ROOT / "model_parts"
PARTS.mkdir(exist_ok=True)

def get_part(index):
    start = index * CHUNK
    end = min(start + CHUNK, TOTAL) - 1
    path = PARTS / f"{index:04d}.bin"
    if path.exists() and path.stat().st_size == end - start + 1:
        return index
    for attempt in range(4):
        try:
            req = urllib.request.Request(URL, headers={"Range": f"bytes={start}-{end}", "User-Agent": "Nengzhihe/0.1"})
            with urllib.request.urlopen(req, timeout=90) as response:
                expected_range = f"bytes {start}-{end}/{TOTAL}"
                if response.status != 206 or response.headers.get("Content-Range") != expected_range:
                    raise RuntimeError(f"Unexpected range {response.status} {response.headers.get('Content-Range')}")
                with path.with_suffix(".part").open("wb") as handle:
                    while block := response.read(1024 * 1024):
                        handle.write(block)
            if path.with_suffix(".part").stat().st_size != end - start + 1:
                raise RuntimeError("Range length mismatch")
            path.with_suffix(".part").replace(path)
            return index
        except Exception:
            if attempt == 3:
                raise
            time.sleep(attempt + 1)

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", default=URL)
    parser.add_argument("--size", type=int, default=TOTAL)
    parser.add_argument("--name", default="Qwen3-4B-Q4_K_M.gguf")
    parser.add_argument("--workers", type=int, default=48)
    args = parser.parse_args()
    URL, TOTAL = args.url, args.size
    if Path(args.name).name != args.name:
        raise ValueError("Filename only")
    PARTS = ROOT / (args.name + ".ranges")
    if args.name == "Qwen3-4B-Q4_K_M.gguf":
        PARTS = ROOT / "model_parts"
    PARTS.mkdir(exist_ok=True)
    started = time.perf_counter()
    count = (TOTAL + CHUNK - 1) // CHUNK
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        futures = [pool.submit(get_part, i) for i in range(count)]
        for done, future in enumerate(as_completed(futures), 1):
            future.result()
            if done % 12 == 0 or done == count:
                print(f"ranges_complete={done}/{count} elapsed_seconds={time.perf_counter()-started:.1f}", flush=True)
    final = ROOT / args.name
    digest = hashlib.sha256()
    with final.open("wb") as out:
        for i in range(count):
            with (PARTS / f"{i:04d}.bin").open("rb") as source:
                while block := source.read(4 * 1024 * 1024):
                    out.write(block)
                    digest.update(block)
    result = {"name": final.name, "source": URL, "bytes": final.stat().st_size, "sha256": digest.hexdigest(), "download_seconds": round(time.perf_counter()-started,3), "ranges": count}
    (ROOT / (args.name + ".download.json")).write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(json.dumps(result), flush=True)
