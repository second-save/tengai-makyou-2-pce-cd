#!/usr/bin/env python3
"""Émulateur HuC6280 minimal — exécution stricte du code MPR6 ($CDxx).

Référence opcodes : https://www.chrismcovell.com/PCEdev/HuC6280_opcodes.html
Code source : work/mesen_decomp_cpu.bin
"""

from __future__ import annotations

import struct
from dataclasses import dataclass, field
from pathlib import Path

FLAG_C = 0x01
FLAG_Z = 0x02
FLAG_I = 0x04
FLAG_D = 0x08
FLAG_B = 0x10
FLAG_V = 0x40
FLAG_N = 0x80

DEFAULT_CPU_DUMP = Path(__file__).resolve().parent.parent / "work" / "mesen_decomp_cpu.bin"
SEG_TABLE_ADDR = 0x800A
DEFAULT_SEG_OFFSETS = (0x100, 0x51F)


@dataclass
class HuC6280:
    mem: bytearray
    a: int = 0
    x: int = 0
    y: int = 0
    sp: int = 0xFF
    p: int = FLAG_I
    pc: int = 0
    pack: bytes = b""
    pack_base: int = 0
    out: bytearray = field(default_factory=bytearray)
    steps: int = 0
    max_steps: int = 30_000_000
    stop_addrs: set[int] = field(default_factory=set)
    halted: bool = False

    def u8(self, v: int) -> int:
        return v & 0xFF

    def u16(self, v: int) -> int:
        return v & 0xFFFF

    def set_nz(self, v: int) -> None:
        v &= 0xFF
        self.p &= ~(FLAG_N | FLAG_Z)
        if v & 0x80:
            self.p |= FLAG_N
        if v == 0:
            self.p |= FLAG_Z

    def flag(self, f: int) -> bool:
        return bool(self.p & f)

    def setf(self, f: int, on: bool) -> None:
        self.p = (self.p | f) if on else (self.p & ~f)

    def read8(self, addr: int) -> int:
        return self.mem[addr & 0xFFFF]

    def write8(self, addr: int, val: int) -> None:
        addr &= 0xFFFF
        val &= 0xFF
        self.mem[addr] = val
        # Segments décompressés (hors pile $0100–$01FF et workspace $24xx–$26xx)
        if (
            0x8000 <= addr < 0x9000
            or 0x6000 <= addr < 0x6600
            or 0x0200 <= addr < 0x0700
        ) and not (0x2400 <= addr < 0x2700):
            if len(self.out) < 0x10000:
                self.out.append(val)

    def zp_r(self, off: int) -> int:
        return self.read8(off)

    def zp_w(self, off: int, val: int) -> None:
        self.write8(off, val)

    def push(self, val: int) -> None:
        self.write8(0x0100 + self.sp, val)
        self.sp = self.u8(self.sp - 1)

    def pull(self) -> int:
        self.sp = self.u8(self.sp + 1)
        return self.read8(0x0100 + self.sp)

    def pack_ptr(self, zp: int) -> int:
        return self.u16(self.zp_r(zp) | (self.zp_r(zp + 1) << 8))

    def pack_read_abs(self, addr: int) -> int:
        off = self.u16(addr - self.pack_base)
        if 0 <= off < len(self.pack):
            return self.pack[off]
        return 0

    def pack_read_ind_y(self, zp: int) -> int:
        return self.pack_read_abs(self.u16(self.pack_ptr(zp) + self.y))

    def write_abs(self, addr: int, val: int) -> None:
        off = self.u16(addr - self.pack_base)
        if 0 <= off < len(self.pack):
            b = bytearray(self.pack)
            b[off] = val & 0xFF
            self.pack = bytes(b)
        else:
            self.write8(addr, val)

    def pack_inc_ptr(self, zp: int) -> None:
        lo = self.u8(self.zp_r(zp) + 1)
        self.zp_w(zp, lo)
        if lo == 0:
            self.zp_w(zp + 1, self.u8(self.zp_r(zp + 1) + 1))

    def abs16(self, pc: int) -> int:
        return struct.unpack_from("<H", self.mem, pc + 1)[0]

    def branch(self, pc: int, cond: bool) -> int:
        rel = self.read8(pc + 1)
        if rel > 127:
            rel -= 256
        return self.u16(pc + 2 + rel) if cond else pc + 2

    def adc(self, val: int) -> None:
        c = 1 if self.flag(FLAG_C) else 0
        tot = self.a + val + c
        self.setf(FLAG_C, tot > 0xFF)
        r = self.u8(tot)
        self.setf(FLAG_V, ((self.a ^ r) & (val ^ r) & 0x80) != 0)
        self.a = r
        self.set_nz(self.a)

    def sbc(self, val: int) -> None:
        self.adc(self.u8(val ^ 0xFF))

    def cmp(self, reg: int, val: int) -> None:
        tot = reg - val
        self.setf(FLAG_C, tot >= 0)
        self.set_nz(self.u8(tot))

    def tst(self, imm: int, val: int) -> None:
        """TST #imm, mem — N/V/Z depuis imm & val (HuC6280)."""
        r = self.u8(imm & val)
        self.p &= ~(FLAG_N | FLAG_V | FLAG_Z)
        if r & 0x80:
            self.p |= FLAG_N
        if r & 0x40:
            self.p |= FLAG_V
        if r == 0:
            self.p |= FLAG_Z

    def bit(self, val: int) -> None:
        val &= 0xFF
        self.p &= ~(FLAG_N | FLAG_V | FLAG_Z)
        if val & 0x80:
            self.p |= FLAG_N
        if val & 0x40:
            self.p |= FLAG_V
        if (self.a & val) == 0:
            self.p |= FLAG_Z

    def rol_a(self) -> None:
        c = 1 if self.flag(FLAG_C) else 0
        self.setf(FLAG_C, bool(self.a & 0x80))
        self.a = self.u8((self.a << 1) | c)
        self.set_nz(self.a)

    def lsr_a(self) -> None:
        self.setf(FLAG_C, bool(self.a & 0x01))
        self.a >>= 1
        self.set_nz(self.a)

    def install_stubs(self) -> None:
        # $FF49 — lit pack via (zp$E8),Y et avance E8/E9
        self.mem[0xFF49 : 0xFF49 + 13] = bytes(
            [
                0xB2,
                0xE8,
                0x85,
                0xEA,
                0xE6,
                0xE8,
                0xD0,
                0x02,
                0xE6,
                0xE9,
                0xA5,
                0xEA,
                0x60,
            ]
        )
        # $CF5A : RTS @ $CF67 mais entrée via JMP @ $CEC4 → BRK pour stop VM
        self.mem[0xCF67] = 0x00
        self.mem[0xC16C] = 0x00
        self.stop_addrs.add(0xC16C)

    def load_mpr6(self, dump: bytes | None = None) -> None:
        dump = dump or DEFAULT_CPU_DUMP.read_bytes()
        if len(dump) != 0x10000:
            raise ValueError("dump CPU 64 KiB requis")
        self.mem[:] = dump
        self.install_stubs()

    def install_segment_table(self, offsets: tuple[int, ...] | list[int]) -> None:
        for i, off in enumerate(offsets[:32]):
            base = SEG_TABLE_ADDR + i * 2
            self.write8(base, off & 0xFF)
            self.write8(base + 1, off >> 8)
        self.write8(0x22D0, SEG_TABLE_ADDR & 0xFF)
        self.write8(0x22D1, SEG_TABLE_ADDR >> 8)

    def init_decompress(self, src_off: int, seg_idx: int | None = None) -> int:
        """Prépare CD4B/CD12 : table segments @ $800A, index dans A / $22E1."""
        from hudson_vm import parse_pack_segment_table

        offsets = parse_pack_segment_table(self.pack)
        if not offsets:
            offsets = list(DEFAULT_SEG_OFFSETS)
        self.install_segment_table(offsets)

        if seg_idx is None:
            seg_idx = offsets.index(src_off) if src_off in offsets else 0
        seg_idx &= 0xFF
        self.a = seg_idx
        self.write8(0x22E1, seg_idx)
        self.zp_w(0x24, self.read8(0x22DB))
        self.zp_w(0x25, self.read8(0x22DC))
        return seg_idx

    def jsr_to(self, target: int) -> None:
        self.push((self.pc >> 8) & 0xFF)
        self.push(self.pc & 0xFF)
        self.pc = target

    def run_jsr(self, target: int, *, strict: bool = False) -> None:
        self.jsr_to(target)
        depth = 1
        self.halted = False
        while depth > 0 and not self.halted:
            prev = self.pc
            try:
                self.step()
            except RuntimeError:
                if strict:
                    raise
                break
            if self.halted:
                break
            op = self.read8(prev)
            if op in (0x20, 0x44):
                depth += 1
            elif op == 0x60:
                depth -= 1

    def step(self) -> None:
        if self.halted or self.pc in self.stop_addrs:
            self.halted = True
            return
        self.steps += 1
        if self.steps > self.max_steps:
            raise RuntimeError(f"max steps @ ${self.pc:04X}")

        pc = self.pc
        op = self.read8(pc)

        # HuC6280 extensions (voir matrice Covell)
        if op == 0x02:  # JMP abs (Hudson)
            self.pc = self.abs16(pc)
            return
        if op == 0x44:  # BSR rel16
            rel = struct.unpack_from("<h", self.mem, pc + 1)[0]
            self.push(((pc + 2) >> 8) & 0xFF)
            self.push((pc + 2) & 0xFF)
            self.pc = self.u16(pc + 3 + rel)
            return
        if op == 0x62:  # CLA
            self.a = 0
            self.set_nz(self.a)
            self.pc = pc + 1
            return
        if op == 0x82:  # CLX
            self.x = 0
            self.set_nz(self.x)
            self.pc = pc + 1
            return
        if op == 0xC2:  # CLY
            self.y = 0
            self.set_nz(self.y)
            self.pc = pc + 1
            return
        if op == 0x64:  # STZ zp
            self.zp_w(self.read8(pc + 1), 0)
            self.pc = pc + 2
            return
        if op == 0x9C:  # STZ abs
            self.write8(self.abs16(pc), 0)
            self.pc = pc + 3
            return
        if op == 0x03:  # ST0 #imm (I/O — no-op stub)
            self.pc = pc + 2
            return
        if op == 0x13:  # ST1 #imm (I/O — no-op stub)
            self.pc = pc + 2
            return
        if op == 0x04:  # TSB zp
            zp = self.read8(pc + 1)
            self.zp_w(zp, self.u8(self.zp_r(zp) | self.a))
            self.pc = pc + 2
            return
        if op == 0x0C:  # TSB abs
            addr = self.abs16(pc)
            self.write8(addr, self.u8(self.read8(addr) | self.a))
            self.pc = pc + 3
            return
        if op == 0x14:  # TRB zp
            zp = self.read8(pc + 1)
            self.zp_w(zp, self.u8(self.zp_r(zp) & ~self.a))
            self.pc = pc + 2
            return
        if op == 0x1C:  # TRB abs
            addr = self.abs16(pc)
            self.write8(addr, self.u8(self.read8(addr) & ~self.a))
            self.pc = pc + 3
            return
        if op == 0x24:  # BIT zp
            self.bit(self.zp_r(self.read8(pc + 1)))
            self.pc = pc + 2
            return
        if op == 0x2C:  # BIT abs
            self.bit(self.read8(self.abs16(pc)))
            self.pc = pc + 3
            return
        if op == 0x22:  # SAX zp — store (A & X)
            zp = self.read8(pc + 1)
            self.zp_w(zp, self.a & self.x)
            self.pc = pc + 2
            return
        if op == 0x7C:  # JMP [abs,X]
            base = self.abs16(pc)
            self.pc = struct.unpack_from("<H", self.mem, self.u16(base + self.x))[0]
            return
        if op == 0xB2:  # LDA (zp),Y
            self.a = self.pack_read_ind_y(self.read8(pc + 1))
            self.set_nz(self.a)
            self.pc = pc + 2
            return
        if op == 0x71:  # ADC (zp),Y
            self.adc(self.pack_read_ind_y(self.read8(pc + 1)))
            self.pc = pc + 2
            return
        if op == 0x72:  # ADC (zp)
            zp = self.read8(pc + 1)
            self.adc(self.pack_read_abs(self.pack_ptr(zp)))
            self.pc = pc + 2
            return
        if op == 0x91:  # STA (zp),Y
            zp = self.read8(pc + 1)
            addr = self.u16(self.pack_ptr(zp) + self.y)
            self.write_abs(addr, self.a)
            self.pc = pc + 2
            return
        if op == 0x9E:  # STZ abs,X
            self.write8(self.u16(self.abs16(pc) + self.x), 0)
            self.pc = pc + 3
            return
        if op == 0xBE:  # LDX abs,Y
            self.x = self.read8(self.u16(self.abs16(pc) + self.y))
            self.set_nz(self.x)
            self.pc = pc + 3
            return
        if op == 0xBC:  # LDY abs,X
            self.y = self.read8(self.u16(self.abs16(pc) + self.x))
            self.set_nz(self.y)
            self.pc = pc + 3
            return
        if op == 0x83:  # TST #imm, zp
            imm = self.read8(pc + 1)
            self.tst(imm, self.zp_r(self.read8(pc + 2)))
            self.pc = pc + 3
            return
        if op == 0x93:  # TST #imm, abs
            imm = self.read8(pc + 1)
            self.tst(imm, self.read8(self.abs16(pc + 2)))
            self.pc = pc + 4
            return
        if op == 0xA3:  # TST #imm, zp,X
            imm = self.read8(pc + 1)
            zp = self.u8(self.read8(pc + 2) + self.x)
            self.tst(imm, self.zp_r(zp))
            self.pc = pc + 3
            return
        if op == 0xB3:  # TST #imm, abs,X
            imm = self.read8(pc + 1)
            self.tst(imm, self.read8(self.u16(self.abs16(pc + 2) + self.x)))
            self.pc = pc + 4
            return
        if op == 0xCE:  # DEC abs
            addr = self.abs16(pc)
            self.write8(addr, self.u8(self.read8(addr) - 1))
            self.pc = pc + 3
            return
        if op == 0xDE:  # DEC abs,X
            addr = self.u16(self.abs16(pc) + self.x)
            self.write8(addr, self.u8(self.read8(addr) - 1))
            self.pc = pc + 3
            return
        if op == 0xFE:  # INC abs,X
            addr = self.u16(self.abs16(pc) + self.x)
            v = self.u8(self.read8(addr) + 1)
            self.write8(addr, v)
            self.pc = pc + 3
            return
        if (op & 0x0F) == 0x0F:  # BBRn / BBSn zp, rel
            n = (op >> 4) & 7
            zp = self.read8(pc + 1)
            bit = bool(self.zp_r(zp) & (1 << n))
            cond = bit if op >= 0x80 else not bit
            self.pc = self.branch(pc + 1, cond)
            return
        if (op & 0x0F) == 0x07:  # RMBn / SMBn zp
            n = (op >> 4) & 7
            zp = self.read8(pc + 1)
            mask = 1 << n
            if op < 0x80:
                self.zp_w(zp, self.u8(self.zp_r(zp) & ~mask))
            else:
                self.zp_w(zp, self.u8(self.zp_r(zp) | mask))
            self.pc = pc + 2
            return
        if op == 0x80:  # BRA
            self.pc = self.branch(pc, True)
            return
        if op == 0x1A:  # INC A
            self.a = self.u8(self.a + 1)
            self.set_nz(self.a)
            self.pc = pc + 1
            return
        if op == 0x3A:  # DEC A
            self.a = self.u8(self.a - 1)
            self.set_nz(self.a)
            self.pc = pc + 1
            return
        if op == 0x5A:  # PHY
            self.push(self.y)
            self.pc = pc + 1
            return
        if op == 0x7A:  # PLY
            self.y = self.pull()
            self.pc = pc + 1
            return
        if op == 0xDA:  # PHX
            self.push(self.x)
            self.pc = pc + 1
            return
        if op == 0xFA:  # PLX
            self.x = self.pull()
            self.pc = pc + 1
            return

        # 6502 / 65C02 commun
        if op == 0xA9:
            self.a = self.read8(pc + 1)
            self.set_nz(self.a)
            self.pc = pc + 2
        elif op == 0xA5:
            self.a = self.zp_r(self.read8(pc + 1))
            self.set_nz(self.a)
            self.pc = pc + 2
        elif op == 0xB5:
            self.a = self.zp_r(self.u8(self.read8(pc + 1) + self.x))
            self.set_nz(self.a)
            self.pc = pc + 2
        elif op == 0xAD:
            self.a = self.read8(self.abs16(pc))
            self.set_nz(self.a)
            self.pc = pc + 3
        elif op == 0xBD:
            self.a = self.read8(self.u16(self.abs16(pc) + self.x))
            self.set_nz(self.a)
            self.pc = pc + 3
        elif op == 0xB9:
            self.a = self.read8(self.u16(self.abs16(pc) + self.y))
            self.set_nz(self.a)
            self.pc = pc + 3
        elif op == 0xB1:
            zp = self.read8(pc + 1)
            self.a = self.pack_read_abs(self.u16(self.pack_ptr(zp) + self.y))
            self.set_nz(self.a)
            self.pc = pc + 2
        elif op == 0xA4:
            self.y = self.zp_r(self.read8(pc + 1))
            self.set_nz(self.y)
            self.pc = pc + 2
        elif op == 0xA6:
            self.x = self.zp_r(self.read8(pc + 1))
            self.set_nz(self.x)
            self.pc = pc + 2
        elif op == 0xAC:
            self.y = self.read8(self.abs16(pc))
            self.set_nz(self.y)
            self.pc = pc + 3
        elif op == 0xAE:
            self.x = self.read8(self.abs16(pc))
            self.set_nz(self.x)
            self.pc = pc + 3
        elif op == 0x84:
            self.zp_w(self.read8(pc + 1), self.y)
            self.pc = pc + 2
        elif op == 0x85:
            self.zp_w(self.read8(pc + 1), self.a)
            self.pc = pc + 2
        elif op == 0x86:
            self.zp_w(self.read8(pc + 1), self.x)
            self.pc = pc + 2
        elif op == 0x8D:
            self.write8(self.abs16(pc), self.a)
            self.pc = pc + 3
        elif op == 0x99:
            self.write8(self.u16(self.abs16(pc) + self.y), self.a)
            self.pc = pc + 3
        elif op == 0x9D:
            self.write8(self.u16(self.abs16(pc) + self.x), self.a)
            self.pc = pc + 3
        elif op == 0xA8:
            self.y = self.a
            self.set_nz(self.y)
            self.pc = pc + 1
        elif op == 0xAA:
            self.x = self.a
            self.set_nz(self.x)
            self.pc = pc + 1
        elif op == 0x8A:
            self.a = self.x
            self.set_nz(self.a)
            self.pc = pc + 1
        elif op == 0x98:
            self.a = self.y
            self.set_nz(self.a)
            self.pc = pc + 1
        elif op == 0x18:
            self.setf(FLAG_C, False)
            self.pc = pc + 1
        elif op == 0x38:
            self.setf(FLAG_C, True)
            self.pc = pc + 1
        elif op == 0x05:
            self.a |= self.zp_r(self.read8(pc + 1))
            self.set_nz(self.a)
            self.pc = pc + 2
        elif op == 0x0D:
            self.a |= self.read8(self.abs16(pc))
            self.set_nz(self.a)
            self.pc = pc + 3
        elif op == 0x29:
            self.a &= self.read8(pc + 1)
            self.set_nz(self.a)
            self.pc = pc + 2
        elif op == 0x49:
            self.a ^= self.read8(pc + 1)
            self.set_nz(self.a)
            self.pc = pc + 2
        elif op == 0xD9:
            self.cmp(self.a, self.read8(self.u16(self.abs16(pc) + self.y)))
            self.pc = pc + 3
        elif op == 0xC9:
            self.cmp(self.a, self.read8(pc + 1))
            self.pc = pc + 2
        elif op == 0xE0:
            self.cmp(self.x, self.read8(pc + 1))
            self.pc = pc + 2
        elif op == 0xC0:
            self.cmp(self.y, self.read8(pc + 1))
            self.pc = pc + 2
        elif op == 0x65:
            self.adc(self.zp_r(self.read8(pc + 1)))
            self.pc = pc + 2
        elif op == 0x6D:
            self.adc(self.read8(self.abs16(pc)))
            self.pc = pc + 3
        elif op == 0x7D:
            self.adc(self.read8(self.u16(self.abs16(pc) + self.x)))
            self.pc = pc + 3
        elif op == 0x79:
            self.adc(self.read8(self.u16(self.abs16(pc) + self.y)))
            self.pc = pc + 3
        elif op == 0x06:
            zp = self.read8(pc + 1)
            v = self.u8(self.zp_r(zp) << 1)
            self.setf(FLAG_C, bool(self.zp_r(zp) & 0x80))
            self.zp_w(zp, v)
            self.pc = pc + 2
        elif op == 0x26:
            zp = self.read8(pc + 1)
            c = 1 if self.flag(FLAG_C) else 0
            v = self.zp_r(zp)
            self.setf(FLAG_C, bool(v & 0x80))
            self.zp_w(zp, self.u8((v << 1) | c))
            self.pc = pc + 2
        elif op == 0x46:
            zp = self.read8(pc + 1)
            v = self.zp_r(zp)
            self.setf(FLAG_C, bool(v & 0x01))
            self.zp_w(zp, v >> 1)
            self.pc = pc + 2
        elif op == 0x66:
            zp = self.read8(pc + 1)
            c = 1 if self.flag(FLAG_C) else 0
            v = self.zp_r(zp)
            self.setf(FLAG_C, bool(v & 0x01))
            self.zp_w(zp, self.u8((v >> 1) | (c << 7)))
            self.pc = pc + 2
        elif op == 0xE5:
            self.sbc(self.zp_r(self.read8(pc + 1)))
            self.pc = pc + 2
        elif op == 0xE9:
            self.sbc(self.read8(pc + 1))
            self.pc = pc + 2
        elif op == 0xED:
            self.sbc(self.read8(self.abs16(pc)))
            self.pc = pc + 3
        elif op == 0xFD:
            self.sbc(self.read8(self.u16(self.abs16(pc) + self.x)))
            self.pc = pc + 3
        elif op == 0xEE:
            addr = self.abs16(pc)
            self.write8(addr, self.u8(self.read8(addr) + 1))
            self.pc = pc + 3
        elif op == 0x0A:
            self.setf(FLAG_C, bool(self.a & 0x80))
            self.a = self.u8(self.a << 1)
            self.set_nz(self.a)
            self.pc = pc + 1
        elif op == 0x2A:
            self.rol_a()
            self.pc = pc + 1
        elif op == 0x4A:
            self.lsr_a()
            self.pc = pc + 1
        elif op == 0x4C:
            self.pc = self.abs16(pc)
        elif op == 0x20:
            self.push(((pc + 2) >> 8) & 0xFF)
            self.push((pc + 2) & 0xFF)
            self.pc = self.abs16(pc)
        elif op == 0x60:
            lo = self.pull()
            hi = self.pull()
            self.pc = self.u16(lo | (hi << 8)) + 1
        elif op == 0x48:
            self.push(self.a)
            self.pc = pc + 1
        elif op == 0x68:
            self.a = self.pull()
            self.set_nz(self.a)
            self.pc = pc + 1
        elif op == 0xC8:
            self.y = self.u8(self.y + 1)
            self.pc = pc + 1
        elif op == 0x88:
            self.y = self.u8(self.y - 1)
            self.pc = pc + 1
        elif op == 0xE8:
            self.x = self.u8(self.x + 1)
            self.pc = pc + 1
        elif op == 0xCA:
            self.x = self.u8(self.x - 1)
            self.pc = pc + 1
        elif op == 0xE6:
            zp = self.read8(pc + 1)
            self.zp_w(zp, self.u8(self.zp_r(zp) + 1))
            self.pc = pc + 2
        elif op == 0xC6:
            zp = self.read8(pc + 1)
            self.zp_w(zp, self.u8(self.zp_r(zp) - 1))
            self.pc = pc + 2
        elif op == 0x90:
            self.pc = self.branch(pc, not self.flag(FLAG_C))
        elif op == 0xB0:
            self.pc = self.branch(pc, self.flag(FLAG_C))
        elif op == 0xF0:
            self.pc = self.branch(pc, self.flag(FLAG_Z))
        elif op == 0xD0:
            self.pc = self.branch(pc, not self.flag(FLAG_Z))
        elif op == 0x30:
            self.pc = self.branch(pc, self.flag(FLAG_N))
        elif op == 0x10:
            self.pc = self.branch(pc, not self.flag(FLAG_N))
        elif op == 0x00:
            self.halted = True
        else:
            raise RuntimeError(f"opcode ${op:02X} @ ${pc:04X}")


