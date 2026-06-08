#!/usr/bin/env python3
"""Hudson pack / ivm2h overlay compression (Tengai Makyou II).

Retail CD artefacts (secteurs 0x6A00+) contain a *directory catalog* of the
developer PC HD (LZSS.EXE, ZPRESS.EXE, ivm2h.awk, …) but not the executable
payloads — only metadata (name, size, timestamps).  The file work/lzss.exe is
a coincidental ``MZ`` signature inside that catalog, not a runnable tool.

Decompression must come from reversing the runtime routine in TENGAI2.PRG
(dispatcher ``$51BA`` → ``JSR $E0D8``; see ``docs/PRG_DECOMPRESS.md``,
``tools/prg_unpack_re.py``) or obtaining original Hudson build tools elsewhere.
"""

from __future__ import annotations

import argparse
import json
import struct
from dataclasses import asdict, dataclass
from pathlib import Path

from tm2_disc import DEFAULT_TRACK2, load_user_data
from ys_data import measure_overlay_size, parse_adpos_catalog, sector_to_offset

# ivm2h.awk segment layout (spec string @ disc ~0x3570404 in build artefacts).
PACK_SEGMENTS: tuple[dict, ...] = (
    {"id": "data1", "ram_base": 0x8000, "max_size": 0x600, "role": "map_aux"},
    {"id": "data2", "ram_base": 0x0000, "max_size": 0x640, "role": "map_aux"},
    {"id": "data3", "ram_base": 0x0000, "max_size": 0x6E0, "role": "map_aux"},
    {"id": "adpcm_a", "ram_base": 0x0000, "max_size": 0x7C0, "role": "adpcm"},
    {"id": "vector_tpseg", "ram_base": 0x6000, "max_size": 0x580, "role": "tilemap"},
    {"id": "evt_mst_mes", "ram_base": 0x0100, "max_size": 0x581, "role": "script_npc_msg"},
    {"id": "evt_mst_mes_b", "ram_base": 0x0100, "max_size": 0x581, "role": "script_npc_msg"},
    {"id": "vector2_data1", "ram_base": 0x6000, "max_size": 0x580, "role": "tilemap"},
    {"id": "adpcm_b", "ram_base": 0x00FF, "max_size": 0x7FF, "role": "adpcm"},
)

BUILD_CATALOG_START = 0x3616000
BUILD_CATALOG_END = 0x3619000
IVM2H_SPEC_OFF = 0x3570404


@dataclass(frozen=True)
class ToolEntry:
    name: str
    size: int
    catalog_offset: int
    meta: tuple[int, int, int, int, int]


@dataclass
class DecompressAttempt:
    method: str
    ok: bool
    out_size: int
    note: str


@dataclass
class DecompressResult:
    ok: bool
    data: bytes | None
    method: str
    attempts: list[DecompressAttempt]
    notes: list[str]


def extract_ivm2h_spec(data: bytes) -> str:
    """Return the ivm2h segment command-line fragment from build artefacts."""
    if IVM2H_SPEC_OFF + 512 > len(data):
        return ""
    chunk = data[IVM2H_SPEC_OFF : IVM2H_SPEC_OFF + 400]
    out = bytearray()
    for b in chunk:
        if b in (0x00, 0xFF) and len(out) > 40:
            break
        if 32 <= b < 127 or b in (0x09,):
            out.append(b)
        elif len(out) > 40:
            break
    return out.decode("ascii", errors="replace")


def parse_build_tool_catalog(data: bytes) -> list[ToolEntry]:
    """Parse 32-byte Hudson HD directory records (name @ +20, size @ +16)."""
    entries: list[ToolEntry] = []
    for off in range(BUILD_CATALOG_START, BUILD_CATALOG_END, 32):
        rec = data[off : off + 32]
        name = rec[20:32].decode("ascii", errors="replace").strip("\x00").strip()
        if not name or not name[0].isalnum():
            continue
        meta = struct.unpack("<5I", rec[:20])
        size = meta[4]
        if size <= 0 or size > 10_000_000:
            continue
        entries.append(ToolEntry(name, size, off, meta))
    return entries


def _lzss_okumura(src: bytes, out_max: int, header_skip: int = 0) -> bytes | None:
    src = src[header_skip:]
    dst = bytearray()
    i = 0
    try:
        while len(dst) < out_max and i < len(src):
            flags = src[i]
            i += 1
            for bit in range(8):
                if len(dst) >= out_max or i >= len(src):
                    return bytes(dst)
                if flags & (1 << bit):
                    dst.append(src[i])
                    i += 1
                else:
                    if i + 1 >= len(src):
                        return bytes(dst)
                    b0, b1 = src[i], src[i + 1]
                    i += 2
                    length = (b1 & 0x0F) + 3
                    offset = b0 | ((b1 & 0xF0) << 4)
                    if offset == 0:
                        return bytes(dst)
                    pos = len(dst) - offset
                    if pos < 0:
                        return None
                    for _ in range(length):
                        dst.append(dst[pos])
                        pos += 1
        return bytes(dst)
    except (IndexError, ValueError):
        return None


def _score_decompressed(blob: bytes) -> int:
    if len(blob) < 128:
        return -1
    score = sum(1 for b in blob[:512] if b < 0x40)
    for marker in (b"\x01\x00\x00\x00\x00", b"\x02", b"\x10"):
        if marker in blob[:4096]:
            score += 200
    score += sum(2 for b in blob[:1024] if 0x81 <= b <= 0xFC)
    if len(set(blob[:256])) > 200:
        score -= 100
    return score


