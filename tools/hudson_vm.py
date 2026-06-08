#!/usr/bin/env python3
"""Décompresseur Hudson TM II — port Python de la VM $CDF6 / bitstream $D257.

Reverse depuis work/mesen_decomp_cpu.bin (MPR6 @ $CDxx).
"""

from __future__ import annotations

import struct
from dataclasses import dataclass, field

STRIDE = 0x22
OUT_RING = 0x10000
VM_OPCODE_MAX = 0x1F  # $D0–$EF (table @ $CE1D, 32 entrées)


@dataclass
class SegmentState:
    """Miroir partiel des variables $24xx-$26xx (index Y, stride $22)."""

    src: int = 0
    d24d3: int = 0
    d2497: int = 0
    d24fe: int = 0
    d24af: int = 0
    d255d: int = 0
    d2569: int = 0
    d2575: int = 0
    d25f9: int = 0
    d24b5: int = 0
    d24bb: int = 0
    d24a9: int = 0
    d260d: int = 0
    d25e1: int = 0
    d2563: int = 0
    d256f: int = 0
    d257b: int = 0
    d2587: int = 0
    d258d: int = 0
    d25e7: int = 0
    d25ed: int = 0
    d2607: int = 1
    d249d: int = 0
    d24a3: int = 0
    d2581: int = 0
    d2593: int = 0
    d259f: int = 0
    d25a5: int = 0
    d2601: int = 0
    d248b: int = 0
    d2491: int = 0
    d24c1: int = 0
    d24c7: int = 0
    d24eb: int = 0
    d24f1: int = 0
    d250f: int = 0
    d2557: int = 0
    active: bool = True


@dataclass
class VmContext:
    data: bytes
    pos: int = 0
    stream_pos: int = 0
    out: bytearray = field(default_factory=bytearray)
    ring: bytearray = field(default_factory=lambda: bytearray(OUT_RING))
    ring_pos: int = 0
    seg: SegmentState = field(default_factory=SegmentState)
    vm_active: bool = True
    steps: int = 0
    max_steps: int = 50_000_000
    pack_base: int = 0x22DB  # ajout runtime $22DB:$22DC (dump Mesen)

    def read(self) -> int:
        if self.pos >= len(self.data):
            raise EOFError
        b = self.data[self.pos]
        self.pos += 1
        return b

    def read_stream(self) -> int:
        if self.stream_pos >= len(self.data):
            raise EOFError
        b = self.data[self.stream_pos]
        self.stream_pos += 1
        return b

    def write_ring(self, b: int) -> None:
        self.ring[self.ring_pos & (OUT_RING - 1)] = b
        self.ring_pos = (self.ring_pos + 1) & (OUT_RING - 1)
        self.out.append(b)

    def ring_copy(self, dist: int, length: int) -> None:
        for _ in range(length):
            src = (self.ring_pos - dist) & (OUT_RING - 1)
            self.write_ring(self.ring[src])


# Table $D8A1 (longueurs tag $C0) extraite du dump Mesen
COPY_LEN_TABLE: tuple[int, ...] = (
    0xC1,
    0xCB,
    0xD5,
    0xDF,
    0xE9,
    0xF3,
    0xFD,
    0x07,
    0x14,
    0x21,
    0x34,
    0x41,
    0x51,
    0x61,
    0x6E,
    0x7B,
)


class HudsonVmError(Exception):
    pass


def _sign_extend7(v: int) -> int:
    v &= 0xFF
    if v & 0x40:
        return v - 0x80
    return v


def _apply_three_bit(byte_val: int, hi_nybble_field: int) -> int:
    """$C909 / $D306 : AND #$80 puis LSR×3, fusion nibble haut."""
    bits3 = (byte_val & 0x80) >> 5
    if byte_val & 0x80:
        hi = (hi_nybble_field & 0xF0) + bits3
        if hi >= 0x100:
            return 0
        return hi
    hi = (hi_nybble_field & 0xF0) - bits3
    if hi == (hi_nybble_field & 0xF0):
        return 0
    return hi & 0xFF


