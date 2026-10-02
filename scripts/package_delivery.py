"""Build the local, non-submission review archive from an explicit allowlist.

This script only copies/hashes bytes. It never runs a model, recalibrates a
threshold, scores a case, deletes a cache, or edits an experimental result.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path, PurePosixPath
import zipfile

ROOT = Path(__file__).resolve().parents[1]
DELIVERY = ROOT / "delivery"
NAME = "能智核_首轮复核包_非提交版"
ZIP_PATH = DELIVERY / (NAME + ".zip")
PREFIX = "nengzhihe/"
MANIFEST_MEMBER = PREFIX + "_package/文件清单.json"
NOTICE_MEMBER = PREFIX + "_package/复核包说明.txt"
MAX_FILE_BYTES = 32 * 1024 * 1024

# Optional exact paths are included only if present. No global recursive walk.
FIXED = {
    ".gitignore", "AGENTS.md", "README.md", "requirements.txt", "requirements.lock",
    "pyproject.toml", "engine.py", "model_client.py", "policies.py", "server.py",
    "protocol_draft.json",
    "data/index.json", "data/calibration.json", "data/policy_config.json",
    "data/data_contract.json", "data/source_manifest.json", "data/holdout_seal.json",
    "data/README.md", "data/raw/bdg2_LICENSE",
    "output/protocol_frozen.json", "output/benchmark.json", "output/benchmark_report.txt",
    "output/development_check.json", "output/development_model_warmup.json",
    "output/posthoc_failure_analysis.json", "output/review_before_holdout.txt",
    "output/metrics_independent_check.json", "output/final_verification.json", "output/首轮交付说明.txt",
    "output/evaluation_v1/benchmark_first_run.json",
    "output/evaluation_v1/execution_receipt.json", "output/evaluation_v1/metrics.csv",
    "output/evaluation_v1/progress.json", "output/evaluation_v1/scored_rows.json",
    "materials/使用说明.txt", "materials/填报内容.json", "materials/渲染状态.json",
    "materials/字数与要求核对.json", "materials/requirements.json",
    "materials/requirements.txt", "materials/requirements.md",
    "materials/参赛要求与方案调整.txt",
    "runtime/download_runtime.py", "runtime/download_model_ranges.py",
    "runtime/verify_downloads.py", "runtime/start_model.ps1", "runtime/stop_model.ps1",
    "runtime/run_smoke.py", "runtime/test_model_client_contract.py",
    "runtime/local_model_config.json", "runtime/README.txt", "runtime/MODEL_CARD.md",
    "runtime/MODEL_LICENSE.txt", "runtime/RUNNER_LICENSE.txt",
    "runtime/checksum_verification.json", "runtime/runner_version.txt",
    "runtime/model_repository.json", "runtime/model_file_metadata.json",
    "runtime/llama_release.json", "runtime/llama_binary_release.json",
    "runtime/Qwen3-4B-Q4_K_M.gguf.download.json",
    "runtime/llama-b11146-bin-win-cuda-13.4-x64.zip.download.json",
    "runtime/cudart-llama-bin-win-cuda-13.4-x64.zip.download.json",
}

# One directory level only. These are positive rules, not an exclusion-only ZIP.
DIRECTORIES = {
    "web": {".html", ".js", ".css", ".svg"},
    "scripts": {".py", ".ps1"},
    "data/cases": {".json"},
    "data/private": {".json"},
    "data/private/holdout_cases": {".json"},
    "output/evaluation_v1/predictions": {".json"},
    "output/demos": {".json"},
    "materials/drafts": {".txt", ".docx", ".pdf"},
    "materials/references": {".json", ".docx", ".pdf"},
    "materials/requirements": {".json", ".txt", ".md"},
}
FORBIDDEN_PARTS = {"working", "debug", "raw", "llama", "model_parts", "__pycache__", ".git"}
FORBIDDEN_SUFFIXES = {".gguf", ".bin", ".exe", ".dll", ".zip", ".part", ".log", ".pid", ".pyc"}
REQUIRED = {
    "engine.py", "model_client.py", "policies.py", "server.py", "README.md", "AGENTS.md",
    "scripts/package_delivery.py", "data/index.json", "data/calibration.json",
    "data/policy_config.json", "data/data_contract.json", "data/source_manifest.json",
    "data/holdout_seal.json", "data/README.md", "data/raw/bdg2_LICENSE", "data/private/dev_labels.json",
    "data/private/demo_labels.json", "data/private/holdout_labels.json",
    "output/protocol_frozen.json", "output/benchmark.json", "output/benchmark_report.txt",
    "output/evaluation_v1/benchmark_first_run.json", "output/evaluation_v1/execution_receipt.json",
    "output/evaluation_v1/scored_rows.json", "output/evaluation_v1/metrics.csv",
    "output/metrics_independent_check.json", "output/final_verification.json", "output/demos/manifest.json",
    "output/review_before_holdout.txt", "output/首轮交付说明.txt",
    "materials/使用说明.txt", "materials/字数与要求核对.json",
    "materials/references/reference_manifest.json", "runtime/local_model_config.json",
    "runtime/checksum_verification.json", "runtime/runner_version.txt",
}

NOTICE = """能智核首轮本地复核包——非正式提交版

