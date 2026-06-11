"""Synthetic dataset indexing and deterministic split assignment."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from curve.synthetic import generate_synthetic_sample


@dataclass(frozen=True)
class DatasetSplit:
    train: int
    val: int
    test: int


def split_counts(count: int, *, val: int = 1, test: int = 1) -> DatasetSplit:
    if count <= 0:
        return DatasetSplit(train=0, val=0, test=0)
    test_count = min(test, count)
    val_count = min(val, count - test_count)
    train_count = count - val_count - test_count
    return DatasetSplit(train=train_count, val=val_count, test=test_count)


def generate_synthetic_dataset(
    *,
    output_dir: str | Path,
    count: int,
    seed: int,
    width: int,
    height: int,
    difficulty: str = "basic",
    val_count: int = 1,
    test_count: int = 1,
) -> dict[str, object]:
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    splits = split_counts(count, val=val_count, test=test_count)
    records: list[dict[str, object]] = []

    for index in range(count):
        sample_seed = seed + index
        sample = generate_synthetic_sample(
            seed=sample_seed,
            width=width,
            height=height,
            difficulty=difficulty,
        )
        split = _split_for_index(index, splits)
        sample_dir = output_dir / split
        image_path, manifest_path = sample.write(sample_dir, f"sample-{index:04d}")
        records.append(
            {
                "id": f"sample-{index:04d}",
                "seed": sample_seed,
                "split": split,
                "difficulty": difficulty,
                "image": str(image_path.relative_to(output_dir)),
                "manifest": str(manifest_path.relative_to(output_dir)),
            }
        )

    index = {
        "count": count,
        "seed": seed,
        "width": width,
        "height": height,
        "difficulty": difficulty,
        "splits": {
            "train": splits.train,
            "val": splits.val,
            "test": splits.test,
        },
        "samples": records,
    }
    (output_dir / "dataset.json").write_text(
        json.dumps(index, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    return index


def _split_for_index(index: int, splits: DatasetSplit) -> str:
    if index < splits.train:
        return "train"
    if index < splits.train + splits.val:
        return "val"
    return "test"
