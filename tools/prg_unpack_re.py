#!/usr/bin/env python3
"""Reverse-engineering helpers for TENGAI2.PRG pack unpack ($51BA / $E0D8)."""

from __future__ import annotations

import argparse
import struct
from pathlib import Path

from tm2_disc import DEFAULT_TRACK2, load_user_data

PRG_START_SECTOR = 0xE8
PRG_END_SECTOR = 0x170
LOADER_SECTOR = 0x14E
LOADER_CPU_BASE = 0xE000
LOADER_MIRROR_OFF = 0x33000  # prog+0x33000 <-> $E000 (YS.DATA.?? @ +$BF)

# Dispatcher $51BA — segment index ($FF) and destination ($F9:$F8 LE)
UNPACK_SEQUENCE: tuple[dict, ...] = (
    {"seg": 0, "dest": None, "note": "default destination"},
    {"seg": 2, "dest": 0x0202, "note": "aux table"},
    {"seg": 3, "dest": "FFF5+4", "note": "dynamic via ADC $FFF5"},
    {"seg": 4, "dest": 0x8000, "note": "data1 (ivm2h ram_base $8000, max $600)"},
    {"seg": 6, "dest": 0x8261, "note": "map/adpcm aux"},
    {"seg": 7, "dest": 0x820D, "note": "map aux"},
    {"seg": 8, "dest": 0x81D2, "note": "map aux"},
    {"seg": 9, "dest": 0x8002, "note": "bank $8000+2"},
    {"seg": 0x0B, "dest": None, "note": "alternate entry @ $522A"},
)


def load_prg(data: bytes) -> bytes:
    start = PRG_START_SECTOR * 0x800
    end = PRG_END_SECTOR * 0x800
    return data[start:end]


def find_jsr_targets(prog: bytes, target: int) -> list[int]:
    pat = bytes([0x20, target & 0xFF, (target >> 8) & 0xFF])
    hits: list[int] = []
    off = 0
    while True:
        idx = prog.find(pat, off)
        if idx < 0:
            break
        hits.append(idx)
        off = idx + 1
    return hits


def disasm_line(prog: bytes, pc: int) -> tuple[str, int]:
    if pc >= len(prog):
        return ("", 0)
    b = prog[pc]
    if b == 0x20 and pc + 2 < len(prog):
        tgt = struct.unpack_from("<H", prog, pc + 1)[0]
        return (f"jsr ${tgt:04x}", 3)
    if b == 0x4C and pc + 2 < len(prog):
        tgt = struct.unpack_from("<H", prog, pc + 1)[0]
        return (f"jmp ${tgt:04x}", 3)
    if b == 0xA9 and pc + 1 < len(prog):
        return (f"lda #${prog[pc + 1]:02x}", 2)
    if b == 0x85 and pc + 1 < len(prog):
        return (f"sta zp${prog[pc + 1]:02x}", 2)
    if b == 0x8D and pc + 2 < len(prog):
        return (f"sta ${struct.unpack_from('<H', prog, pc + 1)[0]:04x}", 3)
    if b == 0xAD and pc + 2 < len(prog):
        return (f"lda ${struct.unpack_from('<H', prog, pc + 1)[0]:04x}", 3)
    if b == 0x6D and pc + 2 < len(prog):
        return (f"adc ${struct.unpack_from('<H', prog, pc + 1)[0]:04x}", 3)
    if b == 0x18:
        return ("clc", 1)
    if b == 0x60:
        return ("rts", 1)
    if b in (0x90, 0xB0, 0xF0, 0xD0) and pc + 1 < len(prog):
        nm = {0x90: "bcc", 0xB0: "bcs", 0xF0: "beq", 0xD0: "bne"}[b]
        r = prog[pc + 1]
        r = r - 256 if r > 127 else r
        return (f"{nm} {r:+d}", 2)
    return (f"${b:02x}", 1)


