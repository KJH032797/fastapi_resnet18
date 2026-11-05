#!/usr/bin/env python3
"""Audit image filename and exact-byte duplicates across dataset splits.

Run from any working directory. The project root is inferred from this file's
location after it is placed in ``<project>/scripts/``.
"""

from __future__ import annotations

import csv
import filecmp
import hashlib
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DATASET_ROOT = PROJECT_ROOT / "dataset"
SPLITS = ("train", "val", "test")
IMAGE_SUFFIXES = {".jpg", ".jpeg", ".png", ".webp", ".bmp", ".tif", ".tiff"}


@dataclass(frozen=True)
class ImageFile:
    split: str
    class_name: str
    path: Path

    @property
    def relative_path(self) -> str:
        return self.path.relative_to(PROJECT_ROOT).as_posix()


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as file:
        for chunk in iter(lambda: file.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def collect_images() -> list[ImageFile]:
    missing = [split for split in SPLITS if not (DATASET_ROOT / split).is_dir()]
    if missing:
        raise FileNotFoundError(
            f"Missing dataset split folder(s): {', '.join(missing)}; "
            f"expected under {DATASET_ROOT}"
        )

    images: list[ImageFile] = []
    for split in SPLITS:
        split_root = DATASET_ROOT / split
        for path in sorted(split_root.rglob("*")):
            if path.is_file() and path.suffix.lower() in IMAGE_SUFFIXES:
                images.append(ImageFile(split, path.parent.name, path))
    return images


def write_csv(path: Path, fieldnames: list[str], rows: list[dict[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as file:
        writer = csv.DictWriter(file, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def filename_duplicates(images: list[ImageFile]) -> list[dict[str, str]]:
    grouped: dict[str, list[ImageFile]] = defaultdict(list)
    for image in images:
        grouped[image.path.name.casefold()].append(image)

    rows: list[dict[str, str]] = []
    for entries in grouped.values():
        if len({entry.split for entry in entries}) < 2:
            continue
        for entry in entries:
            rows.append(
                {
                    "filename": entry.path.name,
                    "split": entry.split,
                    "class": entry.class_name,
                    "relative_path": entry.relative_path,
                }
            )
    return sorted(rows, key=lambda row: (row["filename"].casefold(), row["split"], row["relative_path"]))


def byte_duplicate_rows(images: list[ImageFile]) -> list[dict[str, str]]:
    by_hash: dict[str, list[ImageFile]] = defaultdict(list)
    for image in images:
        by_hash[sha256(image.path)].append(image)

    rows: list[dict[str, str]] = []
    for digest, entries in by_hash.items():
        if len({entry.split for entry in entries}) < 2:
            continue

        # SHA-256 narrows candidates; byte comparison confirms exact equality.
        byte_groups: list[list[ImageFile]] = []
        for entry in entries:
            for group in byte_groups:
                if filecmp.cmp(entry.path, group[0].path, shallow=False):
                    group.append(entry)
                    break
            else:
                byte_groups.append([entry])

        for group in byte_groups:
            if len({entry.split for entry in group}) < 2:
                continue
            for entry in group:
                rows.append(
                    {
                        "sha256": digest,
                        "split": entry.split,
                        "class": entry.class_name,
                        "filename": entry.path.name,
                    }
                )
    return sorted(rows, key=lambda row: (row["sha256"], row["split"], row["class"], row["filename"]))


def main() -> None:
    images = collect_images()
    filename_rows = filename_duplicates(images)
    exact_byte_rows = byte_duplicate_rows(images)

    filename_report = PROJECT_ROOT / "reports/data/filename_cross_split_duplicates.csv"
    byte_report = PROJECT_ROOT / "reports/data/exact_cross_split_duplicates.csv"

    write_csv(
        filename_report,
        ["filename", "split", "class", "relative_path"],
        filename_rows,
    )
    write_csv(byte_report, ["sha256", "split", "class", "filename"], exact_byte_rows)

    print(f"총 {len(images)}개의 이미지 파일을 확인했습니다. (대상 경로: {DATASET_ROOT})")
    print(
        f"분할 간 파일명 중복 이미지 항목 수: {len(filename_rows)} "
        f"(결과 파일: {filename_report.relative_to(PROJECT_ROOT)})"
    )
    print(
        f"분할 간 바이트 완전 일치 이미지 항목 수: {len(exact_byte_rows)} "
        f"(결과 파일: {byte_report.relative_to(PROJECT_ROOT)})"
    )
    if not filename_rows:
        print("분할 간 파일명이 같은 이미지가 없습니다.")
    if not exact_byte_rows:
        print("분할 간 바이트가 완전히 같은 이미지가 없습니다.")


if __name__ == "__main__":
    main()
