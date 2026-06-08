"""Utilities for reading Tengai Makyou II (PCE-CD) disc images."""

from __future__ import annotations

import struct
from pathlib import Path

SECTOR_SIZE = 0x800
MODE1_RAW_SECTOR = 2352
MODE1_USER_OFFSET = 16
MODE1_USER_SIZE = 2048

DEFAULT_TRACK2 = (
    Path(__file__).resolve().parent.parent
    / "Far East of Eden - Tengai Makyou II - Manji Maru (Japan)"
    / "Far East of Eden - Tengai Makyou II - Manji Maru (Japan)"
    / "Far East of Eden - Tengai Makyou II - Manji Maru (Japan) (Track 02).bin"
)


def load_user_data(path: Path | str | None = None) -> bytes:
    """Extract 2048-byte user sectors from a MODE1/2352 track."""
    path = Path(path or DEFAULT_TRACK2)
    raw = path.read_bytes()
    if len(raw) % MODE1_RAW_SECTOR != 0:
        raise ValueError(f"{path}: size {len(raw)} is not a multiple of 2352")
    sectors = []
    for i in range(len(raw) // MODE1_RAW_SECTOR):
        base = i * MODE1_RAW_SECTOR + MODE1_USER_OFFSET
        sectors.append(raw[base : base + MODE1_USER_SIZE])
    return b"".join(sectors)


def offset_to_sector(offset: int) -> int:
    return offset // SECTOR_SIZE


def sector_to_offset(sector: int) -> int:
    return sector * SECTOR_SIZE


def write_iso(path: Path | str, data: bytes) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
