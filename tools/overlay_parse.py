#!/usr/bin/env python3
"""Parse Hudson map overlays (yav, wa*) and related event-map sectors."""

from __future__ import annotations

import argparse
import csv
import json
import re
import struct
from dataclasses import asdict, dataclass, field
from pathlib import Path

from hudson_pack import PACK_SEGMENTS, write_split_with_decompress
from tm2_disc import DEFAULT_TRACK2, load_user_data, sector_to_offset
from ys_data import measure_overlay_size, parse_adpos_catalog

SECTOR_SIZE = 0x800
LABEL_PREFIX = b"\x01\x00\x00\x00\x00"
JAPANESE_RE = re.compile(r"[\u3040-\u309F\u30A0-\u30FF\u4E00-\u9FFF]")

# ivm2h / pack.awk — voir tools/hudson_pack.py (PACK_SEGMENTS).


@dataclass
class EntityLabel:
    offset: int
    name: str


@dataclass
class ScriptMarker:
    offset: int
    kind: int
    arg: int | None
    preview: str


@dataclass
class ParsedRegion:
    name: str
    start: int
    end: int
    notes: str


@dataclass
class EventMapParse:
    sector: int
    size: int
    regions: list[ParsedRegion] = field(default_factory=list)
    entities: list[EntityLabel] = field(default_factory=list)
    script_markers: list[ScriptMarker] = field(default_factory=list)
    npc_blob_offset: int | None = None
    npc_blob_size: int = 0


@dataclass
class OverlayParse:
    name: str
    sector: int
    size: int
    compressed: bool
    segments: list[dict]
    strings: list[dict]
    entity_labels: list[EntityLabel]
    notes: list[str]


def is_sjis_lead(b: int) -> bool:
    return (0x81 <= b <= 0x9F) or (0xE0 <= b <= 0xFC)


def decode_sjis_run(data: bytes, pos: int, limit: int = 80) -> tuple[str, int]:
    out = bytearray()
    i = pos
    while i < len(data) and len(out) < limit:
        b = data[i]
        if b == 0x00:
            break
        if b >= 0xEF or b in (0x01, 0x02, 0x10):
            break
        if 0x20 <= b <= 0x7E:
            out.append(b)
            i += 1
            continue
        if is_sjis_lead(b) and i + 1 < len(data):
            b2 = data[i + 1]
            if 0x40 <= b2 <= 0xFC and b2 != 0x7F:
                out.extend((b, b2))
                i += 2
                continue
        break
    return out.decode("shift_jis", errors="replace"), i


def find_entity_labels(data: bytes) -> list[EntityLabel]:
    labels: list[EntityLabel] = []
    pos = 0
    while True:
        pos = data.find(LABEL_PREFIX, pos)
        if pos < 0:
            break
        end = data.find(b"\x00", pos + 5)
        if end < 0:
            break
        raw = data[pos + 5 : end]
        try:
            name = raw.decode("shift_jis")
        except UnicodeDecodeError:
            pos += 1
            continue
        if JAPANESE_RE.search(name) and 1 <= len(name) <= 24:
            labels.append(EntityLabel(pos, name))
        pos += 1
    return labels


def find_script_markers(data: bytes, limit: int = 100) -> list[ScriptMarker]:
    markers: list[ScriptMarker] = []
    pos = 0
    while pos < len(data) and len(markers) < limit:
        kind = data[pos]
        if kind not in (0x01, 0x02, 0x10):
            pos += 1
            continue
        arg: int | None = None
        body_start = pos + 1
        if kind == 0x10 and body_start < len(data):
            arg = data[body_start]
            body_start += 1
        preview, next_pos = decode_sjis_run(data, body_start, 48)
        if JAPANESE_RE.search(preview) or "$" in preview:
            markers.append(ScriptMarker(pos, kind, arg, preview))
        pos = max(pos + 1, next_pos if next_pos > pos else pos + 1)
    return markers


def scan_strings(data: bytes, min_len: int = 4, limit: int = 200) -> list[dict]:
    """Collect readable SJIS runs; skip bytes after each match (fast enough for 256 KiB)."""
    found: list[dict] = []
    i = 0
    n = len(data)
    while i < n and len(found) < limit:
        b = data[i]
        if b == 0x00 or b < 0x20 or b in (0x01, 0x02, 0x10) or b >= 0xEF:
            i += 1
            continue
        if not (0x20 <= b <= 0x7E or is_sjis_lead(b)):
            i += 1
            continue
        start = i
        text, i = decode_sjis_run(data, i, 120)
        if i == start:
            i += 1
            continue
        if len(text) >= min_len and JAPANESE_RE.search(text):
            found.append({"offset": start, "text": text})
    return found


