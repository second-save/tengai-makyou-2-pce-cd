#!/usr/bin/env python3
"""Convert TM II track 2 (MODE1/2352) to a raw 2048-byte-sector ISO."""

from __future__ import annotations

import argparse
from pathlib import Path

from tm2_disc import DEFAULT_TRACK2, load_user_data, write_iso


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "-i",
        "--input",
        type=Path,
        default=DEFAULT_TRACK2,
        help="Input track 2 BIN (MODE1/2352)",
    )
    parser.add_argument(
        "-o",
        "--output",
        type=Path,
        default=Path(__file__).resolve().parent.parent / "work" / "tm2_02.iso",
        help="Output raw ISO (2048 bytes/sector)",
    )
    args = parser.parse_args()

    data = load_user_data(args.input)
    write_iso(args.output, data)
    sectors = len(data) // 2048
    print(f"Wrote {args.output} ({len(data):,} bytes, {sectors:,} sectors)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
