#!/usr/bin/env python3
"""Désassemble la zone décompresseur Hudson ($FE0C) depuis un dump Mesen CPU 64 KiB."""

from __future__ import annotations

import argparse
import struct
import sys
from pathlib import Path

# Alias empirique : code MPR6 @ banque 2 (CPU $C0xx) ↔ vue MPR7 ($FExx) dans mesen_e000.bin
MPR6_TO_MPR7 = 0x3E00

SEG_TABLE_OFF = 0xFE2D
SEG_TABLE_COUNT = 21  # CMP #$15 @ $FE17


def disasm_huc6280(data: bytes, start: int, count: int) -> list[str]:
    lines: list[str] = []
    pc = start
    for _ in range(count):
        if pc >= len(data):
            break
        b = data[pc]
        addr = pc
        if b == 0x7C and pc + 2 < len(data):
            base = struct.unpack_from("<H", data, pc + 1)[0]
            lines.append(f"${addr:04X}: JMP (${base:04X},X)")
            pc += 3
        elif b == 0x73 and pc + 3 < len(data):
            src = struct.unpack_from("<H", data, pc + 1)[0]
            ln = data[pc + 3]
            lines.append(f"${addr:04X}: TII ${src:04X}, ?, #${ln:02X}")
            pc += 4
        elif b == 0x44 and pc + 1 < len(data):
            rel = data[pc + 1]
            rel = rel - 256 if rel > 127 else rel
            lines.append(f"${addr:04X}: BSR ${pc + 2 + rel:04X}")
            pc += 2
        elif b == 0x20 and pc + 2 < len(data):
            tgt = struct.unpack_from("<H", data, pc + 1)[0]
            lines.append(f"${addr:04X}: JSR ${tgt:04X}")
            pc += 3
        elif b == 0x4C and pc + 2 < len(data):
            tgt = struct.unpack_from("<H", data, pc + 1)[0]
            lines.append(f"${addr:04X}: JMP ${tgt:04X}")
            pc += 3
        elif b in (0x43, 0x53) and pc + 1 < len(data):
            op = "TMA" if b == 0x43 else "TAM"
            lines.append(f"${addr:04X}: {op} #${data[pc + 1]:02X}")
            pc += 2
        elif b in (0x03, 0x13, 0x23) and pc + 1 < len(data):
            lines.append(f"${addr:04X}: ST{b // 0x10} #${data[pc + 1]:02X}")
            pc += 2
        elif b == 0xA9 and pc + 1 < len(data):
            lines.append(f"${addr:04X}: LDA #${data[pc + 1]:02X}")
            pc += 2
        elif b == 0xA5 and pc + 1 < len(data):
            lines.append(f"${addr:04X}: LDA zp${data[pc + 1]:02X}")
            pc += 2
        elif b == 0xB5 and pc + 1 < len(data):
            lines.append(f"${addr:04X}: LDA zp${data[pc + 1]:02X},X")
            pc += 2
        elif b == 0x85 and pc + 1 < len(data):
            lines.append(f"${addr:04X}: STA zp${data[pc + 1]:02X}")
            pc += 2
        elif b == 0xB1 and pc + 1 < len(data):
            lines.append(f"${addr:04X}: LDA (zp${data[pc + 1]:02X}),Y")
            pc += 2
        elif b == 0x91 and pc + 1 < len(data):
            lines.append(f"${addr:04X}: STA (zp${data[pc + 1]:02X}),Y")
            pc += 2
        elif b == 0xB9 and pc + 2 < len(data):
            tgt = struct.unpack_from("<H", data, pc + 1)[0]
            lines.append(f"${addr:04X}: LDA ${tgt:04X},Y")
            pc += 3
        elif b == 0xAD and pc + 2 < len(data):
            tgt = struct.unpack_from("<H", data, pc + 1)[0]
            lines.append(f"${addr:04X}: LDA ${tgt:04X}")
            pc += 3
        elif b == 0x8D and pc + 2 < len(data):
            tgt = struct.unpack_from("<H", data, pc + 1)[0]
            lines.append(f"${addr:04X}: STA ${tgt:04X}")
            pc += 3
        elif b == 0xC9 and pc + 1 < len(data):
            lines.append(f"${addr:04X}: CMP #${data[pc + 1]:02X}")
            pc += 2
        elif b == 0x29 and pc + 1 < len(data):
            lines.append(f"${addr:04X}: AND #${data[pc + 1]:02X}")
            pc += 2
        elif b in (0x90, 0xB0, 0xF0, 0xD0) and pc + 1 < len(data):
            rel = data[pc + 1]
            rel = rel - 256 if rel > 127 else rel
            nm = {0x90: "BCC", 0xB0: "BCS", 0xF0: "BEQ", 0xD0: "BNE"}[b]
            lines.append(f"${addr:04X}: {nm} ${pc + 2 + rel:04X}")
            pc += 2
        elif b in (0x0A, 0x4A, 0x2A, 0x6A):
            nm = ["ASL A", "LSR A", "ROL A", "ROR A"][{0x0A: 0, 0x4A: 1, 0x2A: 2, 0x6A: 3}[b]]
            lines.append(f"${addr:04X}: {nm}")
            pc += 1
        elif b in (0x48, 0x68, 0xDA, 0xFA, 0x5A, 0x7A, 0xAA, 0xA8, 0x8A, 0x98, 0x60, 0x18, 0x38, 0x82):
            m = {
                0x48: "PHA",
                0x68: "PLA",
                0xDA: "PHX",
                0xFA: "PLX",
                0x5A: "PHY",
                0x7A: "PLY",
                0xAA: "TAX",
                0xA8: "TAY",
                0x8A: "TXA",
                0x98: "TYA",
                0x60: "RTS",
                0x18: "CLC",
                0x38: "SEC",
                0x82: "CLX",
            }
            lines.append(f"${addr:04X}: {m[b]}")
            pc += 1
        else:
            lines.append(f"${addr:04X}: .db ${b:02X}")
            pc += 1
    return lines


