#!/usr/bin/env python3
"""Filter tm2_text.csv to remove false positives."""

from __future__ import annotations

import argparse
import csv
from collections import Counter
from pathlib import Path

from text_filter import should_keep

DEFAULT_INPUT = Path(__file__).resolve().parent.parent / "script" / "tm2_text.csv"
DEFAULT_OUTPUT = Path(__file__).resolve().parent.parent / "script" / "tm2_text_filtered.csv"
DEFAULT_REJECTED = Path(__file__).resolve().parent.parent / "script" / "tm2_text_rejected.csv"


def filter_csv(
    input_path: Path,
    output_path: Path,
    rejected_path: Path | None,
) -> tuple[int, int]:
    with input_path.open(encoding="utf-8") as f:
        rows = list(csv.DictReader(f))

    if not rows:
        raise SystemExit(f"No rows in {input_path}")

    fieldnames = rows[0].keys()
    kept: list[dict] = []
    rejected: list[dict] = []

    for row in rows:
        ok, reason = should_keep(row)
        if ok:
            kept.append(row)
        else:
            row = dict(row)
            row["reject_reason"] = reason
            rejected.append(row)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(kept)

    if rejected_path is not None:
        reject_fields = list(fieldnames) + ["reject_reason"]
        with rejected_path.open("w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=reject_fields)
            writer.writeheader()
            writer.writerows(rejected)

    return len(kept), len(rejected)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("-i", "--input", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("-o", "--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument(
        "--rejected",
        type=Path,
        default=DEFAULT_REJECTED,
        help="Write rejected rows here (use /dev/null to skip)",
    )
    args = parser.parse_args()

    rejected_path = args.rejected
    if str(rejected_path) in ("/dev/null", "nul"):
        rejected_path = None

    kept, rejected = filter_csv(args.input, args.output, rejected_path)

    print(f"Kept {kept} / {kept + rejected} rows -> {args.output}")
    if rejected_path:
        print(f"Rejected {rejected} rows -> {rejected_path}")

    with args.output.open(encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    by_type = Counter(r["type"] for r in rows)
    for t, n in sorted(by_type.items()):
        print(f"  {t}: {n}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