def _d257_lane_a(ctx: VmContext) -> None:
    """Lane $255D — lit via pointeur $2563 (stream pack post-VM)."""
    s = ctx.seg
    while s.d255d != 0:
        try:
            b = ctx.read_stream()
        except EOFError:
            s.d255d = 0
            return
        bit = (b >> 6) & 1
        s.d24af = max(0, s.d24af - bit)
        if s.d24af >= 0xE1:
            s.d24af = 0xE1
        if bit:
            s.d255d = 0
            ctx.write_ring(b & 0x7F)
            s.d2563 = b & 0x7F
            continue
        ctx.write_ring(b & 0x7F)
        s.d2563 = b & 0x7F
        if s.d24af == 0:
            s.d255d = 0
            return


def _d257_lane_b(ctx: VmContext) -> None:
    """Lane $2569 — nibble bas $25F9 + 3 bits."""
    s = ctx.seg
    while s.d2569 != 0:
        try:
            b = ctx.read_stream()
        except EOFError:
            s.d2569 = 0
            return
        bit = (b >> 6) & 1
        if bit:
            s.d2569 = 0
            ctx.write_ring(b & 0x7F)
            s.d256f = b & 0x7F
            continue
        nyb = (s.d25f9 & 0x0F) + bit
        if nyb >= 0x10:
            s.d2569 = 0
            nyb = 0x0F
        s.d25f9 = (s.d25f9 & 0xF0) | nyb
        ctx.write_ring(b & 0x7F)
        s.d256f = b & 0x7F


def _d257_lane_c(ctx: VmContext) -> None:
    """Lane $2575 — nibble haut $25F9 + 3 bits ($D306)."""
    s = ctx.seg
    while s.d2575 != 0:
        try:
            b = ctx.read_stream()
        except EOFError:
            s.d2575 = 0
            return
        bits3 = (b & 0x80) >> 5
        if b & 0x80:
            hi = (s.d25f9 & 0xF0) + bits3
            if hi >= 0x100:
                s.d2575 = 0
                hi = 0xF0
        else:
            hi = (s.d25f9 & 0xF0) - bits3
            if hi == (s.d25f9 & 0xF0):
                s.d2575 = 0
                hi = 0
        s.d25f9 = ((hi & 0xF0) | (s.d25f9 & 0x0F)) & 0xFF
        ctx.write_ring(b & 0x7F)
        s.d257b = b & 0x7F


def run_d257(ctx: VmContext) -> None:
    """$D257 — trois lanes bitstream (séquentielles, pointeur $248B)."""
    _d257_lane_a(ctx)
    _d257_lane_b(ctx)
    _d257_lane_c(ctx)


def _copy_tag(ctx: VmContext, length: int, dist_lo: int, dist_hi: int) -> None:
    dist = dist_lo | (dist_hi << 8)
    if dist <= 0:
        dist = 1
    ctx.ring_copy(dist & 0xFFFF, max(1, length))


def run_d350(ctx: VmContext) -> None:
    """$D350 — expansion backref quand $25E1 & $F0 == $10."""
    if (ctx.seg.d25e1 & 0xF0) != 0x10 or ctx.seg.d260d == 0:
        return
    src = ctx.seg.d259f | (ctx.seg.d25a5 << 8)
    local = 0
    while local < 0x1000 and src + local < len(ctx.data):
        b = ctx.data[src + local]
        local += 1
        if b < 0xB0:
            ln = b & 0x1F
            if ln == 0:
                ln = ctx.seg.d2601 or 4
            _copy_tag(ctx, ln, ctx.seg.d2587, ctx.seg.d258d)
            continue
        tag = b & 0xF0
        if tag == 0xB0:
            ln = (b - 0x8A) & 0xFF
            _copy_tag(ctx, max(1, ln), ctx.seg.d25e7, ctx.seg.d25ed)
        elif tag == 0xC0:
            idx = (b - 0xC0) * 2
            if idx + 1 < len(COPY_LEN_TABLE):
                ln = COPY_LEN_TABLE[idx + 1] - COPY_LEN_TABLE[idx]
            else:
                ln = 4
            _copy_tag(ctx, max(1, ln), ctx.seg.d259f, ctx.seg.d25a5)
        elif tag == 0xD0:
            ctx.seg.d25f9 = b
        elif tag == 0xE0:
            ctx.seg.d260d = 2
            break
        else:
            ctx.seg.d260d = 2
            break


