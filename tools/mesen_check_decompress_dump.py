#!/usr/bin/env python3
"""Valide les dumps Mesen pris pendant le décompress (mesen_decomp_*.bin)."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

FE0C_SIG = bytes([0xDA, 0x5A, 0x43, 0x40, 0x48, 0xA9, 0x02, 0x53, 0x40])
CD12_OFF = 0xCD12 - 0xC000  # 0x112 dans mesen_decomp_c000.bin
AA55 = bytes([0xAA, 0x55])


def check_cpu(path: Path) -> tuple[int, list[str]]:
    data = path.read_bytes()
    lines: list[str] = []
    score = 0
    if len(data) != 0x10000:
        lines.append(f"⚠ CPU : {len(data)} o (attendu 65536)")
    else:
        lines.append(f"✓ CPU : {len(data)} o")

    fe = data[0xFE0C : 0xFE0C + len(FE0C_SIG)]
    if fe == FE0C_SIG:
        lines.append(f"✓ $FE0C = entrée dispatch ({fe[:8].hex()}…)")
        score += 1
    elif fe == b"\xff" * len(FE0C_SIG) or fe == b"\x00" * len(FE0C_SIG):
        lines.append(f"✗ $FE0C vide — mauvais moment ({fe[:4].hex()})")
    else:
        lines.append(f"? $FE0C = {fe[:8].hex()}… (partiel)")

    c0 = data[0xC000:0xE000]
    nz_c0 = sum(1 for b in c0 if b not in (0, 0xFF))
    if nz_c0 > 512:
        lines.append(f"✓ $C000-$DFFF = {nz_c0} octets code/data (MPR6 visible)")
        score += 1
    else:
        lines.append(f"✗ $C000-$DFFF quasi vide ({nz_c0} nz) — MPR6 pas en banque 2")

    cd = data[0xCD12 : 0xCD12 + 64]
    nz_cd = sum(1 for b in cd if b not in (0, 0xFF))
    if nz_cd > 32:
        lines.append(f"✓ $CD12+ = corps décompresseur ({nz_cd}/64 nz)")
        score += 1
    else:
        lines.append(f"✗ $CD12+ absent ({nz_cd}/64 nz) — refaire break @ $FE1F ou $CEC8")

    return score, lines


def check_c0(path: Path) -> tuple[int, list[str]]:
    if not path.is_file():
        return 0, ["○ pas de mesen_decomp_c000.bin"]
    data = path.read_bytes()
    lines: list[str] = []
    score = 0
    if len(data) != 0x2000:
        lines.append(f"⚠ C000 : {len(data)} o (attendu 8192)")
    cd = data[CD12_OFF : CD12_OFF + 128]
    nz = sum(1 for b in cd if b not in (0, 0xFF))
    if nz > 64:
        lines.append(f"✓ fenêtre $CD12 = {nz}/128 nz")
        score += 1
    else:
        lines.append(f"✗ fenêtre $CD12 = {nz}/128 nz")
    return score, lines


def check_card(path: Path) -> tuple[int, list[str]]:
    if not path.is_file():
        return 0, ["○ pas de Card RAM dump"]
    data = path.read_bytes()
    lines: list[str] = []
    score = 0
    lines.append(f"○ Card RAM : {len(data)} o")
    idx = data.find(AA55)
    if idx >= 0:
        lines.append(f"✓ signature AA 55 @ +{idx:#x}")
        score += 1
    else:
        lines.append("? pas de AA 55 en clair (pack peut être offset / compressé)")
    nz = sum(1 for b in data[:0x4000] if b not in (0, 0xFF))
    if nz > 0x400:
        lines.append(f"✓ {nz} octets non triviaux dans les 16 KiB bas")
        score += 1
    else:
        lines.append(f"✗ Card RAM peu remplie ({nz} nz / 16K)")
    return score, lines


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--work",
        type=Path,
        default=Path("work"),
        help="Dossier contenant mesen_decomp_*.bin",
    )
    args = parser.parse_args()
    work = args.work

    cpu_p = work / "mesen_decomp_cpu.bin"
    c0_p = work / "mesen_decomp_c000.bin"
    card_p = work / "mesen_decomp_cardram.bin"
    meta_p = work / "mesen_decomp_meta.txt"

    if not cpu_p.is_file():
        print(f"Fichier manquant : {cpu_p}", file=sys.stderr)
        print("\nDans Mesen2 : load tools/mesen_dump_decompress.lua", file=sys.stderr)
        print("Breakpoint @ $FE1F, puis charger une zone.\n", file=sys.stderr)
        return 2

    print(f"Dossier : {work}\n")
    total = 0

    print("=== mesen_decomp_cpu.bin ===")
    s, lines = check_cpu(cpu_p)
    total += s
    print("\n".join(lines))

    print("\n=== mesen_decomp_c000.bin ===")
    s, lines = check_c0(c0_p)
    total += s
    print("\n".join(lines))

    print("\n=== mesen_decomp_cardram.bin ===")
    s, lines = check_card(card_p)
    total += s
    print("\n".join(lines))

    if meta_p.is_file():
        print(f"\n--- {meta_p.name} ---")
        print(meta_p.read_text().rstrip())

    print(f"\nScore : {total}/6")
    if total >= 3:
        print("→ Dump exploitable pour reverse $CDxx.")
        return 0
    print("→ Refaire le dump (break @ $FE1F pendant unpack wa1).")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