def disasm_block(prog: bytes, start: int, count: int = 40) -> list[str]:
    lines: list[str] = []
    pc = start
    for _ in range(count):
        if pc >= len(prog):
            break
        mnem, step = disasm_line(prog, pc)
        lines.append(f"  ${pc:04X}  {mnem}")
        pc += step
    return lines


def cmd_report(data: bytes) -> None:
    prog = load_prg(data)
    print("=== TENGAI2.PRG pack unpack RE ===\n")
    print(f"Taille programme : {len(prog)} o (sect. {PRG_START_SECTOR:#x}–{PRG_END_SECTOR:#x})")
    print(f"Miroir chargeur  : prog+{LOADER_MIRROR_OFF:#x} <-> ${LOADER_CPU_BASE:04X}")
    tmpl = prog.find(b"YS.DATA.??")
    print(f"Gabarit YS.DATA  : prog+{tmpl:#x} (attendu +{LOADER_MIRROR_OFF + 0xBF:#x})")

    print("\n--- Faux positif $580 @ prog+0x880f ---")
    u16 = struct.unpack_from("<H", prog, 0x880F)[0]
    prev_ptr = struct.unpack_from("<H", prog, 0x880D)[0]
    next_ptr = struct.unpack_from("<H", prog, 0x8810)[0]
    print(f"  u16 @ 0x880F = ${u16:04X} — chevauchement pointeurs ${prev_ptr:04X} / ${next_ptr:04X}")
    print("  → table bytecode script, pas tailles ivm2h")

    print("\n--- JSR $E0D8 ---")
    hits = find_jsr_targets(prog, 0xE0D8)
    print(f"  {len(hits)} appels dans le PRG")
    for h in hits[:8]:
        print(f"    prog+{h:#06x} (${h:04X})")
    if len(hits) > 8:
        print(f"    … +{len(hits) - 8} autres")

    print("\n--- Dispatcher $51BA : séquence segments ---")
    for row in UNPACK_SEQUENCE:
        dest = row["dest"]
        dest_s = f"${dest:04X}" if isinstance(dest, int) else str(dest)
        print(f"  seg ${row['seg']:02X} → {dest_s:8s}  ({row['note']})")

    print("\n--- Désassemblage $51BA (extrait) ---")
    for line in disasm_block(prog, 0x51BA, 35):
        print(line)

    print("\n--- Appel overlay (JSR $51BA) ---")
    callers = find_jsr_targets(prog, 0x51BA)
    for c in callers:
        print(f"  prog+{c:#06x}")
        for line in disasm_block(prog, max(0, c - 15), 8):
            print(line)

    print("\n--- Runtime $E0D8 dans le miroir (octets statiques) ---")
    ram_off = LOADER_MIRROR_OFF + 0xD8
    chunk = prog[ram_off : ram_off + 16]
    print(f"  prog+{ram_off:#x}: {chunk.hex()}")
    if chunk == b"\x00" * 8:
        print("  padding $00 — entrée effective probable @ $E0E0 (prog+0x330E0)")
    print("\nVoir docs/PRG_DECOMPRESS.md pour le détail complet.")


def cmd_dump_loader(data: bytes, out: Path) -> None:
    prog = load_prg(data)
    chunk = prog[LOADER_MIRROR_OFF : LOADER_MIRROR_OFF + 0x800]
    out.write_bytes(chunk)
    print(f"Écrit miroir $E000 ({len(chunk)} o) → {out}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--disc", type=Path, default=DEFAULT_TRACK2)
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("report", help="Rapport RE unpack sur stdout")

    dump_p = sub.add_parser("dump-loader", help="Extraire miroir $E000 depuis le PRG")
    dump_p.add_argument("-o", "--output", type=Path, required=True)

    args = parser.parse_args()
    data = load_user_data(args.disc)

    if args.command == "report":
        cmd_report(data)
    elif args.command == "dump-loader":
        cmd_dump_loader(data, args.output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
