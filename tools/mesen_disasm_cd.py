#!/usr/bin/env python3
"""Rapport RE sur la fenêtre MPR6 ($CDxx) depuis mesen_decomp_cpu.bin."""

from __future__ import annotations

import argparse
import struct
import sys
from pathlib import Path

# Chaîne $FDCD → $FE00 (init) puis $CD12 (segment driver)
INIT_CHAIN = (
    0xCD12,
    0xCD57,
    0xCD92,
    0xCDC3,
    0xCDDB,
    0xCE2E,
    0xCE75,
    0xCEC3,
    0xCEC8,
    0xCED2,
)

SEG_CALLEES = (
    ("CDF6", 0xCDF6, "VM bytecode — dispatch opcodes ≥ $D0"),
    ("D257", 0xD257, "bitstream littéral #1 ($255D/$24AF)"),
    ("D350", 0xD350, "copie backref tag $10 ($25E1)"),
    ("D422", 0xD422, "ajustement pointeurs pack ($260D)"),
    ("D510", 0xD510, "écriture segments ($25E1=0)"),
    ("D623", 0xD623, "finalisation segment"),
    ("D64D", 0xD64D, "finalisation segment"),
)

BITSTREAM_SITES = (
    (0xC909, "nibble haut +3 bits commande ($246E)"),
    (0xC92A, "variante soustraction nibble"),
    (0xD306, "idem flux second ($25F9/$2575)"),
    (0xD327, "variante soustraction"),
)


def nz(data: bytes, off: int, size: int) -> int:
    chunk = data[off : off + size]
    return sum(1 for b in chunk if b not in (0, 0xFF))


def report(path: Path) -> int:
    data = path.read_bytes()
    if len(data) != 0x10000:
        print(f"Attention : {len(data)} octets (attendu 65536)\n", file=sys.stderr)

    print(f"=== RE MPR6 / $CDxx — {path} ===\n")

    c0 = data[0xC000:0xE000]
    print(f"Fenêtre $C000-$DFFF : {nz(c0, 0, len(c0))}/{len(c0)} octets non triviaux\n")

    print("--- Chaîne init $FDCD (cibles JSR) ---")
    for addr in INIT_CHAIN:
        off = addr - 0xC000
        print(f"  ${addr:04X}  nz@+64={nz(c0, off, 64)}")

    print("\n--- Callees $CD12 (unpack segment) ---")
    for name, addr, note in SEG_CALLEES:
        off = addr - 0xC000
        print(f"  ${addr:04X} {name:5s}  nz@+48={nz(c0, off, 48):2d}  — {note}")

    print("\n--- Sites bitstream (AND #$80 + LSR×3) ---")
    for addr, note in BITSTREAM_SITES:
        snippet = data[addr : addr + 6].hex()
        print(f"  ${addr:04X}  {snippet}  — {note}")

    print("\n--- Table dispatch CDF6 @ $CE1D ---")
    for i in range(16):
        tgt = struct.unpack_from("<H", data, 0xCE1D + i * 2)[0]
        print(f"  opcode ${i + 0xD0:02X} → ${tgt:04X}")

    print("\n--- Workspace Hudson (extrait) ---")
    for base, label in (
        (0x22D0, "pointeur table segment"),
        (0x22E0, "état unpack"),
        (0x224C, "I/O pack ($F730)"),
    ):
        print(f"  ${base:04X} ({label}): {data[base : base + 8].hex()}")

    print("\n→ Détail asm : python3 tools/mesen_disasm_fe0c.py", path)
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "dump",
        type=Path,
        nargs="?",
        default=Path("work/mesen_decomp_cpu.bin"),
    )
    args = parser.parse_args()
    if not args.dump.is_file():
        print(f"Fichier introuvable : {args.dump}", file=sys.stderr)
        return 2
    return report(args.dump)


if __name__ == "__main__":
    raise SystemExit(main())