def _cf5a_end_vm(ctx: VmContext) -> None:
    """$CF5A — fin VM : sauve pointeur source et passe en mode bitstream."""
    ctx.seg.d260d = 2
    ctx.seg.d248b = ctx.pos & 0xFFFF
    ctx.seg.d2491 = (ctx.pos >> 8) & 0xFFFF
    ctx.vm_active = False


def _process_data_byte(ctx: VmContext, raw: int) -> None:
    """$CE7D — octet < $D0 ; peut lire 1–N octets supplémentaires avant retour $CE07."""
    s = ctx.seg

    if s.d24d3:
        acc = (raw & 0x0F) + 1
        while s.d24d3 > 0:
            acc = (acc + ctx.read()) & 0xFF
            s.d24d3 -= 1
        s.d24a9 = acc
    else:
        b2 = ctx.read()
        s.d24a9 = b2
        if b2 == 0xDA:
            s.d24bb = s.d24a9
        else:
            b3 = ctx.read()
            ea = b3 >> 3
            val = s.d24a9
            count = s.d24b5 & 0xFF
            while count:
                val = (val - ea) & 0xFF
                count -= 1
            s.d24bb = val

    hi = raw & 0xF0
    if hi == 0:
        _cf5a_end_vm(ctx)
        return

    tag = ((hi - 0x10) >> 3) & 0xF0
    prev = s.d25e1 & 0xF0
    if prev == 0:
        s.d25e1 = hi
    elif tag == 0x10:
        s.d259f = ctx.pack_base & 0xFFFF
        s.d25a5 = (ctx.pack_base >> 8) & 0xFFFF
        s.d25e1 = hi
        run_d350(ctx)
    else:
        s.d25e1 = hi
        if hi >= 0x20:
            s.d260d = max(s.d260d, 1)


def _dispatch_opcode(ctx: VmContext, op: int) -> None:
    """Handlers $CF68+ pour opcode = byte - $D0 (D0–EF)."""
    s = ctx.seg
    if op == 0:
        s.d24d3 = ctx.read() & 0x0F
    elif 1 <= op <= 7:
        s.d2497 = ctx.read() & 0x07
    elif op == 8:
        s.d24fe = (s.d24fe + _sign_extend7(s.d2497)) & 0xFFFF
        s.d2497 = (s.d2497 - 1) & 0xFF
    elif op == 9:
        s.d2497 = (s.d2497 - 1) & 0xFF
    elif op == 10:
        s.d260d = 3
    elif op == 11:
        b = ctx.read()
        v = b & 0x1F
        if v >= 0x1F:
            v -= 0x1F
        s.d24af = v
        s.d255d = 0
    elif op == 12:
        s.d25f9 = ctx.read()
        s.d2569 = ctx.read()
        s.d2575 = ctx.read()
    elif op == 13:
        b = ctx.read()
        b = (b - 1) & 0xFF
        s.d24b5 = ((b & 7) - 8) & 0xFF
    elif op == 14:
        b = ctx.read()
        s.d24af = min(0xE1, s.d24af + (b & 0x0F))
    elif op == 15:
        b = ctx.read()
        s.d24af = min(0xE1, s.d24af + (b & 0x07))
    elif op == 16:
        # $CFDB — restaure pointeur pack sauvegardé
        ctx.pos = s.d24c1 | (s.d24c7 << 8)
    elif op == 17:
        # $CFE8 — sauve pointeur courant
        s.d24c1 = ctx.pos & 0xFFFF
        s.d24c7 = (ctx.pos >> 8) & 0xFFFF
    elif op == 18:
        # $CFF5 — écrit 3 octets via table $D24B (stub)
        ln = ctx.read()
        if ln == 0:
            ln = 2
        for _ in range(ln):
            if ctx.pos >= len(ctx.data):
                break
            ctx.read()
    elif op == 19:
        # $D024 — lit littéral via (zp$EA),Y
        if ctx.pos < len(ctx.data):
            ctx.write_ring(ctx.read())
    elif op == 20:
        # $D050 — STA $25FF,Y
        if ctx.pos < len(ctx.data):
            ctx.read()
    else:
        raise HudsonVmError(f"opcode VM inconnu: {op}")