def try_decompress_overlay(blob: bytes) -> DecompressResult:
    """Try known compression families; Hudson VM ($CDF6) depuis mesen_decomp."""
    from hudson_vm import decompress_pack

    attempts: list[DecompressAttempt] = []
    notes = [
        "Formats testés : hudson_vm ($CDF6), LZSS Okumura (entête 0/2/4 o).",
    ]

    vm_raw, vm_method = decompress_pack(blob)
    if vm_raw:
        sc = _score_decompressed(vm_raw)
        attempts.append(
            DecompressAttempt(vm_method or "hudson_vm", sc > 400, len(vm_raw), f"heuristic={sc}")
        )
        if sc > 400:
            return DecompressResult(True, vm_raw, vm_method or "hudson_vm", attempts, notes)
    out_max = sum(seg["max_size"] for seg in PACK_SEGMENTS)
    candidates: list[tuple[str, bytes | None]] = []

    for skip in (0, 2, 4, 8, 16):
        for limit in (out_max, 65536, len(blob) * 4):
            label = f"lzss_okumura_skip{skip}_max{limit:#x}"
            raw = _lzss_okumura(blob, limit, skip)
            candidates.append((label, raw))

    best: tuple[str, bytes] | None = None
    best_score = 0
    for method, raw in candidates:
        if not raw or len(raw) < 256:
            attempts.append(DecompressAttempt(method, False, len(raw) if raw else 0, "too small"))
            continue
        sc = _score_decompressed(raw)
        attempts.append(
            DecompressAttempt(method, sc > 400, len(raw), f"heuristic={sc}")
        )
        if sc > best_score:
            best_score = sc
            best = (method, raw)

    if best and best_score > 400:
        return DecompressResult(True, best[1], best[0], attempts, notes)

    return DecompressResult(False, None, "", attempts, notes)


def load_overlay_blob(data: bytes, name: str) -> tuple[bytes, int, int]:
    catalog = {n: s for n, s in parse_adpos_catalog(data)}
    if name not in catalog:
        known = ", ".join(sorted(catalog))
        raise SystemExit(f"Overlay inconnu {name!r}. Connus: {known}")
    sector = catalog[name]
    start = sector_to_offset(sector)
    size = measure_overlay_size(data, sector) * 0x800
    return data[start : start + size], sector, size


def split_decompressed(blob: bytes) -> dict[str, bytes]:
    """Split a decompressed pack blob into ivm2h segments (fixed max sizes)."""
    pos = 0
    out: dict[str, bytes] = {}
    for seg in PACK_SEGMENTS:
        size = seg["max_size"]
        out[seg["id"]] = blob[pos : pos + size]
        pos += size
    return out


def write_split_with_decompress(data: bytes, name: str, out_dir: Path) -> dict:
    blob, sector, size = load_overlay_blob(data, name)
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / f"{name}.bin").write_bytes(blob)

    result = try_decompress_overlay(blob)
    manifest: dict = {
        "name": name,
        "sector": sector,
        "size": size,
        "compressed": not result.ok,
        "decompress_method": result.method or None,
        "ivm2h_spec": extract_ivm2h_spec(data),
        "segments": PACK_SEGMENTS,
        "extracted": {},
        "decompress_attempts": [asdict(a) for a in result.attempts[:12]],
        "notes": result.notes,
    }

    if result.ok and result.data:
        segments = split_decompressed(result.data)
        for seg_id, seg_data in segments.items():
            path = out_dir / f"{name}_{seg_id}.bin"
            path.write_bytes(seg_data)
            manifest["extracted"][seg_id] = len(seg_data)
        (out_dir / f"{name}_decompressed.bin").write_bytes(result.data)
    else:
        for seg in PACK_SEGMENTS:
            (out_dir / f"{name}_{seg['id']}.bin").write_bytes(b"")
            manifest["extracted"][seg["id"]] = None
        manifest["notes"].append(
            "Binaires ZPRESS/LZSS absents du CD retail (catalogue dev seulement). "
            "Voir tools/hudson_pack.py catalog."
        )

    (out_dir / f"{name}_manifest.json").write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    return manifest


def cmd_catalog(data: bytes, out: Path | None) -> None:
    tools = parse_build_tool_catalog(data)
    payload = {
        "ivm2h_spec": extract_ivm2h_spec(data),
        "note": (
            "Entrées 32 o du disque développeur. Les fichiers .EXE listés "
            "(LZSS, ZPRESS, …) ne sont en général pas copiés dans l'image retail."
        ),
        "tools": [asdict(t) for t in tools if "EXE" in t.name or "AWK" in t.name],
    }
    text = json.dumps(payload, indent=2, ensure_ascii=False) + "\n"
    if out:
        out.write_text(text, encoding="utf-8")
        print(f"Écrit {out}")
    else:
        print(text)


def cmd_decompress(data: bytes, name: str, out_dir: Path) -> None:
    manifest = write_split_with_decompress(data, name, out_dir)
    if manifest["decompress_method"]:
        print(f"{name}: décompressé ({manifest['decompress_method']}) → {out_dir}")
    else:
        print(f"{name}: décompression échouée — segments laissés vides")
        print(f"  Manifest : {out_dir}/{name}_manifest.json")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--disc", type=Path, default=DEFAULT_TRACK2)
    sub = parser.add_subparsers(dest="command", required=True)

    cat_p = sub.add_parser("catalog", help="Catalogue outils build (sect. 0x6A00+)")
    cat_p.add_argument("-o", "--output", type=Path)

    dec_p = sub.add_parser("decompress", help="Tenter pack + écrire segments")
    dec_p.add_argument("name", help="adpos (yav, wa1, …)")
    dec_p.add_argument("-o", "--output", type=Path, required=True)

    args = parser.parse_args()
    data = load_user_data(args.disc)

    if args.command == "catalog":
        cmd_catalog(data, args.output)
    elif args.command == "decompress":
        cmd_decompress(data, args.name, args.output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
