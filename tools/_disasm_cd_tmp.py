#!/usr/bin/env python3
"""Temporary deep disasm helper (internal)."""
from pathlib import Path
import struct

cpu = Path("work/mesen_decomp_cpu.bin").read_bytes()

SHIFT = {0x0A: "ASL A", 0x4A: "LSR A", 0x2A: "ROL A", 0x6A: "ROR A"}
BR = {0x90: "BCC", 0xB0: "BCS", 0xF0: "BEQ", 0xD0: "BNE"}
SINGLE = {
    0xE8: "INX", 0xC8: "INY", 0x88: "DEY", 0xCA: "DEX",
    0xAA: "TAX", 0xA8: "TAY", 0x48: "PHA", 0x68: "PLA",
    0x60: "RTS", 0x18: "CLC", 0x38: "SEC", 0x82: "CLX",
}


def dis(data: bytes, start: int, n: int = 80) -> None:
    pc = start
    while n > 0 and pc < len(data):
        n -= 1
        b = data[pc]
        a = pc
        if b == 0x20 and pc + 2 < len(data):
            t = struct.unpack_from("<H", data, pc + 1)[0]
            print(f"${a:04X}: JSR ${t:04X}")
            pc += 3
        elif b == 0x4C and pc + 2 < len(data):
            t = struct.unpack_from("<H", data, pc + 1)[0]
            print(f"${a:04X}: JMP ${t:04X}")
            pc += 3
        elif b == 0x7C and pc + 2 < len(data):
            t = struct.unpack_from("<H", data, pc + 1)[0]
            print(f"${a:04X}: JMP (${t:04X},X)")
            pc += 3
        elif b == 0x44 and pc + 1 < len(data):
            r = data[pc + 1]
            r = r - 256 if r > 127 else r
            print(f"${a:04X}: BSR ${pc + 2 + r:04X}")
            pc += 2
        elif b == 0x9D and pc + 2 < len(data):
            t = struct.unpack_from("<H", data, pc + 1)[0]
            print(f"${a:04X}: STA ${t:04X},X")
            pc += 3
        elif b == 0x9E and pc + 2 < len(data):
            t = struct.unpack_from("<H", data, pc + 1)[0]
            print(f"${a:04X}: STZ ${t:04X},X")
            pc += 3
        elif b == 0xBD and pc + 2 < len(data):
            t = struct.unpack_from("<H", data, pc + 1)[0]
            print(f"${a:04X}: LDA ${t:04X},X")
            pc += 3
        elif b == 0xB9 and pc + 2 < len(data):
            t = struct.unpack_from("<H", data, pc + 1)[0]
            print(f"${a:04X}: LDA ${t:04X},Y")
            pc += 3
        elif b == 0x99 and pc + 2 < len(data):
            t = struct.unpack_from("<H", data, pc + 1)[0]
            print(f"${a:04X}: STA ${t:04X},Y")
            pc += 3
        elif b == 0xAD and pc + 2 < len(data):
            t = struct.unpack_from("<H", data, pc + 1)[0]
            print(f"${a:04X}: LDA ${t:04X}")
            pc += 3
        elif b == 0x8D and pc + 2 < len(data):
            t = struct.unpack_from("<H", data, pc + 1)[0]
            print(f"${a:04X}: STA ${t:04X}")
            pc += 3
        elif b == 0xA9 and pc + 1 < len(data):
            print(f"${a:04X}: LDA #${data[pc + 1]:02X}")
            pc += 2
        elif b == 0xA5 and pc + 1 < len(data):
            print(f"${a:04X}: LDA zp${data[pc + 1]:02X}")
            pc += 2
        elif b == 0xB1 and pc + 1 < len(data):
            print(f"${a:04X}: LDA (zp${data[pc + 1]:02X}),Y")
            pc += 2
        elif b == 0x91 and pc + 1 < len(data):
            print(f"${a:04X}: STA (zp${data[pc + 1]:02X}),Y")
            pc += 2
        elif b == 0x85 and pc + 1 < len(data):
            print(f"${a:04X}: STA zp${data[pc + 1]:02X}")
            pc += 2
        elif b == 0xC9 and pc + 1 < len(data):
            print(f"${a:04X}: CMP #${data[pc + 1]:02X}")
            pc += 2
        elif b == 0xE0 and pc + 1 < len(data):
            print(f"${a:04X}: CPX #${data[pc + 1]:02X}")
            pc += 2
        elif b == 0x29 and pc + 1 < len(data):
            print(f"${a:04X}: AND #${data[pc + 1]:02X}")
            pc += 2
        elif b == 0x65 and pc + 1 < len(data):
            print(f"${a:04X}: ADC zp${data[pc + 1]:02X}")
            pc += 2
        elif b == 0x6D and pc + 2 < len(data):
            t = struct.unpack_from("<H", data, pc + 1)[0]
            print(f"${a:04X}: ADC ${t:04X}")
            pc += 3
        elif b == 0x79 and pc + 2 < len(data):
            t = struct.unpack_from("<H", data, pc + 1)[0]
            print(f"${a:04X}: ADC ${t:04X},Y")
            pc += 3
        elif b in BR and pc + 1 < len(data):
            r = data[pc + 1]
            r = r - 256 if r > 127 else r
            print(f"${a:04X}: {BR[b]} ${pc + 2 + r:04X}")
            pc += 2
        elif b in SHIFT:
            print(f"${a:04X}: {SHIFT[b]}")
            pc += 1
        elif b in SINGLE:
            print(f"${a:04X}: {SINGLE[b]}")
            pc += 1
        elif b == 0x73 and pc + 3 < len(data):
            s = struct.unpack_from("<H", data, pc + 1)[0]
            ln = data[pc + 3]
            print(f"${a:04X}: TII ${s:04X}, ?, #${ln:02X}")
            pc += 4
        else:
            print(f"${a:04X}: .db ${b:02X}")
            pc += 1


if __name__ == "__main__":
    for addr in [0xD299, 0xD2A3, 0xD2F9, 0xC93F, 0xCF5A, 0xD40E, 0xD510]:
        print(f"\n======== ${addr:04X} ========")
        dis(cpu, addr, 60)