def decompress_segment_emulated(
    pack: bytes,
    src_off: int,
    *,
    dump: bytes | None = None,
) -> bytes:
    """Driver Hudson : VM $CE07 puis boucle $CD12 (CDF6→D510) par slot $22E0."""
    dump = dump or DEFAULT_CPU_DUMP.read_bytes()
    cpu = HuC6280(bytearray(dump), pack=pack, pack_base=0)
    cpu.load_mpr6(dump)
    seg_idx = cpu.init_decompress(src_off)
    cpu.out.clear()
    cpu.max_steps = 2_000_000

    # Pointeurs pack pour le slot courant (sans CD4B — préserve workspace Mesen)
    cpu.zp_w(0xE8, src_off & 0xFF)
    cpu.zp_w(0xE9, src_off >> 8)
    cpu.write8(0x248B + seg_idx, src_off & 0xFF)
    cpu.write8(0x2491 + seg_idx, src_off >> 8)
    cpu.run_jsr(0xCE07)

    ptr = cpu.zp_r(0xE8) | (cpu.zp_r(0xE9) << 8)
    cpu.write8(0x248B + seg_idx, ptr & 0xFF)
    cpu.write8(0x2491 + seg_idx, (ptr >> 8) & 0xFF)

    for x in range(6):
        if cpu.read8(0x260D + x) == 0:
            continue
        cpu.write8(0x22E0, x)
        lo = cpu.read8(0x248B + x)
        hi = cpu.read8(0x2491 + x)
        if lo == 0xFF and hi == 0xFF:
            cpu.zp_w(0xE8, src_off & 0xFF)
            cpu.zp_w(0xE9, src_off >> 8)
        else:
            cpu.zp_w(0xE8, lo)
            cpu.zp_w(0xE9, hi)
        for _ in range(8_192):
            if cpu.read8(0x260D + x) == 0:
                break
            prev = cpu.zp_r(0xE8) | (cpu.zp_r(0xE9) << 8)
            for fn in (0xD257, 0xD350, 0xD422, 0xD510):
                cpu.halted = False
                try:
                    cpu.run_jsr(fn)
                except RuntimeError:
                    break
            ptr = cpu.zp_r(0xE8) | (cpu.zp_r(0xE9) << 8)
            if ptr == prev:
                break

    return bytes(cpu.out)


def main() -> int:
    import argparse

    from hudson_pack import load_overlay_blob
    from tm2_disc import DEFAULT_TRACK2, load_user_data

    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("name", nargs="?", default="wa1")
    p.add_argument("--offset", type=lambda x: int(x, 0), default=0)
    p.add_argument("-o", type=Path, default=Path("work/huc6280_out.bin"))
    p.add_argument("--disc", type=Path, default=DEFAULT_TRACK2)
    args = p.parse_args()

    blob, _, _ = load_overlay_blob(load_user_data(args.disc), args.name)
    out = decompress_segment_emulated(blob, args.offset)
    args.o.write_bytes(out)
    print(f"{args.name}@{args.offset:#x}: {len(out)} o → {args.o}")
    return 0 if len(out) >= 128 else 1


if __name__ == "__main__":
    raise SystemExit(main())