本包包含源代码、已完成首轮实验的固定记录、开发/演示/留出小案例及标签、
三份申报底稿与四份原始参赛参考文件。含标签与本地复核信息，不是匿名正式
提交包。不得未经检查直接作为比赛正式材料上传。

本包不含模型权重、运行器二进制、原始大型下载、缓存、运行日志或PID。
下载并校验运行环境的步骤见runtime/README.txt。当前模型配置中的已验证状态
记录原机器验证事实，不表示新机器已经安装模型。

首轮原始汇总固定保存在output/evaluation_v1/benchmark_first_run.json。
420条预测、执行回执、冻结协议与独立指标复核记录均保留。使用相同案例再运行
只能称复现，不能称新的未见测试，也不能覆盖首轮证据后调参声称首轮收益。

材料目录是按原模板要求准备的非正式底稿；渲染/格式状态与未填项以材料说明
和核对文件为准，不因此宣称已形成可正式提交的匿名Word成品。

运行环境的小型说明、下载与校验资料是补充证据，不能追溯宣称已纳入本轮
冻结清单。打包动作只复制字节，没有重新推理、阈值校准、评分或缓存删除。

文件清单记录所有原项目文件的SHA256与字节数；清单及本说明属于打包元数据，
不递归计算自身SHA256。ZIP整体SHA256由包外同名.sha256文件提供。
"""


def sha(path: Path) -> str:
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def allowed(relative: str) -> bool:
    path = PurePosixPath(relative)
    if path.is_absolute() or ".." in path.parts or "\\" in relative:
        return False
    # The only authorized raw-directory exception is this small license text.
    if relative == "data/raw/bdg2_LICENSE":
        return True
    if any(part.lower() in FORBIDDEN_PARTS or part.lower().endswith(".ranges") for part in path.parts):
        return False
    if path.suffix.lower() in FORBIDDEN_SUFFIXES or path.name.lower().startswith("debug_"):
        return False
    return relative in FIXED or path.suffix.lower() in DIRECTORIES.get(str(path.parent), set())


def selected_paths() -> list[Path]:
    paths = {ROOT / rel for rel in FIXED if (ROOT / rel).is_file()}
    for directory, suffixes in DIRECTORIES.items():
        parent = ROOT / directory
        if parent.exists():
            paths.update(p for p in parent.iterdir() if p.is_file() and p.suffix.lower() in suffixes)
    result = []
    for path in sorted(paths, key=lambda p: p.relative_to(ROOT).as_posix()):
        rel = path.relative_to(ROOT).as_posix()
        if not allowed(rel):
            raise RuntimeError("Selected path violates allowlist: " + rel)
        if path.is_symlink() or not path.resolve().is_relative_to(ROOT.resolve()):
            raise RuntimeError("Symlink or path outside this project: " + rel)
        if path.stat().st_size > MAX_FILE_BYTES:
            raise RuntimeError("Unexpectedly large review-package file: " + rel)
        if rel == "data/raw/bdg2_LICENSE":
            if path.stat().st_size > 64 * 1024:
                raise RuntimeError("The single raw-directory license is no longer a small text file")
            path.read_text(encoding="utf-8-sig")
        result.append(path)
    return result


def inventory(validate_required: bool = True) -> dict:
    paths = selected_paths()
    relatives = {p.relative_to(ROOT).as_posix() for p in paths}
    missing = sorted(REQUIRED - relatives)
    if validate_required and missing:
        raise RuntimeError("Required files are not ready: " + ", ".join(missing))
    counts = {directory: sum(p.relative_to(ROOT).parent.as_posix() == directory for p in paths)
              for directory in DIRECTORIES}
    if validate_required and counts["output/evaluation_v1/predictions"] != 420:
        raise RuntimeError("Expected exactly 420 first-round prediction files")
    if validate_required and counts["data/private/holdout_cases"] != 42:
        raise RuntimeError("Expected exactly 42 sealed holdout payload files")
    records = [{"path": p.relative_to(ROOT).as_posix(), "bytes": p.stat().st_size, "sha256": sha(p)} for p in paths]
    frozen = json.loads((ROOT / "output/protocol_frozen.json").read_text(encoding="utf-8"))
    hashes = {r["path"]: r["sha256"] for r in records}
    for rel, expected in frozen["files_sha256"].items():
        if hashes.get(rel) != expected:
            raise RuntimeError("Frozen source missing or modified: " + rel)
    return {
        "format_version": 1,
        "purpose": "local_review_only_not_anonymous_contest_submission",
        "frozen_at_utc": frozen["frozen_at_utc"],
        "package_contains_case_labels": True,
        "model_weights_and_binaries_included": False,
        "single_raw_directory_exception": "data/raw/bdg2_LICENSE (small UTF-8 license text only)",
        "runtime_support_files_are_not_added_to_original_freeze": True,
        "operations": "copy_and_hash_bytes_only_no_inference_calibration_scoring_or_deletion",
        "source_file_count": len(records),
        "source_total_bytes": sum(r["bytes"] for r in records),
        "first_run_snapshot": "output/evaluation_v1/benchmark_first_run.json",
        "first_run_snapshot_sha256": hashes.get("output/evaluation_v1/benchmark_first_run.json"),
        "directory_counts": counts,
        "missing_required": missing,
        "source_files": records,
    }


def info(name: str, stamp: tuple[int, ...]) -> zipfile.ZipInfo:
    zi = zipfile.ZipInfo(name, stamp)
    zi.compress_type = zipfile.ZIP_DEFLATED
    zi.external_attr = 0o100644 << 16
    return zi


def verify_archive(path: Path) -> dict:
    with zipfile.ZipFile(path) as archive:
        bad = archive.testzip()
        if bad:
            raise RuntimeError("ZIP CRC failed: " + bad)
        manifest = json.loads(archive.read(MANIFEST_MEMBER))
        names = archive.namelist()
        expected = {PREFIX + r["path"] for r in manifest["source_files"]} | {MANIFEST_MEMBER, NOTICE_MEMBER}
        if len(names) != len(set(names)) or set(names) != expected:
            raise RuntimeError("Duplicate, missing or unexpected ZIP members")
        for record in manifest["source_files"]:
            if not allowed(record["path"]):
                raise RuntimeError("ZIP includes a path outside the positive allowlist")
            blob = archive.read(PREFIX + record["path"])
            if len(blob) != record["bytes"] or hashlib.sha256(blob).hexdigest() != record["sha256"]:
                raise RuntimeError("ZIP payload mismatch: " + record["path"])
    return {"verified": True, "source_file_count": manifest["source_file_count"], "archive_member_count": len(names),
            "zip_bytes": path.stat().st_size, "zip_sha256": sha(path)}


def build() -> dict:
    manifest = inventory()
    stamp_dt = datetime.fromisoformat(manifest["frozen_at_utc"])
    stamp = (stamp_dt.year, stamp_dt.month, stamp_dt.day, stamp_dt.hour, stamp_dt.minute, stamp_dt.second)
    encoded = json.dumps(manifest, ensure_ascii=False, indent=2).encode("utf-8")
    DELIVERY.mkdir(exist_ok=True)
    temporary = ZIP_PATH.with_suffix(".zip.tmp")
    with zipfile.ZipFile(temporary, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        for record in manifest["source_files"]:
            blob = (ROOT / record["path"]).read_bytes()
            if len(blob) != record["bytes"] or hashlib.sha256(blob).hexdigest() != record["sha256"]:
                raise RuntimeError("Input changed while packaging: " + record["path"])
            archive.writestr(info(PREFIX + record["path"], stamp), blob, compresslevel=9)
        archive.writestr(info(MANIFEST_MEMBER, stamp), encoded, compresslevel=9)
        archive.writestr(info(NOTICE_MEMBER, stamp), NOTICE.encode("utf-8"), compresslevel=9)
    result = verify_archive(temporary)
    # Abort on concurrent input edits instead of silently mixing versions.
    for record in manifest["source_files"]:
        if sha(ROOT / record["path"]) != record["sha256"]:
            raise RuntimeError("Source changed before package finalization: " + record["path"])
    temporary.replace(ZIP_PATH)
    (DELIVERY / (NAME + "_文件清单.json")).write_bytes(encoded)
    rows = ["path\tbytes\tsha256"] + [f"{r['path']}\t{r['bytes']}\t{r['sha256']}" for r in manifest["source_files"]]
    (DELIVERY / (NAME + "_文件清单.tsv")).write_text("\n".join(rows) + "\n", encoding="utf-8-sig")
    (DELIVERY / (NAME + "_SHA256SUMS.txt")).write_text(
        "\n".join(f"{r['sha256']}  {r['path']}" for r in manifest["source_files"]) + "\n", encoding="utf-8")
    ZIP_PATH.with_suffix(".zip.sha256").write_text(result["zip_sha256"] + "  " + ZIP_PATH.name + "\n", encoding="utf-8")
    receipt = {**result, "zip_path": str(ZIP_PATH), "built_at_utc": datetime.now(timezone.utc).isoformat(),
               "prediction_files": manifest["directory_counts"]["output/evaluation_v1/predictions"],
               "holdout_payload_files": manifest["directory_counts"]["data/private/holdout_cases"],
               "first_run_snapshot_sha256": manifest["first_run_snapshot_sha256"],
               "cache_deletions": 0, "inference_calls": 0, "threshold_updates": 0}
    (DELIVERY / (NAME + "_构建回执.json")).write_text(json.dumps(receipt, ensure_ascii=False, indent=2), encoding="utf-8")
    return receipt


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--inventory", action="store_true", help="Read-only byte inventory; list pending required files")
    mode.add_argument("--build", action="store_true", help="Build only after material completion has been confirmed")
    mode.add_argument("--verify", type=Path, help="Verify an existing archive without extracting it")
    parser.add_argument("--materials-ready", action="store_true", help="Record the operator's confirmed material readiness")
    args = parser.parse_args()
    if args.build:
        if not args.materials_ready:
            parser.error("--build requires --materials-ready after actual material completion")
        result = build()
    elif args.verify:
        result = verify_archive(args.verify)
    else:
        result = inventory(validate_required=False)
        result.pop("source_files")
    print(json.dumps(result, ensure_ascii=False, indent=2))