def looks_compressed(data: bytes) -> bool:
    if len(data) < 256:
        return False
    sample = data[:4096]
    unique = len(set(sample))
    ff = sample.count(0xFF)
    zero = sample.count(0x00)
    return unique > 200 and ff + zero < len(sample) // 4


def parse_event_map(data: bytes, sector: int) -> EventMapParse:
    start = sector_to_offset(sector)
    chunk = data[start : start + SECTOR_SIZE]
    labels = find_entity_labels(chunk)
    markers = find_script_markers(chunk)

    first_label = labels[0].offset if labels else SECTOR_SIZE
    regions = [
        ParsedRegion(
            "binary_header",
            0,
            first_label,
            "tilemap / collision / bytecode (probablement compressé)",
        )
    ]
    if labels:
        npc_start = labels[-1].offset
        end_name = chunk.find(b"\x00", npc_start + 5)
        if end_name >= 0:
            npc_start = end_name + 1
        regions.append(
            ParsedRegion(
                "entity_labels",
                labels[0].offset,
                npc_start,
                "noms d'entités (préfixe 0x01 + 4×00)",
            )
        )
        tail = len(chunk) - npc_start
        if tail > 0:
            regions.append(
                ParsedRegion(
                    "npc_table",
                    npc_start,
                    len(chunk),
                    "table NPC / pointeurs script (binaire)",
                )
            )

    npc_blob_offset = None
    npc_blob_size = 0
    if labels:
        npc_blob_offset = labels[-1].offset
        end_name = chunk.find(b"\x00", npc_blob_offset + 5)
        if end_name >= 0:
            npc_blob_offset = end_name + 1
            npc_blob_size = len(chunk) - npc_blob_offset

    return EventMapParse(
        sector=sector,
        size=len(chunk),
        regions=regions,
        entities=labels,
        script_markers=markers,
        npc_blob_offset=npc_blob_offset,
        npc_blob_size=npc_blob_size,
    )


def load_overlay_blob(data: bytes, name: str) -> tuple[bytes, int, int]:
    catalog = {n: s for n, s in parse_adpos_catalog(data)}
    if name not in catalog:
        known = ", ".join(sorted(catalog))
        raise SystemExit(f"Overlay inconnu {name!r}. Connus: {known}")
    sector = catalog[name]
    start = sector_to_offset(sector)
    size = measure_overlay_size(data, sector) * SECTOR_SIZE
    return data[start : start + size], sector, size


def parse_overlay(data: bytes, name: str, *, scan_text: bool = True) -> OverlayParse:
    blob, sector, size = load_overlay_blob(data, name)
    labels = find_entity_labels(blob)
    strings = scan_strings(blob) if scan_text else []
    compressed = looks_compressed(blob)
    notes = [
        "Build: $(LD) -b vir/{name}.bin /dataseg:0000,0 {name}.o mon/ef.o mp_{name}.o",
        "Puis pack ivm2h (segments ci-dessous) et HDWRITE vers adpos_*.",
    ]
    if compressed:
        notes.append(
            "Données encore compressées (pack/ZPRESS) — séparation exacte tilemap/NPC/script "
            "nécessite ZPRESS/IVCOM (binaires absents du CD retail) ou la routine runtime dans TENGAI2.PRG."
        )
    if not labels and compressed:
        notes.append(
            "Les maps jouables 1-secteur (ex. 0x2C9) restent sur le disque hors overlay ; "
            "utiliser `parse-event` pour ce format."
        )
    return OverlayParse(
        name=name,
        sector=sector,
        size=size,
        compressed=compressed,
        segments=[dict(seg) for seg in PACK_SEGMENTS],
        strings=strings[:200],
        entity_labels=labels[:100],
        notes=notes,
    )


def write_split_overlay(data: bytes, name: str, out_dir: Path) -> None:
    write_split_with_decompress(data, name, out_dir)


def write_event_csv(path: Path, parsed: EventMapParse) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow(["section", "offset", "end", "kind", "value"])
        for region in parsed.regions:
            w.writerow(["region", f"{region.start:#x}", f"{region.end:#x}", region.name, region.notes])
        for ent in parsed.entities:
            w.writerow(["entity", f"{ent.offset:#x}", "", "label", ent.name])
        for mark in parsed.script_markers[:100]:
            w.writerow(
                [
                    "script",
                    f"{mark.offset:#x}",
                    "",
                    f"0x{mark.kind:02x}",
                    mark.preview.replace("\n", "\\n"),
                ]
            )