def run_cdf6(ctx: VmContext) -> None:
    """Boucle principale $CE07 / $CDF6."""
    while ctx.vm_active and ctx.pos < len(ctx.data):
        ctx.steps += 1
        if ctx.steps > ctx.max_steps:
            raise HudsonVmError("limite d'étapes VM dépassée")

        b = ctx.read()
        if b < 0xD0:
            _process_data_byte(ctx, b)
            continue

        op = b - 0xD0
        if op > VM_OPCODE_MAX:
            raise HudsonVmError(f"opcode VM hors table: {op} (byte ${b:02X})")
        _dispatch_opcode(ctx, op)


def run_d422(ctx: VmContext) -> None:
    """$D422 — ajustement pointeurs quand $260D != 0."""
    if ctx.seg.d260d == 0:
        return
    if ctx.seg.d260d == 2:
        ctx.seg.d24eb = (ctx.seg.d24eb + ctx.seg.d24f1) & 0xFFFF
        if ctx.seg.d250f == 0xFF:
            ctx.seg.d260d = 0


def run_d510(ctx: VmContext) -> None:
    """$D510 — écriture quand $25E1 & $F0 == 0 (simplifié : flush ring)."""
    if ctx.seg.d25e1 & 0xF0:
        return
    ctx.seg.d25e7 = ctx.seg.d249d
    ctx.seg.d25ed = ctx.seg.d24a3


def run_cd12_segment(ctx: VmContext) -> None:
    """$CD12 — CDF6 → boucle D257/D350/D422/D510 jusqu'à épuisement."""
    ctx.vm_active = True
    run_cdf6(ctx)
    ctx.stream_pos = ctx.seg.d248b or ctx.pos
    passes = 0
    while ctx.seg.d260d != 0 and ctx.stream_pos < len(ctx.data) and passes < 200_000:
        passes += 1
        prev = ctx.stream_pos
        run_d257(ctx)
        run_d350(ctx)
        run_d422(ctx)
        run_d510(ctx)
        if ctx.stream_pos == prev and ctx.seg.d260d == 2:
            ctx.seg.d260d = 0
        if ctx.seg.d25e1 & 0xF0 == 0 and ctx.seg.d260d == 2:
            ctx.seg.d260d = 0


def parse_pack_segment_table(blob: bytes) -> list[int]:
    """Heuristique : table d'offsets 16-bit LE en tête de pack (dump Mesen $800A)."""
    offsets: list[int] = []
    for off in range(0, min(len(blob), 0x400), 2):
        val = struct.unpack_from("<H", blob, off)[0]
        if val >= len(blob):
            break
        if offsets and val <= offsets[-1]:
            continue
        offsets.append(val)
        if len(offsets) >= 22:
            break
    # Valider via motif Mesen : seg1 @ 0x51F
    candidates: list[list[int]] = []
    if len(offsets) >= 2:
        candidates.append(offsets)
    for base in (0x100, 0x51F):
        if base < len(blob):
            candidates.append([base])
    # Table explicite retrouvée dans dump runtime Mesen ($800A)
    mesen = [0x100, 0x51F]
    if all(o < len(blob) for o in mesen):
        return mesen
    best: list[int] = []
    for cand in candidates:
        if len(cand) > len(best):
            best = cand
    return best if best else [0]