def mpr6_alias(cpu_c0: int) -> int:
    return (cpu_c0 + MPR6_TO_MPR7) & 0xFFFF


def segment_table(data: bytes) -> list[tuple[int, int, int, int]]:
    rows: list[tuple[int, int, int, int]] = []
    for seg in range(SEG_TABLE_COUNT):
        x = seg * 2
        off = SEG_TABLE_OFF + x
        tgt_c0 = struct.unpack_from("<H", data, off)[0]
        tgt_fe = mpr6_alias(tgt_c0)
        nz = sum(1 for b in data[tgt_fe : tgt_fe + 32] if b not in (0, 0xFF))
        rows.append((seg, x, tgt_c0, tgt_fe, nz))
    return rows


def cmd_report(path: Path) -> int:
    data = path.read_bytes()
    if len(data) != 0x10000:
        print(f"Attention : {len(data)} octets (attendu 65536).\n", file=sys.stderr)

    print(f"=== Analyse $FE0C — {path} ===\n")

    print("--- Entrée principale ($E0D8 → JMP $FE0C) ---")
    for line in disasm_huc6280(data, 0xFE0C, 20):
        print(f"  {line}")

    print("\n--- Prologue segment 0 @ $FE00 ---")
    for line in disasm_huc6280(data, 0xFE00, 12):
        print(f"  {line}")

    print("\n--- Dispatch $FE2A ---")
    for line in disasm_huc6280(data, 0xFE2A, 3):
        print(f"  {line}")

    print(f"\n--- Table segments ($FF), {SEG_TABLE_COUNT} entrées @ $FE2D ---")
    print("  seg  X  CPU $C0xx  alias $FExx  code?")
    for seg, x, c0, fe, nz in segment_table(data):
        mark = "oui" if nz > 8 else "non/vide"
        print(f"  {seg:2d}  {x:2d}  ${c0:04X}     ${fe:04X}      {mark}")

    print("\n--- Entrée parallèle ($E0DB → $FE57, banque MPR6=#03) ---")
    for line in disasm_huc6280(data, 0xFE57, 18):
        print(f"  {line}")

    print("\n--- Chaîne d'init ($FDCD → JSR $CDxx, banque via $FDA9) ---")
    for line in disasm_huc6280(data, 0xFDCD, 22):
        print(f"  {line}")

    print("\n--- Helper banque $FDA9 ---")
    for line in disasm_huc6280(data, 0xFDA9, 8):
        print(f"  {line}")

    print("\n--- I/O pack ($F730 → zp vers $224C+) ---")
    for line in disasm_huc6280(data, 0xF730, 20):
        print(f"  {line}")

    print("\n--- JSR $CDxx (alias MPR6→MPR7 absent si MPR6≠banque2 au dump) ---")
    chain = [0xCD12, 0xCD57, 0xCD92, 0xCDC3, 0xCDDB, 0xCE2E, 0xCE75, 0xCEC3, 0xCEC8, 0xCED2]
    for cpu in chain:
        fe = mpr6_alias(cpu)
        direct = sum(1 for b in data[cpu : cpu + 16] if b not in (0, 0xFF))
        alias = sum(1 for b in data[fe : fe + 16] if b not in (0, 0xFF))
        print(f"  ${cpu:04X}  direct={direct}/16  alias ${fe:04X}={alias}/16")

    print("\n--- Table JMP $E0D8 (extrait) ---")
    for i, off in enumerate(range(0xE0D8, 0xE0F4, 3)):
        if data[off] != 0x4C:
            break
        tgt = struct.unpack_from("<H", data, off + 1)[0]
        print(f"  [{i}] ${off:04X} → ${tgt:04X}")

    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "dump",
        type=Path,
        nargs="?",
        default=Path("work/mesen_e000.bin"),
        help="Dump CPU Mesen 64 KiB",
    )
    args = parser.parse_args()
    if not args.dump.is_file():
        print(f"Fichier introuvable : {args.dump}", file=sys.stderr)
        return 2
    return cmd_report(args.dump)


if __name__ == "__main__":
    raise SystemExit(main())
