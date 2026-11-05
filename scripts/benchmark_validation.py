#!/usr/bin/env python3
"""Repeat sync/async inference timing on five Validation images.

Run from the project root with the project virtual environment active:
  python scripts/benchmark_validation.py [--seed 42]

Five unique image files are selected randomly from dataset/val. Pass --seed to
repeat the same selection.

Only the selected images' cache keys in Redis DB 1 are deleted. PostgreSQL and
Redis DB 2/3 are not modified by cache preparation.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import mimetypes
import re
import random
import statistics
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlsplit

import httpx
import redis

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from ai.config import MODEL_PATH, REDIS_CACHE_URL
from ai.services import cache_key


PROJECT_ROOT = Path(__file__).resolve().parents[1]
VAL_ROOT = (PROJECT_ROOT / "dataset" / "val").resolve()
CSV_FIELDS = [
    "run_id", "split", "mode", "cache_status", "path", "http_ms",
    "final_ms", "inference_ms", "cache_hit", "job_id", "top1_label",
    "top1_score",
]


def select_random_images(seed: int | None = None) -> list[tuple[Path, str, bytes]]:
    """Select five distinct image contents from the Validation split."""
    supported = {".jpg", ".jpeg", ".png", ".webp"}
    candidates = [p for p in sorted(VAL_ROOT.rglob("*"))
                  if p.is_file() and p.suffix.lower() in supported]
    if not candidates:
        raise FileNotFoundError(f"Validation 이미지가 없습니다: {VAL_ROOT}")

    # 중복 파일 내용은 하나의 후보로만 취급해 서로 다른 이미지 5장을 보장한다.
    by_content: dict[str, tuple[Path, str, bytes]] = {}
    for path in candidates:
        data = path.read_bytes()
        key = cache_key(data)
        by_content.setdefault(key, (path, path.relative_to(VAL_ROOT).as_posix(), data))
    unique = list(by_content.values())
    if len(unique) < 5:
        raise ValueError(f"서로 다른 이미지가 5장보다 적습니다: {len(unique)}장")
    random.Random(seed).shuffle(unique)
    return unique[:5]


def delete_selected_cache_keys(records: list[tuple[Path, str, bytes]]) -> int:
    parsed = urlsplit(REDIS_CACHE_URL)
    db_number = int(parsed.path.lstrip("/") or "0")
    if db_number != 1:
        raise RuntimeError(f"캐시 URL이 Redis DB 1이 아닙니다(DB {db_number}). 중단합니다.")
    client = redis.Redis.from_url(REDIS_CACHE_URL, decode_responses=True)
    client.ping()
    keys = list(dict.fromkeys(cache_key(data) for _, _, data in records))
    deleted = client.delete(*keys)
    remaining = client.exists(*keys)
    client.close()
    if remaining:
        raise RuntimeError("선택한 캐시 키가 남아 있어 MISS 측정을 시작하지 않습니다.")
    return deleted


def post_sync(client: httpx.Client, base_url: str, record: tuple[Path, str, bytes],
              expected_hit: bool, run_id: str) -> dict:
    _, relative, image_bytes = record
    content_type = mimetypes.guess_type(relative)[0] or "application/octet-stream"
    started = time.perf_counter()
    response = client.post(
        f"{base_url}/api/sync/classify/",
        files={"image": (Path(relative).name, image_bytes, content_type)},
    )
    elapsed = round((time.perf_counter() - started) * 1000, 2)
    response.raise_for_status()
    payload = response.json()
    if payload.get("cache_hit") is not expected_hit:
        raise RuntimeError(f"{run_id}: 예상 cache_hit={expected_hit}, 실제={payload.get('cache_hit')}")
    return {
        "run_id": run_id, "split": "val", "mode": "sync",
        "cache_status": "HIT" if expected_hit else "MISS", "path": relative,
        "http_ms": elapsed, "final_ms": elapsed,
        "inference_ms": payload.get("inference_ms"), "cache_hit": payload.get("cache_hit"),
        "job_id": None, "top1_label": payload["top1"]["label"],
        "top1_score": payload["top1"]["score"], "http_status": response.status_code,
        "response": payload,
    }


def post_async(client: httpx.Client, base_url: str, record: tuple[Path, str, bytes],
               expected_hit: bool, run_id: str, poll_interval: float,
               timeout: float) -> dict:
    _, relative, image_bytes = record
    content_type = mimetypes.guess_type(relative)[0] or "application/octet-stream"
    started = time.perf_counter()
    accepted = client.post(
        f"{base_url}/api/async/classify/",
        files={"image": (Path(relative).name, image_bytes, content_type)},
    )
    accepted_ms = round((time.perf_counter() - started) * 1000, 2)
    if accepted.status_code != 202:
        raise RuntimeError(f"{run_id}: 예상 HTTP 202, 실제 HTTP {accepted.status_code}: {accepted.text}")
    queued = accepted.json()
    job_id = queued["job_id"]
    check_url = queued.get("check_url", f"/api/async/jobs/{job_id}/")

    while True:
        remaining = timeout - (time.perf_counter() - started)
        if remaining <= 0:
            raise TimeoutError(f"{run_id}: Job {job_id}가 {timeout}초 안에 완료되지 않았습니다.")
        state = client.get(check_url, timeout=remaining)
        state.raise_for_status()
        payload = state.json()
        if payload.get("status") == "done":
            final_ms = round((time.perf_counter() - started) * 1000, 2)
            if payload.get("cache_hit") is not expected_hit:
                raise RuntimeError(f"{run_id}: 예상 cache_hit={expected_hit}, 실제={payload.get('cache_hit')}")
            return {
                "run_id": run_id, "split": "val", "mode": "async",
                "cache_status": "HIT" if expected_hit else "MISS", "path": relative,
                "http_ms": accepted_ms, "final_ms": final_ms,
                "inference_ms": payload.get("inference_ms"), "cache_hit": payload.get("cache_hit"),
                "job_id": job_id, "top1_label": payload["top1"]["label"],
                "top1_score": payload["top1"]["score"], "http_status": accepted.status_code,
                "response": payload,
            }
        if payload.get("status") == "failed":
            raise RuntimeError(f"{run_id}: Job {job_id} failed: {payload.get('error_message')}")
        remaining = timeout - (time.perf_counter() - started)
        if remaining <= 0:
            raise TimeoutError(f"{run_id}: Job {job_id}가 {timeout}초 안에 완료되지 않았습니다.")
        time.sleep(min(poll_interval, remaining))


def median(values: list[float | None]) -> float | None:
    present = [float(value) for value in values if value is not None]
    return round(statistics.median(present), 2) if present else None



def write_outputs(all_records: list[dict], records: list[tuple[Path, str, bytes]],
                  args: argparse.Namespace, csv_path: Path, json_path: Path,
                  run_status: str, error: str | None = None) -> dict:
    with csv_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=CSV_FIELDS)
        writer.writeheader()
        for row in all_records:
            writer.writerow({key: row.get(key) for key in CSV_FIELDS})

    groups = {}
    for mode in ("sync", "async"):
        for status in ("MISS", "HIT"):
            subset = [r for r in all_records if r["mode"] == mode and r["cache_status"] == status]
            groups[f"{mode}_{status.lower()}"] = {
                "count": len(subset), "http_median_ms": median([r["http_ms"] for r in subset]),
                "final_median_ms": median([r["final_ms"] for r in subset]),
                "inference_median_ms": median([r["inference_ms"] for r in subset]),
            }
    payload = {
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "run_status": run_status, "error": error,
        "model_id": MODEL_PATH, "source_split": "val", "image_count": 5,
        "poll_interval_ms": round(args.poll_interval * 1000, 2),
        "worker_condition": "Use the project's running solo/concurrency=1 worker.",
        "cache_policy": "Delete only selected five image keys in Redis DB 1 before each MISS group.",
        "selected_images": [
            {"path": rel, "sha256": hashlib.sha256(data).hexdigest()}
            for _, rel, data in records
        ],
        "groups": groups, "records": all_records,
    }
    json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return groups

def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--seed", type=int, help="랜덤 선택 재현용 시드(생략하면 매번 무작위)")
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    parser.add_argument("--poll-interval", type=float, default=0.1)
    parser.add_argument("--timeout", type=float, default=120.0)
    parser.add_argument("--name", default="validation_benchmark_5x",
                        help="결과 파일 접두사. 기본 파일이 있으면 덮어쓰지 않습니다.")
    args = parser.parse_args()
    if args.poll_interval <= 0 or args.timeout <= 0:
        parser.error("poll interval과 timeout은 0보다 커야 합니다.")
    if not re.fullmatch(r"[A-Za-z0-9_-]+", args.name):
        parser.error("--name에는 영문자, 숫자, 밑줄, 하이픈만 사용할 수 있습니다.")
    parsed_base = urlsplit(args.base_url)
    if parsed_base.scheme != "http" or parsed_base.hostname not in {"127.0.0.1", "localhost"}:
        parser.error("이 스크립트는 로컬 평가 서버(http://127.0.0.1 또는 localhost)만 허용합니다.")
    args.base_url = args.base_url.rstrip("/")

    all_records = []
    csv_path = json_path = None
    records = []
    try:
        records = select_random_images(args.seed)
        print("선택된 Validation 이미지:")
        for _, relative, _ in records:
            print(f"- dataset/val/{relative}")
        data_dir = PROJECT_ROOT / "reports" / "data"
        evidence_dir = PROJECT_ROOT / "reports" / "evidence"
        csv_path = data_dir / f"timings_{args.name}.csv"
        json_path = evidence_dir / f"performance_{args.name}.json"
        if csv_path.exists() or json_path.exists():
            raise FileExistsError("결과 파일이 이미 있습니다. --name을 바꿔 덮어쓰기를 피하세요.")
        data_dir.mkdir(parents=True, exist_ok=True)
        evidence_dir.mkdir(parents=True, exist_ok=True)
        print("모델을 적어도 한 번 실행해 워밍업한 뒤 이 스크립트를 시작하세요.")

        with httpx.Client(timeout=args.timeout, base_url=args.base_url) as client:
            for label, expected_hit in (("sync_miss", False), ("sync_hit", True)):
                if label == "sync_miss":
                    deleted = delete_selected_cache_keys(records)
                    print(f"Redis DB 1: 동기 MISS용 선택 키 {deleted}개 삭제")
                print(f"{label}: 시작")
                for index, record in enumerate(records, start=1):
                    all_records.append(post_sync(client, args.base_url, record, expected_hit,
                                                 f"{label}_{index}"))

            deleted = delete_selected_cache_keys(records)
            print(f"Redis DB 1: 비동기 MISS용 선택 키 {deleted}개 삭제")
            for label, expected_hit in (("async_miss", False), ("async_hit", True)):
                print(f"{label}: 시작")
                for index, record in enumerate(records, start=1):
                    all_records.append(post_async(client, args.base_url, record, expected_hit,
                                                  f"{label}_{index}", args.poll_interval,
                                                  args.timeout))

        groups = write_outputs(all_records, records, args, csv_path, json_path,
                               run_status="completed")
        print(f"CSV: {csv_path.relative_to(PROJECT_ROOT)}")
        print(f"JSON: {json_path.relative_to(PROJECT_ROOT)}")
        print(json.dumps(groups, ensure_ascii=False, indent=2))
        return 0
    except Exception as exc:
        print(f"측정 중단: {exc}", file=sys.stderr)
        if all_records and csv_path is not None and json_path is not None:
            try:
                write_outputs(all_records, records, args, csv_path, json_path,
                              run_status="partial", error=str(exc))
                print(f"부분 결과 CSV: {csv_path.relative_to(PROJECT_ROOT)}", file=sys.stderr)
                print(f"부분 결과 JSON: {json_path.relative_to(PROJECT_ROOT)}", file=sys.stderr)
            except Exception as save_exc:
                print(f"부분 결과 저장 실패: {save_exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