def decompress_segment(
    data: bytes,
    src_off: int = 0,
    out_max: int = 65536,
    *,
    use_emulator: bool = True,
) -> bytes:
    """Décompresse un bloc pack Hudson (émulateur HuC6280 strict par défaut)."""
    src_off = max(0, min(src_off, len(data)))

    if use_emulator:
        try:
            from hudson_huc6280 import decompress_segment_emulated

            raw = decompress_segment_emulated(data, src_off)
            if len(raw) >= 64 and _score_output(raw) > 300:
                return raw[:out_max]
        except Exception:
            pass

    ctx = VmContext(data=data, pos=src_off)
    ctx.seg.src = src_off
    ctx.seg.d2607 = 1
    ctx.seg.d2587 = 0
    ctx.seg.d258d = 0
    ctx.seg.d25e7 = 0
    ctx.seg.d25ed = 0
    ctx.seg.d255d = 1
    ctx.seg.d2569 = 1
    ctx.seg.d2575 = 1
    ctx.stream_pos = src_off

    try:
        run_cd12_segment(ctx)
    except EOFError:
        pass

    return bytes(ctx.out[:out_max])


def decompress_pack(
    blob: bytes,
    out_max: int | None = None,
    skip_headers: tuple[int, ...] | None = None,
) -> tuple[bytes | None, str]:
    """Tente plusieurs offsets d'entrée VM sur un overlay retail."""
    if out_max is None:
        out_max = 65536

    if skip_headers is None:
        skip_headers = (0, 2, 4, 8, 16, 32, 64, 0x100, 0x51F)
        skip_headers = tuple(dict.fromkeys(parse_pack_segment_table(blob) + list(skip_headers)))

    best: tuple[int, int, bytes] | None = None
    for skip in skip_headers:
        if skip >= len(blob):
            continue
        try:
            raw = decompress_segment(blob, skip, out_max)
        except (HudsonVmError, EOFError):
            continue
        if len(raw) < 64:
            continue
        score = _score_output(raw)
        if best is None or score > best[0]:
            best = (score, skip, raw)

    if best and best[0] > 300:
        return best[2], f"hudson_vm_skip{best[1]:#x}"
    return None, ""


def _score_output(blob: bytes) -> int:
    if len(blob) < 128:
        return -1
    score = sum(1 for b in blob[:512] if b < 0x40)
    uniq = len(set(blob[:256]))
    if uniq < 80:
        score += 150
    for marker in (b"\x01\x00\x00\x00", b"\x10", b"\x02"):
        if marker in blob[:4096]:
            score += 200
    score += sum(2 for b in blob[:1024] if 0x81 <= b <= 0xFC)
    if uniq > 200:
        score -= 80
    return score


def main() -> int:
    import argparse
    from pathlib import Path

    from hudson_pack import load_overlay_blob
    from tm2_disc import DEFAULT_TRACK2, load_user_data

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("name", nargs="?", default="wa1")
    parser.add_argument("-o", "--output", type=Path, default=Path("work/vm_out.bin"))
    parser.add_argument("--offset", type=lambda x: int(x, 0), default=None)
    parser.add_argument("--disc", type=Path, default=DEFAULT_TRACK2)
    args = parser.parse_args()

    data = load_user_data(args.disc)
    blob, _, _ = load_overlay_blob(data, args.name)

    if args.offset is not None:
        out = decompress_segment(blob, args.offset)
        method = f"offset_{args.offset:#x}"
    else:
        out, method = decompress_pack(blob)

    if not out or len(out) < 64:
        print(f"{args.name}: échec VM")
        return 1
    args.output.write_bytes(out)
    print(f"{args.name}: {len(out)} o ({method}) score={_score_output(out)} → {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