def cmd_info(data: bytes, name: str) -> None:
    blob, sector, size = load_overlay_blob(data, name)
    parsed = parse_overlay(data, name, scan_text=False)
    string_count = len(scan_strings(blob, limit=500))
    print(f"{parsed.name} @ secteur {sector:#x} — {size:,} octets")
    print(f"  Compressé (heuristique): {'oui' if parsed.compressed else 'non'}")
    print(f"  Labels entité trouvés: {len(parsed.entity_labels)}")
    print(f"  Chaînes SJIS lisibles (échantillon): {string_count}")
    print("  Segments pack (RAM max):")
    for seg in parsed.segments:
        print(
            f"    {seg['id']:16s} ${seg['ram_base']:04x}  max {seg['max_size']:#5x}  ({seg['role']})"
        )
    for note in parsed.notes:
        print(f"  • {note}")


def cmd_parse_overlay(data: bytes, name: str, out_dir: Path | None) -> None:
    parsed = parse_overlay(data, name)
    print(json.dumps(asdict(parsed), indent=2, ensure_ascii=False))
    if out_dir:
        out_dir.mkdir(parents=True, exist_ok=True)
        path = out_dir / f"{name}_parse.json"
        path.write_text(json.dumps(asdict(parsed), indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        print(f"Écrit {path}")


def cmd_parse_event(data: bytes, sector: int, out_dir: Path | None) -> None:
    parsed = parse_event_map(data, sector)
    print(f"Event map secteur {sector:#x}")
    for region in parsed.regions:
        print(f"  [{region.name}] {region.start:#x}..{region.end:#x} ({region.end - region.start} o) — {region.notes}")
    for ent in parsed.entities:
        print(f"  entité @{ent.offset:#x}: {ent.name}")
    print(f"  marqueurs script: {len(parsed.script_markers)}")
    if parsed.npc_blob_offset is not None:
        print(f"  blob NPC @{parsed.npc_blob_offset:#x} ({parsed.npc_blob_size} o)")
    if out_dir:
        start = sector_to_offset(sector)
        chunk = data[start : start + SECTOR_SIZE]
        out_dir.mkdir(parents=True, exist_ok=True)
        (out_dir / f"event_{sector:#x}_full.bin").write_bytes(chunk)
        if parsed.regions:
            hdr = parsed.regions[0]
            (out_dir / f"event_{sector:#x}_binary_header.bin").write_bytes(
                chunk[hdr.start : hdr.end]
            )
        if parsed.npc_blob_offset is not None:
            (out_dir / f"event_{sector:#x}_npc_table.bin").write_bytes(
                chunk[parsed.npc_blob_offset :]
            )
        write_event_csv(out_dir / f"event_{sector:#x}.csv", parsed)
        print(f"Sorties dans {out_dir}")


def cmd_split(data: bytes, name: str, out_dir: Path) -> None:
    write_split_overlay(data, name, out_dir)
    print(f"Écrit {out_dir}/{name}.bin + manifest (+ placeholders segments)")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--disc", type=Path, default=DEFAULT_TRACK2, help="Piste 2 MODE1/2352")
    sub = parser.add_subparsers(dest="command", required=True)

    info_p = sub.add_parser("info", help="Résumé d'un overlay YS.DATA")
    info_p.add_argument("name", help="adpos (yav, wa1, …)")

    parse_p = sub.add_parser("parse", help="Analyser un overlay")
    parse_p.add_argument("name")
    parse_p.add_argument("-o", "--output", type=Path, help="JSON de sortie")

    event_p = sub.add_parser("parse-event", help="Parser un secteur map événement (1×2048 o)")
    event_p.add_argument("sector", type=lambda s: int(s, 0), help="ex. 0x2C9")
    event_p.add_argument("-o", "--output", type=Path, help="Dossier de sortie")

    split_p = sub.add_parser("split", help="Extraire overlay + tenter décompression pack")
    split_p.add_argument("name")
    split_p.add_argument("-o", "--output", type=Path, required=True)

    args = parser.parse_args()
    data = load_user_data(args.disc)

    if args.command == "info":
        cmd_info(data, args.name)
    elif args.command == "parse":
        cmd_parse_overlay(data, args.name, args.output)
    elif args.command == "parse-event":
        cmd_parse_event(data, args.sector, args.output)
    elif args.command == "split":
        cmd_split(data, args.name, args.output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
