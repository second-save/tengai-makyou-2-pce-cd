#!/usr/bin/env python3
"""Trace les opcodes manquants sur $D350→$D510 (émulateur HuC6280)."""

from __future__ import annotations

import sys
from pathlib import Path

from hudson_huc6280 import DEFAULT_CPU_DUMP, HuC6280
from hudson_pack import load_overlay_blob
from tm2_disc import DEFAULT_TRACK2, load_user_data

ROUTINES = (
    (0xD257, "D257"),
    (0xD350, "D350"),
    (0xD422, "D422"),
    (0xD510, "D510"),
    (0xD5E2, "D5E2"),
    (0xD611, "D611"),
)


def prep_cpu(src_off: int, *, backref: bool = False, write_mode: bool = False) -> tuple[HuC6280, bytes]:
    data = load_user_data(DEFAULT_TRACK2)
    blob, _, _ = load_overlay_blob(data, "wa1")
    dump = DEFAULT_CPU_DUMP.read_bytes()
    cpu = HuC6280(bytearray(dump), pack=blob, pack_base=0, max_steps=10_000_000)
    cpu.load_mpr6(dump)
    seg_idx = cpu.init_decompress(src_off)
    cpu.zp_w(0xE8, src_off & 0xFF)
    cpu.zp_w(0xE9, src_off >> 8)
    cpu.write8(0x22E0, seg_idx)
    sx = seg_idx
    cpu.run_jsr(0xCE07)
    cpu.run_jsr(0xD257)

    ptr = cpu.zp_r(0xE8) | (cpu.zp_r(0xE9) << 8)
    cpu.write8(0x248B + sx, ptr & 0xFF)
    cpu.write8(0x2491 + sx, (ptr >> 8) & 0xFF)
    cpu.zp_w(0xEA, ptr & 0xFF)
    cpu.zp_w(0xEB, (ptr >> 8) & 0xFF)

    if backref:
        cpu.write8(0x25E1 + sx, 0x10)
        cpu.write8(0x260D + sx, 3)
        cpu.write8(0x259F + sx, ptr & 0xFF)
        cpu.write8(0x25A5 + sx, (ptr >> 8) & 0xFF)
        cpu.write8(0x2587 + sx, 1)
        cpu.write8(0x258D + sx, 0)

    if write_mode:
        cpu.write8(0x25E1 + sx, 0)
        cpu.write8(0x2581 + sx, 0x10)
        cpu.write8(0x2587 + sx, 0)
        cpu.write8(0x258D + sx, 0)
        cpu.write8(0x2593 + sx, 1)

    return cpu, dump


def trace_all(src_off: int = 0) -> list[tuple[str, int, int, str]]:
    failures: list[tuple[str, int, int, str]] = []
    configs = [
        ("default", False, False),
        ("backref", True, False),
        ("write", False, True),
        ("both", True, True),
    ]
    for cfg_name, backref, write_mode in configs:
        cpu, dump = prep_cpu(src_off, backref=backref, write_mode=write_mode)
        for addr, name in ROUTINES:
            cpu.halted = False
            try:
                cpu.run_jsr(addr, strict=True)
            except RuntimeError as exc:
                pc = cpu.pc
                op = dump[pc]
                ctx = dump[pc : pc + 6]
                failures.append((f"{cfg_name}/{name}", pc, op, str(exc)))
                print(
                    f"[{cfg_name}] {name} FAIL ${pc:04X} op=${op:02X} "
                    f"ctx={' '.join(f'{b:02X}' for b in ctx)} — {exc}"
                )
            else:
                print(f"[{cfg_name}] {name} OK (out={len(cpu.out)})")
    return failures


def main() -> int:
    off = int(sys.argv[1], 0) if len(sys.argv) > 1 else 0
    print(f"=== trace D350→D510 @ offset {off:#x} ===")
    fails = trace_all(off)
    if fails:
        print(f"\n{len(fails)} échec(s) opcode")
        return 1
    print("\nTous les chemins passent.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
